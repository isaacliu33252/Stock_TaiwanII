#!/usr/bin/env python3
"""Utilities for TWII-based proxy stress tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from FinRL.data.data_utils import read_parquet_safe
from FinRL.portfolio_data_loader import LLM_SENTIMENT_COLUMNS, add_long_horizon_features


PROJECT_ROOT = Path(__file__).parent
DEFAULT_TWII_MARKET_CACHE = (
    PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_20030101_20110101_1d_market_v2.parquet"
)
DJI_PROXY_COLUMNS = [
    "dji_return_1d_lag1",
    "dji_return_5d_lag1",
    "dji_volatility_20d_lag1",
    "dji_ma60_ratio_lag1",
    "dji_drawdown_60d_lag1",
]
MARKET_CONTEXT_COLUMNS = [
    "twse_index_return_raw",
    "twse_index_volume_change_raw",
    "market_volatility_raw",
    "twse_index_return",
    "twse_index_volume_change",
    "market_volatility",
] + DJI_PROXY_COLUMNS + LLM_SENTIMENT_COLUMNS


def load_twii_market(
    start: str,
    end: str,
    *,
    cache_path: Path | None = None,
) -> pd.DataFrame:
    """Load cached TWII market features for a requested date range."""
    resolved = cache_path or DEFAULT_TWII_MARKET_CACHE
    market = read_parquet_safe(resolved)
    if market is None or market.empty:
        raise RuntimeError(f"Unable to read TWII market cache: {resolved}")

    out = market.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    out = out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()
    if len(out) < 2:
        raise RuntimeError(f"Not enough TWII market rows between {start} and {end}: {len(out)}")

    for column in MARKET_CONTEXT_COLUMNS:
        if column not in out.columns:
            out[column] = 0.0
        out[column] = pd.to_numeric(out[column], errors="coerce").fillna(0.0)

    return out.sort_values("date").reset_index(drop=True)


def build_twii_proxy_ohlcv(
    market: pd.DataFrame,
    *,
    ticker: str,
    leverage: float = 1.0,
    inverse: bool = False,
    base_price: float = 100.0,
    base_volume: float = 1_000_000.0,
) -> pd.DataFrame:
    """Synthesize an ETF-like OHLCV series from TWII daily returns."""
    if market.empty:
        raise RuntimeError("TWII market dataframe is empty")

    twii_return = pd.to_numeric(market["twse_index_return_raw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    volume_change = (
        pd.to_numeric(market["twse_index_volume_change_raw"], errors="coerce")
        .fillna(0.0)
        .clip(-0.95, 10.0)
        .to_numpy(dtype=float)
    )
    vol_raw = (
        pd.to_numeric(market["market_volatility_raw"], errors="coerce")
        .fillna(0.0)
        .clip(0.0, 0.5)
        .to_numpy(dtype=float)
    )

    if inverse:
        gross_returns = np.clip(1.0 - twii_return, 0.05, None)
    else:
        gross_returns = np.clip(1.0 + leverage * twii_return, 0.05, None)

    close = base_price * np.cumprod(gross_returns)
    open_ = np.empty_like(close)
    open_[0] = base_price
    open_[1:] = close[:-1]

    # Use a volatility-aware intraday range proxy so the synthetic bars are not flat.
    intraday_span = np.maximum(np.abs(gross_returns - 1.0) * 0.60, vol_raw)
    intraday_span = np.clip(intraday_span, 0.0025, 0.25)
    high = np.maximum(open_, close) * (1.0 + intraday_span)
    low = np.minimum(open_, close) * np.maximum(1.0 - intraday_span, 0.01)

    volume_scale = np.cumprod(np.clip(1.0 + volume_change, 0.10, None))
    volume = np.maximum(base_volume * volume_scale, 1.0)
    turnover = ((open_ + close) / 2.0) * volume

    proxy = pd.DataFrame(
        {
            "date": market["date"].to_numpy(),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "turnover": turnover,
            "dividends": 0.0,
            "stock_splits": 0.0,
            "symbol": ticker,
        }
    )
    return proxy.replace([np.inf, -np.inf], 0.0).ffill().bfill().reset_index(drop=True)


def attach_market_context(
    df: pd.DataFrame,
    market: pd.DataFrame,
    *,
    add_long_features: bool = False,
) -> pd.DataFrame:
    """Attach market context columns used by downstream environments."""
    context = market[["date"] + MARKET_CONTEXT_COLUMNS].copy()
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    out = out.merge(context, on="date", how="left")

    stock_return = pd.to_numeric(out["close"], errors="coerce").pct_change()
    out["sector_correlation"] = (
        stock_return.rolling(20, min_periods=5)
        .corr(pd.to_numeric(out["twse_index_return_raw"], errors="coerce"))
        .replace([np.inf, -np.inf], 0.0)
        .fillna(0.0)
        .clip(-1.0, 1.0)
    )

    for column in MARKET_CONTEXT_COLUMNS + ["sector_correlation"]:
        out[column] = pd.to_numeric(out[column], errors="coerce").ffill().fillna(0.0)

    if add_long_features:
        out = add_long_horizon_features(out)

    return out.replace([np.inf, -np.inf], 0.0).ffill().bfill().reset_index(drop=True)


def build_0050_twii_proxy_df(
    start: str,
    end: str,
    *,
    base_price: float = 100.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create a 0050-like TWII proxy dataframe for the single-asset env."""
    market = load_twii_market(start, end)
    proxy = build_twii_proxy_ohlcv(
        market,
        ticker="0050.TW",
        leverage=1.0,
        inverse=False,
        base_price=base_price,
        base_volume=1_000_000.0,
    )
    return attach_market_context(proxy, market, add_long_features=True), market


