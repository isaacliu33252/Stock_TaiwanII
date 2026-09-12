"""RG-ResMoE-style regime-gated residual correction pilot for 0050.TW HAR-RV.

Research-only pilot inspired by arXiv:2608.12251 ("Regime-Gated Residual
Mixture-of-Experts for Cross-Sectional Volatility Forecasting"). The paper's
central, and only directly-transferable, finding is an integration-pathway
result, not a trading rule: appending regime state variables directly to a
forecasting model's input degrades accuracy and destabilizes training, while
using the same regime variables only to gate a small residual correction on
top of a frozen base forecast improves accuracy and VaR calibration.

GroupA+ has no cross-sectional pool of assets to route across (the paper's
setting is 1,027 US equities); this pilot adapts the pathway comparison to
the single-instrument HAR-RV forecast already in production
(volatility_forecast.py), which is architecturally the closest analogue.

IMPORTANT PRIOR: a related regime-mixture idea for this exact forecast
(arXiv:2510.03236, regime_switching_volatility_shadow.py -- soft mixture of
regime-clustered HAR coefficient sets) was already tested and failed badly
(QLIKE ~-150% to -200% vs plain HAR-RV, see
results/group_a_plus_regime_switching_volatility_forecast_quality_latest.json).
That approach re-derives a full coefficient set per regime from small,
changepoint-segmented windows -- high variance. This pilot deliberately uses
a much more conservative architecture matched to the paper: the base
forecast is the existing frozen HAR-RV walk-forward forecast (byte-for-byte
reused, not refit), and only a small, separately-fit residual correction is
added, softly gated by a single causal regime scalar. If the gate weight is
near zero the pilot collapses back to plain HAR-RV, so it cannot be much
worse than the baseline by construction -- unlike the earlier full-remix
approach.

Three forecasts are produced per horizon, mirroring the paper's Table 4:
  - base: unmodified har_rv_walkforward_forecast (frozen, unchanged)
  - input_pathway: same HAR features plus the regime scalar appended
    directly to one walk-forward OLS regression (the "bad" pathway)
  - gate_pathway: frozen base + a ridge-regularized residual correction,
    fit on HAR features only, scaled by the regime scalar's trailing
    percentile (the paper's proposed "good" pathway)

This module only produces forecasts; it does not change any target weight.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from group_a_plus.integrations.volatility_forecast import (
    DEFAULT_REFIT_EVERY,
    DEFAULT_ROLLING_WINDOW,
    GK_FLOOR,
    HORIZONS,
    MIN_TRAIN_ROWS,
    _future_avg_variance,
    _fit_ols,
    har_features,
    har_rv_walkforward_forecast,
)

REGIME_SHORT_WINDOW = 20
REGIME_LONG_WINDOW = 120
GATE_PERCENTILE_WINDOW = 252
DEFAULT_RIDGE_LAMBDA = 4.0
LOOKBACK_CALENDAR_DAYS = 1600
DEFAULT_SHADOW_TICKERS = ("0050.TW", "00631L.TW")
H5_HIGH_VOL_GATE_QUANTILE = 0.80


def regime_scalar(gk_variance: pd.Series) -> pd.Series:
    """Causal log-ratio of recent (20d) to longer-run (120d) variance level.

    Single-instrument analogue of the paper's market-volatility state
    variable: how stressed the current regime is relative to its own
    trailing history. Uses only data up to and including t.
    """
    short = gk_variance.rolling(REGIME_SHORT_WINDOW, min_periods=REGIME_SHORT_WINDOW).mean()
    long = gk_variance.rolling(REGIME_LONG_WINDOW, min_periods=REGIME_LONG_WINDOW).mean()
    return np.log(short.clip(lower=GK_FLOOR) / long.clip(lower=GK_FLOOR)).rename("regime_scalar")


def _fit_ridge(x: np.ndarray, y: np.ndarray, *, lam: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Ridge-regularized fit in standardized feature space (intercept unpenalized)."""
    mean = x.mean(axis=0)
    std = x.std(axis=0, ddof=0)
    std[std == 0.0] = 1.0
    x_std = (x - mean) / std
    design = np.column_stack([np.ones(len(x_std)), x_std])
    penalty = np.eye(design.shape[1]) * lam
    penalty[0, 0] = 0.0
    coef = np.linalg.solve(design.T @ design + penalty, design.T @ y)
    return coef, mean, std


