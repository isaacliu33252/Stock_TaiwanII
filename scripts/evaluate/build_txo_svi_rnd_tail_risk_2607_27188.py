#!/usr/bin/env python3
"""arXiv:2607.27188 (Shikhman, Galarnyk, Dash, Welsh -- "Inverse Learning of
Latent Risk-Neutral Densities from Irregular Option Quotes") applicability
test for GroupA+, per the user's own proposed angle: TAIEX has no 00631L/
00632R options market (confirmed 2026-08-23), but TXO (the liquid, already-
fetched TAIEX index options market) could be used to extract a market-
implied risk-neutral density (RND) and derive a tail-risk metric usable as
a risk-off regime-trigger input, without needing options positions.

This paper is a CS/ML systems paper comparing deep-learning RND estimators
(DeepONet, FNO, quote transformer, set decoder) against classical baselines
(per-expiry lognormal mixture, SVI, BL extraction) on both a synthetic
(known ground truth) benchmark and a real NIFTY options benchmark. Its own
headline real-data finding: "per-expiry mixture and SVI fits remain much
more accurate" than the learned operators on 524 held-out NIFTY calls,
despite the learned operators showing narrow advantages on the SYNTHETIC
benchmark. The paper's own evidence therefore argues AGAINST adopting its
fancier architectures for a live production feature and FOR the classical
approach (SVI fit + Breeden-Litzenberger extraction) it uses as its own
strongest real-data baseline -- consistent with this session's own repeated
finding elsewhere (e.g. project_2607_29220_ivs_diffusion_arbitrage_
refinement_closed_20260816) that complex ML approaches lose to simple
baselines on this codebase's own low-data-volume problems.

METHOD: for each trading day, using the nearest TXO monthly expiry with
15-35 calendar days to maturity (aligned to NCF's own h20 horizon), fits a
raw SVI (Gatheral) 5-parameter smile w(k) = a + b*(rho*(k-m) + sqrt((k-m)^2
+ sigma^2)) to Black-76 implied vols computed from OTM TXO quotes (puts for
K<F, calls for K>=F, the standard liquidity-favoring convention), using the
TX futures settlement price for that same expiry as the forward F. Extracts
the risk-neutral density via numerical Breeden-Litzenberger (second
difference of Black-76 call prices priced off the fitted SVI curve on a
fine strike grid), then computes the risk-neutral probability of a >10%
decline in the underlying by that expiry as the daily tail-risk metric.

TXO data already exists in FinRL/data/stock_data.db (taifex_options_daily,
2020-01-02 to present, already fetched by taifex_options_data.py for
production PCR/OI features) -- reused unmodified, no new data fetch needed
for this specific script beyond what's already in the DB. TX futures data
(taifex_futures_daily) supplies forward prices.

Research-only diagnostic. Does not touch any production strategy code.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
RISK_FREE_ANNUAL = 0.012
MIN_DTE_DAYS = 12
MAX_DTE_DAYS = 40
TARGET_DTE_DAYS = 20


def _black76_call(F: float, K: float, T: float, r: float, sigma: float) -> float:
    if sigma <= 1e-6 or T <= 0:
        return max(F - K, 0.0) * np.exp(-r * T)
    d1 = (np.log(F / K) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return np.exp(-r * T) * (F * norm.cdf(d1) - K * norm.cdf(d2))


def _black76_put(F: float, K: float, T: float, r: float, sigma: float) -> float:
    call = _black76_call(F, K, T, r, sigma)
    return call - np.exp(-r * T) * (F - K)


def _implied_vol(price: float, F: float, K: float, T: float, r: float, is_call: bool) -> float | None:
    intrinsic = max(F - K, 0.0) if is_call else max(K - F, 0.0)
    intrinsic *= np.exp(-r * T)
    if price <= intrinsic + 1e-9:
        return None
    lo, hi = 1e-4, 5.0
    price_fn = _black76_call if is_call else _black76_put
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        model_price = price_fn(F, K, T, r, mid)
        if model_price > price:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-5:
            break
    iv = 0.5 * (lo + hi)
    if iv <= 1e-3 or iv >= 4.9:
        return None
    return float(iv)


def _svi_total_variance(params: np.ndarray, k: np.ndarray) -> np.ndarray:
    a, b, rho, m, sigma = params
    return a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sigma**2))


def _fit_svi(k: np.ndarray, w_obs: np.ndarray, weights: np.ndarray) -> np.ndarray | None:
    if len(k) < 6:
        return None
    a0 = max(np.median(w_obs) * 0.5, 1e-4)
    b0 = 0.1
    x0 = np.array([a0, b0, 0.0, 0.0, 0.1])

    def loss(params):
        a, b, rho, m, sigma = params
        if b < 0 or abs(rho) >= 1 or sigma <= 0:
            return 1e6
        w_model = _svi_total_variance(params, k)
        if np.any(w_model < 0):
            return 1e6
        return float(np.sum(weights * (w_model - w_obs) ** 2))

    result = minimize(loss, x0, method="Nelder-Mead", options={"maxiter": 2000, "xatol": 1e-8, "fatol": 1e-10})
    if not result.success and result.fun > 1e5:
        return None
    return result.x


def _rnd_tail_prob(svi_params: np.ndarray, F: float, T: float, r: float, decline_pct: float = 0.10) -> dict[str, float] | None:
    K_grid = np.linspace(F * 0.5, F * 1.5, 401)
    k_grid = np.log(K_grid / F)
    w_grid = _svi_total_variance(svi_params, k_grid)
    if np.any(w_grid <= 0):
        return None
    sigma_grid = np.sqrt(w_grid / T)
    call_prices = np.array([_black76_call(F, K, T, r, s) for K, s in zip(K_grid, sigma_grid)])
    dK = K_grid[1] - K_grid[0]
    d2C = np.gradient(np.gradient(call_prices, dK), dK)
    q = np.exp(r * T) * d2C
    q = np.clip(q, 0.0, None)
    mass = np.trapezoid(q, K_grid)
    if mass <= 1e-6:
        return None
    q_norm = q / mass
    threshold = F * (1 - decline_pct)
    tail_prob = float(np.trapezoid(q_norm[K_grid <= threshold], K_grid[K_grid <= threshold]))
    mean_ST = float(np.trapezoid(K_grid * q_norm, K_grid))
    var_ST = float(np.trapezoid((K_grid - mean_ST) ** 2 * q_norm, K_grid))
    return {
        "tail_prob_decline_10pct": tail_prob,
        "rnd_mean": mean_ST,
        "rnd_std": float(np.sqrt(max(var_ST, 0.0))),
        "rnd_mass_check": float(mass),
    }


def build_daily_series(db_path: Path, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        opt = con.execute(
            """
            SELECT dt, contract_month, strike_price, call_put, close, settlement_price, volume, open_interest,
                   best_bid, best_ask
            FROM taifex_options_daily
            WHERE contract = 'TXO' AND trading_session = '一般' AND dt BETWEEN ? AND ?
            """,
            [start, end],
        ).fetchdf()
        fut = con.execute(
            """
            SELECT dt, contract_month, settlement_price, last
            FROM taifex_futures_daily
            WHERE contract = 'TX' AND trading_session = '一般' AND dt BETWEEN ? AND ?
              AND contract_month NOT LIKE '%/%'
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()

    opt["dt"] = pd.to_datetime(opt["dt"])
    fut["dt"] = pd.to_datetime(fut["dt"])
    opt["mid"] = np.where(
        (opt["best_bid"] > 0) & (opt["best_ask"] > 0),
        (opt["best_bid"] + opt["best_ask"]) / 2,
        np.where(opt["settlement_price"] > 0, opt["settlement_price"], opt["close"]),
    )
    opt = opt[opt["mid"] > 0]

    records = []
    dates = sorted(opt["dt"].unique())
    for i, dt in enumerate(dates):
        day_opt = opt[opt["dt"] == dt]
        day_fut = fut[fut["dt"] == dt]
        if day_fut.empty:
            continue
        candidate_months = day_fut["contract_month"].unique()
        best_month = None
        best_dte = None
        for month_str in candidate_months:
            try:
                expiry_approx = pd.Timestamp(f"{month_str[:4]}-{month_str[4:6]}-15") + pd.offsets.Week(weekday=2, n=3)
            except Exception:
                continue
            dte = (expiry_approx - dt).days
            if MIN_DTE_DAYS <= dte <= MAX_DTE_DAYS:
                if best_dte is None or abs(dte - TARGET_DTE_DAYS) < abs(best_dte - TARGET_DTE_DAYS):
                    best_month, best_dte = month_str, dte
        if best_month is None:
            continue

        F_row = day_fut[day_fut["contract_month"] == best_month]
        F = float(F_row["settlement_price"].iloc[0]) if F_row["settlement_price"].iloc[0] > 0 else float(F_row["last"].iloc[0])
        if F <= 0:
            continue
        T = best_dte / 365.0
        r = RISK_FREE_ANNUAL

        month_opt = day_opt[day_opt["contract_month"] == best_month]
        ks, ws, wts = [], [], []
        for _, row in month_opt.iterrows():
            K = float(row["strike_price"])
            is_call = row["call_put"] == "買權"
            is_otm = (is_call and K >= F) or (not is_call and K < F)
            if not is_otm:
                continue
            iv = _implied_vol(float(row["mid"]), F, K, T, r, is_call)
            if iv is None:
                continue
            weight = 1.0 + np.log1p(float(row["open_interest"]) + float(row["volume"]))
            ks.append(np.log(K / F))
            ws.append(iv**2 * T)
            wts.append(weight)

        if len(ks) < 6:
            continue
        svi = _fit_svi(np.array(ks), np.array(ws), np.array(wts))
        if svi is None:
            continue
        rnd = _rnd_tail_prob(svi, F, T, r)
        if rnd is None:
            continue

        records.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "expiry_month": best_month,
                "dte_days": best_dte,
                "forward": F,
                "n_quotes": len(ks),
                **{f"svi_{name}": val for name, val in zip(["a", "b", "rho", "m", "sigma"], svi)},
                **rnd,
            }
        )
        if (i + 1) % 100 == 0:
            print(f"  ...processed {i + 1}/{len(dates)} days ({dt.date()})")

    return pd.DataFrame(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2026-08-19")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "results" / "txo_svi_rnd_tail_risk_2607_27188.csv"))
    args = parser.parse_args()

    df = build_daily_series(Path(args.db), args.start, args.end)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"\nBuilt {len(df)} daily RND observations")
    print(f"Saved: {output}")
    if len(df):
        print(df[["tail_prob_decline_10pct", "dte_days", "n_quotes"]].describe())


if __name__ == "__main__":
    main()
