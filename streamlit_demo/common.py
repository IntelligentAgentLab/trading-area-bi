from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

월목록 = pd.period_range("2022-01", "2025-12", freq="M").astype(str)
토픽목록 = ["환불·위생", "가격·인상", "배송지연", "인건비 부담", "경영난"]

# C가 scripts/build_news_topics.py로 만드는 실제 산출물 — 있으면 더미 대신 이걸 쓴다.
TOPIC_SHARES_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "news_topic_shares.csv"
TOPIC_KEYWORDS_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "news_topic_keywords.csv"
ARTICLES_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "news_articles_sample.csv"

# WordCloud가 font_path 없이 기본 폰트를 쓰면 한글이 네모(□)로 깨진다 — 한글 지원 폰트를 찾아준다.
_한글_폰트_후보 = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",  # macOS
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # Linux(나눔고딕 설치 시)
    "C:/Windows/Fonts/malgun.ttf",  # Windows
]


def find_korean_font() -> str | None:
    """찾으면 폰트 경로를, 못 찾으면 None을 반환(이 경우 워드클라우드는 한글이 깨진 채로 표시됨)."""
    for path in _한글_폰트_후보:
        if Path(path).exists():
            return path
    return None


@st.cache_data
def generate_topics() -> pd.DataFrame:
    """더미 월×토픽 비중 표 (실제 데이터가 없을 때의 대체용).

    업종 구분이 없다 — 뉴스 토픽은 "이 시기에 소상공인 전반에서 어떤 이슈가 있었는지"를
    보는 것이라 업종 선택과 무관하게 동일하게 표시된다 (4_통합요약.py의 "② 원인" 패널 참고).
    "문서수"는 월별 표본 크기 — 분기 등으로 다시 묶을 때 가중평균에 쓴다(_aggregate_topics 참고).
    """
    rng = np.random.default_rng(7)
    rows = []
    for 토픽 in 토픽목록:
        base = rng.uniform(5, 25)
        trend = rng.normal(0, 2, size=len(월목록)).cumsum()
        for i, 월 in enumerate(월목록):
            비중 = max(base + trend[i], 1)
            rows.append({
                "월": 월, "토픽": 토픽, "비중(%)": round(비중, 1),
                "문서수": int(rng.integers(20, 80)),
            })
    return pd.DataFrame(rows)


def _aggregate_topics(월별_df: pd.DataFrame, 단위: str) -> pd.DataFrame:
    """월별 비중(%)을 "월" 그대로 쓰거나, "분기"로 문서수 가중평균해 묶어준다.

    LDA는 문서마다 토픽 가중치 합이 1이 되게 나오므로, 문서수로 가중평균한 월별 비중(%)의
    평균이 곧 분기 단위로 직접 계산했을 때의 비중(%)과 정확히 같다 — 그래서 build_news_topics.py가
    분기를 따로 저장하지 않고, 여기서 그때그때 묶어도 결과가 달라지지 않는다.

    "개수"는 비중(%)/100 × 문서수로 역산한 것 — 문서 하나가 여러 토픽에 확률적으로 걸쳐 있는
    LDA 특성상 정수로 딱 떨어지지 않는 "예상 건수"다(예: 3.7건). 비중은 월/분기별 상대 크기
    비교에, 개수는 절대적인 기사량 비교에 쓰라고 둘 다 계산해둔다. 분기로 묶을 때 비중은
    가중평균(합쳐서 다시 100%로), 개수는 그냥 합산(3개월치를 더하면 됨 — 이쪽은 원래도
    가산적인 양이라 가중평균이 필요 없다).
    """
    df = 월별_df.copy()
    df["개수"] = (df["비중(%)"] / 100 * df["문서수"]).round(1)

    if 단위 == "월":
        return df[["월", "토픽", "비중(%)", "개수"]].rename(columns={"월": "기간"})

    df["분기"] = pd.to_datetime(df["월"], format="%Y-%m").dt.to_period("Q").astype(str)

    def _wavg(g: pd.DataFrame) -> float:
        return np.average(g["비중(%)"], weights=g["문서수"])

    비중 = df.groupby(["분기", "토픽"]).apply(_wavg, include_groups=False).reset_index(name="비중(%)")
    비중["비중(%)"] = 비중.groupby("분기")["비중(%)"].transform(lambda x: round(x / x.sum() * 100, 1))

    개수 = df.groupby(["분기", "토픽"])["개수"].sum().round(1).reset_index()

    q = 비중.merge(개수, on=["분기", "토픽"])
    return q.rename(columns={"분기": "기간"})


@st.cache_data
def load_topics(단위: str = "분기") -> tuple[pd.DataFrame, bool]:
    """news_topic_shares.csv(build_news_topics.py 산출물)가 있으면 실데이터를, 없으면 더미를 반환.

    단위="월"이면 월별 원본 그대로, 단위="분기"면 문서수 가중평균(비중)·합산(개수)으로 분기
    단위로 묶어서 반환한다. 반환 컬럼은 항상 "기간"(월 또는 분기 문자열)·"토픽"·"비중(%)"·"개수".
    업종 컬럼은 없다(업종별로 뉴스를 가르지 않기로 했기 때문). 두 번째 반환값(실데이터 여부)으로
    페이지에서 "더미 데이터" 표시를 켜고 끌 수 있다.
    """
    if TOPIC_SHARES_PATH.exists():
        df = pd.read_csv(TOPIC_SHARES_PATH, encoding="utf-8-sig")
        df = df.rename(columns={"기준월": "월", "토픽명": "토픽"})[["월", "토픽", "비중(%)", "문서수"]]
        return _aggregate_topics(df, 단위), True
    return _aggregate_topics(generate_topics(), 단위), False


@st.cache_data
def load_articles() -> pd.DataFrame:
    """news_articles_sample.csv(월×토픽별 대표 기사) — 실데이터 없으면 빈 DataFrame.

    이 대시보드의 목적이 "매출이 특이했던 시기를 골라 그때 뉴스를 읽어보는 것"이라, 더미로
    가짜 기사 제목을 지어내지 않는다 — 실데이터가 없으면 이 기능 자체를 페이지에서 숨긴다.
    컬럼: 월, 토픽, 제목, 날짜, URL
    """
    if not ARTICLES_PATH.exists():
        return pd.DataFrame(columns=["월", "토픽", "제목", "날짜", "URL"])
    df = pd.read_csv(ARTICLES_PATH, encoding="utf-8-sig")
    return df.rename(columns={"기준월": "월", "토픽명": "토픽"})[["월", "토픽", "제목", "날짜", "URL"]]


@st.cache_data
def load_topic_keywords() -> dict[str, list[str]]:
    """토픽명 -> 상위 키워드 리스트 (워드클라우드용). 실데이터 없으면 빈 dict를 반환."""
    if not (TOPIC_SHARES_PATH.exists() and TOPIC_KEYWORDS_PATH.exists()):
        return {}
    shares = pd.read_csv(TOPIC_SHARES_PATH, encoding="utf-8-sig")
    id_to_name = shares.drop_duplicates("토픽ID").set_index("토픽ID")["토픽명"].to_dict()
    keywords = pd.read_csv(TOPIC_KEYWORDS_PATH, encoding="utf-8-sig")
    return {
        id_to_name.get(row.토픽ID, row.토픽ID): [kw.strip() for kw in row.상위키워드.split(",")]
        for row in keywords.itertuples()
    }
