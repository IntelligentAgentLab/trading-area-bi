"""
4_인과추론.py — 최저임금 인상의 매출 효과 (이중차분법, DID)
================================================================================
이 페이지는 회귀를 직접 돌리지 않고, 미리 계산해 둔 결과 CSV 3개만 읽어서 그립니다.
자치구x업종 고정효과 회귀가 4~5분 걸려 Streamlit 앱에서 매번 돌리기에 부적합하고,
Streamlit Cloud 메모리 한도에도 부담이 되기 때문입니다.

  결과 CSV  : data/processed/did_event_study.csv
              data/processed/did_static_summary.csv
              data/processed/did_pretrend.csv
  재생성    : python scripts/build_did_results.py
              (비교 연도를 바꾸거나 원본 매출 데이터가 갱신됐을 때만)

필요 패키지 : streamlit, pandas, plotly   (statsmodels/matplotlib 불필요)
================================================================================
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ------------------------------------------------------------------
# 상수
# ------------------------------------------------------------------
# 색상 (색각 이상 대비 검증 완료, 최소 ΔE 24.7)
C_POOLED = "#2a78d6"   # 사전기간 풀링 (강의자료 방식)
C_YOY = "#eb6834"      # 전년동기 매칭 (계절성 제거)
C_MUTED = "#52514e"
C_GRID = "#d8d7d2"

MIN_WAGE = {2021: 8720, 2022: 9160, 2023: 9620, 2024: 9860, 2025: 10030, 2026: 10320}

M_POOLED = "사전기간 풀링(강의자료 29~32쪽)"
M_YOY = "전년동기 매칭(계절성 제거)"

FILES = {
    "est": "did_event_study.csv",
    "static": "did_static_summary.csv",
    "pretrend": "did_pretrend.csv",
}


# ------------------------------------------------------------------
# 데이터 적재
# ------------------------------------------------------------------
def _data_dir() -> Path | None:
    """<저장소 루트>/data/processed 를 찾는다.
    이 파일 위치는 <루트>/streamlit_demo/pages/4_인과추론.py 이므로 parents[2] 가 루트."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "data" / "processed",   # 저장소 루트 기준 (정상 배치)
        here.parents[1] / "data" / "processed",   # streamlit_demo/data/processed
        Path.cwd() / "data" / "processed",        # 실행 위치 기준
    ]
    for c in candidates:
        if (c / FILES["est"]).exists():
            return c
    return None


@st.cache_data
def load_did_results():
    """실제 결과 CSV가 있으면 읽어서 반환하고, 없으면 None 을 반환한다.
    (common.py 의 load_topics() 과 같은 '있으면 쓰고 없으면 폴백' 패턴)"""
    d = _data_dir()
    if d is None:
        return None
    return (
        pd.read_csv(d / FILES["est"], encoding="utf-8-sig"),
        pd.read_csv(d / FILES["static"], encoding="utf-8-sig"),
        pd.read_csv(d / FILES["pretrend"], encoding="utf-8-sig"),
    )


