# -*- coding: utf-8 -*-
"""
서울사랑상품권 → 상권매출 인과추론 대시보드 (재구축)
════════════════════════════════════════════════════════════════
상품권 3종:  가맹점(서울페이업종·자치구)  /  발행·판매(자치구×월)  /  결제내역(자치구×업종×월)
상권 5종(자치구, 2023~2025 분기): 추정매출[결과Y] / 길단위인구 / 직장인구 / 점포 / 상권변화지표[통제]

수정사항
  · 결제내역을 '여러 개 파일' 업로드 가능하게(월별 xlsx 12개 또는 zip 모두 허용)
  · 가맹점 파일 통합(자치구·업종별 가맹점 수 = 노출 규모)
  · 업종 매칭: 서울페이업종(20종) ↔ 추정매출 업종(≈60종) 키워드 근사매핑
    → 같은 자치구×분기 안에서 '상품권 노출 높은 업종 vs 낮은 업종' 비교(명절 교란 제거)
    → '매핑 검토' 탭에서 투명 공개

인과 설계
  · 주 분석: 자치구×분기 이중차분(TWFE) + 이벤트스터디 (분기 FE가 명절 흡수)
  · 강화 분석: 업종 노출 × 발행 상호작용 (자치구×분기 FE + 업종 FE)
  · 결과 Y=추정매출 총매출(구축효과 반영) / 처치 D=발행 / 노출=결제·가맹점

실행: pip install streamlit pandas numpy plotly statsmodels openpyxl
      streamlit run causal_app.py
"""

import io
import re
import zipfile
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import statsmodels.formula.api as smf
    HAS_SM = True
except Exception:
    HAS_SM = False

st.set_page_config(page_title="상품권 인과추론", layout="wide")

GU25 = ["종로구","중구","용산구","성동구","광진구","동대문구","중랑구","성북구","강북구",
        "도봉구","노원구","은평구","서대문구","마포구","양천구","강서구","구로구","금천구",
        "영등포구","동작구","관악구","서초구","강남구","송파구","강동구"]
YEARS = (2023, 2024, 2025)

# 서울페이업종(20) ← 추정매출 업종명에 나타나는 키워드. 위에서부터 먼저 매칭(구체적 우선).
SEOULPAY_RULES = [
    ("자동차/주유", ["자동차", "주유", "카센", "정비", "세차", "타이어", "중고차", "카센타"]),
    ("부동산/임대", ["부동산", "중개", "임대"]),
    ("여행/숙박", ["여행", "숙박", "호텔", "모텔", "펜션", "여관", "콘도", "게스트"]),
    ("입시/교습학원", ["입시", "보습", "교습", "종합학원", "단과", "학습지"]),
    ("외국어/언어", ["외국어", "어학", "영어", "회화"]),
    ("예술 교육", ["예술학원", "음악학원", "미술학원", "무용", "피아노", "미술教", "예능"]),
    ("기술/기능 교육", ["컴퓨터학원", "직업", "기술학원", "운전학원", "자격", "기능"]),
    ("기타교육기관", ["교육원", "평생교육", "교육기관"]),
    ("보건/복지", ["의원", "병원", "치과", "한의원", "약국", "의약", "보건", "요양", "복지",
                 "산부인", "피부과", "정형외과", "내과", "이비인후", "동물병원", "수의", "안과", "한방"]),
    ("문화/체육", ["pc방", "피시방", "노래", "당구", "헬스", "골프", "스포츠", "체육", "볼링",
                 "스크린", "오락", "영화", "체력", "요가", "필라", "수영", "탁구", "테니스", "클럽"]),
    ("가구/인테리어", ["가구", "인테리어", "커튼", "조명", "침구", "벽지"]),
    ("가전/통신", ["가전", "전자제품", "휴대폰", "통신", "핸드폰", "컴퓨터판매"]),
    ("건축/철물", ["건축", "철물", "페인트", "설비", "자재", "조경", "타일", "인테리어자재"]),
    ("디자인/인쇄", ["인쇄", "디자인", "광고", "간판", "출력", "복사"]),
    ("의류/잡화", ["의류", "한복", "신발", "가방", "잡화", "액세", "악세", "시계", "귀금속",
                 "안경", "패션", "의복", "모자", "속옷", "아동복", "편집숍"]),
    ("식자재/유통", ["슈퍼", "편의점", "마트", "청과", "정육", "육류", "수산", "미곡", "농산",
                  "식료품", "반찬가게", "축산", "건어물", "쌀", "곡물"]),
    ("음식점/식음료업", ["음식", "한식", "중식", "일식", "양식", "분식", "제과", "제빵", "베이커리",
                    "커피", "카페", "음료", "치킨", "패스트푸드", "호프", "주점", "뷔페", "고기",
                    "횟집", "포차", "디저트", "아이스크림", "피자", "햄버거", "간이주점", "food"]),
    ("생활/리빙", ["미용", "네일", "세탁", "이용원", "이용업", "목욕", "사우나", "꽃", "화원",
                 "애견", "애완", "문구", "생활용품", "수선", "열쇠", "사진", "공방", "이미용"]),
    ("기업/기관", ["기업", "기관", "협회", "단체"]),
]


