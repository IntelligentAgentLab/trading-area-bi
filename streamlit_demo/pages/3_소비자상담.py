"""1372 소비자상담 상담상세현황 실데이터 탐색 페이지.

토픽모델링과 마찬가지로 대시보드·인과추론과 데이터 속성으로 연결돼 있지 않다(사이드바
업종 필터는 표시만 되고 이 페이지 내용에는 영향을 주지 않음). 업종 매핑 없이 원본 필드
(prdlstLclasNm 등)를 그대로 쓴다.

데이터 범위: data/raw/consumer_counsel/*.json (scripts/fetch_consumer_counsel.py로 수집,
용량이 커서 git에는 포함하지 않음 — 없으면 안내만 뜨고 나머지 페이지는 정상 동작한다).
"""
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from common import render_filters

RAW_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "consumer_counsel"

온라인_유형 = {"국내온라인거래", "모바일거래", "국제온라인거래", "소셜커머스(쇼핑)"}

CHART_HEIGHT = 560

표시방식_목록 = ["비중(%)", "건수", "3개월 이동평균", "전월 대비(%)", "전년 동월 대비(%)"]
# 누적/합산이 의미 있는 지표는 area, 증감률처럼 합산이 무의미한 지표는 line으로 그림
AREA_지표 = {"비중(%)", "건수", "3개월 이동평균"}


@st.cache_data
def load_data() -> pd.DataFrame | None:
    files = sorted(glob.glob(str(RAW_DIR / "*.json")))
    if not files:
        return None
    dfs = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            dfs.append(pd.DataFrame(json.load(fp)))
    df = pd.concat(dfs, ignore_index=True)
    범주형_컬럼 = ["prdlstLclasNm", "prdlstMlsfcNm", "dscsnCnClNm", "ntslTyStleCdNm", "upAreaNm"]
    df[범주형_컬럼] = df[범주형_컬럼].fillna("미상")  # 결측치 최대 3% 수준(dscsnCnClNm) 존재 - sort/groupby 깨지는 것 방지
    df["월"] = pd.to_datetime(df["rcptYm"], format="%Y%m").dt.strftime("%Y-%m")
    df["채널"] = df["ntslTyStleCdNm"].apply(lambda x: "온라인" if x in 온라인_유형 else "기타(오프라인 등)")
    return df


def build_trend(sub_df: pd.DataFrame, 전체월: list[str], color_col: str, extra_col: str | None = None) -> pd.DataFrame:
    """월 × (extra_col ×) color_col 별 건수·비중·이동평균·증감률을 계산.

    color_col은 "dscsnCnClNm"(불만유형)일 수도, "prdlstMlsfcNm"(중분류)일 수도 있음 —
    대분류 전체를 볼 때 중분류끼리 비교하고 싶다는 요청 때문에 색상 기준을 선택할 수 있게 뺐다.

    데이터에 없는 월은 0건으로 채워 넣은 뒤(연속된 월 인덱스 기준) rolling/shift를 적용한다
    — 안 그러면 "전월 대비"가 실제 전월이 아니라 그 다음으로 값이 있는 월과 비교돼버린다.
    """
    group_cols = ([extra_col] if extra_col else []) + [color_col]
    counts = sub_df.groupby(["월", *group_cols]).size().rename("건수").reset_index()

    비중그룹 = ["월"] + ([extra_col] if extra_col else [])
    counts["비중(%)"] = counts.groupby(비중그룹)["건수"].transform(lambda x: round(x / x.sum() * 100, 1))

    rows = []
    for keys, g in counts.groupby(group_cols):
        if not isinstance(keys, tuple):
            keys = (keys,)
        g = g.set_index("월")[["건수", "비중(%)"]].reindex(전체월)
        g["건수"] = g["건수"].fillna(0)
        g["비중(%)"] = g["비중(%)"].fillna(0)
        g["3개월 이동평균"] = g["건수"].rolling(3, min_periods=1).mean().round(1)

        mom = g["건수"].pct_change() * 100
        g["전월 대비(%)"] = mom.replace([np.inf, -np.inf], np.nan).round(1)

        yoy = g["건수"].pct_change(12) * 100
        g["전년 동월 대비(%)"] = yoy.replace([np.inf, -np.inf], np.nan).round(1)

        g = g.reset_index().rename(columns={"index": "월"})
        for col, val in zip(group_cols, keys):
            g[col] = val
        rows.append(g)

    return pd.concat(rows, ignore_index=True)


