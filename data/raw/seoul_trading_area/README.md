# 서울 상권·상품권 원본 데이터

`streamlit_demo/pages/1_대시보드.py`가 이 폴더를 통째로 읽는다(하위 폴더 포함). 출처는 전부
[서울 열린데이터광장](https://data.seoul.go.kr)이고, `.github/workflows/update-seoul-data.yml`이
매월 2일 새벽에 자동으로 갱신한다.

```
seoul_trading_area/
├─ trading_area/     상권분석서비스 5종 (자치구 × 분기)        ← Open API, 매번 전체 교체
├─ gift_payment/     상품권 결제내역 (월별 xlsx, 연도 폴더)     ← 첨부 파일 감시, 새 달이 추가됨
│   └─ 2023/ 2024/ 2025/ …
├─ gift_issue/       상품권 발행·판매 현황 (파일 1개)           ← 첨부 파일 감시, 최신본으로 교체
├─ gift_merchant/    상품권 가맹점 (파일 1개)                  ← 첨부 파일 감시, 최신본으로 교체
└─ _meta/            자동 갱신 기록 (사람이 고칠 일 없음)
```

| 폴더 | 데이터셋 | 포털 페이지 | 원본 갱신 주기 | 수집 스크립트 |
|---|---|---|---|---|
| `trading_area/` | 추정매출-자치구 | [OA-22176](https://data.seoul.go.kr/dataList/OA-22176/S/1/datasetView.do) | 분기 | `scripts/fetch_seoul_api.py` |
| | 점포-자치구 | [OA-22173](https://data.seoul.go.kr/dataList/OA-22173/S/1/datasetView.do) | 분기 | 〃 |
| | 직장인구-자치구 | [OA-22185](https://data.seoul.go.kr/dataList/OA-22185/S/1/datasetView.do) | 분기 | 〃 |
| | 길단위인구-자치구 | [OA-22179](https://data.seoul.go.kr/dataList/OA-22179/S/1/datasetView.do) | 분기 | 〃 |
| | 상권변화지표-자치구 | [OA-15567](https://data.seoul.go.kr/dataList/OA-15567/S/1/datasetView.do) | 분기 | 〃 |
| `gift_payment/` | 자치구별 업종별 결제내역 | [OA-22395](https://data.seoul.go.kr/dataList/OA-22395/F/1/datasetView.do) | 수시 | `scripts/watch_seoul_files.py` |
| `gift_issue/` | 월별 발행 및 판매 현황 | 〃 | 수시 | 〃 |
| `gift_merchant/` | 가맹점 현황 | [OA-21099](https://data.seoul.go.kr/dataList/OA-21099/F/1/datasetView.do) | 반기 | 〃 |

## 파일명을 바꾸면 안 되는 이유

대시보드 로더가 파일명에 든 글자로 데이터 종류를 가려낸다. 폴더는 옮겨도 되지만 아래 글자는
파일명에 남아 있어야 한다.

- 상권분석: `추정매출-자치구`, `점포-자치구`, `직장인구-자치구`, `길단위인구-자치구`, `상권변화지표-자치구` (`.csv`)
- 결제내역: `결제내역` (`.xlsx`). 그리고 파일명 맨 앞의 `NN년NN월`에서 연·월을 읽는다.
- 발행·판매: `발행 및 판매 현황` (`.xlsx`)
- 가맹점: `유효 가맹점` (`.csv`만 읽을 수 있음)

## 자동 갱신이 안 될 때

- 워크플로가 실패하거나 새 파일이 올라오면 GitHub Issue가 만들어진다.
- Issue에 "자동 다운로드 실패"라고 적혀 있으면, 포털에서 직접 받아 위 규칙대로 해당 폴더에 올리면 된다.
- 로컬 점검: `python scripts/fetch_seoul_api.py --check`, `python scripts/watch_seoul_files.py --list`