# ════════════════════════════════════════════════════════════════
# 유틸
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
            or find_col(df, "자치구", "명") or find_col(df, "시군구", "명"))


def induty_col(df):
    return (find_col(df, "서비스업종코드명") or find_col(df, "svc", "induty", "nm")
            or find_col(df, "업종", "명", exclude=("자치구", "상권")))


def quarter_col(df):
    return (find_col(df, "기준", "분기") or find_col(df, "stdr", "yyqu")
            or find_col(df, "년분기") or find_col(df, "yyqu", "cd"))


def parse_yq(v):
    m = re.match(r"(\d{4})Q?(\d)$", str(v).strip().upper())
    return (int(m.group(1)), int(m.group(2))) if m else None


def tidx_of(y, q):
    return y * 4 + (q - 1)


def map_seoulpay(name):
    """추정매출 업종명 → 서울페이업종 20종 중 하나(없으면 None)."""
    n = _norm(name)
    for cat, kws in SEOULPAY_RULES:
        if any(_norm(k) in n for k in kws):
            return cat
    return None


def agg_gu_quarter(df, val_col, how="sum", keep_induty=False):
    nc, qc = gu_name_col(df), quarter_col(df)
    ic = induty_col(df) if keep_induty else None
    if not (nc and qc and val_col and val_col in df.columns):
        return None
    keys = [nc, qc] + ([ic] if ic else [])
    s = df[keys + [val_col]].copy()
    s[val_col] = num(s[val_col])
    yq = s[qc].map(parse_yq)
    s = s[yq.notna()].copy()
    s["year"] = [a for a, _ in yq[yq.notna()]]
    s["q"] = [b for _, b in yq[yq.notna()]]
    s = s[s["year"].isin(YEARS)]
    gcols = ["year", "q", nc] + ([ic] if ic else [])
    g = s.groupby(gcols)[val_col]
    out = (g.sum() if how == "sum" else g.mean()).reset_index()
    ren = {nc: "gu", val_col: "val"}
    if ic:
        ren[ic] = "induty"
    out = out.rename(columns=ren)
    out["gu"] = out["gu"].astype(str).str.strip()
    return out[out["gu"].isin(GU25)]


# ════════════════════════════════════════════════════════════════
# 상품권 로더
# ════════════════════════════════════════════════════════════════
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
    lo["year"], lo["q"] = yy, (mm - 1) // 3 + 1
    return lo


