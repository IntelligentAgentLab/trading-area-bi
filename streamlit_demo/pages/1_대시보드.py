# -*- coding: utf-8 -*-
"""
서울사랑상품권 × 상권 5종  자치구 통합 심층 대시보드
════════════════════════════════════════════════════════════════
결합(자치구명 공통키):
  · 상품권      월별 발행/판매 현황 xlsx      → 발행/판매/판매율
  · 상권매출    추정매출-자치구   OA-22176
  · 유동인구    길단위인구-자치구
  · 직장인구    직장인구-자치구
  · 점포        점포-자치구       OA-22173     → 점포수/개폐업/프랜차이즈
  · 생애주기    상권변화지표-자치구 OA-15567    → LL/LH/HL/HH·영업개월

설계 원칙 — "객관적으로 모든 정보를 보여준다"
  1. 통합 자치구 테이블 원본을 그대로 노출 + 전체 상관행렬 공개(체리피킹 금지)
  2. 규모 교란 제거: 정규화(÷유동인구/직장인구/점포수) 토글로 상관이 규모 때문인지 확인
  3. 편상관(통제변수의 영향을 잔차로 제거한 상관)까지 표시
  4. 인과는 '관찰된 사실'과 '해석(추정)'을 화면에서 분리해 표기

집계규칙: 매출·상품권=기간 합 / 유동인구·직장인구·점포수·영업개월=분기 평균
         (점포는 업종 합산 후 분기 평균) / 생애주기=최신 분기 등급

실행: pip install streamlit pandas plotly openpyxl
      streamlit run giftcard_app.py
"""

import io
import re
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="상품권×상권 통합 대시보드", layout="wide")

GU25 = ["종로구","중구","용산구","성동구","광진구","동대문구","중랑구","성북구","강북구",
        "도봉구","노원구","은평구","서대문구","마포구","양천구","강서구","구로구","금천구",
        "영등포구","동작구","관악구","서초구","강남구","송파구","강동구"]
LIFECYCLE = {"LL": "다이나믹", "LH": "상권확장", "HL": "상권축소", "HH": "정체"}


# ════════════════════════════════════════════════════════════════
# 공통 유틸: 로더 / 컬럼 인식 / 숫자화
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
def read_table(file_bytes):
    """cp949/utf-8 + 쉼표/탭 자동 인식(잘못 잡으면 컬럼 깨져 예외 없이 통과하므로 검증)."""
    def ok(df):
        j = " ".join(map(str, df.columns)).lower()
        return df.shape[1] >= 2 and any(k in j for k in
            ("자치구","상권","기준","코드","인구","매출","점포","signgu","trdar","selng","flpop","stor"))
    for enc in ("cp949", "utf-8-sig", "utf-8"):
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, sep=None, engine="python")
        except Exception:
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
            except Exception:
                continue
        if ok(df):
            return df
    return pd.read_csv(io.BytesIO(file_bytes), encoding="cp949", encoding_errors="ignore")


def gu_name_col(df):
    return (find_col(df, "자치구코드", "명") or find_col(df, "signgu", "cd", "nm")
            or find_col(df, "자치구", "명") or find_col(df, "시군구", "명"))


def quarter_col(df):
    return (find_col(df, "기준", "분기") or find_col(df, "stdr", "yyqu")
            or find_col(df, "년분기") or find_col(df, "yyqu", "cd"))


def agg_gu(df, val_col, over_time="sum"):
    """자치구별 집계. 업종이 있으면 (자치구,분기) 업종합 후, 분기축은 over_time으로."""
    if val_col is None or val_col not in df.columns:
        return None
    nc, qc = gu_name_col(df), quarter_col(df)
    if nc is None:
        return None
    s = df[[c for c in (nc, qc, val_col) if c]].copy()
    s[val_col] = num(s[val_col])
    if qc:
        per_q = s.groupby([nc, qc])[val_col].sum()      # 업종 합산(있으면)
        out = per_q.groupby(level=0).sum() if over_time == "sum" else per_q.groupby(level=0).mean()
    else:
        out = s.groupby(nc)[val_col].sum() if over_time == "sum" else s.groupby(nc)[val_col].mean()
    out.index = out.index.astype(str).str.strip()
    return out