def _fit_ridge_weighted(
    x: np.ndarray, y: np.ndarray, weights: np.ndarray, *, lam: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sample-weighted ridge fit (soft routing): every row contributes to every
    expert, weighted by its gate proximity, instead of a hard train/test split.
    """
    mean = x.mean(axis=0)
    std = x.std(axis=0, ddof=0)
    std[std == 0.0] = 1.0
    x_std = (x - mean) / std
    design = np.column_stack([np.ones(len(x_std)), x_std])
    w = np.clip(weights, 1e-6, None)
    wd = design * w[:, None]
    penalty = np.eye(design.shape[1]) * lam
    penalty[0, 0] = 0.0
    coef = np.linalg.solve(design.T @ wd + penalty, wd.T @ y)
    return coef, mean, std


def rg_resmoe_pathways(
    gk_variance: pd.Series,
    *,
    horizon: int,
    min_train_rows: int = MIN_TRAIN_ROWS,
    refit_every: int = DEFAULT_REFIT_EVERY,
    rolling_window: int | None = DEFAULT_ROLLING_WINDOW,
    ridge_lambda: float = DEFAULT_RIDGE_LAMBDA,
) -> pd.DataFrame:
    """Walk-forward base / input-pathway / gate-pathway forecasts for one horizon."""
    features = har_features(gk_variance)
    z = regime_scalar(gk_variance)
    target = np.log(_future_avg_variance(gk_variance, horizon).clip(lower=GK_FLOOR))

    base_cols = ["log_rv_d", "log_rv_w", "log_rv_m"]
    valid_base = features[base_cols].notna().all(axis=1)
    valid_all = valid_base & z.notna()

    # Frozen base forecast: reuse the production function unmodified.
    base_forecast = har_rv_walkforward_forecast(
        gk_variance, horizon=horizon, min_train_rows=min_train_rows,
        refit_every=refit_every, rolling_window=rolling_window,
    )

    gate_weight = z.rolling(GATE_PERCENTILE_WINDOW, min_periods=60).rank(pct=True)

    out = pd.DataFrame(index=gk_variance.index)
    out[f"input_pathway_h{horizon}"] = np.nan
    out[f"gate_pathway_h{horizon}"] = np.nan
    out[f"gate_pathway_soft_h{horizon}"] = np.nan
    out[f"gate_weight_h{horizon}"] = gate_weight

    input_coef: np.ndarray | None = None
    calm_coef: np.ndarray | None = None
    calm_mean: np.ndarray | None = None
    calm_std: np.ndarray | None = None
    stress_coef: np.ndarray | None = None
    stress_mean: np.ndarray | None = None
    stress_std: np.ndarray | None = None
    soft_calm_coef: np.ndarray | None = None
    soft_calm_mean: np.ndarray | None = None
    soft_calm_std: np.ndarray | None = None
    soft_stress_coef: np.ndarray | None = None
    soft_stress_mean: np.ndarray | None = None
    soft_stress_std: np.ndarray | None = None
    last_fit_idx = -1

    for i, _dt in enumerate(gk_variance.index):
        if not bool(valid_all.iloc[i]):
            continue
        train_end = i - horizon
        if train_end < min_train_rows:
            continue

        if input_coef is None or (i - last_fit_idx) >= refit_every:
            train_start = 0 if rolling_window is None else max(0, train_end + 1 - rolling_window)
            mask = valid_all.iloc[train_start : train_end + 1] & target.iloc[train_start : train_end + 1].notna()
            train_idx = train_start + np.where(mask.to_numpy())[0]
            if len(train_idx) < min_train_rows:
                continue

            x_base = features.iloc[train_idx][base_cols].to_numpy(dtype=float)
            z_train = z.iloc[train_idx].to_numpy(dtype=float)
            y = target.iloc[train_idx].to_numpy(dtype=float)

            # Input pathway: regime scalar appended directly as a 4th regressor.
            x_input = np.column_stack([x_base, z_train])
            input_coef = _fit_ols(x_input, y)

            # Gate pathway: residual of the (unchanged) frozen base against
            # its own in-sample fit, corrected by two regime-conditioned
            # ridge experts (calm / stress split by the regime scalar's
            # in-sample median) on HAR features only -- the regime scalar
            # never enters either regression, it only sets the split and
            # scales the soft blend between the two experts below. Fitting
            # a single global residual regressor on x_base is a no-op here:
            # OLS residuals are exactly orthogonal to their own design
            # matrix, so a second regression of resid-on-x_base over the
            # *same* full sample always returns ~0 coefficients. Splitting
            # into two regime subsets breaks that orthogonality within each
            # subset and lets the experts actually specialize.
            base_coef = _fit_ols(x_base, y)
            base_fitted_log = base_coef[0] + x_base @ base_coef[1:]
            resid_train = y - base_fitted_log

            z_median = float(np.median(z_train))
            calm_mask_train = z_train <= z_median
            stress_mask_train = ~calm_mask_train
            calm_coef, calm_mean, calm_std = _fit_ridge(
                x_base[calm_mask_train], resid_train[calm_mask_train], lam=ridge_lambda
            )
            stress_coef, stress_mean, stress_std = _fit_ridge(
                x_base[stress_mask_train], resid_train[stress_mask_train], lam=ridge_lambda
            )

            # Soft-routing variant: same two experts, but every training row
            # contributes to both, weighted by its in-sample regime-scalar
            # percentile rank -- matching the paper's own finding (Table 5)
            # that hard regime-quantile assignment underperforms a soft gate.
            z_rank_train = pd.Series(z_train).rank(pct=True).to_numpy(dtype=float)
            soft_calm_coef, soft_calm_mean, soft_calm_std = _fit_ridge_weighted(
                x_base, resid_train, 1.0 - z_rank_train, lam=ridge_lambda
            )
            soft_stress_coef, soft_stress_mean, soft_stress_std = _fit_ridge_weighted(
                x_base, resid_train, z_rank_train, lam=ridge_lambda
            )

            last_fit_idx = i

        row_base = features.iloc[i][base_cols].to_numpy(dtype=float)
        row_z = float(z.iloc[i])

        input_row = np.r_[1.0, row_base, row_z]
        input_log_forecast = float(np.dot(input_coef, input_row))
        out.iloc[i, out.columns.get_loc(f"input_pathway_h{horizon}")] = float(np.exp(input_log_forecast))

        base_val = base_forecast.iloc[i]
        if pd.notna(base_val) and calm_coef is not None and stress_coef is not None:
            calm_row_std = (row_base - calm_mean) / calm_std
            stress_row_std = (row_base - stress_mean) / stress_std
            calm_pred_log = float(np.dot(calm_coef, np.r_[1.0, calm_row_std]))
            stress_pred_log = float(np.dot(stress_coef, np.r_[1.0, stress_row_std]))
            gw = gate_weight.iloc[i]
            gw = 0.5 if pd.isna(gw) else float(gw)
            resid_pred_log = (1.0 - gw) * calm_pred_log + gw * stress_pred_log
            gate_log_forecast = np.log(max(float(base_val), GK_FLOOR)) + resid_pred_log
            out.iloc[i, out.columns.get_loc(f"gate_pathway_h{horizon}")] = float(np.exp(gate_log_forecast))

            soft_calm_row_std = (row_base - soft_calm_mean) / soft_calm_std
            soft_stress_row_std = (row_base - soft_stress_mean) / soft_stress_std
            soft_calm_pred_log = float(np.dot(soft_calm_coef, np.r_[1.0, soft_calm_row_std]))
            soft_stress_pred_log = float(np.dot(soft_stress_coef, np.r_[1.0, soft_stress_row_std]))
            soft_resid_pred_log = (1.0 - gw) * soft_calm_pred_log + gw * soft_stress_pred_log
            soft_gate_log_forecast = np.log(max(float(base_val), GK_FLOOR)) + soft_resid_pred_log
            out.iloc[i, out.columns.get_loc(f"gate_pathway_soft_h{horizon}")] = float(np.exp(soft_gate_log_forecast))

    out[f"base_pathway_h{horizon}"] = base_forecast
    return out


def build_rg_resmoe_shadow(
    ohlc: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = HORIZONS,
    rolling_window: int | None = DEFAULT_ROLLING_WINDOW,
    ridge_lambda: float = DEFAULT_RIDGE_LAMBDA,
) -> pd.DataFrame:
    from group_a_plus.integrations.volatility_forecast import garman_klass_variance

    gk_variance = garman_klass_variance(ohlc)
    out = pd.DataFrame(index=ohlc.index)
    out["gk_variance"] = gk_variance
    out["policy"] = "shadow_only_no_weight_change"
    for h in horizons:
        frame = rg_resmoe_pathways(gk_variance, horizon=h, rolling_window=rolling_window, ridge_lambda=ridge_lambda)
        out = out.join(frame, how="left")
    return out


def latest_rg_resmoe_snapshot(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"status": "unavailable", "reason": "empty_frame"}
    row = frame.iloc[-1]
    horizons = sorted(
        int(c.split("base_pathway_h")[1])
        for c in frame.columns
        if c.startswith("base_pathway_h")
    )
    return {
        "status": "available",
        "policy": "shadow_only_no_weight_change",
        "outputs_target_weights": False,
        "horizons": {
            str(h): {
                "base_forecast": float(row.get(f"base_pathway_h{h}", float("nan"))),
                "input_pathway_forecast": float(row.get(f"input_pathway_h{h}", float("nan"))),
                "gate_pathway_forecast": float(row.get(f"gate_pathway_h{h}", float("nan"))),
                "gate_pathway_soft_forecast": float(row.get(f"gate_pathway_soft_h{h}", float("nan"))),
                "gate_weight": float(row.get(f"gate_weight_h{h}", float("nan"))),
            }
            for h in horizons
        },
    }


def _load_ohlc(
    db_path: Path,
    ticker: str,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, open, high, low, close
            FROM ohlcv
            WHERE ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, str(start.date()), str(end.date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _reference_gate(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Translate the shadow forecast into advisory-only 00631L metadata."""
    h5 = (snapshot.get("horizons") or {}).get("5") or {}
    base = _finite(h5.get("base_forecast"))
    soft = _finite(h5.get("gate_pathway_soft_forecast"))
    gate_weight = _finite(h5.get("gate_weight"))
    ratio = (soft / base) if base and soft else None
    high_vol = bool(
        gate_weight is not None
        and gate_weight >= 0.70
        and (ratio is None or ratio >= 1.00)
    )
    elevated_vol = bool(
        not high_vol
        and gate_weight is not None
        and gate_weight >= 0.55
        and (ratio is None or ratio >= 0.95)
    )
    if high_vol:
        gate = "rg_resmoe_high_vol_reference"
        scale = 0.50
        allow_add = False
    elif elevated_vol:
        gate = "rg_resmoe_elevated_vol_reference"
        scale = 0.75
        allow_add = True
    else:
        gate = "rg_resmoe_neutral_vol_reference"
        scale = 1.00
        allow_add = True
    return {
        "policy": "shadow_only_no_weight_change",
        "trade_policy": "advisory_no_auto_weight_change",
        "gate": gate,
        "high_vol_reference": high_vol,
        "elevated_vol_reference": elevated_vol,
        "allow_00631l_add_reference": allow_add,
        "reference_00631l_scale": scale,
        "inputs": {
            "h5_base_forecast_variance": base,
            "h5_gate_pathway_soft_forecast_variance": soft,
            "h5_soft_vs_base_ratio": ratio,
            "h5_gate_weight": gate_weight,
        },
        "rationale": (
            "RG-ResMoE-lite shadow uses regime state only for residual-gate routing; "
            "it is a risk reference and does not change target weights."
        ),
    }


def compute_rg_resmoe_volatility_gate_shadow(
    db_path: Path,
    as_of_date: pd.Timestamp,
    *,
    ticker: str = "0050.TW",
    lookback_days: int = LOOKBACK_CALENDAR_DAYS,
    rolling_window: int | None = DEFAULT_ROLLING_WINDOW,
    ridge_lambda: float = DEFAULT_RIDGE_LAMBDA,
) -> dict[str, Any]:
    """Daily RG-ResMoE-lite volatility gate snapshot.

    Diagnostic only: failures return an unavailable payload and must not block
    production signal generation.
    """
    as_of = pd.Timestamp(as_of_date).normalize()
    start = as_of - pd.Timedelta(days=lookback_days)
    try:
        ohlc = _load_ohlc(db_path, ticker, start=start, end=as_of)
        if ohlc.empty or len(ohlc) < MIN_TRAIN_ROWS + max(HORIZONS) + 60:
            return {"status": "unavailable", "reason": "insufficient_ohlc_history", "ticker": ticker}
        actual = pd.Timestamp(ohlc.index[-1]).normalize()
        if actual < as_of - pd.Timedelta(days=5):
            return {
                "status": "unavailable",
                "reason": "stale_ohlc_history",
                "ticker": ticker,
                "latest_date": str(actual.date()),
            }
        frame = build_rg_resmoe_shadow(
            ohlc,
            rolling_window=rolling_window,
            ridge_lambda=ridge_lambda,
        )
        snapshot = latest_rg_resmoe_snapshot(frame)
        snapshot.update(
            {
                "ticker": ticker,
                "date": str(actual.date()),
                "source": "arXiv:2608.12251 RG-ResMoE-lite pathway shadow",
                "lookback_calendar_days": int(lookback_days),
                "rows": int(len(ohlc)),
                "rolling_window": rolling_window,
                "ridge_lambda": float(ridge_lambda),
            }
        )
        snapshot["volatility_gate_reference"] = _reference_gate(snapshot)
        return snapshot
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc), "ticker": ticker}


