"""Symbol normalization helpers for GroupA+ reports."""

from __future__ import annotations

from typing import Any


FINNHUB_TO_TRADINGVIEW_EXCHANGE = {
    ".TWO": "TPEX",
    ".TW": "TWSE",
    ".T": "TSE",
    ".HK": "HKEX",
    ".KS": "KRX",
    ".KQ": "KRX",
    ".SI": "SGX",
    ".AX": "ASX",
    ".NS": "NSE",
    ".BO": "BSE",
    ".L": "LSE",
    ".DE": "XETR",
    ".TO": "TSX",
    ".SA": "BMFBOVESPA",
}


def split_symbol_suffix(symbol: str) -> tuple[str, str | None]:
    """Split a ticker into root and dot suffix, prioritizing longer suffixes."""

    upper = str(symbol or "").strip().upper()
    if not upper:
        return "", None
    for suffix in sorted(FINNHUB_TO_TRADINGVIEW_EXCHANGE, key=len, reverse=True):
        if upper.endswith(suffix):
            return upper[: -len(suffix)], suffix
    return upper, None


def format_symbol_for_tradingview(symbol: str) -> str:
    """Convert Finnhub/yfinance-style tickers to TradingView-style tickers."""

    root, suffix = split_symbol_suffix(symbol)
    if not root:
        return ""
    if suffix is None:
        return root
    return f"{FINNHUB_TO_TRADINGVIEW_EXCHANGE[suffix]}:{root}"


def symbol_exchange(symbol: str) -> str:
    """Return a compact exchange label for a ticker."""

    _, suffix = split_symbol_suffix(symbol)
    if suffix is None:
        return "US"
    return FINNHUB_TO_TRADINGVIEW_EXCHANGE.get(suffix, suffix.lstrip("."))


def build_symbol_metadata(symbols: list[str] | tuple[str, ...]) -> dict[str, dict[str, Any]]:
    """Build report-friendly symbol metadata."""

    out: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        if str(symbol).lower() == "cash":
            continue
        root, suffix = split_symbol_suffix(symbol)
        out[str(symbol)] = {
            "symbol": str(symbol),
            "root": root,
            "suffix": suffix,
            "exchange": symbol_exchange(symbol),
            "tradingview_symbol": format_symbol_for_tradingview(symbol),
        }
    return out
