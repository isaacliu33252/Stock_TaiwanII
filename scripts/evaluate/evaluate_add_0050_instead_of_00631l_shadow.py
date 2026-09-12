#!/usr/bin/env python3
"""Shadow evaluator for the user's TSMC-concentration-divergence proposal
(2026-08-09): when A21.18 is about to ADD 00631L exposure in golden1, and
TSMC concentration divergence shows "narrow lead" (TSMC up, ex-TSMC proxy
flat/down, TSMC clearly outrunning the broader 0050 basket), redirect that
increment into 0050.TW instead of 00631L.TW.

Research-only. Does NOT modify golden1_0531, a2118.py, or any live weight.
The regime-switching mechanism runs completely unchanged via the real
run_a2118(). This script only post-processes the resulting daily
target-weight series: on any day where 00631L.TW's target weight is
INCREASING versus the previous day AND narrow_lead is detected (price-only,
via group_a_plus.integrations.tsmc_concentration_divergence, exactly
reproducing daily_signal.py's existing narrow_lead boolean), the increment
is redirected into 0050.TW rather than 00631L.TW. Non-increasing days and
days without narrow_lead are untouched.

Two guard variants:
- redirect_add_only (default): redirect only the delta above the prior
  day's 00631L weight; anything already held stays in 00631L.
- redirect_full_golden1_631l: on a narrow_lead day, move the ENTIRE
  golden1 00631L target (not just the increment) into 0050 -- more
  aggressive, tests whether partial redirection is too timid to matter.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.integrations.tsmc_concentration_divergence import (
    TSMC_0050_WEIGHT_ASSUMPTION,
    classify_narrow_lead,
    ex_tsmc_return,
)
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_warning_cashflow_guard import _resolve_end_date
from tw_output_standard import OutputStandardizer, write_standard_output

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/add_0050_instead_of_00631l_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/add_0050_instead_of_00631l_shadow/history"
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


def _load_narrow_lead_series(db_path: Path, index: pd.DatetimeIndex) -> pd.Series:
    """Daily narrow_lead boolean, price-only, matching daily_signal.py exactly."""

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

    ret_0050_5d = close_0050.pct_change(5)
    ret_2330_5d = close_2330.pct_change(5)
    ex_ret_5d = pd.Series(
        [
            ex_tsmc_return(r0, r2, TSMC_0050_WEIGHT_ASSUMPTION)
            if pd.notna(r0) and pd.notna(r2)
            else None
            for r0, r2 in zip(ret_0050_5d, ret_2330_5d)
        ],
        index=index,
    )
    narrow_lead = pd.Series(
        [
            classify_narrow_lead(r2, r0, rex)
            for r2, r0, rex in zip(ret_2330_5d, ret_0050_5d, ex_ret_5d)
        ],
        index=index,
    )
    return narrow_lead


def _apply_add_0050_instead(
    targets: pd.DataFrame,
    narrow_lead: pd.Series,
    *,
    variant: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    adjusted = targets.copy()
    events: list[dict[str, Any]] = []
    prev_631l = None
    for dt in targets.index:
        row = adjusted.loc[dt]
        current_631l = float(row["00631L.TW"])
        is_narrow = bool(narrow_lead.get(dt, False))
        if prev_631l is not None and is_narrow and current_631l > prev_631l:
            if variant == "redirect_full_golden1_631l":
                redirect_amount = current_631l
                new_631l = 0.0
            else:
                redirect_amount = current_631l - prev_631l
                new_631l = prev_631l
            adjusted.loc[dt, "00631L.TW"] = new_631l
            adjusted.loc[dt, "0050.TW"] = float(row["0050.TW"]) + redirect_amount
            events.append(
                {
                    "date": str(dt.date()),
                    "redirected_amount": round(redirect_amount, 6),
                    "00631l_before_redirect": round(current_631l, 6),
                    "00631l_after_redirect": round(new_631l, 6),
                }
            )
        prev_631l = float(adjusted.loc[dt, "00631L.TW"])
    return adjusted, {
        "variant": variant,
        "event_count": len(events),
        "events": events,
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
    variant: str,
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
    narrow_lead = _load_narrow_lead_series(db_path, prices.index)

    adjusted_targets, guard_meta = _apply_add_0050_instead(baseline_targets, narrow_lead, variant=variant)

    baseline_curve, baseline_execution = _simulate_targets(
        prices, baseline_targets, initial_value=initial_value,
        commission_rate=commission_rate, slippage_rate=slippage_rate, equity_etf_sell_tax=equity_etf_sell_tax,
    )
    guarded_curve, guarded_execution = _simulate_targets(
        prices, adjusted_targets, initial_value=initial_value,
        commission_rate=commission_rate, slippage_rate=slippage_rate, equity_etf_sell_tax=equity_etf_sell_tax,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    guarded_metrics = _metrics(guarded_curve, initial_value)

    return {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": resolved_end},
        "narrow_lead_days": int(narrow_lead.sum()),
        "baseline_metrics": baseline_metrics,
        "guarded_metrics": guarded_metrics,
        "delta_vs_baseline": {
            "final_value": float(guarded_metrics["final_value"] - baseline_metrics["final_value"]),
            "sharpe_ratio": float(guarded_metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]),
            "max_drawdown": float(guarded_metrics["max_drawdown"] - baseline_metrics["max_drawdown"]),
            "transaction_cost": float(
                guarded_execution["transaction_cost"] - baseline_execution["transaction_cost"]
            ),
        },
        "guard": guard_meta,
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
    total_events = sum(w["guard"]["event_count"] for w in windows)
    return {
        "window_count": len(windows),
        "triple_pass_windows": len(pass_windows),
        "all_windows_triple_pass": len(pass_windows) == len(windows),
        "total_redirect_events": total_events,
        "decision": (
            "candidate_for_group_a_plus_shadow_queue"
            if len(pass_windows) == len(windows) and total_events > 0
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
            variant=str(args.variant), ncf_panel_631l_path=panel_path,
        )
        for label, start, end, bucket, panel_path in _parse_windows(args.window)
    ]
    return {
        "report_type": "add_0050_instead_of_00631l_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "strategy": "Group A+ shadow only",
            "changes_latest_strategy_live_weights": False,
            "changes_golden1_0531": False,
            "mechanism": "on narrow_lead + 00631L increasing, redirect increment (or full sleeve) to 0050.TW",
        },
        "params": {
            "initial_value": float(args.initial_value),
            "commission_rate": float(args.commission_rate),
            "slippage_rate": float(args.slippage_rate),
            "equity_etf_sell_tax": float(args.equity_etf_sell_tax),
            "variant": str(args.variant),
        },
        "summary": _summarize(windows),
        "windows": windows,
    }


def _history_path(history_dir: Path) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir / f"add_0050_instead_of_00631l_shadow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument(
        "--variant", choices=["redirect_add_only", "redirect_full_golden1_631l"], default="redirect_add_only"
    )
    parser.add_argument("--window", action="append", default=[], help="label:start:end[:bucket[:ncf_panel_631l_path]]")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()

    std = OutputStandardizer("scripts.evaluate.evaluate_add_0050_instead_of_00631l_shadow")
    try:
        report = build_report(args)
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    history = _history_path(_resolve(args.history_dir))
    write_standard_output(payload, history)
    print(f"Add-0050-instead shadow: {_resolve(args.output)}")
    print(f"History: {history.resolve()}")
    if payload.get("success"):
        print(json.dumps(payload["data"]["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
