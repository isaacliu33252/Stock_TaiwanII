#!/usr/bin/env python3
"""Build the GroupA+ latest-strategy 00632R discipline guard.

00632R is a tactical inverse ETF, not a regular accumulation asset. This guard
keeps the latest strategy's default inverse exposure at zero and blocks DCA,
averaging down, or discretionary inverse adds unless the dedicated hedge gates
explicitly allow them.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal.json"
DEFAULT_LETF_READINESS = PROJECT_ROOT / "report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json"
DEFAULT_TAIL_GATE = PROJECT_ROOT / "report/group_a_plus/latest/00632r_tail_tracking_error_gate_review.json"
DEFAULT_TRADE_CHECK = PROJECT_ROOT / "0501_0904_check.xlsx"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/00632r_discipline_guard.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/00632r_discipline_guard.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/00632r_discipline_guard/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _trade_check_00632r_dca_count(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        if "trade_check" not in wb.sheetnames:
            return None
        ws = wb["trade_check"]
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        idx = {header: pos for pos, header in enumerate(headers)}
        count = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[idx.get("ticker")] == "00632R.TW" and row[idx.get("side")] == "buy":
                count += 1
        return count
    except Exception:
        return None


def build_guard(
    *,
    live_signal_path: Path,
    letf_readiness_path: Path,
    tail_gate_path: Path,
    trade_check_path: Path | None,
    max_manual_weight: float,
) -> dict[str, Any]:
    live = _unwrap(_load(live_signal_path))
    letf = _unwrap(_load(letf_readiness_path))
    tail = _unwrap(_load(tail_gate_path))
    weights = live.get("target_weights") if isinstance(live.get("target_weights"), dict) else {}
    current_weight = _float(weights.get("00632R.TW"), 0.0)
    letf_decision = letf.get("decision") if isinstance(letf.get("decision"), dict) else {}
    tail_decision = tail.get("decision") if isinstance(tail.get("decision"), dict) else {}
    dca_count = _trade_check_00632r_dca_count(trade_check_path) if trade_check_path is not None else None

    hedge_gate_allows_open = (
        letf_decision.get("allow_00632r_open") is True
        and tail_decision.get("allow_00632r_open") is True
        and tail_decision.get("manual_hedge_discussion_allowed") is True
    )
    default_zero_weight_ok = abs(current_weight) <= 1e-12

    blockers: list[str] = []
    if not default_zero_weight_ok:
        blockers.append("latest_strategy_00632r_target_must_default_to_zero")
    if not hedge_gate_allows_open:
        blockers.append("dedicated_hedge_gates_do_not_allow_00632r_open")
    if dca_count and dca_count > 0:
        blockers.append("recent_trade_review_found_00632r_buy_or_dca_records")
    blockers.extend(
        [
            "00632r_dca_prohibited",
            "00632r_averaging_down_prohibited",
            "cash_floor_preferred_over_inverse_etf_for_default_defense",
        ]
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_00632r_discipline_guard",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": live.get("requested_as_of_date") or live.get("actual_data_date"),
        "status": "blocked_for_inverse_adds",
        "policy": "latest_strategy_00632r_zero_default_no_dca_no_averaging_down",
        "current_latest_strategy": {
            "strategy_id": live.get("strategy_id"),
            "actual_data_date": live.get("actual_data_date"),
            "target_weight_00632r": current_weight,
            "target_weight_cash": _float(weights.get("cash"), 0.0),
        },
        "rules": {
            "default_target_weight": 0.0,
            "dca_allowed": False,
            "averaging_down_allowed": False,
            "discretionary_buy_allowed": False,
            "prefer_cash_floor_for_default_defense": True,
            "manual_exception_max_weight": float(max_manual_weight),
            "manual_exception_requires_all_hedge_gates": True,
            "must_have_exit_rule_before_open": True,
        },
        "upstream": {
            "letf_allow_00632r_open": letf_decision.get("allow_00632r_open"),
            "tail_gate_allow_00632r_open": tail_decision.get("allow_00632r_open"),
            "tail_gate_manual_hedge_discussion_allowed": tail_decision.get("manual_hedge_discussion_allowed"),
            "trade_check_00632r_buy_count": dca_count,
        },
        "checks": {
            "latest_strategy_default_zero_weight_ok": default_zero_weight_ok,
            "dedicated_hedge_gates_allow_open": hedge_gate_allows_open,
            "recent_trade_review_has_00632r_buy_records": bool(dca_count and dca_count > 0),
        },
        "blocking_reasons": blockers,
        "decision": {
            "latest_strategy_rule_added": True,
            "target_weight_change_allowed": False,
            "latest_strategy_change_allowed": False,
            "allow_00632r_dca": False,
            "allow_00632r_averaging_down": False,
            "allow_00632r_discretionary_buy": False,
            "allow_00632r_open": False,
            "allow_00632r_increase": False,
            "manual_exception_max_weight": float(max_manual_weight),
            "default_defense_asset": "cash",
            "summary": (
                "Keep 00632R at zero by default in the latest strategy. Do not DCA, "
                "average down, or buy it discretionarily; use cash as the default "
                "defensive sleeve unless all dedicated hedge gates explicitly pass."
            ),
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "letf_readiness": str(letf_readiness_path),
            "tail_gate": str(tail_gate_path),
            "trade_check": None if trade_check_path is None else str(trade_check_path),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    decision = report["decision"]
    current = report["current_latest_strategy"]
    lines = [
        "# GroupA+ 00632R Discipline Guard",
        "",
        f"- status: {report['status']}",
        f"- as_of: {report.get('as_of')}",
        f"- policy: {report['policy']}",
        f"- strategy_id: {current.get('strategy_id')}",
        f"- target_weight_00632r: {current.get('target_weight_00632r')}",
        f"- target_weight_cash: {current.get('target_weight_cash')}",
        f"- allow_00632r_open: {decision['allow_00632r_open']}",
        f"- allow_00632r_dca: {decision['allow_00632r_dca']}",
        f"- default_defense_asset: {decision['default_defense_asset']}",
        "",
        "## Rules",
    ]
    for key, value in report["rules"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Blocking Reasons"])
    lines.extend(f"- {item}" for item in report["blocking_reasons"])
    lines.extend(["", "## Decision", decision["summary"], ""])
    return "\n".join(lines)


def _history_path(history_dir: Path, report: dict[str, Any]) -> Path:
    stamp = str(report.get("as_of") or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"00632r_discipline_guard_{stamp}.json"


def write_guard(report: dict[str, Any], *, output: Path, markdown: Path | None, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown is not None:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--letf-readiness", default=str(DEFAULT_LETF_READINESS))
    parser.add_argument("--tail-gate", default=str(DEFAULT_TAIL_GATE))
    parser.add_argument("--trade-check", default=str(DEFAULT_TRADE_CHECK))
    parser.add_argument("--max-manual-weight", type=float, default=0.05)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    trade_check = _resolve(args.trade_check) if args.trade_check else None
    report = build_guard(
        live_signal_path=_resolve(args.live_signal),
        letf_readiness_path=_resolve(args.letf_readiness),
        tail_gate_path=_resolve(args.tail_gate),
        trade_check_path=trade_check,
        max_manual_weight=float(args.max_manual_weight),
    )
    write_guard(
        report,
        output=_resolve(args.output),
        markdown=_resolve(args.markdown) if args.markdown else None,
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"00632R discipline guard: {_resolve(args.output)}")
    print(json.dumps({"status": report["status"], "blockers": report["blocking_reasons"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
