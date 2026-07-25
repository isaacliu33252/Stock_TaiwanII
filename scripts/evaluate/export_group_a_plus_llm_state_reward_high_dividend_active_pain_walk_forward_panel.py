#!/usr/bin/env python3
"""Export the v3 high-dividend active-pain walk-forward panel."""

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

from scripts.evaluate.backtest_group_a_plus_llm_state_reward_frozen_panel_baseline_shadow import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_BASELINE,
    _finite_float,
    _load_panel,
    _sha256_file,
    _weights_from_signal,
)
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_risk_control_overlay_shadow import HIGH_DIVIDEND_BUCKET  # noqa: E402
from scripts.evaluate.build_group_a_plus_llm_state_reward_high_dividend_active_pain_frozen_manifest import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_V3_MANIFEST,
    PROPOSAL_ID,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import _load_json, _resolve  # noqa: E402
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402


DEFAULT_PANEL_OUTPUT_V3 = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel.parquet"
DEFAULT_REVIEW_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel/history"


def _positive_hhi(active_weight: pd.Series) -> float:
    positive = pd.to_numeric(active_weight, errors="coerce").fillna(0.0).clip(lower=0.0)
    total = float(positive.sum())
    if total <= 0:
        return 0.0
    share = positive / total
    return float((share**2).sum())


def _redesigned_row(
    signal: pd.Series,
    current_return: pd.Series,
    lag_return: pd.Series,
    lag_drawdown: pd.Series,
    *,
    eligible_tickers: list[str],
    original_low_threshold: float,
    original_high_threshold: float,
    low_score: float,
    mid_score: float,
    high_score: float,
    active_penalty_scale: float,
    drawdown_scale: float,
    return_pain_scale: float,
    concentration_scale: float,
) -> tuple[pd.Series, dict[str, Any]]:
    signal = pd.to_numeric(signal.reindex(eligible_tickers), errors="coerce")
    raw_weight = _weights_from_signal(
        signal,
        low_threshold=original_low_threshold,
        high_threshold=original_high_threshold,
        low_score=low_score,
        mid_score=mid_score,
        high_score=high_score,
    )
    equal = pd.Series(1.0 / len(eligible_tickers), index=eligible_tickers, dtype=float)
    active = raw_weight - equal
    high_dividend = [ticker for ticker in HIGH_DIVIDEND_BUCKET if ticker in eligible_tickers]
    hd_active = active.reindex(high_dividend).fillna(0.0)
    hd_return = pd.to_numeric(current_return.reindex(high_dividend), errors="coerce").fillna(0.0)
    hd_active_contribution = float((hd_active * hd_return).sum())
    positive_hd = hd_active.clip(lower=0.0)
    positive_hd_sum = max(float(hd_active.sum()), 0.0)
    lag_hd_return = float(pd.to_numeric(lag_return.reindex(high_dividend), errors="coerce").fillna(0.0).mean())
    lag_hd_drawdown = float(pd.to_numeric(lag_drawdown.reindex(high_dividend), errors="coerce").fillna(0.0).mean())
    hhi = _positive_hhi(active)
    pain = positive_hd_sum * (
        drawdown_scale * max(lag_hd_drawdown, 0.0)
        + return_pain_scale * max(-lag_hd_return, 0.0)
        + concentration_scale * hhi
    )
    penalty = active_penalty_scale * pain
    redesigned = signal.copy()
    if penalty > 0 and high_dividend:
        if float(positive_hd.sum()) > 0:
            allocation = positive_hd / float(positive_hd.sum()) * penalty
        else:
            allocation = pd.Series(penalty / len(high_dividend), index=high_dividend, dtype=float)
        redesigned.loc[allocation.index] = redesigned.loc[allocation.index] - allocation
    diagnostics = {
        "active_bucket_weight": float(hd_active.sum()),
        "active_bucket_return_contribution": hd_active_contribution,
        "active_bucket_drawdown_depth": positive_hd_sum * max(lag_hd_drawdown, 0.0),
        "reward_signal_concentration_hhi": hhi,
        "high_dividend_active_pain": pain,
        "active_bucket_drawdown_penalty": penalty,
    }
    return redesigned, diagnostics


