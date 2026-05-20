#!/usr/bin/env python3
"""雙組訓練：Group A (0050+00631L+00632R) + Group B (高股息/S&P500/美債) → Group A 預設回測 2024-2026"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.utils import FloatSchedule

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
FINRL_ROOT = PROJECT_ROOT / "FinRL"
PORTFOLIO_CACHE_DIR = FINRL_ROOT / "data" / "portfolio_cache"

from portfolio_config import COMMISSION_RATE, ETF_TAX_RATE, TRANSACTION_TAX_RATE
from portfolio_train_v2 import calculate_backtest_metrics
from build_llm_sentiment_features import prepare_llm_sentiment_path
from FinRL.data.data_utils import read_parquet_safe
from FinRL.data.stock_db import query_ohlcv
from FinRL.portfolio_data_loader import (
    LLM_SENTIMENT_COLUMNS,
    MARKET_FEATURE_COLUMNS,
    add_long_horizon_features,
    add_market_features,
    download_market_features,
    resolve_llm_sentiment_path,
)


# ==============================================================================
# 雙組設定
# ==============================================================================

DEFAULT_INITIAL_CASH = 1_000_000.0
DEFAULT_DOWNLOAD_END = "2026-05-09"
DEFAULT_WORKBOOK = PROJECT_ROOT / "taiwan_stock_20260516_group.xlsx"

# Group A: 0050 + 00631L + 00632R，預設訓練 2020-2023 / 回測 2024-2026
DEFAULT_GROUP_A_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]
DEFAULT_GROUP_A_TRAIN_START = "2020-01-01"
DEFAULT_GROUP_A_TRAIN_END = "2023-12-31"
DEFAULT_GROUP_A_MODEL_NAME = "group_a_3tickers_2020_2023"
DEFAULT_GROUP_A_PROFILE = "default"
DEFAULT_GROUP_A_DCA_DAY = 26
DEFAULT_GROUP_A_DCA_0050 = 5_000.0
DEFAULT_GROUP_A_INVERSE_MAX_HOLD_DAYS = 5
DEFAULT_GROUP_A_PVA_TARGET_VOL = 0.012
DEFAULT_GROUP_A_PVA_MIN_LEVERAGE_SCALE = 0.35
DEFAULT_GROUP_A_PVA_INVERSE_HEDGE_BUDGET = 0.30
DEFAULT_GROUP_A_SENTIMENT_RISK_OFF_THRESHOLD = 0.10
DEFAULT_GROUP_A_SENTIMENT_SEVERE_THRESHOLD = 0.15
DEFAULT_GROUP_A_SENTIMENT_MIN_CONFIDENCE = 0.40
DEFAULT_GROUP_A_SENTIMENT_MIN_INTENSITY = 0.0
DEFAULT_GROUP_A_SENTIMENT_RISK_OFF_INVERSE_FLOOR = 0.15
DEFAULT_GROUP_A_SENTIMENT_SEVERE_INVERSE_FLOOR = 0.30

# Group B: 多檔訓練（2020-2024）
DEFAULT_GROUP_B_TICKERS = [
    "0056.TW",  # 元大高股息
    "00713.TW",  # 元大台灣高息低波
    "00878.TW",  # 國泰永續高股息
    "00646.TW",  # 元大S&P500
    "00679B.TWO", # 元大美債20年
    "00751B.TWO", # 元大AAA至A公司債
]
DEFAULT_GROUP_B_TRAIN_START = "2020-01-01"
DEFAULT_GROUP_B_TRAIN_END = "2024-12-31"
DEFAULT_GROUP_B_MODEL_NAME = "group_b_multi_2020_2024"

# 統一回測區間
DEFAULT_BACKTEST_START = "2024-01-01"
DEFAULT_BACKTEST_END = "2026-05-08"

# 訓練超參
DEFAULT_TIMESTEPS = 400_000
DEFAULT_SEED = 42

FEATURE_COLUMNS = [
    "close_ma120_ratio",
    "close_ma240_ratio",
    "ma60_ma240_ratio",
    "momentum_21",
    "momentum_63",
    "momentum_126",
    "momentum_252",
    "rolling_mdd_63",
]


def _resolve_group_a_llm_sentiment_input(
    input_path: str | None,
) -> tuple[Path | None, dict[str, object] | None]:
    if input_path:
        resolved_path, info = prepare_llm_sentiment_path(input_path)
        return resolved_path, info

    resolved_path = resolve_llm_sentiment_path(None)
    if resolved_path is None:
        return None, None

    info: dict[str, object] = {
        "mode": "pre_scored",
        "generated": False,
        "path": str(resolved_path),
        "source_path": str(resolved_path),
        "text_columns": [],
    }
    return resolved_path, info

DJI_FEATURE_COLUMNS = [
    "dji_return_1d_lag1",
    "dji_return_5d_lag1",
    "dji_volatility_20d_lag1",
    "dji_ma60_ratio_lag1",
    "dji_drawdown_60d_lag1",
]

GROUP_A_PVA_OBS_COLUMNS = [
    "0050_pva_p_z",
    "0050_pva_v_z",
    "0050_pva_a_z",
    "0050_sjm_state_code",
]

GROUP_A_PROFILE_PRESETS = {
    "default": {
        "env": {
            "profile_name": "default",
            "turnover_penalty": 0.0005,
            "equal_benchmark_weight": 0.3,
            "blend_benchmark_weight": 2.2,
            "underperform_0050_weight": 0.05,
            "leveraged_benchmark_weight": 1.0,
            "drawdown_penalty_weight": 0.2,
            "deep_drawdown_penalty_weight": 0.0,
            "deep_drawdown_threshold": 1.0,
            "concentration_penalty_weight": 0.3,
            "concentration_threshold": 0.65,
            "min_rebalance_days": 5,
            "leverage_cap": 0.30,
            "inverse_cap": 0.30,
            "stress_gate_enabled": False,
            "start_allocation": "blend50",
        },
        "ppo": {
            "learning_rate": 3e-4,
            "n_steps": 1024,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "ent_coef": 0.08,
        },
    },
    "conservative": {
        "env": {
            "profile_name": "conservative",
            "turnover_penalty": 0.0025,
            "equal_benchmark_weight": 0.15,
            "blend_benchmark_weight": 0.0,
            "underperform_0050_weight": 0.2,
            "leveraged_benchmark_weight": 0.25,
            "drawdown_penalty_weight": 1.25,
            "deep_drawdown_penalty_weight": 2.0,
            "deep_drawdown_threshold": 0.10,
            "concentration_penalty_weight": 0.0,
            "concentration_threshold": 1.0,
            "min_rebalance_days": 15,
            "leverage_cap": 0.30,
            "inverse_cap": 0.30,
            "stress_gate_enabled": True,
            "start_allocation": "core_0050",
        },
        "ppo": {
            "learning_rate": 2e-4,
            "n_steps": 1024,
            "gamma": 0.99,
            "gae_lambda": 0.95,
            "ent_coef": 0.02,
        },
    },
}


# ==============================================================================
# 通用工具
# ==============================================================================

def _slice_by_date(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"])
    if out["date"].dt.tz is not None:
        out["date"] = out["date"].dt.tz_localize(None)
    out = out.dropna(subset=["open", "high", "low", "close", "volume"])
    return out[(out["date"] >= pd.Timestamp(start)) & (out["date"] <= pd.Timestamp(end))].copy()


def _resolve_group_a_profile(profile_name: str) -> dict:
    preset = GROUP_A_PROFILE_PRESETS.get(profile_name)
    if preset is None:
        supported = ", ".join(sorted(GROUP_A_PROFILE_PRESETS))
        raise ValueError(f"Unsupported Group A profile: {profile_name}. Choices: {supported}")
    return {
        "name": profile_name,
        "env": dict(preset["env"]),
        "ppo": dict(preset["ppo"]),
    }


def _compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """計算投資組合環境所需的技術特徵"""
    df = df.copy()
    close = df["close"]
    df["close_ma120_ratio"] = close / (close.rolling(120).mean() + 1e-10)
    df["close_ma240_ratio"] = close / (close.rolling(240).mean() + 1e-10)
    df["ma60_ma240_ratio"] = (
        close.rolling(60).mean() / (close.rolling(240).mean() + 1e-10)
    )
    df["momentum_21"] = close / (close.shift(21) + 1e-10) - 1
    df["momentum_63"] = close / (close.shift(63) + 1e-10) - 1
    df["momentum_126"] = close / (close.shift(126) + 1e-10) - 1
    df["momentum_252"] = close / (close.shift(252) + 1e-10) - 1
    rolling_max = close.rolling(63).max()
    rolling_min = close.rolling(63).min()
    df["rolling_mdd_63"] = (close - rolling_max) / (rolling_max - rolling_min + 1e-10)
    return df


def _rolling_zscore(series: pd.Series, window: int = 252, min_periods: int = 63) -> pd.Series:
    values = series.astype(float)
    mean = values.rolling(window, min_periods=min_periods).mean()
    std = values.rolling(window, min_periods=min_periods).std(ddof=1)
    return ((values - mean) / std.replace(0.0, np.nan)).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def _safe_panel_col(panel: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column in panel.columns:
        return panel[column].astype(float)
    return pd.Series(default, index=panel.index, dtype=float)


def _add_group_a_panel_features(panel: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    panel = panel.copy()
    if not {"0050.TW", "00631L.TW", "00632R.TW"}.issubset(set(tickers)):
        return panel

    # Group A uses close/MA ratios in raw form, so P must be centered at 0.0
    # before feeding the PVA/SJM state logic.
    pva_p = _safe_panel_col(panel, "0050.TW_close_ma120_ratio", 1.0) - 1.0
    pva_v = _safe_panel_col(panel, "0050.TW_momentum_63", 0.0)
    pva_a = pva_v - pva_v.shift(20).fillna(pva_v)
    panel["0050_pva_p"] = pva_p
    panel["0050_pva_v"] = pva_v
    panel["0050_pva_a"] = pva_a
    panel["0050_pva_p_z"] = _rolling_zscore(pva_p)
    panel["0050_pva_v_z"] = _rolling_zscore(pva_v)
    panel["0050_pva_a_z"] = _rolling_zscore(pva_a)

    panic = (panel["0050_pva_a_z"] < -2.0) | (panel["0050_pva_v_z"] < -2.0)
    greed = (panel["0050_pva_v_z"] > 1.0) & (panel["0050_pva_a_z"] > 0.0)
    panel["0050_sjm_state_code"] = 0.0
    panel.loc[greed, "0050_sjm_state_code"] = 1.0
    panel.loc[panic, "0050_sjm_state_code"] = -1.0
    return panel.replace([np.inf, -np.inf], 0.0).fillna(0.0)


def _align_panel(
    stock_data: dict[str, pd.DataFrame],
    tickers: list[str],
    start: str,
    end: str,
    *,
    shared_feature_cols: list[str] | None = None,
) -> pd.DataFrame:
    frames = []
    shared_part = None
    shared_feature_cols = shared_feature_cols or []
    for ticker in tickers:
        df = _slice_by_date(stock_data[ticker], start, end)
        df = _compute_features(df)
        if shared_part is None and shared_feature_cols:
            available_shared_cols = [c for c in shared_feature_cols if c in df.columns]
            if available_shared_cols:
                shared_part = df[["date"] + available_shared_cols].copy()
        cols = ["date", "open", "close"] + [c for c in FEATURE_COLUMNS if c in df.columns]
        part = df[cols].copy()
        part = part.rename(columns={c: f"{ticker}_{c}" for c in cols if c != "date"})
        frames.append(part)

    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on="date", how="inner")
    if shared_part is not None:
        panel = panel.merge(shared_part, on="date", how="left")
    panel = panel.sort_values("date").reset_index(drop=True)
    panel = panel.ffill().bfill().fillna(0.0)
    panel = _add_group_a_panel_features(panel, tickers)
    return panel.ffill().bfill().fillna(0.0)


def _prices(panel: pd.DataFrame, tickers: list[str], field: str = "close") -> np.ndarray:
    return panel[[f"{ticker}_{field}" for ticker in tickers]].to_numpy(dtype=float)


def _clip_weights_array(weights: np.ndarray) -> np.ndarray:
    arr = np.asarray(weights, dtype=float)
    arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(arr, 0.0, None)


def _raw_weights_for(tickers: list[str], w: dict[str, float]) -> np.ndarray:
    arr = np.array([w.get(t, 0.0) for t in tickers], dtype=float)
    return _clip_weights_array(arr)


def _weights_for(tickers: list[str], w: dict[str, float]) -> np.ndarray:
    arr = _raw_weights_for(tickers, w)
    s = arr.sum()
    return arr / s if s > 0 else np.ones(len(tickers)) / len(tickers)


def _normalize_weights_array(weights: np.ndarray) -> np.ndarray:
    arr = _clip_weights_array(weights)
    total = float(arr.sum())
    if total <= 0.0:
        return np.ones(len(arr), dtype=float) / len(arr)
    return arr / total


def _sigmoid(value: float) -> float:
    clipped = float(np.clip(value, -20.0, 20.0))
    return float(1.0 / (1.0 + np.exp(-clipped)))


DEFAULT_ACTION_LABELS = {
    0: "hold_current_weights",
    1: "rebalance_to_0050_50_00631L_50",
    2: "rebalance_to_0050_40_00631L_60",
    3: "rebalance_to_0050_40_00713_35_00878_25",
    4: "rebalance_to_equal_weight",
}


GROUP_A_ACTION_SCHEMA_LEGACY_V1 = "legacy_v1"
GROUP_A_ACTION_SCHEMA_TRIPLET_V2 = "triplet_v2"
GROUP_A_ACTION_SCHEMA_TRIPLET_V3_CASH50 = "triplet_v3_cash50"
GROUP_A_ACTION_SCHEMA_CHOICES = (
    GROUP_A_ACTION_SCHEMA_LEGACY_V1,
    GROUP_A_ACTION_SCHEMA_TRIPLET_V2,
    GROUP_A_ACTION_SCHEMA_TRIPLET_V3_CASH50,
)


GROUP_A_LEGACY_ACTION_LABELS = {
    0: "hold_current_weights",
    1: "rebalance_to_0050_50_00631L_50",
    2: "rebalance_to_0050_40_00631L_60",
    3: "rebalance_to_0050_30_00631L_70",
    4: "rebalance_to_equal_weight",
}


GROUP_A_DEFAULT_ACTION_LABELS = {
    0: "hold_current_weights",
    1: "rebalance_to_0050_85_00631L_15",
    2: "rebalance_to_0050_70_00631L_30",
    3: "rebalance_to_0050_100",
    4: "rebalance_to_0050_70_00632R_30",
}


GROUP_A_CASH50_ACTION_LABELS = {
    0: "hold_current_weights",
    1: "rebalance_to_0050_85_00631L_15",
    2: "rebalance_to_0050_70_00631L_30",
    3: "rebalance_to_0050_100",
    4: "rebalance_to_0050_70_00632R_30",
    5: "rebalance_to_0050_50_00631L_25_cash_25",
}


GROUP_A_CONSERVATIVE_ACTION_LABELS = {
    0: "hold_current_weights",
    1: "rebalance_to_0050_100",
    2: "rebalance_to_0050_85_00631L_15",
    3: "rebalance_to_0050_70_00632R_30",
    4: "rebalance_to_0050_70_00631L_30",
}


def _weights_to_dict(tickers: list[str], weights: np.ndarray) -> dict[str, float]:
    return {ticker: float(weight) for ticker, weight in zip(tickers, np.asarray(weights, dtype=float))}


def _weights_to_label(tickers: list[str], weights: np.ndarray) -> str:
    cleaned_weights = _clip_weights_array(weights)
    items = []
    for ticker, weight in zip(tickers, cleaned_weights):
        if float(weight) <= 1e-6:
            continue
        code = ticker.split(".")[0]
        pct = float(weight) * 100.0
        rounded = round(pct)
        pct_text = f"{int(rounded)}%" if abs(pct - rounded) < 0.05 else f"{pct:.1f}%"
        items.append(f"{code} {pct_text}")
    cash_weight = max(0.0, 1.0 - float(cleaned_weights.sum()))
    if cash_weight > 1e-6:
        pct = cash_weight * 100.0
        rounded = round(pct)
        pct_text = f"{int(rounded)}%" if abs(pct - rounded) < 0.05 else f"{pct:.1f}%"
        items.append(f"cash {pct_text}")
    return " / ".join(items) if items else "all_cash"


def infer_group_a_action_schema(
    payload: dict | None = None,
    *,
    model_name: str | None = None,
    action_schema: str | None = None,
) -> str:
    explicit = action_schema
    if payload:
        explicit = (
            explicit
            or payload.get("group_a_action_schema")
            or payload.get("group_a", {}).get("action_schema")
        )
        if model_name is None:
            model_name = payload.get("group_a", {}).get("model_name")

    normalized = str(explicit or "").strip().lower()
    if normalized in GROUP_A_ACTION_SCHEMA_CHOICES:
        return normalized

    model_text = str(model_name or "").strip()
    model_key = model_text.lower()
    if model_text.endswith("_631l_632r") or model_text == "group_a_smoke_tmp_20260518":
        return GROUP_A_ACTION_SCHEMA_LEGACY_V1
    if "cash50" in model_key or "cash_buffer" in model_key or "cashbuf" in model_key:
        return GROUP_A_ACTION_SCHEMA_TRIPLET_V3_CASH50

    return GROUP_A_ACTION_SCHEMA_TRIPLET_V2


def _resolve_model_checkpoint(path_or_name: str | None) -> Path | None:
    if not path_or_name:
        return None

    candidate = Path(str(path_or_name).strip())
    search_paths = []
    if candidate.is_absolute():
        search_paths.append(candidate)
    else:
        search_paths.append((PROJECT_ROOT / candidate).resolve())
        search_paths.append((PROJECT_ROOT / "models" / "portfolio" / candidate).resolve())
        if candidate.suffix != ".zip":
            search_paths.append((PROJECT_ROOT / "models" / "portfolio" / f"{candidate.name}.zip").resolve())

    for path in search_paths:
        if path.exists():
            return path

    checked = ", ".join(str(p) for p in search_paths)
    raise FileNotFoundError(f"Model checkpoint not found: {path_or_name}. Checked: {checked}")


def _action_labels_for_context(
    profile_name: str,
    is_group_a_triplet: bool,
    action_schema: str | None = None,
) -> dict[int, str]:
    if is_group_a_triplet:
        schema = infer_group_a_action_schema(action_schema=action_schema)
        if profile_name == "conservative":
            return GROUP_A_CONSERVATIVE_ACTION_LABELS
        if schema == GROUP_A_ACTION_SCHEMA_LEGACY_V1:
            return GROUP_A_LEGACY_ACTION_LABELS
        if schema == GROUP_A_ACTION_SCHEMA_TRIPLET_V3_CASH50:
            return GROUP_A_CASH50_ACTION_LABELS
        return GROUP_A_DEFAULT_ACTION_LABELS
    return DEFAULT_ACTION_LABELS


def _action_label_for_context(
    action: int,
    profile_name: str,
    is_group_a_triplet: bool,
    action_schema: str | None = None,
) -> str:
    labels = _action_labels_for_context(profile_name, is_group_a_triplet, action_schema)
    return labels.get(int(action), f"action_{int(action)}")


def _normalize_ticker_code(code: str) -> str:
    code = str(code).strip().upper()
    if not code:
        raise ValueError("empty ticker code")
    if "." in code:
        return code
    if code in {"00679B", "00751B"}:
        return f"{code}.TWO"
    return f"{code}.TW"


def _extract_code(cell_value: object) -> str | None:
    if pd.isna(cell_value):
        return None
    text = str(cell_value).strip().upper()
    if not text:
        return None
    matches = re.findall(r"([0-9]{4,5}[A-Z]*)", text)
    if not matches:
        return None
    return matches[-1]


def _load_groups_from_workbook(xlsx_path: Path) -> dict[str, list[str]]:
    df = pd.read_excel(xlsx_path)
    columns = list(df.columns)
    group_positions = []
    for idx, name in enumerate(columns):
        label = str(name).strip().lower()
        if label in {"group a", "group b"}:
            group_positions.append((idx, label))

    if len(group_positions) < 2:
        raise ValueError(f"Workbook does not expose both Group A / Group B headers: {xlsx_path}")
    if df.empty:
        raise ValueError(f"Workbook has no holdings rows: {xlsx_path}")

    groups: dict[str, list[str]] = {}
    for pos, (start_idx, label) in enumerate(group_positions):
        end_idx = group_positions[pos + 1][0] if pos + 1 < len(group_positions) else len(columns)
        tickers: list[str] = []
        for col_idx in range(start_idx, end_idx):
            code = _extract_code(df.iloc[0, col_idx])
            if code is None:
                continue
            ticker = _normalize_ticker_code(code)
            if ticker not in tickers:
                tickers.append(ticker)
        if not tickers:
            raise ValueError(f"{label} has no parsed tickers in workbook: {xlsx_path}")
        groups[label.replace(" ", "_")] = tickers

    if "group_a" not in groups or "group_b" not in groups:
        raise ValueError(f"Workbook groups incomplete: {xlsx_path}")
    return groups


def _find_covering_portfolio_cache(
    ticker: str,
    start: str,
    end: str,
    *,
    require_full_coverage: bool = True,
) -> Path | None:
    safe_ticker = ticker.replace(".", "_")
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    pattern = re.compile(rf"^{re.escape(safe_ticker)}_(\d{{8}})_(\d{{8}})_1d_raw_v1\.parquet$")
    candidates: list[tuple[int, int, int, Path]] = []
    for path in PORTFOLIO_CACHE_DIR.glob(f"{safe_ticker}_*_1d_raw_v1.parquet"):
        match = pattern.match(path.name)
        if not match:
            continue
        cache_start = pd.Timestamp(match.group(1)).normalize()
        cache_end = pd.Timestamp(match.group(2)).normalize()
        if require_full_coverage:
            if cache_start <= start_ts and cache_end >= end_ts:
                span_days = int((cache_end - cache_start).days)
                candidates.append((span_days, -cache_end.value, 0, path))
        else:
            overlap_start = max(cache_start, start_ts)
            overlap_end = min(cache_end, end_ts)
            if overlap_end < overlap_start:
                continue
            overlap_days = int((overlap_end - overlap_start).days)
            span_days = int((cache_end - cache_start).days)
            candidates.append((-overlap_days, span_days, -cache_end.value, path))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def _load_portfolio_cache_ohlcv(
    ticker: str,
    start: str,
    end: str,
    *,
    allow_partial: bool = False,
) -> pd.DataFrame:
    cache_path = _find_covering_portfolio_cache(
        ticker,
        start,
        end,
        require_full_coverage=not allow_partial,
    )
    if cache_path is None:
        return pd.DataFrame()
    df = read_parquet_safe(cache_path)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [str(col).lower().replace(" ", "_") for col in df.columns]
    if "date" not in df.columns:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))].copy()
    if "stock_splits" not in df.columns:
        if "stocksplits" in df.columns:
            df = df.rename(columns={"stocksplits": "stock_splits"})
        else:
            df["stock_splits"] = 0.0
    if "dividends" not in df.columns:
        df["dividends"] = 0.0
    return df[["date", "open", "high", "low", "close", "volume", "dividends", "stock_splits"]].sort_values("date")


def _load_ohlcv_db_first(ticker: str, start: str, end: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    db_df = query_ohlcv(ticker, start, end)
    if not db_df.empty:
        db_df = db_df.rename(columns={"dt": "date"}).copy()
        db_df["date"] = pd.to_datetime(db_df["date"]).dt.tz_localize(None)
        frames.append(db_df[["date", "open", "high", "low", "close", "volume", "dividends", "stock_splits"]])

    db_covers = False
    if not db_df.empty:
        db_start = pd.Timestamp(db_df["date"].min()).normalize()
        db_end = pd.Timestamp(db_df["date"].max()).normalize()
        db_covers = db_start <= pd.Timestamp(start).normalize() and db_end >= pd.Timestamp(end).normalize()

    if not db_covers:
        cache_df = _load_portfolio_cache_ohlcv(ticker, start, end, allow_partial=True)
        if not cache_df.empty:
            frames.append(cache_df)

    if not frames:
        return pd.DataFrame()

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)
    merged["symbol"] = ticker
    return merged


def load_stock_data_db_first(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    print(f"[DB-first loader] 讀取資料: {start} ~ {end}")
    results: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        df = _load_ohlcv_db_first(ticker, start, end)
        if df.empty:
            print(f"  - {ticker}: 無資料")
            continue
        source_parts = []
        db_df = query_ohlcv(ticker, start, end)
        if not db_df.empty:
            source_parts.append("DB")
        if _find_covering_portfolio_cache(ticker, start, end) is not None:
            source_parts.append("cache")
        print(
            f"  - {ticker}: {len(df)} 筆 "
            f"({pd.Timestamp(df['date'].min()).date()} ~ {pd.Timestamp(df['date'].max()).date()}) "
            f"[{' + '.join(source_parts) if source_parts else 'unknown'}]"
        )
        results[ticker] = df
    return results


def _effective_common_start(
    stock_data: dict[str, pd.DataFrame],
    tickers: list[str],
    start: str,
    end: str,
) -> pd.Timestamp | None:
    starts: list[pd.Timestamp] = []
    request_start = pd.Timestamp(start).normalize()
    request_end = pd.Timestamp(end).normalize()
    for ticker in tickers:
        df = stock_data.get(ticker)
        if df is None or df.empty:
            return None
        dates = pd.to_datetime(df["date"]).dt.tz_localize(None)
        dates = dates[(dates >= request_start) & (dates <= request_end)]
        if dates.empty:
            return None
        starts.append(pd.Timestamp(dates.min()).normalize())
    return max(starts) if starts else None


def attach_market_features_db_first(
    stock_data: dict[str, pd.DataFrame],
    tickers: list[str],
    start: str,
    end: str,
    *,
    include_llm_sentiment: bool = False,
    llm_sentiment_path: str | None = None,
) -> dict[str, pd.DataFrame]:
    common_start = _effective_common_start(stock_data, tickers, start, end)
    if common_start is None:
        raise RuntimeError(f"無法為 {tickers} 建立共同市場特徵區間")

    common_end_candidates: list[pd.Timestamp] = []
    request_start = pd.Timestamp(start).normalize()
    request_end = pd.Timestamp(end).normalize()
    for ticker in tickers:
        df = stock_data.get(ticker)
        if df is None or df.empty:
            raise RuntimeError(f"無法為 {tickers} 建立共同市場特徵區間")
        dates = pd.to_datetime(df["date"]).dt.tz_localize(None)
        dates = dates[(dates >= request_start) & (dates <= request_end)]
        if dates.empty:
            raise RuntimeError(f"無法為 {tickers} 建立共同市場特徵區間")
        common_end_candidates.append(pd.Timestamp(dates.max()).normalize())

    common_end = min(common_end_candidates) if common_end_candidates else request_end

    market = download_market_features(
        str(common_start.date()),
        str(common_end.date()),
        include_llm_sentiment=include_llm_sentiment,
        llm_sentiment_path=llm_sentiment_path,
    )
    if market is None or market.empty:
        raise RuntimeError(
            f"無法載入 DJI/TWII 市場特徵: {common_start.date()} ~ {common_end.date()}"
        )

    print(
        f"[Market features] 為 {tickers} 合併市場特徵: "
        f"{common_start.date()} ~ {pd.Timestamp(market['date'].max()).date()}"
    )
    enriched: dict[str, pd.DataFrame] = {}
    for ticker, df in stock_data.items():
        out = df.copy()
        if ticker in tickers:
            out = add_market_features(out, market)
            out = add_long_horizon_features(out)
        enriched[ticker] = out
    return enriched


# ==============================================================================
# 投資組合 Gym 環境（支援任意檔數）
# ==============================================================================

class PortfolioEnv(gym.Env):
    """通用多檔投資組合環境，5 個動作策略。"""

    metadata = {"render_modes": []}

    def __init__(
        self,
        panel: pd.DataFrame,
        tickers: list[str],
        shared_feature_cols: list[str] | None = None,
        initial_cash: float = DEFAULT_INITIAL_CASH,
        commission_rate: float = COMMISSION_RATE,
        turnover_penalty: float = 0.0005,
        equal_benchmark_weight: float = 0.3,
        blend_benchmark_weight: float = 3.0,
        underperform_0050_weight: float = 0.1,
        leveraged_benchmark_weight: float = 0.0,
        drawdown_penalty_weight: float = 0.2,
        deep_drawdown_penalty_weight: float = 0.0,
        deep_drawdown_threshold: float = 1.0,
        concentration_penalty_weight: float = 0.3,
        concentration_threshold: float = 0.65,
        min_rebalance_days: int = 5,
        leverage_cap: float = 1.0,
        inverse_cap: float = 1.0,
        stress_gate_enabled: bool = False,
        start_allocation: str = "blend50",
        profile_name: str = "default",
        group_a_action_schema: str | None = None,
        dca_monthly_amounts: dict[str, float] | None = None,
        dca_day: int = DEFAULT_GROUP_A_DCA_DAY,
        enable_pva_features: bool = False,
        enable_pva_sigmoid: bool = False,
        pva_weight: float = 0.30,
        pva_j_state_weight: float = 0.0,
        pva_m_state_weight: float = 1.0,
        pva_drift_threshold: float = 0.05,
        pva_target_vol: float = DEFAULT_GROUP_A_PVA_TARGET_VOL,
        pva_min_leverage_scale: float = DEFAULT_GROUP_A_PVA_MIN_LEVERAGE_SCALE,
        pva_inverse_hedge_budget: float = DEFAULT_GROUP_A_PVA_INVERSE_HEDGE_BUDGET,
        inverse_m_state_only: bool = True,
        inverse_max_holding_days: int = DEFAULT_GROUP_A_INVERSE_MAX_HOLD_DAYS,
        sentiment_gate_enabled: bool = False,
        sentiment_risk_off_threshold: float = DEFAULT_GROUP_A_SENTIMENT_RISK_OFF_THRESHOLD,
        sentiment_severe_threshold: float = DEFAULT_GROUP_A_SENTIMENT_SEVERE_THRESHOLD,
        sentiment_min_confidence: float = DEFAULT_GROUP_A_SENTIMENT_MIN_CONFIDENCE,
        sentiment_min_intensity: float = DEFAULT_GROUP_A_SENTIMENT_MIN_INTENSITY,
        sentiment_risk_off_inverse_floor: float = DEFAULT_GROUP_A_SENTIMENT_RISK_OFF_INVERSE_FLOOR,
        sentiment_severe_inverse_floor: float = DEFAULT_GROUP_A_SENTIMENT_SEVERE_INVERSE_FLOOR,
    ):
        super().__init__()
        self.panel = panel.reset_index(drop=True)
        self.tickers = tickers
        self.initial_cash = float(initial_cash)
        self.commission_rate = float(commission_rate)
        self.turnover_penalty = float(turnover_penalty)
        self.equal_benchmark_weight = float(equal_benchmark_weight)
        self.blend_benchmark_weight = float(blend_benchmark_weight)
        self.underperform_0050_weight = float(underperform_0050_weight)
        self.leveraged_benchmark_weight = float(leveraged_benchmark_weight)
        self.drawdown_penalty_weight = float(drawdown_penalty_weight)
        self.deep_drawdown_penalty_weight = float(deep_drawdown_penalty_weight)
        self.deep_drawdown_threshold = float(deep_drawdown_threshold)
        self.concentration_penalty_weight = float(concentration_penalty_weight)
        self.concentration_threshold = float(concentration_threshold)
        self.min_rebalance_days = int(min_rebalance_days)
        self.leverage_cap = float(leverage_cap)
        self.inverse_cap = float(inverse_cap)
        self.stress_gate_enabled = bool(stress_gate_enabled)
        self.start_allocation = str(start_allocation)
        self.profile_name = str(profile_name)
        self.group_a_action_schema = infer_group_a_action_schema(action_schema=group_a_action_schema)
        self.date_series = pd.to_datetime(self.panel["date"]).reset_index(drop=True)
        self.date_values = self.date_series.to_numpy(dtype="datetime64[ns]")
        self.date_strings = self.date_series.dt.strftime("%Y-%m-%d").to_numpy()
        self.dca_monthly_amounts = dict(dca_monthly_amounts or {})
        self.dca_amount_array = np.array(
            [float(self.dca_monthly_amounts.get(ticker, 0.0)) for ticker in self.tickers],
            dtype=float,
        )
        self.dca_day = max(int(dca_day), 1)
        self.enable_pva_features = bool(enable_pva_features or enable_pva_sigmoid)
        self.enable_pva_sigmoid = bool(enable_pva_sigmoid)
        self.pva_weight = float(pva_weight)
        self.pva_j_state_weight = float(pva_j_state_weight)
        self.pva_m_state_weight = float(pva_m_state_weight)
        self.pva_drift_threshold = float(pva_drift_threshold)
        self.pva_target_vol = max(float(pva_target_vol), 1e-6)
        self.pva_min_leverage_scale = float(np.clip(pva_min_leverage_scale, 0.0, 1.0))
        self.pva_inverse_hedge_budget = max(float(pva_inverse_hedge_budget), 0.0)
        self.inverse_m_state_only = bool(inverse_m_state_only)
        self.inverse_max_holding_days = max(int(inverse_max_holding_days), 0)
        self.sentiment_gate_enabled = bool(sentiment_gate_enabled)
        self.sentiment_risk_off_threshold = max(float(sentiment_risk_off_threshold), 0.0)
        self.sentiment_severe_threshold = max(
            float(sentiment_severe_threshold),
            self.sentiment_risk_off_threshold,
        )
        self.sentiment_min_confidence = float(np.clip(sentiment_min_confidence, 0.0, 1.0))
        self.sentiment_min_intensity = max(float(sentiment_min_intensity), 0.0)
        self.sentiment_risk_off_inverse_floor = float(
            np.clip(sentiment_risk_off_inverse_floor, 0.0, self.inverse_cap)
        )
        self.sentiment_severe_inverse_floor = float(
            np.clip(
                sentiment_severe_inverse_floor,
                self.sentiment_risk_off_inverse_floor,
                self.inverse_cap,
            )
        )
        self.close_price_array = _prices(self.panel, self.tickers, field="close")
        self.open_price_array = _prices(self.panel, self.tickers, field="open")
        self.tax_rates = np.array([ETF_TAX_RATE] * len(tickers), dtype=float)
        self.group_a_triplet = {"0050.TW", "00631L.TW", "00632R.TW"}.issubset(set(self.tickers))
        self.group_a_index_map = (
            {
                "0050.TW": self.tickers.index("0050.TW"),
                "00631L.TW": self.tickers.index("00631L.TW"),
                "00632R.TW": self.tickers.index("00632R.TW"),
            }
            if self.group_a_triplet
            else {}
        )
        self.dca_schedule = self._build_dca_schedule()
        self.pva_close_ma120_matrix = np.column_stack(
            [
                (self.panel[f"{ticker}_close_ma120_ratio"].to_numpy(dtype=float) - 1.0)
                if f"{ticker}_close_ma120_ratio" in self.panel.columns
                else np.zeros(len(self.panel), dtype=float)
                for ticker in self.tickers
            ]
        )
        self.pva_momentum_63_matrix = np.column_stack(
            [
                self.panel[f"{ticker}_momentum_63"].to_numpy(dtype=float)
                if f"{ticker}_momentum_63" in self.panel.columns
                else np.zeros(len(self.panel), dtype=float)
                for ticker in self.tickers
            ]
        )
        self.pva_close_ma240_matrix = np.column_stack(
            [
                (self.panel[f"{ticker}_close_ma240_ratio"].to_numpy(dtype=float) - 1.0)
                if f"{ticker}_close_ma240_ratio" in self.panel.columns
                else np.zeros(len(self.panel), dtype=float)
                for ticker in self.tickers
            ]
        )
        self.pva_realized_vol_20 = np.zeros(len(self.panel), dtype=float)
        self.pva_downside_vol_20 = np.zeros(len(self.panel), dtype=float)
        self.pva_drawdown_20 = np.zeros(len(self.panel), dtype=float)
        if self.group_a_triplet:
            close_0050 = pd.Series(
                self.close_price_array[:, self.group_a_index_map["0050.TW"]],
                dtype=float,
            )
            returns_0050 = (
                close_0050.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
            )
            downside_returns_0050 = returns_0050.where(returns_0050 < 0.0, 0.0)
            rolling_peak_20 = close_0050.rolling(20, min_periods=1).max()
            self.pva_realized_vol_20 = (
                returns_0050.rolling(20, min_periods=5).std(ddof=1).fillna(0.0).to_numpy(dtype=float)
            )
            self.pva_downside_vol_20 = (
                downside_returns_0050.rolling(20, min_periods=5).std(ddof=1).fillna(0.0).to_numpy(dtype=float)
            )
            self.pva_drawdown_20 = (
                (close_0050 / (rolling_peak_20 + 1e-10) - 1.0).fillna(0.0).to_numpy(dtype=float)
            )

        # benchmark curves
        self.equal_bh_curve = self._benchmark_curve(np.ones(len(tickers)) / len(tickers))
        self.bh_0050_curve = self._benchmark_curve(_weights_for(self.tickers, {"0050.TW": 1.0})) \
            if "0050.TW" in self.tickers else None
        self.bh_00631l_curve = self._benchmark_curve(_weights_for(self.tickers, {"00631L.TW": 1.0})) \
            if "00631L.TW" in self.tickers else None
        blend_weights = {}
        if "0050.TW" in self.tickers and "00631L.TW" in self.tickers:
            blend_weights = {"0050.TW": 0.5, "00631L.TW": 0.5}
        self.blend50_bh_curve = self._benchmark_curve(_weights_for(self.tickers, blend_weights)) \
            if blend_weights else None

        # observation
        self.feature_cols = []
        self.shared_feature_cols = [c for c in (shared_feature_cols or []) if c in self.panel.columns]
        self.pva_feature_cols = []
        if self.enable_pva_features and self.group_a_triplet:
            self.pva_feature_cols = [c for c in GROUP_A_PVA_OBS_COLUMNS if c in self.panel.columns]
        for ticker in self.tickers:
            self.feature_cols.extend(
                [f"{ticker}_{c}" for c in FEATURE_COLUMNS if f"{ticker}_{c}" in self.panel.columns]
            )
        obs_dim = len(self.feature_cols) + len(self.shared_feature_cols) + len(self.pva_feature_cols) + 5
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(obs_dim,), dtype=np.float32)
        action_labels = _action_labels_for_context(
            self.profile_name,
            self.group_a_triplet,
            self.group_a_action_schema,
        )
        self.action_space = spaces.Discrete(len(action_labels))
        self.reset()

    def _apply_group_a_exposure_cap(self, target_weights: np.ndarray) -> np.ndarray:
        if not self.group_a_triplet:
            return target_weights

        capped = target_weights.copy()
        idx_0050 = self.group_a_index_map["0050.TW"]
        idx_00631l = self.group_a_index_map["00631L.TW"]
        idx_00632r = self.group_a_index_map["00632R.TW"]

        if capped[idx_00631l] > self.leverage_cap:
            spill = capped[idx_00631l] - self.leverage_cap
            capped[idx_00631l] = self.leverage_cap
            capped[idx_0050] += spill

        if capped[idx_00632r] > self.inverse_cap:
            spill = capped[idx_00632r] - self.inverse_cap
            capped[idx_00632r] = self.inverse_cap
            capped[idx_0050] += spill

        return capped

    def _current_inverse_weight(self) -> float:
        if not self.group_a_triplet:
            return 0.0
        return float(self.weights[self.group_a_index_map["00632R.TW"]])

    def _zero_inverse_weight(self, target_weights: np.ndarray) -> np.ndarray:
        if not self.group_a_triplet:
            return target_weights.copy()
        adjusted = target_weights.copy()
        idx_0050 = self.group_a_index_map["0050.TW"]
        idx_00632r = self.group_a_index_map["00632R.TW"]
        adjusted[idx_0050] += adjusted[idx_00632r]
        adjusted[idx_00632r] = 0.0
        adjusted = self._apply_group_a_exposure_cap(adjusted)
        return _clip_weights_array(adjusted)

    def _zero_leverage_weight(self, target_weights: np.ndarray) -> np.ndarray:
        if not self.group_a_triplet:
            return target_weights.copy()
        adjusted = target_weights.copy()
        idx_0050 = self.group_a_index_map["0050.TW"]
        idx_00631l = self.group_a_index_map["00631L.TW"]
        adjusted[idx_0050] += adjusted[idx_00631l]
        adjusted[idx_00631l] = 0.0
        adjusted = self._apply_group_a_exposure_cap(adjusted)
        return _clip_weights_array(adjusted)

    def _apply_inverse_floor(self, target_weights: np.ndarray, inverse_floor: float) -> np.ndarray:
        if not self.group_a_triplet:
            return target_weights.copy()
        adjusted = self._zero_leverage_weight(target_weights)
        idx_0050 = self.group_a_index_map["0050.TW"]
        idx_00632r = self.group_a_index_map["00632R.TW"]
        inverse_target = min(self.inverse_cap, max(float(inverse_floor), float(adjusted[idx_00632r])))
        inverse_delta = max(0.0, inverse_target - float(adjusted[idx_00632r]))
        adjusted[idx_0050] = max(0.0, float(adjusted[idx_0050]) - inverse_delta)
        adjusted[idx_00632r] = inverse_target
        adjusted = self._apply_group_a_exposure_cap(adjusted)
        return _clip_weights_array(adjusted)

    def _benchmark_curve(self, weights: np.ndarray) -> np.ndarray:
        shares = self.initial_cash * weights / self.close_price_array[0]
        return self.close_price_array @ shares

    def _portfolio_value(self, prices: np.ndarray) -> float:
        return float(self.cash + np.dot(self.shares, prices))

    def _mark_weights(self, prices: np.ndarray) -> float:
        value = max(self._portfolio_value(prices), 1.0)
        if np.any(self.shares > 0.0):
            self.weights = self.shares * prices / value
        return float(value)

    def _target_weights(self, action: int) -> np.ndarray:
        t = self.tickers
        w = lambda d: _weights_for(t, d)
        raw_w = lambda d: _raw_weights_for(t, d)
        n = len(t)

        if self.group_a_triplet and self.profile_name != "conservative":
            if self.group_a_action_schema == GROUP_A_ACTION_SCHEMA_LEGACY_V1:
                if action == 0:
                    return self.weights.copy()
                if action == 1:
                    return w({"0050.TW": 0.50, "00631L.TW": 0.50})
                if action == 2:
                    return w({"0050.TW": 0.40, "00631L.TW": 0.60})
                if action == 3:
                    return w({"0050.TW": 0.30, "00631L.TW": 0.70})
                if action == 4:
                    return np.ones(n, dtype=float) / n
                return w({"0050.TW": 0.50, "00631L.TW": 0.50})
            if self.group_a_action_schema == GROUP_A_ACTION_SCHEMA_TRIPLET_V3_CASH50:
                if action == 0:
                    return self.weights.copy()
                if action == 1:
                    return w({"0050.TW": 0.85, "00631L.TW": min(self.leverage_cap, 0.15)})
                if action == 2:
                    return w({"0050.TW": 0.70, "00631L.TW": min(self.leverage_cap, 0.30)})
                if action == 3:
                    return w({"0050.TW": 1.0})
                if action == 4:
                    return w({"0050.TW": 0.70, "00632R.TW": min(self.inverse_cap, 0.30)})
                if action == 5:
                    # Keep cash equal to the 00631L position; 50/50 effective exposure
                    # becomes 50% 0050 / 25% 00631L / 25% cash before cap adjustments.
                    return raw_w({"0050.TW": 0.50, "00631L.TW": min(self.leverage_cap, 0.25)})
                return w({"0050.TW": 0.85, "00631L.TW": min(self.leverage_cap, 0.15)})
            if action == 0:
                return self.weights.copy()
            if action == 1:
                return w({"0050.TW": 0.85, "00631L.TW": min(self.leverage_cap, 0.15)})
            if action == 2:
                return w({"0050.TW": 0.70, "00631L.TW": min(self.leverage_cap, 0.30)})
            if action == 3:
                return w({"0050.TW": 1.0})
            if action == 4:
                return w({"0050.TW": 0.70, "00632R.TW": min(self.inverse_cap, 0.30)})
            return w({"0050.TW": 0.85, "00631L.TW": min(self.leverage_cap, 0.15)})

        if self.profile_name == "conservative" and self.group_a_triplet:
            if action == 0:
                return self.weights.copy()
            if action == 1:
                return w({"0050.TW": 1.0})
            if action == 2:
                return w({"0050.TW": 0.85, "00631L.TW": min(self.leverage_cap, 0.15)})
            if action == 3:
                return w({"0050.TW": 0.70, "00632R.TW": 0.30})
            if action == 4:
                return w({"0050.TW": 0.70, "00631L.TW": min(self.leverage_cap, 0.30)})
            return w({"0050.TW": 1.0})

        if action == 0:  # 持有不動
            return self.weights.copy()

        if action == 1:
            # 50% 0050 / 50% 00631L（平衡槓桿）
            if "0050.TW" in t and "00631L.TW" in t:
                return w({"0050.TW": 0.50, "00631L.TW": 0.50})
            return np.ones(n, dtype=float) / n

        if action == 2:
            # 40% 0050 / 60% 00631L（適度槓桿）
            if "0050.TW" in t and "00631L.TW" in t:
                return w({"0050.TW": 0.40, "00631L.TW": 0.60})
            return np.ones(n, dtype=float) / n

        if action == 3:
            # 高股息：40% 0050 / 35% 00713 / 25% 00878
            if "0050.TW" in t and "00713.TW" in t and "00878.TW" in t:
                return w({"0050.TW": 0.40, "00713.TW": 0.35, "00878.TW": 0.25})
            return np.ones(n, dtype=float) / n

        if action == 4:  # 等權
            return np.ones(n, dtype=float) / n

        return w({"0050.TW": 1.0}) if "0050.TW" in t else np.ones(n, dtype=float) / n

    def _market_stress_snapshot(self) -> dict[str, float | bool]:
        if not self.stress_gate_enabled or not self.group_a_triplet:
            return {"risk_off": False, "severe": False, "score": 0.0}

        row = self.panel.iloc[self.step_idx]
        ma60_ratio = float(row.get("dji_ma60_ratio_lag1", 0.0))
        drawdown_60d = float(row.get("dji_drawdown_60d_lag1", 0.0))
        volatility_20d = float(row.get("dji_volatility_20d_lag1", 0.0))
        return_5d = float(row.get("dji_return_5d_lag1", 0.0))
        return_1d = float(row.get("dji_return_1d_lag1", 0.0))

        score = 0
        score += int(ma60_ratio < 0.0)
        score += int(drawdown_60d <= -0.08)
        score += int(volatility_20d >= 1.0)
        score += int(return_5d <= -0.10)
        score += int(return_1d <= -0.06)
        risk_off = score >= 2
        severe = score >= 3 or drawdown_60d <= -0.12 or (ma60_ratio < 0.0 and return_5d <= -0.15)
        return {
            "risk_off": risk_off,
            "severe": severe,
            "score": float(score),
            "dji_ma60_ratio_lag1": ma60_ratio,
            "dji_drawdown_60d_lag1": drawdown_60d,
            "dji_volatility_20d_lag1": volatility_20d,
            "dji_return_5d_lag1": return_5d,
            "dji_return_1d_lag1": return_1d,
        }

    def _llm_sentiment_snapshot(self) -> dict[str, float | bool]:
        base = {
            "enabled": bool(self.sentiment_gate_enabled and self.group_a_triplet),
            "available": False,
            "active": False,
            "risk_off": False,
            "severe": False,
            "composite_score": 0.0,
            "negative_score": 0.0,
            "confidence": 0.0,
            "risk_off_score": 0.0,
            "news_intensity": 0.0,
            "sentiment_score": 0.0,
        }
        if not self.sentiment_gate_enabled or not self.group_a_triplet:
            return base

        row = self.panel.iloc[self.step_idx]
        required_cols = {
            "llm_sentiment_score",
            "llm_sentiment_confidence",
            "llm_risk_off_score",
            "llm_news_intensity",
        }
        if not required_cols.issubset(row.index):
            return base

        sentiment_score = float(row.get("llm_sentiment_score", 0.0))
        confidence = float(np.clip(row.get("llm_sentiment_confidence", 0.0), 0.0, 1.0))
        risk_off_score = float(np.clip(row.get("llm_risk_off_score", 0.0), 0.0, 1.0))
        news_intensity = float(max(row.get("llm_news_intensity", 0.0), 0.0))
        negative_score = float(np.clip(-sentiment_score, 0.0, 1.0))
        intensity_score = float(np.clip(news_intensity / 3.0, 0.0, 1.0))
        composite_score = float(
            (
                0.55 * risk_off_score
                + 0.35 * negative_score
                + 0.10 * intensity_score
            )
            * confidence
        )
        risk_off = bool(
            confidence >= self.sentiment_min_confidence
            and news_intensity >= self.sentiment_min_intensity
            and composite_score >= self.sentiment_risk_off_threshold
        )
        severe = bool(
            risk_off
            and composite_score >= self.sentiment_severe_threshold
            and negative_score >= 0.35
        )

        base.update(
            {
                "available": True,
                "active": bool(risk_off or severe),
                "risk_off": risk_off,
                "severe": severe,
                "composite_score": composite_score,
                "negative_score": negative_score,
                "confidence": confidence,
                "risk_off_score": risk_off_score,
                "news_intensity": news_intensity,
                "sentiment_score": sentiment_score,
            }
        )
        return base

    def _apply_risk_gate(self, target_weights: np.ndarray) -> tuple[np.ndarray, dict[str, object]]:
        gate_info: dict[str, object] = {
            "source": "none",
            "reason": None,
            "allow_inverse_override": False,
            "market_stress": self._market_stress_snapshot(),
            "llm_sentiment": self._llm_sentiment_snapshot(),
        }
        if not self.group_a_triplet:
            return target_weights, gate_info

        capped = self._apply_group_a_exposure_cap(target_weights)
        stress = gate_info["market_stress"]
        sentiment = gate_info["llm_sentiment"]

        if bool(stress.get("severe")):
            gate_info.update(
                {
                    "source": "market_stress",
                    "reason": "market_stress_severe",
                    "allow_inverse_override": True,
                }
            )
            return self._apply_inverse_floor(capped, self.sentiment_severe_inverse_floor), gate_info

        if bool(sentiment.get("severe")):
            gate_info.update(
                {
                    "source": "llm_sentiment",
                    "reason": "llm_sentiment_severe",
                    "allow_inverse_override": True,
                }
            )
            return self._apply_inverse_floor(capped, self.sentiment_severe_inverse_floor), gate_info

        if bool(stress.get("risk_off")):
            gate_info.update(
                {
                    "source": "market_stress",
                    "reason": "market_stress_risk_off",
                    "allow_inverse_override": True,
                }
            )
            return self._apply_inverse_floor(capped, self.sentiment_risk_off_inverse_floor), gate_info

        if bool(sentiment.get("risk_off")):
            gate_info.update(
                {
                    "source": "llm_sentiment",
                    "reason": "llm_sentiment_risk_off",
                    "allow_inverse_override": False,
                }
            )
            return self._zero_leverage_weight(capped), gate_info

        return capped, gate_info

    def _build_dca_schedule(self) -> list[dict]:
        if self.dca_amount_array.sum() <= 0 or len(self.panel) == 0:
            return []
        start = self.date_series.min().to_period("M")
        end = self.date_series.max().to_period("M")
        schedule = []
        for period in pd.period_range(start, end, freq="M"):
            day = min(self.dca_day, period.days_in_month)
            schedule.append(
                {
                    "month": str(period),
                    "scheduled_date": pd.Timestamp(year=period.year, month=period.month, day=day),
                }
            )
        return schedule

    def _apply_dca_if_due(self, idx: int, prices: np.ndarray) -> float:
        if self.dca_amount_array.sum() <= 0:
            return 0.0
        current_date = pd.Timestamp(self.date_values[idx])
        current_date_str = self.date_strings[idx]
        due_items = [
            item for item in self.dca_schedule
            if item["month"] not in self.dca_executed_months and current_date >= item["scheduled_date"]
        ]
        if not due_items:
            return 0.0

        fees = 0.0
        history_items = []
        for item in due_items:
            purchases = {}
            self.dca_executed_months.add(item["month"])
            for i, amount in enumerate(self.dca_amount_array):
                if amount <= 0:
                    continue
                self.cash += amount
                self.total_contributions += amount
                buy_value = amount / (1.0 + self.commission_rate)
                fee = buy_value * self.commission_rate
                self.cash -= buy_value + fee
                self.shares[i] += buy_value / prices[i]
                fees += fee
                purchases[self.tickers[i]] = {
                    "cash_contribution": float(amount),
                    "buy_value": float(buy_value),
                    "fee": float(fee),
                    "price": float(prices[i]),
                    "shares_bought": float(buy_value / prices[i]),
                }
            history_items.append(
                {
                    "date": current_date_str,
                    "month": item["month"],
                    "scheduled_date": str(item["scheduled_date"].date()),
                    "total_contribution": float(sum(p["cash_contribution"] for p in purchases.values())),
                    "fees": float(sum(p["fee"] for p in purchases.values())),
                    "purchases": purchases,
                }
            )

        value_after = max(self._portfolio_value(prices), 1.0)
        self.weights = self.shares * prices / value_after
        self.dca_purchase_count += len(history_items)
        self.dca_purchase_history.extend(history_items)
        return float(fees)

    def _sjm_state(self) -> tuple[str, dict[str, float | str]]:
        if not self.group_a_triplet:
            return "S", {"p": 0.0, "v": 0.0, "a": 0.0, "p_z": 0.0, "v_z": 0.0, "a_z": 0.0, "state": "S"}

        row = self.panel.iloc[self.step_idx]
        state_code = int(float(row.get("0050_sjm_state_code", 0.0)))
        state = "M" if state_code < 0 else "J" if state_code > 0 else "S"
        return state, {
            "p": float(row.get("0050_pva_p", 0.0)),
            "v": float(row.get("0050_pva_v", 0.0)),
            "a": float(row.get("0050_pva_a", 0.0)),
            "p_z": float(row.get("0050_pva_p_z", 0.0)),
            "v_z": float(row.get("0050_pva_v_z", 0.0)),
            "a_z": float(row.get("0050_pva_a_z", 0.0)),
            "state": state,
        }

    def _pva_state_blend_weight(self, sjm_state: str) -> float:
        if sjm_state == "M":
            return min(1.0, max(0.0, self.pva_m_state_weight))
        if sjm_state == "J":
            return min(1.0, max(0.0, self.pva_j_state_weight))
        return min(1.0, max(0.0, self.pva_weight))

    def _pva_risk_scaled_weights(
        self,
        base_target_weights: np.ndarray,
        sjm_state: str,
        sjm_details: dict[str, float | str],
    ) -> tuple[np.ndarray, dict]:
        base_weights = _clip_weights_array(self._apply_group_a_exposure_cap(base_target_weights))
        if not self.group_a_triplet:
            return base_weights, {
                "sjm": sjm_details,
                "policy": "disabled",
                "raw_pva_weights": {ticker: float(w) for ticker, w in zip(self.tickers, base_weights)},
                "risk_metrics": {},
            }

        idx_0050 = self.group_a_index_map["0050.TW"]
        idx_00631l = self.group_a_index_map["00631L.TW"]
        idx_00632r = self.group_a_index_map["00632R.TW"]

        realized_vol = float(self.pva_realized_vol_20[self.step_idx])
        downside_vol = float(self.pva_downside_vol_20[self.step_idx])
        drawdown_20 = float(abs(min(0.0, self.pva_drawdown_20[self.step_idx])))
        blend_weight = self._pva_state_blend_weight(sjm_state)
        p_z = float(sjm_details.get("p_z", 0.0))
        v_z = float(sjm_details.get("v_z", 0.0))
        a_z = float(sjm_details.get("a_z", 0.0))

        regime_pressure = (
            0.40 * _sigmoid(-p_z)
            + 0.35 * _sigmoid(-v_z)
            + 0.25 * _sigmoid(-a_z)
        )
        vol_pressure = max(realized_vol / self.pva_target_vol - 1.0, 0.0)
        downside_pressure = max(downside_vol / self.pva_target_vol - 0.5, 0.0)
        drawdown_pressure = min(drawdown_20 / 0.08, 1.0)
        state_pressure = {"M": 1.0, "S": 0.35, "J": 0.10}.get(sjm_state, 0.35)
        risk_score = float(
            np.clip(
                0.40 * regime_pressure
                + 0.25 * _sigmoid(2.0 * vol_pressure)
                + 0.20 * _sigmoid(2.0 * downside_pressure)
                + 0.10 * drawdown_pressure
                + 0.05 * state_pressure,
                0.0,
                1.0,
            )
        )
        vol_scale = float(
            np.clip(
                self.pva_target_vol / max(realized_vol, 1e-6),
                self.pva_min_leverage_scale,
                1.0,
            )
        )
        regime_scale = float(
            np.clip(
                1.0 - 0.85 * blend_weight * risk_score,
                self.pva_min_leverage_scale,
                1.0,
            )
        )
        leverage_scale = float(min(vol_scale, regime_scale))

        scaled_weights = base_weights.copy()
        base_0050 = float(base_weights[idx_0050])
        base_00631l = float(base_weights[idx_00631l])
        base_00632r = float(base_weights[idx_00632r])
        scaled_00631l = min(self.leverage_cap, base_00631l * leverage_scale)
        freed_budget = max(0.0, base_00631l - scaled_00631l) + base_00632r

        inverse_target = 0.0
        hedge_signal = 0.0
        if sjm_state == "M" and not self.inverse_cooldown_active:
            hedge_signal = float(
                np.clip(
                    0.60 * risk_score + 0.40 * _sigmoid(2.5 * vol_pressure),
                    0.0,
                    1.0,
                )
            )
            inverse_target = min(
                self.inverse_cap,
                self.pva_inverse_hedge_budget * blend_weight * hedge_signal,
            )

        target_0050 = max(0.0, base_0050 + freed_budget - inverse_target)
        scaled_weights[idx_0050] = target_0050
        scaled_weights[idx_00631l] = scaled_00631l
        scaled_weights[idx_00632r] = inverse_target
        scaled_weights = self._apply_group_a_exposure_cap(scaled_weights)
        scaled_weights = _clip_weights_array(scaled_weights)

        return scaled_weights, {
            "sjm": sjm_details,
            "policy": "continuous_risk_scaling",
            "raw_pva_weights": {ticker: float(w) for ticker, w in zip(self.tickers, scaled_weights)},
            "risk_metrics": {
                "blend_weight": float(blend_weight),
                "risk_score": float(risk_score),
                "realized_vol_20": float(realized_vol),
                "downside_vol_20": float(downside_vol),
                "drawdown_20": float(drawdown_20),
                "vol_scale": float(vol_scale),
                "regime_scale": float(regime_scale),
                "leverage_scale": float(leverage_scale),
                "hedge_signal": float(hedge_signal),
                "inverse_cooldown_active": bool(self.inverse_cooldown_active),
            },
            "base_target_weights": {ticker: float(w) for ticker, w in zip(self.tickers, base_weights)},
        }

    def _apply_inverse_hedge_rules(
        self,
        target_weights: np.ndarray,
        sjm_state: str,
        *,
        allow_inverse_override: bool = False,
    ) -> tuple[np.ndarray, dict]:
        if not self.group_a_triplet:
            return target_weights, {"force_rebalance": False, "reason": None}

        current_inverse_weight = self._current_inverse_weight()
        holding_inverse = current_inverse_weight > 1e-6
        reason = None
        adjusted = target_weights.copy()

        if allow_inverse_override and adjusted[self.group_a_index_map["00632R.TW"]] > 1e-6:
            self.inverse_cooldown_active = False
            return adjusted, {
                "force_rebalance": False,
                "reason": None,
                "holding_inverse": bool(holding_inverse),
                "current_inverse_weight": float(current_inverse_weight),
                "inverse_holding_days": int(self.inverse_holding_days),
                "inverse_cooldown_active": bool(self.inverse_cooldown_active),
                "override_active": True,
            }

        if sjm_state != "M":
            self.inverse_cooldown_active = False
            if self.inverse_m_state_only and (holding_inverse or adjusted[self.group_a_index_map["00632R.TW"]] > 1e-6):
                adjusted = self._zero_inverse_weight(adjusted)
                reason = "state_exit"
        elif self.inverse_cooldown_active and (holding_inverse or adjusted[self.group_a_index_map["00632R.TW"]] > 1e-6):
            adjusted = self._zero_inverse_weight(adjusted)
            reason = "m_state_cooldown"
        elif (
            self.inverse_max_holding_days > 0
            and holding_inverse
            and self.inverse_holding_days >= self.inverse_max_holding_days
        ):
            adjusted = self._zero_inverse_weight(adjusted)
            self.inverse_cooldown_active = True
            reason = "max_holding_days"

        return adjusted, {
            "force_rebalance": bool(holding_inverse and reason is not None),
            "reason": reason,
            "holding_inverse": bool(holding_inverse),
            "current_inverse_weight": float(current_inverse_weight),
            "inverse_holding_days": int(self.inverse_holding_days),
            "inverse_cooldown_active": bool(self.inverse_cooldown_active),
            "override_active": False,
        }

    def _pva_overlay_allowed(self) -> tuple[bool, str, dict]:
        if not self.enable_pva_sigmoid or not self.group_a_triplet:
            return False, "S", {"p": 0.0, "v": 0.0, "a": 0.0, "p_z": 0.0, "v_z": 0.0, "a_z": 0.0, "state": "S"}
        sjm_state, sjm_details = self._sjm_state()
        return True, sjm_state, sjm_details

    def _get_obs(self) -> np.ndarray:
        row = self.panel.iloc[self.step_idx]
        features = row[self.feature_cols].to_numpy(dtype=float) if self.feature_cols else np.array([], dtype=float)
        shared_features = (
            row[self.shared_feature_cols].to_numpy(dtype=float)
            if self.shared_feature_cols
            else np.array([], dtype=float)
        )
        pva_features = (
            row[self.pva_feature_cols].to_numpy(dtype=float)
            if self.pva_feature_cols
            else np.array([], dtype=float)
        )
        prices = self.close_price_array[self.step_idx]
        value = max(self._portfolio_value(prices), 1.0)
        weights = self.shares * prices / value
        peak = max(self.peak_value, value, 1.0)
        days_since_rebalance = min(max(self.step_idx - self.last_rebalance_idx, 0), 252) / 252.0

        extra = [self.cash / value, value / peak - 1.0, days_since_rebalance]
        if self.equal_bh_curve is not None:
            extra.append(value / max(float(self.equal_bh_curve[self.step_idx]), 1.0) - 1.0)
        else:
            extra.append(0.0)
        if self.bh_0050_curve is not None:
            extra.append(value / max(float(self.bh_0050_curve[self.step_idx]), 1.0) - 1.0)
        else:
            extra.append(0.0)

        state = np.array(extra, dtype=float)
        obs = np.concatenate([features, shared_features, pva_features, state])
        obs = np.nan_to_num(obs, nan=0.0, posinf=10.0, neginf=-10.0)
        return np.clip(obs, -10.0, 10.0).astype(np.float32)

    def _rebalance(self, target_weights: np.ndarray, prices: np.ndarray) -> float:
        value_before = self._portfolio_value(prices)
        current_values = self.shares * prices
        target_values = value_before * target_weights
        deltas = target_values - current_values
        fees = 0.0

        for i, delta in enumerate(deltas):
            if delta >= 0:
                continue
            sell_value = min(-delta, self.shares[i] * prices[i])
            if sell_value <= 0:
                continue
            fee_rate = self.commission_rate + self.tax_rates[i]
            fees += sell_value * fee_rate
            self.cash += sell_value * (1 - fee_rate)
            self.shares[i] -= sell_value / prices[i]

        for i, delta in enumerate(deltas):
            if delta <= 0:
                continue
            buy_value = min(delta, self.cash / (1 + self.commission_rate))
            if buy_value <= 0:
                continue
            fees += buy_value * self.commission_rate
            self.cash -= buy_value * (1 + self.commission_rate)
            self.shares[i] += buy_value / prices[i]

        value_after = max(self._portfolio_value(prices), 1.0)
        self.weights = self.shares * prices / value_after
        return float(fees)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.step_idx = 0
        self.cash = self.initial_cash
        self.shares = np.zeros(len(self.tickers), dtype=float)

        # 初始配置：50/50 blend 或等權
        if self.profile_name == "conservative" and self.group_a_triplet:
            self.weights = _weights_for(self.tickers, {"0050.TW": 1.0})
        elif "0050.TW" in self.tickers and "00631L.TW" in self.tickers and self.start_allocation == "blend50":
            self.weights = _weights_for(self.tickers, {"0050.TW": 0.50, "00631L.TW": 0.50})
        else:
            self.weights = np.ones(len(self.tickers), dtype=float) / len(self.tickers)

        self.last_rebalance_idx = -10**9
        self.trade_count = 0
        self.fees_paid = 0.0
        self.peak_value = self.initial_cash
        self.equity_curve = [self.initial_cash]
        self.total_contributions = 0.0
        self.dca_purchase_count = 0
        self.dca_purchase_history = []
        self.dca_executed_months = set()
        self.pva_sigmoid_count = 0
        self.pva_sigmoid_history = []
        self.sjm_state_history = []
        self.inverse_holding_days = 0
        self.inverse_cooldown_active = False
        self.inverse_forced_exit_count = 0
        self.inverse_forced_exit_history = []
        return self._get_obs(), {}

    def step(self, action):
        decision_prices = self.close_price_array[self.step_idx]
        value_before = self._mark_weights(decision_prices)
        base_target_weights = self._target_weights(int(action))
        target_weights = base_target_weights.copy()
        pva_allowed, sjm_state, sjm_details = self._pva_overlay_allowed()
        pva_details = None
        pva_state_weight = 0.0
        pva_drift = 0.0
        execution_source = "hold" if int(action) == 0 else "ppo_action"
        if self.group_a_triplet:
            if self._current_inverse_weight() > 1e-6:
                self.inverse_holding_days += 1
            else:
                self.inverse_holding_days = 0
        self.sjm_state_history.append(
            {
                "date": self.date_strings[self.step_idx],
                **sjm_details,
            }
        )
        trade_idx = self.step_idx + 1
        execution_prices = self.open_price_array[trade_idx]
        execution_value_before = self._mark_weights(execution_prices)
        if pva_allowed:
            pva_state_weight = self._pva_state_blend_weight(sjm_state)
            candidate_target_weights, pva_details = self._pva_risk_scaled_weights(
                base_target_weights,
                sjm_state,
                sjm_details,
            )
            pva_drift = float(np.abs(candidate_target_weights - self.weights).sum())
            if pva_drift >= self.pva_drift_threshold:
                target_weights = candidate_target_weights
                execution_source = "pva_risk_scale"
        target_weights, gate_info = self._apply_risk_gate(target_weights)
        if gate_info["source"] != "none":
            execution_source = str(gate_info["reason"])
        target_weights, inverse_rule = self._apply_inverse_hedge_rules(
            target_weights,
            sjm_state,
            allow_inverse_override=bool(gate_info.get("allow_inverse_override", False)),
        )
        target_weights = _clip_weights_array(target_weights)
        if inverse_rule["reason"] is not None:
            execution_source = f"inverse_{inverse_rule['reason']}"
        fees = 0.0
        turnover = float(np.abs(target_weights - self.weights).sum())
        needs_rebalance = turnover > 1e-6

        if needs_rebalance and (
            bool(inverse_rule["force_rebalance"])
            or self.step_idx - self.last_rebalance_idx >= self.min_rebalance_days
        ):
            fees = self._rebalance(target_weights, execution_prices)
            if fees > 0:
                self.trade_count += 1
                self.last_rebalance_idx = trade_idx
                self.fees_paid += fees
                if execution_source == "pva_risk_scale":
                    self.pva_sigmoid_count += 1
                    self.pva_sigmoid_history.append(
                        {
                            "date": self.date_strings[trade_idx],
                            "step_idx": int(trade_idx),
                            "sjm_state": sjm_state,
                            "drift": float(pva_drift),
                            "pva_weight": float(pva_state_weight),
                            "pva_weights": (
                                None
                                if pva_details is None
                                else pva_details["raw_pva_weights"]
                            ),
                            "target_weights": {
                                ticker: float(weight)
                                for ticker, weight in zip(self.tickers, target_weights)
                            },
                            "details": pva_details,
                            "risk_gate": gate_info,
                        }
                    )
                if bool(inverse_rule["force_rebalance"]):
                    self.inverse_forced_exit_count += 1
                    self.inverse_forced_exit_history.append(
                        {
                            "date": self.date_strings[trade_idx],
                            "step_idx": int(trade_idx),
                            "reason": inverse_rule["reason"],
                            "holding_days": int(inverse_rule["inverse_holding_days"]),
                            "current_inverse_weight": float(inverse_rule["current_inverse_weight"]),
                            "target_weights": {
                                ticker: float(weight)
                                for ticker, weight in zip(self.tickers, target_weights)
                            },
                        }
                    )

        self.step_idx = trade_idx
        dca_fees = self._apply_dca_if_due(self.step_idx, execution_prices)
        if dca_fees > 0:
            self.fees_paid += dca_fees
        close_prices = self.close_price_array[self.step_idx]
        value_after = self._mark_weights(close_prices)
        if self.group_a_triplet and self._current_inverse_weight() <= 1e-6:
            self.inverse_holding_days = 0
        self.peak_value = max(self.peak_value, value_after)
        self.equity_curve.append(value_after)

        daily_return = value_after / max(value_before, 1.0) - 1

        # benchmarks
        equal_return = 0.0
        if self.equal_bh_curve is not None and self.step_idx > 0:
            equal_return = float(self.equal_bh_curve[self.step_idx] / max(self.equal_bh_curve[self.step_idx - 1], 1.0) - 1)

        excess_equal = daily_return - equal_return

        excess_vs_blend50 = 0.0
        if self.blend50_bh_curve is not None and self.step_idx > 0:
            blend50_return = float(self.blend50_bh_curve[self.step_idx] / max(self.blend50_bh_curve[self.step_idx - 1], 1.0) - 1)
            excess_vs_blend50 = daily_return - blend50_return

        underperform_0050 = 0.0
        if self.bh_0050_curve is not None and self.step_idx > 0:
            bh_0050_return = float(self.bh_0050_curve[self.step_idx] / max(self.bh_0050_curve[self.step_idx - 1], 1.0) - 1)
            underperform_0050 = max(0.0, bh_0050_return - daily_return)

        excess_vs_00631l = 0.0
        if self.bh_00631l_curve is not None and self.step_idx > 0:
            bh_00631l_return = float(
                self.bh_00631l_curve[self.step_idx] / max(self.bh_00631l_curve[self.step_idx - 1], 1.0) - 1
            )
            excess_vs_00631l = daily_return - bh_00631l_return

        current_drawdown = min(0.0, value_after / max(self.peak_value, 1.0) - 1.0)
        hhi = float(np.sum(self.weights**2))
        concentration_penalty = (
            max(0.0, hhi - self.concentration_threshold) * self.concentration_penalty_weight
        )
        deep_drawdown_penalty = (
            max(0.0, abs(current_drawdown) - self.deep_drawdown_threshold) * self.deep_drawdown_penalty_weight
        )

        reward = float(
            (
                daily_return
                + self.equal_benchmark_weight * excess_equal
                + self.blend_benchmark_weight * excess_vs_blend50
                + self.leveraged_benchmark_weight * excess_vs_00631l
                - self.underperform_0050_weight * underperform_0050
                - self.drawdown_penalty_weight * abs(current_drawdown)
                - deep_drawdown_penalty
                - concentration_penalty
            )
            * 100.0
            - self.turnover_penalty * turnover
            - fees / max(execution_value_before, 1.0)
        )
        terminated = self.step_idx >= len(self.panel) - 1
        return self._get_obs(), reward, terminated, False, {
            "portfolio_value": value_after,
            "fees_paid": self.fees_paid,
            "trade_count": self.trade_count,
            "pva_sigmoid_count": self.pva_sigmoid_count,
            "inverse_forced_exit_count": self.inverse_forced_exit_count,
            "decision_source": execution_source,
            "risk_gate": gate_info,
            "weights": self.weights.copy(),
        }

    def plan_action(self, action: int) -> dict:
        action = int(action)
        decision_prices = self.close_price_array[self.step_idx]
        current_value = self._mark_weights(decision_prices)
        current_weights = self.weights.copy()
        current_cash_weight = float(max(self.cash, 0.0) / max(current_value, 1.0))
        base_target_weights = _clip_weights_array(self._target_weights(action))
        candidate_target_weights = base_target_weights.copy()
        candidate_source = "hold" if action == 0 else "ppo_action"
        candidate_reason = (
            "hold_action"
            if action == 0
            else _action_label_for_context(
                action,
                self.profile_name,
                self.group_a_triplet,
                self.group_a_action_schema,
            )
        )

        pva_allowed, sjm_state, sjm_details = self._pva_overlay_allowed()
        pva_details = None
        pva_state_weight = 0.0
        pva_drift = 0.0
        if pva_allowed:
            pva_state_weight = self._pva_state_blend_weight(sjm_state)
            pva_candidate_weights, pva_details = self._pva_risk_scaled_weights(
                base_target_weights,
                sjm_state,
                sjm_details,
            )
            pva_drift = float(np.abs(pva_candidate_weights - current_weights).sum())
            if pva_drift >= self.pva_drift_threshold:
                candidate_target_weights = pva_candidate_weights
                candidate_source = "pva_risk_scale"
                candidate_reason = f"pva_overlay_{sjm_state.lower()}"

        candidate_target_weights, gate_info = self._apply_risk_gate(candidate_target_weights)
        if gate_info["source"] != "none":
            candidate_source = str(gate_info["source"])
            candidate_reason = str(gate_info["reason"])
        inverse_cooldown_active = self.inverse_cooldown_active
        try:
            candidate_target_weights, inverse_rule = self._apply_inverse_hedge_rules(
                candidate_target_weights,
                sjm_state,
                allow_inverse_override=bool(gate_info.get("allow_inverse_override", False)),
            )
        finally:
            self.inverse_cooldown_active = inverse_cooldown_active

        candidate_target_weights = _clip_weights_array(candidate_target_weights)
        if inverse_rule["reason"] is not None:
            candidate_source = f"inverse_{inverse_rule['reason']}"
            candidate_reason = str(inverse_rule["reason"])

        candidate_turnover = float(np.abs(candidate_target_weights - current_weights).sum())
        days_since_last_rebalance = max(self.step_idx - self.last_rebalance_idx, 0)
        cooldown_remaining = max(self.min_rebalance_days - days_since_last_rebalance, 0)
        can_trade_now = bool(
            inverse_rule["force_rebalance"] or days_since_last_rebalance >= self.min_rebalance_days
        )
        needs_rebalance = candidate_turnover > 1e-6
        execute_trade = bool(needs_rebalance and can_trade_now)

        if execute_trade:
            effective_target_weights = candidate_target_weights.copy()
            final_reason = candidate_reason
        else:
            effective_target_weights = current_weights.copy()
            if not needs_rebalance:
                final_reason = "no_weight_change" if action != 0 else "hold_action"
            elif not can_trade_now:
                final_reason = f"cooldown_{cooldown_remaining}d"
            else:
                final_reason = candidate_reason

        return {
            "date": self.date_strings[self.step_idx],
            "step_idx": int(self.step_idx),
            "action": action,
            "action_label": _action_label_for_context(
                action,
                self.profile_name,
                self.group_a_triplet,
                self.group_a_action_schema,
            ),
            "base_target_label": _weights_to_label(self.tickers, base_target_weights),
            "candidate_target_label": _weights_to_label(self.tickers, candidate_target_weights),
            "effective_target_label": _weights_to_label(self.tickers, effective_target_weights),
            "current_weights": _weights_to_dict(self.tickers, current_weights),
            "current_cash_weight": float(current_cash_weight),
            "base_target_weights": _weights_to_dict(self.tickers, base_target_weights),
            "candidate_target_weights": _weights_to_dict(self.tickers, candidate_target_weights),
            "candidate_target_cash_weight": float(max(0.0, 1.0 - float(candidate_target_weights.sum()))),
            "effective_target_weights": _weights_to_dict(self.tickers, effective_target_weights),
            "effective_target_cash_weight": float(max(0.0, 1.0 - float(effective_target_weights.sum()))),
            "candidate_source": candidate_source,
            "candidate_reason": candidate_reason,
            "reason": final_reason,
            "sjm_state": sjm_state,
            "sjm_details": sjm_details,
            "pva_allowed": bool(pva_allowed),
            "pva_state_weight": float(pva_state_weight),
            "pva_drift": float(pva_drift),
            "pva_details": pva_details,
            "candidate_turnover": float(candidate_turnover),
            "days_since_last_rebalance": int(days_since_last_rebalance),
            "cooldown_remaining": int(cooldown_remaining),
            "can_trade_now": bool(can_trade_now),
            "needs_rebalance": bool(needs_rebalance),
            "execute_trade": bool(execute_trade),
            "inverse_rule": {
                "force_rebalance": bool(inverse_rule["force_rebalance"]),
                "reason": inverse_rule["reason"],
                "holding_inverse": bool(inverse_rule["holding_inverse"]),
                "current_inverse_weight": float(inverse_rule["current_inverse_weight"]),
                "inverse_holding_days": int(inverse_rule["inverse_holding_days"]),
                "inverse_cooldown_active": bool(inverse_rule["inverse_cooldown_active"]),
                "override_active": bool(inverse_rule.get("override_active", False)),
            },
            "risk_gate": gate_info,
        }


ACTION_LABELS = DEFAULT_ACTION_LABELS


# ==============================================================================
# 執行器
# ==============================================================================

def _run_model(model: PPO, panel: pd.DataFrame, tickers: list[str]) -> dict:
    env = PortfolioEnv(panel, tickers)
    obs, _ = env.reset()
    done = False
    info = {"weights": np.zeros(len(tickers))}
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    equity = [float(v) for v in env.equity_curve]
    return {
        "final_value": float(equity[-1]),
        "rl_metrics": calculate_backtest_metrics(equity),
        "num_trades": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "final_weights": {ticker: float(w) for ticker, w in zip(tickers, info["weights"])},
        "equity_curve": equity,
    }


def _buy_and_hold(panel: pd.DataFrame, tickers: list[str], weights: np.ndarray, initial_cash: float) -> dict:
    prices = _prices(panel, tickers, field="close")
    shares = float(initial_cash) * weights / prices[0]
    equity = (prices @ shares).astype(float).tolist()
    return {"final_value": float(equity[-1]), "metrics": calculate_backtest_metrics(equity)}


def _train_group(
    stock_data: dict[str, pd.DataFrame],
    tickers: list[str],
    train_start: str,
    train_end: str,
    model_name: str,
    *,
    shared_feature_cols: list[str] | None,
    initial_cash: float,
    timesteps: int,
    seed: int,
    resume_model_path: Path | None = None,
    env_kwargs: dict | None = None,
    ppo_kwargs: dict | None = None,
) -> tuple:
    print(f"\n{'='*72}")
    print(f"訓練 {model_name}")
    print(f"  標的: {tickers}")
    print(f"  訓練: {train_start} ~ {train_end}")
    print(f"  初始資金: {initial_cash:,.0f}")
    print(f"  Timesteps: {timesteps:,}")
    print(f"  Seed: {seed}")
    if resume_model_path is not None:
        print(f"  Resume: {resume_model_path}")

    for t in tickers:
        if t not in stock_data:
            raise RuntimeError(f"無法載入 {t} 數據")

    train_panel = _align_panel(
        stock_data,
        tickers,
        train_start,
        train_end,
        shared_feature_cols=shared_feature_cols,
    )
    if len(train_panel) < 100:
        raise RuntimeError(f"訓練數據不足：{len(train_panel)} 筆")

    print(f"  訓練期: {train_panel['date'].min().date()} ~ {train_panel['date'].max().date()} ({len(train_panel)} 筆)")

    env_kwargs = dict(env_kwargs or {})
    ppo_kwargs = dict(ppo_kwargs or {})
    learning_rate = float(ppo_kwargs.get("learning_rate", 3e-4))
    print(f"  PPO learning_rate: {learning_rate:g}")
    print(f"{'='*72}")
    train_env = PortfolioEnv(
        train_panel,
        tickers,
        shared_feature_cols=shared_feature_cols,
        initial_cash=initial_cash,
        **env_kwargs,
    )
    if resume_model_path is not None:
        model = PPO.load(str(resume_model_path), env=train_env)
        model.learning_rate = learning_rate
        model.lr_schedule = FloatSchedule(learning_rate)
        model.learn(total_timesteps=timesteps, reset_num_timesteps=False)
    else:
        model = PPO(
            "MlpPolicy",
            train_env,
            learning_rate=learning_rate,
            n_steps=ppo_kwargs.get("n_steps", 1024),
            gamma=ppo_kwargs.get("gamma", 0.99),
            gae_lambda=ppo_kwargs.get("gae_lambda", 0.95),
            ent_coef=ppo_kwargs.get("ent_coef", 0.08),
            seed=seed,
            verbose=1,
        )
        model.learn(total_timesteps=timesteps)

    model_path = PROJECT_ROOT / "models" / "portfolio" / model_name
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(model_path))
    print(f"  模型儲存: {model_path}")

    return model, train_panel


def _backtest_group(
    model: PPO,
    stock_data: dict,
    tickers: list[str],
    group_label: str,
    *,
    shared_feature_cols: list[str] | None,
    backtest_start: str,
    backtest_end: str,
    initial_cash: float,
    env_kwargs: dict | None = None,
) -> dict:
    panel = _align_panel(
        stock_data,
        tickers,
        backtest_start,
        backtest_end,
        shared_feature_cols=shared_feature_cols,
    )
    if len(panel) < 100:
        raise RuntimeError(f"Group {group_label} 回測數據不足：{len(panel)} 筆")

    print(f"\n  [{group_label}] 回測: {panel['date'].min().date()} ~ {panel['date'].max().date()} ({len(panel)} 筆)")

    env = PortfolioEnv(
        panel,
        tickers,
        shared_feature_cols=shared_feature_cols,
        initial_cash=initial_cash,
        **dict(env_kwargs or {}),
    )
    obs, _ = env.reset()
    done = False
    info = {"weights": np.zeros(len(tickers))}
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, info = env.step(action)
        done = terminated or truncated

    equity = [float(v) for v in env.equity_curve]
    total_contributions = float(env.total_contributions)
    total_invested_capital = float(initial_cash + total_contributions)
    net_profit = float(equity[-1] - total_invested_capital)
    result = {
        "final_value": float(equity[-1]),
        "rl_metrics": calculate_backtest_metrics(equity),
        "num_trades": int(env.trade_count),
        "fees_paid_estimate": float(env.fees_paid),
        "pva_sigmoid_count": int(env.pva_sigmoid_count),
        "dca_purchase_count": int(env.dca_purchase_count),
        "dca_total_contributions": total_contributions,
        "total_invested_capital": total_invested_capital,
        "net_profit": net_profit,
        "contribution_return": (
            float(net_profit / total_invested_capital) if total_invested_capital > 0 else None
        ),
        "dca_config": {
            "dca_day": int(env.dca_day),
            "monthly_amounts": {
                ticker: float(amount)
                for ticker, amount in zip(tickers, env.dca_amount_array)
                if float(amount) > 0.0
            },
        },
        "pva_sigmoid_config": {
            "features_enabled": bool(env.enable_pva_features),
            "overlay_enabled": bool(env.enable_pva_sigmoid),
            "pva_weight": float(env.pva_weight),
            "pva_j_state_weight": float(env.pva_j_state_weight),
            "pva_m_state_weight": float(env.pva_m_state_weight),
            "pva_drift_threshold": float(env.pva_drift_threshold),
            "policy_mode": "continuous_risk_scaling" if env.enable_pva_sigmoid else "disabled",
            "pva_target_vol": float(env.pva_target_vol),
            "pva_min_leverage_scale": float(env.pva_min_leverage_scale),
            "pva_inverse_hedge_budget": float(env.pva_inverse_hedge_budget),
        },
        "execution_timing": {
            "signal_price": "close_t",
            "execution_price": "open_t_plus_1",
            "mark_to_market_price": "close_t_plus_1",
        },
        "exposure_cap_config": {
            "00631L.TW": float(env.leverage_cap),
            "00632R.TW": float(env.inverse_cap),
        },
        "inverse_hedge_config": {
            "m_state_only": bool(env.inverse_m_state_only),
            "max_holding_days": int(env.inverse_max_holding_days),
            "forced_exit_count": int(env.inverse_forced_exit_count),
        },
        "dca_purchase_history": env.dca_purchase_history,
        "pva_sigmoid_history": env.pva_sigmoid_history,
        "inverse_forced_exit_history": env.inverse_forced_exit_history,
        "sjm_state_history": env.sjm_state_history,
        "sjm_state_counts": {
            state: int(sum(1 for item in env.sjm_state_history if item.get("state") == state))
            for state in ("S", "J", "M")
        },
        "final_weights": {ticker: float(w) for ticker, w in zip(tickers, info["weights"])},
        "equity_curve": equity,
    }

    # B&H benchmarks
    bh_results = {}
    weights_map = {
        "equal": np.ones(len(tickers)) / len(tickers),
        "50_50_blend": _weights_for(tickers, {"0050.TW": 0.5, "00631L.TW": 0.5})
                        if "0050.TW" in tickers and "00631L.TW" in tickers
                        else _weights_for(tickers, {tickers[0]: 1.0}),
    }
    for name, w in weights_map.items():
        bh = _buy_and_hold(panel, tickers, w, initial_cash)
        bh_results[f"buy_and_hold_{name}"] = bh

    return {
        "group": group_label,
        "tickers": tickers,
        "backtest_start": str(panel["date"].min().date()),
        "backtest_end": str(panel["date"].max().date()),
        "backtest_rows": int(len(panel)),
        **result,
        **bh_results,
    }


def main():
    parser = argparse.ArgumentParser(description="雙組訓練 + Group A 預設回測 2024-2026")
    parser.add_argument("--xlsx", default=str(DEFAULT_WORKBOOK), help="Path to the group workbook")
    parser.add_argument("--initial-cash", type=float, default=DEFAULT_INITIAL_CASH, help="Initial cash per group")
    parser.add_argument("--train-start", default=DEFAULT_GROUP_A_TRAIN_START)
    parser.add_argument("--train-end", default=DEFAULT_GROUP_A_TRAIN_END)
    parser.add_argument("--backtest-start", default=DEFAULT_BACKTEST_START)
    parser.add_argument("--backtest-end", default=DEFAULT_BACKTEST_END)
    parser.add_argument(
        "--download-end",
        default=None,
        help="Download end date; defaults to one day after backtest-end",
    )
    parser.add_argument("--timesteps", type=int, default=DEFAULT_TIMESTEPS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--group-a-model-name", default=DEFAULT_GROUP_A_MODEL_NAME)
    parser.add_argument("--group-b-model-name", default=DEFAULT_GROUP_B_MODEL_NAME)
    parser.add_argument(
        "--group-a-resume-model",
        default=None,
        help="Optional existing Group A PPO model checkpoint (.zip or model name) to continue training from",
    )
    parser.add_argument(
        "--group-a-action-schema",
        choices=sorted(GROUP_A_ACTION_SCHEMA_CHOICES),
        default=None,
        help="Discrete action schema for Group A triplet models",
    )
    parser.add_argument(
        "--group-a-profile",
        choices=sorted(GROUP_A_PROFILE_PRESETS.keys()),
        default=DEFAULT_GROUP_A_PROFILE,
        help="Risk profile for Group A",
    )
    parser.add_argument(
        "--group-a-learning-rate",
        type=float,
        default=None,
        help="Optional PPO learning rate override for Group A fresh training or resume fine-tune",
    )
    parser.add_argument(
        "--group-a-00631l-max-weight",
        type=float,
        default=None,
        help="Optional max weight cap for 00631L.TW in Group A, e.g. 0.30",
    )
    parser.add_argument(
        "--group-a-00632r-max-weight",
        type=float,
        default=None,
        help="Optional max weight cap for 00632R.TW in Group A, e.g. 0.30",
    )
    parser.add_argument(
        "--group-filter",
        choices=["both", "group_a", "group_b"],
        default="both",
        help="Train/backtest both groups or only one group",
    )
    parser.add_argument(
        "--group-a-use-dji-features",
        action="store_true",
        help="Append 5 DJI lag features to Group A observation state",
    )
    parser.add_argument(
        "--group-a-enable-dca",
        action="store_true",
        help="Apply monthly DCA during Group A backtest only",
    )
    parser.add_argument(
        "--group-a-dca-day",
        type=int,
        default=DEFAULT_GROUP_A_DCA_DAY,
        help="Scheduled day-of-month for Group A DCA",
    )
    parser.add_argument(
        "--group-a-dca-0050",
        type=float,
        default=DEFAULT_GROUP_A_DCA_0050,
        help="Monthly DCA cash contribution for 0050.TW during Group A backtest",
    )
    parser.add_argument(
        "--group-a-enable-pva-features",
        action="store_true",
        help="Append Group A PVA/SJM features to observation state without requiring overlay trades",
    )
    parser.add_argument(
        "--group-a-enable-llm-sentiment",
        action="store_true",
        help="Append daily LLM sentiment features to Group A shared market state",
    )
    parser.add_argument(
        "--group-a-llm-sentiment-path",
        default=None,
        help=(
            "Optional daily LLM sentiment feature file, or raw news file/directory "
            "(CSV/TSV/JSON/JSONL/Parquet) that will be auto-converted for Group A"
        ),
    )
    parser.add_argument(
        "--group-a-enable-pva-sigmoid",
        action="store_true",
        help="Apply Group A PVA/SJM continuous risk scaling during training and backtest",
    )
    parser.add_argument(
        "--group-a-pva-weight",
        type=float,
        default=0.30,
        help="Continuous risk scaling intensity outside M state",
    )
    parser.add_argument(
        "--group-a-pva-j-state-weight",
        type=float,
        default=0.0,
        help="Continuous risk scaling intensity in J state",
    )
    parser.add_argument(
        "--group-a-pva-m-state-weight",
        type=float,
        default=1.0,
        help="Continuous risk scaling intensity in M state",
    )
    parser.add_argument(
        "--group-a-pva-drift-threshold",
        type=float,
        default=0.05,
        help="Minimum turnover drift required before Group A PVA scaling executes",
    )
    parser.add_argument(
        "--group-a-pva-target-vol",
        type=float,
        default=DEFAULT_GROUP_A_PVA_TARGET_VOL,
        help="20-day daily volatility target used by Group A PVA risk scaling",
    )
    parser.add_argument(
        "--group-a-pva-min-leverage-scale",
        type=float,
        default=DEFAULT_GROUP_A_PVA_MIN_LEVERAGE_SCALE,
        help="Minimum remaining 00631L scale under Group A PVA risk scaling",
    )
    parser.add_argument(
        "--group-a-pva-inverse-hedge-budget",
        type=float,
        default=DEFAULT_GROUP_A_PVA_INVERSE_HEDGE_BUDGET,
        help="Maximum 00632R hedge budget available to Group A PVA in M state",
    )
    parser.add_argument(
        "--group-a-inverse-max-hold-days",
        type=int,
        default=DEFAULT_GROUP_A_INVERSE_MAX_HOLD_DAYS,
        help="Maximum consecutive trading days to hold 00632R before forced exit",
    )
    parser.add_argument(
        "--group-a-inverse-allow-non-m",
        action="store_true",
        help="Allow 00632R holdings outside M state (default is M-state only short hedge)",
    )
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx)
    if not xlsx_path.is_absolute():
        xlsx_path = (PROJECT_ROOT / xlsx_path).resolve()
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Workbook not found: {xlsx_path}")

    download_end = args.download_end
    if download_end is None:
        download_end = args.backtest_end

    group_a_resume_model_path = _resolve_model_checkpoint(args.group_a_resume_model)

    groups = _load_groups_from_workbook(xlsx_path)
    group_a_tickers = groups["group_a"] or DEFAULT_GROUP_A_TICKERS
    group_b_tickers = groups["group_b"] or DEFAULT_GROUP_B_TICKERS
    group_a_profile = _resolve_group_a_profile(args.group_a_profile)
    group_a_action_schema = infer_group_a_action_schema(
        model_name=(
            group_a_resume_model_path.stem
            if group_a_resume_model_path is not None
            else args.group_a_model_name
        ),
        action_schema=args.group_a_action_schema,
    )
    if args.group_a_learning_rate is not None:
        if float(args.group_a_learning_rate) <= 0.0:
            raise ValueError("--group-a-learning-rate must be > 0")
        group_a_profile["ppo"]["learning_rate"] = float(args.group_a_learning_rate)
    if args.group_a_00631l_max_weight is not None:
        if not 0.0 <= float(args.group_a_00631l_max_weight) <= 1.0:
            raise ValueError("--group-a-00631l-max-weight must be between 0 and 1")
        group_a_profile["env"]["leverage_cap"] = float(args.group_a_00631l_max_weight)
    if args.group_a_00632r_max_weight is not None:
        if not 0.0 <= float(args.group_a_00632r_max_weight) <= 1.0:
            raise ValueError("--group-a-00632r-max-weight must be between 0 and 1")
        group_a_profile["env"]["inverse_cap"] = float(args.group_a_00632r_max_weight)
    if not 0.0 <= float(args.group_a_pva_min_leverage_scale) <= 1.0:
        raise ValueError("--group-a-pva-min-leverage-scale must be between 0 and 1")
    if float(args.group_a_pva_target_vol) <= 0.0:
        raise ValueError("--group-a-pva-target-vol must be > 0")
    if float(args.group_a_pva_inverse_hedge_budget) < 0.0:
        raise ValueError("--group-a-pva-inverse-hedge-budget must be >= 0")
    if int(args.group_a_inverse_max_hold_days) < 0:
        raise ValueError("--group-a-inverse-max-hold-days must be >= 0")
    use_group_a_dji_features = bool(args.group_a_use_dji_features or args.group_a_profile == "conservative")
    use_group_a_pva_features = bool(args.group_a_enable_pva_features or args.group_a_enable_pva_sigmoid)
    selected_tickers: list[str] = []
    if args.group_filter in {"both", "group_a"}:
        selected_tickers.extend(group_a_tickers)
    if args.group_filter in {"both", "group_b"}:
        selected_tickers.extend(group_b_tickers)
    all_tickers = sorted(set(selected_tickers))

    print("=" * 72)
    print("雙組訓練：Group A + Group B")
    print(f"Workbook: {xlsx_path}")
    print(f"Group A: {group_a_tickers} | 訓練 {args.train_start} ~ {args.train_end}")
    print(f"Group B: {group_b_tickers} | 訓練 {args.train_start} ~ {args.train_end}")
    print(f"執行群組: {args.group_filter}")
    print(f"Group A profile: {args.group_a_profile}")
    print(f"Group A action schema: {group_a_action_schema}")
    if group_a_resume_model_path is not None:
        print(f"Group A resume model: {group_a_resume_model_path}")
    print(f"Group A PPO learning rate: {group_a_profile['ppo']['learning_rate']:g}")
    print(f"Group A DJI 5 特徵: {use_group_a_dji_features}")
    print(f"Group A 00631L 上限: {group_a_profile['env']['leverage_cap']:.2%}")
    print(f"Group A 00632R 上限: {group_a_profile['env'].get('inverse_cap', 1.0):.2%}")
    print(
        "Group A 00632R 規則: "
        f"{'僅 M 狀態可持有' if not args.group_a_inverse_allow_non_m else '可跨狀態持有'}, "
        f"最長 {args.group_a_inverse_max_hold_days} 個交易日"
    )
    print("成交時點: 用 t 日資料產生訊號，於 t+1 開盤價成交，並以 t+1 收盤價計算績效")
    if args.group_a_enable_pva_sigmoid:
        print(
            "Group A PVA/SJM: 特徵+連續風險縮放 開啟 "
            f"(pva_weight={args.group_a_pva_weight:.2f}, "
            f"j_state_weight={args.group_a_pva_j_state_weight:.2f}, "
            f"m_state_weight={args.group_a_pva_m_state_weight:.2f}, "
            f"drift_threshold={args.group_a_pva_drift_threshold:.2f}, "
            f"target_vol={args.group_a_pva_target_vol:.4f}, "
            f"min_leverage_scale={args.group_a_pva_min_leverage_scale:.2f}, "
            f"inverse_hedge_budget={args.group_a_pva_inverse_hedge_budget:.2f})"
        )
    elif use_group_a_pva_features:
        print("Group A PVA/SJM: 僅特徵開啟（不執行 overlay）")
    else:
        print("Group A PVA/SJM: 關閉")
    if args.group_a_enable_dca:
        print(f"Group A DCA: 每月 {args.group_a_dca_day} 日加碼 0050 {args.group_a_dca_0050:,.0f} 元（僅回測）")
    else:
        print("Group A DCA: 關閉")
    resolved_group_a_llm_sentiment = None
    group_a_llm_sentiment_info = None
    if args.group_a_enable_llm_sentiment:
        resolved_group_a_llm_sentiment, group_a_llm_sentiment_info = _resolve_group_a_llm_sentiment_input(
            args.group_a_llm_sentiment_path
        )
        if resolved_group_a_llm_sentiment is not None:
            if group_a_llm_sentiment_info and bool(group_a_llm_sentiment_info.get("generated")):
                input_rows = group_a_llm_sentiment_info.get("input_rows")
                daily_rows = group_a_llm_sentiment_info.get("daily_rows")
                mode = group_a_llm_sentiment_info.get("mode", "unknown")
                print(
                    "Group A LLM sentiment: 自動建檔 "
                    f"({group_a_llm_sentiment_info.get('source_path')} -> {resolved_group_a_llm_sentiment}, "
                    f"mode={mode}, input_rows={input_rows}, daily_rows={daily_rows})"
                )
            else:
                print(f"Group A LLM sentiment: 開啟 ({resolved_group_a_llm_sentiment})")
        else:
            print("Group A LLM sentiment: 開啟（目前未找到特徵檔，將以 0 填補）")
        print(
            "Group A sentiment gate: 開啟 "
            f"(risk_off>={DEFAULT_GROUP_A_SENTIMENT_RISK_OFF_THRESHOLD:.2f}, "
            f"severe>={DEFAULT_GROUP_A_SENTIMENT_SEVERE_THRESHOLD:.2f}, "
            f"min_conf={DEFAULT_GROUP_A_SENTIMENT_MIN_CONFIDENCE:.2f}, "
            f"min_intensity={DEFAULT_GROUP_A_SENTIMENT_MIN_INTENSITY:.2f})"
        )
    else:
        print("Group A LLM sentiment: 關閉")
    print(f"回測:    {args.backtest_start} ~ {args.backtest_end}")
    print(f"下載到:  {download_end}")
    print(f"每組初始資金: {args.initial_cash:,.0f}")
    print(f"Timesteps: {args.timesteps:,}")
    print(f"Seed: {args.seed}")
    print("=" * 72)

    group_a_shared_feature_cols = []
    if use_group_a_dji_features:
        group_a_shared_feature_cols.extend(DJI_FEATURE_COLUMNS)
    if args.group_a_enable_llm_sentiment:
        group_a_shared_feature_cols.extend(LLM_SENTIMENT_COLUMNS)
    if not group_a_shared_feature_cols:
        group_a_shared_feature_cols = None

    print(f"\n統一載入資料（DB 優先）: {args.train_start} ~ {download_end}")
    stock_data = load_stock_data_db_first(all_tickers, args.train_start, download_end)
    if group_a_shared_feature_cols and args.group_filter in {"both", "group_a"}:
        stock_data = attach_market_features_db_first(
            stock_data,
            group_a_tickers,
            args.train_start,
            download_end,
            include_llm_sentiment=bool(args.group_a_enable_llm_sentiment),
            llm_sentiment_path=(
                str(resolved_group_a_llm_sentiment)
                if resolved_group_a_llm_sentiment is not None
                else None
            ),
        )

    effective_group_a_start = _effective_common_start(stock_data, group_a_tickers, args.train_start, download_end)
    if args.group_filter in {"both", "group_a"} and effective_group_a_start is not None:
        requested_start = pd.Timestamp(args.train_start).normalize()
        if effective_group_a_start > requested_start:
            print(
                f"[Group A] 名義起訓日 {requested_start.date()} 早於共同資料起點 "
                f"{effective_group_a_start.date()}；實際可用資料將從 {effective_group_a_start.date()} 開始。"
            )

    model_a = train_panel_a = result_a = None
    if args.group_filter in {"both", "group_a"}:
        group_a_train_env_kwargs = dict(group_a_profile["env"])
        group_a_train_env_kwargs["group_a_action_schema"] = group_a_action_schema
        if use_group_a_pva_features:
            group_a_train_env_kwargs["enable_pva_features"] = True
        if args.group_a_enable_llm_sentiment:
            group_a_train_env_kwargs["sentiment_gate_enabled"] = True
        group_a_train_env_kwargs.update(
            {
                "inverse_m_state_only": bool(not args.group_a_inverse_allow_non_m),
                "inverse_max_holding_days": int(args.group_a_inverse_max_hold_days),
            }
        )
        if args.group_a_enable_pva_sigmoid:
            group_a_train_env_kwargs.update(
                {
                    "enable_pva_sigmoid": True,
                    "pva_weight": float(args.group_a_pva_weight),
                    "pva_j_state_weight": float(args.group_a_pva_j_state_weight),
                    "pva_m_state_weight": float(args.group_a_pva_m_state_weight),
                    "pva_drift_threshold": float(args.group_a_pva_drift_threshold),
                    "pva_target_vol": float(args.group_a_pva_target_vol),
                    "pva_min_leverage_scale": float(args.group_a_pva_min_leverage_scale),
                    "pva_inverse_hedge_budget": float(args.group_a_pva_inverse_hedge_budget),
                }
            )
        group_a_backtest_env_kwargs = dict(group_a_profile["env"])
        group_a_backtest_env_kwargs["group_a_action_schema"] = group_a_action_schema
        if use_group_a_pva_features:
            group_a_backtest_env_kwargs["enable_pva_features"] = True
        if args.group_a_enable_llm_sentiment:
            group_a_backtest_env_kwargs["sentiment_gate_enabled"] = True
        group_a_backtest_env_kwargs.update(
            {
                "inverse_m_state_only": bool(not args.group_a_inverse_allow_non_m),
                "inverse_max_holding_days": int(args.group_a_inverse_max_hold_days),
            }
        )
        if args.group_a_enable_pva_sigmoid:
            group_a_backtest_env_kwargs.update(
                {
                    "enable_pva_sigmoid": True,
                    "pva_weight": float(args.group_a_pva_weight),
                    "pva_j_state_weight": float(args.group_a_pva_j_state_weight),
                    "pva_m_state_weight": float(args.group_a_pva_m_state_weight),
                    "pva_drift_threshold": float(args.group_a_pva_drift_threshold),
                    "pva_target_vol": float(args.group_a_pva_target_vol),
                    "pva_min_leverage_scale": float(args.group_a_pva_min_leverage_scale),
                    "pva_inverse_hedge_budget": float(args.group_a_pva_inverse_hedge_budget),
                }
            )
        if args.group_a_enable_dca:
            group_a_backtest_env_kwargs.update(
                {
                    "dca_monthly_amounts": {"0050.TW": float(args.group_a_dca_0050)},
                    "dca_day": int(args.group_a_dca_day),
                }
            )
        model_a, train_panel_a = _train_group(
            stock_data,
            group_a_tickers,
            args.train_start,
            args.train_end,
            args.group_a_model_name,
            shared_feature_cols=group_a_shared_feature_cols,
            initial_cash=args.initial_cash,
            timesteps=args.timesteps,
            seed=args.seed,
            resume_model_path=group_a_resume_model_path,
            env_kwargs=group_a_train_env_kwargs,
            ppo_kwargs=group_a_profile["ppo"],
        )
        result_a = _backtest_group(
            model_a,
            stock_data,
            group_a_tickers,
            "GroupA",
            shared_feature_cols=group_a_shared_feature_cols,
            backtest_start=args.backtest_start,
            backtest_end=args.backtest_end,
            initial_cash=args.initial_cash,
            env_kwargs=group_a_backtest_env_kwargs,
        )

    model_b = train_panel_b = result_b = None
    if args.group_filter in {"both", "group_b"}:
        model_b, train_panel_b = _train_group(
            stock_data,
            group_b_tickers,
            args.train_start,
            args.train_end,
            args.group_b_model_name,
            shared_feature_cols=None,
            initial_cash=args.initial_cash,
            timesteps=args.timesteps,
            seed=args.seed,
            env_kwargs=None,
            ppo_kwargs=None,
        )
        result_b = _backtest_group(
            model_b,
            stock_data,
            group_b_tickers,
            "GroupB",
            shared_feature_cols=None,
            backtest_start=args.backtest_start,
            backtest_end=args.backtest_end,
            initial_cash=args.initial_cash,
            env_kwargs=None,
        )

    # ── 儲存結果 ──
    output_file = PROJECT_ROOT / "results" / (
        f"{args.group_filter}_backtest_{args.backtest_start.replace('-', '')}_{args.backtest_end.replace('-', '')}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "experiment": "dual_group_0050_vs_multi",
        "workbook": str(xlsx_path),
        "initial_cash_per_group": float(args.initial_cash),
        "timesteps": args.timesteps,
        "seed": args.seed,
        "group_filter": args.group_filter,
        "group_a_profile": args.group_a_profile,
        "group_a_resume_model": str(group_a_resume_model_path) if group_a_resume_model_path is not None else None,
        "group_a_action_schema": group_a_action_schema,
        "group_a_ppo_config": {
            "learning_rate": float(group_a_profile["ppo"]["learning_rate"]),
            "n_steps": int(group_a_profile["ppo"]["n_steps"]),
            "gamma": float(group_a_profile["ppo"]["gamma"]),
            "gae_lambda": float(group_a_profile["ppo"]["gae_lambda"]),
            "ent_coef": float(group_a_profile["ppo"]["ent_coef"]),
        },
        "group_a_use_dji_features": use_group_a_dji_features,
        "group_a_use_llm_sentiment": bool(args.group_a_enable_llm_sentiment),
        "group_a_dca_enabled": bool(args.group_a_enable_dca),
        "group_a_exposure_caps": {
            "00631L.TW": float(group_a_profile["env"]["leverage_cap"]),
            "00632R.TW": float(group_a_profile["env"].get("inverse_cap", 1.0)),
        },
        "group_a_llm_sentiment_config": {
            "enabled": bool(args.group_a_enable_llm_sentiment),
            "path": str(resolved_group_a_llm_sentiment) if resolved_group_a_llm_sentiment is not None else None,
            "source_path": (
                str(group_a_llm_sentiment_info.get("source_path"))
                if group_a_llm_sentiment_info and group_a_llm_sentiment_info.get("source_path")
                else args.group_a_llm_sentiment_path
            ),
            "mode": (
                str(group_a_llm_sentiment_info.get("mode"))
                if group_a_llm_sentiment_info and group_a_llm_sentiment_info.get("mode")
                else None
            ),
            "generated": bool(group_a_llm_sentiment_info.get("generated")) if group_a_llm_sentiment_info else False,
            "input_rows": (
                int(group_a_llm_sentiment_info["input_rows"])
                if group_a_llm_sentiment_info and group_a_llm_sentiment_info.get("input_rows") is not None
                else None
            ),
            "daily_rows": (
                int(group_a_llm_sentiment_info["daily_rows"])
                if group_a_llm_sentiment_info and group_a_llm_sentiment_info.get("daily_rows") is not None
                else None
            ),
            "text_columns": (
                list(group_a_llm_sentiment_info.get("text_columns", []))
                if group_a_llm_sentiment_info
                else []
            ),
            "columns": list(LLM_SENTIMENT_COLUMNS),
            "note": (
                "Daily market-level LLM sentiment features are merged into Group A shared market state and "
                "also drive a sentiment risk gate that can neutralize 00631L or enable 00632R defense."
                if args.group_a_enable_llm_sentiment
                else "LLM sentiment features are disabled."
            ),
        },
        "group_a_sentiment_gate_config": {
            "enabled": bool(args.group_a_enable_llm_sentiment),
            "risk_off_threshold": float(DEFAULT_GROUP_A_SENTIMENT_RISK_OFF_THRESHOLD),
            "severe_threshold": float(DEFAULT_GROUP_A_SENTIMENT_SEVERE_THRESHOLD),
            "min_confidence": float(DEFAULT_GROUP_A_SENTIMENT_MIN_CONFIDENCE),
            "min_intensity": float(DEFAULT_GROUP_A_SENTIMENT_MIN_INTENSITY),
            "risk_off_inverse_floor": float(DEFAULT_GROUP_A_SENTIMENT_RISK_OFF_INVERSE_FLOOR),
            "severe_inverse_floor": float(DEFAULT_GROUP_A_SENTIMENT_SEVERE_INVERSE_FLOOR),
            "note": (
                "LLM sentiment can zero 00631L on risk-off days and force a 00632R defensive floor on severe days."
                if args.group_a_enable_llm_sentiment
                else "Sentiment gate is disabled because Group A LLM sentiment is disabled."
            ),
        },
        "group_a_pva_sigmoid_config": {
            "features_enabled": bool(use_group_a_pva_features),
            "overlay_enabled": bool(args.group_a_enable_pva_sigmoid),
            "pva_weight": float(args.group_a_pva_weight),
            "pva_j_state_weight": float(args.group_a_pva_j_state_weight),
            "pva_m_state_weight": float(args.group_a_pva_m_state_weight),
            "pva_drift_threshold": float(args.group_a_pva_drift_threshold),
            "policy_mode": "continuous_risk_scaling" if args.group_a_enable_pva_sigmoid else "disabled",
            "pva_target_vol": float(args.group_a_pva_target_vol),
            "pva_min_leverage_scale": float(args.group_a_pva_min_leverage_scale),
            "pva_inverse_hedge_budget": float(args.group_a_pva_inverse_hedge_budget),
            "note": (
                "Group A PVA/SJM uses continuous risk scaling on 00631L plus short-duration 00632R hedging in M state."
                if args.group_a_enable_pva_sigmoid
                else (
                    "Group A PVA/SJM features are enabled for observation only; overlay is disabled."
                    if use_group_a_pva_features
                    else "Group A PVA/SJM is disabled."
                )
            ),
        },
        "group_a_inverse_hedge_config": {
            "m_state_only": bool(not args.group_a_inverse_allow_non_m),
            "max_holding_days": int(args.group_a_inverse_max_hold_days),
            "note": "00632R is treated as a short hedge and is forcibly exited when M state ends or max holding days is reached.",
        },
        "execution_timing": {
            "signal_price": "close_t",
            "execution_price": "open_t_plus_1",
            "mark_to_market_price": "close_t_plus_1",
            "note": "Signals use day-t data, trades execute at next trading day's open, and performance is marked at next close.",
        },
        "group_a_dca_config": (
            {
                "dca_day": int(args.group_a_dca_day),
                "monthly_amounts": {"0050.TW": float(args.group_a_dca_0050)},
                "note": "Group A DCA is applied only during evaluation/backtest, not PPO training reward.",
            }
            if args.group_a_enable_dca
            else {
                "dca_day": int(args.group_a_dca_day),
                "monthly_amounts": {},
                "note": "Group A DCA is disabled.",
            }
        ),
        "train_start": args.train_start,
        "train_end": args.train_end,
        "backtest_start": args.backtest_start,
        "backtest_end": args.backtest_end,
        "download_end": download_end,
    }
    if train_panel_a is not None and result_a is not None:
        payload["group_a"] = {
            "tickers": group_a_tickers,
            "train_start": args.train_start,
            "train_end": args.train_end,
            "profile": args.group_a_profile,
            "resume_model": str(group_a_resume_model_path) if group_a_resume_model_path is not None else None,
            "action_schema": group_a_action_schema,
            "ppo_config": {
                "learning_rate": float(group_a_profile["ppo"]["learning_rate"]),
                "n_steps": int(group_a_profile["ppo"]["n_steps"]),
                "gamma": float(group_a_profile["ppo"]["gamma"]),
                "gae_lambda": float(group_a_profile["ppo"]["gae_lambda"]),
                "ent_coef": float(group_a_profile["ppo"]["ent_coef"]),
            },
            "model_name": args.group_a_model_name,
            "shared_feature_cols": group_a_shared_feature_cols or [],
            "train_rows": int(len(train_panel_a)),
            "result": result_a,
        }
    if train_panel_b is not None and result_b is not None:
        payload["group_b"] = {
            "tickers": group_b_tickers,
            "train_start": args.train_start,
            "train_end": args.train_end,
            "model_name": args.group_b_model_name,
            "shared_feature_cols": [],
            "train_rows": int(len(train_panel_b)),
            "result": result_b,
        }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    # ── 摘要 ──
    print("\n" + "=" * 72)
    print("結果摘要")
    print("=" * 72)
    summary_rows = []
    if result_a is not None:
        summary_rows.append(("Group A (0050)", result_a))
    if result_b is not None:
        summary_rows.append(("Group B (多檔)", result_b))
    for label, res in summary_rows:
        m = res["rl_metrics"]
        print(f"\n{label}:")
        print(f"  最終價值: {res['final_value']:,.0f}")
        print(f"  報酬率:   {m['total_return']*100:.2f}%")
        print(f"  年化報酬: {m['annual_return']*100:.2f}%")
        print(f"  Sharpe:  {m['sharpe']:.3f}")
        print(f"  MDD:     {m['max_drawdown']*100:.2f}%")
        print(f"  交易次:  {res['num_trades']}")
        if res.get("pva_sigmoid_count", 0) > 0:
            print(f"  PVA次數: {res['pva_sigmoid_count']}")
            print(f"  SJM統計: {res.get('sjm_state_counts', {})}")
        if res.get("dca_purchase_count", 0) > 0:
            print(f"  DCA次數: {res['dca_purchase_count']}")
            print(f"  DCA投入: {res['dca_total_contributions']:,.0f}")
            print(f"  總投入:  {res['total_invested_capital']:,.0f}")
            print(f"  淨利:    {res['net_profit']:,.0f}")
            print(f"  投入報酬:{res['contribution_return']*100:.2f}%")

    print(f"\n結果檔: {output_file}")
    print("=" * 72)


if __name__ == "__main__":
    main()
