#!/usr/bin/env python3
"""
NCF_00631L — Next Close Forecast for 00631L
價格預測 + 方向預測（雙模型）

用法:
    python3 ncf_00631l.py                      # 預測明日收盤+方向
    python3 ncf_00631l.py --output results/ncf_00631l_20260624.json
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.base import clone
from sklearn.feature_selection import SelectFromModel
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import ElasticNet, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

# Optional boosting libraries — gracefully degraded if not installed
try:
    import lightgbm as lgb
    _HAS_LGB = True
except ImportError:
    _HAS_LGB = False

try:
    import xgboost as xgb
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

try:
    from catboost import CatBoostClassifier
    _HAS_CAT = True
except ImportError:
    _HAS_CAT = False

try:
    from pytorch_tabnet.tab_model import TabNetClassifier as _TabNetClassifier
    import torch as _torch
    _HAS_TABNET = True
except ImportError:
    _HAS_TABNET = False

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from FinRL.data.stock_db import DB_PATH
from group_a_plus.integrations.tbrain_features import add_tbrain_features, tbrain_feature_columns
from group_a_plus.integrations.fourier_features import add_fourier_features, fourier_feature_columns
from group_a_plus.integrations.global_features import (
    add_global_features,
    global_feature_columns,
    global_interaction_feature_columns,
)
from ncf_data_quality import ncf_data_freshness
from ncf_external_cache import fetch_yf_close_cached

TICKER = "00631L.TW"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / f"ncf_00631l_{datetime.now().strftime('%Y%m%d')}.json"
TBRAIN_FEATURES = tbrain_feature_columns()
FOURIER_FEATURES = fourier_feature_columns()
GLOBAL_FEATURES = global_feature_columns()
GLOBAL_INTERACTION_FEATURES = global_interaction_feature_columns()

# Scale-invariant features
FEATURES = [
    # Gap / Intraday pattern
    "gap",
    "close_open_ratio",
    "upper_shadow_pct",
    "lower_shadow_pct",
    "body_pct",
    # Lagged returns
    "return_1d",
    "return_2d",
    "return_3d",
    "return_5d",
    "return_10d",
    "return_21d",
    # Price/MA ratios
    "close_ma5_ratio",
    "close_ma10_ratio",
    "close_ma20_ratio",
    "close_ma30_ratio",
    "close_ma60_ratio",
    "close_ma120_ratio",
    "close_ma200_ratio",
    "close_ma240_ratio",
    "ma5_ma10_ratio",
    "ma5_ma20_ratio",
    "ma20_ma60_ratio",
    "ma60_ma200_ratio",
    # Momentum
    "momentum_3",
    "momentum_5",
    "momentum_10",
    "momentum_21",
    "momentum_63",
    # Volatility / regime
    "volatility_5",
    "volatility_20",
    "volatility_60",
    "rolling_mdd_20",
    "rolling_mdd_60",
    # Technical
    "rsi_7",
    "rsi_14",
    "rsi_28",
    "macd_signal",
    "macd_diff",
    "adx_14",
    "atr_14_normalized",
    "bb_position",
    "bb_width",
    "volume_ratio_20",
    "volume_ratio_5",
    # Regime flags
    "above_ma200",
    "above_ma50",
    "above_ma20",
    "close_ma200_dist",
    "close_ma50_dist",
    # Momentum streaks
    "consecutive_up_days",
    "consecutive_down_days",
]

# External market features (optional, --external-features flag)
EXT_FEATURES = [
    # US overnight signals (previous US session, shift=1 on Taiwan calendar)
    "us_qqq_ret",        # QQQ overnight return
    "us_qqq_5d_ret",     # QQQ 5-day momentum (shift=1)
    "us_qqq_10d_ret",    # QQQ 10-day momentum (shift=1)
    "us_soxx_ret",       # SOXX (semiconductors) overnight return
    "us_nasdaq_ret",     # NASDAQ Composite overnight return
    "us_tsm_adr_ret",    # TSM ADR overnight return
    "vix",               # VIX level (previous close)
    "vix_change",        # VIX 1-day change
    "vix_ma20_ratio",    # VIX / VIX_MA20 — spike detection (shift=1)
    "usdtwd_change",     # USD/TWD rate change (+ = TWD weakening)
    # Taiwan market context (same-day, no shift — all close at 1:30pm)
    "twii_ret",          # 加權指數 same-day return
    "twii_5d_ret",       # TWII 5-day momentum (shift=0)
    "twii_vs_ma20",      # TWII distance from 20-day MA
    "tsmc_ret",          # 台積電 (2330.TW) same-day return
    "eti0050_ret",       # 0050 same-day return
    "eti0050_5d_ret",    # 0050 5-day momentum (shift=0)
    "eti0050_bb_pct",    # 0050 Bollinger Band %B (0-1 percentile position, 20-day)
    "eti0050_bb_width",  # 0050 Bollinger Band width (2*std/ma20)
    "tsmc_vs_0050_5d",   # TSMC 5-day return minus 0050 5-day return
    # Institutional chip data (T-1, published after previous close)
    "inst_foreign_net",  # 外資買賣超 normalized
    "inst_total_net",    # 三大法人合計買賣超 normalized
    "inst_foreign_ma5",  # 外資買超 5-day moving average
    # Margin / short (T-1, published after previous close)
    "margin_chg_pct",    # 融資餘額日變化%
    "short_chg_pct",     # 融券餘額日變化%
    "margin_short_log",  # log(融資/融券) ratio
    # 台指期夜盤 (previous available after-hours session)
    "tx_night_ret",      # 台指期夜盤漲跌幅
    # TXO 選擇權法人未平倉 (T-1, published after market close)
    "txo_foreign_put_oi",    # 外資 PUT 淨多頭口數 (+ = 買保護 = 看空)
    "txo_foreign_call_oi",   # 外資 CALL 淨多頭口數 (- = 賣權 = 看空)
    "txo_foreign_pc_spread", # PUT - CALL 差 (+ = 外資淨看空)
    "txo_total_pcr",         # 三大法人合計 PUT/CALL 比率 (>1 = 看空壓力)
    "txo_foreign_pc_spread_ma5",  # txo_foreign_pc_spread 5日均線
    # TXO 全市場 PCR (含散戶) — 逆勢指標, shift=1
    "txo_market_pcr_volume",        # 全市場 Put/Call 量比
    "txo_market_pcr_oi",            # 全市場 Put/Call 未平倉比
    "txo_market_pcr_volume_5d_zscore",  # 量比 5日 z-score
    "txo_market_pcr_oi_5d_zscore",     # OI比 5日 z-score
    "txo_market_pcr_volume_20d_zscore", # 量比 20日 z-score
    # 長週期總體代理 (60d/120d) — PMI/出口訂單替代
    "twii_60d_ret",      # TWII 60日報酬（台灣景氣循環代理）
    "twii_120d_ret",     # TWII 120日報酬（半年景氣趨勢）
    "twii_vs_ma60",      # TWII vs 60日均線（景氣偏離）
    "twii_vs_ma120",     # TWII vs 120日均線
    "us_soxx_60d_ret",   # 費城半導體 60日動能（出口需求代理）
    "ewt_vs_0050_60d",   # EWT vs 0050 60日相對報酬（外資總體看法）
    "soxx_vs_twii_60d",  # 半導體 vs 台灣整體 60日相對強弱
]

INTERACTION_FEATURES = [
    # Internal regime interactions
    "vol20_x_bb_width",
    "vol20_x_close_ma200_dist",
    "momentum21_x_above_ma200",
    "return5_x_vol20",
    "rsi14_x_close_ma50_dist",
    # External market interactions
    "vix_spike_x_vol20",
    "vix_change_x_return1d",
    "qqq5d_x_momentum21",
    "twii5d_x_close_ma200_dist",
    "twii_ret_x_return1d",
    "tsmc0050spread_x_momentum5",
    "usdtwd_x_vix_change",
    "tx_night_x_gap",
    # Chip / margin interactions
    "foreign_x_margin_chg",
    "inst_total_x_short_chg",
    "margin_short_x_rsi14",
    # TXO Put/Call OI interactions
    "txo_pcr_x_ma_gap",          # 高P/C比率 × 晚期多頭 (最強看空信號組合)
    "txo_foreign_pc_x_vix",      # 外資PC差 × VIX (恐慌確認)
    "txo_foreign_pc_x_inst_net", # 外資選擇權 vs 現貨 chip 方向一致性
    # 全市場 PCR 互動
    "txo_mkt_pcr_x_vix",         # 全市場量比 × VIX 高峰 (極端恐慌確認)
    "txo_mkt_pcr_x_inst_net",    # 全市場量比 vs 現貨外資方向背離
    # 0050 Bollinger Band overbought × VIX spike (late-bull de-leverage signal)
    "bb0050_x_vix",
]


def _fetch_yf(ticker: str, start: str, end: str) -> pd.Series:
    """Read Close series from DB cache; optionally download when explicitly enabled."""
    try:
        allow_download = os.environ.get("NCF_EXTERNAL_ALLOW_DOWNLOAD", "").lower() in {"1", "true", "yes"}
        return fetch_yf_close_cached(ticker, start, end, DB_PATH, allow_download=allow_download)
    except Exception:
        return pd.Series(dtype=float, name=ticker)


def load_external_df(main_df: pd.DataFrame, db_path: Path) -> pd.DataFrame:
    """
    Build all EXT_FEATURES aligned to Taiwan trading dates (main_df.index).

    Timing rules:
    - US overnight (QQQ/SOXX/NASDAQ/TSM/VIX/USD/TWD): shift=1 on Taiwan calendar.
      At Taiwan date T, uses the US session that closed at ~4am on date T morning.
    - Taiwan market (TWII/TSMC/0050): shift=0. Close simultaneously with 00631L at 1:30pm.
    - Institutional / Margin: shift=1. Data published after previous day's close.
    - 台指期夜盤 (盤後): shift=1. Use the previous available after-hours session.
    """
    idx = main_df.index
    start_ext = (idx[0] - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    end_ext = (idx[-1] + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    ext = pd.DataFrame(index=idx)

    def _align(series: pd.Series, shift_n: int = 0) -> np.ndarray:
        if series is None or series.empty:
            return np.full(len(idx), np.nan)
        s = series.reindex(idx, method="ffill")
        if shift_n:
            s = s.shift(shift_n)
        return s.values

    # ── US overnight (shift=1) ──────────────────────────────────────────
    us_map = {
        "QQQ":   "us_qqq_ret",
        "SOXX":  "us_soxx_ret",
        "^IXIC": "us_nasdaq_ret",
        "TSM":   "us_tsm_adr_ret",
    }
    for tick, feat in us_map.items():
        cl = _fetch_yf(tick, start_ext, end_ext)
        ext[feat] = _align(cl.pct_change(), shift_n=1)
        if tick == "QQQ":
            ext["us_qqq_5d_ret"] = _align(cl.pct_change(5), shift_n=1)
            ext["us_qqq_10d_ret"] = _align(cl.pct_change(10), shift_n=1)

    # VIX
    vix_cl = _fetch_yf("^VIX", start_ext, end_ext)
    ext["vix"] = _align(vix_cl, shift_n=1)
    ext["vix_change"] = _align(vix_cl.pct_change(), shift_n=1)
    ext["vix_ma20_ratio"] = _align(vix_cl / vix_cl.rolling(20).mean(), shift_n=1)

    # USD/TWD (TWD=X → TWD per USD; +change = TWD weakening)
    usdtwd_cl = _fetch_yf("TWD=X", start_ext, end_ext)
    ext["usdtwd_change"] = _align(usdtwd_cl.pct_change(), shift_n=1)

    # ── Taiwan market same-day (shift=0) ────────────────────────────────
    twii_cl = _fetch_yf("^TWII", start_ext, end_ext)
    ext["twii_ret"] = _align(twii_cl.pct_change(), shift_n=0)
    ext["twii_5d_ret"] = _align(twii_cl.pct_change(5), shift_n=0)
    twii_ma20 = twii_cl.rolling(20).mean()
    ext["twii_vs_ma20"] = _align((twii_cl / twii_ma20 - 1), shift_n=0)

    tsmc_cl = _fetch_yf("2330.TW", start_ext, end_ext)
    ext["tsmc_ret"] = _align(tsmc_cl.pct_change(), shift_n=0)

    # 0050 from DB (already refreshed daily)
    _et50_s: pd.Series = pd.Series(dtype=float)  # shared with macro proxy block
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        et50 = con.execute(
            "SELECT dt, close FROM ohlcv WHERE ticker='0050.TW' AND dt BETWEEN ? AND ? ORDER BY dt",
            [start_ext, end_ext],
        ).fetchdf()
        con.close()
        et50_s = et50.set_index("dt")["close"]
        et50_s.index = pd.to_datetime(et50_s.index)
        _et50_s = et50_s
        ext["eti0050_ret"] = _align(et50_s.pct_change(), shift_n=0)
        ext["eti0050_5d_ret"] = _align(et50_s.pct_change(5), shift_n=0)
        # Bollinger Band %B: 0050 price position within 20-day band (0=lower, 1=upper)
        _et50_ma20 = et50_s.rolling(20).mean()
        _et50_std20 = et50_s.rolling(20).std()
        _bb_upper = _et50_ma20 + 2 * _et50_std20
        _bb_lower = _et50_ma20 - 2 * _et50_std20
        _bb_range = (_bb_upper - _bb_lower).clip(lower=1e-10)
        ext["eti0050_bb_pct"] = _align((et50_s - _bb_lower) / _bb_range, shift_n=0)
        ext["eti0050_bb_width"] = _align((2 * _et50_std20) / _et50_ma20, shift_n=0)
        if not tsmc_cl.empty:
            tsmc_5d = tsmc_cl.pct_change(5).reindex(idx, method="ffill")
            et50_5d = et50_s.pct_change(5).reindex(idx, method="ffill")
            ext["tsmc_vs_0050_5d"] = (tsmc_5d - et50_5d).values
    except Exception as e:
        print(f"  [ExtFeat] 0050/TSMC: {e}")

    # ── 長週期總體代理 (60d/120d) ────────────────────────────────────────
    try:
        twii_ma60  = twii_cl.rolling(60).mean()
        twii_ma120 = twii_cl.rolling(120).mean()
        ext["twii_60d_ret"]  = _align(twii_cl.pct_change(60),  shift_n=0)
        ext["twii_120d_ret"] = _align(twii_cl.pct_change(120), shift_n=0)
        ext["twii_vs_ma60"]  = _align(twii_cl / twii_ma60 - 1, shift_n=0)
        ext["twii_vs_ma120"] = _align(twii_cl / twii_ma120 - 1, shift_n=0)

        soxx_cl = _fetch_yf("SOXX", start_ext, end_ext)
        ext["us_soxx_60d_ret"] = _align(soxx_cl.pct_change(60), shift_n=1)

        ewt_cl = _fetch_yf("EWT", start_ext, end_ext)
        if not ewt_cl.empty and not _et50_s.empty:
            ewt_60d  = ewt_cl.pct_change(60).reindex(idx, method="ffill")
            et50_60d = _et50_s.pct_change(60).reindex(idx, method="ffill")
            ext["ewt_vs_0050_60d"] = (ewt_60d - et50_60d).values

        if not soxx_cl.empty:
            soxx_60d   = soxx_cl.pct_change(60).reindex(idx, method="ffill").shift(1)
            twii_60d_s = twii_cl.pct_change(60).reindex(idx, method="ffill")
            ext["soxx_vs_twii_60d"] = (soxx_60d - twii_60d_s).values
    except Exception as e:
        print(f"  [ExtFeat] macro proxies: {e}")

    # ── DB-based features ───────────────────────────────────────────────
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        close_scale = main_df["close"].reindex(idx, method="ffill") * 1e6

        # 外資買賣超 (shift=1)
        inst = con.execute(
            "SELECT dt, foreign_net_buy, institutional_total_net_buy FROM institutional_data "
            "WHERE ticker='00631L.TW' AND dt BETWEEN ? AND ? ORDER BY dt",
            [start_ext, end_ext],
        ).fetchdf()
        if not inst.empty:
            inst = inst.set_index("dt")
            inst.index = pd.to_datetime(inst.index)
            ig = inst.reindex(idx, method="ffill").shift(1)
            ext["inst_foreign_net"] = ig["foreign_net_buy"].values / close_scale.values
            ext["inst_total_net"] = ig["institutional_total_net_buy"].values / close_scale.values
            foreign_ma5 = inst["foreign_net_buy"].reindex(idx, method="ffill").rolling(5).mean().shift(1)
            ext["inst_foreign_ma5"] = foreign_ma5.values / close_scale.values

        # 融資融券 (shift=1)
        margin = con.execute(
            "SELECT dt, margin_balance, margin_prev_balance, short_balance, short_prev_balance "
            "FROM margin_data WHERE ticker='00631L.TW' AND dt BETWEEN ? AND ? ORDER BY dt",
            [start_ext, end_ext],
        ).fetchdf()
        if not margin.empty:
            margin = margin.set_index("dt")
            margin.index = pd.to_datetime(margin.index)
            mg = margin.reindex(idx, method="ffill").shift(1)
            ext["margin_chg_pct"] = (
                (mg["margin_balance"] - mg["margin_prev_balance"])
                / mg["margin_prev_balance"].clip(lower=1)
            ).values
            ext["short_chg_pct"] = (
                (mg["short_balance"] - mg["short_prev_balance"])
                / mg["short_prev_balance"].clip(lower=1)
            ).values
            ext["margin_short_log"] = np.log1p(
                mg["margin_balance"] / mg["short_balance"].clip(lower=1)
            ).values

        # 台指期夜盤 (shift=1, previous available after-hours session)
        # Use front-month contract only (contract_month is 6-digit like 202606, no '/')
        fn = con.execute(
            "SELECT dt, pct_change FROM taifex_futures_daily "
            "WHERE contract='TX' AND trading_session='盤後' "
            "AND contract_month NOT LIKE '%/%' "
            "AND dt BETWEEN ? AND ? "
            "QUALIFY ROW_NUMBER() OVER (PARTITION BY dt ORDER BY contract_month ASC) = 1 "
            "ORDER BY dt",
            [start_ext, end_ext],
        ).fetchdf()
        if not fn.empty:
            fn = fn.set_index("dt")
            fn.index = pd.to_datetime(fn.index)
            ext["tx_night_ret"] = fn["pct_change"].reindex(idx, method="ffill").shift(1).values

        # TXO 選擇權法人未平倉 (shift=1, published after market close)
        # 外資 PUT 淨多頭 > 0 = 買保護 = 看空；外資 CALL 淨空頭 < 0 = 賣權 = 看空
        txo = con.execute(
            "SELECT dt, put_call, institutional_investors, net_open_interest_balance_volume "
            "FROM derivative_institutional_data "
            "WHERE product_id='TXO' AND dt BETWEEN ? AND ? "
            "ORDER BY dt",
            [start_ext, end_ext],
        ).fetchdf()
        if not txo.empty:
            txo["dt"] = pd.to_datetime(txo["dt"])
            # Pivot to get per-institution per-type daily columns
            txo_piv = txo.pivot_table(
                index="dt",
                columns=["institutional_investors", "put_call"],
                values="net_open_interest_balance_volume",
                aggfunc="sum",
            )
            # 外資 PUT / CALL
            foreign_put = txo_piv.get(("外資", "賣權"), pd.Series(dtype=float, name="fp"))
            foreign_call = txo_piv.get(("外資", "買權"), pd.Series(dtype=float, name="fc"))
            # 三大法人合計 PUT / CALL
            all_put = txo_piv.xs("賣權", axis=1, level=1).sum(axis=1) if "賣權" in txo_piv.columns.get_level_values(1) else pd.Series(dtype=float)
            all_call = txo_piv.xs("買權", axis=1, level=1).sum(axis=1) if "買權" in txo_piv.columns.get_level_values(1) else pd.Series(dtype=float)

            def _shift1(s):
                return s.reindex(idx, method="ffill").shift(1)

            foreign_put_s = _shift1(foreign_put)
            foreign_call_s = _shift1(foreign_call)
            ext["txo_foreign_put_oi"] = foreign_put_s.values
            ext["txo_foreign_call_oi"] = foreign_call_s.values
            ext["txo_foreign_pc_spread"] = (foreign_put_s - foreign_call_s).values
            ext["txo_foreign_pc_spread_ma5"] = (
                (foreign_put_s - foreign_call_s).rolling(5, min_periods=1).mean().values
            )
            # Total P/C ratio: positive = more put protection = bearish pressure
            all_put_s = _shift1(all_put)
            all_call_s = _shift1(all_call)
            total_pcr = all_put_s / (all_call_s.abs().clip(lower=1.0))
            ext["txo_total_pcr"] = total_pcr.values

        con.close()
    except Exception as e:
        print(f"  [ExtFeat] DB features: {e}")

    # ── TXO 全市場 PCR (shift=1, from taifex_options_data) ──────────────
    _skip_txo_mkt = os.environ.get("NCF_SKIP_TXO_MARKET_PCR", "").lower() in {"1", "true", "yes"}
    try:
        if _skip_txo_mkt:
            raise RuntimeError("NCF_SKIP_TXO_MARKET_PCR=1, skipping")
        sys.path.insert(0, str(PROJECT_ROOT))
        from taifex_options_data import query_txo_features
        txo_mkt = query_txo_features(start_ext, end_ext)
        if not txo_mkt.empty:
            txo_mkt["dt"] = pd.to_datetime(txo_mkt["dt"])
            txo_mkt = txo_mkt.set_index("dt")
            for col in (
                "txo_pcr_volume",
                "txo_pcr_oi",
                "txo_pcr_volume_5d_zscore",
                "txo_pcr_oi_5d_zscore",
                "txo_pcr_volume_20d_zscore",
            ):
                ext_name = col.replace("txo_pcr_", "txo_market_pcr_")
                if col in txo_mkt.columns:
                    s = txo_mkt[col].reindex(idx, method="ffill").shift(1)
                    ext[ext_name] = s.values
    except Exception as e:
        print(f"  [ExtFeat] TXO market PCR: {e}")

    # ── Global correlated assets (enabled by --global-features, opt-in) ──
    # Populated in main() after arg parsing; skip if not requested.
    # Placeholder: add_global_features() is called from main() if use_global_features.

    n_valid = ext.notna().sum()
    n_full = (n_valid == len(idx)).sum()
    print(f"  [ExtFeat] Loaded {len(ext.columns)} features  "
          f"({n_full} fully covered, {(n_valid < len(idx)).sum()} with NaN gaps)")
    return ext


def _rolling_mdd(x: pd.Series) -> float:
    cummax = x.cummax()
    return float(((x - cummax) / cummax).min())


def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build all FEATURES from raw OHLCV data."""
    df = df.copy()

    # Moving averages
    for w in [5, 10, 20, 30, 50, 60, 120, 200, 240]:
        df[f"ma{w}"] = df["close"].rolling(w).mean()

    # Price/MA ratios
    for w in [5, 10, 20, 30, 60, 120, 200, 240]:
        df[f"close_ma{w}_ratio"] = df["close"] / df[f"ma{w}"]
    df["ma5_ma10_ratio"] = df["ma5"] / df["ma10"]
    df["ma5_ma20_ratio"] = df["ma5"] / df["ma20"]
    df["ma20_ma60_ratio"] = df["ma20"] / df["ma60"]
    df["ma60_ma200_ratio"] = df["ma60"] / df["ma200"]

    # Returns (scale-invariant targets)
    for w in [1, 2, 3, 5, 10, 21]:
        df[f"return_{w}d"] = df["close"].pct_change(w)

    # Momentum (ratio-based)
    for w in [3, 5, 10, 21, 63]:
        df[f"momentum_{w}"] = df["close"] / df["close"].shift(w) - 1

    # Volatility
    for w in [5, 20, 60]:
        df[f"volatility_{w}"] = df["close"].pct_change().rolling(w).std()

    # Rolling max drawdown
    df["rolling_mdd_20"] = df["close"].rolling(20).apply(_rolling_mdd, raw=False)
    df["rolling_mdd_60"] = df["close"].rolling(60).apply(_rolling_mdd, raw=False)

    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain14 = gain.rolling(14).mean()
    avg_loss14 = loss.rolling(14).mean()
    rs14 = avg_gain14 / avg_loss14.clip(lower=1e-10)
    df["rsi_14"] = 100 - (100 / (1 + rs14))
    avg_gain7 = gain.rolling(7).mean()
    avg_loss7 = loss.rolling(7).mean()
    rs7 = avg_gain7 / avg_loss7.clip(lower=1e-10)
    df["rsi_7"] = 100 - (100 / (1 + rs7))
    avg_gain28 = gain.rolling(28).mean()
    avg_loss28 = loss.rolling(28).mean()
    rs28 = avg_gain28 / avg_loss28.clip(lower=1e-10)
    df["rsi_28"] = 100 - (100 / (1 + rs28))

    # Consecutive up/down day streaks (max 10)
    _daily_ret = df["close"].pct_change()
    _up = (_daily_ret > 0).astype(float).fillna(0)
    _dn = (_daily_ret <= 0).astype(float).fillna(0)
    _up_arr, _dn_arr = _up.to_numpy(), _dn.to_numpy()
    _up_streak, _dn_streak = np.zeros(len(_up_arr)), np.zeros(len(_dn_arr))
    _cu, _cd = 0, 0
    for _i, (_u, _d) in enumerate(zip(_up_arr, _dn_arr)):
        _cu = int((_cu + 1) * _u)
        _cd = int((_cd + 1) * _d)
        _up_streak[_i] = min(_cu, 10)
        _dn_streak[_i] = min(_cd, 10)
    df["consecutive_up_days"] = pd.Series(_up_streak, index=df.index)
    df["consecutive_down_days"] = pd.Series(_dn_streak, index=df.index)

    # MACD
    emac = df["close"].ewm(span=12).mean()
    emas = df["close"].ewm(span=26).mean()
    macd_val = emac - emas
    df["macd_signal"] = macd_val.ewm(span=9).mean()
    df["macd_diff"] = macd_val - df["macd_signal"]

    # ADX
    high, low, close_s = df["high"], df["low"], df["close"]
    tr = pd.concat(
        [high - low, (high - close_s.shift(1)).abs(), (low - close_s.shift(1)).abs()],
        axis=1
    ).max(axis=1)
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_di = 100 * plus_dm.rolling(14).mean() / tr.rolling(14).mean()
    minus_di = 100 * minus_dm.rolling(14).mean() / tr.rolling(14).mean()
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["adx_14"] = dx.rolling(14).mean()

    # ATR normalized
    df["atr_14_normalized"] = tr.rolling(14).mean() / df["close"]

    # Bollinger Bands
    ma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    df["bb_position"] = (df["close"] - ma20) / (2 * std20)
    df["bb_width"] = (2 * std20) / ma20

    # Volume ratios
    df["volume_ratio_20"] = df["volume"] / df["volume"].rolling(20).mean()
    df["volume_ratio_5"] = df["volume"] / df["volume"].rolling(5).mean()

    # Regime flags
    df["above_ma200"] = (df["close"] > df["ma200"]).astype(float)
    df["above_ma50"] = (df["close"] > df["ma50"]).astype(float)
    df["above_ma20"] = (df["close"] > df["ma20"]).astype(float)
    df["close_ma200_dist"] = (df["close"] - df["ma200"]) / df["ma200"]
    df["close_ma50_dist"] = (df["close"] - df["ma50"]) / df["ma50"]

    # === NEW: Gap and intraday pattern features ===
    # Gap: today's open vs yesterday's close
    df["gap"] = (df["open"] - df["close"].shift(1)) / df["close"].shift(1)

    # Intraday pattern: close vs open (who controls the day)
    df["close_open_ratio"] = df["close"] / df["open"]

    # Candle composition
    body = (df["close"] - df["open"]).abs()
    upper_shadow = df["high"] - df[["open", "close"]].max(axis=1)
    lower_shadow = df[["open", "close"]].min(axis=1) - df["low"]
    full_range = df["high"] - df["low"]
    df["upper_shadow_pct"] = upper_shadow / full_range.clip(lower=1e-10)
    df["lower_shadow_pct"] = lower_shadow / full_range.clip(lower=1e-10)
    df["body_pct"] = body / full_range.clip(lower=1e-10)

    df = add_fourier_features(df)
    return add_tbrain_features(df)


