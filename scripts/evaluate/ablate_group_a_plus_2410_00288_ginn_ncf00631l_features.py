#!/usr/bin/env python3
"""Ablate 2410.00288 GARCH-informed volatility features for NCF00631L.

Research-only. Tests whether any individual volatility feature family improves
the existing NCF00631L H20 direction probability under purged walk-forward
validation. It never changes live weights, manifests, golden artifacts, or
orders.
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
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.validation import PurgedWalkForwardSplit  # noqa: E402

BASE_SCRIPT = PROJECT_ROOT / "scripts/evaluate/evaluate_group_a_plus_2410_00288_ginn_ncf00631l_shadow.py"
DEFAULT_PANEL = PROJECT_ROOT / "results/ncf_00631l_panel_latest_20260907.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2410_00288_ginn_ncf00631l_feature_ablation.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2410_00288_ginn_ncf00631l_feature_ablation.md"


def _load_base_module():
    spec = importlib.util.spec_from_file_location("ginn_ncf00631l_shadow", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()

FEATURE_SETS: dict[str, list[str]] = {
    "baseline_logit_only": ["baseline_logit_h20"],
    "realized_vol_only": [
        "baseline_logit_h20",
        "realized_var_5",
        "realized_var_20",
        "realized_var_60",
        "realized_vol_ratio_20_60",
        "ewma_var_94",
    ],
    "vol_cluster_only": [
        "baseline_logit_h20",
        "abs_return_1d",
        "neg_return_flag",
        "vol_cluster_score",
    ],
    "symmetric_garch_only": [
        "baseline_logit_h20",
        "garch_sym_var",
        "garch_sym_persistence",
    ],
    "gjr_asymmetry_only": [
        "baseline_logit_h20",
        "garch_gjr_var",
        "garch_gjr_over_sym",
        "garch_gjr_persistence",
        "garch_gjr_gamma",
        "garch_disagreement_abs_log",
        "neg_return_flag",
    ],
    "garch_all_only": [
        "baseline_logit_h20",
        "garch_sym_var",
        "garch_gjr_var",
        "garch_gjr_over_sym",
        "garch_sym_persistence",
        "garch_gjr_persistence",
        "garch_gjr_gamma",
        "garch_disagreement_abs_log",
    ],
    "all_volatility_families": [
        "baseline_logit_h20",
        "return_1d",
        "abs_return_1d",
        "neg_return_flag",
        "realized_var_5",
        "realized_var_20",
        "realized_var_60",
        "realized_vol_ratio_20_60",
        "ewma_var_94",
        "vol_cluster_score",
        "garch_sym_var",
        "garch_gjr_var",
        "garch_gjr_over_sym",
        "garch_sym_persistence",
        "garch_gjr_persistence",
        "garch_gjr_gamma",
        "garch_disagreement_abs_log",
    ],
}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _fit_predict(train: pd.DataFrame, test: pd.DataFrame, feature_cols: list[str]) -> np.ndarray | None:
    train = train.dropna(subset=feature_cols + ["target_up_h20"])
    test = test.dropna(subset=feature_cols + ["target_up_h20"])
    if train.empty or test.empty or train["target_up_h20"].nunique() < 2:
        return None
    scaler = StandardScaler()
    x_train = scaler.fit_transform(train[feature_cols].astype(float))
    x_test = scaler.transform(test[feature_cols].astype(float))
    y_train = train["target_up_h20"].to_numpy(dtype=int)
    model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=241000288)
    model.fit(x_train, y_train)
    return model.predict_proba(x_test)[:, 1]


def _mean_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [row[key] for row in rows if row.get(key) is not None]
    return float(np.mean(vals)) if vals else None


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    return {
        "accuracy": None if candidate.get("accuracy") is None else float(candidate["accuracy"] - baseline["accuracy"]),
        "auc": None
        if candidate.get("auc") is None or baseline.get("auc") is None
        else float(candidate["auc"] - baseline["auc"]),
        "brier": None if candidate.get("brier") is None else float(candidate["brier"] - baseline["brier"]),
    }


def _score_summary(summary: dict[str, Any]) -> tuple[float, float, float]:
    delta = summary["delta_vs_raw_ncf"]
    acc = float(delta["accuracy"] or 0.0)
    auc = float(delta["auc"] or 0.0)
    brier_improvement = -float(delta["brier"] or 0.0)
    return (acc, brier_improvement, auc)


def evaluate_ablation(
    panel_path: Path,
    db_path: Path,
    *,
    ticker: str,
    n_splits: int,
    purge: int,
    min_train_size: int,
) -> dict[str, Any]:
    frame, returns = BASE._load_model_frame(panel_path, db_path, ticker)
    needed_non_garch = sorted(
        {
            "target_up_h20",
            "baseline_prob_up_h20",
            *[
                col
                for cols in FEATURE_SETS.values()
                for col in cols
                if not col.startswith("garch_")
            ],
        }
    )
    valid = frame.dropna(subset=needed_non_garch).copy()
    valid["target_up_h20"] = (valid["target_up_h20"] > 0.0).astype(int)
    splitter = PurgedWalkForwardSplit(n_splits=n_splits, purge=purge, min_train_size=min_train_size)
    folds = list(splitter.split(valid))
    fold_rows: list[dict[str, Any]] = []
    by_set_fold_metrics: dict[str, list[dict[str, Any]]] = {name: [] for name in FEATURE_SETS}
    raw_baseline_metrics: list[dict[str, Any]] = []

    for fold_id, (train_idx, test_idx) in enumerate(folds, start=1):
        train = valid.iloc[train_idx].copy()
        test = valid.iloc[test_idx].copy()
        train_end = train.index.max()
        returns_to_fit = returns.loc[:train_end]
        garch_features = BASE._fit_fold_garch_features(returns_to_fit.tail(756), returns.reindex(valid.index).fillna(0.0))
        train = train.join(garch_features, how="left", rsuffix="_garch")
        test = test.join(garch_features, how="left", rsuffix="_garch")
        y_test = test["target_up_h20"].to_numpy(dtype=int)
        raw_prob = test["baseline_prob_up_h20"].to_numpy(dtype=float)
        raw_metric = BASE._metric_row(y_test, raw_prob)
        raw_baseline_metrics.append(raw_metric)
        fold_payload: dict[str, Any] = {
            "fold": fold_id,
            "train_start": str(train.index.min().date()),
            "train_end": str(train.index.max().date()),
            "test_start": str(test.index.min().date()),
            "test_end": str(test.index.max().date()),
            "train_rows": int(len(train)),
            "test_rows": int(len(test)),
            "raw_ncf": raw_metric,
            "feature_sets": {},
        }
        for name, cols in FEATURE_SETS.items():
            prob = _fit_predict(train, test, cols)
            if prob is None:
                row = {"status": "skipped", "reason": "empty_or_single_class_train"}
            else:
                metric = BASE._metric_row(y_test, prob)
                row = {
                    "status": "ok",
                    **metric,
                    "delta_vs_raw_ncf": _metric_delta(metric, raw_metric),
                }
                by_set_fold_metrics[name].append(row)
            fold_payload["feature_sets"][name] = row
        fold_rows.append(fold_payload)

    raw_summary = {
        "folds": len(raw_baseline_metrics),
        "accuracy": _mean_metric(raw_baseline_metrics, "accuracy"),
        "auc": _mean_metric(raw_baseline_metrics, "auc"),
        "brier": _mean_metric(raw_baseline_metrics, "brier"),
    }
    summaries: dict[str, Any] = {}
    for name, rows in by_set_fold_metrics.items():
        aggregate = {
            "folds": len(rows),
            "accuracy": _mean_metric(rows, "accuracy"),
            "auc": _mean_metric(rows, "auc"),
            "brier": _mean_metric(rows, "brier"),
        }
        delta = _metric_delta(aggregate, raw_summary) if rows else {"accuracy": None, "auc": None, "brier": None}
        acc_pass = sum((row["delta_vs_raw_ncf"].get("accuracy") or 0.0) > 0.0 for row in rows)
        auc_pass = sum((row["delta_vs_raw_ncf"].get("auc") or 0.0) > 0.0 for row in rows)
        brier_pass = sum((row["delta_vs_raw_ncf"].get("brier") or 0.0) < 0.0 for row in rows)
        summaries[name] = {
            **aggregate,
            "delta_vs_raw_ncf": delta,
            "fold_pass_counts": {
                "accuracy_improved": int(acc_pass),
                "auc_improved": int(auc_pass),
                "brier_improved": int(brier_pass),
                "ok_folds": int(len(rows)),
            },
        }
    ranked = sorted(summaries, key=lambda key: _score_summary(summaries[key]), reverse=True)
    best_name = ranked[0] if ranked else None
    best = summaries[best_name] if best_name else None
    strict_pass = bool(
        best
        and best["delta_vs_raw_ncf"].get("accuracy") is not None
        and best["delta_vs_raw_ncf"].get("brier") is not None
        and best["delta_vs_raw_ncf"]["accuracy"] > 0.0
        and best["delta_vs_raw_ncf"]["brier"] < 0.0
        and best["fold_pass_counts"]["accuracy_improved"] >= 3
        and best["fold_pass_counts"]["brier_improved"] >= 3
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2410_00288_ginn_ncf00631l_feature_ablation",
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
            "raw_baseline": "existing NCF00631L prob_up_h20",
        },
        "window": {
            "date_start": str(valid.index.min().date()) if not valid.empty else None,
            "date_end": str(valid.index.max().date()) if not valid.empty else None,
            "rows": int(len(valid)),
            "non_live_only": True,
        },
        "split": {
            "n_splits": n_splits,
            "purge": purge,
            "min_train_size": min_train_size,
        },
        "raw_ncf_summary": raw_summary,
        "feature_set_summaries": summaries,
        "ranking": ranked,
        "decision": {
            "promotion_allowed": False,
            "best_feature_set": best_name,
            "strict_shadow_metric_passed": strict_pass,
            "decision": "do_not_promote_keep_shadow",
            "reason": (
                "A feature family must improve accuracy and Brier in at least 3/4 purged folds "
                "before it can even move to candidate retraining. This report itself never changes live weights."
            ),
        },
        "folds": fold_rows,
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
        "# 2410.00288 NCF00631L Feature Ablation",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']['decision']}`",
        f"- Best feature set: `{report['decision']['best_feature_set']}`",
        f"- Strict shadow metric passed: `{report['decision']['strict_shadow_metric_passed']}`",
        f"- Window: `{report['window']['date_start']}` to `{report['window']['date_end']}` rows=`{report['window']['rows']}`",
        "",
        "## Summary",
        "",
        "| feature set | folds | acc | dAcc | auc | dAUC | brier | dBrier | acc+ | auc+ | brier+ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    raw = report["raw_ncf_summary"]
    lines.append(
        f"| raw_ncf_prob_up_h20 | {raw['folds']} | {_fmt(raw['accuracy'])} | 0.0000 | "
        f"{_fmt(raw['auc'])} | 0.0000 | {_fmt(raw['brier'])} | 0.0000 |  |  |  |"
    )
    for name in report["ranking"]:
        item = report["feature_set_summaries"][name]
        delta = item["delta_vs_raw_ncf"]
        counts = item["fold_pass_counts"]
        lines.append(
            f"| {name} | {item['folds']} | {_fmt(item['accuracy'])} | {_fmt(delta['accuracy'])} | "
            f"{_fmt(item['auc'])} | {_fmt(delta['auc'])} | {_fmt(item['brier'])} | {_fmt(delta['brier'])} | "
            f"{counts['accuracy_improved']}/{counts['ok_folds']} | "
            f"{counts['auc_improved']}/{counts['ok_folds']} | "
            f"{counts['brier_improved']}/{counts['ok_folds']} |"
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "本 ablation 只做 shadow 評估。若沒有同時改善 Acc 與 Brier 且跨 fold 穩定，不能導入 groupA++ 最新策略。",
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
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = evaluate_ablation(
        _resolve(args.panel),
        _resolve(args.db),
        ticker=args.ticker,
        n_splits=args.n_splits,
        purge=args.purge,
        min_train_size=args.min_train_size,
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(f"best={report['decision']['best_feature_set']}")
    print(f"strict_shadow_metric_passed={report['decision']['strict_shadow_metric_passed']}")
    print(f"promotion_allowed={report['decision']['promotion_allowed']}")
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