# ════════════════════════════════════════════════════════════════
# 상품권 로더
# ════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def load_gift(file_bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    frames = []
    for sn in xls.sheet_names:
        m = re.match(r"\s*(\d+)\s*년\s*(\d+)\s*월", str(sn))
        if not m:
            continue
        yy, mm = 2000 + int(m.group(1)), int(m.group(2))
        df = pd.read_excel(xls, sheet_name=sn, header=0).iloc[:, :3]
        df.columns = ["발행처", "발행액", "판매액"]
        df = df[df["발행처"].notna()]
        df = df[~df["발행처"].astype(str).str.contains("합계|계$", regex=True)]
        df["연"], df["월"] = yy, mm
        df["연월"] = f"{yy}-{mm:02d}"
        df["분기"] = f"{yy}Q{(mm-1)//3+1}"
        frames.append(df)
    d = pd.concat(frames, ignore_index=True)
    d["발행액"] = num(d["발행액"]).fillna(0)
    d["판매액"] = num(d["판매액"]).fillna(0)
    d["판매율"] = np.where(d["발행액"] > 0, d["판매액"] / d["발행액"], np.nan)
    d["구분"] = np.where(d["발행처"].isin(GU25), "자치구", "서울광역")
    return d


# ════════════════════════════════════════════════════════════════
# 통계 유틸: 편상관
# ════════════════════════════════════════════════════════════════
def residual(control, target):
    m = np.isfinite(control) & np.isfinite(target)
    if m.sum() < 3:
        return np.full_like(target, np.nan, dtype=float)
    b1, b0 = np.polyfit(control[m], target[m], 1)
    res = np.full_like(target, np.nan, dtype=float)
    res[m] = target[m] - (b0 + b1 * control[m])
    return res


