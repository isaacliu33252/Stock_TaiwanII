#!/usr/bin/env python3
"""Evaluate 2410.00288-inspired volatility no-add gates for NCF00631L.

Research-only. Uses point-in-time volatility features as an abstention/no-add
gate only on NCF-bullish 00631L rows. It evaluates whether gated rows have
worse forward H20 outcomes than non-gated bullish rows under purged
walk-forward thresholds. It never changes live weights, manifests, golden
artifacts, or orders.
"""

from __future__ import annotations

import argparse
import importlib.util
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

BASE_SCRIPT = PROJECT_ROOT / "scripts/evaluate/evaluate_group_a_plus_2410_00288_ginn_ncf00631l_shadow.py"
DEFAULT_PANEL = PROJECT_ROOT / "results/ncf_00631l_panel_latest_20260907.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2410_00288_ginn_no_add_gate.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2410_00288_ginn_no_add_gate.md"


def _load_base_module():
    spec = importlib.util.spec_from_file_location("ginn_ncf00631l_shadow", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()

GATE_SPECS: dict[str, dict[str, Any]] = {
    "realized_var_20_top25": {"feature": "realized_var_20", "direction": "high", "quantile": 0.75},
    "realized_vol_ratio_20_60_top25": {"feature": "realized_vol_ratio_20_60", "direction": "high", "quantile": 0.75},
    "ewma_var_94_top25": {"feature": "ewma_var_94", "direction": "high", "quantile": 0.75},
    "vol_cluster_score_top25": {"feature": "vol_cluster_score", "direction": "high", "quantile": 0.75},
    "garch_sym_var_top25": {"feature": "garch_sym_var", "direction": "high", "quantile": 0.75},
    "garch_gjr_var_top25": {"feature": "garch_gjr_var", "direction": "high", "quantile": 0.75},
    "garch_disagreement_top25": {"feature": "garch_disagreement_abs_log", "direction": "high", "quantile": 0.75},
    "garch_gjr_over_sym_bottom25": {"feature": "garch_gjr_over_sym", "direction": "low", "quantile": 0.25},
    "realized_var_20_top25_and_negative_5d": {
        "feature": "realized_var_20",
        "direction": "high",
        "quantile": 0.75,
        "extra": "return_5d_negative",
    },
    "vol_cluster_top25_and_negative_5d": {
        "feature": "vol_cluster_score",
        "direction": "high",
        "quantile": 0.75,
        "extra": "return_5d_negative",
    },
    "garch_sym_top25_and_negative_5d": {
        "feature": "garch_sym_var",
        "direction": "high",
        "quantile": 0.75,
        "extra": "return_5d_negative",
    },
    "garch_gjr_top25_and_negative_5d": {
        "feature": "garch_gjr_var",
        "direction": "high",
        "quantile": 0.75,
        "extra": "return_5d_negative",
    },
    "garch_disagreement_top25_and_negative_1d": {
        "feature": "garch_disagreement_abs_log",
        "direction": "high",
        "quantile": 0.75,
        "extra": "return_1d_negative",
    },
    "realized_var_20_top25_and_weak_ncf": {
        "feature": "realized_var_20",
        "direction": "high",
        "quantile": 0.75,
        "extra": "weak_ncf_bull",
    },
    "garch_sym_top25_and_weak_ncf": {
        "feature": "garch_sym_var",
        "direction": "high",
        "quantile": 0.75,
        "extra": "weak_ncf_bull",
    },
}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _first_existing(frame: pd.DataFrame, *cols: str) -> str | None:
    for col in cols:
        if col in frame.columns:
            return col
    return None


def _load_gate_frame(panel_path: Path, db_path: Path, ticker: str) -> tuple[pd.DataFrame, pd.Series]:
    frame, returns = BASE._load_model_frame(panel_path, db_path, ticker)
    gain_col = _first_existing(frame, "forward_gain_h20")
    mdd_col = _first_existing(frame, "forward_mdd_h20")
    mdd_event_col = _first_existing(frame, "actual_fwd_mdd_gt5_h20")
    required = [
        "target_up_h20",
        "baseline_prob_up_h20",
        "confidence",
        "realized_var_20",
        "realized_vol_ratio_20_60",
        "ewma_var_94",
        "vol_cluster_score",
    ]
    if gain_col is None or mdd_col is None or mdd_event_col is None:
        raise ValueError("panel is missing forward_gain_h20/forward_mdd_h20/actual_fwd_mdd_gt5_h20")
    frame["forward_gain_h20_eval"] = pd.to_numeric(frame[gain_col], errors="coerce")
    frame["forward_mdd_h20_eval"] = pd.to_numeric(frame[mdd_col], errors="coerce")
    frame["mdd_gt5_h20_eval"] = pd.to_numeric(frame[mdd_event_col], errors="coerce")
    frame["confidence"] = pd.to_numeric(frame["confidence"], errors="coerce")
    frame["return_5d"] = pd.to_numeric(frame.get("return_5d"), errors="coerce")
    frame = frame.dropna(subset=required + ["forward_gain_h20_eval", "forward_mdd_h20_eval", "mdd_gt5_h20_eval"])
    return frame, returns


def _threshold(train: pd.DataFrame, feature: str, direction: str, quantile: float) -> float:
    values = pd.to_numeric(train[feature], errors="coerce").dropna()
    if values.empty:
        return float("nan")
    return float(values.quantile(quantile))


def _apply_gate(frame: pd.DataFrame, feature: str, direction: str, threshold: float) -> pd.Series:
    values = pd.to_numeric(frame[feature], errors="coerce")
    if direction == "high":
        return values >= threshold
    return values <= threshold


def _extra_mask(frame: pd.DataFrame, extra: str | None, bullish_prob_min: float) -> pd.Series:
    if extra is None:
        return pd.Series(True, index=frame.index)
    if extra == "return_5d_negative":
        if "return_5d" not in frame.columns:
            return pd.Series(False, index=frame.index)
        return pd.to_numeric(frame["return_5d"], errors="coerce").fillna(0.0) < 0.0
    if extra == "return_1d_negative":
        if "return_1d" not in frame.columns:
            return pd.Series(False, index=frame.index)
        return pd.to_numeric(frame["return_1d"], errors="coerce").fillna(0.0) < 0.0
    if extra == "weak_ncf_bull":
        upper = min(0.65, bullish_prob_min + 0.10)
        prob = pd.to_numeric(frame["baseline_prob_up_h20"], errors="coerce")
        return (prob >= bullish_prob_min) & (prob <= upper)
    raise ValueError(f"unknown extra gate condition: {extra}")


def _bucket_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "rows": 0,
            "mean_forward_gain_h20": None,
            "mean_forward_mdd_h20": None,
            "mdd_gt5_rate_h20": None,
            "negative_gain_rate_h20": None,
        }
    gain = pd.to_numeric(frame["forward_gain_h20_eval"], errors="coerce")
    mdd = pd.to_numeric(frame["forward_mdd_h20_eval"], errors="coerce")
    mdd_event = pd.to_numeric(frame["mdd_gt5_h20_eval"], errors="coerce")
    return {
        "rows": int(len(frame)),
        "mean_forward_gain_h20": float(gain.mean()),
        "mean_forward_mdd_h20": float(mdd.mean()),
        "mdd_gt5_rate_h20": float(mdd_event.mean()),
        "negative_gain_rate_h20": float((gain < 0.0).mean()),
    }


