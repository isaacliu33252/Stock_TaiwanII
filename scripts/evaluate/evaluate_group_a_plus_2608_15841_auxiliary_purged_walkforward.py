#!/usr/bin/env python3
"""Purged walk-forward validation for 2608.15841-inspired NCF auxiliary scores."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.ncf import ncf_downside_signal, ncf_upside_signal  # noqa: E402
from group_a_plus.validation import PurgedWalkForwardSplit  # noqa: E402


DEFAULT_PANEL_631L = PROJECT_ROOT / "results/ncf_00631l_panel_latest_20260903.csv"
DEFAULT_PANEL_632R = PROJECT_ROOT / "results/ncf_00632r_panel_latest_20260903.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_purged_walkforward.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_15841_auxiliary_purged_walkforward.md"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _sig(row: pd.Series, suffix: str) -> dict[str, Any]:
    def get(name: str) -> Any:
        value = row.get(f"{name}_{suffix}")
        return None if pd.isna(value) else float(value)

    return {
        "calibrated_prob_up": get("ensemble_prob_up"),
        "confidence": get("confidence") or 0.0,
        "tail_reward_risk_score": get("tail_reward_risk_score_h20"),
        "prob_fwd_mdd_gt5_h20": get("prob_fwd_mdd_gt5_h20"),
        "prob_fwd_gain_gt5_h20": get("prob_fwd_gain_gt5_h20"),
        "direction_conflict": False,
    }


def _first_value(row: pd.Series, *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if not pd.isna(value):
            return value
    return None


def build_score_frame(panel_631l_path: Path, panel_632r_path: Path) -> pd.DataFrame:
    left = pd.read_csv(panel_631l_path, encoding="utf-8-sig")
    right = pd.read_csv(panel_632r_path, encoding="utf-8-sig")
    merged = left.set_index("date").join(right.set_index("date"), how="inner", lsuffix="_631l", rsuffix="_632r")
    rows: list[dict[str, Any]] = []
    for date, row in merged.iterrows():
        sig_631l = _sig(row, "631l")
        sig_632r = _sig(row, "632r")
        downside = ncf_downside_signal(sig_631l, sig_632r)
        upside = ncf_upside_signal(sig_631l, sig_632r)
        rows.append(
            {
                "date": str(pd.Timestamp(date).date()),
                "downside_score": downside,
                "upside_score": upside,
                "net_derisk_score": max(0.0, downside - upside),
                "forward_gain_h20_631l": _first_value(row, "forward_gain_h20_631l", "forward_gain_h20"),
                "forward_mdd_h20_631l": _first_value(row, "forward_mdd_h20_631l", "forward_mdd_h20"),
                "actual_fwd_mdd_gt5_h20_631l": _first_value(
                    row,
                    "actual_fwd_mdd_gt5_h20_631l",
                    "actual_fwd_mdd_gt5_h20",
                ),
            }
        )
    frame = pd.DataFrame(rows)
    for col in frame.columns:
        if col != "date":
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.dropna(subset=["forward_gain_h20_631l", "forward_mdd_h20_631l"]).reset_index(drop=True)


def _fold_row(frame: pd.DataFrame, test_idx, *, score_col: str, quantile: float) -> dict[str, Any]:
    test = frame.iloc[test_idx].copy()
    threshold = float(test[score_col].quantile(quantile))
    high = test[test[score_col] > threshold]
    low = test[test[score_col] <= threshold]
    if high.empty and test[score_col].nunique(dropna=True) > 1:
        top_n = max(1, int(round(len(test) * (1.0 - quantile))))
        high_index = test[score_col].sort_values(ascending=False).head(top_n).index
        high = test.loc[high_index]
        low = test.drop(index=high_index)
    if high.empty or low.empty:
        return {
            "score": score_col,
            "test_start": str(test["date"].min()),
            "test_end": str(test["date"].max()),
            "test_rows": int(len(test)),
            "high_score_rows": int(len(high)),
            "pass": False,
            "reason": "empty_high_or_low_bucket",
        }
    high_gain = float(high["forward_gain_h20_631l"].mean())
    low_gain = float(low["forward_gain_h20_631l"].mean())
    high_mdd = float(high["forward_mdd_h20_631l"].mean())
    low_mdd = float(low["forward_mdd_h20_631l"].mean())
    high_mdd_event = float(high["actual_fwd_mdd_gt5_h20_631l"].mean())
    low_mdd_event = float(low["actual_fwd_mdd_gt5_h20_631l"].mean())
    passed = high_gain <= low_gain and high_mdd <= low_mdd and high_mdd_event >= low_mdd_event
    return {
        "score": score_col,
        "test_start": str(test["date"].min()),
        "test_end": str(test["date"].max()),
        "test_rows": int(len(test)),
        "high_score_rows": int(len(high)),
        "threshold": threshold,
        "high_mean_forward_gain_h20_631l": high_gain,
        "low_mean_forward_gain_h20_631l": low_gain,
        "high_mean_forward_mdd_h20_631l": high_mdd,
        "low_mean_forward_mdd_h20_631l": low_mdd,
        "high_mdd_gt5_rate_631l": high_mdd_event,
        "low_mdd_gt5_rate_631l": low_mdd_event,
        "pass": passed,
        "reason": "high_score_bucket_has_lower_gain_worse_mdd_and_higher_mdd_event" if passed else "mixed_or_wrong_separation",
    }


def build_report(
    panel_631l_path: Path,
    panel_632r_path: Path,
    *,
    n_splits: int = 4,
    purge: int = 20,
    min_train_size: int = 120,
    min_pass_fraction: float = 0.75,
    quantile: float = 0.75,
) -> dict[str, Any]:
    frame = build_score_frame(panel_631l_path, panel_632r_path)
    splitter = PurgedWalkForwardSplit(n_splits=n_splits, purge=purge, min_train_size=min_train_size)
    folds = list(splitter.split(frame))
    rows = [
        _fold_row(frame, test_idx, score_col=score_col, quantile=quantile)
        for _, test_idx in folds
        for score_col in ("downside_score", "net_derisk_score")
    ]
    by_score: dict[str, Any] = {}
    for score_col in ("downside_score", "net_derisk_score"):
        score_rows = [row for row in rows if row["score"] == score_col]
        pass_count = sum(bool(row["pass"]) for row in score_rows)
        total = len(score_rows)
        by_score[score_col] = {
            "folds": total,
            "pass_count": pass_count,
            "pass_fraction": pass_count / total if total else 0.0,
            "passed": total > 0 and (pass_count / total) >= min_pass_fraction,
        }
    overall_passed = any(item["passed"] for item in by_score.values())
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_15841_auxiliary_purged_walkforward",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "2608.15841",
        "policy": "research_only_no_weight_change",
        "inputs": {
            "panel_631l": str(panel_631l_path),
            "panel_632r": str(panel_632r_path),
        },
        "window": {
            "date_start": str(frame["date"].min()) if not frame.empty else None,
            "date_end": str(frame["date"].max()) if not frame.empty else None,
            "rows": int(len(frame)),
        },
        "split": {
            "n_splits": n_splits,
            "purge": purge,
            "min_train_size": min_train_size,
            "quantile": quantile,
            "min_pass_fraction": min_pass_fraction,
        },
        "summary": {
            "purged_walk_forward_policy_impact_passed": overall_passed,
            "best_score": max(by_score, key=lambda key: by_score[key]["pass_fraction"]) if by_score else None,
            "by_score": by_score,
        },
        "folds": rows,
        "decision": {
            "promotion_allowed": False,
            "decision": "shadow_only",
            "reason": "Purged walk-forward score separation is diagnostic only and does not retrain QUESTrader or change weights.",
        },
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2608.15841 Auxiliary Purged Walk-Forward",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Passed: `{report['summary']['purged_walk_forward_policy_impact_passed']}`",
        f"- Best score: `{report['summary']['best_score']}`",
        f"- Rows: `{report['window']['rows']}`",
        "",
        "## Summary",
        "",
        "| score | folds | pass count | pass fraction | passed |",
        "|---|---:|---:|---:|---:|",
    ]
    for score, item in report["summary"]["by_score"].items():
        lines.append(
            f"| `{score}` | {item['folds']} | {item['pass_count']} | {item['pass_fraction']:.3f} | `{item['passed']}` |"
        )
    lines.extend(["", "This report is shadow-only and does not alter live weights."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel-631l", default=str(DEFAULT_PANEL_631L))
    parser.add_argument("--panel-632r", default=str(DEFAULT_PANEL_632R))
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--purge", type=int, default=20)
    parser.add_argument("--min-train-size", type=int, default=120)
    parser.add_argument("--min-pass-fraction", type=float, default=0.75)
    parser.add_argument("--quantile", type=float, default=0.75)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(
        _resolve(args.panel_631l),
        _resolve(args.panel_632r),
        n_splits=args.n_splits,
        purge=args.purge,
        min_train_size=args.min_train_size,
        min_pass_fraction=args.min_pass_fraction,
        quantile=args.quantile,
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(
        "passed={passed} best={best}".format(
            passed=report["summary"]["purged_walk_forward_policy_impact_passed"],
            best=report["summary"]["best_score"],
        )
    )
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
