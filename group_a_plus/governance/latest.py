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
    "a2121_a2118_low_risk_fast_exit": "group_a_plus.runners.a2121",
    "a2122_golden1_tail_risk_trim_shadow": "group_a_plus.runners.a2122",
    "a2123_golden1_follow_through_trim_shadow": "group_a_plus.runners.a2123",
    "a2124_follow_through_trim_rebound_recapture_shadow": "group_a_plus.runners.a2124",
    "a2125_tail_risk_defensive_override_shadow": "group_a_plus.runners.a2125",
    "a2126_golden1_dynamic_leverage_cap_shadow": "group_a_plus.runners.a2126",
    "a2127_recovery_00631l_boost_shadow": "group_a_plus.runners.a2127",
    "a2128_recovery_00631l_boost_age_guard_shadow": "group_a_plus.runners.a2128",
    "a2129_recovery_00631l_boost_age_guard_aggressive_shadow": "group_a_plus.runners.a2129",
}


def resolve_ncf_00631l_panel_path(
    root: Path,
    *,
    fallback: str = "results/ncf_00631l_panel_latest_20260630.csv",
) -> str:
    """Read the production-pinned 00631L NCF panel path out of strategy.json.

    Fable audit (2026-07-08, #4): ops_health.py, run_ncf_daily_pipeline.py's
    drift-audit baseline, and strategy_env.py's REQUIRED_FILES each hardcoded
    this filename separately; only ops_health.py had been updated (2026-07-07)
    to track strategy.json's active_strategy.runner_params.ncf_panel_631l_path
    instead, leaving the other two watching a stale snapshot. This is the
    single shared resolver all three should use. `fallback` only applies when
    strategy.json is missing or doesn't have that field yet.
    """
    try:
        manifest = json.loads((root / "report/group_a_plus/latest/strategy.json").read_text(encoding="utf-8"))
    except Exception:
        return fallback
    path = (manifest.get("active_strategy") or {}).get("runner_params", {}).get("ncf_panel_631l_path")
    return str(path) if path else fallback


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
