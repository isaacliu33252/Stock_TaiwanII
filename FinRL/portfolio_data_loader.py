# ============================================================================
# Portfolio Data Loader - 投資組 合多股票資料下載器
# ============================================================================
"""
下載並整合所有持股的歷史數據，用於多智能體訓練和回測。

功能:
    1. 同時下載 8 檔股票的歷史數據
    2. 對齊交易日 (取交集)
    3. 計算各股票的技術指標
    4. 合併為統一的 DataFrame
"""

import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import warnings
import sys
import os
import re
import time
import requests
import json

# 引入統一資料工具（PyArrow 24 相容 + graceful fallback）
try:
    from .data.data_utils import (
        read_parquet_safe,
        write_parquet_safe,
        normalize_date_column as _normalize_date_column,
        CacheValidator,
        ParquetStreamReader,
        smart_read,
        validator_for_stock_data,
    )
except ImportError:
    from data.data_utils import (
        read_parquet_safe,
        write_parquet_safe,
        normalize_date_column as _normalize_date_column,
        CacheValidator,
        ParquetStreamReader,
        smart_read,
        validator_for_stock_data,
    )

warnings.filterwarnings('ignore')

# 嘗試導入 config
try:
    PROJECT_ROOT = Path(__file__).parent
    sys.path.insert(0, str(PROJECT_ROOT))
    from portfolio_config import (
        ALL_TICKERS, PORTFOLIO_HOLDINGS,
        BACKTEST_START, BACKTEST_END,
        TRAIN_START, TRAIN_END
    )
    from config import TRAIN_START_DATE, TRAIN_END_DATE, TEST_START_DATE, TEST_END_DATE
except ImportError:
    # fallback
    ALL_TICKERS = [
        "0050.TW",
        "0056.TW",
        "00646.TW",
        "00679B.TWO",
        "00713.TW",
        "00751B.TWO",
        "00878.TW",
        "2884.TW",
        "00632R.TW",
        "00631L.TW",
    ]
    PORTFOLIO_HOLDINGS = {}
    BACKTEST_START = "2000-01-01"
    BACKTEST_END = "2010-12-31"
    TRAIN_START = "1990-01-01"
    TRAIN_END = "2000-12-31"


MARKET_TICKER = "^TWII"
GLOBAL_TICKER = "^DJI"
LLM_SENTIMENT_COLUMNS = [
    "llm_sentiment_score",
    "llm_sentiment_confidence",
    "llm_risk_off_score",
    "llm_news_intensity",
]
MARKET_FEATURE_COLUMNS = [
    "twse_index_return",
    "twse_index_volume_change",
    "sector_correlation",
    "market_volatility",
    "dji_return_1d_lag1",
    "dji_return_5d_lag1",
    "dji_volatility_20d_lag1",
    "dji_ma60_ratio_lag1",
    "dji_drawdown_60d_lag1",
] + LLM_SENTIMENT_COLUMNS
LLM_SENTIMENT_DEFAULT_FILES = [
    "data/sentiment/llm_market_sentiment_daily.parquet",
    "data/sentiment/llm_market_sentiment_daily.csv",
    "data/llm_market_sentiment_daily.parquet",
    "data/llm_market_sentiment_daily.csv",
]
MARKET_RAW_COLUMNS = [
    "twse_index_return_raw",
    "twse_index_volume_change_raw",
    "market_volatility_raw",
    "dji_return_1d_raw",
    "dji_return_5d_raw",
    "dji_volatility_20d_raw",
    "dji_ma60_ratio_raw",
    "dji_drawdown_60d_raw",
]

TWSE_SPLIT_ADJUSTMENTS = {
    # The engine does not model share-count changes, so keep a continuous
    # synthetic price series after this known 22-for-1 split.
    "00631L": [(pd.Timestamp("2026-03-31"), 22.0)],
}


def _inclusive_history_end(value: str | datetime | pd.Timestamp) -> str:
    """yfinance history() treats end as exclusive; move it forward one day."""
    return (pd.Timestamp(value).normalize() + timedelta(days=1)).strftime("%Y-%m-%d")