@st.cache_data(show_spinner=False)
def load_payment(files):
    """files: [(name, bytes), ...]  — 개별 xlsx 여러 개 또는 zip 혼합 허용."""
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
        df["year"], df["q"] = yy, (mm - 1) // 3 + 1
        fr.append(df)
    d = pd.concat(fr, ignore_index=True)
    for c in ("발행액", "판매액"):
        d[c] = num(d[c]).fillna(0)
    d["발행처"] = d["발행처"].astype(str).str.strip()
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
# 계량
# ════════════════════════════════════════════════════════════════
def event_study(panel, ycol="y", lo=-3, hi=3):
    df = panel.dropna(subset=[ycol]).copy()
    cols = []
    for k in range(lo, hi + 1):
        if k == -1:
            continue
        c = f"ev_{'m' if k < 0 else 'p'}{abs(k)}"
        df[c] = ((df["event"] <= lo) if k == lo else
                 (df["event"] >= hi) if k == hi else (df["event"] == k)).astype(int)
        cols.append((k, c))
    f = f"{ycol} ~ " + " + ".join(c for _, c in cols) + " + C(gu) + C(tidx)"
    m = smf.ols(f, df).fit(cov_type="cluster", cov_kwds={"groups": df["gu"]})
    out = [dict(event=k, coef=m.params[c], lo=m.conf_int().loc[c][0], hi=m.conf_int().loc[c][1])
           for k, c in cols if c in m.params.index]
    out.append(dict(event=-1, coef=0.0, lo=0.0, hi=0.0))
    return pd.DataFrame(out).sort_values("event"), m


def twfe(panel, treat, controls, ycol="y"):
    df = panel.dropna(subset=[ycol, treat]).copy()
    rhs = [treat] + [c for c in controls if c in df.columns] + ["C(gu)", "C(tidx)"]
    m = smf.ols(f"{ycol} ~ " + " + ".join(rhs), df).fit(
        cov_type="cluster", cov_kwds={"groups": df["gu"]})
    ci = m.conf_int().loc[treat]
    return dict(coef=m.params[treat], se=m.bse[treat], p=m.pvalues[treat],
                lo=ci[0], hi=ci[1], n=int(m.nobs)), m


def exposure_did(panel_ie, ycol="y"):
    """자치구×업종×분기: 발행 × 업종노출 상호작용. 자치구×분기 FE + 업종 FE."""
    df = panel_ie.dropna(subset=[ycol, "DxE"]).copy()
    df["it"] = df["gu"].astype(str) + "_" + df["tlabel"].astype(str)
    m = smf.ols(f"{ycol} ~ DxE + C(it) + C(induty)", df).fit(
        cov_type="cluster", cov_kwds={"groups": df["gu"]})
    ci = m.conf_int().loc["DxE"]
    return dict(coef=m.params["DxE"], se=m.bse["DxE"], p=m.pvalues["DxE"],
                lo=ci[0], hi=ci[1], n=int(m.nobs)), m


# ════════════════════════════════════════════════════════════════
# 사이드바
# ════════════════════════════════════════════════════════════════
st.title("🧪 서울사랑상품권 → 상권매출 인과추론")
st.caption("자치구×분기 이중차분(DiD)·이벤트스터디로 '발매 직후 총매출이 올랐는가'를 추정합니다. "
           "분기 고정효과가 명절 시즌성을 흡수합니다.")

with st.sidebar:
    st.header("① 상품권 3종")
    f_pay = st.file_uploader("결제내역 (월별 xlsx 여러 개 또는 zip)",
                             type=["xlsx", "zip"], accept_multiple_files=True, key="p")
    f_iss = st.file_uploader("발행·판매 현황 xlsx", type=["xlsx"], key="i")
    f_mer = st.file_uploader("가맹점 csv", type=["csv", "txt", "tsv"], key="m")
    st.header("② 상권 자치구 5종 (2023~2025)")
    f_sales = st.file_uploader("추정매출-자치구 [결과 Y·필수]", type=["csv","txt","tsv"], key="s")
    f_flow = st.file_uploader("길단위인구-자치구 (통제)", type=["csv","txt","tsv"], key="f")
    f_work = st.file_uploader("직장인구-자치구 (통제)", type=["csv","txt","tsv"], key="w")
    f_store = st.file_uploader("점포-자치구 (통제)", type=["csv","txt","tsv"], key="st")
    f_change = st.file_uploader("상권변화지표-자치구 (통제)", type=["csv","txt","tsv"], key="c")

