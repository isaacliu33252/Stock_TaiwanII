#!/usr/bin/env python3
"""Shadow evaluator: does adding 00646.TW (Yuanta S&P 500, USD-hedged) as an
extra sleeve carved out of the 0050.TW allocation improve Group A+?

Research-only. Does NOT modify golden1_0531, a2118.py, or any live weight.
The regime-switching mechanism (switch rule, NCF late-bull hedge, defensive/
recovery baskets) runs completely unchanged via the real run_a2118(). This
script only post-processes the resulting daily target-weight series: on any
day where the model holds 0050.TW, it redirects `carve_fraction` of that
sleeve into 00646.TW, then re-simulates a cost-aware curve with the new
5-ticker set and compares metrics against the unmodified baseline.

Rationale for carving out of 0050 specifically (not 00631L/00632R/00679B):
0050 and 00646 are both "core equity beta" sleeves -- 0050 is Taiwan/TAIEX-50
(TSMC-concentrated), 00646 is USD-hedged S&P 500. Splitting between them is a
geographic-diversification decision, not a leverage or hedge decision, so it
should not interact with the leveraged (00631L) / inverse (00632R) / bond
(00679B) sleeves that the regime table already manages deliberately.

Caveats:
- 00646.TW data in this DB only goes back to 2020-01-02 (its IPO era), so
  windows before that are not testable.
- No dividend/distribution rows found for 00646.TW in this DB -- prices used
  as close-only, not total-return. If 00646 pays meaningful distributions
  this understates its true return slightly (same caveat applies equally to
  the baseline's 0050 allocation it's compared against, since 0050 uses
  total-return prices via _load_total_return_prices while 00646 here does
  not -- see _load_prices_close_only()).
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
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_warning_cashflow_guard import _resolve_end_date
from tw_output_standard import OutputStandardizer, write_standard_output

SP500_TICKER = "00646.TW"
EXTENDED_TICKERS = (*TICKERS, SP500_TICKER)

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/00646_sp500_addition_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/00646_sp500_addition_shadow/history"
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
DEFAULT_CARVE_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)


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


def _carve_sp500(targets: pd.DataFrame, carve_fraction: float) -> pd.DataFrame:
    """Redirect carve_fraction of the 0050.TW sleeve into 00646.TW, every day.

    Does not touch 00631L.TW/00632R.TW/00679B.TW/cash -- only decomposes
    whatever weight the (unmodified) regime table already assigned to
    0050.TW on that day.
    """

    carved = targets.copy()
    sp500_slice = carved["0050.TW"] * float(carve_fraction)
    carved["0050.TW"] = carved["0050.TW"] - sp500_slice
    carved[SP500_TICKER] = sp500_slice
    return carved


def _load_prices_extended(db_path: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Total-return prices for TICKERS plus close-only prices for 00646.TW.

    00646.TW has no recorded dividend rows in this DB (checked 2026-08-09),
    so it's loaded as close-only rather than through
    _load_total_return_prices(), which would raise on the missing-dividend
    column semantics mismatch it isn't actually designed for a 5th ticker.
    """

    total_return, coverage = _load_total_return_prices(db_path, index)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker = ? AND dt BETWEEN ? AND ? ORDER BY dt",
            [SP500_TICKER, str(index[0].date()), str(index[-1].date())],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    sp500_close = rows.set_index("dt")["close"].reindex(index)
    if sp500_close.isna().any():
        raise RuntimeError(f"Missing {SP500_TICKER} close prices for requested window")
    total_return[SP500_TICKER] = sp500_close
    return total_return, coverage


