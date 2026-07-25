#!/usr/bin/env python3
"""Build normalized GroupA+ intervention history from managed daily status files.

This is a system-observed intervention history: suggested target changes,
blocked guard trades, and guarded leverage/hedge events. It is not broker
execution history and must not be treated as proof of filled trades.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DAILY_DIR = PROJECT_ROOT / "report/group_a_plus/daily/json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/intervention_history.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/intervention_history/history"
DEFAULT_PROFILE = "a2118_a2111_ncf_late_bull_deleverage"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _int_or_none(value: Any) -> int | None:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _is_leverage(ticker: str) -> bool:
    return ticker == "00631L.TW"


def _is_hedge(ticker: str) -> bool:
    return ticker == "00632R.TW"


def _entry_from_blocked_trade(
    *,
    payload: dict[str, Any],
    source_path: Path,
    guard: dict[str, Any],
    trade: dict[str, Any],
) -> dict[str, Any]:
    ticker = str(trade.get("ticker") or guard.get("ticker") or "")
    current = _int_or_none(trade.get("current_shares"))
    requested = _int_or_none(trade.get("requested_target_shares"))
    guarded = _int_or_none(trade.get("guarded_target_shares"))
    blocked_delta = _int_or_none(trade.get("blocked_delta_shares"))
    if blocked_delta is None and current is not None and requested is not None:
        blocked_delta = requested - current
    side = str(trade.get("side") or ("buy" if (blocked_delta or 0) > 0 else "sell"))
    action = "blocked_add" if side == "buy" else "blocked_reduce"
    return {
        "check_date": payload.get("check_date"),
        "actual_data_date": (payload.get("signal") or {}).get("actual_data_date"),
        "generated_at": payload.get("generated_at"),
        "source_path": str(source_path),
        "source": "daily_status_pre_trade_guard",
        "guard_name": guard.get("name"),
        "guard_status": guard.get("status"),
        "policy": guard.get("policy"),
        "ticker": ticker,
        "action": action,
        "side": side,
        "current_shares": current,
        "requested_target_shares": requested,
        "guarded_target_shares": guarded,
        "blocked_delta_shares": blocked_delta,
        "reason": trade.get("reason") or guard.get("reason"),
        "is_leverage_intervention": _is_leverage(ticker),
        "is_hedge_intervention": _is_hedge(ticker),
        "filled_trade": False,
    }


def _blocked_trade_entries(payload: dict[str, Any], source_path: Path) -> list[dict[str, Any]]:
    group = payload.get("group_a_plus") or {}
    guards = group.get("pre_trade_guards")
    if not isinstance(guards, list):
        guard = group.get("pre_trade_guard") or {}
        guards = [guard] if guard else []
    entries: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for guard in guards:
        if not isinstance(guard, dict):
            continue
        blocked = guard.get("blocked_trades") or []
        if not isinstance(blocked, list):
            continue
        for trade in blocked:
            if not isinstance(trade, dict):
                continue
            entry = _entry_from_blocked_trade(payload=payload, source_path=source_path, guard=guard, trade=trade)
            key = (
                entry["check_date"],
                entry["ticker"],
                entry["guard_name"],
                entry["side"],
                entry["blocked_delta_shares"],
            )
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
    return entries


def _target_change_entries(payloads: list[tuple[Path, dict[str, Any]]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    previous: dict[str, int] = {}
    for path, payload in payloads:
        group = payload.get("group_a_plus") or {}
        current_targets = {
            str(ticker): int(shares)
            for ticker, shares in (group.get("target_shares") or {}).items()
            if _int_or_none(shares) is not None
        }
        if not previous:
            previous = current_targets
            continue
        for ticker, target in sorted(current_targets.items()):
            prior = previous.get(ticker)
            if prior is None or prior == target:
                continue
            delta = target - prior
            entries.append(
                {
                    "check_date": payload.get("check_date"),
                    "actual_data_date": (payload.get("signal") or {}).get("actual_data_date"),
                    "generated_at": payload.get("generated_at"),
                    "source_path": str(path),
                    "source": "daily_status_target_shares_delta",
                    "guard_name": None,
                    "guard_status": None,
                    "policy": "observed_target_share_change_no_fill_assumption",
                    "ticker": ticker,
                    "action": "target_add" if delta > 0 else "target_reduce",
                    "side": "buy" if delta > 0 else "sell",
                    "current_shares": prior,
                    "requested_target_shares": target,
                    "guarded_target_shares": None,
                    "blocked_delta_shares": None,
                    "target_delta_shares": delta,
                    "reason": "daily_status_target_shares_changed",
                    "is_leverage_intervention": _is_leverage(ticker),
                    "is_hedge_intervention": _is_hedge(ticker),
                    "filled_trade": False,
                }
            )
        previous = current_targets
    return entries


def build_history(*, daily_dir: Path, profile: str = DEFAULT_PROFILE) -> dict[str, Any]:
    paths = sorted(daily_dir.glob(f"daily_status_{profile}_*.json"))
    payloads: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        payload = _load(path)
        if payload.get("profile") != profile:
            continue
        payloads.append((path, payload))

    entries: list[dict[str, Any]] = []
    for path, payload in payloads:
        entries.extend(_blocked_trade_entries(payload, path))
    entries.extend(_target_change_entries(payloads))
    entries.sort(key=lambda item: (str(item.get("check_date") or ""), str(item.get("generated_at") or ""), str(item.get("ticker") or "")))

    unique_dates = sorted({str(item.get("check_date")) for item in entries if item.get("check_date")})
    blocked_entries = [item for item in entries if str(item.get("action", "")).startswith("blocked_")]
    leverage_entries = [item for item in entries if item.get("is_leverage_intervention")]
    hedge_entries = [item for item in entries if item.get("is_hedge_intervention")]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_intervention_history",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile": profile,
        "status": "available" if entries else "empty",
        "history_type": "system_observed_daily_status_not_broker_fills",
        "coverage": {
            "source_file_count": len(payloads),
            "entry_count": len(entries),
            "blocked_entry_count": len(blocked_entries),
            "leverage_intervention_count": len(leverage_entries),
            "hedge_intervention_count": len(hedge_entries),
            "first_check_date": unique_dates[0] if unique_dates else None,
            "last_check_date": unique_dates[-1] if unique_dates else None,
        },
        "entries": entries,
        "inputs": {"daily_status_dir": str(daily_dir)},
        "limitations": [
            "not_broker_fill_history",
            "daily_status_files_can_include_multiple_intraday_rebuilds",
            "blocked_guard_entries_are_policy_interventions_not_executions",
        ],
    }


def _history_path(history_dir: Path, history: dict[str, Any]) -> Path:
    last = (history.get("coverage") or {}).get("last_check_date") or datetime.now().strftime("%Y%m%d")
    return history_dir / f"{str(last).replace('-', '')}.json"


def write_history(history: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, history).write_text(
            json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-dir", default=str(DEFAULT_DAILY_DIR))
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    history = build_history(daily_dir=_resolve(args.daily_dir), profile=args.profile)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    output = _resolve(args.output)
    write_history(history, output, history_dir)
    print(f"Intervention history: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, history)}")
    print(json.dumps({"status": history["status"], **history["coverage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
