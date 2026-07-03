"""Resolve and validate the active GroupA+ strategy manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_LATEST_STRATEGY = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "strategy.json"
SUPPORTED_STRATEGIES = {
    "a207": "group_a_plus.runners.a207",
    "a213_cash30_recovery_ramp": "group_a_plus.runners.a213",
    "a214_bond30c30_mw60": "group_a_plus.runners.a214",
    "a215_cash40_mw80": "group_a_plus.runners.a215",
    "a217_tight_entry_mw100": "group_a_plus.runners.a217",
    "a2111_tight_entry_bond30c30": "group_a_plus.runners.a2111",
    "a2112_ma80_tight_entry_bond30c30_lrx": "group_a_plus.runners.a2112",
    "a2113_a2111_ncf_overlay": "group_a_plus.runners.a2113",
    "a2114_a2111_ncf_exit_gate": "group_a_plus.runners.a2114",
    "a2118_a2111_ncf_late_bull_deleverage": "group_a_plus.runners.a2118",
    "a2115_a2111_ncf_dual_mode_gate": "group_a_plus.runners.a2115",
    "a2119_a2111_finbert_gate": "group_a_plus.runners.a2119",
    "a2120_a2111_ncf_late_bull_rally_aware": "group_a_plus.runners.a2120",
}


def resolve_latest(path: Path = DEFAULT_LATEST_STRATEGY) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2:
        raise ValueError(f"Unsupported latest strategy schema: {manifest.get('schema_version')}")
    active = manifest.get("active_strategy")
    if not isinstance(active, dict):
        raise ValueError("Latest strategy manifest is missing active_strategy")
    strategy_id = active.get("id")
    if strategy_id not in SUPPORTED_STRATEGIES:
        raise ValueError(f"Unsupported active strategy: {strategy_id}")
    expected_runner = SUPPORTED_STRATEGIES[strategy_id]
    if active.get("runner") != expected_runner:
        raise ValueError(f"Runner mismatch for {strategy_id}: expected {expected_runner}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--output", default="results/group_a_plus_latest_strategy_resolved.json")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.governance.latest")
    try:
        payload = std.success(resolve_latest(Path(args.manifest)))
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Latest strategy: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
