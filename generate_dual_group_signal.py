#!/usr/bin/env python3
"""Generate signal-only recommendations for the dual-group PPO workflows."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from stable_baselines3 import PPO


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from train_dual_group_2024_2026 import (
    DEFAULT_GROUP_A_DCA_DAY,
    DEFAULT_GROUP_A_INVERSE_MAX_HOLD_DAYS,
    DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RECOVERY_DRAWDOWN_20,
    DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RECOVERY_MA60_RATIO,
    DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RECOVERY_MOMENTUM_21,
    DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RECOVERY_TWSE_RETURN_5D,
    DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RISK_OFF_CLEAR_DAYS,
    DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RISK_OFF_SCORE_THRESHOLD,
    DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RISK_OFF_TEMPLATE,
    DEFAULT_GROUP_A_LOCAL_REGIME_GATE_SEVERE_CLEAR_DAYS,
    DEFAULT_GROUP_A_LOCAL_REGIME_GATE_SEVERE_SCORE_THRESHOLD,
    DEFAULT_GROUP_A_LOCAL_REGIME_GATE_SEVERE_TEMPLATE,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_CASH_FLOOR,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_INVERSE_FLOOR,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_MARGIN_FLOW_THRESHOLD,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_MARGIN_GROWTH_Z_THRESHOLD,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_SHORT_FLOW_THRESHOLD,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_SHORT_GROWTH_Z_THRESHOLD,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_CASH_FLOOR,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_INVERSE_FLOOR,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_MARGIN_FLOW_THRESHOLD,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_MARGIN_GROWTH_Z_THRESHOLD,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_SHORT_FLOW_THRESHOLD,
    DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_SHORT_GROWTH_Z_THRESHOLD,
    DEFAULT_GROUP_A_PVA_BUY_DIP_STRENGTH,
    DEFAULT_GROUP_A_PVA_DRIFT_THRESHOLD,
    DEFAULT_GROUP_A_PVA_INVERSE_HEDGE_BUDGET,
    DEFAULT_GROUP_A_PVA_J_STATE_WEIGHT,
    DEFAULT_GROUP_A_PVA_M_STATE_WEIGHT,
    DEFAULT_GROUP_A_PVA_MIN_LEVERAGE_SCALE,
    DEFAULT_GROUP_A_PVA_S_STATE_DRIFT_BOOST,
    DEFAULT_GROUP_A_PVA_S_STATE_MAX_WEIGHT,
    DEFAULT_GROUP_A_PVA_TARGET_VOL,
    DEFAULT_GROUP_A_PVA_WEIGHT,
    DEFAULT_GROUP_A_SENTIMENT_POSITIVE_LEVERAGE_BOOST,
    DEFAULT_GROUP_A_SENTIMENT_POSITIVE_MIN_CONFIDENCE,
    DEFAULT_GROUP_A_SENTIMENT_POSITIVE_MAX_RISK_OFF_SCORE,
    DEFAULT_GROUP_A_SENTIMENT_POSITIVE_THRESHOLD,
    DEFAULT_INITIAL_CASH,
    PortfolioEnv,
    _align_panel,
    _extract_code,
    _normalize_ticker_code,
    _resolve_group_a_profile,
    _resolve_group_b_profile,
    attach_institutional_features_db_first,
    attach_margin_features_db_first,
    attach_chip_distribution_features_db_first,
    attach_group_a_margin_shared_features_db_first,
    attach_group_a_market_margin_shared_features_db_first,
    attach_group_a_taifex_futures_features_db_first,
    attach_market_features_db_first,
    infer_group_a_action_schema,
    infer_group_b_action_schema,
    load_stock_data_db_first,
    payload_uses_group_a_institutional_features,
    payload_uses_group_a_margin_features,
    payload_uses_group_a_chip_distribution_features,
    payload_uses_group_a_margin_shared_features,
    payload_uses_group_a_market_margin_shared_features,
    payload_uses_group_a_taifex_futures_features,
    payload_uses_group_b_institutional_features,
    payload_uses_group_b_margin_features,
)


RESULT_GLOB_PATTERNS = {
    "group_a": ["group_a_backtest_*.json", "both_backtest_*.json"],
    "group_b": ["group_b_backtest_*.json", "both_backtest_*.json"],
}


def _resolve_result_json(path: str | None, group_key: str) -> Path:
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"Result JSON not found: {candidate}")
        return candidate

    candidates: list[Path] = []
    for pattern in RESULT_GLOB_PATTERNS[group_key]:
        candidates.extend((PROJECT_ROOT / "results").glob(pattern))
    candidates = sorted(set(candidates), key=lambda item: item.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No result JSON found for {group_key} under {PROJECT_ROOT / 'results'}")
    return candidates[-1]


def _group_column_bounds(df: pd.DataFrame) -> dict[str, tuple[int, int]]:
    positions = []
    columns = list(df.columns)
    for idx, name in enumerate(columns):
        label = str(name).strip().lower()
        if label in {"group a", "group b"}:
            positions.append((idx, label.replace(" ", "_")))
    if len(positions) < 2:
        raise ValueError("Workbook does not expose both Group A / Group B headers")

    bounds: dict[str, tuple[int, int]] = {}
    for pos, (start_idx, label) in enumerate(positions):
        end_idx = positions[pos + 1][0] if pos + 1 < len(positions) else len(columns)
        bounds[label] = (start_idx, end_idx)
    return bounds


def _find_holdings_row(df: pd.DataFrame, row_label: str) -> tuple[int, str]:
    needle = str(row_label).strip()
    for row_idx in range(len(df)):
        first_cell = "" if pd.isna(df.iloc[row_idx, 0]) else str(df.iloc[row_idx, 0]).strip()
        if first_cell == needle:
            return row_idx, first_cell
    raise ValueError(f"Workbook row label not found: {row_label}")


def _load_group_holdings(xlsx_path: Path, group_key: str, row_label: str) -> tuple[dict[str, int], str]:
    df = pd.read_excel(xlsx_path)
    bounds = _group_column_bounds(df)
    start_idx, end_idx = bounds[group_key]
    row_idx, matched_label = _find_holdings_row(df, row_label)

    holdings: dict[str, int] = {}
    for col_idx in range(start_idx, end_idx):
        code = _extract_code(df.iloc[0, col_idx])
        if code is None:
            continue
        ticker = _normalize_ticker_code(code)
        raw_value = df.iloc[row_idx, col_idx]
        shares = 0 if pd.isna(raw_value) else int(round(float(raw_value)))
        holdings[ticker] = shares
    if not holdings:
        raise ValueError(f"No parsed holdings for {group_key} from workbook: {xlsx_path}")
    return holdings, matched_label


def _env_kwargs_from_payload(payload: dict, group_key: str) -> tuple[dict, list[str]]:
    if group_key == "group_b":
        profile_name = str(payload.get("group_b_profile", "balanced"))
        profile = _resolve_group_b_profile(profile_name)
        env_kwargs = dict(profile["env"])
        env_kwargs["group_b_action_schema"] = infer_group_b_action_schema(payload=payload)
        shared_feature_cols = list(payload.get("group_b", {}).get("shared_feature_cols", []) or [])
        pva_cfg = payload.get("group_b_pva_sigmoid_config", {})
        if pva_cfg.get("features_enabled"):
            env_kwargs["enable_pva_features"] = True
        if pva_cfg.get("overlay_enabled"):
            env_kwargs.update(
                {
                    "enable_pva_sigmoid": True,
                    "pva_weight": float(pva_cfg.get("pva_weight", 0.30)),
                    "pva_j_state_weight": float(pva_cfg.get("pva_j_state_weight", 0.0)),
                    "pva_m_state_weight": float(pva_cfg.get("pva_m_state_weight", 1.0)),
                    "pva_drift_threshold": float(pva_cfg.get("pva_drift_threshold", 0.05)),
                    "pva_target_vol": float(pva_cfg.get("pva_target_vol", 0.012)),
                    "pva_min_leverage_scale": float(pva_cfg.get("pva_min_leverage_scale", 0.35)),
                    "pva_inverse_hedge_budget": float(pva_cfg.get("pva_inverse_hedge_budget", 0.30)),
                }
            )

        sentiment_cfg = payload.get("group_b_sentiment_gate_config", {}) or {}
        if sentiment_cfg.get("enabled"):
            env_kwargs.update(
                {
                    "sentiment_gate_enabled": True,
                    "sentiment_risk_off_threshold": float(sentiment_cfg.get("risk_off_threshold", 0.25)),
                    "sentiment_severe_threshold": float(sentiment_cfg.get("severe_threshold", 0.50)),
                    "sentiment_min_confidence": float(sentiment_cfg.get("min_confidence", 0.55)),
                    "sentiment_min_intensity": float(sentiment_cfg.get("min_intensity", 1.0)),
                    "sentiment_risk_off_inverse_floor": float(sentiment_cfg.get("risk_off_inverse_floor", 0.15)),
                    "sentiment_severe_inverse_floor": float(sentiment_cfg.get("severe_inverse_floor", 0.30)),
                }
            )
        return env_kwargs, shared_feature_cols

    if group_key != "group_a":
        return {}, []

    profile_name = str(payload.get("group_a_profile", "default"))
    profile = _resolve_group_a_profile(profile_name)
    env_kwargs = dict(profile["env"])
    env_kwargs["group_a_action_schema"] = infer_group_a_action_schema(payload=payload)
    shared_feature_cols = list(payload.get("group_a", {}).get("shared_feature_cols", []) or [])

    caps = payload.get("group_a_exposure_caps", {})
    if "00631L.TW" in caps:
        env_kwargs["leverage_cap"] = float(caps["00631L.TW"])
    if "00632R.TW" in caps:
        env_kwargs["inverse_cap"] = float(caps["00632R.TW"])

    inverse_cfg = payload.get("group_a_inverse_hedge_config", {})
    env_kwargs["inverse_m_state_only"] = bool(inverse_cfg.get("m_state_only", True))
    env_kwargs["inverse_max_holding_days"] = int(
        inverse_cfg.get("max_holding_days", DEFAULT_GROUP_A_INVERSE_MAX_HOLD_DAYS)
    )

    pva_cfg = payload.get("group_a_pva_sigmoid_config", {})
    if pva_cfg.get("features_enabled"):
        env_kwargs["enable_pva_features"] = True
    if pva_cfg.get("overlay_enabled"):
        env_kwargs.update(
            {
                "enable_pva_sigmoid": True,
                "pva_weight": float(pva_cfg.get("pva_weight", DEFAULT_GROUP_A_PVA_WEIGHT)),
                "pva_j_state_weight": float(
                    pva_cfg.get("pva_j_state_weight", DEFAULT_GROUP_A_PVA_J_STATE_WEIGHT)
                ),
                "pva_m_state_weight": float(
                    pva_cfg.get("pva_m_state_weight", DEFAULT_GROUP_A_PVA_M_STATE_WEIGHT)
                ),
                "pva_drift_threshold": float(
                    pva_cfg.get("pva_drift_threshold", DEFAULT_GROUP_A_PVA_DRIFT_THRESHOLD)
                ),
                "pva_target_vol": float(pva_cfg.get("pva_target_vol", DEFAULT_GROUP_A_PVA_TARGET_VOL)),
                "pva_min_leverage_scale": float(
                    pva_cfg.get("pva_min_leverage_scale", DEFAULT_GROUP_A_PVA_MIN_LEVERAGE_SCALE)
                ),
                "pva_inverse_hedge_budget": float(
                    pva_cfg.get("pva_inverse_hedge_budget", DEFAULT_GROUP_A_PVA_INVERSE_HEDGE_BUDGET)
                ),
                "pva_s_state_drift_boost": float(
                    pva_cfg.get("pva_s_state_drift_boost", DEFAULT_GROUP_A_PVA_S_STATE_DRIFT_BOOST)
                ),
                "pva_s_state_max_weight": float(
                    pva_cfg.get("pva_s_state_max_weight", DEFAULT_GROUP_A_PVA_S_STATE_MAX_WEIGHT)
                ),
                "pva_buy_dip_strength": float(
                    pva_cfg.get("pva_buy_dip_strength", DEFAULT_GROUP_A_PVA_BUY_DIP_STRENGTH)
                ),
            }
        )

    dca_cfg = payload.get("group_a_dca_config", {})
    monthly_amounts = {
        ticker: float(amount)
        for ticker, amount in (dca_cfg.get("monthly_amounts", {}) or {}).items()
        if float(amount) > 0.0
    }
    if monthly_amounts:
        env_kwargs["dca_monthly_amounts"] = monthly_amounts
        env_kwargs["dca_day"] = int(dca_cfg.get("dca_day", DEFAULT_GROUP_A_DCA_DAY))

    dividend_cfg = payload.get("group_a_dividend_config", {}) or {}
    if dividend_cfg.get("mode"):
        env_kwargs["dividend_mode"] = str(dividend_cfg["mode"])
    elif "group_a" in payload:
        # Older Group A payloads were produced before dividend mode was explicit.
        env_kwargs["dividend_mode"] = "cash"

    sentiment_cfg = payload.get("group_a_sentiment_gate_config", {}) or {}
    if sentiment_cfg.get("enabled"):
        env_kwargs.update(
            {
                "sentiment_gate_enabled": True,
                "sentiment_risk_off_threshold": float(sentiment_cfg.get("risk_off_threshold", 0.25)),
                "sentiment_severe_threshold": float(sentiment_cfg.get("severe_threshold", 0.50)),
                "sentiment_min_confidence": float(sentiment_cfg.get("min_confidence", 0.55)),
                "sentiment_min_intensity": float(sentiment_cfg.get("min_intensity", 1.0)),
                "sentiment_risk_off_inverse_floor": float(sentiment_cfg.get("risk_off_inverse_floor", 0.15)),
                "sentiment_severe_inverse_floor": float(sentiment_cfg.get("severe_inverse_floor", 0.30)),
                "sentiment_positive_min_confidence": float(
                    sentiment_cfg.get(
                        "positive_min_confidence",
                        DEFAULT_GROUP_A_SENTIMENT_POSITIVE_MIN_CONFIDENCE,
                    )
                ),
                "sentiment_positive_threshold": float(
                    sentiment_cfg.get("positive_threshold", DEFAULT_GROUP_A_SENTIMENT_POSITIVE_THRESHOLD)
                ),
                "sentiment_positive_max_risk_off_score": float(
                    sentiment_cfg.get(
                        "positive_max_risk_off_score",
                        DEFAULT_GROUP_A_SENTIMENT_POSITIVE_MAX_RISK_OFF_SCORE,
                    )
                ),
                "sentiment_positive_leverage_boost": float(
                    sentiment_cfg.get(
                        "positive_leverage_boost",
                        DEFAULT_GROUP_A_SENTIMENT_POSITIVE_LEVERAGE_BOOST,
                    )
                ),
            }
        )

    hard_crash_cfg = payload.get("group_a_hard_crash_gate_config", {}) or {}
    if hard_crash_cfg.get("enabled"):
        env_kwargs.update(
            {
                "hard_crash_gate_enabled": True,
                "hard_crash_gate_risk_off_cash_floor": float(
                    hard_crash_cfg.get("risk_off_cash_floor", 0.30)
                ),
                "hard_crash_gate_risk_off_inverse_floor": float(
                    hard_crash_cfg.get("risk_off_inverse_floor", 0.15)
                ),
                "hard_crash_gate_severe_cash_floor": float(
                    hard_crash_cfg.get("severe_cash_floor", 0.50)
                ),
                "hard_crash_gate_severe_inverse_floor": float(
                    hard_crash_cfg.get("severe_inverse_floor", 0.30)
                ),
            }
        )

    local_regime_cfg = payload.get("group_a_local_regime_gate_config", {}) or {}
    if local_regime_cfg.get("enabled"):
        env_kwargs.update(
            {
                "local_regime_gate_enabled": True,
                "local_regime_gate_risk_off_score_threshold": int(
                    local_regime_cfg.get(
                        "risk_off_score_threshold",
                        DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RISK_OFF_SCORE_THRESHOLD,
                    )
                ),
                "local_regime_gate_severe_score_threshold": int(
                    local_regime_cfg.get(
                        "severe_score_threshold",
                        DEFAULT_GROUP_A_LOCAL_REGIME_GATE_SEVERE_SCORE_THRESHOLD,
                    )
                ),
                "local_regime_gate_risk_off_clear_days": int(
                    local_regime_cfg.get(
                        "risk_off_clear_days",
                        DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RISK_OFF_CLEAR_DAYS,
                    )
                ),
                "local_regime_gate_severe_clear_days": int(
                    local_regime_cfg.get(
                        "severe_clear_days",
                        DEFAULT_GROUP_A_LOCAL_REGIME_GATE_SEVERE_CLEAR_DAYS,
                    )
                ),
                "local_regime_gate_recovery_ma60_ratio": float(
                    local_regime_cfg.get(
                        "recovery_ma60_ratio",
                        DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RECOVERY_MA60_RATIO,
                    )
                ),
                "local_regime_gate_recovery_momentum_21": float(
                    local_regime_cfg.get(
                        "recovery_momentum_21",
                        DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RECOVERY_MOMENTUM_21,
                    )
                ),
                "local_regime_gate_recovery_drawdown_20": float(
                    local_regime_cfg.get(
                        "recovery_drawdown_20",
                        DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RECOVERY_DRAWDOWN_20,
                    )
                ),
                "local_regime_gate_recovery_twse_return_5d": float(
                    local_regime_cfg.get(
                        "recovery_twse_return_5d",
                        DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RECOVERY_TWSE_RETURN_5D,
                    )
                ),
                "local_regime_gate_risk_off_template": str(
                    local_regime_cfg.get(
                        "risk_off_template",
                        DEFAULT_GROUP_A_LOCAL_REGIME_GATE_RISK_OFF_TEMPLATE,
                    )
                ),
                "local_regime_gate_severe_template": str(
                    local_regime_cfg.get(
                        "severe_template",
                        DEFAULT_GROUP_A_LOCAL_REGIME_GATE_SEVERE_TEMPLATE,
                    )
                ),
            }
        )
        hidden_cols = list(env_kwargs.get("hidden_shared_feature_cols", []))
        hidden_cols.extend(local_regime_cfg.get("shared_columns", []) or [])
        if hidden_cols:
            env_kwargs["hidden_shared_feature_cols"] = list(dict.fromkeys(hidden_cols))

    rsi_overlay_cfg = payload.get("group_a_rsi_overlay_config", {}) or {}
    if rsi_overlay_cfg.get("enabled"):
        env_kwargs.update(
            {
                "rsi_overlay_enabled": True,
                "rsi_overlay_oversold_threshold": float(rsi_overlay_cfg.get("oversold_threshold", 30.0)),
                "rsi_overlay_overbought_threshold": float(rsi_overlay_cfg.get("overbought_threshold", 70.0)),
                "rsi_overlay_oversold_0050_boost": float(rsi_overlay_cfg.get("oversold_0050_boost", 0.10)),
                "rsi_overlay_overbought_leverage_scale": float(
                    rsi_overlay_cfg.get("overbought_leverage_scale", 0.50)
                ),
            }
        )

    market_margin_gate_cfg = payload.get("group_a_market_margin_gate_config", {}) or {}
    market_margin_shared_cfg = payload.get("group_a_market_margin_shared_config", {}) or {}
    market_margin_shared_cols = list(market_margin_shared_cfg.get("feature_columns", []) or [])
    if market_margin_shared_cols:
        shared_feature_cols = list(dict.fromkeys([*shared_feature_cols, *market_margin_shared_cols]))
    if market_margin_gate_cfg.get("enabled"):
        env_kwargs.update(
            {
                "market_margin_gate_enabled": True,
                "market_margin_gate_risk_off_margin_flow_threshold": float(
                    market_margin_gate_cfg.get(
                        "risk_off_margin_flow_threshold",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_MARGIN_FLOW_THRESHOLD,
                    )
                ),
                "market_margin_gate_severe_margin_flow_threshold": float(
                    market_margin_gate_cfg.get(
                        "severe_margin_flow_threshold",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_MARGIN_FLOW_THRESHOLD,
                    )
                ),
                "market_margin_gate_risk_off_short_flow_threshold": float(
                    market_margin_gate_cfg.get(
                        "risk_off_short_flow_threshold",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_SHORT_FLOW_THRESHOLD,
                    )
                ),
                "market_margin_gate_severe_short_flow_threshold": float(
                    market_margin_gate_cfg.get(
                        "severe_short_flow_threshold",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_SHORT_FLOW_THRESHOLD,
                    )
                ),
                "market_margin_gate_risk_off_margin_growth_z_threshold": float(
                    market_margin_gate_cfg.get(
                        "risk_off_margin_growth_z_threshold",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_MARGIN_GROWTH_Z_THRESHOLD,
                    )
                ),
                "market_margin_gate_severe_margin_growth_z_threshold": float(
                    market_margin_gate_cfg.get(
                        "severe_margin_growth_z_threshold",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_MARGIN_GROWTH_Z_THRESHOLD,
                    )
                ),
                "market_margin_gate_risk_off_short_growth_z_threshold": float(
                    market_margin_gate_cfg.get(
                        "risk_off_short_growth_z_threshold",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_SHORT_GROWTH_Z_THRESHOLD,
                    )
                ),
                "market_margin_gate_severe_short_growth_z_threshold": float(
                    market_margin_gate_cfg.get(
                        "severe_short_growth_z_threshold",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_SHORT_GROWTH_Z_THRESHOLD,
                    )
                ),
                "market_margin_gate_risk_off_cash_floor": float(
                    market_margin_gate_cfg.get(
                        "risk_off_cash_floor",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_CASH_FLOOR,
                    )
                ),
                "market_margin_gate_risk_off_inverse_floor": float(
                    market_margin_gate_cfg.get(
                        "risk_off_inverse_floor",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_RISK_OFF_INVERSE_FLOOR,
                    )
                ),
                "market_margin_gate_severe_cash_floor": float(
                    market_margin_gate_cfg.get(
                        "severe_cash_floor",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_CASH_FLOOR,
                    )
                ),
                "market_margin_gate_severe_inverse_floor": float(
                    market_margin_gate_cfg.get(
                        "severe_inverse_floor",
                        DEFAULT_GROUP_A_MARKET_MARGIN_GATE_SEVERE_INVERSE_FLOOR,
                    )
                ),
            }
        )
        if not market_margin_shared_cfg.get("observation_enabled", False):
            env_kwargs["hidden_shared_feature_cols"] = list(
                payload.get("group_a", {}).get("market_margin_shared_feature_cols", []) or []
            )

    return env_kwargs, shared_feature_cols


def _llm_sentiment_path_from_payload(payload: dict, group_key: str) -> str | None:
    config = payload.get(f"{group_key}_llm_sentiment_config", {}) or {}
    for key in ("path", "source_path"):
        value = config.get(key)
        if value:
            return str(value)
    return None


def _normalize_weights(values: dict[str, float], tickers: list[str]) -> dict[str, float]:
    clean = {ticker: max(float(values.get(ticker, 0.0)), 0.0) for ticker in tickers}
    total = sum(clean.values())
    if total <= 0.0:
        return {ticker: 1.0 / len(tickers) for ticker in tickers}
    return {ticker: value / total for ticker, value in clean.items()}


def _weights_from_total_value(
    values: dict[str, float],
    tickers: list[str],
    total_value: float,
) -> dict[str, float]:
    base = max(float(total_value), 1.0)
    return {
        ticker: max(float(values.get(ticker, 0.0)), 0.0) / base
        for ticker in tickers
    }


def _load_override_holdings(raw: str | None, tickers: list[str]) -> tuple[dict[str, int] | None, str | None]:
    if not raw:
        return None, None

    candidate = Path(raw)
    payload = None
    if candidate.exists():
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        source = str(candidate)
    else:
        payload = json.loads(raw)
        source = "override_holdings_json"

    holdings = {ticker: 0 for ticker in tickers}
    for key, value in payload.items():
        ticker = _normalize_ticker_code(_extract_code(str(key)) or str(key))
        if ticker in holdings:
            holdings[ticker] = int(round(float(value)))
    return holdings, source


def _seed_live_start_reference_state(
    env: PortfolioEnv,
    tickers: list[str],
) -> float:
    env.step_idx = len(env.panel) - 1
    current_prices = env.close_price_array[env.step_idx]

    reference_weights = env.weights.copy()
    current_value = max(float(env.initial_cash), 1.0)
    cash_weight = max(0.0, 1.0 - float(reference_weights.sum()))
    env.cash = current_value * cash_weight
    env.shares = np.array(
        [
            (current_value * float(reference_weights[idx]) / current_prices[idx]) if current_prices[idx] > 0 else 0.0
            for idx, _ in enumerate(tickers)
        ],
        dtype=float,
    )
    current_value = max(env._mark_weights(current_prices), 1.0)

    # Fresh live deployment should start from the model's own neutral reference
    # allocation at the current market snapshot, not from the historical backtest
    # path and not from the user's arbitrary pre-deployment account mix.
    env.peak_value = current_value
    env.last_rebalance_idx = env.step_idx - 252
    env.trade_count = 0
    env.fees_paid = 0.0
    env.equity_curve = [current_value]
    env.total_contributions = 0.0
    env.dca_purchase_count = 0
    env.dca_purchase_history = []
    env.dca_executed_months = set()
    env.pva_sigmoid_count = 0
    env.pva_sigmoid_history = []
    env.sjm_state_history = []
    env.inverse_holding_days = 0
    env.inverse_cooldown_active = False
    env.inverse_forced_exit_count = 0
    env.inverse_forced_exit_history = []

    if env.equal_bh_curve is not None:
        env.equal_bh_curve = env.equal_bh_curve.copy()
        env.equal_bh_curve[env.step_idx] = current_value
    if env.bh_0050_curve is not None:
        env.bh_0050_curve = env.bh_0050_curve.copy()
        env.bh_0050_curve[env.step_idx] = current_value

    return current_value


def _action_hint(weight_diff: float, delta_shares: int, threshold: float, signal_status: str) -> str:
    if signal_status != "rebalance":
        return "hold"
    if weight_diff >= threshold or delta_shares > 0:
        return "buy"
    if weight_diff <= -threshold or delta_shares < 0:
        return "sell"
    return "hold"


def _apply_group_a_0050_weight_step_overlay(
    target_weights: dict[str, float],
    target_cash_weight: float,
    reference_weights: dict[str, float],
    max_weight_step: float | None,
    step_active_max_ma_ratio: float | None = None,
    ma_brake_price: float | None = None,
    ma_brake_value: float | None = None,
    ma_brake_ratio: float = 1.0,
    ma_brake_max_weight: float | None = None,
    ma_brake_00631l_max_weight: float | None = None,
) -> tuple[dict[str, float], float, dict[str, Any]]:
    step_enabled = max_weight_step is not None and max_weight_step > 0.0
    ma_brake_enabled = (
        ma_brake_price is not None
        and ma_brake_value is not None
        and ma_brake_max_weight is not None
        and ma_brake_max_weight >= 0.0
    )
    if (not step_enabled and not ma_brake_enabled) or "0050.TW" not in target_weights:
        return target_weights, target_cash_weight, {
            "enabled": False,
            "reason": "disabled",
            "max_weight_step": max_weight_step,
            "ma_brake_enabled": ma_brake_enabled,
        }
    ticker = "0050.TW"
    raw_weight = float(target_weights[ticker])
    reference_weight = float(reference_weights.get(ticker, raw_weight))
    reasons = []
    adjusted_weight = raw_weight
    step_gate_active = True
    if (
        step_enabled
        and step_active_max_ma_ratio is not None
        and ma_brake_price is not None
        and ma_brake_value is not None
    ):
        step_gate_active = bool(float(ma_brake_price) <= float(ma_brake_value) * float(step_active_max_ma_ratio))
    if step_enabled and step_gate_active:
        step = float(max_weight_step)
        adjusted_weight = reference_weight + max(min(raw_weight - reference_weight, step), -step)
        if abs(adjusted_weight - raw_weight) > 1e-12:
            reasons.append("limited_0050_target_weight_step")
    elif step_enabled and not step_gate_active:
        reasons.append("trend_gate_released_0050_step")
    adjusted_weight = max(min(adjusted_weight, 1.0), 0.0)
    ma_brake_triggered = False
    if (
        ma_brake_enabled
        and float(ma_brake_price) <= float(ma_brake_value) * float(ma_brake_ratio)
        and adjusted_weight > float(ma_brake_max_weight)
    ):
        adjusted_weight = float(ma_brake_max_weight)
        ma_brake_triggered = True
        reasons.append("ma_brake_capped_0050")
    cash_adjustment = raw_weight - adjusted_weight
    leverage_ticker = "00631L.TW"
    leverage_raw_weight = float(target_weights.get(leverage_ticker, 0.0))
    leverage_adjusted_weight = leverage_raw_weight
    leverage_brake_triggered = False
    if (
        ma_brake_enabled
        and float(ma_brake_price) <= float(ma_brake_value) * float(ma_brake_ratio)
        and ma_brake_00631l_max_weight is not None
        and leverage_ticker in target_weights
        and leverage_raw_weight > float(ma_brake_00631l_max_weight)
    ):
        leverage_adjusted_weight = float(ma_brake_00631l_max_weight)
        leverage_brake_triggered = True
        cash_adjustment += leverage_raw_weight - leverage_adjusted_weight
        reasons.append("ma_brake_capped_00631l")
    adjusted_cash = float(target_cash_weight) + cash_adjustment
    if adjusted_cash < 0.0:
        adjusted_weight += adjusted_cash
        adjusted_cash = 0.0
    adjusted = dict(target_weights)
    adjusted[ticker] = float(max(min(adjusted_weight, 1.0), 0.0))
    if leverage_ticker in adjusted:
        adjusted[leverage_ticker] = float(max(min(leverage_adjusted_weight, 1.0), 0.0))
    return adjusted, float(adjusted_cash), {
        "enabled": True,
        "reason": ";".join(reasons) if reasons else "no_adjustment_needed",
        "max_weight_step": max_weight_step,
        "step_active_max_ma_ratio": step_active_max_ma_ratio,
        "step_gate_active": step_gate_active,
        "reference_0050_weight": reference_weight,
        "raw_0050_weight": raw_weight,
        "adjusted_0050_weight": float(adjusted[ticker]),
        "cash_adjustment": float(cash_adjustment),
        "raw_cash_weight": float(target_cash_weight),
        "adjusted_cash_weight": float(adjusted_cash),
        "ma_brake_enabled": ma_brake_enabled,
        "ma_brake_triggered": ma_brake_triggered,
        "ma_brake_price": ma_brake_price,
        "ma_brake_value": ma_brake_value,
        "ma_brake_ratio": float(ma_brake_ratio),
        "ma_brake_max_weight": ma_brake_max_weight,
        "ma_brake_00631l_max_weight": ma_brake_00631l_max_weight,
        "ma_brake_00631l_triggered": leverage_brake_triggered,
        "raw_00631l_weight": leverage_raw_weight,
        "adjusted_00631l_weight": leverage_adjusted_weight,
    }


def _format_group_a_weights_label(weights: dict[str, float], cash_weight: float) -> str:
    parts = []
    for ticker in ("0050.TW", "00631L.TW", "00679B.TWO", "00632R.TW"):
        weight = float(weights.get(ticker, 0.0))
        if abs(weight) >= 0.0005:
            parts.append(f"{ticker.replace('.TW', '').replace('.TWO', '')} {weight:.1%}")
    if abs(cash_weight) >= 0.0005:
        parts.append(f"cash {cash_weight:.1%}")
    return " / ".join(parts) if parts else "cash 100.0%"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate signal-only recommendations for Group A / Group B models.")
    parser.add_argument("--group", choices=["group_a", "group_b"], default="group_a")
    parser.add_argument("--result-json", default=None, help="Backtest result JSON; defaults to the latest matching result")
    parser.add_argument("--xlsx", default=None, help="Workbook path; defaults to the workbook recorded in result JSON")
    parser.add_argument("--holdings-row-label", default="即時庫存", help="Workbook row label containing current shares")
    parser.add_argument("--simulation-start", default=None, help="Override replay start date")
    parser.add_argument("--history-start", default=None, help="Override data download start date")
    parser.add_argument("--download-end", default=None, help="Override data download end date")
    parser.add_argument("--as-of-date", default=None, help="Signal date; defaults to download-end")
    parser.add_argument(
        "--live-start",
        action="store_true",
        help=(
            "Treat the signal date as the first live deployment day. "
            "The model uses its neutral start allocation at the current market snapshot, "
            "then maps the target weights back onto your actual holdings/cash."
        ),
    )
    parser.add_argument(
        "--extra-cash",
        type=float,
        default=0.0,
        help="Additional free cash to include in the current live portfolio, e.g. 1000000",
    )
    parser.add_argument(
        "--override-holdings-json",
        default=None,
        help="Optional JSON string or JSON file path overriding workbook holdings, e.g. '{\"0050\": 89}'",
    )
    parser.add_argument("--action-threshold", type=float, default=0.01, help="Minimum weight diff for buy/sell hints")
    parser.add_argument("--max-stale-days", type=int, default=3, help="Block signals when data is older than this")
    parser.add_argument("--max-strategy-drawdown", type=float, default=0.27, help="Block signals when strategy drawdown exceeds this")
    parser.add_argument(
        "--max-underperformance-vs-0050",
        type=float,
        default=0.10,
        help="Block signals when strategy trails 0050 buy-and-hold by more than this",
    )
    parser.add_argument(
        "--group-a-0050-max-weight-step",
        type=float,
        default=None,
        help=(
            "Optional Group A execution overlay: cap the 0050 target-weight move from the model "
            "reference weight, e.g. 0.03 limits each signal to +/-3 percentage points and leaves "
            "the unused weight in cash."
        ),
    )
    parser.add_argument(
        "--group-a-0050-step-active-max-ma-ratio",
        type=float,
        default=None,
        help=(
            "Optional Group A execution overlay: apply the 0050 step limiter only when "
            "0050 price <= moving_average * this ratio. Requires --group-a-0050-ma-brake-window."
        ),
    )
    parser.add_argument(
        "--group-a-0050-ma-brake-window",
        type=int,
        default=None,
        help="Optional Group A 0050 trend brake moving-average window, e.g. 60.",
    )
    parser.add_argument(
        "--group-a-0050-ma-brake-ratio",
        type=float,
        default=1.0,
        help="Trigger the 0050 trend brake when 0050 price <= moving_average * ratio.",
    )
    parser.add_argument(
        "--group-a-0050-ma-brake-max-weight",
        type=float,
        default=None,
        help="When the 0050 trend brake triggers, cap 0050 target weight at this level, e.g. 0.47.",
    )
    parser.add_argument(
        "--group-a-0050-ma-brake-00631l-max-weight",
        type=float,
        default=None,
        help="When the 0050 trend brake triggers, also cap 00631L target weight at this level, e.g. 0.0.",
    )
    args = parser.parse_args()

    result_json = _resolve_result_json(args.result_json, args.group)
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    if args.group not in payload:
        raise KeyError(f"{result_json} does not contain payload for {args.group}")

    group_payload = payload[args.group]
    tickers = list(group_payload["tickers"])
    model_name = str(group_payload["model_name"])
    model_path = PROJECT_ROOT / "models" / "portfolio" / f"{model_name}.zip"
    if not model_path.exists():
        raise FileNotFoundError(f"Model path not found: {model_path}")

    xlsx_path: Path | None = None
    workbook_value = args.xlsx or payload.get("workbook") or ""
    if workbook_value:
        candidate = Path(workbook_value)
        if not candidate.is_absolute():
            candidate = (PROJECT_ROOT / candidate).resolve()
        if candidate.exists():
            xlsx_path = candidate
    if args.override_holdings_json is None and xlsx_path is None:
        raise FileNotFoundError("Workbook not found and no --override-holdings-json was provided")

    simulation_start = args.simulation_start or payload.get("backtest_start") or "2025-01-01"
    history_start = args.history_start or payload.get("train_start") or simulation_start
    download_end = args.download_end or args.as_of_date or payload.get("download_end") or payload.get("backtest_end")
    as_of_date = args.as_of_date or download_end
    initial_cash = float(payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))

    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, args.group)
    override_holdings, override_source = _load_override_holdings(args.override_holdings_json, tickers)

    print("=" * 72)
    print("Generate dual-group signal")
    print(f"Group:       {args.group}")
    print(f"Result JSON: {result_json}")
    print(f"Model:       {model_path}")
    print(f"Workbook:    {xlsx_path if xlsx_path is not None else '(override holdings only)'}")
    print(f"History:     {history_start} ~ {download_end}")
    print(f"Simulation:  {simulation_start} ~ {as_of_date}")
    print(f"Mode:        {'live_start' if args.live_start else 'strategy_replay'}")
    print("=" * 72)

    stock_data = load_stock_data_db_first(tickers, history_start, download_end)
    if args.group == "group_a" and payload_uses_group_a_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
        )
    if args.group == "group_a" and payload_uses_group_a_margin_features(payload):
        stock_data = attach_margin_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
        )
    if args.group == "group_a" and payload_uses_group_a_chip_distribution_features(payload):
        stock_data = attach_chip_distribution_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
        )
    if args.group == "group_a" and payload_uses_group_a_margin_shared_features(payload):
        stock_data = attach_group_a_margin_shared_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
        )
    if args.group == "group_a" and payload_uses_group_a_market_margin_shared_features(payload):
        stock_data = attach_group_a_market_margin_shared_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
        )
    if args.group == "group_a" and payload_uses_group_a_taifex_futures_features(payload):
        stock_data = attach_group_a_taifex_futures_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
        )
    if args.group == "group_b" and payload_uses_group_b_institutional_features(payload):
        stock_data = attach_institutional_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
        )
    if args.group == "group_b" and payload_uses_group_b_margin_features(payload):
        stock_data = attach_margin_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
        )
    if shared_feature_cols:
        llm_enabled = bool(payload.get(f"{args.group}_use_llm_sentiment", False))
        llm_path = _llm_sentiment_path_from_payload(payload, args.group) if llm_enabled else None
        stock_data = attach_market_features_db_first(
            stock_data,
            tickers,
            history_start,
            download_end,
            include_llm_sentiment=llm_enabled,
            llm_sentiment_path=llm_path,
        )

    panel = _align_panel(
        stock_data,
        tickers,
        simulation_start,
        as_of_date,
        shared_feature_cols=shared_feature_cols or None,
    )
    if panel.empty:
        raise RuntimeError("No aligned rows available to generate a signal")

    model = PPO.load(str(model_path))
    env = PortfolioEnv(
        panel,
        tickers,
        shared_feature_cols=shared_feature_cols or None,
        initial_cash=initial_cash,
        **env_kwargs,
    )
    obs, _ = env.reset()
    if override_holdings is not None:
        workbook_shares = override_holdings
        matched_row_label = str(override_source)
    else:
        assert xlsx_path is not None
        workbook_shares, matched_row_label = _load_group_holdings(xlsx_path, args.group, args.holdings_row_label)
    current_shares = {ticker: int(workbook_shares.get(ticker, 0)) for ticker in tickers}

    if args.live_start:
        if args.extra_cash < 0:
            raise ValueError("--extra-cash must be >= 0")
        _seed_live_start_reference_state(env, tickers)
        current_obs = env._get_obs()
        latest_action, _ = model.predict(current_obs, deterministic=True)
        decision = env.plan_action(int(latest_action))
    else:
        while env.step_idx < len(panel) - 1:
            action, _ = model.predict(obs, deterministic=True)
            obs, _, terminated, truncated, _ = env.step(action)
            if terminated or truncated:
                break
        current_obs = env._get_obs()
        latest_action, _ = model.predict(current_obs, deterministic=True)
        decision = env.plan_action(int(latest_action))

    actual_date = pd.Timestamp(panel.iloc[env.step_idx]["date"])
    latest_prices = {
        ticker: float(price)
        for ticker, price in zip(tickers, env.close_price_array[env.step_idx])
    }
    current_values = {
        ticker: float(current_shares[ticker] * latest_prices[ticker])
        for ticker in tickers
    }
    current_holdings_market_value = float(sum(current_values.values()))
    current_cash = float(args.extra_cash) if args.live_start else 0.0
    current_total_portfolio_value = float(current_holdings_market_value + current_cash)
    if current_total_portfolio_value <= 0.0:
        raise RuntimeError("Current portfolio value is zero")

    if args.live_start:
        current_weights = _weights_from_total_value(current_values, tickers, current_total_portfolio_value)
        current_cash_weight = max(float(current_cash), 0.0) / max(current_total_portfolio_value, 1.0)
    else:
        current_weights = _normalize_weights(current_values, tickers)
        current_cash_weight = 0.0

    strategy_value = float(env._portfolio_value(env.close_price_array[env.step_idx]))
    strategy_drawdown = float(strategy_value / max(env.peak_value, 1.0) - 1.0)
    relative_vs_0050 = 0.0
    if env.bh_0050_curve is not None:
        relative_vs_0050 = float(strategy_value / max(float(env.bh_0050_curve[env.step_idx]), 1.0) - 1.0)
    stale_days = max((pd.Timestamp(as_of_date) - actual_date).days, 0)

    guard_reasons = []
    if stale_days > args.max_stale_days:
        guard_reasons.append(f"stale_data_{stale_days}d")
    if strategy_drawdown <= -abs(args.max_strategy_drawdown):
        guard_reasons.append(f"drawdown_{strategy_drawdown:.2%}")
    if relative_vs_0050 <= -abs(args.max_underperformance_vs_0050):
        guard_reasons.append(f"underperform_vs_0050_{relative_vs_0050:.2%}")

    planned_target_weights = {
        ticker: float(decision["candidate_target_weights"].get(ticker, 0.0))
        for ticker in tickers
    }
    if guard_reasons:
        signal_status = "guard_blocked"
        signal_reason = "; ".join(guard_reasons)
        executable_target_weights = current_weights.copy()
        executable_cash_weight = float(current_cash_weight)
    elif decision["execute_trade"]:
        signal_status = "rebalance"
        signal_reason = str(decision["reason"])
        executable_target_weights = {
            ticker: float(decision["effective_target_weights"].get(ticker, 0.0))
            for ticker in tickers
        }
        executable_cash_weight = float(decision["effective_target_cash_weight"])
    else:
        signal_status = "hold"
        signal_reason = str(decision["reason"])
        executable_target_weights = current_weights.copy()
        executable_cash_weight = float(current_cash_weight)

    group_a_0050_weight_overlay = {
        "enabled": False,
        "reason": "not_group_a",
        "max_weight_step": args.group_a_0050_max_weight_step,
        "step_active_max_ma_ratio": args.group_a_0050_step_active_max_ma_ratio,
    }
    if args.group == "group_a" and signal_status == "rebalance":
        ma_brake_price = None
        ma_brake_value = None
        if (
            args.group_a_0050_ma_brake_window is not None
            and args.group_a_0050_ma_brake_window > 0
            and (
                args.group_a_0050_ma_brake_max_weight is not None
                or args.group_a_0050_step_active_max_ma_ratio is not None
            )
            and "0050.TW" in tickers
        ):
            close_idx = tickers.index("0050.TW")
            close_series = pd.Series(
                env.close_price_array[: env.step_idx + 1, close_idx],
                dtype=float,
            )
            ma_series = close_series.rolling(
                int(args.group_a_0050_ma_brake_window),
                min_periods=max(5, int(args.group_a_0050_ma_brake_window) // 3),
            ).mean()
            ma_brake_price = float(close_series.iloc[-1])
            ma_brake_value = float(ma_series.iloc[-1]) if pd.notna(ma_series.iloc[-1]) else None
        executable_target_weights, executable_cash_weight, group_a_0050_weight_overlay = (
            _apply_group_a_0050_weight_step_overlay(
                executable_target_weights,
                executable_cash_weight,
                {
                    ticker: float(decision["current_weights"].get(ticker, 0.0))
                    for ticker in tickers
                },
                args.group_a_0050_max_weight_step,
                step_active_max_ma_ratio=args.group_a_0050_step_active_max_ma_ratio,
                ma_brake_price=ma_brake_price,
                ma_brake_value=ma_brake_value,
                ma_brake_ratio=args.group_a_0050_ma_brake_ratio,
                ma_brake_max_weight=args.group_a_0050_ma_brake_max_weight,
                ma_brake_00631l_max_weight=args.group_a_0050_ma_brake_00631l_max_weight,
            )
        )
        if (
            group_a_0050_weight_overlay.get("enabled")
            and group_a_0050_weight_overlay.get("reason") != "no_adjustment_needed"
        ):
            signal_reason = f"{signal_reason}; {group_a_0050_weight_overlay['reason']}"

    strategy_weights = {
        ticker: float(decision["current_weights"].get(ticker, 0.0))
        for ticker in tickers
    }
    planned_target_shares = {}
    target_shares = {}
    rows = []
    for ticker in tickers:
        planned_value = current_total_portfolio_value * planned_target_weights[ticker]
        executable_value = current_total_portfolio_value * executable_target_weights[ticker]
        planned_shares = int(round(planned_value / latest_prices[ticker])) if latest_prices[ticker] > 0 else 0
        final_shares = int(round(executable_value / latest_prices[ticker])) if latest_prices[ticker] > 0 else 0
        planned_target_shares[ticker] = planned_shares
        target_shares[ticker] = final_shares
        weight_diff = float(executable_target_weights[ticker] - current_weights[ticker])
        delta_shares = int(final_shares - current_shares[ticker])
        rows.append(
            {
                "date": str(actual_date.date()),
                "ticker": ticker,
                "latest_price": float(latest_prices[ticker]),
                "current_shares": int(current_shares[ticker]),
                "current_weight": float(current_weights[ticker]),
                "strategy_weight": float(strategy_weights[ticker]),
                "planned_target_weight": float(planned_target_weights[ticker]),
                "target_weight": float(executable_target_weights[ticker]),
                "planned_target_shares": int(planned_shares),
                "target_shares": int(final_shares),
                "delta_shares": int(delta_shares),
                "weight_diff": float(weight_diff),
                "action_hint": _action_hint(weight_diff, delta_shares, args.action_threshold, signal_status),
                "signal_status": signal_status,
            }
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_prefix = PROJECT_ROOT / "results" / f"signal_{args.group}_{timestamp}"
    csv_path = out_prefix.with_suffix(".csv")
    json_path = out_prefix.with_suffix(".json")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    summary = {
        "group": args.group,
        "result_json": str(result_json),
        "model_path": str(model_path),
        "workbook": str(xlsx_path) if xlsx_path is not None else None,
        "signal_mode": "live_start" if args.live_start else "strategy_replay",
        "override_holdings_source": override_source,
        "holdings_row_label": matched_row_label,
        "requested_as_of_date": str(pd.Timestamp(as_of_date).date()),
        "actual_data_date": str(actual_date.date()),
        "stale_days": int(stale_days),
        "signal_status": signal_status,
        "signal_reason": signal_reason,
        "guard_reasons": guard_reasons,
        "group_a_action_schema": env.group_a_action_schema if args.group == "group_a" else None,
        "group_b_action_schema": env.group_b_action_schema if args.group == "group_b" else None,
        "latest_action": int(latest_action),
        "action_label": decision["action_label"],
        "base_target_label": decision["base_target_label"],
        "candidate_target_label": decision["candidate_target_label"],
        "effective_target_label": decision["effective_target_label"],
        "strategy_portfolio_value": float(strategy_value),
        "strategy_drawdown": float(strategy_drawdown),
        "relative_vs_0050_bh": float(relative_vs_0050),
        "current_holdings_market_value": float(current_holdings_market_value),
        "current_cash": float(current_cash),
        "current_cash_weight": float(current_cash_weight),
        "current_total_portfolio_value": float(current_total_portfolio_value),
        "reference_state_weights": (
            {
                ticker: float(decision["current_weights"].get(ticker, 0.0))
                for ticker in tickers
            }
            if args.live_start
            else None
        ),
        "reference_state_cash_weight": (
            float(decision["current_cash_weight"])
            if args.live_start
            else None
        ),
        "latest_prices": latest_prices,
        "current_shares": current_shares,
        "current_weights": current_weights,
        "strategy_weights": strategy_weights,
        "planned_target_weights": planned_target_weights,
        "planned_target_shares": planned_target_shares,
        "target_weights": executable_target_weights,
        "target_cash_weight": float(executable_cash_weight),
        "group_a_0050_weight_overlay": group_a_0050_weight_overlay,
        "target_shares": target_shares,
        "decision": decision,
        "output_csv": str(csv_path),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Signal status: {signal_status}")
    print(f"Reason:        {signal_reason}")
    print(f"Data date:     {actual_date.date()} (stale {stale_days}d)")
    print(f"Action:        {decision['action_label']}")
    print(f"Candidate:     {decision['candidate_target_label']}")
    executable_label = (
        _format_group_a_weights_label(executable_target_weights, executable_cash_weight)
        if args.group == "group_a" and signal_status == "rebalance"
        else decision["effective_target_label"]
        if signal_status == "rebalance"
        else "hold_current"
    )
    print(f"Executable:    {executable_label}")
    print(f"CSV:           {csv_path}")
    print(f"JSON:          {json_path}")


if __name__ == "__main__":
    main()
