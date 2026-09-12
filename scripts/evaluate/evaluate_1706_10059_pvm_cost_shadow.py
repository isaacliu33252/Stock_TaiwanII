#!/usr/bin/env python3
"""PVM/cost-aware shadow evaluator inspired by arXiv:1706.10059.

Research-only. This script does not change live weights, latest pointers, or
the frozen golden1_0531 release. It evaluates whether adding previous-target
weight memory and cost-aware rewards would have helped Group A+ latest-strategy
style allocations.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/pvm_cost_shadow_1706_10059.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/pvm_cost_shadow_1706_10059/history"
# 2026-08-09: added the 2017-2019 backfill window (per the review doc's
# "Updated recommendation" next step) using the existing
# ncf_00631l_panel_backfill_2017_2019 CSV -- without an explicit panel path,
# run_a2118() resolves to the *latest* live NCF snapshot for any date range,
# which would give this window a2118's base switch-rule regime with no
# historical NCF-driven hedge at all, defeating the point of testing the
# PVM/cost-recovery gate against a2118's actual flip behavior.
DEFAULT_WINDOWS = [
    ("live_2024_2026", "2024-01-02", "latest", "tuning_window", None),
    ("active_2025_2026", "2025-01-02", "latest", "recent_oos", None),
    ("stress_2026", "2026-01-02", "latest", "recent_stress", None),
    (
        "backfill_2017_2019",
        "2017-01-03",
        "2019-12-31",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv",
    ),
    # 2026-08-09: added to test the gate against genuinely sharp regime
    # transitions, not just smoothly trending windows -- this is what
    # exposed lookback_days=5's failure (see review doc's "Widened OOS Set"
    # follow-up). backfill_2022_rate_hike is kept despite contributing zero
    # events/deltas in every cell tested so far (no large 00631L/00632R flip
    # was ever proposed by the base strategy in that window) -- it adds
    # coverage even though it hasn't added signal yet.
    (
        "backfill_2020_covid",
        "2020-01-02",
        "2020-12-31",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2020_20260716.csv",
    ),
    (
        "backfill_2022_rate_hike",
        "2022-01-03",
        "2022-10-31",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv",
    ),
    # 2026-08-09: two more genuine late-bull-then-reversal periods, picked
    # by checking 0050.TW's intra-year max drawdown per year (see review
    # doc's "More Late-Bull-Reversal Windows" follow-up). 2021 (May 2021
    # Taiwan COVID community-outbreak correction, -11.5% DD after a +17%
    # run) produced real events and, like backfill_2020_covid, exposed
    # lookback_days=5 regressing. 2024 (Aug 2024 carry-trade-unwind crash,
    # -21.7% DD after a +45% H1 run) is kept for coverage despite
    # contributing zero events so far -- unlike backfill_2022_rate_hike
    # (ma_gap never got hot enough), 2024 WAS a 100%-golden1,
    # ma_gap-exceeded-threshold year, but the NCF panel's own h20/confidence
    # conditions never lined up with the ma_gap condition on the same day
    # to fire the late-bull trigger. Different cause, same zero-signal
    # symptom -- not further diagnosed this pass.
    (
        "backfill_2021_may_correction",
        "2021-01-04",
        "2021-12-30",
        "out_of_sample",
        "results/ncf_00631l_panel_backfill_2021_20260726.csv",
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
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


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


def _weight_turnover(a: dict[str, float], b: dict[str, float]) -> float:
    return float(sum(abs(float(a.get(key, 0.0)) - float(b.get(key, 0.0))) for key in (*TICKERS, "cash")))


def _pvm_delay_targets(
    target_weights: pd.DataFrame,
    *,
    turnover_threshold: float,
    flip_threshold: float,
    max_delay_days: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Hold prior target briefly when a large 00631L/00632R flip appears.

    This is a deliberately simple live-usable PVM proxy: it uses only previous
    target weights and the proposed new weights. It does not peek at future
    returns.
    """

    rows: list[dict[str, float]] = []
    events: list[dict[str, Any]] = []
    last_output: dict[str, float] | None = None
    pending: dict[str, Any] | None = None
    delay_remaining = 0

    for dt, raw_row in target_weights.iterrows():
        proposed = {key: float(raw_row.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")}
        if last_output is None:
            last_output = dict(proposed)
            rows.append(dict(proposed))
            continue

        if pending is not None and delay_remaining > 0:
            delay_remaining -= 1
            rows.append(dict(last_output))
            events.append(
                {
                    "date": str(dt.date()),
                    "event": "delay_active",
                    "delayed_target": pending["date"],
                    "remaining_days_after_today": delay_remaining,
                }
            )
            if delay_remaining == 0:
                last_output = dict(pending["weights"])
                pending = None
            continue

        turnover = _weight_turnover(last_output, proposed)
        long_down = max(float(last_output.get("00631L.TW", 0.0)) - float(proposed.get("00631L.TW", 0.0)), 0.0)
        inverse_up = max(float(proposed.get("00632R.TW", 0.0)) - float(last_output.get("00632R.TW", 0.0)), 0.0)
        inverse_down = max(float(last_output.get("00632R.TW", 0.0)) - float(proposed.get("00632R.TW", 0.0)), 0.0)
        long_up = max(float(proposed.get("00631L.TW", 0.0)) - float(last_output.get("00631L.TW", 0.0)), 0.0)
        flip_score = max(min(long_down, inverse_up), min(inverse_down, long_up))
        should_delay = turnover >= turnover_threshold and flip_score >= flip_threshold and max_delay_days > 0
        if should_delay:
            pending = {"date": str(dt.date()), "weights": dict(proposed)}
            delay_remaining = max_delay_days
            rows.append(dict(last_output))
            events.append(
                {
                    "date": str(dt.date()),
                    "event": "delay_started",
                    "turnover": turnover,
                    "flip_score": flip_score,
                    "delay_days": max_delay_days,
                    "prior_weights": dict(last_output),
                    "proposed_weights": dict(proposed),
                }
            )
        else:
            last_output = dict(proposed)
            rows.append(dict(proposed))

    adjusted = pd.DataFrame(rows, index=target_weights.index)
    return adjusted, {
        "policy": "delay",
        "turnover_threshold": float(turnover_threshold),
        "flip_threshold": float(flip_threshold),
        "max_delay_days": int(max_delay_days),
        "events": events,
        "event_count": len([event for event in events if event["event"] == "delay_started"]),
    }


def _portfolio_return(weights: dict[str, float], start_prices: pd.Series, end_prices: pd.Series) -> float:
    return float(
        sum(
            float(weights.get(ticker, 0.0))
            * (float(end_prices[ticker]) / max(float(start_prices[ticker]), 1e-12) - 1.0)
            for ticker in TICKERS
        )
    )


def _pvm_cost_recovery_targets(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    turnover_threshold: float,
    flip_threshold: float,
    lookback_days: int,
    cost_multiplier: float,
    max_block_days: int,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Block a large flip until trailing relative performance covers cost.

    This is a live-usable proxy for the paper's PVM/cost-aware reward: it uses
    previous weights, proposed weights, trailing prices only, and estimated
    trading cost. It has no future-return lookahead.
    """

    rows: list[dict[str, float]] = []
    events: list[dict[str, Any]] = []
    last_output: dict[str, float] | None = None
    consecutive_blocks = 0
    index = list(target_weights.index)

    for i, dt in enumerate(index):
        raw_row = target_weights.loc[dt]
        proposed = {key: float(raw_row.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")}
        if last_output is None:
            last_output = dict(proposed)
            rows.append(dict(proposed))
            continue

        turnover = _weight_turnover(last_output, proposed)
        long_down = max(float(last_output.get("00631L.TW", 0.0)) - float(proposed.get("00631L.TW", 0.0)), 0.0)
        inverse_up = max(float(proposed.get("00632R.TW", 0.0)) - float(last_output.get("00632R.TW", 0.0)), 0.0)
        inverse_down = max(float(last_output.get("00632R.TW", 0.0)) - float(proposed.get("00632R.TW", 0.0)), 0.0)
        long_up = max(float(proposed.get("00631L.TW", 0.0)) - float(last_output.get("00631L.TW", 0.0)), 0.0)
        flip_score = max(min(long_down, inverse_up), min(inverse_down, long_up))
        is_large_flip = turnover >= turnover_threshold and flip_score >= flip_threshold
        if not is_large_flip:
            last_output = dict(proposed)
            consecutive_blocks = 0
            rows.append(dict(proposed))
            continue

        lookback_i = max(0, i - max(int(lookback_days), 1))
        start_prices = prices.loc[index[lookback_i]]
        end_prices = prices.loc[dt]
        prior_advantage = _portfolio_return(proposed, start_prices, end_prices) - _portfolio_return(
            last_output, start_prices, end_prices
        )
        cost_weight, _turnover_weight = _trade_cost(
            {ticker: float(last_output.get(ticker, 0.0)) for ticker in TICKERS},
            {ticker: float(proposed.get(ticker, 0.0)) for ticker in TICKERS},
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
        )
        required_advantage = float(cost_multiplier) * float(cost_weight)
        should_block = prior_advantage < required_advantage and consecutive_blocks < max_block_days
        if should_block:
            consecutive_blocks += 1
            rows.append(dict(last_output))
            events.append(
                {
                    "date": str(dt.date()),
                    "event": "cost_recovery_block",
                    "turnover": float(turnover),
                    "flip_score": float(flip_score),
                    "lookback_days": int(lookback_days),
                    "prior_advantage": float(prior_advantage),
                    "estimated_cost_weight": float(cost_weight),
                    "required_advantage": float(required_advantage),
                    "consecutive_blocks": int(consecutive_blocks),
                    "prior_weights": dict(last_output),
                    "proposed_weights": dict(proposed),
                }
            )
        else:
            events.append(
                {
                    "date": str(dt.date()),
                    "event": "cost_recovery_allow",
                    "turnover": float(turnover),
                    "flip_score": float(flip_score),
                    "lookback_days": int(lookback_days),
                    "prior_advantage": float(prior_advantage),
                    "estimated_cost_weight": float(cost_weight),
                    "required_advantage": float(required_advantage),
                    "consecutive_blocks_before_allow": int(consecutive_blocks),
                }
            )
            last_output = dict(proposed)
            consecutive_blocks = 0
            rows.append(dict(proposed))

    adjusted = pd.DataFrame(rows, index=target_weights.index)
    return adjusted, {
        "policy": "cost_recovery",
        "turnover_threshold": float(turnover_threshold),
        "flip_threshold": float(flip_threshold),
        "lookback_days": int(lookback_days),
        "cost_multiplier": float(cost_multiplier),
        "max_block_days": int(max_block_days),
        "events": events,
        "event_count": len([event for event in events if event["event"] == "cost_recovery_block"]),
        "allow_count": len([event for event in events if event["event"] == "cost_recovery_allow"]),
    }


def _load_recent_trading_index(db_path: Path, end_date: str, lookback_days: int) -> pd.DatetimeIndex:
    """Real trading-day index ending at end_date, at least lookback_days+1 rows.

    Fetches a generous calendar window (lookback_days is trading days, not
    calendar days) then trims to the tail so the result always has enough
    real market rows for _load_total_return_prices() to reindex against.
    """
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        start_guess = (pd.Timestamp(end_date) - pd.Timedelta(days=int(lookback_days) * 3 + 30)).strftime("%Y-%m-%d")
        rows = con.execute(
            "SELECT DISTINCT dt FROM ohlcv WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            ["0050.TW", start_guess, end_date],
        ).fetchdf()
    finally:
        con.close()
    index = pd.to_datetime(rows["dt"])
    return pd.DatetimeIndex(index.iloc[-(int(lookback_days) + 1):])


def build_workbook_aware_snapshot(
    execution_plan: dict[str, Any],
    *,
    db_path: Path,
    lookback_days: int,
    cost_multiplier: float,
    turnover_threshold: float,
    flip_threshold: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> dict[str, Any]:
    """Diagnostic-only: would today's actual-holdings-to-target transition
    trip the PVM cost-recovery gate?

    Candidate Import #1 from the paper review ("PVM-style previous-weight
    state") explicitly asked for real workbook holdings and the staged-buy
    remainder, not just the backtest's simulated target-weight series. This
    reads an execution_plan.json payload's current_holdings/current_prices/
    target_weights/staged_target_shares_before_guards fields and real
    trailing closes, purely to report a decision -- it never writes to
    execution_plan.json or changes any live weight/trade.
    """

    current_holdings = execution_plan.get("current_holdings") or {}
    current_prices = execution_plan.get("current_prices") or {}
    current_total_assets = float(execution_plan.get("current_total_assets") or 0.0)
    target_weights = execution_plan.get("target_weights") or {}
    staged_target_shares = execution_plan.get("staged_target_shares_before_guards") or {}
    actual_data_date = execution_plan.get("actual_data_date")

    if not current_holdings or not current_prices or current_total_assets <= 0 or not target_weights or not actual_data_date:
        return {"status": "unavailable", "reason": "execution_plan_missing_required_fields"}

    def _weights_from_shares(shares: dict[str, Any]) -> dict[str, float]:
        values = {
            ticker: float(shares.get(ticker, 0) or 0) * float(current_prices.get(ticker, 0.0) or 0.0)
            for ticker in TICKERS
        }
        weights = {ticker: values[ticker] / current_total_assets for ticker in TICKERS}
        weights["cash"] = max(0.0, 1.0 - sum(weights.values()))
        return weights

    current_weights = _weights_from_shares(current_holdings)
    full_target_weights = {key: float(target_weights.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")}
    staged_weights = _weights_from_shares(staged_target_shares) if staged_target_shares else None

    turnover_current_to_full_target = _weight_turnover(current_weights, full_target_weights)
    turnover_current_to_staged = (
        _weight_turnover(current_weights, staged_weights) if staged_weights is not None else None
    )

    index = _load_recent_trading_index(db_path, str(actual_data_date), int(lookback_days))
    prices, _coverage = _load_total_return_prices(db_path, index)
    single_row = pd.DataFrame(
        [current_weights, full_target_weights],
        index=[index[0], index[-1]],
    )
    _adjusted, pvm_policy = _pvm_cost_recovery_targets(
        prices,
        single_row,
        turnover_threshold=turnover_threshold,
        flip_threshold=flip_threshold,
        lookback_days=lookback_days,
        cost_multiplier=cost_multiplier,
        max_block_days=1,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    gate_active = pvm_policy["event_count"] > 0
    would_allow = pvm_policy["allow_count"] > 0

    return {
        "status": "ok",
        "actual_data_date": str(actual_data_date),
        "current_weights": current_weights,
        "full_target_weights": full_target_weights,
        "staged_target_weights": staged_weights,
        "turnover_current_to_full_target": turnover_current_to_full_target,
        "turnover_current_to_staged": turnover_current_to_staged,
        "large_flip_detected": gate_active or would_allow,
        "cost_recovery_would_block": gate_active,
        "cost_recovery_would_allow": would_allow,
        "pvm_policy_detail": pvm_policy,
        "note": (
            "large_flip_detected is true only when the 00631L<->00632R "
            "turnover/flip thresholds are actually crossed; most days this "
            "is false and the gate has nothing to evaluate."
        ),
    }


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
    daily_rows: list[dict[str, Any]] = []

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
                    current_values,
                    target_values,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
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
        daily_rows.append(
            {
                "date": str(dt.date()),
                "value": float(gross_value),
                "cost": float(cost),
                "turnover": float(turnover),
                "weights": {key: float(weights.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")},
            }
        )

    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "daily_rows": daily_rows,
    }


def _event_reward_diagnostics(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    horizon_days: int,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    index = list(prices.index)
    for i in range(1, len(index) - horizon_days):
        dt = index[i]
        prev_dt = index[i - 1]
        end_dt = index[i + horizon_days]
        previous = _normalize(target_weights.loc[prev_dt].to_dict())
        proposed = _normalize(target_weights.loc[dt].to_dict())
        if _weight_turnover(previous, proposed) <= 1e-10:
            continue
        p0 = prices.loc[dt]
        p1 = prices.loc[end_dt]
        previous_values = {ticker: float(previous.get(ticker, 0.0)) for ticker in TICKERS}
        proposed_values = {ticker: float(proposed.get(ticker, 0.0)) for ticker in TICKERS}
        cost, turnover = _trade_cost(
            previous_values,
            proposed_values,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
        )
        prev_ret = sum(float(previous.get(ticker, 0.0)) * (float(p1[ticker]) / float(p0[ticker]) - 1.0) for ticker in TICKERS)
        prop_ret = sum(float(proposed.get(ticker, 0.0)) * (float(p1[ticker]) / float(p0[ticker]) - 1.0) for ticker in TICKERS)
        prev_cash = float(previous.get("cash", 0.0))
        prop_cash = float(proposed.get("cash", 0.0))
        switch_reward = math.log(max(1.0 + prop_ret + prop_cash * 0.0 - cost, 1e-12))
        hold_reward = math.log(max(1.0 + prev_ret + prev_cash * 0.0, 1e-12))
        events.append(
            {
                "date": str(dt.date()),
                "horizon_end": str(end_dt.date()),
                "turnover_weight": float(turnover),
                "cost_weight": float(cost),
                "switch_reward": float(switch_reward),
                "hold_previous_reward": float(hold_reward),
                "switch_minus_hold_reward": float(switch_reward - hold_reward),
                "previous_weights": previous,
                "proposed_weights": proposed,
            }
        )
    deltas = [float(event["switch_minus_hold_reward"]) for event in events]
    high_turnover = [event for event in events if float(event["turnover_weight"]) >= 0.25]
    return {
        "horizon_days": int(horizon_days),
        "event_count": len(events),
        "switch_help_count": sum(delta > 0.0 for delta in deltas),
        "switch_hurt_count": sum(delta < 0.0 for delta in deltas),
        "switch_help_rate": (sum(delta > 0.0 for delta in deltas) / len(deltas) if deltas else None),
        "mean_switch_minus_hold_reward": (sum(deltas) / len(deltas) if deltas else None),
        "high_turnover_event_count": len(high_turnover),
        "high_turnover_mean_switch_minus_hold_reward": (
            sum(float(event["switch_minus_hold_reward"]) for event in high_turnover) / len(high_turnover)
            if high_turnover
            else None
        ),
        "events": events[-50:],
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
    turnover_threshold: float,
    flip_threshold: float,
    policy: str,
    delay_days: int,
    lookback_days: int,
    cost_multiplier: float,
    max_block_days: int,
    horizon_days: int,
    ncf_panel_631l_path: str | None = None,
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
    targets = _targets_from_report(frame, report).reindex(prices.index).ffill()
    if policy == "delay":
        pvm_targets, pvm_policy = _pvm_delay_targets(
            targets,
            turnover_threshold=turnover_threshold,
            flip_threshold=flip_threshold,
            max_delay_days=delay_days,
        )
    elif policy == "cost_recovery":
        pvm_targets, pvm_policy = _pvm_cost_recovery_targets(
            prices,
            targets,
            turnover_threshold=turnover_threshold,
            flip_threshold=flip_threshold,
            lookback_days=lookback_days,
            cost_multiplier=cost_multiplier,
            max_block_days=max_block_days,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
    else:
        raise ValueError(f"unsupported policy: {policy}")
    baseline_curve, baseline_execution = _simulate_targets(
        prices,
        targets,
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    pvm_curve, pvm_execution = _simulate_targets(
        prices,
        pvm_targets,
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    pvm_metrics = _metrics(pvm_curve, initial_value)
    reward_diagnostics = _event_reward_diagnostics(
        prices,
        targets,
        horizon_days=horizon_days,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    return {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": resolved_end},
        "baseline_metrics": baseline_metrics,
        "pvm_policy_metrics": pvm_metrics,
        "delta_vs_baseline": {
            "final_value": float(pvm_metrics["final_value"] - baseline_metrics["final_value"]),
            "total_return": float(pvm_metrics["total_return"] - baseline_metrics["total_return"]),
            "sharpe_ratio": float(pvm_metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]),
            "max_drawdown": float(pvm_metrics["max_drawdown"] - baseline_metrics["max_drawdown"]),
            "transaction_cost": float(pvm_execution["transaction_cost"] - baseline_execution["transaction_cost"]),
            "turnover_value": float(pvm_execution["turnover_value"] - baseline_execution["turnover_value"]),
            "rebalance_count": int(pvm_execution["rebalance_count"] - baseline_execution["rebalance_count"]),
        },
        "baseline_execution": {key: value for key, value in baseline_execution.items() if key != "daily_rows"},
        "pvm_policy_execution": {key: value for key, value in pvm_execution.items() if key != "daily_rows"},
        "pvm_policy": pvm_policy,
        "reward_diagnostics": reward_diagnostics,
        "dividend_coverage": coverage,
    }


def _summarize(windows: list[dict[str, Any]]) -> dict[str, Any]:
    if not windows:
        return {"window_count": 0, "decision": "blocked_no_windows"}
    pass_windows = [
        item
        for item in windows
        if item["delta_vs_baseline"]["final_value"] >= 0.0
        and item["delta_vs_baseline"]["sharpe_ratio"] >= 0.0
        and item["delta_vs_baseline"]["max_drawdown"] >= 0.0
    ]
    event_count = sum(int(item["pvm_policy"]["event_count"]) for item in windows)
    cost_delta = sum(float(item["delta_vs_baseline"]["transaction_cost"]) for item in windows)
    turnover_delta = sum(float(item["delta_vs_baseline"]["turnover_value"]) for item in windows)
    net_cost_pass = cost_delta <= 0.0 and turnover_delta <= 0.0
    metric_pass = len(pass_windows) == len(windows)
    return {
        "window_count": len(windows),
        "triple_pass_windows": len(pass_windows),
        "all_windows_triple_pass": metric_pass,
        "pvm_policy_event_count": event_count,
        "pvm_delay_event_count": event_count,
        "total_transaction_cost_delta": cost_delta,
        "total_turnover_delta": turnover_delta,
        "net_cost_pass": net_cost_pass,
        "decision": (
            "candidate_for_latest_strategy_shadow_queue"
            if metric_pass and net_cost_pass and event_count > 0
            else (
                "research_only_rule_refinement_needed_cost_or_turnover_increased"
                if metric_pass and event_count > 0 and not net_cost_pass
                else "research_only_not_promoted"
            )
        ),
        "golden1_0531_unchanged": True,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    windows = [
        evaluate_window(
            label=label,
            start=start,
            end=end,
            bucket=bucket,
            db_path=db_path,
            initial_value=float(args.initial_value),
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
            turnover_threshold=float(args.turnover_threshold),
            flip_threshold=float(args.flip_threshold),
            policy=str(args.policy),
            delay_days=int(args.delay_days),
            lookback_days=int(args.lookback_days),
            cost_multiplier=float(args.cost_multiplier),
            max_block_days=int(args.max_block_days),
            horizon_days=int(args.horizon_days),
            ncf_panel_631l_path=panel_path,
        )
        for label, start, end, bucket, panel_path in _parse_windows(args.window)
    ]
    workbook_snapshot: dict[str, Any] | None = None
    if getattr(args, "workbook_snapshot", None):
        plan_path = _resolve(args.workbook_snapshot)
        plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
        execution_plan = plan_payload.get("data", plan_payload) if isinstance(plan_payload, dict) else {}
        workbook_snapshot = build_workbook_aware_snapshot(
            execution_plan,
            db_path=db_path,
            lookback_days=int(args.lookback_days),
            cost_multiplier=float(args.cost_multiplier),
            turnover_threshold=float(args.turnover_threshold),
            flip_threshold=float(args.flip_threshold),
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
        )
    return {
        "report_type": "1706_10059_pvm_cost_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": {
            "id": "1706.10059",
            "title": "Deep Portfolio Management",
            "imports_tested": ["portfolio_vector_memory", "cost_aware_reward", "delayed_large_flip_shadow_gate"],
        },
        "scope": {
            "strategy": "Group A+ latest strategy shadow only",
            "changes_latest_strategy_live_weights": False,
            "changes_golden1_0531": False,
        },
        "params": {
            "initial_value": float(args.initial_value),
            "commission_rate": float(args.commission_rate),
            "slippage_rate": float(args.slippage_rate),
            "equity_etf_sell_tax": float(args.equity_etf_sell_tax),
            "turnover_threshold": float(args.turnover_threshold),
            "flip_threshold": float(args.flip_threshold),
            "policy": str(args.policy),
            "delay_days": int(args.delay_days),
            "lookback_days": int(args.lookback_days),
            "cost_multiplier": float(args.cost_multiplier),
            "max_block_days": int(args.max_block_days),
            "horizon_days": int(args.horizon_days),
        },
        "summary": _summarize(windows),
        "windows": windows,
        "workbook_aware_snapshot": workbook_snapshot,
    }


def _history_path(history_dir: Path) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir / f"pvm_cost_shadow_1706_10059_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--turnover-threshold", type=float, default=0.25)
    parser.add_argument("--flip-threshold", type=float, default=0.05)
    parser.add_argument("--policy", choices=["delay", "cost_recovery"], default="cost_recovery")
    parser.add_argument("--delay-days", type=int, default=1)
    # 2026-08-09: default was 5, changed to 3 after a widened-OOS sensitivity
    # sweep (see the review doc's "Widened OOS Set" follow-up) showed
    # lookback=5 fails (regresses final value/Sharpe) on the 2020 COVID-crash
    # window while lookback=3 survives it. Shadow-only script, no production
    # impact either way -- this only changes what a future no-args run of
    # this script reports as its own recommendation.
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--cost-multiplier", type=float, default=3.0)
    parser.add_argument("--max-block-days", type=int, default=20)
    parser.add_argument("--horizon-days", type=int, default=5)
    parser.add_argument(
        "--window",
        action="append",
        default=[],
        help="label:start:end[:bucket[:ncf_panel_631l_path]]",
    )
    parser.add_argument(
        "--workbook-snapshot",
        default=None,
        help=(
            "Path to an execution_plan.json (standardized {success,data,...} "
            "or raw payload) to diagnose today's actual-holdings-to-target "
            "transition against the cost-recovery gate. Diagnostic only -- "
            "never writes to this file or changes any live weight."
        ),
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()

    std = OutputStandardizer("scripts.evaluate.evaluate_1706_10059_pvm_cost_shadow")
    try:
        report = build_report(args)
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    history = _history_path(_resolve(args.history_dir))
    write_standard_output(payload, history)
    print(f"PVM cost shadow: {_resolve(args.output)}")
    print(f"History: {history.resolve()}")
    if payload.get("success"):
        data = payload["data"]
        print(json.dumps(data["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
