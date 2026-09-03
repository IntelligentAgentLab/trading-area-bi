# 소비상권 BI 프로젝트

구조화 데이터(매출)와 비구조화 데이터(뉴스)를 함께 봐서 "현상 → 원인 → 효과"를 설명하는
소상공인 상권 분석 대시보드입니다. Streamlit 멀티페이지 앱으로 구현합니다.

## 팀 구성

| 역할 | 담당 | 작업 페이지 |
|---|---|---|
| A. 매출 대시보드 | 최재원, 남지우 | `streamlit_demo/pages/1_대시보드.py` |
| C. 텍스트마이닝(토픽모델링·소비자상담) | (완료) | `streamlit_demo/pages/2_토픽모델링.py`, `3_소비자상담.py` |
| D. 인과추론 | 조소민 | `streamlit_demo/pages/4_인과추론.py` |

## 아키텍처 노트 — 페이지 간 독립성

- `2_토픽모델링.py`, `3_소비자상담.py`는 업종 선택과 무관하게 독자적으로 동작합니다.

- `5_통합요약.py`는 네 페이지 결과를 한 화면에 모으는 페이지라 A·C·D 결과물을 전부 참조합니다 —
  각자 작업이 어느 정도 끝난 뒤 마지막에 같이 손보면 됩니다.

## 폴더 구조

```
streamlit_demo/          팀 공식 데모 (멀티페이지 Streamlit 앱)
  ├─ app.py                진입점
  ├─ common.py              토픽모델링용 실데이터 로더
  └─ pages/
      ├─ 1_대시보드.py        A 담당 (준비 중)
      ├─ 2_토픽모델링.py       C 담당 (완료, 실데이터 연동됨)
      ├─ 3_소비자상담.py       C 담당 (완료, 실데이터 연동됨)
      ├─ 4_인과추론.py        D 담당 (준비 중)
      └─ 5_통합요약.py        통합 요약 (마지막에 다같이)

scripts/                  데이터 수집·가공 스크립트
  ├─ fetch_consumer_counsel.py            1372 API 수집 (원본 JSON)
  ├─ build_consumer_counsel_summary.py    원본 → 집계 CSV(월별/지역별, git 포함)
  └─ build_news_topics.py                 BigKinds 뉴스 → LDA 토픽모델링

data/
  ├─ raw/                 원본 데이터 (git 미포함 — 각자 준비 필요, 아래 참고)
  └─ processed/            가공된 결과 CSV (git 포함 — 바로 대시보드 실행 가능)
```

로컬에는 `docs/`에 방법론 문서(토픽모델링 파이프라인 설명 등)가 있지만 레포에는 올리지 않습니다 — 필요하면 따로 공유해드릴게요.

## 실행 방법

```bash
# 1. 의존성 설치
pip install -r streamlit_demo/requirements.txt

# 2. (1372 API 쓸 사람만) .env 파일 생성 — .env.example 참고
cp .env.example .env   # 발급받은 서비스키로 채우기

# 3. 팀 공식 데모 실행
cd streamlit_demo
streamlit run app.py
```

`data/processed/`의 CSV는 git에 포함돼 있어서, 토픽모델링·소비자상담 페이지는 **별도 데이터
다운로드 없이 클론만 받아도 바로 실행됩니다.** 원본(1372 JSON 1.8GB, BigKinds 엑셀)은 용량이
크고 개인 API 키/수동 다운로드가 필요해 git에서 제외했고, 대신 대시보드가 쓰는 만큼만 미리
집계해둔 작은 CSV(`consumer_counsel_monthly.csv`, `consumer_counsel_region.csv` 등)를 커밋해뒀습니다.

원본부터 다시 만들고 싶다면(예: 기간을 늘리거나 재집계):

- 1372 데이터: `scripts/fetch_consumer_counsel.py`로 원본 수집(data.go.kr 서비스키 필요) →
  `scripts/build_consumer_counsel_summary.py`로 집계 CSV 재생성
- BigKinds 뉴스: `data/raw/bigkinds/README.md` 참고해 수동 다운로드 → `scripts/build_news_topics.py`

## 환경 참고사항.

- 형태소 분석기 `konlpy.tag.Okt`는 **Java(JDK) 설치가 필요**합니다. `build_news_topics.py`를
  직접 돌릴 사람만 해당(이미 만들어진 `data/processed/*.csv`를 쓰는 대시보드 실행에는 불필요).