if not HAS_SM:
    st.error("statsmodels가 필요합니다:  pip install statsmodels")
    st.stop()

pay = load_payment([(f.name, f.getvalue()) for f in f_pay]) if f_pay else None
mer = load_merchant(f_mer.getvalue()) if f_mer else None


# ════════════════════════════════════════════════════════════════
# 노출도(업종별) 계산 : 결제(우선) 또는 가맹점
# ════════════════════════════════════════════════════════════════
def build_exposure(pay, mer):
    """서울페이업종 → 노출점수(0~1). 결제 총액 우선, 없으면 가맹점 수."""
    if pay is not None:
        s = pay[pay["구분"] == "자치구"].groupby("업종")["순결제액"].sum()
        src = "결제액"
    elif mer is not None:
        s = mer.groupby("업종").size()
        src = "가맹점수"
    else:
        return None, None
    exp = (s / s.max()).rename("노출점수")
    return exp, src


exposure, exp_src = build_exposure(pay, mer)


# ════════════════════════════════════════════════════════════════
# 패널 구축
# ════════════════════════════════════════════════════════════════
def build_panels(sales_b, issue_b, flow_b, worker_b, store_b, change_b, exposure):
    if sales_b is None or issue_b is None:
        return None, None, "추정매출-자치구와 발행/판매 파일이 모두 필요합니다."
    sa = read_table(sales_b)
    amt = find_col(sa, "당월", "매출금액") or find_col(sa, "thsmon", "selng", "amt") or find_col(sa, "매출", "금액")

    # (1) 자치구×분기 총매출
    Yg = agg_gu_quarter(sa, amt, "sum")
    if Yg is None:
        return None, None, "매출 파일에서 자치구·분기·매출 컬럼을 찾지 못했습니다."
    Yg = Yg.rename(columns={"val": "sales"})
    # (2) 자치구×업종×분기 매출 (노출 삼중차분용)
    Yie = agg_gu_quarter(sa, amt, "sum", keep_induty=True)

    iss = load_issue(issue_b)
    isq = (iss.groupby(["발행처", "year", "q"]).agg(issue=("발행액", "sum"), sold=("판매액", "sum"))
           .reset_index().rename(columns={"발행처": "gu"}))
    isq = isq[isq["year"].isin(YEARS)]

    panel = Yg.merge(isq, on=["gu", "year", "q"], how="left")
    panel[["issue", "sold"]] = panel[["issue", "sold"]].fillna(0)

    def add_ctrl(b, name, how="mean"):
        nonlocal panel
        if b is None:
            return
        df = read_table(b)
        col = None
        if name == "flow":
            col = find_col(df, "총", "유동인구수") or find_col(df, "tot", "flpop")
        elif name == "work":
            col = (find_col(df, "총", "직장", "인구") or find_col(df, "tot", "wrc", "popltn")
                   or find_col(df, "tot", "work"))
        elif name == "store":
            col = (find_col(df, "전체", "점포수") or
                   find_col(df, "점포수", exclude=("유사","개업","폐업","프랜차이즈","일반")) or
                   find_col(df, "stor", "co", exclude=("similr","opbiz","clsbiz","frc")))
        elif name == "opmonth":
            col = find_col(df, "운영", "영업", "개월", exclude=("서울",)) or find_col(df, "opr", "sale", exclude=("se",))
        g = agg_gu_quarter(df, col, how)
        if g is not None:
            panel = panel.merge(g.rename(columns={"val": name}), on=["gu", "year", "q"], how="left")

    add_ctrl(flow_b, "flow"); add_ctrl(worker_b, "work")
    add_ctrl(store_b, "store"); add_ctrl(change_b, "opmonth")

    panel["tidx"] = tidx_of(panel["year"], panel["q"])
    panel["tlabel"] = panel["year"].astype(str) + "Q" + panel["q"].astype(str)
    panel["D_bin"] = (panel["issue"] > 0).astype(int)
    panel["lD"] = np.log1p(panel["issue"])
    panel["lsold"] = np.log1p(panel["sold"])
    panel["y"] = np.log(panel["sales"].clip(lower=1))
    for c in ["flow", "work", "store"]:
        if c in panel:
            panel["l" + c] = np.log(panel[c].clip(lower=1))
    cohort = panel[panel["D_bin"] == 1].groupby("gu")["tidx"].min().rename("cohort")
    panel = panel.merge(cohort, on="gu", how="left")
    panel["event"] = panel["tidx"] - panel["cohort"]

    # 노출 삼중차분 패널
    panel_ie = None
    if Yie is not None and exposure is not None:
        Yie = Yie.rename(columns={"val": "sales"})
        Yie["cat"] = Yie["induty"].map(map_seoulpay)
        Yie["exposure"] = Yie["cat"].map(exposure.to_dict())
        Yie = Yie.merge(isq[["gu", "year", "q", "issue"]], on=["gu", "year", "q"], how="left")
        Yie["issue"] = Yie["issue"].fillna(0)
        Yie["tidx"] = tidx_of(Yie["year"], Yie["q"])
        Yie["tlabel"] = Yie["year"].astype(str) + "Q" + Yie["q"].astype(str)
        Yie["y"] = np.log(Yie["sales"].clip(lower=1))
        Yie["DxE"] = np.log1p(Yie["issue"]) * Yie["exposure"]
        panel_ie = Yie
    return panel, panel_ie, None


