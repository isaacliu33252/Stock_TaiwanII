#!/usr/bin/env python3
"""Transaction-cost sensitivity for the TSI compounding ensemble shadow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_group_a_plus_tsi_compounding_ensemble_shadow import DEFAULT_WINDOWS
from scripts.evaluate.evaluate_group_a_plus_tsi_compounding_ensemble_sweep import build_sweep
from scripts.evaluate.evaluate_group_a_plus_tsi_compounding_ensemble_sweep import _float, _parse_floats
from scripts.evaluate.evaluate_group_a_plus_tsi_no_add_shadow import _parse_windows, _resolve
from scripts.evaluate.validate_group_a_plus_tsi_compounding_ensemble_temporal_oos import (
    DEFAULT_FOLDS,
    _parse_folds,
    build_temporal_oos_validation,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/tsi_compounding_ensemble_cost_sensitivity.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/tsi_compounding_ensemble_cost_sensitivity.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/tsi_compounding_ensemble_cost_sensitivity/history"


def _cost_summary(cost_bps: float, sweep: dict[str, Any], temporal_oos: dict[str, Any]) -> dict[str, Any]:
    best = sweep.get("best_by_final_value") or {}
    return {
        "transaction_cost_bps": float(cost_bps),
        "best_threshold": _float(best.get("threshold")),
        "best_tsi_trend_cap": _float(best.get("tsi_trend_cap")),
        "best_delta_final_value_vs_compounding": _float(best.get("ensemble_minus_compounding_final_value_sum")),
        "best_delta_sharpe_vs_compounding": _float(best.get("ensemble_minus_compounding_sharpe_sum")),
        "best_delta_max_drawdown_vs_compounding": _float(best.get("ensemble_minus_compounding_max_drawdown_sum")),
        "best_positive_windows": int(best.get("ensemble_positive_vs_compounding_windows") or 0),
        "best_non_worse_drawdown_windows": int(best.get("ensemble_non_worse_drawdown_vs_compounding_windows") or 0),
        "temporal_oos_passed": temporal_oos.get("decision", {}).get("temporal_oos_passed") is True,
        "temporal_oos_blocking_reasons": list(temporal_oos.get("blocking_reasons") or []),
    }


def build_cost_sensitivity(
    *,
    db_path: Path,
    windows: list[tuple[str, str, str, str, str]],
    thresholds: list[float],
    caps: list[float],
    costs_bps: list[float],
    folds: list[dict[str, Any]],
    initial_value: float,
    warmup_days: int,
) -> dict[str, Any]:
    results = []
    for cost_bps in costs_bps:
        sweep = build_sweep(
            db_path=db_path,
            windows=windows,
            thresholds=thresholds,
            caps=caps,
            initial_value=initial_value,
            transaction_cost_bps=float(cost_bps),
            warmup_days=warmup_days,
        )
        temporal_oos = build_temporal_oos_validation(sweep, folds)
        results.append(
            {
                "transaction_cost_bps": float(cost_bps),
                "summary": _cost_summary(float(cost_bps), sweep, temporal_oos),
                "best_by_final_value": sweep.get("best_by_final_value") or {},
                "temporal_oos_decision": temporal_oos.get("decision") or {},
                "temporal_oos_folds": temporal_oos.get("folds") or [],
            }
        )
    blockers = ["research_only_no_live_weight_change", "cost_sensitivity_not_promoted"]
    if not all(item["summary"]["temporal_oos_passed"] for item in results):
        blockers.append("temporal_oos_not_passed_under_all_costs")
    if not all(item["summary"]["best_delta_final_value_vs_compounding"] > 0.0 for item in results):
        blockers.append("best_sweep_not_positive_under_all_costs")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_tsi_compounding_ensemble_cost_sensitivity",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": "2608.10788",
        "research_only": True,
        "production_effect": "none",
        "costs_bps": [float(item) for item in costs_bps],
        "results": results,
        "summaries": [item["summary"] for item in results],
        "blocking_reasons": blockers,
        "decision": {
            "cost_sensitivity_passed": len(blockers) == 2,
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    rows = []
    for item in payload.get("summaries") or []:
        rows.append(
            "| {cost:.1f} | {threshold:.2f} | {cap:.2f} | {dfv:,.0f} | {dsharpe:.4f} | {dmdd:.2%} | {pos} | {mdd_ok} | {oos} |".format(
                cost=_float(item.get("transaction_cost_bps")),
                threshold=_float(item.get("best_threshold")),
                cap=_float(item.get("best_tsi_trend_cap")),
                dfv=_float(item.get("best_delta_final_value_vs_compounding")),
                dsharpe=_float(item.get("best_delta_sharpe_vs_compounding")),
                dmdd=_float(item.get("best_delta_max_drawdown_vs_compounding")),
                pos=int(item.get("best_positive_windows") or 0),
                mdd_ok=int(item.get("best_non_worse_drawdown_windows") or 0),
                oos=item.get("temporal_oos_passed"),
            )
        )
    return """# GroupA+ TSI Compounding Ensemble Cost Sensitivity

- status: `research_only`
- production_effect: `none`
- cost_sensitivity_passed: `{passed}`
- promotion_allowed: `{promotion}`

## Summary

| cost_bps | best_threshold | best_cap | best_delta_final_value | best_delta_sharpe | best_delta_max_drawdown | positive_windows | non_worse_mdd_windows | temporal_oos_passed |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{rows}

## Blocking Reasons

```json
{blockers}
```

## Governance

This cost sensitivity is research-only. It does not change Golden1_0531,
target weights, execution regimes, or live 00631L permission.
""".format(
        passed=payload.get("decision", {}).get("cost_sensitivity_passed"),
        promotion=payload.get("decision", {}).get("promotion_allowed"),
        rows="\n".join(rows) if rows else "| - | - | - | - | - | - | - | - | - |",
        blockers=json.dumps(payload.get("blocking_reasons") or [], ensure_ascii=False, indent=2),
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
    (history_dir / f"tsi_compounding_ensemble_cost_sensitivity_{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default=DEFAULT_WINDOWS)
    parser.add_argument("--thresholds", default="0.75,0.80,0.85,0.90,0.95")
    parser.add_argument("--caps", default="0.0,0.25,0.50,0.75")
    parser.add_argument("--costs-bps", default="0,5,10")
    parser.add_argument("--folds", default=DEFAULT_FOLDS)
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--warmup-days", type=int, default=420)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_cost_sensitivity(
        db_path=_resolve(args.db),
        windows=_parse_windows(args.windows),
        thresholds=_parse_floats(args.thresholds),
        caps=_parse_floats(args.caps),
        costs_bps=_parse_floats(args.costs_bps),
        folds=_parse_folds(args.folds),
        initial_value=float(args.initial_value),
        warmup_days=int(args.warmup_days),
    )
    write_report(payload, _resolve(args.output), _resolve(args.output_md), None if args.no_history else _resolve(args.history_dir))
    print(f"TSI compounding ensemble cost sensitivity: {_resolve(args.output)}")
    print(json.dumps(payload["decision"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