# ------------------------------------------------------------------
# 그래프
# ------------------------------------------------------------------
def build_figure(est_w: pd.DataFrame, pre_year: int, post_year: int) -> go.Figure:
    """선택 구간의 분기별 ATT 추이를 두 추정량으로 겹쳐 그린다."""
    qcodes = [pre_year * 10 + k for k in (1, 2, 3, 4)] + [post_year * 10 + k for k in (1, 2, 3, 4)]
    pos = {c: i for i, c in enumerate(qcodes)}
    ticktext = [f"{c // 10}Q{c % 10}" for c in qcodes]

    fig = go.Figure()
    for method, color, dash in ((M_POOLED, C_POOLED, "solid"), (M_YOY, C_YOY, "dash")):
        d = est_w[est_w["method"] == method].sort_values("qcode")
        if d.empty:
            continue
        x = [pos[c] for c in d["qcode"]]
        att = (d["att"] * 100).tolist()
        lo = (d["ci_low"] * 100).tolist()
        hi = (d["ci_up"] * 100).tolist()
        pv = d["pvalue"].tolist()
        rgba = f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.13)"

        # 95% 신뢰구간 밴드
        fig.add_trace(go.Scatter(
            x=x + x[::-1], y=hi + lo[::-1], mode="lines", fill="toself",
            fillcolor=rgba, line=dict(width=0), hoverinfo="skip",
            showlegend=False, name=f"{method} CI"))

        # ATT 꺾은선
        fig.add_trace(go.Scatter(
            x=x, y=att, mode="lines+markers", name=method,
            line=dict(color=color, width=2.5, dash=dash),
            marker=dict(size=9, color=color, line=dict(color="white", width=1.5)),
            customdata=list(zip(lo, hi, pv)),
            hovertemplate=(
                "<b>%{text}</b><br>"
                f"{method}<br>"
                "ATT %{y:+.2f}%<br>"
                "95%% CI [%{customdata[0]:+.2f}%%, %{customdata[1]:+.2f}%%]<br>"
                "p = %{customdata[2]:.3f}<extra></extra>"),
            text=[f"{c // 10}Q{c % 10}" for c in d["qcode"]]))

    fig.add_hline(y=0, line=dict(color=C_MUTED, width=1, dash="dot"))
    fig.add_vline(x=3.5, line=dict(color="#0b0b0b", width=1.6, dash="dash"))
    rate = MIN_WAGE[post_year] / MIN_WAGE[pre_year] - 1
    fig.add_annotation(
        x=3.58, y=1, yref="paper", xanchor="left", yanchor="top", showarrow=False,
        text=(f"{post_year}년 최저임금 인상<br>"
              f"{MIN_WAGE[pre_year]:,}원 → {MIN_WAGE[post_year]:,}원 ({rate:+.1%})"),
        font=dict(size=11, color=C_MUTED), align="left")

    fig.update_layout(
        height=520, hovermode="x unified",
        plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=70, r=40, t=50, b=70),
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="left", x=0),
        font=dict(size=13),
        title=dict(text=f"분기별 ATT 추이 : {pre_year}년 vs {post_year}년",
                   font=dict(size=17), x=0, xanchor="left"))
    fig.update_xaxes(tickmode="array", tickvals=list(range(8)), ticktext=ticktext,
                     range=[-0.4, 7.4], showgrid=False, title=None,
                     linecolor=C_GRID, tickfont=dict(color=C_MUTED))
    fig.update_yaxes(
        title=dict(text="ATT : 실험군-대조군 로그매출 격차 (%)",
                   font=dict(color=C_MUTED, size=12)),
        gridcolor=C_GRID, zeroline=False,
        linecolor=C_GRID, tickfont=dict(color=C_MUTED))
    return fig


# ==================================================================
# 본문
# ==================================================================
st.title("📈 인과추론")
st.caption(
    "서울시 자치구 × 서비스업종 × 분기 패널(2021Q1~2026Q1)에 이중차분법(DID)을 적용해 "
    "최저임금 인상이 매출에 미친 영향을 추정했습니다. 최저임금 미만율이 높은 업종을 실험군, "
    "낮은 업종을 대조군으로 두고, 매년 1월 발효되는 인상을 각각 별개의 처치로 보아 2개년씩 비교합니다."
)

results = load_did_results()

if results is None:
    st.warning(
        "**DID 결과 파일이 아직 없습니다.**\n\n"
        "저장소 루트에서 아래를 실행해 `data/processed/` 에 결과 CSV 3개를 만들어 주세요.\n\n"
        "```bash\npython scripts/build_did_results.py\n```\n\n"
        f"필요한 파일: `{FILES['est']}`, `{FILES['static']}`, `{FILES['pretrend']}`"
    )
    st.stop()

est, static, pretrend = results

# ---- 연도 선택 ----
options = [(int(a), int(b)) for a, b in
           static[["pre_year", "post_year"]].drop_duplicates()
           .sort_values("pre_year").itertuples(index=False, name=None)]
