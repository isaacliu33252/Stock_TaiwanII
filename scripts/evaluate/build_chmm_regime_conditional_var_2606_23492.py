#!/usr/bin/env python3
"""arXiv:2606.23492 follow-up, testing the paper's own DISTINCT core claim
(not the regime-detection-trigger angle already tested and closed_negative
in build_chmm_regime_detector_2606_23492.py): a heavy-tailed continuous
HMM's regime-conditional Value-at-Risk, built by averaging the
one-step-ahead predictive density over the model's own filtered latent-
state posterior, passes standard VaR backtests (Kupiec unconditional
coverage, Christoffersen independence and joint conditional coverage) on
real daily equity data.

The paper's own result is on SPY (US). This script independently
replicates the construction on Group A+'s actual traded instruments --
0050.TW (the unleveraged benchmark the existing switch_ma80_dd11 rule is
built on) and 00631L.TW (the leveraged ETF Group A+ actually holds
exposure to, whose own volatility dynamics differ from a simple leveraged
scaling of 0050) -- and compares the regime-conditional VaR against a
simple unconditional rolling-quantile historical VaR baseline, to see
whether the CHMM machinery adds anything Group A+ doesn't already get from
a much simpler estimator.

CAUSALITY: reuses the exact same causal, no-look-ahead construction as
build_chmm_regime_detector_2606_23492.py (quarterly expanding-window
refit, forward-only filtering with fixed post-refit parameters, VaR at day
t built from information through day t and tested against day t+1's
realized return -- a genuine one-step-ahead backtest, matching the paper's
own Table 3 design).

Research-only. Reuses _fit_chmm_t / _logpdf_t from
build_chmm_regime_detector_2606_23492.py unmodified. No production code
touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import chi2, t as student_t

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_chmm_regime_detector_2606_23492 import (  # noqa: E402
    K, REFIT_EVERY, MIN_WINDOW, _fit_chmm_t, _logpdf_t,
)

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
ALPHAS = (0.05, 0.01)
HIST_VAR_WINDOW = 252  # trailing window for the unconditional historical-VaR baseline


def _forward_filter_full(x: np.ndarray, params: dict) -> np.ndarray:
    Kk = len(params["mu"])
    logB = np.stack([_logpdf_t(x, params["mu"][k], params["sigma"][k], params["nu"]) for k in range(Kk)], axis=1)
    log_trans = np.log(params["trans"] + 1e-300)
    T = len(x)
    log_alpha = np.zeros((T, Kk))
    log_alpha[0] = np.log(params["pi"] + 1e-300) + logB[0]
    for t in range(1, T):
        m = log_alpha[t - 1][:, None] + log_trans
        log_alpha[t] = np.logaddexp.reduce(m, axis=0) + logB[t]
    log_alpha -= np.logaddexp.reduce(log_alpha, axis=1, keepdims=True)
    return np.exp(log_alpha)


def _mixture_cdf(x_val: float, weights: np.ndarray, mu: np.ndarray, sigma: np.ndarray, nu: float) -> float:
    return float(sum(w * student_t.cdf((x_val - m) / s, df=nu) for w, m, s in zip(weights, mu, sigma)))


def _mixture_var(alpha_level: float, weights: np.ndarray, mu: np.ndarray, sigma: np.ndarray, nu: float) -> float:
    lo, hi = mu.min() - 15 * sigma.max(), mu.max() + 15 * sigma.max()
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _mixture_cdf(mid, weights, mu, sigma, nu) < alpha_level:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def build_causal_var_series(close: pd.Series) -> pd.DataFrame:
    logret = np.log(close / close.shift(1)).dropna()
    dates = logret.index
    x_all = logret.values
    T = len(x_all)

    var_records = {a: np.full(T, np.nan) for a in ALPHAS}
    params = None
    next_refit_idx = MIN_WINDOW

    idx = 0
    while idx < T:
        if params is None or idx >= next_refit_idx:
            fit_end = idx
            if fit_end < MIN_WINDOW:
                idx += 1
                continue
            params = _fit_chmm_t(x_all[:fit_end], K=K)
            next_refit_idx = fit_end + REFIT_EVERY
        seg_end = min(next_refit_idx, T)
        seg = x_all[:seg_end]
        alpha_full = _forward_filter_full(seg, params)  # T_seg x K, filtered P(state_t | obs up to t)
        pred = alpha_full @ params["trans"]  # one-step-ahead predictive state distribution for t+1
        for t in range(idx, seg_end):
            w = pred[t]
            for a in ALPHAS:
                var_records[a][t] = _mixture_var(a, w, params["mu"], params["sigma"], params["nu"])
        idx = seg_end

    out = pd.DataFrame({f"var_{int(a*100)}pct": var_records[a] for a in ALPHAS}, index=dates)
    out["logret"] = x_all
    out["fwd_logret"] = out["logret"].shift(-1)  # VaR at t is tested against t+1's realized return
    return out.dropna()


def hist_var_baseline(close: pd.Series) -> pd.DataFrame:
    logret = np.log(close / close.shift(1)).dropna()
    out = {}
    for a in ALPHAS:
        out[f"hist_var_{int(a*100)}pct"] = logret.rolling(HIST_VAR_WINDOW).quantile(a)
    df = pd.DataFrame(out, index=logret.index)
    df["fwd_logret"] = logret.shift(-1)
    return df.dropna()


def kupiec_test(breaches: np.ndarray, alpha: float) -> tuple[float, float]:
    n = len(breaches)
    x = int(breaches.sum())
    pi_hat = x / n
    if pi_hat in (0.0, 1.0):
        return np.nan, np.nan
    ll_null = x * np.log(alpha) + (n - x) * np.log(1 - alpha)
    ll_alt = x * np.log(pi_hat) + (n - x) * np.log(1 - pi_hat)
    lr = -2 * (ll_null - ll_alt)
    p = 1 - chi2.cdf(lr, df=1)
    return lr, p


def christoffersen_ind_test(breaches: np.ndarray) -> tuple[float, float]:
    b = breaches.astype(int)
    n00 = np.sum((b[:-1] == 0) & (b[1:] == 0))
    n01 = np.sum((b[:-1] == 0) & (b[1:] == 1))
    n10 = np.sum((b[:-1] == 1) & (b[1:] == 0))
    n11 = np.sum((b[:-1] == 1) & (b[1:] == 1))
    pi01 = n01 / (n00 + n01) if (n00 + n01) > 0 else 0
    pi11 = n11 / (n10 + n11) if (n10 + n11) > 0 else 0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)
    def _ll(p, k, m):
        if p in (0.0, 1.0):
            return 0.0
        return k * np.log(p) + m * np.log(1 - p)
    ll_null = _ll(pi, n01 + n11, n00 + n10)
    ll_alt = _ll(pi01, n01, n00) + _ll(pi11, n11, n10)
    lr = -2 * (ll_null - ll_alt)
    p = 1 - chi2.cdf(lr, df=1)
    return lr, p


def backtest_var(df: pd.DataFrame, var_col: str, alpha: float) -> dict:
    breaches = (df["fwd_logret"].values < df[var_col].values)
    lr_uc, p_uc = kupiec_test(breaches, alpha)
    lr_ind, p_ind = christoffersen_ind_test(breaches)
    lr_cc = lr_uc + lr_ind if not (np.isnan(lr_uc) or np.isnan(lr_ind)) else np.nan
    p_cc = 1 - chi2.cdf(lr_cc, df=2) if not np.isnan(lr_cc) else np.nan
    return {
        "n": len(breaches), "breaches": int(breaches.sum()), "breach_rate": float(breaches.mean()),
        "lr_uc": lr_uc, "p_uc": p_uc, "lr_ind": lr_ind, "p_ind": p_ind, "lr_cc": lr_cc, "p_cc": p_cc,
    }


def run_ticker(con: duckdb.DuckDBPyConnection, ticker: str) -> None:
    print(f"\n{'='*70}\n{ticker}\n{'='*70}")
    close = con.execute("select dt, close from ohlcv where ticker=? order by dt", [ticker]).fetchdf()
    close["dt"] = pd.to_datetime(close["dt"])
    close = close.set_index("dt")["close"].sort_index()

    chmm_df = build_causal_var_series(close)
    hist_df = hist_var_baseline(close)
    common_idx = chmm_df.index.intersection(hist_df.index)
    common_idx = common_idx[common_idx >= pd.Timestamp("2020-01-02")]
    chmm_df = chmm_df.loc[common_idx]
    hist_df = hist_df.loc[common_idx]
    print(f"backtest window: {common_idx.min().date()} to {common_idx.max().date()}, n={len(common_idx)}")

    for a in ALPHAS:
        print(f"\n--- alpha={a} (nominal breach rate {a*100:.0f}%) ---")
        r_chmm = backtest_var(chmm_df, f"var_{int(a*100)}pct", a)
        r_hist = backtest_var(hist_df, f"hist_var_{int(a*100)}pct", a)
        for name, r in [("CHMM regime-conditional VaR", r_chmm), ("unconditional historical VaR (252d)", r_hist)]:
            print(f"  {name:38s} breaches={r['breaches']:3d}/{r['n']}  rate={r['breach_rate']*100:5.2f}%  "
                  f"Kupiec p={r['p_uc']:.3f}  Christoffersen-ind p={r['p_ind']:.3f}  joint-cc p={r['p_cc']:.3f}")

        med_chmm = chmm_df[f"var_{int(a*100)}pct"].median()
        med_hist = hist_df[f"hist_var_{int(a*100)}pct"].median()
        print(f"  median VaR: CHMM={med_chmm*100:.2f}%  historical={med_hist*100:.2f}%")

    out_path = PROJECT_ROOT / "results" / f"chmm_regime_conditional_var_2606_23492_{ticker.replace('.', '_')}.csv"
    chmm_df.to_csv(out_path, encoding="utf-8-sig")
    print(f"\nSaved: {out_path}")


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    for ticker in ("0050.TW", "00631L.TW"):
        run_ticker(con, ticker)


if __name__ == "__main__":
    main()
