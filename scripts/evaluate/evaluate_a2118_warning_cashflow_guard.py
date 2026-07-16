#!/usr/bin/env python3
"""Backtest A21.18 extreme warning as a cashflow-only add guard.

Research-only. This does not change live targets, latest pointers, or execution
plans. The rule under test is: when the extreme warning is active, do not use
new/rebalance cash to increase 0050 or 00631L; leave blocked buy budget in cash.
Holds and reductions remain allowed.
"""

from __future__ import annotations

import argparse
import json
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
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _metric_delta


PANEL_2025_2026 = "results/ncf_00631l_panel_latest_20260707.csv"
PANEL_2017_2019 = "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2118_warning_cashflow_guard_latest.json"
DEFAULT_WINDOWS = [
    ("live_2024_2026", "2024-01-02", "latest", PANEL_2025_2026, "tuning_window"),
    ("active_2025_2026", "2025-01-02", "latest", PANEL_2025_2026, "tuning_window"),
    ("2017_bull", "2017-01-03", "2017-12-29", PANEL_2017_2019, "out_of_sample"),
    ("2018_correction", "2018-01-02", "2018-12-31", PANEL_2017_2019, "out_of_sample"),
    ("2019_recovery", "2019-01-02", "2019-12-31", PANEL_2017_2019, "out_of_sample"),
]


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _resolve_end_date(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    if max_dt is None:
        raise ValueError(f"No OHLCV rows found for {ticker}")
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def _load_panel(path: str | Path | None) -> pd.DataFrame | None:
    if not path:
        return None
    panel_path = _resolve(path)
    if not panel_path.exists():
        return None
    panel = pd.read_csv(panel_path, index_col="date", parse_dates=True, encoding="utf-8-sig")
    panel.index = pd.to_datetime(panel.index).normalize()
    return panel


def _warning_series(
    frame: pd.DataFrame,
    panel: pd.DataFrame | None,
    *,
    h20_max: float,
    mdd_min: float,
) -> pd.Series:
    values: list[bool] = []
    for dt, row in frame.iterrows():
        base_regime = str(row.get("base_regime", row.get("execution_regime", "")))
        active = False
        if base_regime == "golden1" and panel is not None and dt in panel.index:
            panel_row = panel.loc[dt]
            p20 = float(panel_row.get("prob_up_h20", 0.5) or 0.5)
            mdd = float(panel_row.get("prob_fwd_mdd_gt5_h20", 0.0) or 0.0)
            active = p20 <= h20_max and mdd >= mdd_min
        values.append(active)
    return pd.Series(values, index=frame.index, dtype=bool)


def _contribution_dates(index: pd.DatetimeIndex, frequency: str) -> set[pd.Timestamp]:
    if frequency == "none":
        return set()
    if frequency == "daily":
        return set(index)
    if frequency == "monthly":
        return {group.index[0] for _period, group in pd.DataFrame(index=index).groupby(index.to_period("M"))}
    if frequency == "weekly":
        return {group.index[0] for _period, group in pd.DataFrame(index=index).groupby(index.to_period("W-MON"))}
    raise ValueError("--contribution-frequency must be none, daily, monthly, or weekly")


def _targets_from_report(frame: pd.DataFrame, report: dict[str, Any]) -> pd.DataFrame:
    base_weights = {key: _normalize(dict(value)) for key, value in report["base_weights"].items()}
    golden = base_weights["golden1"]
    rows: list[dict[str, float]] = []
    for _dt, row in frame.iterrows():
        regime = str(row.get("execution_regime", "golden1"))
        weights = base_weights.get(regime, base_weights.get("group_a_plus_defensive", golden))
        rows.append({key: float(weights.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")})
    return pd.DataFrame(rows, index=frame.index)


def _simulate_cashflow_guard(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    warning: pd.Series,
    *,
    initial_value: float,
    contribution_amount: float,
    contribution_frequency: str,
    guarded: bool,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, Any]]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_key: tuple[float, ...] | None = None
    contribution_days = _contribution_dates(prices.index, contribution_frequency)
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    total_contributions = 0.0
    rebalance_count = 0
    blocked_buy_value = 0.0
    blocked_days = 0

    for dt, price_row in prices.iterrows():
        if dt in contribution_days and contribution_amount > 0.0:
            cash += float(contribution_amount)
            total_contributions += float(contribution_amount)
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        weights = _normalize(target_weights.loc[dt].to_dict())
        target_key = tuple(round(float(weights.get(key, 0.0)), 8) for key in (*TICKERS, "cash"))
        should_rebalance = target_key != current_key or dt in contribution_days
        if should_rebalance:
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            current_shares = dict(shares)
            net_value = gross_value
            target_values: dict[str, float] = {}
            cost = 0.0
            turnover = 0.0
            blocked_today = 0.0
            for _iteration in range(3):
                target_values = {ticker: net_value * weights.get(ticker, 0.0) for ticker in TICKERS}
                if guarded and bool(warning.loc[dt]):
                    for ticker in ("0050.TW", "00631L.TW"):
                        desired_shares = target_values[ticker] / max(float(price_row[ticker]), 1e-12)
                        if desired_shares > current_shares.get(ticker, 0.0):
                            capped_value = current_shares.get(ticker, 0.0) * float(price_row[ticker])
                            blocked_today += max(target_values[ticker] - capped_value, 0.0)
                            target_values[ticker] = capped_value
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
            if blocked_today > 0.0:
                blocked_buy_value += blocked_today / 3.0
                blocked_days += 1
        values.append(gross_value)
    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "total_contributions": float(total_contributions),
        "blocked_buy_value_estimate": float(blocked_buy_value),
        "blocked_days": int(blocked_days),
    }


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    bucket: str,
    db_path: Path,
    panel_path: str | None,
    initial_value: float,
    contribution_amount: float,
    contribution_frequency: str,
    h20_max: float,
    mdd_min: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> dict[str, Any]:
    end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        ncf_panel_631l_path=panel_path,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
    )
    panel = _load_panel(panel_path)
    prices, dividend_coverage = _load_total_return_prices(db_path, frame.index)
    targets = _targets_from_report(frame, report)
    warning = _warning_series(frame, panel, h20_max=h20_max, mdd_min=mdd_min)
    baseline_curve, baseline_execution = _simulate_cashflow_guard(
        prices,
        targets,
        warning,
        initial_value=initial_value,
        contribution_amount=contribution_amount,
        contribution_frequency=contribution_frequency,
        guarded=False,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    guarded_curve, guarded_execution = _simulate_cashflow_guard(
        prices,
        targets,
        warning,
        initial_value=initial_value,
        contribution_amount=contribution_amount,
        contribution_frequency=contribution_frequency,
        guarded=True,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    guarded_metrics = _metrics(guarded_curve, initial_value)
    warning_days = int(warning.sum())
    return {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": end},
        "baseline_metrics": baseline_metrics,
        "guarded_metrics": guarded_metrics,
        "delta_vs_baseline": _metric_delta(guarded_metrics, baseline_metrics),
        "baseline_execution": baseline_execution,
        "guarded_execution": guarded_execution,
        "warning_days": warning_days,
        "warning_dates": [str(dt.date()) for dt in warning[warning].index],
        "dividend_coverage": dividend_coverage,
        "ncf_panel": panel_path,
    }


def _parse_windows(raw: str | None) -> list[tuple[str, str, str, str | None, str]]:
    if not raw:
        return list(DEFAULT_WINDOWS)
    out: list[tuple[str, str, str, str | None, str]] = []
    for item in raw.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) not in (3, 4, 5):
            raise ValueError("--windows items must be label:start:end[:panel[:bucket]]")
        label, start, end = parts[:3]
        panel = parts[3] if len(parts) >= 4 and parts[3] else PANEL_2025_2026
        bucket = parts[4] if len(parts) >= 5 and parts[4] else "custom"
        out.append((label, start, end, panel, bucket))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--contribution-amount", type=float, default=10_000.0)
    parser.add_argument("--contribution-frequency", choices=("none", "daily", "monthly", "weekly"), default="monthly")
    parser.add_argument("--h20-max", type=float, default=0.22)
    parser.add_argument("--mdd-min", type=float, default=0.85)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--windows", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = _resolve(args.db)
    results = [
        evaluate_window(
            label=label,
            start=start,
            end=end,
            bucket=bucket,
            db_path=db_path,
            panel_path=panel,
            initial_value=float(args.initial_value),
            contribution_amount=float(args.contribution_amount),
            contribution_frequency=str(args.contribution_frequency),
            h20_max=float(args.h20_max),
            mdd_min=float(args.mdd_min),
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
        )
        for label, start, end, panel, bucket in _parse_windows(args.windows)
    ]
    passed = [
        item
        for item in results
        if item["delta_vs_baseline"]["delta_final_value"] >= 0
        and item["delta_vs_baseline"]["delta_sharpe_ratio"] >= 0
        and item["delta_vs_baseline"]["delta_max_drawdown"] >= 0
    ]
    payload = {
        "report_type": "a2118_warning_cashflow_guard",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": {
            "policy": "pause new 0050/00631L adds on extreme warning; no auto-sell",
            "warning_thresholds": {"h20_prob_up_max": float(args.h20_max), "prob_fwd_mdd_gt5_h20_min": float(args.mdd_min)},
            "cashflow": {
                "initial_value": float(args.initial_value),
                "contribution_amount": float(args.contribution_amount),
                "contribution_frequency": str(args.contribution_frequency),
            },
        },
        "summary": {
            "windows": len(results),
            "triple_pass_windows": len(passed),
            "all_windows_triple_pass": len(passed) == len(results),
        },
        "results": results,
    }
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"Triple-pass windows: {len(passed)}/{len(results)}")
    for item in results:
        delta = item["delta_vs_baseline"]
        print(
            f"{item['label']}: Δfinal={delta['delta_final_value']:,.0f}, "
            f"Δsharpe={delta['delta_sharpe_ratio']:.4f}, "
            f"warning_days={item['warning_days']}, "
            f"blocked_days={item['guarded_execution']['blocked_days']}"
        )


if __name__ == "__main__":
    main()
