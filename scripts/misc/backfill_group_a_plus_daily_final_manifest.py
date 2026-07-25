#!/usr/bin/env python3
"""Backfill a daily manifest for final GroupA+ governance/reporting outputs.

This is an outputs-only repair utility. It records already-existing final
daily status and promotion-gate artifacts, but does not claim that NCF model
steps or the full daily pipeline were rerun.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _existing_output(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    return str(path)


def build_manifest(
    *,
    date_stamp: str,
    live_signal: Path,
    promotion_gate: Path,
    daily_status_final: Path,
    deployment_summary: Path,
    daily_status_pointer: Path,
) -> dict[str, Any]:
    outputs = {
        "live_signal": _existing_output(live_signal),
        "promotion_gate": _existing_output(promotion_gate),
        "daily_status_final": _existing_output(daily_status_final),
        "deployment_summary": _existing_output(deployment_summary),
        "daily_status_pointer": _existing_output(daily_status_pointer),
    }
    return {
        "date_stamp": date_stamp,
        "mode": "governance_final_outputs_only",
        "status": "backfilled_outputs_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "outputs": outputs,
        "signals": {},
        "backfill": {
            "reason": "record_existing_final_daily_status_and_promotion_gate_outputs",
            "full_pipeline_rerun": False,
            "model_outputs_backfilled": False,
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def write_manifest(manifest: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-stamp", required=True)
    parser.add_argument("--live-signal", required=True)
    parser.add_argument("--promotion-gate", required=True)
    parser.add_argument("--daily-status-final", required=True)
    parser.add_argument("--deployment-summary", default="report/group_a_plus/latest/deployment_summary.json")
    parser.add_argument("--daily-status-pointer", default="report/group_a_plus/latest/daily_status.json")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    output = _resolve(args.output) if args.output else PROJECT_ROOT / "results" / f"ncf_daily_pipeline_{args.date_stamp}.json"
    manifest = build_manifest(
        date_stamp=args.date_stamp,
        live_signal=_resolve(args.live_signal),
        promotion_gate=_resolve(args.promotion_gate),
        daily_status_final=_resolve(args.daily_status_final),
        deployment_summary=_resolve(args.deployment_summary),
        daily_status_pointer=_resolve(args.daily_status_pointer),
    )
    write_manifest(manifest, output)
    print(f"Backfilled manifest: {output}")
    print(
        json.dumps(
            {
                "date_stamp": manifest["date_stamp"],
                "status": manifest["status"],
                "mode": manifest["mode"],
                "output_count": len(manifest["outputs"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
