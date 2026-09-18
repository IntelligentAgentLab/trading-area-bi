# -*- coding: utf-8 -*-
"""
서울사랑상품권 × 상권  EDA(탐색적 데이터 분석) 대시보드
════════════════════════════════════════════════════════════════
인과추론(causal_app.py) '이전' 단계 — 데이터를 여러 각도에서 먼저 살펴본다.
목적: 분포·결측·커버리지·이상치·시즌성·관계를 파악해 이후 모델링 결정
     (로그변환 여부, 사용할 분기, 평행추세 가능성, 이상치 처리)을 준비.

입력(모두 선택, 올린 만큼 뷰가 열림)
  상품권: 결제내역(월별 xlsx 여러 개/zip) · 발행판매 xlsx · 가맹점 csv
  상권 자치구(2023~2025 분기): 추정매출 · 길단위인구 · 직장인구 · 점포 · 상권변화지표

성격: 순수 탐색용. 중립적 기술통계·그림만 제공하고 인과 해석은 넣지 않는다.

실행: pip install streamlit pandas numpy plotly openpyxl
      streamlit run eda_app.py
"""

import io
import re
import zipfile
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="상품권×상권 EDA", layout="wide")

GU25 = ["종로구","중구","용산구","성동구","광진구","동대문구","중랑구","성북구","강북구",
        "도봉구","노원구","은평구","서대문구","마포구","양천구","강서구","구로구","금천구",
        "영등포구","동작구","관악구","서초구","강남구","송파구","강동구"]
YEARS = (2023, 2024, 2025)

# ════════════════════════════════════════════════════════════════
# GitHub Raw URL 로딩 함수 추가
# ════════════════════════════════════════════════════════════════
# 1. 일반 CSV / 텍스트 파일 불러오기용 (캐싱 적용)
import io
import requests
import pandas as pd
import streamlit as st

@st.cache_data(show_spinner=False)
def load_csv_from_url(url):
    try:
        # 1. requests로 URL의 바이너리 데이터를 직접 수신 (URL 한글 처리 자동)
        res = requests.get(url)
        res.raise_for_status()
        
        # 2. 한글 파일 인코딩(CP949/EUC-KR, UTF-8 등)을 순차적으로 시도하여 읽기
        content = res.content
        for enc in ("cp949", "utf-8-sig", "utf-8"):
            try:
                return pd.read_csv(io.BytesIO(content), encoding=enc)
            except (UnicodeDecodeError, Exception):
                continue
                
        # 3. 예외 처리용 디코딩
        return pd.read_csv(io.BytesIO(content), encoding="cp949", encoding_errors="ignore")
        
    except Exception as e:
        st.error(f"CSV 로드 실패 ({url}): {e}")
        return None

# 2. 바이너리 파일 (Excel, ZIP 등) 불러오기용 (캐싱 적용)
@st.cache_data(show_spinner=False)
def fetch_binary_from_url(url):
    try:
        res = requests.get(url)
        res.raise_for_status()
        return res.content
    except Exception as e:
        st.error(f"파일 다운로드 실패 ({url}): {e}")
        return None

# ════════════════════════════════════════════════════════════════
# 유틸 & 로더 (causal_app 검증본 재사용)
# ════════════════════════════════════════════════════════════════
def num(s):
    return pd.to_numeric(s, errors="coerce")


def _norm(s):
    return re.sub(r"[\s_~\-]", "", str(s)).lower()


def find_col(df, *kw, exclude=()):
    for c in df.columns:
        n = _norm(c)
        if all(k in n for k in kw) and not any(e in n for e in exclude):
            return c
    return None


@st.cache_data(show_spinner=False)
def read_table(b):
    def ok(df):
        j = " ".join(map(str, df.columns)).lower()
        return df.shape[1] >= 2 and any(k in j for k in
            ("자치구","상권","기준","코드","인구","매출","점포","업종","signgu","trdar","selng","flpop","stor"))
    for enc in ("cp949", "utf-8-sig", "utf-8"):
        try:
            df = pd.read_csv(io.BytesIO(b), encoding=enc, sep=None, engine="python")
        except Exception:
            try:
                df = pd.read_csv(io.BytesIO(b), encoding=enc)
            except Exception:
                continue
        if ok(df):
            return df
    return pd.read_csv(io.BytesIO(b), encoding="cp949", encoding_errors="ignore")


