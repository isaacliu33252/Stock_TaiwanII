#!/usr/bin/env python3
"""Build adoption matrix for 2609.08106 GroupA++ candidates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LATEST = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_OUTPUT = LATEST / "2609_08106_adoption_matrix.json"
DEFAULT_MARKDOWN = LATEST / "2609_08106_adoption_matrix.md"
DEFAULT_LATEST_TARGET_REPLAY = LATEST / "2609_08106_latest_target_weight_replay.json"
DEFAULT_LATEST_TARGET_PARAM_SWEEP = LATEST / "2609_08106_latest_target_weight_replay_param_sweep.json"
DEFAULT_MIN_FORWARD_SAMPLES = 20
DEFAULT_MIN_TRIGGERED_FORWARD_SAMPLES = 5


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_optional(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _latest_trigger(forward: dict[str, Any] | None) -> bool | None:
    if not forward:
        return None
    signal = forward.get("signal")
    if not isinstance(signal, dict):
        return None
    return bool(signal.get("triggered"))


def _forward_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    triggered = [row for row in rows if row.get("signal", {}).get("triggered") is True]
    realized = [
        row
        for row in rows
        if row.get("realized_next_day", {}).get("available") is True
        and row.get("realized_next_day", {}).get("net_delta_return") is not None
    ]
    positive_realized = [
        row
        for row in realized
        if float(row.get("realized_next_day", {}).get("net_delta_return") or 0.0) > 0.0
    ]
    return {
        "sample_count": len(rows),
        "triggered_count": len(triggered),
        "realized_count": len(realized),
        "positive_realized_count": len(positive_realized),
        "latest_signal_date": None if not rows else rows[-1].get("signal_date"),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    review = _load_optional(_resolve(args.review))
    readiness = _load_optional(_resolve(args.readiness))
    robustness = _load_optional(_resolve(args.robustness))
    forward = _load_optional(_resolve(args.forward))
    latest_target_replay = _load_optional(_resolve(args.latest_target_replay))
    latest_target_param_sweep = _load_optional(_resolve(args.latest_target_param_sweep))
    latest_strategy = _load_optional(_resolve(args.latest_strategy))
    forward_rows = _load_jsonl(_resolve(args.forward_log))
    forward_stats = _forward_stats(forward_rows)

    readiness_decision = readiness.get("decision", {}) if readiness else {}
    robustness_decision = robustness.get("decision", {}) if robustness else {}
    review_decision = review.get("decision", {}) if review else {}
    active_strategy = (latest_strategy or {}).get("active_strategy", {})

    readiness_passed = bool(readiness and readiness_decision.get("promotion_ready") is False and not readiness.get("blockers"))
    robust_combo_count = int(robustness.get("robust_combo_count") or 0) if robustness else 0
    has_forward_evidence = (
        forward_stats["sample_count"] >= args.min_forward_samples
        and forward_stats["triggered_count"] >= args.min_triggered_forward_samples
        and forward_stats["realized_count"] >= args.min_triggered_forward_samples
    )
    latest_triggered = _latest_trigger(forward)
    latest_target_replay_decision = (
        latest_target_replay.get("decision") if isinstance((latest_target_replay or {}).get("decision"), dict) else {}
    )
    latest_target_replay_delta = (
        latest_target_replay.get("delta_sleeve_minus_baseline")
        if isinstance((latest_target_replay or {}).get("delta_sleeve_minus_baseline"), dict)
        else {}
    )
    latest_target_replay_event_count = (
        None if not latest_target_replay else latest_target_replay.get("event_count")
    )
    latest_target_param_sweep_summary = (
        latest_target_param_sweep.get("summary")
        if isinstance((latest_target_param_sweep or {}).get("summary"), dict)
        else {}
    )
    latest_target_replay_reason = (
        "Historical mom5-gated tests, latest-target replay, and parameter sweep are encouraging, but live forward evidence is still insufficient."
        if (latest_target_replay_event_count or 0) > 0
        and (latest_target_replay_delta.get("total_return") or 0.0) > 0.0
        and (latest_target_replay_delta.get("sharpe_ratio") or 0.0) > 0.0
        and (latest_target_param_sweep_summary.get("positive_core_metric_rate") or 0.0) >= 0.5
        else "Historical mom5-gated tests are encouraging, but latest-target replay has no current positive sleeve evidence and live forward evidence is still insufficient."
    )

    candidates = [
        {
            "candidate": "nystrom_attention_replacement",
            "verdict": "broad_universe_research_only",
            "advisory_import_allowed": False,
            "live_weight_change_allowed": False,
            "evidence": {
                "review_decision": review_decision,
                "active_strategy_id": active_strategy.get("id"),
                "watchlist_size": None if not review else review.get("group_a_plus_fit", {}).get("current_watchlist_size"),
            },
            "reason": "Current GroupA++ is a small ETF sleeve; Nystrom's practical edge is scaling large cross-sections, not improving a 6-asset live allocation directly.",
        },
        {
            "candidate": "graph_or_topk_sparse_masks",
            "verdict": "reject",
            "advisory_import_allowed": False,
            "live_weight_change_allowed": False,
            "evidence": {
                "paper_takeaway": "Sparse, top-K, and graph-masked attention variants degraded performance in the paper review.",
            },
            "reason": "The paper's useful cross-sectional signal is near-global and low-rank; hard sparsification is the wrong import path.",
        },
        {
            "candidate": "cross_asset_complementarity_score",
            "verdict": "advisory_ready",
            "advisory_import_allowed": True,
            "live_weight_change_allowed": False,
            "evidence": {
                "readiness_passed_without_blockers": readiness_passed,
                "robust_combo_count": robust_combo_count,
                "latest_triggered": latest_triggered,
                "forward_stats": forward_stats,
            },
            "reason": "The anti-correlation/complementarity insight fits the current 0050/00631L/bond sleeve as a daily diagnostic without mutating target weights.",
        },
        {
            "candidate": "mom5_gated_bond_sleeve",
            "verdict": "continue_forward_shadow",
            "advisory_import_allowed": True,
            "live_weight_change_allowed": False,
            "evidence": {
                "readiness_decision": readiness_decision,
                "robustness_decision": robustness_decision,
                "latest_target_weight_replay": {
                    "event_count": latest_target_replay_event_count,
                    "days_with_00631l_weight": None
                    if not latest_target_replay
                    else latest_target_replay.get("coverage", {}).get("days_with_00631l_weight"),
                    "delta_total_return": latest_target_replay_delta.get("total_return"),
                    "delta_sharpe": latest_target_replay_delta.get("sharpe_ratio"),
                    "blockers": latest_target_replay_decision.get("blockers", []),
                },
                "latest_target_weight_param_sweep": {
                    "grid_count": latest_target_param_sweep_summary.get("grid_count"),
                    "positive_core_metric_count": latest_target_param_sweep_summary.get("positive_core_metric_count"),
                    "positive_core_metric_rate": latest_target_param_sweep_summary.get("positive_core_metric_rate"),
                    "best_by_delta_sharpe": latest_target_param_sweep_summary.get("best_by_delta_sharpe"),
                },
                "latest_triggered": latest_triggered,
                "forward_stats": forward_stats,
                "forward_gate_satisfied": has_forward_evidence,
            },
            "reason": latest_target_replay_reason,
        },
    ]

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2609_08106_adoption_matrix",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_summary_no_orders_no_live_weight_change",
        "source_paper": "2609.08106",
        "latest_strategy_context": {
            "strategy_id": active_strategy.get("id"),
            "status": active_strategy.get("status"),
            "runner": active_strategy.get("runner"),
        },
        "forward_evidence_gate": {
            "min_forward_samples": int(args.min_forward_samples),
            "min_triggered_forward_samples": int(args.min_triggered_forward_samples),
            "passed": has_forward_evidence,
            **forward_stats,
        },
        "candidates": candidates,
        "decision": {
            "adopt_into_latest_strategy_now": False,
            "advisory_import_allowed": True,
            "live_weight_change_allowed": False,
            "continue_forward_shadow": True,
            "attach_to_daily_pipeline": True,
            "golden1_0531_lockdown": True,
            "golden2_0830_lockdown": True,
            "reason": "2609.08106 has a useful complementarity diagnostic for GroupA++, but current forward evidence is too thin for live target-weight changes.",
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    gate = report["forward_evidence_gate"]
    lines = [
        "# 2609.08106 Adoption Matrix",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- policy: `{report['policy']}`",
        f"- latest_strategy: `{report['latest_strategy_context']['strategy_id']}`",
        f"- adopt_into_latest_strategy_now: `{report['decision']['adopt_into_latest_strategy_now']}`",
        f"- advisory_import_allowed: `{report['decision']['advisory_import_allowed']}`",
        f"- live_weight_change_allowed: `{report['decision']['live_weight_change_allowed']}`",
        f"- forward_gate_passed: `{gate['passed']}`",
        f"- forward_samples: `{gate['sample_count']}`",
        f"- triggered_forward_samples: `{gate['triggered_count']}`",
        f"- realized_forward_samples: `{gate['realized_count']}`",
        "",
        "| candidate | verdict | advisory | live weights | reason |",
        "|---|---|---:|---:|---|",
    ]
    for row in report["candidates"]:
        lines.append(
            "| {candidate} | {verdict} | `{advisory}` | `{live}` | {reason} |".format(
                candidate=row["candidate"],
                verdict=row["verdict"],
                advisory=row["advisory_import_allowed"],
                live=row["live_weight_change_allowed"],
                reason=row["reason"],
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Import the complementarity score into advisory/reporting only.",
            "- Continue daily forward shadow logging with realized after-cost attribution.",
            "- Do not change latest GroupA++ target weights, execution plans, or orders.",
            "- Do not import graph masks, top-K masks, or a Nystrom replacement into the current small live sleeve.",
            "- `golden1_0531` and `golden2_0830` are lockdown comparators.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", default=str(LATEST / "2609_08106_nystrom_attention_review.json"))
    parser.add_argument("--readiness", default=str(LATEST / "2609_08106_complementarity_readiness_mom5gate.json"))
    parser.add_argument("--robustness", default=str(LATEST / "2609_08106_complementarity_mom5gate_robustness.json"))
    parser.add_argument("--forward", default=str(LATEST / "2609_08106_complementarity_forward_shadow_latest.json"))
    parser.add_argument("--forward-log", default=str(PROJECT_ROOT / "results/2609_08106_complementarity_forward_shadow_log.jsonl"))
    parser.add_argument("--latest-target-replay", default=str(DEFAULT_LATEST_TARGET_REPLAY))
    parser.add_argument("--latest-target-param-sweep", default=str(DEFAULT_LATEST_TARGET_PARAM_SWEEP))
    parser.add_argument("--latest-strategy", default=str(LATEST / "strategy.json"))
    parser.add_argument("--min-forward-samples", type=int, default=DEFAULT_MIN_FORWARD_SAMPLES)
    parser.add_argument("--min-triggered-forward-samples", type=int, default=DEFAULT_MIN_TRIGGERED_FORWARD_SAMPLES)
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


if __name__ == "__main__":
    main()
