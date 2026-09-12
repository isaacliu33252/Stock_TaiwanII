#!/usr/bin/env python3
"""Review broker holdings that are outside the Group A+ execution universe."""

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

from backtest_group_a_plus_policy_signal import TICKERS  # noqa: E402
DEFAULT_BROKER_SAMPLE = PROJECT_ROOT / "report/group_a_plus/latest/broker_holdings_time_series_sample.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/broker_holding_scope_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/broker_holding_scope_review.md"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load(path: str | Path) -> dict[str, Any]:
    resolved = _resolve(path)
    if not resolved.exists():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_broker_holding_scope_review(
    *,
    broker_sample: dict[str, Any],
    execution_universe: tuple[str, ...] = TICKERS,
) -> dict[str, Any]:
    positions = broker_sample.get("latest_positions") if isinstance(broker_sample.get("latest_positions"), dict) else {}
    universe = set(execution_universe)
    out_of_universe = {
        ticker: int(shares)
        for ticker, shares in sorted(positions.items())
        if ticker not in universe and int(shares or 0) != 0
    }
    blockers = []
    if broker_sample.get("authoritative_broker_export") is not True:
        blockers.append("broker_sample_not_authoritative")
    if out_of_universe:
        blockers.append("nonzero_holding_outside_execution_universe")
    status = "blocked_scope_decision_required" if blockers else "in_scope"
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_broker_holding_scope_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "scope_review_only_no_orders_no_weight_change",
        "live_execution_effect": "none",
        "status": status,
        "execution_universe": list(execution_universe),
        "out_of_universe_nonzero_holdings": out_of_universe,
        "blockers": blockers,
        "decision": {
            "creates_orders": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "scope_decision_required": bool(out_of_universe),
            "can_build_live_execution_plan_without_scope_exception": not blockers,
        },
        "resolution_options": [
            "confirm out-of-universe holdings are outside Group A+ and exclude them from the Group A+ broker sample",
            "explicitly add the ticker to the Group A+ execution universe after strategy/governance review",
            "move or liquidate the ticker outside this Group A+ workflow before generating a live execution plan",
        ],
    }


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Group A+ Broker Holding Scope Review",
        "",
        f"- Status: `{payload['status']}`",
        f"- Live effect: `{payload['live_execution_effect']}`",
        "",
        "## Out-Of-Universe Nonzero Holdings",
        "",
    ]
    holdings = payload.get("out_of_universe_nonzero_holdings") or {}
    if not holdings:
        lines.append("- None")
    for ticker, shares in holdings.items():
        lines.append(f"- `{ticker}`: `{shares}`")
    lines.extend(["", "## Resolution Options", ""])
    lines.extend(f"- {item}" for item in payload["resolution_options"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker-sample", default=str(DEFAULT_BROKER_SAMPLE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    args = parser.parse_args()

    payload = build_broker_holding_scope_review(broker_sample=_load(args.broker_sample))
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_md(_resolve(args.output_md), payload)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = _resolve(args.results_dir) / f"group_a_plus_broker_holding_scope_review_{stamp}.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
