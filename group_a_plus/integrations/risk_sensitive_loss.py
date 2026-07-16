"""Risk-sensitive loss and routing diagnostics.

These helpers are model-agnostic. They are intended for shadow evaluation of
forecast/routing systems, not for direct portfolio weight calculation.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats


def qlike_loss(
    realized_variance: pd.Series,
    forecast_variance: pd.Series,
    *,
    floor: float = 1e-12,
) -> pd.Series:
    """Quasi-likelihood loss for positive variance forecasts."""
    y = pd.to_numeric(realized_variance, errors="coerce").clip(lower=floor)
    yhat = pd.to_numeric(forecast_variance, errors="coerce").clip(lower=floor)
    ratio = y / yhat
    return ratio - ratio.map(lambda value: math.log(float(value))) - 1.0


def underprediction_loss(
    realized_variance: pd.Series,
    forecast_variance: pd.Series,
    *,
    floor: float = 1e-12,
) -> pd.Series:
    """Squared relative penalty when realized variance exceeds forecast."""
    y = pd.to_numeric(realized_variance, errors="coerce").clip(lower=floor)
    yhat = pd.to_numeric(forecast_variance, errors="coerce").clip(lower=floor)
    return ((y - yhat).clip(lower=0.0) / y) ** 2


def diebold_mariano_test(
    loss_a: pd.Series,
    loss_b: pd.Series,
    *,
    h: int,
) -> dict[str, Any]:
    """Harvey, Leybourne & Newbold (1997) small-sample-corrected Diebold-Mariano test.

    Tests whether the mean loss differential d_t = loss_a_t - loss_b_t is zero,
    i.e. whether model A's forecasts are significantly more/less accurate than
    model B's. Uses a Bartlett-kernel HAC variance estimator with truncation
    lag h-1, matching the autocorrelation induced by overlapping h-step-ahead
    forecast windows -- the same test (and same rationale) used by
    arXiv:2606.03828 Section 5.4 (`dm.test` in R) to decide whether GNHAR beats
    HAR rather than trusting a raw win-rate or mean-loss gap.

    A negative statistic means model A (loss_a) has lower average loss (is
    more accurate) than model B (loss_b).
    """
    d = pd.to_numeric(loss_a, errors="coerce") - pd.to_numeric(loss_b, errors="coerce")
    d = d.dropna()
    n = len(d)
    if n < max(10, 2 * h):
        return {"status": "insufficient_data", "n": n}

    d_arr = d.to_numpy(dtype=float)
    mean_d = float(d_arr.mean())
    centered = d_arr - mean_d

    max_lag = max(int(h) - 1, 0)
    gamma_0 = float(np.dot(centered, centered) / n)
    long_run_var = gamma_0
    for lag in range(1, max_lag + 1):
        weight = 1.0 - lag / (max_lag + 1)  # Bartlett kernel
        gamma_lag = float(np.dot(centered[lag:], centered[:-lag]) / n)
        long_run_var += 2.0 * weight * gamma_lag

    if long_run_var <= 0:
        return {"status": "non_positive_variance", "n": n, "mean_diff": mean_d}

    dm_stat = mean_d / math.sqrt(long_run_var / n)
    correction = math.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    corrected_stat = dm_stat * correction
    p_value = float(2.0 * scipy_stats.t.sf(abs(corrected_stat), df=n - 1))

    return {
        "status": "ok",
        "n": n,
        "horizon": int(h),
        "mean_diff": mean_d,
        "dm_statistic": dm_stat,
        "corrected_statistic": corrected_stat,
        "p_value": p_value,
        "significant_at_5pct": p_value < 0.05,
        "a_more_accurate": mean_d < 0,
    }


def risk_sensitive_loss(
    realized_variance: pd.Series,
    forecast_variance: pd.Series,
    *,
    underprediction_weight: float = 1.0,
    floor: float = 1e-12,
) -> pd.Series:
    """QLIKE plus an explicit underprediction penalty."""
    return qlike_loss(realized_variance, forecast_variance, floor=floor) + float(underprediction_weight) * underprediction_loss(
        realized_variance,
        forecast_variance,
        floor=floor,
    )


def routing_regret_frame(
    *,
    selected_route: pd.Series,
    candidate_losses: pd.DataFrame,
) -> pd.DataFrame:
    """Compute selected loss, oracle loss, regret, and miss-best flags."""
    selected_route = selected_route.astype(str).reindex(candidate_losses.index)
    selected_loss: list[float | None] = []
    best_route: list[str | None] = []
    best_loss: list[float | None] = []
    for dt, row in candidate_losses.iterrows():
        clean = pd.to_numeric(row, errors="coerce").dropna()
        if clean.empty:
            selected_loss.append(None)
            best_route.append(None)
            best_loss.append(None)
            continue
        route = selected_route.loc[dt]
        selected_loss.append(float(row.get(route)) if route in row.index and pd.notna(row.get(route)) else None)
        best = clean.idxmin()
        best_route.append(str(best))
        best_loss.append(float(clean.loc[best]))
    out = pd.DataFrame(
        {
            "selected_route": selected_route,
            "selected_loss": selected_loss,
            "best_route": best_route,
            "best_loss": best_loss,
        },
        index=candidate_losses.index,
    )
    out["selected_regret"] = pd.to_numeric(out["selected_loss"], errors="coerce") - pd.to_numeric(out["best_loss"], errors="coerce")
    out["miss_best"] = (out["selected_route"] != out["best_route"]) & out["best_route"].notna()
    return out


def summarize_routing_diagnostics(regret: pd.DataFrame) -> dict[str, Any]:
    """Summarize routing diagnostics in a stable JSON-friendly shape."""
    if regret.empty:
        return {
            "row_count": 0,
            "evaluated_count": 0,
            "miss_best_rate": None,
            "mean_selected_regret": None,
            "median_selected_regret": None,
        }
    evaluated = regret.dropna(subset=["selected_loss", "best_loss"])
    if evaluated.empty:
        return {
            "row_count": int(len(regret)),
            "evaluated_count": 0,
            "miss_best_rate": None,
            "mean_selected_regret": None,
            "median_selected_regret": None,
        }
    selected_regret = pd.to_numeric(evaluated["selected_regret"], errors="coerce").dropna()
    return {
        "row_count": int(len(regret)),
        "evaluated_count": int(len(evaluated)),
        "miss_best_rate": round(float(evaluated["miss_best"].mean()), 6),
        "mean_selected_regret": round(float(selected_regret.mean()), 8),
        "median_selected_regret": round(float(selected_regret.median()), 8),
        "selected_route_counts": evaluated["selected_route"].value_counts(dropna=False).to_dict(),
        "best_route_counts": evaluated["best_route"].value_counts(dropna=False).to_dict(),
    }
