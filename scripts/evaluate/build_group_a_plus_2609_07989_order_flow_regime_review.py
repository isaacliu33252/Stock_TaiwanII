#!/usr/bin/env python3
"""Review arXiv 2609.07989 for GroupA++ adoption candidates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_07989_order_flow_regime_review.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_07989_order_flow_regime_review.md"


def build_report(pdf_path: Path) -> dict[str, Any]:
    candidates = [
        {
            "name": "duration_aware_intraday_order_flow_changepoint_shadow",
            "status": "conditional_shadow",
            "group_a_plusplus_mapping": (
                "Use a log-normal duration-aware BOCPD/BOSD filter on signed intraday volume for 0050, "
                "00631L, 00632R, 00713, 00679B, and 2330 when reliable trade-sign data exists."
            ),
            "expected_advantage": (
                "Could flag execution-time flow breaks earlier than daily OHLCV indicators, especially before "
                "adding leveraged 00631L exposure or resizing the 00713/cash sleeve."
            ),
            "live_change_allowed": False,
            "success_gate": (
                "Taiwan intraday signed-flow backtest must reduce after-cost slippage/drawdown versus the "
                "current execution guard across purged forward windows."
            ),
        },
        {
            "name": "lognormal_duration_prior_for_regime_monitors",
            "status": "recommended_research_only",
            "group_a_plusplus_mapping": (
                "When a future GroupA++ monitor models event durations online, compare constant-hazard BOCPD "
                "against a log-normal run-length hazard instead of assuming geometric regime lengths."
            ),
            "expected_advantage": (
                "The paper's strongest positive result is that order-flow regimes have no single characteristic "
                "timescale; a log-normal duration prior may reduce over-fragmentation of stable periods."
            ),
            "live_change_allowed": False,
            "success_gate": "Predeclared MSE/log-likelihood/false-alarm tests on local Taiwan data.",
        },
        {
            "name": "daily_ohlcv_proxy_order_flow_regime_gate",
            "status": "do_not_adopt",
            "group_a_plusplus_mapping": (
                "Do not replace signed trade flow with daily OHLCV or rough volume-return proxies for live "
                "allocation decisions."
            ),
            "expected_advantage": "None with current evidence; the paper's signal is defined on signed high-frequency transactions.",
            "live_change_allowed": False,
            "success_gate": "Requires direct trade-sign reconstruction or exchange-quality intraday order-flow data.",
        },
        {
            "name": "multivariate_bocpdms_bvar_live_gate",
            "status": "reject_for_now",
            "group_a_plusplus_mapping": (
                "Do not add a multivariate Bayesian VAR changepoint gate to latest strategy weights."
            ),
            "expected_advantage": (
                "Not supported by this paper: the bivariate BOCPDMS experiment underperformed two independent "
                "univariate filters, and pairwise DM tests did not establish superiority."
            ),
            "live_change_allowed": False,
            "success_gate": (
                "Only reconsider after a separate Taiwan intraday experiment with robust scaling, intercept models, "
                "and a populated model universe."
            ),
        },
    ]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_07989_order_flow_regime_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": {
            "path": str(pdf_path),
            "short_title": "Regimes in the Order Flow",
            "subtitle": "Duration-Aware and Multivariate Bayesian Online Changepoint Detection for High-Frequency Markets",
            "arxiv_id": "2609.07989",
        },
        "paper_claims_used": [
            "The tested data are signed high-frequency order-flow series for AAPL and MSFT from LOBSTER.",
            "The modeled quantity is aggregated signed volume in volume-clock or one-minute buckets, not daily returns.",
            "Duration-aware BOCPD/BOSD with a log-normal duration law outperformed constant-hazard BOCPD in the univariate order-flow tests.",
            "The log-normal duration law dominated the geometric and Pareto alternatives across assets, months, and calibration criteria.",
            "The multivariate BOCPDMS/BVAR extension was negative on the bivariate order-flow test, underperforming two independent univariate filters.",
            "Heavy-tailed innovations and short regimes made adaptive multivariate coefficients overreact to spikes.",
            "The paper reports no trading strategy, no transaction-cost-adjusted Sharpe, and no ETF allocation test.",
        ],
        "group_a_plusplus_context": {
            "active_strategy": "a2118_a2111_ncf_late_bull_deleverage",
            "current_target_assets": ["0050", "00631L", "00632R", "00679B", "00713", "cash"],
            "latest_strategy_time_scale": "daily allocation with execution/advisory shadows",
            "data_gap": (
                "The repository has daily OHLCV and some intraday bars, but this paper's core input is signed "
                "transaction/order-flow data. Without reliable trade signs, direct import would create a proxy risk."
            ),
            "important_mismatch": (
                "The paper studies high-frequency microstructure regime detection; GroupA++ latest strategy is a "
                "small ETF allocation system. The fit is strongest for execution-risk advisory, not for changing "
                "strategic target weights."
            ),
        },
        "adoption_candidates": candidates,
        "decision": {
            "can_import_to_group_a_plusplus": True,
            "import_mode": "execution_advisory_shadow_only",
            "advisory_import_allowed": True,
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_golden2_0830": False,
            "order_generation_allowed": False,
            "live_weight_change_allowed": False,
            "recommended_next_step": (
                "Do not change latest strategy weights. If reliable Taiwan signed intraday flow becomes available, "
                "build a duration-aware univariate order-flow changepoint shadow for execution timing only."
            ),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.07989 Order-Flow Regime Review",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- paper: `{report['paper']['short_title']}`",
        f"- subtitle: `{report['paper']['subtitle']}`",
        f"- pdf: `{report['paper']['path']}`",
        f"- decision: `{report['decision']['import_mode']}`",
        f"- changes_latest_strategy: `{report['decision']['changes_latest_strategy']}`",
        f"- changes_golden1_0531: `{report['decision']['changes_golden1_0531']}`",
        f"- changes_golden2_0830: `{report['decision']['changes_golden2_0830']}`",
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
            f"- Time scale: `{report['group_a_plusplus_context']['latest_strategy_time_scale']}`",
            f"- Data gap: {report['group_a_plusplus_context']['data_gap']}",
            f"- Mismatch: {report['group_a_plusplus_context']['important_mismatch']}",
            "",
            "## Adoption Candidates",
            "",
            "| candidate | status | live change | expected advantage |",
            "|---|---|---:|---|",
        ]
    )
    for item in report["adoption_candidates"]:
        lines.append(
            f"| `{item['name']}` | `{item['status']}` | `{item['live_change_allowed']}` | {item['expected_advantage']} |"
        )
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"- {report['decision']['recommended_next_step']}",
            "- Keep this paper out of live target-weight logic unless Taiwan signed-flow evidence passes a separate forward-validation gate.",
            "- Prefer the paper's positive univariate duration-aware result over its negative multivariate BOCPDMS result for any future shadow.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        default="/mnt/c/Users/isaac/Downloads/2609.07989_regimes_in_the_order_flow.pdf",
    )
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
