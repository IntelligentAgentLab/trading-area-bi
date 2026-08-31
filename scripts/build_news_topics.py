"""빅카인즈 뉴스에서 분기별 토픽 비중을 계산한다 (업종 구분 없음).

전제: data/raw/bigkinds/ 안에 "소상공인 OR 자영업" 검색으로 받은 .xlsx 파일들이 있음
(파일명은 자유 — 더 이상 업종별로 나눠 검색하지 않으므로 파일명이 업종을 의미하지 않는다).
자세한 검색 방법은 data/raw/bigkinds/README.md 참고.

업종으로 안 쪼개는 이유: "외식업 매출이 급증한 시기에 그 원인이 될 만한 뉴스"를 찾을 때, 그
뉴스에 "식당"·"카페" 같은 업종 키워드가 꼭 들어있어야 할 이유는 없다(예: "긴급재난지원금 지급"
뉴스는 업종명이 없어도 외식업 매출에 영향을 줌). 그래서 뉴스는 업종과 무관하게 "이 분기에
소상공인 전반에서 어떤 이슈가 있었는지"만 보고, 대시보드에서는 업종 선택과 무관하게 이 분기별
트렌드를 그대로 보여준다 (streamlit_demo/pages/4_통합요약.py의 "② 원인" 패널 참고).

사용법:
    python3 scripts/build_news_topics.py [--n-topics 4]

출력:
    data/processed/news_topic_shares.csv    — 기준월, 토픽ID, 토픽명, 비중(%), 문서수  (대시보드용)
                                                월 단위로 저장 — 분기 등 더 넓은 단위는
                                                대시보드에서 문서수 가중평균으로 즉석 집계한다.
    data/processed/news_topic_keywords.csv  — 토픽ID, 상위 키워드 10개                (라벨링용)
    data/processed/news_articles_sample.csv — 기준월, 토픽ID, 토픽명, 제목, 날짜, URL   (대시보드 "시기 살펴보기"용)
                                                월×토픽별로 그 토픽에 가장 강하게 걸린 기사 상위
                                                TOP_ARTICLES_PER_TOPIC_MONTH개씩만 남긴 샘플 —
                                                이 대시보드의 목적이 "매출이 특이했던 시기를 골라
                                                그때 뉴스를 읽어보는 것"이라, 실제 읽을 기사가 있어야 함.

주의:
- "토픽명"은 LDA가 자동으로 이름을 붙여주지 않아서, 스크립트 안 `토픽_라벨` 딕셔너리에 사람이
  미리 붙여둔 라벨을 매핑한다. 처음 실행하면 비어있으니 news_topic_keywords.csv를 보고 채워야 함.
  딕셔너리에 없는 토픽ID는 그냥 "토픽N"으로 남는다.
"""
import argparse
import glob
import sys
from pathlib import Path

import pandas as pd
from konlpy.tag import Okt
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.feature_extraction.text import CountVectorizer

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "bigkinds"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

TOP_ARTICLES_PER_TOPIC_MONTH = 5  # "시기 살펴보기"에서 월×토픽별로 보여줄 대표 기사 수

# 기사 상투어·부적합 명사 — 실제 주제와 무관하게 자주 나와서 토픽을 흐리는 단어들
불용어 = {
    "기자", "사진", "연합뉴스", "뉴스", "무단전재", "재배포", "금지", "제공", "이날",
    "오늘", "지난해", "올해", "최근", "기사", "이번", "관련", "가운데", "위해", "통해",
    # Okt 명사 추출기가 "소상공인"을 "소상"+"공인", "자영업자"를 "자영"+"업자"로 쪼갠다.
    # 검색어 자체가 이 단어들을 포함하므로 거의 모든 문서에 등장해 토픽 구분에 도움이 안 됨.
    "소상", "공인", "자영", "업자", "상공",
    # 문서빈도 상위 100개를 직접 훑어보고 추가한 것들.
    # "아시아"는 매체가 "아시아경제"라 본문에 자기 매체명을 자주 언급해서 생긴 잔재(전체 문서의
    # 31.9%에 등장 — 단일 매체 편향의 구체적 사례).
    "아시아",
    # "경제"는 문서빈도 1위(44.7%)인데, 여러 토픽 상위 키워드에 중복으로 걸릴 뿐 특정 토픽을
    # 대표하지 못해서(어디에나 "OO경제"식으로 붙는 수식어) 제외.
    "경제",
    # 문법적 기능어 — 내용과 무관하게 자주 등장.
    "지난", "대한", "대해", "오전", "오후", "이상", "종합", "기준",
}

컬럼_별칭 = {
    "날짜": ["일자", "날짜", "게재일"],
    "제목": ["제목", "뉴스제목"],
    "본문": ["본문", "내용"],
    "URL": ["URL", "링크", "기사 URL"],
}

