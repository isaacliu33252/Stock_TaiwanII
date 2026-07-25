#!/usr/bin/env python3
"""Audit frozen GIFT panel leakage controls and plan purged walk-forward folds.

This is a validation-design report only. It does not train models, output
actions, target weights, or live rebalance decisions.
"""

from __future__ import annotations

import argparse
import hashlib
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

from group_a_plus.validation.purged_walk_forward import PurgedWalkForwardSplit  # noqa: E402
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import (  # noqa: E402
    DEFAULT_PANEL_OUTPUT,
    DEFAULT_REVIEW_OUTPUT as DEFAULT_PANEL_REVIEW,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_frozen_panel_walk_forward_audit.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_frozen_panel_walk_forward_audit/history"
DEFAULT_FORWARD_HORIZON = 5


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _load_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    panel = pd.read_parquet(path)
    if "date" in panel.columns:
        panel["date"] = pd.to_datetime(panel["date"])
    return panel.sort_values(["date", "ticker"]).reset_index(drop=True)


def _column_finite_ratio(panel: pd.DataFrame, columns: list[str]) -> dict[str, float | None]:
    ratios: dict[str, float | None] = {}
    for column in columns:
        if column not in panel.columns or panel.empty:
            ratios[column] = None
            continue
        numeric = pd.to_numeric(panel[column], errors="coerce")
        ratios[column] = float(np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan)).sum() / len(panel))
    return ratios


