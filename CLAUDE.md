# CLAUDE.md

이 파일은 이 저장소에서 작업하는 Claude Code(claude.ai/code)에게 주는 가이드입니다.

## 프로젝트 개요

소비상권 BI 프로젝트 — 구조화 데이터(매출)와 비구조화 데이터(뉴스, 소비자상담)를 함께 봐서
소상공인 상권의 "현상 → 원인 → 효과"를 설명하는 Streamlit 멀티페이지 앱입니다. 4인 팀 프로젝트이며,
현재 역할 분담과 페이지별 담당자는 `README.md` 참고.

## 자주 쓰는 명령어

```bash
# 의존성 설치 (requirements.txt는 streamlit_demo/ 안에 하나만 있음)
pip install -r streamlit_demo/requirements.txt

# 앱 실행 (반드시 streamlit_demo/로 cd 먼저 — 페이지 import·경로 계산이 이 cwd를 전제로 함)
cd streamlit_demo && streamlit run app.py

# 뉴스 토픽모델링 재생성 (data/raw/bigkinds/*.xlsx가 바뀌었을 때만)
python3 scripts/build_news_topics.py --n-topics 8

# 1372 소비자상담 데이터 수집 (.env에 DATA_GO_KR_SERVICE_KEY 필요)
python3 scripts/fetch_consumer_counsel.py --test   # 1페이지만 빠르게 확인
python3 scripts/fetch_consumer_counsel.py --minutes 20
```

pytest 같은 테스트 스위트는 없습니다. 페이지를 수정한 뒤 검증하는 관행은
`streamlit.testing.v1.AppTest`를 `streamlit_demo/`에서 `python3 -c "..."`로 인라인 실행하는 것입니다:

```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("pages/2_토픽모델링.py")
at.run(timeout=60)
assert not at.exception
```

`common.py`나 여러 페이지가 공유하는 패턴을 건드렸다면, `["app.py"] + glob.glob("pages/*.py")`
전체를 이런 식으로 돌려서 회귀 테스트하는 게 기본입니다. `streamlit_demo/` 변경 작업은 이 확인을
거쳐야 끝난 걸로 봅니다.

## 아키텍처

**멀티페이지 앱, 사이드바 순서대로 파일명 번호가 매겨짐**(`streamlit_demo/pages/N_이름.py`):
`1_대시보드` → `2_토픽모델링` → `3_소비자상담` → `4_인과추론` → `5_통합요약`. 페이지를 중간에
끼워 넣을 땐 git mv로 신중하게 재번호를 매겨야 함 — Streamlit이 파일명 접두 숫자로 사이드바
순서를 정하기 때문.

**의도적인 독립 구조**: `2_토픽모델링.py`와 `3_소비자상담.py`는 `1_대시보드.py`/`4_인과추론.py`와
업종 같은 공통 데이터 축으로 연결돼 있지 **않습니다**. 원래는 "업종" 축으로 전 페이지를 join하려던
계획에서 의도적으로 방향을 튼 것이라, 이유는 README의 "아키텍처 노트" 참고. 그 판단을 다시
확인하지 않은 채로 페이지 간 결합(예: 공통 사이드바 필터)을 되살리지 마세요 — 지금은 페이지를
잇는 공통 필터·session_state 키가 없는 상태입니다.

**"실데이터 있으면 쓰고 없으면 더미로 폴백" 로더 패턴** (`streamlit_demo/common.py`): 페이지가
필요로 하는 데이터는 전부 `load_X()` 함수를 거칩니다 — `data/processed/` 아래 가공된 CSV가
있는지 확인해서, 있으면 그걸 쓰고 없으면 `generate_X()` 더미 생성기(같은 스키마의 가짜 값)로
폴백하며, `(데이터프레임, 실데이터여부: bool)` 튜플을 반환합니다. 페이지는 이 bool로 "(더미 데이터)"
표시를 켜고 끕니다. 이 패턴 덕분에 한 사람의 페이지가 다른 사람의 데이터 파이프라인이 없어도
동작합니다 — `1_대시보드.py`/`4_인과추론.py`도 나중에 실제 데이터 파이프라인을 만들 때 이 패턴을
따라야 합니다(`load_topics()`가 참고할 구현 예시). 가공된 CSV가 없다고 페이지가 그냥 죽게
만들지 마세요.

**데이터 흐름**: `scripts/*.py`(데이터 수집·가공, Streamlit 프로세스와 별개로 수동 실행) →
`data/processed/*.csv`(git에 커밋됨, 용량 작음) → `common.py` 로더 → 페이지. `data/raw/`(용량
크고 개인 API 키나 수동 다운로드가 필요한 원본 데이터)는 `data/raw/bigkinds/README.md`만 빼고
git에서 제외돼 있고, `data/processed/`는 커밋돼 있어서 아무도 파이프라인 스크립트를 다시 안
돌려도 앱이 바로 돌아갑니다.

- `scripts/build_news_topics.py`: BigKinds 뉴스 엑셀 → Okt 형태소분석 → CountVectorizer →
  `sklearn.decomposition.LatentDirichletAllocation` → `data/processed/news_topic_shares.csv`
  (월 단위로 저장 — 분기 집계는 미리 계산해두지 않고 `common.py`에서 문서수 가중평균으로 즉석
  처리함, `_aggregate_topics()` 참고), `news_topic_keywords.csv`, `news_articles_sample.csv`
  (토픽별 대표 기사, "시기 살펴보기" UI용). 토픽 라벨(`토픽_라벨` 딕셔너리)은 `news_topic_keywords.csv`를
  사람이 보고 수동으로 붙인 것이라 자동 재생성되지 않습니다 — 코퍼스나 `--n-topics`를 바꾸면
  다시 확인해야 함.
- `scripts/fetch_consumer_counsel.py`: 1372 data.go.kr API를 월 단위로 페이지네이션해서
  `data/raw/consumer_counsel/*.json`에 저장(월별 파일 1개, 이미 받은 월은 건너뜀).

**한글 식별자**: 변수·함수명이 한글(도메인 용어: `업종`, `분기`, `기간`, `토픽`)과 영어(라이브러리
호출, 범용 헬퍼)를 섞어 씁니다. 전부 영어나 전부 한글로 통일하려 하지 말고 기존 파일의 관례를
따르세요.

이 코드베이스의 주석은 코드가 뭘 하는지 재서술하기보다, **왜 그렇게 판단했는지**를 설명하는
경우가 많습니다(예: 왜 중복 제거 기준을 바꿨는지, 왜 어떤 필터 기준값이 알고 보니 아무 효과가
없었는지). 편집할 때 이 밀도를 유지하고 걷어내지 마세요.
