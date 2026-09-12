#!/usr/bin/env python3
"""Adaptive-lookback feature-window shadow test, applied to the TSMC
concentration-divergence narrow_lead trigger.

User-proposed research line, 2026-08-09 (same day as
tsmc_concentration_divergence.py / evaluate_add_0050_instead_of_00631l_shadow.py).
The core idea: A21.18 (and shadow overlays built on top of it) use several
fixed lookback windows (5-day for the narrow_lead trigger, MA100 for the
main switch, etc). This project's own prior parameter-tuning line
(coordinate descent over a handful of backtest windows to find one "best"
fixed set of parameters) was closed as overfitting-prone. This is a
DIFFERENT mechanism: pre-declare a fixed candidate window SET
{20, 40, 60, 120, 252} and, each day, causally pick whichever candidate had
the best trailing directional hit-rate as of T-1 -- the candidate set never
changes, only which member is used today, and the selection criterion is
realized (past) prediction quality, never future performance.

Scope, per explicit user instruction: do NOT touch the MA100 main switch
rule as a first step. This tests the narrow_lead trigger inside the
ADD_0050_INSTEAD shadow guard (evaluate_add_0050_instead_of_00631l_shadow.py)
instead -- that guard is itself a shadow-only, additive mechanism layered on
top of a2118's unchanged golden1_0531 regime output, so varying its
internal feature window does not touch A21.18's core decision rule either.
`A21.18_fixed_window` (5-day, hardcoded, matches daily_signal.py's live
narrow_lead) is compared against `A21.18_adaptive_feature_window` (window
chosen daily from the candidate set) -- the regime backtest, golden1_0531,
and every other part of a2118 stay byte-identical between the two arms.

Simplification versus daily_signal.py's exact narrow_lead rule: that rule's
third condition (`ret_2330_5d - ret_0050_5d > 0.01`) is an absolute-return
gap calibrated for a 5-day window specifically and does not have an obvious
scale-invariant generalization to a 252-day window. This test uses a
simplified two-condition trigger (`ret_2330(window) > 0` AND
`concentration_divergence(window) > 0`) for BOTH arms, so the fixed-window
and adaptive-window arms are compared on the identical rule shape --
differing only in which window value is used, not in rule complexity.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.integrations.tsmc_concentration_divergence import TSMC_0050_WEIGHT_ASSUMPTION
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_warning_cashflow_guard import _resolve_end_date
from tw_output_standard import OutputStandardizer, write_standard_output

CANDIDATE_WINDOWS = (20, 40, 60, 120, 252)
DEFAULT_EVAL_LOOKBACK = 60
FIXED_WINDOW = 5  # matches daily_signal.py's live narrow_lead window

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/adaptive_lookback_narrow_lead_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/adaptive_lookback_narrow_lead_shadow/history"
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


def _load_2330_0050_closes(db_path: Path, index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows_0050 = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = '0050.TW' AND dt BETWEEN ? AND ? ORDER BY dt",
            [str(index[0].date()), str(index[-1].date())],
        ).fetchdf()
        rows_2330 = con.execute(
            "SELECT dt, close FROM external_market_ohlcv "
            "WHERE provider = 'yfinance' AND ticker = '2330.TW' AND dt BETWEEN ? AND ? ORDER BY dt",
            [str(index[0].date()), str(index[-1].date())],
        ).fetchdf()
    finally:
        con.close()
    rows_0050["dt"] = pd.to_datetime(rows_0050["dt"])
    rows_2330["dt"] = pd.to_datetime(rows_2330["dt"])
    close_0050 = rows_0050.set_index("dt")["close"].reindex(index).ffill()
    close_2330 = rows_2330.set_index("dt")["close"].reindex(index).ffill()
    return close_2330, close_0050


def _divergence_series_for_window(
    close_2330: pd.Series, close_0050: pd.Series, window: int, tsmc_weight: float
) -> tuple[pd.Series, pd.Series]:
    """Returns (concentration_divergence, ret_2330), both indexed like inputs.

    divergence[t] uses only trailing `window`-day returns known as of close
    of day t -- no lookahead.
    """
    ret_2330 = close_2330.pct_change(window)
    ret_0050 = close_0050.pct_change(window)
    ex_ret = (ret_0050 - tsmc_weight * ret_2330) / (1.0 - tsmc_weight)
    divergence = ret_2330 - ex_ret
    return divergence, ret_2330


def select_adaptive_window(
    close_2330: pd.Series,
    close_631l: pd.Series,
    close_0050: pd.Series,
    index: pd.DatetimeIndex,
    *,
    candidate_windows: tuple[int, ...] = CANDIDATE_WINDOWS,
    eval_lookback: int = DEFAULT_EVAL_LOOKBACK,
    tsmc_weight: float = TSMC_0050_WEIGHT_ASSUMPTION,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Causally choose, for each day, the candidate window whose divergence
    sign best predicted the realized 1-day-forward 00631L-vs-0050 relative
    return sign over the trailing `eval_lookback` days -- using only
    outcomes known strictly before that day (no lookahead into the future
    being predicted).

    Returns (chosen_window, divergence_with_chosen_window, ret_2330_with_chosen_window).
    """

    divergence_by_window: dict[int, pd.Series] = {}
    ret2330_by_window: dict[int, pd.Series] = {}
    for w in candidate_windows:
        div, ret2330 = _divergence_series_for_window(close_2330, close_0050, w, tsmc_weight)
        divergence_by_window[w] = div
        ret2330_by_window[w] = ret2330

    ret_631l_1d_fwd = (close_631l.shift(-1) / close_631l - 1.0).to_numpy()
    ret_0050_1d_fwd = (close_0050.shift(-1) / close_0050 - 1.0).to_numpy()
    realized_rel_1d_fwd = ret_631l_1d_fwd - ret_0050_1d_fwd  # known once day t+1 closes

    div_arrays = {w: divergence_by_window[w].to_numpy() for w in candidate_windows}
    n = len(index)
    default_window = candidate_windows[len(candidate_windows) // 2]
    chosen = np.full(n, default_window, dtype=int)

    min_valid = 10
    for i in range(n):
        # Only outcomes for s with s+1 <= i-1 (i.e. s <= i-2) are known by day i.
        eval_end = i - 1  # exclusive upper bound on s
        eval_start = max(0, eval_end - eval_lookback)
        if eval_end - eval_start < min_valid:
            continue
        best_w = None
        best_hit_rate = -1.0
        outcome_slice = realized_rel_1d_fwd[eval_start:eval_end]
        for w in candidate_windows:
            div_slice = div_arrays[w][eval_start:eval_end]
            valid = np.isfinite(div_slice) & np.isfinite(outcome_slice) & (outcome_slice != 0.0)
            if int(valid.sum()) < min_valid:
                continue
            hits = float((np.sign(div_slice[valid]) == np.sign(outcome_slice[valid])).mean())
            if hits > best_hit_rate:
                best_hit_rate = hits
                best_w = w
        if best_w is not None:
            chosen[i] = best_w

    chosen_series = pd.Series(chosen, index=index)
    divergence_chosen = pd.Series(
        [divergence_by_window[chosen[i]].iloc[i] for i in range(n)], index=index
    )
    ret2330_chosen = pd.Series(
        [ret2330_by_window[chosen[i]].iloc[i] for i in range(n)], index=index
    )
    return chosen_series, divergence_chosen, ret2330_chosen


def _apply_add_0050_instead_from_trigger(
    targets: pd.DataFrame,
    trigger: pd.Series,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Same redirect mechanism as evaluate_add_0050_instead_of_00631l_shadow.py's
    _apply_add_0050_instead (redirect_add_only variant), parameterized by an
    externally-supplied boolean trigger series instead of recomputing
    narrow_lead internally.
    """
    adjusted = targets.copy()
    events: list[dict[str, Any]] = []
    prev_631l = None
    for dt in targets.index:
        row = adjusted.loc[dt]
        current_631l = float(row["00631L.TW"])
        is_triggered = bool(trigger.get(dt, False))
        if prev_631l is not None and is_triggered and current_631l > prev_631l:
            redirect_amount = current_631l - prev_631l
            new_631l = prev_631l
            adjusted.loc[dt, "00631L.TW"] = new_631l
            adjusted.loc[dt, "0050.TW"] = float(row["0050.TW"]) + redirect_amount
            events.append({"date": str(dt.date()), "redirected_amount": round(redirect_amount, 6)})
        prev_631l = float(adjusted.loc[dt, "00631L.TW"])
    return adjusted, {"event_count": len(events), "events": events}


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
    eval_lookback: int,
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
    close_2330, close_0050 = _load_2330_0050_closes(db_path, prices.index)
    close_631l = prices["00631L.TW"]

    # Fixed-window (5-day) simplified trigger, identical rule shape to the
    # adaptive arm, used as the honest baseline (not daily_signal.py's exact
    # 3-condition narrow_lead, which has a window-specific magnitude gap --
    # see module docstring).
    div_fixed, ret2330_fixed = _divergence_series_for_window(close_2330, close_0050, FIXED_WINDOW, TSMC_0050_WEIGHT_ASSUMPTION)
    trigger_fixed = (ret2330_fixed > 0.0) & (div_fixed > 0.0)

    chosen_window, div_adaptive, ret2330_adaptive = select_adaptive_window(
        close_2330, close_631l, close_0050, prices.index, eval_lookback=eval_lookback
    )
    trigger_adaptive = (ret2330_adaptive > 0.0) & (div_adaptive > 0.0)

    fixed_targets, fixed_guard = _apply_add_0050_instead_from_trigger(baseline_targets, trigger_fixed)
    adaptive_targets, adaptive_guard = _apply_add_0050_instead_from_trigger(baseline_targets, trigger_adaptive)

    baseline_curve, baseline_execution = _simulate_targets(
        prices, baseline_targets, initial_value=initial_value,
        commission_rate=commission_rate, slippage_rate=slippage_rate, equity_etf_sell_tax=equity_etf_sell_tax,
    )
    fixed_curve, fixed_execution = _simulate_targets(
        prices, fixed_targets, initial_value=initial_value,
        commission_rate=commission_rate, slippage_rate=slippage_rate, equity_etf_sell_tax=equity_etf_sell_tax,
    )
    adaptive_curve, adaptive_execution = _simulate_targets(
        prices, adaptive_targets, initial_value=initial_value,
        commission_rate=commission_rate, slippage_rate=slippage_rate, equity_etf_sell_tax=equity_etf_sell_tax,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    fixed_metrics = _metrics(fixed_curve, initial_value)
    adaptive_metrics = _metrics(adaptive_curve, initial_value)

    window_counts = chosen_window.value_counts().to_dict()

    def _delta(m: dict[str, Any]) -> dict[str, Any]:
        return {
            "final_value": float(m["final_value"] - baseline_metrics["final_value"]),
            "sharpe_ratio": float(m["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]),
            "max_drawdown": float(m["max_drawdown"] - baseline_metrics["max_drawdown"]),
        }

    return {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": resolved_end},
        "fixed_window_days": FIXED_WINDOW,
        "fixed_event_count": fixed_guard["event_count"],
        "adaptive_event_count": adaptive_guard["event_count"],
        "adaptive_window_usage_counts": {str(k): int(v) for k, v in window_counts.items()},
        "baseline_metrics": baseline_metrics,
        "fixed_window_metrics": fixed_metrics,
        "adaptive_window_metrics": adaptive_metrics,
        "fixed_window_delta_vs_baseline": _delta(fixed_metrics),
        "adaptive_window_delta_vs_baseline": _delta(adaptive_metrics),
        "adaptive_minus_fixed": {
            "final_value": float(adaptive_metrics["final_value"] - fixed_metrics["final_value"]),
            "sharpe_ratio": float(adaptive_metrics["sharpe_ratio"] - fixed_metrics["sharpe_ratio"]),
            "max_drawdown": float(adaptive_metrics["max_drawdown"] - fixed_metrics["max_drawdown"]),
        },
        "dividend_coverage": coverage,
    }


def _summarize(windows: list[dict[str, Any]]) -> dict[str, Any]:
    if not windows:
        return {"window_count": 0, "decision": "blocked_no_windows"}
    adaptive_better = sum(
        1 for w in windows
        if w["adaptive_minus_fixed"]["final_value"] >= 0.0
        and w["adaptive_minus_fixed"]["sharpe_ratio"] >= 0.0
        and w["adaptive_minus_fixed"]["max_drawdown"] >= 0.0
    )
    total_adaptive_events = sum(w["adaptive_event_count"] for w in windows)
    total_fixed_events = sum(w["fixed_event_count"] for w in windows)
    return {
        "window_count": len(windows),
        "adaptive_beats_fixed_windows": adaptive_better,
        "total_adaptive_events": total_adaptive_events,
        "total_fixed_events": total_fixed_events,
        "decision": (
            "adaptive_window_candidate_for_shadow_queue"
            if adaptive_better == len(windows) and total_adaptive_events > 0
            else "research_only_not_promoted"
        ),
        "golden1_0531_unchanged": True,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    windows = [
        evaluate_window(
            label=label, start=start, end=end, bucket=bucket, db_path=db_path,
            initial_value=float(args.initial_value), commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate), equity_etf_sell_tax=float(args.equity_etf_sell_tax),
            eval_lookback=int(args.eval_lookback), ncf_panel_631l_path=panel_path,
        )
        for label, start, end, bucket, panel_path in _parse_windows(args.window)
    ]
    return {
        "report_type": "adaptive_lookback_narrow_lead_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "strategy": "Group A+ shadow only",
            "changes_latest_strategy_live_weights": False,
            "changes_golden1_0531": False,
            "changes_a2118_core_decision_rule": False,
            "mechanism": (
                "adaptive feature-estimation window (causal, from a fixed "
                "candidate set) for the narrow_lead trigger inside the "
                "ADD_0050_INSTEAD shadow guard, compared vs the fixed 5-day "
                "window -- A21.18's own regime rule is identical in both arms"
            ),
        },
        "params": {
            "candidate_windows": list(CANDIDATE_WINDOWS),
            "eval_lookback": int(args.eval_lookback),
            "fixed_window_days": FIXED_WINDOW,
            "initial_value": float(args.initial_value),
        },
        "summary": _summarize(windows),
        "windows": windows,
    }


def _history_path(history_dir: Path) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir / f"adaptive_lookback_narrow_lead_shadow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--eval-lookback", type=int, default=DEFAULT_EVAL_LOOKBACK)
    parser.add_argument("--window", action="append", default=[], help="label:start:end[:bucket[:ncf_panel_631l_path]]")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()

    std = OutputStandardizer("scripts.evaluate.evaluate_adaptive_lookback_narrow_lead_shadow")
    try:
        report = build_report(args)
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    history = _history_path(_resolve(args.history_dir))
    write_standard_output(payload, history)
    print(f"Adaptive lookback narrow_lead shadow: {_resolve(args.output)}")
    print(f"History: {history.resolve()}")
    if payload.get("success"):
        print(json.dumps(payload["data"]["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