def _combine_gate_references(by_ticker: dict[str, dict[str, Any]]) -> dict[str, Any]:
    available_refs = {
        ticker: shadow.get("volatility_gate_reference") or {}
        for ticker, shadow in by_ticker.items()
        if shadow.get("status") == "available"
    }
    if not available_refs:
        return {
            "policy": "shadow_only_no_weight_change",
            "trade_policy": "advisory_no_auto_weight_change",
            "gate": "rg_resmoe_unavailable",
            "high_vol_reference": False,
            "elevated_vol_reference": False,
            "allow_00631l_add_reference": True,
            "reference_00631l_scale": 1.0,
            "inputs": {},
        }
    high = any(ref.get("high_vol_reference") is True for ref in available_refs.values())
    elevated = any(ref.get("elevated_vol_reference") is True for ref in available_refs.values())
    scales = [
        _finite(ref.get("reference_00631l_scale"))
        for ref in available_refs.values()
    ]
    clean_scales = [scale for scale in scales if scale is not None]
    scale = min(clean_scales) if clean_scales else 1.0
    if high:
        gate = "rg_resmoe_combined_high_vol_reference"
        allow_add = False
    elif elevated:
        gate = "rg_resmoe_combined_elevated_vol_reference"
        allow_add = True
    else:
        gate = "rg_resmoe_combined_neutral_vol_reference"
        allow_add = True
    return {
        "policy": "shadow_only_no_weight_change",
        "trade_policy": "advisory_no_auto_weight_change",
        "gate": gate,
        "high_vol_reference": high,
        "elevated_vol_reference": elevated,
        "allow_00631l_add_reference": allow_add,
        "reference_00631l_scale": scale,
        "inputs": {
            ticker: ref.get("inputs") or {}
            for ticker, ref in available_refs.items()
        },
        "rationale": (
            "Combined RG-ResMoE-lite shadow uses the most conservative available "
            "0050/00631L volatility reference. Advisory only; no target-weight change."
        ),
    }