def render_trend_chart(trend_df: pd.DataFrame, 표시방식: str, title: str, color_col: str,
                        facet_col: str | None = None, uirevision_key: str = "", chart_key: str = ""):
    kwargs = {"facet_col": facet_col} if facet_col else {}
    if 표시방식 in AREA_지표:
        fig = px.area(trend_df, x="월", y=표시방식, color=color_col, title=title, height=CHART_HEIGHT, **kwargs)
    else:
        fig = px.line(trend_df, x="월", y=표시방식, color=color_col, title=title, height=CHART_HEIGHT,
                       markers=True, **kwargs)
        fig.add_hline(y=0, line_dash="dot", line_color="gray")
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=-0.35))
    # uirevision을 (카테고리 선택 기준으로) 고정해두면, 표시방식만 바꿀 때는 범례 숨김/고립 상태가
    # 유지되고, 카테고리를 바꿀 때만(=uirevision 값이 달라질 때만) 초기화된다.
    fig.update_layout(uirevision=uirevision_key)
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


st.set_page_config(page_title="소비자상담", page_icon="🔎", layout="wide")

render_filters()  # 사이드바 표시용 — 이 페이지 내용 자체는 업종 선택과 무관함

df = load_data()

st.title("🔎 1372 소비자상담 탐색")
st.caption("업종 구분 없이 원본 품목 분류(prdlstLclasNm 등)를 그대로 씁니다 — "
           "사이드바에서 업종을 바꿔도 이 페이지는 바뀌지 않습니다.")

if df is None:
    st.warning(
        f"`{RAW_DIR}`에 데이터가 없습니다. `scripts/fetch_consumer_counsel.py`를 먼저 실행해 "
        "1372 소비자상담 데이터를 받아주세요(data.go.kr 서비스키 필요)."
    )
    st.stop()

전체월 = sorted(df["월"].unique())
대분류_건수 = df["prdlstLclasNm"].value_counts()

col_m1, col_m2 = st.columns(2)
col_m1.metric("전체 건수", f"{len(df):,}건")
col_m2.metric("기간", f"{df['월'].min()} ~ {df['월'].max()}")

col1, col2, col3 = st.columns([1.2, 1.2, 1])
with col1:
    대분류 = st.selectbox(
        "대분류",
        대분류_건수.index.tolist(),
        format_func=lambda x: f"{x} ({대분류_건수[x]:,}건)",
        key="대분류_선택",
    )

대분류_sub = df[df["prdlstLclasNm"] == 대분류]
중분류_건수 = 대분류_sub["prdlstMlsfcNm"].value_counts()

with col2:
    중분류 = st.selectbox(
        "중분류 (더 구체적으로 좁히기)",
        ["(대분류 전체 보기)"] + 중분류_건수.index.tolist(),
        format_func=lambda x: x if x == "(대분류 전체 보기)" else f"{x} ({중분류_건수[x]:,}건)",
        key="중분류_선택",
    )

# 대분류 전체를 보고 있을 때만 "중분류별로 비교"가 의미 있음(중분류 하나로 좁혔으면 비교 대상이 없음)
중분류_비교_가능 = 중분류 == "(대분류 전체 보기)"
with col3:
    if 중분류_비교_가능:
        비교기준 = st.radio("비교 기준", ["불만유형별", "중분류별"], key="비교기준")
    else:
        비교기준 = "불만유형별"
        st.caption("비교 기준")
        st.caption("중분류를 좁히면 불만유형별로만 비교합니다.")

표시방식 = st.radio("표시 방식 (추이 탭 전용)", 표시방식_목록, index=1, horizontal=True, key="표시방식")

st.divider()

