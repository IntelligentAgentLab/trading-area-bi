"""
DID 결과 사전계산 스크립트 — streamlit_demo/pages/4_인과추론.py 용
================================================================================
인과추론 페이지는 회귀를 직접 돌리지 않고 이 스크립트가 만든 CSV 3개만 읽습니다.
자치구x업종 고정효과 회귀가 4~5분 걸려서 Streamlit 앱에서 매번 돌리기에
부적합하기 때문입니다.

언제 실행하나
  - 비교 연도(WINDOWS)를 바꿀 때
  - 원본 CSV(매출 데이터)가 갱신됐을 때

실행 방법 (저장소 루트에서)
  python scripts/build_did_results.py                 # data/raw/ 의 기본 파일 사용
  python scripts/build_did_results.py <원본CSV경로>    # 다른 경로 지정

입력 : data/raw/Seoul_sales_selected_data.csv
출력 : data/processed/did_event_study.csv
        data/processed/did_static_summary.csv
        data/processed/did_pretrend.csv

필요 패키지 : pandas, numpy, statsmodels   (matplotlib 불필요)
================================================================================
"""

import os
import sys

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

# ==================================================================
# 설정
# ==================================================================
# 이 스크립트는 <저장소 루트>/scripts/ 에 있으므로 루트는 한 단계 위
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    REPO_ROOT, "data", "raw", "Seoul_sales_selected_data.csv")
OUT_DIR = os.path.join(REPO_ROOT, "data", "processed")
os.makedirs(OUT_DIR, exist_ok=True)

# 페이지 드롭다운에 나올 비교 구간. 연도를 바꾸려면 여기만 고치면 됩니다.
# 주의: 2026년은 데이터에 1분기밖에 없어 사용할 수 없습니다 (2021~2025만 가능).
WINDOWS = [(2022, 2023), (2023, 2024), (2024, 2025)]

USE_RECTANGULAR_PANEL = True
N_BOOT = 999
RANDOM_SEED = 20260914
FE_MODE = "entity"      # "entity"(표준, 느림) / "additive"(약 10배 빠름, 직사각 패널에선 계수 동일)

OUTCOME_RAW = "당월_매출_금액"
COL_DISTRICT = "자치구_코드"
COL_INDUSTRY = "서비스_업종_코드"
COL_QCODE = "기준_년분기_코드"
COL_TREAT = "treatment"

M_POOLED = "사전기간 풀링(강의자료 29~32쪽)"
M_YOY = "전년동기 매칭(계절성 제거)"


def _fe(time_term):
    unit = "C(entity)" if FE_MODE == "entity" else f"C({COL_DISTRICT}) + C({COL_INDUSTRY})"
    return f"{unit} + {time_term}"


# ==================================================================
# 데이터 적재 / 직사각 균형패널
# ==================================================================
def load_data(path=DATA_PATH, rectangular=USE_RECTANGULAR_PANEL):
    df = pd.read_csv(path)
    df["year"] = df[COL_QCODE] // 10
    df["q"] = df[COL_QCODE] % 10
    df["log_sales"] = np.log(df[OUTCOME_RAW])
    df["entity"] = df[COL_DISTRICT].astype(str) + "_" + df[COL_INDUSTRY].astype(str)

    assert (df.groupby(COL_INDUSTRY)[COL_TREAT].nunique() == 1).all(), \
        "treatment 가 동일 업종 내에서 일정하지 않습니다."

    n0 = len(df)
    if rectangular:
        n_q = df[COL_QCODE].nunique()
        cov = df.groupby(COL_INDUSTRY)[COL_DISTRICT].nunique()
        keep_ind = cov[cov == df[COL_DISTRICT].nunique()].index
        full = df.groupby("entity")[COL_QCODE].transform("nunique") == n_q
        df = df[df[COL_INDUSTRY].isin(keep_ind) & full].copy()
        print(f"[패널] 직사각 균형패널: {n0:,}행 -> {len(df):,}행 "
              f"(업종 {df[COL_INDUSTRY].nunique()}개 x 자치구 {df[COL_DISTRICT].nunique()}개 "
              f"x 분기 {df[COL_QCODE].nunique()}개)")
    return df