def gu_name_col(df):
    return (find_col(df, "자치구코드", "명") or find_col(df, "signgu", "cd", "nm")
            or find_col(df, "자치구", "명") or find_col(df, "자치구") or find_col(df, "시군구", "명"))


def induty_col(df):
    return (find_col(df, "서비스업종코드명") or find_col(df, "svc", "induty", "nm")
            or find_col(df, "업종", "명", exclude=("자치구", "상권")))


def quarter_col(df):
    return (find_col(df, "기준", "분기") or find_col(df, "stdr", "yyqu")
            or find_col(df, "년분기") or find_col(df, "yyqu", "cd"))


def parse_yq(v):
    m = re.match(r"(\d{4})Q?(\d)$", str(v).strip().upper())
    return (int(m.group(1)), int(m.group(2))) if m else None


def agg_gu_quarter(df, val_col, how="sum"):
    nc, qc = gu_name_col(df), quarter_col(df)
    if not (nc and qc and val_col and val_col in df.columns):
        return None
    s = df[[nc, qc, val_col]].copy()
    s[val_col] = num(s[val_col])
    yq = s[qc].map(parse_yq)
    s = s[yq.notna()].copy()
    s["year"] = [a for a, _ in yq[yq.notna()]]
    s["q"] = [b for _, b in yq[yq.notna()]]
    s = s[s["year"].isin(YEARS)]
    g = s.groupby(["gu" if False else nc, "year", "q"])[val_col]
    out = (g.sum() if how == "sum" else g.mean()).reset_index()
    out.columns = ["gu", "year", "q", "val"]
    out["gu"] = out["gu"].astype(str).str.strip()
    return out[out["gu"].isin(GU25)]


def _payment_one(name, b):
    base = str(name).split("/")[-1]
    nums = re.findall(r"\d+", base)
    if len(nums) < 2:
        return None
    yy, mm = 2000 + int(nums[0]) % 100, int(nums[1])
    df = pd.read_excel(io.BytesIO(b), sheet_name=0, header=0)
    idc = df.columns[0]
    inds = [c for c in df.columns[1:] if str(c) != "합계"]
    lo = df.melt(id_vars=idc, value_vars=inds, var_name="업종", value_name="순결제액")
    lo = lo.rename(columns={idc: "발행처"})
    lo["year"], lo["month"], lo["q"] = yy, mm, (mm - 1) // 3 + 1
    return lo


@st.cache_data(show_spinner=False)
def load_payment(files):
    frames = []
    for name, b in files:
        if str(name).lower().endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(b))

            def fix(n):
                for enc in ("euc-kr", "utf-8"):
                    try:
                        return n.encode("cp437").decode(enc)
                    except Exception:
                        pass
                return n
            for n in z.namelist():
                if n.lower().endswith(".xlsx"):
                    fr = _payment_one(fix(n), z.read(n))
                    if fr is not None:
                        frames.append(fr)
        elif str(name).lower().endswith((".xlsx", ".xls")):
            fr = _payment_one(name, b)
            if fr is not None:
                frames.append(fr)
    if not frames:
        return None
    d = pd.concat(frames, ignore_index=True)
    d["순결제액"] = num(d["순결제액"]).fillna(0)
    d["발행처"] = d["발행처"].astype(str).str.strip()
    d["업종"] = d["업종"].astype(str).str.strip()
    d["구분"] = np.where(d["발행처"].isin(GU25), "자치구", "기타")
    d["연월"] = d["year"].astype(str) + "-" + d["month"].astype(str).str.zfill(2)
    return d


