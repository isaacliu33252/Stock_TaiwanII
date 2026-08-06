"""Broker-neutral rebalance planning for GroupA+ live target weights.

This module intentionally stops before broker execution. It converts the
already-produced `daily_signal.py` target weights into auditable buy/sell
instructions using current holdings, prices, and cash. Broker-specific order
placement belongs in a later adapter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


CASH_KEY = "cash"


@dataclass(frozen=True)
class RebalanceConfig:
    min_trade_value: float = 1_000.0
    default_lot_size: int = 1
    lot_sizes: dict[str, int] = field(default_factory=dict)
    cash_key: str = CASH_KEY

    def lot_size_for(self, ticker: str) -> int:
        lot_size = int(self.lot_sizes.get(ticker, self.default_lot_size))
        if lot_size <= 0:
            raise ValueError(f"lot size must be positive for {ticker}: {lot_size}")
        return lot_size


@dataclass(frozen=True)
class PlannedOrder:
    ticker: str
    side: str
    shares: int
    price: float
    trade_value: float
    current_weight: float
    target_weight: float
    value_delta: float

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "side": self.side,
            "shares": self.shares,
            "price": self.price,
            "trade_value": self.trade_value,
            "current_weight": self.current_weight,
            "target_weight": self.target_weight,
            "value_delta": self.value_delta,
        }


@dataclass(frozen=True)
class RebalancePlan:
    strategy_id: str
    signal_asof: str
    portfolio_value: float
    target_weights: dict[str, float]
    current_values: dict[str, float]
    target_values: dict[str, float]
    orders: list[PlannedOrder]
    skipped: list[dict[str, Any]]
    warnings: list[str]
    cash_before: float
    cash_after_planned: float
    target_cash: float

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "signal_asof": self.signal_asof,
            "portfolio_value": self.portfolio_value,
            "target_weights": dict(self.target_weights),
            "current_values": dict(self.current_values),
            "target_values": dict(self.target_values),
            "orders": [order.to_json_dict() for order in self.orders],
            "skipped": list(self.skipped),
            "warnings": list(self.warnings),
            "cash_before": self.cash_before,
            "cash_after_planned": self.cash_after_planned,
            "target_cash": self.target_cash,
        }


def _clean_float(value: Any, *, field_name: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric: {value!r}") from exc
    if not math.isfinite(out):
        raise ValueError(f"{field_name} must be finite: {value!r}")
    return out


def _round_shares(raw_shares: float, lot_size: int) -> int:
    if raw_shares <= 0:
        return 0
    return int(math.floor(raw_shares / lot_size) * lot_size)


def _resolve_prices(daily_signal: dict[str, Any], prices: dict[str, float] | None) -> dict[str, float]:
    raw_prices = prices if prices is not None else dict(daily_signal.get("latest_prices") or {})
    return {
        ticker: _clean_float(price, field_name=f"price[{ticker}]")
        for ticker, price in raw_prices.items()
    }


def build_rebalance_plan(
    daily_signal: dict[str, Any],
    *,
    current_shares: dict[str, float],
    cash: float,
    prices: dict[str, float] | None = None,
    config: RebalanceConfig | None = None,
) -> RebalancePlan:
    """Build an auditable rebalance plan from a GroupA+ live signal.

    `daily_signal` is expected to be the JSON/dict shape produced by
    `group_a_plus.operations.daily_signal`. `current_shares` excludes cash;
    pass cash separately. Share quantities in returned orders are rounded down
    to each ticker's lot size and therefore may leave residual cash.
    """
    cfg = config or RebalanceConfig()
    resolved_prices = _resolve_prices(daily_signal, prices)
    target_weights = {
        str(ticker): _clean_float(weight, field_name=f"target_weights[{ticker}]")
        for ticker, weight in dict(daily_signal.get("target_weights") or {}).items()
    }
    if not target_weights:
        raise ValueError("daily_signal has no target_weights")
    if any(weight < -1e-12 for weight in target_weights.values()):
        raise ValueError(f"target_weights must be non-negative: {target_weights}")
    weight_sum = sum(target_weights.values())
    if weight_sum > 1.000001:
        raise ValueError(f"target_weights sum exceeds 1.0: {weight_sum:.8f}")

    cash_before = _clean_float(cash, field_name="cash")
    if cash_before < 0:
        raise ValueError(f"cash must be non-negative: {cash_before}")

    current_values: dict[str, float] = {cfg.cash_key: cash_before}
    for ticker, shares_raw in current_shares.items():
        ticker = str(ticker)
        shares = _clean_float(shares_raw, field_name=f"current_shares[{ticker}]")
        if shares < 0:
            raise ValueError(f"current_shares must be non-negative for {ticker}: {shares}")
        if ticker not in resolved_prices:
            if shares == 0 and target_weights.get(ticker, 0.0) == 0:
                continue
            raise ValueError(f"missing price for current holding {ticker}")
        price = resolved_prices[ticker]
        if price <= 0:
            raise ValueError(f"price must be positive for {ticker}: {price}")
        current_values[ticker] = shares * price

    for ticker, weight in target_weights.items():
        if ticker == cfg.cash_key or weight == 0:
            continue
        if ticker not in resolved_prices:
            raise ValueError(f"missing price for target ticker {ticker}")
        if resolved_prices[ticker] <= 0:
            raise ValueError(f"price must be positive for {ticker}: {resolved_prices[ticker]}")
        current_values.setdefault(ticker, 0.0)

    portfolio_value = sum(current_values.values())
    if portfolio_value <= 0:
        raise ValueError("portfolio value must be positive")

    target_values = {
        ticker: portfolio_value * weight
        for ticker, weight in target_weights.items()
    }
    target_cash = target_values.get(cfg.cash_key, 0.0)

    orders: list[PlannedOrder] = []
    skipped: list[dict[str, Any]] = []
    tickers = sorted((set(current_values) | set(target_weights)) - {cfg.cash_key})
    for ticker in tickers:
        price = resolved_prices.get(ticker)
        current_value = current_values.get(ticker, 0.0)
        target_value = target_values.get(ticker, 0.0)
        value_delta = target_value - current_value
        current_weight = current_value / portfolio_value
        target_weight = target_weights.get(ticker, 0.0)
        if abs(value_delta) < cfg.min_trade_value:
            skipped.append(
                {
                    "ticker": ticker,
                    "reason": "below_min_trade_value",
                    "value_delta": value_delta,
                    "min_trade_value": cfg.min_trade_value,
                }
            )
            continue
        if price is None or price <= 0:
            raise ValueError(f"missing or invalid price for ticker {ticker}")

        lot_size = cfg.lot_size_for(ticker)
        raw_shares = abs(value_delta) / price
        shares = _round_shares(raw_shares, lot_size)
        if shares <= 0:
            skipped.append(
                {
                    "ticker": ticker,
                    "reason": "rounded_to_zero_by_lot_size",
                    "value_delta": value_delta,
                    "lot_size": lot_size,
                }
            )
            continue

        side = "BUY" if value_delta > 0 else "SELL"
        if side == "SELL":
            current_share_count = _clean_float(current_shares.get(ticker, 0.0), field_name=f"current_shares[{ticker}]")
            shares = min(shares, _round_shares(current_share_count, lot_size))
            if shares <= 0:
                skipped.append(
                    {
                        "ticker": ticker,
                        "reason": "no_sellable_shares_after_lot_rounding",
                        "value_delta": value_delta,
                        "lot_size": lot_size,
                    }
                )
                continue

        orders.append(
            PlannedOrder(
                ticker=ticker,
                side=side,
                shares=shares,
                price=price,
                trade_value=shares * price,
                current_weight=current_weight,
                target_weight=target_weight,
                value_delta=value_delta,
            )
        )

    sell_value = sum(order.trade_value for order in orders if order.side == "SELL")
    buy_value = sum(order.trade_value for order in orders if order.side == "BUY")
    cash_after = cash_before + sell_value - buy_value
    warnings: list[str] = []
    if cash_after < -1e-6:
        warnings.append(f"planned buys exceed available cash after sells by {abs(cash_after):.2f}")
    if abs(target_cash - cash_after) >= cfg.min_trade_value:
        warnings.append(f"planned cash differs from target cash by {target_cash - cash_after:.2f}")

    return RebalancePlan(
        strategy_id=str(daily_signal.get("strategy_id", "")),
        signal_asof=str(pd.Timestamp(daily_signal.get("actual_data_date")).date()),
        portfolio_value=portfolio_value,
        target_weights=target_weights,
        current_values=current_values,
        target_values=target_values,
        orders=orders,
        skipped=skipped,
        warnings=warnings,
        cash_before=cash_before,
        cash_after_planned=cash_after,
        target_cash=target_cash,
    )
