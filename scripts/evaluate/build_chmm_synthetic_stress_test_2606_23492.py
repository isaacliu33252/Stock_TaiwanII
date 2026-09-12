#!/usr/bin/env python3
"""arXiv:2606.23492 follow-up, testing the paper's third distinct use case
(the other two -- regime-detection trigger, regime-conditional VaR -- were
already tested separately): using the fitted heavy-tailed CHMM as a
SYNTHETIC DATA GENERATOR to stress-test whether Group A+'s existing
price-technical switch rule (switch_risk_ma80_dd11: 80-day MA-gap <= -1.5%
AND 80-day drawdown <= -11% triggers defensive, exit when MA-gap >= +1.5%,
5-day minimum hold) has a genuine edge over buy-and-hold, or whether its
apparent edge on the single realized 2020-2026 Taiwan history is an
overfitting artifact (feedback_overfitting_fixed_window_tuning) that
wouldn't generalize to other statistically-similar alternate histories.

METHOD: fit a K=3 Student-t CHMM on the FULL available 0050.TW history
(unconditional fit -- this is a synthetic-generation exercise, not a live
trading signal, so the causal/no-look-ahead discipline used in the other
two follow-ups does not apply here). Simulate N=300 independent synthetic
daily-return paths of the same length as the real 2020-2026 backtest
window, drawing the initial state from the fitted stationary distribution
(matching the paper's own Algorithm 2). For each synthetic path, apply a
SIMPLIFIED price-only version of the switch rule (same MA-gap/drawdown/
hold-day thresholds; the chip/derivative/total-risk-score gates are
dropped since they need data no univariate price generator can produce --
this is disclosed as a real simplification, not hidden) and compare its
Sharpe/MDD against buy-and-hold on that same synthetic path. Locate where
the REAL 2020-2026 history's own edge (same simplified rule, same
thresholds) falls within the resulting cross-synthetic-path distribution:
if the real edge sits deep in the tail of what 300 statistically-similar
alternate histories produce, the realized edge is likely a lucky fit to
this one history rather than a property the rule reliably captures.

Research-only. Reuses _fit_chmm_t from build_chmm_regime_detector_2606_
23492.py unmodified. No production code touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import t as student_t

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_chmm_regime_detector_2606_23492 import _fit_chmm_t  # noqa: E402

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
K = 3
N_PATHS = 300
MA_WINDOW = 80
DD_WINDOW = 80
ENTER_MA_GAP = -0.015
ENTER_DD = -0.11
EXIT_MA_GAP = 0.015
MIN_HOLD = 5
SEED = 20260823


def _stationary_dist(trans: np.ndarray) -> np.ndarray:
    Kk = trans.shape[0]
    pi = np.full(Kk, 1.0 / Kk)
    for _ in range(5000):
        pi = pi @ trans
        pi = pi / pi.sum()
    return pi


def simulate_paths(params: dict, n_days: int, n_paths: int, rng: np.random.Generator) -> np.ndarray:
    pi_stat = _stationary_dist(params["trans"])
    Kk = len(params["mu"])
    out = np.zeros((n_paths, n_days))
    for p in range(n_paths):
        state = rng.choice(Kk, p=pi_stat)
        for t in range(n_days):
            z = student_t.rvs(df=params["nu"], random_state=rng)
            out[p, t] = params["mu"][state] + params["sigma"][state] * z
            state = rng.choice(Kk, p=params["trans"][state])
    return out


def simplified_switch_return(logret: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Returns (rule_ret, defensive_flag) for a price-only proxy of
    switch_risk_ma80_dd11: defensive (flat/cash, 0 return) when 80-day
    MA-gap <= -1.5% and 80-day drawdown <= -11%; exit to golden (=underlying
    return) when MA-gap recovers to >= +1.5%; 5-day minimum hold either way.
    Chip/derivative/total-risk-score gates are dropped (unavailable from a
    univariate price generator)."""
    n = len(logret)
    price = np.exp(np.cumsum(logret))
    ma = pd.Series(price).rolling(MA_WINDOW).mean().values
    ma_gap = price / ma - 1.0
    roll_max = pd.Series(price).rolling(DD_WINDOW, min_periods=1).max().values
    drawdown = price / roll_max - 1.0

    defensive = False
    hold_left = 0
    flags = np.zeros(n, dtype=bool)
    for t in range(n):
        if np.isnan(ma_gap[t]):
            flags[t] = False
            continue
        if hold_left > 0:
            hold_left -= 1
        else:
            if not defensive and ma_gap[t] <= ENTER_MA_GAP and drawdown[t] <= ENTER_DD:
                defensive = True
                hold_left = MIN_HOLD - 1
            elif defensive and ma_gap[t] >= EXIT_MA_GAP:
                defensive = False
                hold_left = MIN_HOLD - 1
        flags[t] = defensive

    rule_ret = np.where(flags, 0.0, np.exp(logret) - 1.0)
    return rule_ret, flags


