#!/usr/bin/env python3
"""Build a turnover-capped shadow from an existing execution plan.

Research-only.  This answers: if we keep the production turnover cap, which
part of today's plan can be executed without changing the model target?
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.operations.execution_plan import _build_trades


DEFAULT_PLAN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "turnover_capped_execution_shadow_20260715.json"


def _read_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["data"] if isinstance(payload.get("data"), dict) else payload


def _priority(trade: dict[str, Any], mode: str) -> tuple[int, str]:
    ticker = str(trade.get("ticker") or "")
    side = str(trade.get("side") or "")
    if mode == "sell_first":
        return (0 if side == "sell" else 1, ticker)
    if mode == "buys_first":
        return (0 if side == "buy" else 1, ticker)
    if mode == "risk_first":
        if side == "buy" and ticker == "00631L.TW":
            return (0, ticker)
        if side == "buy" and ticker == "0050.TW":
            return (1, ticker)
        return (2 if side == "sell" else 3, ticker)
    raise ValueError(f"unknown priority mode: {mode}")


def _apply_trade(targets: dict[str, int], trade: dict[str, Any], shares: int) -> None:
    current = int(trade["current_shares"])
    side = str(trade["side"])
    ticker = str(trade["ticker"])
    if shares <= 0:
        targets[ticker] = current
    elif side == "buy":
        targets[ticker] = current + shares
    else:
        targets[ticker] = current - shares


def _parse_target_overrides(items: list[str]) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"target override must be TICKER=SHARES, got: {item}")
        ticker, raw_shares = item.split("=", 1)
        overrides[ticker.strip()] = int(raw_shares.strip())
    return overrides


def turnover_capped_shadow(
    plan: dict[str, Any],
    *,
    cap_ratio: float,
    priority_mode: str,
    target_overrides: dict[str, int] | None = None,
) -> dict[str, Any]:
    total_assets = float(plan["current_total_assets"])
    max_turnover = total_assets * float(cap_ratio)
    prices = {str(k): float(v) for k, v in (plan.get("current_prices") or {}).items()}
    current = {str(k): int(v) for k, v in (plan.get("current_holdings") or {}).items()}
    full_targets = {str(k): int(v) for k, v in (plan.get("target_shares") or {}).items()}
    full_targets.update(target_overrides or {})
    controls = plan.get("execution_controls") or {}
    commission_rate = float(controls.get("effective_commission_rate", controls.get("published_commission_rate", 0.001425)))
    slippage_rate = float(controls.get("slippage_rate", 0.0005))
    # execution_controls does not currently expose sell tax as a separate field;
    # use the same default as execution_plan.py.
    equity_etf_sell_tax = 0.001

    full_trades, full_totals = _build_trades(current, full_targets, prices, commission_rate, slippage_rate, equity_etf_sell_tax)
    shadow_targets = dict(current)
    remaining = max_turnover
    executed: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []

    for trade in sorted(full_trades, key=lambda item: _priority(item, priority_mode)):
        full_delta = abs(int(trade["delta_shares"]))
        price = float(trade["price"])
        max_shares = min(full_delta, int(math.floor(max(remaining, 0.0) / max(price, 1e-12))))
        if max_shares <= 0:
            _apply_trade(shadow_targets, trade, 0)
            deferred.append({**trade, "deferred_delta_shares": int(trade["delta_shares"]), "reason": "turnover_cap_exhausted"})
            continue
        _apply_trade(shadow_targets, trade, max_shares)
        executed_delta = max_shares if trade["side"] == "buy" else -max_shares
        remaining -= max_shares * price
        if max_shares < full_delta:
            deferred_delta = int(trade["delta_shares"]) - executed_delta
            deferred.append(
                {
                    **trade,
                    "executed_delta_shares": executed_delta,
                    "deferred_delta_shares": deferred_delta,
                    "reason": "partially_deferred_by_turnover_cap",
                }
            )

    shadow_trades, shadow_totals = _build_trades(current, shadow_targets, prices, commission_rate, slippage_rate, equity_etf_sell_tax)
    for trade in shadow_trades:
        executed.append(trade)

    return {
        "cap_ratio": float(cap_ratio),
        "priority_mode": priority_mode,
        "current_total_assets": total_assets,
        "max_turnover_notional": max_turnover,
        "full_plan": {
            "target_shares": full_targets,
            "target_overrides": target_overrides or {},
            "turnover_notional": full_totals["turnover_notional"],
            "turnover_ratio": full_totals["turnover_notional"] / total_assets,
            "trades": full_trades,
        },
        "shadow_plan": {
            "target_shares": shadow_targets,
            "turnover_notional": shadow_totals["turnover_notional"],
            "turnover_ratio": shadow_totals["turnover_notional"] / total_assets,
            "buy_notional": shadow_totals["buy_notional"],
            "sell_notional": shadow_totals["sell_notional"],
            "total_execution_cost": shadow_totals["total_execution_cost"],
            "trades": shadow_trades,
            "deferred_trades": deferred,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--cap-ratio", type=float, default=0.50)
    parser.add_argument("--priority-mode", choices=("sell_first", "buys_first", "risk_first"), default="buys_first")
    parser.add_argument(
        "--target-override",
        action="append",
        default=[],
        help="Research-only target override in TICKER=SHARES form. May be repeated.",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    plan_path = Path(args.execution_plan)
    if not plan_path.is_absolute():
        plan_path = PROJECT_ROOT / plan_path
    payload = {
        "schema_version": 1,
        "experiment": "turnover_capped_execution_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "execution_plan_path": str(plan_path),
        "result": turnover_capped_shadow(
            _read_plan(plan_path),
            cap_ratio=args.cap_ratio,
            priority_mode=args.priority_mode,
            target_overrides=_parse_target_overrides(args.target_override),
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(json.dumps(payload["result"]["shadow_plan"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