panel, panel_ie, err = build_panels(
    f_sales.getvalue() if f_sales else None,
    f_iss.getvalue() if f_iss else None,
    f_flow.getvalue() if f_flow else None,
    f_work.getvalue() if f_work else None,
    f_store.getvalue() if f_store else None,
    f_change.getvalue() if f_change else None,
    exposure)


# ════════════════════════════════════════════════════════════════
# 탭
# ════════════════════════════════════════════════════════════════
t0, t1, t2, t3, t4, t5 = st.tabs(
    ["📋 설계·데이터", "🔎 상품권 구조", "📈 이벤트스터디", "📊 DiD 추정",
     "🔀 업종 노출 삼중차분", "🗺️ 매핑 검토"])

# ── 설계·데이터 ─────────────────────────────────────────────────
with t0:
    st.markdown("#### 데이터 적재 상태")
    pay_q = pay.groupby(["year", "q"]).ngroups if pay is not None else 0
    status = {
        "결제내역(노출·기전)": (pay is not None, f"{pay_q}분기" if pay is not None else ""),
        "발행·판매(처치 D)": (f_iss is not None, ""),
        "가맹점(노출 규모)": (mer is not None, f"{len(mer):,}개" if mer is not None else ""),
        "추정매출(결과 Y)": (f_sales is not None, "필수"),
        "유동인구·직장·점포·상권변화(통제)": (any([f_flow, f_work, f_store, f_change]), ""),
    }
    st.table(pd.DataFrame([{"데이터": k, "적재": "✅" if v[0] else "—", "비고": v[1]}
                           for k, v in status.items()]))
    if err:
        st.info(err + " 인과추정은 두 필수 파일(추정매출·발행)이 있어야 실행됩니다.")
    elif panel is not None:
        st.success(f"자치구 패널: {panel['gu'].nunique()}개 자치구 × {panel['tlabel'].nunique()}분기 "
                   f"= {len(panel)}행 ({panel['tlabel'].min()}~{panel['tlabel'].max()})")
        st.markdown("**설계** — 결과 Y=총매출(로그), 처치 D=분기 발행, 자치구 FE+분기 FE(명절 흡수), "
                    "통제=유동/직장/점포/영업개월. 이벤트스터디로 처치 전 평행추세를 먼저 검증.")
        st.dataframe(panel[["gu","tlabel","sales","issue","D_bin","event"]]
                     .sort_values(["gu","tlabel"]).head(25), use_container_width=True)