@st.cache_data(show_spinner=False)
def load_issue(b):
    xls = pd.ExcelFile(io.BytesIO(b))
    fr = []
    for sn in xls.sheet_names:
        m = re.match(r"\s*(\d+)\s*년\s*(\d+)\s*월", str(sn))
        if not m:
            continue
        yy, mm = 2000 + int(m.group(1)), int(m.group(2))
        df = pd.read_excel(xls, sheet_name=sn, header=0).iloc[:, :3]
        df.columns = ["발행처", "발행액", "판매액"]
        df = df[df["발행처"].notna()]
        df = df[~df["발행처"].astype(str).str.contains("합계|계$", regex=True)]
        df["year"], df["month"], df["q"] = yy, mm, (mm - 1) // 3 + 1
        fr.append(df)
    d = pd.concat(fr, ignore_index=True)
    for c in ("발행액", "판매액"):
        d[c] = num(d[c]).fillna(0)
    d["발행처"] = d["발행처"].astype(str).str.strip()
    d["연월"] = d["year"].astype(str) + "-" + d["month"].astype(str).str.zfill(2)
    return d[d["발행처"].isin(GU25)]


@st.cache_data(show_spinner=False)
def load_merchant(b):
    df = read_table(b)
    gc = find_col(df, "자치구", "명") or find_col(df, "자치구")
    ic = find_col(df, "서울페이업종") or find_col(df, "업종", "명") or find_col(df, "업종")
    if not (gc and ic):
        return None
    m = df[[gc, ic]].copy()
    m.columns = ["gu", "업종"]
    m["gu"] = m["gu"].astype(str).str.strip()
    m["업종"] = m["업종"].astype(str).str.strip()
    return m[m["gu"].isin(GU25)]


# ════════════════════════════════════════════════════════════════
# 통합 자치구×분기 EDA 패널
# ════════════════════════════════════════════════════════════════
def build_panel(pay, iss, sales_b, flow_b, work_b, store_b, change_b):
    base = pd.MultiIndex.from_product(
        [GU25, YEARS, (1, 2, 3, 4)], names=["gu", "year", "q"]).to_frame(index=False)
    panel = base

    def join_metric(g, name):
        nonlocal panel
        if g is not None:
            panel = panel.merge(g.rename(columns={"val": name}), on=["gu", "year", "q"], how="left")

    if iss is not None:
        isq = (iss.groupby(["발행처", "year", "q"]).agg(발행=("발행액", "sum"), 판매=("판매액", "sum"))
               .reset_index().rename(columns={"발행처": "gu"}))
        panel = panel.merge(isq, on=["gu", "year", "q"], how="left")
    if pay is not None:
        pq = (pay[pay["구분"] == "자치구"].groupby(["발행처", "year", "q"])["순결제액"].sum()
              .reset_index().rename(columns={"발행처": "gu", "순결제액": "결제"}))
        panel = panel.merge(pq, on=["gu", "year", "q"], how="left")
    if sales_b is not None:
        sa = read_table(sales_b)
        amt = find_col(sa, "당월", "매출금액") or find_col(sa, "thsmon", "selng", "amt") or find_col(sa, "매출", "금액")
        join_metric(agg_gu_quarter(sa, amt, "sum"), "매출")
    for b, nm, kwfn, how in [
        (flow_b, "유동인구", lambda df: find_col(df, "총", "유동인구수") or find_col(df, "tot", "flpop"), "mean"),
        (work_b, "직장인구", lambda df: find_col(df, "총", "직장", "인구") or find_col(df, "tot", "wrc", "popltn") or find_col(df, "tot", "work"), "mean"),
        (store_b, "점포수", lambda df: find_col(df, "전체", "점포수") or find_col(df, "점포수", exclude=("유사","개업","폐업","프랜차이즈","일반")) or find_col(df, "stor", "co", exclude=("similr","opbiz","clsbiz","frc")), "mean"),
        (change_b, "영업개월", lambda df: find_col(df, "운영", "영업", "개월", exclude=("서울",)) or find_col(df, "opr", "sale", exclude=("se",)), "mean"),
    ]:
        if b is not None:
            df = read_table(b)
            join_metric(agg_gu_quarter(df, kwfn(df), how), nm)

    panel["분기"] = panel["year"].astype(str) + "Q" + panel["q"].astype(str)
    panel["tidx"] = panel["year"] * 4 + (panel["q"] - 1)
    # 파생지표
    if {"발행", "판매"} <= set(panel.columns):
        panel["판매율"] = panel["판매"] / panel["발행"].replace(0, np.nan)
    if {"결제", "매출"} <= set(panel.columns):
        panel["결제_매출비"] = panel["결제"] / panel["매출"].replace(0, np.nan)
    if {"매출", "유동인구"} <= set(panel.columns):
        panel["유동인구당매출"] = panel["매출"] / panel["유동인구"].replace(0, np.nan)
    return panel