def partial_corr(df, x, y, ctrl):
    sub = df[[x, y, ctrl]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(sub) < 4:
        return np.nan, len(sub)
    rx = residual(sub[ctrl].values, sub[x].values)
    ry = residual(sub[ctrl].values, sub[y].values)
    ok = np.isfinite(rx) & np.isfinite(ry)
    if ok.sum() < 3:
        return np.nan, int(ok.sum())
    return float(np.corrcoef(rx[ok], ry[ok])[0, 1]), int(ok.sum())


# ════════════════════════════════════════════════════════════════
# 사이드바 — 업로드
# ════════════════════════════════════════════════════════════════
st.title("💳🏙️ 서울사랑상품권 × 상권 통합 심층 대시보드")
st.caption("상품권 발행·판매를 상권 매출·유동인구·직장인구·점포·생애주기와 자치구 단위로 결합합니다. "
           "상관은 인과가 아니며, 규모 교란을 걷어내는 정규화·편상관을 함께 제공합니다.")

with st.sidebar:
    st.header("① 상품권 (필수)")
    f_gift = st.file_uploader("월별 발행·판매 현황 xlsx", type=["xlsx"], key="g")
    st.header("② 상권 자치구 (선택 · 올릴수록 심층)")
    f_sales = st.file_uploader("추정매출-자치구 (OA-22176)", type=["csv","txt","tsv"], key="s")
    f_flow = st.file_uploader("길단위인구-자치구 (유동인구)", type=["csv","txt","tsv"], key="f")
    f_worker = st.file_uploader("직장인구-자치구", type=["csv","txt","tsv"], key="w")
    f_store = st.file_uploader("점포-자치구 (OA-22173)", type=["csv","txt","tsv"], key="st")
    f_change = st.file_uploader("상권변화지표-자치구 (OA-15567)", type=["csv","txt","tsv"], key="c")

if f_gift is None:
    st.info("상품권 월별 발행·판매 파일을 올리면 시작합니다. 상권 자치구 파일들을 추가할수록 "
            "통합 상관·편상관·시계열 오버레이가 확장됩니다.")
    st.stop()

d = load_gift(f_gift.getvalue())
gg_all = d[d["구분"] == "자치구"].copy()


# ════════════════════════════════════════════════════════════════
# 통합 자치구 feature table 구축
# ════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=True)
def build_features(gift_bytes, sales_b, flow_b, worker_b, store_b, change_b):
    g = load_gift(gift_bytes)
    gu = g[g["구분"] == "자치구"]
    feat = gu.groupby("발행처").agg(상품권발행=("발행액", "sum"),
                                    상품권판매=("판매액", "sum")).copy()
    feat["상품권판매율"] = feat["상품권판매"] / feat["상품권발행"].replace(0, np.nan)
    feat.index = feat.index.astype(str).str.strip()
    life = None

    if sales_b is not None:
        sa = read_table(sales_b)
        col = find_col(sa, "당월", "매출금액") or find_col(sa, "thsmon", "selng", "amt") or find_col(sa, "매출", "금액")
        s = agg_gu(sa, col, "sum")
        if s is not None:
            feat = feat.join(s.rename("상권매출"))
    if flow_b is not None:
        fa = read_table(flow_b)
        col = find_col(fa, "총", "유동인구수") or find_col(fa, "tot", "flpop")
        s = agg_gu(fa, col, "mean")
        if s is not None:
            feat = feat.join(s.rename("유동인구"))
    if worker_b is not None:
        wa = read_table(worker_b)
        col = (find_col(wa, "총", "직장", "인구") or find_col(wa, "총", "직장인구수")
               or find_col(wa, "tot", "wrc", "popltn") or find_col(wa, "tot", "work"))
        s = agg_gu(wa, col, "mean")
        if s is not None:
            feat = feat.join(s.rename("직장인구"))
    if store_b is not None:
        sta = read_table(store_b)
        c_cnt = (find_col(sta, "전체", "점포수") or
                 find_col(sta, "점포수", exclude=("유사","개업","폐업","프랜차이즈","일반")) or
                 find_col(sta, "stor", "co", exclude=("similr","opbiz","clsbiz","frc")))
        c_op = find_col(sta, "개업", "점포수") or find_col(sta, "opbiz", "stor", "co")
        c_cl = find_col(sta, "폐업", "점포수") or find_col(sta, "clsbiz", "stor", "co")
        c_fr = find_col(sta, "프랜차이즈", "점포수") or find_col(sta, "frc", "stor", "co")
        for col, name in [(c_cnt, "점포수"), (c_op, "개업점포"), (c_cl, "폐업점포"), (c_fr, "프랜차이즈수")]:
            s = agg_gu(sta, col, "mean")
            if s is not None:
                feat = feat.join(s.rename(name))
        if {"개업점포", "폐업점포"} <= set(feat.columns):
            feat["순출점"] = feat["개업점포"] - feat["폐업점포"]
    if change_b is not None:
        ca = read_table(change_b)
        c_op = find_col(ca, "운영", "영업", "개월", exclude=("서울",)) or find_col(ca, "opr", "sale", exclude=("se",))
        s = agg_gu(ca, c_op, "mean")
        if s is not None:
            feat = feat.join(s.rename("운영영업개월"))
        c_code = find_col(ca, "변화지표", exclude=("명",)) or find_col(ca, "trdar", "chnge", "ix", exclude=("nm",))
        nc, qc = gu_name_col(ca), quarter_col(ca)
        if c_code and nc:
            cc = ca[[nc, qc, c_code]].copy() if qc else ca[[nc, c_code]].copy()
            if qc:
                cc = cc.sort_values(qc).groupby(nc).tail(1)     # 최신 분기 등급
            life = cc.set_index(cc[nc].astype(str).str.strip())[c_code].astype(str).str.strip().str.upper()

    # 파생(강도) 지표
    if "상권매출" in feat and "유동인구" in feat:
        feat["유동인구당상권매출"] = feat["상권매출"] / feat["유동인구"].replace(0, np.nan)
    if "상권매출" in feat and "점포수" in feat:
        feat["점포당상권매출"] = feat["상권매출"] / feat["점포수"].replace(0, np.nan)
    if "직장인구" in feat and "유동인구" in feat:
        feat["오피스지수"] = feat["직장인구"] / feat["유동인구"].replace(0, np.nan)
    feat = feat[feat.index.isin(GU25)]
    return feat, (life.reindex(feat.index) if life is not None else None)


feat, life = build_features(
    f_gift.getvalue(),
    f_sales.getvalue() if f_sales else None,
    f_flow.getvalue() if f_flow else None,
    f_worker.getvalue() if f_worker else None,
    f_store.getvalue() if f_store else None,
    f_change.getvalue() if f_change else None)

present_extra = [c for c in ["상권매출", "유동인구", "직장인구", "점포수"] if c in feat.columns]
st.success(f"결합된 상권 데이터: {', '.join(present_extra) if present_extra else '없음(상품권만)'} "
           f"· 자치구 {len(feat)}개")


# ════════════════════════════════════════════════════════════════
# 탭
# ════════════════════════════════════════════════════════════════
tabs = st.tabs(["📈 상품권 시계열", "🏙️ 자치구 비교", "🗓️ 시즌성",
                "🧮 통합표·상관", "🔍 관계 탐색", "📉 추이 오버레이", "🧪 인과 검토"])

# ── 1. 상품권 시계열 ────────────────────────────────────────────
with tabs[0]:
    ts = gg_all.groupby("연월").agg(발행액=("발행액","sum"), 판매액=("판매액","sum")).reset_index()
    ts["판매율"] = ts["판매액"] / ts["발행액"].replace(0, np.nan)
    fig = go.Figure()
    fig.add_bar(x=ts["연월"], y=ts["발행액"]/1e8, name="발행액(억)", opacity=0.5)
    fig.add_bar(x=ts["연월"], y=ts["판매액"]/1e8, name="판매액(억)", opacity=0.85)
    fig.update_layout(barmode="overlay", yaxis_title="억원", title="월별 발행 vs 판매", legend_title="")
    st.plotly_chart(fig, use_container_width=True)
    fig2 = px.line(ts, x="연월", y="판매율", markers=True, title="월별 판매율")
    fig2.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig2, use_container_width=True)

