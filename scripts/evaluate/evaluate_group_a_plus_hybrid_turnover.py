#!/usr/bin/env python3
"""Evaluate GroupA+ hybrid risk_off/severe turnover caps across stress windows."""

from __future__ import annotations

import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import twii_proxy_utils
from backtest_group_a_plus_overlay import _variant_config
from compare_group_a_plus_2008_golden_latest import (
    GROUP_A_PLUS_CONFIG,
    LATEST_MODEL,
    LATEST_PAYLOAD,
    _capture_model_events,
    _load_json,
    _run_group_a_plus,
)
from stress_group_a_plus_multi_windows import WINDOWS, _select_twii_cache


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_a13_fast_riskoff_stress_20260614.json"
PROFILES = [
    "focused_tdcc_0124_stab5_turn15",
    "focused_tdcc_0124_stab5_turn15_fast_disabled",
    "focused_tdcc_0124_stab5_turn15_fast_tight",
    "focused_tdcc_0124_stab5_turn15_fast_cd3",
    "focused_tdcc_0124_stab5_turn15_fast_cd2",
    "focused_tdcc_0124_stab2_turn10",
    "focused_tdcc_0124_stab2_turn12",
    "focused_tdcc_0124_stab2_turn15",
    "focused_tdcc_0124_stab3_turn12",
    "focused_tdcc_0124_stab5_turn12",
    "focused_tdcc_0134_stab5_turn15",
    "focused_tdcc_0145_stab5_turn15",
    "focused_tdcc_0224_stab5_turn15",
    "focused_tdcc_0235_stab5_turn15",
    "focused_tdcc_0245_stab5_turn15",
    "focused_tdcc_0258_stab3_turn08",
    "focused_tdcc_0258_stab3_turn10",
    "focused_tdcc_0258_stab2_turn08",
    "focused_tdcc_0258_stab2_turn10",
    "focused_tdcc_0258_stab2_turn12",
    "focused_tdcc_0258_stab2_turn15",
    "focused_tdcc_0258_stab3_turn12",
    "focused_tdcc_0258_stab5_turn10",
    "focused_tdcc_0258_stab5_turn12",
    "focused_tdcc_0258_stab3_turn15",
    "focused_tdcc_0258_stab5_turn15",
    "focused_tdcc_0258_stab3_turn15_sev08",
    "focused_tdcc_0258_stab3_turn15_sev10",
    "focused_tdcc_0258_stab3_turn18",
    "focused_tdcc_0258_stab3_turn18_sev08",
    "focused_tdcc_0258_stab3_turn20",
    "focused_tdcc_0258_stab3_turn20_sev08",
    "focused_tdcc_0258_stab3_turn25",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profiles",
        default=",".join(PROFILES),
        help="Comma-separated GroupA+ profile names to evaluate.",
    )
    parser.add_argument("--output", default=str(OUTPUT), help="Output JSON path.")
    return parser.parse_args()


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _metric_delta(plus: dict[str, Any], base: dict[str, Any]) -> dict[str, float]:
    return {
        key: float(plus[key] - base[key])
        for key in ["final_value", "sharpe_ratio", "max_drawdown", "volatility", "contribution_return"]
    }


def _aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    by_profile: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_profile.setdefault(str(row["profile"]), []).append(row)
    for profile, items in by_profile.items():
        out.append(
            {
                "profile": profile,
                "windows_total": len(items),
                "windows_positive_final": int(sum(item["delta_final_value"] > 0 for item in items)),
                "avg_delta_final_value": float(sum(item["delta_final_value"] for item in items) / len(items)),
                "min_delta_final_value": float(min(item["delta_final_value"] for item in items)),
                "avg_delta_sharpe_ratio": float(sum(item["delta_sharpe_ratio"] for item in items) / len(items)),
                "min_delta_sharpe_ratio": float(min(item["delta_sharpe_ratio"] for item in items)),
                "avg_mdd_improvement": float(sum(item["delta_max_drawdown"] for item in items) / len(items)),
                "min_mdd_improvement": float(min(item["delta_max_drawdown"] for item in items)),
                "avg_volatility_reduction": float(-sum(item["delta_volatility"] for item in items) / len(items)),
                "max_cost": float(max(item["total_cost"] for item in items)),
            }
        )
    return sorted(out, key=lambda row: row["profile"])


def main() -> None:
    args = _parse_args()
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    profiles = [item.strip() for item in str(args.profiles).split(",") if item.strip()]
    if not profiles:
        raise ValueError("--profiles must contain at least one profile")

    base_config = _load_json(GROUP_A_PLUS_CONFIG)
    profile_configs = {profile: _variant_config(base_config, profile) for profile in profiles}
    rows: list[dict[str, Any]] = []
    strategies: dict[str, Any] = {}
    skipped: list[dict[str, str]] = []

    for label, start, end in WINDOWS:
        cache = _select_twii_cache(start)
        if cache is None or not cache.exists():
            skipped.append({"window": label, "reason": f"no local TWII proxy cache for {start} ~ {end}"})
            continue
        twii_proxy_utils.DEFAULT_TWII_MARKET_CACHE = cache
        try:
            captured = _capture_model_events(
                name="latest_group_a_production_2020_2025_100k",
                payload_path=LATEST_PAYLOAD,
                model_path=LATEST_MODEL,
                start=start,
                end=end,
            )
        except Exception as exc:
            skipped.append({"window": label, "reason": str(exc)})
            continue

        window_profiles: dict[str, Any] = {}
        for profile, config in profile_configs.items():
            plus = _run_group_a_plus(captured, config)
            delta = _metric_delta(plus["metrics"], captured["base_metrics"])
            rows.append(
                {
                    "window": label,
                    "profile": profile,
                    "final_value": float(plus["metrics"]["final_value"]),
                    "sharpe_ratio": float(plus["metrics"]["sharpe_ratio"]),
                    "max_drawdown": float(plus["metrics"]["max_drawdown"]),
                    "volatility": float(plus["metrics"]["volatility"]),
                    "total_cost": float(plus["metrics"]["total_cost"]),
                    **{f"delta_{key}": value for key, value in delta.items()},
                }
            )
            window_profiles[profile] = {
                "metrics": plus["metrics"],
                "delta_plus_vs_base": delta,
                "event_count": len(plus["events"]),
                "final_weights": plus["final_weights"],
                "final_cash_weight": plus["final_cash_weight"],
            }

        strategies[label] = {
            "requested_window": {"start": start, "end": end},
            "twii_market_cache": str(cache.resolve()),
            "actual_window": {
                "start": captured["actual_start"],
                "end": captured["actual_end"],
                "rows": captured["rows"],
            },
            "base_metrics": captured["base_metrics"],
            "profiles": window_profiles,
        }

    report = {
        "experiment": "group_a_plus_hybrid_turnover_stress",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_config": str(GROUP_A_PLUS_CONFIG.resolve()),
        "profiles": profiles,
        "windows": WINDOWS,
        "strategies": strategies,
        "aggregate": _aggregate(rows),
        "rows": rows,
        "skipped": skipped,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    pd.DataFrame(rows).to_csv(output.with_suffix(".csv"), index=False, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {output.with_suffix('.csv')}")
    for row in report["aggregate"]:
        print(
            f"{row['profile']}: positive={row['windows_positive_final']}/{row['windows_total']}, "
            f"avg_final={row['avg_delta_final_value']:.0f}, worst_final={row['min_delta_final_value']:.0f}, "
            f"min_sharpe={row['min_delta_sharpe_ratio']:.4f}"
        )


if __name__ == "__main__":
    main()
