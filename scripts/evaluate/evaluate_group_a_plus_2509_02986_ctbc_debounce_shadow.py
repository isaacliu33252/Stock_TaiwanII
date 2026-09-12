#!/usr/bin/env python3
"""Evaluate CTBC-inspired sliding-window event debounce for GroupA++.

Research-only follow-up for arXiv:2509.02986. The paper is a robotics control
paper, so this script tests only its transferable trigger concept: require a
candidate no-add event to persist in a short window before it can fire.

It never changes live weights, golden artifacts, strategy manifests, NCF gates,
or order generation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.validation import PurgedWalkForwardSplit  # noqa: E402
from scripts.evaluate import evaluate_group_a_plus_2410_00288_ginn_no_add_gate as base_no_add  # noqa: E402


DEFAULT_PANEL = PROJECT_ROOT / "results/ncf_00631l_panel_latest_20260907.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_debounce_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_debounce_shadow.md"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _confirm(mask: pd.Series, *, mode: str) -> pd.Series:
    raw = mask.fillna(False).astype(bool)
    if mode == "raw":
        return raw
    if mode == "2of3":
        return raw.rolling(3, min_periods=3).sum().fillna(0).astype(int) >= 2
    if mode == "3of3":
        return raw.rolling(3, min_periods=3).sum().fillna(0).astype(int) >= 3
    raise ValueError(f"unknown confirmation mode: {mode}")


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [row for row in rows if row.get("status") == "ok"]
    pass_count = sum(bool(row.get("pass")) for row in ok)
    blocked_all = pd.DataFrame([row.get("blocked", {}) for row in ok])
    allowed_all = pd.DataFrame([row.get("allowed", {}) for row in ok])
    return {
        "ok_folds": int(len(ok)),
        "pass_count": int(pass_count),
        "pass_fraction": float(pass_count / len(ok)) if ok else 0.0,
        "total_blocked_rows": int(sum(int((row.get("blocked") or {}).get("rows") or 0) for row in ok)),
        "total_allowed_rows": int(sum(int((row.get("allowed") or {}).get("rows") or 0) for row in ok)),
        "avg_blocked_mean_gain": None
        if blocked_all.empty
        else float(pd.to_numeric(blocked_all["mean_forward_gain_h20"], errors="coerce").mean()),
        "avg_allowed_mean_gain": None
        if allowed_all.empty
        else float(pd.to_numeric(allowed_all["mean_forward_gain_h20"], errors="coerce").mean()),
        "avg_blocked_mdd_gt5_rate": None
        if blocked_all.empty
        else float(pd.to_numeric(blocked_all["mdd_gt5_rate_h20"], errors="coerce").mean()),
        "avg_allowed_mdd_gt5_rate": None
        if allowed_all.empty
        else float(pd.to_numeric(allowed_all["mdd_gt5_rate_h20"], errors="coerce").mean()),
    }


def evaluate_debounce_shadow(
    panel_path: Path,
    db_path: Path,
    *,
    ticker: str,
    n_splits: int,
    purge: int,
    min_train_size: int,
    bullish_prob_min: float,
    confidence_min: float,
    min_blocked_rows: int,
    gate_names: tuple[str, ...],
) -> dict[str, Any]:
    frame, returns = base_no_add._load_gate_frame(panel_path, db_path, ticker)
    splitter = PurgedWalkForwardSplit(n_splits=n_splits, purge=purge, min_train_size=min_train_size)
    folds = list(splitter.split(frame))
    modes = ("raw", "2of3", "3of3")
    rows_by_candidate: dict[str, list[dict[str, Any]]] = {
        f"{gate_name}_{mode}": [] for gate_name in gate_names for mode in modes
    }

    for fold_id, (train_idx, test_idx) in enumerate(folds, start=1):
        train = frame.iloc[train_idx].copy()
        test = frame.iloc[test_idx].copy()
        train_end = train.index.max()
        garch = base_no_add.BASE._fit_fold_garch_features(
            returns.loc[:train_end].tail(756),
            returns.reindex(frame.index).fillna(0.0),
        )
        train = train.join(garch, how="left", rsuffix="_garch")
        test = test.join(garch, how="left", rsuffix="_garch")
        train_bullish = train[
            (train["baseline_prob_up_h20"] >= bullish_prob_min)
            & (train["confidence"] >= confidence_min)
        ]
        test_bullish_mask = (
            (test["baseline_prob_up_h20"] >= bullish_prob_min)
            & (test["confidence"] >= confidence_min)
        )
        test_bullish = test[test_bullish_mask]

        for gate_name in gate_names:
            spec = base_no_add.GATE_SPECS[gate_name]
            feature = str(spec["feature"])
            direction = str(spec["direction"])
            quantile = float(spec["quantile"])
            extra = spec.get("extra")
            if feature not in train_bullish.columns or feature not in test.columns:
                for mode in modes:
                    rows_by_candidate[f"{gate_name}_{mode}"].append(
                        {"fold": fold_id, "status": "skipped", "reason": f"missing_feature:{feature}"}
                    )
                continue
            threshold = base_no_add._threshold(train_bullish, feature, direction, quantile)
            if not np.isfinite(threshold) or test_bullish.empty:
                for mode in modes:
                    rows_by_candidate[f"{gate_name}_{mode}"].append(
                        {
                            "fold": fold_id,
                            "status": "skipped",
                            "reason": "empty_train_threshold_or_test_bullish",
                            "test_bullish_rows": int(len(test_bullish)),
                        }
                    )
                continue

            raw_mask_all = (
                base_no_add._apply_gate(test, feature, direction, threshold).fillna(False)
                & base_no_add._extra_mask(test, extra, bullish_prob_min).fillna(False)
            )
            for mode in modes:
                confirmed_all = _confirm(raw_mask_all, mode=mode)
                gated_mask = confirmed_all.reindex(test_bullish.index, fill_value=False)
                blocked = test_bullish[gated_mask]
                allowed = test_bullish[~gated_mask]
                blocked_metrics = base_no_add._bucket_metrics(blocked)
                allowed_metrics = base_no_add._bucket_metrics(allowed)
                delta = base_no_add._delta(blocked_metrics, allowed_metrics)
                rows_by_candidate[f"{gate_name}_{mode}"].append(
                    {
                        "fold": fold_id,
                        "status": "ok",
                        "test_start": str(test.index.min().date()),
                        "test_end": str(test.index.max().date()),
                        "gate": gate_name,
                        "confirmation": mode,
                        "feature": feature,
                        "direction": direction,
                        "extra": extra,
                        "train_threshold": threshold,
                        "train_bullish_rows": int(len(train_bullish)),
                        "test_bullish_rows": int(len(test_bullish)),
                        "raw_trigger_days_in_test": int(raw_mask_all.sum()),
                        "confirmed_trigger_days_in_test": int(confirmed_all.sum()),
                        "blocked": blocked_metrics,
                        "allowed": allowed_metrics,
                        "delta_blocked_minus_allowed": delta,
                        "pass": base_no_add._fold_pass(
                            delta,
                            min_blocked_rows,
                            blocked_metrics["rows"],
                            allowed_metrics["rows"],
                        ),
                    }
                )

    summaries = {name: _summarize_rows(rows) for name, rows in rows_by_candidate.items()}
    ranking = sorted(
        summaries,
        key=lambda key: (
            summaries[key]["pass_fraction"],
            summaries[key]["total_blocked_rows"],
            -(summaries[key]["avg_blocked_mean_gain"] or 0.0),
        ),
        reverse=True,
    )
    best = ranking[0] if ranking else None
    best_summary = summaries.get(best or "", {})
    strict_pass = bool(
        best_summary
        and best_summary.get("pass_count", 0) >= 3
        and best_summary.get("total_blocked_rows", 0) >= min_blocked_rows * 3
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2509_02986_ctbc_debounce_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "id": "2509.02986",
            "title": "CTBC: Contact-Triggered Blind Climbing for Wheeled Bipedal Robots with Instruction Learning and Reinforcement Learning",
            "transferred_idea": "sliding_window_trigger_debounce",
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "changes_ncf_live_gate": False,
        "inputs": {
            "panel": str(panel_path),
            "db_path": str(db_path),
            "ticker": ticker,
            "gate_names": list(gate_names),
            "confirmation_modes": list(modes),
            "bullish_prob_min": bullish_prob_min,
            "confidence_min": confidence_min,
            "min_blocked_rows": min_blocked_rows,
        },
        "window": {
            "date_start": str(frame.index.min().date()) if not frame.empty else None,
            "date_end": str(frame.index.max().date()) if not frame.empty else None,
            "rows": int(len(frame)),
            "non_live_only": True,
        },
        "split": {
            "n_splits": n_splits,
            "purge": purge,
            "min_train_size": min_train_size,
        },
        "candidate_summaries": summaries,
        "ranking": ranking,
        "decision": {
            "promotion_allowed": False,
            "decision": "do_not_promote_keep_shadow",
            "best_candidate": best,
            "strict_debounce_gate_passed": strict_pass,
            "reason": (
                "CTBC debounce can be promoted only if a confirmed event identifies NCF-bullish rows "
                "with lower H20 gain, worse drawdown, and higher MDD>5% rate in at least 3/4 purged folds."
            ),
        },
        "folds_by_candidate": rows_by_candidate,
    }


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "NA"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "NA"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2509.02986 CTBC Debounce Shadow",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']['decision']}`",
        f"- Best candidate: `{report['decision']['best_candidate']}`",
        f"- Strict debounce gate passed: `{report['decision']['strict_debounce_gate_passed']}`",
        f"- Window: `{report['window']['date_start']}` to `{report['window']['date_end']}` rows=`{report['window']['rows']}`",
        "",
        "## Candidate Summary",
        "",
        "| candidate | ok folds | pass | blocked rows | allowed rows | blocked gain | allowed gain | blocked mdd>5 | allowed mdd>5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in report["ranking"]:
        item = report["candidate_summaries"][name]
        lines.append(
            f"| `{name}` | {item['ok_folds']} | {item['pass_count']}/{item['ok_folds']} | "
            f"{item['total_blocked_rows']} | {item['total_allowed_rows']} | "
            f"{_fmt(item['avg_blocked_mean_gain'])} | {_fmt(item['avg_allowed_mean_gain'])} | "
            f"{_fmt(item['avg_blocked_mdd_gt5_rate'])} | {_fmt(item['avg_allowed_mdd_gt5_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "CTBC 的 sliding-window trigger 概念目前只保留為 shadow。若不能穩定改善 00631L no-add 分辨力，就不能導入 groupA++ 最新策略。",
            "",
            "This report does not emit trades, target weights, NCF gates, or order-generation changes.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_gates(raw: str) -> tuple[str, ...]:
    gates = tuple(item.strip() for item in raw.split(",") if item.strip())
    unknown = [gate for gate in gates if gate not in base_no_add.GATE_SPECS]
    if unknown:
        raise ValueError(f"unknown gate names: {unknown}")
    return gates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ticker", default="00631L.TW")
    parser.add_argument(
        "--gates",
        default="realized_var_20_top25_and_weak_ncf,realized_var_20_top25,garch_gjr_top25_and_negative_5d,garch_disagreement_top25_and_negative_1d",
    )
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--purge", type=int, default=20)
    parser.add_argument("--min-train-size", type=int, default=160)
    parser.add_argument("--bullish-prob-min", type=float, default=0.55)
    parser.add_argument("--confidence-min", type=float, default=0.10)
    parser.add_argument("--min-blocked-rows", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = evaluate_debounce_shadow(
        _resolve(args.panel),
        _resolve(args.db),
        ticker=args.ticker,
        n_splits=args.n_splits,
        purge=args.purge,
        min_train_size=args.min_train_size,
        bullish_prob_min=args.bullish_prob_min,
        confidence_min=args.confidence_min,
        min_blocked_rows=args.min_blocked_rows,
        gate_names=_parse_gates(args.gates),
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = _json_safe(report)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(f"best_candidate={report['decision']['best_candidate']}")
    print(f"strict_debounce_gate_passed={report['decision']['strict_debounce_gate_passed']}")
    print(f"promotion_allowed={report['decision']['promotion_allowed']}")
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