def _delta(blocked: dict[str, Any], allowed: dict[str, Any]) -> dict[str, Any]:
    def diff(key: str) -> float | None:
        if blocked.get(key) is None or allowed.get(key) is None:
            return None
        return float(blocked[key] - allowed[key])

    return {
        "blocked_minus_allowed_mean_gain": diff("mean_forward_gain_h20"),
        "blocked_minus_allowed_mean_mdd": diff("mean_forward_mdd_h20"),
        "blocked_minus_allowed_mdd_gt5_rate": diff("mdd_gt5_rate_h20"),
        "blocked_minus_allowed_negative_gain_rate": diff("negative_gain_rate_h20"),
    }


def _fold_pass(delta: dict[str, Any], min_blocked_rows: int, blocked_rows: int, allowed_rows: int) -> bool:
    if blocked_rows < min_blocked_rows or allowed_rows < min_blocked_rows:
        return False
    gain = delta.get("blocked_minus_allowed_mean_gain")
    mdd = delta.get("blocked_minus_allowed_mean_mdd")
    mdd_event = delta.get("blocked_minus_allowed_mdd_gt5_rate")
    return bool(gain is not None and mdd is not None and mdd_event is not None and gain < 0.0 and mdd < 0.0 and mdd_event > 0.0)


def evaluate_no_add_gate(
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
) -> dict[str, Any]:
    frame, returns = _load_gate_frame(panel_path, db_path, ticker)
    splitter = PurgedWalkForwardSplit(n_splits=n_splits, purge=purge, min_train_size=min_train_size)
    folds = list(splitter.split(frame))
    gate_rows: dict[str, list[dict[str, Any]]] = {name: [] for name in GATE_SPECS}

    for fold_id, (train_idx, test_idx) in enumerate(folds, start=1):
        train = frame.iloc[train_idx].copy()
        test = frame.iloc[test_idx].copy()
        train_end = train.index.max()
        garch = BASE._fit_fold_garch_features(returns.loc[:train_end].tail(756), returns.reindex(frame.index).fillna(0.0))
        train = train.join(garch, how="left", rsuffix="_garch")
        test = test.join(garch, how="left", rsuffix="_garch")
        train_bullish = train[
            (train["baseline_prob_up_h20"] >= bullish_prob_min)
            & (train["confidence"] >= confidence_min)
        ]
        test_bullish = test[
            (test["baseline_prob_up_h20"] >= bullish_prob_min)
            & (test["confidence"] >= confidence_min)
        ]
        for name, spec in GATE_SPECS.items():
            feature = str(spec["feature"])
            direction = str(spec["direction"])
            quantile = float(spec["quantile"])
            extra = spec.get("extra")
            if feature not in train_bullish.columns or feature not in test_bullish.columns:
                row = {
                    "fold": fold_id,
                    "status": "skipped",
                    "reason": f"missing_feature:{feature}",
                }
                gate_rows[name].append(row)
                continue
            threshold = _threshold(train_bullish, feature, direction, quantile)
            if not np.isfinite(threshold) or test_bullish.empty:
                row = {
                    "fold": fold_id,
                    "status": "skipped",
                    "reason": "empty_train_threshold_or_test_bullish",
                    "test_bullish_rows": int(len(test_bullish)),
                }
                gate_rows[name].append(row)
                continue
            gated_mask = (
                _apply_gate(test_bullish, feature, direction, threshold).fillna(False)
                & _extra_mask(test_bullish, extra, bullish_prob_min).fillna(False)
            )
            blocked = test_bullish[gated_mask]
            allowed = test_bullish[~gated_mask]
            blocked_metrics = _bucket_metrics(blocked)
            allowed_metrics = _bucket_metrics(allowed)
            delta = _delta(blocked_metrics, allowed_metrics)
            row = {
                "fold": fold_id,
                "status": "ok",
                "test_start": str(test.index.min().date()),
                "test_end": str(test.index.max().date()),
                "feature": feature,
                "direction": direction,
                "extra": extra,
                "train_threshold": threshold,
                "train_bullish_rows": int(len(train_bullish)),
                "test_bullish_rows": int(len(test_bullish)),
                "blocked": blocked_metrics,
                "allowed": allowed_metrics,
                "delta_blocked_minus_allowed": delta,
                "pass": _fold_pass(delta, min_blocked_rows, blocked_metrics["rows"], allowed_metrics["rows"]),
            }
            gate_rows[name].append(row)

    summaries: dict[str, Any] = {}
    for name, rows in gate_rows.items():
        ok = [row for row in rows if row.get("status") == "ok"]
        pass_count = sum(bool(row.get("pass")) for row in ok)
        total_blocked_rows = sum(int((row.get("blocked") or {}).get("rows") or 0) for row in ok)
        total_allowed_rows = sum(int((row.get("allowed") or {}).get("rows") or 0) for row in ok)
        blocked_all = pd.DataFrame([row.get("blocked", {}) for row in ok])
        allowed_all = pd.DataFrame([row.get("allowed", {}) for row in ok])
        summaries[name] = {
            "ok_folds": int(len(ok)),
            "pass_count": int(pass_count),
            "pass_fraction": float(pass_count / len(ok)) if ok else 0.0,
            "total_blocked_rows": int(total_blocked_rows),
            "total_allowed_rows": int(total_allowed_rows),
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
        "report_type": "group_a_plus_2410_00288_ginn_no_add_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2410.00288",
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "inputs": {
            "panel": str(panel_path),
            "db_path": str(db_path),
            "ticker": ticker,
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
        "gate_summaries": summaries,
        "ranking": ranking,
        "decision": {
            "promotion_allowed": False,
            "decision": "do_not_promote_keep_shadow",
            "best_gate": best,
            "strict_no_add_gate_passed": strict_pass,
            "reason": (
                "A no-add gate must identify NCF-bullish rows with lower future gain, worse MDD, "
                "and higher MDD>5% event rate in at least 3/4 purged folds before candidate promotion."
            ),
        },
        "folds_by_gate": gate_rows,
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
        "# 2410.00288 Volatility No-Add Gate",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']['decision']}`",
        f"- Best gate: `{report['decision']['best_gate']}`",
        f"- Strict no-add gate passed: `{report['decision']['strict_no_add_gate_passed']}`",
        f"- Window: `{report['window']['date_start']}` to `{report['window']['date_end']}` rows=`{report['window']['rows']}`",
        "",
        "## Gate Summary",
        "",
        "| gate | ok folds | pass | blocked rows | allowed rows | blocked gain | allowed gain | blocked mdd>5 | allowed mdd>5 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in report["ranking"]:
        item = report["gate_summaries"][name]
        lines.append(
            f"| {name} | {item['ok_folds']} | {item['pass_count']}/{item['ok_folds']} | "
            f"{item['total_blocked_rows']} | {item['total_allowed_rows']} | "
            f"{_fmt(item['avg_blocked_mean_gain'])} | {_fmt(item['avg_allowed_mean_gain'])} | "
            f"{_fmt(item['avg_blocked_mdd_gt5_rate'])} | {_fmt(item['avg_allowed_mdd_gt5_rate'])} |"
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "此 no-add gate 評估仍是 shadow-only。若 gate 不能穩定找出 NCF 看多但後續 H20 較差的樣本，就不能導入 groupA++ 最新策略。",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ticker", default="00631L.TW")
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--purge", type=int, default=20)
    parser.add_argument("--min-train-size", type=int, default=160)
    parser.add_argument("--bullish-prob-min", type=float, default=0.55)
    parser.add_argument("--confidence-min", type=float, default=0.10)
    parser.add_argument("--min-blocked-rows", type=int, default=5)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = evaluate_no_add_gate(
        _resolve(args.panel),
        _resolve(args.db),
        ticker=args.ticker,
        n_splits=args.n_splits,
        purge=args.purge,
        min_train_size=args.min_train_size,
        bullish_prob_min=args.bullish_prob_min,
        confidence_min=args.confidence_min,
        min_blocked_rows=args.min_blocked_rows,
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(f"best_gate={report['decision']['best_gate']}")
    print(f"strict_no_add_gate_passed={report['decision']['strict_no_add_gate_passed']}")
    print(f"promotion_allowed={report['decision']['promotion_allowed']}")
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
