#!/usr/bin/env python3
"""Build the A21.18 PPO seed-averaging promotion gate.

The gate is intentionally conservative: it requires enough forward shadow
rows, date-matched live inference snapshots, high parity pass rate, and a
passing latest row before any human promotion review can proceed.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MONITOR = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json"
DEFAULT_LOG = PROJECT_ROOT / "results/a2118_seed_averaging_forward_shadow_monitor_log.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_promotion_gate.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_promotion_gate.md"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    resolved = _resolve(path)
    if not resolved.exists():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_log(path: str | Path) -> list[dict[str, Any]]:
    resolved = _resolve(path)
    if not resolved.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in resolved.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    rows.sort(key=lambda row: str(row.get("as_of") or ""))
    return rows


def _parity_pass(row: dict[str, Any]) -> bool:
    parity = row.get("latest_live_action_parity")
    return bool(isinstance(parity, dict) and parity.get("validated") is True)


def _has_date_matched_inference(row: dict[str, Any]) -> bool:
    inference = row.get("ensemble_inference")
    return isinstance(inference, dict) and str(inference.get("as_of") or "") == str(row.get("as_of") or "")


def build_promotion_gate(
    *,
    latest_monitor: dict[str, Any],
    history_rows: list[dict[str, Any]],
    minimum_forward_rows: int = 20,
    minimum_parity_pass_rate: float = 0.95,
) -> dict[str, Any]:
    rows_by_date = {str(row.get("as_of") or ""): row for row in history_rows if row.get("as_of")}
    rows = [rows_by_date[key] for key in sorted(rows_by_date)]
    if latest_monitor.get("as_of"):
        rows_by_date[str(latest_monitor["as_of"])] = latest_monitor
        rows = [rows_by_date[key] for key in sorted(rows_by_date)]

    blockers: list[str] = []
    warnings: list[str] = []
    if not latest_monitor:
        blockers.append("latest_forward_shadow_monitor_missing")
    if len(rows) < minimum_forward_rows:
        blockers.append("forward_shadow_monitoring_history_insufficient")
    inference_rows = [row for row in rows if _has_date_matched_inference(row)]
    if len(inference_rows) < len(rows):
        blockers.append("forward_shadow_inference_snapshot_missing_or_stale")

    parity_rows = [row for row in rows if isinstance(row.get("latest_live_action_parity"), dict)]
    parity_pass_count = sum(1 for row in parity_rows if _parity_pass(row))
    parity_pass_rate = parity_pass_count / len(parity_rows) if parity_rows else 0.0
    if not parity_rows:
        blockers.append("latest_live_action_parity_not_validated")
    elif parity_pass_rate < minimum_parity_pass_rate:
        blockers.append("latest_live_action_parity_pass_rate_below_threshold")
    if latest_monitor and not _parity_pass(latest_monitor):
        blockers.append("latest_live_action_parity_not_validated")

    latest_status = latest_monitor.get("status")
    if latest_status not in {"candidate_forward_shadow_row_available", "forward_shadow_row_available_parity_pending"}:
        warnings.append(f"latest_monitor_status:{latest_status}")

    status = "ready_for_human_promotion_review" if not blockers else "blocked"
    return {
        "schema_version": 1,
        "report_type": "a2118_ppo_seed_averaging_promotion_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "promotion_gate_only_no_live_weight_change_no_orders",
        "live_execution_effect": "none",
        "status": status,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "criteria": {
            "minimum_forward_rows": minimum_forward_rows,
            "minimum_parity_pass_rate": minimum_parity_pass_rate,
            "latest_row_must_pass_parity": True,
            "all_rows_require_date_matched_inference": True,
        },
        "summary": {
            "forward_rows": len(rows),
            "date_matched_inference_rows": len(inference_rows),
            "parity_rows": len(parity_rows),
            "parity_pass_count": parity_pass_count,
            "parity_pass_rate": parity_pass_rate,
            "latest_as_of": latest_monitor.get("as_of"),
            "latest_monitor_status": latest_status,
            "latest_live_action": ((latest_monitor.get("latest_live_action_parity") or {}).get("live_action")),
            "latest_ensemble_action": ((latest_monitor.get("latest_live_action_parity") or {}).get("ensemble_action")),
        },
        "decision": {
            "can_promote_to_production": status == "ready_for_human_promotion_review",
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "requires_human_promotion_review": True,
        },
    }


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# A21.18 PPO Seed Averaging Promotion Gate",
        "",
        f"- Status: `{payload['status']}`",
        f"- Forward rows: `{summary['forward_rows']}`",
        f"- Parity pass rate: `{summary['parity_pass_rate']:.4f}`",
        f"- Latest live / ensemble action: `{summary['latest_live_action']}` / `{summary['latest_ensemble_action']}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in payload["blockers"])
    lines.extend(["", "This gate is shadow-only and creates no orders or target-weight changes.", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monitor", default=str(DEFAULT_MONITOR))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--minimum-forward-rows", type=int, default=20)
    parser.add_argument("--minimum-parity-pass-rate", type=float, default=0.95)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    payload = build_promotion_gate(
        latest_monitor=_load_json(args.monitor),
        history_rows=_load_log(args.log),
        minimum_forward_rows=args.minimum_forward_rows,
        minimum_parity_pass_rate=args.minimum_parity_pass_rate,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_md(_resolve(args.output_md), payload)
    print(json.dumps({"output": str(output), "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