def _find_covering_cache(
    cache_dir: Path,
    prefix: str,
    start_date: str,
    end_date: str,
    interval: str,
    suffix: str,
) -> Optional[Path]:
    """Find the smallest cache file whose filename range covers the request."""
    start_ts = pd.Timestamp(start_date).normalize()
    end_ts = pd.Timestamp(end_date).normalize()
    pattern = re.compile(
        rf"^{re.escape(prefix)}_(\d{{8}})_(\d{{8}})_{re.escape(interval)}_{re.escape(suffix)}\.parquet$"
    )
    candidates = []
    for path in cache_dir.glob(f"{prefix}_*_{interval}_{suffix}.parquet"):
        match = pattern.match(path.name)
        if not match:
            continue
        cache_start = pd.Timestamp(match.group(1)).normalize()
        cache_end = pd.Timestamp(match.group(2)).normalize()
        if cache_start <= start_ts and cache_end >= end_ts:
            span_days = (cache_end - cache_start).days
            candidates.append((span_days, -cache_end.value, path))

    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def _read_relaxed_cache(
    file_path: Path,
    *,
    start_date: str,
    end_date: str,
    required_columns: list[str],
    min_rows: int,
    start_tolerance_days: int = 7,
    end_tolerance_days: int = 7,
    allow_late_start: bool = False,
) -> Optional[pd.DataFrame]:
    """Read cache with a trading-day tolerance for the requested end date."""
    df = read_parquet_safe(file_path)
    if df is None or df.empty:
        return None

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        return None

    df = _normalize_date_column(df)
    start_ts = pd.Timestamp(start_date).normalize()
    end_ts = pd.Timestamp(end_date).normalize()
    df = df[(df["date"] >= start_ts) & (df["date"] <= end_ts)].reset_index(drop=True)
    if len(df) < min_rows:
        return None

    file_start = df["date"].min()
    file_end = df["date"].max()
    if not allow_late_start and file_start > start_ts + pd.Timedelta(days=start_tolerance_days):
        return None
    if file_end < end_ts - pd.Timedelta(days=end_tolerance_days):
        return None
    return df


# 統一使用 data_utils 的 _normalize_date_column（已在上方 import）


def _rolling_zscore(series: pd.Series, window: int = 60, min_periods: int = 20) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mean = values.rolling(window, min_periods=min_periods).mean()
    std = values.rolling(window, min_periods=min_periods).std().replace(0, np.nan)
    return ((values - mean) / std).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def resolve_llm_sentiment_path(sentiment_path: str | Path | None = None) -> Optional[Path]:
    candidates: list[Path] = []
    if sentiment_path:
        raw = Path(sentiment_path)
        candidates.append(raw)
        if not raw.is_absolute():
            candidates.append(PROJECT_ROOT / raw)
            candidates.append(PROJECT_ROOT.parent / raw)

    env_path = os.getenv("FINRL_LLM_SENTIMENT_FILE")
    if env_path:
        env_candidate = Path(env_path)
        candidates.append(env_candidate)
        if not env_candidate.is_absolute():
            candidates.append(PROJECT_ROOT / env_candidate)
            candidates.append(PROJECT_ROOT.parent / env_candidate)

    for rel_path in LLM_SENTIMENT_DEFAULT_FILES:
        candidates.append(PROJECT_ROOT / rel_path)

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate.absolute()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists():
            return resolved
    return None


def _read_json_records(file_path: Path) -> pd.DataFrame:
    if file_path.suffix.lower() == ".jsonl":
        records = []
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
        return pd.DataFrame(records)

    with file_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        if "data" in payload and isinstance(payload["data"], list):
            return pd.DataFrame(payload["data"])
        return pd.DataFrame([payload])
    return pd.DataFrame(payload)


