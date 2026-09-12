#!/usr/bin/env python3
"""Research-only lifecycle audit for fixed NCF auxiliary heads."""

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
DEFAULT_REGIME_DECAY = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_regime_decay_audit.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_lifecycle_audit.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_lifecycle_audit.md"

AUXILIARY_HEADS = {
    "h20_forward_drawdown_gt5": ("prob_fwd_mdd_gt5_h20", "actual_fwd_mdd_gt5_h20"),
    "h20_forward_gain_gt5": ("prob_fwd_gain_gt5_h20", "actual_fwd_gain_gt5_h20"),
    "tail_reward_risk_score": ("tail_reward_risk_score_h20", "actual_fwd_gain_gt5_h20"),
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


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _auc(frame: pd.DataFrame, prob_col: str, actual_col: str) -> float | None:
    if prob_col not in frame.columns or actual_col not in frame.columns:
        return None
    resolved = frame[[prob_col, actual_col]].dropna()
    if resolved.empty:
        return None
    y = resolved[actual_col].astype(int)
    if y.nunique() < 2:
        return None
    return float(roc_auc_score(y, resolved[prob_col].astype(float)))


def _failed_regime_tasks(regime_decay: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    failed: dict[tuple[str, str], dict[str, Any]] = {}
    if not regime_decay:
        return failed
    summary = regime_decay.get("summary") if isinstance(regime_decay.get("summary"), dict) else {}
    for item in summary.get("failed_tasks", []) if isinstance(summary.get("failed_tasks"), list) else []:
        if isinstance(item, dict):
            failed[(str(item.get("ticker")), str(item.get("task")))] = item
    return failed


def _redundancy_pairs(frame: pd.DataFrame, *, corr_threshold: float) -> list[dict[str, Any]]:
    available = {
        name: col
        for name, (col, _) in AUXILIARY_HEADS.items()
        if col in frame.columns and frame[col].notna().sum() > 2
    }
    pairs: list[dict[str, Any]] = []
    names = list(available)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            corr = frame[[available[left], available[right]]].corr().iloc[0, 1]
            if pd.notna(corr) and abs(float(corr)) >= corr_threshold:
                pairs.append({"left": left, "right": right, "correlation": float(corr)})
    return pairs


def _head_status(
    *,
    ticker: str,
    head: str,
    recent_auc: float | None,
    regime_failed: bool,
    redundant: bool,
    min_recent_auc: float,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if recent_auc is None or recent_auc < min_recent_auc:
        reasons.append("recent_auc_below_floor")
    if regime_failed:
        reasons.append("regime_or_decay_failed")
    if redundant:
        reasons.append("high_redundancy")
    if "recent_auc_below_floor" in reasons and "regime_or_decay_failed" in reasons:
        return "retire_candidate", reasons
    if redundant:
        return "redundant_candidate", reasons
    if reasons:
        return "watchlist", reasons
    return "keep_shadow", reasons


def build_report(
    panels: list[tuple[str, Path]],
    *,
    regime_decay: dict[str, Any] | None = None,
    min_recent_auc: float = 0.52,
    corr_threshold: float = 0.85,
) -> dict[str, Any]:
    failed_tasks = _failed_regime_tasks(regime_decay)
    head_reports: list[dict[str, Any]] = []
    redundancy: list[dict[str, Any]] = []
    missing_panels: list[str] = []
    for ticker, path in panels:
        if not path.exists():
            missing_panels.append(ticker)
            continue
        frame = pd.read_csv(path, encoding="utf-8-sig")
        if "date" not in frame.columns:
            missing_panels.append(ticker)
            continue
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date")
        recent = frame.tail(126)
        pairs = _redundancy_pairs(frame, corr_threshold=corr_threshold)
        redundancy.extend([{"ticker": ticker, **pair} for pair in pairs])
        redundant_heads = {pair["left"] for pair in pairs} | {pair["right"] for pair in pairs}
        for head, (prob_col, actual_col) in AUXILIARY_HEADS.items():
            if prob_col not in frame.columns:
                continue
            recent_auc = _auc(recent, prob_col, actual_col)
            full_auc = _auc(frame, prob_col, actual_col)
            regime_failed = (ticker, head) in failed_tasks
            status, reasons = _head_status(
                ticker=ticker,
                head=head,
                recent_auc=recent_auc,
                regime_failed=regime_failed,
                redundant=head in redundant_heads,
                min_recent_auc=min_recent_auc,
            )
            head_reports.append(
                {
                    "ticker": ticker,
                    "head": head,
                    "status": status,
                    "reasons": reasons,
                    "full_auc": full_auc,
                    "recent_auc": recent_auc,
                    "regime_decay_failed": regime_failed,
                    "redundant": head in redundant_heads,
                }
            )
    status_counts: dict[str, int] = {}
    for item in head_reports:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    blockers = []
    if missing_panels:
        blockers.append("missing_or_invalid_panels")
    if any(item["status"] in {"retire_candidate", "redundant_candidate"} for item in head_reports):
        blockers.append("head_lifecycle_review_required")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_15841_auxiliary_lifecycle_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "id": "2608.15841",
            "transferable_use": "auxiliary_head_pruning_redundancy_retirement_gate",
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "thresholds": {"min_recent_auc": min_recent_auc, "corr_threshold": corr_threshold},
        "summary": {
            "head_lifecycle_passed": not blockers and bool(head_reports),
            "promotion_allowed": False,
            "decision": "head_lifecycle_review_required" if blockers else "shadow_passed_but_not_promoted",
            "blockers": blockers,
            "status_counts": status_counts,
        },
        "redundancy_pairs": redundancy,
        "heads": head_reports,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2608.15841 Auxiliary Head Lifecycle Audit",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['summary']['decision']}`",
        f"- Lifecycle passed: `{report['summary']['head_lifecycle_passed']}`",
        f"- Promotion allowed: `{report['summary']['promotion_allowed']}`",
        "",
        "| ticker | head | status | full AUC | recent AUC | reasons |",
        "|---|---|---|---:|---:|---|",
    ]
    for item in report["heads"]:
        lines.append(
            f"| `{item['ticker']}` | `{item['head']}` | `{item['status']}` | "
            f"{item.get('full_auc')} | {item.get('recent_auc')} | "
            f"`{', '.join(item.get('reasons') or []) or 'none'}` |"
        )
    lines.extend(["", "This audit is shadow-only and does not retire production heads."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", action="append", dest="panels", default=None)
    parser.add_argument("--regime-decay", default=str(DEFAULT_REGIME_DECAY))
    parser.add_argument("--min-recent-auc", type=float, default=0.52)
    parser.add_argument("--corr-threshold", type=float, default=0.85)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(
        _items(args.panels or DEFAULT_PANELS),
        regime_decay=_load_optional_json(_resolve(args.regime_decay) if args.regime_decay else None),
        min_recent_auc=args.min_recent_auc,
        corr_threshold=args.corr_threshold,
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(f"decision={report['summary']['decision']} lifecycle_passed={report['summary']['head_lifecycle_passed']}")
    print("blockers=" + ",".join(report["summary"]["blockers"]))
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
