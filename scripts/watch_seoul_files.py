"""서울 열린데이터광장의 '파일로만 제공되는' 데이터셋(서울사랑상품권)을 감시한다.

Open API가 없는 데이터셋은 담당자가 엑셀을 게시글에 첨부하는 방식이라, 페이지의 첨부 파일
목록을 읽어 지난번에 없던 파일이 생겼는지 비교하는 수밖에 없다. 새 파일이 있으면 내려받아
data/raw/seoul_trading_area/ 아래 제자리에 두고, 무슨 일이 있었는지 watch_report.md에 적는다
(워크플로가 이 파일로 GitHub Issue를 만들어 알린다).

사용법:
    python scripts/watch_seoul_files.py            # 감시 실행 (Actions가 실행하는 방식)
    python scripts/watch_seoul_files.py --list     # 페이지에서 읽어낸 파일 목록만 출력
    python scripts/watch_seoul_files.py --test     # 대상별 최신 파일 1개를 _watch_test/에 시험 다운로드

감시 대상은 scripts/seoul_files.json에 있다. mode가 두 가지:
    all    - 새 파일이 올라올 때마다 추가로 받는다 (월별 결제내역)
    latest - 최신 파일 하나만 고정된 이름으로 유지하고 덮어쓴다 (가맹점, 발행·판매 현황)
"""
import datetime
import html as htmllib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "seoul_trading_area"
CONFIG_PATH = Path(__file__).resolve().parent / "seoul_files.json"
STATE_PATH = RAW_DIR / "_meta" / "file_watch_state.json"
REPORT_PATH = ROOT / "watch_report.md"
TEST_DIR = ROOT / "_watch_test"
KST = datetime.timezone(datetime.timedelta(hours=9))
MAX_BYTES = 95 * 1024 * 1024  # GitHub는 파일 하나에 100MB까지만 받는다

PAGE_URL = "https://data.seoul.go.kr/dataList/{inf_id}/F/1/datasetView.do"
# 내려받기 버튼(downloadFile(번호))이 보내는 요청을 그대로 흉내 낸다. 2026-10 실측으로 확인한
# 형식이고, 포털이 개편되면 여기가 가장 먼저 깨진다 - 그때는 --test로 확인.
DOWNLOAD_URL = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"
HEADERS = {"User-Agent": "Mozilla/5.0 (trading-area-bi data watch)"}

# 아래 검사들은 streamlit_demo/pages/1_대시보드.py의 로더가 각 파일에 기대하는 모양과 맞춘 것이다.
# 포털 파일은 사람이 만들어 올리는 엑셀이라 형식이 예고 없이 바뀔 수 있는데, 그대로 받아 넣으면
# 페이지가 조용히 빈 값이나 엉뚱한 값을 그린다 - 로더가 못 읽을 파일은 넣지 않고 알리는 쪽이 낫다.
GU25 = ["종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구", "성북구", "강북구",
        "도봉구", "노원구", "은평구", "서대문구", "마포구", "양천구", "강서구", "구로구", "금천구",
        "영등포구", "동작구", "관악구", "서초구", "강남구", "송파구", "강동구"]

EXT = r"(?:xlsx|xlsm|xls|csv|zip|hwpx|hwp|pdf|txt|json|xml)"
NAME_RE = re.compile(r"[^\n\r\t]*?\." + EXT + r"(?![A-Za-z0-9])", re.I)
CALL_RE = re.compile(r"downloadFile\(\s*['\"]?(\d+)['\"]?\s*\)")


def text_of(fragment):
    return htmllib.unescape(re.sub(r"<[^>]+>", "\n", fragment))


def list_files(page_html):
    """페이지 HTML에서 [(번호, 파일명)]을 뽑는다. 번호가 클수록 나중에 올라온 파일이다."""
    calls = list(CALL_RE.finditer(page_html))
    found = {}
    for i, m in enumerate(calls):
        seq = int(m.group(1))
        if seq in found:
            continue
        # 파일명이 버튼(a 태그) 안에 있는 경우와, 같은 줄의 앞 칸에 있는 경우를 둘 다 본다
        inner = page_html[m.end(): m.end() + 600].split("</a>")[0]
        names = NAME_RE.findall(text_of(inner))
        if not names:
            start = calls[i - 1].end() if i > 0 else max(0, m.start() - 3000)
            names = NAME_RE.findall(text_of(page_html[start: m.start()]))
        found[seq] = names[-1].strip() if names else f"file_{seq}"
    return sorted(found.items())


def fetch_page(target):
    url = target.get("page_url") or PAGE_URL.format(inf_id=target["inf_id"])
    res = requests.get(url, headers=HEADERS, timeout=60)
    res.raise_for_status()
    if not res.encoding or res.encoding.lower() == "iso-8859-1":
        res.encoding = "utf-8"
    return url, res.text