def _normalize_llm_sentiment_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["date"] + LLM_SENTIMENT_COLUMNS)

    out = df.copy()
    rename_map = {}
    had_canonical_intensity = "llm_news_intensity" in out.columns
    alias_map = {
        "sentiment_score": "llm_sentiment_score",
        "market_sentiment_score": "llm_sentiment_score",
        "score": "llm_sentiment_score",
        "confidence": "llm_sentiment_confidence",
        "sentiment_confidence": "llm_sentiment_confidence",
        "risk_off": "llm_risk_off_score",
        "risk_off_score": "llm_risk_off_score",
        "fear_score": "llm_risk_off_score",
        "headline_count": "llm_news_intensity",
        "news_count": "llm_news_intensity",
        "article_count": "llm_news_intensity",
        "mention_count": "llm_news_intensity",
    }
    lowered = {str(col).strip().lower(): col for col in out.columns}
    for alias, target in alias_map.items():
        if target in out.columns:
            continue
        source = lowered.get(alias)
        if source is not None:
            rename_map[source] = target
    if rename_map:
        out = out.rename(columns=rename_map)

    if "date" not in out.columns:
        for candidate in ("dt", "datetime", "published_at", "timestamp"):
            if candidate in out.columns:
                out = out.rename(columns={candidate: "date"})
                break
    if "date" not in out.columns:
        raise ValueError("LLM sentiment input must contain a date-like column")

    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.tz_localize(None)
    out = out.dropna(subset=["date"]).copy()
    out["date"] = out["date"].dt.normalize()

    for col in LLM_SENTIMENT_COLUMNS:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce")

    raw_intensity = out["llm_news_intensity"].fillna(0.0).clip(lower=0.0)
    if had_canonical_intensity:
        out["llm_news_intensity"] = raw_intensity.clip(0.0, 5.0)
    else:
        out["llm_news_intensity"] = np.log1p(raw_intensity).clip(0.0, 5.0)
    out["llm_sentiment_score"] = out["llm_sentiment_score"].fillna(0.0).clip(-1.0, 1.0)
    out["llm_sentiment_confidence"] = out["llm_sentiment_confidence"].fillna(0.0).clip(0.0, 1.0)
    out["llm_risk_off_score"] = out["llm_risk_off_score"].fillna(0.0).clip(0.0, 1.0)

    aggregations = {
        "llm_sentiment_score": "mean",
        "llm_sentiment_confidence": "mean",
        "llm_risk_off_score": "mean",
        "llm_news_intensity": "sum",
    }
    out = out.groupby("date", as_index=False).agg(aggregations)
    out["llm_news_intensity"] = out["llm_news_intensity"].clip(0.0, 5.0)
    return out[["date"] + LLM_SENTIMENT_COLUMNS].sort_values("date").reset_index(drop=True)


def load_llm_sentiment_features(
    start_date: str,
    end_date: str,
    sentiment_path: str | Path | None = None,
) -> Optional[pd.DataFrame]:
    resolved = resolve_llm_sentiment_path(sentiment_path)
    if resolved is None:
        return None

    suffix = resolved.suffix.lower()
    if suffix == ".parquet":
        df = read_parquet_safe(resolved)
    elif suffix in {".csv", ".tsv"}:
        sep = "\t" if suffix == ".tsv" else ","
        df = pd.read_csv(resolved, sep=sep)
    elif suffix in {".json", ".jsonl"}:
        df = _read_json_records(resolved)
    else:
        raise ValueError(f"Unsupported LLM sentiment file format: {resolved}")

    out = _normalize_llm_sentiment_frame(df)
    start_ts = pd.Timestamp(start_date).normalize()
    end_ts = pd.Timestamp(end_date).normalize()
    out = out[(out["date"] >= start_ts) & (out["date"] <= end_ts)].copy()
    if out.empty:
        return pd.DataFrame(columns=["date"] + LLM_SENTIMENT_COLUMNS)
    return out.reset_index(drop=True)


