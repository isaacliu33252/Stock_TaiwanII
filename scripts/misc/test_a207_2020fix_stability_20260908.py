#!/usr/bin/env python3
"""Direction #8 (Fable 10-directions list): walk-forward stability check for
the 2020 COVID switch-rule fix (risk_score_lookback_days=5,
momentum_fast_exit_min=0.10, momentum_fast_exit_ma_gap_min=-0.08 layered on
top of A207_RULE). Compares pre-fix vs post-fix regime-switch outcomes across
three independent stress windows (2020 COVID, 2022 bear market, 2025-03
tariff shock) to check whether the fix -- validated only against 2020 -- is
robust elsewhere or shows overfitting-to-2020 red flags.

Read-only research. Does not touch any production/live file.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    _load_chip_features,
    _load_prices,
    _metrics,
    _simulate_regime_curve,
    _switch_returns,
)
from group_a_plus.runners.a207 import A207_RULE
from backtest_group_a_plus_policy_signal import TICKERS as ALL_TICKERS

TICKERS = list(ALL_TICKERS)  # module-level _rebalance()/_mark_to_market() iterate this full set
GOLDEN1 = {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30}
DEFENSIVE = {"0050.TW": 0.40, "cash": 0.60}
INITIAL_VALUE = 1_000_000.0

WINDOWS = [
    ("2020_covid", "2020-01-02", "2020-12-31"),
    ("2022_bear", "2022-01-03", "2022-12-30"),
    ("2025_tariff", "2025-01-02", "2025-12-31"),
]

WARMUP_DAYS = 200


def run_variant(prices, chip_features, *, fixed: bool):
    kwargs = {}
    if fixed:
        kwargs = dict(
            risk_score_lookback_days=5,
            momentum_fast_exit_min=0.10,
            momentum_fast_exit_ma_gap_min=-0.08,
        )
    events, frame = _switch_returns(prices, chip_features, A207_RULE, **kwargs)
    regimes = frame["regime"].astype(str)
    weights_by_regime = {"golden1": GOLDEN1, "group_a_plus_defensive": DEFENSIVE}
    curve = _simulate_regime_curve(prices[TICKERS], regimes, weights_by_regime, INITIAL_VALUE)
    return curve, regimes


def trim(curve, regimes, start, end):
    return curve.loc[start:end], regimes.loc[start:end]


def main():
    import pandas as pd

    for label, start, end in WINDOWS:
        load_start = (pd.Timestamp(start) - pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")
        prices = _load_prices(DB_PATH, TICKERS, load_start, end)
        chip_features = _load_chip_features(DB_PATH, prices.index, load_start, end)

        curve_pre, reg_pre = run_variant(prices, chip_features, fixed=False)
        curve_post, reg_post = run_variant(prices, chip_features, fixed=True)

        curve_pre_w, reg_pre_w = trim(curve_pre, reg_pre, start, end)
        curve_post_w, reg_post_w = trim(curve_post, reg_post, start, end)

        # renormalize each window's curve to start at INITIAL_VALUE at window start
        # (curve carries warmup drift; use return-based rebasing for fair comparison)
        base_pre = curve_pre_w.iloc[0]
        base_post = curve_post_w.iloc[0]
        curve_pre_reb = curve_pre_w / base_pre * INITIAL_VALUE
        curve_post_reb = curve_post_w / base_post * INITIAL_VALUE

        m_pre = _metrics(curve_pre_reb, INITIAL_VALUE)
        m_post = _metrics(curve_post_reb, INITIAL_VALUE)

        defensive_days_pre = int((reg_pre_w == "group_a_plus_defensive").sum())
        defensive_days_post = int((reg_post_w == "group_a_plus_defensive").sum())

        print(f"=== {label} ({start}..{end}) ===")
        print(f"  PRE-fix : final={m_pre['final_value']:,.0f} sharpe={m_pre['sharpe_ratio']:.4f} "
              f"mdd={m_pre['max_drawdown']*100:.2f}% defensive_days={defensive_days_pre}")
        print(f"  POST-fix: final={m_post['final_value']:,.0f} sharpe={m_post['sharpe_ratio']:.4f} "
              f"mdd={m_post['max_drawdown']*100:.2f}% defensive_days={defensive_days_post}")
        d_final = m_post['final_value'] - m_pre['final_value']
        d_sharpe = m_post['sharpe_ratio'] - m_pre['sharpe_ratio']
        d_mdd = (m_post['max_drawdown'] - m_pre['max_drawdown']) * 100
        print(f"  DELTA (post-pre): final={d_final:+,.0f} sharpe={d_sharpe:+.4f} mdd={d_mdd:+.2f}pp")
        print()


if __name__ == "__main__":
    main()
