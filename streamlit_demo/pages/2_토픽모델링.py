import pandas as pd
import plotly.express as px
import streamlit as st

from common import load_topics, load_topic_keywords, load_articles

st.set_page_config(page_title="토픽모델링", page_icon="🗣️", layout="wide")

col_단위, col_표시값 = st.columns(2)
단위 = col_단위.radio("표시 단위", ["월", "분기"], horizontal=True, key="토픽_표시단위")
표시값 = col_표시값.radio("표시값", ["비중(%)", "개수"], horizontal=True, key="토픽_표시값")
토픽_df, 실데이터 = load_topics(단위)
토픽키워드 = load_topic_keywords()  # 실데이터일 때만 채워짐 — {토픽명: [키워드,...]}
기사_df = load_articles()  # 실데이터일 때만 채워짐 — 월×토픽별 대표 기사(제목·날짜·URL)
토픽목록_실제 = sorted(토픽_df["토픽"].unique())

st.title(f"🗣️ 토픽모델링{'' if 실데이터 else ' (더미 데이터)'}")
st.caption("매출 대시보드에서 궁금했던 시기를 골라, 그때 소상공인 관련 뉴스에서 어떤 이슈가 있었는지 확인하는 페이지입니다. "
           "업종 구분은 없습니다 — 대시보드·인과추론과 데이터로 연결되지 않고 독립적으로 동작합니다.")
if 실데이터:
    st.caption("BigKinds 뉴스(소상공인 OR 자영업 검색) → LDA 토픽모델링 결과입니다. "
               "표본 규모는 data/raw/bigkinds/README.md 참고. 월 단위는 표본이 더 적어 그래프가 들쭉날쭉할 수 있습니다.")
    if 표시값 == "개수":
        st.caption("'개수'는 비중(%)×문서수로 역산한 예상 건수입니다 — 기사 하나가 여러 토픽에 확률적으로 "
                   "걸쳐 있는 LDA 특성상 정수로 딱 떨어지지 않을 수 있어요(예: 3.7건).")

st.subheader(f"{단위}별 토픽 {표시값} 추이")
fig = px.area(토픽_df, x="기간", y=표시값, color="토픽")
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── 시기 살펴보기 ────────────────────────────────────────────────
st.subheader("🔍 시기 살펴보기")
st.caption("매출이 튀거나 꺼진 시기를 골라보세요 — 그 시기 토픽 비중, 직전 대비 변화, 대표 기사를 한 번에 보여줍니다.")

기간목록 = sorted(토픽_df["기간"].unique())
선택기간 = st.select_slider("확인할 기간", options=기간목록, value=기간목록[-1])

변화_단위 = "%p" if 표시값 == "비중(%)" else "건"

이번 = 토픽_df[토픽_df["기간"] == 선택기간].set_index("토픽")[표시값]
기간idx = 기간목록.index(선택기간)
이전기간 = 기간목록[기간idx - 1] if 기간idx > 0 else None

colA, colB = st.columns(2)

with colA:
    st.markdown(f"**{선택기간} 토픽 {표시값}**")
    fig2 = px.bar(이번.reset_index(), x="토픽", y=표시값, color="토픽")
    fig2.update_layout(showlegend=False, height=360)
    st.plotly_chart(fig2, use_container_width=True)

with colB:
    if 이전기간:
        st.markdown(f"**직전({이전기간}) 대비 변화**")
        이전 = 토픽_df[토픽_df["기간"] == 이전기간].set_index("토픽")[표시값]
        변화 = (이번 - 이전.reindex(이번.index).fillna(0)).round(1)
        변화_df = 변화.reset_index()
        변화_df.columns = ["토픽", f"변화({변화_단위})"]
        변화_df = 변화_df.sort_values(f"변화({변화_단위})")
        fig3 = px.bar(변화_df, x=f"변화({변화_단위})", y="토픽", orientation="h",
                      color=f"변화({변화_단위})", color_continuous_scale="RdBu_r", color_continuous_midpoint=0)
        fig3.update_layout(height=360, coloraxis_showscale=False)
        st.plotly_chart(fig3, use_container_width=True)
        top_증가 = 변화_df.iloc[-1]
        if top_증가[f"변화({변화_단위})"] > 0:
            st.caption(f"⬆️ 가장 많이 증가한 토픽: **{top_증가['토픽']}** ({top_증가[f'변화({변화_단위})']:+.1f}{변화_단위}) — 이 시기에 무슨 일이 있었는지 아래 대표 기사에서 확인해보세요.")
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
