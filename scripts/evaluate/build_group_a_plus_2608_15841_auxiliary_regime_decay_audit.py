#!/usr/bin/env python3
"""Temporal/regime stability audit for 2608.15841-inspired auxiliary heads."""

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
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_regime_decay_audit.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_regime_decay_audit.md"

AUXILIARY_TASKS = {
    "h20_forward_drawdown_gt5": ("prob_fwd_mdd_gt5_h20", "actual_fwd_mdd_gt5_h20"),
    "h20_forward_gain_gt5": ("prob_fwd_gain_gt5_h20", "actual_fwd_gain_gt5_h20"),
}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


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


def _metric(frame: pd.DataFrame, prob_col: str, actual_col: str) -> dict[str, Any]:
    if prob_col not in frame.columns or actual_col not in frame.columns:
        return {"available": False, "rows": 0, "positives": 0, "auc": None, "brier": None}
    resolved = frame[[prob_col, actual_col]].dropna()
    if resolved.empty:
        return {"available": True, "rows": 0, "positives": 0, "auc": None, "brier": None}
    y = resolved[actual_col].astype(int)
    p = resolved[prob_col].astype(float).clip(0.0, 1.0)
    return {
        "available": True,
        "rows": int(len(resolved)),
        "positives": int(y.sum()),
        "auc": float(roc_auc_score(y, p)) if y.nunique() == 2 else None,
        "brier": float(brier_score_loss(y, p)),
    }


def _slice_metrics(frame: pd.DataFrame, prob_col: str, actual_col: str) -> dict[str, dict[str, Any]]:
    ordered = frame.sort_values("date").reset_index(drop=True)
    midpoint = len(ordered) // 2
    slices: dict[str, pd.DataFrame] = {
        "first_half": ordered.iloc[:midpoint],
        "second_half": ordered.iloc[midpoint:],
        "recent_126": ordered.tail(126),
    }
    if "direction" in ordered.columns:
        for direction, part in ordered.groupby("direction", dropna=True):
            slices[f"direction_{str(direction).lower()}"] = part
    if "confidence" in ordered.columns and ordered["confidence"].notna().any():
        median_conf = float(pd.to_numeric(ordered["confidence"], errors="coerce").median())
        slices["confidence_high"] = ordered[pd.to_numeric(ordered["confidence"], errors="coerce") >= median_conf]
        slices["confidence_low"] = ordered[pd.to_numeric(ordered["confidence"], errors="coerce") < median_conf]
    if "tail_reward_risk_score_h20" in ordered.columns and ordered["tail_reward_risk_score_h20"].notna().any():
        tail = pd.to_numeric(ordered["tail_reward_risk_score_h20"], errors="coerce")
        median_tail = float(tail.median())
        slices["tail_score_high"] = ordered[tail >= median_tail]
        slices["tail_score_low"] = ordered[tail < median_tail]
    return {name: _metric(part, prob_col, actual_col) for name, part in slices.items()}


def _task_report(
    ticker: str,
    frame: pd.DataFrame,
    task: str,
    prob_col: str,
    actual_col: str,
    *,
    min_slice_rows: int,
    min_recent_auc: float,
    max_auc_decay: float,
) -> dict[str, Any]:
    slices = _slice_metrics(frame, prob_col, actual_col)
    first_auc = slices.get("first_half", {}).get("auc")
    second_auc = slices.get("second_half", {}).get("auc")
    recent_auc = slices.get("recent_126", {}).get("auc")
    auc_decay = (
        float(first_auc) - float(second_auc)
        if first_auc is not None and second_auc is not None
        else None
    )
    weak_slices = [
        name
        for name, metric in slices.items()
        if int(metric.get("rows") or 0) >= min_slice_rows
        and (metric.get("auc") is None or float(metric.get("auc") or 0.0) < min_recent_auc)
    ]
    blockers: list[str] = []
    if recent_auc is None or float(recent_auc) < min_recent_auc:
        blockers.append("recent_auc_below_floor")
    if auc_decay is not None and auc_decay > max_auc_decay:
        blockers.append("second_half_auc_decay_too_large")
    if weak_slices:
        blockers.append("weak_regime_or_temporal_slices")
    return {
        "ticker": ticker,
        "task": task,
        "slices": slices,
        "auc_decay_first_to_second_half": auc_decay,
        "weak_slices": weak_slices,
        "passed": not blockers,
        "blockers": blockers,
    }


def build_report(
    panels: list[tuple[str, Path]],
    *,
    min_slice_rows: int = 40,
    min_recent_auc: float = 0.52,
    max_auc_decay: float = 0.15,
) -> dict[str, Any]:
    task_reports: list[dict[str, Any]] = []
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
        for task, (prob_col, actual_col) in AUXILIARY_TASKS.items():
            task_reports.append(
                _task_report(
                    ticker,
                    frame,
                    task,
                    prob_col,
                    actual_col,
                    min_slice_rows=min_slice_rows,
                    min_recent_auc=min_recent_auc,
                    max_auc_decay=max_auc_decay,
                )
            )
    blockers = []
    if missing_panels:
        blockers.append("missing_or_invalid_panels")
    if any(not item["passed"] for item in task_reports):
        blockers.append("unstable_auxiliary_task_slices")
    passed = bool(task_reports) and not blockers
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_15841_auxiliary_regime_decay_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "id": "2608.15841",
            "transferable_use": "auxiliary_task_temporal_regime_stability_gate",
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "thresholds": {
            "min_slice_rows": min_slice_rows,
            "min_recent_auc": min_recent_auc,
            "max_auc_decay": max_auc_decay,
        },
        "summary": {
            "temporal_regime_stability_passed": passed,
            "promotion_allowed": False,
            "decision": "temporal_regime_stability_not_cleared" if not passed else "shadow_passed_but_not_promoted",
            "blockers": blockers,
            "failed_tasks": [
                {"ticker": item["ticker"], "task": item["task"], "blockers": item["blockers"]}
                for item in task_reports
                if not item["passed"]
            ],
        },
        "tasks": task_reports,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2608.15841 Auxiliary Regime / Decay Audit",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['summary']['decision']}`",
        f"- Stability passed: `{report['summary']['temporal_regime_stability_passed']}`",
        f"- Promotion allowed: `{report['summary']['promotion_allowed']}`",
        "",
        "| ticker | task | recent AUC | AUC decay | weak slices | pass |",
        "|---|---|---:|---:|---|---:|",
    ]
    for item in report["tasks"]:
        recent_auc = item["slices"].get("recent_126", {}).get("auc")
        lines.append(
            f"| `{item['ticker']}` | `{item['task']}` | {recent_auc} | "
            f"{item.get('auc_decay_first_to_second_half')} | "
            f"`{', '.join(item.get('weak_slices') or []) or 'none'}` | `{item['passed']}` |"
        )
    lines.extend(["", "This audit is shadow-only and does not alter live weights."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", action="append", dest="panels", default=None)
    parser.add_argument("--min-slice-rows", type=int, default=40)
    parser.add_argument("--min-recent-auc", type=float, default=0.52)
    parser.add_argument("--max-auc-decay", type=float, default=0.15)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(
        _items(args.panels or DEFAULT_PANELS),
        min_slice_rows=args.min_slice_rows,
        min_recent_auc=args.min_recent_auc,
        max_auc_decay=args.max_auc_decay,
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(
        f"decision={report['summary']['decision']} "
        f"stability_passed={report['summary']['temporal_regime_stability_passed']}"
    )
    print("blockers=" + ",".join(report["summary"]["blockers"]))
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