def _merge_llm_sentiment_features(
    market: pd.DataFrame,
    start_date: str,
    end_date: str,
    *,
    include_llm_sentiment: bool = False,
    llm_sentiment_path: str | Path | None = None,
) -> pd.DataFrame:
    out = _normalize_date_column(market)
    if not include_llm_sentiment:
        for col in LLM_SENTIMENT_COLUMNS:
            if col not in out.columns:
                out[col] = 0.0
        return out

    sentiment = load_llm_sentiment_features(start_date, end_date, sentiment_path=llm_sentiment_path)
    if sentiment is None or sentiment.empty:
        print("[Portfolio Data Loader] 未找到可用的 LLM sentiment 特徵檔，將以 0 填補。")
        for col in LLM_SENTIMENT_COLUMNS:
            out[col] = 0.0
        return out

    print(f"[Portfolio Data Loader] 合併 LLM sentiment: {len(sentiment)} 筆")
    out = out.merge(sentiment, on="date", how="left")
    for col in LLM_SENTIMENT_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def download_market_features(
    start_date: str,
    end_date: str,
    interval: str = "1d",
    cache_dir: str = None,
    include_llm_sentiment: bool = False,
    llm_sentiment_path: str | Path | None = None,
) -> Optional[pd.DataFrame]:
    """Download TWSE index data and derive market features."""
    if cache_dir is None:
        cache_dir = PROJECT_ROOT / "data" / "portfolio_cache"
    else:
        cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    safe_start = start_date.replace("-", "")
    safe_end = end_date.replace("-", "")
    cache_file = cache_dir / f"TWII_DJI_{safe_start}_{safe_end}_{interval}_market_v3.parquet"

    if cache_file.exists():
        market = _read_relaxed_cache(
            cache_file,
            start_date=start_date,
            end_date=end_date,
            required_columns=["date"],
            min_rows=20,
        )
        if market is not None:
            return _merge_llm_sentiment_features(
                _normalize_date_column(market),
                start_date,
                end_date,
                include_llm_sentiment=include_llm_sentiment,
                llm_sentiment_path=llm_sentiment_path,
            )

    fallback_cache = _find_covering_cache(
        cache_dir,
        prefix="TWII_DJI",
        start_date=start_date,
        end_date=end_date,
        interval=interval,
        suffix="market_v3",
    )
    if fallback_cache is not None and fallback_cache != cache_file:
        market = _read_relaxed_cache(
            fallback_cache,
            start_date=start_date,
            end_date=end_date,
            required_columns=["date"],
            min_rows=20,
        )
        if market is not None:
            print(f"[Portfolio Data Loader] 使用大盤覆蓋快取: {fallback_cache.name}")
            return _merge_llm_sentiment_features(
                _normalize_date_column(market),
                start_date,
                end_date,
                include_llm_sentiment=include_llm_sentiment,
                llm_sentiment_path=llm_sentiment_path,
            )

    print(f"[Portfolio Data Loader] 下載大盤 {MARKET_TICKER}...", end=" ", flush=True)
    try:
        market = yf.Ticker(MARKET_TICKER).history(
            start=start_date,
            end=_inclusive_history_end(end_date),
            interval=interval,
        )
        if market.empty:
            print("無數據")
            return None

        market = market.reset_index()
        market.columns = [c.lower() for c in market.columns]
        market = _normalize_date_column(market)
        market = market.rename(columns={"close": "twse_close", "volume": "twse_volume"})

        market["twse_index_return_raw"] = (
            pd.to_numeric(market["twse_close"], errors="coerce").pct_change().fillna(0.0).clip(-0.2, 0.2)
        )
        vol_change = pd.to_numeric(market["twse_volume"], errors="coerce").pct_change()
        market["twse_index_volume_change_raw"] = (
            vol_change.replace([np.inf, -np.inf], 0.0).fillna(0.0).clip(-5.0, 5.0)
        )
        market["market_volatility_raw"] = (
            market["twse_index_return_raw"].rolling(20, min_periods=5).std(ddof=1).fillna(0.0).clip(0.0, 1.0)
        )

        market["twse_index_return"] = (market["twse_index_return_raw"] * 10.0).clip(-2.0, 2.0)
        market["twse_index_volume_change"] = market["twse_index_volume_change_raw"].clip(-2.0, 2.0)
        market["market_volatility"] = _rolling_zscore(market["market_volatility_raw"]).clip(-3.0, 3.0)

        print(f"[Portfolio Data Loader] 下載全球市場 {GLOBAL_TICKER}...", end=" ", flush=True)
        try:
            dji = yf.Ticker(GLOBAL_TICKER).history(
                start=start_date,
                end=_inclusive_history_end(end_date),
                interval=interval,
            )
            if dji.empty:
                print("無數據")
                dji_features = pd.DataFrame({"date": market["date"]})
            else:
                dji = dji.reset_index()
                dji.columns = [c.lower() for c in dji.columns]
                dji = _normalize_date_column(dji)
                dji_close = pd.to_numeric(dji["close"], errors="coerce")
                dji_features = pd.DataFrame({"date": dji["date"]})
                dji_features["dji_return_1d_raw"] = dji_close.pct_change().fillna(0.0).clip(-0.2, 0.2)
                dji_features["dji_return_5d_raw"] = dji_close.pct_change(5).fillna(0.0).clip(-0.4, 0.4)
                dji_features["dji_volatility_20d_raw"] = (
                    dji_features["dji_return_1d_raw"].rolling(20, min_periods=5).std(ddof=1).fillna(0.0).clip(0.0, 1.0)
                )
                ma60 = dji_close.rolling(60, min_periods=20).mean()
                dji_features["dji_ma60_ratio_raw"] = (dji_close / ma60 - 1.0).replace([np.inf, -np.inf], 0.0).fillna(0.0)
                peak60 = dji_close.rolling(60, min_periods=20).max()
                dji_features["dji_drawdown_60d_raw"] = (dji_close / peak60 - 1.0).replace([np.inf, -np.inf], 0.0).fillna(0.0)

                # Taiwan trading decisions can only use information known after the
                # previous US close, so shift all DJI signals by one local date.
                for col in [
                    "dji_return_1d_raw",
                    "dji_return_5d_raw",
                    "dji_volatility_20d_raw",
                    "dji_ma60_ratio_raw",
                    "dji_drawdown_60d_raw",
                ]:
                    dji_features[col] = dji_features[col].shift(1)
                print(f"{len(dji_features)} 筆")
        except Exception as e:
            print(f"失敗: {e}")
            dji_features = pd.DataFrame({"date": market["date"]})

        market = market.merge(dji_features, on="date", how="left")
        for col in [
            "dji_return_1d_raw",
            "dji_return_5d_raw",
            "dji_volatility_20d_raw",
            "dji_ma60_ratio_raw",
            "dji_drawdown_60d_raw",
        ]:
            if col not in market:
                market[col] = 0.0
            market[col] = pd.to_numeric(market[col], errors="coerce").ffill().fillna(0.0)

        market["dji_return_1d_lag1"] = (market["dji_return_1d_raw"] * 10.0).clip(-2.0, 2.0)
        market["dji_return_5d_lag1"] = (market["dji_return_5d_raw"] * 5.0).clip(-2.0, 2.0)
        market["dji_volatility_20d_lag1"] = _rolling_zscore(market["dji_volatility_20d_raw"]).clip(-3.0, 3.0)
        market["dji_ma60_ratio_lag1"] = market["dji_ma60_ratio_raw"].clip(-1.0, 1.0)
        market["dji_drawdown_60d_lag1"] = market["dji_drawdown_60d_raw"].clip(-1.0, 0.0)

        out = market[["date"] + MARKET_RAW_COLUMNS + [
            "twse_index_return",
            "twse_index_volume_change",
            "market_volatility",
            "dji_return_1d_lag1",
            "dji_return_5d_lag1",
            "dji_volatility_20d_lag1",
            "dji_ma60_ratio_lag1",
            "dji_drawdown_60d_lag1",
        ]].copy()
        write_parquet_safe(out, cache_file)
        print(f"{len(out)} 筆")
        return _merge_llm_sentiment_features(
            out,
            start_date,
            end_date,
            include_llm_sentiment=include_llm_sentiment,
            llm_sentiment_path=llm_sentiment_path,
        )
    except Exception as e:
        print(f"失敗: {e}")
        return None


