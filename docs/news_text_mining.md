---
title: 뉴스 텍스트마이닝 코드 및 결과 설명
---

# 뉴스 텍스트마이닝 코드 및 결과 설명

이 문서 하나만 읽으면 "어떤 데이터를 가져와서, 어떻게 텍스트마이닝을 진행했는지" 알 수 있도록
정리했습니다. 소비상권 BI 프로젝트의 C(텍스트 분석) 역할 산출물입니다.

## 1. 사용 데이터

| 항목 | 내용 |
|---|---|
| 출처 | BigKinds(빅카인즈) 뉴스 검색·다운로드 (Open API가 유료라 수동 다운로드) |
| 검색어 | `소상공인 OR 자영업` |
| 언론사 | 아시아경제 (단일 매체 — 8번 항목 한계 참고) |
| 원본 건수 | 16,261건 |
| 다운로드 기간 | 2021-08-23 ~ 2026-08-23 |
| 실제 분석 기간 | 기사 날짜 기준 2021-08 ~ 2026-08 |
| 중복 제거 후 | 16,255건 (제목+날짜 완전 일치 6건 제거) |
| 원본 파일 위치 | `data/raw/bigkinds/*.xlsx` |

원본 엑셀 컬럼 중 실제로 쓰는 것: 일자, 제목, 본문, URL. (본문은 BigKinds 무료 다운로드 제한으로
기사당 최대 200자까지만 제공됨.)

## 2. 전체 처리 흐름

```
data/raw/bigkinds/*.xlsx
    ↓ load_raw()      — 여러 파일 로드 + 합치기 + 중복 제거
    ↓ preprocess()     — 날짜 파싱, 월/분기 계산, 제목+본문 합쳐서 "문서" 컬럼 생성
    ↓ tokenize()       — Okt로 명사만 추출 + 불용어 제거
    ↓ CountVectorizer  — 문서×단어 등장횟수 행렬로 변환 (특성집합 확정)
    ↓ LatentDirichletAllocation — LDA 토픽모델링
    ↓ main()           — 월별 집계, 라벨 매핑, CSV 3종 저장
data/processed/news_topic_shares.csv, news_topic_keywords.csv, news_articles_sample.csv
```

## 3. 특성집합(어휘) 규모

**11,912개 단어**가 최종 특성집합입니다.

계산 방법: `sklearn.feature_extraction.text.CountVectorizer(min_df=2, max_df=0.6)`을
16,255개 문서(Okt로 명사만 추출하고 불용어를 제거한 뒤)에 적용했습니다.

- 필터링 전 원시 어휘(중복 없이 모은 전체 명사 집합)는 19,470개
- `min_df=2` — 2개 미만 문서에 등장한 단어 제외 → 11,922개로 축소(즉, 1개 문서에서만 등장한
  단어가 전체의 39%를 차지했다는 뜻)
- `max_df=0.6` — 문서의 60% 넘게 등장하는 단어 제외. 다만 실측 결과 이 코퍼스에서 가장 흔한
  단어("경제")조차 44.7% 문서에만 등장해서, 0.6이라는 기준은 사실상 효과가 없었음(그래서
  "경제"는 max_df가 아니라 수동으로 불용어에 추가함 — 4번 항목 참고)
- 불용어 수동 추가분(아시아·경제·지난·대한·대해·오전·오후·이상·종합·기준 10개)까지 반영해
  최종 **11,912개**

이 11,912개 단어 각각이 LDA 입력 행렬의 한 "특성(feature)"이 되고, LDA는 이 안에서 토픽을 찾습니다.

## 4. 불용어 목록과 선정 이유

| 구분 | 단어 | 이유 |
|---|---|---|
| 기사 상투어 | 기자, 사진, 연합뉴스, 뉴스, 무단전재, 재배포, 금지, 제공, 이날, 오늘, 지난해, 올해, 최근, 기사, 이번, 관련, 가운데, 위해, 통해 | 내용과 무관하게 거의 모든 기사에 등장 |
| 검색어 파편 | 소상, 공인, 자영, 업자, 상공 | Okt가 "소상공인"→"소상"+"공인", "자영업자"→"자영"+"업자"로 잘못 분절. 검색어 자체라 거의 모든 문서에 등장해 토픽 구분에 무용 |
| 매체 편향 잔재 | 아시아 | "아시아경제"가 본문에 자기 매체명을 자주 언급(31.9%의 문서에 등장) — 단일 매체 사용의 부작용 |
| 과다빈출 수식어 | 경제 | 문서빈도 1위(44.7%)인데 특정 토픽을 대표하지 못하고 여러 토픽에 걸쳐 반복 등장 |
| 문법적 기능어 | 지난, 대한, 대해, 오전, 오후, 이상, 종합, 기준 | 내용과 무관하게 자주 등장하는 문법적 표현 |

## 5. LDA 토픽모델링 설정

- 모델: `sklearn.decomposition.LatentDirichletAllocation`
- 토픽 개수: **8개** (`n_components=8`)
- `random_state=42`(재현성 고정), `max_iter=20`
- 토픽 개수는 4~16개까지 직접 실험해서 결정했습니다: 8~12개까지는 토픽이 뚜렷하게 구분됐고, 16개부터는
  같은 내용의 토픽이 중복으로 쪼개지기 시작했습니다. 최종적으로 8개로 정리했습니다.
