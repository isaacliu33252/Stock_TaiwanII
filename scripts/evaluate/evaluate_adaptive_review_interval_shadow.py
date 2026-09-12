#!/usr/bin/env python3
"""Adaptive review interval shadow test for Group A+.

User-proposed research line, 2026-08-09. Distinct from two existing
mechanisms:
- staged_buys / buy_fraction (execution_plan.py): how fast to trade toward
  an already-decided target.
- min_hold_days (backtest_group_a_plus_switch_policy.py's SwitchRule):
  once a regime is entered, block EXITING it for N days -- the signal is
  still recomputed every day, it just isn't allowed to act on an exit yet.

Adaptive review interval is a third, different thing: how often to even
RECOMPUTE the signal at all. Between scheduled review days, this shadow
freezes the portfolio at whatever target was decided on the last review
day -- the underlying a2118 regime/target-weight computation is completely
unchanged (golden1_0531 untouched, A21.18's decision rule untouched), this
only decides which of a2118's own daily outputs are actually looked at.

Classification rule (causal -- uses only that day's own frame data, no
lookahead):
- "crash-like" (drawdown within `crash_dd_buffer` of the -11% dd_threshold,
  or tail_risk_score >= `crash_tail_risk_score_min`) OR regime is
  group_a_plus_recovery -> review again in 1 day.
- stable golden1 (not crash-like, ma_gap comfortably above the -0.3%
  defensive-entry threshold, drawdown comfortably above the -11% trigger)
  -> review again in 3 days.
- stable defensive, far from the +1% re-entry threshold -> review again in
  5 days.
- anything else (near a threshold, ambiguous) -> 1 day (conservative
  default).

Two paper-account arms, both driven by the identical unmodified a2118
regime backtest:
- Daily Review: baseline, recomputes every day (= current a2118 behavior).
- Adaptive Review: only recomputes on scheduled review days, holds the
  last-reviewed target weights in between.

Research-only. Does not change any live weight, execution plan, or
A21.18/golden1_0531 decision logic.
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

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_warning_cashflow_guard import _resolve_end_date
from tw_output_standard import OutputStandardizer, write_standard_output

# Switch-rule thresholds this classifier is calibrated against -- must match
# group_a_plus/runners/a2111.py::_build_switch_rule() (a2118's own switch
# rule). Not imported directly since that function returns a SwitchRule
# object with positional fields, not named constants; duplicated here as
# literals with an explicit cross-reference so drift is visible.
ENTRY_MA_GAP = -0.003  # golden1 -> defensive trigger
EXIT_MA_GAP = 0.010  # defensive -> golden1 trigger
DD_THRESHOLD = -0.11  # drawdown override trigger

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/adaptive_review_interval_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/adaptive_review_interval_shadow/history"
DEFAULT_WINDOWS = [
    ("live_2024_2026", "2024-01-02", "latest", "tuning_window", None),
    ("active_2025_2026", "2025-01-02", "latest", "recent_oos", None),
    ("stress_2026", "2026-01-02", "latest", "recent_stress", None),
    (
        "backfill_2020_covid",
        "2020-01-02",
        "2020-12-31",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2020_20260716.csv",
    ),
    (
        "backfill_2021_may_correction",
        "2021-01-04",
        "2021-12-30",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2021_20260726.csv",
    ),
    (
        "backfill_2022_rate_hike",
        "2022-01-03",
        "2022-10-31",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv",
    ),
    (
        "backfill_2024_aug_unwind",
        "2024-01-02",
        "2024-12-31",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2024_20260726.csv",
    ),
]


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _parse_windows(raw_windows: list[str]) -> list[tuple[str, str, str, str, str | None]]:
    if not raw_windows:
        return DEFAULT_WINDOWS
    parsed: list[tuple[str, str, str, str, str | None]] = []
    for raw in raw_windows:
        parts = [part.strip() for part in raw.split(":")]
        if len(parts) not in {3, 4, 5}:
            raise ValueError("--window must be label:start:end[:bucket[:ncf_panel_631l_path]]")
        label, start, end = parts[:3]
        bucket = parts[3] if len(parts) >= 4 else "custom"
        panel_path = parts[4] if len(parts) == 5 and parts[4] else None
        parsed.append((label, start, end, bucket, panel_path))
    return parsed


def _targets_from_report(frame: pd.DataFrame, report: dict[str, Any]) -> pd.DataFrame:
    base_weights = {key: _normalize(dict(value)) for key, value in report["base_weights"].items()}
    golden = base_weights["golden1"]
    rows: list[dict[str, float]] = []
    for _dt, row in frame.iterrows():
        regime = str(row.get("execution_regime", "golden1"))
        weights = base_weights.get(regime, base_weights.get("group_a_plus_defensive", golden))
        rows.append({key: float(weights.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")})
    return pd.DataFrame(rows, index=frame.index)


def classify_review_interval(
    row: pd.Series,
    *,
    crash_dd_buffer: float = 0.03,
    crash_tail_risk_score_min: int = 5,
    golden_stable_ma_gap_buffer: float = 0.02,
    golden_stable_dd_buffer: float = 0.05,
    defensive_stable_ma_gap_buffer: float = 0.02,
) -> tuple[int, str]:
    """Causal, single-day classification -- returns (interval_days, label).

    Uses only `row`'s own fields (today's frame data), no lookahead.
    """

    regime = str(row.get("execution_regime", "golden1"))
    ma_gap = float(row.get("ma_gap", 0.0) or 0.0)
    drawdown = float(row.get("drawdown", 0.0) or 0.0)
    tail_risk_score = float(row.get("tail_risk_score", 0.0) or 0.0)

    crash_like = (
        drawdown <= DD_THRESHOLD + crash_dd_buffer or tail_risk_score >= crash_tail_risk_score_min
    )
    if regime == "group_a_plus_recovery" or crash_like:
        return 1, "crash_or_recovery"

    if regime == "golden1":
        stable = (
            ma_gap >= ENTRY_MA_GAP + golden_stable_ma_gap_buffer
            and drawdown >= DD_THRESHOLD + golden_stable_dd_buffer
        )
        if stable:
            return 3, "stable_golden1"
        return 1, "golden1_near_threshold"

    if regime == "group_a_plus_defensive":
        far_from_reentry = ma_gap <= EXIT_MA_GAP - defensive_stable_ma_gap_buffer
        if far_from_reentry:
            return 5, "stable_defensive_far_from_threshold"
        return 1, "defensive_near_threshold"

    return 1, "other_regime_conservative_default"


def simulate_adaptive_review(
    frame: pd.DataFrame, baseline_targets: pd.DataFrame, **classify_kwargs: Any
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    adjusted_rows: list[dict[str, float]] = []
    review_log: list[dict[str, Any]] = []
    last_weights: dict[str, float] | None = None
    next_review_i = 0
    index = list(frame.index)

    for i, dt in enumerate(index):
        if i >= next_review_i:
            last_weights = baseline_targets.loc[dt].to_dict()
            interval, label = classify_review_interval(frame.loc[dt], **classify_kwargs)
            next_review_i = i + interval
            review_log.append({"date": str(dt.date()), "interval_days": interval, "reason": label})
        adjusted_rows.append(dict(last_weights))

    adjusted = pd.DataFrame(adjusted_rows, index=frame.index)
    return adjusted, review_log


def _simulate_targets(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, Any]]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_key: tuple[float, ...] | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        weights = _normalize(target_weights.loc[dt].to_dict())
        target_key = tuple(round(float(weights.get(key, 0.0)), 8) for key in (*TICKERS, "cash"))
        cost = 0.0
        turnover = 0.0
        if target_key != current_key:
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            net_value = gross_value
            target_values: dict[str, float] = {}
            for _iteration in range(3):
                target_values = {ticker: net_value * weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover = _trade_cost(
                    current_values, target_values, commission_rate, slippage_rate, equity_etf_sell_tax
                )
                net_value = max(gross_value - cost, 0.0)
            cash = max(net_value - sum(target_values.values()), 0.0)
            shares = {
                ticker: target_values.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
                for ticker in TICKERS
            }
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            current_key = target_key
        values.append(gross_value)

    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
    }


def _count_regime_flips(regime: pd.Series) -> int:
    return int((regime != regime.shift(1)).sum() - 1) if len(regime) > 0 else 0


def _delayed_and_avoided_transitions(
    frame: pd.DataFrame, baseline_targets: pd.DataFrame, adaptive_targets: pd.DataFrame
) -> dict[str, int]:
    """Days where adaptive (frozen) target differs from the fresh (baseline)
    target, split by whether freezing turned out to help or hurt that day's
    single-day portfolio return in hindsight -- diagnostic only, computed
    post-hoc for reporting, does not feed back into the simulation.
    """
    delayed_useful = 0
    avoided_false = 0
    suppressed_days = 0
    for i in range(1, len(frame.index)):
        dt = frame.index[i]
        base_row = baseline_targets.loc[dt]
        adapt_row = adaptive_targets.loc[dt]
        if (base_row - adapt_row).abs().sum() < 1e-9:
            continue
        suppressed_days += 1
        # Heuristic: if the fresh target moved toward defensive/cash relative
        # to the frozen one and the market fell that day (0050 1d return <0),
        # freezing delayed a useful defensive move. If the fresh target moved
        # toward risk-on and the market fell, freezing avoided a false
        # risk-on move (a good thing). Uses only that day's own realized
        # return, not future information.
        ret_1d = float(frame.loc[dt, "return_0050_1d"]) if "return_0050_1d" in frame.columns else 0.0
        base_cash = float(base_row.get("cash", 0.0))
        adapt_cash = float(adapt_row.get("cash", 0.0))
        moved_more_defensive_in_fresh = base_cash > adapt_cash
        if ret_1d < 0.0 and moved_more_defensive_in_fresh:
            delayed_useful += 1
        elif ret_1d < 0.0 and not moved_more_defensive_in_fresh:
            avoided_false += 1
        elif ret_1d >= 0.0 and not moved_more_defensive_in_fresh:
            avoided_false += 1
        elif ret_1d >= 0.0 and moved_more_defensive_in_fresh:
            delayed_useful += 1
    return {
        "suppressed_days": suppressed_days,
        "delayed_useful_transition_days": delayed_useful,
        "avoided_false_transition_days": avoided_false,
    }


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    bucket: str,
    db_path: Path,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    ncf_panel_631l_path: str | None,
) -> dict[str, Any]:
    resolved_end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=resolved_end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
        ncf_panel_631l_path=ncf_panel_631l_path,
    )
    prices, coverage = _load_total_return_prices(db_path, frame.index)
    baseline_targets = _targets_from_report(frame, report).reindex(prices.index).ffill()
    frame_aligned = frame.reindex(prices.index).ffill()

    adaptive_targets, review_log = simulate_adaptive_review(frame_aligned, baseline_targets)

    baseline_curve, baseline_execution = _simulate_targets(
        prices, baseline_targets, initial_value=initial_value,
        commission_rate=commission_rate, slippage_rate=slippage_rate, equity_etf_sell_tax=equity_etf_sell_tax,
    )
    adaptive_curve, adaptive_execution = _simulate_targets(
        prices, adaptive_targets, initial_value=initial_value,
        commission_rate=commission_rate, slippage_rate=slippage_rate, equity_etf_sell_tax=equity_etf_sell_tax,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    adaptive_metrics = _metrics(adaptive_curve, initial_value)

    transitions = _delayed_and_avoided_transitions(frame_aligned, baseline_targets, adaptive_targets)
    interval_counts: dict[str, int] = {}
    for entry in review_log:
        key = str(entry["interval_days"])
        interval_counts[key] = interval_counts.get(key, 0) + 1

    return {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": resolved_end},
        "review_count": len(review_log),
        "review_interval_usage": interval_counts,
        "baseline_metrics": baseline_metrics,
        "adaptive_metrics": adaptive_metrics,
        "delta_vs_baseline": {
            "final_value": float(adaptive_metrics["final_value"] - baseline_metrics["final_value"]),
            "sharpe_ratio": float(adaptive_metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]),
            "max_drawdown": float(adaptive_metrics["max_drawdown"] - baseline_metrics["max_drawdown"]),
            "transaction_cost": float(
                adaptive_execution["transaction_cost"] - baseline_execution["transaction_cost"]
            ),
            "turnover_value": float(adaptive_execution["turnover_value"] - baseline_execution["turnover_value"]),
            "rebalance_count": int(adaptive_execution["rebalance_count"] - baseline_execution["rebalance_count"]),
        },
        "regime_flip_count": _count_regime_flips(frame_aligned["execution_regime"]),
        "transitions": transitions,
        "dividend_coverage": coverage,
    }


def _summarize(windows: list[dict[str, Any]]) -> dict[str, Any]:
    if not windows:
        return {"window_count": 0, "decision": "blocked_no_windows"}
    pass_windows = [
        w for w in windows
        if w["delta_vs_baseline"]["final_value"] >= 0.0
        and w["delta_vs_baseline"]["sharpe_ratio"] >= 0.0
        and w["delta_vs_baseline"]["max_drawdown"] >= 0.0
    ]
    total_cost_delta = sum(w["delta_vs_baseline"]["transaction_cost"] for w in windows)
    total_turnover_delta = sum(w["delta_vs_baseline"]["turnover_value"] for w in windows)
    return {
        "window_count": len(windows),
        "triple_pass_windows": len(pass_windows),
        "all_windows_triple_pass": len(pass_windows) == len(windows),
        "total_transaction_cost_delta": total_cost_delta,
        "total_turnover_delta": total_turnover_delta,
        "net_cost_pass": total_cost_delta <= 0.0 and total_turnover_delta <= 0.0,
        "decision": (
            "candidate_for_group_a_plus_shadow_queue"
            if len(pass_windows) == len(windows) and total_cost_delta <= 0.0
            else "research_only_not_promoted"
        ),
        "golden1_0531_unchanged": True,
        "a2118_decision_rule_unchanged": True,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    windows = [
        evaluate_window(
            label=label, start=start, end=end, bucket=bucket, db_path=db_path,
            initial_value=float(args.initial_value), commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate), equity_etf_sell_tax=float(args.equity_etf_sell_tax),
            ncf_panel_631l_path=panel_path,
        )
        for label, start, end, bucket, panel_path in _parse_windows(args.window)
    ]
    return {
        "report_type": "adaptive_review_interval_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "strategy": "Group A+ shadow only",
            "changes_latest_strategy_live_weights": False,
            "changes_golden1_0531": False,
            "changes_a2118_decision_rule": False,
            "mechanism": (
                "adaptive review interval: NEXT_REVIEW_1D/3D/5D, causal, "
                "based on regime + distance from switch-rule thresholds; "
                "between reviews the portfolio is frozen at the last "
                "reviewed target -- a2118's own regime/target computation "
                "is unchanged, this only decides which days' outputs get "
                "acted on"
            ),
        },
        "thresholds_used": {
            "entry_ma_gap": ENTRY_MA_GAP,
            "exit_ma_gap": EXIT_MA_GAP,
            "dd_threshold": DD_THRESHOLD,
        },
        "summary": _summarize(windows),
        "windows": windows,
    }


def _history_path(history_dir: Path) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir / f"adaptive_review_interval_shadow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--window", action="append", default=[], help="label:start:end[:bucket[:ncf_panel_631l_path]]")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()

    std = OutputStandardizer("scripts.evaluate.evaluate_adaptive_review_interval_shadow")
    try:
        report = build_report(args)
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    history = _history_path(_resolve(args.history_dir))
    write_standard_output(payload, history)
    print(f"Adaptive review interval shadow: {_resolve(args.output)}")
    print(f"History: {history.resolve()}")
    if payload.get("success"):
        print(json.dumps(payload["data"]["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
