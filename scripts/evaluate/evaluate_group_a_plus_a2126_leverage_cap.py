#!/usr/bin/env python3
"""Evaluate A21.26 golden1 00631L leverage cap with tuning and OOS windows.

This formalizes the old a2126 shadow checks under the same standard used by the
2026-07-10 A22/a2124 work: run the original four tuning windows and the
backfilled 2017/2018/2019 out-of-sample years in one pass. Research-only; does
not touch live signals or target weights.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.runners.a2118 import CHIP_DATA_FALLBACK_MAX_STALE_DAYS, run_a2118
from group_a_plus.runners.a2126 import (
    A2126_EFFECTIVE_MAX_00631L_WEIGHT,
    A2126_LEGACY_MAX_00631L_WEIGHT,
    run_a2126,
)

PANEL_2025_2026 = "results/ncf_00631l_panel_latest_20260707.csv"
PANEL_2017_2019 = "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"

WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31", PANEL_2025_2026, "tuning_window"),
    ("inflation_2022", "2022-01-03", "2022-12-30", PANEL_2025_2026, "tuning_window"),
    ("live_2024_2026", "2024-01-02", "2026-07-09", PANEL_2025_2026, "tuning_window"),
    ("active_2025_2026", "2025-01-02", "2026-07-09", PANEL_2025_2026, "tuning_window"),
    ("2017_bull", "2017-01-03", "2017-12-29", PANEL_2017_2019, "out_of_sample"),
    ("2018_correction", "2018-01-02", "2018-12-31", PANEL_2017_2019, "out_of_sample"),
    ("2019_recovery", "2019-01-02", "2019-12-31", PANEL_2017_2019, "out_of_sample"),
]

COMMON_KW = dict(
    h20_max=0.33,
    conf_min=0.55,
    h5_reentry_min=0.55,
    chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
)

VARIANTS = {
    "legacy_cap_015": dict(
        max_00631l_weight=A2126_LEGACY_MAX_00631L_WEIGHT,
        tail_risk_score_min=1,
        realized_vol_ratio_min=1.25,
        drawdown_max=-0.08,
    ),
    "effective_cap_010": dict(
        max_00631l_weight=A2126_EFFECTIVE_MAX_00631L_WEIGHT,
        tail_risk_score_min=1,
        realized_vol_ratio_min=1.25,
        drawdown_max=-0.08,
    ),
    "higher_confidence_cap_010": dict(
        max_00631l_weight=A2126_EFFECTIVE_MAX_00631L_WEIGHT,
        tail_risk_score_min=2,
        realized_vol_ratio_min=1.25,
        drawdown_max=-0.08,
    ),
}


def _metrics_subset(metrics: dict) -> dict:
    keys = [
        "final_value",
        "annual_return",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "worst_20d_return",
        "transaction_cost",
        "rebalance_count",
    ]
    return {key: metrics.get(key) for key in keys if key in metrics}


def _delta(variant: dict, baseline: dict) -> dict:
    return {
        key: variant[key] - baseline[key]
        for key in variant
        if key in baseline and isinstance(variant[key], (int, float)) and isinstance(baseline[key], (int, float))
    }


def main() -> None:
    db_path = Path(DB_PATH)
    all_results: dict[str, list[dict]] = {}
    summary: dict[str, dict] = {}

    for variant_name, variant_kw in VARIANTS.items():
        print(f"\n=== variant: {variant_name} ===")
        rows = []
        for label, start, end, panel, kind in WINDOWS:
            baseline, _ = run_a2118(
                start=start,
                end=end,
                initial_value=1_000_000.0,
                db=db_path,
                ncf_panel_631l_path=panel,
                **COMMON_KW,
            )
            variant, frame = run_a2126(
                start=start,
                end=end,
                initial_value=1_000_000.0,
                db=db_path,
                ncf_panel_631l_path=panel,
                **COMMON_KW,
                **variant_kw,
            )
            bm = _metrics_subset(baseline["metrics"])
            vm = _metrics_subset(variant["metrics"])
            cap_days = int((frame["execution_regime"] == "golden1_leverage_cap").sum())
            row = {
                "label": label,
                "kind": kind,
                "window": {"start": start, "end": end},
                "params": variant_kw,
                "leverage_cap_days": cap_days,
                "baseline": bm,
                "variant": vm,
                "delta": _delta(vm, bm),
            }
            rows.append(row)
            print(
                f"[{kind:14s}] {label:18s} cap_days={cap_days:3d} "
                f"delta_final={row['delta'].get('final_value', 0.0):>10.1f} "
                f"delta_sharpe={row['delta'].get('sharpe_ratio', 0.0):>8.4f}"
            )

        tuning = [r for r in rows if r["kind"] == "tuning_window"]
        oos = [r for r in rows if r["kind"] == "out_of_sample"]
        summary[variant_name] = {
            "params": variant_kw,
            "tuning_sum_delta_final_value": sum(r["delta"].get("final_value", 0.0) for r in tuning),
            "tuning_sum_delta_sharpe_ratio": sum(r["delta"].get("sharpe_ratio", 0.0) for r in tuning),
            "oos_sum_delta_final_value": sum(r["delta"].get("final_value", 0.0) for r in oos),
            "oos_sum_delta_sharpe_ratio": sum(r["delta"].get("sharpe_ratio", 0.0) for r in oos),
            "total_leverage_cap_days": sum(r["leverage_cap_days"] for r in rows),
        }
        print(
            "summary "
            f"tuning_delta_sharpe={summary[variant_name]['tuning_sum_delta_sharpe_ratio']:.4f} "
            f"tuning_delta_final={summary[variant_name]['tuning_sum_delta_final_value']:.1f} "
            f"oos_delta_sharpe={summary[variant_name]['oos_sum_delta_sharpe_ratio']:.4f} "
            f"oos_delta_final={summary[variant_name]['oos_sum_delta_final_value']:.1f}"
        )
        all_results[variant_name] = rows

    payload = {
        "strategy": "a2126_golden1_dynamic_leverage_cap_shadow",
        "research_only": True,
        "windows": WINDOWS,
        "summary": summary,
        "results": all_results,
        "promotion_review": {
            "decision": "do_not_promote_keep_shadow",
            "reason": "Requires positive out-of-sample evidence and acceptable final-value trade-off.",
        },
    }
    output_path = PROJECT_ROOT / "results" / "group_a_plus_a2126_leverage_cap_20260710.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
