"""Generate an execution-guarded daily signal from the active latest strategy."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY
from group_a_plus.runners.latest import run_latest
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_LIVE_SIGNAL = Path("report/group_a_plus/latest/live_signal.json")
OPTIONAL_SOURCE_SPECS = {
    "institutional_0050": ("institutional_data", "ticker = '0050.TW'", 3),
    "margin_0050": ("margin_data", "ticker = '0050.TW'", 3),
    "market_margin": ("market_margin_data", "1 = 1", 3),
    "tdcc_0050": ("shareholding_distribution", "stock_id = '0050'", 10),
    "foreign_shareholding_0050": ("foreign_shareholding_data", "ticker = '0050.TW'", 3),
    "short_balance_0050": ("short_sale_balance_data", "ticker = '0050.TW'", 3),
    "securities_lending_0050": ("securities_lending_data", "ticker = '0050.TW'", 3),
    "day_trading_0050": ("day_trading_data", "ticker = '0050.TW'", 3),
    "dealer_tx": ("dealer_futures_data", "futures_id = 'TX' AND is_after_hour = 0", 3),
    "dealer_txo": ("dealer_options_data", "option_id = 'TXO' AND is_after_hour = 0", 3),
    "foreign_tx_oi": (
        "derivative_institutional_data",
        "market = 'futures' AND product_id = 'TX' AND institutional_investors = '外資'",
        3,
    ),
    "foreign_txo_oi": (
        "derivative_institutional_data",
        "market = 'options' AND product_id = 'TXO' AND institutional_investors = '外資'",
        3,
    ),
}
TAIWAN_MARKET_HOLIDAYS = {
    pd.Timestamp("2026-06-19"),  # Dragon Boat Festival market holiday
}


def _business_days_between(start: str | pd.Timestamp, end: str | pd.Timestamp) -> int:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    if end_ts <= start_ts:
        return 0
    weekdays = pd.bdate_range(start_ts + pd.Timedelta(days=1), end_ts)
    return int(sum(day.normalize() not in TAIWAN_MARKET_HOLIDAYS for day in weekdays))


def _resolve_weights(report: dict[str, Any], regime: str) -> dict[str, float]:
    weights = report.get("weights") or {}
    if regime in weights:
        return _normalize(dict(weights[regime]))
    aliases = {
        "golden1": "golden1_0531_1m",
        "group_a_plus_defensive": "group_a_plus_defensive_1m",
    }
    alias = aliases.get(regime)
    if alias and alias in weights:
        return _normalize(dict(weights[alias]))
    raise ValueError(f"No target weights for execution regime: {regime}")


def _source_freshness(db_path: Path, requested_as_of: pd.Timestamp) -> dict[str, Any]:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {
            row[0]
            for row in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
        }
        ticker_rows = con.execute(
            """
            SELECT ticker, max(dt) AS latest_dt, arg_max(close, dt) AS latest_close
            FROM ohlcv
            WHERE ticker IN (?, ?, ?, ?) AND dt <= ?
            GROUP BY ticker
            ORDER BY ticker
            """,
            [*TICKERS, str(requested_as_of.date())],
        ).fetchdf()
        optional = {}
        for source, (table, where, max_stale) in OPTIONAL_SOURCE_SPECS.items():
            if table not in tables:
                optional[source] = {
                    "table": table,
                    "exists": False,
                    "latest_date": None,
                    "business_stale_days": None,
                    "max_business_stale_days": max_stale,
                    "status": "block",
                }
                continue
            latest = con.execute(
                f"SELECT max(dt) FROM {table} WHERE {where} AND dt <= ?",
                [str(requested_as_of.date())],
            ).fetchone()[0]
            stale_days = _business_days_between(latest, requested_as_of) if latest is not None else None
            optional[source] = {
                "table": table,
                "exists": True,
                "latest_date": str(latest) if latest is not None else None,
                "business_stale_days": stale_days,
                "max_business_stale_days": max_stale,
                "status": "ok" if stale_days is not None and stale_days <= max_stale else "block",
            }
    finally:
        con.close()
    ticker_dates = {
        str(row.ticker): str(pd.Timestamp(row.latest_dt).date())
        for row in ticker_rows.itertuples(index=False)
        if pd.notna(row.latest_dt)
    }
    latest_prices = {
        str(row.ticker): float(row.latest_close)
        for row in ticker_rows.itertuples(index=False)
        if pd.notna(row.latest_close)
    }
    return {
        "ohlcv_by_ticker": ticker_dates,
        "latest_prices": latest_prices,
        "optional_sources": optional,
    }


def build_daily_signal(
    requested_as_of: str,
    portfolio_value: float,
    max_business_stale_days: int,
    lookback_days: int,
    db_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    as_of = pd.Timestamp(requested_as_of).normalize()
    start = str((as_of - pd.Timedelta(days=lookback_days)).date())
    report, frame = run_latest(start, str(as_of.date()), portfolio_value, db_path, manifest_path)
    if frame.empty:
        raise RuntimeError("Latest strategy runner returned an empty frame")
    actual = pd.Timestamp(frame.index[-1]).normalize()
    regime_column = "execution_regime" if "execution_regime" in frame.columns else "regime"
    regimes = frame[regime_column].astype(str)
    execution_regime = str(regimes.iloc[-1])
    base_regime = str(frame["base_regime"].iloc[-1]) if "base_regime" in frame.columns else execution_regime
    target_weights = _resolve_weights(report, execution_regime)
    source_freshness = _source_freshness(db_path, as_of)
    ticker_dates = source_freshness["ohlcv_by_ticker"]
    latest_prices = source_freshness["latest_prices"]
    optional_blocks = sorted(
        source
        for source, detail in source_freshness["optional_sources"].items()
        if detail["status"] == "block"
    )
    missing_tickers = sorted(set(TICKERS) - set(ticker_dates))
    ticker_misaligned = sorted(
        ticker for ticker, date in ticker_dates.items() if pd.Timestamp(date).normalize() != actual
    )
    business_stale = _business_days_between(actual, as_of)
    calendar_stale = max(int((as_of - actual).days), 0)
    execution_allowed = (
        report["status"] == "active"
        and
        business_stale <= max_business_stale_days
        and not missing_tickers
        and not ticker_misaligned
        and not optional_blocks
    )
    changed = regimes.ne(regimes.shift())
    transition_date = pd.Timestamp(changed[changed].index[-1]).normalize()
    changed_today = bool(transition_date == actual)
    reason = {
        "golden1": "A20.7 formal defensive state is inactive",
        "group_a_plus_defensive": "A20.7 defensive state is active and recovery ramp has not triggered",
        "group_a_plus_recovery": "A20.7 remains defensive; MA75 gap and five-day momentum triggered recovery ramp",
    }.get(execution_regime, "active strategy regime")
    latest_row = frame.iloc[-1]
    target_shares = {
        ticker: (
            int((portfolio_value * target_weights.get(ticker, 0.0)) // latest_prices[ticker])
            if latest_prices.get(ticker, 0.0) > 0.0
            else 0
        )
        for ticker in TICKERS
    }
    target_market_values = {
        ticker: target_shares[ticker] * latest_prices.get(ticker, 0.0)
        for ticker in TICKERS
    }
    estimated_cash_after_rounding = portfolio_value - sum(target_market_values.values())
    return {
        "signal_version": 2,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "strategy_id": report["active_strategy_id"],
        "strategy_status": report["status"],
        "requested_as_of_date": str(as_of.date()),
        "actual_data_date": str(actual.date()),
        "business_stale_days": business_stale,
        "calendar_stale_days": calendar_stale,
        "max_business_stale_days": max_business_stale_days,
        "execution_allowed": execution_allowed,
        "execution_guard_reasons": [
            reason
            for condition, reason in (
                (business_stale > max_business_stale_days, f"OHLCV is {business_stale} business days stale"),
                (bool(missing_tickers), f"missing OHLCV tickers: {missing_tickers}"),
                (bool(ticker_misaligned), f"OHLCV dates do not align: {ticker_misaligned}"),
                (bool(optional_blocks), f"required strategy sources are stale or missing: {optional_blocks}"),
                (report["status"] != "active", f"strategy status is {report['status']}; shadow signals are non-executable"),
            )
            if condition
        ],
        "base_regime": base_regime,
        "execution_regime": execution_regime,
        "regime_reason": reason,
        "last_transition_date": str(transition_date.date()),
        "strategy_transition_today": changed_today,
        "action": "rebalance_to_target" if changed_today else "hold_or_align_to_target",
        "target_weights": target_weights,
        "target_values": {key: portfolio_value * value for key, value in target_weights.items()},
        "reference_target_shares_before_cost": target_shares,
        "reference_target_market_values": target_market_values,
        "estimated_cash_after_rounding_before_cost": estimated_cash_after_rounding,
        "latest_prices": latest_prices,
        "portfolio_value_input": float(portfolio_value),
        "latest_features": {
            "ma_gap": float(latest_row.get("ma_gap", 0.0)),
            "drawdown": float(latest_row.get("drawdown", 0.0)),
            "exit_momentum_5d": float(latest_row.get("exit_momentum", 0.0)),
            "chip_score": int(latest_row.get("chip_score", 0)),
            "derivative_score": int(latest_row.get("derivative_score", 0)),
            "total_risk_score": int(latest_row.get("total_risk_score", 0)),
            "tail_risk_score": int(latest_row.get("tail_risk_score", 0)),
        },
        "data_freshness": source_freshness,
        "manifest": str(manifest_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--portfolio-value", type=float, default=1_000_000.0)
    parser.add_argument("--max-business-stale-days", type=int, default=3)
    parser.add_argument("--lookback-days", type=int, default=730)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--output", default="results/group_a_plus_live_signal_v2.json")
    parser.add_argument("--latest-pointer", default=str(DEFAULT_LIVE_SIGNAL))
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.operations.daily_signal")
    try:
        signal = build_daily_signal(
            args.as_of,
            args.portfolio_value,
            args.max_business_stale_days,
            args.lookback_days,
            Path(args.db),
            Path(args.manifest),
        )
        payload = std.success(signal)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    write_standard_output(payload, args.latest_pointer)
    print(f"Live signal: {Path(args.output).resolve()}")
    print(f"Latest pointer: {Path(args.latest_pointer).resolve()}")


if __name__ == "__main__":
    main()