# ── 상품권 구조 ─────────────────────────────────────────────────
with t1:
    st.markdown("**상품권이 실제 어디서 쓰이나 (결제내역) & 어디서 받나 (가맹점)** — 처치 노출의 근거")
    if pay is None and mer is None:
        st.info("결제내역 또는 가맹점 파일을 올리면 표시됩니다.")
    if pay is not None:
        gu = pay[pay["구분"] == "자치구"]
        bi = (gu.groupby("업종")["순결제액"].sum() / 1e8).sort_values(ascending=False).reset_index()
        bi.columns = ["업종", "순결제액(억)"]
        fig = px.bar(bi, x="순결제액(억)", y="업종", orientation="h",
                     title="업종별 상품권 순결제액 (억원)")
        fig.update_layout(yaxis=dict(autorange="reversed"), height=560)
        st.plotly_chart(fig, use_container_width=True)
    if mer is not None:
        bm = mer.groupby("업종").size().sort_values(ascending=False).reset_index()
        bm.columns = ["업종", "가맹점수"]
        st.plotly_chart(px.bar(bm, x="가맹점수", y="업종", orientation="h",
                               title="업종별 가맹점 수").update_layout(
                               yaxis=dict(autorange="reversed"), height=560),
                        use_container_width=True)

# ── 이벤트스터디 ────────────────────────────────────────────────
with t2:
    st.markdown("**이벤트스터디** — 발행 개시(t=0) 전후 로그 총매출. t<0가 0 근처면 평행추세, t≥0 상승이면 발매 직후 효과.")
    if panel is None:
        st.info("필수 두 파일을 올리면 실행됩니다.")
    elif panel["event"].notna().sum() < 8 or panel[panel["event"].notna()]["cohort"].nunique() < 2:
        st.warning("발행 개시 시점의 변이가 부족합니다(대부분 동일 분기 시작).")
    else:
        es, m = event_study(panel)
        fig = go.Figure()
        fig.add_scatter(x=es["event"], y=es["coef"], mode="lines+markers", name="효과")
        fig.add_scatter(x=es["event"], y=es["hi"], mode="lines", line=dict(width=0), showlegend=False)
        fig.add_scatter(x=es["event"], y=es["lo"], mode="lines", fill="tonexty",
                        line=dict(width=0), name="95% CI", fillcolor="rgba(0,100,200,.15)")
        fig.add_hline(y=0, line_dash="dot"); fig.add_vline(x=-0.5, line_dash="dash", line_color="gray")
        fig.update_layout(title="이벤트스터디: 발행 개시 전후 로그매출 효과",
                          xaxis_title="발행 개시 대비 분기(0=개시)", yaxis_title="로그매출 계수")
        st.plotly_chart(fig, use_container_width=True)
        pre = es[es["event"] < 0]["coef"].abs().max()
        st.caption(f"처치 전 계수 절댓값 최대 {pre:.3f} (0에 가까울수록 평행추세 지지). 음영=95% CI(자치구 군집).")

# ── DiD 추정 ────────────────────────────────────────────────────
with t3:
    st.markdown("**이중차분(TWFE)** — 로그 총매출에 대한 발행 효과. 여러 설정 비교(강건성).")
    if panel is None:
        st.info("필수 두 파일을 올리면 실행됩니다.")
    else:
        ctrls = [c for c in ["lflow", "lwork", "lstore", "opmonth"] if c in panel.columns]
        specs = [("발행여부, 통제없음", "D_bin", []), ("발행여부+통제", "D_bin", ctrls),
                 ("발행액(로그)+통제", "lD", ctrls), ("판매액(로그)+통제", "lsold", ctrls)]
        rows = []
        for label, treat, cc in specs:
            try:
                r, _ = twfe(panel, treat, cc)
                rows.append(dict(설정=label, 계수=round(r["coef"], 4), 표준오차=round(r["se"], 4),
                                 신뢰구간=f"[{r['lo']:.3f}, {r['hi']:.3f}]", p값=round(r["p"], 3), N=r["n"]))
            except Exception as e:
                rows.append(dict(설정=label, 계수="오류", 표준오차=str(e)[:24], 신뢰구간="", p값="", N=""))
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("종속변수=로그(총매출). 발행여부 계수≈발행 분기의 매출 %차이. CI가 0을 포함하면 비유의.")
        st.info("주의: 발행이 명절마다 반복되는 staggered 구조라 TWFE는 편향될 수 있습니다(Goodman-Bacon). "
                "이벤트스터디 pre-trend와 함께 해석하세요.")

