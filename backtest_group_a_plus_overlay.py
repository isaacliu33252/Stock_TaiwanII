#!/usr/bin/env python3
"""Approximate replay backtest for the GroupA+ portfolio overlay.

This does not retrain or rerun the underlying Group A agents. It replays the
selected Group A meta events, applies the GroupA+ portfolio controls, and
simulates close-to-close ETF returns with estimated transaction costs.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np


def _backtest_vix(actual_date: str) -> float | None:
    """Fetch VIX close <= actual_date. Returns None on failure."""
    try:
        end = (pd.Timestamp(actual_date) + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        df = yf.download("^VIX", start="2020-01-01", end=end, auto_adjust=True, progress=False) if False else None
        # Fallback: use yfinance if available
        import yfinance as yf2
        df = yf2.download("^VIX", start="2020-01-01", end=end, auto_adjust=True, progress=False)
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index).normalize()
        dates = df.index.strftime("%Y-%m-%d")
        mask = dates <= actual_date
        if not mask.any():
            return None
        return float(df.loc[mask, "Close"].iloc[-1])
    except Exception:
        return None


def _backtest_turbulence(prices_df: pd.DataFrame, current_date: str) -> float:
    """Calculate Mahalanobis turbulence from price DataFrame."""
    pivot = prices_df.loc[:current_date].copy()
    if len(pivot) < 60:
        return 0.0
    returns = pivot.pct_change().dropna()
    if returns.empty or returns.shape[1] < 2:
        return 0.0
    window = returns.iloc[-min(len(returns), 252):]
    if len(window) < 20:
        return 0.0
    try:
        cov = window.cov()
        current_ret = returns.iloc[-1].values
        inv_cov = pd.DataFrame(np.linalg.pinv(cov.values), cov.columns, cov.index)
        turbulence_val = float(current_ret @ inv_cov @ current_ret.T)
        return max(float(turbulence_val), 0.0)
    except Exception:
        return 0.0


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = PROJECT_ROOT / "results" / "group_a_meta_real_vote_tune_sweep_20250101_20260606_llmfilled.json"
DEFAULT_DCA_SOURCE = PROJECT_ROOT / "results" / "group_a_meta_ensemble_real_backtest_20250101_20260606_llmfilled.json"
DEFAULT_CONFIG = PROJECT_ROOT / "group_a_plus_config.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_overlay_backtest_20250102_20260605.json"
DEFAULT_VARIANT = "adaptive_momcash_price_severe12_vote_bearfilter_recovery_defense22"
DEFAULT_INITIAL_CASH = 1_000_000.0
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
CACHE_STEMS = {
    "0050.TW": "0050_TW",
    "00631L.TW": "00631L_TW",
    "00632R.TW": "00632R_TW",
    "00679B.TWO": "00679B_TWO",
}
PLUS_VARIANT_OVERRIDES: dict[str, dict[str, Any]] = {
    "live_return_guard": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.02, "risk_off": 0.04, "severe": 0.08},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.08, "caution": 0.08, "risk_off": 0.06, "severe": 0.03},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 0.70, "severe": 0.50},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 0.75, "severe": 0.50},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 0.60, "risk_off": 0.25, "severe": 0.25},
    },
    "current_dynamic": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.10, "caution": 0.15, "risk_off": 0.20, "severe": 0.25},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.08, "caution": 0.06, "risk_off": 0.04, "severe": 0.0},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 0.75, "risk_off": 0.50, "severe": 0.25},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
    },
    "balanced_dynamic": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.05, "caution": 0.10, "risk_off": 0.15, "severe": 0.20},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.08, "caution": 0.06, "risk_off": 0.04, "severe": 0.0},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 0.85, "risk_off": 0.65, "severe": 0.35},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 0.85, "risk_off": 0.65, "severe": 0.35},
    },
    "light_dynamic": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.05, "risk_off": 0.10, "severe": 0.15},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.08, "caution": 0.07, "risk_off": 0.05, "severe": 0.02},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 0.90, "risk_off": 0.75, "severe": 0.50},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 0.80, "risk_off": 0.60, "severe": 0.35},
    },
    "minimal_dynamic": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.03, "risk_off": 0.06, "severe": 0.10},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.08, "caution": 0.08, "risk_off": 0.06, "severe": 0.03},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 0.85, "severe": 0.65},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 0.75, "risk_off": 0.50, "severe": 0.25},
    },
    # ultra-conservative: minimize return drag to pass promotion gate
    # Target: drag > -2%, Sharpe delta > -0.03, vol reduction > 1%
    "shadow_conservative": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.02, "severe": 0.04},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.05, "caution": 0.05, "risk_off": 0.03, "severe": 0.01},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 0.95, "severe": 0.80},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 0.90, "risk_off": 0.30, "severe": 0.10},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 0.80, "risk_off": 0.10, "severe": 0.05},
    },
    # hedge_preserving: similar to shadow_conservative but with slightly higher risk_off weight
    "hedge_preserving": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.02, "risk_off": 0.03, "severe": 0.05},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.06, "caution": 0.06, "risk_off": 0.04, "severe": 0.02},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 0.90, "severe": 0.70},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 0.85, "risk_off": 0.40, "severe": 0.15},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 0.70, "risk_off": 0.12, "severe": 0.08},
    },
    # promotion_seeking: target drag< -2%, Sharpe delta > -0.03
    # Key: very low dynamic bands + near-zero turnover in risk_off
    "promotion_seeking": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.015, "severe": 0.03},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.04, "caution": 0.04, "risk_off": 0.02, "severe": 0.01},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 0.95, "risk_off": 0.20, "severe": 0.05},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 0.90, "risk_off": 0.05, "severe": 0.02},
    },
    # regime_stable: only trigger TDCC after 3 consecutive risk_off days (filters noise)
    "regime_stable": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.02, "severe": 0.04},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.05, "caution": 0.05, "risk_off": 0.03, "severe": 0.01},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 0.95, "severe": 0.80},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 0.90, "risk_off": 0.30, "severe": 0.10},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 0.80, "risk_off": 0.10, "severe": 0.05},
        "overlay.regime_stability_consecutive_days": 3,
    },
    # pure_bond_hedge: no TDCC selling of Group A equities.
    # Instead, shift allocation between 00679B and cash in the bond sleeve only.
    # Target: pass promotion gate by eliminating equity sell transaction costs.
    "pure_bond_hedge": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.02, "risk_off": 0.04, "severe": 0.06},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.00, "caution": 0.00, "risk_off": 0.00, "severe": 0.00},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 0.0, "caution": 0.0, "risk_off": 0.0, "severe": 0.0},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
    },
    # pure_bond_hedge_v2: same but with slightly higher risk_off bond allocation
    "pure_bond_hedge_v2": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.03, "risk_off": 0.05, "severe": 0.08},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.00, "caution": 0.00, "risk_off": 0.00, "severe": 0.00},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 0.0, "caution": 0.0, "risk_off": 0.0, "severe": 0.0},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
    },
    # no_leverage_drag: completely disable leverage for 00631L/00632R across all regimes.
    # The overlay should NOT touch leverage allocation - let Group A handle it.
    # Only add 00679B bond hedge in risk_off/severe regimes.
    "no_leverage_drag": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.00, "risk_off": 0.04, "severe": 0.06},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.00, "caution": 0.00, "risk_off": 0.00, "severe": 0.00},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 0.0, "severe": 0.0},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
    },
    # ultra_low_turnover: minimize all trading. Only rebalance when deviation > 5%.
    # Intended to pass promotion gate by eliminating transaction costs.
    "ultra_low_turnover": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.02, "severe": 0.04},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.04, "caution": 0.04, "risk_off": 0.02, "severe": 0.01},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 0.95, "risk_off": 0.50, "severe": 0.10},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 0.50, "caution": 0.50, "risk_off": 0.50, "severe": 0.50},
    },
    # bond_augment_only: Direction B - never sell Group A equities.
 # Only redirect new cash (DCA + released leverage) toward 00679B in risk_off/severe.
    # This eliminates equity sell transaction costs which were the main drag source.
    # Bond sleeve only grows, never shrinks.
    "bond_augment_only": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.02, "risk_off": 0.05, "severe": 0.08},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.00, "caution": 0.00, "risk_off": 0.00, "severe": 0.00},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 0.0, "caution": 0.0, "risk_off": 0.0, "severe": 0.0},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "overlay.bond_sleeve_never_shrink": True,
    },
    # no_overlay_final_optimize: Direction C - don't touch Group A signal at all.
    # Just cap leverage (00631L) to reduce volatility without changing equity exposure.
    # This tests whether the leverage cap alone can pass promotion gate.
    "no_overlay_final_optimize": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.00, "risk_off": 0.00, "severe": 0.00},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.08, "caution": 0.06, "risk_off": 0.04, "severe": 0.02},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
    },
    # zero_overhead: pure pass-through. risk_on cap=20% (> base max 19.5%), so cap never
    # binds in bull markets. Only caps in risk_off (8%) and severe (0%).
    # Bond sleeve=0, no second-stage, no VIX/turbulence.
    # This variant tests whether GroupA+ can achieve zero drag vs base.
    "zero_overhead": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.00, "risk_off": 0.00, "severe": 0.00},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.20, "caution": 0.15, "risk_off": 0.08, "severe": 0.00},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
    },
    # cap_guard_optimized: 2026-06-11 cap sweep winner.
    # Keep bull-market Group A behavior untouched, but remove 00631L entirely
    # once the base signal reaches risk_off. This improved final value and Sharpe
    # versus the base approximation in the 2025-2026 replay.
    "cap_guard_optimized": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.00, "risk_off": 0.00, "severe": 0.00},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.20, "caution": 0.18, "risk_off": 0.00, "severe": 0.00},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
    },
    # pure_zero_overhead: cap=20% for risk_on AND caution. risk_off=8%, severe=0%.
    # Base 00631L max=19.5% (risk_on) and 18% (caution). Neither will bind.
    # Bond sleeve=0, no overlay, no second-stage, no VIX/turbulence.
    "pure_zero_overhead": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.00, "risk_off": 0.00, "severe": 0.00},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.20, "caution": 0.20, "risk_off": 0.08, "severe": 0.00},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 1.0, "severe": 1.0},
    },
    # ultra_stable: regime stability filter = 5 days, moderate bond weights
    # Tests whether longer stability filter + balanced bond allocation can reduce
    # regime noise and transaction costs enough to beat base.
    "ultra_stable": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.02, "risk_off": 0.05, "severe": 0.08},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.08, "caution": 0.08, "risk_off": 0.05, "severe": 0.02},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 0.90, "severe": 0.70},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 0.75, "risk_off": 0.50, "severe": 0.25},
        "execution_control.max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 0.75, "risk_off": 0.30, "severe": 0.20},
        "overlay.regime_stability_consecutive_days": 5,
    },
    # minimal_stable: same as minimal_dynamic but WITH the regime stability filter
    # This isolates whether the stability filter itself (not parameter changes) helps.
    "minimal_stable": {
        "overlay.dynamic_weight_bands": {"risk_on": 0.00, "caution": 0.03, "risk_off": 0.06, "severe": 0.10},
        "leverage_control.max_weight_by_regime": {"risk_on": 0.08, "caution": 0.08, "risk_off": 0.06, "severe": 0.03},
        "execution_control.buy_fraction_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 0.85, "severe": 0.65},
        "execution_control.defensive_sleeve_sell_fraction_by_regime": {"risk_on": 1.0, "caution": 0.75, "risk_off": 0.50, "severe": 0.25},
        "overlay.regime_stability_consecutive_days": 3,
    },
}


def _add_focused_tdcc_variants() -> None:
    bands_by_name = {
        "0113": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.01, "severe": 0.03},
        "0114": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.01, "severe": 0.04},
        "0123": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.02, "severe": 0.03},
        "0124": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.02, "severe": 0.04},
        "0125": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.02, "severe": 0.05},
        "0134": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.03, "severe": 0.04},
        "0145": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.04, "severe": 0.05},
        "0224": {"risk_on": 0.00, "caution": 0.02, "risk_off": 0.02, "severe": 0.04},
        "0235": {"risk_on": 0.00, "caution": 0.02, "risk_off": 0.03, "severe": 0.05},
        "0245": {"risk_on": 0.00, "caution": 0.02, "risk_off": 0.04, "severe": 0.05},
        "0258": {"risk_on": 0.00, "caution": 0.02, "risk_off": 0.05, "severe": 0.08},
        # Direction B (2026-06-17): new bands testing wider severe coverage (0/1/3/5)
        # vs A15 baseline 0124 (0/1/2/4): wider risk_off(3% vs 2%)/severe(5% vs 4%)
        "0135": {"risk_on": 0.00, "caution": 0.01, "risk_off": 0.03, "severe": 0.05},
    }
    for band_name, bands in bands_by_name.items():
        for stability_days in (0, 2, 3, 5):
            PLUS_VARIANT_OVERRIDES[f"focused_tdcc_{band_name}_stab{stability_days}"] = {
                "overlay.dynamic_weight_bands": bands,
                "overlay.regime_stability_consecutive_days": stability_days,
                "leverage_control.max_weight_by_regime": {
                    "risk_on": 0.20,
                    "caution": 0.18,
                    "risk_off": 0.00,
                    "severe": 0.00,
                },
                "execution_control.buy_fraction_by_regime": {
                    "risk_on": 1.0,
                    "caution": 1.0,
                    "risk_off": 1.0,
                    "severe": 1.0,
                },
                "execution_control.defensive_sleeve_sell_fraction_by_regime": {
                    "risk_on": 1.0,
                    "caution": 1.0,
                    "risk_off": 1.0,
                    "severe": 1.0,
                },
                "execution_control.max_turnover_ratio_by_regime": {
                    "risk_on": 1.0,
                    "caution": 1.0,
                    "risk_off": 1.0,
                    "severe": 1.0,
                },
            }


_add_focused_tdcc_variants()


def _add_focused_execution_variants() -> None:
    focused_names = [
        name
        for name in PLUS_VARIANT_OVERRIDES
        if name.startswith("focused_tdcc_") and "_stab" in name and "_turn" not in name
    ]
    for base_name in focused_names:
        base = copy.deepcopy(PLUS_VARIANT_OVERRIDES[base_name])
        for cap in (0.50, 0.35, 0.25, 0.20, 0.18, 0.17, 0.16, 0.15, 0.14, 0.13, 0.12, 0.11, 0.10, 0.08):
            severe_cap = min(cap, 0.15)
            variant = copy.deepcopy(base)
            variant["execution_control.max_turnover_ratio_by_regime"] = {
                "risk_on": 1.0,
                "caution": 1.0,
                "risk_off": cap,
                "severe": severe_cap,
            }
            PLUS_VARIANT_OVERRIDES[f"{base_name}_turn{int(round(cap * 100)):02d}"] = variant
        for risk_off_cap, severe_cap in ((0.15, 0.08), (0.15, 0.10), (0.18, 0.08), (0.20, 0.08)):
            variant = copy.deepcopy(base)
            variant["execution_control.max_turnover_ratio_by_regime"] = {
                "risk_on": 1.0,
                "caution": 1.0,
                "risk_off": risk_off_cap,
                "severe": severe_cap,
            }
            PLUS_VARIANT_OVERRIDES[
                f"{base_name}_turn{int(round(risk_off_cap * 100)):02d}"
                f"_sev{int(round(severe_cap * 100)):02d}"
            ] = variant


_add_focused_execution_variants()


def _add_focused_stop_variants() -> None:
    specs = [
        ("stop_loose", -0.18, -0.15, 3),
        ("stop_base", -0.15, -0.12, 3),
        ("stop_fast", -0.12, -0.10, 3),
        ("stop_fast_cd2", -0.12, -0.10, 2),
        ("stop_mid_cd2", -0.15, -0.12, 2),
        ("stop_mid_cd5", -0.15, -0.12, 5),
        ("stop_abs_tight", -0.15, -0.10, 3),
        ("stop_trail_tight", -0.12, -0.12, 3),
        ("stop_disabled", None, None, None),
    ]
    focused_turn_names = [
        name
        for name in PLUS_VARIANT_OVERRIDES
        if name.startswith("focused_tdcc_") and "_stab" in name and "_turn" in name and "_stop_" not in name
    ]
    for base_name in focused_turn_names:
        base = copy.deepcopy(PLUS_VARIANT_OVERRIDES[base_name])
        for name, trailing, absolute, cooldown in specs:
            variant = copy.deepcopy(base)
            if trailing is None:
                variant["leverage_stop_cooldown.enabled"] = False
            else:
                variant["leverage_stop_cooldown.enabled"] = True
                variant["leverage_stop_cooldown.trailing_stop_pct"] = trailing
                variant["leverage_stop_cooldown.absolute_stop_pct"] = absolute
                variant["leverage_stop_cooldown.cooldown_days"] = cooldown
            PLUS_VARIANT_OVERRIDES[f"{base_name}_{name}"] = variant


_add_focused_stop_variants()


def _add_focused_fast_risk_off_variants() -> None:
    specs = [
        ("fast_disabled", {"fast_risk_off_control.enabled": False}),
        ("fast_loose", {"fast_risk_off_control.drawdown_threshold": -0.06}),
        ("fast_tight", {"fast_risk_off_control.drawdown_threshold": -0.04}),
        ("fast_cd3", {"fast_risk_off_control.duration_days": 3}),
        ("fast_cd2", {"fast_risk_off_control.duration_days": 2}),
        ("fast_cash20", {"fast_risk_off_control.cash_floor": 0.20}),
        ("fast_cash25", {"fast_risk_off_control.cash_floor": 0.25}),
    ]
    focused_turn_names = [
        name
        for name in PLUS_VARIANT_OVERRIDES
        if name.startswith("focused_tdcc_") and "_stab" in name and "_turn" in name and "_fast_" not in name
    ]
    for base_name in focused_turn_names:
        base = copy.deepcopy(PLUS_VARIANT_OVERRIDES[base_name])
        for suffix, overrides in specs:
            variant = copy.deepcopy(base)
            variant.update(overrides)
            PLUS_VARIANT_OVERRIDES[f"{base_name}_{suffix}"] = variant


_add_focused_fast_risk_off_variants()


def _add_focused_inverse_variants() -> None:
    """Direction 3: Add 00632R conditional inverse weight in severe regime.

    00632R is a 2x leveraged inverse ETF. In severe regime (large drawdown),
    adding a small inverse allocation can partially hedge 00631L leverage exposure.
    Sweep severe_inverse_weight from 0% to 10% to find optimal hedge ratio.
    """
    # Collect focused names that already have stability + execution + fast_risk_off
    focused_names = [
        name
        for name in PLUS_VARIANT_OVERRIDES
        if name.startswith("focused_tdcc_") and "_stab" in name and "_turn" in name and "_fast_" in name
    ]
    # Add a separate sweep for the 0135 band (Direction B new band)
    focused_names_0135 = [
        name
        for name in PLUS_VARIANT_OVERRIDES
        if name.startswith("focused_tdcc_0135_")
    ]
    for base_name in list(set(focused_names + focused_names_0135)):
        base = copy.deepcopy(PLUS_VARIANT_OVERRIDES[base_name])
        for sev_inv_pct in (0.03, 0.05, 0.08, 0.10):
            variant = copy.deepcopy(base)
            variant["inverse_control"] = {
                "enabled": True,
                "ticker": "00632R.TW",
                "severe_inverse_weight": sev_inv_pct,
            }
            PLUS_VARIANT_OVERRIDES[f"{base_name}_inv{int(sev_inv_pct*100):02d}"] = variant


_add_focused_inverse_variants()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument(
        "--dca-source",
        default=str(DEFAULT_DCA_SOURCE),
        help="Optional exact backtest JSON containing base_exact_backtest.dca_purchase_history.",
    )
    parser.add_argument(
        "--dca-scale",
        type=float,
        default=1.0,
        help="Scale DCA cash contributions for capital-policy sensitivity tests.",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--etf-sell-tax-rate", type=float, default=0.001)
    parser.add_argument(
        "--plus-variants",
        default="cap_guard_optimized,live_return_guard,current_dynamic,balanced_dynamic,light_dynamic,minimal_dynamic,shadow_conservative,hedge_preserving,promotion_seeking,regime_stable,pure_bond_hedge,pure_bond_hedge_v2,bond_augment_only,no_overlay_final_optimize,zero_overhead,pure_zero_overhead",
        help="Comma-separated GroupA+ overlay variants to replay.",
    )
    parser.add_argument(
        "--grid-sweep",
        action="store_true",
        help="Sweep risk-off 00679B, buy fraction, defensive sell fraction, and turnover cap.",
    )
    parser.add_argument("--grid-risk-off-bond", default="0.04,0.06,0.08,0.10")
    parser.add_argument("--grid-risk-off-buy", default="0.70,0.80,0.85,0.90")
    parser.add_argument("--grid-risk-off-bond-sell", default="0.25,0.50,0.75")
    parser.add_argument("--grid-risk-off-turnover-cap", default="0.25,0.30,0.35,0.40")
    return parser.parse_args()


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _latest_cache(ticker: str) -> Path:
    stem = CACHE_STEMS[ticker]
    cache_dir = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache"
    matches = sorted(cache_dir.glob(f"{stem}_20200101_*_1d_raw_v1.parquet"))
    if not matches:
        fallback = cache_dir / f"{stem}.parquet"
        if fallback.exists():
            return fallback
        raise FileNotFoundError(f"No cache parquet found for {ticker}")
    return matches[-1]


def _load_prices(start: str, end: str) -> pd.DataFrame:
    frames: list[pd.Series] = []
    for ticker in TICKERS:
        path = _latest_cache(ticker)
        df = pd.read_parquet(path)
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        series = df.set_index("date")["close"].astype(float).rename(ticker)
        frames.append(series)
    prices = pd.concat(frames, axis=1).sort_index()
    prices = prices.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    return prices.dropna(subset=TICKERS)


def _set_nested(config: dict[str, Any], dotted_key: str, value: Any) -> None:
    cursor = config
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = value


def _variant_config(base_config: dict[str, Any], variant_name: str) -> dict[str, Any]:
    if variant_name not in PLUS_VARIANT_OVERRIDES:
        raise ValueError(f"Unknown plus variant: {variant_name}")
    config = copy.deepcopy(base_config)
    for key, value in PLUS_VARIANT_OVERRIDES[variant_name].items():
        _set_nested(config, key, copy.deepcopy(value))
    return config


def _parse_plus_variants(value: str) -> list[str]:
    variants = [item.strip() for item in value.split(",") if item.strip()]
    if not variants:
        raise ValueError("--plus-variants must contain at least one variant")
    unknown = [name for name in variants if name not in PLUS_VARIANT_OVERRIDES]
    if unknown:
        raise ValueError(f"Unknown plus variants: {unknown}")
    return variants


def _parse_float_list(value: str) -> list[float]:
    out = sorted({float(item.strip()) for item in value.split(",") if item.strip()})
    if not out:
        raise ValueError("grid values must contain at least one number")
    return out


def _grid_variant_configs(
    base_config: dict[str, Any],
    *,
    risk_off_bonds: list[float],
    risk_off_buys: list[float],
    risk_off_bond_sells: list[float],
    risk_off_turnover_caps: list[float],
) -> dict[str, dict[str, Any]]:
    configs: dict[str, dict[str, Any]] = {}
    for bond in risk_off_bonds:
        for buy in risk_off_buys:
            for bond_sell in risk_off_bond_sells:
                for turnover_cap in risk_off_turnover_caps:
                    name = (
                        f"grid_b{int(round(bond * 100)):02d}"
                        f"_buy{int(round(buy * 100)):02d}"
                        f"_bsell{int(round(bond_sell * 100)):02d}"
                        f"_turn{int(round(turnover_cap * 100)):02d}"
                    )
                    config = copy.deepcopy(base_config)
                    _set_nested(
                        config,
                        "overlay.dynamic_weight_bands",
                        {
                            "risk_on": 0.0,
                            "caution": min(bond * 0.5, 0.05),
                            "risk_off": bond,
                            "severe": min(bond + 0.04, 0.15),
                        },
                    )
                    _set_nested(
                        config,
                        "leverage_control.max_weight_by_regime",
                        {
                            "risk_on": 0.08,
                            "caution": 0.08,
                            "risk_off": 0.06,
                            "severe": 0.03,
                        },
                    )
                    _set_nested(
                        config,
                        "execution_control.buy_fraction_by_regime",
                        {
                            "risk_on": 1.0,
                            "caution": 1.0,
                            "risk_off": buy,
                            "severe": max(buy - 0.20, 0.25),
                        },
                    )
                    _set_nested(
                        config,
                        "execution_control.defensive_sleeve_sell_fraction_by_regime",
                        {
                            "risk_on": 1.0,
                            "caution": min(bond_sell + 0.25, 1.0),
                            "risk_off": bond_sell,
                            "severe": max(bond_sell - 0.25, 0.0),
                        },
                    )
                    _set_nested(
                        config,
                        "execution_control.max_turnover_ratio_by_regime",
                        {
                            "risk_on": 1.0,
                            "caution": 0.60,
                            "risk_off": turnover_cap,
                            "severe": min(turnover_cap, 0.25),
                        },
                    )
                    configs[name] = config
    return configs


def _load_dca_history(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    source_path = _resolve(path)
    if not source_path.exists():
        return []
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if isinstance(payload.get("base_exact_backtest"), dict):
        history = payload["base_exact_backtest"].get("dca_purchase_history", [])
    else:
        history = payload.get("dca_purchase_history", [])
    return list(history or [])


def _scale_dca_history(dca_history: list[dict[str, Any]], scale: float) -> list[dict[str, Any]]:
    if abs(scale - 1.0) < 1e-12:
        return list(dca_history)
    if scale < 0:
        raise ValueError("--dca-scale must be non-negative")
    scaled = copy.deepcopy(dca_history)
    for item in scaled:
        item["total_contribution"] = float(item.get("total_contribution", 0.0)) * scale
        for purchase in dict(item.get("purchases", {}) or {}).values():
            for key in ("cash_contribution", "buy_value", "fee", "shares_bought"):
                if key in purchase:
                    purchase[key] = float(purchase[key]) * scale
    return scaled


def _dca_by_date(dca_history: list[dict[str, Any]]) -> dict[pd.Timestamp, list[dict[str, Any]]]:
    out: dict[pd.Timestamp, list[dict[str, Any]]] = {}
    for item in dca_history:
        out.setdefault(pd.Timestamp(item["date"]).normalize(), []).append(item)
    return out


def _apply_dca_purchases(
    dt: pd.Timestamp,
    price_row: pd.Series,
    shares: dict[str, float],
    cash: float,
    dca_map: dict[pd.Timestamp, list[dict[str, Any]]],
    *,
    commission_rate: float,
) -> tuple[float, float, float]:
    fees = 0.0
    contributions = 0.0
    for item in dca_map.get(dt, []):
        amount = float(item.get("total_contribution", 0.0))
        if amount <= 0:
            continue
        contributions += amount
        purchases = dict(item.get("purchases", {}) or {})
        if purchases:
            for ticker, purchase in purchases.items():
                if ticker not in shares or ticker not in price_row:
                    cash += float(purchase.get("cash_contribution", 0.0))
                    continue
                cash_contribution = float(purchase.get("cash_contribution", amount))
                fee = cash_contribution * commission_rate / (1.0 + commission_rate)
                buy_value = cash_contribution - fee
                shares[ticker] += buy_value / float(price_row[ticker])
                fees += fee
        else:
            cash += amount
    return cash, fees, contributions


def _metrics(
    values: pd.Series,
    *,
    rebalances: int,
    total_cost: float,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    contributions: float = 0.0,
) -> dict[str, Any]:
    daily = values.pct_change().dropna()
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1e-9)
    total_return = float(values.iloc[-1] / values.iloc[0] - 1.0)
    annual_return = float((values.iloc[-1] / values.iloc[0]) ** (1.0 / years) - 1.0)
    volatility = float(daily.std() * math.sqrt(252)) if len(daily) > 1 else 0.0
    sharpe = float((daily.mean() / daily.std()) * math.sqrt(252)) if len(daily) > 1 and daily.std() > 0 else 0.0
    max_drawdown = float((values / values.cummax() - 1.0).min())
    invested = float(initial_cash + contributions)
    return {
        "final_value": float(values.iloc[-1]),
        "total_return": total_return,
        "annual_return": annual_return,
        "volatility": volatility,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown,
        "num_rebalances": int(rebalances),
        "total_cost": float(total_cost),
        "dca_total_contributions": float(contributions),
        "total_invested_capital": invested,
        "net_profit": float(values.iloc[-1] - invested),
        "contribution_return": float((values.iloc[-1] - invested) / max(invested, 1.0)),
    }


def _plus_regime(
    row: dict[str, Any],
    *,
    vix: float | None = None,
    turbulence: float | None = None,
    vix_cfg: dict[str, Any] | None = None,
    turb_cfg: dict[str, Any] | None = None,
) -> str:
    regime = str(row.get("regime") or "").lower()
    state = str(row.get("tdcc_state") or "").lower()
    if regime == "risk_on" or state in {"normal", "risk_on"}:
        base = "risk_on"
    elif regime in {"neutral", "caution"} or state == "caution":
        base = "caution"
    elif regime == "severe" or state == "severe":
        base = "severe"
    elif regime == "risk_off" or state == "risk_off":
        base = "risk_off"
    else:
        base = "risk_on"

    # FinRL-Meta VIX upgrade
    if vix is not None and vix_cfg:
        vth = float(vix_cfg.get("threshold_risk_off", 25.0))
        sth = float(vix_cfg.get("threshold_severe", 35.0))
        if vix >= sth and base in {"risk_on", "caution"}:
            base = "severe"
        elif vix >= vth and base == "risk_on":
            base = "risk_off"

    # FinRL-Meta turbulence upgrade
    if turbulence is not None and turb_cfg:
        tth = float(turb_cfg.get("threshold_risk_off", 50.0))
        sth = float(turb_cfg.get("threshold_severe", 100.0))
        if turbulence >= sth and base in {"risk_on", "caution", "risk_off"}:
            base = "severe"
        elif turbulence >= tth and base == "risk_on":
            base = "risk_off"

    return base


def _fast_risk_off_overlay(
    prices: pd.DataFrame,
    current_date: pd.Timestamp,
    config: dict[str, Any],
    *,
    active_until: pd.Timestamp | None = None,
) -> tuple[str | None, pd.Timestamp | None, dict[str, Any]]:
    cfg = dict(config.get("fast_risk_off_control", {}) or {})
    if not cfg.get("enabled", False):
        return None, active_until, {"enabled": False, "active": False}

    reference_ticker = str(cfg.get("reference_ticker", "0050.TW"))
    lookback_days = int(cfg.get("lookback_days", 3))
    drawdown_threshold = float(cfg.get("drawdown_threshold", -0.03))
    duration_days = int(cfg.get("duration_days", 5))
    override_regime = str(cfg.get("override_regime", "risk_off"))
    cap_ticker = str(cfg.get("cap_ticker", "00631L.TW"))
    cap_weight = float(cfg.get("cap_weight", 0.0))
    cash_floor = cfg.get("cash_floor")

    if active_until is not None and current_date <= active_until:
        return override_regime, active_until, {
            "enabled": True,
            "active": True,
            "reason": "cooldown_active",
            "active_until": str(active_until.date()),
            "override_regime": override_regime,
            "cap_ticker": cap_ticker,
            "cap_weight": cap_weight,
            "cash_floor": cash_floor,
        }

    if reference_ticker not in prices.columns:
        return None, None, {
            "enabled": True,
            "active": False,
            "reason": "reference_ticker_missing",
            "reference_ticker": reference_ticker,
        }

    series = prices.loc[:current_date, reference_ticker].dropna()
    if len(series) < lookback_days + 1:
        return None, None, {
            "enabled": True,
            "active": False,
            "reason": "insufficient_history",
            "reference_ticker": reference_ticker,
            "lookback_days": lookback_days,
        }

    current_price = float(series.iloc[-1])
    prior_price = float(series.iloc[-(lookback_days + 1)])
    lookback_return = current_price / prior_price - 1.0 if prior_price > 0 else 0.0
    triggered = lookback_return <= drawdown_threshold
    if not triggered:
        return None, None, {
            "enabled": True,
            "active": False,
            "reason": "not_triggered",
            "reference_ticker": reference_ticker,
            "lookback_return": lookback_return,
            "drawdown_threshold": drawdown_threshold,
        }

    new_until = current_date + pd.tseries.offsets.BDay(duration_days)
    return override_regime, pd.Timestamp(new_until).normalize(), {
        "enabled": True,
        "active": True,
        "reason": "price_shock_triggered",
        "reference_ticker": reference_ticker,
        "lookback_days": lookback_days,
        "lookback_return": lookback_return,
        "drawdown_threshold": drawdown_threshold,
        "active_until": str(pd.Timestamp(new_until).date()),
        "override_regime": override_regime,
        "cap_ticker": cap_ticker,
        "cap_weight": cap_weight,
        "cash_floor": cash_floor,
    }


def _leverage_stop_cooldown_overlay(
    prices: pd.DataFrame,
    current_date: pd.Timestamp,
    config: dict[str, Any],
    *,
    active_until: pd.Timestamp | None = None,
) -> tuple[pd.Timestamp | None, dict[str, Any]]:
    cfg = dict(config.get("leverage_stop_cooldown", {}) or {})
    if not cfg.get("enabled", False):
        return active_until, {"enabled": False, "active": False}

    ticker = str(cfg.get("ticker", "00631L.TW"))
    lookback_days = int(cfg.get("lookback_days", 20))
    trailing_stop_pct = float(cfg.get("trailing_stop_pct", -0.10))
    absolute_lookback_days = int(cfg.get("absolute_lookback_days", 5))
    absolute_stop_pct = float(cfg.get("absolute_stop_pct", -0.08))
    cooldown_days = int(cfg.get("cooldown_days", 5))
    cap_weight = float(cfg.get("cap_weight", 0.0))

    if active_until is not None and current_date <= active_until:
        return active_until, {
            "enabled": True,
            "active": True,
            "reason": "cooldown_active",
            "ticker": ticker,
            "active_until": str(active_until.date()),
            "cap_weight": cap_weight,
        }

    if ticker not in prices.columns:
        return None, {
            "enabled": True,
            "active": False,
            "reason": "ticker_missing",
            "ticker": ticker,
        }

    series = prices.loc[:current_date, ticker].dropna()
    min_required = max(lookback_days, absolute_lookback_days) + 1
    if len(series) < min_required:
        return None, {
            "enabled": True,
            "active": False,
            "reason": "insufficient_history",
            "ticker": ticker,
        }

    current_price = float(series.iloc[-1])
    peak_price = float(series.iloc[-lookback_days:].max())
    drawdown_from_peak = current_price / peak_price - 1.0 if peak_price > 0 else 0.0
    prior_price = float(series.iloc[-(absolute_lookback_days + 1)])
    absolute_return = current_price / prior_price - 1.0 if prior_price > 0 else 0.0
    triggered = drawdown_from_peak <= trailing_stop_pct or absolute_return <= absolute_stop_pct
    if not triggered:
        return None, {
            "enabled": True,
            "active": False,
            "reason": "not_triggered",
            "ticker": ticker,
            "drawdown_from_peak": drawdown_from_peak,
            "trailing_stop_pct": trailing_stop_pct,
            "absolute_return": absolute_return,
            "absolute_stop_pct": absolute_stop_pct,
        }

    new_until = current_date + pd.tseries.offsets.BDay(cooldown_days)
    reason = "trailing_stop_triggered" if drawdown_from_peak <= trailing_stop_pct else "absolute_stop_triggered"
    return pd.Timestamp(new_until).normalize(), {
        "enabled": True,
        "active": True,
        "reason": reason,
        "ticker": ticker,
        "drawdown_from_peak": drawdown_from_peak,
        "trailing_stop_pct": trailing_stop_pct,
        "absolute_return": absolute_return,
        "absolute_stop_pct": absolute_stop_pct,
        "active_until": str(pd.Timestamp(new_until).date()),
        "cap_weight": cap_weight,
    }


def _apply_group_a_plus_risk_overlays(
    weights: dict[str, float],
    cash_weight: float,
    *,
    fast_report: dict[str, Any],
    stop_report: dict[str, Any],
) -> tuple[dict[str, float], float, dict[str, Any]]:
    adjusted = dict(weights)
    cash = float(cash_weight)
    actions: list[dict[str, Any]] = []

    for report in (fast_report, stop_report):
        if not report.get("active"):
            continue
        ticker = str(report.get("cap_ticker") or report.get("ticker") or "00631L.TW")
        cap_weight = float(report.get("cap_weight", 0.0))
        before = float(adjusted.get(ticker, 0.0))
        if before > cap_weight:
            released = before - cap_weight
            adjusted[ticker] = cap_weight
            cash += released
            actions.append(
                {
                    "type": "cap_weight",
                    "source": report.get("reason"),
                    "ticker": ticker,
                    "before_weight": before,
                    "after_weight": cap_weight,
                    "released_to_cash": released,
                }
            )

    cash_floor = fast_report.get("cash_floor") if fast_report.get("active") else None
    if cash_floor is not None:
        cash_floor = float(cash_floor)
        if cash < cash_floor:
            deficit = cash_floor - cash
            invested = sum(max(float(v), 0.0) for v in adjusted.values())
            if invested > 0:
                scale = max((invested - deficit) / invested, 0.0)
                adjusted = {ticker: max(float(weight) * scale, 0.0) for ticker, weight in adjusted.items()}
                cash = 1.0 - sum(adjusted.values())
                actions.append(
                    {
                        "type": "cash_floor",
                        "cash_floor": cash_floor,
                        "scale": scale,
                    }
                )

    adjusted, cash = _normalize(adjusted, cash)
    return adjusted, cash, {
        "fast_risk_off": fast_report,
        "leverage_stop_cooldown": stop_report,
        "actions": actions,
        "applied": bool(actions),
    }


def _normalize(weights: dict[str, float], cash: float) -> tuple[dict[str, float], float]:
    cleaned = {ticker: max(float(weights.get(ticker, 0.0)), 0.0) for ticker in TICKERS}
    cash = max(float(cash), 0.0)
    total = cash + sum(cleaned.values())
    if total <= 0:
        return {ticker: 0.0 for ticker in TICKERS}, 1.0
    return {ticker: value / total for ticker, value in cleaned.items()}, cash / total


def _group_a_plus_target(
    event: dict[str, Any],
    regime: str,
    config: dict[str, Any],
) -> tuple[dict[str, float], float, dict[str, Any]]:
    overlay = dict(config.get("overlay", {}) or {})
    bands = dict(overlay.get("dynamic_weight_bands", {}) or {})
    bond_weight = float(bands.get(regime, bands.get("risk_off", 0.20)))
    group_sleeve = 1.0 - bond_weight

    base_weights = {ticker: float(dict(event.get("target_weights", {}) or {}).get(ticker, 0.0)) for ticker in TICKERS}
    base_cash = float(event.get("target_cash_weight", 0.0))
    base_weights, base_cash = _normalize(base_weights, base_cash)

    control = dict(config.get("leverage_control", {}) or {})
    lev_ticker = str(control.get("ticker") or "00631L.TW")
    caps = dict(control.get("max_weight_by_regime", {}) or {})
    cap = float(caps.get(regime, caps.get("risk_off", base_weights.get(lev_ticker, 0.0))))
    before_leverage = float(base_weights.get(lev_ticker, 0.0))
    released = max(before_leverage - cap, 0.0)
    if released > 0:
        base_weights[lev_ticker] = cap
        base_cash += released
        base_weights, base_cash = _normalize(base_weights, base_cash)

    target = {ticker: group_sleeve * base_weights.get(ticker, 0.0) for ticker in TICKERS}
    target["00679B.TWO"] = bond_weight
    target_cash = group_sleeve * base_cash

    # Direction 3: Add 00632R inverse allocation in severe regime
    inverse_cfg = dict(config.get("inverse_control") or {})
    inverse_report: dict[str, Any] = {"enabled": False}
    if inverse_cfg.get("enabled") and regime == "severe":
        sev_inv = float(inverse_cfg.get("severe_inverse_weight", 0.0))
        if sev_inv > 0:
            inv_ticker = str(inverse_cfg.get("ticker", "00632R.TW"))
            inv_before = float(target.get(inv_ticker, 0.0))
            deficit = min(sev_inv - inv_before, sev_inv)
            if deficit > 0:
                # Pull from other positions proportionally
                other_total = sum(v for k, v in target.items() if k != inv_ticker)
                for t in TICKERS:
                    if other_total > 0 and target.get(t, 0.0) > 0:
                        reduction = deficit * target[t] / other_total
                        target[t] = max(target[t] - reduction, 0.0)
                target[inv_ticker] = inv_before + deficit
            inverse_report = {"enabled": True, "severe_inverse_weight": sev_inv, "inverse_ticker": inv_ticker, "inverse_before": inv_before}

    target, target_cash = _normalize(target, target_cash)
    return target, target_cash, {
        "regime": regime,
        "bond_weight": bond_weight,
        "group_sleeve": group_sleeve,
        "leverage_ticker": lev_ticker,
        "leverage_cap": cap,
        "leverage_before": before_leverage,
        "leverage_released_to_cash": released,
        "inverse_control": inverse_report,
    }


def _apply_staged_execution(
    current_weights: dict[str, float],
    target_weights: dict[str, float],
    target_cash: float,
    regime: str,
    config: dict[str, Any],
) -> tuple[dict[str, float], float, dict[str, Any]]:
    control = dict(config.get("execution_control", {}) or {})
    buy_fractions = dict(control.get("buy_fraction_by_regime", {}) or {})
    sell_fractions = dict(control.get("sell_fraction_by_regime", {}) or {})
    defensive_sell_fractions = dict(control.get("defensive_sleeve_sell_fraction_by_regime", {}) or {})
    turnover_caps = dict(control.get("max_turnover_ratio_by_regime", {}) or {})
    defensive_ticker = str(dict(config.get("overlay", {}) or {}).get("ticker") or "00679B.TWO")
    buy_fraction = min(max(float(buy_fractions.get(regime, buy_fractions.get("risk_off", 1.0))), 0.0), 1.0)
    sell_fraction = min(max(float(sell_fractions.get(regime, sell_fractions.get("risk_off", 1.0))), 0.0), 1.0)
    defensive_sell_fraction = min(
        max(float(defensive_sell_fractions.get(regime, defensive_sell_fractions.get("risk_off", sell_fraction))), 0.0),
        1.0,
    )
    adjusted: dict[str, float] = {}
    for ticker in TICKERS:
        current = float(current_weights.get(ticker, 0.0))
        target = float(target_weights.get(ticker, 0.0))
        delta = target - current
        if delta > 0:
            adjusted[ticker] = current + delta * buy_fraction
        elif delta < 0:
            active_sell_fraction = defensive_sell_fraction if ticker == defensive_ticker else sell_fraction
            adjusted[ticker] = current + delta * active_sell_fraction
        else:
            adjusted[ticker] = target
    adjusted_cash = max(1.0 - sum(adjusted.values()), 0.0)
    initial_turnover_ratio = sum(abs(float(adjusted.get(ticker, 0.0)) - float(current_weights.get(ticker, 0.0))) for ticker in TICKERS)
    cap_value = turnover_caps.get(regime, turnover_caps.get("risk_off"))
    turnover_scale = 1.0
    turnover_cap_applied = False
    if cap_value is not None:
        cap_value = max(float(cap_value), 0.0)
        if initial_turnover_ratio > cap_value:
            turnover_scale = cap_value / initial_turnover_ratio if initial_turnover_ratio > 0 else 1.0
            adjusted = {
                ticker: float(current_weights.get(ticker, 0.0))
                + (float(adjusted.get(ticker, 0.0)) - float(current_weights.get(ticker, 0.0))) * turnover_scale
                for ticker in TICKERS
            }
            adjusted_cash = max(1.0 - sum(adjusted.values()), 0.0)
            turnover_cap_applied = True
    adjusted, adjusted_cash = _normalize(adjusted, adjusted_cash)
    final_turnover_ratio = sum(abs(float(adjusted.get(ticker, 0.0)) - float(current_weights.get(ticker, 0.0))) for ticker in TICKERS)
    return adjusted, adjusted_cash, {
        "buy_fraction": buy_fraction,
        "sell_fraction": sell_fraction,
        "defensive_sleeve_sell_fraction": defensive_sell_fraction,
        "defensive_sleeve_ticker": defensive_ticker,
        "turnover_cap": cap_value,
        "turnover_cap_applied": turnover_cap_applied,
        "initial_turnover_ratio": initial_turnover_ratio,
        "final_turnover_ratio": final_turnover_ratio,
        "turnover_scale": turnover_scale,
        "target_cash_before_execution": target_cash,
    }


def _event_by_date(events: list[dict[str, Any]]) -> dict[pd.Timestamp, dict[str, Any]]:
    return {pd.Timestamp(event["date"]).normalize(): event for event in events}


def _simulate_plus(
    prices: pd.DataFrame,
    replay: dict[str, Any],
    config: dict[str, Any],
    *,
    commission_rate: float,
    etf_sell_tax_rate: float,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    dca_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    event_map = _event_by_date(list(replay["events"]))
    curve_rows = {pd.Timestamp(row["date"]).normalize(): row for row in replay["equity_curve"]}
    dca_map = _dca_by_date(list(dca_history or []))
    cash = float(initial_cash)
    shares = {ticker: 0.0 for ticker in TICKERS}
    last_event: dict[str, Any] | None = None
    last_signature: tuple[Any, ...] | None = None
    values: list[tuple[pd.Timestamp, float]] = []
    events: list[dict[str, Any]] = []
    total_cost = 0.0
    contributions = 0.0
    fast_risk_off_until: pd.Timestamp | None = None
    leverage_stop_until: pd.Timestamp | None = None

    # Regime stability filter: require N consecutive days in risk_off/severe before activating TDCC overlay
    # This prevents regime noise from triggering unnecessary rebalances
    stability_days = int(config.get("overlay", {}).get("regime_stability_consecutive_days", 0))
    regime_history: list[str] = []  # rolling history of raw regime values

    # Pre-fetch VIX for all price dates (FinRL-Meta regime upgrade)
    vix_by_date: dict[pd.Timestamp, float | None] = {}
    if config.get("vix_regime_control", {}).get("enabled"):
        for dt in prices.index:
            vix_by_date[dt] = _backtest_vix(dt.strftime("%Y-%m-%d"))

    # Pre-compute turbulence for all dates (Mahalanobis distance, FinRL-Meta style)
    turb_by_date: dict[pd.Timestamp, float] = {}
    if config.get("turbulence_control", {}).get("enabled"):
        for dt in prices.index:
            turb_by_date[dt] = _backtest_turbulence(prices, dt.strftime("%Y-%m-%d"))

    for dt, price_row in prices.iterrows():
        cash, dca_fees, dca_contributions = _apply_dca_purchases(
            dt,
            price_row,
            shares,
            cash,
            dca_map,
            commission_rate=commission_rate,
        )
        total_cost += dca_fees
        contributions += dca_contributions
        total = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        if dt in event_map:
            last_event = event_map[dt]
        if last_event is not None and dt in curve_rows:
            regime = _plus_regime(
                curve_rows[dt],
                vix=vix_by_date.get(dt),
                turbulence=turb_by_date.get(dt),
                vix_cfg=config.get("vix_regime_control") or None,
                turb_cfg=config.get("turbulence_control") or None,
            )
            regime_history.append(regime)
            if stability_days > 0:
                # Apply regime stability filter: require N consecutive risk_off/severe days
                # before activating the overlay. Otherwise use the previous stable regime.
                stable_regimes = {"risk_off", "severe"}
                recent = regime_history[-stability_days:]
                # Check if we have enough history AND all recent are stable
                if len(recent) >= stability_days and all(r in stable_regimes for r in recent):
                    effective_regime = regime  # confirmed stable
                else:
                    # Downgrade to the most recent stable regime, or risk_on as fallback
                    effective_regime = "risk_on"
                    for r in reversed(regime_history[:-1]):
                        if r in stable_regimes:
                            effective_regime = r
                            break
                    effective_regime = "risk_on"
            else:
                effective_regime = regime

            fast_override, fast_risk_off_until, fast_report = _fast_risk_off_overlay(
                prices,
                dt,
                config,
                active_until=fast_risk_off_until,
            )
            if fast_override is not None:
                effective_regime = fast_override

            target, target_cash, target_report = _group_a_plus_target(last_event, effective_regime, config)
            target_report["regime_stability_filter"] = {
                "raw_regime": regime,
                "effective_regime": effective_regime,
                "stability_days": stability_days,
                "filtered": regime != effective_regime,
            }
            leverage_stop_until, stop_report = _leverage_stop_cooldown_overlay(
                prices,
                dt,
                config,
                active_until=leverage_stop_until,
            )
            target, target_cash, risk_overlay_report = _apply_group_a_plus_risk_overlays(
                target,
                target_cash,
                fast_report=fast_report,
                stop_report=stop_report,
            )
            target_report["finrl_trading_risk_overlays"] = risk_overlay_report

            # Direction B: bond_augment_only - never shrink bond sleeve below current level
            if config.get("overlay", {}).get("bond_sleeve_never_shrink"):
                current_bond_value = shares.get("00679B.TWO", 0.0) * float(price_row["00679B.TWO"])
                if current_bond_value > 0 and total > 0:
                    current_bond_weight = current_bond_value / total
                    if target.get("00679B.TWO", 0.0) < current_bond_weight:
                        deficit = current_bond_weight - target.get("00679B.TWO", 0.0)
                        target["00679B.TWO"] = current_bond_weight
                        # Reduce all other tickers proportionally to compensate
                        for t in TICKERS:
                            if t != "00679B.TWO":
                                target[t] = max(target.get(t, 0.0) - deficit * target.get(t, 0.0) / max(sum(v for v in target.values() if v > 0 and v != current_bond_weight), 1e-10), 0.0)
                        target, target_cash = _normalize(target, target_cash)
                        target_report["bond_sleeve_never_shrink_applied"] = True

            signature = (
                tuple(round(target[ticker], 12) for ticker in TICKERS),
                round(target_cash, 12),
                effective_regime,
            )
            if signature != last_signature:
                current_weights = {
                    ticker: (shares[ticker] * float(price_row[ticker]) / total if total > 0 else 0.0)
                    for ticker in TICKERS
                }
                executable, executable_cash, execution_report = _apply_staged_execution(
                    current_weights,
                    target,
                    target_cash,
                    effective_regime,
                    config,
                )
                target_values = {ticker: total * executable[ticker] for ticker in TICKERS}
                current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
                traded = sum(abs(target_values[ticker] - current_values[ticker]) for ticker in TICKERS)
                sell_notional = sum(max(current_values[ticker] - target_values[ticker], 0.0) for ticker in TICKERS)
                cost = traded * commission_rate + sell_notional * etf_sell_tax_rate
                after_cost = max(total - cost, 0.0)
                shares = {
                    ticker: after_cost * executable[ticker] / float(price_row[ticker])
                    for ticker in TICKERS
                }
                cash = after_cost * executable_cash
                total = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
                total_cost += cost
                events.append(
                    {
                        "date": str(dt.date()),
                        "regime": regime,
                        "target_weights_before_execution": target,
                        "target_cash_before_execution": target_cash,
                        "executable_weights": executable,
                        "executable_cash_weight": executable_cash,
                        "trade_notional": traded,
                        "sell_notional": sell_notional,
                        "cost": cost,
                        "target_report": target_report,
                        "execution_report": execution_report,
                    }
                )
                last_signature = signature
        values.append((dt, total))

    series = pd.Series([value for _, value in values], index=[dt for dt, _ in values], dtype=float)
    final_value = float(series.iloc[-1])
    return {
        "metrics": _metrics(
            series,
            rebalances=len(events),
            total_cost=total_cost,
            initial_cash=initial_cash,
            contributions=contributions,
        ),
        "events": events,
        "equity_curve": [
            {"date": str(dt.date()), "value": float(value)}
            for dt, value in values
        ],
        "final_weights": {
            ticker: float(shares[ticker] * float(prices.iloc[-1][ticker]) / final_value)
            for ticker in TICKERS
        },
        "final_cash_weight": float(cash / final_value),
    }


def _simulate_base_events_approx(
    prices: pd.DataFrame,
    replay: dict[str, Any],
    *,
    commission_rate: float,
    etf_sell_tax_rate: float,
    initial_cash: float = DEFAULT_INITIAL_CASH,
    dca_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    event_map = _event_by_date(list(replay["events"]))
    dca_map = _dca_by_date(list(dca_history or []))
    cash = float(initial_cash)
    shares = {ticker: 0.0 for ticker in TICKERS}
    last_signature: tuple[Any, ...] | None = None
    values: list[tuple[pd.Timestamp, float]] = []
    events: list[dict[str, Any]] = []
    total_cost = 0.0
    contributions = 0.0

    for dt, price_row in prices.iterrows():
        cash, dca_fees, dca_contributions = _apply_dca_purchases(
            dt,
            price_row,
            shares,
            cash,
            dca_map,
            commission_rate=commission_rate,
        )
        total_cost += dca_fees
        contributions += dca_contributions
        total = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        if dt in event_map:
            event = event_map[dt]
            target = {
                ticker: float(dict(event.get("target_weights", {}) or {}).get(ticker, 0.0))
                for ticker in TICKERS
            }
            target_cash = float(event.get("target_cash_weight", 0.0))
            target, target_cash = _normalize(target, target_cash)
            signature = (
                tuple(round(target[ticker], 12) for ticker in TICKERS),
                round(target_cash, 12),
            )
            if signature != last_signature:
                target_values = {ticker: total * target[ticker] for ticker in TICKERS}
                current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
                traded = sum(abs(target_values[ticker] - current_values[ticker]) for ticker in TICKERS)
                sell_notional = sum(max(current_values[ticker] - target_values[ticker], 0.0) for ticker in TICKERS)
                cost = traded * commission_rate + sell_notional * etf_sell_tax_rate
                after_cost = max(total - cost, 0.0)
                shares = {
                    ticker: after_cost * target[ticker] / float(price_row[ticker])
                    for ticker in TICKERS
                }
                cash = after_cost * target_cash
                total = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
                total_cost += cost
                events.append(
                    {
                        "date": str(dt.date()),
                        "target_weights": target,
                        "target_cash_weight": target_cash,
                        "trade_notional": traded,
                        "sell_notional": sell_notional,
                        "cost": cost,
                    }
                )
                last_signature = signature
        values.append((dt, total))

    series = pd.Series([value for _, value in values], index=[dt for dt, _ in values], dtype=float)
    final_value = float(series.iloc[-1])
    return {
        "metrics": _metrics(
            series,
            rebalances=len(events),
            total_cost=total_cost,
            initial_cash=initial_cash,
            contributions=contributions,
        ),
        "events": events,
        "equity_curve": [
            {"date": str(dt.date()), "value": float(value)}
            for dt, value in values
        ],
        "final_weights": {
            ticker: float(shares[ticker] * float(prices.iloc[-1][ticker]) / final_value)
            for ticker in TICKERS
        },
        "final_cash_weight": float(cash / final_value),
    }


def _promotion_gate(
    base_metrics: dict[str, Any],
    plus_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Classify whether GroupA+ is ready for promotion or retraining."""
    base_final = float(base_metrics["final_value"])
    base_sharpe = float(base_metrics["sharpe_ratio"])
    base_mdd = float(base_metrics["max_drawdown"])
    base_vol = float(base_metrics["volatility"])
    rows: list[dict[str, Any]] = []

    for name, result in plus_results.items():
        metrics = dict(result["metrics"])
        final_value = float(metrics["final_value"])
        sharpe = float(metrics["sharpe_ratio"])
        max_drawdown = float(metrics["max_drawdown"])
        volatility = float(metrics["volatility"])
        final_drag_pct = final_value / base_final - 1.0 if base_final > 0 else 0.0
        sharpe_delta = sharpe - base_sharpe
        mdd_improvement = max_drawdown - base_mdd
        volatility_reduction = base_vol - volatility
        rows.append(
            {
                "variant": f"GroupA+_{name}",
                "final_drag_pct": final_drag_pct,
                "sharpe_delta": sharpe_delta,
                "mdd_improvement": mdd_improvement,
                "volatility_reduction": volatility_reduction,
                "return_upgrade_candidate": final_drag_pct >= -0.10 and sharpe_delta >= -0.05,
                "risk_control_candidate": volatility_reduction >= 0.01 and final_drag_pct >= -0.15 and sharpe_delta >= -0.05,
                "retrain_candidate": (
                    volatility_reduction >= 0.02 and final_drag_pct >= -0.20
                ),
            }
        )

    best_return = max(rows, key=lambda row: (row["final_drag_pct"], row["sharpe_delta"]))
    best_risk = max(rows, key=lambda row: (row["mdd_improvement"], row["volatility_reduction"]))
    if any(row["return_upgrade_candidate"] for row in rows):
        decision = "promotion_candidate"
        rationale = "At least one GroupA+ variant keeps return and Sharpe close enough to the base approximation."
    elif any(row["retrain_candidate"] for row in rows):
        decision = "retrain_candidate"
        rationale = "At least one GroupA+ variant materially improves risk without excessive return drag."
    elif any(row["risk_control_candidate"] for row in rows):
        decision = "shadow_risk_control_only"
        rationale = "GroupA+ reduces volatility, but return or Sharpe drag is too large for promotion."
    else:
        decision = "do_not_promote"
        rationale = "No GroupA+ variant clears return, Sharpe, or risk-control gates."

    return {
        "decision": decision,
        "rationale": rationale,
        "base_reference": {
            "final_value": base_final,
            "sharpe_ratio": base_sharpe,
            "max_drawdown": base_mdd,
            "volatility": base_vol,
        },
        "thresholds": {
            "promotion_max_final_drag_pct": -0.10,
            "promotion_min_sharpe_delta": -0.05,
            "risk_control_min_volatility_reduction": 0.01,
            "risk_control_max_final_drag_pct": -0.15,
            "risk_control_min_sharpe_delta": -0.05,
            "retrain_min_volatility_reduction": 0.02,
            "retrain_max_final_drag_pct": -0.20,
        },
        "best_return_variant": best_return["variant"],
        "best_risk_variant": best_risk["variant"],
        "variants": rows,
    }


