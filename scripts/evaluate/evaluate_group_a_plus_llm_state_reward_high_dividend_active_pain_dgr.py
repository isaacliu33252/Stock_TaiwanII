#!/usr/bin/env python3
"""DGR diagnostic for the high-dividend active-pain GIFT redesign.

This evaluates whether a redesigned reward proxy penalizes high-dividend active
overweight before future high-dividend active pain. It uses frozen-panel OOS
folds only, does not train models, and does not output live target weights.
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

from scripts.evaluate.backtest_group_a_plus_llm_state_reward_frozen_panel_baseline_shadow import (  # noqa: E402
    DEFAULT_EXCLUDED_TICKERS,
    DEFAULT_OUTPUT as DEFAULT_BASELINE,
    _finite_float,
    _load_panel,
    _sha256_file,
    _weights_from_signal,
)
from scripts.evaluate.backtest_group_a_plus_llm_state_reward_risk_control_overlay_shadow import HIGH_DIVIDEND_BUCKET  # noqa: E402
from scripts.evaluate.build_group_a_plus_llm_state_reward_high_dividend_active_pain_redesign_review import (  # noqa: E402
    DEFAULT_OUTPUT as DEFAULT_REDESIGN_REVIEW,
    PROPOSAL_ID,
)
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import _load_json, _resolve  # noqa: E402
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_high_dividend_active_pain_dgr_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_high_dividend_active_pain_dgr/history"
DEFAULT_FORWARD_HORIZON = 5


def _safe_corr(left: pd.Series, right: pd.Series, *, min_rows: int) -> float | None:
    pair = pd.concat(
        [pd.to_numeric(left, errors="coerce"), pd.to_numeric(right, errors="coerce")],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if len(pair) < min_rows:
        return None
    if pair.iloc[:, 0].std(ddof=0) <= 0 or pair.iloc[:, 1].std(ddof=0) <= 0:
        return None
    return _finite_float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))


def _mean(values: list[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and np.isfinite(float(value))]
    return _finite_float(np.mean(finite)) if finite else None


def _reward_snr(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return None
    std = float(clean.std(ddof=0))
    if std <= 0:
        return None
    return _finite_float(abs(float(clean.mean())) / std)


def _grade_alignment(alignment: float | None) -> dict[str, Any]:
    if alignment is None:
        return {
            "grade": "unavailable",
            "risk_sensitive_useful": False,
            "ppo_training_queue_allowed": False,
            "reason": "future_high_dividend_active_pain_alignment_unavailable",
        }
    if alignment <= -0.05:
        return {
            "grade": "green",
            "risk_sensitive_useful": True,
            "ppo_training_queue_allowed": True,
            "reason": "reward_declines_before_future_high_dividend_active_pain",
        }
    if alignment <= -0.02:
        return {
            "grade": "yellow",
            "risk_sensitive_useful": True,
            "ppo_training_queue_allowed": False,
            "reason": "weak_negative_alignment_requires_manual_review",
        }
    return {
        "grade": "red",
        "risk_sensitive_useful": False,
        "ppo_training_queue_allowed": False,
        "reason": "reward_does_not_penalize_future_high_dividend_active_pain_enough",
    }


def _bucket_mean(frame: pd.DataFrame, columns: list[str], row_date: pd.Timestamp) -> float:
    row = frame.reindex(columns=columns).loc[row_date]
    return float(pd.to_numeric(row, errors="coerce").fillna(0.0).mean())


def _fold_frame(
    panel: pd.DataFrame,
    fold: dict[str, Any],
    *,
    eligible_tickers: list[str],
    low_quantile: float,
    high_quantile: float,
    low_score: float,
    mid_score: float,
    high_score: float,
    active_penalty_scale: float,
    drawdown_scale: float,
    return_pain_scale: float,
    concentration_scale: float,
    forward_horizon: int,
) -> pd.DataFrame:
    train = panel[
        (panel["date"] >= pd.Timestamp(fold["train_start"]))
        & (panel["date"] <= pd.Timestamp(fold["train_end"]))
        & (panel["ticker"].isin(eligible_tickers))
    ]
    test = panel[
        (panel["date"] >= pd.Timestamp(fold["test_start"]))
        & (panel["date"] <= pd.Timestamp(fold["test_end"]))
        & (panel["ticker"].isin(eligible_tickers))
    ]
    train_reward = pd.to_numeric(train["reward_proxy"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if train_reward.empty or test.empty:
        return pd.DataFrame()

    low_threshold = float(train_reward.quantile(low_quantile))
    high_threshold = float(train_reward.quantile(high_quantile))
    all_eligible = panel[panel["ticker"].isin(eligible_tickers)]
    returns = test.pivot(index="date", columns="ticker", values="return").sort_index().reindex(columns=eligible_tickers)
    close = all_eligible.pivot(index="date", columns="ticker", values="close").sort_index().reindex(columns=eligible_tickers)
    reward_signal = (
        all_eligible.pivot(index="date", columns="ticker", values="reward_proxy")
        .sort_index()
        .shift(1)
        .reindex(returns.index)
        .reindex(columns=eligible_tickers)
    )
    drawdown = (
        all_eligible.pivot(index="date", columns="ticker", values="drawdown_depth")
        .sort_index()
        .shift(1)
        .reindex(returns.index)
        .reindex(columns=eligible_tickers)
    )
    volatility = (
        all_eligible.pivot(index="date", columns="ticker", values="realized_volatility")
        .sort_index()
        .shift(1)
        .reindex(returns.index)
        .reindex(columns=eligible_tickers)
    )
    lagged_returns = returns.shift(1).reindex(returns.index)
    equal_weight = pd.Series(1.0 / len(eligible_tickers), index=eligible_tickers, dtype=float)
    high_dividend = [ticker for ticker in HIGH_DIVIDEND_BUCKET if ticker in eligible_tickers]
    rows: list[dict[str, Any]] = []
    for dt, return_row in returns.iterrows():
        signal_row = reward_signal.loc[dt].reindex(eligible_tickers)
        weight = _weights_from_signal(
            signal_row,
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            low_score=low_score,
            mid_score=mid_score,
            high_score=high_score,
        )
        active_weight = weight - equal_weight
        high_dividend_active_weight = float(active_weight.reindex(high_dividend).fillna(0.0).sum())
        positive_hd_active_weight = max(high_dividend_active_weight, 0.0)
        active_return_contribution = active_weight * pd.to_numeric(return_row, errors="coerce").fillna(0.0)
        high_dividend_active_contribution = float(active_return_contribution.reindex(high_dividend).fillna(0.0).sum())
        lagged_hd_return = float(pd.to_numeric(lagged_returns.loc[dt].reindex(high_dividend), errors="coerce").fillna(0.0).mean())
        lagged_hd_drawdown = float(pd.to_numeric(drawdown.loc[dt].reindex(high_dividend), errors="coerce").fillna(0.0).mean())
        lagged_hd_vol = float(pd.to_numeric(volatility.loc[dt].reindex(high_dividend), errors="coerce").fillna(0.0).mean())
        positive_active = active_weight.clip(lower=0.0)
        active_total = float(positive_active.sum())
        concentration_hhi = float(((positive_active / active_total) ** 2).sum()) if active_total > 0 else 0.0
        high_dividend_active_pain = positive_hd_active_weight * (
            drawdown_scale * max(lagged_hd_drawdown, 0.0)
            + return_pain_scale * max(-lagged_hd_return, 0.0)
            + concentration_scale * concentration_hhi
        )
        active_bucket_drawdown_penalty = active_penalty_scale * high_dividend_active_pain
        base_portfolio_reward = float((weight * pd.to_numeric(signal_row, errors="coerce").fillna(0.0)).sum())
        redesigned_reward_proxy = base_portfolio_reward - active_bucket_drawdown_penalty

        future_date_idx = close.index.get_indexer([dt])[0] if dt in close.index else -1
        future_high_dividend_active_pain = np.nan
        if future_date_idx >= 0 and future_date_idx + forward_horizon < len(close.index):
            future_dt = close.index[future_date_idx + forward_horizon]
            current_close = close.loc[dt]
            future_close = close.loc[future_dt]
            future_returns = pd.to_numeric(future_close / current_close - 1.0, errors="coerce").replace([np.inf, -np.inf], np.nan)
            hd_future = float(future_returns.reindex(high_dividend).dropna().mean()) if high_dividend else np.nan
            all_future = float(future_returns.reindex(eligible_tickers).dropna().mean())
            future_hd_underperformance = all_future - hd_future
            future_high_dividend_active_pain = positive_hd_active_weight * max(future_hd_underperformance, 0.0)

        rows.append(
            {
                "fold": int(fold["fold"]),
                "date": pd.Timestamp(dt),
                "high_dividend_active_weight": high_dividend_active_weight,
                "high_dividend_positive_active_weight": positive_hd_active_weight,
                "active_bucket_return_contribution": high_dividend_active_contribution,
                "active_bucket_drawdown_depth": positive_hd_active_weight * max(lagged_hd_drawdown, 0.0),
                "reward_signal_concentration_hhi": concentration_hhi,
                "high_dividend_active_pain": high_dividend_active_pain,
                "active_bucket_drawdown_penalty": active_bucket_drawdown_penalty,
                "base_portfolio_reward": base_portfolio_reward,
                "redesigned_reward_proxy": redesigned_reward_proxy,
                "future_high_dividend_active_pain": future_high_dividend_active_pain,
            }
        )
    return pd.DataFrame(rows)


def _event_probe(rows: pd.DataFrame, event_date: str = "2024-08-05") -> dict[str, Any]:
    if rows.empty:
        return {}
    event = rows[rows["date"] == pd.Timestamp(event_date)]
    if event.empty:
        return {"event_date": event_date, "available": False}
    row = event.iloc[0]
    return {
        "event_date": event_date,
        "available": True,
        "fold": int(row["fold"]),
        "high_dividend_active_weight": _finite_float(row["high_dividend_active_weight"]),
        "high_dividend_active_pain": _finite_float(row["high_dividend_active_pain"]),
        "active_bucket_drawdown_penalty": _finite_float(row["active_bucket_drawdown_penalty"]),
        "base_portfolio_reward": _finite_float(row["base_portfolio_reward"]),
        "redesigned_reward_proxy": _finite_float(row["redesigned_reward_proxy"]),
        "reward_delta_vs_base": _finite_float(row["redesigned_reward_proxy"] - row["base_portfolio_reward"]),
        "future_high_dividend_active_pain": _finite_float(row["future_high_dividend_active_pain"]),
    }


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    baseline_path: Path = DEFAULT_BASELINE,
    redesign_review_path: Path = DEFAULT_REDESIGN_REVIEW,
    active_penalty_scale: float = 1.0,
    drawdown_scale: float = 1.0,
    return_pain_scale: float = 2.0,
    concentration_scale: float = 0.05,
    forward_horizon: int = DEFAULT_FORWARD_HORIZON,
    min_rows: int = 120,
    min_reward_finite_ratio: float = 0.95,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    panel = _load_panel(panel_path)
    baseline = _load_json(baseline_path)
    redesign = _load_json(redesign_review_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if panel.empty:
        blockers.append("missing_or_empty_frozen_panel")
    if not baseline:
        blockers.append("missing_baseline_shadow_backtest")
    elif baseline.get("status") != "available_for_manual_offline_review":
        blockers.append(f"baseline_shadow_backtest_not_available:{baseline.get('status')}")
    if not redesign:
        blockers.append("missing_high_dividend_active_pain_redesign_review")
    elif redesign.get("status") != "available_for_offline_dgr_design":
        blockers.append(f"redesign_review_not_available_for_dgr:{redesign.get('status')}")
    expected_hash = baseline.get("inputs", {}).get("panel_sha256") if baseline else None
    actual_hash = _sha256_file(panel_path)
    if expected_hash and actual_hash and expected_hash != actual_hash:
        blockers.append("frozen_panel_hash_mismatch")

    inputs = baseline.get("inputs", {}) if baseline else {}
    eligible_tickers = list(inputs.get("eligible_tickers") or [])
    if len(eligible_tickers) < 2:
        blockers.append("too_few_eligible_tickers")
    if {"00631L.TW", "00632R.TW"} & set(eligible_tickers):
        blockers.append("leveraged_or_inverse_ticker_not_excluded")
    folds = baseline.get("fold_results") if isinstance(baseline.get("fold_results"), list) else []
    if not folds:
        blockers.append("missing_baseline_folds")

    fold_frames = [
        _fold_frame(
            panel,
            fold,
            eligible_tickers=eligible_tickers,
            low_quantile=float(inputs.get("low_quantile", 0.30)),
            high_quantile=float(inputs.get("high_quantile", 0.70)),
            low_score=float(inputs.get("low_score", 0.50)),
            mid_score=float(inputs.get("mid_score", 1.00)),
            high_score=float(inputs.get("high_score", 1.50)),
            active_penalty_scale=active_penalty_scale,
            drawdown_scale=drawdown_scale,
            return_pain_scale=return_pain_scale,
            concentration_scale=concentration_scale,
            forward_horizon=forward_horizon,
        )
        for fold in folds
    ] if not blockers else []
    rows = pd.concat([frame for frame in fold_frames if not frame.empty], ignore_index=True) if fold_frames else pd.DataFrame()
    if rows.empty and not blockers:
        blockers.append("empty_dgr_frame")

    finite_ratio = None
    if not rows.empty:
        finite_ratio = float(
            pd.to_numeric(rows["redesigned_reward_proxy"], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .notna()
            .mean()
        )
        if finite_ratio < min_reward_finite_ratio:
            blockers.append(f"low_reward_finite_ratio:{finite_ratio:.4f}")

    alignment = (
        _safe_corr(rows["redesigned_reward_proxy"], rows["future_high_dividend_active_pain"], min_rows=min_rows)
        if not rows.empty
        else None
    )
    base_alignment = (
        _safe_corr(rows["base_portfolio_reward"], rows["future_high_dividend_active_pain"], min_rows=min_rows)
        if not rows.empty
        else None
    )
    pain_feature_alignment = (
        _safe_corr(rows["high_dividend_active_pain"], rows["future_high_dividend_active_pain"], min_rows=min_rows)
        if not rows.empty
        else None
    )
    gate = _grade_alignment(alignment)
    if gate["grade"] in {"red", "unavailable"}:
        warnings.append(f"high_dividend_active_pain_alignment_{gate['grade']}")

    reward_snr = _reward_snr(rows["redesigned_reward_proxy"]) if not rows.empty else None
    event_probe = _event_probe(rows)
    if event_probe.get("available") and (event_probe.get("reward_delta_vs_base") or 0.0) >= 0:
        warnings.append("event_probe_reward_not_penalized_vs_base")

    pass_dgr = bool(not blockers and gate["grade"] == "green" and gate["risk_sensitive_useful"])
    fold_summaries = []
    if not rows.empty:
        for fold, group in rows.groupby("fold"):
            fold_summaries.append(
                {
                    "fold": int(fold),
                    "rows": int(len(group)),
                    "alignment_to_future_high_dividend_active_pain": _safe_corr(
                        group["redesigned_reward_proxy"], group["future_high_dividend_active_pain"], min_rows=max(20, min_rows // 4)
                    ),
                    "mean_high_dividend_active_weight": _finite_float(group["high_dividend_active_weight"].mean()),
                    "mean_high_dividend_active_pain": _finite_float(group["high_dividend_active_pain"].mean()),
                    "mean_reward_delta_vs_base": _finite_float(
                        (group["redesigned_reward_proxy"] - group["base_portfolio_reward"]).mean()
                    ),
                }
            )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_high_dividend_active_pain_dgr_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "high_dividend_active_pain_dgr_only_no_model_training_no_live_action",
        "proposal_id": PROPOSAL_ID,
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "baseline_shadow_backtest": str(baseline_path),
            "redesign_review": str(redesign_review_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": list(inputs.get("excluded_tickers") or DEFAULT_EXCLUDED_TICKERS),
            "active_penalty_scale": active_penalty_scale,
            "drawdown_scale": drawdown_scale,
            "return_pain_scale": return_pain_scale,
            "concentration_scale": concentration_scale,
            "forward_horizon": forward_horizon,
        },
        "summary": {
            "row_count": int(len(rows)),
            "fold_count": int(rows["fold"].nunique()) if not rows.empty else 0,
            "finite_reward_ratio": _finite_float(finite_ratio),
            "reward_snr_abs_mean_over_std": reward_snr,
            "base_reward_alignment_to_future_high_dividend_active_pain": base_alignment,
            "redesigned_reward_alignment_to_future_high_dividend_active_pain": alignment,
            "high_dividend_active_pain_feature_alignment": pain_feature_alignment,
            "alignment_grade": gate["grade"],
            "risk_sensitive_useful": gate["risk_sensitive_useful"],
            "event_probe_2024_08_05": event_probe,
            "pass_high_dividend_active_pain_dgr": pass_dgr,
        },
        "fold_diagnostics": fold_summaries,
        "diagnostic_gate": gate,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "Negative redesigned reward alignment is useful: reward is lower before future high-dividend active pain.",
            "State features use prior-day reward signals, active exposure, drawdown, volatility, and concentration only.",
            "This diagnostic does not authorize PPO, live allocation, target weights, 00631L additions, or 00632R openings.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "high_dividend_active_pain_dgr_passed": pass_dgr,
            "offline_smoke_allowed_after_dgr_green": pass_dgr,
            "next_shadow_model_design_allowed": False,
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
    return history_dir / f"llm_state_reward_interface_high_dividend_active_pain_dgr_{stamp}.json"


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
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--redesign-review", default=str(DEFAULT_REDESIGN_REVIEW))
    parser.add_argument("--active-penalty-scale", type=float, default=1.0)
    parser.add_argument("--drawdown-scale", type=float, default=1.0)
    parser.add_argument("--return-pain-scale", type=float, default=2.0)
    parser.add_argument("--concentration-scale", type=float, default=0.05)
    parser.add_argument("--forward-horizon", type=int, default=DEFAULT_FORWARD_HORIZON)
    parser.add_argument("--min-rows", type=int, default=120)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        baseline_path=_resolve(args.baseline),
        redesign_review_path=_resolve(args.redesign_review),
        active_penalty_scale=args.active_penalty_scale,
        drawdown_scale=args.drawdown_scale,
        return_pain_scale=args.return_pain_scale,
        concentration_scale=args.concentration_scale,
        forward_horizon=args.forward_horizon,
        min_rows=args.min_rows,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward high-dividend active-pain DGR review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "alignment_grade": review["summary"]["alignment_grade"],
                "redesigned_alignment": review["summary"]["redesigned_reward_alignment_to_future_high_dividend_active_pain"],
                "pass_dgr": review["decision"]["high_dividend_active_pain_dgr_passed"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
