"""Emit a small runner catalog for GroupA+ research workflows."""

from __future__ import annotations

import argparse
import importlib
from datetime import datetime
from pathlib import Path
from typing import Any

from tw_output_standard import OutputStandardizer, write_standard_output

from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY, SUPPORTED_STRATEGIES, resolve_latest

# Fable audit (2026-07-16, combination opportunities #4): this catalog was
# hand-maintained separately from group_a_plus.governance.latest's
# SUPPORTED_STRATEGIES (the actual live-dispatch registry read from
# strategy.json), and silently drifted two generations behind -- "active"
# stayed hardcoded at "a213_runner" through the entire a2111-a2129 era, and
# the runner list stopped at a216 with none of a217/a2111-a2129 ever added.
# Modules whose SUPPORTED_STRATEGIES entry duplicates one already hand-curated
# below (a207/a213/a214/a215, which predate SUPPORTED_STRATEGIES and keep
# their richer legacy templates with a root-level script) are skipped by
# _LEGACY_COVERED_MODULES so this never double-lists a runner.
_LEGACY_COVERED_MODULES = {
    "group_a_plus.runners.a207",
    "group_a_plus.runners.a213",
    "group_a_plus.runners.a214",
    "group_a_plus.runners.a215",
}
_FALLBACK_ACTIVE_STRATEGY_ID = "a2118_a2111_ncf_late_bull_deleverage"


def _resolve_active_strategy_id(manifest_path: Path = DEFAULT_LATEST_STRATEGY) -> str:
    try:
        manifest = resolve_latest(manifest_path)
        strategy_id = manifest["active_strategy"]["id"]
        return str(strategy_id) if strategy_id else _FALLBACK_ACTIVE_STRATEGY_ID
    except Exception:
        return _FALLBACK_ACTIVE_STRATEGY_ID