# ==================================================================
# 추정량
# ==================================================================
def diagnose_pretrend(df, pre_year):
    g = (df[df.year == pre_year]
         .groupby([COL_QCODE, COL_TREAT])["log_sales"].mean().unstack())
    gap = (g[1] - g[0]).reset_index()
    gap.columns = [COL_QCODE, "gap"]
    gap["t"] = np.arange(len(gap))
    m = smf.ols("gap ~ t", data=gap).fit()
    return {"pre_year": pre_year, "slope": m.params["t"], "pvalue": m.pvalues["t"],
            "gap_first": gap["gap"].iloc[0], "gap_last": gap["gap"].iloc[-1]}


def did_pooled_pre(panel, target_q):
    """강의자료 30쪽 did_date() 의 분기 버전 — 사전기간을 한 덩어리로 묶어 비교."""
    sub = panel[(panel["post_base"] == 0) | (panel[COL_QCODE] == target_q)]
    sub = sub[sub[COL_QCODE] <= target_q].copy()
    sub["post"] = (sub[COL_QCODE] == target_q).astype(int)
    sub["qs"] = sub[COL_QCODE].astype(str)

    m = smf.ols(f"log_sales ~ I(treatment * post) + {_fe('C(qs)')}", data=sub).fit(
        cov_type="cluster", cov_kwds={"groups": sub[COL_INDUSTRY]})
    k = "I(treatment * post)"
    lo, hi = m.conf_int().loc[k]
    return {"qcode": target_q, "att": m.params[k], "se": m.bse[k],
            "ci_low": lo, "ci_up": hi, "pvalue": m.pvalues[k]}


def did_same_quarter(df, base_year, comp_year, qq):
    """같은 분기끼리만 비교 — 계절성이 설계상 상쇄됨."""
    sub = df[(df.q == qq) & (df.year.isin([base_year, comp_year]))].copy()
    sub["post"] = (sub.year == comp_year).astype(int)

    m = smf.ols(f"log_sales ~ I(treatment * post) + {_fe('C(year)')}", data=sub).fit(
        cov_type="cluster", cov_kwds={"groups": sub[COL_INDUSTRY]})
    k = "I(treatment * post)"
    lo, hi = m.conf_int().loc[k]
    return {"qcode": comp_year * 10 + qq, "att": m.params[k], "se": m.bse[k],
            "ci_low": lo, "ci_up": hi, "pvalue": m.pvalues[k]}


def _twoway_within(y, entity, time):
    s = pd.Series(y)
    return (s - s.groupby(entity).transform("mean")
              - s.groupby(time).transform("mean") + s.mean()).to_numpy()


def wild_cluster_bootstrap_p(sub, n_boot=N_BOOT, seed=RANDOM_SEED):
    """귀무가설 제약 하 Rademacher wild cluster bootstrap p-value."""
    y = _twoway_within(sub["log_sales"].to_numpy(), sub["entity"].to_numpy(), sub["qs"].to_numpy())
    d = _twoway_within((sub[COL_TREAT] * sub["post"]).to_numpy().astype(float),
                       sub["entity"].to_numpy(), sub["qs"].to_numpy())
    dd = float(d @ d)
    if dd == 0:
        return np.nan, np.nan

    g = pd.factorize(sub[COL_INDUSTRY].to_numpy())[0]
    G = g.max() + 1

    def t_stat(yv):
        b = float(d @ yv) / dd
        u = yv - b * d
        score = np.bincount(g, weights=d * u, minlength=G)
        return b / np.sqrt((score ** 2).sum() / dd ** 2), b

    t_obs, b_obs = t_stat(y)
    rng = np.random.default_rng(seed)
    cnt = 0
    for _ in range(n_boot):
        w = rng.choice([-1.0, 1.0], size=G)[g]
        if abs(t_stat(y * w)[0]) >= abs(t_obs):
            cnt += 1
    return (cnt + 1) / (n_boot + 1), b_obs


