#!/usr/bin/env python3
"""Build an information bill of materials for Group A++ alpha claims.

arXiv 2609.04917 argues that investment experiments need point-in-time data
and model provenance by construction. This report inventories the current
Group A++/Group A+ signal artifacts and flags missing availability-time or
model-version evidence. It is shadow-only and cannot create orders.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_information_bom.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_information_bom.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2609_04917_information_bom/history"
DEFAULT_ARTIFACTS = (
    "live_signal=report/group_a_plus/latest/live_signal.json",
    "execution_plan=report/group_a_plus/latest/execution_plan.json",
    "ops_health=report/group_a_plus/latest/ops_health.json",
    "signal_alignment=report/group_a_plus/latest/signal_alignment.json",
    "watchlist_news=report/group_a_plus/latest/watchlist_news.json",
    "market_aligned_sentiment=report/group_a_plus/latest/market_aligned_sentiment_shadow.json",
    "profit_deployment_readiness=report/group_a_plus/latest/profit_deployment_readiness.json",
    "ncf_0050_signal=results/ncf_0050_latest_20260909.json",
    "ncf_00631l_signal=results/ncf_00631l_latest_20260909.json",
    "ncf_00632r_signal=results/ncf_00632r_latest_20260909.json",
    "ncf_0050_panel=results/ncf_0050_panel_latest_20260909.csv",
    "ncf_00631l_panel=results/ncf_00631l_panel_latest_20260909.csv",
    "ncf_00632r_panel=results/ncf_00632r_panel_latest_20260909.csv",
)

DATE_KEYS = (
    "actual_data_date",
    "requested_as_of_date",
    "as_of",
    "date",
    "last_close_date",
    "signal_asof",
    "generated_at",
)
MODEL_KEYS = (
    "models",
    "model_version",
    "model_path",
    "model_family",
    "strategy_id",
    "policy",
    "prompt_hash",
    "tool_schema_version",
    "data_snapshot_hash",
)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _items(raw_items: tuple[str, ...] | list[str]) -> list[tuple[str, Path]]:
    parsed = []
    for raw in raw_items:
        label, sep, path = raw.partition("=")
        if not sep:
            candidate = _resolve(raw)
            label = candidate.stem
        else:
            candidate = _resolve(path)
        parsed.append((label.strip(), candidate))
    return parsed


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _walk_dict(payload: Any, keys: tuple[str, ...], *, limit: int = 24) -> dict[str, Any]:
    found: dict[str, Any] = {}

    def visit(value: Any, prefix: str) -> None:
        if len(found) >= limit:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                if key in keys and key not in found:
                    found[key] = item
                visit(item, path)
        elif isinstance(value, list):
            for idx, item in enumerate(value[:5]):
                visit(item, f"{prefix}[{idx}]")

    visit(payload, "")
    return found


def _csv_summary(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    date_values = [row.get("date") for row in rows if row.get("date")]
    return {
        "format": "csv",
        "rows": len(rows),
        "columns": reader.fieldnames or [],
        "filename_date_hint": _filename_date_hint(path),
        "date_start": min(date_values) if date_values else None,
        "date_end": max(date_values) if date_values else None,
        "has_event_time": "date" in (reader.fieldnames or []),
        "has_availability_time": any(col in (reader.fieldnames or []) for col in ("availability_time", "available_at")),
        "model_fields": [col for col in (reader.fieldnames or []) if "model" in col.lower() or "version" in col.lower()],
    }


def _filename_date_hint(path: Path) -> str | None:
    import re

    match = re.search(r"(20\d{2})[-_]?(0\d|1[0-2])[-_]?([0-3]\d)", path.name)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _artifact(label: str, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "label": label,
            "path": str(path),
            "exists": False,
            "status": "missing",
            "blockers": ["artifact_missing"],
            "warnings": [],
        }
    stat = path.stat()
    base = {
        "label": label,
        "path": str(path),
        "exists": True,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "size_bytes": stat.st_size,
        "blockers": [],
        "warnings": [],
    }
    if path.suffix.lower() == ".csv":
        summary = _csv_summary(path)
        base.update(summary)
        if not summary["has_availability_time"]:
            base["warnings"].append("availability_time_column_missing")
        if not summary["model_fields"]:
            base["warnings"].append("model_version_column_missing")
    else:
        payload = _unwrap(json.loads(path.read_text(encoding="utf-8-sig")))
        dates = _walk_dict(payload, DATE_KEYS)
        models = _walk_dict(payload, MODEL_KEYS)
        base.update({"format": "json", "date_fields": dates, "model_fields": models})
        if not any(key in dates for key in ("actual_data_date", "as_of", "date", "last_close_date", "signal_asof")):
            base["warnings"].append("event_or_data_date_missing")
        if not any(key in dates for key in ("generated_at", "requested_as_of_date")):
            base["warnings"].append("availability_or_generation_time_missing")
        if not models:
            base["warnings"].append("model_or_policy_version_missing")
    base["status"] = "warning" if base["warnings"] else "available"
    return base


def build_report(*, artifacts: list[tuple[str, Path]], as_of: str | None = None) -> dict[str, Any]:
    rows = [_artifact(label, path) for label, path in artifacts]
    missing = [row["label"] for row in rows if row["status"] == "missing"]
    warnings = {
        row["label"]: row["warnings"]
        for row in rows
        if row.get("warnings")
    }
    status = "blocked" if missing else ("warning" if warnings else "available")
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_information_bom",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "shadow_only_information_bill_of_materials_no_weight_change",
        "live_execution_effect": "none",
        "source_paper": {
            "arxiv": "2609.04917",
            "concept": "point_in_time_information_and_model_versions",
        },
        "status": status,
        "artifact_count": len(rows),
        "missing_artifacts": missing,
        "warning_artifacts": warnings,
        "artifacts": rows,
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "latest_strategy_change_allowed": False,
            "promotion_allowed": False,
            "information_bom_required_before_live_promotion": True,
        },
        "recommended_next_actions": [
            "add availability_time or available_at to NCF and sentiment panels",
            "record model_path or model_version for every predictive artifact",
            "treat generated_at as artifact creation time, not as data availability time",
            "link each promoted candidate to this BOM before human promotion review",
        ],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.04917 Information Bill of Materials",
        "",
        f"- status: {report['status']}",
        f"- artifact_count: {report['artifact_count']}",
        f"- missing_artifacts: {', '.join(report['missing_artifacts']) or 'none'}",
        "",
        "| artifact | status | warnings |",
        "| --- | --- | --- |",
    ]
    for row in report["artifacts"]:
        lines.append(
            f"| {row['label']} | {row['status']} | {', '.join(row.get('warnings', [])) or 'none'} |"
        )
    lines.extend(["", "## Recommended Next Actions", ""])
    lines.extend(f"- {item}" for item in report["recommended_next_actions"])
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = as_of or datetime.now().strftime("%Y%m%d")
    return history_dir / f"2609_04917_information_bom_{stamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", action="append", dest="artifacts", default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()

    report = build_report(artifacts=_items(args.artifacts or list(DEFAULT_ARTIFACTS)), as_of=args.as_of)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    history = _history_path(_resolve(args.history_dir), args.as_of)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    history.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(_markdown(report), encoding="utf-8")
    history.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": report["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
