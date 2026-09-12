#!/usr/bin/env python3
"""Out-of-sample volatility forecast quality: does GJR-GARCH's asymmetric
leverage term actually produce better next-day variance forecasts for
00631L.TW than the existing symmetric GARCH(1,1) proxy used in
backtest_group_a_plus_financial_econometrics.py::_garch_proxy_vol?

Follow-up to scripts/misc/gjr_garch_asymmetry_test.py (2026-08-01), which
only established an in-sample LR test (00631L gamma p<0.0001). That's a
statement about fit, not forecast usefulness -- a model can fit better
in-sample and still not forecast better OOS. This answers the actual
question this project's discipline requires before wiring anything into
production: does the extra parameter earn its keep out of sample?

Method: expanding-window refit every ~63 trading days (~1 quarter) on both
symmetric GARCH(1,1) and GJR-GARCH(1,1), Gaussian QMLE via scipy.optimize
(same hand-rolled fitter as the prior script -- no `arch` package
installed). Between refits, both models generate proper recursive
one-step-ahead variance forecasts using realized returns up to each day
(not a static multi-step forecast). Forecast loss evaluated against
squared demeaned returns (standard proxy absent intraday realized vol)
using two losses: MSE and QLIKE (log(sigma2) + r2/sigma2 -- the
Patton-2011-preferred loss for variance forecast comparison, robust to
noise in the realized-vol proxy and penalizes under-prediction more,
which is exactly what matters for tail risk). Significance via a paired
sign test and t-test on the daily loss differential (GJR minus symmetric
-- negative means GJR wins).

Read-only research. Does not modify garch_regime_shadow.py,
backtest_group_a_plus_financial_econometrics.py, or any production file.
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
from group_a_plus.integrations.risk_sensitive_loss import diebold_mariano_test  # noqa: E402

TICKER = "00631L.TW"
START = "2014-10-23"
END = "2026-08-12"
INITIAL_TRAIN_DAYS = 500
REFIT_EVERY_DAYS = 63


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
        _neg_log_likelihood, x0, args=(resid, asymmetric),
        method="L-BFGS-B", bounds=bounds, options={"maxiter": 2000},
    )
    if asymmetric:
        mu, log_omega, alpha, gamma, beta = result.x
        params = {"mu": mu, "omega": float(np.exp(log_omega)), "alpha": alpha, "gamma": gamma, "beta": beta}
    else:
        mu, log_omega, alpha, beta = result.x
        params = {"mu": mu, "omega": float(np.exp(log_omega)), "alpha": alpha, "beta": beta}
    return {"converged": bool(result.success), "params": {k: float(v) for k, v in params.items()}}


def _forecast_path(all_resid: np.ndarray, params: dict[str, float], asymmetric: bool, seed_var: float) -> np.ndarray:
    """Recursive one-step-ahead variance forecasts over the FULL series
    given fixed params, seeded with seed_var at t=0. Returns var[t] = the
    forecast MADE AT t-1 FOR day t (i.e. var[t] uses only resid[0..t-1])."""
    n = len(all_resid)
    eps = all_resid - params["mu"]
    var = np.empty(n)
    var[0] = seed_var
    gamma = params.get("gamma", 0.0)
    for t in range(1, n):
        prev_eps = eps[t - 1]
        neg_flag = 1.0 if prev_eps < 0.0 else 0.0
        var[t] = params["omega"] + params["alpha"] * prev_eps**2 + gamma * neg_flag * prev_eps**2 + params["beta"] * var[t - 1]
    return np.clip(var, 1e-12, None)


def _qlike(sigma2: np.ndarray, r2: np.ndarray) -> np.ndarray:
    return np.log(sigma2) + r2 / sigma2


def run_spec(
    resid_full: np.ndarray,
    dates: pd.DatetimeIndex,
    *,
    initial_train_days: int = INITIAL_TRAIN_DAYS,
    refit_every_days: int = REFIT_EVERY_DAYS,
) -> dict[str, Any]:
    """Run one (train_window, refit_every) specification end to end and
    return the overall + tail DM-test results. Factored out of main() so a
    robustness sweep can call this across a grid of specifications without
    duplicating the fitting/forecasting logic."""
    n = len(resid_full)
    sym_var_forecast = np.full(n, np.nan)
    gjr_var_forecast = np.full(n, np.nan)
    refit_dates: list[str] = []

    refit_points = list(range(initial_train_days, n, refit_every_days))
    total = len(refit_points)
    for i, cut in enumerate(refit_points):
        train = resid_full[:cut]
        sym_fit = _fit(train, asymmetric=False)
        gjr_fit = _fit(train, asymmetric=True)
        next_cut = refit_points[i + 1] if i + 1 < len(refit_points) else n
        seed_var = float(np.var(train[-63:]))
        # forecast over [cut, next_cut) using params estimated on data < cut,
        # recursively using realized resid up to each forecast day (no leakage:
        # var[t] forecast only ever uses resid[0..t-1], and params only ever
        # estimated on resid[0..cut-1] with cut <= t)
        window_resid = resid_full[:next_cut]
        sym_path = _forecast_path(window_resid, sym_fit["params"], False, seed_var)
        gjr_path = _forecast_path(window_resid, gjr_fit["params"], True, seed_var)
        sym_var_forecast[cut:next_cut] = sym_path[cut:next_cut]
        gjr_var_forecast[cut:next_cut] = gjr_path[cut:next_cut]
        refit_dates.append(str(dates[cut].date()))
        pct = (i + 1) / total
        print(f"[{i+1}/{total} ({pct:.0%})] refit at {dates[cut].date()}, "
              f"sym(a={sym_fit['params']['alpha']:.3f},b={sym_fit['params']['beta']:.3f}) "
              f"gjr(a={gjr_fit['params']['alpha']:.3f},g={gjr_fit['params']['gamma']:.3f},b={gjr_fit['params']['beta']:.3f})",
              flush=True)

    valid = ~np.isnan(sym_var_forecast)
    r2 = (resid_full - np.nanmean(resid_full)) ** 2
    r2_v, sym_v, gjr_v, dates_v = r2[valid], sym_var_forecast[valid], gjr_var_forecast[valid], dates[valid]

    sym_mse = (sym_v - r2_v) ** 2
    gjr_mse = (gjr_v - r2_v) ** 2
    sym_qlike = _qlike(sym_v, r2_v)
    gjr_qlike = _qlike(gjr_v, r2_v)

    mse_diff = gjr_mse - sym_mse  # negative = GJR better
    qlike_diff = gjr_qlike - sym_qlike

    mse_t = stats.ttest_1samp(mse_diff, 0.0)
    qlike_t = stats.ttest_1samp(qlike_diff, 0.0)
    mse_sign = stats.binomtest((mse_diff < 0).sum(), len(mse_diff), 0.5)
    qlike_sign = stats.binomtest((qlike_diff < 0).sum(), len(qlike_diff), 0.5)

    # Proper Diebold-Mariano (HAC-corrected, Harvey-Leybourne-Newbold small-
    # sample correction) via the same tested helper the 2026-08-01 predecessor
    # analysis used (results/gjr_garch_oos_forecast_quality_00631l_20260801.json)
    # -- the naive t-test/sign-test above assume i.i.d. loss differentials,
    # which GARCH forecast losses are not (volatility clustering induces serial
    # correlation), so those two overstate significance. h=1 for a one-step-
    # ahead forecast (no overlapping-window correction needed).
    qlike_dm = diebold_mariano_test(pd.Series(gjr_qlike), pd.Series(sym_qlike), h=1)
    mse_dm = diebold_mariano_test(pd.Series(gjr_mse), pd.Series(sym_mse), h=1)

    # crash-day subset: worst 5% of realized r2 days (tail-risk-relevant subset)
    tail_cut = np.quantile(r2_v, 0.95)
    tail_mask = r2_v >= tail_cut
    sym_qlike_tail = sym_qlike[tail_mask].mean()
    gjr_qlike_tail = gjr_qlike[tail_mask].mean()
    sym_mse_tail = sym_mse[tail_mask].mean()
    gjr_mse_tail = gjr_mse[tail_mask].mean()
    # were forecasts under-predicting on tail days (var forecast < realized r2)?
    sym_underpred_frac_tail = float((sym_v[tail_mask] < r2_v[tail_mask]).mean())
    gjr_underpred_frac_tail = float((gjr_v[tail_mask] < r2_v[tail_mask]).mean())
    qlike_dm_tail = diebold_mariano_test(pd.Series(gjr_qlike[tail_mask]), pd.Series(sym_qlike[tail_mask]), h=1)

    result = {
        "ticker": TICKER,
        "oos_window": {"start": str(dates_v[0].date()), "end": str(dates_v[-1].date()), "n": int(valid.sum())},
        "n_refits": total,
        "refit_dates": refit_dates,
        "overall": {
            "mse_symmetric_mean": float(sym_mse.mean()),
            "mse_gjr_mean": float(gjr_mse.mean()),
            "mse_diff_gjr_minus_sym": float(mse_diff.mean()),
            "mse_ttest_p": float(mse_t.pvalue),
            "mse_sign_test_gjr_win_frac": float((mse_diff < 0).mean()),
            "mse_sign_test_p": float(mse_sign.pvalue),
            "qlike_symmetric_mean": float(sym_qlike.mean()),
            "qlike_gjr_mean": float(gjr_qlike.mean()),
            "qlike_diff_gjr_minus_sym": float(qlike_diff.mean()),
            "qlike_ttest_p": float(qlike_t.pvalue),
            "qlike_sign_test_gjr_win_frac": float((qlike_diff < 0).mean()),
            "qlike_sign_test_p": float(qlike_sign.pvalue),
            "qlike_diebold_mariano": qlike_dm,
            "mse_diebold_mariano": mse_dm,
        },
        "tail_5pct_worst_realized_days": {
            "n_days": int(tail_mask.sum()),
            "mse_symmetric_mean": float(sym_mse_tail),
            "mse_gjr_mean": float(gjr_mse_tail),
            "qlike_symmetric_mean": float(sym_qlike_tail),
            "qlike_gjr_mean": float(gjr_qlike_tail),
            "underpred_frac_symmetric": sym_underpred_frac_tail,
            "underpred_frac_gjr": gjr_underpred_frac_tail,
            "qlike_diebold_mariano": qlike_dm_tail,
        },
    }
    return result


def main() -> None:
    returns = _load_returns(TICKER, START, END)
    resid_full = returns.to_numpy(dtype=float)
    dates = returns.index
    print(f"{TICKER}: {len(resid_full)} obs, {dates[0].date()} .. {dates[-1].date()}", flush=True)
    result = run_spec(resid_full, dates)
    out_path = PROJECT_ROOT / "results" / "gjr_garch_oos_forecast_quality_00631l.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nSaved: {out_path}", flush=True)
    print(json.dumps(result["overall"], indent=2), flush=True)
    print(json.dumps(result["tail_5pct_worst_realized_days"], indent=2), flush=True)


if __name__ == "__main__":
    main()
