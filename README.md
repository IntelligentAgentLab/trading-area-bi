# 소비상권 BI 프로젝트

구조화 데이터(매출)와 비구조화 데이터(뉴스)를 함께 봐서 "현상 → 원인 → 효과"를 설명하는
소상공인 상권 분석 대시보드입니다. Streamlit 멀티페이지 앱으로 구현합니다.

## 팀 구성

| 역할 | 담당 | 작업 페이지 |
|---|---|---|
| A. 매출 대시보드 | 최재원, 남지우 | `streamlit_demo/pages/1_대시보드.py` |
| C. 텍스트마이닝(토픽모델링) | (완료) | `streamlit_demo/pages/2_토픽모델링.py`, `exploration/consumer_counsel_app.py` |
| D. 인과추론 | 조소민 | `streamlit_demo/pages/3_인과추론.py` |

## 아키텍처 노트 — 페이지 간 독립성

**토픽모델링(②)과 1372 소비자상담 탐색 페이지는 대시보드(①)·인과추론(③)과 데이터 속성으로
연결돼 있지 않습니다.** 원래 계획에서는 "업종"을 공통 축으로 네 페이지를 다 엮으려 했는데,
"매출 급변 시기의 원인 뉴스"가 꼭 그 업종명을 포함할 필요는 없다는 점 때문에 방향을
바꿨습니다. 그래서:

- `2_토픽모델링.py`는 업종 선택과 무관하게 독자적으로 동작합니다(사이드바 업종 필터를 무시함).
- `exploration/consumer_counsel_app.py`는 아예 별도의 독립 앱입니다(팀 공식 데모와 다른 실행 파일).
- 각자 담당 페이지(①③)는 서로 업종·분기 축으로 연결되어 있으니, `streamlit_demo/common.py`의
  `업종목록`·`분기목록`이나 `render_filters()`를 건드릴 때는 서로 확인하고 진행해주세요.
- `4_통합요약.py`는 네 페이지 결과를 한 화면에 모으는 페이지라 A·C·D 결과물을 전부 참조합니다 —
  각자 작업이 어느 정도 끝난 뒤 마지막에 같이 손보면 됩니다.

## 폴더 구조

```
streamlit_demo/          팀 공식 데모 (멀티페이지 Streamlit 앱)
  ├─ app.py                진입점
  ├─ common.py              공통 필터·더미데이터·실데이터 로더
  └─ pages/
      ├─ 1_대시보드.py        A 담당 (현재 더미 데이터)
      ├─ 2_토픽모델링.py       C 담당 (완료, 실데이터 연동됨)
      ├─ 3_인과추론.py        D 담당 (현재 더미 데이터)
      └─ 4_통합요약.py        통합 요약 (마지막에 다같이)

exploration/              탐색용 독립 앱
  └─ consumer_counsel_app.py   1372 소비자상담 데이터 탐색 (실데이터)

scripts/                  데이터 수집·가공 스크립트
  ├─ fetch_consumer_counsel.py   1372 API 수집
  └─ build_news_topics.py        BigKinds 뉴스 → LDA 토픽모델링

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

# 4. 1372 소비자상담 탐색 앱(독립) 실행 — 원본 데이터 있을 때만
streamlit run exploration/consumer_counsel_app.py
```

`data/processed/`의 CSV(뉴스 토픽 결과 등)는 git에 포함돼 있어서, 위 3번은 별도 데이터 다운로드
없이 바로 실행됩니다. `data/raw/`(1372 원본 JSON, BigKinds 원본 엑셀)는 용량이 크고 개인 API
키/수동 다운로드가 필요해 git에서 제외했습니다 — 필요하면 각자 아래를 참고해 준비하세요.

- 1372 데이터: `scripts/fetch_consumer_counsel.py` 참고 (data.go.kr 서비스키 필요)
- BigKinds 뉴스: `data/raw/bigkinds/README.md` 참고 (수동 다운로드)

## 환경 참고사항

- 형태소 분석기 `konlpy.tag.Okt`는 **Java(JDK) 설치가 필요**합니다. `build_news_topics.py`를
  직접 돌릴 사람만 해당(이미 만들어진 `data/processed/*.csv`를 쓰는 대시보드 실행에는 불필요).
