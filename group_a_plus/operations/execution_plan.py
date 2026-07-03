"""Build a guarded A21.3 trade plan from the Group A++ workbook holdings."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY
from group_a_plus.operations.daily_signal import build_daily_signal
from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_WORKBOOK = PROJECT_ROOT / "taiwan_stock_20260619.xlsx"
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"
BOND_ETFS = {"00679B.TWO", "00751B.TWO"}


def _extract_code(value: object) -> str | None:
    text = "" if pd.isna(value) else str(value).upper()
    matches = re.findall(r"\b\d{4,5}[A-Z]?\b", text)
    return matches[-1] if matches else None


def _normalize_ticker(code: str) -> str:
    return f"{code}.TWO" if code in {"00679B", "00751B"} else f"{code}.TW"


def _parse_group_a_plus_holdings(frame: pd.DataFrame, row_label: str = "即時庫存") -> dict[str, int]:
    group_row = group_start = None
    for row_idx in range(len(frame)):
        for col_idx in range(frame.shape[1]):
            if str(frame.iloc[row_idx, col_idx]).strip() in {"Group A++", "Group A+"}:
                group_row, group_start = row_idx, col_idx
                break
        if group_start is not None:
            break
    if group_row is None or group_start is None:
        raise ValueError("Workbook has no Group A++ section")
    group_end = frame.shape[1]
    for col_idx in range(group_start + 1, frame.shape[1]):
        value = str(frame.iloc[group_row, col_idx]).strip()
        if value.startswith("Group "):
            group_end = col_idx
            break
    holdings_row = None
    for row_idx in range(len(frame)):
        if any(str(value).strip() == row_label for value in frame.iloc[row_idx].tolist()):
            holdings_row = row_idx
            break
    if holdings_row is None:
        raise ValueError(f"Workbook row not found: {row_label}")
    header_row = group_row + 1
    holdings: dict[str, int] = {}
    for col_idx in range(group_start, group_end):
        code = _extract_code(frame.iloc[header_row, col_idx])
        if code is None:
            continue
        value = frame.iloc[holdings_row, col_idx]
        holdings[_normalize_ticker(code)] = 0 if pd.isna(value) else int(round(float(value)))
    if not holdings:
        raise ValueError("No Group A++ holdings parsed from workbook")
    return holdings


def load_group_a_plus_holdings(path: Path, row_label: str = "即時庫存") -> dict[str, int]:
    return _parse_group_a_plus_holdings(pd.read_excel(path, sheet_name=0, header=None), row_label)


def _latest_prices(db_path: Path, tickers: list[str], as_of: str) -> dict[str, float]:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT ticker, arg_max(close, dt) AS latest_close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt <= ?
            GROUP BY ticker
            """,
            [*tickers, as_of],
        ).fetchdf()
    finally:
        con.close()
    return {
        str(row.ticker): float(row.latest_close)
        for row in rows.itertuples(index=False)
        if pd.notna(row.latest_close)
    }