# ── 업종 노출 삼중차분 ──────────────────────────────────────────
with t4:
    st.markdown("**업종 노출 삼중차분** — 같은 자치구·같은 분기 안에서 상품권 노출이 높은 업종의 매출이 "
                "발행에 더 반응하는가. 자치구×분기 FE가 명절을 흡수하므로 가장 명절-강건한 설계입니다.")
    if panel_ie is None:
        st.info("추정매출·발행에 더해 결제내역(또는 가맹점)이 있어야 노출을 만들 수 있습니다.")
    else:
        n_map = panel_ie["exposure"].notna().sum()
        n_all = len(panel_ie)
        st.caption(f"노출({exp_src} 기반) 매핑된 관측치 {n_map:,}/{n_all:,} "
                   f"({n_map/n_all*100:.0f}%). 매핑 실패 업종은 제외됩니다 → 매핑 검토 탭 참고.")
        try:
            r, m = exposure_did(panel_ie)
            c = st.columns(3)
            c[0].metric("상호작용 계수 (발행×노출)", f"{r['coef']:+.4f}")
            c[1].metric("95% 신뢰구간", f"[{r['lo']:.3f}, {r['hi']:.3f}]")
            c[2].metric("p값", f"{r['p']:.3f}")
            st.caption("계수>0이고 CI가 0을 넘지 않으면: 상품권 노출이 큰 업종일수록 발행 많은 자치구·분기에 "
                       "매출이 더 오른다는 뜻(명절 등 공통효과를 제거한 순효과). N="+str(r["n"]))
        except Exception as e:
            st.warning(f"추정 실패: {e}")

# ── 매핑 검토 ───────────────────────────────────────────────────
with t5:
    st.markdown("**업종 매핑 검토** — 추정매출 업종(≈60종) → 서울페이업종(20종) 근사 매핑. "
                "여기서 오분류가 보이면 알려주세요(코드의 SEOULPAY_RULES 키워드로 조정).")
    if panel_ie is None:
        st.info("추정매출 파일을 올리면 실제 업종 매핑 결과가 표시됩니다.")
    else:
        mp = (panel_ie[["induty", "cat", "exposure"]].drop_duplicates("induty")
              .sort_values(["cat", "induty"]))
        mp["매핑상태"] = np.where(mp["cat"].isna(), "❌ 미분류(제외)", "✅ " + mp["cat"].astype(str))
        st.dataframe(mp[["induty", "매핑상태", "exposure"]].rename(
            columns={"induty": "추정매출 업종", "exposure": "노출점수"}),
            use_container_width=True, height=500)
        miss = mp["cat"].isna().sum()
        st.caption(f"총 {len(mp)}개 추정매출 업종 중 {miss}개 미분류. "
                   f"노출점수 출처: {exp_src}(0~1 정규화).")
    if exposure is not None:
        st.markdown("**서울페이업종별 노출점수**")
        st.dataframe(exposure.sort_values(ascending=False).reset_index().rename(
            columns={"업종": "서울페이업종", "노출점수": "노출점수(0~1)"}),
            use_container_width=True)

st.divider()
st.caption("결과=추정매출 총매출 / 처치=발행 / 노출=결제·가맹점. 계수는 가정 하의 추정치이며 "
           "인과 해석은 pre-trend 검증과 함께라야 합니다. 기간 2023~2025.")
