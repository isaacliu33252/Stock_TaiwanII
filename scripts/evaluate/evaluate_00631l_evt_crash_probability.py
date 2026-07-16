#!/usr/bin/env python3
"""Walk-forward EVT/POT crash-probability estimator for 0050.TW, and a rare,
threshold-gated (not daily-adjusted) 00631L de-risk-to-0% rule built on it.

Research-only, 2026-07-12, following a discussion of Niu & Sayed (2025,
Analytic Methods in Accident Research), "Bayesian forecasting of short-term
crash risk with conditional extreme value models" -- a traffic-safety paper
(not stock-market crash risk; flagged clearly to the user), but its
GARCH-EVT vs one-stage conditional-POT comparison is the same methodology
family as group_a_plus/integrations/garch_regime_shadow.py's existing
GARCH-proxy + ratio/percentile threshold (a simplified two-stage-style
approach that has never been calibrated against an actual EVT/POT tail
model).

User's explicit design constraint: do NOT adjust 00631L daily / continuously
(the continuous vol-scaling and staged re-entry mechanisms tested earlier
this session both failed, partly from turnover). Instead, build a genuine
tail-probability ("crash_prob") estimate and ONLY flip 00631L to 0% when
that probability crosses a rare, extreme threshold -- matching how VaR/CVaR
are meant to be used (rare exceedance events), not a continuously-adjusted
score.

Method (simplified frequentist version of the paper's POT approach --  not
the full score-driven Bayesian GAS/MCMC machinery, which is a much larger
undertaking; this tests the core premise first):
  1. Rolling window (504 trading days) of daily returns for 0050.TW.
  2. Threshold u = 90th percentile of the trailing window's NEGATED daily
     returns (i.e. we model the left tail of returns as exceedances over u).
  3. Fit a Generalized Pareto (GP) distribution via MLE to the exceedances
     (e_i = negated_return_i - u for negated_return_i > u) using
     scipy.stats.genpareto.
  4. crash_prob_t = P(single-day negated return > crash_threshold), i.e. the
     GP tail survival function evaluated at a fixed extreme severity level
     (default 0.07, a 7% single-day drop), using Pr(X>u) * GP.sf(crash_
     threshold - u) per standard POT tail estimation (Coles 2001, ch. 4 --
     the same formula this session's other EVT-adjacent work has not yet
     used).
  5. Refit every 21 trading days (matches this project's existing HAR-RV
     walk-forward convention), no look-ahead: crash_prob_t only uses data
     available up to and including t-1.

This script first checks CALIBRATION (does the estimator produce a rare,
well-behaved probability, and does its rank-ordering actually align with
subsequent realized drawdowns) before considering any trading rule --
same "test the premise before building trading-curve machinery" discipline
used all session.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_downside_vol_return_timing import _load_close

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_evt_crash_probability_latest.json"

ROLLING_WINDOW = 504
REFIT_EVERY = 21
THRESHOLD_PERCENTILE = 0.90
CRASH_SEVERITY = 0.07  # 7% single-day drop
MIN_EXCEEDANCES = 20


def _walk_forward_crash_prob(
    returns: pd.Series,
    *,
    window: int = ROLLING_WINDOW,
    refit_every: int = REFIT_EVERY,
    threshold_percentile: float = THRESHOLD_PERCENTILE,
    crash_severity: float = CRASH_SEVERITY,
) -> pd.Series:
    negated = -returns
    n = len(negated)
    crash_prob = pd.Series(np.nan, index=negated.index)

    u: float | None = None
    shape: float | None = None
    scale: float | None = None
    exceed_rate: float | None = None
    last_fit_idx = -10**9

    for i in range(n):
        train_start = max(0, i - window)
        train_end = i  # causal: use data strictly before day i
        if train_end - train_start < window // 2:
            continue
        if (i - last_fit_idx) >= refit_every or u is None:
            train = negated.iloc[train_start:train_end].dropna()
            u_candidate = float(train.quantile(threshold_percentile))
            exceedances = train[train > u_candidate] - u_candidate
            if len(exceedances) < MIN_EXCEEDANCES:
                last_fit_idx = i
                continue
            try:
                shape_c, _, scale_c = stats.genpareto.fit(exceedances.to_numpy(), floc=0.0)
            except Exception:
                last_fit_idx = i
                continue
            u = u_candidate
            shape = float(shape_c)
            scale = float(scale_c)
            exceed_rate = float(len(exceedances) / len(train))
            last_fit_idx = i

        if u is None or crash_severity <= u:
            continue
        tail_excess = crash_severity - u
        sf = float(stats.genpareto.sf(tail_excess, shape, loc=0.0, scale=scale))
        crash_prob.iloc[i] = exceed_rate * sf

    return crash_prob


def evaluate(ticker: str, start: str, end: str) -> dict:
    close = _load_close(DB_PATH, ticker).loc[start:end]
    returns = close.pct_change().fillna(0.0)
    crash_prob = _walk_forward_crash_prob(returns)

    valid = crash_prob.dropna()
    forward_20d_min_return = close.pct_change(1).rolling(20).min().shift(-20)
    forward_20d_min_return = forward_20d_min_return.reindex(valid.index)

    joint = pd.DataFrame({"crash_prob": valid, "forward_20d_min_daily_return": forward_20d_min_return}).dropna()
    corr = float(joint["crash_prob"].corr(joint["forward_20d_min_daily_return"])) if len(joint) > 10 else None

    firing_levels = {}
    for pct in (0.90, 0.95, 0.99, 0.995):
        thresh = float(valid.quantile(pct))
        fired = valid >= thresh
        n_fired = int(fired.sum())
        realized_min_ret_when_fired = (
            float(forward_20d_min_return[fired.reindex(forward_20d_min_return.index, fill_value=False)].mean())
            if n_fired > 0
            else None
        )
        realized_min_ret_baseline = float(forward_20d_min_return.mean())
        firing_levels[f"p{int(pct*1000)}"] = {
            "threshold_prob": thresh,
            "n_fired": n_fired,
            "fraction_of_days": n_fired / len(valid),
            "mean_fwd_20d_min_daily_return_when_fired": realized_min_ret_when_fired,
            "mean_fwd_20d_min_daily_return_baseline": realized_min_ret_baseline,
        }

    return {
        "ticker": ticker,
        "window": {"start": start, "end": end},
        "n_valid_days": int(len(valid)),
        "crash_prob_summary": {
            "mean": float(valid.mean()),
            "median": float(valid.median()),
            "max": float(valid.max()),
            "min": float(valid.min()),
        },
        "corr_crash_prob_vs_fwd_20d_min_return": corr,
        "firing_levels": firing_levels,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="0050.TW")
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default="2026-07-09")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = evaluate(args.ticker, args.start, args.end)
    print(f"{payload['ticker']} {payload['window']['start']}..{payload['window']['end']}: n={payload['n_valid_days']}")
    print(f"crash_prob summary: {payload['crash_prob_summary']}")
    print(f"corr(crash_prob, fwd_20d_min_daily_return) = {payload['corr_crash_prob_vs_fwd_20d_min_return']}")
    print("(negative correlation is the expected sign: higher crash_prob -> more negative subsequent min daily return)")
    for level, res in payload["firing_levels"].items():
        print(
            f"  {level}: threshold={res['threshold_prob']:.4f} n_fired={res['n_fired']} "
            f"({res['fraction_of_days']*100:.2f}% of days) "
            f"mean_fwd_min_ret_when_fired={res['mean_fwd_20d_min_daily_return_when_fired']} "
            f"vs baseline={res['mean_fwd_20d_min_daily_return_baseline']:.4f}"
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
