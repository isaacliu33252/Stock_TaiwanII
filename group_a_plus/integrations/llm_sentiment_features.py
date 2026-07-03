"""Attach daily LLM sentiment features to model panels.

The builder in ``build_llm_sentiment_features.py`` creates daily sentiment
files. This module turns those files into leak-aware tabular features that can
be joined to NCF, LightGBM, or other shadow research panels.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from group_a_plus.paths import PROJECT_ROOT


DEFAULT_LLM_DAILY = PROJECT_ROOT / "FinRL" / "data" / "sentiment" / "llm_market_sentiment_daily.csv"
BASE_COLUMNS = [
    "llm_sentiment_score",
    "llm_sentiment_confidence",
    "llm_risk_off_score",
    "llm_news_intensity",
]


def load_llm_sentiment_daily(path: str | Path = DEFAULT_LLM_DAILY) -> pd.DataFrame:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    if not candidate.exists():
        return pd.DataFrame(columns=["date", *BASE_COLUMNS])
    frame = pd.read_csv(candidate)
    if "date" not in frame.columns:
        raise ValueError("LLM sentiment file is missing date column")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["date"]).sort_values("date")
    for col in BASE_COLUMNS:
        if col not in frame.columns:
            frame[col] = 0.0
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
    return frame[["date", *BASE_COLUMNS]].reset_index(drop=True)


def build_llm_sentiment_feature_frame(
    daily: pd.DataFrame,
    *,
    windows: Iterable[int] = (7, 14, 28),
    lag_days: int = 1,
) -> pd.DataFrame:
    """Create rolling sentiment features indexed by date.

    ``lag_days=1`` is the default to avoid using same-day news in models that
    predict from end-of-day market features.
    """

    if daily.empty:
        return pd.DataFrame()
    if lag_days < 0:
        raise ValueError("lag_days must be >= 0")

    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["date"]).sort_values("date").set_index("date")
    for col in BASE_COLUMNS:
        if col not in frame.columns:
            frame[col] = 0.0
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)

    shifted = frame[BASE_COLUMNS].shift(lag_days).fillna(0.0)
    features = shifted.add_suffix(f"_lag{lag_days}")
    for window in windows:
        if int(window) <= 0:
            raise ValueError("rolling windows must be positive")
        w = int(window)
        features[f"llm_sentiment_{w}d"] = shifted["llm_sentiment_score"].rolling(w, min_periods=1).mean()
        features[f"llm_risk_off_{w}d"] = shifted["llm_risk_off_score"].rolling(w, min_periods=1).mean()
        features[f"llm_confidence_{w}d"] = shifted["llm_sentiment_confidence"].rolling(w, min_periods=1).mean()
        features[f"llm_news_intensity_{w}d"] = shifted["llm_news_intensity"].rolling(w, min_periods=1).sum()

    if {"llm_sentiment_7d", "llm_sentiment_28d"}.issubset(features.columns):
        features["llm_sentiment_acceleration_7_28d"] = features["llm_sentiment_7d"] - features["llm_sentiment_28d"]
    if "llm_risk_off_28d" in features.columns:
        mean = features["llm_risk_off_28d"].rolling(120, min_periods=20).mean()
        std = features["llm_risk_off_28d"].rolling(120, min_periods=20).std().replace(0.0, np.nan)
        features["llm_risk_off_28d_z"] = ((features["llm_risk_off_28d"] - mean) / std).fillna(0.0)
    return features.replace([np.inf, -np.inf], 0.0).fillna(0.0)


def attach_llm_sentiment_features(
    panel: pd.DataFrame,
    sentiment: pd.DataFrame | str | Path = DEFAULT_LLM_DAILY,
    *,
    date_column: str = "date",
    lag_days: int = 1,
    windows: Iterable[int] = (7, 14, 28),
) -> pd.DataFrame:
    """Left-join LLM sentiment features to a dated panel."""

    if isinstance(sentiment, pd.DataFrame):
        daily = sentiment
    else:
        daily = load_llm_sentiment_daily(sentiment)
    out = panel.copy()
    if date_column in out.columns:
        dates = pd.to_datetime(out[date_column], errors="coerce").dt.normalize()
        out[date_column] = dates
        indexed = out.set_index(date_column)
        restore_column = True
    else:
        indexed = out.copy()
        indexed.index = pd.to_datetime(indexed.index, errors="coerce").normalize()
        restore_column = False

    features = build_llm_sentiment_feature_frame(daily, windows=windows, lag_days=lag_days)
    if features.empty:
        joined = indexed
    else:
        joined = indexed.join(features, how="left")
    sentiment_cols = [col for col in joined.columns if col.startswith("llm_")]
    joined[sentiment_cols] = joined[sentiment_cols].fillna(0.0)
    return joined.reset_index() if restore_column else joined