def _add_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add current-date interaction features after optional external merge."""
    if {"volatility_20", "bb_width"} <= set(df.columns):
        df["vol20_x_bb_width"] = df["volatility_20"] * df["bb_width"]
    if {"volatility_20", "close_ma200_dist"} <= set(df.columns):
        df["vol20_x_close_ma200_dist"] = df["volatility_20"] * df["close_ma200_dist"]
    if {"momentum_21", "above_ma200"} <= set(df.columns):
        df["momentum21_x_above_ma200"] = df["momentum_21"] * df["above_ma200"]
    if {"return_5d", "volatility_20"} <= set(df.columns):
        df["return5_x_vol20"] = df["return_5d"] * df["volatility_20"]
    if {"rsi_14", "close_ma50_dist"} <= set(df.columns):
        df["rsi14_x_close_ma50_dist"] = (df["rsi_14"] / 100.0) * df["close_ma50_dist"]
    if {"vix_ma20_ratio", "volatility_20"} <= set(df.columns):
        df["vix_spike_x_vol20"] = (df["vix_ma20_ratio"] - 1.0) * df["volatility_20"]
    if {"vix_change", "return_1d"} <= set(df.columns):
        df["vix_change_x_return1d"] = df["vix_change"] * df["return_1d"]
    if {"us_qqq_5d_ret", "momentum_21"} <= set(df.columns):
        df["qqq5d_x_momentum21"] = df["us_qqq_5d_ret"] * df["momentum_21"]
    if {"twii_5d_ret", "close_ma200_dist"} <= set(df.columns):
        df["twii5d_x_close_ma200_dist"] = df["twii_5d_ret"] * df["close_ma200_dist"]
    if {"twii_ret", "return_1d"} <= set(df.columns):
        df["twii_ret_x_return1d"] = df["twii_ret"] * df["return_1d"]
    if {"tsmc_vs_0050_5d", "momentum_5"} <= set(df.columns):
        df["tsmc0050spread_x_momentum5"] = df["tsmc_vs_0050_5d"] * df["momentum_5"]
    if {"usdtwd_change", "vix_change"} <= set(df.columns):
        df["usdtwd_x_vix_change"] = df["usdtwd_change"] * df["vix_change"]
    if {"tx_night_ret", "gap"} <= set(df.columns):
        df["tx_night_x_gap"] = df["tx_night_ret"] * df["gap"]
    if {"inst_foreign_net", "margin_chg_pct"} <= set(df.columns):
        df["foreign_x_margin_chg"] = df["inst_foreign_net"] * df["margin_chg_pct"]
    if {"inst_total_net", "short_chg_pct"} <= set(df.columns):
        df["inst_total_x_short_chg"] = df["inst_total_net"] * df["short_chg_pct"]
    if {"margin_short_log", "rsi_14"} <= set(df.columns):
        df["margin_short_x_rsi14"] = df["margin_short_log"] * (df["rsi_14"] / 100.0)
    # TXO Put/Call OI interactions
    if {"txo_total_pcr", "close_ma200_dist"} <= set(df.columns):
        # 高P/C × 晚期多頭：P/C>1時才強調，否則置零
        df["txo_pcr_x_ma_gap"] = df["txo_total_pcr"].clip(lower=0) * df["close_ma200_dist"].clip(lower=0)
    if {"txo_foreign_pc_spread", "vix"} <= set(df.columns):
        df["txo_foreign_pc_x_vix"] = df["txo_foreign_pc_spread"] * df["vix"]
    if {"txo_foreign_pc_spread", "inst_foreign_net"} <= set(df.columns):
        df["txo_foreign_pc_x_inst_net"] = df["txo_foreign_pc_spread"] * df["inst_foreign_net"]
    if {"txo_market_pcr_volume", "vix_ma20_ratio"} <= set(df.columns):
        df["txo_mkt_pcr_x_vix"] = df["txo_market_pcr_volume"] * df["vix_ma20_ratio"]
    if {"txo_market_pcr_volume", "inst_foreign_net"} <= set(df.columns):
        df["txo_mkt_pcr_x_inst_net"] = df["txo_market_pcr_volume"] * df["inst_foreign_net"]
    # 0050 BB overbought × VIX spike: 1 when 0050 near upper band AND VIX elevated
    if {"eti0050_bb_pct", "vix_ma20_ratio"} <= set(df.columns):
        df["bb0050_x_vix"] = df["eti0050_bb_pct"] * (df["vix_ma20_ratio"] - 1.0)
    return df


def triple_barrier_label(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    t_max: int,
    tp_mult: float = 1.0,
    sl_mult: float = 1.0,
    atr_window: int = 14,
) -> pd.Series:
    """Triple Barrier Labeling (López de Prado, 2018).

    For each bar i:
      TP = close[i] + tp_mult × ATR14[i],  SL = close[i] − sl_mult × ATR14[i]
      Scan bars i+1 … i+t_max:
        label=1  if TP barrier hit first (UP)
        label=0  if SL barrier hit first (DOWN)
        label=-1 if timeout without hitting either (NEUTRAL)

    Same-bar simultaneous hit → tiebreak by close vs entry close.
    Last t_max rows default to -1 (incomplete forward window).
    """
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_window).mean()

    close_arr = close.to_numpy()
    high_arr  = high.to_numpy()
    low_arr   = low.to_numpy()
    atr_arr   = atr.to_numpy()
    n = len(close_arr)
    labels = np.full(n, -1, dtype=np.int8)

    for i in range(n - 1):
        if np.isnan(atr_arr[i]) or np.isnan(close_arr[i]):
            continue
        tp = close_arr[i] + tp_mult * atr_arr[i]
        sl = close_arr[i] - sl_mult * atr_arr[i]

        for j in range(i + 1, min(i + t_max + 1, n)):
            hit_tp = high_arr[j] >= tp
            hit_sl = low_arr[j] <= sl
            if hit_tp and hit_sl:
                labels[i] = 1 if close_arr[j] >= close_arr[i] else 0
                break
            elif hit_tp:
                labels[i] = 1
                break
            elif hit_sl:
                labels[i] = 0
                break

    return pd.Series(labels.astype(int), index=close.index)


def load_data(db_path: Path, ticker: str, start: str, end: str) -> pd.DataFrame:
    """Load OHLCV from DuckDB, set DatetimeIndex."""
    con = duckdb.connect(str(db_path), read_only=True)
    rows = con.execute(
        """
        SELECT dt, open, high, low, close, volume
        FROM ohlcv
        WHERE ticker = ? AND dt BETWEEN ? AND ?
        ORDER BY dt
        """,
        [ticker, start, end],
    ).fetchdf()
    con.close()
    rows["date"] = pd.to_datetime(rows["dt"])
    rows = rows.set_index("date").sort_index()
    rows = rows[["open", "high", "low", "close", "volume"]]
    rows = rows.astype(float)
    return rows


def resolve_end_date(db_path: Path, ticker: str, requested_end: str) -> str:
    """Resolve 'latest' to the newest available OHLCV date for this ticker.

    2026-07-12 fix: a non-trading day (market holiday, or a ticker-specific
    trading halt) can leave a spurious `ohlcv` row behind -- prior close
    carried forward, volume=0 -- instead of the date being skipped. Since
    this function only ever runs for the "latest" (live) case, excluding
    volume=0 rows here is always correct: no historical backtest depends on
    this path, only same-day/live panel generation does. See
    GROUP_A_PLUS_A2118_CHIP_DATA_CORE_CLOCK_AUDIT_HANDOFF_20260712.md for
    the same bug found and fixed in run_a2118()'s live signal generation.
    """
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    max_dt = con.execute(
        "SELECT MAX(dt) FROM ohlcv WHERE ticker = ? AND volume > 0",
        [ticker],
    ).fetchone()[0]
    con.close()
    if max_dt is None:
        raise ValueError(f"No OHLCV rows found for {ticker}")
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def build_dataset(
    df: pd.DataFrame,
    horizon: int = 1,
    ext_df: pd.DataFrame | None = None,
    direction_threshold: float = 0.0,
    labeling: str = "simple",
    tbl_mult: float = 0.75,
) -> tuple[pd.DataFrame, pd.Series, pd.Series, list[str]]:
    """Build feature matrix and targets (return + direction) for given horizon.

    ext_df: pre-loaded external features from load_external_df(), or None.
    direction_threshold: (simple mode) rows where |fwd_return| <= threshold → NEUTRAL (-1).
    labeling: 'simple' (return sign / threshold) or 'triple_barrier' (ATR barriers).
    tbl_mult: ATR multiplier for Triple Barrier TP/SL barriers.
    """
    feat_df = _build_features(df)

    # Merge external features if provided
    if ext_df is not None:
        for col in ext_df.columns:
            feat_df[col] = ext_df[col].reindex(feat_df.index)
    feat_df = _add_interaction_features(feat_df)

    # Return target: return over `horizon` days, shifted to avoid look-ahead
    feat_df["target_return"] = feat_df["close"].pct_change(horizon).shift(-horizon)

    # Direction target: 1=UP, 0=DOWN, -1=NEUTRAL
    if labeling == "triple_barrier":
        tbl = triple_barrier_label(
            feat_df["close"], feat_df["high"], feat_df["low"],
            t_max=horizon, tp_mult=tbl_mult, sl_mult=tbl_mult,
        )
        feat_df["target_direction"] = tbl.reindex(feat_df.index)
    elif direction_threshold > 0:
        feat_df["target_direction"] = np.where(
            feat_df["target_return"] >  direction_threshold, 1,
            np.where(feat_df["target_return"] < -direction_threshold, 0, -1)
        )
    else:
        feat_df["target_direction"] = (feat_df["target_return"] > 0).astype(int)
    feat_df = feat_df.dropna(subset=["target_return"])

    all_features = FEATURES + INTERACTION_FEATURES + (EXT_FEATURES if ext_df is not None else [])
    available = [f for f in all_features if f in feat_df.columns]
    X = feat_df[available]
    # Drop rows where base FEATURES have NaN; allow ext features to forward-fill later
    base_available = [f for f in FEATURES if f in X.columns]
    X = X.dropna(subset=base_available)
    # Fill remaining NaN in ext features with 0 (neutral signal when data unavailable)
    if ext_df is not None:
        ext_cols = [f for f in EXT_FEATURES if f in X.columns]
        X[ext_cols] = X[ext_cols].fillna(0.0)
    interaction_cols = [f for f in INTERACTION_FEATURES if f in X.columns]
    X[interaction_cols] = X[interaction_cols].fillna(0.0)
    y_return = feat_df.loc[X.index, "target_return"]
    y_direction = feat_df.loc[X.index, "target_direction"]
    return X, y_return, y_direction, available


def forward_max_drawdown_label(
    close: pd.Series,
    horizon: int = 20,
    threshold: float = 0.05,
) -> tuple[pd.Series, pd.Series]:
    """Label whether the next `horizon` trading days suffer drawdown worse than threshold."""
    future = pd.concat([close.shift(-i) for i in range(1, horizon + 1)], axis=1)
    future_min = future.min(axis=1)
    forward_mdd = (future_min / close - 1.0).rename(f"forward_mdd_{horizon}d")
    label = (forward_mdd <= -abs(threshold)).astype(float).rename(f"target_fwd_mdd_gt{int(threshold * 100)}_h{horizon}")
    label[future_min.isna()] = np.nan
    return forward_mdd, label


def forward_max_gain_label(
    close: pd.Series,
    horizon: int = 20,
    threshold: float = 0.05,
) -> tuple[pd.Series, pd.Series]:
    """Label whether the next `horizon` trading days rally more than threshold."""
    future = pd.concat([close.shift(-i) for i in range(1, horizon + 1)], axis=1)
    future_max = future.max(axis=1)
    forward_gain = (future_max / close - 1.0).rename(f"forward_gain_{horizon}d")
    label = (forward_gain >= abs(threshold)).astype(float).rename(f"target_fwd_gain_gt{int(threshold * 100)}_h{horizon}")
    label[future_max.isna()] = np.nan
    return forward_gain, label


def build_feature_matrix(df: pd.DataFrame, ext_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build the current feature matrix without adding prediction targets."""
    feat_df = _build_features(df)
    if ext_df is not None:
        for col in ext_df.columns:
            feat_df[col] = ext_df[col].reindex(feat_df.index)
    feat_df = _add_interaction_features(feat_df)
    all_features = FEATURES + INTERACTION_FEATURES + (EXT_FEATURES if ext_df is not None else [])
    available = [f for f in all_features if f in feat_df.columns]
    X = feat_df[available]
    base_available = [f for f in FEATURES if f in X.columns]
    X = X.dropna(subset=base_available)
    if ext_df is not None:
        ext_cols = [f for f in EXT_FEATURES if f in X.columns]
        X[ext_cols] = X[ext_cols].fillna(0.0)
    interaction_cols = [f for f in INTERACTION_FEATURES if f in X.columns]
    X[interaction_cols] = X[interaction_cols].fillna(0.0)
    return X