def _supported_strategy_runner_entries(active_strategy_id: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for strategy_id, module_path in SUPPORTED_STRATEGIES.items():
        if module_path in _LEGACY_COVERED_MODULES:
            continue
        short_id = module_path.rsplit(".", 1)[-1]
        try:
            description = (importlib.import_module(module_path).__doc__ or "").strip().splitlines()[0]
        except Exception:
            description = f"GroupA+ {short_id} strategy runner."
        entries.append(
            {
                "id": strategy_id,
                "kind": "active_strategy" if strategy_id == active_strategy_id else "shadow_candidate",
                "module": module_path,
                "description": description,
                "module_command_template": (
                    f"python3 -m {module_path} --start {{start}} --end {{end}} "
                    f"--output results/group_a_plus_runner_{short_id}_{{label}}.json "
                    f"--frame-output results/group_a_plus_runner_{short_id}_{{label}}_frame.csv"
                ),
                "outputs": ["json", "frame_csv"],
            }
        )
    return entries


def build_catalog(
    default_start: str,
    default_end: str,
    *,
    manifest_path: Path = DEFAULT_LATEST_STRATEGY,
) -> dict[str, Any]:
    active_strategy_id = _resolve_active_strategy_id(manifest_path)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "default_window": {"start": default_start, "end": default_end},
        "active": active_strategy_id,
        "baseline": "a207_runner",
        "latest_manifest": "report/group_a_plus/latest/strategy.json",
        "legacy_latest_pointer": "report/group_a_plus/latest/switch_backtest.json",
        "guardrails": {
            "formal_upgrade": [
                "candidate_final_value >= baseline_final_value",
                "candidate_sharpe_ratio >= baseline_sharpe_ratio",
                "candidate_max_drawdown >= baseline_max_drawdown",
                "effective_override_days > 0",
            ],
            "research_watchlist": [
                "candidate_sharpe_ratio >= baseline_sharpe_ratio",
                "candidate_max_drawdown >= baseline_max_drawdown",
                "candidate_final_value >= baseline_final_value * 0.98",
                "effective_override_days > 0",
            ],
        },
        "runners": [
            {
                "id": "a207_runner",
                "kind": "baseline",
                "script": "group_a_plus_runner.py",
                "module": "group_a_plus.runners.a207",
                "description": "Standardized A20.7 baseline runner.",
                "command_template": (
                    "python3 group_a_plus_runner.py --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a207_{label}.json "
                    "--frame-output results/group_a_plus_runner_a207_{label}_frame.csv"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.runners.a207 --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a207_{label}.json "
                    "--frame-output results/group_a_plus_runner_a207_{label}_frame.csv"
                ),
                "outputs": ["json", "frame_csv"],
            },
            {
                "id": "news_anomaly",
                "kind": "overlay",
                "script": "backtest_group_a_plus_news_anomaly.py",
                "module": "group_a_plus.strategies.news_anomaly",
                "description": "LTN news risk anomaly selector/guard overlay.",
                "command_template": (
                    "python3 backtest_group_a_plus_news_anomaly.py --start {start} --end {end} "
                    "--output-prefix results/group_a_plus_news_anomaly_{label}"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.strategies.news_anomaly --start {start} --end {end} "
                    "--output-prefix results/group_a_plus_news_anomaly_{label}"
                ),
                "outputs": ["json", "csv", "curve_csv", "best_frame_csv"],
            },
            {
                "id": "derivative_options_overlay",
                "kind": "overlay",
                "script": "backtest_group_a_plus_derivative_options_overlay.py",
                "module": "group_a_plus.strategies.options_overlay",
                "description": "TXO put-call/dealer options stress selector/guard overlay.",
                "command_template": (
                    "python3 backtest_group_a_plus_derivative_options_overlay.py --start {start} --end {end} "
                    "--output-prefix results/group_a_plus_derivative_options_overlay_{label}"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.strategies.options_overlay --start {start} --end {end} "
                    "--output-prefix results/group_a_plus_derivative_options_overlay_{label}"
                ),
                "outputs": ["json", "csv", "curve_csv", "best_frame_csv"],
            },
            {
                "id": "scaling_tail",
                "kind": "research_candidate",
                "script": "backtest_group_a_plus_scaling_tail.py",
                "module": "group_a_plus.strategies.scaling_tail",
                "description": "Chapter 8 scaling/Hill tail proxy overlay.",
                "command_template": (
                    "python3 backtest_group_a_plus_scaling_tail.py --start {start} --end {end} "
                    "--output-prefix results/group_a_plus_scaling_tail_{label}"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.strategies.scaling_tail --start {start} --end {end} "
                    "--output-prefix results/group_a_plus_scaling_tail_{label}"
                ),
                "outputs": ["json", "csv", "curve_csv", "best_frame_csv"],
            },
            {
                "id": "abm_agents",
                "kind": "research_candidate",
                "script": "backtest_group_a_plus_abm_agents.py",
                "module": "group_a_plus.strategies.abm_agents",
                "description": "Chapter 12 observable-agent ABM proxy overlay.",
                "command_template": (
                    "python3 backtest_group_a_plus_abm_agents.py --start {start} --end {end} "
                    "--output-prefix results/group_a_plus_abm_agents_{label}"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.strategies.abm_agents --start {start} --end {end} "
                    "--output-prefix results/group_a_plus_abm_agents_{label}"
                ),
                "outputs": ["json", "csv", "curve_csv", "best_frame_csv"],
            },
            {
                "id": "scaling_tail_ready",
                "kind": "research_candidate",
                "script": "backtest_group_a_plus_scaling_tail_ready.py",
                "module": "group_a_plus.strategies.scaling_tail_ready",
                "description": "Warmup-aware scaling-tail addon with valid Hill-alpha gating.",
                "command_template": (
                    "python3 backtest_group_a_plus_scaling_tail_ready.py --start {start} --end {end} "
                    "--output-prefix results/group_a_plus_scaling_tail_ready_{label}"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.strategies.scaling_tail_ready --start {start} --end {end} "
                    "--output-prefix results/group_a_plus_scaling_tail_ready_{label}"
                ),
                "outputs": ["json", "csv", "best_frame_csv"],
            },
            {
                "id": "fingpt_sentiment_alignment",
                "kind": "research_candidate",
                "script": "backtest_group_a_plus_fingpt_sentiment_alignment.py",
                "module": "group_a_plus.strategies.fingpt_sentiment_alignment",
                "description": "Lagged multi-horizon FinGPT sentiment and source-alignment overlay.",
                "command_template": (
                    "python3 backtest_group_a_plus_fingpt_sentiment_alignment.py "
                    "--start {start} --end {end} "
                    "--output-prefix results/group_a_plus_fingpt_sentiment_alignment_{label}"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.strategies.fingpt_sentiment_alignment "
                    "--start {start} --end {end} "
                    "--output-prefix results/group_a_plus_fingpt_sentiment_alignment_{label}"
                ),
                "outputs": ["json", "csv", "best_frame_csv"],
            },
            {
                "id": "dynamic_exposure",
                "kind": "research_candidate",
                "script": "backtest_group_a_plus_dynamic_exposure.py",
                "module": "group_a_plus.strategies.dynamic_exposure",
                "description": "A20.7 staged defense with tail confirmation and volatility-aware recovery.",
                "command_template": (
                    "python3 backtest_group_a_plus_dynamic_exposure.py "
                    "--start {start} --end {end} "
                    "--output-prefix results/group_a_plus_dynamic_exposure_{label}"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.strategies.dynamic_exposure "
                    "--start {start} --end {end} "
                    "--output-prefix results/group_a_plus_dynamic_exposure_{label}"
                ),
                "outputs": ["json", "csv", "best_frame_csv"],
            },
            {
                "id": "coverage_normalized",
                "kind": "research_candidate",
                "script": "backtest_group_a_plus_coverage_normalized.py",
                "module": "group_a_plus.strategies.coverage_normalized",
                "description": "A20.8 coverage-normalized entry risk with A20.7 fallback.",
                "command_template": (
                    "python3 backtest_group_a_plus_coverage_normalized.py "
                    "--start {start} --end {end} "
                    "--output-prefix results/group_a_plus_coverage_normalized_{label}"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.strategies.coverage_normalized "
                    "--start {start} --end {end} "
                    "--output-prefix results/group_a_plus_coverage_normalized_{label}"
                ),
                "outputs": ["json", "csv", "best_frame_csv"],
            },
            {
                "id": "warmup_consistency",
                "kind": "research_candidate",
                "script": "backtest_group_a_plus_warmup_consistency.py",
                "module": "group_a_plus.strategies.warmup_consistency",
                "description": "A20.9 pre-window feature/state warmup consistency audit.",
                "command_template": (
                    "python3 backtest_group_a_plus_warmup_consistency.py "
                    "--start {start} --end {end} "
                    "--output-prefix results/group_a_plus_warmup_consistency_{label}"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.strategies.warmup_consistency "
                    "--start {start} --end {end} "
                    "--output-prefix results/group_a_plus_warmup_consistency_{label}"
                ),
                "outputs": ["json", "csv", "best_frame_csv"],
            },
            {
                "id": "defensive_basket",
                "kind": "research_candidate",
                "script": "backtest_group_a_plus_defensive_basket.py",
                "module": "group_a_plus.strategies.defensive_basket",
                "description": "A21 dividend- and cost-aware defensive basket robustness.",
                "command_template": (
                    "python3 backtest_group_a_plus_defensive_basket.py "
                    "--start {start} --end {end} "
                    "--output-prefix results/group_a_plus_defensive_basket_{label}"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.strategies.defensive_basket "
                    "--start {start} --end {end} "
                    "--output-prefix results/group_a_plus_defensive_basket_{label}"
                ),
                "outputs": ["json", "csv", "best_frame_csv"],
            },
            {
                "id": "a213_runner",
                # Fable audit (2026-07-16, #4): no longer the active strategy
                # (superseded by a2118 and later); this hardcoded label was
                # never updated when active moved on. See
                # _resolve_active_strategy_id() for the current one.
                "kind": "legacy_superseded",
                "script": "group_a_plus_a213_runner.py",
                "module": "group_a_plus.runners.a213",
                "description": "A21.3 cash30 recovery-ramp standardized runner.",
                "command_template": (
                    "python3 group_a_plus_a213_runner.py --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a213_{label}.json "
                    "--frame-output results/group_a_plus_runner_a213_{label}_frame.csv"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.runners.a213 --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a213_{label}.json "
                    "--frame-output results/group_a_plus_runner_a213_{label}_frame.csv"
                ),
                "outputs": ["json", "frame_csv"],
            },
            {
                "id": "a214_runner",
                "kind": "research_candidate",
                "script": "group_a_plus_a214_runner.py",
                "module": "group_a_plus.runners.a214",
                "description": "A21.4 MA60 bond30/cash30 recovery-ramp research runner.",
                "command_template": (
                    "python3 group_a_plus_a214_runner.py --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a214_{label}.json "
                    "--frame-output results/group_a_plus_runner_a214_{label}_frame.csv"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.runners.a214 --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a214_{label}.json "
                    "--frame-output results/group_a_plus_runner_a214_{label}_frame.csv"
                ),
                "outputs": ["json", "frame_csv"],
            },
            {
                "id": "a215_runner",
                "kind": "shadow_candidate",
                "script": "group_a_plus_a215_runner.py",
                "module": "group_a_plus.runners.a215",
                "description": "A21.5 MA80 cash40 train-selected shadow runner.",
                "command_template": (
                    "python3 group_a_plus_a215_runner.py --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a215_{label}.json "
                    "--frame-output results/group_a_plus_runner_a215_{label}_frame.csv"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.runners.a215 --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a215_{label}.json "
                    "--frame-output results/group_a_plus_runner_a215_{label}_frame.csv"
                ),
                "outputs": ["json", "frame_csv"],
            },
            {
                "id": "a216_runner",
                "kind": "research_candidate",
                "script": "group_a_plus_a216_runner.py",
                "module": "group_a_plus.runners.a216",
                "description": "A21.6 severity-scaled cash40 defense research runner.",
                "command_template": (
                    "python3 group_a_plus_a216_runner.py --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a216_{label}.json "
                    "--frame-output results/group_a_plus_runner_a216_{label}_frame.csv"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.runners.a216 --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a216_{label}.json "
                    "--frame-output results/group_a_plus_runner_a216_{label}_frame.csv"
                ),
                "outputs": ["json", "frame_csv"],
            },
            {
                "id": "a2110_runner",
                # Fable audit (2026-07-28, #5): not in SUPPORTED_STRATEGIES,
                # not in _LEGACY_COVERED_MODULES, and not referenced by any
                # other module in the repo -- an orphaned candidate runner
                # left on disk with no catalog record of its status.
                "kind": "archived",
                "script": "group_a_plus_a2110_runner.py",
                "module": "group_a_plus.runners.a2110",
                "description": "A21.10 semi-defensive intermediate allocation research runner (Direction C, superseded).",
                "command_template": (
                    "python3 group_a_plus_a2110_runner.py --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a2110_{label}.json "
                    "--frame-output results/group_a_plus_runner_a2110_{label}_frame.csv"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.runners.a2110 --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a2110_{label}.json "
                    "--frame-output results/group_a_plus_runner_a2110_{label}_frame.csv"
                ),
                "outputs": ["json", "frame_csv"],
            },
            {
                "id": "a218_runner",
                # Fable audit (2026-07-28, #5): same orphan pattern as a2110
                # above -- absent from every governance list, unreferenced.
                "kind": "archived",
                "script": "group_a_plus_a218_runner.py",
                "module": "group_a_plus.runners.a218",
                "description": "A21.8 risk-override entry research runner (superseded).",
                "command_template": (
                    "python3 group_a_plus_a218_runner.py --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a218_{label}.json "
                    "--frame-output results/group_a_plus_runner_a218_{label}_frame.csv"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.runners.a218 --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a218_{label}.json "
                    "--frame-output results/group_a_plus_runner_a218_{label}_frame.csv"
                ),
                "outputs": ["json", "frame_csv"],
            },
            {
                "id": "a219_runner",
                # Fable audit (2026-07-28, #5): same orphan pattern as a2110
                # above -- absent from every governance list, unreferenced.
                "kind": "archived",
                "script": "group_a_plus_a219_runner.py",
                "module": "group_a_plus.runners.a219",
                "description": "A21.9 low-risk fast-exit research runner (Direction B, superseded).",
                "command_template": (
                    "python3 group_a_plus_a219_runner.py --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a219_{label}.json "
                    "--frame-output results/group_a_plus_runner_a219_{label}_frame.csv"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.runners.a219 --start {start} --end {end} "
                    "--output results/group_a_plus_runner_a219_{label}.json "
                    "--frame-output results/group_a_plus_runner_a219_{label}_frame.csv"
                ),
                "outputs": ["json", "frame_csv"],
            },
            {
                "id": "latest_runner",
                "kind": "active_dispatcher",
                "script": "group_a_plus_latest_runner.py",
                "module": "group_a_plus.runners.latest",
                "description": "Schema-v2 dispatcher for the active GroupA+ strategy.",
                "command_template": (
                    "python3 group_a_plus_latest_runner.py --start {start} --end {end} "
                    "--output results/group_a_plus_runner_latest_{label}.json "
                    "--frame-output results/group_a_plus_runner_latest_{label}_frame.csv"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.runners.latest --start {start} --end {end} "
                    "--output results/group_a_plus_runner_latest_{label}.json "
                    "--frame-output results/group_a_plus_runner_latest_{label}_frame.csv"
                ),
                "outputs": ["json", "frame_csv"],
            },
            {
                "id": "live_signal_v2",
                "kind": "active_operation",
                "script": "group_a_plus_live_signal.py",
                "module": "group_a_plus.operations.daily_signal",
                "description": "Execution-guarded daily target signal for schema-v2 latest.",
                "command_template": (
                    "python3 group_a_plus_live_signal.py --as-of {end} "
                    "--output results/group_a_plus_live_signal_{label}.json"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.operations.daily_signal --as-of {end} "
                    "--output results/group_a_plus_live_signal_{label}.json"
                ),
                "outputs": ["json", "latest_pointer_json"],
            },
            {
                "id": "execution_plan_v2",
                "kind": "active_operation",
                "script": "group_a_plus_execution_plan.py",
                "module": "group_a_plus.operations.execution_plan",
                "description": (
                    "Cost-aware trade plan from Group A++ workbook holdings. Requires a real cash "
                    "balance; unattended daily pipeline intentionally does not regenerate this plan."
                ),
                "command_template": (
                    "python3 group_a_plus_execution_plan.py --as-of {end} "
                    "--cash-balance {cash_balance} --compounding-regime latest "
                    "--output results/group_a_plus_execution_plan_{label}.json"
                ),
                "module_command_template": (
                    "python3 -m group_a_plus.operations.execution_plan --as-of {end} "
                    "--cash-balance {cash_balance} --compounding-regime latest "
                    "--output results/group_a_plus_execution_plan_{label}.json"
                ),
                "required_runtime_inputs": ["cash_balance"],
                "manual_only_reason": "portfolio workbook has no reliable cash field",
                "guards": [
                    "volatility_gate_no_00631l_add",
                    "a2118_extreme_risk_no_new_adds",
                    "compounding_regime_no_00631l_add",
                    "portfolio_snapshot_mismatch",
                    "compounding_regime_date_alignment",
                ],
                "outputs": ["json", "latest_pointer_json"],
            },
        ]
        + _supported_strategy_runner_entries(active_strategy_id),
        "compare_command_template": (
            "python3 compare_group_a_plus_results.py "
            "--baseline results/group_a_plus_runner_a207_{label}.json "
            "--candidates results/group_a_plus_*_{label}.json "
            "--output results/group_a_plus_compare_{label}.json"
        ),
        "module_compare_command_template": (
            "python3 -m group_a_plus.governance.compare "
            "--baseline results/group_a_plus_runner_a207_{label}.json "
            "--candidates results/group_a_plus_*_{label}.json "
            "--output results/group_a_plus_compare_{label}.json"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--output", default="results/group_a_plus_runner_catalog_20260619.json")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.governance.catalog")
    payload = std.success(build_catalog(args.start, args.end))
    write_standard_output(payload, args.output)
    print(f"Catalog: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