# news_topic_keywords.csv의 상위 키워드를 사람이 보고 붙이는 라벨.
# random_state=42로 고정돼 있어 입력 데이터가 그대로면 재실행해도 같은 토픽 순서가 나오지만,
# 데이터를 추가/교체하면 토픽 내용이 달라지므로 재실행 후 news_topic_keywords.csv를 보고 채워야 함.
# 딕셔너리에 없는 토픽ID는 "토픽N"으로 그대로 남는다.
토픽_라벨: dict[str, str] = {
    "토픽0": "정치권 재난·위기 재정대응",
    "토픽1": "은행·금융권 소상공인 지원",
    "토픽2": "코로나 방역·지자체 행정",
    "토픽3": "최저임금·노사 협상",
    "토픽4": "지역화폐·소비쿠폰",
    "토픽5": "물가·민생 거시대책",
    "토픽6": "온라인 플랫폼·디지털 지원",
    "토픽7": "상생협력·중소기업 지원",
}


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    for cand in candidates:
        for col in columns:
            if cand in str(col):
                return col
    return None


def load_raw() -> pd.DataFrame:
    """data/raw/bigkinds/*.xlsx를 전부 읽어 합친다.

    "소상공인"/"자영업"으로 검색해서 받았다는 전제이므로 관련성은 검색 단계에서 이미
    보장된다 — 별도의 필터링을 하지 않는다. 중복은 (제목, 날짜) 조합으로 제거한다.

    "뉴스 식별자" 컬럼은 쓰지 않는다 — 실제로 확인해보니 서로 다른 기사(제목이 전혀 다름)인데도
    같은 식별자 값을 갖는 경우가 많았다(한 다운로드에서 16,261건 중 12,785건이 이 방식으로
    "중복" 판정되는 오탐이 발생함). 이 컬럼이 기사 단위 고유값이 아닌 것으로 보여 신뢰하지 않는다.
    """
    files = sorted(f for f in glob.glob(str(RAW_DIR / "*.xlsx")) if "~$" not in f)
    if not files:
        raise SystemExit(f"{RAW_DIR}에 .xlsx 파일이 없습니다. README.md 보고 먼저 다운로드하세요.")

    rows = []
    for f in files:
        df = pd.read_excel(f)
        날짜col = _find_column(df.columns, 컬럼_별칭["날짜"])
        제목col = _find_column(df.columns, 컬럼_별칭["제목"])
        본문col = _find_column(df.columns, 컬럼_별칭["본문"])
        URLcol = _find_column(df.columns, 컬럼_별칭["URL"])
        if not (날짜col and 제목col):
            raise SystemExit(
                f"{f}에서 날짜/제목 컬럼을 못 찾았습니다. 실제 컬럼: {list(df.columns)} "
                "— 컬럼_별칭 딕셔너리에 별칭을 추가해주세요."
            )
        sub = pd.DataFrame({
            "날짜": df[날짜col],
            "제목": df[제목col].fillna(""),
            "본문": df[본문col].fillna("") if 본문col else "",
            "URL": df[URLcol].fillna("") if URLcol else "",
        })
        rows.append(sub)
        print(f"{Path(f).name}: {len(sub)}건 로드")

    combined = pd.concat(rows, ignore_index=True)
    전체건수 = len(combined)
    combined = combined.drop_duplicates(subset=["제목", "날짜"]).reset_index(drop=True)
    중복건수 = 전체건수 - len(combined)
    if 중복건수 > 0:
        print(f"중복 기사(제목+날짜 동일) {중복건수}건 제거")

    return combined


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["날짜"] = pd.to_datetime(df["날짜"].astype(str), format="mixed", errors="coerce")
    df = df.dropna(subset=["날짜"])
    df["월"] = df["날짜"].dt.strftime("%Y-%m")
    df["분기"] = df["날짜"].dt.to_period("Q").astype(str)
    df["문서"] = (df["제목"] + " " + df["본문"]).str.strip()
    df = df[df["문서"].str.len() > 0].reset_index(drop=True)
    return df


def tokenize(texts: list[str]) -> list[list[str]]:
    okt = Okt()
    tokenized = []
    for t in texts:
        nouns = [n for n in okt.nouns(t) if len(n) >= 2 and n not in 불용어]
        tokenized.append(nouns)
    return tokenized