def load_rg_resmoe_readiness_review(review_path: Path) -> dict[str, Any]:
    """Load the latest RG-ResMoE readiness review if it exists."""
    if not review_path.exists():
        return {"status": "unavailable", "reason": "missing_readiness_review", "path": str(review_path)}
    try:
        payload = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "unavailable", "reason": str(exc), "path": str(review_path)}
    payload["status"] = payload.get("status", "available")
    payload["path"] = str(review_path)
    return payload


def _h5_daily_reference(
    ticker: str,
    ticker_shadow: dict[str, Any],
    readiness_detail: dict[str, Any],
    *,
    high_vol_gate_quantile: float,
) -> dict[str, Any]:
    h5 = ((ticker_shadow.get("horizons") or {}).get("5")) or {}
    base = _finite(h5.get("base_forecast"))
    soft = _finite(h5.get("gate_pathway_soft_forecast"))
    gate_weight = _finite(h5.get("gate_weight"))
    ratio = (soft / base) if base and soft else None
    active = bool(gate_weight is not None and gate_weight >= high_vol_gate_quantile)
    ready = bool(readiness_detail.get("ready") is True and readiness_detail.get("tail_ready") is True)
    return {
        "ticker": ticker,
        "status": ticker_shadow.get("status", "unavailable"),
        "date": ticker_shadow.get("date"),
        "policy": "shadow_only_no_weight_change",
        "horizon": 5,
        "h5_high_vol_ready_reference": ready,
        "h5_high_vol_active_reference": active,
        "high_vol_gate_quantile": float(high_vol_gate_quantile),
        "readiness": {
            "qlike_improvement_pct": _finite(readiness_detail.get("qlike_improvement_pct")),
            "dm_p_value": _finite(readiness_detail.get("dm_p_value")),
            "dm_a_more_accurate": readiness_detail.get("dm_a_more_accurate"),
            "tail_ready": readiness_detail.get("tail_ready"),
            "note": readiness_detail.get("note"),
        },
        "inputs": {
            "h5_base_forecast_variance": base,
            "h5_gate_pathway_soft_forecast_variance": soft,
            "h5_soft_vs_base_ratio": ratio,
            "h5_gate_weight": gate_weight,
        },
    }


