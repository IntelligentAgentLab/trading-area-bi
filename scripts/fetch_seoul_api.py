"""서울 열린데이터광장 Open API에서 상권분석서비스(자치구) 데이터를 받아 data/raw/에 CSV로 저장한다.

사용법:
    python scripts/fetch_seoul_api.py --check    # 저장 없이 서비스명·필드명만 확인 (5건씩만 조회)
    python scripts/fetch_seoul_api.py            # 전체 수집 후 CSV 교체

받을 데이터셋 목록과 "API 필드명 → CSV 열 이름" 매핑은 scripts/seoul_api.json에 있다.
인증키는 .env 또는 환경변수의 SEOUL_API_KEY (data.go.kr 키와 별개 — data.seoul.go.kr에서 발급).

요청 형식: http://openapi.seoul.go.kr:8088/{인증키}/json/{서비스명}/{시작행}/{끝행}/
"""
import csv
import datetime
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://openapi.seoul.go.kr:8088"
PAGE_SIZE = 1000  # 서울 API는 한 번에 1000건까지만 허용 - 넘기면 ERROR-336

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "seoul_trading_area"
CONFIG_PATH = Path(__file__).resolve().parent / "seoul_api.json"
INDEX_PATH = RAW_DIR / "_meta" / "api_index.json"
KST = datetime.timezone(datetime.timedelta(hours=9))

# 이 API에는 분기로 걸러 받는 요청인자가 없어서 매번 전 기간을 통째로 받아 파일을 교체한다.
# 그래서 응답이 중간에 잘리면 과거 분기가 조용히 사라질 수 있음 - 직전 수집보다 건수가 이 비율
# 밑으로 줄면 덮어쓰지 않고 실패 처리한다(데이터는 분기마다 늘기만 하는 게 정상).
MIN_KEEP_RATIO = 0.9


def get_json(url):
    """인증키가 URL 경로에 들어가므로, 실패해도 URL이나 예외 메시지 원문은 로그에 찍지 않는다."""
    last_error = None
    for attempt in range(3):
        try:
            res = requests.get(url, timeout=60)
            if res.status_code == 200:
                return res.json()
            last_error = f"HTTP {res.status_code}"
        except ValueError:
            last_error = "JSON이 아닌 응답"
        except requests.RequestException as exc:
            last_error = type(exc).__name__
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"요청 실패 ({last_error})")


def fetch_rows(service, key, limit=None):
    """(행 목록, 전체 건수). limit을 주면 그만큼만 받고 끝낸다(--check용)."""
    rows, start = [], 1
    while True:
        end = start + (limit or PAGE_SIZE) - 1
        data = get_json(f"{BASE_URL}/{key}/json/{service}/{start}/{end}/")
        body = data.get(service)
        if body is None:  # 오류일 때는 서비스명 없이 최상위에 RESULT만 온다
            result = data.get("RESULT", {})
            raise RuntimeError(f"API 오류 {result.get('CODE')}: {result.get('MESSAGE')}")
        code = body.get("RESULT", {}).get("CODE", "INFO-000")
        if code != "INFO-000":
            raise RuntimeError(f"API 오류 {code}: {body['RESULT'].get('MESSAGE')}")
        page = body.get("row") or []
        total = int(body.get("list_total_count") or 0)
        rows.extend(page)
        if limit or not page or len(rows) >= total:
            return rows, total
        start = end + 1
        time.sleep(0.2)


def write_csv(path, rows, columns):
    """columns(API 필드명 → CSV 열 이름)에 적힌 열만, 그 순서로 저장한다.

    형식은 포털에서 직접 내려받은 CSV와 맞춘다(cp949, 모든 값 따옴표) - 1_대시보드.py의 로더가
    cp949를 먼저 시도하고, 팀원이 수동으로 받은 파일과 섞여도 diff가 덜 지저분하다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="cp949", errors="replace") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(columns.values())
        for row in rows:
            line = []
            for field in columns:
                v = row.get(field, "")
                if isinstance(v, float) and v.is_integer():
                    v = int(v)  # JSON 숫자가 12345.0으로 찍히지 않게
                line.append("" if v is None else v)
            writer.writerow(line)
    tmp.replace(path)  # 다 쓴 뒤에 바꿔치기 - 쓰다 죽어도 기존 파일이 반쯤 깨진 채 남지 않게


def check(datasets, key):
    for ds in datasets:
        print(f"\n== {ds['name']} ({ds['service']}) ==")
        try:
            rows, total = fetch_rows(ds["service"], key, limit=5)
            fields = list(rows[0].keys()) if rows else []
            missing = [f for f in ds["columns"] if f not in fields]
            extra = [f for f in fields if f not in ds["columns"]]
            print(f"  전체 {total}건, 필드 {len(fields)}개")
            print(f"  매핑에는 있는데 API에 없는 필드: {missing or '없음'}")
            print(f"  API에는 있는데 매핑에 없는 필드: {extra or '없음'}")
        except Exception as exc:
            print(f"  [실패] {exc}")


def main():
    key = os.environ.get("SEOUL_API_KEY", "").strip()
    if not key:
        sys.exit("SEOUL_API_KEY가 없습니다. .env에 넣거나 환경변수로 지정하세요.")
    datasets = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    if "--check" in sys.argv:
        check(datasets, key)
        return

    now = datetime.datetime.now(KST).isoformat(timespec="seconds")
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
    failed = []
    for ds in datasets:
        name = ds["name"]
        try:
            rows, _ = fetch_rows(ds["service"], key)
            absent = [f for f in ds["columns"] if rows and f not in rows[0]]
            if absent:
                raise RuntimeError(f"API 응답에 없는 필드: {absent} (명세가 바뀌었을 수 있음)")
            before = index.get(name, {}).get("count", 0)
            if len(rows) < before * MIN_KEEP_RATIO:
                raise RuntimeError(f"건수가 {before} → {len(rows)}로 줄어 덮어쓰지 않았습니다")
            write_csv(RAW_DIR / ds["filename"], rows, ds["columns"])
            quarters = sorted({str(r.get("STDR_YYQU_CD")) for r in rows})
            index[name] = {"file": ds["filename"], "count": len(rows), "updated_at": now,
                           "first_quarter": quarters[0], "last_quarter": quarters[-1], "status": "ok"}
            print(f"[성공] {name}: {len(rows)}건 ({quarters[0]}~{quarters[-1]})")
        except Exception as exc:  # 하나가 실패해도 나머지는 계속 - 실패한 것은 기존 파일 유지
            failed.append(name)
            index.setdefault(name, {}).update(status="failed", last_error=str(exc)[:200], last_error_at=now)
            print(f"[실패] {name}: {exc}")

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if failed:
        sys.exit(f"실패한 데이터셋: {', '.join(failed)}")


if __name__ == "__main__":
    main()
