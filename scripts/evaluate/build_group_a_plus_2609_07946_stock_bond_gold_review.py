#!/usr/bin/env python3
"""Review arXiv 2609.07946 for GroupA++ adoption candidates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PDF = Path("/mnt/c/Users/isaac/Downloads/2609.07946_simple_dynamic_stock_bond_gold_portfolios.pdf")
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_stock_bond_gold_review.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_07946_stock_bond_gold_review.md"


def build_report(pdf_path: Path) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = [
        {
            "name": "short_window_volatility_control_cash_scaler",
            "status": "recommended_shadow",
            "paper_mapping": "Monthly volatility-controlled benchmark: scale a fixed stock/bond/gold mix toward cash when trailing volatility exceeds target.",
            "group_a_plusplus_mapping": (
                "Shadow a capped scaler on the active latest GroupA++ risky sleeve using 11-trading-day realized portfolio volatility. "
                "Only reduce risk into cash; never lever up and never rewrite Golden1/Golden2."
            ),
            "expected_advantage": "May reduce 00631L drawdown spikes while preserving the existing latest strategy's relative asset signal.",
            "main_risk": "GroupA++ already has defensive and execution guards; a second volatility scaler can double-count risk and suppress profitable rebounds.",
            "live_change_allowed": False,
            "success_gate": "Cost-aware multi-window backtest must improve max drawdown and Sharpe versus latest without increasing missed rebound loss or turnover beyond cap.",
        },
        {
            "name": "stock_bond_gold_complementarity_shadow",
            "status": "conditional_shadow",
            "paper_mapping": "50/30/20 stock/bond/gold mix improves drawdown and risk-adjusted performance versus stock/bond only in the paper's U.S. ETF setting.",
            "group_a_plusplus_mapping": (
                "Use 0050/00631L as stock-risk sleeve, 00679B/00751B as bond sleeve, and GC=F or a reviewed Taiwan gold ETF as gold proxy. "
                "For now GC=F is data-only because gold is not in the current tradable watchlist."
            ),
            "expected_advantage": "Adds a third defensive driver when stock/bond correlation is unfavorable; can complement the 2609.08106 bond-only sleeve.",
            "main_risk": "Gold proxy may not map cleanly to executable Taiwan ETF liquidity, tax, spread, and currency exposure.",
            "live_change_allowed": False,
            "success_gate": "A tradable gold instrument must pass liquidity/spread/data-quality review before any target-weight experiment can be considered.",
        },
        {
            "name": "monthly_constrained_markowitz_shadow",
            "status": "conditional_shadow",
            "paper_mapping": "Small convex Markowitz problem maximizes forecast next-month return net of trading cost subject to long-only, cash, volatility, and L1 trust-region constraints.",
            "group_a_plusplus_mapping": (
                "Run a monthly shadow allocator over 0050/00631L/00679B/00751B/00713/cash plus optional gold proxy. "
                "Constrain output near latest strategy weights and cap changes from 00631L to avoid replacing the active policy."
            ),
            "expected_advantage": "Gives a transparent optimizer for risk-budget and cash-sleeve sizing, using cost-aware objective instead of ad hoc thresholds.",
            "main_risk": "Return forecasts are fragile; paper uses U.S. SPY/AGG/GLD 2006-2026 and monthly cadence, not Taiwan leveraged ETF dynamics.",
            "live_change_allowed": False,
            "success_gate": "Purged walk-forward Taiwan ETF validation must beat latest, Golden1 lockdown comparator, and Golden2 lockdown comparator after costs.",
        },
        {
            "name": "direct_live_replacement",
            "status": "do_not_adopt",
            "paper_mapping": "Paper portfolio is an independent U.S. stock/bond/gold strategy.",
            "group_a_plusplus_mapping": "Do not replace latest GroupA++ or lockdown Golden1/Golden2 with the paper's 50/30/20 or Markowitz weights.",
            "expected_advantage": "None without Taiwan-specific evidence and executable gold sleeve.",
            "main_risk": "Would violate lockdown/governance and create asset-universe mismatch.",
            "live_change_allowed": False,
            "success_gate": "Not eligible for direct promotion.",
        },
    ]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_07946_stock_bond_gold_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": {
            "path": str(pdf_path),
            "short_title": "Simple Dynamic Stock/Bond/Gold Portfolios",
            "arxiv_id": "2609.07946",
            "date": "2026-09-09",
        },
        "paper_claims_used": [
            "The paper studies long-only portfolios of SPY, AGG, GLD, and cash with monthly rebalancing and public data.",
            "Volatility control scales fixed portfolios toward cash when estimated risk exceeds a target; it does not lever up in calm regimes.",
            "The reported volatility estimate is an 11-trading-day trailing realized volatility annualized by sqrt(252).",
            "The 50/30/20 volatility-controlled portfolio reports return 7.8%, volatility 7.3%, Sharpe 0.82, max drawdown 15.9%, turnover 79.0%.",
            "The Markowitz portfolio reports return 11.6%, volatility 9.0%, Sharpe 1.08, max drawdown 18.1%, turnover 284.4%.",
            "The fixed 60/40 benchmark reports Sharpe 0.56 and max drawdown 33.7%.",
            "The paper includes trading costs and shows rankings persist at 10 and 20 basis point cost assumptions.",
            "The authors caution via robustness/statistical sections that Sharpe advantages have uncertainty and require careful validation.",
        ],
        "group_a_plusplus_context": {
            "active_strategy": "a2118_a2111_ncf_late_bull_deleverage",
            "tradable_core": ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO", "00713.TW", "cash"],
            "bond_candidates": ["00679B.TWO", "00751B.TWO"],
            "gold_status": "not_in_current_tradable_watchlist",
            "gold_data_proxy_available": "GC=F in external_market_ohlcv",
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "important_mismatch": (
                "The paper is monthly, U.S.-ETF, unlevered, and includes GLD. GroupA++ is Taiwan ETF based and uses 00631L leverage, "
                "so only shadow translation is justified."
            ),
        },
        "adoption_candidates": candidates,
        "decision": {
            "can_import_to_group_a_plusplus": True,
            "import_mode": "shadow_only",
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_golden2_0830": False,
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "order_generation_allowed": False,
            "recommended_next_step": (
                "Backtest the short_window_volatility_control_cash_scaler against latest GroupA++ first; "
                "evaluate gold only as a data proxy until a tradable Taiwan gold instrument passes review."
            ),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.07946 Stock/Bond/Gold Review",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- paper: `{report['paper']['short_title']}`",
        f"- pdf: `{report['paper']['path']}`",
        f"- decision: `{report['decision']['import_mode']}`",
        f"- changes_latest_strategy: `{report['decision']['changes_latest_strategy']}`",
        f"- golden1_0531_lockdown: `{report['decision']['golden1_0531_lockdown']}`",
        f"- golden2_0830_lockdown: `{report['decision']['golden2_0830_lockdown']}`",
        "",
        "## Paper Takeaways",
        "",
    ]
    for claim in report["paper_claims_used"]:
        lines.append(f"- {claim}")
    lines.extend(
        [
            "",
            "## GroupA++ Fit",
            "",
            f"- Active strategy: `{report['group_a_plusplus_context']['active_strategy']}`",
            f"- Tradable core: `{report['group_a_plusplus_context']['tradable_core']}`",
            f"- Bond candidates: `{report['group_a_plusplus_context']['bond_candidates']}`",
            f"- Gold status: `{report['group_a_plusplus_context']['gold_status']}`; proxy: `{report['group_a_plusplus_context']['gold_data_proxy_available']}`",
            f"- Mismatch: {report['group_a_plusplus_context']['important_mismatch']}",
            "",
            "## Adoption Candidates",
            "",
            "| candidate | status | live change | expected advantage | main risk |",
            "|---|---|---:|---|---|",
        ]
    )
    for item in report["adoption_candidates"]:
        lines.append(
            f"| `{item['name']}` | `{item['status']}` | `{item['live_change_allowed']}` | {item['expected_advantage']} | {item['main_risk']} |"
        )
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"- {report['decision']['recommended_next_step']}",
            "- Do not modify or overwrite lockdown `golden1_0531` / `golden2_0830`.",
            "- Do not promote to live until Taiwan-specific, cost-aware, multi-window validation passes.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(Path(args.pdf))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"Review JSON: {output}")
    print(f"Review Markdown: {markdown}")


if __name__ == "__main__":
    main()
