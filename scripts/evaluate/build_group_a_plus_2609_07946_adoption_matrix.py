#!/usr/bin/env python3
"""Build adoption matrix for 2609.07946 GroupA++ shadow candidates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LATEST = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_OUTPUT = LATEST / "2609_07946_adoption_matrix.json"
DEFAULT_MARKDOWN = LATEST / "2609_07946_adoption_matrix.md"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_optional(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _top_combo(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not report:
        return None
    rows = report.get("top_screened_combos")
    return rows[0] if isinstance(rows, list) and rows else None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    vol_monthly = _load_optional(_resolve(args.vol_monthly))
    vol_daily = _load_optional(_resolve(args.vol_daily))
    complementarity = _load_optional(_resolve(args.complementarity))
    markowitz = _load_optional(_resolve(args.markowitz))
    stock_bond_gold_forward = _load_optional(_resolve(args.stock_bond_gold_forward))
    bond_only_forward = _load_optional(_resolve(args.bond_only_forward))
    instrument_review = _load_optional(_resolve(args.instrument_review))
    promotion_gate = _load_optional(_resolve(args.promotion_gate))

    vol_monthly_top = _top_combo(vol_monthly)
    vol_daily_top = _top_combo(vol_daily)
    comp_top = _top_combo(complementarity)
    markowitz_top = _top_combo(markowitz)

    candidates = [
        {
            "candidate": "short_window_volatility_control_cash_scaler_monthly",
            "evidence": {
                "robust_combo_count": None if not vol_monthly else vol_monthly.get("robust_combo_count"),
                "top_combo": vol_monthly_top,
            },
            "verdict": "reject",
            "reason": "No robust pass; return drag is not compensated enough by drawdown improvement.",
            "latest_strategy_import": False,
        },
        {
            "candidate": "short_window_volatility_control_cash_scaler_daily",
            "evidence": {
                "robust_combo_count": None if not vol_daily else vol_daily.get("robust_combo_count"),
                "top_combo": vol_daily_top,
            },
            "verdict": "reject",
            "reason": "No robust pass; daily scaling increases operational churn without stable net benefit.",
            "latest_strategy_import": False,
        },
        {
            "candidate": "stock_bond_gold_complementarity_sleeve",
            "evidence": {
                "robust_combo_count": None if not complementarity else complementarity.get("robust_combo_count"),
                "top_combo": comp_top,
                "latest_forward_signal": None if not stock_bond_gold_forward else stock_bond_gold_forward.get("signal"),
                "instrument_review": None if not instrument_review else instrument_review.get("decision"),
                "promotion_gate": None if not promotion_gate else promotion_gate.get("stock_bond_gold_complementarity"),
            },
            "verdict": "forward_shadow_continue",
            "reason": "Backtest is robust, but 00635U is a futures ETF outside current watchlist/tradable core; latest 2026-09-10 signal is not triggered.",
            "latest_strategy_import": False,
        },
        {
            "candidate": "bond_only_complementarity_sleeve",
            "evidence": {
                "robust_combo_count": None if not complementarity else complementarity.get("robust_combo_count"),
                "bond_only_forward_signal": None if not bond_only_forward else bond_only_forward.get("signal"),
                "promotion_gate": None if not promotion_gate else promotion_gate.get("bond_only_complementarity"),
            },
            "verdict": "forward_shadow_continue",
            "reason": "Uses existing pipeline tickers and has robust historical evidence, but latest 2026-09-10 signal is not triggered and no forward live log exists yet.",
            "latest_strategy_import": False,
        },
        {
            "candidate": "monthly_constrained_markowitz",
            "evidence": {
                "robust_combo_count": None if not markowitz else markowitz.get("robust_combo_count"),
                "top_combo": markowitz_top,
            },
            "verdict": "reject",
            "reason": "Best screened combo only passes 3/5 windows; improvement is too small for optimizer complexity.",
            "latest_strategy_import": False,
        },
    ]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_07946_adoption_matrix",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_summary_no_orders_no_live_weight_change",
        "source_paper": "2609.07946",
        "candidates": candidates,
        "decision": {
            "adopt_into_latest_strategy_now": False,
            "promotion_gate_ready": None if not promotion_gate else promotion_gate.get("decision", {}).get("any_ready_for_live_review"),
            "continue_forward_shadow": ["stock_bond_gold_complementarity_sleeve", "bond_only_complementarity_sleeve"],
            "reject": [
                "short_window_volatility_control_cash_scaler_monthly",
                "short_window_volatility_control_cash_scaler_daily",
                "monthly_constrained_markowitz",
            ],
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "reason": "No 2609.07946 candidate clears live-promotion requirements today; best candidates remain forward shadow only.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.07946 Adoption Matrix",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- policy: `{report['policy']}`",
        f"- adopt_into_latest_strategy_now: `{report['decision']['adopt_into_latest_strategy_now']}`",
        f"- promotion_gate_ready: `{report['decision']['promotion_gate_ready']}`",
        "",
        "| candidate | verdict | import_now | reason |",
        "|---|---|---:|---|",
    ]
    for row in report["candidates"]:
        lines.append(f"| {row['candidate']} | {row['verdict']} | `{row['latest_strategy_import']}` | {row['reason']} |")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Do not change latest GroupA++ target weights, execution plans, or orders.",
            "- Continue forward shadow for complementarity sleeves.",
            "- `golden1_0531` and `golden2_0830` are lockdown comparators.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vol-monthly", default=str(LATEST / "2609_07946_vol_control_cash_scaler_shadow_monthly.json"))
    parser.add_argument("--vol-daily", default=str(LATEST / "2609_07946_vol_control_cash_scaler_shadow_daily.json"))
    parser.add_argument("--complementarity", default=str(LATEST / "2609_07946_stock_bond_gold_complementarity_shadow.json"))
    parser.add_argument("--markowitz", default=str(LATEST / "2609_07946_monthly_markowitz_shadow.json"))
    parser.add_argument("--stock-bond-gold-forward", default=str(LATEST / "2609_07946_stock_bond_gold_forward_shadow_latest.json"))
    parser.add_argument("--bond-only-forward", default=str(LATEST / "2609_07946_bond_only_forward_shadow_latest.json"))
    parser.add_argument("--instrument-review", default=str(LATEST / "00635u_instrument_review.json"))
    parser.add_argument("--promotion-gate", default=str(LATEST / "2609_07946_complementarity_promotion_gate.json"))
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
    print(f"Adoption matrix JSON: {output}")
    print(f"Adoption matrix Markdown: {markdown}")
    print("Decision:", json.dumps(report["decision"], ensure_ascii=False))


if __name__ == "__main__":
    main()
