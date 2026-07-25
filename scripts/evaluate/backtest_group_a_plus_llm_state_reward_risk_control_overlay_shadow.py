#!/usr/bin/env python3
"""Risk-control overlay shadow for frozen GroupA+ GIFT reward tilt.

The overlay caps single-name active weight, high-dividend bucket active weight,
bond bucket active weight, and daily turnover. It is transparent, no-model, and
does not output live target weights or rebalance decisions.
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
    _aggregate_folds,
    _finite_float,
    _load_panel,
    _metrics,
    _sha256_file,
    _weights_from_signal,
)
from scripts.evaluate.export_group_a_plus_llm_state_reward_frozen_panel import DEFAULT_PANEL_OUTPUT  # noqa: E402
from scripts.evaluate.evaluate_group_a_plus_llm_state_reward_interface_offline_smoke import (  # noqa: E402
    _load_json,
    _resolve,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/llm_state_reward_interface_risk_control_overlay_shadow_backtest.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/llm_state_reward_interface_risk_control_overlay_shadow_backtest/history"
HIGH_DIVIDEND_BUCKET = ["0056.TW", "00713.TW", "00878.TW"]
BOND_BUCKET = ["00679B.TWO", "00751B.TWO"]


def _normalize(weights: pd.Series) -> pd.Series:
    clean = pd.to_numeric(weights, errors="coerce").fillna(0.0).clip(lower=0.0)
    total = float(clean.sum())
    if total <= 0:
        return pd.Series(1.0 / len(clean), index=clean.index, dtype=float)
    return clean / total


def _apply_cap(weights: pd.Series, cap: pd.Series) -> pd.Series:
    out = _normalize(weights).copy()
    cap = cap.reindex(out.index).astype(float)
    for _ in range(20):
        over = out > cap + 1e-12
        if not bool(over.any()):
            break
        excess = float((out[over] - cap[over]).sum())
        out[over] = cap[over]
        room = (cap - out).clip(lower=0.0)
        room[over] = 0.0
        if room.sum() <= 1e-12:
            break
        out += room / room.sum() * excess
    return _normalize(out)


def _apply_bucket_cap(weights: pd.Series, bucket: list[str], cap_value: float) -> pd.Series:
    present = [ticker for ticker in bucket if ticker in weights.index]
    if not present:
        return _normalize(weights)
    out = _normalize(weights)
    bucket_weight = float(out[present].sum())
    if bucket_weight <= cap_value + 1e-12:
        return out
    scale = cap_value / bucket_weight if bucket_weight > 0 else 0.0
    excess = float(out[present].sum() - cap_value)
    out[present] = out[present] * scale
    others = [ticker for ticker in out.index if ticker not in present]
    if others and out[others].sum() > 0:
        out[others] = out[others] + out[others] / out[others].sum() * excess
    return _normalize(out)


def _apply_turnover_cap(weights: pd.Series, previous: pd.Series, max_turnover: float) -> pd.Series:
    turnover = float((weights - previous).abs().sum())
    if turnover <= max_turnover or turnover <= 1e-12:
        return _normalize(weights)
    blend = max_turnover / turnover
    return _normalize(previous + (weights - previous) * blend)


def _overlay_weight(
    raw_weight: pd.Series,
    previous_weight: pd.Series,
    *,
    single_name_active_cap: float,
    high_dividend_bucket_active_cap: float,
    bond_bucket_active_cap: float,
    max_daily_turnover: float,
) -> pd.Series:
    tickers = list(raw_weight.index)
    equal = pd.Series(1.0 / len(tickers), index=tickers, dtype=float)
    cap = equal + float(single_name_active_cap)
    capped = _apply_cap(raw_weight, cap)

    high_div_present = [ticker for ticker in HIGH_DIVIDEND_BUCKET if ticker in capped.index]
    if high_div_present:
        high_div_equal = float(equal[high_div_present].sum())
        capped = _apply_bucket_cap(capped, high_div_present, high_div_equal + high_dividend_bucket_active_cap)

    bond_present = [ticker for ticker in BOND_BUCKET if ticker in capped.index]
    if bond_present:
        bond_equal = float(equal[bond_present].sum())
        capped = _apply_bucket_cap(capped, bond_present, bond_equal + bond_bucket_active_cap)

    capped = _apply_cap(capped, cap)
    return _apply_turnover_cap(capped, previous_weight, max_daily_turnover)


def _fold_overlay_backtest(
    panel: pd.DataFrame,
    fold: dict[str, Any],
    *,
    eligible_tickers: list[str],
    low_quantile: float,
    high_quantile: float,
    low_score: float,
    mid_score: float,
    high_score: float,
    cost_bps: float,
    single_name_active_cap: float,
    high_dividend_bucket_active_cap: float,
    bond_bucket_active_cap: float,
    max_daily_turnover: float,
) -> dict[str, Any]:
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
        return {"fold": fold["fold"], "status": "blocked", "blocking_reason": "empty_train_reward_or_test_frame"}

    low_threshold = float(train_reward.quantile(low_quantile))
    high_threshold = float(train_reward.quantile(high_quantile))
    wide_returns = test.pivot(index="date", columns="ticker", values="return").sort_index().reindex(columns=eligible_tickers)
    wide_signal = (
        panel[panel["ticker"].isin(eligible_tickers)]
        .pivot(index="date", columns="ticker", values="reward_proxy")
        .sort_index()
        .shift(1)
        .reindex(wide_returns.index)
        .reindex(columns=eligible_tickers)
    )
    equal_weight = pd.Series(1.0 / len(eligible_tickers), index=eligible_tickers, dtype=float)
    previous_overlay = equal_weight.copy()
    overlay_returns: list[float] = []
    baseline_returns: list[float] = []
    turnovers: list[float] = []
    cost_rate = cost_bps / 10_000.0
    for dt, return_row in wide_returns.iterrows():
        usable_returns = pd.to_numeric(return_row, errors="coerce").fillna(0.0)
        raw_weight = _weights_from_signal(
            wide_signal.loc[dt],
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            low_score=low_score,
            mid_score=mid_score,
            high_score=high_score,
        )
        overlay = _overlay_weight(
            raw_weight,
            previous_overlay,
            single_name_active_cap=single_name_active_cap,
            high_dividend_bucket_active_cap=high_dividend_bucket_active_cap,
            bond_bucket_active_cap=bond_bucket_active_cap,
            max_daily_turnover=max_daily_turnover,
        )
        turnover = float((overlay - previous_overlay).abs().sum())
        overlay_returns.append(float((overlay * usable_returns).sum() - turnover * cost_rate))
        baseline_returns.append(float((equal_weight * usable_returns).sum()))
        turnovers.append(turnover)
        previous_overlay = overlay

    overlay_series = pd.Series(overlay_returns, index=wide_returns.index, dtype=float)
    baseline_series = pd.Series(baseline_returns, index=wide_returns.index, dtype=float)
    turnover_series = pd.Series(turnovers, index=wide_returns.index, dtype=float)
    overlay_metrics = _metrics(overlay_series, turnover=turnover_series)
    baseline_metrics = _metrics(baseline_series)
    return {
        "fold": fold["fold"],
        "status": "available_for_manual_offline_review",
        "train_start": fold["train_start"],
        "train_end": fold["train_end"],
        "test_start": fold["test_start"],
        "test_end": fold["test_end"],
        "test_days": int(len(overlay_series)),
        "overlay": overlay_metrics,
        "equal_weight_baseline": baseline_metrics,
        "delta_vs_equal_weight": {
            "final_value": _finite_float((overlay_metrics["final_value"] or 0.0) - (baseline_metrics["final_value"] or 0.0)),
            "sharpe_ratio": _finite_float((overlay_metrics["sharpe_ratio"] or 0.0) - (baseline_metrics["sharpe_ratio"] or 0.0)),
            "max_drawdown": _finite_float((overlay_metrics["max_drawdown"] or 0.0) - (baseline_metrics["max_drawdown"] or 0.0)),
        },
    }


def build_review(
    *,
    panel_path: Path = DEFAULT_PANEL_OUTPUT,
    baseline_path: Path = DEFAULT_BASELINE,
    single_name_active_cap: float = 0.055,
    high_dividend_bucket_active_cap: float = 0.035,
    bond_bucket_active_cap: float = 0.020,
    max_daily_turnover: float = 0.12,
    min_positive_final_folds: int = 4,
    min_positive_sharpe_folds: int = 4,
    min_non_worse_drawdown_folds: int = 3,
    as_of: str = "2026-07-20",
) -> dict[str, Any]:
    panel = _load_panel(panel_path)
    baseline = _load_json(baseline_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if panel.empty:
        blockers.append("missing_or_empty_frozen_panel")
    if not baseline:
        blockers.append("missing_baseline_shadow_backtest")
    elif baseline.get("status") != "available_for_manual_offline_review":
        blockers.append(f"baseline_shadow_backtest_not_available:{baseline.get('status')}")
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

    fold_rows = [
        _fold_overlay_backtest(
            panel,
            fold,
            eligible_tickers=eligible_tickers,
            low_quantile=float(inputs.get("low_quantile", 0.30)),
            high_quantile=float(inputs.get("high_quantile", 0.70)),
            low_score=float(inputs.get("low_score", 0.50)),
            mid_score=float(inputs.get("mid_score", 1.00)),
            high_score=float(inputs.get("high_score", 1.50)),
            cost_bps=float(inputs.get("cost_bps", 5.0)),
            single_name_active_cap=single_name_active_cap,
            high_dividend_bucket_active_cap=high_dividend_bucket_active_cap,
            bond_bucket_active_cap=bond_bucket_active_cap,
            max_daily_turnover=max_daily_turnover,
        )
        for fold in folds
    ] if not blockers else []
    for row in fold_rows:
        if row.get("status") != "available_for_manual_offline_review":
            blockers.append(f"fold_not_available:{row.get('fold')}:{row.get('blocking_reason')}")

    overlay_aggregate = _aggregate_folds(fold_rows)
    baseline_aggregate = baseline.get("summary", {}) if baseline else {}
    if overlay_aggregate["available_fold_count"]:
        if overlay_aggregate["positive_final_value_folds"] < min_positive_final_folds:
            warnings.append(
                f"positive_final_value_folds_below_threshold:{overlay_aggregate['positive_final_value_folds']}<{min_positive_final_folds}"
            )
        if overlay_aggregate["positive_sharpe_folds"] < min_positive_sharpe_folds:
            warnings.append(
                f"positive_sharpe_folds_below_threshold:{overlay_aggregate['positive_sharpe_folds']}<{min_positive_sharpe_folds}"
            )
        if overlay_aggregate["non_worse_drawdown_folds"] < min_non_worse_drawdown_folds:
            warnings.append(
                "non_worse_drawdown_folds_below_threshold:"
                f"{overlay_aggregate['non_worse_drawdown_folds']}<{min_non_worse_drawdown_folds}"
            )

    pass_gate = bool(
        not blockers
        and overlay_aggregate["positive_final_value_folds"] >= min_positive_final_folds
        and overlay_aggregate["positive_sharpe_folds"] >= min_positive_sharpe_folds
        and overlay_aggregate["non_worse_drawdown_folds"] >= min_non_worse_drawdown_folds
    )

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_llm_state_reward_interface_risk_control_overlay_shadow_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "available_for_manual_offline_review",
        "policy": "risk_control_overlay_shadow_only_no_model_training_no_live_action",
        "inputs": {
            "panel": str(panel_path),
            "panel_sha256": actual_hash,
            "baseline_shadow_backtest": str(baseline_path),
            "eligible_tickers": eligible_tickers,
            "excluded_tickers": list(inputs.get("excluded_tickers") or DEFAULT_EXCLUDED_TICKERS),
            "single_name_active_cap": single_name_active_cap,
            "high_dividend_bucket": HIGH_DIVIDEND_BUCKET,
            "high_dividend_bucket_active_cap": high_dividend_bucket_active_cap,
            "bond_bucket": BOND_BUCKET,
            "bond_bucket_active_cap": bond_bucket_active_cap,
            "max_daily_turnover": max_daily_turnover,
        },
        "summary": {
            "baseline_positive_final_value_folds": baseline_aggregate.get("positive_final_value_folds"),
            "baseline_positive_sharpe_folds": baseline_aggregate.get("positive_sharpe_folds"),
            "baseline_non_worse_drawdown_folds": baseline_aggregate.get("non_worse_drawdown_folds"),
            "overlay": overlay_aggregate,
            "delta_overlay_minus_baseline": {
                "positive_final_value_folds": (
                    overlay_aggregate["positive_final_value_folds"]
                    - int(baseline_aggregate.get("positive_final_value_folds", 0) or 0)
                ),
                "positive_sharpe_folds": (
                    overlay_aggregate["positive_sharpe_folds"]
                    - int(baseline_aggregate.get("positive_sharpe_folds", 0) or 0)
                ),
                "non_worse_drawdown_folds": (
                    overlay_aggregate["non_worse_drawdown_folds"]
                    - int(baseline_aggregate.get("non_worse_drawdown_folds", 0) or 0)
                ),
            },
            "pass_risk_control_overlay_gate": pass_gate,
        },
        "fold_results": fold_rows,
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "interpretation": [
            "The overlay constrains reward-tilt concentration without using a learned model.",
            "Passing this gate requires preserving return and Sharpe fold counts while improving drawdown fold count.",
            "This report is a shadow diagnostic only and does not authorize live weights.",
        ],
        "decision": {
            "available_for_manual_offline_review": not blockers,
            "risk_control_overlay_ready_for_review": not blockers,
            "risk_control_overlay_passed_shadow_gate": pass_gate,
            "next_shadow_model_design_allowed": pass_gate,
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
    return history_dir / f"llm_state_reward_interface_risk_control_overlay_shadow_backtest_{stamp}.json"


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
    parser.add_argument("--single-name-active-cap", type=float, default=0.055)
    parser.add_argument("--high-dividend-bucket-active-cap", type=float, default=0.035)
    parser.add_argument("--bond-bucket-active-cap", type=float, default=0.020)
    parser.add_argument("--max-daily-turnover", type=float, default=0.12)
    parser.add_argument("--min-positive-final-folds", type=int, default=4)
    parser.add_argument("--min-positive-sharpe-folds", type=int, default=4)
    parser.add_argument("--min-non-worse-drawdown-folds", type=int, default=3)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        panel_path=_resolve(args.panel),
        baseline_path=_resolve(args.baseline),
        single_name_active_cap=args.single_name_active_cap,
        high_dividend_bucket_active_cap=args.high_dividend_bucket_active_cap,
        bond_bucket_active_cap=args.bond_bucket_active_cap,
        max_daily_turnover=args.max_daily_turnover,
        min_positive_final_folds=args.min_positive_final_folds,
        min_positive_sharpe_folds=args.min_positive_sharpe_folds,
        min_non_worse_drawdown_folds=args.min_non_worse_drawdown_folds,
        as_of=args.as_of,
    )
    write_review(review, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"LLM state-reward risk-control overlay shadow backtest: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "overlay": review["summary"]["overlay"],
                "risk_control_overlay_passed_shadow_gate": review["decision"]["risk_control_overlay_passed_shadow_gate"],
                "promote_to_live": review["decision"]["promote_to_live"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
