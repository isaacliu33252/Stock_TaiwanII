#!/usr/bin/env python3
"""Evaluate TSI as a severity cap on the compounding add-speed shadow.

Research-only. The base candidate is the prior compounding staged policy:
baseline add 40%, mean-reverting add 0%, trend-persistent add 100%. This
script tests whether TSI stress should cap trend-persistent add speed to 50%.
It never changes live target weights or execution guards.
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

from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices
from backtest_group_a_plus_policy_signal import TICKERS
from group_a_plus.integrations.leveraged_compounding_regime import (
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
from scripts.evaluate.evaluate_00631l_compounding_regime_no_add_shadow import (
    _metric_delta,
    _simulate_speed_baseline,
    simulate_no_add_guard,
)
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import PANEL_2025_2026, _resolve_end_date, _targets_from_report
from scripts.evaluate.evaluate_group_a_plus_tsi_no_add_shadow import _parse_windows, _resolve, _tsi_alert_for_window


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/tsi_compounding_ensemble_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/tsi_compounding_ensemble_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/tsi_compounding_ensemble_shadow/history"
DEFAULT_WINDOWS = (
    "covid_2020,2020-01-02,2020-12-31,results/ncf_00631l_panel_backfill_2020_20260716.csv,out_of_sample;"
    "recovery_2021,2021-01-04,2021-12-30,results/ncf_00631l_panel_backfill_2021_20260726.csv,out_of_sample;"
    "rate_hike_2022,2022-01-03,2022-10-31,results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv,out_of_sample;"
    "rebound_2023,2023-01-03,2023-12-29,results/ncf_00631l_panel_backfill_2023_20260726.csv,out_of_sample;"
    "full_2024,2024-01-02,2024-12-31,results/ncf_00631l_panel_backfill_2024_20260726.csv,out_of_sample;"
    f"active_2025_2026,2025-01-02,latest,{PANEL_2025_2026},tuning_window;"
    f"taiwan_2026_q1q2_stress,2026-02-02,2026-04-30,{PANEL_2025_2026},stress_window;"
    f"taiwan_2026_recent,2026-05-15,latest,{PANEL_2025_2026},recent_window"
)


def _float(value: Any) -> float:
    out = float(value)
    return out if np.isfinite(out) else 0.0


def _thresholds() -> CompoundingRegimeThresholds:
    return CompoundingRegimeThresholds(ar1_revert_max=-0.15, mean_reversion_score_min=5)


def _window_report(
    *,
    label: str,
    start: str,
    end: str,
    panel: str,
    kind: str,
    db_path: Path,
    initial_value: float,
    tsi_threshold: float,
    tsi_trend_cap: float,
    transaction_cost_bps: float,
    warmup_days: int,
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
    tsi_alert = _tsi_alert_for_window(
        db_path=db_path,
        start=start,
        end=resolved_end,
        threshold=tsi_threshold,
        warmup_days=warmup_days,
    ).astype(bool).reindex(prices.index, fill_value=False)

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
    trend_add_by_date = pd.Series(1.0, index=prices.index)
    trend_add_by_date.loc[(regimes == TREND_PERSISTENT) & tsi_alert] = float(tsi_trend_cap)
    ensemble = simulate_no_add_guard(
        prices=prices,
        target_weights=target_weights,
        regimes=regimes,
        initial_value=initial_value,
        baseline_add_fraction=0.4,
        mean_reversion_add_fraction=0.0,
        trend_persistent_add_fraction=1.0,
        trend_persistent_add_fraction_by_date=trend_add_by_date,
        transaction_cost_bps=transaction_cost_bps,
    )
    return {
        "label": label,
        "kind": kind,
        "window": {"start": start, "end": resolved_end, "rows": int(len(prices))},
        "tsi_alert_days": int(tsi_alert.sum()),
        "trend_persistent_tsi_alert_days": int(((regimes == TREND_PERSISTENT) & tsi_alert).sum()),
        "baseline_speed40": baseline,
        "compounding_staged": compounding,
        "tsi_compounding_ensemble": ensemble,
        "compounding_delta_vs_speed40": _metric_delta(compounding, baseline),
        "ensemble_delta_vs_speed40": _metric_delta(ensemble, baseline),
        "ensemble_delta_vs_compounding": _metric_delta(ensemble, compounding),
    }


def build_report(
    *,
    db_path: Path,
    windows: list[tuple[str, str, str, str, str]],
    initial_value: float,
    tsi_threshold: float,
    tsi_trend_cap: float,
    transaction_cost_bps: float,
    warmup_days: int,
) -> dict[str, Any]:
    reports = [
        _window_report(
            label=label,
            start=start,
            end=end,
            panel=panel,
            kind=kind,
            db_path=db_path,
            initial_value=initial_value,
            tsi_threshold=tsi_threshold,
            tsi_trend_cap=tsi_trend_cap,
            transaction_cost_bps=transaction_cost_bps,
            warmup_days=warmup_days,
        )
        for label, start, end, panel, kind in windows
    ]
    totals = {
        "tsi_alert_days": int(sum(item["tsi_alert_days"] for item in reports)),
        "trend_persistent_tsi_alert_days": int(sum(item["trend_persistent_tsi_alert_days"] for item in reports)),
        "compounding_delta_final_value_sum": float(sum(item["compounding_delta_vs_speed40"]["final_value"] for item in reports)),
        "ensemble_delta_final_value_sum": float(sum(item["ensemble_delta_vs_speed40"]["final_value"] for item in reports)),
        "ensemble_minus_compounding_final_value_sum": float(sum(item["ensemble_delta_vs_compounding"]["final_value"] for item in reports)),
        "ensemble_minus_compounding_sharpe_sum": float(sum(item["ensemble_delta_vs_compounding"]["sharpe_ratio"] for item in reports)),
        "ensemble_minus_compounding_max_drawdown_sum": float(sum(item["ensemble_delta_vs_compounding"]["max_drawdown"] for item in reports)),
        "ensemble_positive_vs_compounding_windows": int(sum(item["ensemble_delta_vs_compounding"]["final_value"] > 0.0 for item in reports)),
        "ensemble_non_worse_drawdown_vs_compounding_windows": int(
            sum(item["ensemble_delta_vs_compounding"]["max_drawdown"] >= 0.0 for item in reports)
        ),
    }
    blockers = ["research_only_no_live_weight_change", "tsi_auxiliary_severity_not_promoted"]
    if totals["ensemble_positive_vs_compounding_windows"] < len(reports):
        blockers.append("ensemble_not_positive_vs_compounding_in_all_windows")
    if totals["ensemble_minus_compounding_final_value_sum"] <= 0.0:
        blockers.append("ensemble_does_not_improve_total_final_value_vs_compounding")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_tsi_compounding_ensemble_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": "2608.10788",
        "research_only": True,
        "production_effect": "none",
        "policy": "compounding_staged_with_tsi_trend_persistent_add_cap_shadow",
        "tsi_threshold": float(tsi_threshold),
        "tsi_trend_cap": float(tsi_trend_cap),
        "windows": reports,
        "totals": totals,
        "blocking_reasons": blockers,
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
    for item in payload.get("windows") or []:
        delta = item.get("ensemble_delta_vs_compounding") or {}
        rows.append(
            "| {label} | {alerts} | {trend_alerts} | {dfv:,.0f} | {dsharpe:.4f} | {dmdd:.2%} |".format(
                label=item.get("label"),
                alerts=int(item.get("tsi_alert_days") or 0),
                trend_alerts=int(item.get("trend_persistent_tsi_alert_days") or 0),
                dfv=_float(delta.get("final_value")),
                dsharpe=_float(delta.get("sharpe_ratio")),
                dmdd=_float(delta.get("max_drawdown")),
            )
        )
    return """# GroupA+ TSI Compounding Ensemble Shadow

