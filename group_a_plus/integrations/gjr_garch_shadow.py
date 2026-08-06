"""GJR-GARCH asymmetry shadow diagnostic for GroupA+.

The 2026-08-01 review of arXiv:2607.16450v1 found a statistically significant
GJR leverage term for 00631L.TW in-sample, but the rolling out-of-sample QLIKE
test did not justify replacing the existing symmetric GARCH proxy. This module
therefore exposes the asymmetric model only as a daily shadow feature:
model-disagreement evidence for human review, never a target-weight input.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize

DEFAULT_TICKER = "00631L.TW"
DEFAULT_LOOKBACK_CALENDAR_DAYS = 1300
DEFAULT_TRAIN_OBS = 756
MIN_OBS = 252
DISAGREEMENT_RATIO_THRESHOLD = 1.15


def _load_returns(db_path: Path, ticker: str, start: str, end: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.Series(dtype=float, name=ticker)
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    prices = rows.set_index("dt")["close"].astype(float).sort_index()
    return prices.pct_change().dropna().rename(ticker)


def _neg_log_likelihood(params: np.ndarray, resid: np.ndarray, *, asymmetric: bool) -> float:
    if asymmetric:
        mu, log_omega, alpha, gamma, beta = params
    else:
        mu, log_omega, alpha, beta = params
        gamma = 0.0
    omega = float(np.exp(log_omega))
    eps = resid - mu
    var = np.empty(len(eps))
    var[0] = max(float(np.var(eps)), 1e-12)
    for idx in range(1, len(eps)):
        prev_eps = eps[idx - 1]
        neg_flag = 1.0 if prev_eps < 0.0 else 0.0
        var[idx] = omega + alpha * prev_eps**2 + gamma * neg_flag * prev_eps**2 + beta * var[idx - 1]
    var = np.clip(var, 1e-12, None)
    ll = -0.5 * np.sum(np.log(2 * np.pi * var) + (eps**2) / var)
    return -float(ll)


def _fit_garch(resid: np.ndarray, *, asymmetric: bool) -> dict[str, Any]:
    uncond_var = max(float(np.var(resid)), 1e-12)
    if asymmetric:
        x0 = np.array([0.0, np.log(uncond_var * 0.05), 0.03, 0.05, 0.85])
        bounds = [(-0.01, 0.01), (None, None), (1e-6, 0.5), (0.0, 0.5), (1e-6, 0.999)]
    else:
        x0 = np.array([0.0, np.log(uncond_var * 0.05), 0.05, 0.90])
        bounds = [(-0.01, 0.01), (None, None), (1e-6, 0.5), (1e-6, 0.999)]
    result = minimize(
        lambda params: _neg_log_likelihood(params, resid, asymmetric=asymmetric),
        x0,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 1000},
    )
    if asymmetric:
        mu, log_omega, alpha, gamma, beta = result.x
        params = {"mu": mu, "omega": np.exp(log_omega), "alpha": alpha, "gamma": gamma, "beta": beta}
        persistence = alpha + beta + gamma / 2.0
    else:
        mu, log_omega, alpha, beta = result.x
        params = {"mu": mu, "omega": np.exp(log_omega), "alpha": alpha, "beta": beta}
        persistence = alpha + beta
    return {
        "converged": bool(result.success),
        "log_likelihood": -float(result.fun),
        "params": {key: float(value) for key, value in params.items()},
        "persistence": float(persistence),
    }


def _forecast_next_variance(params: dict[str, float], prev_return: float, prev_var: float, *, asymmetric: bool) -> float:
    eps = float(prev_return) - float(params["mu"])
    gamma = float(params.get("gamma", 0.0)) if asymmetric else 0.0
    neg_flag = 1.0 if eps < 0.0 else 0.0
    value = (
        float(params["omega"])
        + float(params["alpha"]) * eps**2
        + gamma * neg_flag * eps**2
        + float(params["beta"]) * float(prev_var)
    )
    return max(float(value), 1e-12)


def compute_gjr_garch_shadow(
    db_path: Path,
    as_of_date: str | pd.Timestamp,
    *,
    ticker: str = DEFAULT_TICKER,
    lookback_calendar_days: int = DEFAULT_LOOKBACK_CALENDAR_DAYS,
    train_obs: int = DEFAULT_TRAIN_OBS,
    disagreement_ratio_threshold: float = DISAGREEMENT_RATIO_THRESHOLD,
) -> dict[str, Any]:
    """Return a daily GJR-vs-symmetric volatility-model disagreement snapshot.

    Shadow-only contract: callers may log or display this result, but must not
    feed it into target weights, target shares, execution_regime, or automated
    promotion gates without a separate OOS promotion study.
    """
    as_of = pd.Timestamp(as_of_date).normalize()
    start = (as_of - pd.Timedelta(days=lookback_calendar_days)).strftime("%Y-%m-%d")
    end = as_of.strftime("%Y-%m-%d")
    try:
        returns = _load_returns(db_path, ticker, start, end)
        if len(returns) < MIN_OBS:
            return {"status": "unavailable", "reason": "insufficient_return_history", "rows": int(len(returns))}
        train = returns.tail(train_obs)
        resid = train.to_numpy(dtype=float)
        sym = _fit_garch(resid, asymmetric=False)
        gjr = _fit_garch(resid, asymmetric=True)
        lr_stat = max(2.0 * (gjr["log_likelihood"] - sym["log_likelihood"]), 0.0)
        p_value = float(stats.chi2.sf(lr_stat, df=1))
        prev_var = max(float(np.var(resid)), 1e-12)
        latest_return = float(train.iloc[-1])
        sym_var = _forecast_next_variance(sym["params"], latest_return, prev_var, asymmetric=False)
        gjr_var = _forecast_next_variance(gjr["params"], latest_return, prev_var, asymmetric=True)
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": str(exc)}

    ratio = gjr_var / sym_var if sym_var > 0 else float("nan")
    abs_log_ratio = abs(float(np.log(ratio))) if ratio > 0 else float("inf")
    disagreement = bool(ratio >= disagreement_ratio_threshold or ratio <= 1.0 / disagreement_ratio_threshold)
    negative_shock = latest_return < 0.0
    asymmetry_shock = bool(negative_shock and ratio >= disagreement_ratio_threshold)
    evidence_level = "weak" if asymmetry_shock else ("watch" if disagreement else "none")

    return {
        "status": "available",
        "policy": "shadow_only_no_weight_change",
        "active_allocation_impact": "none",
        "date": str(returns.index[-1].date()),
        "ticker": ticker,
        "window": {
            "start": str(train.index.min().date()),
            "end": str(train.index.max().date()),
            "rows": int(len(train)),
        },
        "research_context": {
            "source": "arXiv:2607.16450v1 review 2026-08-01",
            "in_sample_asymmetry": "significant_for_00631l",
            "oos_forecast_gate": "failed_high_vol_days_dm_test",
            "production_boundary": "diagnostic_only_no_target_weight_or_gate_input",
        },
        "symmetric_garch": sym,
        "gjr_garch": gjr,
        "likelihood_ratio_test": {
            "statistic": float(lr_stat),
            "p_value": p_value,
            "significant_at_5pct": bool(p_value < 0.05),
        },
        "latest_return": latest_return,
        "symmetric_forecast_variance": float(sym_var),
        "gjr_forecast_variance": float(gjr_var),
        "forecast_variance_ratio_gjr_over_symmetric": float(ratio),
        "forecast_disagreement_abs_log_ratio": float(abs_log_ratio),
        "vol_model_disagreement": disagreement,
        "gjr_asymmetry_shock": asymmetry_shock,
        "evidence_level": evidence_level,
        "decision_boundary": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "promotion_gate_input_allowed": False,
            "risk_mechanism_trigger_allowed": False,
        },
    }


def append_gjr_garch_shadow_log(log_path: Path, shadow: dict[str, Any]) -> None:
    if shadow.get("status") != "available":
        return
    row = {
        "date": shadow.get("date"),
        "ticker": shadow.get("ticker"),
        "evidence_level": shadow.get("evidence_level"),
        "vol_model_disagreement": shadow.get("vol_model_disagreement"),
        "gjr_asymmetry_shock": shadow.get("gjr_asymmetry_shock"),
        "forecast_variance_ratio_gjr_over_symmetric": shadow.get("forecast_variance_ratio_gjr_over_symmetric"),
        "latest_return": shadow.get("latest_return"),
        "gamma": ((shadow.get("gjr_garch") or {}).get("params") or {}).get("gamma"),
        "lr_p_value": (shadow.get("likelihood_ratio_test") or {}).get("p_value"),
        "policy": shadow.get("policy"),
    }
    rows: list[dict[str, Any]] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if existing.get("date") != row["date"]:
                rows.append(existing)
    rows.append(row)
    rows.sort(key=lambda item: str(item.get("date") or ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows) + "\n", encoding="utf-8")
