#!/usr/bin/env python3
"""FinRL-Meta Style Multi-Broker Interface — Abstract broker for Group A+.

Supports Alpaca (real/paper) and a local simulated broker for backtesting.
Design pattern from finrl/meta/paper_trading/alpaca.py but abstracted so
the trading logic doesn't depend on any specific broker.

Usage:
  python multi_broker_interface.py --broker paper --mode check
  python multi_broker_interface.py --broker alpaca --mode check  # needs API keys

For real Alpaca paper trading, set environment variables:
  ALPACA_API_KEY=...
  ALPACA_API_SECRET=...
  ALPACA_BASE_URL=https://paper-api.alpaca.markets  # or live
"""

from __future__ import annotations

import argparse
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent


# ─── Data Classes ─────────────────────────────────────────────────────────────

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    symbol: str
    qty: int
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    avg_fill_price: float | None = None
    order_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    broker_ref: str | None = None  # broker-specific order ID


@dataclass
class Position:
    symbol: str
    qty: int
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0


@dataclass
class Account:
    cash: float
    equity: float
    buying_power: float
    currency: str = "USD"


# ─── Abstract Broker Interface ────────────────────────────────────────────────

class Broker(ABC):
    """Abstract broker interface (FinRL-Meta style).

    Subclasses must implement all abstract methods. The trading logic
    in backtest scripts calls these methods without knowing which
    broker is being used.
    """

    @abstractmethod
    def get_account(self) -> Account:
        """Get current account state."""
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Get all open positions."""
        ...

    @abstractmethod
    def get_position(self, symbol: str) -> Position | None:
        """Get position for a specific symbol."""
        ...

    @abstractmethod
    def get_latest_price(self, symbol: str) -> float:
        """Get latest market price for symbol."""
        ...

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submit a new order. Returns updated Order with broker order_id."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if successful."""
        ...

    @abstractmethod
    def cancel_all_orders(self) -> int:
        """Cancel all open orders. Returns count of cancelled orders."""
        ...

    @abstractmethod
    def is_market_open(self) -> bool:
        """Check if market is currently open."""
        ...

    @abstractmethod
    def get_clock(self) -> dict[str, Any]:
        """Get market clock info (next open/close times)."""
        ...

    @abstractmethod
    def wait_for_market_open(self, poll_interval: int = 60) -> None:
        """Block until market opens."""
        ...

    @abstractmethod
    def close_all_positions(self, side: OrderSide | None = None) -> list[Order]:
        """Close all positions (or only 'side' positions). Returns list of orders."""
        ...

    @abstractmethod
    def close_position(self, symbol: str, qty: int | None = None) -> Order:
        """Close (partially or fully) a position. qty=None means close all."""
        ...

    def name(self) -> str:
        """Broker name for logging."""
        return self.__class__.__name__


# ─── Simulated Paper Broker (for backtesting) ─────────────────────────────────

