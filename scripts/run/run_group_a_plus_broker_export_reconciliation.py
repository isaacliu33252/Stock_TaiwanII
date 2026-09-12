#!/usr/bin/env python3
"""Run the Group A+ broker export import and reconciliation handoff.

Default mode is staging-only: validate the CSV and write a staging sample
without replacing the current broker_holdings_time_series_sample.json. Use
--apply to promote a valid authoritative sample into the reconciliation input.
This script never creates orders or changes target weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_broker_holdings_reconciliation_review import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_RECONCILIATION_OUTPUT,
    DEFAULT_SAMPLE as DEFAULT_LIVE_SAMPLE,
    build_review,
    confirmed_from_authoritative_sample,
    write_review,
)
from scripts.evaluate.import_group_a_plus_broker_authoritative_export import (  # noqa: E402
    DEFAULT_INPUT,
    DEFAULT_OUTPUT as DEFAULT_STAGING_SAMPLE,
    build_authoritative_sample,
    write_sample,
)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def run_broker_export_reconciliation(
    *,
    input_path: Path,
    staging_output: Path,
    live_sample_output: Path,
    reconciliation_output: Path,
    apply: bool = False,
) -> dict[str, Any]:
    sample = build_authoritative_sample(input_path)
    write_sample(sample, staging_output, history_dir=None)
    result: dict[str, Any] = {
        "schema_version": 1,
        "report_type": "group_a_plus_broker_export_reconciliation_run",
        "policy": "no_order_generation_no_weight_change",
        "live_execution_effect": "none",
        "mode": "apply" if apply else "staging_only",
        "input": str(input_path),
        "staging_sample": str(staging_output),
        "authoritative_sample_status": sample["status"],
        "authoritative_sample_errors": sample.get("errors") or [],
        "applied_to_live_sample": False,
        "reconciliation_output": None,
        "reconciliation_status": None,
        "next_commands": [],
    }
    if sample["status"] != "authoritative_sample_ready":
        result["status"] = "blocked_invalid_broker_export"
        result["next_commands"] = ["complete broker_authoritative_export_template.csv and rerun this command"]
        return result
    if not apply:
        result["status"] = "staging_ready_apply_required"
        result["next_commands"] = [
            ".venv/bin/python scripts/run/run_group_a_plus_broker_export_reconciliation.py --apply",
            ".venv/bin/python scripts/evaluate/build_group_a_plus_deployment_consistency_review.py",
            ".venv/bin/python scripts/evaluate/build_group_a_plus_deployment_summary.py",
            ".venv/bin/python scripts/evaluate/build_group_a_plus_profit_deployment_readiness.py",
        ]
        return result

    write_sample(sample, live_sample_output, history_dir=None)
    confirmed = confirmed_from_authoritative_sample(live_sample_output)
    review = build_review(
        sample_path=live_sample_output,
        confirmed_holdings=confirmed,
        confirmed_holdings_source="authoritative_broker_export_latest_positions",
    )
    write_review(review, reconciliation_output, history_dir=None)
    result.update(
        {
            "status": "reconciliation_ready",
            "applied_to_live_sample": True,
            "live_sample": str(live_sample_output),
            "reconciliation_output": str(reconciliation_output),
            "reconciliation_status": review["status"],
            "reconciliation_blocking_reasons": review.get("blocking_reasons") or [],
            "next_commands": [
                ".venv/bin/python scripts/evaluate/build_group_a_plus_deployment_consistency_review.py",
                ".venv/bin/python scripts/evaluate/build_group_a_plus_deployment_summary.py",
                ".venv/bin/python scripts/evaluate/build_group_a_plus_profit_deployment_readiness.py",
            ],
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--staging-output", default=str(DEFAULT_STAGING_SAMPLE))
    parser.add_argument("--live-sample-output", default=str(DEFAULT_LIVE_SAMPLE))
    parser.add_argument("--reconciliation-output", default=str(DEFAULT_RECONCILIATION_OUTPUT))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    result = run_broker_export_reconciliation(
        input_path=_resolve(args.input),
        staging_output=_resolve(args.staging_output),
        live_sample_output=_resolve(args.live_sample_output),
        reconciliation_output=_resolve(args.reconciliation_output),
        apply=bool(args.apply),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"staging_ready_apply_required", "reconciliation_ready"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
