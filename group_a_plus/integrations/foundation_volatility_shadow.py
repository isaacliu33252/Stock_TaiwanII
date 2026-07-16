"""Model-agnostic realized-volatility shadow forecast schema.

This module is the first integration step for foundation time-series volatility
models such as TimesFM. It deliberately starts with HAR-RV context variants so
the GroupA+ pipeline can validate schema, evaluation, and downstream policy
hooks before any heavyweight model dependency is introduced.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from group_a_plus.integrations.volatility_forecast import (
    HORIZONS,
    garman_klass_variance,
    har_rv_walkforward_forecast,
)


DEFAULT_CONTEXT_LENGTHS = (64, 128, 512)
FOUNDATION_VOL_SCHEMA_VERSION = 1


def _safe_percentile(series: pd.Series, window: int = 252, min_periods: int = 60) -> pd.Series:
    rolling = series.rolling(window, min_periods=min_periods)
    return rolling.rank(pct=True).fillna(0.5)


def build_foundation_vol_shadow_frame(
    ohlc: pd.DataFrame,
    *,
    context_lengths: tuple[int, ...] = DEFAULT_CONTEXT_LENGTHS,
    horizons: tuple[int, ...] = HORIZONS,
    refit_every: int = 21,
) -> pd.DataFrame:
    """Build a TimesFM-ready shadow forecast panel using HAR-RV context proxies.

    Each context length is represented by a HAR-RV rolling training window. The
    column names intentionally use `model_context_horizon` terms, so a future
    TimesFM implementation can be compared by replacing only the producer.
    """

    gk_variance = garman_klass_variance(ohlc)
    out = pd.DataFrame(index=ohlc.index)
    out["realized_variance_gk"] = gk_variance

    forecast_cols: list[str] = []
    for context in context_lengths:
        min_train_rows = max(30, min(130, int(context)))
        rolling_window = max(int(context), min_train_rows)
        for horizon in horizons:
            col = f"har_rv_ctx{context}_h{horizon}_variance"
            forecast = har_rv_walkforward_forecast(
                gk_variance,
                horizon=int(horizon),
                min_train_rows=min_train_rows,
                refit_every=refit_every,
                rolling_window=rolling_window,
            )
            out[col] = forecast
            out[f"{col}_percentile_252d"] = _safe_percentile(forecast)
            forecast_cols.append(col)

    for horizon in horizons:
        cols = [f"har_rv_ctx{context}_h{horizon}_variance" for context in context_lengths]
        ensemble = out[cols].mean(axis=1, skipna=True)
        dispersion = out[cols].std(axis=1, skipna=True)
        out[f"ensemble_h{horizon}_variance"] = ensemble
        out[f"ensemble_h{horizon}_percentile_252d"] = _safe_percentile(ensemble)
        out[f"ensemble_h{horizon}_dispersion"] = dispersion.fillna(0.0)
        out[f"ensemble_h{horizon}_uncertainty_ratio"] = (
            dispersion / ensemble.replace(0.0, np.nan)
        ).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    return out


def latest_foundation_vol_snapshot(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "schema_version": FOUNDATION_VOL_SCHEMA_VERSION,
            "status": "unavailable",
            "reason": "empty_frame",
        }

    row = frame.iloc[-1]
    horizons = sorted(
        int(col.removeprefix("ensemble_h").removesuffix("_variance"))
        for col in frame.columns
        if col.startswith("ensemble_h") and col.endswith("_variance")
    )
    return {
        "schema_version": FOUNDATION_VOL_SCHEMA_VERSION,
        "status": "available",
        "model_family": "har_rv_context_shadow",
        "horizons": {
            str(horizon): {
                "forecast_variance": float(row.get(f"ensemble_h{horizon}_variance", float("nan"))),
                "percentile_252d": float(row.get(f"ensemble_h{horizon}_percentile_252d", float("nan"))),
                "dispersion": float(row.get(f"ensemble_h{horizon}_dispersion", float("nan"))),
                "uncertainty_ratio": float(row.get(f"ensemble_h{horizon}_uncertainty_ratio", float("nan"))),
            }
            for horizon in horizons
        },
    }


def recovery_quality_from_snapshot(
    snapshot: dict[str, Any],
    *,
    horizon: int = 10,
    max_percentile: float = 0.65,
    max_uncertainty_ratio: float = 0.50,
) -> dict[str, Any]:
    """Translate a volatility snapshot into a conservative recovery-boost gate."""

    if snapshot.get("status") != "available":
        return {"allow_recovery_boost": False, "reason": "snapshot_unavailable"}
    entry = (snapshot.get("horizons") or {}).get(str(horizon))
    if not isinstance(entry, dict):
        return {"allow_recovery_boost": False, "reason": "horizon_unavailable", "horizon": horizon}

    percentile = float(entry.get("percentile_252d", float("nan")))
    uncertainty = float(entry.get("uncertainty_ratio", float("nan")))
    allow = bool(percentile <= float(max_percentile) and uncertainty <= float(max_uncertainty_ratio))
    return {
        "allow_recovery_boost": allow,
        "horizon": int(horizon),
        "percentile_252d": percentile,
        "uncertainty_ratio": uncertainty,
        "max_percentile": float(max_percentile),
        "max_uncertainty_ratio": float(max_uncertainty_ratio),
        "reason": "forecast_vol_quality_ok" if allow else "forecast_vol_quality_blocked",
    }
