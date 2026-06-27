"""Quick diagnostic: check FEATURE_COLUMNS in panel after _align_panel"""
import sys
sys.path.insert(0, ".")
import pandas as pd
from portfolio_data_loader import download_all_stocks

FEATURE_COLUMNS = [
    "close_ma120_ratio", "close_ma240_ratio", "ma60_ma240_ratio",
    "momentum_21", "momentum_63", "momentum_126", "momentum_252", "rolling_mdd_63",
    "rsi_14", "macd_signal", "macd_hist", "vol_ratio_20", "bb_position", "atr_14",
]

def _slice_by_date(df, start, end):
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"])
        if out["date"].dt.tz is not None:
            out["date"] = out["date"].dt.tz_localize(None)
    elif "timestamp" in out.columns:
        out["date"] = pd.to_datetime(out["timestamp"])
        if out["date"].dt.tz is not None:
            out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()

def _compute_features(df):
    df = df.copy()
    close = df["close"]
    volume = df["volume"]
    df["close_ma120_ratio"] = close / (close.rolling(120).mean() + 1e-10)
    df["close_ma240_ratio"] = close / (close.rolling(240).mean() + 1e-10)
    df["ma60_ma240_ratio"] = close.rolling(60).mean() / (close.rolling(240).mean() + 1e-10)
    df["momentum_21"] = close / (close.shift(21) + 1e-10) - 1
    df["momentum_63"] = close / (close.shift(63) + 1e-10) - 1
    df["momentum_126"] = close / (close.shift(126) + 1e-10) - 1
    df["momentum_252"] = close / (close.shift(252) + 1e-10) - 1
    rolling_max = close.rolling(63).max()
    rolling_min = close.rolling(63).min()
    df["rolling_mdd_63"] = (close - rolling_max) / (rolling_max - rolling_min + 1e-10)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi_14"] = 100 - (100 / (gain / (loss + 1e-10) + 1))
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9).mean()
    df["macd_signal"] = signal_line / (close + 1e-10)
    df["macd_hist"] = (macd_line - signal_line) / (close + 1e-10)
    df["vol_ratio_20"] = volume / (volume.rolling(20, min_periods=1).mean() + 1e-10)
    bb20 = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df["bb_position"] = (close - (bb20 - 2 * bb_std)) / (4 * bb_std + 1e-10)
    high = df.get("high", close)
    low = df.get("low", close)
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    df["atr_14"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(14).mean() / (close + 1e-10)
    return df

def _align_panel(stock_data, tickers, start, end):
    frames = []
    for ticker in tickers:
        df = _slice_by_date(stock_data[ticker], start, end)
        df = _compute_features(df)
        cols = ["date", "close"] + [c for c in FEATURE_COLUMNS if c in df.columns]
        part = df[cols].copy()
        part = part.rename(columns={c: f"{ticker}_{c}" for c in cols if c != "date"})
        frames.append(part)
    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on="date", how="inner")
    panel = panel.sort_values("date").reset_index(drop=True)
    return panel.ffill().bfill().fillna(0.0)

data = download_all_stocks(["0050.TW", "00631L.TW", "00632R.TW"], "2025-01-01", "2026-05-16")
panel = _align_panel(data, ["0050.TW", "00631L.TW", "00632R.TW"], "2025-01-01", "2026-05-15")

print(f"Panel shape: {panel.shape}")
print(f"Panel columns: {panel.columns.tolist()}")

feat_cols = []
missing = []
for tic in ["0050.TW", "00631L.TW", "00632R.TW"]:
    for fc in FEATURE_COLUMNS:
        col = f"{tic}_{fc}"
        if col in panel.columns:
            feat_cols.append(col)
        else:
            missing.append(col)

print(f"\nFeature cols found: {len(feat_cols)} / {3*len(FEATURE_COLUMNS)}")
print(f"Missing columns ({len(missing)}): {missing}")

# Check what columns ARE in panel for 0050.TW
tic0_cols = [c for c in panel.columns if c.startswith("0050.TW_")]
print(f"\n0050.TW columns in panel: {tic0_cols}")