METRICS_ALL = ["발행", "판매", "결제", "매출", "유동인구", "직장인구", "점포수", "영업개월",
               "판매율", "결제_매출비", "유동인구당매출"]


# ════════════════════════════════════════════════════════════════
# 사이드바 (기존 file_uploader ➔ Raw URL 읽기로 변경)
# ════════════════════════════════════════════════════════════════
st.title("🔬 서울사랑상품권 × 상권  EDA 대시보드")
st.caption("인과추론 이전 단계 — 데이터를 여러 각도로 살펴봅니다. 분포·결측·커버리지·시즌성·관계.")

# ⚠️ 본인의 GitHub 사용자명 / 리포지토리명 / 브랜치명에 맞춰 BASE_URL 설정
GITHUB_BASE_URL = "https://raw.githubusercontent.com/kwjw0/trading-area-bi/namjiwoo"

with st.sidebar:
    st.header("⚙️ 데이터 로드 설정")
    st.info("GitHub Raw URL을 통해 지정된 경로에서 데이터를 자동으로 가져옵니다.")

# ----------------------------------------------------------------
# 1. 파일 경로 설정 (GitHub 리포지토리 상대 경로 지정)
# ----------------------------------------------------------------
# 상권 자치구 데이터 CSV 경로 (예시)
sales_url  = f"{GITHUB_BASE_URL}/data/raw/seoul%20trading-area/서울시상권분석서비스(추정매출-자치구).csv" 
flow_url   = f"{GITHUB_BASE_URL}/data/raw/seoul%20trading-area/서울시상권분석서비스(길단위인구-자치구).csv"
work_url   = f"{GITHUB_BASE_URL}/data/raw/seoul%20trading-area/서울시상권분석서비스(직장인구-자치구).csv"
store_url  = f"{GITHUB_BASE_URL}/data/raw/seoul%20trading-area/서울시상권분석서비스(점포-자치구).csv"
change_url = f"{GITHUB_BASE_URL}/data/raw/seoul%20trading-area/서울시상권분석서비스(상권변화지표-자치구).csv"

# 상품권 데이터 경로 (예시 - 필요시 실제 파일 이름으로 변경)
payments_zip_url = [f"{GITHUB_BASE_URL}/data/raw/seoul%20trading-area/2023년_자치구별_업종별_서울사랑상품권_결제내역.zip",
                    f"{GITHUB_BASE_URL}/data/raw/seoul%20trading-area/2024년_자치구별_업종별_서울사랑상품권_결제내역.zip",
                    f"{GITHUB_BASE_URL}/data/raw/seoul%20trading-area/2025년_자치구별_업종별_서울사랑상품권_결제내역.zip"]
issue_url  = f"{GITHUB_BASE_URL}/data/raw/seoul%20trading-area/월별%20서울사랑상품권_발행_및_판매현황(202404~202603).xlsx"
merchant_url = f"{GITHUB_BASE_URL}/data/raw/seoul%20trading-area/서울사랑상품권_유효_가맹점(25.8.22_기준).csv"

# ----------------------------------------------------------------
# 2. 데이터 가져오기 및 가공
# ----------------------------------------------------------------
# (1) CSV 상권 데이터 로드
df_sales  = load_csv_from_url(sales_url)
df_flow   = load_csv_from_url(flow_url)
df_work   = load_csv_from_url(work_url)
df_store  = load_csv_from_url(store_url)
df_change = load_csv_from_url(change_url)