def perf_stats(r: np.ndarray) -> dict:
    ann_ret = r.mean() * 252
    ann_vol = r.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
    cum = np.cumprod(1 + r)
    mdd = (cum / np.maximum.accumulate(cum) - 1).min()
    return {"ann_ret": float(ann_ret), "sharpe": float(sharpe), "mdd": float(mdd)}


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    close = con.execute("select dt, close from ohlcv where ticker='0050.TW' order by dt").fetchdf()
    close["dt"] = pd.to_datetime(close["dt"])
    close = close.set_index("dt")["close"].sort_index()
    logret_full = np.log(close / close.shift(1)).dropna().values

    print(f"Fitting K={K} Student-t CHMM on full 0050.TW history (n={len(logret_full)} days, unconditional fit)")
    params = _fit_chmm_t(logret_full, K=K)
    for k in range(K):
        print(f"  state {k}: mu={params['mu'][k]*100:.3f}%/day  sigma={params['sigma'][k]*100:.3f}%/day  "
              f"nu={params['nu']:.1f}")

    real_len = 1611  # matches the 2020-01-02 to 2026-08 backtest window used elsewhere this session
    real_logret = logret_full[-real_len:]
    real_rule_ret, real_flags = simplified_switch_return(real_logret)
    real_bh_ret = np.exp(real_logret) - 1.0
    real_rule_perf = perf_stats(real_rule_ret)
    real_bh_perf = perf_stats(real_bh_ret)
    real_edge_sharpe = real_rule_perf["sharpe"] - real_bh_perf["sharpe"]
    real_edge_mdd = real_rule_perf["mdd"] - real_bh_perf["mdd"]
    print(f"\nReal 2020-2026 history (last {real_len} days): "
          f"defensive_share={real_flags.mean()*100:.1f}%  "
          f"rule_sharpe={real_rule_perf['sharpe']:.3f}  bh_sharpe={real_bh_perf['sharpe']:.3f}  "
          f"edge_sharpe={real_edge_sharpe:+.3f}  "
          f"rule_mdd={real_rule_perf['mdd']*100:.2f}%  bh_mdd={real_bh_perf['mdd']*100:.2f}%  "
          f"edge_mdd_pp={real_edge_mdd*100:+.2f}pp")

    rng = np.random.default_rng(SEED)
    print(f"\nSimulating {N_PATHS} synthetic {real_len}-day paths from the fitted CHMM...")
    synth_paths = simulate_paths(params, real_len, N_PATHS, rng)

    edge_sharpes, edge_mdds, defensive_shares = [], [], []
    for p in range(N_PATHS):
        lr = synth_paths[p]
        rule_ret, flags = simplified_switch_return(lr)
        bh_ret = np.exp(lr) - 1.0
        rp = perf_stats(rule_ret)
        bp = perf_stats(bh_ret)
        edge_sharpes.append(rp["sharpe"] - bp["sharpe"])
        edge_mdds.append(rp["mdd"] - bp["mdd"])
        defensive_shares.append(flags.mean())

    edge_sharpes = np.array(edge_sharpes)
    edge_mdds = np.array(edge_mdds)
    defensive_shares = np.array(defensive_shares)

    pct_sharpe = float((edge_sharpes < real_edge_sharpe).mean() * 100)
    pct_mdd = float((edge_mdds < real_edge_mdd).mean() * 100)

    print(f"\n=== Synthetic-ensemble distribution of the rule's edge over buy-and-hold ({N_PATHS} paths) ===")
    print(f"edge_sharpe: mean={edge_sharpes.mean():+.3f}  median={np.median(edge_sharpes):+.3f}  "
          f"[p5,p95]=[{np.percentile(edge_sharpes,5):+.3f}, {np.percentile(edge_sharpes,95):+.3f}]  "
          f"pct of synthetic paths below real edge: {pct_sharpe:.1f}%")
    print(f"edge_mdd_pp: mean={edge_mdds.mean()*100:+.2f}  median={np.median(edge_mdds)*100:+.2f}  "
          f"[p5,p95]=[{np.percentile(edge_mdds,5)*100:+.2f}, {np.percentile(edge_mdds,95)*100:+.2f}]  "
          f"pct of synthetic paths below real edge: {pct_mdd:.1f}%")
    print(f"defensive-day share: mean={defensive_shares.mean()*100:.1f}%  "
          f"[p5,p95]=[{np.percentile(defensive_shares,5)*100:.1f}%, {np.percentile(defensive_shares,95)*100:.1f}%]  "
          f"(real history: {real_flags.mean()*100:.1f}%)")
    print(f"share of synthetic paths where the rule beats buy-and-hold on Sharpe: "
          f"{float((edge_sharpes > 0).mean()*100):.1f}%")
    print(f"share of synthetic paths where the rule improves MDD (less negative): "
          f"{float((edge_mdds > 0).mean()*100):.1f}%")

    out = pd.DataFrame({"edge_sharpe": edge_sharpes, "edge_mdd": edge_mdds, "defensive_share": defensive_shares})
    out_path = PROJECT_ROOT / "results" / "chmm_synthetic_stress_test_2606_23492.csv"
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
