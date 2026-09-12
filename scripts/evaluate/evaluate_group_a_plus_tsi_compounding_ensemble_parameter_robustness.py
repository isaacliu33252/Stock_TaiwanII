#!/usr/bin/env python3
"""TSI parameter robustness for the compounding ensemble shadow."""

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


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/tsi_compounding_ensemble_parameter_robustness.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/tsi_compounding_ensemble_parameter_robustness.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/tsi_compounding_ensemble_parameter_robustness/history"
DEFAULT_VARIANTS = (
    "default,20,12,0.60,0.08;"
    "short_window,15,10,0.60,0.08;"
    "long_window,30,18,0.60,0.08;"
    "fast_memory,20,12,0.80,0.15;"
    "slow_memory,20,12,0.40,0.04"
)


def _parse_variants(raw: str) -> list[dict[str, Any]]:
    variants = []
    for item in raw.split(";"):
        if not item.strip():
            continue
        parts = [part.strip() for part in item.split(",")]
        if len(parts) != 5:
            raise ValueError("Each variant must be label,window_days,min_observations,alpha_up,alpha_down")
        variants.append(
            {
                "label": parts[0],
                "window_days": int(parts[1]),
                "min_observations": int(parts[2]),
                "alpha_up": float(parts[3]),
                "alpha_down": float(parts[4]),
            }
        )
    if not variants:
        raise ValueError("Expected at least one TSI parameter variant")
    return variants


def _variant_summary(variant: dict[str, Any], sweep: dict[str, Any], temporal_oos: dict[str, Any]) -> dict[str, Any]:
    best = sweep.get("best_by_final_value") or {}
    return {
        "variant": variant["label"],
        "window_days": int(variant["window_days"]),
        "min_observations": int(variant["min_observations"]),
        "alpha_up": float(variant["alpha_up"]),
        "alpha_down": float(variant["alpha_down"]),
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


def build_parameter_robustness(
    *,
    db_path: Path,
    windows: list[tuple[str, str, str, str, str]],
    thresholds: list[float],
    caps: list[float],
    variants: list[dict[str, Any]],
    folds: list[dict[str, Any]],
    initial_value: float,
    transaction_cost_bps: float,
    warmup_days: int,
) -> dict[str, Any]:
    results = []
    for variant in variants:
        sweep = build_sweep(
            db_path=db_path,
            windows=windows,
            thresholds=thresholds,
            caps=caps,
            initial_value=initial_value,
            transaction_cost_bps=transaction_cost_bps,
            warmup_days=warmup_days,
            tsi_window_days=int(variant["window_days"]),
            tsi_min_observations=int(variant["min_observations"]),
            tsi_alpha_up=float(variant["alpha_up"]),
            tsi_alpha_down=float(variant["alpha_down"]),
        )
        temporal_oos = build_temporal_oos_validation(sweep, folds)
        results.append(
            {
                "variant": variant,
                "summary": _variant_summary(variant, sweep, temporal_oos),
                "best_by_final_value": sweep.get("best_by_final_value") or {},
                "temporal_oos_decision": temporal_oos.get("decision") or {},
                "temporal_oos_folds": temporal_oos.get("folds") or [],
            }
        )
    blockers = ["research_only_no_live_weight_change", "parameter_robustness_not_promoted"]
    if not all(item["summary"]["temporal_oos_passed"] for item in results):
        blockers.append("temporal_oos_not_passed_under_all_tsi_parameter_variants")
    if not all(item["summary"]["best_delta_final_value_vs_compounding"] > 0.0 for item in results):
        blockers.append("best_sweep_not_positive_under_all_tsi_parameter_variants")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_tsi_compounding_ensemble_parameter_robustness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": "2608.10788",
        "research_only": True,
        "production_effect": "none",
        "results": results,
        "summaries": [item["summary"] for item in results],
        "blocking_reasons": blockers,
        "decision": {
            "parameter_robustness_passed": len(blockers) == 2,
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
            "| {variant} | {window} | {aup:.2f} | {adown:.2f} | {threshold:.2f} | {cap:.2f} | {dfv:,.0f} | {dsharpe:.4f} | {dmdd:.2%} | {pos} | {mdd_ok} | {oos} |".format(
                variant=item.get("variant"),
                window=int(item.get("window_days") or 0),
                aup=_float(item.get("alpha_up")),
                adown=_float(item.get("alpha_down")),
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
    return """# GroupA+ TSI Compounding Ensemble Parameter Robustness

- status: `research_only`
- production_effect: `none`
- parameter_robustness_passed: `{passed}`
- promotion_allowed: `{promotion}`

## Summary

| variant | window | alpha_up | alpha_down | best_threshold | best_cap | best_delta_final_value | best_delta_sharpe | best_delta_max_drawdown | positive_windows | non_worse_mdd_windows | temporal_oos_passed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{rows}

## Blocking Reasons

```json
{blockers}
```

## Governance

This parameter robustness check is research-only. It does not change
Golden1_0531, target weights, execution regimes, or live 00631L permission.
""".format(
        passed=payload.get("decision", {}).get("parameter_robustness_passed"),
        promotion=payload.get("decision", {}).get("promotion_allowed"),
        rows="\n".join(rows) if rows else "| - | - | - | - | - | - | - | - | - | - | - | - |",
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
    (history_dir / f"tsi_compounding_ensemble_parameter_robustness_{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default=DEFAULT_WINDOWS)
    parser.add_argument("--thresholds", default="0.75,0.80,0.85,0.90,0.95")
    parser.add_argument("--caps", default="0.0,0.25,0.50,0.75")
    parser.add_argument("--variants", default=DEFAULT_VARIANTS)
    parser.add_argument("--folds", default=DEFAULT_FOLDS)
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--transaction-cost-bps", type=float, default=0.0)
    parser.add_argument("--warmup-days", type=int, default=420)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_parameter_robustness(
        db_path=_resolve(args.db),
        windows=_parse_windows(args.windows),
        thresholds=_parse_floats(args.thresholds),
        caps=_parse_floats(args.caps),
        variants=_parse_variants(args.variants),
        folds=_parse_folds(args.folds),
        initial_value=float(args.initial_value),
        transaction_cost_bps=float(args.transaction_cost_bps),
        warmup_days=int(args.warmup_days),
    )
    write_report(payload, _resolve(args.output), _resolve(args.output_md), None if args.no_history else _resolve(args.history_dir))
    print(f"TSI compounding ensemble parameter robustness: {_resolve(args.output)}")
    print(json.dumps(payload["decision"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
