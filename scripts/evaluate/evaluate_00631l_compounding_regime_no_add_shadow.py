#!/usr/bin/env python3
"""Shadow-test 00631L add-speed rules based on compounding regime.

Research-only.  This evaluates the practical implication of
``Compounding Effects in Leveraged ETFs: Beyond the Volatility Drag Paradigm``:
slow or block incremental 00631L exposure only when the sequence diagnostic
classifies the market as mean-reverting.  It never cuts existing 00631L
exposure and never changes A21.18 target weights outside the simulated shadow
path.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _metrics
from group_a_plus.integrations.leveraged_compounding_regime import (
    MEAN_REVERTING,
    TREND_PERSISTENT,
    CompoundingRegimeThresholds,
    build_compounding_features,
    classify_compounding_regime,
)
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import (
    PANEL_2017_2019,
    PANEL_2025_2026,
    _resolve_end_date,
    _targets_from_report,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_compounding_regime_no_add_shadow_20260715.json"
DEFAULT_WINDOWS = [
    ("live_2024_2026", "2024-01-02", "latest", PANEL_2025_2026, "tuning_window"),
    ("active_2025_2026", "2025-01-02", "latest", PANEL_2025_2026, "tuning_window"),
    ("2017_bull", "2017-01-03", "2017-12-29", PANEL_2017_2019, "out_of_sample"),
    ("2018_correction", "2018-01-02", "2018-12-31", PANEL_2017_2019, "out_of_sample"),
    ("2019_recovery", "2019-01-02", "2019-12-31", PANEL_2017_2019, "out_of_sample"),
]


def _parse_windows(raw: str) -> list[tuple[str, str, str, str, str]]:
    if raw == "default":
        return DEFAULT_WINDOWS
    windows: list[tuple[str, str, str, str, str]] = []
    for item in raw.split(";"):
        if not item.strip():
            continue
        parts = [part.strip() for part in item.split(",")]
        if len(parts) != 5:
            raise ValueError("Each window must be label,start,end,panel,kind")
        windows.append((parts[0], parts[1], parts[2], parts[3], parts[4]))
    return windows


def _portfolio_value(price_row: pd.Series, shares: dict[str, float], cash: float) -> float:
    return float(cash) + sum(float(shares.get(ticker, 0.0)) * float(price_row[ticker]) for ticker in TICKERS)


def simulate_no_add_guard(
    *,
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    regimes: pd.Series,
    initial_value: float,
    baseline_add_fraction: float = 1.0,
    mean_reversion_add_fraction: float = 0.0,
    trend_persistent_add_fraction: float | None = None,
    trend_persistent_add_fraction_by_date: pd.Series | None = None,
    transaction_cost_bps: float = 0.0,
    ticker: str = "00631L.TW",
) -> dict[str, Any]:
    """Simulate daily target rebalancing with mean-reversion add-speed guard."""

    prices = prices[list(TICKERS)].astype(float).sort_index()
    target_weights = target_weights.reindex(prices.index).fillna(0.0)
    regimes = regimes.reindex(prices.index).fillna("UNAVAILABLE")
    baseline_add_fraction = min(max(float(baseline_add_fraction), 0.0), 1.0)
    mean_reversion_add_fraction = min(max(float(mean_reversion_add_fraction), 0.0), 1.0)
    if trend_persistent_add_fraction is None:
        trend_persistent_add_fraction = baseline_add_fraction
    trend_persistent_add_fraction = min(max(float(trend_persistent_add_fraction), 0.0), 1.0)
    trend_persistent_add_fraction_by_date = (
        trend_persistent_add_fraction_by_date.reindex(prices.index).astype(float)
        if trend_persistent_add_fraction_by_date is not None
        else pd.Series(trend_persistent_add_fraction, index=prices.index, dtype=float)
    ).clip(lower=0.0, upper=1.0)
    transaction_cost_rate = max(float(transaction_cost_bps), 0.0) / 10_000.0
    shares = {name: 0.0 for name in TICKERS}
    cash = float(initial_value)
    values: list[float] = []
    events: list[dict[str, Any]] = []
    total_transaction_cost = 0.0

    for dt, price_row in prices.iterrows():
        value = _portfolio_value(price_row, shares, cash)
        current_value = float(shares.get(ticker, 0.0)) * float(price_row[ticker])
        desired_weight = float(target_weights.loc[dt].get(ticker, 0.0) or 0.0)
        desired_value = value * desired_weight
        regime = str(regimes.loc[dt])
        is_00631l_add = desired_value > current_value
        guarded_add = bool(regime == MEAN_REVERTING and is_00631l_add)
        trend_add_fraction = float(trend_persistent_add_fraction_by_date.loc[dt])
        accelerated_add = bool(regime == TREND_PERSISTENT and is_00631l_add and trend_add_fraction > baseline_add_fraction)

        new_values: dict[str, float] = {}
        for asset in TICKERS:
            target_value = value * float(target_weights.loc[dt].get(asset, 0.0) or 0.0)
            if asset == ticker and target_value > current_value:
                add_fraction = baseline_add_fraction
                if regime == MEAN_REVERTING:
                    add_fraction = mean_reversion_add_fraction
                elif regime == TREND_PERSISTENT:
                    add_fraction = trend_add_fraction
                target_value = current_value + (target_value - current_value) * add_fraction
            new_values[asset] = max(float(target_value), 0.0)

        current_values = {asset: float(shares.get(asset, 0.0)) * float(price_row[asset]) for asset in TICKERS}
        traded_notional = sum(abs(float(new_values[asset]) - current_values[asset]) for asset in TICKERS)
        transaction_cost = traded_notional * transaction_cost_rate
        total_transaction_cost += transaction_cost
        invested = sum(new_values.values())
        if invested > 0.0 and invested + transaction_cost > value:
            scale = max(value - transaction_cost, 0.0) / invested
            new_values = {asset: float(asset_value) * scale for asset, asset_value in new_values.items()}
            invested = sum(new_values.values())
        cash = max(value - invested - transaction_cost, 0.0)
        shares = {asset: new_values[asset] / max(float(price_row[asset]), 1e-12) for asset in TICKERS}
        values.append(_portfolio_value(price_row, shares, cash))

        if guarded_add or accelerated_add:
            blocked_weight = (desired_value - new_values[ticker]) / value if value else 0.0
            events.append(
                {
                    "date": str(pd.Timestamp(dt).date()),
                    "compounding_regime": regime,
                    "baseline_add_fraction": baseline_add_fraction,
                    "mean_reversion_add_fraction": mean_reversion_add_fraction,
                    "trend_persistent_add_fraction": trend_persistent_add_fraction,
                    "effective_trend_persistent_add_fraction": round(trend_add_fraction, 6),
                    "portfolio_value": round(value, 2),
                    "current_00631l_weight": round(current_value / value, 6) if value else 0.0,
                    "requested_00631l_weight": round(desired_weight, 6),
                    "allowed_00631l_add_weight": round((new_values[ticker] - current_value) / value, 6)
                    if value
                    else 0.0,
                    "blocked_00631l_weight": round(blocked_weight, 6),
                    "accelerated_00631l_weight": round(
                        max((new_values[ticker] - current_value) / value - baseline_add_fraction * (desired_value - current_value) / value, 0.0),
                        6,
                    )
                    if value
                    else 0.0,
                }
            )

    curve = pd.Series(values, index=prices.index[: len(values)], dtype=float)
    guarded_days = sum(float(event.get("blocked_00631l_weight", 0.0) or 0.0) > 0.0 for event in events)
    accelerated_days = sum(float(event.get("accelerated_00631l_weight", 0.0) or 0.0) > 0.0 for event in events)
    return {
        "metrics": _metrics(curve, initial_value),
        "event_days": len(events),
        "blocked_days": int(guarded_days),
        "accelerated_days": int(accelerated_days),
        "transaction_cost_bps": float(transaction_cost_bps),
        "total_transaction_cost": float(total_transaction_cost),
        "blocked_events": events[:200],
    }


def _simulate_baseline(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    initial_value: float,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    return simulate_no_add_guard(
        prices=prices,
        target_weights=target_weights,
        regimes=pd.Series("TRANSITIONAL", index=prices.index),
        initial_value=initial_value,
        baseline_add_fraction=1.0,
        transaction_cost_bps=transaction_cost_bps,
    )


def _simulate_speed_baseline(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    initial_value: float,
    baseline_add_fraction: float,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    return simulate_no_add_guard(
        prices=prices,
        target_weights=target_weights,
        regimes=pd.Series("TRANSITIONAL", index=prices.index),
        initial_value=initial_value,
        baseline_add_fraction=baseline_add_fraction,
        mean_reversion_add_fraction=baseline_add_fraction,
        trend_persistent_add_fraction=baseline_add_fraction,
        transaction_cost_bps=transaction_cost_bps,
    )


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    return {
        key: float(candidate["metrics"][key] - baseline["metrics"][key])
        for key in ("final_value", "sharpe_ratio", "sortino_ratio", "max_drawdown", "worst_20d_return")
    }


def _apply_ce_filter(classified: pd.DataFrame, mode: str) -> pd.Series:
    regimes = classified["compounding_regime"].copy()
    if mode == "none":
        return regimes
    ce20 = classified.get("compounding_effect_20d", pd.Series(index=classified.index, dtype=float))
    ce60 = classified.get("compounding_effect_60d", pd.Series(index=classified.index, dtype=float))
    if mode == "ce20_negative":
        keep = ce20 < 0.0
    elif mode == "ce20_or_60_negative":
        keep = (ce20 < 0.0) | (ce60 < 0.0)
    elif mode == "ce20_and_60_negative":
        keep = (ce20 < 0.0) & (ce60 < 0.0)
    else:
        raise ValueError(f"unknown CE filter: {mode}")
    regimes.loc[(regimes == MEAN_REVERTING) & ~keep.fillna(False)] = "TRANSITIONAL"
    return regimes


def _trend_add_fraction_by_edge(
    classified: pd.DataFrame,
    regimes: pd.Series,
    *,
    mode: str,
    normal_fraction: float | None,
    weak_fraction: float,
) -> pd.Series | None:
    if normal_fraction is None or mode == "none":
        return None
    normal = min(max(float(normal_fraction), 0.0), 1.0)
    weak = min(max(float(weak_fraction), 0.0), 1.0)
    trend = regimes.reindex(classified.index) == TREND_PERSISTENT
    weak_edge = pd.Series(False, index=classified.index)
    if mode == "trend_score_eq_min":
        weak_edge = classified["trend_score"] <= classified["trend_score"].where(trend).min()
    elif mode == "relative_momentum_nonpositive":
        weak_edge = classified["00631L_vs_0050_relative_momentum"] <= 0.0
    elif mode == "ce20_negative":
        weak_edge = classified["compounding_effect_20d"] < 0.0
    elif mode == "any":
        min_trend_score = classified["trend_score"].where(trend).min()
        weak_edge = (
            (classified["trend_score"] <= min_trend_score)
            | (classified["00631L_vs_0050_relative_momentum"] <= 0.0)
            | (classified["compounding_effect_20d"] < 0.0)
        )
    else:
        raise ValueError(f"unknown weak trend edge gate: {mode}")
    fractions = pd.Series(normal, index=classified.index, dtype=float)
    fractions.loc[trend & weak_edge.fillna(False)] = weak
    return fractions


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    panel: str,
    kind: str,
    db_path: Path,
    initial_value: float,
    thresholds: CompoundingRegimeThresholds,
    baseline_add_fraction: float,
    mean_reversion_add_fraction: float,
    trend_persistent_add_fraction: float | None,
    weak_trend_edge_gate: str = "none",
    weak_trend_add_fraction: float = 0.90,
    ce_filter: str,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    resolved_end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=resolved_end,
        initial_value=initial_value,
        db=db_path,
        ncf_panel_631l_path=panel,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
    )
    prices = _load_prices(db_path, list(TICKERS), start, resolved_end).reindex(frame.index).dropna()
    target_weights = _targets_from_report(frame.reindex(prices.index), report)
    features = build_compounding_features(prices["00631L.TW"], prices["0050.TW"])
    classified = classify_compounding_regime(features, thresholds=thresholds)
    regimes = _apply_ce_filter(classified, ce_filter).reindex(prices.index)
    trend_add_fraction_by_date = _trend_add_fraction_by_edge(
        classified.reindex(prices.index),
        regimes,
        mode=weak_trend_edge_gate,
        normal_fraction=trend_persistent_add_fraction,
        weak_fraction=weak_trend_add_fraction,
    )

    baseline = (
        _simulate_baseline(prices, target_weights, initial_value, float(transaction_cost_bps))
        if float(baseline_add_fraction) >= 1.0
        else _simulate_speed_baseline(
            prices,
            target_weights,
            initial_value,
            float(baseline_add_fraction),
            float(transaction_cost_bps),
        )
    )
    guarded = simulate_no_add_guard(
        prices=prices,
        target_weights=target_weights,
        regimes=regimes,
        initial_value=initial_value,
        baseline_add_fraction=baseline_add_fraction,
        mean_reversion_add_fraction=mean_reversion_add_fraction,
        trend_persistent_add_fraction=trend_persistent_add_fraction,
        trend_persistent_add_fraction_by_date=trend_add_fraction_by_date,
        transaction_cost_bps=transaction_cost_bps,
    )
    regime_counts = regimes.value_counts(dropna=False)
    return {
        "label": label,
        "kind": kind,
        "window": {"start": start, "end": resolved_end, "rows": int(len(prices))},
        "regime_counts": {str(k): int(v) for k, v in regime_counts.items()},
        "baseline": baseline,
        "mean_reversion_no_add": guarded,
        "delta_vs_baseline": _metric_delta(guarded, baseline),
        "weak_trend_edge_gate": weak_trend_edge_gate,
        "weak_trend_add_fraction": float(weak_trend_add_fraction),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = Path(args.db)
    thresholds = CompoundingRegimeThresholds(
        ar1_trend_min=float(args.ar1_trend_min),
        ar1_revert_max=float(args.ar1_revert_max),
        variance_ratio_trend_min=float(args.variance_ratio_trend_min),
        variance_ratio_revert_max=float(args.variance_ratio_revert_max),
        trend_persistence_min=float(args.trend_persistence_min),
        trend_persistence_revert_max=float(args.trend_persistence_revert_max),
        reversal_speed_revert_min=float(args.reversal_speed_revert_min),
        reversal_speed_trend_max=float(args.reversal_speed_trend_max),
        drawdown_recovery_revert_min=float(args.drawdown_recovery_revert_min),
        trend_score_min=int(args.trend_score_min),
        mean_reversion_score_min=int(args.mean_reversion_score_min),
    )
    windows = []
    for label, start, end, panel, kind in _parse_windows(args.windows):
        print(f"Evaluating {label}: {start}..{end}")
        windows.append(
            evaluate_window(
                label=label,
                start=start,
                end=end,
                panel=panel,
                kind=kind,
                db_path=db_path,
                initial_value=float(args.initial_value),
                thresholds=thresholds,
                baseline_add_fraction=float(args.baseline_add_fraction),
                mean_reversion_add_fraction=float(args.mean_reversion_add_fraction),
                trend_persistent_add_fraction=(
                    None if args.trend_persistent_add_fraction is None else float(args.trend_persistent_add_fraction)
                ),
                weak_trend_edge_gate=str(args.weak_trend_edge_gate),
                weak_trend_add_fraction=float(args.weak_trend_add_fraction),
                ce_filter=str(args.ce_filter),
                transaction_cost_bps=float(args.transaction_cost_bps),
            )
        )

    totals = {
        "blocked_days": int(sum(w["mean_reversion_no_add"]["blocked_days"] for w in windows)),
        "accelerated_days": int(sum(w["mean_reversion_no_add"].get("accelerated_days", 0) for w in windows)),
        "event_days": int(sum(w["mean_reversion_no_add"].get("event_days", 0) for w in windows)),
        "delta_final_value_sum": float(sum(w["delta_vs_baseline"]["final_value"] for w in windows)),
        "delta_sharpe_sum": float(sum(w["delta_vs_baseline"]["sharpe_ratio"] for w in windows)),
        "delta_max_drawdown_sum": float(sum(w["delta_vs_baseline"]["max_drawdown"] for w in windows)),
        "positive_final_value_windows": int(sum(w["delta_vs_baseline"]["final_value"] > 0.0 for w in windows)),
    }
    return {
        "schema_version": 1,
        "experiment": "00631l_compounding_regime_no_add_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "paper_reference": "/mnt/c/Users/isaac/Downloads/2504.20116v1.pdf",
        "policy": "slow_or_block_incremental_00631l_only_when_compounding_regime_is_MEAN_REVERTING",
        "baseline_add_fraction": float(args.baseline_add_fraction),
        "mean_reversion_add_fraction": float(args.mean_reversion_add_fraction),
        "trend_persistent_add_fraction": args.trend_persistent_add_fraction,
        "weak_trend_edge_gate": str(args.weak_trend_edge_gate),
        "weak_trend_add_fraction": float(args.weak_trend_add_fraction),
        "ce_filter": str(args.ce_filter),
        "transaction_cost_bps": float(args.transaction_cost_bps),
        "thresholds": thresholds.__dict__,
        "windows": windows,
        "totals": totals,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default="default", help="default or semicolon-separated label,start,end,panel,kind")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--baseline-add-fraction",
        type=float,
        default=1.0,
        help="Baseline fraction of requested incremental 00631L add executed each day.",
    )
    parser.add_argument(
        "--mean-reversion-add-fraction",
        type=float,
        default=0.0,
        help="Fraction of requested incremental 00631L add allowed in MEAN_REVERTING; 0=no-add, 1=no guard.",
    )
    parser.add_argument(
        "--trend-persistent-add-fraction",
        type=float,
        default=None,
        help="Fraction of requested incremental 00631L add allowed in TREND_PERSISTENT; default equals baseline.",
    )
    parser.add_argument(
        "--weak-trend-edge-gate",
        choices=("none", "trend_score_eq_min", "relative_momentum_nonpositive", "ce20_negative", "any"),
        default="none",
        help="Use weak-trend add fraction for TREND_PERSISTENT dates with thin edge.",
    )
    parser.add_argument("--weak-trend-add-fraction", type=float, default=0.90)
    parser.add_argument(
        "--ce-filter",
        choices=("none", "ce20_negative", "ce20_or_60_negative", "ce20_and_60_negative"),
        default="none",
        help="Require negative rolling compounding effect before treating MEAN_REVERTING as guarded.",
    )
    parser.add_argument("--transaction-cost-bps", type=float, default=0.0)
    parser.add_argument("--ar1-trend-min", type=float, default=0.05)
    parser.add_argument("--ar1-revert-max", type=float, default=-0.05)
    parser.add_argument("--variance-ratio-trend-min", type=float, default=1.02)
    parser.add_argument("--variance-ratio-revert-max", type=float, default=0.98)
    parser.add_argument("--trend-persistence-min", type=float, default=0.60)
    parser.add_argument("--trend-persistence-revert-max", type=float, default=0.55)
    parser.add_argument("--reversal-speed-revert-min", type=float, default=0.55)
    parser.add_argument("--reversal-speed-trend-max", type=float, default=0.45)
    parser.add_argument("--drawdown-recovery-revert-min", type=float, default=0.50)
    parser.add_argument("--trend-score-min", type=int, default=4)
    parser.add_argument("--mean-reversion-score-min", type=int, default=3)
    args = parser.parse_args()

    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(json.dumps(report["totals"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