def download(target, seq, dest, referer):
    form = {"infId": target["inf_id"], "seqNo": "", "seq": str(seq), "infSeq": "1"}
    with requests.post(target.get("download_url", DOWNLOAD_URL), data=form,
                       headers={**HEADERS, "Referer": referer}, timeout=600, stream=True) as res:
        if res.status_code != 200:
            raise RuntimeError(f"HTTP {res.status_code}")
        m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)",
                      res.headers.get("Content-Disposition", ""), re.I)
        served = unquote(m.group(1)).strip() if m else ""
        dest.parent.mkdir(parents=True, exist_ok=True)
        size, head = 0, b""
        with open(dest, "wb") as f:
            for chunk in res.iter_content(1024 * 256):
                head = head or chunk[:200]
                f.write(chunk)
                size += len(chunk)
    # 요청 형식이 틀리면 200 OK로 오류 안내 페이지(HTML)가 온다 - 그걸 데이터로 저장하지 않게
    if size < 200 or b"<html" in head.lower() or b"<!doctype html" in head.lower():
        dest.unlink(missing_ok=True)
        raise RuntimeError("파일이 아닌 응답을 받았습니다 (다운로드 요청 형식이 바뀌었을 수 있음)")
    return size, served


def check_payment(path, name):
    """로더(_payment_one)는 파일명 앞의 두 숫자를 연·월로, 첫 시트 첫 열을 발행처(자치구)로 읽는다."""
    import pandas as pd

    if not re.match(r"\d{2}년\d{2}월", name):
        raise RuntimeError("파일명이 'NN년NN월'로 시작하지 않아 연·월을 읽을 수 없습니다")
    df = pd.read_excel(path, sheet_name=0, header=0)
    found = set(df.iloc[:, 0].astype(str).str.strip()) & set(GU25)
    if len(found) < len(GU25):
        raise RuntimeError(f"첫 열에서 자치구 25개 중 {len(found)}개만 찾았습니다 (표 형식이 바뀌었을 수 있음)")


def check_issue(path, name):
    """로더(load_issue)는 'NN년N월' 형태의 시트만 읽는다 - 그런 시트가 하나도 없으면 빈 데이터가 된다."""
    import pandas as pd

    sheets = pd.ExcelFile(path).sheet_names
    if not any(re.match(r"\s*\d+\s*년\s*\d+\s*월", str(n)) for n in sheets):
        raise RuntimeError(f"'NN년N월' 형태의 시트가 없습니다 (실제 시트: {sheets[:5]})")


CHECKS = {"payment": check_payment, "issue": check_issue}