sub = 대분류_sub if 중분류 == "(대분류 전체 보기)" else 대분류_sub[대분류_sub["prdlstMlsfcNm"] == 중분류]
선택레이블 = 대분류 if 중분류 == "(대분류 전체 보기)" else f"{대분류} > {중분류}"
color_col = "dscsnCnClNm" if 비교기준 == "불만유형별" else "prdlstMlsfcNm"
색상_라벨 = {"dscsnCnClNm": "불만유형", "prdlstMlsfcNm": "중분류"}

tab1, tab2, tab3 = st.tabs(["📈 불만유형 비중 추이", "🛒 온라인 vs 오프라인 추이", "🗺️ 지역별 비교"])

# ── 1. 품목×시간별 불만유형/중분류 비중 추이 ──────────────────────────────
with tab1:
    if 표시방식 == "전년 동월 대비(%)" and len(전체월) < 13:
        st.caption("⚠️ 아직 1년치가 안 모여서 전년 동월 대비는 계산이 안 되는 구간이 있을 수 있어요.")

    추이 = build_trend(sub, 전체월, color_col=color_col)
    render_trend_chart(추이, 표시방식, f"{선택레이블} — 월별 {색상_라벨[color_col]} {표시방식} ({len(sub):,}건)",
                        color_col=color_col, uirevision_key=f"tab1-{선택레이블}-{color_col}", chart_key="tab1_chart")

# ── 2. 온라인 vs 오프라인, 같은 카테고리 안에서의 추이 비교 ──────────
with tab2:
    st.caption("온라인 = 국내온라인거래·모바일거래·국제온라인거래·소셜커머스. 나머지는 방문판매·일반판매·전화권유판매·TV홈쇼핑 등을 뭉뚱그린 '기타'. "
               "위에서 고른 품목 범위 안에서, 채널별로 월별 비중이 어떻게 다르게 움직이는지 비교합니다.")

    채널추이 = build_trend(sub, 전체월, color_col=color_col, extra_col="채널")
    render_trend_chart(채널추이, 표시방식, f"{선택레이블} — 채널별 월별 {색상_라벨[color_col]} {표시방식}", facet_col="채널",
                        color_col=color_col, uirevision_key=f"tab2-{선택레이블}-{color_col}", chart_key="tab2_chart")

    채널건수 = sub["채널"].value_counts()
    if len(채널건수) < 2 or 채널건수.min() < 5:
        st.caption(f"⚠️ 이 품목 범위는 채널별 건수가 적어({채널건수.to_dict()}) 추이가 불안정하게 보일 수 있습니다 — 대분류 전체 보기로 넓혀보세요.")

# ── 3. 지역별 비교 (건수 아니라 지역 내 구성비로 봐야 인구 편향이 안 생김) ──
with tab3:
    지역매트릭스 = sub.pivot_table(index="upAreaNm", columns=color_col, values="rcptYm",
                                aggfunc="count", fill_value=0)
    지역매트릭스_비중 = 지역매트릭스.div(지역매트릭스.sum(axis=1), axis=0).mul(100).round(1)
    # 건수 많은 지역이 위로 오게 정렬(비중 자체는 인구 편향 없지만, 정렬 기준은 표본 신뢰도 순으로 두는 게 보기 편함)
    지역매트릭스_비중 = 지역매트릭스_비중.loc[지역매트릭스.sum(axis=1).sort_values(ascending=False).index]
    지역매트릭스_비중 = 지역매트릭스_비중[지역매트릭스.sum(axis=0).sort_values(ascending=False).index]

    fig3 = px.imshow(지역매트릭스_비중, aspect="auto", color_continuous_scale="Oranges",
                      text_auto=".0f",
                      title=f"{선택레이블} — 지역(시도) 내 {색상_라벨[color_col]} 구성비(%)", height=CHART_HEIGHT + 60)
    fig3.update_xaxes(tickangle=45)
    fig3.update_layout(uirevision=f"tab3-{선택레이블}-{color_col}")
    st.plotly_chart(fig3, use_container_width=True, key="tab3_chart")

    지역건수 = sub["upAreaNm"].value_counts()
    저표본_지역 = 지역건수[지역건수 < 30]
    if len(저표본_지역) > 0:
        st.caption(f"⚠️ 표본이 30건 미만인 지역은 구성비가 요행일 수 있어요: {', '.join(저표본_지역.index)}")