def _simulate_targets(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[pd.Series, dict[str, Any]]:
    tickers = EXTENDED_TICKERS
    shares = {ticker: 0.0 for ticker in tickers}
    cash = float(initial_value)
    current_key: tuple[float, ...] | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in tickers)
        weights = _normalize(target_weights.loc[dt].to_dict())
        target_key = tuple(round(float(weights.get(key, 0.0)), 8) for key in (*tickers, "cash"))
        cost = 0.0
        turnover = 0.0
        if target_key != current_key:
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in tickers}
            net_value = gross_value
            target_values: dict[str, float] = {}
            for _iteration in range(3):
                target_values = {ticker: net_value * weights.get(ticker, 0.0) for ticker in tickers}
                cost, turnover = _trade_cost_extended(
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
                for ticker in tickers
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


def _trade_cost_extended(
    current_values: dict[str, float],
    target_values: dict[str, float],
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[float, float]:
    cost = 0.0
    turnover = 0.0
    for ticker in EXTENDED_TICKERS:
        trade = float(target_values.get(ticker, 0.0)) - float(current_values.get(ticker, 0.0))
        turnover += abs(trade)
        if trade > 0.0:
            cost += trade * (commission_rate + slippage_rate)
        elif trade < 0.0:
            tax = 0.0 if ticker == "00679B.TWO" else equity_etf_sell_tax
            cost += abs(trade) * (commission_rate + slippage_rate + tax)
    return cost, turnover


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
    carve_fractions: tuple[float, ...],
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
    prices, coverage = _load_prices_extended(db_path, frame.index)
    baseline_targets = _targets_from_report(frame, report).reindex(prices.index).ffill()

    cells = []
    for carve_fraction in carve_fractions:
        carved_targets = _carve_sp500(baseline_targets, carve_fraction)
        curve, execution = _simulate_targets(
            prices,
            carved_targets,
            initial_value=initial_value,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
        )
        metrics = _metrics(curve, initial_value)
        cells.append(
            {
                "carve_fraction": float(carve_fraction),
                "metrics": metrics,
                "execution": execution,
            }
        )

    baseline_cell = cells[0]
    for cell in cells[1:]:
        cell["delta_vs_baseline"] = {
            "final_value": float(cell["metrics"]["final_value"] - baseline_cell["metrics"]["final_value"]),
            "sharpe_ratio": float(cell["metrics"]["sharpe_ratio"] - baseline_cell["metrics"]["sharpe_ratio"]),
            "max_drawdown": float(cell["metrics"]["max_drawdown"] - baseline_cell["metrics"]["max_drawdown"]),
            "transaction_cost": float(
                cell["execution"]["transaction_cost"] - baseline_cell["execution"]["transaction_cost"]
            ),
        }

    return {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": resolved_end},
        "cells": cells,
        "dividend_coverage": coverage,
    }


def _summarize(windows: list[dict[str, Any]], carve_fractions: tuple[float, ...]) -> dict[str, Any]:
    if not windows:
        return {"window_count": 0, "decision": "blocked_no_windows"}
    per_fraction: dict[float, dict[str, Any]] = {}
    for carve_fraction in carve_fractions:
        if carve_fraction == 0.0:
            continue
        pass_windows = 0
        for window in windows:
            cell = next(c for c in window["cells"] if c["carve_fraction"] == carve_fraction)
            delta = cell.get("delta_vs_baseline")
            if delta is None:
                continue
            if delta["final_value"] >= 0.0 and delta["sharpe_ratio"] >= 0.0 and delta["max_drawdown"] >= 0.0:
                pass_windows += 1
        per_fraction[carve_fraction] = {
            "triple_pass_windows": pass_windows,
            "window_count": len(windows),
            "all_windows_triple_pass": pass_windows == len(windows),
        }
    best_fraction = max(
        per_fraction, key=lambda f: per_fraction[f]["triple_pass_windows"], default=None
    )
    return {
        "window_count": len(windows),
        "carve_fraction_results": per_fraction,
        "best_carve_fraction": best_fraction,
        "decision": (
            "candidate_for_group_a_plus_shadow_queue"
            if best_fraction is not None and per_fraction[best_fraction]["all_windows_triple_pass"]
            else "research_only_not_promoted"
        ),
        "golden1_0531_unchanged": True,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    carve_fractions = tuple(float(x) for x in args.carve_fractions)
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
            carve_fractions=carve_fractions,
            ncf_panel_631l_path=panel_path,
        )
        for label, start, end, bucket, panel_path in _parse_windows(args.window)
    ]
    return {
        "report_type": "00646_sp500_addition_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "strategy": "Group A+ shadow only",
            "changes_latest_strategy_live_weights": False,
            "changes_golden1_0531": False,
            "mechanism": "carve_fraction of 0050.TW sleeve redirected into 00646.TW daily, regime table unchanged",
        },
        "params": {
            "initial_value": float(args.initial_value),
            "commission_rate": float(args.commission_rate),
            "slippage_rate": float(args.slippage_rate),
            "equity_etf_sell_tax": float(args.equity_etf_sell_tax),
            "carve_fractions": list(carve_fractions),
        },
        "summary": _summarize(windows, carve_fractions),
        "windows": windows,
    }


def _history_path(history_dir: Path) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    return history_dir / f"00646_sp500_addition_shadow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument(
        "--carve-fractions",
        nargs="+",
        default=[str(f) for f in DEFAULT_CARVE_FRACTIONS],
    )
    parser.add_argument("--window", action="append", default=[], help="label:start:end[:bucket[:ncf_panel_631l_path]]")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    args = parser.parse_args()

    std = OutputStandardizer("scripts.evaluate.evaluate_00646_sp500_addition_shadow")
    try:
        report = build_report(args)
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    history = _history_path(_resolve(args.history_dir))
    write_standard_output(payload, history)
    print(f"00646 S&P500 addition shadow: {_resolve(args.output)}")
    print(f"History: {history.resolve()}")
    if payload.get("success"):
        print(json.dumps(payload["data"]["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
