#!/usr/bin/env python3
"""Targeted risk-off sweep for the Group A real meta ensemble."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_meta_ensemble import _normalize, _price_regimes, _rule_strategy
from backtest_group_a_tdcc_latest import DEFAULT_CONFIG, DEFAULT_DB, PROJECT_ROOT, TICKERS, _load_prices, _metrics, _resolve
from evaluate_group_a_tdcc_overlay_variants import Variant, _apply_hysteresis, _raw_tdcc_state


DEFAULT_SOURCE = PROJECT_ROOT / "results" / "group_a_meta_ensemble_real_backtest_20250601_20260603.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_meta_real_riskoff_sweep_20260603.json"


@dataclass(frozen=True)
class RiskOffVariant:
    name: str
    risk_off_cap: float | None
    destination: str = "cash"
    primary_fraction: float = 0.5
    tiered_cap: bool = False
    risk_off_rule_weight: float = 0.15
    risk_off_ppo_weight: float = 0.85
    caution_cap: float = 0.10
    inverse_weight: float = 0.0
    cash_floor: float = 0.0
    zero_small_inverse_threshold: float = 0.0
    fine_tiered_cap: bool = False
    momentum_cash_floor: bool = False
    momentum_cash_ma60_floor: float = 0.15
    momentum_cash_ma20_floor: float = 0.10
    momentum_cash_base_floor: float = 0.025
    adaptive_momentum_cash: bool = False
    trailing_stop_drawdown: float = 0.0
    trailing_stop_cap: float | None = None
    conditional_inverse_weight: float = 0.0
    conditional_inverse_min_weight: float = 0.0
    severe_inverse_weight: float = 0.0
    severe_ret5_threshold: float = -0.05
    severe_ret20_threshold: float = -0.10
    severe_price_only: bool = False
    leverage_cap_risk_on: float | None = None
    leverage_cap_neutral: float | None = None
    dynamic_cash: bool = False
    cash_risk_on_min: float = 0.15
    cash_risk_on_max: float = 0.20
    cash_neutral_min: float = 0.25
    cash_neutral_max: float = 0.30
    cash_risk_off_min: float = 0.40
    cash_risk_off_max: float = 0.55
    buydip_enabled: bool = False
    buydip_level1: float = -0.03
    buydip_level2: float = -0.05
    buydip_level3: float = -0.08
    buydip_add1: float = 0.05
    buydip_add2: float = 0.10
    buydip_add3: float = 0.20
    buydip_cash_floor: float = 0.12
    recovery_cash_cap: float | None = None
    recovery_leverage_cap: float | None = None
    recovery_requires_risk_on: bool = False
    recovery_bear_filter: bool = False
    recovery_ma60_slope_days: int = 10
    recovery_ret60_min: float = 0.0
    regime_vote: bool = False
    vote_bear_cap: float = 0.03
    vote_caution_cap: float = 0.08
    vote_cash_floor_bear: float = 0.22
    vote_cash_floor_caution: float = 0.15
    bear_defense: bool = False
    bear_defense_cap: float = 0.0
    bear_defense_cash_floor: float = 0.22
    bear_defense_disable_recovery: bool = True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--fee-rate", type=float, default=0.001425)
    return parser.parse_args()


def _event_map(events: list[dict[str, Any]]) -> dict[pd.Timestamp, dict[str, float]]:
    return {pd.Timestamp(event["date"]).normalize(): dict(event["target_weights"]) for event in events}


def _variants() -> list[RiskOffVariant]:
    variants = [
        RiskOffVariant("current_cap0_cash_rule15", risk_off_cap=0.00),
        RiskOffVariant("cap03_cash_rule10", risk_off_cap=0.03, risk_off_rule_weight=0.10, risk_off_ppo_weight=0.90),
        RiskOffVariant("cap05_cash_rule10", risk_off_cap=0.05, risk_off_rule_weight=0.10, risk_off_ppo_weight=0.90),
        RiskOffVariant("cap08_cash_rule10", risk_off_cap=0.08, risk_off_rule_weight=0.10, risk_off_ppo_weight=0.90),
        RiskOffVariant("cap03_split50_rule10", risk_off_cap=0.03, destination="split_primary_cash", primary_fraction=0.50, risk_off_rule_weight=0.10, risk_off_ppo_weight=0.90),
        RiskOffVariant("cap05_split50_rule10", risk_off_cap=0.05, destination="split_primary_cash", primary_fraction=0.50, risk_off_rule_weight=0.10, risk_off_ppo_weight=0.90),
        RiskOffVariant("cap08_split50_rule10", risk_off_cap=0.08, destination="split_primary_cash", primary_fraction=0.50, risk_off_rule_weight=0.10, risk_off_ppo_weight=0.90),
        RiskOffVariant("cap05_primary_rule05", risk_off_cap=0.05, destination="primary", risk_off_rule_weight=0.05, risk_off_ppo_weight=0.95),
        RiskOffVariant("cap08_primary_rule05", risk_off_cap=0.08, destination="primary", risk_off_rule_weight=0.05, risk_off_ppo_weight=0.95),
        RiskOffVariant("tiered_cash_rule10", risk_off_cap=None, tiered_cap=True, risk_off_rule_weight=0.10, risk_off_ppo_weight=0.90),
        RiskOffVariant("tiered_split50_rule10", risk_off_cap=None, tiered_cap=True, destination="split_primary_cash", primary_fraction=0.50, risk_off_rule_weight=0.10, risk_off_ppo_weight=0.90),
        RiskOffVariant("tiered_primary_rule05", risk_off_cap=None, tiered_cap=True, destination="primary", risk_off_rule_weight=0.05, risk_off_ppo_weight=0.95),
    ]
    for cap in [0.05, 0.06, 0.07, 0.08]:
        for cash_floor in [0.10, 0.15]:
            cap_label = f"{int(round(cap * 100)):02d}"
            cash_label = f"{int(round(cash_floor * 100)):02d}"
            variants.append(
                RiskOffVariant(
                    f"cap{cap_label}_primary_rule05_cash{cash_label}",
                    risk_off_cap=cap,
                    destination="primary",
                    risk_off_rule_weight=0.05,
                    risk_off_ppo_weight=0.95,
                    cash_floor=cash_floor,
                )
            )
            variants.append(
                RiskOffVariant(
                    f"cap{cap_label}_primary_rule05_cash{cash_label}_noinv",
                    risk_off_cap=cap,
                    destination="primary",
                    risk_off_rule_weight=0.05,
                    risk_off_ppo_weight=0.95,
                    cash_floor=cash_floor,
                    zero_small_inverse_threshold=0.01,
                )
            )
    for risk_cap in [0.09, 0.10, 0.12, 0.14]:
        for caution_cap in [0.12, 0.15, 0.20]:
            risk_label = f"{int(round(risk_cap * 100)):02d}"
            caution_label = f"{int(round(caution_cap * 100)):02d}"
            variants.append(
                RiskOffVariant(
                    f"focused_cap{risk_label}_caution{caution_label}_primary_rule05",
                    risk_off_cap=risk_cap,
                    caution_cap=caution_cap,
                    destination="primary",
                    risk_off_rule_weight=0.05,
                    risk_off_ppo_weight=0.95,
                    zero_small_inverse_threshold=0.01,
                    conditional_inverse_weight=0.01,
                    conditional_inverse_min_weight=0.01,
                )
            )
            variants.append(
                RiskOffVariant(
                    f"focused_cap{risk_label}_caution{caution_label}_primary_rule00",
                    risk_off_cap=risk_cap,
                    caution_cap=caution_cap,
                    destination="primary",
                    risk_off_rule_weight=0.0,
                    risk_off_ppo_weight=1.0,
                    zero_small_inverse_threshold=0.01,
                    conditional_inverse_weight=0.01,
                    conditional_inverse_min_weight=0.01,
                )
            )
    for risk_cap in [0.14, 0.16, 0.18, 0.20]:
        for caution_cap in [0.13, 0.14, 0.15, 0.16, 0.17]:
            risk_label = f"{int(round(risk_cap * 100)):02d}"
            caution_label = f"{int(round(caution_cap * 100)):02d}"
            variants.append(
                RiskOffVariant(
                    f"micro_cap{risk_label}_caution{caution_label}_primary_rule00",
                    risk_off_cap=risk_cap,
                    caution_cap=caution_cap,
                    destination="primary",
                    risk_off_rule_weight=0.0,
                    risk_off_ppo_weight=1.0,
                    zero_small_inverse_threshold=0.01,
                    conditional_inverse_weight=0.01,
                    conditional_inverse_min_weight=0.01,
                )
            )
    variants.extend(
        [
            RiskOffVariant(
                "balanced_cap12_dyn_cash_buydip",
                risk_off_cap=0.05,
                caution_cap=0.12,
                leverage_cap_risk_on=0.15,
                leverage_cap_neutral=0.12,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                dynamic_cash=True,
                buydip_enabled=True,
                zero_small_inverse_threshold=0.01,
            ),
            RiskOffVariant(
                "balanced_cap10_dyn_cash_buydip",
                risk_off_cap=0.03,
                caution_cap=0.10,
                leverage_cap_risk_on=0.12,
                leverage_cap_neutral=0.10,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                dynamic_cash=True,
                buydip_enabled=True,
                zero_small_inverse_threshold=0.01,
            ),
            RiskOffVariant(
                "balanced_cap15_dyn_cash_buydip",
                risk_off_cap=0.08,
                caution_cap=0.15,
                leverage_cap_risk_on=0.15,
                leverage_cap_neutral=0.12,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                dynamic_cash=True,
                buydip_enabled=True,
                buydip_add1=0.04,
                buydip_add2=0.08,
                buydip_add3=0.16,
                zero_small_inverse_threshold=0.01,
            ),
            RiskOffVariant(
                "balanced_defensive_cap08_dyn_cash_buydip",
                risk_off_cap=0.00,
                caution_cap=0.08,
                leverage_cap_risk_on=0.12,
                leverage_cap_neutral=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                dynamic_cash=True,
                cash_risk_on_min=0.18,
                cash_risk_on_max=0.24,
                cash_neutral_min=0.30,
                cash_neutral_max=0.36,
                cash_risk_off_min=0.45,
                cash_risk_off_max=0.58,
                buydip_enabled=True,
                buydip_add1=0.04,
                buydip_add2=0.08,
                buydip_add3=0.14,
                buydip_cash_floor=0.18,
                zero_small_inverse_threshold=0.01,
            ),
            RiskOffVariant(
                "balanced_light_cap12_dyn_cash_buydip",
                risk_off_cap=0.05,
                caution_cap=0.12,
                leverage_cap_risk_on=0.15,
                leverage_cap_neutral=0.12,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                dynamic_cash=True,
                cash_risk_on_min=0.12,
                cash_risk_on_max=0.22,
                cash_neutral_min=0.24,
                cash_neutral_max=0.32,
                cash_risk_off_min=0.32,
                cash_risk_off_max=0.45,
                buydip_enabled=True,
                buydip_add1=0.03,
                buydip_add2=0.06,
                buydip_add3=0.10,
                buydip_cash_floor=0.20,
                zero_small_inverse_threshold=0.01,
            ),
            RiskOffVariant(
                "balanced_momcash_cap08_buydip",
                risk_off_cap=0.08,
                caution_cap=0.12,
                leverage_cap_risk_on=0.15,
                leverage_cap_neutral=0.12,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.12,
                momentum_cash_ma20_floor=0.08,
                momentum_cash_base_floor=0.025,
                buydip_enabled=True,
                buydip_add1=0.03,
                buydip_add2=0.06,
                buydip_add3=0.10,
                buydip_cash_floor=0.20,
                zero_small_inverse_threshold=0.01,
            ),
            RiskOffVariant(
                "balanced_momcash_high_cap08_buydip",
                risk_off_cap=0.08,
                caution_cap=0.12,
                leverage_cap_risk_on=0.15,
                leverage_cap_neutral=0.12,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.22,
                momentum_cash_ma20_floor=0.15,
                momentum_cash_base_floor=0.025,
                buydip_enabled=True,
                buydip_add1=0.03,
                buydip_add2=0.06,
                buydip_add3=0.10,
                buydip_cash_floor=0.22,
                zero_small_inverse_threshold=0.01,
            ),
            RiskOffVariant(
                "adv_stop3_cap03",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                trailing_stop_drawdown=0.03,
                trailing_stop_cap=0.03,
            ),
            RiskOffVariant(
                "adv_stop5_cap03",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                trailing_stop_drawdown=0.05,
                trailing_stop_cap=0.03,
            ),
            RiskOffVariant(
                "adv_momentum_cash",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
            ),
            RiskOffVariant(
                "adv_momcash_light_12_08",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.12,
                momentum_cash_ma20_floor=0.08,
                momentum_cash_base_floor=0.025,
            ),
            RiskOffVariant(
                "adv_momcash_mid_18_12",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
            ),
            RiskOffVariant(
                "adv_momcash_high_22_15",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.22,
                momentum_cash_ma20_floor=0.15,
                momentum_cash_base_floor=0.025,
            ),
            RiskOffVariant(
                "adv_momcash_base05_15_10",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.15,
                momentum_cash_ma20_floor=0.10,
                momentum_cash_base_floor=0.05,
            ),
            RiskOffVariant(
                "adv_fine_tier_primary",
                risk_off_cap=None,
                fine_tiered_cap=True,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
            ),
            RiskOffVariant(
                "adv_conditional_inverse",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
            ),
            RiskOffVariant(
                "severe_inverse_05_fast",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.05,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
            ),
            RiskOffVariant(
                "severe_inverse_08_fast",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.08,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
            ),
            RiskOffVariant(
                "severe_inverse_10_fast",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.10,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
            ),
            RiskOffVariant(
                "severe_inverse_05_crash_strict",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.05,
                severe_ret5_threshold=-0.04,
                severe_ret20_threshold=-0.08,
            ),
            RiskOffVariant(
                "severe_inverse_08_relaxed",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.08,
                severe_ret5_threshold=-0.03,
                severe_ret20_threshold=-0.06,
            ),
            RiskOffVariant(
                "combo_momcash_severe03_fast",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.03,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
            ),
            RiskOffVariant(
                "combo_momcash_severe05_fast",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.05,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
            ),
            RiskOffVariant(
                "combo_momcash_severe08_fast",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.08,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
            ),
            RiskOffVariant(
                "combo_momcash_severe10_fast",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.10,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe10",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.10,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe08",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.08,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_recovery_cash10",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                recovery_cash_cap=0.10,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_recovery_step12",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                recovery_cash_cap=0.10,
                recovery_leverage_cap=0.12,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_recovery_step18",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                recovery_cash_cap=0.10,
                recovery_leverage_cap=0.18,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_riskon_recovery_step18",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                recovery_cash_cap=0.10,
                recovery_leverage_cap=0.18,
                recovery_requires_risk_on=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_bearfilter_recovery_step18",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                recovery_cash_cap=0.10,
                recovery_leverage_cap=0.18,
                recovery_bear_filter=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_regime_vote",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                regime_vote=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_bear_defense",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                bear_defense=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_vote_bearfilter_recovery",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                recovery_cash_cap=0.10,
                recovery_leverage_cap=0.18,
                recovery_bear_filter=True,
                regime_vote=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_vote_bearfilter_recovery_defensive",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                recovery_cash_cap=0.10,
                recovery_leverage_cap=0.18,
                recovery_bear_filter=True,
                regime_vote=True,
                vote_bear_cap=0.0,
                vote_caution_cap=0.06,
                vote_cash_floor_bear=0.25,
                vote_cash_floor_caution=0.18,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_vote_bearfilter_recovery_defense22",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                recovery_cash_cap=0.10,
                recovery_leverage_cap=0.18,
                recovery_bear_filter=True,
                regime_vote=True,
                bear_defense=True,
                bear_defense_cap=0.0,
                bear_defense_cash_floor=0.25,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_vote_bearfilter_recovery_balanced12",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                recovery_cash_cap=0.10,
                recovery_leverage_cap=0.12,
                recovery_bear_filter=True,
                regime_vote=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_vote_bearfilter_recovery_strict60",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                recovery_cash_cap=0.10,
                recovery_leverage_cap=0.18,
                recovery_bear_filter=True,
                recovery_ma60_slope_days=20,
                recovery_ret60_min=0.02,
                regime_vote=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe12_vote_bearfilter_recovery_cash12",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.12,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
                recovery_cash_cap=0.12,
                recovery_leverage_cap=0.16,
                recovery_bear_filter=True,
                regime_vote=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe10_soft",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.10,
                severe_ret5_threshold=-0.015,
                severe_ret20_threshold=-0.04,
                severe_price_only=True,
            ),
            RiskOffVariant(
                "adaptive_momcash_price_severe10_strict",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.18,
                momentum_cash_ma20_floor=0.12,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.10,
                severe_ret5_threshold=-0.03,
                severe_ret20_threshold=-0.06,
                severe_price_only=True,
            ),
            RiskOffVariant(
                "adaptive_balanced20_13_price_severe10",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.20,
                momentum_cash_ma20_floor=0.13,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.10,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
            ),
            RiskOffVariant(
                "adaptive_high_price_severe10",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                momentum_cash_ma60_floor=0.22,
                momentum_cash_ma20_floor=0.15,
                momentum_cash_base_floor=0.025,
                adaptive_momentum_cash=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.10,
                severe_ret5_threshold=-0.02,
                severe_ret20_threshold=-0.05,
                severe_price_only=True,
            ),
            RiskOffVariant(
                "combo_momcash_severe08_relaxed",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
                severe_inverse_weight=0.08,
                severe_ret5_threshold=-0.03,
                severe_ret20_threshold=-0.06,
            ),
            RiskOffVariant(
                "adv_stop5_momcash",
                risk_off_cap=0.08,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                trailing_stop_drawdown=0.05,
                trailing_stop_cap=0.03,
                momentum_cash_floor=True,
            ),
            RiskOffVariant(
                "adv_finetier_momcash",
                risk_off_cap=None,
                fine_tiered_cap=True,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                momentum_cash_floor=True,
            ),
            RiskOffVariant(
                "adv_all_controls",
                risk_off_cap=None,
                fine_tiered_cap=True,
                destination="primary",
                risk_off_rule_weight=0.05,
                risk_off_ppo_weight=0.95,
                trailing_stop_drawdown=0.05,
                trailing_stop_cap=0.03,
                momentum_cash_floor=True,
                zero_small_inverse_threshold=0.01,
                conditional_inverse_weight=0.01,
                conditional_inverse_min_weight=0.01,
            ),
        ]
    )
    return variants


def _blend(
    ppo: dict[str, float],
    a2c: dict[str, float],
    sac: dict[str, float],
    regime: str,
    variant: RiskOffVariant,
) -> tuple[dict[str, float], float, dict[str, Any]]:
    rule, rule_cash = _rule_strategy(regime)
    ppo, ppo_cash = _normalize(ppo, max(0.0, 1.0 - sum(ppo.values())))
    a2c, a2c_cash = _normalize(a2c, max(0.0, 1.0 - sum(a2c.values())))
    sac, sac_cash = _normalize(sac, max(0.0, 1.0 - sum(sac.values())))
    sleeves = {
        "ppo": (ppo, ppo_cash),
        "a2c": (a2c, a2c_cash),
        "sac": (sac, sac_cash),
        "rule_based": (rule, rule_cash),
    }
    if regime == "risk_on":
        alloc = {"ppo": 0.85, "a2c": 0.0, "sac": 0.10, "rule_based": 0.05}
    elif regime == "risk_off":
        alloc = {
            "ppo": variant.risk_off_ppo_weight,
            "a2c": 0.0,
            "sac": 0.0,
            "rule_based": variant.risk_off_rule_weight,
        }
    else:
        alloc = {"ppo": 0.90, "a2c": 0.0, "sac": 0.0, "rule_based": 0.10}
    total_alloc = sum(max(v, 0.0) for v in alloc.values())
    alloc = {name: max(weight, 0.0) / total_alloc for name, weight in alloc.items()}
    weights = {ticker: 0.0 for ticker in TICKERS}
    cash = 0.0
    for name, sleeve_weight in alloc.items():
        sleeve_weights, sleeve_cash = sleeves[name]
        for ticker in TICKERS:
            weights[ticker] += sleeve_weight * sleeve_weights.get(ticker, 0.0)
        cash += sleeve_weight * sleeve_cash
    weights, cash = _normalize(weights, cash)
    return weights, cash, {"regime": regime, "allocator_weights": alloc}


def _tdcc_pressure_score(config: dict[str, Any], assessment: dict[str, Any]) -> float | None:
    leverage = dict(assessment.get("snapshots", {}).get(str(config["leverage_ticker"]), {}))
    if not leverage.get("available"):
        return None
    risk_cfg = dict(config["risk_off"])
    minority_ratio = float(leverage["minority_percent_change"]) / float(risk_cfg["leverage_minority_percent_change"])
    people_ratio = float(leverage["total_people_change_ratio"]) / float(risk_cfg["leverage_total_people_change_ratio"])
    return max(minority_ratio, people_ratio)


def _tiered_risk_off_cap(config: dict[str, Any], assessment: dict[str, Any]) -> float:
    score = _tdcc_pressure_score(config, assessment)
    if score is None:
        return 0.05
    if score >= 1.25:
        return 0.00
    if score >= 1.05:
        return 0.03
    if score >= 0.90:
        return 0.05
    return 0.08


def _fine_tiered_risk_off_cap(config: dict[str, Any], assessment: dict[str, Any]) -> float:
    score = _tdcc_pressure_score(config, assessment)
    if score is None:
        return 0.05
    if score < 1.20:
        return 0.08
    if score < 1.60:
        return 0.05
    if score < 2.00:
        return 0.03
    return 0.00


def _apply_overlay(
    weights: dict[str, float],
    cash: float,
    *,
    state: str,
    regime: str,
    variant: RiskOffVariant,
    config: dict[str, Any],
    assessment: dict[str, Any],
    cap_override: float | None = None,
    cash_floor_override: float | None = None,
    conditional_inverse_allowed: bool = False,
    severe_inverse_allowed: bool = False,
    recovery_allowed: bool = False,
    buydip_tier: int = 0,
    dip_from_20d_high: float | None = None,
) -> tuple[dict[str, float], float, dict[str, Any]]:
    target = dict(weights)
    target_cash = float(cash)
    leverage = f"{config['leverage_ticker']}.TW"
    primary = f"{config['primary_ticker']}.TW"
    inverse = f"{config['inverse_ticker']}.TW"
    cap = None
    if state == "risk_off":
        if variant.fine_tiered_cap:
            cap = _fine_tiered_risk_off_cap(config, assessment)
        elif variant.tiered_cap:
            cap = _tiered_risk_off_cap(config, assessment)
        else:
            cap = variant.risk_off_cap
    elif state == "caution":
        cap = variant.caution_cap
    elif regime == "risk_on":
        cap = variant.leverage_cap_risk_on
    else:
        cap = variant.leverage_cap_neutral
    if cap_override is not None:
        cap = min(cap if cap is not None else cap_override, cap_override)
    released = 0.0
    if cap is not None:
        prior = target.get(leverage, 0.0)
        target[leverage] = min(prior, cap)
        released = prior - target[leverage]
        if variant.destination == "primary":
            target[primary] = target.get(primary, 0.0) + released
        elif variant.destination == "split_primary_cash":
            target[primary] = target.get(primary, 0.0) + released * variant.primary_fraction
            target_cash += released * (1.0 - variant.primary_fraction)
        else:
            target_cash += released
    inverse_added = 0.0
    if state == "risk_off" and variant.inverse_weight > 0.0:
        inverse_added = min(variant.inverse_weight, max(target_cash, 0.0))
        target[inverse] = target.get(inverse, 0.0) + inverse_added
        target_cash -= inverse_added
    if state == "risk_off" and conditional_inverse_allowed and variant.conditional_inverse_weight > 0.0:
        add = min(variant.conditional_inverse_weight, max(target_cash, 0.0))
        if add < variant.conditional_inverse_min_weight:
            primary_available = max(0.0, target.get(primary, 0.0))
            from_primary = min(variant.conditional_inverse_min_weight - add, primary_available)
            target[primary] = primary_available - from_primary
            add += from_primary
        target[inverse] = target.get(inverse, 0.0) + add
        target_cash = max(0.0, target_cash - min(variant.conditional_inverse_weight, target_cash))
        inverse_added += add
    if (
        (state == "risk_off" or variant.severe_price_only)
        and severe_inverse_allowed
        and variant.severe_inverse_weight > inverse_added
    ):
        extra_need = variant.severe_inverse_weight - inverse_added
        add = min(extra_need, max(target_cash, 0.0))
        if add < extra_need:
            primary_available = max(0.0, target.get(primary, 0.0))
            from_primary = min(extra_need - add, primary_available)
            target[primary] = primary_available - from_primary
            add += from_primary
        target[inverse] = target.get(inverse, 0.0) + add
        target_cash = max(0.0, target_cash - min(extra_need, target_cash))
        inverse_added += add
    inverse_zeroed = 0.0
    if (
        variant.zero_small_inverse_threshold > 0.0
        and not conditional_inverse_allowed
        and target.get(inverse, 0.0) < variant.zero_small_inverse_threshold
    ):
        inverse_zeroed = target.get(inverse, 0.0)
        target[inverse] = 0.0
        target_cash += inverse_zeroed
    cash_floor_release = 0.0
    effective_cash_floor = max(variant.cash_floor, float(cash_floor_override or 0.0))
    if effective_cash_floor > 0.0 and target_cash < effective_cash_floor:
        need_cash = effective_cash_floor - target_cash
        primary_available = max(0.0, target.get(primary, 0.0))
        cash_floor_release = min(need_cash, primary_available)
        target[primary] = primary_available - cash_floor_release
        target_cash += cash_floor_release
    recovery_cash_redeployed = 0.0
    recovery_leverage_added = 0.0
    if recovery_allowed and variant.recovery_cash_cap is not None and target_cash > variant.recovery_cash_cap:
        recovery_cash_redeployed = target_cash - variant.recovery_cash_cap
        target_cash = variant.recovery_cash_cap
        if variant.recovery_leverage_cap is not None:
            leverage_room = max(0.0, variant.recovery_leverage_cap - target.get(leverage, 0.0))
            recovery_leverage_added = min(recovery_cash_redeployed, leverage_room)
            target[leverage] = target.get(leverage, 0.0) + recovery_leverage_added
        target[primary] = target.get(primary, 0.0) + recovery_cash_redeployed - recovery_leverage_added
    dynamic_cash_adjustment = 0.0
    dynamic_cash_range = None
    if variant.dynamic_cash:
        if state == "risk_off" or regime == "risk_off":
            dynamic_cash_range = (variant.cash_risk_off_min, variant.cash_risk_off_max)
        elif regime == "risk_on":
            dynamic_cash_range = (variant.cash_risk_on_min, variant.cash_risk_on_max)
        else:
            dynamic_cash_range = (variant.cash_neutral_min, variant.cash_neutral_max)
        low, high = dynamic_cash_range
        if target_cash < low:
            need_cash = low - target_cash
            primary_available = max(0.0, target.get(primary, 0.0))
            release = min(need_cash, primary_available)
            target[primary] = primary_available - release
            target_cash += release
            dynamic_cash_adjustment += release
        elif target_cash > high:
            deploy = target_cash - high
            target[primary] = target.get(primary, 0.0) + deploy
            target_cash -= deploy
            dynamic_cash_adjustment -= deploy
    buydip_added = 0.0
    if variant.buydip_enabled and buydip_tier > 0:
        if buydip_tier >= 3:
            requested = variant.buydip_add3
        elif buydip_tier == 2:
            requested = variant.buydip_add2
        else:
            requested = variant.buydip_add1
        cash_floor = max(variant.buydip_cash_floor, effective_cash_floor)
        available_cash = max(0.0, target_cash - cash_floor)
        buydip_added = min(requested, available_cash)
        target[primary] = target.get(primary, 0.0) + buydip_added
        target_cash -= buydip_added
    target, target_cash = _normalize(target, target_cash)
    return target, target_cash, {
        "tdcc_state": state,
        "cap": cap,
        "tiered_cap": variant.tiered_cap,
        "fine_tiered_cap": variant.fine_tiered_cap,
        "tdcc_pressure_score": _tdcc_pressure_score(config, assessment),
        "released_leverage_budget": released,
        "destination": variant.destination,
        "inverse_added": inverse_added,
        "inverse_zeroed": inverse_zeroed,
        "cash_floor": effective_cash_floor,
        "cash_floor_release": cash_floor_release,
        "cap_override": cap_override,
        "conditional_inverse_allowed": conditional_inverse_allowed,
        "severe_inverse_allowed": severe_inverse_allowed,
        "recovery_allowed": recovery_allowed,
        "recovery_cash_redeployed": recovery_cash_redeployed,
        "recovery_leverage_added": recovery_leverage_added,
        "dynamic_cash": variant.dynamic_cash,
        "dynamic_cash_range": dynamic_cash_range,
        "dynamic_cash_adjustment": dynamic_cash_adjustment,
        "buydip_tier": buydip_tier,
        "dip_from_20d_high": dip_from_20d_high,
        "buydip_added_to_primary": buydip_added,
    }


def _simulate(
    prices: pd.DataFrame,
    source: dict[str, Any],
    config: dict[str, Any],
    raw: dict[pd.Timestamp, dict[str, Any]],
    tdcc_by_date: dict[pd.Timestamp, str],
    regime_by_date: dict[pd.Timestamp, str],
    variant: RiskOffVariant,
    fee_rate: float,
) -> dict[str, Any]:
    base = source["base_exact_backtest"]
    ppo_by_date = _event_map(base["rebalance_events"])
    a2c_by_date = _event_map(source["a2c_shadow_backtest"]["rebalance_events"])
    sac_by_date = _event_map(source["sac_shadow_backtest"]["rebalance_events"])
    dca_by_date = {pd.Timestamp(item["date"]).normalize(): item for item in base["dca_purchase_history"]}
    initial_cash = float(base["total_invested_capital"] - base["dca_total_contributions"])

    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = initial_cash
    fees = 0.0
    contributions = 0.0
    rebalances = 0
    last_ppo = last_a2c = last_sac = None
    last_target = None
    last_cash = None
    last_state = None
    last_regime = None
    curve = []
    events = []
    cap_counts: dict[str, int] = {}
    close = prices["0050.TW"]
    ma20 = close.rolling(20, min_periods=10).mean()
    ma60 = close.rolling(60, min_periods=20).mean()
    ma20_rising = ma20.diff(5) > 0
    ma60_slope = ma60.diff(variant.recovery_ma60_slope_days)
    ret5 = close.pct_change(5)
    ret20 = close.pct_change(20)
    ret21 = close.pct_change(21)
    ret60 = close.pct_change(60)
    high20 = close.rolling(20, min_periods=10).max()
    peak_value = initial_cash
    trailing_stop_count = 0
    momentum_cash_count = 0
    conditional_inverse_count = 0
    severe_inverse_count = 0
    recovery_count = 0
    regime_vote_count = 0
    bear_defense_count = 0
    buydip_counts = {1: 0, 2: 0, 3: 0}
    last_buydip_tier = 0

    for dt, row in prices.iterrows():
        state = tdcc_by_date[dt]
        regime = regime_by_date[dt]
        if dt in dca_by_date:
            item = dca_by_date[dt]
            amount = float(item.get("total_contribution", 0.0))
            purchase = item.get("purchases", {}).get("0050.TW")
            if purchase and amount > 0:
                fee = amount * fee_rate / (1.0 + fee_rate)
                shares["0050.TW"] += (amount - fee) / float(row["0050.TW"])
                fees += fee
                contributions += amount
            elif amount > 0:
                cash += amount
                contributions += amount
        total_value = cash + sum(shares[ticker] * float(row[ticker]) for ticker in TICKERS)
        peak_value = max(peak_value, total_value)
        strategy_drawdown = total_value / max(peak_value, 1.0) - 1.0
        updated = False
        if dt in ppo_by_date:
            last_ppo = ppo_by_date[dt]
            updated = True
        if dt in a2c_by_date:
            last_a2c = a2c_by_date[dt]
            updated = True
        if dt in sac_by_date:
            last_sac = sac_by_date[dt]
            updated = True
        changed_state = last_state is not None and state != last_state
        changed_regime = last_regime is not None and regime != last_regime
        dip_from_20d_high = None
        buydip_tier = 0
        if variant.buydip_enabled and pd.notna(high20.loc[dt]) and float(high20.loc[dt]) > 0.0:
            dip_from_20d_high = float(close.loc[dt]) / float(high20.loc[dt]) - 1.0
            if dip_from_20d_high <= variant.buydip_level3:
                buydip_tier = 3
            elif dip_from_20d_high <= variant.buydip_level2:
                buydip_tier = 2
            elif dip_from_20d_high <= variant.buydip_level1:
                buydip_tier = 1
        changed_buydip_tier = variant.buydip_enabled and buydip_tier != last_buydip_tier
        if (updated or changed_state or changed_regime or changed_buydip_tier) and last_ppo is not None:
            blended, blended_cash, blend_diag = _blend(last_ppo, last_a2c or last_ppo, last_sac or last_ppo, regime, variant)
            cap_override = None
            if (
                variant.trailing_stop_drawdown > 0.0
                and strategy_drawdown <= -variant.trailing_stop_drawdown
                and variant.trailing_stop_cap is not None
            ):
                cap_override = variant.trailing_stop_cap
                trailing_stop_count += 1
            cash_floor_override = None
            if variant.momentum_cash_floor:
                current_close = float(close.loc[dt])
                use_high_floor = (
                    variant.adaptive_momentum_cash
                    and pd.notna(ret20.loc[dt])
                    and pd.notna(ma60.loc[dt])
                    and current_close < float(ma60.loc[dt])
                    and float(ret20.loc[dt]) < -0.03
                )
                if use_high_floor:
                    cash_floor_override = max(0.22, variant.momentum_cash_ma60_floor)
                elif pd.notna(ma60.loc[dt]) and current_close < float(ma60.loc[dt]):
                    cash_floor_override = variant.momentum_cash_ma60_floor
                elif (
                    pd.notna(ma20.loc[dt])
                    and (current_close < float(ma20.loc[dt]) or not bool(ma20_rising.loc[dt]))
                ):
                    cash_floor_override = variant.momentum_cash_ma20_floor
                else:
                    cash_floor_override = variant.momentum_cash_base_floor
                if cash_floor_override > variant.momentum_cash_base_floor:
                    momentum_cash_count += 1
            current_close = float(close.loc[dt])
            bearish_price = (
                pd.notna(ma60.loc[dt])
                and pd.notna(ma60_slope.loc[dt])
                and pd.notna(ret20.loc[dt])
                and current_close < float(ma60.loc[dt])
                and float(ma60_slope.loc[dt]) < 0.0
                and float(ret20.loc[dt]) < 0.0
            )
            if variant.regime_vote:
                vote_score = 0
                if state == "risk_off":
                    vote_score += 2
                elif state == "caution":
                    vote_score += 1
                if pd.notna(ma60.loc[dt]) and current_close < float(ma60.loc[dt]):
                    vote_score += 1
                if pd.notna(ma60_slope.loc[dt]) and float(ma60_slope.loc[dt]) < 0.0:
                    vote_score += 1
                if pd.notna(ret20.loc[dt]) and float(ret20.loc[dt]) < 0.0:
                    vote_score += 1
                if pd.notna(ret5.loc[dt]) and float(ret5.loc[dt]) < 0.0:
                    vote_score += 1
                if vote_score >= 4:
                    cap_override = min(cap_override if cap_override is not None else variant.vote_bear_cap, variant.vote_bear_cap)
                    cash_floor_override = max(float(cash_floor_override or 0.0), variant.vote_cash_floor_bear)
                    regime_vote_count += 1
                elif vote_score >= 2:
                    cap_override = min(cap_override if cap_override is not None else variant.vote_caution_cap, variant.vote_caution_cap)
                    cash_floor_override = max(float(cash_floor_override or 0.0), variant.vote_cash_floor_caution)
                    regime_vote_count += 1
            if variant.bear_defense and bearish_price:
                cap_override = min(cap_override if cap_override is not None else variant.bear_defense_cap, variant.bear_defense_cap)
                cash_floor_override = max(float(cash_floor_override or 0.0), variant.bear_defense_cash_floor)
                bear_defense_count += 1
            conditional_inverse_allowed = (
                variant.conditional_inverse_weight > 0.0
                and pd.notna(ma60.loc[dt])
                and pd.notna(ret5.loc[dt])
                and float(close.loc[dt]) < float(ma60.loc[dt])
                and float(ret5.loc[dt]) < -0.03
            )
            severe_inverse_allowed = (
                variant.severe_inverse_weight > 0.0
                and (state == "risk_off" or variant.severe_price_only)
                and pd.notna(ma60.loc[dt])
                and pd.notna(ret5.loc[dt])
                and pd.notna(ret20.loc[dt])
                and float(close.loc[dt]) < float(ma60.loc[dt])
                and float(ret5.loc[dt]) < variant.severe_ret5_threshold
                and float(ret20.loc[dt]) < variant.severe_ret20_threshold
            )
            recovery_allowed = (
                variant.recovery_cash_cap is not None
                and state != "risk_off"
                and pd.notna(ma60.loc[dt])
                and pd.notna(ret21.loc[dt])
                and float(close.loc[dt]) > float(ma60.loc[dt])
                and float(ret21.loc[dt]) > 0.0
                and (regime == "risk_on" or not variant.recovery_requires_risk_on)
                and not (variant.bear_defense and variant.bear_defense_disable_recovery and bearish_price)
                and (
                    not variant.recovery_bear_filter
                    or (
                        pd.notna(ma60_slope.loc[dt])
                        and pd.notna(ret60.loc[dt])
                        and float(ma60_slope.loc[dt]) > 0.0
                        and float(ret60.loc[dt]) >= variant.recovery_ret60_min
                    )
                )
            )
            if conditional_inverse_allowed:
                conditional_inverse_count += 1
            if severe_inverse_allowed:
                severe_inverse_count += 1
            if recovery_allowed:
                recovery_count += 1
            target, target_cash, overlay_diag = _apply_overlay(
                blended,
                blended_cash,
                state=state,
                regime=regime,
                variant=variant,
                config=config,
                assessment=raw[dt],
                cap_override=cap_override,
                cash_floor_override=cash_floor_override,
                conditional_inverse_allowed=conditional_inverse_allowed,
                severe_inverse_allowed=severe_inverse_allowed,
                recovery_allowed=recovery_allowed,
                buydip_tier=buydip_tier,
                dip_from_20d_high=dip_from_20d_high,
            )
            if overlay_diag["buydip_added_to_primary"] > 0.0:
                buydip_counts[buydip_tier] = buydip_counts.get(buydip_tier, 0) + 1
            if overlay_diag["cap"] is not None:
                cap_key = f"{float(overlay_diag['cap']):.2f}"
                cap_counts[cap_key] = cap_counts.get(cap_key, 0) + 1
            changed = (
                last_target is None
                or any(abs(target.get(t, 0.0) - last_target.get(t, 0.0)) > 1e-12 for t in TICKERS)
                or abs(target_cash - float(last_cash or 0.0)) > 1e-12
            )
            if changed:
                target_values = {ticker: total_value * target.get(ticker, 0.0) for ticker in TICKERS}
                trade_value = sum(abs(target_values[ticker] - shares[ticker] * float(row[ticker])) for ticker in TICKERS)
                fee = trade_value * fee_rate
                after_fee = max(total_value - fee, 0.0)
                shares = {ticker: after_fee * target.get(ticker, 0.0) / float(row[ticker]) for ticker in TICKERS}
                cash = after_fee * target_cash
                fees += fee
                rebalances += 1
                last_target = dict(target)
                last_cash = target_cash
                total_value = cash + sum(shares[ticker] * float(row[ticker]) for ticker in TICKERS)
                events.append(
                    {
                        "date": str(dt.date()),
                        "tdcc_state": state,
                        "regime": regime,
                        "target_weights": target,
                        "target_cash_weight": target_cash,
                        "fee": fee,
                        "strategy_drawdown": strategy_drawdown,
                        "blend": blend_diag,
                        "overlay": overlay_diag,
                    }
                )
        last_state = state
        last_regime = regime
        last_buydip_tier = buydip_tier
        curve.append({"date": str(dt.date()), "value": float(total_value), "tdcc_state": state, "regime": regime})

    values = pd.Series([item["value"] for item in curve], index=pd.to_datetime([item["date"] for item in curve]))
    final_value = float(values.iloc[-1])
    final_weights = {ticker: float(shares[ticker] * float(prices.iloc[-1][ticker]) / final_value) for ticker in TICKERS}
    return {
        "metrics": _metrics(values, initial_cash, contributions, fees, rebalances),
        "events": events,
        "equity_curve": curve,
        "final_shares": shares,
        "final_cash": cash,
        "final_weights": final_weights,
        "final_cash_weight": float(cash / max(final_value, 1.0)),
        "cap_counts": cap_counts,
        "control_counts": {
            "trailing_stop": trailing_stop_count,
            "momentum_cash": momentum_cash_count,
            "conditional_inverse": conditional_inverse_count,
            "severe_inverse": severe_inverse_count,
            "recovery": recovery_count,
            "regime_vote": regime_vote_count,
            "bear_defense": bear_defense_count,
            "buydip_level1": buydip_counts.get(1, 0),
            "buydip_level2": buydip_counts.get(2, 0),
            "buydip_level3": buydip_counts.get(3, 0),
        },
    }


def _composite_score(row: dict[str, Any], base: dict[str, Any]) -> float:
    final_value = float(row["final_value"])
    mdd_bonus = 120_000.0 * max(0.0, float(row["max_drawdown"]) - float(base["max_drawdown"]))
    sharpe_bonus = 50_000.0 * (float(row["sharpe_ratio"]) - float(base["sharpe_ratio"]))
    extra_rebalances = max(0, int(row["num_rebalances"]) - int(base["num_trades"]))
    rebalance_penalty = 1_000.0 * extra_rebalances
    low_cash_penalty = 200_000.0 * max(0.0, 0.05 - float(row["final_cash_weight"]))
    return final_value + mdd_bonus + sharpe_bonus - rebalance_penalty - low_cash_penalty


def _balanced_score(row: dict[str, Any], base: dict[str, Any]) -> float:
    final_value = float(row["final_value"])
    final_gap = final_value - float(base["final_value"])
    mdd_improvement = float(row["max_drawdown"]) - float(base["max_drawdown"])
    sharpe_improvement = float(row["sharpe_ratio"]) - float(base["sharpe_ratio"])
    extra_rebalances = max(0, int(row["num_rebalances"]) - int(base["num_trades"]))
    return (
        final_value
        + 350_000.0 * max(0.0, mdd_improvement)
        - 250_000.0 * max(0.0, -mdd_improvement)
        + 90_000.0 * sharpe_improvement
        - 0.35 * max(0.0, -final_gap)
        - 1_500.0 * extra_rebalances
    )


def _fixed_strategy_score(row: dict[str, Any], base: dict[str, Any]) -> float:
    """Single-window score with stable weights for comparing Group A candidates."""
    final_value = float(row["final_value"])
    final_gap = final_value - float(base["final_value"])
    sharpe = float(row["sharpe_ratio"])
    mdd = float(row["max_drawdown"])
    base_mdd = float(base["max_drawdown"])
    mdd_improvement = mdd - base_mdd
    extra_rebalances = max(0, int(row["num_rebalances"]) - int(base["num_trades"]))
    low_cash_penalty = 150_000.0 * max(0.0, 0.08 - float(row["final_cash_weight"]))
    severe_mdd_penalty = 500_000.0 * max(0.0, -0.25 - mdd)
    return (
        final_value
        + 0.30 * max(final_gap, 0.0)
        - 0.20 * max(-final_gap, 0.0)
        + 85_000.0 * sharpe
        + 250_000.0 * max(0.0, mdd_improvement)
        - 200_000.0 * max(0.0, -mdd_improvement)
        - 1_200.0 * extra_rebalances
        - low_cash_penalty
        - severe_mdd_penalty
    )


def main() -> None:
    args = _parse_args()
    source_path = _resolve(args.source)
    config_path = _resolve(args.config)
    db_path = _resolve(args.db)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    dates = [pd.Timestamp(item["date"]).normalize() for item in source["latest_tdcc_overlay_replay"]["equity_curve"]]
    prices = _load_prices(db_path, dates)
    raw = {dt: _raw_tdcc_state(config, db_path, dt) for dt in prices.index}
    raw_states = [str(raw[dt]["state"]) for dt in prices.index]
    effective_states = _apply_hysteresis(
        raw_states,
        Variant("latest_default", risk_off_cap=float(config["risk_off"]["leverage_weight_cap"])),
    )
    tdcc_by_date = dict(zip(prices.index, effective_states))
    regime_by_date = _price_regimes(prices, tdcc_by_date)
    base = source["base_exact_backtest"]
    tdcc = source["latest_tdcc_overlay_replay"]["metrics"]
    rows = []
    details = {}
    for variant in _variants():
        replay = _simulate(
            prices,
            source,
            config,
            raw,
            tdcc_by_date,
            regime_by_date,
            variant,
            float(args.fee_rate),
        )
        metrics = replay["metrics"]
        row = {
            "variant": variant.name,
            **metrics,
            "delta_final_vs_base": metrics["final_value"] - base["final_value"],
            "delta_sharpe_vs_base": metrics["sharpe_ratio"] - base["sharpe_ratio"],
            "delta_mdd_vs_base": metrics["max_drawdown"] - base["max_drawdown"],
            "delta_final_vs_tdcc": metrics["final_value"] - tdcc["final_value"],
            "delta_sharpe_vs_tdcc": metrics["sharpe_ratio"] - tdcc["sharpe_ratio"],
            "delta_mdd_vs_tdcc": metrics["max_drawdown"] - tdcc["max_drawdown"],
            "final_cash_weight": replay["final_cash_weight"],
            "control_counts": replay["control_counts"],
            **{f"final_{ticker}": replay["final_weights"][ticker] for ticker in TICKERS},
        }
        row["composite_score"] = _composite_score(row, base)
        row["balanced_score"] = _balanced_score(row, base)
        row["fixed_score"] = _fixed_strategy_score(row, base)
        rows.append(row)
        details[variant.name] = {"variant": variant.__dict__, "replay": replay}
    ranked = sorted(rows, key=lambda row: (row["final_value"], row["sharpe_ratio"]), reverse=True)
    score_ranked = sorted(rows, key=lambda row: row["composite_score"], reverse=True)
    balanced_ranked = sorted(rows, key=lambda row: row["balanced_score"], reverse=True)
    fixed_ranked = sorted(rows, key=lambda row: row["fixed_score"], reverse=True)
    report = {
        "experiment": "GroupA_meta_real_riskoff_sweep",
        "source": str(source_path.resolve()),
        "actual_window": source["actual_window"],
        "base_final_value": base["final_value"],
        "tdcc_final_value": tdcc["final_value"],
        "scope": "Directions 1 and 2: lower risk-off defensive intensity and tier TDCC risk-off caps.",
        "variants": ranked,
        "score_ranked_variant_names": [row["variant"] for row in score_ranked],
        "balanced_ranked_variant_names": [row["variant"] for row in balanced_ranked],
        "fixed_ranked_variant_names": [row["variant"] for row in fixed_ranked],
        "details": details,
    }
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(ranked).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    for row in ranked:
        print(
            f"{row['variant']}: final={row['final_value']:.2f}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, rebalances={row['num_rebalances']}, "
            f"cash={row['final_cash_weight']:.2%}, 631L={row['final_00631L.TW']:.2%}, "
            f"score={row['composite_score']:.2f}, balanced={row['balanced_score']:.2f}"
        )
    print("Top by composite score:")
    for row in score_ranked[:8]:
        print(
            f"  {row['variant']}: score={row['composite_score']:.2f}, final={row['final_value']:.2f}, "
            f"sharpe={row['sharpe_ratio']:.4f}, mdd={row['max_drawdown']:.4%}, cash={row['final_cash_weight']:.2%}"
        )
    print("Top by balanced score:")
    for row in balanced_ranked[:8]:
        print(
            f"  {row['variant']}: balanced={row['balanced_score']:.2f}, final={row['final_value']:.2f}, "
            f"sharpe={row['sharpe_ratio']:.4f}, mdd={row['max_drawdown']:.4%}, cash={row['final_cash_weight']:.2%}"
        )


if __name__ == "__main__":
    main()
