#!/usr/bin/env python3
"""Calculate simple technical support and resistance levels for 0050.TW."""

import json
from datetime import datetime

import numpy as np
import pandas as pd

from portfolio_data_loader import download_all_stocks


TICKER = "0050.TW"
START = "2024-01-01"
END = "2026-05-10"

# Latest Yahoo Taiwan quote observed on 2026-05-08:
# https://tw.stock.yahoo.com/quote/0050.TW
LATEST_BAR = {
    "date": "2026-05-07",
    "open": 97.95,
    "high": 98.40,
    "low": 97.40,
    "close": 97.70,
    "volume": 110_211_000,
}


def clean(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    out = out.sort_values("date").drop_duplicates("date", keep="last")
    return out.reset_index(drop=True)


def add_latest_bar(df: pd.DataFrame) -> pd.DataFrame:
    latest_date = pd.Timestamp(LATEST_BAR["date"])
    if df["date"].max() >= latest_date:
        return df
    latest_bar = LATEST_BAR.copy()
    latest_bar["date"] = latest_date
    return pd.concat([df, pd.DataFrame([latest_bar])], ignore_index=True).sort_values("date").reset_index(drop=True)


def rsi(close: pd.Series, window: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return float(100 - (100 / (1 + rs.iloc[-1])))


def atr(df: pd.DataFrame, window: int = 14) -> float:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(tr.rolling(window).mean().iloc[-1])


def moving_averages(df: pd.DataFrame) -> dict:
    close = df["close"]
    return {f"ma{w}": round(float(close.rolling(w).mean().iloc[-1]), 2) for w in (5, 10, 20, 60, 120, 200)}


def range_levels(df: pd.DataFrame) -> dict:
    levels = {}
    for w in (20, 60, 120):
        recent = df.tail(w)
        levels[f"{w}d_low"] = round(float(recent["low"].min()), 2)
        levels[f"{w}d_high"] = round(float(recent["high"].max()), 2)
    return levels


def pivot_levels(df: pd.DataFrame) -> dict:
    prev = df.iloc[-2]
    high, low, close = float(prev["high"]), float(prev["low"]), float(prev["close"])
    pivot = (high + low + close) / 3
    return {
        "pivot": round(pivot, 2),
        "s1": round(2 * pivot - high, 2),
        "s2": round(pivot - (high - low), 2),
        "r1": round(2 * pivot - low, 2),
        "r2": round(pivot + (high - low), 2),
    }


def volume_profile(df: pd.DataFrame, bucket_size: float = 0.5, lookback: int = 120) -> list:
    recent = df.tail(lookback).copy()
    typical = (recent["high"] + recent["low"] + recent["close"]) / 3
    recent["bucket"] = (typical / bucket_size).round() * bucket_size
    nodes = recent.groupby("bucket")["volume"].sum().sort_values(ascending=False).head(8)
    return [{"price": round(float(idx), 2), "volume": int(vol)} for idx, vol in nodes.items()]


def swing_levels(df: pd.DataFrame, lookback: int = 90, radius: int = 3) -> dict:
    recent = df.tail(lookback).reset_index(drop=True)
    highs = []
    lows = []
    for i in range(radius, len(recent) - radius):
        window = recent.iloc[i - radius : i + radius + 1]
        if recent.loc[i, "high"] == window["high"].max():
            highs.append(float(recent.loc[i, "high"]))
        if recent.loc[i, "low"] == window["low"].min():
            lows.append(float(recent.loc[i, "low"]))
    return {
        "swing_supports": [round(x, 2) for x in sorted(lows, reverse=True)[:6]],
        "swing_resistances": [round(x, 2) for x in sorted(highs)[:6]],
    }


def nearest(levels: list[float], price: float, side: str, limit: int = 4) -> list[float]:
    if side == "support":
        pool = [x for x in levels if x <= price]
        return [round(x, 2) for x in sorted(set(pool), reverse=True)[:limit]]
    pool = [x for x in levels if x >= price]
    return [round(x, 2) for x in sorted(set(pool))[:limit]]


def main() -> None:
    raw = download_all_stocks([TICKER], START, END)[TICKER]
    df = add_latest_bar(clean(raw))
    close = float(df.iloc[-1]["close"])

    ma = moving_averages(df)
    ranges = range_levels(df)
    pivots = pivot_levels(df)
    swings = swing_levels(df)
    vp = volume_profile(df)
    atr14 = atr(df)

    support_candidates = [
        pivots["s1"],
        pivots["s2"],
        ranges["20d_low"],
        ranges["60d_low"],
        ranges["120d_low"],
        ma["ma5"],
        ma["ma10"],
        ma["ma20"],
        ma["ma60"],
        ma["ma120"],
        ma["ma200"],
        *swings["swing_supports"],
        *[x["price"] for x in vp],
    ]
    resistance_candidates = [
        pivots["r1"],
        pivots["r2"],
        ranges["20d_high"],
        ranges["60d_high"],
        ranges["120d_high"],
        ma["ma5"],
        ma["ma10"],
        ma["ma20"],
        ma["ma60"],
        ma["ma120"],
        ma["ma200"],
        *swings["swing_resistances"],
        *[x["price"] for x in vp],
    ]

    payload = {
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "ticker": TICKER,
        "latest_date": str(pd.Timestamp(df.iloc[-1]["date"]).date()),
        "latest_close": round(close, 2),
        "ohlc": {
            "open": round(float(df.iloc[-1]["open"]), 2),
            "high": round(float(df.iloc[-1]["high"]), 2),
            "low": round(float(df.iloc[-1]["low"]), 2),
            "close": round(close, 2),
            "volume": int(df.iloc[-1]["volume"]),
        },
        "trend": {
            **ma,
            "rsi14": round(rsi(df["close"]), 2),
            "atr14": round(atr14, 2),
            "bollinger_upper20": round(float(df["close"].rolling(20).mean().iloc[-1] + 2 * df["close"].rolling(20).std(ddof=1).iloc[-1]), 2),
            "bollinger_lower20": round(float(df["close"].rolling(20).mean().iloc[-1] - 2 * df["close"].rolling(20).std(ddof=1).iloc[-1]), 2),
        },
        "ranges": ranges,
        "pivots": pivots,
        "swing_levels": swings,
        "volume_profile_120d": vp,
        "nearest_supports": nearest(support_candidates, close, "support"),
        "nearest_resistances": nearest(resistance_candidates, close, "resistance"),
        "risk_bands": {
            "near_support_zone": [round(close - atr14, 2), round(close - 0.5 * atr14, 2)],
            "near_resistance_zone": [round(close + 0.5 * atr14, 2), round(close + atr14, 2)],
        },
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
