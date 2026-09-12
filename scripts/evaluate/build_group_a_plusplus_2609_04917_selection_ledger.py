#!/usr/bin/env python3
"""Build a selection/search ledger for Group A++ profit candidates.

arXiv 2609.04917 treats repeated search as a first-class threat to alpha
claims. This report inventories sweep, seed, OOS, validation, and candidate
artifacts so promotion review can see the search footprint. It remains
shadow-only and blocks promotion unless a confirmatory specification is frozen.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFIT_READINESS = PROJECT_ROOT / "report/group_a_plus/latest/profit_deployment_readiness.json"
DEFAULT_SEARCH_ROOTS = (
    PROJECT_ROOT / "report/group_a_plus/latest",
    PROJECT_ROOT / "results",
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_selection_ledger.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_selection_ledger.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2609_04917_selection_ledger/history"
DEFAULT_FROZEN_SPEC = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_staged_reentry_frozen_confirmatory_spec.json"
KEYWORDS = ("sweep", "seed", "oos", "validation", "robustness", "candidate", "promotion", "ablation")


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload.get("data", payload) if isinstance(payload.get("data"), dict) else payload


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _candidate_paths(roots: list[Path], *, limit: int) -> list[Path]:
    paths: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.glob("*"):
            if path.suffix.lower() not in {".json", ".md", ".csv"}:
                continue
            name = path.name.lower()
            if any(keyword in name for keyword in KEYWORDS):
                paths.append(path)
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def _json_summary(path: Path) -> dict[str, Any]:
    try:
        payload = _load_optional(path)
    except Exception as exc:
        return {"load_error": str(exc)}
    summary: dict[str, Any] = {}
    for key in (
        "status",
        "report_type",
        "variant",
        "best_variant",
        "parameter_count",
        "eligible_parameter_count",
        "active_event_count",
    ):
        if key in payload:
            summary[key] = payload[key]
    for key in ("top_variants", "rows", "variants", "candidate_reviews", "train_sweep_rows"):
        value = payload.get(key)
        if isinstance(value, list):
            summary[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            summary[f"{key}_count"] = len(value)
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    if decision:
        for key in ("promotion_allowed", "target_weight_change_allowed", "promotion_ready"):
            if key in decision:
                summary[f"decision_{key}"] = decision[key]
    return summary


def _artifact(path: Path) -> dict[str, Any]:
    stat = path.stat()
    row = {
        "path": str(path),
        "name": path.name,
        "suffix": path.suffix.lower(),
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "size_bytes": stat.st_size,
    }
    if path.suffix.lower() == ".json":
        row["summary"] = _json_summary(path)
    return row


def build_report(
    *,
    profit_readiness_path: Path,
    search_roots: list[Path],
    frozen_spec_path: Path | None = None,
    max_artifacts: int = 80,
    as_of: str | None = None,
) -> dict[str, Any]:
    profit = _load_optional(profit_readiness_path)
    active = _as_list(profit.get("active_shadow_candidates"))
    paths = _candidate_paths(search_roots, limit=max_artifacts)
    artifacts = [_artifact(path) for path in paths]
    frozen_spec_available = bool(frozen_spec_path and frozen_spec_path.exists())
    blockers = []
    if not artifacts:
        blockers.append("no_selection_artifacts_found")
    if not frozen_spec_available:
        blockers.append("frozen_confirmatory_specification_missing")
    status = "blocked" if blockers else "available_for_confirmatory_review"
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_selection_ledger",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "shadow_only_selection_ledger_no_weight_change",
        "live_execution_effect": "none",
        "source_paper": {
            "arxiv": "2609.04917",
            "concept": "selection_control_and_repeated_search_budget",
        },
        "status": status,
        "active_shadow_candidates": active,
        "artifact_count": len(artifacts),
        "search_roots": [str(path) for path in search_roots],
        "frozen_confirmatory_specification": str(frozen_spec_path) if frozen_spec_path else None,
        "frozen_confirmatory_specification_available": frozen_spec_available,
        "blocking_reasons": blockers,
        "artifacts": artifacts,
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "creates_orders": False,
            "latest_strategy_change_allowed": False,
            "selection_ledger_available": bool(artifacts),
            "confirmatory_specification_frozen": frozen_spec_available,
        },
        "recommended_next_actions": [
            "choose exactly one active shadow candidate for confirmatory validation",
            "write a frozen specification with candidate name, parameters, windows, costs, and pass/fail rule",
            "treat later parameter changes as a new exploratory run, not as the confirmatory result",
            "keep the full attempted-artifact ledger attached to promotion review",
        ],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.04917 Selection Ledger",
        "",
        f"- status: {report['status']}",
        f"- active_shadow_candidates: {', '.join(map(str, report['active_shadow_candidates'])) or 'none'}",
        f"- artifact_count: {report['artifact_count']}",
        f"- frozen_confirmatory_specification_available: {report['frozen_confirmatory_specification_available']}",
        f"- blocking_reasons: {', '.join(report['blocking_reasons']) or 'none'}",
        "",
        "| artifact | suffix | mtime |",
        "| --- | --- | --- |",
    ]
    for row in report["artifacts"][:40]:
        lines.append(f"| {row['name']} | {row['suffix']} | {row['mtime']} |")
    lines.extend(["", "## Recommended Next Actions", ""])
    lines.extend(f"- {item}" for item in report["recommended_next_actions"])
    return "\n".join(lines) + "\n"


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = as_of or datetime.now().strftime("%Y%m%d")
    return history_dir / f"2609_04917_selection_ledger_{stamp}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profit-readiness", default=str(DEFAULT_PROFIT_READINESS))
    parser.add_argument("--search-root", action="append", default=None)
    parser.add_argument("--frozen-spec", default=str(DEFAULT_FROZEN_SPEC))
    parser.add_argument("--max-artifacts", type=int, default=80)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()
    roots = [_resolve(path) for path in (args.search_root or [str(path) for path in DEFAULT_SEARCH_ROOTS])]
    frozen = _resolve(args.frozen_spec) if args.frozen_spec else None
    report = build_report(
        profit_readiness_path=_resolve(args.profit_readiness),
        search_roots=roots,
        frozen_spec_path=frozen,
        max_artifacts=args.max_artifacts,
        as_of=args.as_of,
    )
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
