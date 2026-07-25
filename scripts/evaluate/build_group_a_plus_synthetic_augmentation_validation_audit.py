#!/usr/bin/env python3
"""Build a synthetic-augmentation validation audit from an OOS NCF panel.

This implements the size-matched null and block-permutation mechanics inspired
by arXiv 2604.14498. It is a validation audit only: it evaluates whether
existing rare-regime model scores beat a null distribution; it does not create
synthetic samples and never changes live weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PANEL = PROJECT_ROOT / "results/ncf_00631l_panel_latest_20260720.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/synthetic_augmentation_validation_audit.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/synthetic_augmentation_validation_audit/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _average_precision(y_true: np.ndarray, score: np.ndarray) -> float | None:
    y = np.asarray(y_true, dtype=int)
    s = np.asarray(score, dtype=float)
    mask = np.isfinite(s)
    y = y[mask]
    s = s[mask]
    positives = int(y.sum())
    if len(y) == 0 or positives == 0:
        return None
    order = np.argsort(-s, kind="mergesort")
    ranked_y = y[order]
    precision_at_k = np.cumsum(ranked_y) / (np.arange(len(ranked_y)) + 1)
    return float((precision_at_k * ranked_y).sum() / positives)


def _permute_in_blocks(values: np.ndarray, *, block_size: int, rng: np.random.Generator) -> np.ndarray:
    if block_size <= 1:
        out = values.copy()
        rng.shuffle(out)
        return out
    blocks = [values[i : i + block_size].copy() for i in range(0, len(values), block_size)]
    rng.shuffle(blocks)
    return np.concatenate(blocks)


def _task_audit(
    df: pd.DataFrame,
    *,
    task_name: str,
    score_col: str,
    label_col: str,
    n_permutations: int,
    block_size: int,
    rng: np.random.Generator,
) -> dict[str, Any]:
    data = df[[score_col, label_col]].dropna()
    y = data[label_col].to_numpy(dtype=int)
    score = data[score_col].to_numpy(dtype=float)
    observed = _average_precision(y, score)
    null_scores: list[float] = []
    if observed is not None and len(y) >= max(20, block_size * 4):
        for _ in range(n_permutations):
            shuffled = _permute_in_blocks(score, block_size=block_size, rng=rng)
            ap = _average_precision(y, shuffled)
            if ap is not None:
                null_scores.append(ap)
    null_arr = np.asarray(null_scores, dtype=float)
    null_mean = float(null_arr.mean()) if len(null_arr) else None
    null_p95 = float(np.quantile(null_arr, 0.95)) if len(null_arr) else None
    p_value = (
        float((1.0 + np.sum(null_arr >= float(observed))) / (len(null_arr) + 1.0))
        if observed is not None and len(null_arr)
        else None
    )
    lift_vs_null = float(observed - null_mean) if observed is not None and null_mean is not None else None
    passed = bool(
        observed is not None
        and null_mean is not None
        and p_value is not None
        and observed > null_p95
        and p_value <= 0.05
    )
    return {
        "task": task_name,
        "score_column": score_col,
        "label_column": label_col,
        "sample_size": int(len(data)),
        "positive_rate": float(y.mean()) if len(y) else None,
        "metric": "average_precision",
        "observed": observed,
        "size_matched_null_mean": null_mean,
        "size_matched_null_p95": null_p95,
        "lift_vs_null_mean": lift_vs_null,
        "block_permutation_p_value": p_value,
        "n_permutations": int(len(null_scores)),
        "block_size": block_size,
        "passed": passed,
    }


def build_audit(
    *,
    panel_path: Path,
    n_permutations: int = 500,
    block_size: int = 5,
    seed: int = 260414498,
    as_of: str | None = None,
) -> dict[str, Any]:
    df = pd.read_csv(panel_path, encoding="utf-8-sig")
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date")
    df = df[df.get("is_live", False) != True].copy()  # noqa: E712
    rng = np.random.default_rng(seed)
    tasks = [
        _task_audit(
            df,
            task_name="directional_up_ensemble",
            score_col="ensemble_prob_up",
            label_col="actual_up_h20" if "actual_up_h20" in df.columns else "actual_up_h1",
            n_permutations=n_permutations,
            block_size=block_size,
            rng=rng,
        )
        if ("actual_up_h20" in df.columns or "actual_up_h1" in df.columns)
        else {
            "task": "directional_up_ensemble",
            "score_column": "ensemble_prob_up",
            "label_column": None,
            "sample_size": 0,
            "metric": "average_precision",
            "observed": None,
            "size_matched_null_mean": None,
            "size_matched_null_p95": None,
            "lift_vs_null_mean": None,
            "block_permutation_p_value": None,
            "n_permutations": 0,
            "block_size": block_size,
            "passed": False,
            "skipped_reason": "missing_actual_up_horizon_label",
        },
        _task_audit(
            df,
            task_name="rare_gain_h20",
            score_col="prob_fwd_gain_gt5_h20",
            label_col="actual_fwd_gain_gt5_h20",
            n_permutations=n_permutations,
            block_size=block_size,
            rng=rng,
        ),
        _task_audit(
            df,
            task_name="rare_mdd_h20",
            score_col="prob_fwd_mdd_gt5_h20",
            label_col="actual_fwd_mdd_gt5_h20",
            n_permutations=n_permutations,
            block_size=block_size,
            rng=rng,
        ),
    ]
    passed_tasks = [row["task"] for row in tasks if row["passed"]]
    rare_tasks = [row for row in tasks if str(row["task"]).startswith("rare_")]
    directional_tasks = [row for row in tasks if str(row["task"]).startswith("directional_")]
    rare_validation_passed = all(row["passed"] for row in rare_tasks)
    directional_validation_passed = all(row["passed"] for row in directional_tasks)
    validation_passed = rare_validation_passed and directional_validation_passed
    dates = df["date"].dropna() if "date" in df.columns else pd.Series(dtype="datetime64[ns]")
    panel_start = dates.min().date().isoformat() if len(dates) else None
    panel_end = dates.max().date().isoformat() if len(dates) else None
    report_as_of = as_of or panel_end or "2026-07-20"
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_synthetic_augmentation_validation_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_size_matched_null_block_permutation_no_weight_change",
        "status": "passed" if validation_passed else "failed",
        "as_of": report_as_of,
        "panel_path": str(panel_path),
        "panel_coverage": {
            "start": panel_start,
            "end": panel_end,
            "row_count": int(len(df)),
        },
        "method": {
            "size_matched_null_augmentation_implemented": True,
            "block_permutation_test_implemented": True,
            "walk_forward_oos_panel_used": True,
            "n_permutations_requested": n_permutations,
            "block_size": block_size,
            "seed": seed,
            "note": "Scores are tested against block-shuffled same-size null scores on OOS panel rows.",
        },
        "tasks": tasks,
        "summary": {
            "task_count": len(tasks),
            "passed_task_count": len(passed_tasks),
            "passed_tasks": passed_tasks,
            "validation_passed": validation_passed,
            "rare_validation_passed": rare_validation_passed,
            "directional_validation_passed": directional_validation_passed,
            "directional_synthetic_alpha_tested": all("skipped_reason" not in row for row in directional_tasks),
            "directional_synthetic_alpha_reason": (
                "directional label tested against block-shuffled size-matched null"
                if all("skipped_reason" not in row for row in directional_tasks)
                else "panel lacks actual_up_horizon label; rerun NCF panel after actual_up_h* export"
            ),
        },
        "decision": {
            "synthetic_validation_passed": validation_passed,
            "directional_synthetic_alpha_allowed": directional_validation_passed,
            "synthetic_generator_promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"{stamp}.json"


def write_audit(audit: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, audit.get("as_of")).write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--n-permutations", type=int, default=500)
    parser.add_argument("--block-size", type=int, default=5)
    parser.add_argument("--seed", type=int, default=260414498)
    parser.add_argument("--as-of", default=None, help="Report date used for the latest/history stamp.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    audit = build_audit(
        panel_path=_resolve(args.panel),
        n_permutations=args.n_permutations,
        block_size=args.block_size,
        seed=args.seed,
        as_of=args.as_of,
    )
    history_dir = None if args.no_history else _resolve(args.history_dir)
    output = _resolve(args.output)
    write_audit(audit, output, history_dir)
    print(f"Synthetic augmentation validation audit: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, audit.get('as_of'))}")
    print(
        json.dumps(
            {
                "status": audit["status"],
                "validation_passed": audit["summary"]["validation_passed"],
                "passed_tasks": audit["summary"]["passed_tasks"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