class PaperBroker(Broker):
    """Local simulated broker for backtesting without API keys.

    Maintains an in-memory order book and account state.
    Prices come from a DataFrame (passed at construction time).
    """

    def __init__(
        self,
        prices_df: Any | None = None,  # pd.DataFrame with tickers as columns
        initial_cash: float = 1_000_000.0,
        commission_rate: float = 0.001425,
        slippage_bps: float = 5.0,
    ):
        import pandas as pd

        self._prices_df = prices_df  # keyed by timestamp
        self._current_idx = 0
        self._cash = float(initial_cash)
        self._initial_cash = float(initial_cash)
        self._commission_rate = float(commission_rate)
        self._slippage_bps = float(slippage_bps)

        self._positions: dict[str, Position] = {}
        self._orders: list[Order] = []
        self._next_order_id = 1
        self._market_open = True  # Simulated always open for backtest

    def _current_price(self, symbol: str) -> float:
        """Get current simulated price from DataFrame."""
        if self._prices_df is not None and len(self._prices_df) > self._current_idx:
            row = self._prices_df.iloc[self._current_idx]
            return float(row.get(symbol, 0.0))
        return 0.0

    def _apply_slippage(self, price: float, side: OrderSide) -> float:
        """Apply slippage: buy slightly higher, sell slightly lower."""
        slippage = price * self._slippage_bps / 10000
        if side == OrderSide.BUY:
            return price + slippage
        return price - slippage

    def advance_time(self, idx: int) -> None:
        """Advance the broker's time index to idx in the price DataFrame."""
        self._current_idx = idx

    def get_account(self) -> Account:
        total_equity = self._cash
        for pos in self._positions.values():
            total_equity += pos.qty * pos.current_price

        return Account(
            cash=round(self._cash, 2),
            equity=round(total_equity, 2),
            buying_power=round(self._cash * 2, 2),  # margin not fully simulated
            currency="USD",
        )

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_position(self, symbol: str) -> Position | None:
        return self._positions.get(symbol)

    def get_latest_price(self, symbol: str) -> float:
        return self._current_price(symbol)

    def submit_order(self, order: Order) -> Order:
        price = self._apply_slippage(self._current_price(order.symbol), order.side)
        qty = int(order.qty)

        if order.side == OrderSide.BUY:
            cost = qty * price * (1 + self._commission_rate)
            if cost > self._cash:
                order.status = OrderStatus.REJECTED
                return order

            self._cash -= cost
            if order.symbol in self._positions:
                pos = self._positions[order.symbol]
                total_qty = pos.qty + qty
                pos.avg_entry_price = (pos.avg_entry_price * pos.qty + price * qty) / total_qty
                pos.qty = total_qty
            else:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    qty=qty,
                    avg_entry_price=price,
                    current_price=price,
                    unrealized_pnl=0.0,
                )
        else:  # SELL
            pos = self._positions.get(order.symbol)
            if pos is None or pos.qty < qty:
                order.status = OrderStatus.REJECTED
                return order

            proceeds = qty * price * (1 - self._commission_rate)
            self._cash += proceeds
            pos.qty -= qty
            pos.realized_pnl += (price - pos.avg_entry_price) * qty

            if pos.qty <= 0:
                del self._positions[order.symbol]

        order.status = OrderStatus.FILLED
        order.filled_qty = qty
        order.avg_fill_price = price
        order.order_id = f"PAPER_{self._next_order_id}"
        order.broker_ref = f"PAPER_{self._next_order_id}"
        self._next_order_id += 1
        order.updated_at = datetime.now()

        # Update current prices for all positions
        for sym, p in self._positions.items():
            p.current_price = self._current_price(sym)
            p.unrealized_pnl = (p.current_price - p.avg_entry_price) * p.qty

        self._orders.append(order)
        return order

    def cancel_order(self, order_id: str) -> bool:
        # Paper broker: orders fill immediately, nothing to cancel
        return False

    def cancel_all_orders(self) -> int:
        return 0  # No open orders in paper broker

    def is_market_open(self) -> bool:
        return self._market_open

    def get_clock(self) -> dict[str, Any]:
        return {
            "is_open": self._market_open,
            "next_open": None,
            "next_close": None,
        }

    def wait_for_market_open(self, poll_interval: int = 60) -> None:
        pass  # No-op for backtest

    def close_all_positions(self, side: OrderSide | None = None) -> list[Order]:
        orders = []
        for symbol, pos in list(self._positions.items()):
            if side is None or side == OrderSide.SELL:
                o = Order(
                    symbol=symbol,
                    qty=pos.qty,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                )
                orders.append(self.submit_order(o))
        return orders

    def close_position(self, symbol: str, qty: int | None = None) -> Order:
        pos = self._positions.get(symbol)
        if pos is None:
            raise ValueError(f"No position for {symbol}")

        close_qty = qty if qty is not None else pos.qty
        o = Order(
            symbol=symbol,
            qty=close_qty,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
        )
        return self.submit_order(o)

    def get_orders_history(self) -> list[Order]:
        return list(self._orders)


