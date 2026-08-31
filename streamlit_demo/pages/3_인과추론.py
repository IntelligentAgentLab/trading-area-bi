import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import render_filters, generate_did_baseline

st.set_page_config(page_title="인과추론", page_icon="📈", layout="wide")
st.title("📈 인과추론 (더미 DiD 데모)")

선택업종 = render_filters()

rng = np.random.default_rng(3)

분기목록 = pd.period_range("2016Q1", "2020Q4", freq="Q").astype(str)
처치시점 = "2018Q1"
처치idx = 분기목록.get_loc(처치시점)

st.caption(
    f"공통 필터 선택 업종: **{선택업종}**. DiD는 처치군(음식점업 등 최저임금 영향 큰 업종)과 "
    "통제군(전문서비스업 등 영향 적은 업종)을 비교하는 구조라, 선택 업종이 처치군에 해당하는지에 "
    "따라 해석이 달라집니다."
)

기본_처치효과 = int(round(generate_did_baseline()))
처치효과 = st.slider("가상 처치효과 크기 (더미, 통합요약 페이지와 기본값 공유)", -30, 0, 기본_처치효과)

base = 100 + rng.normal(0, 3, size=len(분기목록)).cumsum()
처치군 = base.copy()
통제군 = base.copy() + rng.normal(0, 2, size=len(분기목록))

처치군[처치idx:] += 처치효과 + rng.normal(0, 2, size=len(분기목록) - 처치idx)

df = pd.DataFrame({"분기": 분기목록, "처치군(예: 음식점업)": 처치군, "통제군(예: 전문서비스업)": 통제군})

st.subheader("평행추세 검증 + DiD 처치효과")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df["분기"], y=df["처치군(예: 음식점업)"], name="처치군", mode="lines+markers"))
fig.add_trace(go.Scatter(x=df["분기"], y=df["통제군(예: 전문서비스업)"], name="통제군", mode="lines+markers"))
fig.add_vline(x=처치idx, line_dash="dash", line_color="red", annotation_text="최저임금 인상 시점")
st.plotly_chart(fig, use_container_width=True)

col1, col2, col3 = st.columns(3)
col1.metric("추정 ATT (처치효과)", f"{처치효과}")
col2.metric("사전기간 평행추세", "p > 0.05 (더미)")
col3.metric("Placebo 검정", "δ ≈ 0 (더미)")

st.subheader("계수표 (더미)")
coef_df = pd.DataFrame(
    {
        "변수": ["Treat", "Post", "Treat × Post (ATT)"],
        "계수": [round(rng.normal(0, 1), 2), round(rng.normal(0, 1), 2), 처치효과],
        "표준오차": [round(abs(rng.normal(1, 0.3)), 2) for _ in range(3)],
    }
)
st.dataframe(coef_df, use_container_width=True)

st.caption("※ 실제 프로젝트에서는 statsmodels/linearmodels로 계산한 진짜 DiD 결과가 이 자리에 들어갑니다. "
           "결과는 이 페이지 안에서만 표시되며 별도 파일로 내보내지 않습니다 (대시보드와 독립).")