# (2) 결제내역 ZIP 파일 3개 순회 수신
payment_files = []
for url in payments_zip_urls:
    b = fetch_binary_from_url(url)
    if b:
        filename = url.split("/")[-1]
        payment_files.append((filename, b))

# 3개 ZIP 파일 바이너리가 포함된 리스트 전달
pay = load_payment(payment_files) if payment_files else None

# (3) 발행 및 가맹점 파일 처리
issue_bytes = fetch_binary_from_url(issue_url)
iss = load_issue(issue_bytes) if issue_bytes else None

merchant_bytes = fetch_binary_from_url(merchant_url)
mer = load_merchant(merchant_bytes) if merchant_bytes else None

# ----------------------------------------------------------------
# 3. 통합 패널 빌드
# ----------------------------------------------------------------
panel = build_panel(pay, iss, df_sales, df_flow, df_work, df_store, df_change)
have = [m for m in METRICS_ALL if m in panel.columns and panel[m].notna().any()]

# (이하 대시보드 탭 t0~t5 로직은 기존과 동일)

# ════════════════════════════════════════════════════════════════
# 탭
# ════════════════════════════════════════════════════════════════
t0, t1, t2, t3, t4, t5 = st.tabs(
    ["📋 데이터 품질·커버리지", "📈 시계열 추이", "📊 분포·이상치",
     "🏙️ 자치구 비교", "🏷️ 업종 구조", "🔗 관계 탐색"])