def build_rg_resmoe_h5_high_vol_shadow_advisory(
    shadow: dict[str, Any],
    *,
    readiness_review_path: Path | None = None,
    readiness_review: dict[str, Any] | None = None,
    high_vol_gate_quantile: float = H5_HIGH_VOL_GATE_QUANTILE,
) -> dict[str, Any]:
    """Daily H5 high-vol-only advisory from the RG-ResMoE readiness layer.

    This is intentionally separate from target-weight generation. The readiness
    review decides whether the H5 high-vol-only layer is worth observing; the
    current daily shadow decides whether today's gate is in that high-vol zone.
    """
    if shadow.get("status") != "available":
        return {
            "status": "unavailable",
            "reason": "shadow_unavailable",
            "policy": "shadow_only_no_weight_change",
            "outputs_target_weights": False,
        }
    review = readiness_review
    if review is None and readiness_review_path is not None:
        review = load_rg_resmoe_readiness_review(readiness_review_path)
    review = review or {"status": "unavailable", "reason": "missing_readiness_review"}
    layered = review.get("layered_decision") or {}
    details = layered.get("h5_high_vol_shadow_details") or {}
    by_ticker = shadow.get("by_ticker") or {}
    references = {
        ticker: _h5_daily_reference(
            ticker,
            ticker_shadow,
            details.get(ticker) or {},
            high_vol_gate_quantile=high_vol_gate_quantile,
        )
        for ticker, ticker_shadow in by_ticker.items()
    }
    active_tickers = sorted(
        ticker
        for ticker, ref in references.items()
        if ref.get("h5_high_vol_ready_reference") is True
        and ref.get("h5_high_vol_active_reference") is True
    )
    ready_tickers = sorted(
        ticker
        for ticker, ref in references.items()
        if ref.get("h5_high_vol_ready_reference") is True
    )
    h5_ready = layered.get("h5_high_vol_shadow_ready")
    status = "partial_ready_shadow_only" if h5_ready in {True, "partial"} and ready_tickers else "watch_shadow_only"
    return {
        "status": status,
        "date": shadow.get("date"),
        "policy": "shadow_only_no_weight_change",
        "trade_policy": "shadow_only_no_weight_change",
        "outputs_target_weights": False,
        "allow_target_weight_change": False,
        "source": {
            "daily_shadow": "arXiv:2608.12251 RG-ResMoE-lite pathway shadow",
            "readiness_review": review.get("path") or review.get("source"),
        },
        "readiness": {
            "full_promotion_ready": layered.get("full_promotion_ready"),
            "tail_calibration_ready": layered.get("tail_calibration_ready"),
            "h5_high_vol_shadow_ready": h5_ready,
            "trade_policy": layered.get("trade_policy"),
            "blockers": (layered.get("blockers") or {}).get("h5_high_vol_shadow"),
            "interpretation": layered.get("interpretation"),
        },
        "combined_reference": {
            "h5_high_vol_active_reference": bool(active_tickers),
            "active_tickers": active_tickers,
            "ready_tickers": ready_tickers,
            "high_vol_gate_quantile": float(high_vol_gate_quantile),
            "manual_review_reason": (
                "H5 RG-ResMoE high-vol-only shadow is active today."
                if active_tickers
                else "H5 RG-ResMoE high-vol-only shadow is ready/observed but not active today."
            ),
        },
        "by_ticker": references,
    }


