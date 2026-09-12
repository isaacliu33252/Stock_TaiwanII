"""2026-08-11 fix: `_simulate_regime_curve` only rebalanced when the regime
label changed. A constant regime (golden1_0531_1m/group_a_plus_defensive_1m
are simulated with a regime series that never changes) therefore rebalanced
exactly once at t=0 and never again -- a leveraged sleeve (00631L, 2x) then
drifted away from its target weight indefinitely as it compounded faster
than the rest of the portfolio. Verified against real data: 00631L's weight
in golden1_0531_1m drifted from 20% at inception (2017) to 62% by 2026-08 in
the never-rebalanced curve, which fully explained both an inflated realized
market beta (1.337 vs a nominal ~1.0) and a crash-window underperformance
that worsened every year. `rebalance_every_days` is opt-in (default None
preserves the original, unchanged behavior for every existing caller/test)
and adds a periodic rebalance on top of the regime-change trigger. See
GROUP_A_PLUS_20260811_ALPHAZEROBETA_FACTOR_ATTRIBUTION_AND_CRASH_PROTECTION_HANDOFF.md
section 8 for the full discovery and derivation.
"""

from __future__ import annotations

import pandas as pd

from backtest_group_a_plus_switch_policy import TICKERS, _simulate_regime_curve

WEIGHTS_BY_REGIME = {
    "golden1": {"0050.TW": 0.6, "00631L.TW": 0.2, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.2},
}


def _make_prices(n_days: int, leveraged_daily_return: float) -> pd.DataFrame:
    """0050/00632R/00679B held flat at 100; 00631L compounds at
    `leveraged_daily_return` every day, simulating a leveraged sleeve that
    persistently outpaces the rest of the portfolio."""
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    letf_prices = [100.0 * (1.0 + leveraged_daily_return) ** i for i in range(n_days)]
    return pd.DataFrame(
        {
            "0050.TW": 100.0,
            "00631L.TW": letf_prices,
            "00632R.TW": 100.0,
            "00679B.TWO": 100.0,
        },
        index=dates,
    )


def _letf_weight(shares_letf: float, price_letf: float, total_value: float) -> float:
    return shares_letf * price_letf / total_value


def test_default_never_rebalances_constant_regime_and_weight_drifts():
    prices = _make_prices(n_days=252, leveraged_daily_return=0.01)
    regimes = pd.Series("golden1", index=prices.index)

    curve = _simulate_regime_curve(prices, regimes, WEIGHTS_BY_REGIME, initial_value=1_000_000.0)

    # Reconstruct 00631L's weight at the end under a buy-once-at-t0 assumption.
    initial_letf_shares = 0.2 * 1_000_000.0 / prices["00631L.TW"].iloc[0]
    final_letf_value = initial_letf_shares * prices["00631L.TW"].iloc[-1]
    final_weight = final_letf_value / curve.iloc[-1]

    assert final_weight > 0.5, "00631L's weight should have drifted well above its 20% target with no rebalancing"


def test_periodic_rebalance_bounds_weight_drift():
    prices = _make_prices(n_days=252, leveraged_daily_return=0.01)
    regimes = pd.Series("golden1", index=prices.index)

    unrebalanced = _simulate_regime_curve(prices, regimes, WEIGHTS_BY_REGIME, initial_value=1_000_000.0)
    rebalanced = _simulate_regime_curve(
        prices, regimes, WEIGHTS_BY_REGIME, initial_value=1_000_000.0, rebalance_every_days=21
    )

    # With the same inputs, periodic rebalancing trims the winning leveraged
    # sleeve back toward target repeatedly, so it should compound to a lower
    # final value than letting it run unrebalanced in a persistently rising
    # market (this is the expected trade-off, not a bug).
    assert rebalanced.iloc[-1] < unrebalanced.iloc[-1]


def test_rebalance_every_days_default_matches_original_behavior():
    """Default (None) must reproduce the exact original rebalance-only-on-
    regime-change behavior -- no existing caller/test should see any
    difference."""
    prices = _make_prices(n_days=120, leveraged_daily_return=0.005)
    regimes = pd.Series("golden1", index=prices.index)

    default_curve = _simulate_regime_curve(prices, regimes, WEIGHTS_BY_REGIME, initial_value=1_000_000.0)
    explicit_none_curve = _simulate_regime_curve(
        prices, regimes, WEIGHTS_BY_REGIME, initial_value=1_000_000.0, rebalance_every_days=None
    )

    pd.testing.assert_series_equal(default_curve, explicit_none_curve)


def test_regime_change_still_rebalances_with_periodic_option_set():
    prices = _make_prices(n_days=60, leveraged_daily_return=0.01)
    weights = {
        "golden1": {"0050.TW": 0.6, "00631L.TW": 0.2, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.2},
        "group_a_plus_defensive": {"0050.TW": 0.0, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 1.0},
    }
    regimes = pd.Series("golden1", index=prices.index)
    regimes.iloc[30:] = "group_a_plus_defensive"

    curve = _simulate_regime_curve(prices, regimes, weights, initial_value=1_000_000.0, rebalance_every_days=100)

    # Once in "group_a_plus_defensive" (100% cash), the curve must go flat
    # regardless of 00631L's price path -- confirms the regime-change trigger
    # still fires even with a periodic option configured.
    tail = curve.iloc[31:]
    assert tail.max() - tail.min() < 1e-6
