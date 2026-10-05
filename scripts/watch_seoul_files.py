"""서울 열린데이터광장의 '파일로만 제공되는' 데이터셋(서울사랑상품권)을 감시한다.

Open API가 없는 데이터셋은 담당자가 엑셀을 게시글에 첨부하는 방식이다. 새 자료가 올라오는
모양이 세 가지라(새 첨부가 추가됨 / 같은 자리의 파일이 이름만 바뀌어 교체됨 / 이름도 그대로인데
내용만 바뀜), 목록의 번호나 파일명만 봐서는 놓치는 경우가 생긴다. 그래서 감시 대상 파일을 매번
내려받아 **내용 해시**를 지난번과 비교한다 - 대상이 몇 개 안 되고 가장 큰 것도 30MB라 부담이 없다.

바뀐 파일은 data/raw/seoul_trading_area/ 아래 제자리에 두고, 무슨 일이 있었는지
update_report.md에 적는다(워크플로가 이 파일로 GitHub Issue를 만들어 알린다).

사용법:
    python scripts/watch_seoul_files.py            # 감시 실행 (Actions가 실행하는 방식)
    python scripts/watch_seoul_files.py --list     # 페이지에서 읽어낸 파일 목록만 출력
    python scripts/watch_seoul_files.py --test     # 대상별 최신 파일 1개를 _watch_test/에 시험 다운로드

감시 대상은 scripts/seoul_files.json에 있다. mode가 두 가지:
    all    - 목록에 있는 감시 대상을 전부 본다. 새 달이 올라오면 추가된다 (결제내역)
    latest - 가장 나중에 올라온 파일 하나만 고정된 이름으로 유지한다 (발행·판매 현황, 가맹점)
"""
import hashlib
import html as htmllib
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "seoul_trading_area"
CONFIG_PATH = Path(__file__).resolve().parent / "seoul_files.json"
STATE_PATH = RAW_DIR / "_meta" / "file_watch_state.json"
REPORT_PATH = ROOT / "update_report.md"
TEST_DIR = ROOT / "_watch_test"
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


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def year_dir(target, name):
    """dest의 {year}를 파일명의 'NN년'에서 뽑은 연도로 채운다 (예: 26년04월 → 2026)."""
    m = re.match(r"(\d{2})년", name)
    return RAW_DIR / target["dest"].replace("{year}", f"20{m.group(1)}" if m else "기타")


def put(src, final, check, name):
    """검사를 통과한 파일을 제자리에 둔다. 한 일을 '추가'/'내용 갱신'/None(이미 같음)으로 돌려준다."""
    if final.exists() and sha256_of(final) == sha256_of(src):
        return None
    if check:
        CHECKS[check](src, name)
    if src.stat().st_size > MAX_BYTES:
        raise RuntimeError(f"{src.stat().st_size / 1e6:.0f}MB로 GitHub 한도(100MB)에 걸립니다")
    did = "내용 갱신" if final.exists() else "추가"
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(src.read_bytes())
    return did


def apply(target, name, src, workdir):
    """내려받은 파일 하나를 저장소에 반영하고, 알림에 쓸 문장 목록을 돌려준다(바뀐 게 없으면 빈 목록)."""
    rel = lambda p: p.relative_to(ROOT).as_posix()
    check = target.get("check")

    if name.lower().endswith(".zip"):
        # 연말에 올라오는 연도별 zip. 안에 든 월별 파일을 꺼내 월별로 받은 것과 같은 자리에 둔다 -
        # 월별 파일이 따로 안 올라왔던 달을 채우고, 이미 있는 달은 내용이 같으면 건드리지 않는다.
        notes, found = [], 0
        with zipfile.ZipFile(src) as z:
            for info in z.infolist():
                member = info.filename
                try:  # 한글 Windows에서 만든 zip은 파일명이 깨져 보인다 - 1_대시보드.py와 같은 방식으로 복원
                    member = member.encode("cp437").decode("euc-kr")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass  # 이미 정상적인 이름
                base = member.replace("\\", "/").split("/")[-1]
                if not re.match(r"\d{2}년\d{2}월.*\.xlsx$", base):
                    continue
                out = workdir / base
                out.write_bytes(z.read(info))
                final = year_dir(target, base) / base
                did = put(out, final, check, base)
                found += 1
                if did:
                    notes.append(f"{did}: `{rel(final)}`")
        if not found:  # 아무것도 못 꺼냈는데 조용히 넘어가면 "처리함"으로 기록돼 다시는 보지 않게 된다
            raise RuntimeError("zip 안에서 'NN년NN월 ….xlsx' 파일을 찾지 못했습니다")
        return notes

    if target.get("mode", "all") == "latest":
        folder = RAW_DIR / target["dest"]
        if target.get("to_csv"):
            final = folder / f"{target['filename']}.csv"
            folder.mkdir(parents=True, exist_ok=True)
            notes = [f"교체: `{rel(final)}` ({to_csv(src, final, target['columns'])})"]
        else:
            final = folder / f"{target['filename']}{Path(name).suffix}"
            did = put(src, final, check, name)
            notes = [f"{did}: `{rel(final)}`"] if did else []
        # 고정 이름인데 확장자만 다른 예전 파일이 남으면 로더가 어느 쪽을 집을지 모호해진다
        for old in folder.glob(f"{target['filename']}.*"):
            if old != final:
                old.unlink()
        return notes

    final = year_dir(target, name) / name
    did = put(src, final, check, name)
    return [f"{did}: `{rel(final)}`"] if did else []


