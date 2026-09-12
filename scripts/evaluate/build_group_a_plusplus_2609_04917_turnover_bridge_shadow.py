#!/usr/bin/env python3
"""Build a 2609.04917 turnover-cap execution bridge shadow.

This is a research-only bridge between a same-day execution plan and the
alpha-translation gates. It never writes the official execution_plan.json and
never marks execution as allowed.
"""

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

DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "results/group_a_plus_execution_plan_a2120_shadow_snapshot_20260909.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_04917_turnover_bridge_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2609_04917_turnover_bridge_shadow/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else payload


def _int_map(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): int(v) for k, v in raw.items() if k != "cash"}


def _float_map(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): float(v) for k, v in raw.items() if k != "cash"}


def _trade_notional(current: dict[str, int], target: dict[str, int], prices: dict[str, float]) -> float:
    tickers = set(current) | set(target)
    return float(sum(abs(int(target.get(t, 0)) - int(current.get(t, 0))) * float(prices.get(t, 0.0)) for t in tickers))


def _trade_rows(current: dict[str, int], target: dict[str, int], prices: dict[str, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker in sorted(set(current) | set(target)):
        delta = int(target.get(ticker, 0)) - int(current.get(ticker, 0))
        if delta == 0:
            continue
        price = float(prices.get(ticker, 0.0))
        rows.append(
            {
                "ticker": ticker,
                "side": "buy" if delta > 0 else "sell",
                "current_shares": int(current.get(ticker, 0)),
                "target_shares": int(target.get(ticker, 0)),
                "delta_shares": delta,
                "price": price,
                "notional": float(abs(delta) * price),
            }
        )
    return rows


def _planned_trades(
    current: dict[str, int],
    full_target: dict[str, int],
    prices: dict[str, float],
    disallow_add: set[str],
) -> tuple[list[tuple[str, int, float, str]], list[tuple[str, int, float, str]]]:
    sells: list[tuple[str, int, float, str]] = []
    buys: list[tuple[str, int, float, str]] = []
    for ticker in sorted(set(current) | set(full_target)):
        cur = int(current.get(ticker, 0))
        tgt = int(full_target.get(ticker, 0))
        delta = tgt - cur
        price = float(prices.get(ticker, 0.0))
        if price <= 0 or delta == 0:
            continue
        if delta < 0:
            reason = "target_zero_or_reduction"
            sells.append((ticker, delta, abs(delta) * price, reason))
        elif ticker in disallow_add:
            continue
        else:
            buys.append((ticker, delta, abs(delta) * price, "allowed_non_leveraged_buy"))
    sells.sort(key=lambda item: (full_target.get(item[0], 0) != 0, -item[2], item[0]))
    buys.sort(key=lambda item: (-item[2], item[0]))
    return sells, buys


def _apply_trade(
    target: dict[str, int],
    ticker: str,
    requested_delta: int,
    price: float,
    remaining_notional: float,
) -> tuple[int, float]:
    if price <= 0 or remaining_notional <= 0:
        return 0, remaining_notional
    max_shares = int(remaining_notional // price)
    shares = min(abs(requested_delta), max_shares)
    if shares <= 0:
        return 0, remaining_notional
    signed = shares if requested_delta > 0 else -shares
    target[ticker] = int(target.get(ticker, 0)) + signed
    return signed, remaining_notional - shares * price


def build_bridge(
    *,
    execution_plan: dict[str, Any],
    max_turnover: float,
    disallow_add: set[str],
) -> dict[str, Any]:
    current = _int_map(execution_plan.get("current_holdings"))
    full_target = _int_map(execution_plan.get("target_shares"))
    prices = _float_map(execution_plan.get("current_prices"))
    nav = float(execution_plan.get("current_total_assets") or 0.0)
    blockers: list[str] = []
    warnings: list[str] = []
    if not current:
        blockers.append("current_holdings_missing")
    if not full_target:
        blockers.append("target_shares_missing")
    if not prices:
        blockers.append("current_prices_missing")
    if nav <= 0:
        blockers.append("current_total_assets_missing")
    if max_turnover <= 0:
        blockers.append("max_turnover_not_positive")

    bridge_target = dict(current)
    budget = nav * max_turnover if nav > 0 else 0.0
    remaining = budget
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    sells, buys = _planned_trades(current, full_target, prices, disallow_add)
    for ticker, delta, notional, reason in sells + buys:
        price = float(prices.get(ticker, 0.0))
        signed, remaining = _apply_trade(bridge_target, ticker, delta, price, remaining)
        if signed == 0:
            skipped.append({"ticker": ticker, "requested_delta": delta, "reason": "turnover_budget_exhausted"})
            continue
        applied.append(
            {
                "ticker": ticker,
                "requested_delta": delta,
                "applied_delta": signed,
                "requested_notional": float(notional),
                "applied_notional": float(abs(signed) * price),
                "reason": reason,
            }
        )
        if abs(signed) < abs(delta):
            skipped.append(
                {
                    "ticker": ticker,
                    "requested_delta": delta,
                    "applied_delta": signed,
                    "reason": "partially_filled_by_turnover_cap",
                }
            )

    for ticker in sorted(disallow_add):
        cur = int(current.get(ticker, 0))
        tgt = int(full_target.get(ticker, 0))
        if tgt > cur:
            skipped.append({"ticker": ticker, "requested_delta": tgt - cur, "reason": "leveraged_add_disallowed"})

    bridge_notional = _trade_notional(current, bridge_target, prices)
    full_notional = _trade_notional(current, full_target, prices)
    bridge_turnover = bridge_notional / nav if nav > 0 else None
    full_turnover = full_notional / nav if nav > 0 else None
    if bridge_turnover is None:
        blockers.append("bridge_turnover_unavailable")
    elif bridge_turnover > max_turnover + 1e-9:
        blockers.append("bridge_turnover_exceeds_cap")

    status = "blocked" if blockers else "shadow_bridge_available_for_manual_review"
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_04917_turnover_bridge_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_turnover_cap_bridge_no_order_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2609.04917_ai_equity_crypto_markets_profitability_limits.pdf",
            "imported_concepts": [
                "portfolio_to_execution_translation_must_be_feasible",
                "joint_signal_portfolio_execution_evaluation",
                "implementation_realism_before_profit_claim",
            ],
        },
        "status": status,
        "as_of": execution_plan.get("requested_as_of_date") or execution_plan.get("actual_data_date"),
        "actual_data_date": execution_plan.get("actual_data_date"),
        "limits": {
            "max_turnover": float(max_turnover),
            "disallow_add": sorted(disallow_add),
        },
        "computed": {
            "nav": nav,
            "full_target_notional": float(full_notional),
            "full_target_turnover": full_turnover,
            "bridge_notional": float(bridge_notional),
            "bridge_turnover": bridge_turnover,
            "turnover_reduction": None if full_turnover is None or bridge_turnover is None else float(full_turnover - bridge_turnover),
            "remaining_turnover_budget_notional": float(max(0.0, remaining)),
        },
        "current_holdings": current,
        "current_prices": prices,
        "full_target_shares": full_target,
        "bridge_target_shares": bridge_target,
        "target_shares": bridge_target,
        "current_total_assets": nav,
        "execution_allowed": False,
        "planning_status": "shadow_bridge_manual_review_required",
        "bridge_trades": _trade_rows(current, bridge_target, prices),
        "applied_trade_plan": applied,
        "skipped_trade_plan": skipped,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "execution_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "summary": "Shadow bridge only; it can reduce turnover pressure but cannot override rebalance, market-impact, or human-approval gates.",
        },
    }


