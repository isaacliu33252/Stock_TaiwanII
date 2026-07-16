#!/usr/bin/env python3
"""Sensitivity sweep for GroupA+ recovery boost with volatility-quality gate.

Small, interpretable grid only. This is meant to test whether A21.27's 10%
recovery boost and the p65 volatility-quality gate are in a stable region, not
to search a large parameter space.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.evaluate_group_a_plus_reentry_accelerator_clean import (
    WINDOWS,
    evaluate_window,
)


def main() -> None:
    windows = [evaluate_window(*window) for window in WINDOWS]
    rows = []
    variants = sorted(windows[0]["variants"])
    keep_prefixes = ("recovery_as_golden1", "recovery_boost_")
    for variant in variants:
        if not variant.startswith(keep_prefixes):
            continue
        tuning = [w for w in windows if w["kind"] == "tuning_window"]
        oos = [w for w in windows if w["kind"] == "out_of_sample"]
        row = {
            "variant": variant,
            "tuning_sum_delta_final_value": sum(w["variants"][variant]["delta_vs_baseline"]["delta_final_value"] for w in tuning),
            "tuning_sum_delta_sharpe_ratio": sum(w["variants"][variant]["delta_vs_baseline"]["delta_sharpe_ratio"] for w in tuning),
            "oos_sum_delta_final_value": sum(w["variants"][variant]["delta_vs_baseline"]["delta_final_value"] for w in oos),
            "oos_sum_delta_sharpe_ratio": sum(w["variants"][variant]["delta_vs_baseline"]["delta_sharpe_ratio"] for w in oos),
            "changed_days": sum(
                int(w["variants"][variant].get("changed_days", w["variants"][variant].get("recapture_days", 0)))
                for w in windows
            ),
        }
        rows.append(row)

    rows.sort(
        key=lambda r: (
            r["tuning_sum_delta_final_value"] > 0,
            r["oos_sum_delta_final_value"] > 0,
            r["oos_sum_delta_sharpe_ratio"],
            r["tuning_sum_delta_sharpe_ratio"],
        ),
        reverse=True,
    )
    payload = {
        "strategy": "group_a_plus_reentry_vol_quality_sensitivity",
        "research_only": True,
        "rows": rows,
        "windows": windows,
        "decision_note": (
            "This is a small sensitivity sweep. Promote only after broader event count "
            "or true forward evidence; do not optimize further on the same windows."
        ),
    }
    output = PROJECT_ROOT / "results" / "group_a_plus_reentry_vol_quality_sweep_20260710.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    for row in rows:
        print(
            f"{row['variant']:42s} tuning_fv={row['tuning_sum_delta_final_value']:9.1f} "
            f"tuning_sh={row['tuning_sum_delta_sharpe_ratio']:8.4f} "
            f"oos_fv={row['oos_sum_delta_final_value']:9.1f} "
            f"oos_sh={row['oos_sum_delta_sharpe_ratio']:8.4f} "
            f"days={row['changed_days']:3d}"
        )
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
