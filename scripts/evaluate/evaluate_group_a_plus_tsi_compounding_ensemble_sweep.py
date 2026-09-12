#!/usr/bin/env python3
"""Sweep TSI severity caps on the compounding staged 00631L shadow.

Research-only follow-up for arXiv:2608.10788. This keeps the stronger
compounding staged add-speed policy as the baseline candidate and tests whether
TSI stress should cap trend-persistent 00631L adds.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices
from group_a_plus.integrations.leveraged_compounding_regime import (
    TREND_PERSISTENT,
    build_compounding_features,
    classify_compounding_regime,
)
from group_a_plus.integrations.triadic_stress_index import (
    DEFAULT_ALPHA_DOWN,
    DEFAULT_ALPHA_UP,
    DEFAULT_MIN_OBSERVATIONS,
    DEFAULT_TICKER_SOURCES,
    DEFAULT_WINDOW_DAYS,
    load_tsi_price_panel,
    rolling_tsi_frame,
)
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_00631l_compounding_regime_no_add_shadow import (
    _metric_delta,
    _simulate_speed_baseline,
    simulate_no_add_guard,
)
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import _resolve_end_date, _targets_from_report
from scripts.evaluate.evaluate_group_a_plus_tsi_compounding_ensemble_shadow import DEFAULT_WINDOWS, _float, _thresholds
from scripts.evaluate.evaluate_group_a_plus_tsi_no_add_shadow import _parse_windows, _resolve


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/tsi_compounding_ensemble_sweep.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/tsi_compounding_ensemble_sweep.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/tsi_compounding_ensemble_sweep/history"


def _parse_floats(raw: str) -> list[float]:
    values = [float(item.strip()) for item in raw.split(",") if item.strip()]
    if not values:
        raise ValueError("Expected at least one numeric value")
    return values


def _tsi_percentile_for_window(
    *,
    db_path: Path,
    start: str,
    end: str,
    warmup_days: int,
    tsi_window_days: int = DEFAULT_WINDOW_DAYS,
    tsi_min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    tsi_alpha_up: float = DEFAULT_ALPHA_UP,
    tsi_alpha_down: float = DEFAULT_ALPHA_DOWN,
) -> pd.Series:
    warmup_start = (pd.Timestamp(start) - pd.Timedelta(days=int(warmup_days))).date().isoformat()
    prices, _status = load_tsi_price_panel(
        db_path=db_path,
        start=warmup_start,
        end=end,
        ticker_sources=DEFAULT_TICKER_SOURCES,
    )
    frame, _metrics = rolling_tsi_frame(
        prices,
        window_days=int(tsi_window_days),
        min_observations=int(tsi_min_observations),
        alpha_up=float(tsi_alpha_up),
        alpha_down=float(tsi_alpha_down),
    )
    if frame.empty or "tsi_memory_percentile" not in frame:
        return pd.Series(dtype=float, name="tsi_memory_percentile")
    out = frame["tsi_memory_percentile"].astype(float)
    out.name = "tsi_memory_percentile"
    return out.loc[(out.index >= pd.Timestamp(start)) & (out.index <= pd.Timestamp(end))]


def _prepare_window(
    *,
    label: str,
    start: str,
    end: str,
    panel: str,
    kind: str,
    db_path: Path,
    initial_value: float,
    transaction_cost_bps: float,
    warmup_days: int,
    tsi_window_days: int,
    tsi_min_observations: int,
    tsi_alpha_up: float,
    tsi_alpha_down: float,
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
    classified = classify_compounding_regime(features, thresholds=_thresholds())
    regimes = classified["compounding_regime"].reindex(prices.index).fillna("TRANSITIONAL")
    tsi_percentile = _tsi_percentile_for_window(
        db_path=db_path,
        start=start,
        end=resolved_end,
        warmup_days=warmup_days,
        tsi_window_days=tsi_window_days,
        tsi_min_observations=tsi_min_observations,
        tsi_alpha_up=tsi_alpha_up,
        tsi_alpha_down=tsi_alpha_down,
    ).reindex(prices.index)
    baseline = _simulate_speed_baseline(prices, target_weights, initial_value, 0.4, transaction_cost_bps)
    compounding = simulate_no_add_guard(
        prices=prices,
        target_weights=target_weights,
        regimes=regimes,
        initial_value=initial_value,
        baseline_add_fraction=0.4,
        mean_reversion_add_fraction=0.0,
        trend_persistent_add_fraction=1.0,
        transaction_cost_bps=transaction_cost_bps,
    )
    return {
        "label": label,
        "kind": kind,
        "window": {"start": start, "end": resolved_end, "rows": int(len(prices))},
        "prices": prices,
        "target_weights": target_weights,
        "regimes": regimes,
        "tsi_percentile": tsi_percentile,
        "baseline_speed40": baseline,
        "compounding_staged": compounding,
    }


def _combo_window(prepared: dict[str, Any], *, threshold: float, cap: float, initial_value: float, transaction_cost_bps: float) -> dict[str, Any]:
    prices = prepared["prices"]
    regimes = prepared["regimes"]
    tsi_alert = prepared["tsi_percentile"].astype(float) >= float(threshold)
    trend_alert = (regimes == TREND_PERSISTENT) & tsi_alert.fillna(False)
    trend_add_by_date = pd.Series(1.0, index=prices.index)
    trend_add_by_date.loc[trend_alert] = float(cap)
    ensemble = simulate_no_add_guard(
        prices=prices,
        target_weights=prepared["target_weights"],
        regimes=regimes,
        initial_value=initial_value,
        baseline_add_fraction=0.4,
        mean_reversion_add_fraction=0.0,
        trend_persistent_add_fraction=1.0,
        trend_persistent_add_fraction_by_date=trend_add_by_date,
        transaction_cost_bps=transaction_cost_bps,
    )
    return {
        "label": prepared["label"],
        "kind": prepared["kind"],
        "window": prepared["window"],
        "tsi_alert_days": int(tsi_alert.fillna(False).sum()),
        "trend_persistent_tsi_alert_days": int(trend_alert.sum()),
        "ensemble_delta_vs_speed40": _metric_delta(ensemble, prepared["baseline_speed40"]),
        "ensemble_delta_vs_compounding": _metric_delta(ensemble, prepared["compounding_staged"]),
    }


def _summarize_combo(windows: list[dict[str, Any]], *, threshold: float, cap: float) -> dict[str, Any]:
    return {
        "threshold": float(threshold),
        "tsi_trend_cap": float(cap),
        "tsi_alert_days": int(sum(item["tsi_alert_days"] for item in windows)),
        "trend_persistent_tsi_alert_days": int(sum(item["trend_persistent_tsi_alert_days"] for item in windows)),
        "ensemble_minus_compounding_final_value_sum": float(
            sum(item["ensemble_delta_vs_compounding"]["final_value"] for item in windows)
        ),
        "ensemble_minus_compounding_sharpe_sum": float(sum(item["ensemble_delta_vs_compounding"]["sharpe_ratio"] for item in windows)),
        "ensemble_minus_compounding_max_drawdown_sum": float(
            sum(item["ensemble_delta_vs_compounding"]["max_drawdown"] for item in windows)
        ),
        "ensemble_positive_vs_compounding_windows": int(
            sum(item["ensemble_delta_vs_compounding"]["final_value"] > 0.0 for item in windows)
        ),
        "ensemble_non_worse_drawdown_vs_compounding_windows": int(
            sum(item["ensemble_delta_vs_compounding"]["max_drawdown"] >= 0.0 for item in windows)
        ),
    }


def build_sweep(
    *,
    db_path: Path,
    windows: list[tuple[str, str, str, str, str]],
    thresholds: list[float],
    caps: list[float],
    initial_value: float,
    transaction_cost_bps: float,
    warmup_days: int,
    tsi_window_days: int = DEFAULT_WINDOW_DAYS,
    tsi_min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    tsi_alpha_up: float = DEFAULT_ALPHA_UP,
    tsi_alpha_down: float = DEFAULT_ALPHA_DOWN,
) -> dict[str, Any]:
    prepared = [
        _prepare_window(
            label=label,
            start=start,
            end=end,
            panel=panel,
            kind=kind,
            db_path=db_path,
            initial_value=initial_value,
            transaction_cost_bps=transaction_cost_bps,
            warmup_days=warmup_days,
            tsi_window_days=int(tsi_window_days),
            tsi_min_observations=int(tsi_min_observations),
            tsi_alpha_up=float(tsi_alpha_up),
            tsi_alpha_down=float(tsi_alpha_down),
        )
        for label, start, end, panel, kind in windows
    ]
    combos: list[dict[str, Any]] = []
    for threshold in thresholds:
        for cap in caps:
            combo_windows = [
                _combo_window(item, threshold=threshold, cap=cap, initial_value=initial_value, transaction_cost_bps=transaction_cost_bps)
                for item in prepared
            ]
            summary = _summarize_combo(combo_windows, threshold=threshold, cap=cap)
            combos.append({**summary, "windows": combo_windows})
    best_by_final = max(combos, key=lambda item: item["ensemble_minus_compounding_final_value_sum"])
    best_by_drawdown = max(combos, key=lambda item: item["ensemble_minus_compounding_max_drawdown_sum"])
    best_by_coverage = max(
        combos,
        key=lambda item: (
            item["ensemble_positive_vs_compounding_windows"],
            item["ensemble_non_worse_drawdown_vs_compounding_windows"],
            item["ensemble_minus_compounding_final_value_sum"],
        ),
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_tsi_compounding_ensemble_sweep",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": "2608.10788",
        "research_only": True,
        "production_effect": "none",
        "thresholds": thresholds,
        "tsi_trend_caps": caps,
        "tsi_parameters": {
            "window_days": int(tsi_window_days),
            "min_observations": int(tsi_min_observations),
            "alpha_up": float(tsi_alpha_up),
            "alpha_down": float(tsi_alpha_down),
        },
        "summaries": [{key: value for key, value in item.items() if key != "windows"} for item in combos],
        "combo_windows": [
            {
                "threshold": item["threshold"],
                "tsi_trend_cap": item["tsi_trend_cap"],
                "windows": item["windows"],
            }
            for item in combos
        ],
        "best_by_final_value": {key: value for key, value in best_by_final.items() if key != "windows"},
        "best_by_drawdown": {key: value for key, value in best_by_drawdown.items() if key != "windows"},
        "best_by_window_coverage": {key: value for key, value in best_by_coverage.items() if key != "windows"},
        "best_final_value_windows": best_by_final["windows"],
        "blocking_reasons": [
            "research_only_no_live_weight_change",
            "tsi_auxiliary_severity_not_promoted",
            "requires_stability_across_windows_before_promotion",
        ],
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    rows = []
    for item in payload.get("summaries") or []:
        rows.append(
            "| {threshold:.2f} | {cap:.2f} | {alerts} | {trend_alerts} | {dfv:,.0f} | {dsharpe:.4f} | {dmdd:.2%} | {positive} | {mdd_ok} |".format(
                threshold=_float(item.get("threshold")),
                cap=_float(item.get("tsi_trend_cap")),
                alerts=int(item.get("tsi_alert_days") or 0),
                trend_alerts=int(item.get("trend_persistent_tsi_alert_days") or 0),
                dfv=_float(item.get("ensemble_minus_compounding_final_value_sum")),
                dsharpe=_float(item.get("ensemble_minus_compounding_sharpe_sum")),
                dmdd=_float(item.get("ensemble_minus_compounding_max_drawdown_sum")),
                positive=int(item.get("ensemble_positive_vs_compounding_windows") or 0),
                mdd_ok=int(item.get("ensemble_non_worse_drawdown_vs_compounding_windows") or 0),
            )
        )
    return """# GroupA+ TSI Compounding Ensemble Sweep

