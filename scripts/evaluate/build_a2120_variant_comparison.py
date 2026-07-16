#!/usr/bin/env python3
"""Build A21.20 main-vs-risk-sensitive variant comparison.

Research-only.  This summarizes the main trend100 candidate against the
CE20-negative-to-trend90 minimum-edge variant without changing the promotion
scorecard or production behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_MAIN_7WIN = PROJECT_ROOT / "results" / "00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_7win_20260715.json"
DEFAULT_MAIN_COST20 = PROJECT_ROOT / "results" / "00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_7win_cost20bps_20260715.json"
DEFAULT_VARIANT_7WIN = PROJECT_ROOT / "results" / "00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_ce20neg90_7win_20260716.json"
DEFAULT_VARIANT_COST20 = PROJECT_ROOT / "results" / "00631l_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_ce20neg90_7win_cost20bps_20260716.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "shadow" / "a2120_variant_comparison_20260716.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _num(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _totals(report: dict[str, Any]) -> dict[str, Any]:
    return report.get("totals") if isinstance(report.get("totals"), dict) else {}


def _window_rows(main: dict[str, Any], variant: dict[str, Any]) -> list[dict[str, Any]]:
    main_windows = {str(row.get("label")): row for row in main.get("windows", []) if isinstance(row, dict)}
    rows: list[dict[str, Any]] = []
    for variant_row in variant.get("windows", []):
        if not isinstance(variant_row, dict):
            continue
        label = str(variant_row.get("label"))
        main_row = main_windows.get(label, {})
        main_delta = _num((main_row.get("delta_vs_baseline") or {}).get("final_value"))
        variant_delta = _num((variant_row.get("delta_vs_baseline") or {}).get("final_value"))
        main_mdd = _num((main_row.get("delta_vs_baseline") or {}).get("max_drawdown"))
        variant_mdd = _num((variant_row.get("delta_vs_baseline") or {}).get("max_drawdown"))
        rows.append(
            {
                "label": label,
                "main_delta_final_value": main_delta,
                "variant_delta_final_value": variant_delta,
                "variant_minus_main_final_value": variant_delta - main_delta,
                "main_delta_max_drawdown": main_mdd,
                "variant_delta_max_drawdown": variant_mdd,
                "variant_minus_main_max_drawdown": variant_mdd - main_mdd,
                "variant_event_days": int((variant_row.get("mean_reversion_no_add") or {}).get("event_days", 0) or 0),
            }
        )
    return rows


def build_comparison(
    *,
    main_7win: dict[str, Any],
    main_cost20: dict[str, Any],
    variant_7win: dict[str, Any],
    variant_cost20: dict[str, Any],
) -> dict[str, Any]:
    main7 = _totals(main_7win)
    main20 = _totals(main_cost20)
    variant7 = _totals(variant_7win)
    variant20 = _totals(variant_cost20)
    cost20_rows = _window_rows(main_cost20, variant_cost20)
    return {
        "schema_version": 1,
        "report_type": "a2120_variant_comparison",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "main_candidate": "score3_ar0_persist50_rev50_trend100",
        "variant_candidate": "score3_ar0_persist50_rev50_trend100_ce20_negative_to_trend90",
        "decision": {
            "main_candidate": "keep_as_primary_shadow_candidate",
            "variant_candidate": "keep_as_risk_sensitive_shadow_variant",
            "production": "do_not_promote",
            "reason": (
                "CE20 weak-edge variant remains 7/7 positive under event and 20 bps stress, "
                "but gives up final-value upside versus the main candidate."
            ),
        },
        "summary": {
            "main_7win_delta_final_value_sum": _num(main7.get("delta_final_value_sum")),
            "variant_7win_delta_final_value_sum": _num(variant7.get("delta_final_value_sum")),
            "variant_minus_main_7win_delta_final_value_sum": _num(variant7.get("delta_final_value_sum"))
            - _num(main7.get("delta_final_value_sum")),
            "main_7win_positive_windows": int(main7.get("positive_final_value_windows", 0) or 0),
            "variant_7win_positive_windows": int(variant7.get("positive_final_value_windows", 0) or 0),
            "main_cost20_delta_final_value_sum": _num(main20.get("delta_final_value_sum")),
            "variant_cost20_delta_final_value_sum": _num(variant20.get("delta_final_value_sum")),
            "variant_minus_main_cost20_delta_final_value_sum": _num(variant20.get("delta_final_value_sum"))
            - _num(main20.get("delta_final_value_sum")),
            "main_cost20_positive_windows": int(main20.get("positive_final_value_windows", 0) or 0),
            "variant_cost20_positive_windows": int(variant20.get("positive_final_value_windows", 0) or 0),
        },
        "cost20_windows": cost20_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-7win", default=str(DEFAULT_MAIN_7WIN))
    parser.add_argument("--main-cost20", default=str(DEFAULT_MAIN_COST20))
    parser.add_argument("--variant-7win", default=str(DEFAULT_VARIANT_7WIN))
    parser.add_argument("--variant-cost20", default=str(DEFAULT_VARIANT_COST20))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = build_comparison(
        main_7win=_load(Path(args.main_7win)),
        main_cost20=_load(Path(args.main_cost20)),
        variant_7win=_load(Path(args.variant_7win)),
        variant_cost20=_load(Path(args.variant_cost20)),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
