"""1372 소비자상담 원본(JSON, 213만 건, 1.8GB)을 대시보드가 쓸 수 있는 작은 집계 CSV로 만든다.

원본은 개인 API 키로 받아야 하고 용량도 커서 git에 올리지 않는다(.gitignore 참고). 그러면
팀원이 저장소를 클론만 받았을 때 소비자상담 페이지에서 아무것도 못 보게 되는 문제가 생겨서,
행 단위 원본 대신 "몇 개 조합으로 몇 건이었는지"만 남긴 집계본을 만들어 git에 커밋해둔다.

두 개로 나눈 이유: 추이 차트(월별)는 지역이 필요 없고, 지역 차트는 월이 필요 없다. 지역까지
합쳐서 한 번에 집계하면(대분류×중분류×불만유형×채널×지역×월) 조합 수가 원본의 30%밖에 안
줄어드는데(60만 행, 58MB), 필요할 때만 나눠서 집계하면 훨씬 작아진다(합쳐서 17만 행, 13MB).

사용법:
    python3 scripts/build_consumer_counsel_summary.py

출력:
    data/processed/consumer_counsel_monthly.csv — 월,대분류,중분류,불만유형,채널,건수 (추이 탭용)
    data/processed/consumer_counsel_region.csv  — 대분류,중분류,불만유형,지역,건수      (지역 탭용)
"""
import glob
import json
import sys
from pathlib import Path

import pandas as pd

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "consumer_counsel"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

온라인_유형 = {"국내온라인거래", "모바일거래", "국제온라인거래", "소셜커머스(쇼핑)"}

컬럼명_매핑 = {
    "prdlstLclasNm": "대분류",
    "prdlstMlsfcNm": "중분류",
    "dscsnCnClNm": "불만유형",
    "upAreaNm": "지역",
}


def load_raw() -> pd.DataFrame:
    files = sorted(glob.glob(str(RAW_DIR / "*.json")))
    if not files:
        raise SystemExit(
            f"{RAW_DIR}에 데이터가 없습니다. scripts/fetch_consumer_counsel.py로 먼저 받아주세요."
        )
    dfs = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            dfs.append(pd.DataFrame(json.load(fp)))
    df = pd.concat(dfs, ignore_index=True)
    print(f"원본 {len(df):,}건 로드")

    범주형_컬럼 = list(컬럼명_매핑) + ["ntslTyStleCdNm"]
    df[범주형_컬럼] = df[범주형_컬럼].fillna("미상")  # 결측치 최대 3% 수준(dscsnCnClNm) 존재
    df["월"] = pd.to_datetime(df["rcptYm"], format="%Y%m").dt.strftime("%Y-%m")
    df["채널"] = df["ntslTyStleCdNm"].apply(lambda x: "온라인" if x in 온라인_유형 else "기타(오프라인 등)")
    return df.rename(columns=컬럼명_매핑)


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df = load_raw()

    월별 = df.groupby(["월", "대분류", "중분류", "불만유형", "채널"]).size().reset_index(name="건수")
    지역별 = df.groupby(["대분류", "중분류", "불만유형", "지역"]).size().reset_index(name="건수")

    월별_path = PROCESSED_DIR / "consumer_counsel_monthly.csv"
    지역별_path = PROCESSED_DIR / "consumer_counsel_region.csv"
    월별.to_csv(월별_path, index=False, encoding="utf-8-sig")
    지역별.to_csv(지역별_path, index=False, encoding="utf-8-sig")

    print(f"저장 완료: {월별_path} ({len(월별):,}행)")
    print(f"저장 완료: {지역별_path} ({len(지역별):,}행)")


if __name__ == "__main__":
    sys.exit(main())
