#!/usr/bin/env python3
"""Delayed-credit audit for 2608.15841-inspired auxiliary heads."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.metrics import roc_auc_score


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PANELS = (
    "00631L.TW=results/ncf_00631l_panel_latest_20260903.csv",
    "00632R.TW=results/ncf_00632r_panel_latest_20260903.csv",
    "0050.TW=results/ncf_0050_panel_latest_20260903.csv",
)
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_delayed_credit_audit.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_delayed_credit_audit.md"

HEADS = {
    "direction_prob": {"score": "ensemble_prob_up", "target": "gain"},
    "drawdown_prob": {"score": "prob_fwd_mdd_gt5_h20", "target": "risk"},
    "gain_prob": {"score": "prob_fwd_gain_gt5_h20", "target": "gain"},
    "tail_reward_risk_score": {"score": "tail_reward_risk_score_h20", "target": "gain"},
}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _items(raw_items: list[str] | tuple[str, ...]) -> list[tuple[str, Path]]:
    parsed: list[tuple[str, Path]] = []
    for raw in raw_items:
        label, sep, path_text = raw.partition("=")
        path = _resolve(path_text if sep else raw)
        parsed.append((label.strip() if sep else path.stem, path))
    return parsed


def _auc(frame: pd.DataFrame, score_col: str, actual_col: str) -> float | None:
    if score_col not in frame.columns or actual_col not in frame.columns:
        return None
    resolved = frame[[score_col, actual_col]].dropna()
    if resolved.empty:
        return None
    y = resolved[actual_col].astype(int)
    if y.nunique() < 2:
        return None
    return float(roc_auc_score(y, resolved[score_col].astype(float)))


def _quartile_gap(frame: pd.DataFrame, score_col: str, value_col: str) -> dict[str, Any]:
    if score_col not in frame.columns or value_col not in frame.columns:
        return {"available": False}
    resolved = frame[[score_col, value_col]].dropna()
    if len(resolved) < 8 or resolved[score_col].nunique() < 2:
        return {"available": False}
    low_cut = resolved[score_col].quantile(0.25)
    high_cut = resolved[score_col].quantile(0.75)
    low = resolved[resolved[score_col] <= low_cut][value_col]
    high = resolved[resolved[score_col] >= high_cut][value_col]
    if low.empty or high.empty:
        return {"available": False}
    return {
        "available": True,
        "low_rows": int(len(low)),
        "high_rows": int(len(high)),
        "low_mean": float(low.mean()),
        "high_mean": float(high.mean()),
        "high_minus_low": float(high.mean() - low.mean()),
    }


def _head_report(
    ticker: str,
    frame: pd.DataFrame,
    head: str,
    score_col: str,
    target: str,
    *,
    min_h20_auc: float,
) -> dict[str, Any]:
    horizon_auc = {
        "h1": _auc(frame, score_col, "actual_up_h1"),
        "h5": _auc(frame, score_col, "actual_up_h5"),
        "h20": _auc(frame, score_col, "actual_up_h20"),
    }
    risk_event_auc = _auc(frame, score_col, "actual_fwd_mdd_gt5_h20")
    gain_gap = _quartile_gap(frame, score_col, "forward_gain_h20")
    mdd_gap = _quartile_gap(frame, score_col, "forward_mdd_h20")
    gain_corr = (
        float(frame[[score_col, "forward_gain_h20"]].dropna().corr(method="spearman").iloc[0, 1])
        if score_col in frame.columns and "forward_gain_h20" in frame.columns and frame[score_col].nunique(dropna=True) > 1
        else None
    )
    mdd_corr = (
        float(frame[[score_col, "forward_mdd_h20"]].dropna().corr(method="spearman").iloc[0, 1])
        if score_col in frame.columns and "forward_mdd_h20" in frame.columns and frame[score_col].nunique(dropna=True) > 1
        else None
    )
    if target == "risk":
        h20_ok = risk_event_auc is not None and float(risk_event_auc) >= min_h20_auc
    else:
        h20_ok = horizon_auc["h20"] is not None and float(horizon_auc["h20"]) >= min_h20_auc
    if target == "risk":
        delayed_ok = bool(mdd_gap.get("available")) and float(mdd_gap["high_minus_low"]) < 0.0
    else:
        delayed_ok = bool(gain_gap.get("available")) and float(gain_gap["high_minus_low"]) > 0.0
    blockers: list[str] = []
    if not h20_ok:
        blockers.append("h20_direction_auc_below_floor")
    if not delayed_ok:
        blockers.append("delayed_h20_outcome_separation_failed")
    return {
        "ticker": ticker,
        "head": head,
        "score_column": score_col,
        "target": target,
        "horizon_direction_auc": horizon_auc,
        "risk_event_auc_h20": risk_event_auc,
        "spearman_forward_gain_h20": gain_corr,
        "spearman_forward_mdd_h20": mdd_corr,
        "forward_gain_h20_quartile_gap": gain_gap,
        "forward_mdd_h20_quartile_gap": mdd_gap,
        "passed": not blockers,
        "blockers": blockers,
    }


def build_report(
    panels: list[tuple[str, Path]],
    *,
    min_h20_auc: float = 0.52,
) -> dict[str, Any]:
    head_reports: list[dict[str, Any]] = []
    missing_panels: list[str] = []
    for ticker, path in panels:
        if not path.exists():
            missing_panels.append(ticker)
            continue
        frame = pd.read_csv(path, encoding="utf-8-sig")
        for head, spec in HEADS.items():
            if spec["score"] in frame.columns:
                head_reports.append(
                    _head_report(
                        ticker,
                        frame,
                        head,
                        str(spec["score"]),
                        str(spec["target"]),
                        min_h20_auc=min_h20_auc,
                    )
                )
    blockers = []
    if missing_panels:
        blockers.append("missing_or_invalid_panels")
    if any(not item["passed"] for item in head_reports):
        blockers.append("delayed_credit_alignment_failed")
    passed = bool(head_reports) and not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_15841_delayed_credit_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "id": "2608.15841",
            "transferable_use": "delayed_auxiliary_task_contribution_gate",
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "thresholds": {"min_h20_auc": min_h20_auc},
        "summary": {
            "delayed_credit_passed": passed,
            "promotion_allowed": False,
            "decision": "delayed_credit_alignment_not_cleared" if not passed else "shadow_passed_but_not_promoted",
            "blockers": blockers,
            "failed_heads": [
                {"ticker": item["ticker"], "head": item["head"], "blockers": item["blockers"]}
                for item in head_reports
                if not item["passed"]
            ],
        },
        "heads": head_reports,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2608.15841 Delayed Credit Audit",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['summary']['decision']}`",
        f"- Delayed-credit passed: `{report['summary']['delayed_credit_passed']}`",
        f"- Promotion allowed: `{report['summary']['promotion_allowed']}`",
        "",
        "| ticker | head | h20 AUC | gain gap | mdd gap | pass |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for item in report["heads"]:
        gain_gap = item["forward_gain_h20_quartile_gap"].get("high_minus_low")
        mdd_gap = item["forward_mdd_h20_quartile_gap"].get("high_minus_low")
        lines.append(
            f"| `{item['ticker']}` | `{item['head']}` | {item['horizon_direction_auc'].get('h20')} | "
            f"{gain_gap} | {mdd_gap} | `{item['passed']}` |"
        )
    lines.extend(["", "This audit is shadow-only and does not alter live weights."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", action="append", dest="panels", default=None)
    parser.add_argument("--min-h20-auc", type=float, default=0.52)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(_items(args.panels or DEFAULT_PANELS), min_h20_auc=args.min_h20_auc)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(f"decision={report['summary']['decision']} delayed_credit_passed={report['summary']['delayed_credit_passed']}")
    print("blockers=" + ",".join(report["summary"]["blockers"]))
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
