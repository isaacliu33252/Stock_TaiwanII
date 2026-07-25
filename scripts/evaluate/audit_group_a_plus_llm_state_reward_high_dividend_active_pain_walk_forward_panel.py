#!/usr/bin/env python3
"""Audit the v3 high-dividend active-pain walk-forward panel."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LATEST = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_PANEL = LATEST / "llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel.parquet"
DEFAULT_PANEL_REVIEW = LATEST / "llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_review.json"
DEFAULT_OUTPUT = LATEST / "llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_audit.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_audit/history"
PROPOSAL_ID = "gift_research_high_dividend_active_pain_v1"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    panel = pd.read_parquet(path)
    if "date" in panel.columns:
        panel["date"] = pd.to_datetime(panel["date"])
    for col in ["train_start", "train_end", "test_start", "test_end"]:
        if col in panel.columns:
            panel[col] = pd.to_datetime(panel[col])
    return panel.sort_values(["fold", "date", "ticker"]).reset_index(drop=True)


def _finite_ratio(frame: pd.DataFrame, column: str) -> float | None:
    if column not in frame.columns or frame.empty:
        return None
    numeric = pd.to_numeric(frame[column], errors="coerce")
    return float(np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan)).sum() / len(frame))


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL,
    panel_review_path: Path = DEFAULT_PANEL_REVIEW,
    min_finite_ratio: float = 0.95,
    forward_horizon: int = 5,
    as_of: str = "2026-07-21",
) -> dict[str, Any]:
    review = _load(panel_review_path)
    panel = _load_panel(panel_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if not review:
        blockers.append("missing_v3_panel_review")
    elif review.get("status") != "available_for_manual_offline_review":
        blockers.append(f"v3_panel_review_not_available:{review.get('status')}")
    if not panel_path.exists():
        blockers.append("missing_v3_panel")
    if panel.empty:
        blockers.append("empty_v3_panel")

    expected_hash = (review.get("outputs") or {}).get("panel_sha256") if review else None
    actual_hash = _sha256_file(panel_path)
    if expected_hash and actual_hash and expected_hash != actual_hash:
        blockers.append("v3_panel_hash_mismatch")

    required_columns = [
        "fold",
        "date",
        "ticker",
        "train_start",
        "train_end",
        "test_start",
        "test_end",
        "freeze_id",
        "frozen_manifest_sha256",
        "proposal_id",
        "return",
        "original_reward_proxy",
        "redesigned_reward_proxy",
        "active_bucket_weight",
        "active_bucket_return_contribution",
        "active_bucket_drawdown_depth",
        "reward_signal_concentration_hhi",
        "high_dividend_active_pain",
        "active_bucket_drawdown_penalty",
    ]
    missing = [col for col in required_columns if col not in panel.columns]
    if missing:
        blockers.append(f"missing_required_columns:{','.join(missing)}")

    duplicate_fold_date_ticker = 0
    if {"fold", "date", "ticker"}.issubset(panel.columns):
        duplicate_fold_date_ticker = int(panel.duplicated(["fold", "date", "ticker"]).sum())
        if duplicate_fold_date_ticker:
            blockers.append(f"duplicate_fold_date_ticker_rows:{duplicate_fold_date_ticker}")

    freeze_hash_count = int(panel["frozen_manifest_sha256"].nunique()) if "frozen_manifest_sha256" in panel.columns and len(panel) else 0
    freeze_id_count = int(panel["freeze_id"].nunique()) if "freeze_id" in panel.columns and len(panel) else 0
    proposal_ids = sorted(panel["proposal_id"].dropna().astype(str).unique().tolist()) if "proposal_id" in panel.columns else []
    if freeze_hash_count != 1 and len(panel):
        blockers.append(f"non_unique_frozen_manifest_hash:{freeze_hash_count}")
    if freeze_id_count != 1 and len(panel):
        blockers.append(f"non_unique_freeze_id:{freeze_id_count}")
    if proposal_ids != [PROPOSAL_ID] and len(panel):
        blockers.append(f"proposal_id_mismatch:{','.join(proposal_ids)}")

    finite_columns = [
        "original_reward_proxy",
        "redesigned_reward_proxy",
        "active_bucket_weight",
        "active_bucket_return_contribution",
        "active_bucket_drawdown_depth",
        "reward_signal_concentration_hhi",
        "high_dividend_active_pain",
        "active_bucket_drawdown_penalty",
    ]
    finite_ratios = {col: _finite_ratio(panel, col) for col in finite_columns}
    for col, ratio in finite_ratios.items():
        if ratio is not None and ratio < min_finite_ratio:
            warnings.append(f"low_finite_ratio:{col}:{ratio:.4f}")

    fold_rows: list[dict[str, Any]] = []
    if {"fold", "date", "ticker", "train_end", "test_start", "test_end"}.issubset(panel.columns):
        for fold, group in panel.groupby("fold"):
            dates = group["date"].drop_duplicates().sort_values()
            tickers = sorted(group["ticker"].dropna().astype(str).unique().tolist())
            expected_rows = int(len(dates) * len(tickers))
            actual_rows = int(len(group))
            train_end = pd.Timestamp(group["train_end"].iloc[0])
            test_start = pd.Timestamp(group["test_start"].iloc[0])
            test_end = pd.Timestamp(group["test_end"].iloc[0])
            min_date = pd.Timestamp(dates.min()) if len(dates) else None
            max_date = pd.Timestamp(dates.max()) if len(dates) else None
            purge_days = int((test_start - train_end).days)
            row = {
                "fold": int(fold),
                "rows": actual_rows,
                "expected_complete_rows": expected_rows,
                "complete_grid": actual_rows == expected_rows,
                "ticker_count": len(tickers),
                "date_count": int(len(dates)),
                "date_start": min_date.date().isoformat() if min_date is not None else None,
                "date_end": max_date.date().isoformat() if max_date is not None else None,
                "test_start": test_start.date().isoformat(),
                "test_end": test_end.date().isoformat(),
                "train_end": train_end.date().isoformat(),
                "purge_calendar_days": purge_days,
                "test_dates_match_panel_dates": bool(min_date == test_start and max_date == test_end),
            }
            if not row["complete_grid"]:
                blockers.append(f"fold_incomplete_grid:{fold}")
            if not row["test_dates_match_panel_dates"]:
                blockers.append(f"fold_test_date_mismatch:{fold}")
            if purge_days < forward_horizon:
                blockers.append(f"fold_purge_less_than_forward_horizon:{fold}:{purge_days}<{forward_horizon}")
            fold_rows.append(row)

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_audit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "v3_fold_aware_panel_audit_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_review": str(panel_review_path),
            "expected_panel_sha256": expected_hash,
            "actual_panel_sha256": actual_hash,
            "min_finite_ratio": min_finite_ratio,
            "forward_horizon": forward_horizon,
        },
        "summary": {
            "row_count": int(len(panel)),
            "fold_count": int(panel["fold"].nunique()) if "fold" in panel.columns and len(panel) else 0,
            "ticker_count": int(panel["ticker"].nunique()) if "ticker" in panel.columns and len(panel) else 0,
            "date_count": int(panel["date"].nunique()) if "date" in panel.columns and len(panel) else 0,
            "duplicate_fold_date_ticker_rows": duplicate_fold_date_ticker,
            "freeze_id_count": freeze_id_count,
            "frozen_manifest_hash_count": freeze_hash_count,
            "proposal_ids": proposal_ids,
            "finite_ratios": finite_ratios,
            "folds_complete": bool(fold_rows and all(row["complete_grid"] for row in fold_rows)),
            "folds_test_dates_match": bool(fold_rows and all(row["test_dates_match_panel_dates"] for row in fold_rows)),
            "purge_covers_forward_horizon": bool(fold_rows and all(row["purge_calendar_days"] >= forward_horizon for row in fold_rows)),
        },
        "folds": fold_rows,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "v3_walk_forward_panel_audit_passed": not blockers,
            "v3_shadow_gate_update_allowed": not blockers,
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
    return history_dir / f"llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_audit_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, review.get("as_of")).write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default="2026-07-21")
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--panel-review", default=str(DEFAULT_PANEL_REVIEW))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()
    review = build_review(
        panel_path=_resolve(args.panel),
        panel_review_path=_resolve(args.panel_review),
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward high-dividend active-pain walk-forward panel audit: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "row_count": review["summary"]["row_count"],
                "fold_count": review["summary"]["fold_count"],
                "v3_shadow_gate_update_allowed": review["decision"]["v3_shadow_gate_update_allowed"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
