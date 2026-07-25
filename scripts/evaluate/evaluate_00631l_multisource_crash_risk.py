#!/usr/bin/env python3
"""Multi-source 00631L crash-risk feature test.

Research-only, 2026-07-12. This extends the direct ML crash-risk shadow with
feature families that are genuinely different from close/vol/chip-only
features:

1. TXO/options tail demand.
2. Liquidity / forced-selling stress.
3. Cross-market overnight/global shock proxies.

It evaluates each family alone, all families combined, and a simple
non-ML 2-of-3 ensemble veto. No live signal or target weight is changed.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices
from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _metrics
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_00631l_ml_crash_risk_derisk import (
    CRASH_LABELS,
    WINDOWS,
    _forecast_metrics,
    _resolve_end_date,
)
from scripts.evaluate.evaluate_group_a_plus_00631l_downside_oracle_ceiling import _label_max_drawdown
from scripts.evaluate.evaluate_group_a_plus_00631l_downside_race_classifier import (
    MIN_TRAIN_ROWS,
    REFIT_EVERY,
    TRAIN_WINDOW,
    _load_ohlc,
    _rolling_quantile_flag,
    _simulate_scaled_curve,
    _walkforward_predict,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "00631l_multisource_crash_risk_latest.json"
MIN_REASONABLE_SOXX_IV = 0.05
MAX_REASONABLE_SOXX_IV = 2.0

OPTIONS_COLS = [
    "txo_pcr_volume_z20",
    "txo_pcr_oi_z20",
    "txo_foreign_put_call_net_oi_z60",
    "txo_foreign_put_call_net_oi_chg5_z60",
    "tx_foreign_net_oi_z60",
    "tx_foreign_net_oi_chg5_z60",
]
LIQUIDITY_COLS = [
    "market_margin_flow_to_balance_5d_z60",
    "market_margin_balance_chg20_z252",
    "market_short_margin_ratio_z60",
    "market_margin_forced_repay_z60",
    "etf_margin_flow_0050_z60",
    "etf_margin_flow_00631l_z60",
    "securities_lending_0050_volume_z60",
]
CROSS_COLS = [
    "vix_level_z60",
    "vix_chg5_z60",
    "soxx_ret1",
    "soxx_ret5_z60",
    "soxx_realized_vol20_z60",
    "soxx_downside_vol20_z60",
    "vix_soxx_realized_vol_gap_z60",
    "soxx_atm_iv30_raw",
    "soxx_options_dte",
    "soxx_options_contract_count",
    "soxx_put_call_iv_skew_raw",
    "soxx_put_call_volume_ratio_raw",
    "soxx_put_call_oi_ratio_raw",
    "soxx_atm_iv30_z252",
    "soxx_iv_rank_252",
    "soxx_iv_minus_rv20_z252",
    "soxx_put_call_iv_skew_z252",
    "soxx_put_call_volume_ratio_z60",
    "soxx_put_call_oi_ratio_z60",
    "qqq_ret1",
    "twii_ret1",
    "us_taiwan_gap1",
    "tsm_adr_ret1",
    "usdtwd_ret5_z60",
]

FEATURE_SETS = {
    "options_tail": OPTIONS_COLS,
    "liquidity_forced_selling": LIQUIDITY_COLS,
    "cross_market_shock": CROSS_COLS,
    "all_multisource": OPTIONS_COLS + LIQUIDITY_COLS + CROSS_COLS,
}


def _zscore(s: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    minp = min_periods if min_periods is not None else max(10, window // 4)
    mean = s.rolling(window, min_periods=minp).mean()
    std = s.rolling(window, min_periods=minp).std().replace(0.0, np.nan)
    return ((s - mean) / std).replace([math.inf, -math.inf], np.nan)


def _load_options_features(db_path: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        opt = con.execute(
            """
            SELECT dt, call_put, volume, open_interest
            FROM taifex_options_daily
            WHERE contract = 'TXO' AND trading_session = '一般'
            ORDER BY dt
            """
        ).fetchdf()
        inst = con.execute(
            """
            SELECT dt, product_id, put_call, institutional_investors, net_open_interest_balance_volume
            FROM derivative_institutional_data
            WHERE product_id IN ('TX', 'TXO') AND institutional_investors = '外資'
            ORDER BY dt
            """
        ).fetchdf()
    finally:
        con.close()
    out = pd.DataFrame(index=index)
    if not opt.empty:
        opt["dt"] = pd.to_datetime(opt["dt"])
        piv_vol = opt.pivot_table(index="dt", columns="call_put", values="volume", aggfunc="sum")
        piv_oi = opt.pivot_table(index="dt", columns="call_put", values="open_interest", aggfunc="sum")
        put_vol = piv_vol.get("Put", piv_vol.get("賣權", pd.Series(0.0, index=piv_vol.index)))
        call_vol = piv_vol.get("Call", piv_vol.get("買權", pd.Series(0.0, index=piv_vol.index)))
        put_oi = piv_oi.get("Put", piv_oi.get("賣權", pd.Series(0.0, index=piv_oi.index)))
        call_oi = piv_oi.get("Call", piv_oi.get("買權", pd.Series(0.0, index=piv_oi.index)))
        pcr_vol = (put_vol / call_vol.replace(0.0, np.nan)).sort_index()
        pcr_oi = (put_oi / call_oi.replace(0.0, np.nan)).sort_index()
        out["txo_pcr_volume_z20"] = _zscore(pcr_vol.shift(1), 20).reindex(index)
        out["txo_pcr_oi_z20"] = _zscore(pcr_oi.shift(1), 20).reindex(index)
    if not inst.empty:
        inst["dt"] = pd.to_datetime(inst["dt"])
        txo = inst[inst["product_id"] == "TXO"]
        piv = txo.pivot_table(index="dt", columns="put_call", values="net_open_interest_balance_volume", aggfunc="sum")
        call_oi = piv.get("買權", pd.Series(0.0, index=piv.index))
        put_oi = piv.get("賣權", pd.Series(0.0, index=piv.index))
        pc_net = (put_oi - call_oi).sort_index()
        out["txo_foreign_put_call_net_oi_z60"] = _zscore(pc_net.shift(1), 60).reindex(index)
        out["txo_foreign_put_call_net_oi_chg5_z60"] = _zscore(pc_net.diff(5).shift(1), 60).reindex(index)
        tx = inst[inst["product_id"] == "TX"].set_index("dt")["net_open_interest_balance_volume"].sort_index()
        out["tx_foreign_net_oi_z60"] = _zscore(tx.shift(1), 60).reindex(index)
        out["tx_foreign_net_oi_chg5_z60"] = _zscore(tx.diff(5).shift(1), 60).reindex(index)
    return out


def _load_liquidity_features(db_path: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        market = con.execute("SELECT * FROM market_margin_data ORDER BY dt").fetchdf()
        margin = con.execute(
            "SELECT * FROM margin_data WHERE ticker IN ('0050.TW','00631L.TW') ORDER BY dt, ticker"
        ).fetchdf()
        lend = con.execute(
            "SELECT dt, ticker, volume FROM securities_lending_data WHERE ticker = '0050.TW' ORDER BY dt"
        ).fetchdf()
    finally:
        con.close()
    out = pd.DataFrame(index=index)
    if not market.empty:
        market["dt"] = pd.to_datetime(market["dt"])
        m = market.set_index("dt").sort_index()
        flow = (m["margin_buy"] - m["margin_sell"] - m["margin_repayment"]).rolling(5, min_periods=1).sum()
        flow_ratio = flow / m["margin_prev_balance"].rolling(5, min_periods=1).mean().replace(0.0, np.nan)
        short_ratio = m["short_balance"] / m["margin_balance"].replace(0.0, np.nan)
        forced_repay = m["margin_repayment"].rolling(5, min_periods=1).sum() / m["margin_prev_balance"].rolling(5, min_periods=1).mean().replace(0.0, np.nan)
        out["market_margin_flow_to_balance_5d_z60"] = _zscore(flow_ratio.shift(1), 60).reindex(index)
        out["market_margin_balance_chg20_z252"] = _zscore(m["margin_balance"].diff(20).shift(1), 252).reindex(index)
        out["market_short_margin_ratio_z60"] = _zscore(short_ratio.shift(1), 60).reindex(index)
        out["market_margin_forced_repay_z60"] = _zscore(forced_repay.shift(1), 60).reindex(index)
    if not margin.empty:
        margin["dt"] = pd.to_datetime(margin["dt"])
        for ticker in ("0050.TW", "00631L.TW"):
            part = margin[margin["ticker"] == ticker].set_index("dt").sort_index()
            flow = (part["margin_buy"] - part["margin_sell"] - part["margin_repayment"]).rolling(5, min_periods=1).sum()
            ratio = flow / part["margin_prev_balance"].rolling(5, min_periods=1).mean().replace(0.0, np.nan)
            out[f"etf_margin_flow_{ticker.replace('.TW','').lower()}_z60"] = _zscore(ratio.shift(1), 60).reindex(index)
    if not lend.empty:
        lend["dt"] = pd.to_datetime(lend["dt"])
        vol = lend.groupby("dt")["volume"].sum().sort_index()
        out["securities_lending_0050_volume_z60"] = _zscore(vol.shift(1), 60).reindex(index)
    return out


def _load_external_close(db_path: Path, tickers: list[str]) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            "SELECT ticker, dt, close FROM external_market_ohlcv WHERE ticker IN (%s) ORDER BY dt"
            % ",".join(["?"] * len(tickers)),
            tickers,
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def _load_external_options_iv_raw(db_path: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if "external_options_iv" not in tables:
            return pd.DataFrame(index=index)
        rows = con.execute(
            """
            SELECT
                dt,
                underlying,
                spot,
                dte,
                contract_count,
                atm_iv,
                put_call_iv_skew,
                put_call_volume_ratio,
                put_call_oi_ratio
            FROM external_options_iv
            WHERE provider = 'yfinance' AND underlying = 'SOXX'
            ORDER BY dt
            """
        ).fetchdf()
    finally:
        con.close()
    out = pd.DataFrame(index=index)
    if rows.empty:
        return out
    rows["dt"] = pd.to_datetime(rows["dt"])
    iv = rows.drop_duplicates(subset=["dt"], keep="last").set_index("dt").sort_index()
    return iv.reindex(index.union(iv.index)).sort_index().ffill().reindex(index)


def _load_external_options_iv(db_path: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    aligned = _load_external_options_iv_raw(db_path, index)
    out = pd.DataFrame(index=index)
    if aligned.empty or "atm_iv" not in aligned:
        return out
    atm_iv = pd.to_numeric(aligned["atm_iv"], errors="coerce")
    atm_iv = atm_iv.where((atm_iv >= MIN_REASONABLE_SOXX_IV) & (atm_iv <= MAX_REASONABLE_SOXX_IV))
    skew = pd.to_numeric(aligned["put_call_iv_skew"], errors="coerce")
    put_call_volume = pd.to_numeric(aligned["put_call_volume_ratio"], errors="coerce")
    put_call_oi = pd.to_numeric(aligned["put_call_oi_ratio"], errors="coerce")
    out["soxx_atm_iv30_raw"] = atm_iv.shift(1)
    out["soxx_options_dte"] = pd.to_numeric(aligned["dte"], errors="coerce").shift(1)
    out["soxx_options_contract_count"] = pd.to_numeric(aligned["contract_count"], errors="coerce").shift(1)
    out["soxx_put_call_iv_skew_raw"] = skew.shift(1)
    out["soxx_put_call_volume_ratio_raw"] = put_call_volume.shift(1)
    out["soxx_put_call_oi_ratio_raw"] = put_call_oi.shift(1)
    out["soxx_atm_iv30_z252"] = _zscore(atm_iv.shift(1), 252, min_periods=20)
    out["soxx_iv_rank_252"] = atm_iv.shift(1).rolling(252, min_periods=20).rank(pct=True)
    out["soxx_put_call_iv_skew_z252"] = _zscore(skew.shift(1), 252, min_periods=20)
    out["soxx_put_call_volume_ratio_z60"] = _zscore(put_call_volume.shift(1), 60, min_periods=10)
    out["soxx_put_call_oi_ratio_z60"] = _zscore(put_call_oi.shift(1), 60, min_periods=10)
    return out


def _load_cross_market_features(db_path: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    ext = _load_external_close(db_path, ["^VIX", "SOXX", "QQQ", "^TWII", "TSM", "TWD=X"])
    out = pd.DataFrame(index=index)
    aligned = ext.reindex(index.union(ext.index)).sort_index().ffill().reindex(index)
    iv_raw = _load_external_options_iv_raw(db_path, index)
    iv_features = _load_external_options_iv(db_path, index)
    if not iv_features.empty:
        out = pd.concat([out, iv_features], axis=1)
    if "^VIX" in aligned:
        vix = aligned["^VIX"].astype(float)
        out["vix_level_z60"] = _zscore(vix.shift(1), 60)
        out["vix_chg5_z60"] = _zscore(vix.pct_change(5).shift(1), 60)
    for ticker, prefix in (("SOXX", "soxx"), ("QQQ", "qqq"), ("^TWII", "twii"), ("TSM", "tsm_adr")):
        if ticker in aligned:
            ret1 = aligned[ticker].astype(float).pct_change(1).shift(1)
            out[f"{prefix}_ret1"] = ret1
            if prefix == "soxx":
                soxx_close = aligned[ticker].astype(float)
                soxx_ret = soxx_close.pct_change()
                soxx_realized_vol20 = soxx_ret.rolling(20, min_periods=10).std() * np.sqrt(252)
                soxx_downside_vol20 = soxx_ret.clip(upper=0.0).rolling(20, min_periods=10).std() * np.sqrt(252)
                out["soxx_ret5_z60"] = _zscore(soxx_close.pct_change(5).shift(1), 60)
                out["soxx_realized_vol20_z60"] = _zscore(soxx_realized_vol20.shift(1), 60)
                out["soxx_downside_vol20_z60"] = _zscore(soxx_downside_vol20.shift(1), 60)
                if "^VIX" in aligned:
                    # VIX is an implied-volatility proxy. Comparing it with SOXX
                    # realized volatility approximates the implied/realized risk
                    # spread when SOXX option-implied volatility is unavailable.
                    implied_realized_gap = aligned["^VIX"].astype(float) / 100.0 - soxx_realized_vol20
                    out["vix_soxx_realized_vol_gap_z60"] = _zscore(implied_realized_gap.shift(1), 60)
                if not iv_raw.empty and "atm_iv" in iv_raw:
                    out["soxx_iv_minus_rv20_z252"] = _zscore(
                        (pd.to_numeric(iv_raw["atm_iv"], errors="coerce") - soxx_realized_vol20).shift(1),
                        252,
                        min_periods=20,
                    )
    if "SOXX" in aligned and "^TWII" in aligned:
        out["us_taiwan_gap1"] = aligned["SOXX"].pct_change(1).shift(1) - aligned["^TWII"].pct_change(1).shift(1)
    if "TWD=X" in aligned:
        out["usdtwd_ret5_z60"] = _zscore(aligned["TWD=X"].astype(float).pct_change(5).shift(1), 60)
    return out


def build_multisource_features(db_path: Path, index: pd.DatetimeIndex) -> pd.DataFrame:
    parts = [
        _load_options_features(db_path, index),
        _load_liquidity_features(db_path, index),
        _load_cross_market_features(db_path, index),
    ]
    features = pd.concat(parts, axis=1)
    for col in OPTIONS_COLS + LIQUIDITY_COLS + CROSS_COLS:
        if col not in features:
            features[col] = np.nan
    return features.replace([math.inf, -math.inf], np.nan)


# Fable audit (2026-07-16, combination opportunities #6): these per-family
# stress thresholds used to be hardcoded three times independently -- here,
# in group_a_plus/integrations/trough_nowcast.py's capitulation-score
# conditions, and in scripts/run/build_00631l_crash_risk_alert.py's
# _category_flags(). All three copies still agreed, but nothing enforced
# that; this is the same failure mode that let the TSMC/0050 weight constant
# silently drift to three different hardcoded values elsewhere in the
# codebase. FAMILY_STRESS_CONDITIONS is now the single source of truth for
# the column/comparator/threshold triple behind every condition name; both
# downstream consumers import it (or the evaluate_family_condition /
# family_condition_flags_for_row helpers below) instead of re-typing numbers.
FamilyCondition = tuple[str, str, float]  # (column, comparator, threshold)

FAMILY_STRESS_CONDITIONS: dict[str, dict[str, FamilyCondition]] = {
    "options_tail": {
        "txo_pcr_volume_z20_ge_1": ("txo_pcr_volume_z20", ">=", 1.0),
        "txo_pcr_oi_z20_ge_1": ("txo_pcr_oi_z20", ">=", 1.0),
        "txo_foreign_put_call_net_oi_chg5_z60_ge_1": ("txo_foreign_put_call_net_oi_chg5_z60", ">=", 1.0),
    },
    "liquidity_forced_selling": {
        "market_margin_forced_repay_z60_ge_1": ("market_margin_forced_repay_z60", ">=", 1.0),
        "market_margin_balance_chg20_z252_le_minus_1": ("market_margin_balance_chg20_z252", "<=", -1.0),
        "securities_lending_0050_volume_z60_ge_1": ("securities_lending_0050_volume_z60", ">=", 1.0),
    },
    "cross_market_shock": {
        "vix_level_z60_ge_1": ("vix_level_z60", ">=", 1.0),
        "vix_chg5_z60_ge_1": ("vix_chg5_z60", ">=", 1.0),
        "soxx_ret1_le_minus_3pct": ("soxx_ret1", "<=", -0.03),
        "soxx_realized_vol20_z60_ge_1": ("soxx_realized_vol20_z60", ">=", 1.0),
        "soxx_downside_vol20_z60_ge_1": ("soxx_downside_vol20_z60", ">=", 1.0),
        "vix_soxx_realized_vol_gap_z60_ge_1": ("vix_soxx_realized_vol_gap_z60", ">=", 1.0),
        "soxx_atm_iv30_raw_ge_55pct": ("soxx_atm_iv30_raw", ">=", 0.55),
        "soxx_put_call_volume_ratio_raw_ge_3": ("soxx_put_call_volume_ratio_raw", ">=", 3.0),
        "soxx_put_call_oi_ratio_raw_ge_3": ("soxx_put_call_oi_ratio_raw", ">=", 3.0),
        "soxx_atm_iv30_z252_ge_1": ("soxx_atm_iv30_z252", ">=", 1.0),
        "soxx_iv_rank_252_ge_80pct": ("soxx_iv_rank_252", ">=", 0.8),
        "soxx_iv_minus_rv20_z252_ge_1": ("soxx_iv_minus_rv20_z252", ">=", 1.0),
        "soxx_put_call_iv_skew_z252_ge_1": ("soxx_put_call_iv_skew_z252", ">=", 1.0),
        "soxx_put_call_volume_ratio_z60_ge_1": ("soxx_put_call_volume_ratio_z60", ">=", 1.0),
        "soxx_put_call_oi_ratio_z60_ge_1": ("soxx_put_call_oi_ratio_z60", ">=", 1.0),
        "qqq_ret1_le_minus_2_5pct": ("qqq_ret1", "<=", -0.025),
        "us_taiwan_gap1_le_minus_3pct": ("us_taiwan_gap1", "<=", -0.03),
        "usdtwd_ret5_z60_ge_1": ("usdtwd_ret5_z60", ">=", 1.0),
    },
}


def evaluate_family_condition(value: Any, comparator: str, threshold: float) -> bool:
    if value is None or pd.isna(value):
        return False
    if comparator == ">=":
        return float(value) >= threshold
    if comparator == "<=":
        return float(value) <= threshold
    raise ValueError(f"unknown comparator: {comparator}")


def family_condition_flags_for_row(row: pd.Series, family: str) -> dict[str, bool]:
    """Per-condition booleans for one family, evaluated on a single feature row."""
    return {
        name: evaluate_family_condition(row.get(column), comparator, threshold)
        for name, (column, comparator, threshold) in FAMILY_STRESS_CONDITIONS[family].items()
    }


def _family_active_series(features: pd.DataFrame, family: str) -> pd.Series:
    active = pd.Series(False, index=features.index)
    for column, comparator, threshold in FAMILY_STRESS_CONDITIONS[family].values():
        if column not in features:
            continue
        condition = features[column] >= threshold if comparator == ">=" else features[column] <= threshold
        active = active | condition.fillna(False)
    return active


def _stress_veto_fraction(features: pd.DataFrame) -> pd.Series:
    options = _family_active_series(features, "options_tail")
    liquidity = _family_active_series(features, "liquidity_forced_selling")
    cross = _family_active_series(features, "cross_market_shock")
    score = options.astype(int) + liquidity.astype(int) + cross.astype(int)
    return (score >= 2).astype(float)


def _evaluate_trigger(
    *,
    name: str,
    derisk_fraction: pd.Series,
    pred_proba: pd.Series,
    label: pd.Series,
    db_path: Path,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> list[dict]:
    rows = []
    for kind, win_label, start, end, panel in WINDOWS:
        end_resolved = _resolve_end_date(db_path, end)
        try:
            report, frame = run_a2118(
                start=start,
                end=end_resolved,
                initial_value=initial_value,
                db=db_path,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                equity_etf_sell_tax=equity_etf_sell_tax,
                ncf_panel_631l_path=panel,
                h20_max=0.33,
                conf_min=0.55,
                h5_reentry_min=0.55,
                chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
                risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
                momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
                momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
            )
        except Exception as exc:
            rows.append({"kind": kind, "label": win_label, "status": "failed", "error": str(exc)})
            continue
        prices = _load_prices(db_path, list(TICKERS), start, end_resolved)
        total_return_prices, _ = _load_total_return_prices(db_path, prices.index)
        execution_regime = frame["execution_regime"].astype(str)
        baseline_metrics = dict(report["metrics"])
        baseline_execution = dict(report["execution"])
        forecast = _forecast_metrics(label.reindex(frame.index), pred_proba.reindex(frame.index), top_quantile=0.95)
        curve, sim = _simulate_scaled_curve(
            total_return_prices,
            execution_regime,
            derisk_fraction.reindex(frame.index).fillna(0.0),
            dict(report["base_weights"]["golden1"]),
            dict(report["base_weights"]),
            initial_value,
            commission_rate,
            slippage_rate,
            equity_etf_sell_tax,
            buckets=1,
        )
        metrics = _metrics(curve, initial_value)
        d = {
            "final_value": metrics["final_value"] - baseline_metrics["final_value"],
            "sharpe_ratio": metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"],
            "max_drawdown": metrics["max_drawdown"] - baseline_metrics["max_drawdown"],
        }
        row = {
            "kind": kind,
            "label": win_label,
            "status": "ok",
            "method": name,
            "forecast": forecast,
            "golden1_days": int((execution_regime == "golden1").sum()),
            "derisk_days_within_golden1": sim["days_with_derisk_gt0_golden1"],
            "delta_vs_baseline": d,
            "extra_transaction_cost": float(sim["transaction_cost"] - baseline_execution.get("transaction_cost", 0.0)),
        }
        rows.append(row)
        print(
            f"{name} [{kind}] {win_label}: auc={forecast['auc']} ap={forecast['average_precision']} "
            f"derisk={row['derisk_days_within_golden1']}/{row['golden1_days']} "
            f"delta_final={d['final_value']:.1f} delta_sharpe={d['sharpe_ratio']:.4f}"
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--feature-start", default="2016-01-04")
    parser.add_argument("--label", choices=list(CRASH_LABELS), default="10d_mdd_lt_5pct")
    parser.add_argument("--methods", default="options_tail,liquidity_forced_selling,cross_market_shock,all_multisource,ensemble_veto_2of3")
    parser.add_argument("--rolling-quantile-window", type=int, default=252)
    parser.add_argument("--rolling-quantile-level", type=float, default=0.95)
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    overall_end = _resolve_end_date(db_path, "latest")
    ohlc_631l = _load_ohlc(db_path, "00631L.TW", args.feature_start, overall_end)
    features = build_multisource_features(db_path, ohlc_631l.index)
    spec = CRASH_LABELS[args.label]
    future_mdd = _label_max_drawdown(ohlc_631l["close"].astype(float), spec["horizon"])
    label = (future_mdd < spec["threshold"]).astype(float)
    label[future_mdd.isna()] = float("nan")

    payload = {
        "experiment": "00631l_multisource_crash_risk",
        "label": {"name": args.label, **spec},
        "feature_coverage": {
            col: {
                "non_null": int(features[col].notna().sum()),
                "first": str(features[col].dropna().index.min().date()) if features[col].notna().any() else None,
                "last": str(features[col].dropna().index.max().date()) if features[col].notna().any() else None,
            }
            for col in OPTIONS_COLS + LIQUIDITY_COLS + CROSS_COLS
        },
        "methods": [],
    }
    for method in [m.strip() for m in args.methods.split(",") if m.strip()]:
        if method == "ensemble_veto_2of3":
            pred = _stress_veto_fraction(features)
            frac = pred
        else:
            cols = FEATURE_SETS[method]
            x = features[cols].fillna(0.0)
            pred = _walkforward_predict(
                x,
                label,
                train_window=TRAIN_WINDOW,
                refit_every=REFIT_EVERY,
                min_train_rows=MIN_TRAIN_ROWS,
                horizon=spec["horizon"],
            )
            frac = _rolling_quantile_flag(pred, args.rolling_quantile_window, args.rolling_quantile_level).astype(float)
        rows = _evaluate_trigger(
            name=method,
            derisk_fraction=frac,
            pred_proba=pred,
            label=label,
            db_path=db_path,
            initial_value=args.initial_value,
            commission_rate=args.commission_rate,
            slippage_rate=args.slippage_rate,
            equity_etf_sell_tax=args.equity_etf_sell_tax,
        )
        payload["methods"].append({"name": method, "feature_columns": FEATURE_SETS.get(method), "windows": rows})

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