# ── 데이터 품질·커버리지 ────────────────────────────────────────
with t0:
    st.markdown("#### 지표별 요약 (자치구×분기 패널 기준)")
    rows = []
    for m in have:
        s = panel[m]
        rows.append(dict(지표=m, 관측치=int(s.notna().sum()),
                         결측률=f"{s.isna().mean()*100:.0f}%",
                         영값비율=f"{(s.fillna(0)==0).mean()*100:.0f}%",
                         최소=f"{np.nanmin(s):,.0f}" if s.notna().any() else "",
                         중앙값=f"{np.nanmedian(s):,.0f}" if s.notna().any() else "",
                         최대=f"{np.nanmax(s):,.0f}" if s.notna().any() else ""))
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("영값비율이 높은 지표(예: 발행)는 특정 분기에만 값이 있음을 뜻합니다. "
               "결측률이 높으면 그 데이터의 분기 범위가 2023~2025 전체를 덮지 못한 것입니다.")

    st.markdown("#### 데이터 커버리지 — 지표가 존재하는 (자치구·분기) 셀")
    if have:
        mm = st.selectbox("커버리지를 볼 지표", have, key="cov")
        cov = panel.pivot_table(index="gu", columns="분기", values=mm,
                                aggfunc=lambda x: 1 if x.notna().any() and (x.fillna(0) != 0).any() else 0,
                                fill_value=0).reindex([g for g in GU25 if g in panel["gu"].unique()])
        fig = px.imshow(cov, color_continuous_scale=[[0, "#eee"], [1, "#2f6fed"]],
                        aspect="auto", title=f"'{mm}' 값이 있는 셀(파랑=있음)")
        fig.update_layout(height=620, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("인과추정은 처치(발행)와 결과(매출)가 함께 존재하는 분기에서만 가능합니다. "
                   "이 그림으로 사용 가능한 분석 창을 먼저 확인하세요.")

# ── 시계열 추이 ─────────────────────────────────────────────────
with t1:
    st.markdown("#### 월별 추이 (상품권 원자료)")
    if pay is not None or iss is not None:
        fig = go.Figure()
        if iss is not None:
            m = iss.groupby("연월").agg(발행=("발행액", "sum"), 판매=("판매액", "sum")).reset_index()
            fig.add_bar(x=m["연월"], y=m["발행"] / 1e8, name="발행(억)", opacity=0.5)
            fig.add_scatter(x=m["연월"], y=m["판매"] / 1e8, name="판매(억)", mode="lines+markers")
        if pay is not None:
            pm = pay[pay["구분"] == "자치구"].groupby("연월")["순결제액"].sum().reset_index()
            fig.add_scatter(x=pm["연월"], y=pm["순결제액"] / 1e8, name="결제(억)",
                            mode="lines+markers", line=dict(dash="dot"))
        fig.update_layout(title="월별 발행·판매·결제", yaxis_title="억원", legend_title="")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("설·추석 직전 달의 발행 급증(시즌성)을 확인하세요. 결제는 업로드된 월 범위에만 표시됩니다.")

    st.markdown("#### 분기별 추이 (상권 지표)")
    q_metrics = [m for m in ["매출", "유동인구", "직장인구", "점포수"] if m in have]
    if q_metrics:
        mm = st.selectbox("지표", q_metrics, key="qtrend")
        by_q = panel.groupby("분기")[mm].sum(min_count=1).reset_index()
        st.plotly_chart(px.line(by_q, x="분기", y=mm, markers=True,
                                title=f"분기별 {mm}(자치구 합)"), use_container_width=True)
        sel = st.multiselect("자치구 겹쳐보기(선택)", GU25, default=[], key="qtrend_gu")
        if sel:
            sub = panel[panel["gu"].isin(sel)]
            st.plotly_chart(px.line(sub, x="분기", y=mm, color="gu", markers=True,
                                    title=f"자치구별 {mm} 추이"), use_container_width=True)
    else:
        st.caption("상권 지표 파일을 올리면 분기 추이가 표시됩니다.")

# ── 분포·이상치 ─────────────────────────────────────────────────
with t2:
    st.markdown("#### 지표 분포 (자치구×분기 값)")
    if have:
        mm = st.selectbox("지표 선택", have, key="dist")
        logy = st.checkbox("로그 스케일(왜도 큰 금액 지표에 유용)", value=False)
        s = panel[["gu", "분기", mm]].dropna()
        vals = s[mm]
        c1, c2 = st.columns(2)
        h = px.histogram(s, x=mm, nbins=30, title=f"{mm} 히스토그램")
        b = px.box(s, y=mm, points="outliers", title=f"{mm} 박스플롯")
        if logy and (vals > 0).all():
            h.update_xaxes(type="log"); b.update_yaxes(type="log")
        c1.plotly_chart(h, use_container_width=True)
        c2.plotly_chart(b, use_container_width=True)
        # IQR 이상치
        q1, q3 = vals.quantile(.25), vals.quantile(.75)
        iqr = q3 - q1
        out = s[(vals < q1 - 1.5 * iqr) | (vals > q3 + 1.5 * iqr)].sort_values(mm, ascending=False)
        st.markdown(f"**IQR 이상치 {len(out)}건** (1.5×IQR 밖)")
        if len(out):
            st.dataframe(out.rename(columns={"gu": "자치구", mm: mm}).head(20),
                         use_container_width=True, hide_index=True)
        st.caption("금액 지표가 오른쪽으로 크게 치우쳐 있으면 이후 회귀에서 로그변환이 필요하다는 신호입니다.")

# ── 자치구 비교 ─────────────────────────────────────────────────
with t3:
    st.markdown("#### 자치구 비교")
    if have:
        mm = st.selectbox("지표", have, key="cs")
        agg = st.radio("집계", ["기간 합", "기간 평균"], horizontal=True)
        g = (panel.groupby("gu")[mm].sum(min_count=1) if agg == "기간 합"
             else panel.groupby("gu")[mm].mean()).dropna().sort_values(ascending=False).reset_index()
        st.plotly_chart(px.bar(g, x=mm, y="gu", orientation="h", title=f"자치구별 {mm} ({agg})")
                        .update_layout(yaxis=dict(autorange="reversed"), height=650, yaxis_title=""),
                        use_container_width=True)
        st.markdown("#### 자치구 × 분기 히트맵")
        piv = panel.pivot_table(index="gu", columns="분기", values=mm, aggfunc="sum")
        piv = piv.reindex([x for x in GU25 if x in piv.index])
        st.plotly_chart(px.imshow(piv, aspect="auto", color_continuous_scale="YlOrRd",
                                  title=f"{mm} 히트맵").update_layout(height=650),
                        use_container_width=True)

# ── 업종 구조 ───────────────────────────────────────────────────
with t4:
    st.markdown("#### 업종 구조 (상품권)")
    if pay is None and mer is None:
        st.info("결제내역 또는 가맹점 파일을 올리면 표시됩니다.")
    if pay is not None:
        gu = pay[pay["구분"] == "자치구"]
        bi = (gu.groupby("업종")["순결제액"].sum() / 1e8).sort_values(ascending=False).reset_index()
        bi.columns = ["업종", "순결제액(억)"]
        st.plotly_chart(px.bar(bi, x="순결제액(억)", y="업종", orientation="h",
                               title="업종별 순결제액").update_layout(
                               yaxis=dict(autorange="reversed"), height=560),
                        use_container_width=True)
    if mer is not None:
        bm = mer.groupby("업종").size().sort_values(ascending=False).reset_index()
        bm.columns = ["업종", "가맹점수"]
        st.plotly_chart(px.bar(bm, x="가맹점수", y="업종", orientation="h",
                               title="업종별 가맹점 수").update_layout(
                               yaxis=dict(autorange="reversed"), height=560),
                        use_container_width=True)
    if pay is not None and mer is not None:
        pj = pay[pay["구분"] == "자치구"].groupby("업종")["순결제액"].sum()
        mj = mer.groupby("업종").size()
        j = pd.concat([pj.rename("결제"), mj.rename("가맹점수")], axis=1).dropna()
        j["가맹점당결제(만원)"] = j["결제"] / j["가맹점수"] / 1e4
        st.markdown("**업종별 가맹점당 결제액** (가맹점 1곳이 얼마나 결제를 일으키나)")
        jj = j.sort_values("가맹점당결제(만원)", ascending=False).reset_index()
        st.plotly_chart(px.bar(jj, x="가맹점당결제(만원)", y="업종", orientation="h")
                        .update_layout(yaxis=dict(autorange="reversed"), height=560, yaxis_title=""),
                        use_container_width=True)

# ── 관계 탐색 ───────────────────────────────────────────────────
with t5:
    st.markdown("#### 지표 간 관계 (가설 발굴용 — 인과 아님)")
    numcols = [m for m in have]
    if len(numcols) < 2:
        st.info("서로 다른 데이터 2종 이상을 올리면 지표 간 관계를 볼 수 있습니다.")
    else:
        unit = st.radio("분석 단위", ["자치구(기간 합산)", "자치구×분기"], horizontal=True)
        if unit.startswith("자치구("):
            base = panel.groupby("gu")[numcols].sum(min_count=1)
        else:
            base = panel.set_index(["gu", "분기"])[numcols]
        c1, c2 = st.columns(2)
        x = c1.selectbox("X", numcols, index=0)
        y = c2.selectbox("Y", numcols, index=min(1, len(numcols) - 1))
        d2 = base[[x, y]].dropna().reset_index()
        if len(d2) >= 3:
            sc = px.scatter(d2, x=x, y=y, hover_data=d2.columns, title=f"{x} vs {y}",
                            text="gu" if "gu" in d2.columns and unit.startswith("자치구(") else None)
            if unit.startswith("자치구("):
                sc.update_traces(textposition="top center")
            st.plotly_chart(sc, use_container_width=True)
            st.caption(f"피어슨 상관 r = {d2[x].corr(d2[y]):+.2f} · 관측치 {len(d2)}개. "
                       "상관은 규모 교란을 포함할 수 있어 인과가 아닙니다(인과는 causal_app 참조).")
        st.markdown("#### 상관행렬")
        cor = base.corr()
        st.plotly_chart(px.imshow(cor, text_auto=".2f", color_continuous_scale="RdBu_r",
                                  zmin=-1, zmax=1, aspect="auto", title="지표 상관행렬")
                        .update_layout(height=600), use_container_width=True)

st.divider()
st.caption("EDA 전용 — 기술통계·그림만 제공합니다. 인과 추정(이벤트스터디·DiD·삼중차분)은 causal_app.py에서. "
           "기간 2023~2025.")
