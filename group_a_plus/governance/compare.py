"""Compare GroupA+ candidate result JSON files against an A20.7 baseline."""

from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tw_output_standard import OutputStandardizer, write_standard_output


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("data", payload) if isinstance(payload, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return _unwrap(json.load(handle))


def _metrics_from_report(report: dict[str, Any]) -> dict[str, float]:
    if isinstance(report.get("metrics"), dict):
        return report["metrics"]
    summary = report.get("summary")
    if isinstance(summary, dict):
        if isinstance(summary.get("a207"), dict):
            return summary["a207"]
        if isinstance(summary.get("switch_risk_ma75_dd11_total6_hold5_eg0175_xg020"), dict):
            return summary["switch_risk_ma75_dd11_total6_hold5_eg0175_xg020"]
    raise ValueError("Could not locate baseline metrics in report")


def _candidate_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("rows", "selector_rows", "guard_rows", "rule_reports"):
        value = report.get(key)
        if isinstance(value, list):
            if key == "rule_reports":
                for item in value:
                    if isinstance(item, dict) and isinstance(item.get("metrics"), dict):
                        rows.append({"variant": item.get("variant") or item.get("name"), **item["metrics"]})
            else:
                rows.extend(row for row in value if isinstance(row, dict))
    if not rows and isinstance(report.get("best"), dict):
        rows.append(report["best"])
    return rows


def _effective_override(row: dict[str, Any]) -> int:
    for key in ("override_days", "effective_override_days"):
        if key in row and pd.notna(row[key]):
            return int(row[key])
    for key in ("trigger_days", "event_count"):
        if key in row and pd.notna(row[key]):
            return int(row[key])
    return 0


def compare_candidates(baseline_path: Path, candidate_paths: list[Path]) -> dict[str, Any]:
    baseline_report = _load_json(baseline_path)
    baseline_metrics = _metrics_from_report(baseline_report)
    rows = []
    for path in candidate_paths:
        if path.resolve() == baseline_path.resolve():
            continue
        try:
            report = _load_json(path)
        except Exception as exc:
            rows.append({"path": str(path), "load_error": str(exc)})
            continue
        experiment = report.get("experiment", path.stem)
        for row in _candidate_rows(report):
            metrics = row.get("metrics", row)
            if "final_value" not in metrics:
                continue
            effective_override = _effective_override(row)
            final_value = float(metrics.get("final_value", 0.0))
            sharpe = float(metrics.get("sharpe_ratio", 0.0))
            mdd = float(metrics.get("max_drawdown", -1.0))
            formal_eligible = bool(row.get("formal_eligible", True))
            formal_upgrade = (
                formal_eligible
                and final_value >= float(baseline_metrics["final_value"])
                and sharpe >= float(baseline_metrics["sharpe_ratio"])
                and mdd >= float(baseline_metrics["max_drawdown"])
                and effective_override > 0
            )
            watchlist = (
                final_value >= float(baseline_metrics["final_value"]) * 0.98
                and sharpe >= float(baseline_metrics["sharpe_ratio"])
                and mdd >= float(baseline_metrics["max_drawdown"])
                and effective_override > 0
            )
            rows.append(
                {
                    "path": str(path),
                    "experiment": experiment,
                    "variant": row.get("variant") or row.get("name") or "candidate",
                    "final_value": final_value,
                    "sharpe_ratio": sharpe,
                    "sortino_ratio": float(metrics.get("sortino_ratio", 0.0)),
                    "max_drawdown": mdd,
                    "trigger_days": int(row.get("trigger_days", row.get("event_count", 0)) or 0),
                    "override_days": effective_override,
                    "defense_days": int(row.get("defense_days", 0) or 0),
                    "delta_final": final_value - float(baseline_metrics["final_value"]),
                    "delta_sharpe": sharpe - float(baseline_metrics["sharpe_ratio"]),
                    "delta_mdd": mdd - float(baseline_metrics["max_drawdown"]),
                    "formal_eligible": formal_eligible,
                    "formal_ineligible_reason": row.get("formal_ineligible_reason"),
                    "formal_upgrade_pass": formal_upgrade,
                    "research_watchlist_pass": watchlist,
                }
            )
    ranked = sorted(
        rows,
        key=lambda item: (
            item.get("formal_upgrade_pass", False),
            item.get("sharpe_ratio", -99),
            item.get("final_value", 0),
        ),
        reverse=True,
    )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline_path": str(baseline_path),
        "baseline_metrics": baseline_metrics,
        "candidate_file_count": len(candidate_paths),
        "candidate_row_count": len(rows),
        "formal_upgrade_pass_count": sum(1 for row in rows if row.get("formal_upgrade_pass")),
        "research_watchlist_pass_count": sum(1 for row in rows if row.get("research_watchlist_pass")),
        "top_candidates": ranked[:25],
        "rows": rows,
    }


def _expand_patterns(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            paths.extend(Path(match) for match in matches)
        else:
            paths.append(Path(pattern))
    return sorted(set(paths))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidates", nargs="+", required=True)
    parser.add_argument("--output", default="results/group_a_plus_compare_20260619.json")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.governance.compare")
    try:
        report = compare_candidates(Path(args.baseline), _expand_patterns(args.candidates))
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Compare: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