- LDA는 "정치", "코로나" 같은 의미를 모릅니다 — 어떤 단어들이 같은 문서에 자주 같이 등장하는지
  통계적으로 찾아낼 뿐입니다. 토픽 개수(사람이 지정)와 토픽 이름(사람이 라벨링, 7번 항목)은
  전부 사람이 정한 것이고, "어떤 단어가 어떤 토픽에 속하는가"만 알고리즘이 계산합니다.

## 6. 대표 기사 선정 기준

LDA가 계산한 문서×토픽 확률(`doc_topic` 행렬)에서, 토픽별로 확률값이 가장 높은 문서를
월별로 상위 5개씩 뽑았습니다. 사람이 고른 게 아니라 LDA 확률 순위 그대로입니다.
(`data/processed/news_articles_sample.csv`, 총 2,440건)

## 7. 최종 토픽 8개 설명

각 토픽은 상위 키워드 10개와, 그 토픽에 가장 강하게 걸린 대표 기사(LDA 확률 상위)로 검증했습니다.

### 토픽0 — 정치권 재난·위기 재정대응
키워드: 피해, 국민, 민주당, 정부, 후보, 국회, 대통령, 의원, 원금, 이재명
대표 기사: 이재명 손실보상 100조 주장, 산불 피해 국가 책임론, 전국민 재난지원금 논쟁 등.
재난·위기 상황에서 정치권이 재정 대응을 놓고 벌이는 논쟁 성격.

### 토픽1 — 은행·금융권 소상공인 지원
키워드: 금융, 지원, 은행, 대출, 보증, 신용, 자금, 중소기업, 금리, 협약
대표 기사: 카카오뱅크·신협·토스뱅크·케이뱅크의 소상공인 대상 보증대출/담보대출 상품 출시.
8개 중 가장 일관된 토픽.

### 토픽2 — 코로나 방역·지자체 행정
키워드: 광주, 민생, 코로나, 예산, 정부, 회복, 정책, 규제, 추진, 시민
대표 기사: 거리두기·방역패스 정책과, 신임 시장·구청장 시정 비전 발표가 섞여 있음
("지자체 단위 대응"이라는 공통점으로 묶인 것으로 추정).

### 토픽3 — 최저임금·노사 협상
키워드: 서울, 청장, 현장, 간담, 연합, 회장, 최저임금, 위원회, 방문, 개최
대표 기사: 최저임금 인상폭 노사 갈등이 중심이나, 구청장 주민간담회 기사도 일부 섞임
("간담"이라는 단어가 양쪽에 다 쓰여서 혼입된 것으로 추정).

### 토픽4 — 지역화폐·소비쿠폰
키워드: 지역, 지원, 사업, 상품권, 상권, 소비, 활성화, 시장, 사랑, 골목
대표 기사: 지역사랑상품권, 골목상권 할인, 상생체크카드 캐시백 등 지자체발 소비 진작책.
라벨과 가장 잘 맞는 토픽 중 하나.

### 토픽5 — 물가·민생 거시대책
키워드: 정부, 물가, 대책, 안정, 회의, 지원, 대응, 보험, 장관, 점검
대표 기사: 식용유 할당관세, 물가안정 대책, 추석 성수품 공급 확대 등 정부의 물가·민생 관리 정책.

### 토픽6 — 온라인 플랫폼·디지털 지원
키워드: 서비스, 플랫폼, 카카오, 온라인, 시장, 매출, 운영, 판매, 결제, 상품
대표 기사: 토스플레이스 결제단말기, 제로페이 QR결제, 테이블오더 등 소상공인 대상 디지털
결제·주문 서비스. 대표 기사 중 하나(다이소 기부)는 주제와 다소 어긋남.

### 토픽7 — 상생협력·중소기업 지원
키워드: 지원, 사업, 중소, 중소기업, 벤처기업, 기업, 지역, 개최, 시장, 진흥
대표 기사: 기업 R&D·지식재산권 지원, 대학-창업 협력, 전통시장 판로 확대 등 중소기업·소상공인
대상 각종 지원사업 모음.

## 8. 한계

- **단일 매체(아시아경제) 편향** — 이 매체가 자주 다루는 주제(지자체 보도자료성 기사 등)가
  과대표될 수 있음
- **토픽 라벨은 사람이 붙인 것** — 키워드·대표 기사를 보고 판단한 것이라 주관 개입, 정량적
  검증(사람 라벨링과의 일치도 측정 등)은 하지 않음
- **토픽2·3처럼 서로 다른 두 성격이 섞인 토픽 존재** — LDA가 통계적으로 묶은 것일 뿐, 완벽하게
  단일 주제로 분리되진 않음

## 9. 실행 방법

```
python3 scripts/build_news_topics.py --n-topics 8
```

`data/raw/bigkinds/`에 BigKinds 엑셀 파일을 넣고 실행하면 `data/processed/`에 CSV 3개가
생성됩니다. 코드 전체는 부록 참고.

---

# 부록 — 전체 코드 (scripts/build_news_topics.py)

```python
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
    python3 scripts/build_news_topics.py [--n-topics 8]

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
```
