#!/usr/bin/env python3
"""Build a research-only readiness gate for 2608.15841 auxiliary-task ideas."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PANELS = (
    "00631L.TW=results/ncf_00631l_panel_latest_20260903.csv",
    "00632R.TW=results/ncf_00632r_panel_latest_20260903.csv",
    "0050.TW=results/ncf_0050_panel_latest_20260903.csv",
)
DEFAULT_SIGNALS = (
    "00631L.TW=results/ncf_00631l_latest_20260903.json",
    "00632R.TW=results/ncf_00632r_latest_20260903.json",
    "0050.TW=results/ncf_0050_latest_20260903.json",
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_task_discovery_readiness.md"
DEFAULT_POLICY_LIFT = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_existing_aux_heads_policy_lift_shadow.json"
DEFAULT_PURGED_WF = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_purged_walkforward.json"
DEFAULT_CHURN_SHADOW = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_churn_shadow.json"
DEFAULT_REGIME_DECAY = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_regime_decay_audit.json"
DEFAULT_CANDIDATE_BANK_BLUEPRINT = (
    PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_candidate_auxiliary_bank_blueprint.json"
)
DEFAULT_LIFECYCLE_AUDIT = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_lifecycle_audit.json"
DEFAULT_DELAYED_CREDIT = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_delayed_credit_audit.json"


AUXILIARY_TASKS = {
    "h20_forward_drawdown_gt5": ("prob_fwd_mdd_gt5_h20", "actual_fwd_mdd_gt5_h20"),
    "h20_forward_gain_gt5": ("prob_fwd_gain_gt5_h20", "actual_fwd_gain_gt5_h20"),
}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_json_optional(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _items(raw_items: list[str] | tuple[str, ...]) -> list[tuple[str, Path]]:
    parsed: list[tuple[str, Path]] = []
    for raw in raw_items:
        label, sep, path_text = raw.partition("=")
        if not sep:
            path = _resolve(raw)
            label = path.stem
        else:
            path = _resolve(path_text)
        parsed.append((label.strip(), path))
    return parsed


def _metric_pair(frame: pd.DataFrame, *, prob_col: str, actual_col: str) -> dict[str, Any]:
    if prob_col not in frame.columns or actual_col not in frame.columns:
        return {
            "available": False,
            "resolved_rows": 0,
            "positive_rows": 0,
            "positive_rate": None,
            "auc": None,
            "brier": None,
        }
    resolved = frame[[prob_col, actual_col]].dropna()
    if resolved.empty:
        return {
            "available": True,
            "resolved_rows": 0,
            "positive_rows": 0,
            "positive_rate": None,
            "auc": None,
            "brier": None,
        }
    y = resolved[actual_col].astype(int)
    p = resolved[prob_col].astype(float).clip(0.0, 1.0)
    auc = float(roc_auc_score(y, p)) if y.nunique() == 2 else None
    return {
        "available": True,
        "resolved_rows": int(len(resolved)),
        "positive_rows": int(y.sum()),
        "positive_rate": float(y.mean()),
        "auc": auc,
        "brier": float(brier_score_loss(y, p)),
    }


def _panel_summary(ticker: str, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "ticker": ticker,
            "panel": str(path),
            "available": False,
            "rows": 0,
            "date_start": None,
            "date_end": None,
            "auxiliary_tasks": {},
            "tail_reward_risk_score_available": False,
        }
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "date" in frame.columns:
        dates = pd.to_datetime(frame["date"], errors="coerce")
        date_start = str(dates.min().date()) if dates.notna().any() else None
        date_end = str(dates.max().date()) if dates.notna().any() else None
    else:
        date_start = None
        date_end = None
    return {
        "ticker": ticker,
        "panel": str(path),
        "available": True,
        "rows": int(len(frame)),
        "date_start": date_start,
        "date_end": date_end,
        "auxiliary_tasks": {
            name: _metric_pair(frame, prob_col=prob_col, actual_col=actual_col)
            for name, (prob_col, actual_col) in AUXILIARY_TASKS.items()
        },
        "tail_reward_risk_score_available": "tail_reward_risk_score_h20" in frame.columns,
    }


def _signal_summary(ticker: str, path: Path) -> dict[str, Any]:
    payload = _load_json_optional(path)
    if payload is None:
        return {"ticker": ticker, "signal": str(path), "available": False, "freshness_status": "missing"}
    freshness = payload.get("data_freshness") if isinstance(payload.get("data_freshness"), dict) else {}
    stale_sources = freshness.get("stale_sources") if isinstance(freshness.get("stale_sources"), list) else []
    missing_sources = freshness.get("missing_sources") if isinstance(freshness.get("missing_sources"), list) else []
    return {
        "ticker": ticker,
        "signal": str(path),
        "available": True,
        "last_close_date": payload.get("last_close_date"),
        "freshness_status": freshness.get("status", "unknown"),
        "stale_sources": stale_sources,
        "missing_sources": missing_sources,
    }


def _policy_lift_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"available": False, "path": None, "best_variant": None, "validated": False}
    payload = _load_json_optional(path)
    if payload is None:
        return {"available": False, "path": str(path), "best_variant": None, "validated": False}
    results = payload.get("results") if isinstance(payload.get("results"), dict) else {}
    variants: dict[str, Any] = {}
    for name, item in results.items():
        delta = item.get("delta_vs_baseline", {}) if isinstance(item, dict) else {}
        variants[str(name)] = {
            "delta_final_value": delta.get("final_value"),
            "delta_sharpe_ratio": delta.get("sharpe_ratio"),
            "delta_max_drawdown": delta.get("max_drawdown"),
            "mean_score_on_golden1_days": item.get("mean_score_on_golden1_days") if isinstance(item, dict) else None,
            "days_score_gt_0": item.get("days_score_gt_0") if isinstance(item, dict) else None,
            "joint_pass": (
                float(delta.get("final_value") or 0.0) >= 0.0
                and float(delta.get("sharpe_ratio") or 0.0) >= 0.0
                and float(delta.get("max_drawdown") or 0.0) >= 0.0
            ),
        }
    best_name = max(
        variants,
        key=lambda key: (
            float(variants[key]["delta_final_value"] or 0.0),
            float(variants[key]["delta_sharpe_ratio"] or 0.0),
            float(variants[key]["delta_max_drawdown"] or 0.0),
        ),
        default=None,
    )
    return {
        "available": True,
        "path": str(path),
        "window": payload.get("window"),
        "best_variant": best_name,
        "variants": variants,
        "validated": any(item["joint_pass"] for item in variants.values()),
        "validation_rule": "requires_delta_final_value_delta_sharpe_and_delta_max_drawdown_all_nonnegative",
    }


def _purged_wf_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"available": False, "path": None, "passed": False}
    payload = _load_json_optional(path)
    if payload is None:
        return {"available": False, "path": str(path), "passed": False}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "available": True,
        "path": str(path),
        "passed": bool(summary.get("purged_walk_forward_policy_impact_passed")),
        "best_score": summary.get("best_score"),
        "by_score": summary.get("by_score", {}),
        "window": payload.get("window", {}),
    }


def _churn_shadow_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"available": False, "path": None, "passed": False}
    payload = _load_json_optional(path)
    if payload is None:
        return {"available": False, "path": str(path), "passed": False}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "available": True,
        "path": str(path),
        "passed": bool(summary.get("multi_window_cost_turnover_passed")),
        "decision": summary.get("decision"),
        "blockers": summary.get("blockers", []),
        "variants": payload.get("variants", []),
        "window": payload.get("window", {}),
    }


def _regime_decay_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"available": False, "path": None, "passed": False}
    payload = _load_json_optional(path)
    if payload is None:
        return {"available": False, "path": str(path), "passed": False}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "available": True,
        "path": str(path),
        "passed": bool(summary.get("temporal_regime_stability_passed")),
        "decision": summary.get("decision"),
        "blockers": summary.get("blockers", []),
        "failed_tasks": summary.get("failed_tasks", []),
    }


def _candidate_bank_blueprint_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"available": False, "path": None, "training_allowed": False}
    payload = _load_json_optional(path)
    if payload is None:
        return {"available": False, "path": str(path), "training_allowed": False}
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    return {
        "available": True,
        "path": str(path),
        "training_allowed": bool(payload.get("training_allowed")),
        "promotion_allowed": bool(payload.get("promotion_allowed")),
        "decision": decision.get("decision"),
        "blockers": decision.get("blockers", []),
        "candidate_grid": payload.get("candidate_grid", []),
        "admission_tests": payload.get("admission_tests", []),
    }


def _lifecycle_audit_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"available": False, "path": None, "passed": False}
    payload = _load_json_optional(path)
    if payload is None:
        return {"available": False, "path": str(path), "passed": False}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "available": True,
        "path": str(path),
        "passed": bool(summary.get("head_lifecycle_passed")),
        "decision": summary.get("decision"),
        "blockers": summary.get("blockers", []),
        "status_counts": summary.get("status_counts", {}),
        "redundancy_pairs": payload.get("redundancy_pairs", []),
        "heads": payload.get("heads", []),
    }


def _delayed_credit_summary(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"available": False, "path": None, "passed": False}
    payload = _load_json_optional(path)
    if payload is None:
        return {"available": False, "path": str(path), "passed": False}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "available": True,
        "path": str(path),
        "passed": bool(summary.get("delayed_credit_passed")),
        "decision": summary.get("decision"),
        "blockers": summary.get("blockers", []),
        "failed_heads": summary.get("failed_heads", []),
    }


def build_report(
    panels: list[tuple[str, Path]],
    signals: list[tuple[str, Path]],
    *,
    policy_lift_path: Path | None = None,
    purged_wf_path: Path | None = None,
    churn_shadow_path: Path | None = None,
    regime_decay_path: Path | None = None,
    candidate_bank_blueprint_path: Path | None = None,
    lifecycle_audit_path: Path | None = None,
    delayed_credit_path: Path | None = None,
    min_resolved_rows: int = 250,
    min_positive_rows: int = 20,
    min_auc: float = 0.55,
) -> dict[str, Any]:
    panel_summaries = [_panel_summary(ticker, path) for ticker, path in panels]
    signal_summaries = [_signal_summary(ticker, path) for ticker, path in signals]
    all_task_metrics = [
        task
        for panel in panel_summaries
        for task in panel.get("auxiliary_tasks", {}).values()
    ]
    missing_or_unavailable = [
        panel["ticker"]
        for panel in panel_summaries
        if not panel.get("available") or not panel.get("tail_reward_risk_score_available")
    ]
    weak_tasks = [
        {
            "ticker": panel["ticker"],
            "task": task_name,
            "reason": "insufficient_or_weak_auxiliary_metric",
            "metric": metric,
        }
        for panel in panel_summaries
        for task_name, metric in panel.get("auxiliary_tasks", {}).items()
        if (
            not metric.get("available")
            or int(metric.get("resolved_rows") or 0) < min_resolved_rows
            or int(metric.get("positive_rows") or 0) < min_positive_rows
            or metric.get("auc") is None
            or float(metric.get("auc") or 0.0) < min_auc
        )
    ]
    stale_signals = [
        summary
        for summary in signal_summaries
        if summary.get("freshness_status") not in {"ok", "fresh"}
    ]
    policy_lift = _policy_lift_summary(policy_lift_path)
    purged_wf = _purged_wf_summary(purged_wf_path)
    churn_shadow = _churn_shadow_summary(churn_shadow_path)
    regime_decay = _regime_decay_summary(regime_decay_path)
    candidate_bank_blueprint = _candidate_bank_blueprint_summary(candidate_bank_blueprint_path)
    lifecycle_audit = _lifecycle_audit_summary(lifecycle_audit_path)
    delayed_credit = _delayed_credit_summary(delayed_credit_path)
    checks = {
        "existing_aux_heads_available": not missing_or_unavailable and all(task.get("available") for task in all_task_metrics),
        "aux_head_standalone_quality_passed": not weak_tasks,
        "live_feature_freshness_ok": not stale_signals,
        "quest_trader_retrained_for_group_a_plus": False,
        "downstream_policy_lift_validated": bool(policy_lift["validated"]),
        "purged_walk_forward_policy_impact_passed": bool(purged_wf["passed"]),
        "multi_window_cost_turnover_passed": bool(churn_shadow["passed"]),
        "temporal_regime_stability_passed": bool(regime_decay["passed"]),
        "auxiliary_head_lifecycle_passed": bool(lifecycle_audit["passed"]),
        "delayed_credit_alignment_passed": bool(delayed_credit["passed"]),
        "candidate_auxiliary_bank_blueprint_available": bool(candidate_bank_blueprint["available"]),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_15841_auxiliary_task_discovery_readiness",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "id": "2608.15841",
            "title": "Self-Supervised Auxiliary Task Discovery for Stable Reinforcement Learning in Stock Trading",
            "transferable_use": "auxiliary_task_discovery_readiness_gate_only",
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "decision": {
            "promotion_allowed": False,
            "decision": "shadow_readiness_only",
            "reason": "Existing NCF auxiliary heads can be audited, but QUESTrader-style task discovery has not been trained or validated on GroupA+ ETF policy impact.",
            "blockers": blockers,
        },
        "thresholds": {
            "min_resolved_rows": min_resolved_rows,
            "min_positive_rows": min_positive_rows,
            "min_auc": min_auc,
        },
        "checks": checks,
        "panels": panel_summaries,
        "signals": signal_summaries,
        "weak_tasks": weak_tasks,
        "stale_or_missing_signals": stale_signals,
        "policy_lift_shadow": policy_lift,
        "purged_walk_forward_shadow": purged_wf,
        "churn_cost_shadow": churn_shadow,
        "regime_decay_audit": regime_decay,
        "auxiliary_head_lifecycle_audit": lifecycle_audit,
        "delayed_credit_audit": delayed_credit,
        "candidate_auxiliary_bank_blueprint": candidate_bank_blueprint,
        "recommended_next_experiment": {
            "status": "not_started",
            "scope": "shadow_only_compare_existing_fixed_aux_heads_vs_small_candidate_auxiliary_bank",
            "constraints": [
                "purged_walk_forward_no_forward_label_leakage",
                "multi_window_policy_impact_not_standalone_auc_only",
                "realistic_cost_and_turnover_comparison",
                "no_latest_strategy_change_until_passed",
            ],
            "initial_grid": {
                "gvf_question_count": [16, 32, 64],
                "meta_unroll_length": [10, 20],
            },
        },
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2608.15841 Auxiliary Task Discovery Readiness",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']['decision']}`",
        f"- Promotion allowed: `{report['decision']['promotion_allowed']}`",
        f"- No target-weight change: `{not report['changes_latest_strategy']}`",
        "",
        "## Checks",
        "",
        "| check | pass |",
        "|---|---:|",
    ]
    for name, passed in report["checks"].items():
        lines.append(f"| `{name}` | `{passed}` |")
    lines.extend(["", "## Panel Metrics", ""])
    for panel in report["panels"]:
        lines.append(f"### {panel['ticker']}")
        lines.append("")
        lines.append(f"- rows: `{panel['rows']}`")
        lines.append(f"- range: `{panel['date_start']}` to `{panel['date_end']}`")
        for task_name, metric in panel.get("auxiliary_tasks", {}).items():
            lines.append(
                f"- `{task_name}`: rows={metric.get('resolved_rows')} positives={metric.get('positive_rows')} "
                f"auc={metric.get('auc')} brier={metric.get('brier')}"
            )
        lines.append("")
    policy_lift = report.get("policy_lift_shadow", {})
    lines.extend(["## Policy Lift Shadow", ""])
    lines.append(f"- available: `{policy_lift.get('available')}`")
    lines.append(f"- validated: `{policy_lift.get('validated')}`")
    lines.append(f"- best variant: `{policy_lift.get('best_variant')}`")
    for name, item in (policy_lift.get("variants") or {}).items():
        lines.append(
            f"- `{name}`: dFV={item.get('delta_final_value')} "
            f"dSharpe={item.get('delta_sharpe_ratio')} dMDD={item.get('delta_max_drawdown')} "
            f"joint_pass={item.get('joint_pass')}"
        )
    lines.append("")
    purged_wf = report.get("purged_walk_forward_shadow", {})
    lines.extend(["## Purged Walk-Forward Shadow", ""])
    lines.append(f"- available: `{purged_wf.get('available')}`")
    lines.append(f"- passed: `{purged_wf.get('passed')}`")
    lines.append(f"- best score: `{purged_wf.get('best_score')}`")
    for name, item in (purged_wf.get("by_score") or {}).items():
        lines.append(
            f"- `{name}`: folds={item.get('folds')} pass_count={item.get('pass_count')} "
            f"pass_fraction={item.get('pass_fraction')} passed={item.get('passed')}"
        )
    churn_shadow = report.get("churn_cost_shadow", {})
    lines.extend(["", "## Churn / Cost Shadow", ""])
    lines.append(f"- available: `{churn_shadow.get('available')}`")
    lines.append(f"- passed: `{churn_shadow.get('passed')}`")
    lines.append(f"- decision: `{churn_shadow.get('decision')}`")
    lines.append(f"- blockers: `{', '.join(churn_shadow.get('blockers') or []) or 'none'}`")
    regime_decay = report.get("regime_decay_audit", {})
    lines.extend(["", "## Regime / Decay Audit", ""])
    lines.append(f"- available: `{regime_decay.get('available')}`")
    lines.append(f"- passed: `{regime_decay.get('passed')}`")
    lines.append(f"- decision: `{regime_decay.get('decision')}`")
    lines.append(f"- blockers: `{', '.join(regime_decay.get('blockers') or []) or 'none'}`")
    lifecycle = report.get("auxiliary_head_lifecycle_audit", {})
    lines.extend(["", "## Auxiliary Head Lifecycle Audit", ""])
    lines.append(f"- available: `{lifecycle.get('available')}`")
    lines.append(f"- passed: `{lifecycle.get('passed')}`")
    lines.append(f"- decision: `{lifecycle.get('decision')}`")
    lines.append(f"- status counts: `{lifecycle.get('status_counts')}`")
    delayed = report.get("delayed_credit_audit", {})
    lines.extend(["", "## Delayed Credit Audit", ""])
    lines.append(f"- available: `{delayed.get('available')}`")
    lines.append(f"- passed: `{delayed.get('passed')}`")
    lines.append(f"- decision: `{delayed.get('decision')}`")
    blueprint = report.get("candidate_auxiliary_bank_blueprint", {})
    lines.extend(["", "## Candidate Auxiliary Bank Blueprint", ""])
    lines.append(f"- available: `{blueprint.get('available')}`")
    lines.append(f"- training allowed: `{blueprint.get('training_allowed')}`")
    lines.append(f"- decision: `{blueprint.get('decision')}`")
    lines.append("")
    lines.append("This report is a QUESTrader-inspired shadow/readiness gate only.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", action="append", dest="panels", default=None)
    parser.add_argument("--signal", action="append", dest="signals", default=None)
    parser.add_argument("--min-resolved-rows", type=int, default=250)
    parser.add_argument("--min-positive-rows", type=int, default=20)
    parser.add_argument("--min-auc", type=float, default=0.55)
    parser.add_argument("--policy-lift", default=str(DEFAULT_POLICY_LIFT))
    parser.add_argument("--purged-wf", default=str(DEFAULT_PURGED_WF))
    parser.add_argument("--churn-shadow", default=str(DEFAULT_CHURN_SHADOW))
    parser.add_argument("--regime-decay", default=str(DEFAULT_REGIME_DECAY))
    parser.add_argument("--candidate-bank-blueprint", default=str(DEFAULT_CANDIDATE_BANK_BLUEPRINT))
    parser.add_argument("--lifecycle-audit", default=str(DEFAULT_LIFECYCLE_AUDIT))
    parser.add_argument("--delayed-credit", default=str(DEFAULT_DELAYED_CREDIT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(
        _items(args.panels or DEFAULT_PANELS),
        _items(args.signals or DEFAULT_SIGNALS),
        policy_lift_path=_resolve(args.policy_lift) if args.policy_lift else None,
        purged_wf_path=_resolve(args.purged_wf) if args.purged_wf else None,
        churn_shadow_path=_resolve(args.churn_shadow) if args.churn_shadow else None,
        regime_decay_path=_resolve(args.regime_decay) if args.regime_decay else None,
        candidate_bank_blueprint_path=(
            _resolve(args.candidate_bank_blueprint) if args.candidate_bank_blueprint else None
        ),
        lifecycle_audit_path=_resolve(args.lifecycle_audit) if args.lifecycle_audit else None,
        delayed_credit_path=_resolve(args.delayed_credit) if args.delayed_credit else None,
        min_resolved_rows=args.min_resolved_rows,
        min_positive_rows=args.min_positive_rows,
        min_auc=args.min_auc,
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(f"decision={report['decision']['decision']} promotion_allowed={report['decision']['promotion_allowed']}")
    print("blockers=" + ",".join(report["decision"]["blockers"]))
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
