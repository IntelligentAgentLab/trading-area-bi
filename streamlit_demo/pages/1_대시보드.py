import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from common import render_filters, generate_panel, 업종목록, 분기목록

st.set_page_config(page_title="대시보드", page_icon="📊", layout="wide")
st.title("📊 대시보드 (더미 데이터)")

선택업종 = render_filters()
rng = np.random.default_rng(0)

매출_df = generate_panel()

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("업종별 매출 추이")
    비교업종 = st.multiselect("비교할 업종 (기본값 = 공통 필터 선택 업종)", 업종목록, default=[선택업종])
    filtered = 매출_df[매출_df["업종"].isin(비교업종)]
    fig = px.line(filtered, x="분기", y="매출액(백만원)", color="업종", markers=True)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader(f"KPI 카드 · {선택업종}")
    업종_df = 매출_df[매출_df["업종"] == 선택업종]
    최근분기 = 분기목록[-1]
    이전분기 = 분기목록[-2]
    최근 = 업종_df[업종_df["분기"] == 최근분기]["매출액(백만원)"].sum()
    이전 = 업종_df[업종_df["분기"] == 이전분기]["매출액(백만원)"].sum()
    증감률 = (최근 - 이전) / 이전 * 100
    st.metric(f"{선택업종} 매출 (최근분기)", f"{최근:,.0f}백만원", f"{증감률:+.1f}%")
    st.metric("업종 수", f"{len(업종목록)}개")
    st.metric("데이터 기간", f"{분기목록[0]} ~ {분기목록[-1]}")

st.caption("※ 공통 필터에서 업종을 바꾸면 KPI 카드와 비교 업종 기본값이 함께 바뀝니다 — 토픽모델링·통합요약 페이지에서도 동일 업종이 유지됩니다.")

st.divider()

col3, col4 = st.columns(2)

with col3:
    st.subheader(f"요일 × 시간대 매출 히트맵 · {선택업종}")
    요일 = ["월", "화", "수", "목", "금", "토", "일"]
    시간대 = [f"{h}시" for h in range(9, 22)]
    heat = rng.integers(10, 100, size=(len(요일), len(시간대)))
    heat_df = pd.DataFrame(heat, index=요일, columns=시간대)
    fig2 = px.imshow(heat_df, aspect="auto", color_continuous_scale="Blues")
    st.plotly_chart(fig2, use_container_width=True)

with col4:
    st.subheader("상권 지도 (더미 점포 위치)")
    n = 150
    map_df = pd.DataFrame(
        {
            "lat": 37.55 + rng.normal(0, 0.03, n),
            "lon": 126.98 + rng.normal(0, 0.03, n),
        }
    )
    st.map(map_df, size=20)

st.caption("※ 전부 랜덤 생성된 더미 데이터이며 실제 상권·매출과 무관합니다.")
