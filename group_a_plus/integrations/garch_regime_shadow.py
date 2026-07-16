"""GARCH-proxy volatility-regime routing shadow diagnostic (2026-07-05).

Research background: a user question about "specialist routing" (swap which
model/rule you trust depending on volatility regime) led to a walk-forward
validation of the existing GARCH-proxy volatility selector
(scripts/backtest/backtest_group_a_plus_financial_econometrics.py, 2026-06-19).
Results (see results/garch_specialist_routing_walkforward_20260705.json and
results/garch_specialist_routing_2008_fold_20260705.json):

- 2022-2026 real-data walk-forward (6 expanding-window folds): no consistent
  out-of-sample edge (3/6 folds) versus simply freezing whichever of a207/ma20
  had the better train-period Sharpe.
- 2008 TWII-proxy crash fold (train=2003-2007, test=2007-07~2009-12): a
  threshold-robust edge -- 24/24 grid variants of the selector beat ma20 OOS.

That is one real crisis sample (n=1) with no independent second stress period
available locally to confirm it. Not enough evidence to change any weight
calculation. This module exists purely to accumulate real forward-looking
observations from now on: it computes, once per trading day, what the frozen
selector rule below would pick, and logs it. It must never feed
target_weights, execution_regime, base_regime, or any other production
decision -- same diagnostic-only contract as
group_a_plus.operations.market_state.classify_market_state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_plus_switch_policy import _load_chip_features, _load_prices, _switch_returns
from scripts.backtest.backtest_group_a_plus_financial_econometrics import A207_RULE, MA20_RULE, _garch_features

# Frozen parameters (2026-07-05 walk-forward research): the only combo picked
# consistently across all 6 real-data 2022-2026 folds, and part of the 24/24
# grid that beat ma20 out-of-sample in the 2008 crisis fold. Do not retune
# these from live data without re-running the walk-forward research --
# picking thresholds to fit recent shadow-log history would reintroduce the
# exact look-ahead bias this module exists to avoid.
RATIO_THRESHOLD = 1.05
PERCENTILE_THRESHOLD = 0.70
REQUIRE_NEGATIVE_5D = True
LOOKBACK_CALENDAR_DAYS = 900  # ~2.5y burn-in for the 252d GARCH floor + 75d MA windows
LOW_VOL_PERCENTILE_THRESHOLD = 0.40
LOW_VOL_RATIO_MAX = 1.00
HIGH_VOL_REFERENCE_SCALE = 0.50
NEUTRAL_VOL_REFERENCE_SCALE = 0.75
LOW_VOL_REFERENCE_SCALE = 1.00


def volatility_gate_reference(
    *,
    high_vol: bool,
    ratio: float,
    percentile: float,
    return_5d: float,
) -> dict[str, Any]:
    """Translate the shadow vol-regime reading into diagnostic gate metadata.

    This is deliberately advisory-only. It records the kind of low-vol gating /
    volatility scaling idea suggested by the CSI 300 paper, but it must not be
    consumed by live allocation until it passes separate walk-forward promotion.
    """
    low_vol = (
        not bool(high_vol)
        and float(percentile) <= LOW_VOL_PERCENTILE_THRESHOLD
        and float(ratio) <= LOW_VOL_RATIO_MAX
    )
    if high_vol:
        gate = "high_vol_defensive"
        reliability = "suppress_return_prediction"
        scale = HIGH_VOL_REFERENCE_SCALE
        rationale = "High volatility with negative 5d confirmation; use return signals defensively only."
    elif low_vol:
        gate = "low_vol_participation"
        reliability = "allow_return_prediction"
        scale = LOW_VOL_REFERENCE_SCALE
        rationale = "Low volatility regime; return predictors are expected to be more usable."
    else:
        gate = "neutral_vol"
        reliability = "calibrate_thresholds"
        scale = NEUTRAL_VOL_REFERENCE_SCALE
        rationale = "Intermediate volatility; require calibrated thresholds and turnover discipline."

    return {
        "policy": "shadow_only_no_weight_change",
        "gate": gate,
        "low_vol_gate": bool(low_vol),
        "high_vol_gate": bool(high_vol),
        "signal_reliability": reliability,
        "reference_00631l_scale": round(float(scale), 4),
        "inputs": {
            "garch_proxy_vol_ratio": round(float(ratio), 4),
            "garch_proxy_vol_percentile": round(float(percentile), 4),
            "return_0050_5d": round(float(return_5d), 4),
        },
        "rationale": rationale,
    }


def compute_garch_regime_shadow(
    db_path: Path,
    as_of_date: pd.Timestamp,
    *,
    lookback_days: int = LOOKBACK_CALENDAR_DAYS,
) -> dict[str, Any]:
    """Diagnostic only. Returns what the frozen GARCH-vol selector would pick
    as of `as_of_date`. Does not affect target_weights or execution_regime."""
    as_of = pd.Timestamp(as_of_date).normalize()
    start = (as_of - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = as_of.strftime("%Y-%m-%d")
    # Everything below is a diagnostic side computation -- per this module's
    # own contract (see docstring), a failure here must never break the
    # day's real live signal. Wrap the whole thing, not just price loading:
    # _load_chip_features/_switch_returns/_garch_features can also raise
    # (e.g. a duckdb table genuinely missing), and daily_signal.py has no
    # local try/except around this call -- an uncaught exception here would
    # otherwise propagate to build_daily_signal's top-level handler and turn
    # the whole day's output (including target_weights) into an error payload.
    try:
        prices = _load_prices(db_path, ["0050.TW"], start, end)
        if prices.empty or prices.index[-1] < as_of - pd.Timedelta(days=5):
            return {"status": "unavailable", "reason": "insufficient_price_history"}

        chip_features = _load_chip_features(db_path, prices.index, start, end)
        _a207_events, a207_frame = _switch_returns(prices, chip_features, A207_RULE)
        _ma20_events, ma20_frame = _switch_returns(prices, chip_features, MA20_RULE)
        garch = _garch_features(prices, chip_features)

        last = garch.iloc[-1]
        ratio = float(last["garch_proxy_vol_ratio"])
        percentile = float(last["garch_proxy_vol_percentile"])
        return_5d = float(last["return_0050_5d"])
        high_vol = (ratio >= RATIO_THRESHOLD) or (percentile >= PERCENTILE_THRESHOLD)
        if REQUIRE_NEGATIVE_5D:
            high_vol = high_vol and return_5d < 0.0

        selected_rule = "ma20" if high_vol else "a207"
        a207_regime = str(a207_frame["regime"].iloc[-1])
        ma20_regime = str(ma20_frame["regime"].iloc[-1])
        shadow_selected_regime = ma20_regime if high_vol else a207_regime
        volatility_gate = volatility_gate_reference(
            high_vol=bool(high_vol),
            ratio=ratio,
            percentile=percentile,
            return_5d=return_5d,
        )
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)}

    return {
        "status": "available",
        "policy": "shadow_only_no_weight_change",
        "date": str(prices.index[-1].date()),
        "params": {
            "ratio_threshold": RATIO_THRESHOLD,
            "percentile_threshold": PERCENTILE_THRESHOLD,
            "require_negative_5d": REQUIRE_NEGATIVE_5D,
            "source": "walk-forward research 2026-07-05",
        },
        "garch_proxy_vol_ratio": round(ratio, 4),
        "garch_proxy_vol_percentile": round(percentile, 4),
        "return_0050_5d": round(return_5d, 4),
        "high_vol_flag": bool(high_vol),
        "selected_rule": selected_rule,
        "a207_regime": a207_regime,
        "ma20_regime": ma20_regime,
        "shadow_selected_regime": shadow_selected_regime,
        "volatility_gate": volatility_gate,
    }


def append_garch_regime_shadow_log(
    log_path: Path,
    shadow: dict[str, Any],
    *,
    execution_regime: str | None = None,
) -> None:
    """Append one day's shadow observation to a JSON-lines log for later review.

    Idempotent per date: replaces any existing row for the same date instead
    of duplicating it, so re-running daily_signal same-day does not skew the
    forward-observation count.
    """
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
            if existing.get("date") != row["date"]:
                rows.append(existing)
    rows.append(row)
    rows.sort(key=lambda r: r.get("date", ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
