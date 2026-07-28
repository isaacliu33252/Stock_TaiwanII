#!/usr/bin/env python3
"""Build an advisory-only A21.18 decision-focused action snapshot.

This reads a precomputed DFL shadow result and the current live signal date,
then emits the matching finite-action decision if present. It never changes
target weights, execution guards, or latest live-signal pointers.
"""

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


# 2026-07-26: repointed to STABLE filenames that `run_ncf_daily_pipeline.py`'s
# "dfl_shadow_refresh_*" steps now regenerate every run (see
# GROUP_A_PLUS_DFL_ADVISORY_STALE_INPUT_FIX_20260726.md). Previously
# pointed at one-off dated snapshot files (e.g. "..._20260714_rerun.json")
# that nobody ever repointed after later corrections -- for 10 days a live
# report kept re-asserting a disproven "7/7 triple_pass" claim. Using
# stable, always-refreshed filenames instead of dated ones removes the
# whole failure class rather than fixing one instance of it.
DEFAULT_INPUT = PROJECT_ROOT / "results" / "a2118_decision_focused_action_shadow_dfl_main_latest.json"
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_dfl_advisory.json"
DEFAULT_SELECTIVE_INPUTS = (
    "p50=results/a2118_decision_focused_action_shadow_dfl_selective_p50_latest.json,"
    "p70=results/a2118_decision_focused_action_shadow_dfl_selective_p70_latest.json"
)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _unwrap_standard(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _live_actual_date(live_signal: dict[str, Any]) -> str | None:
    data = _unwrap_standard(live_signal)
    date = data.get("actual_data_date") or data.get("requested_as_of_date")
    return str(date) if date else None


def _all_decisions(result: dict[str, Any]) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for window in result.get("results", []) or []:
        if not isinstance(window, dict):
            continue
        label = window.get("label")
        bucket = window.get("bucket")
        for key in ("non_keep_decisions", "recent_decisions"):
            for row in window.get(key, []) or []:
                if not isinstance(row, dict) or "date" not in row:
                    continue
                item = dict(row)
                item["window_label"] = label
                item["window_bucket"] = bucket
                item["source_list"] = key
                decisions.append(item)
    # Prefer non_keep_decisions over recent_decisions for the same date/window.
    decisions.sort(key=lambda row: 0 if row.get("source_list") == "non_keep_decisions" else 1)
    return decisions


def build_advisory(
    *,
    input_path: Path,
    live_signal_path: Path,
    as_of: str | None = None,
    selective_inputs: dict[str, Path] | None = None,
) -> dict[str, Any]:
    if not input_path.exists():
        return {
            "schema_version": 1,
            "report_type": "a2118_dfl_advisory",
            "status": "unavailable",
            "policy": "advisory_only_no_auto_weight_change",
            "reason": "dfl_shadow_result_missing",
            "input": str(input_path),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }
    if not live_signal_path.exists() and not as_of:
        return {
            "schema_version": 1,
            "report_type": "a2118_dfl_advisory",
            "status": "unavailable",
            "policy": "advisory_only_no_auto_weight_change",
            "reason": "live_signal_missing",
            "input": str(input_path),
            "live_signal": str(live_signal_path),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        }

    result = _load_json(input_path)
    actual_date = as_of or _live_actual_date(_load_json(live_signal_path))
    decisions = [row for row in _all_decisions(result) if str(row.get("date")) == str(actual_date)]
    selected = decisions[0] if decisions else None
    action = str((selected or {}).get("action") or "KEEP")
    active = action != "KEEP"
    method = result.get("method") if isinstance(result.get("method"), dict) else {}
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    selective_variants = {
        name: build_advisory(input_path=path, live_signal_path=live_signal_path, as_of=actual_date, selective_inputs=None)
        for name, path in (selective_inputs or {}).items()
    }
    for variant in selective_variants.values():
        variant.pop("selective_variants", None)

    return {
        "schema_version": 1,
        "report_type": "a2118_dfl_advisory",
        "status": "available",
        "policy": "advisory_only_no_auto_weight_change",
        "active_allocation_impact": "none",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": actual_date,
        "action": action,
        "advisory_active": active,
        "recommended_action": "manual_review_consider_shadow_action" if active else "keep_a2118",
        "selected_decision": selected,
        "input": str(input_path),
        "live_signal": str(live_signal_path),
        "method": {
            "actions": method.get("actions"),
            "target": method.get("target"),
            "stabilizers": method.get("stabilizers"),
            "model": method.get("model"),
        },
        "evidence": {
            "source_status": result.get("status"),
            "summary": summary,
            "matched_decision_count": len(decisions),
            "note": (
                "DFL output is sparse and research-only; non-KEEP action is not an execution instruction."
                if active
                else "No DFL non-KEEP action matched the live signal date."
            ),
        },
        "selective_variants": selective_variants,
    }


def _parse_selective_inputs(raw: str | None) -> dict[str, Path]:
    if not raw:
        return {}
    out: dict[str, Path] = {}
    for item in raw.split(","):
        if not item.strip():
            continue
        if "=" not in item:
            raise ValueError("--selective-inputs items must be name=path")
        name, path = item.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError("--selective-inputs name cannot be empty")
        out[name] = _resolve(path.strip())
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--selective-inputs", default=DEFAULT_SELECTIVE_INPUTS)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = build_advisory(
        input_path=_resolve(args.input),
        live_signal_path=_resolve(args.live_signal),
        as_of=args.as_of,
        selective_inputs=_parse_selective_inputs(args.selective_inputs),
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"JSON: {output}")
    print(f"Status: {payload.get('status')} action={payload.get('action')}")


if __name__ == "__main__":
    main()