def _fold_plan(
    dates: pd.Series,
    *,
    n_splits: int,
    test_size: int | None,
    train_size: int | None,
    purge: int,
    min_train_size: int,
) -> list[dict[str, Any]]:
    unique_dates = pd.Series(pd.to_datetime(dates).drop_duplicates().sort_values().to_list())
    splitter = PurgedWalkForwardSplit(
        n_splits=n_splits,
        test_size=test_size,
        train_size=train_size,
        purge=purge,
        min_train_size=min_train_size,
    )
    rows: list[dict[str, Any]] = []
    for fold, (train_idx, test_idx) in enumerate(splitter.split(unique_dates), start=1):
        train_dates = unique_dates.iloc[train_idx]
        test_dates = unique_dates.iloc[test_idx]
        rows.append(
            {
                "fold": fold,
                "train_start": train_dates.min().date().isoformat(),
                "train_end": train_dates.max().date().isoformat(),
                "test_start": test_dates.min().date().isoformat(),
                "test_end": test_dates.max().date().isoformat(),
                "train_days": int(len(train_dates)),
                "test_days": int(len(test_dates)),
                "purge_days": int((test_dates.min() - train_dates.max()).days),
                "purge_observations": int(test_idx[0] - train_idx[-1] - 1),
            }
        )
    return rows


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    panel_review_path: Path = DEFAULT_PANEL_REVIEW,
    n_splits: int = 6,
    test_size: int = 126,
    train_size: int | None = None,
    purge: int = DEFAULT_FORWARD_HORIZON,
    min_train_size: int = 756,
    forward_horizon: int = DEFAULT_FORWARD_HORIZON,
    min_finite_ratio: float = 0.95,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    panel_review = _load_json(panel_review_path)
    panel = _load_panel(panel_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if not panel_review:
        blockers.append("missing_frozen_panel_review")
    elif panel_review.get("status") != "available_for_manual_offline_review":
        blockers.append(f"frozen_panel_review_not_available:{panel_review.get('status')}")
    if not panel_path.exists():
        blockers.append("missing_frozen_panel")
    if panel.empty:
        blockers.append("empty_frozen_panel")

    expected_hash = (panel_review.get("outputs") or {}).get("panel_sha256") if panel_review else None
    actual_hash = _sha256_file(panel_path)
    if expected_hash and actual_hash and expected_hash != actual_hash:
        blockers.append("frozen_panel_hash_mismatch")

    required_columns = [
        "date",
        "ticker",
        "close",
        "return",
        "freeze_id",
        "frozen_manifest_sha256",
        "proposal_id",
        "reward_proxy",
    ]
    state_columns = (panel_review.get("summary") or {}).get("state_columns") if panel_review else []
    reward_columns = (panel_review.get("summary") or {}).get("reward_columns") if panel_review else []
    required_columns.extend([str(column) for column in state_columns or []])
    required_columns.extend([str(column) for column in reward_columns or []])
    missing_columns = [column for column in sorted(set(required_columns)) if column not in panel.columns]
    if missing_columns:
        blockers.append(f"missing_required_columns:{','.join(missing_columns)}")

    duplicate_key_count = 0
    if {"date", "ticker"}.issubset(panel.columns):
        duplicate_key_count = int(panel.duplicated(["date", "ticker"]).sum())
        if duplicate_key_count:
            blockers.append(f"duplicate_date_ticker_rows:{duplicate_key_count}")

    freeze_hash_count = int(panel["frozen_manifest_sha256"].nunique()) if "frozen_manifest_sha256" in panel.columns else 0
    if freeze_hash_count != 1 and not panel.empty:
        blockers.append(f"non_unique_frozen_manifest_hash:{freeze_hash_count}")

    if "reward_proxy" in panel.columns and len(panel):
        reward = pd.to_numeric(panel["reward_proxy"], errors="coerce")
        if reward.min() < -0.25 or reward.max() > 0.0:
            blockers.append("reward_proxy_not_bounded")

    finite_ratios = _column_finite_ratio(panel, sorted(set([*(state_columns or []), *(reward_columns or [])])))
    low_finite = {
        column: ratio
        for column, ratio in finite_ratios.items()
        if ratio is not None and ratio < min_finite_ratio
    }
    for column, ratio in low_finite.items():
        warnings.append(f"low_finite_ratio:{column}:{ratio:.4f}")

    folds: list[dict[str, Any]] = []
    split_error: str | None = None
    if "date" in panel.columns and not panel.empty:
        try:
            folds = _fold_plan(
                panel["date"],
                n_splits=n_splits,
                test_size=test_size,
                train_size=train_size,
                purge=purge,
                min_train_size=min_train_size,
            )
        except ValueError as exc:
            split_error = str(exc)
            blockers.append(f"purged_walk_forward_split_error:{split_error}")

    if purge < forward_horizon:
        blockers.append(f"purge_less_than_forward_horizon:{purge}<{forward_horizon}")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_frozen_panel_walk_forward_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "leakage_audit_and_walk_forward_plan_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_review": str(panel_review_path),
            "expected_panel_sha256": expected_hash,
            "actual_panel_sha256": actual_hash,
            "n_splits": n_splits,
            "test_size": test_size,
            "train_size": train_size,
            "purge": purge,
            "min_train_size": min_train_size,
            "forward_horizon": forward_horizon,
            "min_finite_ratio": min_finite_ratio,
        },
        "summary": {
            "row_count": int(len(panel)),
            "ticker_count": int(panel["ticker"].nunique()) if "ticker" in panel.columns else 0,
            "date_count": int(panel["date"].nunique()) if "date" in panel.columns else 0,
            "date_start": panel["date"].min().date().isoformat() if "date" in panel.columns and len(panel) else None,
            "date_end": panel["date"].max().date().isoformat() if "date" in panel.columns and len(panel) else None,
            "duplicate_date_ticker_rows": duplicate_key_count,
            "frozen_manifest_hash_count": freeze_hash_count,
            "finite_ratios": finite_ratios,
            "low_finite_columns": low_finite,
            "fold_count": len(folds),
            "purge_covers_forward_horizon": purge >= forward_horizon,
        },
        "folds": folds,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "The split plan uses unique trading dates, then maps each fold to all tickers on those dates.",
            "The purge gap must be at least the forward label horizon before any OOS shadow experiment.",
            "This audit prepares validation design only and does not permit PPO training.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "frozen_panel_leakage_audit_passed": not blockers,
            "purged_walk_forward_plan_ready": not blockers,
            "model_training_allowed": False,
            "ppo_training_allowed": False,
            "outputs_actions": False,
            "outputs_target_weights": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"llm_state_reward_interface_frozen_panel_walk_forward_audit_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL_OUTPUT))
    parser.add_argument("--panel-review", default=str(DEFAULT_PANEL_REVIEW))
    parser.add_argument("--n-splits", type=int, default=6)
    parser.add_argument("--test-size", type=int, default=126)
    parser.add_argument("--train-size", type=int, default=None)
    parser.add_argument("--purge", type=int, default=DEFAULT_FORWARD_HORIZON)
    parser.add_argument("--min-train-size", type=int, default=756)
    parser.add_argument("--forward-horizon", type=int, default=DEFAULT_FORWARD_HORIZON)
    parser.add_argument("--min-finite-ratio", type=float, default=0.95)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        panel_review_path=_resolve(args.panel_review),
        n_splits=args.n_splits,
        test_size=args.test_size,
        train_size=args.train_size,
        purge=args.purge,
        min_train_size=args.min_train_size,
        forward_horizon=args.forward_horizon,
        min_finite_ratio=args.min_finite_ratio,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward frozen panel walk-forward audit: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "row_count": review["summary"]["row_count"],
                "date_count": review["summary"]["date_count"],
                "fold_count": review["summary"]["fold_count"],
                "purge_covers_forward_horizon": review["summary"]["purge_covers_forward_horizon"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
