#!/usr/bin/env python3
"""Split-session dynamic correlation shadow test for Group A+ (arXiv:2607.03669).

The paper (Chen, Hansen & Tong, "Split-Session Cluster GARCH for Overnight
and Intraday Returns") argues that overnight and intraday return components
have materially different tail heaviness, and that pooling them under a
single tail parameter distorts dynamic multivariate correlation estimation.
Its own empirical application is NOT about predicting forward returns from
overnight/intraday event combinations (that was tested separately, see
GROUP_A_PLUS_20260819_2607_03669_OVERNIGHT_INTRADAY_SESSION_SPLIT_HANDOFF.md,
and was a null result on a different question). This script tests the
paper's actual mechanism: does splitting overnight/intraday and allowing
session-specific tail heaviness improve (a) out-of-sample fit and (b)
downstream GMV-portfolio risk, for Group A+'s real traded universe (0050,
00631L, 00632R, 00679B)?

Pipeline
--------
1. Load OHLCV, retroactively fix 3 known unadjusted corporate-action price
   breaks (0050 2014-01-02 1:4 split, 00631L 2015-01-05 ~1:22 reverse
   merger, 00632R 2024-12-02 ~1:7 reverse merger -- see memory
   project_2608_00127_drawdown_bootstrap_calibration_20260816; that prior
   fix only patched a derived analysis curve, not this raw table, so it is
   re-applied here), and compute overnight/intraday log returns.
2. Stage 1: fit a univariate EGARCH(1,1)-t model per asset per session (8
   fits) via direct MLE -> standardized innovations Z^N_t, Z^D_t. This
   drops the paper's cross-session mean/volatility spillover terms
   (Section 2) for tractability -- a deliberate scope simplification, not
   an oversight.
3. Stage 2: fit a corrected-DCC (cDCC, Aielli 2013) dynamic correlation on
   the common overlap window, in three variants exactly matching the
   paper's own DCC benchmark (Section 6, Table 5 Panel A): Gaussian /
   pooled multivariate-t (G=1, one shared nu across both sessions) /
   session Cluster-t (G=2, session-specific nu, block-diagonal
   C_t^ND=0 as the paper's own diagnostics justify). This uses the paper's
   DCC-t benchmark engine, not its more complex score-driven matrix-log GAS
   estimator (Sections 3-5), which needs materially more numerical
   infrastructure than is justified before knowing whether the core
   session/tail-heterogeneity mechanism helps at all for only 4 assets.
4. Out-of-sample (train <= 2024-12-31, test 2025-01-01 onward, n=394 days):
   compare log-likelihood and GMV-portfolio realized variance, mirroring
   the paper's Table 5 / Table 8 evaluation, plus a paired significance
   check on the daily log-likelihood gap and a bootstrap CI on the GMV
   squared-return gap (the project's standard gate, since raw aggregate
   deltas alone have repeatedly been misleading in prior sessions here).

Research-only. Does not modify any production runner, signal, or execution
plan. All I/O is confined to --output.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize
from scipy.special import gammaln

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
KNOWN_BREAKS = {
    "0050.TW": pd.Timestamp("2014-01-02"),
    "00631L.TW": pd.Timestamp("2015-01-05"),
    "00632R.TW": pd.Timestamp("2024-12-02"),
}
TRAIN_END = pd.Timestamp("2024-12-31")


# ---------------------------------------------------------------- data prep
def load_session_returns(ticker: str) -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute(
        f"select dt, open, close from ohlcv where ticker='{ticker}' order by dt"
    ).fetchdf()
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.sort_values("dt").reset_index(drop=True)
    df = df[(df["open"] > 0) & (df["close"] > 0)].reset_index(drop=True)

    if ticker in KNOWN_BREAKS:
        brk = KNOWN_BREAKS[ticker]
        idx = df.index[df["dt"] == brk]
        if len(idx):
            i = idx[0]
            ratio = df.loc[i, "open"] / df.loc[i - 1, "close"]
            for col in ["open", "close"]:
                df.loc[: i - 1, col] = df.loc[: i - 1, col] * ratio

    df["prev_close"] = df["close"].shift(1)
    df["overnight_ret"] = np.log(df["open"] / df["prev_close"])
    df["intraday_ret"] = np.log(df["close"] / df["open"])
    df = df.dropna(subset=["overnight_ret", "intraday_ret"]).reset_index(drop=True)
    return df[["dt", "overnight_ret", "intraday_ret"]]


# ------------------------------------------------------- stage 1: EGARCH-t
def _egarch_t_negloglik(params, r):
    mu, omega, beta_raw, tau1, tau2, log_nu_m2 = params
    nu = 2.0 + np.exp(log_nu_m2)
    beta = np.tanh(beta_raw)
    T = len(r)
    e = r - mu
    log_h = np.empty(T)
    log_h[0] = omega / max(1e-6, (1 - beta))
    z = np.empty(T)
    z[0] = e[0] / np.exp(0.5 * log_h[0])
    for t in range(1, T):
        log_h[t] = omega + beta * log_h[t - 1] + tau1 * z[t - 1] + tau2 * (
            np.abs(z[t - 1]) - np.sqrt(2 / np.pi)
        )
        z[t] = e[t] / np.exp(0.5 * log_h[t])
    c = gammaln((nu + 1) / 2) - gammaln(nu / 2) - 0.5 * np.log((nu - 2) * np.pi)
    ll = c - 0.5 * log_h - (nu + 1) / 2 * np.log(1 + z ** 2 / (nu - 2))
    if not np.all(np.isfinite(ll)):
        return 1e10
    return -np.sum(ll)


def fit_egarch_t(r: np.ndarray) -> dict:
    x0 = np.array([r.mean(), 0.0, np.arctanh(0.9), -0.05, 0.1, np.log(8.0)])
    res = minimize(_egarch_t_negloglik, x0, args=(r,), method="Nelder-Mead",
                    options={"maxiter": 4000, "xatol": 1e-6, "fatol": 1e-6})
    mu, omega, beta_raw, tau1, tau2, log_nu_m2 = res.x
    beta = np.tanh(beta_raw)
    nu = 2.0 + np.exp(log_nu_m2)

    T = len(r)
    e = r - mu
    log_h = np.empty(T)
    log_h[0] = omega / max(1e-6, (1 - beta))
    z = np.empty(T)
    z[0] = e[0] / np.exp(0.5 * log_h[0])
    for t in range(1, T):
        log_h[t] = omega + beta * log_h[t - 1] + tau1 * z[t - 1] + tau2 * (
            np.abs(z[t - 1]) - np.sqrt(2 / np.pi)
        )
        z[t] = e[t] / np.exp(0.5 * log_h[t])
    return {"mu": float(mu), "omega": float(omega), "beta": float(beta),
            "tau1": float(tau1), "tau2": float(tau2), "nu": float(nu),
            "z": z, "loglik": float(-res.fun), "converged": bool(res.success)}


# ------------------------------------------------------------- stage 2: DCC
def dcc_Q_path(Z: np.ndarray, alpha: float, beta: float) -> np.ndarray:
    """Corrected DCC (cDCC-style) Q_t recursion. Z: (T,n) standardized resid."""
    T, n = Z.shape
    Qbar = np.corrcoef(Z, rowvar=False)
    Q = np.empty((T, n, n))
    Q[0] = Qbar
    for t in range(1, T):
        zz = np.outer(Z[t - 1], Z[t - 1])
        Q[t] = (1 - alpha - beta) * Qbar + beta * Q[t - 1] + alpha * zz
    return Q


def Q_to_C(Q: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.diagonal(Q, axis1=-2, axis2=-1))
    dinv = 1.0 / d
    return Q * dinv[..., :, None] * dinv[..., None, :]


def mvt_loglik_blockdiag(Zn, Zd, Cn, Cd, nu):
    T, n = Zn.shape
    m = 2 * n
    ll = np.empty(T)
    c = gammaln((nu + m) / 2) - gammaln(nu / 2) - (m / 2) * np.log((nu - 2) * np.pi)
    for t in range(T):
        try:
            sign_n, logdet_n = np.linalg.slogdet(Cn[t])
            sign_d, logdet_d = np.linalg.slogdet(Cd[t])
            if sign_n <= 0 or sign_d <= 0:
                ll[t] = -1e6
                continue
            q = Zn[t] @ np.linalg.inv(Cn[t]) @ Zn[t] + Zd[t] @ np.linalg.inv(Cd[t]) @ Zd[t]
            ll[t] = c - 0.5 * (logdet_n + logdet_d) - (nu + m) / 2 * np.log(1 + q / (nu - 2))
        except np.linalg.LinAlgError:
            ll[t] = -1e6
    return ll


def mvt_loglik_single(Z, C, nu):
    T, n = Z.shape
    ll = np.empty(T)
    c = gammaln((nu + n) / 2) - gammaln(nu / 2) - (n / 2) * np.log((nu - 2) * np.pi)
    for t in range(T):
        try:
            sign, logdet = np.linalg.slogdet(C[t])
            if sign <= 0:
                ll[t] = -1e6
                continue
            q = Z[t] @ np.linalg.inv(C[t]) @ Z[t]
            ll[t] = c - 0.5 * logdet - (nu + n) / 2 * np.log(1 + q / (nu - 2))
        except np.linalg.LinAlgError:
            ll[t] = -1e6
    return ll


def gauss_loglik_single(Z, C):
    T, n = Z.shape
    ll = np.empty(T)
    c = -(n / 2) * np.log(2 * np.pi)
    for t in range(T):
        try:
            sign, logdet = np.linalg.slogdet(C[t])
            if sign <= 0:
                ll[t] = -1e6
                continue
            q = Z[t] @ np.linalg.inv(C[t]) @ Z[t]
            ll[t] = c - 0.5 * logdet - 0.5 * q
        except np.linalg.LinAlgError:
            ll[t] = -1e6
    return ll


def _sigmoid_ab(a_raw, b_raw, alpha_max=0.25):
    alpha = alpha_max / (1 + np.exp(-a_raw))
    beta = (0.999 - alpha) / (1 + np.exp(-b_raw))
    return alpha, beta


def fit_dcc_single_t(Z: np.ndarray, dist: str) -> dict:
    def negloglik(theta):
        alpha, beta = _sigmoid_ab(theta[0], theta[1])
        C = Q_to_C(dcc_Q_path(Z, alpha, beta))
        if dist == "gaussian":
            ll = gauss_loglik_single(Z, C)
        else:
            nu = 2.0 + np.exp(theta[2])
            ll = mvt_loglik_single(Z, C, nu)
        return -np.sum(ll)

    x0 = [0.0, 0.0] if dist == "gaussian" else [0.0, 0.0, np.log(8.0)]
    res = minimize(negloglik, x0, method="Nelder-Mead",
                    options={"maxiter": 3000, "xatol": 1e-6, "fatol": 1e-6})
    alpha, beta = _sigmoid_ab(res.x[0], res.x[1])
    nu = float(2.0 + np.exp(res.x[2])) if dist == "t" else None
    return {"alpha": float(alpha), "beta": float(beta), "nu": nu, "loglik": float(-res.fun)}


def fit_dcc_pooled_t(Zn: np.ndarray, Zd: np.ndarray) -> dict:
    def negloglik(theta):
        alphaN, betaN = _sigmoid_ab(theta[0], theta[1])
        alphaD, betaD = _sigmoid_ab(theta[2], theta[3])
        nu = 2.0 + np.exp(theta[4])
        Cn = Q_to_C(dcc_Q_path(Zn, alphaN, betaN))
        Cd = Q_to_C(dcc_Q_path(Zd, alphaD, betaD))
        return -np.sum(mvt_loglik_blockdiag(Zn, Zd, Cn, Cd, nu))

    x0 = [0.0, 0.0, 0.0, 0.0, np.log(8.0)]
    res = minimize(negloglik, x0, method="Nelder-Mead",
                    options={"maxiter": 4000, "xatol": 1e-6, "fatol": 1e-6})
    alphaN, betaN = _sigmoid_ab(res.x[0], res.x[1])
    alphaD, betaD = _sigmoid_ab(res.x[2], res.x[3])
    nu = float(2.0 + np.exp(res.x[4]))
    return {"alphaN": float(alphaN), "betaN": float(betaN), "alphaD": float(alphaD),
            "betaD": float(betaD), "nu": nu, "loglik": float(-res.fun)}


def fit_dcc_pooled_gaussian(Zn: np.ndarray, Zd: np.ndarray) -> dict:
    def negloglik(theta):
        alphaN, betaN = _sigmoid_ab(theta[0], theta[1])
        alphaD, betaD = _sigmoid_ab(theta[2], theta[3])
        Cn = Q_to_C(dcc_Q_path(Zn, alphaN, betaN))
        Cd = Q_to_C(dcc_Q_path(Zd, alphaD, betaD))
        return -np.sum(gauss_loglik_single(Zn, Cn) + gauss_loglik_single(Zd, Cd))

    x0 = [0.0, 0.0, 0.0, 0.0]
    res = minimize(negloglik, x0, method="Nelder-Mead",
                    options={"maxiter": 3000, "xatol": 1e-6, "fatol": 1e-6})
    alphaN, betaN = _sigmoid_ab(res.x[0], res.x[1])
    alphaD, betaD = _sigmoid_ab(res.x[2], res.x[3])
    return {"alphaN": float(alphaN), "betaN": float(betaN), "alphaD": float(alphaD),
            "betaD": float(betaD), "loglik": float(-res.fun)}


# ------------------------------------------------------------- GMV weights
def gmv_test_returns(Cn: np.ndarray, Cd: np.ndarray, Zn: np.ndarray, Zd: np.ndarray,
                      test_mask: np.ndarray) -> np.ndarray:
    out = []
    for t in np.where(test_mask)[0]:
        Cb = np.zeros((8, 8))
        Cb[:4, :4] = Cn[t]
        Cb[4:, 4:] = Cd[t]
        try:
            Cinv = np.linalg.inv(Cb)
        except np.linalg.LinAlgError:
            continue
        ones = np.ones(8)
        w = Cinv @ ones / (ones @ Cinv @ ones)
        z = np.concatenate([Zn[t], Zd[t]])
        out.append(w @ z)
    return np.array(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(
        PROJECT_ROOT / "results" / "2607_03669_split_session_dcc_shadow.json"))
    args = parser.parse_args()

    data = {tk: load_session_returns(tk) for tk in TICKERS}

    stage1 = {}
    for tk in TICKERS:
        for sess in ["overnight_ret", "intraday_ret"]:
            stage1[f"{tk}|{sess}"] = fit_egarch_t(data[tk][sess].values)

    date_sets = [set(data[tk]["dt"]) for tk in TICKERS]
    common_dates = pd.DatetimeIndex(sorted(set.intersection(*date_sets)))

    Zn = np.zeros((len(common_dates), 4))
    Zd = np.zeros((len(common_dates), 4))
    for j, tk in enumerate(TICKERS):
        idx = data[tk].set_index("dt")
        Zn[:, j] = pd.Series(stage1[f"{tk}|overnight_ret"]["z"], index=idx.index).reindex(common_dates).values
        Zd[:, j] = pd.Series(stage1[f"{tk}|intraday_ret"]["z"], index=idx.index).reindex(common_dates).values

    train_mask = np.asarray(common_dates <= TRAIN_END)
    test_mask = ~train_mask
    Zn_tr, Zd_tr = Zn[train_mask], Zd[train_mask]

    fit_gauss = fit_dcc_pooled_gaussian(Zn_tr, Zd_tr)
    fit_mvt = fit_dcc_pooled_t(Zn_tr, Zd_tr)
    fit_cn = fit_dcc_single_t(Zn_tr, dist="t")
    fit_cd = fit_dcc_single_t(Zd_tr, dist="t")

    Cn_g = Q_to_C(dcc_Q_path(Zn, fit_gauss["alphaN"], fit_gauss["betaN"]))
    Cd_g = Q_to_C(dcc_Q_path(Zd, fit_gauss["alphaD"], fit_gauss["betaD"]))
    ll_g = gauss_loglik_single(Zn, Cn_g) + gauss_loglik_single(Zd, Cd_g)

    Cn_m = Q_to_C(dcc_Q_path(Zn, fit_mvt["alphaN"], fit_mvt["betaN"]))
    Cd_m = Q_to_C(dcc_Q_path(Zd, fit_mvt["alphaD"], fit_mvt["betaD"]))
    ll_m = mvt_loglik_blockdiag(Zn, Zd, Cn_m, Cd_m, fit_mvt["nu"])

    Cn_c = Q_to_C(dcc_Q_path(Zn, fit_cn["alpha"], fit_cn["beta"]))
    Cd_c = Q_to_C(dcc_Q_path(Zd, fit_cd["alpha"], fit_cd["beta"]))
    ll_c = mvt_loglik_single(Zn, Cn_c, fit_cn["nu"]) + mvt_loglik_single(Zd, Cd_c, fit_cd["nu"])

    d_ll = ll_c[test_mask] - ll_m[test_mask]
    t_stat, p_val = stats.ttest_1samp(d_ll, 0)
    sign_favor_cluster = int((d_ll > 0).sum())

    r_mvt = gmv_test_returns(Cn_m, Cd_m, Zn, Zd, test_mask)
    r_cluster = gmv_test_returns(Cn_c, Cd_c, Zn, Zd, test_mask)
    r_gauss = gmv_test_returns(Cn_g, Cd_g, Zn, Zd, test_mask)

    rng = np.random.default_rng(0)
    sq_diff = r_cluster ** 2 - r_mvt ** 2
    boot = np.array([rng.choice(sq_diff, size=len(sq_diff), replace=True).mean() for _ in range(5000)])

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "common_window": {"start": str(common_dates.min().date()), "end": str(common_dates.max().date()),
                           "n_days": int(len(common_dates)), "n_train": int(train_mask.sum()),
                           "n_test": int(test_mask.sum())},
        "stage1_egarch": {k: {kk: vv for kk, vv in v.items() if kk != "z"} for k, v in stage1.items()},
        "stage2_dcc_fits": {
            "gaussian": fit_gauss, "multivariate_t_g1": fit_mvt,
            "cluster_t_g2_night": fit_cn, "cluster_t_g2_day": fit_cd,
        },
        "oos_loglik": {
            "gaussian": float(ll_g[test_mask].sum()),
            "multivariate_t_g1": float(ll_m[test_mask].sum()),
            "cluster_t_g2": float(ll_c[test_mask].sum()),
        },
        "oos_gmv_realized_variance": {
            "gaussian": float(np.var(r_gauss)),
            "multivariate_t_g1": float(np.var(r_mvt)),
            "cluster_t_g2": float(np.var(r_cluster)),
        },
        "significance": {
            "daily_loglik_diff_cluster_minus_mvt": {
                "mean": float(d_ll.mean()), "t_stat": float(t_stat), "p_value": float(p_val),
                "n_days_favoring_cluster_t": sign_favor_cluster, "n_test_days": int(test_mask.sum()),
            },
            "gmv_sq_return_diff_cluster_minus_mvt": {
                "mean": float(sq_diff.mean()),
                "bootstrap_90pct_ci": [float(np.percentile(boot, 5)), float(np.percentile(boot, 95))],
            },
        },
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps({k: out[k] for k in ["oos_loglik", "oos_gmv_realized_variance", "significance"]}, indent=2))


if __name__ == "__main__":
    main()