def write_report(report: dict[str, Any], output: Path, markdown: Path | None, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown is not None:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(report.get("as_of") or "unknown").replace("-", "")
        (history_dir / f"2609_04917_turnover_bridge_shadow_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _markdown(report: dict[str, Any]) -> str:
    computed = report.get("computed") or {}
    lines = [
        "# 2609.04917 Turnover Bridge Shadow",
        "",
        f"- status: {report.get('status')}",
        f"- actual_data_date: {report.get('actual_data_date')}",
        f"- full_target_turnover: {computed.get('full_target_turnover')}",
        f"- bridge_turnover: {computed.get('bridge_turnover')}",
        f"- turnover_reduction: {computed.get('turnover_reduction')}",
        f"- execution_allowed: {report.get('decision', {}).get('execution_allowed')}",
        "",
        "## Bridge Trades",
        "",
        "| ticker | side | current | target | delta | notional |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in report.get("bridge_trades") or []:
        lines.append(
            f"| {row['ticker']} | {row['side']} | {row['current_shares']} | {row['target_shares']} | "
            f"{row['delta_shares']} | {row['notional']:.2f} |"
        )
    lines.extend(["", "## Skipped", "", "| ticker | requested_delta | reason |", "| --- | ---: | --- |"])
    for row in report.get("skipped_trade_plan") or []:
        lines.append(f"| {row['ticker']} | {row['requested_delta']} | {row['reason']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--max-turnover", type=float, default=0.50)
    parser.add_argument("--disallow-add", default="00631L.TW")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    plan_path = _resolve(args.execution_plan)
    disallow_add = {item.strip() for item in str(args.disallow_add).split(",") if item.strip()}
    report = build_bridge(
        execution_plan=_load_json(plan_path),
        max_turnover=float(args.max_turnover),
        disallow_add=disallow_add,
    )
    report["inputs"] = {"execution_plan": str(plan_path)}
    write_report(
        report,
        _resolve(args.output),
        _resolve(args.markdown) if args.markdown else None,
        None if args.no_history else _resolve(args.history_dir),
    )
    print(json.dumps({"output": str(_resolve(args.output)), "status": report["status"], "computed": report["computed"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
