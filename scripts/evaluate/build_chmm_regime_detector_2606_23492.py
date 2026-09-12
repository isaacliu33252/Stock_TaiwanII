#!/usr/bin/env python3
"""arXiv:2606.23492 (Alswaidan, Jin, Varner -- "Continuous Hidden Markov
Models for Equity Returns: Heavy-Tail Emission Families and
Regime-Conditional Value-at-Risk") applicability test for Group A+, per the
user's specific proposed angle: a continuous HMM with a heavy-tailed
(Student-t) emission family separates temporal dependence (the latent regime
chain) from the marginal distribution (per-regime location/scale/shape), and
could plausibly replace or outperform Group A+'s existing rule-based
switch_risk_ma80_dd11_total6_hold5_eg015_xg015 trigger (an 80-day MA-gap +
80-day drawdown + composite risk-score rule) for classifying golden1
(offense) vs defensive regimes on 0050.

METHOD: fits a K=2-state Student-t continuous HMM on 0050.TW daily log
returns via EM (Baum-Welch for T/pi, ECM-style weighted location/scale
update for the shared-nu Student-t emission, matching the paper's own
"shared-nu" ablation -- Table S9 of the paper found this to be the cleanest
single-row heavy-tail fit in its own panel, so reusing it here is not an
arbitrary simplification). CAUSALITY: the model is refit only on an
expanding window through the end of each quarter (63 trading days, matching
the paper's own periodic-refit recommendation for live use), and the
regime classification for days within the following quarter uses ONLY a
forward (filtered, not smoothed) recursion with those already-fixed
parameters -- no future data enters any day's regime call. The realized
state-dependent regime call is further lagged by one trading day before
being applied to portfolio composition (decide on day t's close, act on day
t+1), matching this project's established look-ahead-bug guard
(feedback_lookahead_bug_same_day_signal_decision).

Reuses golden1_0531_1m and group_a_plus_defensive_1m from the existing
switch-backtest curve CSV as the two legs to blend under the CHMM regime
call, exactly as backtest_group_a_plus_switch_policy.py blends them under
its own rule-based regime call -- so the comparison isolates the regime
classifier, not the underlying offense/defense legs.

Research-only. Does not touch any production runner, signal, or execution
plan.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import t as student_t
from scipy.optimize import minimize_scalar

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
SWITCH_CURVE = PROJECT_ROOT / "results" / "whatif_four_axis_switch_backtest_20260819_curve.csv"
SWITCH_COL = "switch_risk_ma80_dd11_total6_hold5_eg015_xg015"
GOLDEN_COL = "golden1_0531_1m"
DEFENSIVE_COL = "group_a_plus_defensive_1m"

K = 2
REFIT_EVERY = 63  # trading days, quarterly, matching the paper's own periodic-refit recommendation
MIN_WINDOW = 252  # need at least one year before the first fit
MIN_HOLD_DAYS = 5  # matches the compared rule's min_hold_days
NU_GRID = (3.0, 5.0, 8.0, 15.0, 30.0)


def _logpdf_t(x: np.ndarray, mu: float, sigma: float, nu: float) -> np.ndarray:
    sigma = max(sigma, 1e-8)
    return student_t.logpdf((x - mu) / sigma, df=nu) - np.log(sigma)


def _fit_chmm_t(x: np.ndarray, K: int = 2, max_iter: int = 60, tol: float = 1e-4) -> dict:
    T = len(x)
    order = np.argsort(x)
    chunks = np.array_split(order, K)
    mu = np.array([x[c].mean() for c in chunks])
    sigma = np.array([max(x[c].std(), 1e-4) for c in chunks])
    order_idx = np.argsort(mu)
    mu, sigma = mu[order_idx], sigma[order_idx]
    trans = np.full((K, K), 1.0 / K)
    pi = np.full(K, 1.0 / K)
    nu = 8.0

    prev_ll = -np.inf
    for _ in range(max_iter):
        logB = np.stack([_logpdf_t(x, mu[k], sigma[k], nu) for k in range(K)], axis=1)  # T x K

        log_alpha = np.zeros((T, K))
        log_alpha[0] = np.log(pi + 1e-300) + logB[0]
        log_trans = np.log(trans + 1e-300)
        for t in range(1, T):
            m = log_alpha[t - 1][:, None] + log_trans
            log_alpha[t] = np.logaddexp.reduce(m, axis=0) + logB[t]
        ll = np.logaddexp.reduce(log_alpha[-1])

        log_beta = np.zeros((T, K))
        for t in range(T - 2, -1, -1):
            m = log_trans + (logB[t + 1] + log_beta[t + 1])[None, :]
            log_beta[t] = np.logaddexp.reduce(m, axis=1)

        log_gamma = log_alpha + log_beta
        log_gamma -= np.logaddexp.reduce(log_gamma, axis=1, keepdims=True)
        gamma = np.exp(log_gamma)

        xi_sum = np.zeros((K, K))
        for t in range(T - 1):
            m = (log_alpha[t][:, None] + log_trans + logB[t + 1][None, :] + log_beta[t + 1][None, :])
            m -= np.logaddexp.reduce(m.ravel())
            xi_sum += np.exp(m)

        pi = gamma[0] / gamma[0].sum()
        trans = xi_sum / xi_sum.sum(axis=1, keepdims=True)

        u = np.stack([(nu + 1.0) / (nu + ((x - mu[k]) / sigma[k]) ** 2) for k in range(K)], axis=1)
        for k in range(K):
            w = gamma[:, k] * u[:, k]
            mu[k] = (w * x).sum() / w.sum()
            sigma[k] = np.sqrt((gamma[:, k] * u[:, k] * (x - mu[k]) ** 2).sum() / gamma[:, k].sum())
            sigma[k] = max(sigma[k], 1e-4)

        best_nu, best_ll = nu, -np.inf
        for cand in NU_GRID:
            cand_ll = sum(np.sum(gamma[:, k] * _logpdf_t(x, mu[k], sigma[k], cand)) for k in range(K))
            if cand_ll > best_ll:
                best_ll, best_nu = cand_ll, cand
        nu = best_nu

        order_idx = np.argsort(mu)
        mu, sigma = mu[order_idx], sigma[order_idx]
        trans = trans[order_idx][:, order_idx]
        pi = pi[order_idx]

        if abs(ll - prev_ll) < tol:
            break
        prev_ll = ll

    return {"pi": pi, "trans": trans, "mu": mu, "sigma": sigma, "nu": nu}


def _forward_filter_causal(x: np.ndarray, params: dict) -> np.ndarray:
    """Returns P(state=bear | obs up to and including each t), forward-only, no smoothing."""
    K = len(params["mu"])
    logB = np.stack([_logpdf_t(x, params["mu"][k], params["sigma"][k], params["nu"]) for k in range(K)], axis=1)
    log_trans = np.log(params["trans"] + 1e-300)
    T = len(x)
    log_alpha = np.zeros((T, K))
    log_alpha[0] = np.log(params["pi"] + 1e-300) + logB[0]
    for t in range(1, T):
        m = log_alpha[t - 1][:, None] + log_trans
        log_alpha[t] = np.logaddexp.reduce(m, axis=0) + logB[t]
    log_alpha -= np.logaddexp.reduce(log_alpha, axis=1, keepdims=True)
    alpha = np.exp(log_alpha)
    bear_state = int(np.argmax(params["sigma"]))  # higher-sigma state = high-vol / bear regime
    return alpha[:, bear_state]


def build_causal_regime_series(close: pd.Series) -> pd.Series:
    logret = np.log(close / close.shift(1)).dropna()
    dates = logret.index
    x_all = logret.values

    p_bear = pd.Series(index=dates, dtype=float)
    params = None
    next_refit_idx = MIN_WINDOW

    idx = 0
    while idx < len(x_all):
        if params is None or idx >= next_refit_idx:
            fit_end = idx  # expanding window through the day before the current segment (causal)
            if fit_end < MIN_WINDOW:
                idx += 1
                continue
            params = _fit_chmm_t(x_all[:fit_end], K=K)
            next_refit_idx = fit_end + REFIT_EVERY
        seg_end = min(next_refit_idx, len(x_all))
        seg = x_all[:seg_end]  # forward filter recomputed from window start each segment; only in-segment causal
        filt = _forward_filter_causal(seg, params)
        p_bear.iloc[idx:seg_end] = filt[idx:seg_end]
        idx = seg_end

    return p_bear.dropna()


def apply_min_hold(is_defensive_raw: pd.Series, min_hold: int) -> pd.Series:
    state = False
    hold_left = 0
    out = []
    for flag in is_defensive_raw:
        if hold_left > 0:
            hold_left -= 1
        else:
            if flag != state:
                state = flag
                hold_left = min_hold - 1
        out.append(state)
    return pd.Series(out, index=is_defensive_raw.index)


def perf_stats(r: np.ndarray) -> dict:
    ann_ret = r.mean() * 252
    ann_vol = r.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
    cum = np.exp(np.cumsum(np.log1p(r)))
    mdd = (cum / np.maximum.accumulate(cum) - 1).min()
    return {"ann_ret": float(ann_ret), "ann_vol": float(ann_vol), "sharpe": float(sharpe), "mdd": float(mdd)}


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    close = con.execute(
        "select dt, close from ohlcv where ticker='0050.TW' order by dt"
    ).fetchdf()
    close["dt"] = pd.to_datetime(close["dt"])
    close = close.set_index("dt")["close"].sort_index()

    p_bear = build_causal_regime_series(close)
    print(f"Fitted causal CHMM regime series: {len(p_bear)} days, "
          f"mean P(bear)={p_bear.mean():.3f}, days P(bear)>0.5: {(p_bear > 0.5).sum()} "
          f"({(p_bear > 0.5).mean()*100:.1f}%)")

    is_defensive_raw = p_bear > 0.5
    is_defensive = apply_min_hold(is_defensive_raw, MIN_HOLD_DAYS)
    is_defensive_lagged = is_defensive.shift(1).fillna(False)  # decide on close(t), act on t+1

    curve = pd.read_csv(SWITCH_CURVE)
    curve["dt"] = pd.to_datetime(curve["dt"])
    curve = curve.set_index("dt").sort_index()
    golden_ret = curve[GOLDEN_COL].pct_change()
    defensive_ret = curve[DEFENSIVE_COL].pct_change()
    switch_ret = curve[SWITCH_COL].pct_change()

    df = pd.concat(
        [golden_ret.rename("golden"), defensive_ret.rename("defensive"), switch_ret.rename("switch_ma_dd"),
         is_defensive_lagged.rename("chmm_defensive")],
        axis=1,
    ).dropna()
    df["chmm_ret"] = np.where(df["chmm_defensive"], df["defensive"], df["golden"])

    print(f"\nCHMM-regime defensive-day share (lagged, post-min-hold): {df['chmm_defensive'].mean()*100:.1f}%")

    print("\n=== Full-window performance: golden1 alone vs rule-based switch vs CHMM-regime switch ===")
    for name, col in [("golden1_alone", "golden"), ("switch_ma80_dd11 (rule)", "switch_ma_dd"), ("chmm_t_regime_switch", "chmm_ret")]:
        p = perf_stats(df[col].values)
        print(f"{name:28s} ann_ret={p['ann_ret']*100:7.2f}%  ann_vol={p['ann_vol']*100:6.2f}%  "
              f"sharpe={p['sharpe']:6.3f}  mdd={p['mdd']*100:7.2f}%")

    episodes = {
        "covid_crash_2020": ("2020-01-20", "2020-03-23"),
        "bear_2022_full_year": ("2022-01-01", "2022-12-31"),
        "tariff_shock_2025_04": ("2025-04-01", "2025-04-15"),
    }
    print("\n=== Episode-level cumulative return: golden1 vs rule-switch vs CHMM-switch ===")
    for name, (s, e) in episodes.items():
        sub = df.loc[s:e]
        if sub.empty:
            continue
        cg = (1 + sub["golden"]).prod() - 1
        cs = (1 + sub["switch_ma_dd"]).prod() - 1
        cc = (1 + sub["chmm_ret"]).prod() - 1
        n_defensive_days = int(sub["chmm_defensive"].sum())
        print(f"{name:24s} golden1={cg*100:+7.2f}%  rule_switch={cs*100:+7.2f}%  "
              f"chmm_switch={cc*100:+7.2f}%  (CHMM defensive days: {n_defensive_days}/{len(sub)})")

    # Direct agreement with the rule's own regime label, using the recommended_regime CSV if available
    regime_csv = PROJECT_ROOT / "results" / "whatif_four_axis_switch_backtest_20260819_recommended_regime.csv"
    if regime_csv.exists():
        reg = pd.read_csv(regime_csv, usecols=["dt", "regime"])
        reg["dt"] = pd.to_datetime(reg["dt"])
        reg = reg.set_index("dt")["regime"]
        rule_defensive = (reg == "defensive").reindex(df.index).fillna(False)
        agreement = (df["chmm_defensive"] == rule_defensive).mean()
        both_defensive = (df["chmm_defensive"] & rule_defensive).sum()
        chmm_only = (df["chmm_defensive"] & ~rule_defensive).sum()
        rule_only = (~df["chmm_defensive"] & rule_defensive).sum()
        print(f"\n=== Agreement with rule-based regime label ===")
        print(f"day-by-day agreement: {agreement*100:.1f}%  "
              f"both_defensive={both_defensive}  chmm_only_defensive={chmm_only}  rule_only_defensive={rule_only}")

    out_path = PROJECT_ROOT / "results" / "chmm_regime_detector_2606_23492.csv"
    df.to_csv(out_path, encoding="utf-8-sig")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
