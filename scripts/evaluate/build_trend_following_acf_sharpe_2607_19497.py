#!/usr/bin/env python3
"""arXiv:2607.19497 (Sepp & Lucic, "The Science and Practice of Trend-Following
Systems") applicability test for Group A+, per the user's specific proposed
angle: golden1/00631L's regime switch is structurally a form of trend-
following (closer to the paper's "American TF" -- binary position sized
from EWMA-filter crossovers, breakout entries, trailing-stop exits -- than
to the paper's continuous "European TF"), and the paper's closed-form
Sharpe-ratio-from-autocorrelation framework could tell us when to hold vs
exit 00631L.

METHOD: replicates the paper's own diagnostic and verification methodology
(Section 5, Corollary 5.5; Section 7.3) on Group A+'s actual instruments:

  1. Compute volatility-normalized daily returns z_t = r_t / sigma_{t-1},
     with sigma_t the EWMA volatility of returns at the paper's own span
     of 33 days (eq. 2.13).
  2. Estimate the sample autocorrelation function of z_t (the paper's own
     Assumption 4.8 / eq. 4.12 object) -- this answers the first-order
     question: does 0050/00631L exhibit the positive autocorrelation
     (trend persistence) the paper's whole framework requires for a TF
     system to be structurally profitable at zero drift?
  3. Apply the closed-form Sharpe ratio (Corollary 5.5, eq. 5.12) at a
     grid of EWMA filter spans, using the empirical ACF and the empirical
     drift -- this is the paper's own "predicted Sharpe from sample ACF
     and drift" object (Section 7.3).
  4. Build an ACTUAL single-filter European TF system per the paper's own
     Definition 4.1 (continuous EWMA-filtered, variance-preserving,
     volatility-normalized signal) on 0050/00631L, and backtest its
     REALIZED gross Sharpe ratio -- this is the paper's own in-sample
     verification methodology (does the closed form reproduce the
     realized Sharpe on this market, the way it does on the paper's 84
     futures contracts at pooled correlation 0.99).
  5. Compare the resulting span-dependent Sharpe profile against Group
     A+'s existing switch_risk_ma80_dd11 rule's own implicit lookback (80
     days), to see whether the two converge on a similar horizon.

Research-only. No production code touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
A = 260.0  # paper's annualization factor (weekday count)
VOL_SPAN = 33  # paper's own EWMA volatility span
WARMUP = 250  # paper skips this many days before using z_t
SPANS = (5, 10, 21, 63, 125, 250, 500)
MAX_LAG = 500


def ewma_vol(r: np.ndarray, span: int, sigma_floor: float = 0.001) -> np.ndarray:
    """EWMA volatility with a small floor to prevent z_t blow-up during
    stretches of zero/near-zero returns (0050 has 183 exact-zero-return
    days, mostly 2009-2013 when it traded thinly), which otherwise decay
    the EWMA variance toward zero and cause the next real return's
    volatility-normalized value to explode."""
    nu = 1 - 2 / (span + 1)
    var = np.empty_like(r)
    var[0] = max(r[0] ** 2, sigma_floor ** 2)
    for t in range(1, len(r)):
        var[t] = max((1 - nu) * r[t] ** 2 + nu * var[t - 1], sigma_floor ** 2)
    return np.sqrt(var)


def sample_acf(z: np.ndarray, max_lag: int) -> np.ndarray:
    z = z - z.mean()
    n = len(z)
    denom = np.sum(z ** 2)
    acf = np.empty(max_lag + 1)
    acf[0] = 1.0
    for m in range(1, max_lag + 1):
        acf[m] = np.sum(z[m:] * z[:-m]) / denom
    return acf


def psi_nu(acf: np.ndarray, nu: float) -> float:
    m = np.arange(1, len(acf))
    return float(np.sum(nu ** m * acf[1:]))


def predicted_sharpe(acf: np.ndarray, span: int, mu_z_an: float, a: float = A) -> float:
    nu = 1 - 2 / (span + 1)
    psi = psi_nu(acf, nu)
    A_nu = (1 - nu) / nu * psi
    B_nu = (1 - nu) / (1 + nu) * (1 + 2 * psi)
    num = np.sqrt(a) * A_nu + (mu_z_an ** 2) / np.sqrt(a)
    den = np.sqrt(B_nu + A_nu ** 2 + (mu_z_an ** 2 / a) * (1 + B_nu + 2 * A_nu))
    return float(num / den) if den > 0 else np.nan


def build_european_tf_returns(z: np.ndarray, span: int, sigma_target: float = 0.15) -> np.ndarray:
    """Definition 4.1: variance-preserving EWMA signal on z_t, position
    proportional to signal and to a volatility-target weight (held fixed
    here at 1, since the closed-form Sharpe is independent of sigma_target
    and of the filter loading l -- eq. 5.12)."""
    nu = 1 - 2 / (span + 1)
    l = np.sqrt((1 + nu) / (1 - nu))
    prefactor = sigma_target / np.sqrt(A)  # eq. 4.3: f_t = (sigma_target/sqrt(a)) * S_{t-1} * z_t
    n = len(z)
    L = 0.0  # raw EWMA filter L^(nu)
    f = np.zeros(n)
    for t in range(n):
        S_prev = l * L  # variance-preserving signal from *before* today's z_t enters
        if t > 0:
            f[t] = prefactor * S_prev * z[t]
        L = (1 - nu) * z[t] + nu * L
    return f


def perf(x: np.ndarray) -> dict:
    ann_ret = x.mean() * A
    ann_vol = x.std() * np.sqrt(A)
    return {"ann_ret": float(ann_ret), "ann_vol": float(ann_vol),
            "sharpe": float(ann_ret / ann_vol) if ann_vol > 0 else np.nan}


def run_ticker(con: duckdb.DuckDBPyConnection, ticker: str) -> None:
    print(f"\n{'='*70}\n{ticker}\n{'='*70}")
    close = con.execute("select dt, close from ohlcv where ticker=? order by dt", [ticker]).fetchdf()
    close["dt"] = pd.to_datetime(close["dt"])
    close = close.set_index("dt")["close"].sort_index()
    r = np.log(close / close.shift(1)).dropna().values
    print(f"n days = {len(r)}, date range {close.index.min().date()} to {close.index.max().date()}")

    sigma = ewma_vol(r, VOL_SPAN)
    z = r[1:] / sigma[:-1]
    z = z[WARMUP:]
    print(f"z_t: n={len(z)}, mean={z.mean():.5f}, std={z.std():.4f}")

    mu_z_an = np.sqrt(A) * z.mean()
    print(f"annualized drift mu_z_an (Sharpe of underlying, unit-var convention) = {mu_z_an:.3f}")

    max_lag = min(MAX_LAG, len(z) // 4)
    acf = sample_acf(z, max_lag)
    print(f"sample ACF of z_t: lag1={acf[1]:+.4f}  lag2={acf[2]:+.4f}  lag5={acf[5]:+.4f}  "
          f"lag10={acf[10]:+.4f}  lag21={acf[21]:+.4f}  lag63={acf[min(63,max_lag)]:+.4f}")
    # mean autocorrelation over first 20 lags, as a simple persistence gauge
    print(f"mean ACF over lags 1-20: {acf[1:21].mean():+.5f}")

    print("\n--- span | predicted Sharpe (closed-form, autocorr+drift) | realized gross Sharpe (actual EWMA TF backtest) ---")
    for span in SPANS:
        pred = predicted_sharpe(acf, span, mu_z_an)
        f_t = build_european_tf_returns(z, span)
        real = perf(f_t[1:])  # drop first day (no signal yet)
        print(f"span={span:4d}d  predicted_SR={pred:6.3f}   realized_gross_SR={real['sharpe']:6.3f}   "
              f"realized_ann_ret={real['ann_ret']*100:6.2f}%  realized_ann_vol={real['ann_vol']*100:6.2f}%")


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    for ticker in ("0050.TW", "00631L.TW"):
        run_ticker(con, ticker)


if __name__ == "__main__":
    main()