- status: `research_only`
- production_effect: `none`
- promotion_allowed: `{promotion}`

## Summary

| threshold | trend_cap | tsi_alert_days | trend_alert_days | delta_final_value_vs_compounding | delta_sharpe | delta_max_drawdown | positive_windows | non_worse_mdd_windows |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{rows}

## Best By Final Value

```json
{best_final}
```

## Best By Drawdown

```json
{best_drawdown}
```

## Best By Window Coverage

```json
{best_coverage}
```

## Governance

This is a sweep-only shadow. It does not change Golden1_0531, target weights,
execution regimes, or live 00631L permission.
""".format(
        promotion=payload.get("decision", {}).get("promotion_allowed"),
        rows="\n".join(rows) if rows else "| - | - | - | - | - | - | - | - | - |",
        best_final=json.dumps(payload.get("best_by_final_value") or {}, ensure_ascii=False, indent=2),
        best_drawdown=json.dumps(payload.get("best_by_drawdown") or {}, ensure_ascii=False, indent=2),
        best_coverage=json.dumps(payload.get("best_by_window_coverage") or {}, ensure_ascii=False, indent=2),
    )


def write_sweep(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(payload), encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    (history_dir / f"tsi_compounding_ensemble_sweep_{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default=DEFAULT_WINDOWS)
    parser.add_argument("--thresholds", default="0.75,0.80,0.85,0.90,0.95")
    parser.add_argument("--caps", default="0.0,0.25,0.50,0.75")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--transaction-cost-bps", type=float, default=0.0)
    parser.add_argument("--warmup-days", type=int, default=420)
    parser.add_argument("--tsi-window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--tsi-min-observations", type=int, default=DEFAULT_MIN_OBSERVATIONS)
    parser.add_argument("--tsi-alpha-up", type=float, default=DEFAULT_ALPHA_UP)
    parser.add_argument("--tsi-alpha-down", type=float, default=DEFAULT_ALPHA_DOWN)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_sweep(
        db_path=_resolve(args.db),
        windows=_parse_windows(args.windows),
        thresholds=_parse_floats(args.thresholds),
        caps=_parse_floats(args.caps),
        initial_value=float(args.initial_value),
        transaction_cost_bps=float(args.transaction_cost_bps),
        warmup_days=int(args.warmup_days),
        tsi_window_days=int(args.tsi_window_days),
        tsi_min_observations=int(args.tsi_min_observations),
        tsi_alpha_up=float(args.tsi_alpha_up),
        tsi_alpha_down=float(args.tsi_alpha_down),
    )
    write_sweep(payload, _resolve(args.output), _resolve(args.output_md), None if args.no_history else _resolve(args.history_dir))
    print(f"TSI compounding ensemble sweep: {_resolve(args.output)}")
    print(json.dumps(payload["best_by_final_value"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