# ── 2. 자치구 비교 ──────────────────────────────────────────────
with tabs[1]:
    by = feat.reset_index().rename(columns={"index": "자치구", "발행처": "자치구"})
    metric = st.radio("정렬 기준", ["상품권발행", "상품권판매", "상품권판매율"], horizontal=True)
    o = by.sort_values(metric, ascending=False)
    fig = px.bar(o, x=metric, y="자치구", orientation="h", color="상품권판매율",
                 color_continuous_scale="RdYlGn", title=f"자치구별 {metric}")
    fig.update_layout(yaxis=dict(autorange="reversed"), height=650, yaxis_title="")
    if metric == "상품권판매율":
        fig.update_xaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)
    sc = px.scatter(by, x="상품권발행", y="상품권판매율", text="자치구",
                    title="발행 규모 vs 판매율 (오른쪽 아래=과발행/수요초과)")
    sc.update_traces(textposition="top center"); sc.update_yaxes(tickformat=".0%")
    st.plotly_chart(sc, use_container_width=True)
    st.caption(f"발행액–판매율 상관 = {by['상품권발행'].corr(by['상품권판매율']):.2f}")

# ── 3. 시즌성 ───────────────────────────────────────────────────
with tabs[2]:
    seas = gg_all.groupby("월")["발행액"].sum().reindex(range(1, 13)).reset_index()
    fig = px.bar(seas, x="월", y="발행액", title="월(1~12) 누적 발행액 — 명절 시즌성")
    fig.update_xaxes(tickmode="linear", dtick=1)
    st.plotly_chart(fig, use_container_width=True)
    piv = gg_all.pivot_table(index="발행처", columns="연월", values="발행액", aggfunc="sum", fill_value=0)
    piv = piv.reindex([g for g in GU25 if g in piv.index])
    hm = px.imshow(piv/1e8, aspect="auto", color_continuous_scale="YlOrRd",
                   labels=dict(color="억원"), title="자치구 × 월 발행액(억원)")
    hm.update_layout(height=650)
    st.plotly_chart(hm, use_container_width=True)

