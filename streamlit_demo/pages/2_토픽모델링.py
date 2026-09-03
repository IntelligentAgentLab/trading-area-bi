import pandas as pd
import plotly.express as px
import streamlit as st

from common import load_topics, load_topic_keywords, load_articles

st.set_page_config(page_title="토픽모델링", page_icon="🗣️", layout="wide")

단위 = st.radio("표시 단위", ["월", "분기"], horizontal=True, key="토픽_표시단위")
토픽_df, 실데이터 = load_topics(단위)
토픽키워드 = load_topic_keywords()  # 실데이터일 때만 채워짐 — {토픽명: [키워드,...]}
기사_df = load_articles()  # 실데이터일 때만 채워짐 — 월×토픽별 대표 기사(제목·날짜·URL)
토픽목록_실제 = sorted(토픽_df["토픽"].unique())

st.title(f"🗣️ 토픽모델링{'' if 실데이터 else ' (더미 데이터)'}")
st.caption("")
if 실데이터:
    st.caption("")

st.subheader(f"{단위}별 토픽 비중 추이")
# area(누적)로 그리면 토픽이 8개라 위로 쌓이면서 겹쳐서, 각 토픽 개별 추이를 읽기 어려웠음 —
# line으로 바꿔서 겹쳐 그리면 서로 가리지 않고 각자의 흐름을 그대로 비교할 수 있다.
fig = px.line(토픽_df, x="기간", y="비중(%)", color="토픽", markers=True)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── 시기 살펴보기 ────────────────────────────────────────────────
st.subheader("🔍 시기 살펴보기")
st.caption("매출이 튀거나 꺼진 시기를 골라보세요 — 그 시기 토픽 비중, 직전 대비 변화, 대표 기사를 한 번에 보여줍니다.")

기간목록 = sorted(토픽_df["기간"].unique())
선택기간 = st.select_slider("확인할 기간", options=기간목록, value=기간목록[-1])

이번 = 토픽_df[토픽_df["기간"] == 선택기간].set_index("토픽")["비중(%)"]
기간idx = 기간목록.index(선택기간)
이전기간 = 기간목록[기간idx - 1] if 기간idx > 0 else None

colA, colB = st.columns(2)

with colA:
    st.markdown(f"**{선택기간} 토픽 비중**")
    fig2 = px.bar(이번.reset_index(), x="토픽", y="비중(%)", color="토픽")
    fig2.update_layout(showlegend=False, height=360)
    st.plotly_chart(fig2, use_container_width=True)

with colB:
    if 이전기간:
        st.markdown(f"**직전({이전기간}) 대비 변화**")
        이전 = 토픽_df[토픽_df["기간"] == 이전기간].set_index("토픽")["비중(%)"]
        변화 = (이번 - 이전.reindex(이번.index).fillna(0)).round(1)
        변화_df = 변화.reset_index()
        변화_df.columns = ["토픽", "변화(%p)"]
        변화_df = 변화_df.sort_values("변화(%p)")
        fig3 = px.bar(변화_df, x="변화(%p)", y="토픽", orientation="h",
                      color="변화(%p)", color_continuous_scale="RdBu_r", color_continuous_midpoint=0)
        fig3.update_layout(height=360, coloraxis_showscale=False)
        st.plotly_chart(fig3, use_container_width=True)
        top_증가 = 변화_df.iloc[-1]
        if top_증가["변화(%p)"] > 0:
            st.caption(f"⬆️ 가장 많이 증가한 토픽: **{top_증가['토픽']}** ({top_증가['변화(%p)']:+.1f}%p) — 이 시기에 무슨 일이 있었는지 아래 대표 기사에서 확인해보세요.")
    else:
        st.caption("가장 이른 시기라 직전 대비 비교가 없습니다.")

st.markdown(f"##### 📰 {선택기간} 대표 기사")
if not 실데이터 or 기사_df.empty:
    st.caption("실데이터가 있어야 기사 목록을 볼 수 있어요 — data/raw/bigkinds/README.md 참고해 데이터를 받고 스크립트를 실행하세요.")
else:
    if 단위 == "월":
        해당월 = {선택기간}
    else:
        해당월 = {m for m in 기사_df["월"].unique() if pd.Period(m, freq="M").asfreq("Q") == pd.Period(선택기간)}
    기간내_기사 = 기사_df[기사_df["월"].isin(해당월)]

    토픽필터 = st.selectbox("토픽으로 좁히기", ["전체"] + 토픽목록_실제, key="기사_토픽필터")
    if 토픽필터 != "전체":
        기간내_기사 = 기간내_기사[기간내_기사["토픽"] == 토픽필터]
        if 토픽필터 in 토픽키워드:
            st.caption(f"'{토픽필터}' 키워드: {', '.join(토픽키워드[토픽필터])}")

    기간내_기사 = 기간내_기사.sort_values("날짜", ascending=False)
    if 기간내_기사.empty:
        st.caption("이 조건에 맞는 대표 기사가 없습니다.")
    else:
        st.dataframe(
            기간내_기사[["날짜", "토픽", "제목", "URL"]],
            hide_index=True,
            use_container_width=True,
            column_config={
                "URL": st.column_config.LinkColumn("링크", display_text="기사 보기"),
            },
        )

if not 실데이터:
    st.caption("※ data/raw/bigkinds/에 뉴스 엑셀을 넣고 scripts/build_news_topics.py를 실행하면 이 페이지가 실데이터로 자동 전환됩니다.")
