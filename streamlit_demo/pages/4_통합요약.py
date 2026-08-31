import pandas as pd
import plotly.express as px
import streamlit as st

from common import render_filters, generate_panel, load_topics, load_articles, generate_did_baseline

st.set_page_config(page_title="통합요약", page_icon="🧩", layout="wide")
st.title("🧩 통합요약 — 현상 → 원인 → 효과")

선택업종 = render_filters()

st.markdown(
    f"### 선택 업종: **{선택업종}**\n"
    "대시보드·토픽모델링·인과추론 세 페이지의 핵심 결과를 같은 업종 축으로 한 화면에 모았습니다."
)

매출_df = generate_panel()
토픽_df, 토픽_실데이터 = load_topics()

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("#### ① 현상 (대시보드)")
    업종_매출 = 매출_df[매출_df["업종"] == 선택업종]
    최근 = 업종_매출["매출액(백만원)"].iloc[-1]
    이전 = 업종_매출["매출액(백만원)"].iloc[-2]
    증감 = (최근 - 이전) / 이전 * 100
    st.metric("최근분기 매출", f"{최근:,.0f}백만원", f"{증감:+.1f}%")
    fig1 = px.line(업종_매출, x="분기", y="매출액(백만원)")
    fig1.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.markdown(f"#### ② 원인 (토픽모델링{'' if 토픽_실데이터 else ' · 더미'})")
    최신분기 = 토픽_df["기간"].max()
    top_토픽 = (
        토픽_df[토픽_df["기간"] == 최신분기]
        .sort_values("비중(%)", ascending=False)
        .iloc[0]
    )
    st.metric("최근분기 최다 토픽", top_토픽["토픽"], f"{top_토픽['비중(%)']:.1f}%")
    fig2 = px.area(토픽_df, x="기간", y="비중(%)", color="토픽")
    fig2.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    st.plotly_chart(fig2, use_container_width=True)
    st.caption("업종 구분 없이 소상공인 전반의 이슈를 봅니다 — 업종을 바꿔도 이 패널은 그대로예요.")

    if 토픽_실데이터:
        기사_df = load_articles()
        해당월 = {m for m in 기사_df["월"].unique() if pd.Period(m, freq="M").asfreq("Q") == pd.Period(최신분기)}
        대표기사 = (
            기사_df[기사_df["월"].isin(해당월) & (기사_df["토픽"] == top_토픽["토픽"])]
            .sort_values("날짜", ascending=False)
        )
        if not 대표기사.empty:
            기사 = 대표기사.iloc[0]
            st.caption(f"📰 대표 기사: [{기사['제목']}]({기사['URL']}) · 자세히 보려면 토픽모델링 페이지의 '시기 살펴보기'로")

with col3:
    st.markdown("#### ③ 효과 (인과추론)")
    처치효과 = generate_did_baseline()
    st.metric("추정 ATT (더미)", f"{처치효과}", help="3_인과추론.py와 같은 공통 함수(generate_did_baseline)를 참조 — 슬라이더로 조정 전 기본값과 일치")
    st.caption("처치군: 최저임금 영향 큰 업종 vs 통제군: 영향 적은 업종")
    st.caption(f"'{선택업종}'이 처치군에 해당하는 업종이라면, 매출 하락 중 일부는 정책 효과로 설명됩니다.")

st.divider()
st.info(
    "이 페이지가 설계안 5장 '통합 분석 시나리오'를 실제로 구현한 화면입니다: "
    "① 매출 하락 포착 → ② 그 시기 소상공인 전반의 이슈 확인 → ③ 정책 효과 추정까지 한 번에 봅니다. "
    "사이드바에서 업종을 바꾸면 ①③은 함께 갱신되지만, ②는 업종과 무관하게 분기 기준으로 고정됩니다."
)
