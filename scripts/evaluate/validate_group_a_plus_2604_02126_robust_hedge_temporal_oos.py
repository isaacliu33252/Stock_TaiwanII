#!/usr/bin/env python3
"""Temporal OOS validation for GroupA+ 2604.02126 robust hedge parameters."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_2604_02126_robust_hedge_review import (
    DEFAULT_DB,
    DEFAULT_LATEST_STRATEGY,
    DEFAULT_LETF_READINESS,
    _finite,
    _resolve,
    build_review,
)
from scripts.evaluate.sweep_group_a_plus_2604_02126_robust_hedge import DEFAULT_OUTPUT as DEFAULT_SWEEP


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2604_02126_robust_hedge_temporal_oos.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2604_02126_robust_hedge_temporal_oos.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2604_02126_robust_hedge_temporal_oos/history"
DEFAULT_WINDOWS = "early_2020_2022:2020-01-01:2022-12-31;mid_2023_2024:2023-01-01:2024-12-31;recent_2025_2026:2025-01-01:2026-08-28"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_windows(raw: str) -> list[dict[str, str]]:
    windows = []
    for item in raw.split(";"):
        if not item.strip():
            continue
        label, start, end = item.split(":", 2)
        windows.append({"label": label.strip(), "start": start.strip(), "end": end.strip()})
    if not windows:
        raise ValueError("Expected at least one temporal window")
    return windows


def _method(review: dict[str, Any], name: str) -> dict[str, Any]:
    return (((review.get("hedge_review") or {}).get("method_comparison") or {}).get(name) or {})


def _effectiveness(method: dict[str, Any], field: str) -> float | None:
    eff = method.get("effectiveness")
    if not isinstance(eff, dict):
        return None
    return _finite(eff.get(field))


def _parameter_rows(sweep: dict[str, Any]) -> list[dict[str, Any]]:
    rows = sweep.get("all_rows")
    if isinstance(rows, list) and rows:
        return [
            {
                "window": int(row["window"]),
                "uncertainty_window": int(row["uncertainty_window"]),
                "max_hedge_weight": float(row["max_hedge_weight"]),
            }
            for row in rows
            if {"window", "uncertainty_window", "max_hedge_weight"} <= set(row)
        ]
    grid = sweep.get("grid") if isinstance(sweep.get("grid"), dict) else {}
    params = []
    for window in grid.get("windows", []):
        for uncertainty_window in grid.get("uncertainty_windows", []):
            for cap in grid.get("max_hedge_weights", []):
                params.append(
                    {
                        "window": int(window),
                        "uncertainty_window": int(uncertainty_window),
                        "max_hedge_weight": float(cap),
                    }
                )
    return params


def _window_result(
    *,
    db_path: Path,
    temporal_window: dict[str, str],
    params: dict[str, Any],
    warmup_start: str,
    letf_readiness_path: Path,
    latest_strategy_path: Path,
) -> dict[str, Any]:
    review = build_review(
        db_path=db_path,
        start=warmup_start,
        as_of=temporal_window["end"],
        window=int(params["window"]),
        uncertainty_window=int(params["uncertainty_window"]),
        max_hedge_weight=float(params["max_hedge_weight"]),
        evaluation_start=temporal_window["start"],
        letf_readiness_path=letf_readiness_path,
        latest_strategy_path=latest_strategy_path,
    )
    standard = _method(review, "standard")
    robust = _method(review, "robust_variance_only")
    robust_turnover_delta = _finite(robust.get("turnover_reduction_vs_standard"))
    robust_std_delta = _finite(robust.get("exposure_std_reduction_vs_standard"))
    robust_che = _effectiveness(robust, "conditional_hedge_effectiveness")
    standard_che = _effectiveness(standard, "conditional_hedge_effectiveness")
    robust_he = _effectiveness(robust, "hedge_effectiveness")
    standard_he = _effectiveness(standard, "hedge_effectiveness")
    passed = (
        robust_turnover_delta is not None
        and robust_turnover_delta >= 0.0
        and robust_std_delta is not None
        and robust_std_delta >= 0.0
        and robust_che is not None
        and standard_che is not None
        and robust_che >= standard_che
    )
    return {
        "label": temporal_window["label"],
        "start": temporal_window["start"],
        "end": temporal_window["end"],
        "actual_data_end": review.get("actual_data_end"),
        "observation_count": (review.get("hedge_review") or {}).get("observation_count"),
        "robust_turnover_reduction_vs_standard": robust_turnover_delta,
        "robust_exposure_std_reduction_vs_standard": robust_std_delta,
        "robust_he": robust_he,
        "standard_he": standard_he,
        "robust_conditional_he": robust_che,
        "standard_conditional_he": standard_che,
        "robust_latest_exposure": robust.get("latest_long_inverse_exposure"),
        "standard_latest_exposure": standard.get("latest_long_inverse_exposure"),
        "passed": passed,
    }


def build_temporal_oos(
    *,
    sweep: dict[str, Any],
    db_path: Path = DEFAULT_DB,
    windows: list[dict[str, str]] | None = None,
    warmup_start: str = "2020-01-01",
    letf_readiness_path: Path = DEFAULT_LETF_READINESS,
    latest_strategy_path: Path = DEFAULT_LATEST_STRATEGY,
) -> dict[str, Any]:
    temporal_windows = windows or _parse_windows(DEFAULT_WINDOWS)
    params = _parameter_rows(sweep)
    rows: list[dict[str, Any]] = []
    for param in params:
        window_results = [
            _window_result(
                db_path=db_path,
                temporal_window=temporal_window,
                params=param,
                warmup_start=warmup_start,
                letf_readiness_path=letf_readiness_path,
                latest_strategy_path=latest_strategy_path,
            )
            for temporal_window in temporal_windows
        ]
        valid_windows = [item for item in window_results if item.get("observation_count")]
        passed_windows = [item for item in valid_windows if item.get("passed")]
        row = {
            **param,
            "valid_window_count": len(valid_windows),
            "passed_window_count": len(passed_windows),
            "all_valid_windows_passed": bool(valid_windows) and len(passed_windows) == len(valid_windows),
            "mean_robust_turnover_reduction": _finite(
                sum(float(item["robust_turnover_reduction_vs_standard"]) for item in valid_windows if item["robust_turnover_reduction_vs_standard"] is not None)
                / len([item for item in valid_windows if item["robust_turnover_reduction_vs_standard"] is not None])
            )
            if any(item["robust_turnover_reduction_vs_standard"] is not None for item in valid_windows)
            else None,
            "mean_robust_conditional_he_delta": _finite(
                sum(
                    float(item["robust_conditional_he"] - item["standard_conditional_he"])
                    for item in valid_windows
                    if item["robust_conditional_he"] is not None and item["standard_conditional_he"] is not None
                )
                / len(
                    [
                        item
                        for item in valid_windows
                        if item["robust_conditional_he"] is not None and item["standard_conditional_he"] is not None
                    ]
                )
            )
            if any(item["robust_conditional_he"] is not None and item["standard_conditional_he"] is not None for item in valid_windows)
            else None,
            "windows": window_results,
        }
        rows.append(row)

    ranked = sorted(
        rows,
        key=lambda row: (
            int(row.get("passed_window_count") or 0),
            float(row.get("mean_robust_conditional_he_delta") or -999.0),
            float(row.get("mean_robust_turnover_reduction") or -999.0),
        ),
        reverse=True,
    )
    eligible = [row for row in rows if row["all_valid_windows_passed"]]
    blockers = [
        "research_only_temporal_oos",
        "letf_readiness_blocks_00632r_open",
        "live_hedge_policy_not_validated_for_robust_ratio",
        "daily_close_proxy_not_high_frequency_realized_covariance",
        "transaction_cost_and_execution_slippage_not_revalidated",
    ]
    if not eligible:
        blockers.append("no_parameter_set_passed_all_temporal_windows")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2604_02126_robust_hedge_temporal_oos",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_sweep_report_type": sweep.get("report_type"),
        "policy": "research_only_temporal_oos_no_00632r_open_no_weight_change",
        "status": "blocked_for_live_promotion",
        "temporal_windows": temporal_windows,
        "warmup_start": warmup_start,
        "parameter_count": len(rows),
        "eligible_parameter_count": len(eligible),
        "best_rows": ranked[:10],
        "eligible_rows": eligible[:10],
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "temporal_oos_complete": bool(rows),
            "temporal_oos_passed": bool(eligible),
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "sweep": str(DEFAULT_SWEEP),
            "db_path": str(db_path),
            "warmup_start": warmup_start,
            "letf_tracking_error_effective_fee_readiness": str(letf_readiness_path),
            "latest_strategy_preview": str(latest_strategy_path),
        },
    }


def _fmt(value: Any, digits: int = 6) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2604.02126 Robust Hedge Temporal OOS",
        "",
        f"Generated: `{report.get('generated_at')}`",
        f"Status: `{report.get('status')}`",
        "",
        "## Decision",
        "",
        "- Do not change live target weights.",
        "- Do not open or increase `00632R.TW`.",
        "- Keep `Golden1_0531` unchanged.",
        "",
        "## Summary",
        "",
        f"- parameter count: `{report.get('parameter_count')}`",
        f"- eligible parameter count: `{report.get('eligible_parameter_count')}`",
        "",
        "## Best Rows",
        "",
        "| window | uncertainty | cap | valid | pass | mean turnover delta | mean CHE delta | all pass |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report.get("best_rows", [])[:10]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("window")),
                    str(row.get("uncertainty_window")),
                    _fmt(row.get("max_hedge_weight"), 2),
                    str(row.get("valid_window_count")),
                    str(row.get("passed_window_count")),
                    _fmt(row.get("mean_robust_turnover_reduction")),
                    _fmt(row.get("mean_robust_conditional_he_delta")),
                    str(row.get("all_valid_windows_passed")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- `{reason}`" for reason in report.get("blocking_reasons", []))
    lines.append("")
    return "\n".join(lines)


def _history_path(history_dir: Path) -> Path:
    return history_dir / f"2604_02126_robust_hedge_temporal_oos_{datetime.now().strftime('%Y%m%d')}.json"


def write_report(
    report: dict[str, Any],
    output_path: Path,
    output_md_path: Path | None = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md_path is not None:
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_markdown(report) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", default=str(DEFAULT_SWEEP))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--windows", default=DEFAULT_WINDOWS)
    parser.add_argument("--warmup-start", default="2020-01-01")
    parser.add_argument("--letf-readiness", default=str(DEFAULT_LETF_READINESS))
    parser.add_argument("--latest-strategy", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_temporal_oos(
        sweep=_load_json(_resolve(args.sweep)),
        db_path=_resolve(args.db),
        windows=_parse_windows(args.windows),
        warmup_start=args.warmup_start,
        letf_readiness_path=_resolve(args.letf_readiness),
        latest_strategy_path=_resolve(args.latest_strategy),
    )
    output_md = None if not args.output_md else _resolve(args.output_md)
    write_report(report, _resolve(args.output), output_md, None if args.no_history else _resolve(args.history_dir))
    print(f"2604.02126 robust hedge temporal OOS: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": report["status"],
                "parameter_count": report["parameter_count"],
                "eligible_parameter_count": report["eligible_parameter_count"],
                "temporal_oos_passed": report["decision"]["temporal_oos_passed"],
                "allow_00632r_open": report["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