def build_panel(
    *,
    frozen_panel_path: Path = DEFAULT_PANEL_OUTPUT,
    baseline_path: Path = DEFAULT_BASELINE,
    manifest_path: Path = DEFAULT_V3_MANIFEST,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    panel = _load_panel(frozen_panel_path)
    baseline = _load_json(baseline_path)
    manifest = _load_json(manifest_path)
    blockers: list[str] = []
    if panel.empty:
        blockers.append("missing_or_empty_frozen_panel")
    if not baseline:
        blockers.append("missing_baseline_shadow_backtest")
    elif baseline.get("status") != "available_for_manual_offline_review":
        blockers.append(f"baseline_shadow_backtest_not_available:{baseline.get('status')}")
    if not manifest:
        blockers.append("missing_v3_frozen_manifest")
    elif manifest.get("status") != "frozen_for_manual_offline_review":
        blockers.append(f"v3_frozen_manifest_not_available:{manifest.get('status')}")
    if (manifest.get("decision") or {}).get("offline_walk_forward_panel_export_allowed") is not True:
        blockers.append("offline_walk_forward_panel_export_not_allowed")
    freeze = manifest.get("freeze") if isinstance(manifest.get("freeze"), dict) else {}
    if freeze.get("proposal_id") != PROPOSAL_ID:
        blockers.append("proposal_id_mismatch")
    expected_hash = (baseline.get("inputs") or {}).get("panel_sha256") if baseline else None
    actual_hash = _sha256_file(frozen_panel_path)
    if expected_hash and actual_hash and expected_hash != actual_hash:
        blockers.append("source_frozen_panel_hash_mismatch")

    inputs = baseline.get("inputs", {}) if baseline else {}
    eligible_tickers = list(inputs.get("eligible_tickers") or [])
    folds = baseline.get("fold_results") if isinstance(baseline.get("fold_results"), list) else []
    params = freeze.get("reward_params") or {}
    rows: list[pd.DataFrame] = []
    if not blockers:
        eligible = panel[panel["ticker"].isin(eligible_tickers)].copy()
        reward_wide = eligible.pivot(index="date", columns="ticker", values="reward_proxy").sort_index().reindex(columns=eligible_tickers)
        return_wide = eligible.pivot(index="date", columns="ticker", values="return").sort_index().reindex(columns=eligible_tickers)
        drawdown_wide = eligible.pivot(index="date", columns="ticker", values="drawdown_depth").sort_index().reindex(columns=eligible_tickers)
        lag_reward = reward_wide.shift(1)
        lag_return = return_wide.shift(1)
        lag_drawdown = drawdown_wide.shift(1)
        for fold in folds:
            train = eligible[
                (eligible["date"] >= pd.Timestamp(fold["train_start"]))
                & (eligible["date"] <= pd.Timestamp(fold["train_end"]))
            ]
            train_reward = pd.to_numeric(train["reward_proxy"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            if train_reward.empty:
                blockers.append(f"empty_train_reward:{fold.get('fold')}")
                continue
            original_low = float(train_reward.quantile(float(inputs.get("low_quantile", 0.30))))
            original_high = float(train_reward.quantile(float(inputs.get("high_quantile", 0.70))))
            test_dates = return_wide.loc[fold["test_start"] : fold["test_end"]].index
            date_frames: list[pd.DataFrame] = []
            for dt in test_dates:
                redesigned, diag = _redesigned_row(
                    lag_reward.loc[dt],
                    return_wide.loc[dt],
                    lag_return.loc[dt],
                    lag_drawdown.loc[dt],
                    eligible_tickers=eligible_tickers,
                    original_low_threshold=original_low,
                    original_high_threshold=original_high,
                    low_score=float(inputs.get("low_score", 0.50)),
                    mid_score=float(inputs.get("mid_score", 1.00)),
                    high_score=float(inputs.get("high_score", 1.50)),
                    active_penalty_scale=float(params.get("active_penalty_scale", 20.0)),
                    drawdown_scale=float(params.get("drawdown_scale", 1.0)),
                    return_pain_scale=float(params.get("return_pain_scale", 4.0)),
                    concentration_scale=float(params.get("concentration_scale", 0.1)),
                )
                day = eligible[eligible["date"] == dt].copy()
                day["fold"] = int(fold["fold"])
                day["train_start"] = fold["train_start"]
                day["train_end"] = fold["train_end"]
                day["test_start"] = fold["test_start"]
                day["test_end"] = fold["test_end"]
                day["original_low_reward_threshold"] = original_low
                day["original_high_reward_threshold"] = original_high
                day["original_reward_proxy"] = day["ticker"].map(lag_reward.loc[dt].to_dict())
                day["redesigned_reward_proxy"] = day["ticker"].map(redesigned.to_dict())
                for key, value in diag.items():
                    day[key] = value
                day["freeze_id"] = freeze.get("freeze_id")
                day["frozen_manifest_sha256"] = freeze.get("frozen_manifest_sha256")
                day["proposal_id"] = freeze.get("proposal_id")
                date_frames.append(day)
            if date_frames:
                rows.append(pd.concat(date_frames, ignore_index=True))
    out = pd.concat(rows, ignore_index=True).sort_values(["fold", "date", "ticker"]) if rows else pd.DataFrame()
    finite_ratio = None
    if not out.empty:
        finite_ratio = float(pd.to_numeric(out["redesigned_reward_proxy"], errors="coerce").replace([np.inf, -np.inf], np.nan).notna().mean())
    review = {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": manifest.get("as_of") or "2026-07-21",
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "fold_aware_v3_panel_only_no_model_training_no_live_action",
        "inputs": {
            "source_frozen_panel": str(frozen_panel_path),
            "source_frozen_panel_sha256": actual_hash,
            "baseline_shadow_backtest": str(baseline_path),
            "v3_frozen_manifest": str(manifest_path),
            "eligible_tickers": eligible_tickers,
            "reward_params": params,
        },
        "summary": {
            "row_count": int(len(out)),
            "fold_count": int(out["fold"].nunique()) if "fold" in out.columns and len(out) else 0,
            "ticker_count": int(out["ticker"].nunique()) if "ticker" in out.columns and len(out) else 0,
            "date_start": out["date"].min().date().isoformat() if "date" in out.columns and len(out) else None,
            "date_end": out["date"].max().date().isoformat() if "date" in out.columns and len(out) else None,
            "finite_redesigned_reward_ratio": _finite_float(finite_ratio),
            "state_columns": freeze.get("state_columns"),
            "reward_columns": freeze.get("reward_columns"),
        },
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "offline_walk_forward_input_ready": not blockers,
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
    return out, review


def write_outputs(panel: pd.DataFrame, review: dict[str, Any], *, panel_output: Path, review_output: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> dict[str, Any]:
    panel_output.parent.mkdir(parents=True, exist_ok=True)
    review_output.parent.mkdir(parents=True, exist_ok=True)
    if not panel.empty:
        panel.to_parquet(panel_output, index=False)
    review = dict(review)
    review["outputs"] = {"panel": str(panel_output), "panel_sha256": _sha256_file(panel_output), "review": str(review_output)}
    review_output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = str(review.get("as_of") or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
        (history_dir / f"llm_state_reward_interface_high_dividend_active_pain_walk_forward_panel_review_{stamp}.json").write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return review


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-panel", default=str(DEFAULT_PANEL_OUTPUT))
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--manifest", default=str(DEFAULT_V3_MANIFEST))
    parser.add_argument("--panel-output", default=str(DEFAULT_PANEL_OUTPUT_V3))
    parser.add_argument("--review-output", default=str(DEFAULT_REVIEW_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()
    panel, review = build_panel(
        frozen_panel_path=_resolve(args.frozen_panel),
        baseline_path=_resolve(args.baseline),
        manifest_path=_resolve(args.manifest),
    )
    review = write_outputs(
        panel,
        review,
        panel_output=_resolve(args.panel_output),
        review_output=_resolve(args.review_output),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"LLM state-reward high-dividend active-pain walk-forward panel review: {_resolve(args.review_output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "row_count": review["summary"]["row_count"],
                "fold_count": review["summary"]["fold_count"],
                "panel_sha256": review["outputs"]["panel_sha256"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