# ── 4. 통합표·상관 ──────────────────────────────────────────────
with tabs[3]:
    st.markdown("#### 관찰된 사실 — 통합 자치구 테이블 (원본 그대로)")
    show = feat.copy()
    if life is not None:
        show["생애주기"] = life.map(lambda x: f"{x}·{LIFECYCLE.get(x,'')}" if pd.notna(x) else "")
    st.dataframe(show.style.format({c: "{:,.0f}" for c in feat.columns
                                    if c != "상품권판매율"} | {"상품권판매율": "{:.1%}"}),
                 use_container_width=True, height=500)
    csv = show.to_csv().encode("utf-8-sig")
    st.download_button("이 표 CSV로 내려받기", csv, "자치구_통합지표.csv", "text/csv")

    numcols = [c for c in feat.columns if feat[c].notna().sum() > 2]
    st.markdown("#### 전체 상관행렬 (모든 지표, 체리피킹 없이)")
    norm = st.selectbox("정규화(규모 교란 제거)",
                        ["없음(원자료)"] + [f"÷ {c}" for c in ["유동인구","직장인구","점포수"] if c in feat],
                        help="금액 지표를 규모 변수로 나눠 '1단위당' 강도로 바꾼 뒤 상관을 봅니다.")
    fm = feat[numcols].copy()
    if norm.startswith("÷"):
        base = norm[2:].strip()
        for c in numcols:
            if c != base and c != "상품권판매율" and feat[c].abs().max() > 1000:  # 금액/카운트만 정규화
                fm[c] = feat[c] / feat[base].replace(0, np.nan)
        fm = fm.drop(columns=[base], errors="ignore")
    cor = fm.corr()
    hm = px.imshow(cor, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
                   aspect="auto", title=f"피어슨 상관행렬 ({norm})")
    hm.update_layout(height=600)
    st.plotly_chart(hm, use_container_width=True)
    st.caption("정규화를 켰을 때 상관이 크게 줄면, 원자료의 높은 상관은 상당 부분 자치구 '규모' 때문입니다.")

    # 상품권과의 상관 순위(객관적 나열)
    for target in ["상품권판매", "상품권판매율"]:
        if target in cor.columns:
            s = cor[target].drop(labels=[target], errors="ignore").dropna().sort_values(key=abs, ascending=False)
            if len(s):
                st.markdown(f"**{target}** 과의 상관(절댓값 순): " +
                            " · ".join(f"{k} {v:+.2f}" for k, v in s.items()))