def train_forward_drawdown_risk(
    df: pd.DataFrame,
    ext_df: pd.DataFrame | None,
    val_start: str,
    do_feature_selection: bool = False,
    horizon: int = 20,
    threshold: float = 0.05,
    expanding_model_weights: bool = False,
) -> dict:
    """Train an additive classifier for P(next-H max drawdown worse than threshold)."""
    X = build_feature_matrix(df, ext_df)
    forward_mdd, y_risk = forward_max_drawdown_label(df["close"], horizon=horizon, threshold=threshold)
    common_idx = X.index.intersection(y_risk.dropna().index)
    X_model = X.loc[common_idx]
    y_model = y_risk.loc[common_idx].astype(int)
    train_mask = X_model.index < val_start
    X_train, X_val = X_model[train_mask], X_model[~train_mask]
    y_train, y_val = y_model[train_mask], y_model[~train_mask]
    if len(X_train) < 100 or len(X_val) < 20 or y_train.nunique() < 2 or y_val.nunique() < 2:
        return {
            "available": False,
            "reason": "insufficient_rows_or_single_class",
            "train_rows": int(len(X_train)),
            "val_rows": int(len(X_val)),
            "train_positive_rate": float(y_train.mean()) if len(y_train) else None,
            "val_positive_rate": float(y_val.mean()) if len(y_val) else None,
        }

    clf = train_classifier(
        X_train,
        y_train,
        X_val,
        y_val,
        do_feature_selection=do_feature_selection,
        horizon=horizon,
        expanding_model_weights=expanding_model_weights,
    )
    last_row = X.iloc[-1:]
    W_inf = clf["ensemble"]["weights"]
    model_probas = {}
    for nm, mdl in clf["_models"].items():
        nm_feats = clf[nm]["features"]
        model_probas[nm] = float(mdl.predict_proba(last_row[nm_feats])[0][1])
    latest_proba = float(sum(W_inf[nm] * model_probas[nm] for nm in W_inf))
    val_proba = pd.Series(clf["ensemble"]["proba"], index=X_val.index, name=f"prob_fwd_mdd_gt{int(threshold * 100)}_h{horizon}")
    return {
        "available": True,
        "horizon_days": horizon,
        "threshold": threshold,
        "probability": latest_proba,
        "direction": "RISK_ON" if latest_proba >= 0.5 else "RISK_OFF",
        "confidence": abs(latest_proba - 0.5) * 2.0,
        "auc": float(clf["ensemble"]["auc"]),
        "brier": float(clf["ensemble"]["brier"]),
        "train_rows": int(len(X_train)),
        "val_rows": int(len(X_val)),
        "train_positive_rate": float(y_train.mean()),
        "val_positive_rate": float(y_val.mean()),
        "model_probas": model_probas,
        "model_weights": {k: float(v) for k, v in W_inf.items()},
        "val_proba": val_proba,
        "val_label": y_val.rename(f"actual_fwd_mdd_gt{int(threshold * 100)}_h{horizon}"),
        "val_forward_mdd": forward_mdd.reindex(X_val.index),
    }


def train_forward_upside_reward(
    df: pd.DataFrame,
    ext_df: pd.DataFrame | None,
    val_start: str,
    do_feature_selection: bool = False,
    horizon: int = 20,
    threshold: float = 0.05,
    expanding_model_weights: bool = False,
) -> dict:
    """Train an additive classifier for P(next-H max gain exceeds threshold)."""
    X = build_feature_matrix(df, ext_df)
    forward_gain, y_reward = forward_max_gain_label(df["close"], horizon=horizon, threshold=threshold)
    common_idx = X.index.intersection(y_reward.dropna().index)
    X_model = X.loc[common_idx]
    y_model = y_reward.loc[common_idx].astype(int)
    train_mask = X_model.index < val_start
    X_train, X_val = X_model[train_mask], X_model[~train_mask]
    y_train, y_val = y_model[train_mask], y_model[~train_mask]
    if len(X_train) < 100 or len(X_val) < 20 or y_train.nunique() < 2 or y_val.nunique() < 2:
        return {
            "available": False,
            "reason": "insufficient_rows_or_single_class",
            "train_rows": int(len(X_train)),
            "val_rows": int(len(X_val)),
            "train_positive_rate": float(y_train.mean()) if len(y_train) else None,
            "val_positive_rate": float(y_val.mean()) if len(y_val) else None,
        }

    clf = train_classifier(
        X_train,
        y_train,
        X_val,
        y_val,
        do_feature_selection=do_feature_selection,
        horizon=horizon,
        expanding_model_weights=expanding_model_weights,
    )
    last_row = X.iloc[-1:]
    W_inf = clf["ensemble"]["weights"]
    model_probas = {}
    for nm, mdl in clf["_models"].items():
        nm_feats = clf[nm]["features"]
        model_probas[nm] = float(mdl.predict_proba(last_row[nm_feats])[0][1])
    latest_proba = float(sum(W_inf[nm] * model_probas[nm] for nm in W_inf))
    val_proba = pd.Series(clf["ensemble"]["proba"], index=X_val.index, name=f"prob_fwd_gain_gt{int(threshold * 100)}_h{horizon}")
    return {
        "available": True,
        "horizon_days": horizon,
        "threshold": threshold,
        "probability": latest_proba,
        "direction": "REWARD_ON" if latest_proba >= 0.5 else "REWARD_OFF",
        "confidence": abs(latest_proba - 0.5) * 2.0,
        "auc": float(clf["ensemble"]["auc"]),
        "brier": float(clf["ensemble"]["brier"]),
        "train_rows": int(len(X_train)),
        "val_rows": int(len(X_val)),
        "train_positive_rate": float(y_train.mean()),
        "val_positive_rate": float(y_val.mean()),
        "model_probas": model_probas,
        "model_weights": {k: float(v) for k, v in W_inf.items()},
        "val_proba": val_proba,
        "val_label": y_val.rename(f"actual_fwd_gain_gt{int(threshold * 100)}_h{horizon}"),
        "val_forward_gain": forward_gain.reindex(X_val.index),
    }


def reconcile_latest_panel_row(panel_path: Path, payload: dict) -> dict:
    """Align the panel's latest live row with the JSON horizon payload."""
    if not panel_path.exists():
        return {"status": "missing_panel", "path": str(panel_path)}
    try:
        panel_df = pd.read_csv(panel_path)
    except Exception as exc:
        return {"status": "read_error", "path": str(panel_path), "reason": str(exc)}
    if "date" not in panel_df.columns:
        return {"status": "missing_date_column", "path": str(panel_path)}

    last_date = str(payload.get("last_close_date"))
    mask = panel_df["date"].astype(str) == last_date
    if not mask.any():
        return {"status": "missing_latest_row", "path": str(panel_path), "date": last_date}

    row_idx = panel_df.index[mask][-1]
    horizons = payload.get("horizons", {})
    updated: dict[str, float | str] = {}
    for h in ("1", "5", "20"):
        prob = (
            horizons.get(h, {})
            .get("classification", {})
            .get("probability_up")
        )
        if prob is None:
            continue
        col = f"prob_up_h{h}"
        if col in panel_df.columns:
            panel_df.loc[row_idx, col] = float(prob)
            updated[col] = float(prob)
        if h == "20":
            if "h20_prob_up" in panel_df.columns:
                panel_df.loc[row_idx, "h20_prob_up"] = float(prob)
                updated["h20_prob_up"] = float(prob)
            if "h20_direction" in panel_df.columns:
                direction = "UP" if float(prob) > 0.5 else "DOWN"
                panel_df.loc[row_idx, "h20_direction"] = direction
                updated["h20_direction"] = direction

    ensemble = payload.get("horizon_ensemble", {})
    # H2 (2026-07-02 Fable 5 audit, Option A): use the panel-aligned values
    # (computed with the same expanding-window AUC weighting as the panel
    # itself) rather than `combined_probability_up`, which uses a different,
    # fixed-per-horizon-AUC weighting scheme -- reconciling with that value
    # was overwriting the panel's own consistent computation with a number
    # from a different formula, and `confidence` used to be overwritten with
    # the JSON's composite consensus/magnitude/spread blend (a different
    # scale entirely from every other row's `prob_magnitude`-equal
    # `confidence` value in this column).
    ensemble_prob_up_aligned = ensemble.get("ensemble_prob_up_panel_aligned")
    prob_magnitude_aligned = ensemble.get("prob_magnitude_panel_aligned")
    if ensemble_prob_up_aligned is not None and "ensemble_prob_up" in panel_df.columns:
        panel_df.loc[row_idx, "ensemble_prob_up"] = float(ensemble_prob_up_aligned)
        updated["ensemble_prob_up"] = float(ensemble_prob_up_aligned)
    if prob_magnitude_aligned is not None:
        if "prob_magnitude" in panel_df.columns:
            panel_df.loc[row_idx, "prob_magnitude"] = float(prob_magnitude_aligned)
            updated["prob_magnitude"] = float(prob_magnitude_aligned)
        if "confidence" in panel_df.columns:
            panel_df.loc[row_idx, "confidence"] = float(prob_magnitude_aligned)
            updated["confidence"] = float(prob_magnitude_aligned)
    direction = ensemble.get("direction")
    if direction is not None and "direction" in panel_df.columns:
        panel_df.loc[row_idx, "direction"] = str(direction)
        updated["direction"] = str(direction)

    panel_df.to_csv(panel_path, index=False, encoding="utf-8-sig")
    return {
        "status": "updated",
        "path": str(panel_path),
        "date": last_date,
        "updated": updated,
    }


def _build_expanding_horizon_ensemble_panel(
    probs_by_horizon: dict[int, pd.Series],
    labels_by_horizon: dict[int, pd.Series] | None = None,
    *,
    min_history: int = 60,
) -> pd.DataFrame:
    """Build horizon ensemble rows using only labels before each row."""
    horizons = sorted(probs_by_horizon)
    if not horizons:
        return pd.DataFrame()

    common_idx = probs_by_horizon[horizons[0]].index
    for horizon in horizons[1:]:
        common_idx = common_idx.intersection(probs_by_horizon[horizon].index)
    common_idx = common_idx.sort_values()

    prob_df = pd.DataFrame(
        {f"prob_up_h{horizon}": probs_by_horizon[horizon].reindex(common_idx) for horizon in horizons},
        index=common_idx,
    )
    if labels_by_horizon:
        label_df = pd.DataFrame(
            {
                horizon: labels_by_horizon[horizon].reindex(common_idx)
                for horizon in horizons
                if horizon in labels_by_horizon and labels_by_horizon[horizon] is not None
            },
            index=common_idx,
        )
    else:
        label_df = pd.DataFrame(index=common_idx)

    equal_weights = {horizon: 1.0 / len(horizons) for horizon in horizons}
    weight_rows: list[dict[int, float]] = []
    ensemble_values: list[float] = []

    for pos, idx in enumerate(common_idx):
        raw_weights: dict[int, float] = {}
        for horizon in horizons:
            if horizon not in label_df:
                continue
            # M1 (2026-07-02 Fable 5 audit): label_df[horizon].iloc[i] is the
            # forward-looking label for row i (needs `horizon` days of future
            # price data to resolve), so as of `pos` only rows up to
            # `pos - horizon` are actually known -- the previous `iloc[:pos]`
            # included up to `horizon-1` days of unresolved forward labels
            # near the training frontier (up to 19 days for h=20).
            resolved_end = max(0, pos - horizon)
            hist_labels = label_df[horizon].iloc[:resolved_end]
            hist_probs = prob_df[f"prob_up_h{horizon}"].iloc[:resolved_end]
            valid = hist_labels.notna() & hist_probs.notna()
            if int(valid.sum()) < min_history or hist_labels[valid].nunique() < 2:
                continue
            auc = roc_auc_score(hist_labels[valid].astype(int), hist_probs[valid])
            raw_weights[horizon] = max(0.0, float(auc) - 0.5)

        total_weight = sum(raw_weights.values())
        if total_weight > 0:
            weights = {horizon: raw_weights.get(horizon, 0.0) / total_weight for horizon in horizons}
        else:
            weights = equal_weights

        row_probs = prob_df.loc[idx]
        ensemble_values.append(
            float(sum(weights[horizon] * row_probs[f"prob_up_h{horizon}"] for horizon in horizons))
        )
        weight_rows.append(weights)

    panel_df = prob_df.copy()
    panel_df["ensemble_prob_up"] = ensemble_values
    panel_df["direction"] = panel_df["ensemble_prob_up"].apply(lambda p: "UP" if p > 0.5 else "DOWN")
    panel_df["prob_magnitude"] = (panel_df["ensemble_prob_up"] - 0.5).abs() * 2
    for horizon in horizons:
        panel_df[f"ensemble_weight_h{horizon}"] = [weights[horizon] for weights in weight_rows]
    panel_df["horizon_ensemble_method"] = f"expanding_prior_auc_min{min_history}"
    return panel_df


def _expanding_model_ensemble_weights(
    probas_by_model: dict[str, np.ndarray],
    y_val_arr: np.ndarray,
    *,
    horizon: int | None = None,
    min_history: int = 150,
    full_confidence_history: int = 800,
) -> tuple[np.ndarray, list[dict[str, float]]]:
    """Per-row model-ensemble blend using only labels resolved before that row.

    Mirrors `_build_expanding_horizon_ensemble_panel`'s walk-forward AUC weighting,
    applied one level down (across base models within one horizon, instead of
    across horizons). Row `pos`'s weight uses only rows `[:pos - horizon]` --
    rows whose forward-looking label had actually resolved as of row `pos` --
    with the same `raw_w = auc_w * brier_w` shape as the current global weight
    formula, and the same equal-weight fallback before `min_history` resolved
    rows exist or before any model clears the Brier bar.

    2026-07-07 shrinkage note: with 7-8 base models (vs. 3 horizons in the
    sibling function above), a raw AUC/Brier weight computed on a small
    resolved sample can concentrate almost all weight onto whichever single
    model got lucky/unlucky on that small sample -- verified empirically to
    cause *larger*, not smaller, historical-row swings than the original
    global-weight bug for direction tasks that also split by bull/bear regime
    (shrinking the effective validation sample further). `full_confidence_history`
    linearly ramps from equal weights (at `min_history` resolved rows) to the
    full computed weight (at `full_confidence_history` resolved rows) instead
    of jumping straight to the raw weight the moment `min_history` is cleared,
    trading a slower ramp-up for materially more stable historical rows.
    """
    names = list(probas_by_model)
    n = len(y_val_arr)
    h = int(horizon) if horizon else 0
    equal_weights = {name: 1.0 / len(names) for name in names}
    ens = np.empty(n, dtype=float)
    weight_rows: list[dict[str, float]] = []
    ramp_span = max(1, full_confidence_history - min_history)

    for pos in range(n):
        resolved_end = max(0, pos - h)
        hist_y = y_val_arr[:resolved_end]
        weights = equal_weights
        if len(hist_y) >= min_history and len(np.unique(hist_y)) >= 2:
            p_base_hist = float(np.mean(hist_y))
            naive_brier_hist = p_base_hist * (1.0 - p_base_hist)
            auc_w: dict[str, float] = {}
            brier_w: dict[str, float] = {}
            for name in names:
                hist_p = probas_by_model[name][:resolved_end]
                auc_w[name] = max(0.0, roc_auc_score(hist_y, hist_p) - 0.5)
                brier_w[name] = max(0.0, naive_brier_hist - brier_score_loss(hist_y, hist_p))
            raw_w = {name: auc_w[name] * brier_w[name] for name in names}
            total_w = sum(raw_w.values())
            if total_w > 0:
                raw_weights = {name: raw_w[name] / total_w for name in names}
            else:
                total_auc_w = sum(auc_w.values())
                raw_weights = ({name: auc_w[name] / total_auc_w for name in names}
                               if total_auc_w > 0 else equal_weights)
            shrink = min(1.0, (len(hist_y) - min_history) / ramp_span)
            weights = {
                name: shrink * raw_weights[name] + (1.0 - shrink) * equal_weights[name]
                for name in names
            }
        ens[pos] = sum(weights[name] * probas_by_model[name][pos] for name in names)
        weight_rows.append(weights)

    return np.clip(ens, 0.0, 1.0), weight_rows


def _feature_selection(X_train: pd.DataFrame, y_train: pd.Series, X_val: pd.DataFrame) -> tuple:
    """Select top features using RF importance, return selected DataFrames."""
    selector = SelectFromModel(
        RandomForestRegressor(n_estimators=200, max_depth=10, min_samples_leaf=5, n_jobs=-1, random_state=42),
        threshold="median",
        prefit=False,
    )
    selector.fit(X_train, y_train)
    selected = selector.get_support()
    n_selected = selected.sum()
    print(f"    Feature selection: {n_selected}/{len(selected)} features kept")
    return X_train.iloc[:, selected], X_val.iloc[:, selected], list(np.array(X_train.columns)[selected])


def apply_feature_selection(X_train: pd.DataFrame, y_train: pd.Series, X_val: pd.DataFrame) -> tuple:
    """Run feature selection once, return same selected features for train and val."""
    selector = SelectFromModel(
        RandomForestRegressor(n_estimators=200, max_depth=10, min_samples_leaf=5, n_jobs=-1, random_state=42),
        threshold="median",
        prefit=False,
    )
    selector.fit(X_train, y_train)
    selected = selector.get_support()
    n_selected = selected.sum()
    print(f"    Feature selection: {n_selected}/{len(selected)} features kept")
    sel_features = list(np.array(X_train.columns)[selected])
    return X_train.iloc[:, selected], X_val.iloc[:, selected], sel_features