labels = {w: f"{w[0]}년 vs {w[1]}년  (최저임금 {MIN_WAGE[w[1]] / MIN_WAGE[w[0]] - 1:+.1%})"
          for w in options}

choice = st.selectbox("비교 구간 선택", options,
                      format_func=lambda w: labels[w], index=len(options) - 1)
pre_year, post_year = choice

srow = static[(static.pre_year == pre_year) & (static.post_year == post_year)].iloc[0]
prow = pretrend[pretrend.pre_year == pre_year]
n_sig = int(prow["n_placebo_sig"].iloc[0]) if len(prow) else 0
n_pl = int(prow["n_placebo"].iloc[0]) if len(prow) else 0

# ---- 요약 지표 카드 ----
st.markdown("")
c1, c2, c3, c4 = st.columns(4)
c1.metric("최저임금 인상률", f"{MIN_WAGE[post_year] / MIN_WAGE[pre_year] - 1:+.1%}",
          help=f"{MIN_WAGE[pre_year]:,}원 → {MIN_WAGE[post_year]:,}원")
c2.metric("정적 DID ATT", f"{srow.att * 100:+.2f}%",
          help="사전연도 4개 분기 vs 사후연도 4개 분기. 양쪽 모두 Q1~Q4를 온전히 "
               "포함해 계절 효과가 자동으로 상쇄됩니다.")
c3.metric("p값 (wild)", f"{srow.pvalue_wild:.3f}",
          help=f"Rademacher wild cluster bootstrap. 처치가 업종 단위로 배정되어 "
               f"유효 클러스터가 {int(srow.n_clusters)}개뿐이라 소수 클러스터 보정을 적용했습니다.")
c4.metric("사전 placebo", f"{n_sig} / {n_pl}개",
          help="처치가 없었던 사전연도에도 격차가 유의하게 벌어졌는지 센 값입니다. "
               "0개여야 평행추세 가정이 성립하고 ATT를 인과효과로 읽을 수 있습니다.")

st.caption(
    f"95% 신뢰구간 [{srow.ci_low * 100:+.2f}%, {srow.ci_up * 100:+.2f}%] · "
    f"통상 클러스터 p={srow.pvalue_cluster:.3f} · "
    f"관측치 {int(srow.n_obs):,}개 · 클러스터(업종) {int(srow.n_clusters)}개"
    + ("  —  ⚠ 처치 이전에 이미 유의한 격차 변화가 있어 이 구간의 ATT는 "
       "인과효과로 해석하기 어렵습니다." if n_sig else "")
)

# ---- 그래프 ----
st.plotly_chart(
    build_figure(est[est["window"] == f"{pre_year}_{post_year}"], pre_year, post_year),
    use_container_width=True)

with st.expander("두 추정량은 무엇이 다른가요?"):
    st.markdown(
        f"""
**{M_POOLED}** — 사후 분기 하나를 사전연도 **4개 분기 전체의 평균**과 비교합니다.
기준선을 4개 분기로 만들어 정밀하지만, 한쪽은 특정 계절이고 다른 쪽은 사계절 평균이라
**그 분기의 계절 편차가 추정치에 섞입니다.** 이 데이터에서 실험군-대조군 격차의
계절 편차는 Q1 −2.2%p / Q2 +0.6%p / Q3 +2.0%p / Q4 +0.0%p 수준입니다.

**{M_YOY}** — 사후 분기를 **전년 같은 분기 하나**와만 비교합니다(2023Q3 ↔ 2022Q3).
같은 계절이라 계절 편차가 양쪽에 똑같이 들어 있다가 뺄셈에서 사라집니다.
대신 기준선이 1개 분기뿐이라 신뢰구간은 더 넓어집니다.

수치를 인용할 때는 **전년동기 매칭** 또는 위의 **정적 DID**를 쓰고, 풀링 추정치는
"강의자료 방식을 그대로 적용하면 왜 다르게 나오는가"를 보여주는 대비용으로 쓰는 것이 좋습니다.
"""
    )