# ── 5. 관계 탐색(편상관 포함) ───────────────────────────────────
with tabs[4]:
    numcols = [c for c in feat.columns if feat[c].notna().sum() > 3]
    if len(numcols) < 2:
        st.info("상권 파일을 2종 이상 올리면 지표 간 관계를 탐색할 수 있습니다.")
    else:
        c1, c2, c3 = st.columns(3)
        x = c1.selectbox("X 축", numcols, index=numcols.index("상품권판매") if "상품권판매" in numcols else 0)
        y = c2.selectbox("Y 축", numcols, index=numcols.index("상권매출") if "상권매출" in numcols else min(1, len(numcols)-1))
        ctrl_opts = ["(없음)"] + [c for c in numcols if c not in (x, y)]
        ctrl = c3.selectbox("통제변수(편상관)", ctrl_opts,
                            index=(ctrl_opts.index("유동인구") if "유동인구" in ctrl_opts else 0))
        dfp = feat.reset_index().rename(columns={"index": "자치구", "발행처": "자치구"})
        color = None
        if life is not None:
            dfp["생애주기"] = life.reindex(feat.index).values
            color = "생애주기"
        sc = px.scatter(dfp, x=x, y=y, text="자치구", color=color,
                        title=f"{x} vs {y}")
        sc.update_traces(textposition="top center")
        sub = feat[[x, y]].dropna()
        if len(sub) >= 3:
            b1, b0 = np.polyfit(sub[x], sub[y], 1)
            xs = np.array([sub[x].min(), sub[x].max()])
            sc.add_scatter(x=xs, y=b0 + b1*xs, mode="lines", name="추세선", line=dict(dash="dash"))
        st.plotly_chart(sc, use_container_width=True)

        r = feat[x].corr(feat[y])
        cols = st.columns(2)
        cols[0].metric("단순 상관 r", f"{r:+.2f}")
        if ctrl != "(없음)":
            pr, n = partial_corr(feat, x, y, ctrl)
            cols[1].metric(f"편상관 r ({ctrl} 통제)", f"{pr:+.2f}" if pd.notna(pr) else "N/A")
            if pd.notna(pr):
                drop = abs(r) - abs(pr)
                if abs(r) > 0.1 and drop > 0.15:
                    st.warning(f"{ctrl}를 통제하니 상관이 {r:+.2f} → {pr:+.2f}로 약해졌습니다. "
                               f"두 지표의 관계는 상당 부분 {ctrl}(규모/수요)로 설명됩니다.")
                elif abs(pr) >= abs(r) - 0.05:
                    st.info(f"{ctrl}를 통제해도 상관이 유지됩니다({pr:+.2f}). "
                            f"{ctrl}만으로는 설명되지 않는 직접적 관련이 남아 있습니다.")

# ── 6. 추이 오버레이 ────────────────────────────────────────────
with tabs[5]:
    st.markdown("**상품권 발행 ↔ 상권 매출 (분기 시계열 겹쳐보기)** — 발행 급증 직후 분기에 "
                "매출이 오르는지 눈으로 확인합니다. (인과 아님 · 시각적 단서)")
    if f_sales is None:
        st.info("추정매출-자치구 파일을 올리면 자치구별 분기 추이를 겹쳐 봅니다.")
    else:
        sa = read_table(f_sales.getvalue())
        nc, qc = gu_name_col(sa), quarter_col(sa)
        amt = find_col(sa, "당월", "매출금액") or find_col(sa, "thsmon", "selng", "amt") or find_col(sa, "매출", "금액")
        if not (nc and qc and amt):
            st.warning("매출 파일에서 자치구·분기·매출 컬럼을 찾지 못했습니다.")
        else:
            sa[amt] = num(sa[amt])
            sel = st.selectbox("자치구 선택", [g for g in GU25 if g in feat.index])
            sale_q = (sa[sa[nc].astype(str).str.strip() == sel]
                      .groupby(qc)[amt].sum().rename("상권매출"))
            gift_q = (gg_all[gg_all["발행처"] == sel].groupby("분기")["발행액"].sum().rename("상품권발행"))
            # 분기 라벨 정규화(20244 → 2024Q4)
            def q_norm(x):
                x = str(x)
                m = re.match(r"(\d{4})(\d)$", x)
                return f"{m.group(1)}Q{m.group(2)}" if m else x
            sale_q.index = [q_norm(i) for i in sale_q.index]
            j = pd.concat([sale_q, gift_q], axis=1).sort_index()
            fig = go.Figure()
            fig.add_bar(x=j.index, y=j["상품권발행"]/1e8, name="상품권 발행(억)", opacity=0.5)
            fig.add_scatter(x=j.index, y=j["상권매출"]/1e8, name="상권 매출(억)", yaxis="y2",
                            mode="lines+markers")
            fig.update_layout(title=f"{sel} · 분기별 상품권 발행 vs 상권 매출",
                              yaxis=dict(title="상품권 발행(억)"),
                              yaxis2=dict(title="상권 매출(억)", overlaying="y", side="right"),
                              legend_title="")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("겹치는 분기가 적으면 두 파일의 기간이 어긋난 것입니다. 매출 파일 분기 범위를 확인하세요.")

