#!/usr/bin/env python3
"""Build and append an advisory-only A21.18 DFL shadow ensemble log row."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_ADVISORY = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_dfl_advisory.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_dfl_shadow_ensemble.json"
DEFAULT_LOG = PROJECT_ROOT / "results" / "a2118_dfl_shadow_ensemble_log.jsonl"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _clean(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _decision_summary(payload: dict[str, Any]) -> dict[str, Any]:
    selected = payload.get("selected_decision") if isinstance(payload.get("selected_decision"), dict) else {}
    return {
        "action": payload.get("action"),
        "active": bool(payload.get("advisory_active")),
        "recommended_action": payload.get("recommended_action"),
        "predicted_regret": selected.get("predicted_regret"),
        "candidate_action_before_reliability": selected.get("candidate_action_before_reliability"),
        "candidate_predicted_regret_before_reliability": selected.get("candidate_predicted_regret_before_reliability"),
        "reliability_error_percentile": selected.get("reliability_error_percentile"),
        "reliability_gate_pass": selected.get("reliability_gate_pass"),
        "action_allowed": selected.get("action_allowed"),
        "window_label": selected.get("window_label"),
        "source_list": selected.get("source_list"),
    }


def ensemble_level(base: dict[str, Any], p50: dict[str, Any], p70: dict[str, Any]) -> str:
    base_active = bool(base.get("active"))
    p50_active = bool(p50.get("active"))
    p70_active = bool(p70.get("active"))
    actions = {str(item.get("action") or "KEEP") for item in (base, p50, p70)}
    non_keep_actions = {action for action in actions if action != "KEEP"}
    if not non_keep_actions:
        return "none"
    if len(non_keep_actions) > 1:
        return "conflict"
    if p50_active and p70_active:
        return "strong_watch"
    if p70_active or base_active:
        return "watch"
    if p50_active:
        return "conflict"
    return "none"


def build_ensemble_snapshot(advisory: dict[str, Any]) -> dict[str, Any]:
    variants = advisory.get("selective_variants") if isinstance(advisory.get("selective_variants"), dict) else {}
    base = _decision_summary(advisory)
    p50 = _decision_summary(variants.get("p50", {}) if isinstance(variants.get("p50"), dict) else {})
    p70 = _decision_summary(variants.get("p70", {}) if isinstance(variants.get("p70"), dict) else {})
    level = ensemble_level(base, p50, p70)
    return _clean(
        {
            "schema_version": 1,
            "report_type": "a2118_dfl_shadow_ensemble",
            "status": "available" if advisory.get("status") == "available" else "unavailable",
            "policy": "shadow_only_no_auto_weight_change",
            "active_allocation_impact": "none",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": advisory.get("as_of"),
            "ensemble_level": level,
            "manual_review_required": level in {"watch", "strong_watch", "conflict"},
            "signals": {
                "base": base,
                "p50": p50,
                "p70": p70,
            },
            "note": "Observation-only DFL ensemble; not an execution instruction.",
        }
    )


def append_ensemble_log(snapshot: dict[str, Any], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    as_of = str(snapshot.get("as_of") or "")
    rows = [row for row in rows if str(row.get("as_of") or "") != as_of]
    rows.append(snapshot)
    rows.sort(key=lambda row: str(row.get("as_of") or ""))
    log_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--advisory", default=str(DEFAULT_ADVISORY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-append-log", action="store_true")
    args = parser.parse_args()

    snapshot = build_ensemble_snapshot(_load_json(args.advisory))
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.no_append_log:
        append_ensemble_log(snapshot, _resolve(args.log))
    print(f"JSON: {output}")
    print(f"Level: {snapshot.get('ensemble_level')}")


if __name__ == "__main__":
    main()
