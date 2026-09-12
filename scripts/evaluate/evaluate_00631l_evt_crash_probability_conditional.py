#!/usr/bin/env python3
"""Covariate-conditional extension of evaluate_00631l_evt_crash_probability.py.

Research-only, 2026-08-14. Follows a review of arXiv:2506.17549 (Das,
"Predicting Stock Market Crash with Bayesian Generalised Pareto
Regression"), closed as not directly importable (its own covariate is
same-day/contemporaneous with the response and its train/test split is
random rather than walk-forward -- both would leak look-ahead into a
"prediction"). This script keeps the paper's one genuinely testable idea --
letting the GPD scale parameter respond to a covariate via a log-linear
link, MAP-estimated under a Cauchy prior (paper's own best-performing prior
choice, Table 2) -- and reattaches it to this project's own walk-forward
POT estimator for 00631L, which evaluate_00631l_evt_crash_probability.py's
docstring already flagged as "the cleanest calibration result of this
session's EVT/tail-risk line" (unconditional scale, 2026-07-12).

Covariate: trailing 21-day realized volatility of the evaluated ticker's own
daily returns (00631L.TW by default, matching the base script's cleanest
result), shifted by one day so the value used to explain day t's exceedance
never includes day t's own return (fixes the paper's contemporaneous-covariate
flaw). Standardised using only the training window's mean/std, frozen at
each refit (fixes the paper's random-split flaw: no test-period statistic
enters standardisation, exactly as the base script's refit_every/no-lookahead
discipline already requires).

Model (paper's Eq. for the GPD regression, mu=0 on exceedances):
    e_i ~ GPD(0, sigma_i, xi),  log(sigma_i) = beta0 + beta1 * vol_std_i

MAP objective = negative log-likelihood + Cauchy(0,1) penalty on (beta0,
beta1) + truncated-Cauchy(0,1) penalty on xi (support xi < 1), optimised
with L-BFGS-B (paper uses BFGS; bounds keep xi in the region where the MLE
is asymptotically well-behaved, Smith 1985).

This script only checks whether the conditional scale improves calibration
(correlation with forward 20d min return, and firing-level realized
severity) relative to the unconditional baseline -- same "test the premise
before building a trading rule" discipline as the base script. It does not
build or evaluate a trading gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_downside_vol_return_timing import _load_close
from scripts.evaluate.evaluate_00631l_evt_crash_probability import (
    _walk_forward_crash_prob as _walk_forward_crash_prob_unconditional,
)

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_evt_crash_probability_conditional_latest.json"

ROLLING_WINDOW = 504
REFIT_EVERY = 21
THRESHOLD_PERCENTILE = 0.90
CRASH_SEVERITY = 0.07
MIN_EXCEEDANCES = 20
VOL_LOOKBACK = 21


def _trailing_vol(returns: pd.Series, lookback: int = VOL_LOOKBACK) -> pd.Series:
    """Causal trailing realized volatility: value at t uses returns up to and
    including t-1 only (shift(1) after rolling), matching the base script's
    no-look-ahead convention."""
    return returns.rolling(lookback).std().shift(1)


def _neg_log_posterior(params: np.ndarray, exceedances: np.ndarray, vol_std: np.ndarray) -> float:
    beta0, beta1, xi = params
    if xi >= 0.95 or xi <= -0.95 or not np.isfinite(beta0) or not np.isfinite(beta1):
        return 1e12
    log_scale = beta0 + beta1 * vol_std
    if np.any(log_scale > 30.0) or np.any(log_scale < -30.0):
        return 1e12
    scale = np.exp(log_scale)
    z = xi * exceedances / scale
    support_term = 1.0 + z
    if np.any(support_term <= 1e-8):
        return 1e12
    nll = float(np.sum(log_scale) - (1.0 / xi - 1.0) * np.sum(np.log(support_term)))
    if not np.isfinite(nll):
        return 1e12
    # Cauchy(0,1) penalty on beta0, beta1: -log p(beta) = log(1 + beta^2) + const
    penalty_beta = float(np.log1p(beta0**2) + np.log1p(beta1**2))
    # truncated-Cauchy(0,1) penalty on xi (xi < 1 already enforced above)
    penalty_xi = float(np.log1p(xi**2))
    return nll + penalty_beta + penalty_xi


def _fit_conditional_gpd(
    exceedances: np.ndarray,
    vol_std: np.ndarray,
    *,
    mle_shape: float,
    mle_scale: float,
) -> tuple[float, float, float] | None:
    x0 = np.array([np.log(max(mle_scale, 1e-6)), 0.0, float(np.clip(mle_shape, -0.49, 0.9))])
    result = minimize(
        _neg_log_posterior,
        x0,
        args=(exceedances, vol_std),
        method="Nelder-Mead",
        options={"xatol": 1e-6, "fatol": 1e-6, "maxiter": 2000},
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        return None
    beta0, beta1, xi = result.x
    if xi >= 0.95 or xi <= -0.95:
        return None
    return float(beta0), float(beta1), float(xi)


def _walk_forward_crash_prob_conditional(
    returns: pd.Series,
    *,
    window: int = ROLLING_WINDOW,
    refit_every: int = REFIT_EVERY,
    threshold_percentile: float = THRESHOLD_PERCENTILE,
    crash_severity: float = CRASH_SEVERITY,
    vol_lookback: int = VOL_LOOKBACK,
) -> pd.Series:
    negated = -returns
    vol = _trailing_vol(returns, vol_lookback)
    n = len(negated)
    crash_prob = pd.Series(np.nan, index=negated.index)

    u: float | None = None
    beta0 = beta1 = xi = None
    vol_mean = vol_std_scale = None
    exceed_rate: float | None = None
    last_fit_idx = -(10**9)

    for i in range(n):
        train_start = max(0, i - window)
        train_end = i
        if train_end - train_start < window // 2:
            continue
        if (i - last_fit_idx) >= refit_every or u is None:
            train_negated = negated.iloc[train_start:train_end]
            train_vol = vol.iloc[train_start:train_end]
            train = pd.DataFrame({"negated": train_negated, "vol": train_vol}).dropna()
            if len(train) < window // 2:
                last_fit_idx = i
                continue
            u_candidate = float(train["negated"].quantile(threshold_percentile))
            mask = train["negated"] > u_candidate
            exceed_df = train.loc[mask]
            if len(exceed_df) < MIN_EXCEEDANCES:
                last_fit_idx = i
                continue

            vol_mean_c = float(train["vol"].mean())
            vol_std_scale_c = float(train["vol"].std())
            if not np.isfinite(vol_std_scale_c) or vol_std_scale_c <= 0.0:
                last_fit_idx = i
                continue

            exceedance_vals = (exceed_df["negated"] - u_candidate).to_numpy()
            vol_std_vals = ((exceed_df["vol"] - vol_mean_c) / vol_std_scale_c).to_numpy()

            try:
                mle_shape_c, _, mle_scale_c = stats.genpareto.fit(exceedance_vals, floc=0.0)
            except Exception:
                last_fit_idx = i
                continue

            fit = _fit_conditional_gpd(
                exceedance_vals, vol_std_vals, mle_shape=float(mle_shape_c), mle_scale=float(mle_scale_c)
            )
            if fit is None:
                last_fit_idx = i
                continue

            u = u_candidate
            beta0, beta1, xi = fit
            vol_mean, vol_std_scale = vol_mean_c, vol_std_scale_c
            exceed_rate = float(len(exceed_df) / len(train))
            last_fit_idx = i

        if u is None or crash_severity <= u:
            continue
        current_vol = vol.iloc[i]
        if pd.isna(current_vol):
            continue
        vol_std_i = (float(current_vol) - vol_mean) / vol_std_scale
        scale_i = float(np.exp(beta0 + beta1 * vol_std_i))
        tail_excess = crash_severity - u
        sf = float(stats.genpareto.sf(tail_excess, xi, loc=0.0, scale=scale_i))
        crash_prob.iloc[i] = exceed_rate * sf

    return crash_prob


def _calibration_summary(ticker: str, close: pd.Series, crash_prob: pd.Series) -> dict:
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
        realized = (
            float(forward_20d_min_return[fired.reindex(forward_20d_min_return.index, fill_value=False)].mean())
            if n_fired > 0
            else None
        )
        baseline = float(forward_20d_min_return.mean())
        firing_levels[f"p{int(pct*1000)}"] = {
            "threshold_prob": thresh,
            "n_fired": n_fired,
            "fraction_of_days": n_fired / len(valid) if len(valid) else None,
            "mean_fwd_20d_min_daily_return_when_fired": realized,
            "mean_fwd_20d_min_daily_return_baseline": baseline,
        }

    return {
        "ticker": ticker,
        "n_valid_days": int(len(valid)),
        "crash_prob_summary": {
            "mean": float(valid.mean()) if len(valid) else None,
            "median": float(valid.median()) if len(valid) else None,
            "max": float(valid.max()) if len(valid) else None,
            "min": float(valid.min()) if len(valid) else None,
        },
        "corr_crash_prob_vs_fwd_20d_min_return": corr,
        "firing_levels": firing_levels,
    }


def evaluate(ticker: str, start: str, end: str) -> dict:
    close = _load_close(DB_PATH, ticker).loc[start:end]
    returns = close.pct_change().fillna(0.0)

    crash_prob_unconditional = _walk_forward_crash_prob_unconditional(returns)
    crash_prob_conditional = _walk_forward_crash_prob_conditional(returns)

    return {
        "ticker": ticker,
        "window": {"start": start, "end": end},
        "unconditional": _calibration_summary(ticker, close, crash_prob_unconditional),
        "conditional_on_0050_trailing_vol": _calibration_summary(ticker, close, crash_prob_conditional),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="00631L.TW")
    parser.add_argument("--start", default="2013-01-01")
    parser.add_argument("--end", default="2026-08-14")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = evaluate(args.ticker, args.start, args.end)
    for label in ("unconditional", "conditional_on_0050_trailing_vol"):
        res = payload[label]
        print(f"[{label}] n={res['n_valid_days']} corr(crash_prob, fwd_20d_min_ret)={res['corr_crash_prob_vs_fwd_20d_min_return']}")
        for level, fl in res["firing_levels"].items():
            print(
                f"  {level}: threshold={fl['threshold_prob']:.4f} n_fired={fl['n_fired']} "
                f"mean_fwd_min_ret_when_fired={fl['mean_fwd_20d_min_daily_return_when_fired']} "
                f"vs baseline={fl['mean_fwd_20d_min_daily_return_baseline']}"
            )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
