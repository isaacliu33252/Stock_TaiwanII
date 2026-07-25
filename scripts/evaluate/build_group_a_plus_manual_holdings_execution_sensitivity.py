#!/usr/bin/env python3
"""Build manual-holdings execution sensitivity for GroupA+.

This is a scenario checker for uncertain broker inputs. It does not update the
production execution-plan pointer.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY
from group_a_plus.operations.execution_plan import build_execution_plan


DEFAULT_HOLDINGS = PROJECT_ROOT / "config/group_a_plus_holdings_20260720_manual.json"
DEFAULT_COMP_REGIME = PROJECT_ROOT / "results/00631l_leveraged_compounding_regime_20260720.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/group_a_plus_manual_holdings_execution_sensitivity_20260720.json"
DEFAULT_CSV = PROJECT_ROOT / "results/group_a_plus_manual_holdings_execution_sensitivity_20260720.csv"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _parse_int_list(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_float_list(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _load_base_holdings(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    holdings = payload.get("holdings") if isinstance(payload, dict) else None
    if not isinstance(holdings, dict):
        raise ValueError(f"{path} has no holdings object")
    return {str(ticker): int(round(float(shares))) for ticker, shares in holdings.items()}


def _trade_delta(plan: dict[str, Any], ticker: str, side: str) -> int:
    return int(
        sum(
            abs(int(trade.get("delta_shares", 0) or 0))
            for trade in plan.get("trades", []) or []
            if isinstance(trade, dict) and trade.get("ticker") == ticker and trade.get("side") == side
        )
    )


def _blocked_add(plan: dict[str, Any], ticker: str) -> tuple[int, float]:
    summary = plan.get("guard_impact_summary") or {}
    rows = summary.get("combined_blocked_buys") or []
    blocked_shares = 0
    blocked_notional = 0.0
    for row in rows:
        if not isinstance(row, dict) or row.get("ticker") != ticker:
            continue
        blocked_shares += int(row.get("blocked_delta_shares", 0) or 0)
        blocked_notional += float(row.get("blocked_notional", 0.0) or 0.0)
    return blocked_shares, blocked_notional


def _summarize_plan(plan: dict[str, Any], *, cash_balance: float, bond_shares: int) -> dict[str, Any]:
    blocked_631l, blocked_notional = _blocked_add(plan, "00631L.TW")
    guards = plan.get("guard_impact_summary") or {}
    return {
        "cash_balance": cash_balance,
        "00679b_shares": bond_shares,
        "current_total_assets": plan.get("current_total_assets"),
        "planning_status": plan.get("planning_status"),
        "execution_allowed": plan.get("execution_allowed"),
        "actual_data_date": plan.get("actual_data_date"),
        "target_0050": (plan.get("target_shares") or {}).get("0050.TW"),
        "target_00631l": (plan.get("target_shares") or {}).get("00631L.TW"),
        "target_00632r": (plan.get("target_shares") or {}).get("00632R.TW"),
        "target_00679b": (plan.get("target_shares") or {}).get("00679B.TWO"),
        "sell_0050_shares": _trade_delta(plan, "0050.TW", "sell"),
        "sell_00679b_shares": _trade_delta(plan, "00679B.TWO", "sell"),
        "buy_00631l_shares": _trade_delta(plan, "00631L.TW", "buy"),
        "blocked_00631l_add_shares": blocked_631l,
        "blocked_00631l_add_notional": blocked_notional,
        "blocked_guard_names": guards.get("blocked_guard_names") or [],
        "active_guard_names": guards.get("active_guard_names") or [],
    }


def build_sensitivity(
    *,
    base_holdings_path: Path = DEFAULT_HOLDINGS,
    cash_balances: list[float],
    bond_share_scenarios: list[int],
    as_of: str,
    compounding_regime_path: Path | None,
    db_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    base_holdings = _load_base_holdings(base_holdings_path)
    rows: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="group_a_plus_manual_holdings_") as tmp:
        tmp_dir = Path(tmp)
        for cash_balance in cash_balances:
            for bond_shares in bond_share_scenarios:
                holdings = dict(base_holdings)
                holdings["00679B.TWO"] = bond_shares
                scenario_path = tmp_dir / f"holdings_cash_{int(cash_balance)}_bond_{bond_shares}.json"
                scenario_path.write_text(
                    json.dumps({"holdings": holdings}, ensure_ascii=False),
                    encoding="utf-8",
                )
                plan = build_execution_plan(
                    Path("unused_when_holdings_json_is_set.xlsx"),
                    as_of,
                    cash_balance,
                    3,
                    db_path,
                    manifest_path,
                    compounding_regime_path=compounding_regime_path,
                    holdings_json_path=scenario_path,
                )
                rows.append(_summarize_plan(plan, cash_balance=cash_balance, bond_shares=bond_shares))
    all_block_631l_add = all(int(row["blocked_00631l_add_shares"] or 0) > 0 for row in rows)
    any_00632r_open = any(int(row["target_00632r"] or 0) > 0 for row in rows)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_manual_holdings_execution_sensitivity",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "manual_holdings_sensitivity_no_latest_pointer_update",
        "base_holdings_path": str(base_holdings_path),
        "cash_balances": cash_balances,
        "00679b_share_scenarios": bond_share_scenarios,
        "scenario_count": len(rows),
        "rows": rows,
        "decision": {
            "all_scenarios_block_00631l_add": all_block_631l_add,
            "any_scenario_opens_00632r": any_00632r_open,
            "promote_to_formal_execution_plan": False,
            "required_confirmation": ["actual_cash_balance", "final_00679b_shares"],
        },
    }


def write_outputs(report: dict[str, Any], output: Path, csv_output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = report.get("rows") or []
    if rows:
        csv_output.parent.mkdir(parents=True, exist_ok=True)
        with csv_output.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-holdings", default=str(DEFAULT_HOLDINGS))
    parser.add_argument("--cash-balances", default="0,100000,300000")
    parser.add_argument("--00679b-shares", dest="bond_shares", default="0,3000,5000")
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--compounding-regime", default=str(DEFAULT_COMP_REGIME))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--csv-output", default=str(DEFAULT_CSV))
    args = parser.parse_args()

    report = build_sensitivity(
        base_holdings_path=_resolve(args.base_holdings),
        cash_balances=_parse_float_list(args.cash_balances),
        bond_share_scenarios=_parse_int_list(args.bond_shares),
        as_of=args.as_of,
        compounding_regime_path=_resolve(args.compounding_regime) if args.compounding_regime else None,
        db_path=_resolve(args.db),
        manifest_path=_resolve(args.manifest),
    )
    write_outputs(report, _resolve(args.output), _resolve(args.csv_output))
    print(f"Manual holdings sensitivity JSON: {_resolve(args.output)}")
    print(f"Manual holdings sensitivity CSV: {_resolve(args.csv_output)}")
    print(
        json.dumps(
            {
                "scenario_count": report["scenario_count"],
                "all_scenarios_block_00631l_add": report["decision"]["all_scenarios_block_00631l_add"],
                "any_scenario_opens_00632r": report["decision"]["any_scenario_opens_00632r"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