# ─── Alpaca Broker (real/paper) ───────────────────────────────────────────────

class AlpacaBroker(Broker):
    """Alpaca broker implementation.

    Requires ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL env vars.
    For paper trading: ALPACA_BASE_URL=https://paper-api.alpaca.markets
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
        paper: bool = True,
    ):
        api_key = api_key or os.getenv("ALPACA_API_KEY")
        api_secret = api_secret or os.getenv("ALPACA_API_SECRET")
        base_url = base_url or os.getenv(
            "ALPACA_BASE_URL",
            "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets",
        )

        if not api_key or not api_secret:
            raise ValueError(
                "Alpaca API keys not found. Set ALPACA_API_KEY and ALPACA_API_SECRET env vars."
            )

        try:
            import alpaca_trade_api as tradeapi
        except ImportError:
            raise ImportError(
                "alpaca_trade_api not installed. Run: pip install alpaca-trade-api"
            )

        self._api = tradeapi.REST(api_key, api_secret, base_url, "v2")

    def get_account(self) -> Account:
        acc = self._api.get_account()
        return Account(
            cash=float(acc.cash),
            equity=float(acc.equity),
            buying_power=float(acc.buying_power),
            currency=str(acc.currency),
        )

    def get_positions(self) -> list[Position]:
        raw = self._api.list_positions()
        positions = []
        for p in raw:
            positions.append(
                Position(
                    symbol=str(p.symbol),
                    qty=int(float(p.qty)),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    unrealized_pnl=float(p.unrealized_pl),
                    realized_pnl=float(p.realized_pl),
                )
            )
        return positions

    def get_position(self, symbol: str) -> Position | None:
        try:
            p = self._api.get_position(symbol)
            return Position(
                symbol=str(p.symbol),
                qty=int(float(p.qty)),
                avg_entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price),
                unrealized_pnl=float(p.unrealized_pl),
                realized_pnl=float(p.realized_pl),
            )
        except Exception:
            return None

    def get_latest_price(self, symbol: str) -> float:
        bar = self._api.get_crypto_bars(symbol, "1Min", limit=1) if "BTC" in symbol else self._api.get_bars(symbol, "1Min", limit=1)
        # Fallback to quote
        quote = self._api.get_quote(symbol)
        return float(quote.askprice)

    def submit_order(self, order: Order) -> Order:
        side_str = "buy" if order.side == OrderSide.BUY else "sell"
        type_str = "market" if order.order_type == OrderType.MARKET else "limit"

        kwargs: dict[str, Any] = {
            "symbol": order.symbol,
            "qty": str(order.qty),
            "side": side_str,
            "type": type_str,
            "time_in_force": "day",
        }
        if order.limit_price is not None:
            kwargs["limit_price"] = str(order.limit_price)

        try:
            o = self._api.submit_order(**kwargs)
            order.order_id = str(o.id)
            order.broker_ref = str(o.id)
            order.status = OrderStatus.PENDING
            order.created_at = datetime.now()
        except Exception as e:
            order.status = OrderStatus.REJECTED

        return order

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._api.cancel_order(order_id)
            return True
        except Exception:
            return False

    def cancel_all_orders(self) -> int:
        count = 0
        for o in self._api.list_orders(status="open"):
            try:
                self._api.cancel_order(o.id)
                count += 1
            except Exception:
                pass
        return count

    def is_market_open(self) -> bool:
        return self._api.get_clock().is_open

    def get_clock(self) -> dict[str, Any]:
        clock = self._api.get_clock()
        return {
            "is_open": clock.is_open,
            "next_open": clock.next_open.isoformat() if clock.next_open else None,
            "next_close": clock.next_close.isoformat() if clock.next_close else None,
        }

    def wait_for_market_open(self, poll_interval: int = 60) -> None:
        clock = self._api.get_clock()
        if clock.is_open:
            return
        opening_time = clock.next_open
        while True:
            clock = self._api.get_clock()
            if clock.is_open:
                return
            now = datetime.now()
            wait_seconds = (opening_time - now).total_seconds()
            if wait_seconds > 0:
                time.sleep(min(wait_seconds, poll_interval))

    def close_all_positions(self, side: OrderSide | None = None) -> list[Order]:
        orders = []
        for pos in self._api.list_positions():
            if side is not None:
                if side == OrderSide.BUY and float(pos.qty) > 0:
                    continue
                if side == OrderSide.SELL and float(pos.qty) < 0:
                    continue

            qty = abs(int(float(pos.qty)))
            o = self.submit_order(
                Order(
                    symbol=str(pos.symbol),
                    qty=qty,
                    side=OrderSide.SELL if float(pos.qty) > 0 else OrderSide.BUY,
                    order_type=OrderType.MARKET,
                )
            )
            orders.append(o)
        return orders

    def close_position(self, symbol: str, qty: int | None = None) -> Order:
        pos = self._api.get_position(symbol)
        close_qty = qty if qty is not None else abs(int(float(pos.qty)))
        return self.submit_order(
            Order(
                symbol=symbol,
                qty=close_qty,
                side=OrderSide.SELL if float(pos.qty) > 0 else OrderSide.BUY,
                order_type=OrderType.MARKET,
            )
        )


# ─── Broker Factory ───────────────────────────────────────────────────────────

def create_broker(
    broker_type: str,
    prices_df: Any = None,
    initial_cash: float = 1_000_000.0,
    commission_rate: float = 0.001425,
    paper: bool = True,
) -> Broker:
    """Create a broker instance by type.

    broker_type: "paper" | "simulated" | "alpaca" | "alpaca-live"
    """
    bt = broker_type.lower()
    if bt in ("paper", "simulated", "local"):
        return PaperBroker(
            prices_df=prices_df,
            initial_cash=initial_cash,
            commission_rate=commission_rate,
        )
    elif bt == "alpaca":
        return AlpacaBroker(paper=True)
    elif bt == "alpaca-live":
        return AlpacaBroker(paper=False)
    else:
        raise ValueError(f"Unknown broker type: {broker_type}")


# ─── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--broker",
        default="paper",
        choices=["paper", "simulated", "alpaca", "alpaca-live"],
        help="Broker type to use",
    )
    parser.add_argument(
        "--mode",
        default="check",
        choices=["check", "positions", "account"],
        help="Operation mode",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Symbol for single-position queries",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    try:
        broker = create_broker(args.broker)
    except Exception as e:
        print(f"ERROR: {e}")
        return

    print(f"Broker: {broker.name()}")

    if args.mode == "check":
        clock = broker.get_clock()
        print(f"Market open: {clock['is_open']}")
        if clock.get("next_open"):
            print(f"Next open: {clock['next_open']}")
        if clock.get("next_close"):
            print(f"Next close: {clock['next_close']}")

        account = broker.get_account()
        print(f"Account — cash: {account.cash:,.2f}, equity: {account.equity:,.2f}")

        positions = broker.get_positions()
        print(f"Open positions: {len(positions)}")
        for p in positions:
            print(f"  {p.symbol}: qty={p.qty}, avg={p.avg_entry_price:.2f}, "
                  f"current={p.current_price:.2f}, pnl={p.unrealized_pnl:.2f}")

    elif args.mode == "account":
        acc = broker.get_account()
        print(f"Cash:      {acc.cash:,.2f}")
        print(f"Equity:    {acc.equity:,.2f}")
        print(f"Buying:    {acc.buying_power:,.2f}")
        print(f"Currency:  {acc.currency}")

    elif args.mode == "positions":
        if args.symbol:
            pos = broker.get_position(args.symbol)
            if pos:
                print(f"{pos.symbol}: qty={pos.qty}, avg={pos.avg_entry_price:.2f}, "
                      f"current={pos.current_price:.2f}")
            else:
                print(f"No position for {args.symbol}")
        else:
            for p in broker.get_positions():
                print(f"{p.symbol}: qty={p.qty}")


if __name__ == "__main__":
    main()