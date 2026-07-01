"""FinBERT daily sentiment integration for GroupA+ live signals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_FINBERT_DAILY = Path("FinRL/data/sentiment/finbert_market_sentiment_daily.csv")


def load_finbert_daily_snapshot(
    requested_as_of: str | pd.Timestamp,
    actual_data_date: str | pd.Timestamp,
    *,
    path: str | Path = DEFAULT_FINBERT_DAILY,
) -> dict[str, Any]:
    """Load the latest FinBERT daily sentiment row available by actual_data_date.

    Expected CSV columns:
      date, finbert_sentiment_score, finbert_negative_ratio,
      finbert_positive_ratio, finbert_neutral_ratio, finbert_confidence,
      finbert_news_intensity

    Missing optional numeric columns default to zero so the integration can be
    introduced before the full FinBERT scoring pipeline is populated.
    """
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if not candidate.exists():
        return {
            "status": "unavailable",
            "reason": "file_not_found",
            "path": str(candidate),
            "risk_score": 0.0,
        }

    df = pd.read_csv(candidate)
    if df.empty or "date" not in df.columns:
        return {
            "status": "unavailable",
            "reason": "empty_or_missing_date",
            "path": str(candidate),
            "risk_score": 0.0,
        }

    actual = pd.Timestamp(actual_data_date).normalize()
    requested = pd.Timestamp(requested_as_of).normalize()
    data = df.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.normalize()
    data = data.dropna(subset=["date"])
    data = data[data["date"] <= actual].sort_values("date")
    if data.empty:
        return {
            "status": "unavailable",
            "reason": "no_rows_before_actual_date",
            "path": str(candidate),
            "actual_data_date": str(actual.date()),
            "risk_score": 0.0,
        }

    row = data.iloc[-1]

    def val(name: str, default: float = 0.0) -> float:
        if name not in row or pd.isna(row[name]):
            return default
        return float(row[name])

    sentiment = val("finbert_sentiment_score")
    negative_ratio = val("finbert_negative_ratio")
    positive_ratio = val("finbert_positive_ratio")
    neutral_ratio = val("finbert_neutral_ratio")
    confidence = val("finbert_confidence")
    intensity = max(val("finbert_news_intensity"), 0.0)
    negative_score = min(max(-sentiment, negative_ratio, 0.0), 1.0)
    intensity_score = min(intensity / 3.0, 1.0)
    raw_risk_score = min(max(0.55 * negative_score + 0.25 * confidence + 0.20 * intensity_score, 0.0), 1.0)
    selected_date = pd.Timestamp(row["date"]).normalize()
    stale_days = max(int((requested - selected_date).days), 0)
    actual_stale_days = max(int((actual - selected_date).days), 0)
    if actual_stale_days <= 7:
        freshness_scale = 1.0
    else:
        freshness_scale = max(0.0, 1.0 - ((actual_stale_days - 7) / 14.0))
    risk_score = raw_risk_score * freshness_scale
    status = "ok" if freshness_scale > 0.0 else "stale"

    return {
        "status": status,
        "path": str(candidate),
        "date": str(selected_date.date()),
        "requested_as_of_date": str(requested.date()),
        "actual_data_date": str(actual.date()),
        "calendar_stale_days": stale_days,
        "actual_calendar_stale_days": actual_stale_days,
        "freshness_scale": round(float(freshness_scale), 4),
        "finbert_sentiment_score": sentiment,
        "finbert_negative_ratio": negative_ratio,
        "finbert_positive_ratio": positive_ratio,
        "finbert_neutral_ratio": neutral_ratio,
        "finbert_confidence": confidence,
        "finbert_news_intensity": intensity,
        "raw_risk_score": round(float(raw_risk_score), 4),
        "risk_score": round(float(risk_score), 4),
    }