def main() -> None:
    args = _parse_args()
    source_path = _resolve(args.source)
    dca_source_path = _resolve(args.dca_source) if args.dca_source else None
    config_path = _resolve(args.config)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    dca_history = _scale_dca_history(_load_dca_history(dca_source_path), float(args.dca_scale))
    variant = str(args.variant)
    replay = source["details"][variant]["replay"]
    start = str(source["actual_window"]["start"])
    end = str(source["actual_window"]["end"])
    prices = _load_prices(start, end)
    base_approx = _simulate_base_events_approx(
        prices,
        replay,
        commission_rate=float(args.commission_rate),
        etf_sell_tax_rate=float(args.etf_sell_tax_rate),
        initial_cash=DEFAULT_INITIAL_CASH,
        dca_history=dca_history,
    )

    source_values = pd.Series(
        [float(row["value"]) for row in replay["equity_curve"]],
        index=pd.to_datetime([row["date"] for row in replay["equity_curve"]]),
        dtype=float,
    ).reindex(prices.index).dropna()
    source_replay_metrics = dict(replay.get("metrics", {}) or {})
    source_metrics = _metrics(
        source_values,
        rebalances=int(source_replay_metrics.get("num_rebalances", 0)),
        total_cost=float(source_replay_metrics.get("fees_paid_estimate", source_replay_metrics.get("total_cost", 0.0))),
        initial_cash=DEFAULT_INITIAL_CASH,
        contributions=float(source_replay_metrics.get("dca_total_contributions", 0.0)),
    )

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    if args.grid_sweep:
        plus_configs = _grid_variant_configs(
            config,
            risk_off_bonds=_parse_float_list(str(args.grid_risk_off_bond)),
            risk_off_buys=_parse_float_list(str(args.grid_risk_off_buy)),
            risk_off_bond_sells=_parse_float_list(str(args.grid_risk_off_bond_sell)),
            risk_off_turnover_caps=_parse_float_list(str(args.grid_risk_off_turnover_cap)),
        )
    else:
        plus_configs = {
            name: _variant_config(config, name)
            for name in _parse_plus_variants(str(args.plus_variants))
        }
    plus_results = {
        name: _simulate_plus(
            prices,
            replay,
            variant_config,
            commission_rate=float(args.commission_rate),
            etf_sell_tax_rate=float(args.etf_sell_tax_rate),
            initial_cash=DEFAULT_INITIAL_CASH,
            dca_history=dca_history,
        )
        for name, variant_config in plus_configs.items()
    }
    rows = [
        {"variant": variant, "mode": "source_selected_meta", **source_metrics},
        {"variant": variant, "mode": "base_events_approx", **base_approx["metrics"]},
    ]
    for name, result in plus_results.items():
        rows.append({"variant": f"GroupA+_{name}", "mode": "plus_overlay_approx", **result["metrics"]})
    curve_data = {
        "source_selected_meta": source_values,
        "base_events_approx": pd.Series(
            [row["value"] for row in base_approx["equity_curve"]],
            index=pd.to_datetime([row["date"] for row in base_approx["equity_curve"]]),
            dtype=float,
        ),
    }
    for name, result in plus_results.items():
        curve_data[f"GroupA+_{name}"] = pd.Series(
            [row["value"] for row in result["equity_curve"]],
            index=pd.to_datetime([row["date"] for row in result["equity_curve"]]),
            dtype=float,
        )
    curves = pd.DataFrame(
        curve_data
    )
    plus_summary = {f"GroupA+_{name}": result["metrics"] for name, result in plus_results.items()}
    delta_plus_vs_base = {
        f"GroupA+_{name}": {
            key: result["metrics"][key] - base_approx["metrics"][key]
            for key in ["final_value", "sharpe_ratio", "max_drawdown", "volatility"]
        }
        for name, result in plus_results.items()
    }
    best_by_final = max(plus_summary, key=lambda name: plus_summary[name]["final_value"])
    best_by_sharpe = max(plus_summary, key=lambda name: plus_summary[name]["sharpe_ratio"])
    promotion_gate = _promotion_gate(base_approx["metrics"], plus_results)
    report = {
        "experiment": "group_a_plus_overlay_backtest",
        "method_note": (
            "Research approximation. Replays selected Group A meta rebalance events, "
            "then applies GroupA+ dynamic 00679B sleeve, 00631L caps, and staged buy "
            "execution at close prices. It is for overlay validation, not a full model rerun."
        ),
        "source": str(source_path.resolve()),
        "dca_source": str(dca_source_path.resolve()) if dca_source_path else None,
        "config": str(config_path.resolve()),
        "variant": variant,
        "window": {"start": start, "end": end, "rows": int(len(prices))},
        "settings": {
            "commission_rate": float(args.commission_rate),
            "etf_sell_tax_rate": float(args.etf_sell_tax_rate),
            "initial_cash": DEFAULT_INITIAL_CASH,
            "dca_purchase_count": len(dca_history),
            "dca_scale": float(args.dca_scale),
            "grid_sweep": bool(args.grid_sweep),
            "plus_variants": list(plus_configs),
        },
        "summary": {
            "source_selected_meta": source_metrics,
            "base_events_approx": base_approx["metrics"],
            **plus_summary,
            "delta_base_approx_vs_source": {
                key: base_approx["metrics"][key] - source_metrics[key]
                for key in ["final_value", "sharpe_ratio", "max_drawdown", "volatility"]
            },
            "delta_plus_vs_base_approx": delta_plus_vs_base,
            "best_plus_by_final_value": best_by_final,
            "best_plus_by_sharpe_ratio": best_by_sharpe,
            "promotion_gate": promotion_gate,
        },
        "plus_details": {
            f"GroupA+_{name}": {
                "variant_config": plus_configs[name],
                "final_weights": result["final_weights"],
                "final_cash_weight": result["final_cash_weight"],
                "events": result["events"],
            }
            for name, result in plus_results.items()
        },
        "outputs": {
            "json": str(output),
            "csv": str(csv_path),
            "curve_csv": str(curve_path),
        },
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curves.to_csv(curve_path, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print(f"Curve CSV: {curve_path}")
    for row in rows:
        print(
            f"{row['mode']}: final={row['final_value']:.2f}, "
            f"sharpe={row['sharpe_ratio']:.4f}, mdd={row['max_drawdown']:.4%}, "
            f"vol={row['volatility']:.4%}, rebalances={row['num_rebalances']}"
        )
    ranked = sorted(
        [
            {
                "variant": name,
                "final_value": result["metrics"]["final_value"],
                "sharpe_ratio": result["metrics"]["sharpe_ratio"],
                "max_drawdown": result["metrics"]["max_drawdown"],
                "volatility": result["metrics"]["volatility"],
            }
            for name, result in plus_results.items()
        ],
        key=lambda row: (row["final_value"], row["sharpe_ratio"]),
        reverse=True,
    )
    print("Top 5 plus variants by final value:")
    for row in ranked[:5]:
        print(
            f"  GroupA+_{row['variant']}: final={row['final_value']:.2f}, "
            f"sharpe={row['sharpe_ratio']:.4f}, mdd={row['max_drawdown']:.4%}, "
            f"vol={row['volatility']:.4%}"
        )
    for name, delta in report["summary"]["delta_plus_vs_base_approx"].items():
        print(
            f"Delta {name}-base_approx: "
            f"final={delta['final_value']:.2f}, "
            f"sharpe={delta['sharpe_ratio']:.4f}, "
            f"mdd={delta['max_drawdown']:.4%}, "
            f"vol={delta['volatility']:.4%}"
        )
    print(f"Best plus by final value: {best_by_final}")
    print(f"Best plus by Sharpe: {best_by_sharpe}")
    print(f"Promotion gate: {promotion_gate['decision']} - {promotion_gate['rationale']}")


if __name__ == "__main__":
    main()