def add_market_features(df: pd.DataFrame, market: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Merge market features into one stock dataframe."""
    out = _normalize_date_column(df)
    if market is None or market.empty:
        for col in LLM_SENTIMENT_COLUMNS:
            if col not in out.columns:
                out[col] = 0.0
        return out

    drop_cols = [c for c in MARKET_FEATURE_COLUMNS + MARKET_RAW_COLUMNS if c in out.columns]
    if drop_cols:
        out = out.drop(columns=drop_cols)

    market_cols = ["date"] + MARKET_RAW_COLUMNS + [
        "twse_index_return",
        "twse_index_volume_change",
        "market_volatility",
        "dji_return_1d_lag1",
        "dji_return_5d_lag1",
        "dji_volatility_20d_lag1",
        "dji_ma60_ratio_lag1",
        "dji_drawdown_60d_lag1",
    ] + LLM_SENTIMENT_COLUMNS
    available_market_cols = ["date"] + [col for col in market_cols[1:] if col in market.columns]
    out = out.merge(market[available_market_cols], on="date", how="left")
    for col in market_cols[1:]:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").ffill().fillna(0.0)

    stock_return = pd.to_numeric(out["close"], errors="coerce").pct_change()
    out["sector_correlation"] = (
        stock_return.rolling(20, min_periods=5)
        .corr(out["twse_index_return_raw"])
        .replace([np.inf, -np.inf], 0.0)
        .fillna(0.0)
        .clip(-1.0, 1.0)
    )
    return out


def add_long_horizon_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add slow trend/risk features that help ETF holding decisions."""
    out = _normalize_date_column(df)
    if "close" not in out.columns:
        return out

    close = pd.to_numeric(out["close"], errors="coerce")
    for window in (60, 120, 240):
        ma_col = f"ma{window}"
        if ma_col not in out.columns:
            out[ma_col] = close.rolling(window, min_periods=max(5, window // 4)).mean()

    out["close_ma120_ratio"] = (close / out["ma120"] - 1.0).replace([np.inf, -np.inf], 0.0)
    out["close_ma240_ratio"] = (close / out["ma240"] - 1.0).replace([np.inf, -np.inf], 0.0)
    out["ma60_ma240_ratio"] = (out["ma60"] / out["ma240"] - 1.0).replace([np.inf, -np.inf], 0.0)
    out["momentum_63"] = close.pct_change(63)
    out["momentum_126"] = close.pct_change(126)
    out["momentum_252"] = close.pct_change(252)

    rolling_high = close.rolling(252, min_periods=60).max()
    rolling_low = close.rolling(252, min_periods=60).min()
    out["high_252_position"] = ((close - rolling_low) / (rolling_high - rolling_low)).replace([np.inf, -np.inf], 0.0)

    rolling_peak_63 = close.rolling(63, min_periods=20).max()
    out["rolling_mdd_63"] = (close / rolling_peak_63 - 1.0).replace([np.inf, -np.inf], 0.0)

    long_cols = [
        "close_ma120_ratio",
        "close_ma240_ratio",
        "ma60_ma240_ratio",
        "momentum_63",
        "momentum_126",
        "momentum_252",
        "high_252_position",
        "rolling_mdd_63",
    ]
    for col in long_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).clip(-3.0, 3.0)

    return out


def _parse_roc_date(value: str) -> pd.Timestamp:
    year, month, day = value.split("/")
    return pd.Timestamp(year=int(year) + 1911, month=int(month), day=int(day))


def _download_twse_monthly_history(
    ticker: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Download TWSE monthly OHLCV data when Yahoo has no usable response."""
    local_code = ticker.split(".")[0]
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    months = pd.date_range(start_ts.replace(day=1), end_ts.replace(day=1), freq="MS")
    rows = []

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    for month in months:
        payload = None
        for attempt in range(3):
            response = session.get(
                "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY",
                params={
                    "date": month.strftime("%Y%m%d"),
                    "stockNo": local_code,
                    "response": "json",
                },
                timeout=30,
            )
            response.raise_for_status()
            try:
                payload = response.json()
                break
            except ValueError:
                time.sleep(0.5 * (attempt + 1))
        if payload is None:
            continue
        if payload.get("stat") != "OK":
            continue
        for raw in payload.get("data", []):
            rows.append(
                {
                    "date": _parse_roc_date(raw[0]),
                    "volume": int(str(raw[1]).replace(",", "")),
                    "open": float(str(raw[3]).replace(",", "")),
                    "high": float(str(raw[4]).replace(",", "")),
                    "low": float(str(raw[5]).replace(",", "")),
                    "close": float(str(raw[6]).replace(",", "")),
                }
            )
        time.sleep(0.15)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df[(df["date"] >= start_ts) & (df["date"] <= end_ts)].sort_values("date").reset_index(drop=True)
    df["dividends"] = 0.0
    df["stock splits"] = 0.0

    for split_date, factor in TWSE_SPLIT_ADJUSTMENTS.get(local_code, []):
        mask = df["date"] >= split_date
        df.loc[mask, ["open", "high", "low", "close"]] *= factor

    return df


def download_all_stocks(
    tickers: List[str],
    start_date: str,
    end_date: str,
    interval: str = "1d",
    cache_dir: str = None
) -> Dict[str, pd.DataFrame]:
    """
    下載所有股票的歷史數據

    Args:
        tickers: 股票代碼列表
        start_date: 開始日期
        end_date: 結束日期
        interval: K線週期
        cache_dir: 快取目錄

    Returns:
        dict: {ticker: DataFrame} 的字典
    """
    if cache_dir is None:
        cache_dir = PROJECT_ROOT / "data" / "portfolio_cache"
    else:
        cache_dir = Path(cache_dir)

    cache_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    print(f"[Portfolio Data Loader] 開始下載 {len(tickers)} 檔股票...")
    print(f"[Portfolio Data Loader] 日期區間: {start_date} ~ {end_date}")

    # TW/TWO mapping for Yahoo Finance
    YF_TICKER_MAP = {
        "00679B.TW": "00679B.TWO",
        "00751B.TW": "00751B.TWO",
    }

    market = download_market_features(start_date, end_date, interval=interval, cache_dir=str(cache_dir))

    for i, ticker in enumerate(tickers):
        safe_ticker = ticker.replace('.', '_')
        safe_start = start_date.replace('-', '')
        safe_end = end_date.replace('-', '')
        # Store raw OHLC prices separately. yfinance's adjusted prices already
        # embed dividends; using raw prices is required when the backtest adds
        # dividends as explicit cash flows.
        cache_file = cache_dir / f"{safe_ticker}_{safe_start}_{safe_end}_{interval}_raw_v1.parquet"

        # 嘗試從快取讀取（使用 CacheValidator 驗證）
        if cache_file.exists():
            df = _read_relaxed_cache(
                cache_file,
                start_date=start_date,
                end_date=end_date,
                required_columns=['date', 'open', 'high', 'low', 'close', 'volume'],
                min_rows=50,
                allow_late_start=True,
            )
            if df is not None:
                print(f"  [{i+1}/{len(tickers)}] {ticker} 從快取驗證通過: {len(df)} 筆")
                results[ticker] = add_long_horizon_features(add_market_features(df, market))
                continue
            else:
                print(f"  [{i+1}/{len(tickers)}] {ticker} 快取無效或過期，將重新下載")

        fallback_cache = _find_covering_cache(
            cache_dir,
            prefix=safe_ticker,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            suffix="raw_v1",
        )
        if fallback_cache is not None and fallback_cache != cache_file:
            df = _read_relaxed_cache(
                fallback_cache,
                start_date=start_date,
                end_date=end_date,
                required_columns=['date', 'open', 'high', 'low', 'close', 'volume'],
                min_rows=50,
                allow_late_start=True,
            )
            if df is not None:
                print(f"  [{i+1}/{len(tickers)}] {ticker} 使用覆蓋快取: {fallback_cache.name} ({len(df)} 筆)")
                results[ticker] = add_long_horizon_features(add_market_features(df, market))
                continue

        # 轉換為 Yahoo Finance ticker
        yf_ticker = YF_TICKER_MAP.get(ticker, ticker)
        
        # 下載
        print(f"  [{i+1}/{len(tickers)}] 下載 {ticker}... (YF: {yf_ticker})", end=" ", flush=True)
        try:
            yf_ticker_obj = yf.Ticker(yf_ticker)
            df = yf_ticker_obj.history(
                start=start_date,
                end=_inclusive_history_end(end_date),
                interval=interval,
                auto_adjust=False,
                actions=True,
            )

            if df.empty:
                print("no Yahoo data; trying TWSE fallback...", end=" ", flush=True)
                df = _download_twse_monthly_history(ticker, start_date, end_date)

            if df.empty:
                print("無數據")
                continue

            df = df.reset_index()
            if 'Datetime' in df.columns:
                df['Date'] = df['Datetime'].dt.tz_localize(None)
                df = df.drop(columns=['Datetime'])
            elif 'Date' in df.columns and str(df['Date'].dtype).startswith('datetime'):
                pass  # 已經是正確格式

            df.columns = [c.lower() for c in df.columns]

            # 確保必要欄位
            required = ['date', 'open', 'high', 'low', 'close', 'volume']
            for col in required:
                if col not in df.columns:
                    print(f"缺少欄位 {col}")
                    continue

            # 保存快取（使用 write_parquet_safe 避免 PyArrow 24 問題）
            write_ok = write_parquet_safe(df, cache_file)
            if write_ok:
                print(f"{len(df)} 筆")
            else:
                print(f"{len(df)} 筆（寫入快取失敗，跳過）")
            results[ticker] = add_long_horizon_features(add_market_features(df, market))

        except Exception as e:
            print(f"失敗: {e}")

    print(f"[Portfolio Data Loader] 完成，共 {len(results)} 檔股票")
    return results


def align_trading_days(stock_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    對齊所有股票的交易日 (取交集)

    這樣確保每個時間點所有股票都有數據。
    """
    # 取得每支股票的交易日
    trading_days_per_stock = {}
    for ticker, df in stock_data.items():
        if 'date' not in df.columns:
            continue
        df['date'] = pd.to_datetime(df['date'])
        trading_days_per_stock[ticker] = set(df['date'])

    # 取交集
    if not trading_days_per_stock:
        raise ValueError("沒有任何股票數據")

    common_days = set.intersection(*trading_days_per_stock.values())
    common_days = sorted(common_days)

    print(f"[align_trading_days] 共同交易日: {len(common_days)} 天")
    print(f"  {common_days[0]} ~ {common_days[-1]}")

    return pd.DataFrame({'date': common_days})


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    為股票數據添加技術指標。
    
    統一使用 data/technical_indicators.py 的 TechnicalIndicators 類別，
    確保計算邏輯一致，避免重複代碼。
    """
    try:
        from .data.technical_indicators import TechnicalIndicators
    except ImportError:
        from data.technical_indicators import TechnicalIndicators
    ti = TechnicalIndicators(df)
    return ti.calculate_all()


def merge_portfolio_data(
    stock_data: Dict[str, pd.DataFrame],
    add_indicators: bool = True
) -> pd.DataFrame:
    """
    合併所有股票數據為一個 DataFrame

    輸出格式:
        date, ticker, open, high, low, close, volume, turnover,
        returns, log_returns, ma5, ma20, ma60, rsi, macd, ...
    """
    all_dfs = []

    for ticker, df in stock_data.items():
        df = df.copy()
        if 'date' not in df.columns:
            continue

        df['date'] = pd.to_datetime(df['date'])

        if add_indicators:
            df = add_technical_indicators(df)

        df['ticker'] = ticker

        # 重新排列欄位
        cols = ['date', 'ticker', 'open', 'high', 'low', 'close', 'volume']
        other_cols = [c for c in df.columns if c not in cols]
        df = df[cols + other_cols]

        all_dfs.append(df)

    merged = pd.concat(all_dfs, ignore_index=True)
    merged = merged.sort_values(['ticker', 'date']).reset_index(drop=True)

    print(f"[merge_portfolio_data] 合併後總共 {len(merged)} 筆")
    return merged


def calculate_portfolio_weights(current_prices: Dict[str, float]) -> Dict[str, float]:
    """
    根據 current_prices 和持股數計算各股票權重
    """
    holdings = PORTFOLIO_HOLDINGS
    values = {}
    total = 0

    for ticker, info in holdings.items():
        shares = info['shares']
        price = current_prices.get(ticker, 0)
        value = shares * price
        values[ticker] = value
        total += value

    if total == 0:
        return {t: 1.0/len(values) for t in values}

    return {t: v / total for t, v in values.items()}


# =============================================================================
# 主程式：下載並準備資料
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='下載投資組合歷史數據')
    parser.add_argument('--start', type=str, default='2000-01-01')
    parser.add_argument('--end', type=str, default='2010-12-31')
    parser.add_argument('--mode', type=str, default='all',
                        choices=['all', 'train', 'test'])
    args = parser.parse_args()

    if args.mode == 'train':
        start, end = TRAIN_START_DATE, TRAIN_END_DATE
    elif args.mode == 'test':
        start, end = TEST_START_DATE, TEST_END_DATE
    else:
        start, end = args.start, args.end

    print("=" * 60)
    print("投資組合數據下載")
    print("=" * 60)
    print(f"股票: {ALL_TICKERS}")
    print(f"日期: {start} ~ {end}")
    print("=" * 60)

    # 下載
    stock_data = download_all_stocks(ALL_TICKERS, start, end)

    # 合併
    merged = merge_portfolio_data(stock_data)

    # 儲存
    output_file = PROJECT_ROOT / "data" / "portfolio_data.parquet"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(output_file, index=False)
    print(f"\n數據已儲存至: {output_file}")