# Group B TWII proxy: ticker → (leverage, inverse, correlation_proxy)
# correlation_proxy maps to a vol_scalar that reduces price noise for
# lower-correlation assets, making synthetic bars look more realistic.
_GROUP_B_TWII_PROXY_PARAMS = {
    "0056.TW":     dict(leverage=0.85, inverse=False,  vol_scale=1.0),
    "00646.TW":    dict(leverage=0.75, inverse=False,  vol_scale=0.85),   # S&P500 USD hedge dampens TWII correlation
    "00679B.TWO":  dict(leverage=0.45, inverse=False,  vol_scale=0.70),   # 20yr treasury – flight-to-safety, low TWII correlation
    "00713.TW":    dict(leverage=0.80, inverse=False,  vol_scale=0.95),
    "00751B.TWO":  dict(leverage=0.75, inverse=False,  vol_scale=0.90),
    "00878.TW":    dict(leverage=0.85, inverse=False,  vol_scale=1.0),
}


def _build_group_b_single_proxy(
    market: pd.DataFrame,
    ticker: str,
    *,
    base_price: float = 100.0,
    base_volume: float = 500_000.0,
    vol_scale: float = 1.0,
) -> pd.DataFrame:
    """Build one Group B proxy with asset-specific vol scaling."""
    params = _GROUP_B_TWII_PROXY_PARAMS[ticker]
    # Use standard TWII returns but scale volatility to reflect empirical correlation
    twii_return = pd.to_numeric(market["twse_index_return_raw"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    volume_change = (
        pd.to_numeric(market["twse_index_volume_change_raw"], errors="coerce")
        .fillna(0.0)
        .clip(-0.95, 10.0)
        .to_numpy(dtype=float)
    )
    vol_raw = (
        pd.to_numeric(market["market_volatility_raw"], errors="coerce")
        .fillna(0.0)
        .clip(0.0, 0.5)
        .to_numpy(dtype=float)
    )

    leverage = params["leverage"]
    inverse = params["inverse"]

    if inverse:
        gross_returns = np.clip(1.0 - twii_return, 0.05, None)
    else:
        gross_returns = np.clip(1.0 + leverage * twii_return, 0.05, None)

    close = base_price * np.cumprod(gross_returns)
    open_ = np.empty_like(close)
    open_[0] = base_price
    open_[1:] = close[:-1]

    # Apply vol_scale to make lower-correlation assets look less TWII-like
    intraday_span = np.maximum(np.abs(gross_returns - 1.0) * 0.60, vol_raw * vol_scale)
    intraday_span = np.clip(intraday_span, 0.0025, 0.30)
    high = np.maximum(open_, close) * (1.0 + intraday_span)
    low = np.minimum(open_, close) * np.maximum(1.0 - intraday_span, 0.01)

    volume_scale = np.cumprod(np.clip(1.0 + volume_change, 0.10, None))
    volume = np.maximum(base_volume * volume_scale, 1.0)
    turnover = ((open_ + close) / 2.0) * volume

    proxy = pd.DataFrame(
        {
            "date": market["date"].to_numpy(),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "turnover": turnover,
            "dividends": 0.0,
            "stock_splits": 0.0,
            "symbol": ticker,
        }
    )
    return proxy.replace([np.inf, -np.inf], 0.0).ffill().bfill().reset_index(drop=True)


def build_group_b_twii_proxy_data(
    start: str,
    end: str,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Create TWII-based synthetic OHLCV for Group B multi-ticker stress tests.

    Each ticker uses asset-specific leverage and vol_scale to reflect empirical
    correlation to TWII during the 2008 crisis period.
    """
    market = load_twii_market(start, end)
    stock_data = {
        ticker: attach_market_context(
            _build_group_b_single_proxy(
                market,
                ticker,
                base_price=100.0,
                base_volume=500_000.0,
                vol_scale=params["vol_scale"],
            ),
            market,
            add_long_features=False,
        )
        for ticker, params in _GROUP_B_TWII_PROXY_PARAMS.items()
    }
    return stock_data, market


def build_group_a_twii_proxy_data(
    start: str,
    end: str,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Create TWII-based synthetic OHLCV for Group A triplet tests."""
    market = load_twii_market(start, end)
    stock_data = {
        "0050.TW": attach_market_context(
            build_twii_proxy_ohlcv(
                market,
                ticker="0050.TW",
                leverage=1.0,
                inverse=False,
                base_price=100.0,
                base_volume=1_000_000.0,
            ),
            market,
            add_long_features=False,
        ),
        "00631L.TW": attach_market_context(
            build_twii_proxy_ohlcv(
                market,
                ticker="00631L.TW",
                leverage=2.0,
                inverse=False,
                base_price=100.0,
                base_volume=800_000.0,
            ),
            market,
            add_long_features=False,
        ),
        "00632R.TW": attach_market_context(
            build_twii_proxy_ohlcv(
                market,
                ticker="00632R.TW",
                leverage=1.0,
                inverse=True,
                base_price=100.0,
                base_volume=600_000.0,
            ),
            market,
            add_long_features=False,
        ),
    }
    return stock_data, market
