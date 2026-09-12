#!/usr/bin/env python3
"""Build ramp path-dependence shadow report for GroupA+.

arXiv 2608.08405 separates capacity level experiments from path-dependence
questions. A ramp-up/ramp-down study needs its own path protocol and realized
deployment evidence. This report audits whether GroupA+ has those ingredients;
it cannot change live weights or scale capital.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INTERVENTION_HISTORY = PROJECT_ROOT / "report/group_a_plus/latest/intervention_history.json"
DEFAULT_ASSIGNED_REALIZED = (
    PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_assigned_realized_deployment_shadow.json"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_ramp_path_dependence_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2608_08405_ramp_path_dependence_shadow/history"


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


def _entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("entries")
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def _ticker_sequences(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in entries:
        ticker = item.get("ticker")
        if ticker:
            grouped[str(ticker)].append(item)

    out: dict[str, dict[str, Any]] = {}
    for ticker, rows in sorted(grouped.items()):
        deltas: list[float] = []
        filled = 0
        for row in rows:
            try:
                deltas.append(float(row.get("target_delta_shares") or 0.0))
            except (TypeError, ValueError):
                deltas.append(0.0)
            if row.get("filled_trade") is True:
                filled += 1
        positive = sum(1 for item in deltas if item > 0)
        negative = sum(1 for item in deltas if item < 0)
        out[ticker] = {
            "entry_count": len(rows),
            "positive_target_delta_count": positive,
            "negative_target_delta_count": negative,
            "filled_trade_count": filled,
            "has_two_sided_target_path": bool(positive and negative),
            "has_realized_two_sided_path": False,
        }
    return out


def build_report(
    *,
    intervention_history_path: Path,
    assigned_realized_path: Path,
    minimum_two_sided_tickers: int = 2,
) -> dict[str, Any]:
    intervention_history = _unwrap(_load(intervention_history_path))
    assigned_realized = _unwrap(_load(assigned_realized_path))
    entries = _entries(intervention_history)
    sequences = _ticker_sequences(entries)
    two_sided_target_count = sum(1 for item in sequences.values() if item["has_two_sided_target_path"])
    realized_two_sided_count = sum(1 for item in sequences.values() if item["has_realized_two_sided_path"])
    realized_ready = assigned_realized.get("status") == "ready_for_capacity_shadow_review"
    history_type = intervention_history.get("history_type")

    blockers: list[str] = []
    if not entries:
        blockers.append("intervention_history_missing")
    if two_sided_target_count < minimum_two_sided_tickers:
        blockers.append("two_sided_ramp_target_paths_insufficient")
    if history_type == "system_observed_daily_status_not_broker_fills":
        blockers.append("intervention_history_is_target_status_not_realized_fills")
    if not realized_ready:
        blockers.append("realized_deployment_series_missing")
    if realized_two_sided_count < minimum_two_sided_tickers:
        blockers.append("realized_two_sided_ramp_paths_missing")
    blockers.extend(
        [
            "ramp_up_down_protocol_not_pre_registered",
            "path_dependent_outcome_window_not_estimated",
            "capacity_level_grid_cannot_substitute_for_ramp_experiment",
        ]
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_08405_ramp_path_dependence_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": (intervention_history.get("coverage") or {}).get("last_check_date") or assigned_realized.get("as_of"),
        "status": "blocked_shadow_only",
        "policy": "ramp_path_dependence_shadow_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2608.08405_robustness_or_crowding_strategy_capacity.pdf",
            "concept": "path_dependence_requires_a_separate_ramp_experiment",
        },
        "coverage": {
            "history_type": history_type,
            "entry_count": len(entries),
            "ticker_count": len(sequences),
            "two_sided_target_path_ticker_count": two_sided_target_count,
            "realized_two_sided_path_ticker_count": realized_two_sided_count,
            "minimum_two_sided_tickers": int(minimum_two_sided_tickers),
        },
        "ticker_sequences": sequences,
        "checks": {
            "target_ramp_paths_observed": two_sided_target_count >= minimum_two_sided_tickers,
            "realized_ramp_paths_observed": realized_two_sided_count >= minimum_two_sided_tickers,
            "assigned_realized_ready": realized_ready,
            "pre_registered_ramp_protocol": False,
            "path_dependent_outcome_window_estimated": False,
            "can_be_combined_with_capacity_grid_as_same_estimand": False,
        },
        "blocking_reasons": blockers,
        "decision": {
            "ramp_path_dependence_claim_allowed": False,
            "capacity_claim_allowed": False,
            "capacity_scaling_allowed": False,
            "latest_strategy_change_allowed": False,
            "target_weight_change_allowed": False,
            "golden1_0531_change_allowed": False,
            "golden2_0830_change_allowed": False,
            "summary": (
                "GroupA+ has target-change history, but not a pre-registered realized "
                "ramp-up/ramp-down experiment. Path dependence remains a separate shadow "
                "question and cannot support capacity scaling or strategy changes."
            ),
        },
        "inputs": {
            "intervention_history": str(intervention_history_path),
            "assigned_realized": str(assigned_realized_path),
        },
    }


def _markdown(report: dict[str, Any]) -> str:
    decision = report["decision"]
    coverage = report["coverage"]
    lines = [
        "# 2608.08405 Ramp Path Dependence Shadow",
        "",
        f"- status: {report['status']}",
        f"- as_of: {report.get('as_of')}",
        f"- policy: {report['policy']}",
        f"- history_type: {coverage.get('history_type')}",
        f"- entry_count: {coverage['entry_count']}",
        f"- two_sided_target_path_ticker_count: {coverage['two_sided_target_path_ticker_count']}",
        f"- realized_two_sided_path_ticker_count: {coverage['realized_two_sided_path_ticker_count']}",
        f"- ramp_path_dependence_claim_allowed: {decision['ramp_path_dependence_claim_allowed']}",
        "",
        "## Blocking Reasons",
    ]
    lines.extend(f"- {item}" for item in report["blocking_reasons"])
    lines.extend(["", "## Ticker Sequences"])
    for ticker, item in report["ticker_sequences"].items():
        lines.append(
            "- {ticker}: entries={entries}, positive={positive}, negative={negative}, filled={filled}".format(
                ticker=ticker,
                entries=item["entry_count"],
                positive=item["positive_target_delta_count"],
                negative=item["negative_target_delta_count"],
                filled=item["filled_trade_count"],
            )
        )
    lines.extend(["", "## Decision", decision["summary"], ""])
    return "\n".join(lines)


def _history_path(history_dir: Path, report: dict[str, Any]) -> Path:
    date = str(report.get("as_of") or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2608_08405_ramp_path_dependence_shadow_{date}.json"


def write_report(report: dict[str, Any], *, output_path: Path, markdown_path: Path | None, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intervention-history", default=str(DEFAULT_INTERVENTION_HISTORY))
    parser.add_argument("--assigned-realized", default=str(DEFAULT_ASSIGNED_REALIZED))
    parser.add_argument("--minimum-two-sided-tickers", type=int, default=2)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report = build_report(
        intervention_history_path=_resolve(args.intervention_history),
        assigned_realized_path=_resolve(args.assigned_realized),
        minimum_two_sided_tickers=int(args.minimum_two_sided_tickers),
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown) if args.markdown else None
    history = None if args.no_history else _resolve(args.history_dir)
    write_report(report, output_path=output, markdown_path=markdown, history_dir=history)
    print(f"2608.08405 ramp path-dependence shadow: {output}")
    print(json.dumps({"status": report["status"], "blockers": report["blocking_reasons"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