# ── 7. 인과 검토 ────────────────────────────────────────────────
with tabs[6]:
    st.markdown("#### 관찰된 사실 (데이터가 말하는 것)")
    facts = []
    by = feat
    if "상품권발행" in by:
        c = by["상품권발행"].corr(by["상품권판매율"])
        facts.append(f"발행액과 판매율의 상관은 {c:+.2f} — 많이 발행한 자치구일수록 판매율이 "
                     f"{'낮은' if c < 0 else '높은'} 경향.")
    if "상권매출" in by and "상품권판매" in by:
        r = by["상품권판매"].corr(by["상권매출"])
        pr = partial_corr(by, "상품권판매", "상권매출", "유동인구")[0] if "유동인구" in by else np.nan
        facts.append(f"상품권 판매액과 상권 매출의 단순 상관 {r:+.2f}"
                     + (f", 유동인구 통제 후 편상관 {pr:+.2f}." if pd.notna(pr) else "."))
    for f in facts:
        st.markdown("- " + f)
    if not facts:
        st.caption("상권 파일을 올리면 관찰된 상관이 여기에 자동으로 요약됩니다.")

    st.markdown("#### 해석 (추정 — 인과 아님)")
    st.markdown(
        "- 상품권 판매액과 상권 매출이 함께 크더라도, 둘 다 자치구 **규모·소득**에 좌우되는 "
        "공통원인 구조일 수 있습니다(부유한 구가 상품권도 많이 사고 상권도 큼). 위 편상관에서 "
        "유동인구를 통제했을 때 상관이 크게 줄면 그 신호입니다.\n"
        "- **역인과** 가능성: 소비가 원래 활발한 지역이라 상품권 발행·판매도 컸을 수 있습니다.\n"
        "- **구축효과**: 상품권 소비가 원래 할 소비를 대체만 했다면 상권 매출 순증은 없습니다.\n"
        "- 그럼에도 상품권이 명절 소비를 앞당기거나 역외 유출을 막는 **진작 효과**를 봤다는 연구도, "
        "재정 대비 효과가 작다는 비판도 있어 정책적으로 논쟁적입니다. 어느 한쪽으로 단정하지 않는 게 정확합니다.")

    st.markdown("#### 인과를 보려면 (이 데이터로 가능한 준실험)")
    st.markdown(
        "- **이벤트스터디/DiD**: 2026-01 발행 0 → 2026-02 급증처럼 발행이 급변한 시점을 기준으로, "
        "발행 급증 자치구(처치군) vs 그 시기 발행이 거의 없던 자치구(대조군)의 이후 분기 상권 매출 "
        "변화를 차분합니다. 계절·규모 요인이 상당히 상쇄됩니다.\n"
        "- **전제(평행추세)**: 처치 전 두 군의 매출 추세가 나란했는지 '추이 오버레이' 탭에서 먼저 확인해야 합니다.\n"
        "- 이 추정은 SDK의 M5 인과추론(DiD를 numpy/statsmodels로 Tool use 호출)이 담당할 자리입니다.")
    st.info("이 탭은 '사실'과 '추정'을 분리해 보여줍니다. 인과 결론은 위 준실험을 실제로 추정한 뒤, "
            "효과 크기와 신뢰구간을 함께 제시할 때만 내리는 것이 맞습니다.")

st.divider()
st.caption("출처: 서울사랑상품권 월별 발행·판매 / 서울 상권분석서비스 자치구 5종. "
           "상관≠인과. 집계: 금액=기간합, 인구·점포·영업개월=분기평균, 생애주기=최신분기.")