def _build_trades(
    current_shares: dict[str, int],
    target_shares: dict[str, int],
    prices: dict[str, float],
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    trades: list[dict[str, Any]] = []
    totals = {"buy_notional": 0.0, "sell_notional": 0.0, "commission": 0.0, "sell_tax": 0.0, "slippage": 0.0}
    for ticker in sorted(set(current_shares) | set(target_shares)):
        current = int(current_shares.get(ticker, 0))
        target = int(target_shares.get(ticker, 0))
        delta = target - current
        if delta == 0:
            continue
        price = float(prices[ticker])
        notional = abs(delta) * price
        side = "buy" if delta > 0 else "sell"
        commission = notional * commission_rate
        slippage = notional * slippage_rate
        sell_tax_rate = 0.0 if ticker in BOND_ETFS else equity_etf_sell_tax
        sell_tax = notional * sell_tax_rate if side == "sell" else 0.0
        totals[f"{side}_notional"] += notional
        totals["commission"] += commission
        totals["slippage"] += slippage
        totals["sell_tax"] += sell_tax
        trades.append(
            {
                "ticker": ticker,
                "side": side,
                "current_shares": current,
                "target_shares": target,
                "delta_shares": delta,
                "price": price,
                "notional": notional,
                "commission": commission,
                "slippage": slippage,
                "sell_tax_rate": sell_tax_rate,
                "sell_tax": sell_tax,
                "estimated_cost": commission + slippage + sell_tax,
            }
        )
    totals["total_execution_cost"] = totals["commission"] + totals["slippage"] + totals["sell_tax"]
    totals["turnover_notional"] = totals["buy_notional"] + totals["sell_notional"]
    trades.sort(key=lambda row: (0 if row["side"] == "sell" else 1, row["ticker"]))
    return trades, totals


def _apply_execution_controls(
    current_shares: dict[str, int],
    theoretical_target_shares: dict[str, int],
    prices: dict[str, float],
    total_assets: float,
    min_trade_notional: float,
    min_weight_deviation: float,
    share_lot_size: int,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    if share_lot_size < 1:
        raise ValueError("share_lot_size must be at least 1")
    targets: dict[str, int] = {}
    suppressed: list[dict[str, Any]] = []
    for ticker in sorted(set(current_shares) | set(theoretical_target_shares)):
        current = int(current_shares.get(ticker, 0))
        theoretical = int(theoretical_target_shares.get(ticker, 0))
        controlled = theoretical if theoretical == 0 else (theoretical // share_lot_size) * share_lot_size
        price = float(prices.get(ticker, 0.0))
        delta_notional = abs(controlled - current) * price
        weight_deviation = delta_notional / total_assets if total_assets > 0 else 0.0
        if controlled == current:
            targets[ticker] = current
            continue
        liquidation = theoretical == 0 and current != 0
        reasons = []
        if controlled != theoretical:
            reasons.append(f"rounded_to_{share_lot_size}_share_lot")
        if not liquidation and delta_notional < min_trade_notional:
            reasons.append("below_min_trade_notional")
        if not liquidation and weight_deviation < min_weight_deviation:
            reasons.append("inside_weight_deviation_band")
        if reasons and ("below_min_trade_notional" in reasons or "inside_weight_deviation_band" in reasons):
            targets[ticker] = current
            suppressed.append(
                {
                    "ticker": ticker,
                    "current_shares": current,
                    "theoretical_target_shares": theoretical,
                    "controlled_target_before_band": controlled,
                    "delta_notional": delta_notional,
                    "weight_deviation": weight_deviation,
                    "reasons": reasons,
                }
            )
        else:
            targets[ticker] = controlled
    return targets, suppressed


def _apply_buy_staging(
    current_shares: dict[str, int],
    target_shares: dict[str, int],
    prices: dict[str, float],
    max_initial_buy_fraction: float,
    min_staged_buy_notional: float,
    share_lot_size: int,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    if share_lot_size < 1:
        raise ValueError("share_lot_size must be at least 1")
    if not 0.0 < max_initial_buy_fraction <= 1.0:
        raise ValueError("max_initial_buy_fraction must be in (0, 1]")
    if max_initial_buy_fraction >= 1.0:
        return dict(target_shares), []

    staged_targets = dict(target_shares)
    staged: list[dict[str, Any]] = []
    for ticker in sorted(set(current_shares) | set(target_shares)):
        current = int(current_shares.get(ticker, 0))
        target = int(target_shares.get(ticker, current))
        delta = target - current
        if delta <= 0:
            continue
        price = float(prices.get(ticker, 0.0))
        buy_notional = delta * price
        if buy_notional < min_staged_buy_notional:
            continue

        staged_delta = int(delta * max_initial_buy_fraction)
        staged_delta = max(share_lot_size, (staged_delta // share_lot_size) * share_lot_size)
        staged_delta = min(delta, staged_delta)
        staged_target = current + staged_delta
        if staged_target >= target:
            continue

        staged_targets[ticker] = staged_target
        staged.append(
            {
                "ticker": ticker,
                "current_shares": current,
                "full_target_shares": target,
                "staged_target_shares": staged_target,
                "full_delta_shares": delta,
                "staged_delta_shares": staged_delta,
                "deferred_delta_shares": target - staged_target,
                "price": price,
                "full_buy_notional": buy_notional,
                "staged_buy_notional": staged_delta * price,
                "deferred_buy_notional": (target - staged_target) * price,
                "max_initial_buy_fraction": max_initial_buy_fraction,
                "reason": "large_buy_staged",
            }
        )
    return staged_targets, staged


def build_execution_plan(
    workbook: Path,
    requested_as_of: str,
    cash_balance: float,
    max_business_stale_days: int,
    db_path: Path,
    manifest_path: Path,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
    max_turnover_ratio: float = 0.5,
    commission_discount: float = 1.0,
    min_trade_notional: float = 5_000.0,
    min_weight_deviation: float = 0.005,
    share_lot_size: int = 1,
    max_initial_buy_fraction: float = 0.4,
    min_staged_buy_notional: float = 20_000.0,
) -> dict[str, Any]:
    if not 0.0 <= commission_discount <= 1.0:
        raise ValueError("commission_discount must be between 0 and 1")
    holdings = load_group_a_plus_holdings(workbook)
    held_tickers = sorted(ticker for ticker, shares in holdings.items() if shares != 0)
    held_prices = _latest_prices(db_path, held_tickers, requested_as_of)
    unknown_prices = sorted(set(held_tickers) - set(held_prices))
    holdings_market_value = sum(holdings[ticker] * held_prices.get(ticker, 0.0) for ticker in holdings)
    total_assets = holdings_market_value + cash_balance
    if total_assets <= 0.0:
        raise ValueError("Current holdings plus cash must have positive value")
    signal = build_daily_signal(
        requested_as_of,
        total_assets,
        max_business_stale_days,
        730,
        db_path,
        manifest_path,
    )
    all_prices = {**held_prices, **signal["latest_prices"]}
    theoretical_target_shares = {
        **{ticker: 0 for ticker in holdings},
        **{ticker: int(shares) for ticker, shares in signal["reference_target_shares_before_cost"].items()},
    }
    target_shares, suppressed_trades = _apply_execution_controls(
        holdings,
        theoretical_target_shares,
        all_prices,
        total_assets,
        min_trade_notional,
        min_weight_deviation,
        share_lot_size,
    )
    target_shares, staged_buys = _apply_buy_staging(
        holdings,
        target_shares,
        all_prices,
        max_initial_buy_fraction,
        min_staged_buy_notional,
        share_lot_size,
    )
    missing_trade_prices = sorted(
        ticker
        for ticker in set(holdings) | set(target_shares)
        if holdings.get(ticker, 0) != target_shares.get(ticker, 0) and ticker not in all_prices
    )
    trades: list[dict[str, Any]] = []
    totals = {"buy_notional": 0.0, "sell_notional": 0.0, "total_execution_cost": 0.0, "turnover_notional": 0.0}
    if not missing_trade_prices:
        trades, totals = _build_trades(
            holdings,
            target_shares,
            all_prices,
            commission_rate * commission_discount,
            slippage_rate,
            equity_etf_sell_tax,
        )
    estimated_cash_after_execution = (
        cash_balance
        + totals["sell_notional"]
        - totals["buy_notional"]
        - totals["total_execution_cost"]
    )
    turnover_ratio = totals["turnover_notional"] / total_assets
    guard_reasons = list(signal["execution_guard_reasons"])
    if unknown_prices:
        guard_reasons.append(f"missing current-holding prices: {unknown_prices}")
    if missing_trade_prices:
        guard_reasons.append(f"missing trade prices: {missing_trade_prices}")
    if estimated_cash_after_execution < 0.0:
        guard_reasons.append(f"estimated cash after execution is negative: {estimated_cash_after_execution:.2f}")
    if turnover_ratio > max_turnover_ratio:
        guard_reasons.append(
            f"turnover ratio {turnover_ratio:.2%} exceeds automatic limit {max_turnover_ratio:.2%}"
        )
    execution_allowed = bool(signal["execution_allowed"] and not guard_reasons)
    return {
        "plan_version": 2,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "strategy_id": signal["strategy_id"],
        "requested_as_of_date": requested_as_of,
        "actual_data_date": signal["actual_data_date"],
        "workbook": str(workbook),
        "holdings_row": "即時庫存",
        "current_holdings": holdings,
        "current_cash_input": cash_balance,
        "cash_assumption": "workbook has no cash field; using explicit --cash-balance input",
        "current_holdings_market_value": holdings_market_value,
        "current_total_assets": total_assets,
        "current_prices": all_prices,
        "execution_regime": signal["execution_regime"],
        "target_weights": signal["target_weights"],
        "theoretical_target_shares": theoretical_target_shares,
        "target_shares": target_shares,
        "suppressed_trades": suppressed_trades,
        "staged_buys": staged_buys,
        "execution_controls": {
            "published_commission_rate": commission_rate,
            "commission_discount": commission_discount,
            "effective_commission_rate": commission_rate * commission_discount,
            "min_trade_notional": min_trade_notional,
            "min_weight_deviation": min_weight_deviation,
            "share_lot_size": share_lot_size,
            "forced_liquidations_bypass_bands": True,
            "max_initial_buy_fraction": max_initial_buy_fraction,
            "min_staged_buy_notional": min_staged_buy_notional,
            "buy_staging_applies_to_sells": False,
        },
        "trades": trades,
        "execution_summary": {
            **totals,
            "estimated_cash_after_execution": estimated_cash_after_execution,
            "turnover_ratio": turnover_ratio,
            "max_automatic_turnover_ratio": max_turnover_ratio,
        },
        "planning_status": "ready" if execution_allowed else "manual_review_required",
        "manual_confirmation_required": not execution_allowed,
        "execution_allowed": execution_allowed,
        "execution_guard_reasons": guard_reasons,
        "source_live_signal": signal,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--as-of", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--cash-balance", type=float, default=0.0)
    parser.add_argument("--max-business-stale-days", type=int, default=3)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--max-turnover-ratio", type=float, default=0.5)
    parser.add_argument("--commission-discount", type=float, default=1.0)
    parser.add_argument("--min-trade-notional", type=float, default=5000.0)
    parser.add_argument("--min-weight-deviation", type=float, default=0.005)
    parser.add_argument("--share-lot-size", type=int, default=1)
    parser.add_argument("--max-initial-buy-fraction", type=float, default=0.4)
    parser.add_argument("--min-staged-buy-notional", type=float, default=20_000.0)
    parser.add_argument("--output", default="results/group_a_plus_execution_plan_v2.json")
    parser.add_argument("--latest-pointer", default=str(DEFAULT_EXECUTION_PLAN))
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.operations.execution_plan")
    try:
        plan = build_execution_plan(
            Path(args.workbook),
            args.as_of,
            args.cash_balance,
            args.max_business_stale_days,
            Path(args.db),
            Path(args.manifest),
            args.commission_rate,
            args.slippage_rate,
            args.equity_etf_sell_tax,
            args.max_turnover_ratio,
            args.commission_discount,
            args.min_trade_notional,
            args.min_weight_deviation,
            args.share_lot_size,
            args.max_initial_buy_fraction,
            args.min_staged_buy_notional,
        )
        payload = std.success(plan)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    write_standard_output(payload, args.latest_pointer)
    print(f"Execution plan: {Path(args.output).resolve()}")
    print(f"Latest pointer: {Path(args.latest_pointer).resolve()}")


if __name__ == "__main__":
    main()
