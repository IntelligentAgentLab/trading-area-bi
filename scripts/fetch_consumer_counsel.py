"""1372 소비자상담 상담상세현황 API에서 원본 데이터를 내려받아 data/raw/에 저장한다.

사용법:
    python scripts/fetch_consumer_counsel.py                # 전체 기간 수집
    python scripts/fetch_consumer_counsel.py --test          # rcptYm 1개월만 테스트 조회 후 종료
    python scripts/fetch_consumer_counsel.py --minutes 20    # 시간 예산 내에서 월 단위로 수집,
                                                              # 예산 초과 시 진행 중이던 월까지만 완결하고 중단

요청변수(공식 문서 기준): serviceKey, pageNo, numOfRows, resultType(xml/json),
rcptYm(등록년월 YYYYMM), caseNo(사건번호, 특정 건 조회용 - 대량수집 시 미사용)
"""
import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

SERVICE_KEY = os.environ["DATA_GO_KR_SERVICE_KEY"]
BASE_URL = "https://apis.data.go.kr/1130000/CcnDscsnDetailSttus_2Service"
OPERATION = "getDscsnDetailSttus_2"

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "consumer_counsel"
NUM_OF_ROWS = 5000  # 실측: 10000까지도 2초대에 응답 - 100이었을 때보다 요청 수를 확 줄임

# 일일 트래픽 한도(10,000)를 넘기지 않기 위한 안전 버퍼 - 이 한도에 닿으면 크래시 대신 깔끔히 중단
MAX_REQUESTS_PER_RUN = 9500
_request_count = 0


def _prev_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[4:])
    m -= 1
    if m == 0:
        m, y = 12, y - 1
    return f"{y:04d}{m:02d}"


START_YM = "202201"
# 이번 달은 아직 집계가 안 끝났을 수 있어 제외 - 전달까지만. (0건으로 저장되면 나중에 진짜 데이터가
# 나와도 "이미 존재"로 건너뛰게 되므로, 최신월은 아예 안 건드리는 게 안전함)
END_YM = _prev_month(datetime.date.today().strftime("%Y%m"))


def month_range(start_ym: str, end_ym: str):
    y, m = int(start_ym[:4]), int(start_ym[4:])
    ey, em = int(end_ym[:4]), int(end_ym[4:])
    while (y, m) <= (ey, em):
        yield f"{y:04d}{m:02d}"
        m += 1
        if m > 12:
            m = 1
            y += 1


class ApiHalt(Exception):
    """할당량 소진 등 API 응답 이상 - 전체 수집을 깔끔히 중단시키기 위한 신호."""


def fetch_page(rcpt_ym: str, page_no: int, num_of_rows: int = NUM_OF_ROWS) -> dict:
    global _request_count
    if _request_count >= MAX_REQUESTS_PER_RUN:
        raise ApiHalt(f"이번 실행 요청 한도({MAX_REQUESTS_PER_RUN}회)에 도달")
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "resultType": "json",
        "rcptYm": rcpt_ym,
    }
    resp = requests.get(f"{BASE_URL}/{OPERATION}", params=params, timeout=60)
    _request_count += 1
    resp.raise_for_status()
    return resp.json()


def fetch_month(rcpt_ym: str) -> list[dict]:
    """해당 월(rcptYm)의 전체 페이지를 순회해 item 리스트를 모아 반환."""
    all_items: list[dict] = []
    page_no = 1
    while True:
        data = fetch_page(rcpt_ym, page_no)
        if data.get("resultCode") != "00":
            raise ApiHalt(f"API 오류 [{rcpt_ym} p{page_no}]: {data.get('resultCode')} {data.get('resultMsg')}")
        items = data.get("items") or []
        # 결과 1건일 때 items가 dict로 오는 경우가 있어 방어적으로 처리
        if isinstance(items, dict):
            items = [items]
        if not items:
            break
        all_items.extend(items)
        total_count = int(data.get("totalCount", 0))
        if page_no * NUM_OF_ROWS >= total_count:
            break
        page_no += 1
        time.sleep(0.2)  # 과호출 방지
    return all_items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="1개월 1페이지만 호출해 응답 구조 확인")
    parser.add_argument("--minutes", type=float, default=None, help="시간 예산(분). 예산 초과 시 다음 월은 시작하지 않고 중단")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if args.test:
        data = fetch_page(rcpt_ym="202206", page_no=1, num_of_rows=10)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    deadline = time.time() + args.minutes * 60 if args.minutes else None

    for rcpt_ym in month_range(START_YM, END_YM):
        out_path = RAW_DIR / f"{rcpt_ym}.json"
        if out_path.exists():
            print(f"skip {rcpt_ym} (이미 존재)")
            continue
        if deadline and time.time() >= deadline:
            print(f"시간 예산 소진 - {rcpt_ym}부터는 수집하지 않고 종료")
            break
        try:
            items = fetch_month(rcpt_ym)
        except ApiHalt as e:
            print(f"중단: {e} — {rcpt_ym}부터는 못 받음. 완료된 월은 그대로 저장돼 있으니, "
                  f"내일(할당량 리셋 후) 다시 실행하면 이어서 받습니다.")
            break
        out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{rcpt_ym}: {len(items)}건 저장 -> {out_path} (누적 요청 {_request_count}회)")


if __name__ == "__main__":
    sys.exit(main())
