#!/usr/bin/env python3
"""Evaluate 00631L no-add guard behavior across current-holdings scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.operations.execution_guard import apply_volatility_gate_pre_trade_guard


DEFAULT_PLAN = PROJECT_ROOT / "results" / "group_a_plus_execution_plan_dry_run_20260709.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_volatility_guard_holdings_scenarios_20260710.json"
DEFAULT_CURRENT_SHARE_SCENARIOS = [0, 100, 250, 476, 600, 1000, 1192]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _execution_stage_requested_00631l(plan: dict[str, Any]) -> int:
    guard = plan.get("pre_trade_guard") or {}
    if isinstance(guard, dict) and guard.get("requested_target_shares") is not None:
        return int(guard["requested_target_shares"])
    target_shares = plan.get("target_shares") or {}
    return int(target_shares.get("00631L.TW", 0) or 0)


def evaluate_scenarios(
    plan: dict[str, Any],
    current_00631l_shares: list[int],
    *,
    ticker: str = "00631L.TW",
) -> dict[str, Any]:
    live_signal = dict(plan.get("source_live_signal") or {})
    current_base = dict(plan.get("current_holdings") or {})
    target_base = dict(plan.get("target_shares") or {})
    requested_00631l = _execution_stage_requested_00631l(plan)
    target_base[ticker] = requested_00631l
    price = float((plan.get("current_prices") or {}).get(ticker, 0.0) or 0.0)

    rows: list[dict[str, Any]] = []
    for current in current_00631l_shares:
        scenario_current = dict(current_base)
        scenario_current[ticker] = int(current)
        guarded_targets, guard = apply_volatility_gate_pre_trade_guard(
            scenario_current,
            target_base,
            live_signal,
            ticker=ticker,
        )
        blocked_delta = 0
        if guard.get("blocked_trades"):
            blocked_delta = int(guard["blocked_trades"][0].get("blocked_delta_shares", 0) or 0)
        rows.append(
            {
                "current_00631l_shares": int(current),
                "requested_00631l_target_shares": int(requested_00631l),
                "guarded_00631l_target_shares": int(guarded_targets.get(ticker, 0) or 0),
                "guard_status": guard.get("status"),
                "blocked_delta_shares": blocked_delta,
                "blocked_notional": round(float(blocked_delta * price), 2),
                "allow_00631l_add": guard.get("allow_00631l_add"),
            }
        )

    return {
        "strategy_id": plan.get("strategy_id"),
        "actual_data_date": plan.get("actual_data_date"),
        "execution_regime": plan.get("execution_regime"),
        "ticker": ticker,
        "execution_stage_requested_00631l_shares": requested_00631l,
        "theoretical_00631l_target_shares": int((plan.get("theoretical_target_shares") or {}).get(ticker, 0) or 0),
        "price": price,
        "rows": rows,
        "summary": {
            "scenario_count": len(rows),
            "blocked_scenario_count": sum(1 for row in rows if row["guard_status"] == "blocked"),
            "max_blocked_delta_shares": max((row["blocked_delta_shares"] for row in rows), default=0),
            "max_blocked_notional": max((row["blocked_notional"] for row in rows), default=0.0),
        },
    }


def _parse_share_scenarios(raw: str | None, requested: int) -> list[int]:
    if raw:
        return [int(item.strip()) for item in raw.split(",") if item.strip()]
    defaults = list(DEFAULT_CURRENT_SHARE_SCENARIOS)
    if requested not in defaults:
        defaults.append(int(requested))
    return sorted(set(defaults))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--current-00631l-shares", default=None, help="Comma-separated current 00631L share scenarios.")
    args = parser.parse_args()

    plan_path = Path(args.plan)
    if not plan_path.is_absolute():
        plan_path = PROJECT_ROOT / plan_path
    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)

    plan = _load_json(plan_path)
    requested = _execution_stage_requested_00631l(plan)
    scenarios = _parse_share_scenarios(args.current_00631l_shares, requested)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": "scripts/evaluate/evaluate_group_a_plus_volatility_guard_holdings_scenarios.py",
        "source_plan": str(plan_path),
        "policy": "current_holdings_scenario_grid_for_pre_trade_no_00631l_add_guard",
        **evaluate_scenarios(plan, scenarios),
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pd.DataFrame(result["rows"]).to_csv(output.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    print(f"Wrote {output}")
    print(f"Wrote {output.with_suffix('.csv')}")
    print(
        "Blocked scenarios: "
        f"{result['summary']['blocked_scenario_count']}/{result['summary']['scenario_count']}"
    )


if __name__ == "__main__":
    main()
