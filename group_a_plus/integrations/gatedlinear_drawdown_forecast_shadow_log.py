"""Pure-logging daily accumulator for the GatedLinear-lite drawdown forecast
(2607.09537 follow-up, 2026-08-16).

Today's review of "GatedLinear: Adaptive Routing of Complementary Linear
Bases for Time Series Forecasting" tested whether its tri-basis (trend /
difference / phase-recurrence) + learned-gate architecture, stripped down to
a lightweight numpy/ridge implementation, could forecast 0050.TW's own
`drawdown` feature (one of the two decision variables the production switch
rule consumes) better than simple baselines. Result: mostly a wash or tied
with a plain ridge-on-raw-lags model, EXCEPT at a 20-trading-day horizon,
where it beat persistence, the unconditional-mean baseline, AND ridge-on-
raw-lags in the aggregate test AND in all 3 independent sub-window checks,
with non-degenerate gate weights (all 3 bases contributing) -- see
docs/HANDOFF_2607_09537_GATEDLINEAR_GROUPA_PLUS_20260816.md for the full
backtest. The edge was real but small (~7% RMSE vs persistence, ~1.5% vs
ridge) on a single train/test split; not promoted to any live decision.

This logs the model's H=20 drawdown forecast every day at live speed,
accumulating real predicted-vs-eventually-realized pairs instead of relying
solely on the one historical backtest split. Never changes target weights,
execution guards, or the live signal -- purely observational.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

SHADOW_LOG_SCHEMA_VERSION = 1
L = 20  # lookback window (trading days)
P = 5   # phase period (trading week)
H = 20  # forecast horizon (trading days) -- the only horizon that showed a robust edge


def _basis_trend(x: np.ndarray, horizon: int) -> np.ndarray:
    t = np.arange(x.shape[1])
    tmean = t.mean()
    tvar = ((t - tmean) ** 2).sum()
    xmean = x.mean(axis=1, keepdims=True)
    slope = ((x - xmean) * (t - tmean)).sum(axis=1) / tvar
    intercept = xmean.squeeze(-1) - slope * tmean
    return intercept + slope * (t[-1] + horizon)


def _basis_phase(x: np.ndarray, period: int, horizon: int) -> np.ndarray:
    width = x.shape[1]
    target_pos = (width - 1) + horizon
    phase = target_pos % period
    mask = (np.arange(width) % period) == phase
    return x[:, mask].mean(axis=1)


def _basis_diff_fit_predict(
    x_train: np.ndarray, y_train: np.ndarray, x_test: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    dx_train = np.diff(x_train, axis=1)
    dy_train = y_train - x_train[:, -1]
    dx_test = np.diff(x_test, axis=1)
    model = Ridge(alpha=1.0)
    model.fit(dx_train, dy_train)
    pred_diff_train = model.predict(dx_train)
    pred_diff_test = model.predict(dx_test)
    return x_train[:, -1] + pred_diff_train, x_test[:, -1] + pred_diff_test


def fit_and_forecast(drawdown: pd.Series) -> dict[str, Any]:
    """Walk-forward H-step drawdown forecast using all history up to (and
    including) the series' last date. Trains only on (window, target) pairs
    whose target already lies in the past -- the same discipline as the
    original research backtest, just re-fit online instead of on a single
    fixed split."""
    arr = drawdown.dropna().to_numpy()
    dates = drawdown.dropna().index
    n = len(arr)
    min_required = L + H + 50  # need enough complete training pairs to fit a stable ridge gate
    if n < min_required:
        return {
            "schema_version": SHADOW_LOG_SCHEMA_VERSION,
            "status": "unavailable",
            "reason": f"insufficient_history (have {n}, need {min_required})",
        }

    windows = np.lib.stride_tricks.sliding_window_view(arr, L)
    x_train = windows[: n - L - H + 1]
    y_train = arr[L + H - 1 : n]
    x_test = arr[n - L : n].reshape(1, -1)

    predA_train = _basis_trend(x_train, H)
    predC_train = _basis_phase(x_train, P, H)
    predB_train, predB_test = _basis_diff_fit_predict(x_train, y_train, x_test)
    predA_test = _basis_trend(x_test, H)
    predC_test = _basis_phase(x_test, P, H)

    stack_train = np.column_stack([predA_train, predB_train, predC_train])
    stack_test = np.column_stack([predA_test, predB_test, predC_test])
    gate = Ridge(alpha=1.0, positive=True)
    gate.fit(stack_train, y_train)
    predicted = float(gate.predict(stack_test)[0])

    return {
        "schema_version": SHADOW_LOG_SCHEMA_VERSION,
        "status": "available",
        "date": str(pd.Timestamp(dates[-1]).date()),
        "current_drawdown": float(arr[-1]),
        "predicted_drawdown_h20": predicted,
        "horizon_trading_days": H,
        "gate_weights": {"trend": float(gate.coef_[0]), "diff": float(gate.coef_[1]), "phase": float(gate.coef_[2])},
        "gate_intercept": float(gate.intercept_),
        "n_train_pairs": int(len(y_train)),
    }


def append_shadow_log_row(row: dict[str, Any], log_path: str | Path) -> bool:
    """Append row to a JSONL log, deduped by date. Returns True if appended."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if row.get("status") != "available":
        return False
    existing_dates: set[str] = set()
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                existing_dates.add(json.loads(line).get("date"))
    if row.get("date") in existing_dates:
        return False
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True