def compute_group_a_plus_rg_resmoe_volatility_gate_shadow(
    db_path: Path,
    as_of_date: pd.Timestamp,
    *,
    tickers: tuple[str, ...] = DEFAULT_SHADOW_TICKERS,
    lookback_days: int = LOOKBACK_CALENDAR_DAYS,
    rolling_window: int | None = DEFAULT_ROLLING_WINDOW,
    ridge_lambda: float = DEFAULT_RIDGE_LAMBDA,
) -> dict[str, Any]:
    """GroupA+ daily RG-ResMoE-lite shadow for the risk-bearing ETF pair."""
    by_ticker = {
        ticker: compute_rg_resmoe_volatility_gate_shadow(
            db_path,
            as_of_date,
            ticker=ticker,
            lookback_days=lookback_days,
            rolling_window=rolling_window,
            ridge_lambda=ridge_lambda,
        )
        for ticker in tickers
    }
    available = {
        ticker: shadow
        for ticker, shadow in by_ticker.items()
        if shadow.get("status") == "available"
    }
    dates = [
        str(shadow.get("date"))
        for shadow in available.values()
        if shadow.get("date")
    ]
    return {
        "status": "available" if available else "unavailable",
        "reason": None if available else "no_available_ticker_shadow",
        "policy": "shadow_only_no_weight_change",
        "outputs_target_weights": False,
        "date": max(dates) if dates else str(pd.Timestamp(as_of_date).date()),
        "tickers": list(tickers),
        "by_ticker": by_ticker,
        "volatility_gate_reference": _combine_gate_references(by_ticker),
    }


def append_rg_resmoe_volatility_gate_shadow_log(
    log_path: Path,
    shadow: dict[str, Any],
    *,
    execution_regime: str | None = None,
) -> None:
    """Append one idempotent daily RG-ResMoE shadow observation."""
    if shadow.get("status") != "available":
        return
    row = dict(shadow)
    row["logged_execution_regime"] = execution_regime
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
            if existing.get("date") != row.get("date"):
                rows.append(existing)
    rows.append(row)
    rows.sort(key=lambda r: r.get("date", ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def append_rg_resmoe_h5_high_vol_shadow_advisory_log(
    log_path: Path,
    advisory: dict[str, Any],
    *,
    execution_regime: str | None = None,
) -> None:
    """Append one idempotent daily H5 high-vol advisory observation."""
    if advisory.get("status") == "unavailable":
        return
    row = dict(advisory)
    row["logged_execution_regime"] = execution_regime
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
            if existing.get("date") != row.get("date"):
                rows.append(existing)
    rows.append(row)
    rows.sort(key=lambda r: r.get("date", ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