def walk_forward_evaluate(
    X: pd.DataFrame,
    y_return: pd.Series,
    y_direction: np.ndarray,
    horizon: int,
    n_windows: int = 5,
) -> dict:
    """
    Walk-forward evaluation: train on expanding window, test on next chunk.
    Returns per-window metrics and averages.
    """
    n_total = len(X)
    # Minimum 300 rows for first train, step sized to create n_windows
    min_train = 300
    remaining = n_total - min_train
    step = max(remaining // n_windows, 50)

    results = {"windows": [], "direction_acc": {}, "regression_mae": {}}
    all_model_names = ["rf", "et", "hgb", "gb"]

    for i in range(n_windows):
        train_end = min_train + i * step
        test_start = train_end
        test_end = min(test_start + step, n_total)

        if train_end >= n_total - 50 or test_start >= n_total:
            break

        X_train, X_test = X.iloc[:train_end], X.iloc[test_start:test_end]
        y_train_ret, y_test_ret = y_return.iloc[:train_end], y_return.iloc[test_start:test_end]
        y_train_dir, y_test_dir = y_direction[:train_end], y_direction[test_start:test_end]

        # Check sufficient samples and class balance in test set
        if len(X_test) < 20:
            print(f"    WF-{i+1}: train={len(X_train)} test={len(X_test)} — test set too small, skipping")
            continue
        n_up_test = (y_test_dir == 1).sum()
        n_down_test = (y_test_dir == 0).sum()
        if n_up_test == 0 or n_down_test == 0:
            print(f"    WF-{i+1}: train={len(X_train)} test={len(X_test)} — only one class in test, skipping")
            continue

        above_ma200_train = X_train["above_ma200"] >= 0.5
        above_ma200_test = X_test["above_ma200"] >= 0.5

        # Filter NEUTRAL (-1) from training labels (triple_barrier can produce -1 timeout rows)
        bull_nonneutral = y_train_dir[above_ma200_train.values] != -1
        bear_nonneutral = y_train_dir[(~above_ma200_train).values] != -1
        X_bull_fit = X_train[above_ma200_train][bull_nonneutral]
        y_bull_fit = y_train_dir[above_ma200_train.values][bull_nonneutral]
        X_bear_fit = X_train[~above_ma200_train][bear_nonneutral]
        y_bear_fit = y_train_dir[(~above_ma200_train).values][bear_nonneutral]

        # Decide whether to use regime-split or combined training.
        # Regime-split requires: both regimes in test AND each regime train ≥5 rows with 2 classes.
        both_test_regimes = above_ma200_test.sum() >= 1 and (~above_ma200_test).sum() >= 1
        bull_fit_ok = len(X_bull_fit) >= 5 and len(np.unique(y_bull_fit)) >= 2
        bear_fit_ok = len(X_bear_fit) >= 5 and len(np.unique(y_bear_fit)) >= 2
        use_regime_split = both_test_regimes and bull_fit_ok and bear_fit_ok

        if use_regime_split:
            y_bull_test_bin = (y_test_ret.values[above_ma200_test.values] > 0).astype(int)
            y_bear_test_bin = (y_test_ret.values[(~above_ma200_test).values] > 0).astype(int)
            clf_bull = train_classifier(X_bull_fit, y_bull_fit,
                                        X_test[above_ma200_test], y_bull_test_bin,
                                        do_feature_selection=False)
            clf_bear = train_classifier(X_bear_fit, y_bear_fit,
                                        X_test[~above_ma200_test], y_bear_test_bin,
                                        do_feature_selection=False)
            mode_tag = "regime-split"
            # Per-regime accuracy: both classifiers are evaluated on their respective subsets
            for is_bull, clf in [(True, clf_bull), (False, clf_bear)]:
                mask = above_ma200_test.values == is_bull
                if mask.sum() == 0:
                    continue
                for name in all_model_names:
                    if name in clf:
                        results["direction_acc"].setdefault(name, []).append(clf[name]["accuracy"])
        else:
            # Combined fallback: pool all regimes together for training and evaluation.
            # Used when: only one regime in test, or a regime train subset is too small.
            nonneutral_all = y_train_dir != -1
            X_combined = X_train[nonneutral_all]
            y_combined = y_train_dir[nonneutral_all]
            y_test_bin_all = (y_test_ret.values > 0).astype(int)
            if len(X_combined) < 10 or len(np.unique(y_combined)) < 2 or len(np.unique(y_test_bin_all)) < 2:
                reason_skip = (f"bull_fit={'ok' if bull_fit_ok else f'{len(X_bull_fit)}rows'} "
                               f"bear_fit={'ok' if bear_fit_ok else f'{len(X_bear_fit)}rows'} "
                               f"test_regimes={'both' if both_test_regimes else 'one'}")
                print(f"    WF-{i+1}: train={len(X_train)} test={len(X_test)} — combined fallback insufficient ({reason_skip}), skipping")
                continue
            if not both_test_regimes:
                mode_tag = f"combined(test-{'bull' if above_ma200_test.sum() > 0 else 'bear'}-only)"
            else:
                mode_tag = f"combined(bear-train={len(X_bear_fit)}rows)"
            clf_combined = train_classifier(X_combined, y_combined, X_test, y_test_bin_all,
                                            do_feature_selection=False)
            for name in all_model_names:
                if name in clf_combined:
                    results["direction_acc"].setdefault(name, []).append(clf_combined[name]["accuracy"])

        print(f"    WF-{i+1}: train={len(X_train)} test={len(X_test)} | "
              f"Bull n={above_ma200_test.sum()} Bear n={(~above_ma200_test).sum()} | {mode_tag}")

    # Average accuracy across windows
    print(f"\n  Walk-forward avg direction accuracy (H={horizon}):")
    avg_acc = {}
    for name in all_model_names:
        vals = results["direction_acc"].get(name, [])
        if vals:
            avg = np.mean(vals)
            avg_acc[name] = avg
            print(f"    {name:10s}: {avg:.4f}  (n_windows={len(vals)})")

    return {"avg_accuracy": avg_acc, "windows": results["windows"]}


# ─── Purged K-Fold + Embargo ────────────────────────────────────────────────

def purged_kfold_splits(
    n_samples: int,
    n_splits: int,
    horizon: int,
    embargo_bars: int | None = None,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Purged K-Fold splits with embargo for time-series label-overlap prevention.

    For each test fold [test_start, test_end):
      Purge:   remove training rows i where i + horizon >= test_start
               (their label window extends into the test fold)
      Embargo: skip [test_end, test_end + embargo_bars) from training
               (autocorrelation buffer after the test fold)

    Training = all rows outside [test_start - horizon, test_end + embargo).
    """
    if embargo_bars is None:
        embargo_bars = horizon
    fold_size = n_samples // n_splits
    splits = []
    for k in range(n_splits):
        test_start = k * fold_size
        test_end   = test_start + fold_size if k < n_splits - 1 else n_samples
        test_idx   = np.arange(test_start, test_end)
        purge_start  = max(0, test_start - horizon)
        embargo_end  = min(n_samples, test_end + embargo_bars)
        all_idx      = np.arange(n_samples)
        train_idx    = all_idx[(all_idx < purge_start) | (all_idx >= embargo_end)]
        if len(train_idx) >= 100 and len(test_idx) >= 20:
            splits.append((train_idx, test_idx))
    return splits


def evaluate_purged_kfold(
    X: pd.DataFrame,
    y_return: pd.Series,
    y_direction: np.ndarray,
    horizon: int,
    n_splits: int = 5,
    embargo_bars: int | None = None,
) -> dict:
    """Purged K-Fold + Embargo cross-validation for direction classification.

    Addresses two sources of time-series contamination:
      1. Label overlap  — the h-day label at row i uses close[i+1..i+h]; any
         training row whose window reaches into the test fold is purged.
      2. Autocorrelation bleed — an embargo buffer of `embargo_bars` is added
         after every test fold to prevent correlation leakage.

    Training labels : y_direction (NEUTRAL = -1 rows filtered out).
    Test labels     : binary (y_return > 0) on all test rows — consistent with
                      main() val evaluation so AUC values are directly comparable.
    """
    if embargo_bars is None:
        embargo_bars = horizon

    y_dir = np.asarray(y_direction)
    y_bin = (np.asarray(y_return) > 0).astype(int)
    n     = len(X)

    splits    = purged_kfold_splits(n, n_splits, horizon, embargo_bars)
    names     = ["rf", "et", "hgb", "gb", "ensemble"]
    fold_aucs = {nm: [] for nm in names}
    fold_accs = {nm: [] for nm in names}

    print(f"\n  Purged K-Fold (k={n_splits}, H={horizon}, embargo={embargo_bars}d)")
    print(f"  {'Fold':>4} {'Trn':>5} {'Tst':>5} {'Excluded':>9} | "
          f"{'RF':>6} {'ET':>6} {'HGB':>6} {'GB':>6} {'Ens':>6}")
    print(f"  {'-'*70}")

    for fi, (tr_idx, te_idx) in enumerate(splits):
        binary_mask = y_dir[tr_idx] != -1
        tr_clf  = tr_idx[binary_mask]
        y_tr    = y_dir[tr_clf]
        y_te    = y_bin[te_idx]
        n_excl  = n - len(tr_idx)   # rows excluded by purge + embargo + test fold

        if len(tr_clf) < 60 or len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
            print(f"  {fi+1:>4}: skipped (train={len(tr_clf)}, classes={len(np.unique(y_tr))})")
            continue

        res = train_classifier(X.iloc[tr_clf], y_tr, X.iloc[te_idx], y_te)
        row = {nm: res[nm]["auc"] for nm in names}

        print(f"  {fi+1:>4}: {len(tr_clf):>5} {len(te_idx):>5} {n_excl:>9} | "
              + "  ".join(f"{row[nm]:.4f}" for nm in names))

        for nm in names:
            fold_aucs[nm].append(res[nm]["auc"])
            fold_accs[nm].append(res[nm]["accuracy"])

    avg_auc = {nm: float(np.mean(v)) if v else float("nan") for nm, v in fold_aucs.items()}
    avg_acc = {nm: float(np.mean(v)) if v else float("nan") for nm, v in fold_accs.items()}
    print(f"  {'Avg':>4}: {'':>5} {'':>5} {'':>9} | "
          + "  ".join(f"{avg_auc[nm]:.4f}" if not np.isnan(avg_auc[nm]) else f"{'N/A':>6}"
                      for nm in names))

    return {"avg_auc": avg_auc, "avg_acc": avg_acc}


def train_regressor(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    do_feature_selection: bool = False,
) -> dict:
    """Train return regression ensemble: RF, ET, Ridge, ElasticNet (L2/L1 regularized linear).
    
    移除 HGB/GB（對槓桿ETF預測能力差且給出荒謬回測值）。
    Ridge/ElasticNet 對此類高波動資產的均值回歸特性更魯棒。
    """
    results = {}

    # Optionally select features
    if do_feature_selection:
        X_train_sel, X_val_sel, sel_features = _feature_selection(X_train, y_train, X_val)
    else:
        X_train_sel, X_val_sel = X_train, X_val
        sel_features = list(X_train.columns)

    # Scaler for linear models (Ridge/ElasticNet need standardized features)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train_sel)
    X_val_scaled = scaler.transform(X_val_sel)

    # RandomForest — tuned
    rf = RandomForestRegressor(
        n_estimators=500,
        max_depth=12,
        min_samples_leaf=3,
        min_samples_split=5,
        max_features="sqrt",
        n_jobs=-1,
        random_state=42,
    )
    rf.fit(X_train_sel, y_train)
    rf_pred = rf.predict(X_val_sel)
    results["rf"] = {"model": rf, "mae": mean_absolute_error(y_val, rf_pred),
                      "rmse": np.sqrt(mean_squared_error(y_val, rf_pred)),
                      "r2": r2_score(y_val, rf_pred), "predictions": rf_pred,
                      "features": sel_features, "scaler": None}

    # ExtraTrees — more randomness, often better for noisy data
    et = ExtraTreesRegressor(
        n_estimators=500,
        max_depth=12,
        min_samples_leaf=3,
        min_samples_split=5,
        max_features="sqrt",
        n_jobs=-1,
        random_state=42,
    )
    et.fit(X_train_sel, y_train)
    et_pred = et.predict(X_val_sel)
    results["et"] = {"model": et, "mae": mean_absolute_error(y_val, et_pred),
                    "rmse": np.sqrt(mean_squared_error(y_val, et_pred)),
                    "r2": r2_score(y_val, et_pred), "predictions": et_pred,
                    "features": sel_features, "scaler": None}

    # ElasticNet — L1+L2, can perform feature selection internally
    # alpha=0.05 with l1_ratio=0.3 gives strong regularization to avoid wild long-horizon predictions
    en = ElasticNet(alpha=0.05, l1_ratio=0.3, max_iter=2000, random_state=42)
    en.fit(X_train_scaled, y_train)
    en_pred = en.predict(X_val_scaled)
    results["elasticnet"] = {"model": en, "mae": mean_absolute_error(y_val, en_pred),
                             "rmse": np.sqrt(mean_squared_error(y_val, en_pred)),
                             "r2": r2_score(y_val, en_pred), "predictions": en_pred,
                             "features": sel_features, "scaler": scaler}

    # 3-model ensemble (RF + ET + ElasticNet — Ridge removed for stability)
    ens_pred = (rf_pred + et_pred + en_pred) / 3
    results["ensemble"] = {"mae": mean_absolute_error(y_val, ens_pred),
                           "rmse": np.sqrt(mean_squared_error(y_val, ens_pred)),
                           "r2": r2_score(y_val, ens_pred), "predictions": ens_pred}

    # Store callable for prediction (uses scaler if needed)
    def ens_predict(X):
        X_sel = X[sel_features]
        # Scale if scaler is present
        X_scaled = scaler.transform(X_sel) if scaler is not None else X_sel
        return (rf.predict(X_sel) + et.predict(X_sel) +
                en.predict(X_scaled)) / 3
    results["ensemble"]["model"] = type("EnsReg", (), {"predict": ens_predict})()
    results["ensemble"]["features"] = sel_features
    results["ensemble"]["scaler"] = scaler

    return results


def identify_stable_features(
    X: pd.DataFrame,
    y_dir: np.ndarray,
    n_folds: int = 3,
    top_k: int = 20,
    min_folds: int = None,
) -> list:
    """Return features that land in the top-k importances on >= min_folds TimeSeriesSplit folds.

    Uses a fast 200-tree RF.  Default min_folds = n_folds (require ALL folds).
    Falls back to the top-20 single-fold features if fewer than 5 stable features are found.
    """
    if min_folds is None:
        min_folds = n_folds
    feature_names = list(X.columns)
    tss = TimeSeriesSplit(n_splits=n_folds)
    top_k_sets: list = []
    for tr_idx, _ in tss.split(X):
        if len(tr_idx) < 80:
            continue
        y_tr = y_dir[tr_idx]
        mask = y_tr != -1
        X_tr_clean = X.iloc[tr_idx][mask]
        y_tr_clean = y_tr[mask]
        if len(np.unique(y_tr_clean)) < 2 or len(X_tr_clean) < 50:
            continue
        rf = RandomForestClassifier(
            n_estimators=200, max_depth=8, min_samples_leaf=5,
            max_features="sqrt", n_jobs=-1, random_state=42,
        )
        rf.fit(X_tr_clean, y_tr_clean)
        top_k_sets.append(set(np.argsort(-rf.feature_importances_)[:top_k]))
    if len(top_k_sets) < 2:
        return feature_names
    stable_idx = [i for i in range(len(feature_names))
                  if sum(1 for s in top_k_sets if i in s) >= min_folds]
    stable = [feature_names[i] for i in stable_idx]
    if len(stable) < 5:
        # fallback: use features present in at least one fold
        fallback_idx = list(dict.fromkeys(
            idx for s in top_k_sets for idx in sorted(s)
        ))[:top_k]
        stable = [feature_names[i] for i in fallback_idx]
    return stable


def evaluate_feature_stability(
    X: pd.DataFrame,
    y_dir: np.ndarray,
    n_splits: int = 5,
    top_n: int = 15,
) -> dict:
    """Feature importance stability across TimeSeriesSplit folds.

    Uses a fast RandomForest (200 trees) per fold for impurity-based importances.

    Metrics per feature
    -------------------
    mean_imp  : average importance across folds
    cv        : std / mean  — lower = more stable
    rank_std  : std of rank position across folds — lower = more stable
    top10_freq: how often the feature is in the top-10 (e.g. "4/5")
    stability : HIGH / MED / LOW

    Overall metrics
    ---------------
    mean_rank_corr  : mean pairwise Spearman correlation of fold importance vectors
    stability_grade : A>=0.85 / B>=0.70 / C>=0.55 / D<0.55
    top10_consistency: fraction of top-10 features consistent across ALL folds
    """
    feature_names = list(X.columns)
    n_feat = len(feature_names)
    tss = TimeSeriesSplit(n_splits=n_splits)

    fold_importances: list = []

    for tr_idx, _ in tss.split(X):
        if len(tr_idx) < 80:
            continue
        y_tr = y_dir[tr_idx]
        mask = y_tr != -1
        X_tr_clean = X.iloc[tr_idx][mask]
        y_tr_clean = y_tr[mask]
        if len(np.unique(y_tr_clean)) < 2 or len(X_tr_clean) < 50:
            continue
        rf = RandomForestClassifier(
            n_estimators=200, max_depth=8, min_samples_leaf=5,
            max_features="sqrt", n_jobs=-1, random_state=42,
        )
        rf.fit(X_tr_clean, y_tr_clean)
        fold_importances.append(rf.feature_importances_)

    if len(fold_importances) < 2:
        return {"error": "insufficient folds", "mean_rank_corr": 0.0, "stability_grade": "N/A",
                "feature_stats": [], "top10_consistency": 0.0, "n_folds_used": 0}

    n_folds  = len(fold_importances)
    imp_mat  = np.array(fold_importances)   # (n_folds, n_features)
    mean_imp = imp_mat.mean(axis=0)
    std_imp  = imp_mat.std(axis=0)
    cv       = np.where(mean_imp > 1e-7, std_imp / mean_imp, np.inf)

    # Rank of each feature within each fold (rank 0 = most important)
    rank_mat  = np.array([np.argsort(np.argsort(-imp)) for imp in fold_importances])
    rank_std  = rank_mat.std(axis=0)

    # Pairwise Spearman rank correlation of fold importance vectors (no scipy needed)
    def _spearman(a: np.ndarray, b: np.ndarray) -> float:
        ra = np.argsort(np.argsort(a)).astype(float)
        rb = np.argsort(np.argsort(b)).astype(float)
        return float(np.corrcoef(ra, rb)[0, 1])

    rank_corrs = [
        _spearman(fold_importances[i], fold_importances[j])
        for i in range(n_folds) for j in range(i + 1, n_folds)
    ]
    mean_rank_corr = float(np.mean(rank_corrs))

    # Top-K consistency: fraction of top-10 features in top-10 on EVERY fold
    TOP_K = min(10, n_feat)
    top_k_sets = [set(np.argsort(-imp)[:TOP_K]) for imp in fold_importances]
    common_top = set.intersection(*top_k_sets)
    top10_consistency = len(common_top) / TOP_K

    # Per-feature stability thresholds
    thr_cv_high   = 0.50
    thr_rank_high = n_feat * 0.15   # rank fluctuates by <15% of feature count
    thr_cv_med    = 1.00
    thr_rank_med  = n_feat * 0.30

    sorted_idx = np.argsort(-mean_imp)
    stats = []
    for fi in sorted_idx[:top_n]:
        cv_v  = float(cv[fi])
        rs    = float(rank_std[fi])
        if cv_v < thr_cv_high and rs < thr_rank_high:
            label = "HIGH"
        elif cv_v < thr_cv_med and rs < thr_rank_med:
            label = "MED"
        else:
            label = "LOW"
        top10_count = sum(1 for s in top_k_sets if fi in s)
        stats.append({
            "feature":    feature_names[fi],
            "mean_imp":   float(mean_imp[fi]),
            "cv":         cv_v,
            "rank_std":   rs,
            "top10_freq": f"{top10_count}/{n_folds}",
            "stability":  label,
        })

    if mean_rank_corr >= 0.85:
        grade = "A"
    elif mean_rank_corr >= 0.70:
        grade = "B"
    elif mean_rank_corr >= 0.55:
        grade = "C"
    else:
        grade = "D"

    return {
        "feature_stats":      stats,
        "mean_rank_corr":     mean_rank_corr,
        "stability_grade":    grade,
        "top10_consistency":  top10_consistency,
        "n_folds_used":       n_folds,
    }


def train_classifier(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_val: pd.DataFrame,
    y_val: np.ndarray,
    do_feature_selection: bool = False,
    n_folds: int = 5,
    calib_frac: float = 0.20,
    stable_features: list | None = None,
    late_bull_threshold: float | None = 0.15,
    optuna_params: dict | None = None,
    horizon: int | None = None,
    expanding_model_weights: bool = False,
) -> dict:
    """Train direction classification ensemble: RF, ET, HGB, GB + LGB/XGB/CatBoost if available.

    Ensemble weights are computed dynamically from val AUC:
      w_i = max(0, AUC_i − 0.5)   (models at chance level get zero weight)

    Probability calibration: last `calib_frac` of training rows are held out for
    Isotonic Regression calibration.  Calibrated probabilities replace raw probabilities.

    late_bull_threshold: when set, a separate Isotonic calibrator is fit on
    training rows where close_ma200_dist > threshold ("late bull" regime).
    At prediction time, late-bull rows use this calibrator instead of the
    global one.  Val AUC is also reported per ma_gap sub-regime.
    Set to None to disable (restores original behaviour).

    stable_features: if provided, an extra 'stable_rf' sub-model is trained using
    only those features and included in the AUC-weighted ensemble.

    expanding_model_weights: when True, the AUC+Brier ensemble weight for each
    validation row is computed using only rows whose forward-looking `horizon`-day
    label had already resolved as of that row (i.e. an expanding/walk-forward
    window, mirroring `_build_expanding_horizon_ensemble_panel`'s per-horizon
    weighting one level down, at the per-model level). This avoids the panel-drift
    failure mode where every model's global AUC/Brier -- and therefore every
    historical row's blended probability -- silently shifts whenever the
    validation set grows (see GROUP_A_PLUS_NCF_PANEL_DRIFT_AUDIT_20260706.md).
    Default False preserves the original single global-weight behavior exactly.
    """
    results = {}

    if do_feature_selection:
        X_train_sel, X_val_sel, sel_features = _feature_selection(
            X_train, pd.Series(y_train, index=X_train.index), X_val)
    else:
        X_train_sel, X_val_sel = X_train, X_val
        sel_features = list(X_train.columns)

    X_train_sel = X_train_sel.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    X_val_sel = X_val_sel.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    y_train_arr = np.asarray(y_train)
    y_val_arr   = np.asarray(y_val)

    # ── Build model registry (always include sklearn models; add boosters if available) ──
    base_defs: dict = {
        "rf": RandomForestClassifier(
            n_estimators=500, max_depth=12, min_samples_leaf=3,
            max_features="sqrt", n_jobs=-1, random_state=42,
        ),
        "et": ExtraTreesClassifier(
            n_estimators=500, max_depth=12, min_samples_leaf=3,
            max_features="sqrt", n_jobs=-1, random_state=42,
        ),
        "hgb": HistGradientBoostingClassifier(
            max_iter=500, max_depth=6, learning_rate=0.03,
            min_samples_leaf=5, l2_regularization=0.1, random_state=42,
        ),
        "gb": GradientBoostingClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            min_samples_leaf=5, subsample=0.8, max_features="sqrt",
            random_state=42,
        ),
    }
    if _HAS_LGB:
        base_defs["lgb"] = lgb.LGBMClassifier(
            n_estimators=500, max_depth=6, learning_rate=0.03,
            num_leaves=31, min_child_samples=5,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=0.1,
            n_jobs=-1, random_state=42, verbose=-1,
        )
    if _HAS_XGB:
        base_defs["xgb"] = xgb.XGBClassifier(
            n_estimators=500, max_depth=5, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=0.1, reg_lambda=1.0,
            eval_metric="logloss", n_jobs=-1,
            random_state=42, verbosity=0,
        )
    if _HAS_CAT:
        base_defs["cat"] = CatBoostClassifier(
            iterations=300, depth=6, learning_rate=0.05,
            l2_leaf_reg=3.0, thread_count=-1,
            random_seed=42, verbose=False,
        )

    # Override with Optuna best params when provided
    if optuna_params:
        _cls_map = {
            "lgb": (lgb.LGBMClassifier, {"n_jobs": -1, "random_state": 42, "verbose": -1}) if _HAS_LGB else None,
            "xgb": (xgb.XGBClassifier,  {"eval_metric": "logloss", "n_jobs": -1, "random_state": 42, "verbosity": 0}) if _HAS_XGB else None,
            "hgb": (HistGradientBoostingClassifier, {"random_state": 42}),
            "rf":  (RandomForestClassifier, {"n_jobs": -1, "random_state": 42}),
            "et":  (ExtraTreesClassifier, {"n_jobs": -1, "random_state": 42}),
        }
        for _mn, _opt in optuna_params.items():
            if _mn not in _cls_map or _cls_map[_mn] is None:
                continue
            _cls, _fixed = _cls_map[_mn]
            _merged = {**_opt.get("best_params", {}), **_fixed}
            try:
                base_defs[_mn] = _cls(**_merged)
            except Exception:
                pass  # keep default if params invalid

    BASE_NAMES = list(base_defs.keys())

    # ── TabNet (optional deep tabular model) ───────────────────────────────────
    # Trained separately after tree models; integrated into AUC-weighted ensemble.
    _tabnet_result: dict | None = None

    # ── Calibration split: last calib_frac rows are held out for Platt scaling ──
    # Time order is preserved: models are fit on the earlier portion, calibrated on the later.
    # Minimum thresholds: n_fit>=50 AND n_calib>=60 to avoid noisy sigmoid fits.
    n_tr     = len(X_train_sel)
    n_calib  = max(30, int(n_tr * calib_frac))
    n_fit    = n_tr - n_calib
    MIN_CALIB = 60  # below this Platt fit is unreliable (too few rows)
    CALIB_MAX_AUC_DROP = 0.03  # max acceptable AUC loss from isotonic calibration
    use_calibration = n_fit >= 50 and n_calib >= MIN_CALIB

    if use_calibration:
        X_fit   = X_train_sel.iloc[:n_fit]
        y_fit   = y_train_arr[:n_fit]
        X_calib = X_train_sel.iloc[n_fit:]
        y_calib = y_train_arr[n_fit:]
    else:
        X_fit, y_fit = X_train_sel, y_train_arr

    # ── Determine late-bull mask (close_ma200_dist > late_bull_threshold) ────────
    # Used for per-sub-regime AUC reporting and separate calibration.
    # Only active when late_bull_threshold is set and the column exists.
    _late_bull_col = "close_ma200_dist"
    _use_late_bull = (
        late_bull_threshold is not None
        and _late_bull_col in X_train_sel.columns
        and _late_bull_col in X_val_sel.columns
    )
    if _use_late_bull:
        late_bull_calib_mask = (
            X_train_sel.iloc[n_fit:][_late_bull_col].values > late_bull_threshold
            if use_calibration else np.zeros(0, dtype=bool)
        )
        late_bull_val_mask = X_val_sel[_late_bull_col].values > late_bull_threshold

    class _IsotonicModel:
        """Raw model + Isotonic Regression calibration.

        Optionally applies a separate late-bull isotonic calibrator when
        close_ma200_dist > late_bull_threshold at prediction time.
        """
        def __init__(self, base, iso_reg, iso_late_bull=None, late_bull_col=None, threshold=None):
            self._base = base
            self._iso  = iso_reg
            self._iso_lb = iso_late_bull   # separate calibrator for late-bull rows
            self._lb_col = late_bull_col
            self._thr    = threshold

        def predict_proba(self, X):
            raw = self._base.predict_proba(X)[:, 1]
            cal = np.clip(self._iso.predict(raw), 0.0, 1.0)
            # Late-bull override: apply separate calibrator for far-from-MA rows
            if self._iso_lb is not None and self._lb_col in X.columns:
                lb_mask = X[self._lb_col].values > self._thr
                if lb_mask.any():
                    cal[lb_mask] = np.clip(self._iso_lb.predict(raw[lb_mask]), 0.0, 1.0)
            return np.column_stack([1 - cal, cal])

        def predict(self, X):
            return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)

    # ── Train all base models; apply Isotonic Regression calibration; collect val predictions ──
    # Design: always train a full-data model first (baseline).
    # Separately attempt calibration using the 80/20 temporal split.
    # Isotonic regression replaces Platt sigmoid — monotone, non-parametric,
    # better suited for tree ensemble probability outputs.
    # Accept calibration only if it improves val Brier. Isotonic regression is
    # rank-preserving, so it cannot meaningfully move AUC — gating acceptance
    # on AUC was a near no-op; Brier is what calibration actually optimizes for.
    # Late-bull: additionally fit a separate isotonic on calib rows where
    # close_ma200_dist > late_bull_threshold to handle the high-ma_gap regime.
    for name in BASE_NAMES:
        m_full = clone(base_defs[name])
        m_full.fit(X_train_sel, y_train_arr)
        v_proba_raw = m_full.predict_proba(X_val_sel)[:, 1]
        auc_raw = roc_auc_score(y_val_arr, v_proba_raw)

        calib_applied = False
        late_bull_calib_applied = False
        cal_m   = m_full
        v_proba = v_proba_raw

        if use_calibration:
            m_fit = clone(base_defs[name])
            m_fit.fit(X_fit, y_fit)
            raw_cal = m_fit.predict_proba(X_calib)[:, 1]

            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(raw_cal, y_calib)
            iso_val_proba = np.clip(iso.predict(m_fit.predict_proba(X_val_sel)[:, 1]), 0.0, 1.0)
            brier_iso = brier_score_loss(y_val_arr, iso_val_proba)
            brier_raw = brier_score_loss(y_val_arr, v_proba_raw)
            auc_iso   = roc_auc_score(y_val_arr, iso_val_proba)

            iso_late_bull = None
            if _use_late_bull and late_bull_calib_mask.sum() >= 30:
                lb_raw = raw_cal[late_bull_calib_mask]
                lb_y   = y_calib[late_bull_calib_mask]
                if len(np.unique(lb_y)) == 2:
                    iso_lb = IsotonicRegression(out_of_bounds="clip")
                    iso_lb.fit(lb_raw, lb_y)
                    iso_late_bull = iso_lb
                    late_bull_calib_applied = True

            # Accept only if Brier genuinely improves AND held-out AUC doesn't
            # degrade materially. Isotonic's step function creates ties on
            # unseen data, which can quietly erode ranking power even while
            # Brier improves -- a Brier-only gate was too permissive.
            if brier_iso < brier_raw and auc_iso >= auc_raw - CALIB_MAX_AUC_DROP:
                cal_m = _IsotonicModel(
                    m_fit, iso,
                    iso_late_bull=iso_late_bull,
                    late_bull_col=_late_bull_col if _use_late_bull else None,
                    threshold=late_bull_threshold,
                )
                v_proba       = iso_val_proba
                calib_applied = True
            # else: keep full-data model (no Brier gain from calibration)

        v_pred = (v_proba >= 0.5).astype(int)
        results[name] = {
            "model":          cal_m,
            "accuracy":       accuracy_score(y_val_arr, v_pred),
            "proba":          v_proba,
            "proba_raw":      v_proba_raw,
            "predictions":    v_pred,
            "auc":            roc_auc_score(y_val_arr, v_proba),
            "auc_raw":        roc_auc_score(y_val_arr, v_proba_raw),
            "brier":          brier_score_loss(y_val_arr, v_proba),
            "brier_raw":      brier_score_loss(y_val_arr, v_proba_raw),
            "calib_applied":  calib_applied,
            "features":       sel_features,
        }

    # ── TabNet training (optional, added to ensemble if AUC > 0.5) ─────────────
    if _HAS_TABNET:
        try:
            from sklearn.preprocessing import StandardScaler
            from sklearn.impute import SimpleImputer
            _imp = SimpleImputer(strategy="median")
            _scl = StandardScaler()
            _Xtr = _scl.fit_transform(_imp.fit_transform(X_fit.values)).astype(np.float32)
            _Xvl = _scl.transform(_imp.transform(X_val_sel.values)).astype(np.float32)
            _ytr = y_fit.astype(np.int64)
            _yvl = y_val_arr.astype(np.int64)
            n_feat = _Xtr.shape[1]
            _tn = _TabNetClassifier(
                n_d=min(16, n_feat), n_a=min(16, n_feat),
                n_steps=3, gamma=1.5,
                n_independent=2, n_shared=2,
                momentum=0.02, mask_type="sparsemax",
                optimizer_fn=_torch.optim.Adam,
                optimizer_params={"lr": 2e-3, "weight_decay": 1e-4},
                scheduler_fn=_torch.optim.lr_scheduler.StepLR,
                scheduler_params={"step_size": 20, "gamma": 0.9},
                verbose=0, seed=42,
            )
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                _tn.fit(
                    _Xtr, _ytr,
                    eval_set=[(_Xvl, _yvl)],
                    eval_metric=["auc"],
                    max_epochs=80, patience=15,
                    batch_size=min(128, max(32, len(_Xtr) // 8)),
                    virtual_batch_size=min(64, max(16, len(_Xtr) // 16)),
                )
            _tab_proba = _tn.predict_proba(_Xvl)[:, 1]
            _tab_auc = roc_auc_score(_yvl, _tab_proba)

            class _TabWrapper:
                def __init__(self, tn, imp, scl):
                    self._tn, self._imp, self._scl = tn, imp, scl
                def predict_proba(self, X):
                    Xn = self._scl.transform(self._imp.transform(
                        X.values if hasattr(X, "values") else X
                    )).astype(np.float32)
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        return self._tn.predict_proba(Xn)

            results["tabnet"] = {
                "model":       _TabWrapper(_tn, _imp, _scl),
                "accuracy":    accuracy_score(_yvl, (_tab_proba >= 0.5).astype(int)),
                "proba":       _tab_proba,
                "proba_raw":   _tab_proba,
                "predictions": (_tab_proba >= 0.5).astype(int),
                "auc":         _tab_auc,
                "auc_raw":     _tab_auc,
                "brier":       brier_score_loss(_yvl, _tab_proba),
                "brier_raw":   brier_score_loss(_yvl, _tab_proba),
                "calib_applied": False,
                "features":    sel_features,
            }
        except Exception as _e:
            print(f"  [TabNet] skipped: {_e}")

    ALL_NAMES = BASE_NAMES + (["tabnet"] if "tabnet" in results else [])

    # ── AUC+Brier-weighted ensemble (uses calibrated probabilities) ──
    # w_i ∝ max(0, AUC_i - 0.5) * max(0, naive_brier - Brier_i)
    # AUC alone rewards ranking skill but ignores calibration quality: a model
    # with AUC > 0.5 but Brier worse than the constant-base-rate naive predictor
    # is actively miscalibrated and should not get material blend weight just
    # because it ranks decently. naive_brier is the Brier score of always
    # predicting the validation-set base rate (Bernoulli variance p*(1-p)).
    p_base      = float(np.mean(y_val_arr))
    naive_brier = p_base * (1.0 - p_base)
    if expanding_model_weights:
        ens_proba, weight_rows = _expanding_model_ensemble_weights(
            {name: results[name]["proba"] for name in ALL_NAMES}, y_val_arr, horizon=horizon,
        )
        W = weight_rows[-1] if weight_rows else {name: 1.0 / len(ALL_NAMES) for name in ALL_NAMES}
    else:
        auc_w   = {name: max(0.0, results[name]["auc"] - 0.5) for name in ALL_NAMES}
        brier_w = {name: max(0.0, naive_brier - results[name]["brier"]) for name in ALL_NAMES}
        raw_w   = {name: auc_w[name] * brier_w[name] for name in ALL_NAMES}
        total_w = sum(raw_w.values())
        if total_w > 0:
            W = {name: raw_w[name] / total_w for name in ALL_NAMES}
        else:
            # No model clears the Brier bar (e.g. a weak horizon) — fall back to
            # the original AUC-only weighting, then to equal weight as last resort.
            total_auc_w = sum(auc_w.values())
            W = ({name: auc_w[name] / total_auc_w for name in ALL_NAMES}
                 if total_auc_w > 0 else {name: 1.0 / len(ALL_NAMES) for name in ALL_NAMES})
        ens_proba = sum(W[name] * results[name]["proba"] for name in ALL_NAMES)
    ens_pred  = (ens_proba >= 0.5).astype(int)
    ens_brier = brier_score_loss(y_val_arr, ens_proba)
    results["ensemble"] = {
        "accuracy":    accuracy_score(y_val_arr, ens_pred),
        "proba":       ens_proba,
        "predictions": ens_pred,
        "auc":         roc_auc_score(y_val_arr, ens_proba),
        "brier":       ens_brier,
        "features":    sel_features,
        "weights":     W,
        "ensemble_weight_method": "expanding_prior" if expanding_model_weights else "global",
    }

    # ── Calibration comparison table ──────────────────────────────────────────
    if use_calibration:
        n_applied = sum(results[nm]["calib_applied"] for nm in BASE_NAMES)
        print(f"\n  Isotonic Calibration (fit={n_fit} / calib={n_calib}, accepted={n_applied}/{len(BASE_NAMES)}):")
        print(f"  {'Model':<8} {'AUC_raw':>9} {'AUC_cal':>9}  {'Brier_raw':>10} {'Brier_cal':>10}  Status")
        for name in BASE_NAMES:
            r   = results[name]
            da  = r["auc"] - r["auc_raw"]
            db  = r["brier"] - r["brier_raw"]
            tag = "iso-OK" if r["calib_applied"] else "skip(no-gain)"
            print(f"  {name:<8} {r['auc_raw']:>9.4f} {r['auc']:>9.4f}({da:+.4f})"
                  f"  {r['brier_raw']:>10.4f} {r['brier']:>10.4f}({db:+.4f})  {tag}")
        print(f"  {'ensemble':<8} {'':>9} {results['ensemble']['auc']:>9.4f}          "
              f"  {'':>10} {ens_brier:>10.4f}")
    else:
        print(f"\n  Calibration skipped (n_calib={n_calib} < {MIN_CALIB}, using raw probabilities)")

    # ── Late-bull sub-regime AUC diagnostic ───────────────────────────────────
    # Reports ensemble AUC split by ma_gap regime: near-MA bull vs late/far bull.
    # A near-random late-bull AUC confirms NCF is unreliable when ma_gap is large.
    if _use_late_bull and late_bull_val_mask.sum() >= 10:
        near_bull_mask = ~late_bull_val_mask
        ens_p = results["ensemble"]["proba"]
        late_bull_n   = int(late_bull_val_mask.sum())
        near_bull_n   = int(near_bull_mask.sum())
        y_lb = y_val_arr[late_bull_val_mask]
        y_nb = y_val_arr[near_bull_mask]
        p_lb = ens_p[late_bull_val_mask]
        p_nb = ens_p[near_bull_mask]
        try:
            auc_lb = roc_auc_score(y_lb, p_lb) if len(np.unique(y_lb)) == 2 else float("nan")
        except Exception:
            auc_lb = float("nan")
        try:
            auc_nb = roc_auc_score(y_nb, p_nb) if len(np.unique(y_nb)) == 2 else float("nan")
        except Exception:
            auc_nb = float("nan")
        flag_lb = " ← near-random, suppress" if not (auc_lb != auc_lb) and auc_lb < 0.52 else ""
        print(f"\n  Late-bull sub-regime AUC (ma_gap > {late_bull_threshold:.0%}):")
        print(f"    Near-MA bull  (ma_gap ≤ {late_bull_threshold:.0%}): AUC={auc_nb:.4f}  n={near_bull_n}")
        print(f"    Late/far bull (ma_gap > {late_bull_threshold:.0%}): AUC={auc_lb:.4f}  n={late_bull_n}{flag_lb}")

    # ── Stable-feature sub-model (only when stable_features provided) ──────────
    # ALL_NAMES already set above (includes tabnet if present)

    if stable_features and len(stable_features) >= 5:
        stb_cols = [f for f in stable_features if f in X_train_sel.columns]
        stb_val_cols = [f for f in stable_features if f in X_val_sel.columns]
        stb_cols = [f for f in stb_cols if f in stb_val_cols]  # intersection

        if len(stb_cols) >= 5:
            X_train_stb = X_train_sel[stb_cols]
            X_val_stb   = X_val_sel[stb_cols]

            # Train stable_rf on full training set
            stb_m = RandomForestClassifier(
                n_estimators=500, max_depth=8, min_samples_leaf=5,
                max_features="sqrt", n_jobs=-1, random_state=43,
            )
            stb_m.fit(X_train_stb, y_train_arr)
            stb_proba_raw = stb_m.predict_proba(X_val_stb)[:, 1]
            stb_proba     = stb_proba_raw
            stb_cal_m     = stb_m
            stb_calib_applied = False

            # Attempt isotonic calibration for stable_rf if we have enough data
            if use_calibration:
                X_fit_stb   = X_train_stb.iloc[:n_fit]
                X_calib_stb = X_train_stb.iloc[n_fit:]
                stb_fit = RandomForestClassifier(
                    n_estimators=500, max_depth=8, min_samples_leaf=5,
                    max_features="sqrt", n_jobs=-1, random_state=43,
                )
                stb_fit.fit(X_fit_stb, y_fit)
                raw_cal_stb = stb_fit.predict_proba(X_calib_stb)[:, 1]
                iso_stb = IsotonicRegression(out_of_bounds="clip")
                iso_stb.fit(raw_cal_stb, y_calib)
                iso_stb_val = iso_stb.transform(stb_m.predict_proba(X_val_stb)[:, 1])
                stb_auc_raw   = roc_auc_score(y_val_arr, stb_proba)
                stb_brier_raw = brier_score_loss(y_val_arr, stb_proba)
                stb_auc_iso   = roc_auc_score(y_val_arr, iso_stb_val)
                stb_brier_iso = brier_score_loss(y_val_arr, iso_stb_val)
                if stb_brier_iso < stb_brier_raw and stb_auc_iso >= stb_auc_raw - CALIB_MAX_AUC_DROP:
                    stb_cal_m = _IsotonicModel(stb_fit, iso_stb)
                    stb_proba = stb_cal_m.predict_proba(X_val_stb)[:, 1]
                    stb_calib_applied = True

            stb_auc  = roc_auc_score(y_val_arr, stb_proba)
            stb_pred = (stb_proba >= 0.5).astype(int)
            print(f"\n  Stable sub-model (stable_rf, {len(stb_cols)} features): "
                  f"AUC={stb_auc:.4f}  Brier={brier_score_loss(y_val_arr, stb_proba):.4f}"
                  f"  calib={'OK' if stb_calib_applied else 'skip'}")

            results["stable_rf"] = {
                "model":          stb_cal_m,
                "accuracy":       accuracy_score(y_val_arr, stb_pred),
                "proba":          stb_proba,
                "proba_raw":      stb_proba_raw,
                "predictions":    stb_pred,
                "auc":            stb_auc,
                "auc_raw":        roc_auc_score(y_val_arr, stb_proba_raw),
                "brier":          brier_score_loss(y_val_arr, stb_proba),
                "brier_raw":      brier_score_loss(y_val_arr, stb_proba_raw),
                "calib_applied":  stb_calib_applied,
                "features":       stb_cols,  # IMPORTANT: different from sel_features
            }
            ALL_NAMES = ALL_NAMES + ["stable_rf"]

            # Recompute AUC+Brier-weighted ensemble with stable_rf included
            if expanding_model_weights:
                ens_proba2, weight_rows2 = _expanding_model_ensemble_weights(
                    {name: results[name]["proba"] for name in ALL_NAMES}, y_val_arr, horizon=horizon,
                )
                W2 = weight_rows2[-1] if weight_rows2 else {name: 1.0 / len(ALL_NAMES) for name in ALL_NAMES}
            else:
                auc_w2   = {name: max(0.0, results[name]["auc"] - 0.5) for name in ALL_NAMES}
                brier_w2 = {name: max(0.0, naive_brier - results[name]["brier"]) for name in ALL_NAMES}
                raw_w2   = {name: auc_w2[name] * brier_w2[name] for name in ALL_NAMES}
                total_w2 = sum(raw_w2.values())
                if total_w2 > 0:
                    W2 = {name: raw_w2[name] / total_w2 for name in ALL_NAMES}
                else:
                    total_auc_w2 = sum(auc_w2.values())
                    W2 = ({name: auc_w2[name] / total_auc_w2 for name in ALL_NAMES}
                          if total_auc_w2 > 0 else {name: 1.0 / len(ALL_NAMES) for name in ALL_NAMES})
                ens_proba2 = sum(W2[name] * results[name]["proba"] for name in ALL_NAMES)
            ens_pred2  = (ens_proba2 >= 0.5).astype(int)
            ens_brier2 = brier_score_loss(y_val_arr, ens_proba2)
            old_ens_auc = results["ensemble"]["auc"]
            results["ensemble"] = {
                "accuracy":    accuracy_score(y_val_arr, ens_pred2),
                "proba":       ens_proba2,
                "predictions": ens_pred2,
                "auc":         roc_auc_score(y_val_arr, ens_proba2),
                "brier":       ens_brier2,
                "features":    sel_features,
                "weights":     W2,
                "ensemble_weight_method": "expanding_prior" if expanding_model_weights else "global",
            }
            new_ens_auc = results["ensemble"]["auc"]
            print(f"  Ensemble AUC: {old_ens_auc:.4f} → {new_ens_auc:.4f} "
                  f"({'improved' if new_ens_auc > old_ens_auc else 'unchanged/lower'})")

    results["_sel_features"] = sel_features
    results["_models"]       = {name: results[name]["model"] for name in ALL_NAMES}
    n_applied_total          = sum(results[nm]["calib_applied"] for nm in ALL_NAMES) if use_calibration else 0
    results["_calib_info"]   = {
        "method":   "isotonic_regression",
        "n_fit":    n_fit if use_calibration else n_tr,
        "n_calib":  n_calib if use_calibration else 0,
        "applied":  use_calibration,
        "n_models_calibrated": n_applied_total,
    }

    return results


def main() -> None:
    global _HAS_TABNET

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ticker", default=TICKER)
    parser.add_argument("--train-start", default="2020-01-01")
    parser.add_argument("--val-start", default="2025-01-02")
    parser.add_argument("--val-end", default="latest",
                        help="Validation/data end date, or 'latest' to use newest DB OHLCV date")
    parser.add_argument("--feature-selection", action="store_true", help="Enable feature selection per model")
    parser.add_argument("--walk-forward", action="store_true", help="Run walk-forward evaluation")
    parser.add_argument("--purged-cv", action="store_true",
                        help="Run Purged K-Fold + Embargo cross-validation (slower, ~3× runtime)")
    parser.add_argument("--purged-cv-k", type=int, default=5,
                        help="Number of folds for purged CV (default 5)")
    parser.add_argument("--direction-threshold", type=float, default=0.005,
                        help="NEUTRAL zone threshold for classification training (default 0.005 = 0.5%%)")
    parser.add_argument("--labeling", choices=["auto", "simple", "triple_barrier"], default="auto",
                        help="Direction labeling: 'auto' (H=5→TBL, others→simple), 'simple', or 'triple_barrier' (all horizons)")
    parser.add_argument("--tbl-mult", type=float, default=0.75,
                        help="ATR multiplier for Triple Barrier TP/SL barriers (default 0.75)")
    parser.add_argument("--calib-frac", type=float, default=0.20,
                        help="Fraction of training data held out for calibration (default 0.20)")
    parser.add_argument("--no-external-features", action="store_true",
                        help="Disable external market features (US/VIX/TWII/institutional/margin/futures)")
    parser.add_argument("--tbrain-features", action="store_true",
                        help="Enable experimental TBrain-style KDJ/location/squash features")
    parser.add_argument("--no-tbrain-features", action="store_true",
                        help="Disable TBrain-style KDJ/location/squash feature additions")
    parser.add_argument("--fourier-features", action="store_true",
                        help="Enable Fourier trend-decomposition features (3/6/9 component dev+slope)")
    parser.add_argument("--no-fourier-features", action="store_true",
                        help="Disable Fourier trend features")
    parser.add_argument("--global-features", action="store_true",
                        help="Enable global correlated asset features (N225/HSI/USDJPY/KOSPI)")
    parser.add_argument("--no-global-features", action="store_true",
                        help="Disable global correlated asset features")
    parser.add_argument("--cascade", action="store_true",
                        help="Cascade H=1 calibrated probability as feature for H=5 (OOF to prevent leakage)")
    parser.add_argument("--feature-stability", action="store_true",
                        help="Run feature stability analysis (RF importance across TimeSeriesSplit folds)")
    parser.add_argument("--feature-stability-k", type=int, default=5,
                        help="Number of folds for feature stability analysis (default 5)")
    parser.add_argument(
        "--no-expanding-model-weights", dest="expanding_model_weights", action="store_false",
        help=(
            "Disable expanding-window per-model ensemble weights and restore the "
            "old single global weight over the whole validation set (pre-2026-07-07 "
            "behavior). Off by default means the fix is ON: default is expanding "
            "weights, since 2026-07-07 verification (results/ncf_00631l_panel_drift_"
            "verify_ON_v4_20260707.json vs GROUP_A_PLUS_NCF_PANEL_DRIFT_AUDIT_"
            "20260706.md) showed this eliminates the historical-panel-drift failure "
            "mode (max drift down from up to 0.48 to <=0.13 across all reported "
            "columns) at the cost of a small, understood AUC drop on the forward "
            "upside-reward task only (0.652->0.624; that task's base models are "
            "closely AUC-matched, so any weight-changing scheme trades a little of "
            "its accuracy for stability -- accepted for consistency with every "
            "other task rather than special-cased)."
        ),
    )
    parser.set_defaults(expanding_model_weights=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--val-predictions-output", default=None,
        help="If set, save per-day val prediction panel as CSV (enables A21.13 historical backtest)",
    )
    parser.add_argument(
        "--full-panel", action="store_true",
        help="Extend the panel to include the unlabeled tail (last H=20 trading days without forward labels).",
    )
    parser.add_argument(
        "--optuna-params", default=None,
        help="Path to ncf_optuna_best_params.json; overrides default LGB/XGB/HGB/RF hyperparameters.",
    )
    parser.add_argument(
        "--no-tabnet",
        action="store_true",
        help="Disable optional TabNet classifier training for faster daily panel generation.",
    )
    args = parser.parse_args()
    if args.no_tabnet:
        _HAS_TABNET = False
    use_tbrain_features = bool(args.tbrain_features and not args.no_tbrain_features)
    if use_tbrain_features:
        FEATURES[:] = FEATURES + [feature for feature in TBRAIN_FEATURES if feature not in FEATURES]
    use_fourier_features = bool(args.fourier_features and not args.no_fourier_features)
    if use_fourier_features:
        FEATURES[:] = FEATURES + [feature for feature in FOURIER_FEATURES if feature not in FEATURES]
    use_global_features = bool(args.global_features and not args.no_global_features)
    if use_global_features:
        EXT_FEATURES[:] = EXT_FEATURES + [f for f in GLOBAL_FEATURES + GLOBAL_INTERACTION_FEATURES if f not in EXT_FEATURES]

    db_path = Path(args.db)
    val_end = resolve_end_date(db_path, args.ticker, args.val_end)
    print(f"[NCF_00631L] Loading data from {db_path}")
    print(f"  Validation/data end: {val_end}")
    raw = load_data(db_path, args.ticker, args.train_start, val_end)
    print(f"  Raw rows: {len(raw)}, range: {raw.index[0].date()} ~ {raw.index[-1].date()}")

    # Load external features once (shared across all horizons) — on by default
    ext_df = None
    if not args.no_external_features:
        print(f"\n[ExtFeat] Downloading external market data...")
        ext_df = load_external_df(raw, db_path)
        # Warn if DB-sourced features are stale — query actual max date from DB
        last_date_raw = raw.index[-1]
        _con = duckdb.connect(str(db_path), read_only=True)
        _stale = {
            "外資買賣超": _con.execute(
                "SELECT MAX(dt) FROM institutional_data WHERE ticker='00631L.TW'"
            ).fetchone()[0],
            "融資融券": _con.execute(
                "SELECT MAX(dt) FROM margin_data WHERE ticker='00631L.TW'"
            ).fetchone()[0],
            "台指期夜盤": _con.execute(
                "SELECT MAX(dt) FROM taifex_futures_daily WHERE contract='TX' AND trading_session='盤後'"
            ).fetchone()[0],
        }
        _con.close()
        for name, max_dt in _stale.items():
            if max_dt is not None:
                lag = (last_date_raw.date() - max_dt).days
                if lag > 3:
                    print(f"  ⚠️  {name}: DB 最後日 {max_dt}，落後 {lag} 天（已填 0）")
        if use_global_features and ext_df is not None:
            print(f"  [GlobalFeat] Fetching N225/HSI/USDJPY/KOSPI...")
            _idx = raw.index
            _start_ext = ((_idx[0] - pd.Timedelta(days=90)).strftime("%Y-%m-%d"))
            _end_ext = ((_idx[-1] + pd.Timedelta(days=2)).strftime("%Y-%m-%d"))
            add_global_features(ext_df, _idx, _fetch_yf, _start_ext, _end_ext)

    # Load Optuna best params if provided
    _optuna_params: dict = {}
    if args.optuna_params:
        _op = Path(args.optuna_params)
        if _op.exists():
            _optuna_params = json.loads(_op.read_text(encoding="utf-8")).get("models", {})
            print(f"\n[Optuna] Loaded best params from {_op}")
            for _m, _r in _optuna_params.items():
                print(f"  {_m.upper():>5}: CV AUC={_r.get('best_auc', 0):.4f}")
        else:
            print(f"  ⚠️  --optuna-params file not found: {_op}")

    HORIZONS = [1, 5, 20]
    val_panels: dict = {}  # per-horizon val prediction panels (used if --val-predictions-output)
    all_clf_models: dict = {}  # stores trained classifiers per horizon for --full-panel tail extension
    _cascade_h1_train: pd.Series | None = None  # OOF H=1 probs for training set (cascade)
    _cascade_h1_val:   pd.Series | None = None  # H=1 probs for val set (cascade)
    # Features identified as unstable (Grade D) for specific horizons — drop before training
    HORIZON_DROP_FEATURES: dict[int, list[str]] = {
        1: ["close_open_ratio"],
        5: ["rsi_14"],
    }
    all_results = {}

    for h in HORIZONS:
        print(f"\n{'='*60}")
        # per-horizon labeling: auto → H=5 TBL, others simple
        if args.labeling == "auto":
            h_labeling = "triple_barrier" if h == 5 else "simple"
        else:
            h_labeling = args.labeling
        tbl_tag = f"[TBL×{args.tbl_mult}]" if h_labeling == "triple_barrier" else "[SIMPLE]"
        print(f"=== HORIZON {h} day{'s' if h > 1 else ''} {'[FS]' if args.feature_selection else ''}{tbl_tag}{'[EXT]' if ext_df is not None else ''} ===")
        print(f"{'='*60}")

        X, y_return, y_direction, available = build_dataset(
            raw, horizon=h, ext_df=ext_df,
            direction_threshold=args.direction_threshold,
            labeling=h_labeling,
            tbl_mult=args.tbl_mult,
        )

        train_mask = X.index < args.val_start
        val_mask = (X.index >= args.val_start) & (X.index <= val_end)
        X_train, y_train_ret = X[train_mask], y_return[train_mask]
        X_val, y_val_ret = X[val_mask], y_return[val_mask]
        y_train_dir = y_direction[train_mask].values
        # Val direction always binary for fair evaluation across all days
        y_val_dir = (y_return[val_mask] > 0).astype(int).values

        # NEUTRAL filter: remove noise-zone rows from classification training only
        clf_train_mask = y_train_dir != -1
        n_neutral_tr = (~clf_train_mask).sum()
        y_train_dir_clf = y_train_dir[clf_train_mask]   # only 0/1
        X_train_clf    = X_train[clf_train_mask]

        up_pct = (y_train_dir_clf == 1).mean()
        print(f"  Train: {len(X_train)} rows | Val: {len(X_val)} rows")
        if n_neutral_tr > 0:
            print(f"  NEUTRAL filtered: {n_neutral_tr} ({n_neutral_tr/len(X_train):.1%}) → "
                  f"clf train={len(X_train_clf)} rows")
        print(f"  Train direction: {(y_train_dir_clf==1).sum()} up / {(y_train_dir_clf==0).sum()} down ({up_pct:.1%} up)")

        # Feature selection — apply ONCE per horizon so all models share the same selected features
        # Regime columns are needed for regime split — preserve them separately
        regime_cols = ["above_ma200", "above_ma50", "above_ma20"]
        X_regime_train = X_train[regime_cols]
        X_regime_val = X_val[regime_cols]
        X_train_feat = X_train.drop(columns=regime_cols)
        X_val_feat = X_val.drop(columns=regime_cols)

        if args.feature_selection:
            X_train_sel, X_val_sel, sel_features = apply_feature_selection(
                X_train_feat, y_train_ret, X_val_feat)
            do_fs = False
        else:
            X_train_sel, X_val_sel = X_train_feat.copy(), X_val_feat.copy()
            sel_features = list(X_train_feat.columns)
            do_fs = False

        # Drop horizon-specific unstable features
        drop_cols = [c for c in HORIZON_DROP_FEATURES.get(h, []) if c in X_train_sel.columns]
        if drop_cols:
            X_train_sel = X_train_sel.drop(columns=drop_cols)
            X_val_sel   = X_val_sel.drop(columns=drop_cols)
            print(f"  Dropped unstable features for H={h}: {drop_cols}")

        # Add regime columns back
        X_train_sel[regime_cols] = X_regime_train.values
        X_val_sel[regime_cols] = X_regime_val.values

        # ── Cascade: inject H=1 prob as feature for H=5 ─────────────────
        if h == 5 and args.cascade and _cascade_h1_train is not None and _cascade_h1_val is not None:
            h1_tr = _cascade_h1_train.reindex(X_train_sel.index).fillna(0.5)
            h1_vl = _cascade_h1_val.reindex(X_val_sel.index).fillna(0.5)
            X_train_sel = X_train_sel.copy()
            X_val_sel   = X_val_sel.copy()
            X_train_sel.insert(0, "h1_prob_cascade", h1_tr.values)
            X_val_sel.insert(0,   "h1_prob_cascade", h1_vl.values)
            print(f"  [Cascade] h1_prob_cascade injected → H=5 feature count={X_train_sel.shape[1]}")

        # Overall regression
        reg_all = train_regressor(X_train_sel, y_train_ret, X_val_sel, y_val_ret, do_feature_selection=do_fs)
        print(f"\n  --- Regression (all) ---")
        for name in ["rf", "et", "elasticnet", "ensemble"]:
            r = reg_all[name]
            print(f"    {name:10s}  MAE={r['mae']:.6f}  R²={r['r2']:.4f}")

        # Regime split
        above_ma200_train = X_train_sel["above_ma200"] >= 0.5
        above_ma200_val = X_val_sel["above_ma200"] >= 0.5
        n_bull = above_ma200_val.sum()
        n_bear = (~above_ma200_val).sum()

        reg_bull = train_regressor(X_train_sel[above_ma200_train], y_train_ret[above_ma200_train],
                                   X_val_sel[above_ma200_val], y_val_ret[above_ma200_val],
                                   do_feature_selection=do_fs)
        # Bear regime: fall back to bull model when val has 0 bear samples (e.g. all-bull years)
        if (~above_ma200_val).sum() == 0 or (~above_ma200_train).sum() < 20:
            reg_bear = reg_bull
        else:
            reg_bear = train_regressor(X_train_sel[~above_ma200_train], y_train_ret[~above_ma200_train],
                                       X_val_sel[~above_ma200_val], y_val_ret[~above_ma200_val],
                                       do_feature_selection=do_fs)

        print(f"\n  --- Regime Regression ---")
        for regime, reg, n in [("Bull", reg_bull, n_bull), ("Bear", reg_bear, n_bear)]:
            print(f"    {regime:5s}  RF MAE={reg['rf']['mae']:.6f}  R²={reg['rf']['r2']:.4f}  |"
                  f"  ET MAE={reg['et']['mae']:.6f}  |  Ens MAE={reg['ensemble']['mae']:.6f}  (n={n})")

        # Classification per regime — use NEUTRAL-filtered training set
        X_train_clf_sel = X_train_sel[clf_train_mask]
        above_ma200_train_clf = X_train_clf_sel["above_ma200"] >= 0.5

        # H=20: compute stable features and pass to train_classifier
        stable_feats = None
        if h == 20:
            stable_feats = identify_stable_features(
                X_train_clf_sel, y_train_dir_clf, n_folds=3, top_k=20, min_folds=3
            )
            print(f"  Stable features ({len(stable_feats)}): {stable_feats[:8]}...")

        clf_bull = train_classifier(X_train_clf_sel[above_ma200_train_clf], y_train_dir_clf[above_ma200_train_clf],
                                    X_val_sel[above_ma200_val], y_val_dir[above_ma200_val],
                                    do_feature_selection=do_fs, stable_features=stable_feats,
                                    optuna_params=_optuna_params,
                                    calib_frac=args.calib_frac,
                                    horizon=h, expanding_model_weights=args.expanding_model_weights)
        # Bear regime: use bull model as fallback when val has 0 bear samples (e.g. all-bull years)
        if (~above_ma200_val).sum() == 0 or (~above_ma200_train_clf).sum() < 20:
            clf_bear = clf_bull
        else:
            clf_bear = train_classifier(X_train_clf_sel[~above_ma200_train_clf], y_train_dir_clf[~above_ma200_train_clf],
                                        X_val_sel[~above_ma200_val], y_val_dir[~above_ma200_val],
                                        do_feature_selection=do_fs, stable_features=stable_feats,
                                        optuna_params=_optuna_params,
                                        calib_frac=args.calib_frac,
                                        horizon=h, expanding_model_weights=args.expanding_model_weights)
        # Save for --full-panel tail extension
        all_clf_models[h] = {
            "bull": clf_bull, "bear": clf_bear,
            "sel_features": sel_features,
            "drop_cols": HORIZON_DROP_FEATURES.get(h, []),
        }

        # ── Cascade: after H=1, build OOF probs for H=5 input ──────────
        if h == 1 and args.cascade:
            # Val probs: combine bull/bear ensemble predictions
            bull_idx_v = X_val.index[above_ma200_val]
            bear_idx_v = X_val.index[~above_ma200_val]
            # When the bear-regime fallback above set clf_bear = clf_bull (thin
            # bear training data but a non-empty bear val slice -- see the
            # 2026-07-10 fix note near that assignment), clf_bull["ensemble"]["proba"]
            # is sized for the bull val slice and cannot be reused for bear_idx_v
            # without a length mismatch. Use a neutral (no-edge) placeholder instead.
            bear_p_v = (
                np.full(len(bear_idx_v), 0.5) if clf_bear is clf_bull else clf_bear["ensemble"]["proba"]
            )
            h1v = pd.concat([
                pd.Series(clf_bull["ensemble"]["proba"], index=bull_idx_v),
                pd.Series(bear_p_v, index=bear_idx_v),
            ]).sort_index()
            _cascade_h1_val = h1v

            # OOF probs for training: 3-fold time-series split on clf training set
            from sklearn.model_selection import TimeSeriesSplit
            from lightgbm import LGBMClassifier
            oof_probs = np.full(len(X_train_clf_sel), 0.5)
            tss3 = TimeSeriesSplit(n_splits=3)
            feat_cols = [c for c in X_train_clf_sel.columns if c not in ["above_ma200", "above_ma50", "above_ma20"]]
            for _tr, _te in tss3.split(X_train_clf_sel):
                _lgb = LGBMClassifier(n_estimators=200, learning_rate=0.05,
                                      num_leaves=31, random_state=42, verbose=-1)
                _lgb.fit(X_train_clf_sel[feat_cols].iloc[_tr].values, y_train_dir_clf[_tr])
                oof_probs[_te] = _lgb.predict_proba(X_train_clf_sel[feat_cols].iloc[_te].values)[:, 1]
            # Map clf indices back to full training index
            clf_train_idx = np.where(clf_train_mask)[0]
            h1_train_full = np.full(len(X_train), 0.5)
            h1_train_full[clf_train_idx] = oof_probs
            _cascade_h1_train = pd.Series(h1_train_full, index=X_train.index)
            print(f"  [Cascade] H=1 OOF probs generated: mean={_cascade_h1_train.mean():.3f}  "
                  f"val probs: mean={_cascade_h1_val.mean():.3f}")

        print(f"\n  --- Regime Classification ---")
        for regime, clf, n in [("Bull", clf_bull, n_bull), ("Bear", clf_bear, n_bear)]:
            active = list(clf["_models"].keys())
            best_name = max(active + ["ensemble"], key=lambda nm: clf[nm]["auc"])
            auc_parts = "  ".join(f"{nm.upper()}={clf[nm]['auc']:.4f}" for nm in active)
            print(f"    {regime:5s}  {auc_parts}  Ens={clf['ensemble']['auc']:.4f}  Best={best_name}  (n={n})")

        # Collect per-day val predictions for panel output (used when --val-predictions-output is set)
        if args.val_predictions_output:
            import pandas as _pd
            bull_idx = X_val.index[above_ma200_val]
            bear_idx = X_val.index[~above_ma200_val]
            bull_p = clf_bull["ensemble"]["proba"]
            # Bear-regime fallback (clf_bear = clf_bull, set above when bear
            # training data is too thin to fit its own model) means
            # clf_bull["ensemble"]["proba"] is sized for the bull val slice,
            # not bear_idx -- reusing it directly here crashes
            # (ValueError: length mismatch; first hit 2026-07-10 backfilling
            # ncf_00631l on 2017-2019 data, n_bull=605/n_bear=125). Use a
            # neutral (no-edge) probability for the bear slice in that case
            # instead of silently concatenating mismatched arrays.
            bear_p = np.full(len(bear_idx), 0.5) if clf_bear is clf_bull else clf_bear["ensemble"]["proba"]
            h_series = _pd.concat([
                _pd.Series(bull_p, index=bull_idx),
                _pd.Series(bear_p, index=bear_idx),
            ]).sort_index()
            h_label = _pd.concat([
                _pd.Series(np.asarray(y_val_dir[above_ma200_val]), index=bull_idx),
                _pd.Series(np.asarray(y_val_dir[~above_ma200_val]), index=bear_idx),
            ]).sort_index()
            n_total = n_bull + n_bear
            h_auc = (clf_bull["ensemble"]["auc"] * n_bull + clf_bear["ensemble"]["auc"] * n_bear) / max(n_total, 1)
            val_panels[h] = {"proba": h_series, "label": h_label, "auc": h_auc}

        # Prediction — use regime-appropriate models
        last_row = X.iloc[-1:].copy()
        # Cascade: inject H=1 prob into last_row for H=5 inference
        if h == 5 and args.cascade and 1 in all_results:
            h1_ens_proba = all_results[1].get("ens_proba", 0.5)
            last_row["h1_prob_cascade"] = h1_ens_proba
        last_close = float(raw["close"].iloc[-1])
        last_date = raw.index[-1].date()
        is_bull = bool(last_row["above_ma200"].values[0] >= 0.5)
        current_regime = "BULL" if is_bull else "BEAR"

        reg_sel = reg_bull if is_bull else reg_bear
        clf_sel = clf_bull if is_bull else clf_bear

        # Get features used by selected models and scaler
        sel_features = reg_sel["ensemble"]["features"]
        scaler = reg_sel["ensemble"]["scaler"]

        # Regression predictions (3-model ensemble: RF + ET + ElasticNet)
        last_sel = last_row[sel_features]
        last_sel_scaled = scaler.transform(last_sel) if scaler is not None else last_sel
        rf_ret = float(reg_sel["rf"]["model"].predict(last_sel)[0])
        et_ret = float(reg_sel["et"]["model"].predict(last_sel)[0])
        en_ret = float(reg_sel["elasticnet"]["model"].predict(last_sel_scaled)[0])
        raw_ens_ret = (rf_ret + et_ret + en_ret) / 3
        # Clip predictions to historically plausible bounds per horizon
        # H=1: ±2σ daily ≈ ±5.5%, use ±10% conservatively
        # H=5: 5th~95th historical = -8.6%~+9.7%, use ±12%
        # H=20: 5th~95th historical = -15.5%~+23.0%, use ±25%
        clip_bounds = {1: (-0.10, 0.10), 5: (-0.12, 0.12), 20: (-0.25, 0.25)}
        lo, hi = clip_bounds.get(h, (-0.25, 0.25))
        ens_ret = float(np.clip(raw_ens_ret, lo, hi))

        # Classification predictions — AUC-weighted ensemble, per-model feature sets
        W_inf = clf_sel["ensemble"]["weights"]
        model_probas = {}
        for nm, mdl in clf_sel["_models"].items():
            nm_feats = clf_sel[nm]["features"]
            nm_input = last_row[nm_feats]
            model_probas[nm] = float(mdl.predict_proba(nm_input)[0][1])
        ens_proba = sum(W_inf[nm] * model_probas[nm] for nm in W_inf)
        # NEUTRAL zone at inference matches training threshold
        _neut = args.direction_threshold * 10  # e.g., 0.5% → ±0.05 around 0.5
        if ens_proba >= 0.5 + _neut:
            direction = "UP"
        elif ens_proba <= 0.5 - _neut:
            direction = "DOWN"
        else:
            direction = "NEUTRAL"

        sigma_ret = np.std(y_val_ret[above_ma200_val if is_bull else ~above_ma200_val].values - reg_sel["ensemble"]["predictions"])

        proba_str = "  ".join(f"{nm.upper()}={p:.3f}" for nm, p in model_probas.items())
        weight_str = "  ".join(f"{nm.upper()}={W_inf[nm]:.2f}" for nm in W_inf)
        print(f"\n  [{current_regime}] Last close: {last_close:.2f}")
        print(f"  Regression: {ens_ret:+.4%} → {last_close*(1+ens_ret):.2f}  (RF={rf_ret:+.4%}  ET={et_ret:+.4%}  EN={en_ret:+.4%})")
        print(f"  Direction: {direction}  prob={ens_proba:.3f}  ({proba_str})")
        print(f"  Weights: {weight_str}")
        print(f"  68% CI: [{last_close*(1+ens_ret-sigma_ret):.2f}, {last_close*(1+ens_ret+sigma_ret):.2f}]")

        best_clf_name = max(list(clf_sel["_models"].keys()) + ["ensemble"], key=lambda nm: clf_sel[nm]["auc"])
        print(f"  Val MAE: {reg_sel['ensemble']['mae']*100:.2f}%  |  Best clf: {best_clf_name}  Acc={clf_sel[best_clf_name]['accuracy']:.4f}  AUC={clf_sel[best_clf_name]['auc']:.4f}")

        all_results[h] = {
            "reg": reg_sel, "clf": clf_sel,
            "is_bull": is_bull,
            "rf_ret": rf_ret, "et_ret": et_ret,
            "en_ret": en_ret,
            "ens_ret": ens_ret,
            "model_probas": model_probas,
            "ens_proba": ens_proba,
            "direction": direction,
            "sigma_ret": sigma_ret,
            "last_close": last_close,
            "last_date": last_date,
            "sel_features": sel_features,
            "best_clf_name": best_clf_name,
        }

    print(f"\n{'='*60}")
    print("=== FORWARD DRAWDOWN RISK: next 20d MDD > 5% ===")
    print(f"{'='*60}")
    drawdown_risk = train_forward_drawdown_risk(
        raw,
        ext_df,
        args.val_start,
        do_feature_selection=args.feature_selection,
        horizon=20,
        threshold=0.05,
        expanding_model_weights=args.expanding_model_weights,
    )
    if drawdown_risk.get("available"):
        print(
            "  P(fwd 20d MDD > 5%): "
            f"{drawdown_risk['probability']:.3f}  "
            f"AUC={drawdown_risk['auc']:.4f}  "
            f"val_pos={drawdown_risk['val_positive_rate']:.2%}"
        )
    else:
        print(f"  unavailable: {drawdown_risk.get('reason')}")

    print(f"\n{'='*60}")
    print("=== FORWARD UPSIDE REWARD: next 20d max gain > 5% ===")
    print(f"{'='*60}")
    upside_reward = train_forward_upside_reward(
        raw,
        ext_df,
        args.val_start,
        do_feature_selection=args.feature_selection,
        horizon=20,
        threshold=0.05,
        expanding_model_weights=args.expanding_model_weights,
    )
    if upside_reward.get("available"):
        print(
            "  P(fwd 20d gain > 5%): "
            f"{upside_reward['probability']:.3f}  "
            f"AUC={upside_reward['auc']:.4f}  "
            f"val_pos={upside_reward['val_positive_rate']:.2%}"
        )
    else:
        print(f"  unavailable: {upside_reward.get('reason')}")

    # --- Val Prediction Panel (for A21.13 historical backtest) ---
    if args.val_predictions_output and val_panels:
        import pandas as _pd, numpy as _np
        avail_h = sorted(val_panels.keys())
        panel_df = _build_expanding_horizon_ensemble_panel(
            {_h: val_panels[_h]["proba"] for _h in avail_h},
            {_h: val_panels[_h]["label"] for _h in avail_h if "label" in val_panels[_h]},
        )
        common_idx = panel_df.index
        # h20_only: most reliable single horizon — separate column for A21.13 conservative path
        if 20 in avail_h:
            panel_df["h20_prob_up"] = val_panels[20]["proba"].reindex(common_idx)
            panel_df["h20_direction"] = panel_df["h20_prob_up"].apply(lambda p: "UP" if p > 0.5 else "DOWN")
        for _h in avail_h:
            if "label" in val_panels[_h]:
                panel_df[f"actual_up_h{_h}"] = val_panels[_h]["label"].reindex(common_idx)
        if drawdown_risk.get("available"):
            panel_df["prob_fwd_mdd_gt5_h20"] = drawdown_risk["val_proba"].reindex(common_idx)
            panel_df["actual_fwd_mdd_gt5_h20"] = drawdown_risk["val_label"].reindex(common_idx)
            panel_df["forward_mdd_h20"] = drawdown_risk["val_forward_mdd"].reindex(common_idx)
        if upside_reward.get("available"):
            panel_df["prob_fwd_gain_gt5_h20"] = upside_reward["val_proba"].reindex(common_idx)
            panel_df["actual_fwd_gain_gt5_h20"] = upside_reward["val_label"].reindex(common_idx)
            panel_df["forward_gain_h20"] = upside_reward["val_forward_gain"].reindex(common_idx)
        if drawdown_risk.get("available") and upside_reward.get("available"):
            panel_df["tail_reward_risk_score_h20"] = (
                panel_df["prob_fwd_gain_gt5_h20"] - panel_df["prob_fwd_mdd_gt5_h20"]
            )
        panel_df["confidence"] = (panel_df["prob_magnitude"] * 0.6 + 0.4 * panel_df["prob_magnitude"].clip(0, 1))
        panel_df.index.name = "date"

        # --- Full panel: extend with unlabeled tail (dates without forward labels) ---
        if args.full_panel and all_clf_models:
            try:
                # Build full features (no label dropping)
                _full_feat = _build_features(raw.copy())
                if ext_df is not None:
                    for _col in ext_df.columns:
                        _full_feat[_col] = ext_df[_col].reindex(_full_feat.index)
                _full_feat = _add_interaction_features(_full_feat)

                _last_labeled = panel_df.index[-1]
                _tail = _full_feat[_full_feat.index > _last_labeled].copy()

                if not _tail.empty:
                    _REGIME_COLS = ["above_ma200", "above_ma50", "above_ma20"]
                    _tail_probs: dict[int, _pd.Series] = {}
                    for _h, _hm in all_clf_models.items():
                        _dc = _hm["drop_cols"]
                        # sel_features does NOT include regime_cols, but models were trained
                        # with regime_cols added back — include them here.
                        _sf = [f for f in _hm["sel_features"] if f not in _dc and f in _tail.columns]
                        _sf_full = _sf + [c for c in _REGIME_COLS if c in _tail.columns and c not in _sf]
                        _above = (_tail.get("above_ma200", _pd.Series(1.0, index=_tail.index)) >= 0.5)
                        _p = _pd.Series(_np.nan, index=_tail.index)
                        for _mask, _key in [(_above, "bull"), (~_above, "bear")]:
                            if _mask.sum() == 0:
                                continue
                            _sub = _tail.loc[_mask, _sf_full].fillna(0.0)
                            _clf = _hm[_key]
                            _W = _clf["ensemble"]["weights"]
                            _names = list(_clf["_models"].keys())
                            _ep = _np.zeros(len(_sub))
                            for _nm in _names:
                                _w = _W.get(_nm, 0.0)
                                if _w == 0.0:
                                    continue
                                # stable_rf uses a different (smaller) feature set
                                _nm_feats = _clf.get(_nm, {}).get("features")
                                _sub_nm = _sub[_nm_feats] if _nm_feats else _sub
                                try:
                                    _ep += _w * _clf["_models"][_nm].predict_proba(_sub_nm)[:, 1]
                                except Exception:
                                    pass
                            _p[_tail[_mask].index] = _ep
                        _tail_probs[_h] = _p

                    _avail_th = sorted(_tail_probs.keys())
                    _combined_probs = {
                        _h: _pd.concat([panel_df[f"prob_up_h{_h}"], _tail_probs[_h]])
                        for _h in _avail_th
                        if f"prob_up_h{_h}" in panel_df.columns
                    }
                    _combined_labels = {
                        _h: val_panels[_h]["label"].reindex(_combined_probs[_h].index)
                        for _h in _combined_probs
                        if _h in val_panels and "label" in val_panels[_h]
                    }
                    _combined_panel = _build_expanding_horizon_ensemble_panel(
                        _combined_probs,
                        _combined_labels,
                    )
                    _tail_df = _combined_panel.reindex(_tail.index)
                    _tail_df["confidence"] = (
                        _tail_df["prob_magnitude"] * 0.6
                        + 0.4 * _tail_df["prob_magnitude"].clip(0, 1)
                    )
                    if 20 in _avail_th:
                        _tail_df["h20_prob_up"] = _tail_probs[20]
                        _tail_df["h20_direction"] = _tail_df["h20_prob_up"].apply(lambda p: "UP" if p > 0.5 else "DOWN")
                    _tail_df["is_live"] = True
                    panel_df["is_live"] = False
                    panel_df = _pd.concat([panel_df, _tail_df], sort=False)
                    print(f"  [FULL PANEL] Extended by {len(_tail_df)} unlabeled tail rows → total {len(panel_df)}")
            except Exception as _e:
                print(f"  ⚠️  Full panel extension failed: {_e}")

        out_panel = Path(args.val_predictions_output)
        out_panel.parent.mkdir(parents=True, exist_ok=True)
        panel_df.to_csv(out_panel, encoding="utf-8-sig")
        print(f"\n[VAL PANEL] {len(panel_df)} rows → {out_panel.resolve()}")

    # --- Walk-Forward Evaluation ---
    if args.walk_forward:
        print(f"\n{'='*60}")
        print("=== WALK-FORWARD EVALUATION ===")
        print(f"{'='*60}")
        wf_all: dict = {}
        for h in HORIZONS:
            wf_labeling = ("triple_barrier" if h == 5 else "simple") if args.labeling == "auto" else args.labeling
            X_h, y_ret_h, y_dir_h, _ = build_dataset(
                raw, horizon=h, ext_df=ext_df,
                direction_threshold=args.direction_threshold,
                labeling=wf_labeling, tbl_mult=args.tbl_mult,
            )
            print(f"\n  Horizon {h}:")
            wf_all[h] = walk_forward_evaluate(X_h, y_ret_h, y_dir_h.values, horizon=h, n_windows=5)
        all_results["walk_forward"] = wf_all

    # --- Purged K-Fold + Embargo Evaluation ---
    if args.purged_cv:
        print(f"\n{'='*60}")
        print(f"=== PURGED K-FOLD + EMBARGO (k={args.purged_cv_k}) ===")
        print(f"{'='*60}")
        pkf_results = {}
        for h in HORIZONS:
            h_labeling = ("triple_barrier" if h == 5 else "simple") if args.labeling == "auto" else args.labeling
            X_h, y_ret_h, y_dir_h, _ = build_dataset(
                raw, horizon=h, ext_df=ext_df,
                direction_threshold=args.direction_threshold,
                labeling=h_labeling, tbl_mult=args.tbl_mult,
            )
            print(f"\n  H={h} ({h_labeling}, embargo={h}d):")
            # Compare purged-CV AUC vs current val AUC (single split)
            val_auc = all_results[h]["clf"]["ensemble"]["auc"]
            pkf = evaluate_purged_kfold(
                X_h, y_ret_h, y_dir_h.values,
                horizon=h, n_splits=args.purged_cv_k, embargo_bars=h,
            )
            print(f"  → Purged-CV Ens AUC: {pkf['avg_auc']['ensemble']:.4f}  "
                  f"(single-split val: {val_auc:.4f}  "
                  f"Δ={pkf['avg_auc']['ensemble'] - val_auc:+.4f})")
            pkf_results[h] = pkf
        all_results["purged_cv"] = pkf_results

    # --- Feature Stability Analysis ---
    if args.feature_stability:
        print(f"\n{'='*60}")
        print(f"=== FEATURE STABILITY (k={args.feature_stability_k}, RF importance) ===")
        print(f"{'='*60}")
        stability_results = {}
        for h in HORIZONS:
            h_labeling = ("triple_barrier" if h == 5 else "simple") if args.labeling == "auto" else args.labeling
            X_h, _, y_dir_h, _ = build_dataset(
                raw, horizon=h, ext_df=ext_df,
                direction_threshold=args.direction_threshold,
                labeling=h_labeling, tbl_mult=args.tbl_mult,
            )
            # Use full dataset (all regimes combined) on the TRAINING period
            X_train_h = X_h[X_h.index < args.val_start]
            y_dir_train_h = y_dir_h[X_h.index < args.val_start].values

            print(f"\n  H={h} (n={len(X_train_h)}, folds={args.feature_stability_k}):")
            stab = evaluate_feature_stability(
                X_train_h, y_dir_train_h,
                n_splits=args.feature_stability_k, top_n=15,
            )

            if "error" in stab:
                print(f"  Insufficient data: {stab['error']}")
                stability_results[h] = stab
                continue

            grade_emoji = {"A": "★★★", "B": "★★", "C": "★", "D": "☆"}.get(stab["stability_grade"], "")
            print(f"  Overall rank-corr: {stab['mean_rank_corr']:.3f}  "
                  f"Grade: {stab['stability_grade']} {grade_emoji}  "
                  f"Top-10 consistency: {stab['top10_consistency']:.0%}  "
                  f"(folds used: {stab['n_folds_used']})")
            print()
            print(f"  {'Feature':<28} {'Imp':>6}  {'CV':>5}  {'Rank±':>6}  {'Top10':>5}  Stability")
            print(f"  {'-'*28} {'-'*6}  {'-'*5}  {'-'*6}  {'-'*5}  ---------")
            for s in stab["feature_stats"]:
                bar  = "█" * int(s["mean_imp"] * 500)  # visual bar (50% → 25 chars max)
                bar  = bar[:12].ljust(12)                # cap at 12 chars
                flag = "  ⚠" if s["stability"] == "LOW" else ""
                print(f"  {s['feature']:<28} {s['mean_imp']:>6.4f}  {s['cv']:>5.2f}  "
                      f"{s['rank_std']:>6.1f}  {s['top10_freq']:>5}  "
                      f"{s['stability']:>4}{flag}")
            stability_results[h] = stab
        all_results["feature_stability"] = stability_results

    # --- Horizon Ensemble (confidence-aware voting) ---
    print(f"\n{'='*60}")
    print(f"=== HORIZON ENSEMBLE (confidence-aware) ===")
    print(f"{'='*60}")

    horizon_probs   = np.array([all_results[h]["ens_proba"] for h in HORIZONS])
    horizon_returns = np.array([all_results[h]["ens_ret"] for h in HORIZONS])
    horizon_maes    = np.array([all_results[h]["reg"]["ensemble"]["mae"] for h in HORIZONS])
    horizon_aucs    = np.array([all_results[h]["clf"]["ensemble"]["auc"] for h in HORIZONS])
    horizon_dirs    = np.array([1 if all_results[h]["direction"] == "UP" else 0 for h in HORIZONS])

    # Return weights: inverse-MAE² — rewards lower regression error
    inv_mae2_w = 1.0 / (horizon_maes ** 2)
    return_w   = inv_mae2_w / inv_mae2_w.sum()

    # Direction weights: AUC-based — rewards better discrimination power
    # w_i = max(0, AUC_i − 0.5)  same formula as per-model ensemble
    raw_auc_w = np.maximum(0.0, horizon_aucs - 0.5)
    dir_w = (raw_auc_w / raw_auc_w.sum()
             if raw_auc_w.sum() > 0
             else np.ones(len(HORIZONS)) / len(HORIZONS))

    # Combined probability uses AUC-based weights (direction quality → direction signal)
    combined_prob = float(np.dot(dir_w, horizon_probs))

    # --- Confidence signal ---
    # Component 1: Direction consensus (do all horizons agree on direction?)
    dir_votes = horizon_dirs.sum()  # 0-3
    max_votes = max(dir_votes, len(HORIZONS) - dir_votes)  # stronger of UP or DOWN
    consensus = max_votes / len(HORIZONS)  # 1.0 = all agree, 0.67 = 2/3, 0.33 = split

    # Component 2: Probability magnitude (far from 0.5 = more confident)
    prob_magnitude = abs(combined_prob - 0.5) * 2  # 0 to 1

    # Component 3: Spread between horizon probs (low spread = more confident)
    prob_std = float(np.std(horizon_probs))
    spread_conf = max(0, 1 - prob_std * 4)  # std=0.25 → 0, std=0 → 1

    # H2 (2026-07-02 Fable 5 audit, Option A): the composite `confidence`
    # below (consensus/magnitude/spread, clamped to [0.1, 1.0]) is a
    # different metric on a different scale than the panel CSV's
    # `prob_magnitude` column, which a2118's conf_min backtest calibration
    # was actually swept against -- observed to differ by ~18x on the same
    # day. `combined_prob` above also uses fixed per-horizon AUC weights
    # from this run's own validation set, not the panel's expanding-window
    # (walk-forward-through-calendar-time) AUC weights, so even the
    # underlying probability differs, not just the confidence formula.
    # Compute a panel-consistent value here (same val_panels source data,
    # same _build_expanding_horizon_ensemble_panel weighting) so live and
    # backtest can read the same number; a2118.py's trigger now reads this
    # instead of the composite `confidence` below.
    ensemble_prob_up_panel_aligned: float | None = None
    prob_magnitude_panel_aligned: float | None = None
    try:
        avail_h_live = sorted(val_panels.keys())
        if avail_h_live:
            panel_probs_live = {h: val_panels[h]["proba"] for h in avail_h_live}
            panel_labels_live = {
                h: val_panels[h]["label"] for h in avail_h_live if "label" in val_panels[h]
            }
            live_panel_row = _build_expanding_horizon_ensemble_panel(panel_probs_live, panel_labels_live)
            if len(live_panel_row):
                ensemble_prob_up_panel_aligned = float(live_panel_row["ensemble_prob_up"].iloc[-1])
                prob_magnitude_panel_aligned = float(live_panel_row["prob_magnitude"].iloc[-1])
    except Exception as _panel_align_exc:
        print(f"  ⚠️  panel-aligned confidence computation failed: {_panel_align_exc}")

    # Walk-forward H=1 RF accuracy as 4th confidence component (when --walk-forward was used).
    # Handoff 2026-06-25: switched from HGB (H=1 WF acc ~0.516, near-random) to RF
    # (H=1 WF acc ~0.683, best model across horizons).
    wf_acc_h1 = all_results.get("walk_forward", {}).get(1, {}).get("avg_accuracy", {})
    wf_h1_rf_acc: float | None = wf_acc_h1.get("rf")
    if wf_h1_rf_acc is not None:
        wf_conf = max(0.0, (wf_h1_rf_acc - 0.5) * 2)  # 0 at chance (50%), 1 at perfect
        confidence = (consensus * 0.35 + prob_magnitude * 0.35 + spread_conf * 0.15 + wf_conf * 0.15)
        print(f"  WF H=1 RF acc: {wf_h1_rf_acc:.4f} → WF conf component: {wf_conf:.3f}")
    else:
        wf_conf = None
        confidence = (consensus * 0.4 + prob_magnitude * 0.4 + spread_conf * 0.2)
    confidence = max(0.1, min(1.0, confidence))  # clamp to [0.1, 1.0]

    # Shrinkage: low confidence → pull toward 0.5, high confidence → stretch toward extremes
    # shrinkage_factor: 0=full shrink to 0.5, 1=no shrink
    shrinkage = 0.3 + 0.7 * confidence  # range [0.3, 1.0]
    calibrated_prob = 0.5 + (combined_prob - 0.5) * shrinkage
    calibrated_prob = max(0.01, min(0.99, calibrated_prob))

    direction_dir = "UP" if calibrated_prob >= 0.5 else "DOWN"

    print(f"  Confidence components: consensus={consensus:.2f} magnitude={prob_magnitude:.2f} spread={spread_conf:.2f}")
    print(f"  Confidence score: {confidence:.3f} (shrinkage={shrinkage:.2f})")
    print(f"  Raw combined prob: {combined_prob:.3f} → Calibrated: {calibrated_prob:.3f} → {direction_dir}")
    auc_str  = "  ".join(f"H{h}={dir_w[i]:.2f}(AUC={horizon_aucs[i]:.3f})"
                         for i, h in enumerate(HORIZONS))
    mae_str  = "  ".join(f"H{h}={return_w[i]:.2f}" for i, h in enumerate(HORIZONS))
    print(f"  Dir  weights (AUC):  {auc_str}")
    print(f"  Ret  weights (MAE²): {mae_str}")

    # Return: weighted by inverse-MAE²
    ens_horizon_ret = float(np.dot(return_w, horizon_returns))
    print(f"  Combined return: {ens_horizon_ret:+.4%} → {last_close*(1+ens_horizon_ret):.2f}")

    # Simple vote count
    dir_vote_count = int(dir_votes)
    print(f"  Vote count: UP={dir_vote_count}  DOWN={len(HORIZONS)-dir_vote_count}  →  {direction_dir}")

    # Low confidence warning
    if confidence < 0.4:
        print(f"  ⚠️  Low confidence ({confidence:.2f}) — signal may be unreliable")

    # Override return direction if confidence is very low (< 0.3) and direction is DOWN
    # Instead of DOWN with low confidence, stay neutral (use regression only)
    if confidence < 0.3 and direction_dir == "DOWN":
        direction_dir = "NEUTRAL"
        print(f"  ⚠️  Very low confidence DOWN → NEUTRAL (use regression signal only)")

    # --- Summary ---
    _base = pd.Timestamp(str(all_results[1]["last_date"]))
    print(f"\n{'='*60}")
    print(f"=== SUMMARY: {TICKER} ({all_results[1]['last_date']}) ===")
    print(f"{'='*60}")
    print(f"\n  {'Horizon':<10} {'Reg Return':>12} {'→ Price':>8} {'Direction':>8} {'Prob':>6} {'68% CI':>22}")
    print(f"  {'-'*10} {'-'*12} {'-'*8} {'-'*8} {'-'*6} {'-'*22}")
    for h in HORIZONS:
        r = all_results[h]
        last_close = r["last_close"]
        sigma = r["sigma_ret"]
        ret = r["ens_ret"]
        _pdate = (_base + pd.offsets.BDay(h)).strftime("%-m/%-d")
        print(f"  H={h:<6} {ret:>+11.2%} {last_close*(1+ret):>7.2f}  {r['direction']:>7}   {r['ens_proba']:.3f}   [{last_close*(1+ret-sigma):.2f}, {last_close*(1+ret+sigma):.2f}]  ({_pdate})")

    print(f"\n  Horizon Ensemble: {direction_dir}  (combined prob={combined_prob:.3f}, confidence={confidence:.2f})")
    print(f"  Weighted return: {ens_horizon_ret:+.4%} → {all_results[1]['last_close']*(1+ens_horizon_ret):.2f}")

    # --- Save ---
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    last_close = all_results[1]["last_close"]
    last_date = all_results[1]["last_date"]
    payload = {
        "ticker": TICKER,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "last_close_date": str(last_date),
        "last_close": round(last_close, 4),
        "current_regime": all_results[1]["is_bull"] and "BULL" or "BEAR",
        "data_freshness": ncf_data_freshness(db_path, TICKER, str(last_date)),
        "feature_selection": args.feature_selection,
        "external_features": not args.no_external_features,
        "tbrain_features": use_tbrain_features,
        "fourier_features": use_fourier_features,
        "global_features": use_global_features,
        "labeling_mode": args.labeling,
        "labeling_per_horizon": {
            str(h): (("triple_barrier" if h == 5 else "simple") if args.labeling == "auto" else args.labeling)
            for h in HORIZONS
        },
        "tbl_mult": args.tbl_mult,
        "direction_threshold": args.direction_threshold,
        "probability_calibration": all_results[1]["clf"]["_calib_info"],
        "models": {"regression": ["rf", "et", "elasticnet"],
                   "classification": list(all_results[1]["clf"]["_models"].keys())},
        "horizons": {},
        "horizon_ensemble": {
            "direction": direction_dir,
            "combined_probability_up": round(float(combined_prob), 4),
            "calibrated_probability_up": round(float(calibrated_prob), 4),
            "confidence": round(float(confidence), 4),
            # H2 (2026-07-02): panel-consistent alternative to the composite
            # `confidence` above -- see the comment above `prob_std`/
            # `spread_conf` for why these two metrics differ. a2118.py's
            # live trigger reads this field, not `confidence`.
            "ensemble_prob_up_panel_aligned": (
                round(ensemble_prob_up_panel_aligned, 4)
                if ensemble_prob_up_panel_aligned is not None
                else None
            ),
            "prob_magnitude_panel_aligned": (
                round(prob_magnitude_panel_aligned, 4)
                if prob_magnitude_panel_aligned is not None
                else None
            ),
            "shrinkage": round(float(shrinkage), 4),
            "weighted_return": round(ens_horizon_ret, 6),
            "predicted_close": round(last_close * (1 + ens_horizon_ret), 4),
            "votes_up": dir_vote_count,
            "direction_weights": {str(h): round(float(dir_w[i]), 4) for i, h in enumerate(HORIZONS)},
            "return_weights":    {str(h): round(float(return_w[i]), 4) for i, h in enumerate(HORIZONS)},
            "horizon_aucs":      {str(h): round(float(horizon_aucs[i]), 4) for i, h in enumerate(HORIZONS)},
            "wf_h1_rf_accuracy": round(wf_h1_rf_acc, 4) if wf_h1_rf_acc is not None else None,
            "wf_confidence_component": round(wf_conf, 4) if wf_conf is not None else None,
            "wf_confidence_used": wf_h1_rf_acc is not None,
        },
        "forward_drawdown_risk": {
            k: (
                round(float(v), 6)
                if isinstance(v, (float, np.floating))
                else v
            )
            for k, v in drawdown_risk.items()
            if k not in {"val_proba", "val_label", "val_forward_mdd"}
        },
        "forward_upside_reward": {
            k: (
                round(float(v), 6)
                if isinstance(v, (float, np.floating))
                else v
            )
            for k, v in upside_reward.items()
            if k not in {"val_proba", "val_label", "val_forward_gain"}
        },
        "tail_reward_risk_score": (
            round(float(upside_reward["probability"] - drawdown_risk["probability"]), 6)
            if upside_reward.get("available") and drawdown_risk.get("available")
            else None
        ),
    }
    for h in HORIZONS:
        r = all_results[h]
        # Dynamically compute prediction date by adding h business days to last_date
        _base = pd.Timestamp(str(last_date))
        pred_date = str((_base + pd.offsets.BDay(h)).date())
        sigma = r["sigma_ret"]
        payload["horizons"][str(h)] = {
            "prediction_date": pred_date,
            "regression": {
                "predicted_return": round(r["ens_ret"], 6),
                "predicted_close": round(last_close * (1 + r["ens_ret"]), 4),
                "model_returns": {"rf": round(r["rf_ret"], 6), "et": round(r["et_ret"], 6),
                                   "en": round(r["en_ret"], 6)},
                "val_mae_return": round(r["reg"]["ensemble"]["mae"], 8),
                "val_r2": round(r["reg"]["ensemble"]["r2"], 6),
                "confidence_68_return": {"low": round(r["ens_ret"] - sigma, 6), "high": round(r["ens_ret"] + sigma, 6)},
                "confidence_68_price": {"low": round(last_close * (1 + r["ens_ret"] - sigma), 4),
                                         "high": round(last_close * (1 + r["ens_ret"] + sigma), 4)},
            },
            "classification": {
                "direction": r["direction"],
                "probability_up": round(r["ens_proba"], 4),
                "model_probabilities": {nm: round(p, 4) for nm, p in r["model_probas"].items()},
                "ensemble_weights": {nm: round(w, 4) for nm, w in r["clf"]["ensemble"]["weights"].items()},
                "best_model": r["best_clf_name"],
                "val_accuracy": round(r["clf"][r["best_clf_name"]]["accuracy"], 4),
                "val_auc": round(r["clf"][r["best_clf_name"]]["auc"], 4),
                "val_auc_raw": round(r["clf"][r["best_clf_name"]].get("auc_raw", r["clf"][r["best_clf_name"]]["auc"]), 4),
                "ensemble_val_brier": round(r["clf"]["ensemble"]["brier"], 4),
                "model_brier": {nm: round(r["clf"][nm]["brier"], 4) for nm in r["clf"]["_models"]},
                "model_brier_raw": {nm: round(r["clf"][nm]["brier_raw"], 4) for nm in r["clf"]["_models"]},
            },
        }

    # Walk-forward results (when computed with --walk-forward)
    if "walk_forward" in all_results:
        payload["walk_forward"] = {
            str(h): {
                "avg_accuracy": {
                    nm: round(v, 4) for nm, v in res.get("avg_accuracy", {}).items()
                }
            }
            for h, res in all_results["walk_forward"].items()
        }
        # Best model averaged across all horizons by WF direction accuracy
        wf_model_avgs: dict[str, list[float]] = {}
        for h_res in all_results["walk_forward"].values():
            for nm, v in h_res.get("avg_accuracy", {}).items():
                wf_model_avgs.setdefault(nm, []).append(v)
        wf_final_avgs = {nm: float(np.mean(vs)) for nm, vs in wf_model_avgs.items() if vs}
        if wf_final_avgs:
            payload["wf_recommended_model"] = max(wf_final_avgs, key=wf_final_avgs.get)
            payload["wf_avg_accuracy_all_horizons"] = {nm: round(v, 4) for nm, v in wf_final_avgs.items()}

    # Feature importance from 1-day horizon
    rf_model = all_results[1]["reg"]["rf"]["model"]
    rf_importance = pd.Series(rf_model.feature_importances_,
                               index=rf_model.feature_names_in_).sort_values(ascending=False)
    payload["top_features"] = rf_importance.head(15).round(6).to_dict()

    # Feature stability results (if computed)
    if args.feature_stability and "feature_stability" in all_results:
        fs_payload = {}
        for h, stab in all_results["feature_stability"].items():
            if "error" in stab:
                fs_payload[str(h)] = stab
            else:
                fs_payload[str(h)] = {
                    "stability_grade":    stab["stability_grade"],
                    "mean_rank_corr":     round(stab["mean_rank_corr"], 4),
                    "top10_consistency":  round(stab["top10_consistency"], 4),
                    "n_folds_used":       stab["n_folds_used"],
                    "top_features": [
                        {k: (round(v, 5) if isinstance(v, float) else v)
                         for k, v in s.items()}
                        for s in stab["feature_stats"]
                    ],
                }
        payload["feature_stability"] = fs_payload

    if args.val_predictions_output:
        panel_reconciliation = reconcile_latest_panel_row(Path(args.val_predictions_output), payload)
        payload["val_panel_reconciliation"] = panel_reconciliation
        if panel_reconciliation.get("status") == "updated":
            print(
                f"\n[VAL PANEL] Reconciled latest row "
                f"{panel_reconciliation.get('date')} with JSON horizon payload"
            )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
