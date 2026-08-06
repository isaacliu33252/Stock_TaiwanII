#!/usr/bin/env python3
"""Read-only research: does 0050.TW/00631L.TW show a statistically significant
GJR-GARCH leverage/asymmetry effect (negative shocks raise future volatility
more than positive shocks of the same size), matching arXiv:2607.16450v1's
finding for Taiwan-exposed ETFs (EWP gamma~0.118, p<0.001)?

This directly checks a claim from the same-day analysis of that paper: GroupA+'s
existing garch_regime_shadow.py / _garch_proxy_vol (backtest_group_a_plus_
financial_econometrics.py:65) is a hand-rolled SYMMETRIC GARCH(1,1) recursion
(omega + alpha*prev_ret^2 + beta*prev_var) with no leverage term -- an earlier
answer in this session incorrectly claimed it already matched the paper's
asymmetric-GARCH recommendation. This script tests whether that gap is
material for GroupA+'s actual assets, not just the paper's 30-ETF universe.

No `arch` package is installed in this environment (checked; not added here --
adding a new dependency is a separate decision from running this diagnostic).
This hand-rolls a Gaussian QMLE GARCH(1,1) and GJR-GARCH(1,1) fit via
scipy.optimize, then compares them with a likelihood-ratio test on the
asymmetry parameter (gamma), matching the LR-test approach standard in this
class of nested-model comparison. Does not modify garch_regime_shadow.py or
any production file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402


def _load_returns(ticker: str, start: str, end: str) -> pd.Series:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    prices = rows.set_index("dt")["close"].astype(float).sort_index()
    return prices.pct_change().dropna().rename(ticker)


def _neg_log_likelihood(params: np.ndarray, resid: np.ndarray, asymmetric: bool) -> float:
    if asymmetric:
        mu, log_omega, alpha, gamma, beta = params
    else:
        mu, log_omega, alpha, beta = params
        gamma = 0.0
    omega = np.exp(log_omega)
    eps = resid - mu
    n = len(eps)
    var = np.empty(n)
    var[0] = float(np.var(eps))
    for t in range(1, n):
        prev_eps = eps[t - 1]
        neg_flag = 1.0 if prev_eps < 0.0 else 0.0
        var[t] = omega + alpha * prev_eps**2 + gamma * neg_flag * prev_eps**2 + beta * var[t - 1]
    var = np.clip(var, 1e-12, None)
    ll = -0.5 * np.sum(np.log(2 * np.pi * var) + (eps**2) / var)
    return -float(ll)


def _fit(resid: np.ndarray, asymmetric: bool) -> dict[str, Any]:
    uncond_var = float(np.var(resid))
    if asymmetric:
        x0 = np.array([0.0, np.log(uncond_var * 0.05), 0.03, 0.05, 0.85])
        bounds = [(-0.01, 0.01), (None, None), (1e-6, 0.5), (0.0, 0.5), (1e-6, 0.999)]
    else:
        x0 = np.array([0.0, np.log(uncond_var * 0.05), 0.05, 0.90])
        bounds = [(-0.01, 0.01), (None, None), (1e-6, 0.5), (1e-6, 0.999)]
    result = minimize(
        _neg_log_likelihood,
        x0,
        args=(resid, asymmetric),
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 2000},
    )
    log_lik = -float(result.fun)
    if asymmetric:
        mu, log_omega, alpha, gamma, beta = result.x
        persistence = alpha + beta + gamma / 2.0
        params = {"mu": mu, "omega": np.exp(log_omega), "alpha": alpha, "gamma": gamma, "beta": beta}
    else:
        mu, log_omega, alpha, beta = result.x
        persistence = alpha + beta
        params = {"mu": mu, "omega": np.exp(log_omega), "alpha": alpha, "beta": beta}
    return {
        "converged": bool(result.success),
        "log_likelihood": log_lik,
        "params": params,
        "persistence": float(persistence),
    }


def _analyze(ticker: str, start: str, end: str) -> dict[str, Any]:
    returns = _load_returns(ticker, start, end)
    resid = returns.to_numpy(dtype=float)
    sym = _fit(resid, asymmetric=False)
    asym = _fit(resid, asymmetric=True)
    lr_stat = 2.0 * (asym["log_likelihood"] - sym["log_likelihood"])
    lr_stat = max(lr_stat, 0.0)
    p_value = float(stats.chi2.sf(lr_stat, df=1))
    return {
        "ticker": ticker,
        "window": {"start": str(returns.index.min().date()), "end": str(returns.index.max().date()), "rows": len(returns)},
        "symmetric_garch": sym,
        "gjr_garch": asym,
        "likelihood_ratio_test": {
            "statistic": lr_stat,
            "p_value": p_value,
            "significant_at_5pct": p_value < 0.05,
            "significant_at_1pct": p_value < 0.01,
        },
        "gamma_estimate": asym["params"]["gamma"],
    }


def main() -> None:
    results = {
        "0050.TW": _analyze("0050.TW", "2009-01-02", "2026-07-31"),
        "00631L.TW": _analyze("00631L.TW", "2014-10-23", "2026-07-31"),
    }
    out_path = PROJECT_ROOT / "results" / "gjr_garch_asymmetry_test_20260801.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Saved: {out_path}")
    for ticker, res in results.items():
        print(f"\n=== {ticker} ({res['window']['start']} ~ {res['window']['end']}, n={res['window']['rows']}) ===")
        sym = res["symmetric_garch"]
        asym = res["gjr_garch"]
        lr = res["likelihood_ratio_test"]
        print(f"  symmetric GARCH(1,1):  alpha={sym['params']['alpha']:.4f} beta={sym['params']['beta']:.4f} "
              f"persistence={sym['persistence']:.4f} logL={sym['log_likelihood']:.2f}")
        print(f"  GJR-GARCH(1,1):        alpha={asym['params']['alpha']:.4f} gamma={asym['params']['gamma']:.4f} "
              f"beta={asym['params']['beta']:.4f} persistence={asym['persistence']:.4f} logL={asym['log_likelihood']:.2f}")
        print(f"  LR test on gamma=0:    LR={lr['statistic']:.3f} p={lr['p_value']:.4f} "
              f"significant_5pct={lr['significant_at_5pct']}")


if __name__ == "__main__":
    main()