- status: `research_only`
- policy: `{policy}`
- tsi_threshold: `{threshold}`
- tsi_trend_cap: `{cap}`
- promotion_allowed: `{promotion}`

## Ensemble Vs Compounding Staged

| window | tsi_alert_days | trend_persistent_tsi_alert_days | delta_final_value | delta_sharpe | delta_max_drawdown |
|---|---:|---:|---:|---:|---:|
{rows}

## Totals

```json
{totals}
```

## Governance

This is an ensemble shadow only. It does not change Golden1_0531, target
weights, execution regimes, or live 00631L permission.
""".format(
        policy=payload.get("policy"),
        threshold=payload.get("tsi_threshold"),
        cap=payload.get("tsi_trend_cap"),
        promotion=payload.get("decision", {}).get("promotion_allowed"),
        rows="\n".join(rows) if rows else "| - | - | - | - | - | - |",
        totals=json.dumps(payload.get("totals") or {}, ensure_ascii=False, indent=2),
    )


def write_report(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(payload), encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    (history_dir / f"tsi_compounding_ensemble_shadow_{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default=DEFAULT_WINDOWS)
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--tsi-threshold", type=float, default=0.80)
    parser.add_argument("--tsi-trend-cap", type=float, default=0.50)
    parser.add_argument("--transaction-cost-bps", type=float, default=0.0)
    parser.add_argument("--warmup-days", type=int, default=420)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_report(
        db_path=_resolve(args.db),
        windows=_parse_windows(args.windows),
        initial_value=float(args.initial_value),
        tsi_threshold=float(args.tsi_threshold),
        tsi_trend_cap=float(args.tsi_trend_cap),
        transaction_cost_bps=float(args.transaction_cost_bps),
        warmup_days=int(args.warmup_days),
    )
    write_report(payload, _resolve(args.output), _resolve(args.output_md), None if args.no_history else _resolve(args.history_dir))
    print(f"TSI compounding ensemble shadow: {_resolve(args.output)}")
    print(json.dumps(payload["totals"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