def watched(target, files):
    mine = [f for f in files if re.search(target["match"], f[1])]
    return mine[-1:] if target.get("mode", "all") == "latest" else mine


def run_list(targets):
    for t in targets:
        _, page = fetch_page(t)
        files = list_files(page)
        mine = {seq for seq, _ in watched(t, files)}
        print(f"\n== {t['name']} ({t['inf_id']}): {len(files)}개 ==")
        for seq, name in files:
            print(f"  [{seq:>3}] {'감시' if seq in mine else '    '}  {name}")


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
    # 상태 파일에는 "원본 파일명 → 마지막으로 처리한 내용의 해시"만 둔다. 시각 같은 걸 넣으면 바뀐 게
    # 없는 날에도 파일이 달라져 매번 커밋이 생긴다.
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    report, broken = [], []
    for t in targets:
        tname = t["name"]
        try:
            url, page = fetch_page(t)
            files = watched(t, list_files(page))
            if not files:
                raise RuntimeError("감시 대상 파일을 찾지 못했습니다 (페이지 구조나 파일명 규칙이 바뀌었을 수 있음)")
        except Exception as exc:
            broken.append(tname)
            report.append(f"### {tname}\n- 감시 실패: {exc}")
            print(f"[실패] {tname}: {exc}")
            continue

        old = state.get(tname, {})
        new_state, lines = {}, []
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            for seq, name in files:
                try:
                    src = workdir / f"{seq}{Path(name).suffix}"
                    download(t, seq, src, url)
                    digest = sha256_of(src)
                except Exception as exc:
                    # 내려받지 못한 것은 '본 적 없음'으로 남겨 다음 실행 때 다시 시도한다
                    if name in old:
                        new_state[name] = old[name]
                    lines.append(f"- **{name}** → 다운로드 실패: {exc}")
                    print(f"[다운로드 실패] {tname}: {name}: {exc}")
                    continue
                if old.get(name) in (digest, "실패:" + digest):
                    new_state[name] = old[name]  # 지난번에 처리한(또는 반영에 실패해 이미 알린) 그 내용
                    continue
                try:
                    notes = apply(t, name, src, workdir)
                    new_state[name] = digest
                    for note in notes:
                        lines.append(f"- **{name}** → {note}")
                        print(f"[갱신] {tname}: {name}: {note}")
                except Exception as exc:
                    # 같은 내용으로 매번 알림이 반복되지 않게 실패한 해시도 기억해 둔다
                    new_state[name] = "실패:" + digest
                    lines.append(f"- **{name}** → 자동 반영 실패: {exc}. "
                                 "기존 파일은 그대로 두었습니다. 포털에서 직접 확인해 주세요.")
                    print(f"[반영 실패] {tname}: {name}: {exc}")
        state[tname] = dict(sorted(new_state.items()))
        if lines:
            report.append("\n".join([f"### {tname}", f"페이지: {url}"] + lines))
        else:
            print(f"[변화 없음] {tname}")

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if report:  # fetch_seoul_api.py가 먼저 적어 둔 내용이 있을 수 있어 이어 쓴다
        with open(REPORT_PATH, "a", encoding="utf-8") as f:
            f.write("\n\n".join(report) + "\n\n")
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
