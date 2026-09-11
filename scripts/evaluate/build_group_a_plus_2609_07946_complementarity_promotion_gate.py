#!/usr/bin/env python3
"""Promotion gate for 2609.07946 complementarity forward shadows.

The gate is intentionally conservative. It can only report readiness; it never
changes live target weights, watchlists, execution plans, or orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LATEST = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_OUTPUT = LATEST / "2609_07946_complementarity_promotion_gate.json"
DEFAULT_MARKDOWN = LATEST / "2609_07946_complementarity_promotion_gate.md"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _summarize_log(path: Path, min_observations: int, min_triggers: int) -> dict[str, Any]:
    rows = _read_jsonl(path)
    trigger_rows = [row for row in rows if row.get("signal", {}).get("triggered")]
    realized_rows = [
        row
        for row in trigger_rows
        if row.get("realized_next_day", {}).get("available")
        and row.get("realized_next_day", {}).get("net_delta_return") is not None
    ]
    positive_realized = [
        row for row in realized_rows if float(row.get("realized_next_day", {}).get("net_delta_return") or 0.0) > 0.0
    ]
    net_values = [float(row["realized_next_day"]["net_delta_return"]) for row in realized_rows]
    return {
        "path": str(path),
        "observation_count": len(rows),
        "trigger_count": len(trigger_rows),
        "realized_trigger_count": len(realized_rows),
        "positive_realized_trigger_count": len(positive_realized),
        "avg_realized_net_delta_return": None if not net_values else sum(net_values) / len(net_values),
        "latest_signal_date": None if not rows else rows[-1].get("signal_date"),
        "latest_triggered": None if not rows else rows[-1].get("signal", {}).get("triggered"),
        "passes_observation_count": len(rows) >= min_observations,
        "passes_trigger_count": len(trigger_rows) >= min_triggers,
        "passes_realized_positive": bool(realized_rows and len(positive_realized) == len(realized_rows)),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    stock_bond_gold = _summarize_log(_resolve(args.stock_bond_gold_log), args.min_observations, args.min_triggers)
    bond_only = _summarize_log(_resolve(args.bond_only_log), args.min_observations, args.min_triggers)
    instrument_review = json.loads(_resolve(args.instrument_review).read_text(encoding="utf-8")) if _resolve(args.instrument_review).exists() else {}
    instrument_live_ready = bool(instrument_review.get("decision", {}).get("instrument_ready_for_live_core"))
    stock_bond_gold_ready = bool(
        stock_bond_gold["passes_observation_count"]
        and stock_bond_gold["passes_trigger_count"]
        and stock_bond_gold["passes_realized_positive"]
        and instrument_live_ready
    )
    bond_only_ready = bool(
        bond_only["passes_observation_count"] and bond_only["passes_trigger_count"] and bond_only["passes_realized_positive"]
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_07946_complementarity_promotion_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "promotion_governance_only_no_orders_no_live_weight_change",
        "source_paper": "2609.07946",
        "thresholds": {
            "min_observations": args.min_observations,
            "min_triggers": args.min_triggers,
            "require_all_realized_triggers_positive": True,
            "stock_bond_gold_requires_00635u_live_instrument_ready": True,
        },
        "stock_bond_gold_complementarity": stock_bond_gold,
        "bond_only_complementarity": bond_only,
        "instrument_live_ready": instrument_live_ready,
        "decision": {
            "stock_bond_gold_ready_for_live_review": stock_bond_gold_ready,
            "bond_only_ready_for_live_review": bond_only_ready,
            "any_ready_for_live_review": bool(stock_bond_gold_ready or bond_only_ready),
            "allow_target_weight_change": False,
            "allow_order_generation": False,
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "reason": "Forward-shadow evidence is insufficient for live review until observation, trigger, realized-performance, and instrument-readiness gates pass.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.07946 Complementarity Promotion Gate",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- policy: `{report['policy']}`",
        f"- any_ready_for_live_review: `{report['decision']['any_ready_for_live_review']}`",
        f"- min_observations: `{report['thresholds']['min_observations']}`",
        f"- min_triggers: `{report['thresholds']['min_triggers']}`",
        "",
        "| variant | observations | triggers | realized_triggers | avg_net_delta | ready_for_live_review |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    rows = [
        ("stock_bond_gold", report["stock_bond_gold_complementarity"], report["decision"]["stock_bond_gold_ready_for_live_review"]),
        ("bond_only", report["bond_only_complementarity"], report["decision"]["bond_only_ready_for_live_review"]),
    ]
    for name, row, ready in rows:
        avg = row["avg_realized_net_delta_return"]
        lines.append(
            f"| {name} | {row['observation_count']} | {row['trigger_count']} | {row['realized_trigger_count']} | "
            f"{'' if avg is None else f'{avg:.4%}'} | `{ready}` |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Do not change latest GroupA++ target weights, execution plans, or orders.",
            "- Continue forward shadow until the gate has enough realized observations.",
            "- `golden1_0531` and `golden2_0830` are lockdown comparators.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-bond-gold-log", default=str(PROJECT_ROOT / "results/2609_07946_stock_bond_gold_forward_shadow_log.jsonl"))
    parser.add_argument("--bond-only-log", default=str(PROJECT_ROOT / "results/2609_07946_bond_only_forward_shadow_log.jsonl"))
    parser.add_argument("--instrument-review", default=str(LATEST / "00635u_instrument_review.json"))
    parser.add_argument("--min-observations", type=int, default=20)
    parser.add_argument("--min-triggers", type=int, default=3)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()
    report = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"Promotion gate JSON: {output}")
    print(f"Promotion gate Markdown: {markdown}")
    print("Decision:", json.dumps(report["decision"], ensure_ascii=False))


if __name__ == "__main__":
    main()
