#!/usr/bin/env python3
"""Audit effective non-KEEP dates from the A21.18 DFL shadow test.

Research-only. This does not update live allocation, latest pointers, or the
execution plan. The goal is to replay only the finite-action dates that actually
changed weights, then check deployability constraints and cost/turnover impact.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import _resolve


DEFAULT_INPUT = PROJECT_ROOT / "results" / "a2118_decision_focused_action_shadow_fixed_7win_20260714_rerun.json"
DEFAULT_OVERLAP = PROJECT_ROOT / "results" / "a2118_decision_focused_action_overlap_fixed_7win_20260714_rerun.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2118_dfl_active_date_audit_latest.json"
DEFAULT_INITIAL_VALUE = 1_000_000.0


PriceLookup = Callable[[str], dict[str, float | None]]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(out):
        return default
    return out


def _decision_key(label: str, date: str) -> tuple[str, str]:
    return (str(label), str(pd.Timestamp(date).date()))


def _overlap_index(overlap_report: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    if not overlap_report:
        return out
    for item in overlap_report.get("results", []):
        label = str(item.get("label", ""))
        for decision in item.get("decisions", []) or []:
            if "date" in decision:
                out[_decision_key(label, str(decision["date"]))] = dict(decision)
    return out


def _panel_dates(panel_path: str | None) -> set[str]:
    if not panel_path:
        return set()
    resolved = _resolve(panel_path)
    if not resolved.exists():
        return set()
    panel = pd.read_csv(resolved, usecols=["date"], encoding="utf-8-sig")
    return {str(pd.Timestamp(value).date()) for value in panel["date"].dropna()}


def _default_price_lookup(db_path: Path, start: str, end: str) -> PriceLookup:
    prices = _load_prices(db_path, ["0050.TW", "00631L.TW"], start, end)
    prices.index = pd.to_datetime(prices.index).normalize()

    def lookup(date: str) -> dict[str, float | None]:
        dt = pd.Timestamp(date).normalize()
        if dt not in prices.index:
            return {"0050.TW": None, "00631L.TW": None}
        row = prices.loc[dt]
        return {
            "0050.TW": _num(row.get("0050.TW"), default=float("nan")),
            "00631L.TW": _num(row.get("00631L.TW"), default=float("nan")),
        }

    return lookup


def turnover_proxy(decision: dict[str, Any]) -> float:
    """Weight-deviation proxy vs A21.18, not exact stateful daily turnover."""

    base = _num(decision.get("base_00631l_weight"))
    final = _num(decision.get("final_00631l_weight"))
    return float(2.0 * abs(final - base))


def estimate_cap10_cost_per_initial_value(
    decision: dict[str, Any],
    *,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> dict[str, float]:
    base = _num(decision.get("base_00631l_weight"))
    final = _num(decision.get("final_00631l_weight"))
    reduced_weight = max(base - final, 0.0)
    sell_00631l_notional = reduced_weight * float(initial_value)
    buy_0050_notional = sell_00631l_notional
    sell_cost = sell_00631l_notional * (commission_rate + slippage_rate + equity_etf_sell_tax)
    buy_cost = buy_0050_notional * (commission_rate + slippage_rate)
    return {
        "sell_00631l_notional": float(sell_00631l_notional),
        "buy_0050_notional": float(buy_0050_notional),
        "estimated_cost": float(sell_cost + buy_cost),
        "estimated_cost_bps": float((sell_cost + buy_cost) / max(float(initial_value), 1e-12) * 10_000.0),
    }


def _share_delta_estimates(
    decision: dict[str, Any],
    *,
    prices: dict[str, float | None],
    initial_value: float,
) -> dict[str, float | None]:
    base = _num(decision.get("base_00631l_weight"))
    final = _num(decision.get("final_00631l_weight"))
    reduced_notional = max(base - final, 0.0) * float(initial_value)
    price_00631l = prices.get("00631L.TW")
    price_0050 = prices.get("0050.TW")
    return {
        "00631L.TW": float(-reduced_notional / price_00631l) if price_00631l and price_00631l > 0 else None,
        "0050.TW": float(reduced_notional / price_0050) if price_0050 and price_0050 > 0 else None,
    }


def _audit_decision(
    *,
    item: dict[str, Any],
    decision: dict[str, Any],
    method: dict[str, Any],
    overlap: dict[str, Any] | None,
    panel_dates: set[str],
    price_lookup: PriceLookup,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    min_trade_notional: float,
) -> dict[str, Any]:
    date = str(pd.Timestamp(decision["date"]).date())
    action = str(decision.get("action", ""))
    actions = set(method.get("actions", []))
    stabilizers = method.get("stabilizers", {}) or {}
    edge_threshold = _num(stabilizers.get("edge_threshold"), default=0.0005)
    reenter_edge_threshold = _num(stabilizers.get("reenter_edge_threshold"), default=edge_threshold)
    regret_clip = _num(stabilizers.get("regret_clip"), default=0.02)
    turnover_cap = _num(stabilizers.get("turnover_cap"), default=0.05)

    predicted_regret = _num(decision.get("predicted_regret"))
    edge_pass_threshold = reenter_edge_threshold if action == "REENTER" else edge_threshold
    turnover = turnover_proxy(decision)
    cost = estimate_cap10_cost_per_initial_value(
        decision,
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    prices = price_lookup(date)
    share_deltas = _share_delta_estimates(decision, prices=prices, initial_value=initial_value)
    notional = max(cost["sell_00631l_notional"], cost["buy_0050_notional"])
    overlap = overlap or {}

    warnings = {
        "turnover_proxy_above_cap": bool(turnover > turnover_cap),
    }
    checks = {
        "finite_action": bool(action in actions),
        "action_allowed": bool(decision.get("action_allowed", False)),
        "panel_date_available": bool(date in panel_dates),
        "edge_pass": bool(predicted_regret > edge_pass_threshold),
        "within_regret_clip": bool(abs(predicted_regret) <= regret_clip),
        "turnover_cap_configured": bool(turnover_cap > 0.0),
        "min_trade_notional_pass": bool(notional >= float(min_trade_notional)),
        "price_available": bool(prices.get("0050.TW") and prices.get("00631L.TW")),
    }
    checks["all_pass"] = bool(all(checks.values()))

    return {
        "date": date,
        "label": item.get("label"),
        "bucket": item.get("bucket"),
        "window": item.get("window"),
        "ncf_panel": item.get("ncf_panel"),
        "action": action,
        "predicted_regret": predicted_regret,
        "predicted_regrets": decision.get("predicted_regrets", {}),
        "edge_threshold_used": float(edge_pass_threshold),
        "base_00631l_weight": _num(decision.get("base_00631l_weight")),
        "final_00631l_weight": _num(decision.get("final_00631l_weight")),
        "delta_00631l_weight": _num(decision.get("final_00631l_weight")) - _num(decision.get("base_00631l_weight")),
        "turnover_proxy": turnover,
        "estimated_cost_per_initial_value": cost,
        "prices": prices,
        "share_delta_estimates_per_initial_value": share_deltas,
        "existing_guard_overlap": {
            "volatility_gate": overlap.get("volatility_gate"),
            "volatility_high_vol": bool(overlap.get("volatility_high_vol", False)),
            "a2118_extreme_warning_proxy": bool(overlap.get("a2118_extreme_warning_proxy", False)),
            "covered_by_existing_guard": bool(overlap.get("covered_by_existing_guard", False)),
        },
        "checks": checks,
        "warnings": warnings,
    }


def build_active_date_audit(
    dfl_report: dict[str, Any],
    *,
    overlap_report: dict[str, Any] | None = None,
    price_lookup: PriceLookup | None = None,
    initial_value: float = DEFAULT_INITIAL_VALUE,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
    min_trade_notional: float = 5_000.0,
) -> dict[str, Any]:
    method = dfl_report.get("method", {}) or {}
    overlap = _overlap_index(overlap_report)
    panels: dict[str, set[str]] = {}
    decisions: list[dict[str, Any]] = []
    all_dates: list[str] = []
    for item in dfl_report.get("results", []) or []:
        panel_path = item.get("ncf_panel")
        panels.setdefault(str(panel_path), _panel_dates(panel_path))
        for decision in item.get("non_keep_decisions", []) or []:
            if "date" in decision:
                all_dates.append(str(pd.Timestamp(decision["date"]).date()))

    if price_lookup is None and all_dates:
        price_lookup = _default_price_lookup(
            _resolve(DB_PATH),
            min(all_dates),
            max(all_dates),
        )
    if price_lookup is None:
        price_lookup = lambda _date: {"0050.TW": None, "00631L.TW": None}

    for item in dfl_report.get("results", []) or []:
        label = str(item.get("label", ""))
        panel_path = str(item.get("ncf_panel"))
        for decision in item.get("non_keep_decisions", []) or []:
            if "date" not in decision:
                continue
            key = _decision_key(label, str(decision["date"]))
            decisions.append(
                _audit_decision(
                    item=item,
                    decision=decision,
                    method=method,
                    overlap=overlap.get(key),
                    panel_dates=panels.get(panel_path, set()),
                    price_lookup=price_lookup,
                    initial_value=initial_value,
                    commission_rate=commission_rate,
                    slippage_rate=slippage_rate,
                    equity_etf_sell_tax=equity_etf_sell_tax,
                    min_trade_notional=min_trade_notional,
                )
            )

    action_counts: dict[str, int] = {}
    for row in decisions:
        action_counts[row["action"]] = action_counts.get(row["action"], 0) + 1
    total_cost = sum(row["estimated_cost_per_initial_value"]["estimated_cost"] for row in decisions)
    covered = sum(1 for row in decisions if row["existing_guard_overlap"]["covered_by_existing_guard"])
    fail_rows = [row for row in decisions if not row["checks"]["all_pass"]]
    warning_rows = [row for row in decisions if any(row.get("warnings", {}).values())]
    summary = {
        "active_days": int(len(decisions)),
        "action_counts": action_counts,
        "all_checks_pass": bool(not fail_rows),
        "failed_days": int(len(fail_rows)),
        "warning_days": int(len(warning_rows)),
        "existing_guard_overlap_days": int(covered),
        "max_turnover_proxy": float(max((row["turnover_proxy"] for row in decisions), default=0.0)),
        "total_estimated_cost_per_initial_value": float(total_cost),
        "total_estimated_cost_bps": float(total_cost / max(float(initial_value), 1e-12) * 10_000.0),
        "max_estimated_cost_bps_single_day": float(
            max((row["estimated_cost_per_initial_value"]["estimated_cost_bps"] for row in decisions), default=0.0)
        ),
    }
    if decisions and summary["all_checks_pass"] and covered == 0:
        conclusion = (
            "passes_replay_audit_with_warnings_shadow_only"
            if warning_rows
            else "passes_replay_audit_shadow_only"
        )
    else:
        conclusion = "review_required_shadow_only"
    return {
        "report_type": "a2118_dfl_active_date_audit",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_status": dfl_report.get("status"),
        "method": method,
        "assumptions": {
            "initial_value": float(initial_value),
            "commission_rate": float(commission_rate),
            "slippage_rate": float(slippage_rate),
            "equity_etf_sell_tax": float(equity_etf_sell_tax),
            "min_trade_notional": float(min_trade_notional),
            "turnover_proxy": "CAP10 reduction in 00631L is assumed to move into 0050, so turnover=2*abs(delta_00631L_weight)",
            "turnover_proxy_note": "For stateful_actions=true, this is a deviation proxy versus A21.18, not exact same-day model turnover.",
            "policy": "shadow_only_no_auto_weight_change",
        },
        "summary": summary,
        "conclusion": conclusion,
        "decisions": decisions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--overlap", default=str(DEFAULT_OVERLAP))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--initial-value", type=float, default=DEFAULT_INITIAL_VALUE)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--min-trade-notional", type=float, default=5_000.0)
    args = parser.parse_args()

    input_path = _resolve(args.input)
    overlap_path = _resolve(args.overlap)
    dfl_report = json.loads(input_path.read_text(encoding="utf-8"))
    overlap_report = json.loads(overlap_path.read_text(encoding="utf-8")) if overlap_path.exists() else None
    payload = build_active_date_audit(
        dfl_report,
        overlap_report=overlap_report,
        initial_value=float(args.initial_value),
        commission_rate=float(args.commission_rate),
        slippage_rate=float(args.slippage_rate),
        equity_etf_sell_tax=float(args.equity_etf_sell_tax),
        min_trade_notional=float(args.min_trade_notional),
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    summary = payload["summary"]
    print(
        f"Active days: {summary['active_days']}, all_checks_pass={summary['all_checks_pass']}, "
        f"overlap={summary['existing_guard_overlap_days']}, "
        f"total_cost_bps={summary['total_estimated_cost_bps']:.4f}"
    )
    print(f"Conclusion: {payload['conclusion']}")


if __name__ == "__main__":
    main()