def fit_topics(df: pd.DataFrame, n_topics: int):
    tokenized = tokenize(df["문서"].tolist())
    docs_joined = [" ".join(toks) for toks in tokenized]

    vectorizer = CountVectorizer(
        tokenizer=str.split, token_pattern=None,
        min_df=2, max_df=0.6,
    )
    X = vectorizer.fit_transform(docs_joined)
    if X.shape[1] == 0:
        raise SystemExit("토큰화 후 남은 단어가 없습니다 — 표본이 너무 적거나 불용어 필터가 과합니다.")

    lda = LatentDirichletAllocation(n_components=n_topics, random_state=42, max_iter=20)
    doc_topic = lda.fit_transform(X)  # (문서수, n_topics)

    feature_names = vectorizer.get_feature_names_out()
    topic_keywords = []
    for k in range(n_topics):
        top_idx = lda.components_[k].argsort()[::-1][:10]
        topic_keywords.append([feature_names[i] for i in top_idx])

    return doc_topic, topic_keywords


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-topics", type=int, default=8)  # 16,255건 기준으로 튜닝한 값 — 표본이 바뀌면 재조정
    args = parser.parse_args()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    raw = load_raw()
    df = preprocess(raw)
    print(f"전처리 후 {len(df)}건 (기간 {df['월'].min()}~{df['월'].max()})")

    doc_topic, topic_keywords = fit_topics(df, args.n_topics)

    토픽_컬럼 = [f"토픽{k}" for k in range(args.n_topics)]
    topic_df = pd.DataFrame(doc_topic, columns=토픽_컬럼)
    full = pd.concat([df[["월"]].reset_index(drop=True), topic_df], axis=1)

    # 월 단위(가장 세밀한 단위)로 저장한다. 분기는 대시보드에서 월 3개를 문서수 가중평균으로
    # 합치면 되므로 따로 다시 집계할 필요가 없다 — LDA는 문서마다 토픽 가중치 합이 1이 되게
    # 나오므로, 문서수로 가중평균한 월별 비중(%)의 평균이 곧 분기 비중(%)과 정확히 같다.
    문서수 = df.groupby("월").size().rename("문서수")

    long_df = full.melt(id_vars=["월"], var_name="토픽ID", value_name="가중치")
    shares = long_df.groupby(["월", "토픽ID"])["가중치"].mean().reset_index()
    shares["비중(%)"] = shares.groupby("월")["가중치"].transform(lambda x: round(x / x.sum() * 100, 1))
    shares = shares.merge(문서수, on="월")
    shares = shares.rename(columns={"월": "기준월"})
    shares["토픽명"] = shares["토픽ID"].map(토픽_라벨).fillna(shares["토픽ID"])
    shares = shares[["기준월", "토픽ID", "토픽명", "비중(%)", "문서수"]]

    keywords_df = pd.DataFrame({
        "토픽ID": 토픽_컬럼,
        "상위키워드": [", ".join(kw) for kw in topic_keywords],
    })

    # 월×토픽별 대표 기사 — 그 토픽에 가장 강하게 걸린 순으로 상위 N개만 남긴다.
    article_rows = []
    for k, 토픽ID in enumerate(토픽_컬럼):
        sub = df[["월", "날짜", "제목", "URL"]].copy()
        sub["비중"] = doc_topic[:, k]
        sub["토픽ID"] = 토픽ID
        top = (
            sub.sort_values("비중", ascending=False)
            .groupby("월", group_keys=False)
            .head(TOP_ARTICLES_PER_TOPIC_MONTH)
        )
        article_rows.append(top)
    articles = pd.concat(article_rows, ignore_index=True)
    articles["날짜"] = articles["날짜"].dt.strftime("%Y-%m-%d")
    articles["토픽명"] = articles["토픽ID"].map(토픽_라벨).fillna(articles["토픽ID"])
    articles = articles.rename(columns={"월": "기준월"})
    articles = articles[["기준월", "토픽ID", "토픽명", "제목", "날짜", "URL"]]
    articles = articles.sort_values(["기준월", "토픽ID"]).reset_index(drop=True)

    shares_path = PROCESSED_DIR / "news_topic_shares.csv"
    keywords_path = PROCESSED_DIR / "news_topic_keywords.csv"
    articles_path = PROCESSED_DIR / "news_articles_sample.csv"
    shares.to_csv(shares_path, index=False, encoding="utf-8-sig")
    keywords_df.to_csv(keywords_path, index=False, encoding="utf-8-sig")
    articles.to_csv(articles_path, index=False, encoding="utf-8-sig")

    print(f"저장 완료: {shares_path}")
    print(f"저장 완료: {keywords_path}")
    print(f"저장 완료: {articles_path} ({len(articles)}건)")
    print("\n토픽별 상위 키워드 (이거 보고 스크립트 안 토픽_라벨 딕셔너리를 채우세요):")
    for row in keywords_df.itertuples():
        print(f"  {row.토픽ID}: {row.상위키워드}")


if __name__ == "__main__":
    sys.exit(main())
