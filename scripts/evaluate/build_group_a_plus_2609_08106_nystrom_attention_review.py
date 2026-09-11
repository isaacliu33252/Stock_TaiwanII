#!/usr/bin/env python3
"""Review arXiv 2609.08106 for GroupA++ adoption candidates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_nystrom_attention_review.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2609_08106_nystrom_attention_review.md"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def build_report(pdf_path: Path) -> dict[str, Any]:
    candidates = [
        {
            "name": "cross_asset_low_rank_attention_shadow",
            "status": "recommended_shadow",
            "group_a_plusplus_mapping": (
                "Build an offline panel over the current watchlist plus liquid Taiwan ETF/large-cap candidates; "
                "compare per-asset temporal baseline vs dynamic low-rank cross-asset attention."
            ),
            "expected_advantage": (
                "Tests whether GroupA++ can extract complementarity among 0050/00631L/00632R/00679B/00713/2330 "
                "without hand-coded correlation masks."
            ),
            "live_change_allowed": False,
            "success_gate": "Purged walk-forward IC/RankIC and realized portfolio utility must beat current latest baseline across multiple seeds after costs.",
        },
        {
            "name": "nystrom_attention_scaling_path",
            "status": "conditional_shadow",
            "group_a_plusplus_mapping": (
                "If the candidate universe expands above roughly 300 names, evaluate Nyström m=32 attention as a "
                "drop-in approximation for full cross-sectional attention."
            ),
            "expected_advantage": "Lower memory and inference cost for broad-universe shadow research.",
            "live_change_allowed": False,
            "success_gate": "Equivalent or better RankIC within a predeclared TOST margin; no worse turnover/cost profile.",
        },
        {
            "name": "anti_correlation_complementarity_feature",
            "status": "recommended_shadow",
            "group_a_plusplus_mapping": (
                "Add daily complementarity diagnostics: low attention/proxy weight to highly co-moving assets, "
                "higher proxy weight to assets with diversifying return paths."
            ),
            "expected_advantage": "May improve 00631L deleverage and 00713/cash sleeve decisions by avoiding redundant risk exposure.",
            "live_change_allowed": False,
            "success_gate": "Forward shadow must reduce drawdown or improve H5/H20 utility without suppressing profitable risk-on windows.",
        },
        {
            "name": "avoid_graph_or_topk_sparse_masks",
            "status": "do_not_adopt",
            "group_a_plusplus_mapping": "Do not add hard industry/correlation graph masks or top-K sparse attention to the live strategy.",
            "expected_advantage": "None for current evidence; the paper finds sparse/graph alternatives degrade performance.",
            "live_change_allowed": False,
            "success_gate": "Requires new Taiwan-specific contrary evidence before reconsideration.",
        },
    ]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_08106_nystrom_attention_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": {
            "path": str(pdf_path),
            "short_title": "Nyström Attention Matches Full Attention for Cross-Sectional Stock Prediction",
            "arxiv_id": "2609.08106",
        },
        "paper_claims_used": [
            "Inter-stock attention contributes the largest ablation value in MASTER-style cross-sectional stock prediction.",
            "Attention is near-uniform but its small deviation from uniformity carries cross-sectional discrimination.",
            "The deviation matrix is low-rank; top modes capture most energy.",
            "Nyström attention with m=32 matches full attention at N=300 and N=800 in the reported tests.",
            "Sparse/top-K/graph-masked alternatives degrade performance.",
            "At N≈3500, cross-stock modules did not significantly beat a per-stock LSTM baseline.",
            "Reported economic Sharpe results are frictionless and exclude transaction costs.",
        ],
        "group_a_plusplus_context": {
            "active_strategy": "a2118_a2111_ncf_late_bull_deleverage",
            "current_watchlist_size": 6,
            "current_target_assets": ["0050", "00631L", "00632R", "00679B", "cash"],
            "important_mismatch": (
                "GroupA++ currently trades a small ETF sleeve; the paper's strongest efficiency benefit appears at "
                "large cross-sections, so live adoption is not justified from this paper alone."
            ),
        },
        "adoption_candidates": candidates,
        "decision": {
            "can_import_to_group_a_plusplus": True,
            "import_mode": "shadow_only",
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_golden2_0830": False,
            "order_generation_allowed": False,
            "recommended_next_step": "Build cross_asset_low_rank_attention_shadow with Taiwan PIT data and cost-aware forward validation.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 2609.08106 Nyström Attention Review",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- paper: `{report['paper']['short_title']}`",
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
            f"- Current watchlist size: `{report['group_a_plusplus_context']['current_watchlist_size']}`",
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
            "- Do not promote into latest strategy until Taiwan-specific purged walk-forward, multi-seed, cost-aware evidence passes.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        default="/mnt/c/Users/isaac/Downloads/2609.08106_nystrom_attention_cross_sectional_stock_prediction.pdf",
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
