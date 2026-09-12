#!/usr/bin/env python3
"""Build the Riccati/mean-variance GroupA+ shadow diagnostic snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.integrations.riccati_mv_shadow import MeanVarianceSpec, build_riccati_mv_shadow_report  # noqa: E402


DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"
DEFAULT_LATEST_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "riccati_mv_shadow.json"


def _resolve_execution_plan(path_text: str) -> Path:
    path = Path(path_text)
    if path.exists():
        return path
    matches = sorted(
        (PROJECT_ROOT / "results").glob("group_a_plus_execution_plan_*.json"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    if matches:
        return matches[0]
    raise FileNotFoundError(f"execution plan not found: {path}")


def _infer_as_of(payload: dict, explicit: str | None) -> str:
    if explicit:
        return explicit
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    value = data.get("actual_data_date") or data.get("requested_as_of_date")
    if not value:
        raise ValueError("--as-of is required when execution plan has no actual_data_date")
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--results-dir", default=str(PROJECT_ROOT / "results"))
    parser.add_argument("--output", default=None)
    parser.add_argument("--latest-output", default=str(DEFAULT_LATEST_OUTPUT))
    parser.add_argument("--lookback-days", type=int, default=252)
    parser.add_argument("--grid-step", type=float, default=0.025)
    parser.add_argument("--min-cash", type=float, default=0.20)
    parser.add_argument("--variance-penalty", type=float, default=35.0)
    args = parser.parse_args()

    execution_plan_path = _resolve_execution_plan(args.execution_plan)
    execution_plan = json.loads(execution_plan_path.read_text(encoding="utf-8-sig"))
    as_of = _infer_as_of(execution_plan, args.as_of)
    spec = MeanVarianceSpec(
        lookback_days=args.lookback_days,
        grid_step=args.grid_step,
        min_cash=args.min_cash,
        variance_penalty=args.variance_penalty,
    )
    report = build_riccati_mv_shadow_report(
        db_path=Path(args.db),
        as_of=as_of,
        execution_plan=execution_plan,
        results_dir=Path(args.results_dir),
        spec=spec,
    )
    report["input_execution_plan"] = str(execution_plan_path)

    output = Path(args.output) if args.output else Path(args.results_dir) / f"riccati_mv_shadow_{as_of.replace('-', '')}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    latest_output = Path(args.latest_output)
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    latest_vol = report["risk_state"]["latest_target_stats"]["annualized_volatility"]
    shadow_vol = report["risk_state"]["shadow_target_stats"]["annualized_volatility"]
    print(f"Riccati MV shadow status={report['status']} latest_vol={latest_vol:.2%} shadow_vol={shadow_vol:.2%}")
    print(f"Recommendations: {', '.join(report['recommendations'])}")
    print(f"Output: {output}")
    print(f"Latest: {latest_output}")


if __name__ == "__main__":
    main()