def to_csv(src, out_csv, columns):
    """엑셀/CSV를 cp949 CSV로 바꾸면서 columns에 적힌 열만 남긴다.

    1_대시보드.py의 가맹점 로더(read_table)는 CSV만 읽을 수 있는데 포털은 xlsx와 csv를 번갈아
    올린다. 그리고 페이지가 실제로 쓰는 열은 자치구·업종 둘뿐이라 나머지(상호·주소 등)를 버리면
    45MB → 10MB 안팎으로 줄어든다. 열을 못 찾으면 기존 파일을 건드리지 않고 실패시킨다 - 전체
    열을 그냥 저장하면 페이지가 자치구·업종 열을 못 찾아 가맹점 분석이 통째로 빠지기 때문.
    """
    import pandas as pd

    if src.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(src, dtype=str)
    else:
        try:
            df = pd.read_csv(src, dtype=str, encoding="cp949")
        except UnicodeDecodeError:
            df = pd.read_csv(src, dtype=str, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise RuntimeError(f"열 {missing}을 찾지 못했습니다 (실제 열: {list(df.columns)[:15]})")
    df = df[columns]
    note = f"CSV로 변환, {len(df):,}행, 열 {columns}만 남김"
    tmp = out_csv.with_suffix(".tmp")
    df.to_csv(tmp, index=False, encoding="cp949", errors="replace")
    tmp.replace(out_csv)
    return note


def dest_dir_of(target, name):
    """dest의 {year}를 파일명의 'NN년'에서 뽑은 연도로 채운다 (예: 26년04월 → 2026)."""
    dest = target.get("dest", "")
    if "{year}" in dest:
        m = re.search(r"(\d{2})년", name)
        dest = dest.replace("{year}", f"20{m.group(1)}" if m else "기타")
    return RAW_DIR / dest


def final_path_of(target, name):
    d = dest_dir_of(target, name)
    if target.get("mode", "all") == "latest":
        ext = ".csv" if target.get("to_csv") else Path(name).suffix
        return d / f"{target['filename']}{ext}"
    return d / name


def store(target, seq, name, referer):
    """새 파일 하나를 내려받아 제자리에 둔다. 알림에 쓸 설명 한 줄을 돌려준다."""
    final = final_path_of(target, name)
    tmp = final.parent / f".download_{seq}{Path(name).suffix}"
    size, _ = download(target, seq, tmp, referer)
    note = ""
    try:
        if target.get("check"):
            CHECKS[target["check"]](tmp, name)
        if target.get("to_csv"):
            note = " (" + to_csv(tmp, final, target["columns"]) + ")"
        else:
            if size > MAX_BYTES:
                raise RuntimeError(f"{size / 1e6:.0f}MB로 GitHub 한도(100MB)에 걸려 저장하지 않았습니다")
            tmp.replace(final)
    finally:
        tmp.unlink(missing_ok=True)
    if target.get("mode", "all") == "latest":
        # 고정 이름인데 확장자만 다른 예전 파일이 남으면 로더가 어느 쪽을 집을지 모호해진다
        for old in final.parent.glob(f"{target['filename']}.*"):
            if old != final:
                old.unlink()
    return f"`{final.relative_to(ROOT).as_posix()}`에 저장{note}"


def watched(target, files):
    return [f for f in files if re.search(target["match"], f[1])]


def run_list(targets):
    for t in targets:
        _, page = fetch_page(t)
        files = list_files(page)
        print(f"\n== {t['name']} ({t['inf_id']}): {len(files)}개 ==")
        for seq, name in files:
            print(f"  [{seq:>3}] {'감시' if re.search(t['match'], name) else '    '}  {name}")


def run_test(targets):
    for t in targets:
        url, page = fetch_page(t)
        files = watched(t, list_files(page))
        if not files:
            print(f"[실패] {t['name']}: 감시 대상 파일을 찾지 못했습니다")
            continue
        seq, name = files[-1]
        try:
            size, _ = download(t, seq, TEST_DIR / name, url)
            print(f"[성공] {t['name']}: {name} ({size / 1024:,.0f}KB) -> _watch_test/")
        except Exception as exc:
            print(f"[실패] {t['name']}: {name}: {exc}")


def run_watch(targets):
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    report, broken = [], []
    for t in targets:
        name, latest = t["name"], t.get("mode", "all") == "latest"
        try:
            url, page = fetch_page(t)
            files = list_files(page)
            mine = watched(t, files)
            if not mine:
                raise RuntimeError("감시 대상 파일을 찾지 못했습니다 (페이지 구조나 파일명 규칙이 바뀌었을 수 있음)")
        except Exception as exc:
            broken.append(name)
            report.append(f"### {name}\n- 감시 실패: {exc}")
            print(f"[실패] {name}: {exc}")
            continue

        if name in state:
            seen = set(state[name]["seen"])
            new = [f for f in mine if f[0] not in seen]
        elif latest:
            # 첫 실행: 저장소에 있는 파일이 포털의 어느 판인지 알 수 없으니 최신판으로 한 번 맞춘다
            new = mine[-1:]
        else:
            # 첫 실행: 포털에는 있는데 저장소에 없는 것만 채운다 (이미 있는 달은 다시 받지 않음)
            new = [f for f in mine if not final_path_of(t, f[1]).exists()]
        if latest:
            new = new[-1:]  # 여러 판이 한꺼번에 올라와도 최신 하나만 필요

        state[name] = {"seen": sorted(seq for seq, _ in files)}
        if not new:
            print(f"[변화 없음] {name}")
            continue

        lines = [f"### {name}", f"페이지: {url}"]
        for seq, fname in new:
            try:
                lines.append(f"- 새 파일 **{fname}** → {store(t, seq, fname, url)}")
                print(f"[새 파일] {name}: {fname}")
            except Exception as exc:
                lines.append(f"- 새 파일 **{fname}** → 자동 반영 실패: {exc}. "
                             "기존 파일은 그대로 두었습니다. 포털에서 직접 확인해 주세요.")
                print(f"[반영 실패] {name}: {fname}: {exc}")
        report.append("\n".join(lines))

    state["_checked_at"] = datetime.datetime.now(KST).isoformat(timespec="seconds")
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if report:
        REPORT_PATH.write_text("\n\n".join(report) + "\n", encoding="utf-8")
    if broken:
        sys.exit(f"감시 실패: {', '.join(broken)}")


def main():
    targets = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if "--list" in sys.argv:
        run_list(targets)
    elif "--test" in sys.argv:
        run_test(targets)
    else:
        run_watch(targets)


if __name__ == "__main__":
    main()