def run_static_did(df, pre_year, post_year):
    w = df[df.year.isin([pre_year, post_year])].copy()
    w["post"] = (w.year == post_year).astype(int)
    w["qs"] = w[COL_QCODE].astype(str)

    m = smf.ols(f"log_sales ~ I(treatment * post) + {_fe('C(qs)')}", data=w).fit(
        cov_type="cluster", cov_kwds={"groups": w[COL_INDUSTRY]})
    k = "I(treatment * post)"
    lo, hi = m.conf_int().loc[k]
    p_wild, b_check = wild_cluster_bootstrap_p(w)
    assert abs(b_check - m.params[k]) < 1e-8, "within 변환 계수와 OLS 계수가 불일치합니다."

    return {"pre_year": pre_year, "post_year": post_year,
            "att": m.params[k], "se": m.bse[k], "ci_low": lo, "ci_up": hi,
            "pvalue_cluster": m.pvalues[k], "pvalue_wild": p_wild,
            "n_obs": int(m.nobs), "n_clusters": int(w[COL_INDUSTRY].nunique())}


def run_window(df, pre_year, post_year):
    w = df[df.year.isin([pre_year, post_year])].copy()
    w["post_base"] = (w.year == post_year).astype(int)
    qcodes = sorted(w[COL_QCODE].unique())

    pooled = pd.DataFrame([did_pooled_pre(w, qc) for qc in qcodes[1:]])
    pooled["method"] = M_POOLED

    rows = []
    prev = pre_year - 1
    if prev in set(df.year.unique()):
        rows += [did_same_quarter(df, prev, pre_year, qq) for qq in (1, 2, 3, 4)]
    rows += [did_same_quarter(df, pre_year, post_year, qq) for qq in (1, 2, 3, 4)]
    yoy = pd.DataFrame(rows)
    yoy["method"] = M_YOY

    for d in (pooled, yoy):
        d["year"] = d["qcode"] // 10
        d["q"] = d["qcode"] % 10
        d["label"] = d["year"].astype(str) + "Q" + d["q"].astype(str)
        d["is_post"] = d["year"] == post_year
        d["window"] = f"{pre_year}_{post_year}"
    return pooled, yoy


# ==================================================================
# 메인
# ==================================================================
def main():
    print(f"[입력] {DATA_PATH}")
    df = load_data()

    statics, all_est, pretrends = [], [], []
    for pre_year, post_year in WINDOWS:
        print(f"\n=== {pre_year} vs {post_year} 계산 중 ===")
        pt = diagnose_pretrend(df, pre_year)
        pretrends.append(pt)

        st_res = run_static_did(df, pre_year, post_year)
        statics.append(st_res)
        print(f"  정적 DID ATT={st_res['att']*100:+.2f}% "
              f"(클러스터 p={st_res['pvalue_cluster']:.3f}, wild p={st_res['pvalue_wild']:.3f})")

        pooled, yoy = run_window(df, pre_year, post_year)
        placebo = yoy[~yoy["is_post"]]
        pt["n_placebo"] = len(placebo)
        pt["n_placebo_sig"] = int((placebo["pvalue"] < 0.05).sum())
        print(f"  처치 전 유의 placebo {pt['n_placebo_sig']}/{pt['n_placebo']}개")

        all_est += [pooled, yoy]

    pd.concat(all_est, ignore_index=True).to_csv(
        os.path.join(OUT_DIR, "did_event_study.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(statics).to_csv(
        os.path.join(OUT_DIR, "did_static_summary.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(pretrends).to_csv(
        os.path.join(OUT_DIR, "did_pretrend.csv"), index=False, encoding="utf-8-sig")
    print(f"\n[완료] 결과 CSV 3개 저장: {OUT_DIR}")
    print("   커밋 후 푸시하면 Streamlit Cloud 가 자동 재배포합니다.")


if __name__ == "__main__":
    main()
