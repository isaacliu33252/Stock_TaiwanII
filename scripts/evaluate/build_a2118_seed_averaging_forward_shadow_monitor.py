#!/usr/bin/env python3
"""Build a forward shadow monitor row for A21.18 PPO seed averaging.

This intentionally does not run PPO inference. It records the daily live
context and whether the seed-averaging candidate has enough integrated
inference evidence to be compared with the current live signal.
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

DEFAULT_SHADOW = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_shadow.json"
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_forward_shadow_monitor.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_forward_shadow_monitor.md"
DEFAULT_LOG = PROJECT_ROOT / "results" / "a2118_seed_averaging_forward_shadow_monitor_log.jsonl"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _signal_payload(live_signal: dict[str, Any]) -> dict[str, Any]:
    data = live_signal.get("data") if isinstance(live_signal.get("data"), dict) else live_signal
    market_state = data.get("market_state") if isinstance(data.get("market_state"), dict) else {}
    return {
        "strategy_id": data.get("strategy_id"),
        "requested_as_of_date": data.get("requested_as_of_date"),
        "actual_data_date": data.get("actual_data_date"),
        "action": data.get("action"),
        "execution_regime": data.get("execution_regime"),
        "target_weights": data.get("target_weights"),
        "market_state": {
            "state": market_state.get("state"),
            "bucket": market_state.get("bucket"),
            "dominant_direction": (market_state.get("inputs") or {}).get("dominant_direction")
            if isinstance(market_state.get("inputs"), dict)
            else None,
            "risk_level": market_state.get("risk_level"),
        },
        "execution_allowed": data.get("execution_allowed"),
        "execution_guard_reasons": _as_list(data.get("execution_guard_reasons")),
        "execution_warning_reasons": _as_list(data.get("execution_warning_reasons")),
    }


def _monitor_status(
    shadow: dict[str, Any],
    *,
    inference_snapshot: dict[str, Any] | None,
    inference_matches_live_date: bool,
) -> tuple[str, list[str]]:
    blockers = _as_list((shadow.get("decision") or {}).get("production_blockers") if isinstance(shadow.get("decision"), dict) else [])
    blockers = [item for item in blockers if item != "forward_shadow_monitoring_missing"]
    blockers = [item for item in blockers if item != "no_production_promotion_gate"]
    if inference_snapshot and inference_matches_live_date:
        blockers = [item for item in blockers if item != "inference_integration_not_implemented"]
    else:
        blockers = blockers + [
            "forward_shadow_inference_snapshot_stale_or_mismatched"
            if inference_snapshot
            else "forward_shadow_inference_snapshot_missing"
        ]
    blockers = list(dict.fromkeys(str(item) for item in blockers))
    if inference_snapshot and inference_matches_live_date and "latest_live_action_parity_not_validated" not in blockers:
        return "candidate_forward_shadow_row_available", blockers
    if inference_snapshot and inference_matches_live_date:
        return "forward_shadow_row_available_parity_pending", blockers
    if inference_snapshot:
        return "monitoring_scaffold_ready_inference_stale", blockers
    return "monitoring_scaffold_ready_inference_missing", blockers


def build_monitor(
    *,
    shadow: dict[str, Any],
    live_signal: dict[str, Any],
    inference_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    decision = shadow.get("decision") if isinstance(shadow.get("decision"), dict) else {}
    live = _signal_payload(live_signal)
    as_of = live.get("actual_data_date") or live.get("requested_as_of_date")
    inference_as_of = inference_snapshot.get("as_of") if isinstance(inference_snapshot, dict) else None
    inference_matches_live_date = bool(inference_snapshot) and str(inference_as_of) == str(as_of)
    status, blockers = _monitor_status(
        shadow,
        inference_snapshot=inference_snapshot,
        inference_matches_live_date=inference_matches_live_date,
    )
    parity = {
        "validated": False,
        "reason": "a2118_seed_averaging_live_inference_not_available",
        "live_action": live.get("action"),
        "ensemble_action": None,
    }
    if inference_snapshot and inference_matches_live_date:
        parity = {
            "validated": inference_snapshot.get("action") == live.get("action"),
            "reason": "compared_inference_snapshot_action_to_live_action",
            "live_action": live.get("action"),
            "ensemble_action": inference_snapshot.get("action"),
        }
    elif inference_snapshot:
        parity = {
            "validated": False,
            "reason": "inference_snapshot_as_of_mismatch",
            "live_action": live.get("action"),
            "ensemble_action": inference_snapshot.get("action"),
            "live_as_of": as_of,
            "inference_as_of": inference_as_of,
        }
    return {
        "schema_version": 1,
        "report_type": "a2118_ppo_seed_averaging_forward_shadow_monitor",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": status,
        "policy": "shadow_only_no_live_weight_change",
        "live_execution_effect": "none",
        "preferred_ensemble": shadow.get("preferred_ensemble"),
        "shadow_gate": decision.get("shadow_gate"),
        "shadow_queue": decision.get("shadow_queue"),
        "production": "do_not_promote",
        "production_blockers": blockers,
        "live_signal": live,
        "ensemble_inference": inference_snapshot,
        "latest_live_action_parity": parity,
        "monitoring_requirements": {
            "minimum_forward_rows_before_review": 20,
            "current_forward_rows_counted_by_log": None,
            "required_next_artifact": "daily seed-level PPO action/probability snapshot for preferred ensemble",
        },
        "note": "This monitor records the daily promotion gap; it does not generate PPO actions unless an inference snapshot is supplied.",
    }


def append_monitor_log(snapshot: dict[str, Any], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    as_of = str(snapshot.get("as_of") or "")
    rows = [row for row in rows if str(row.get("as_of") or "") != as_of]
    rows.append(snapshot)
    rows.sort(key=lambda row: str(row.get("as_of") or ""))
    count = len(rows)
    for row in rows:
        req = row.setdefault("monitoring_requirements", {})
        if isinstance(req, dict):
            req["current_forward_rows_counted_by_log"] = count
    log_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return count


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# A21.18 PPO Seed Averaging Forward Shadow Monitor",
        "",
        f"- As of: `{payload.get('as_of')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Preferred ensemble: `{payload.get('preferred_ensemble')}`",
        f"- Shadow gate: `{payload.get('shadow_gate')}`",
        f"- Production: `{payload.get('production')}`",
        f"- Live action: `{(payload.get('live_signal') or {}).get('action')}`",
        f"- Parity validated: `{(payload.get('latest_live_action_parity') or {}).get('validated')}`",
        "",
        "## Blockers",
        "",
    ]
    for blocker in payload.get("production_blockers") or []:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "This is shadow-only and creates no target-weight or order change.", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", default=str(DEFAULT_SHADOW))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--inference-snapshot", default=None)
    parser.add_argument("--optional-inference-snapshot", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-append-log", action="store_true")
    args = parser.parse_args()

    inference = None
    if args.inference_snapshot:
        inference = _load_json(args.inference_snapshot)
    elif args.optional_inference_snapshot:
        optional_snapshot = _resolve(args.optional_inference_snapshot)
        if optional_snapshot.exists():
            inference = _load_json(optional_snapshot)
    payload = build_monitor(shadow=_load_json(args.shadow), live_signal=_load_json(args.live_signal), inference_snapshot=inference)
    output = _resolve(args.output)
    _write_json_atomic(output, payload)
    _write_md(_resolve(args.output_md), payload)
    if not args.no_append_log:
        count = append_monitor_log(payload, _resolve(args.log))
        payload["monitoring_requirements"]["current_forward_rows_counted_by_log"] = count
        _write_json_atomic(output, payload)
        _write_md(_resolve(args.output_md), payload)
    print(json.dumps({"output": str(output), "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
