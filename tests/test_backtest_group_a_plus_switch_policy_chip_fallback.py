"""2026-07-04 fix: a2118's SwitchRule requires total_risk_score >= 6 to enter
`group_a_plus_defensive`. If the underlying chip/derivative source tables go
missing (e.g. a real data-pipeline outage, or the 2008 TWII proxy window
which predates real chip-data collection), chip_score/derivative_score
silently default to 0 -- indistinguishable from a genuinely calm market --
and the defensive entry condition becomes permanently unsatisfiable
regardless of price action. `chip_data_fallback_max_stale_days` is an
opt-in (default None = no behavior change) escape hatch: when the source
tables have had no real data for that many trading days, the chip/
derivative/total-risk gates are bypassed so entry falls back to price
action alone. See GROUP_A_PLUS_FABLE_AUDIT_MARKET_STATE_ARBITRATION_HANDOFF_20260704.md.
"""

from __future__ import annotations

import pandas as pd

from backtest_group_a_plus_switch_policy import SwitchRule, _chip_data_is_stale, _switch_returns

TEST_RULE = SwitchRule(
    name="test_rule",
    ma_window=5,
    enter_ma_gap=-0.02,
    exit_ma_gap=0.02,
    drawdown_window=5,
    enter_drawdown=-0.99,  # effectively disabled; entry driven by ma_gap only
    exit_momentum_days=5,
    min_hold_days=1,
    require_chip_score=0,
    require_derivative_score=0,
    require_total_risk_score=6,
    exit_max_total_risk_score=None,
)

_ZERO_RAW_CHIP_COLUMNS = [
    "inst_0050_5d",
    "foreign_0050_5d",
    "margin_0050_balance_chg_5d",
    "market_margin_balance_chg_5d",
    "tdcc_0050_minority_chg_1w",
    "tdcc_0050_major_chg_1w",
    "foreign_shareholding_0050_ratio_chg_5d",
    "short_0050_margin_balance_chg_5d",
    "short_0050_sbl_balance_chg_5d",
    "securities_lending_0050_volume_5d",
    "day_trade_0050_volume_5d",
    "dealer_tx_volume_5d",
    "dealer_txo_volume_5d",
    "tx_foreign_net_oi",
    "tx_foreign_net_oi_chg_5d",
    "txo_foreign_call_net_oi",
    "txo_foreign_put_net_oi",
    "txo_foreign_put_call_net_oi",
    "txo_foreign_put_call_net_oi_chg_5d",
    "smart_money_cost_20d",
    "smart_money_cost_60d",
    "smart_money_cost_gap_20d",
    "smart_money_cost_gap_60d",
    "smart_money_pressure_20d",
]


def _make_prices(index: pd.DatetimeIndex) -> pd.DataFrame:
    # Flat at 100 for the first half, then a sustained drop to 90 -- with a
    # 5-day MA, ma_gap breaches enter_ma_gap=-0.02 partway through the drop.
    half = len(index) // 2
    closes = [100.0] * half + [90.0] * (len(index) - half)
    return pd.DataFrame({"0050.TW": closes}, index=index)


def _make_chip_features(
    index: pd.DatetimeIndex,
    *,
    risky: bool,
    days_since_update: int,
    core_days_since_update: int | None = None,
) -> pd.DataFrame:
    features = pd.DataFrame({col: 0.0 for col in _ZERO_RAW_CHIP_COLUMNS}, index=index)
    features["smart_money_cost_risk"] = 0
    if risky:
        # 6 non-rolling-window risk flags -> chip_score=4, derivative_score=2,
        # total_risk_score=6, meeting TEST_RULE.require_total_risk_score.
        features["inst_0050_5d"] = -1.0
        features["foreign_0050_5d"] = -1.0
        features["foreign_shareholding_0050_ratio_chg_5d"] = -1.0
        features["tdcc_0050_minority_chg_1w"] = 1.0
        features["tdcc_0050_major_chg_1w"] = -1.0
        features["tx_foreign_net_oi"] = -1.0
        features["tx_foreign_net_oi_chg_5d"] = -1.0
        features["txo_foreign_put_call_net_oi"] = 1.0
        features["txo_foreign_put_call_net_oi_chg_5d"] = 1.0
    features["chip_data_days_since_source_update"] = days_since_update
    if core_days_since_update is not None:
        features["chip_data_core_days_since_source_update"] = core_days_since_update
    return features


def _defensive_switch_count(events: list[dict]) -> int:
    return sum(1 for e in events if e["action"] == "switch_to_group_a_plus_defensive")


def test_chip_data_is_stale_helper() -> None:
    assert _chip_data_is_stale(10, 10) is True
    assert _chip_data_is_stale(15, 10) is True
    assert _chip_data_is_stale(9, 10) is False
    assert _chip_data_is_stale(0, 10) is False


def test_fallback_disabled_never_enters_when_total_risk_score_stuck_at_zero() -> None:
    """Baseline: price drops sharply, but chip/derivative data is missing
    (total_risk_score forced to 0 the whole window) and the fallback is off
    (default None). Entry never fires -- this reproduces the bug."""
    index = pd.bdate_range("2026-01-01", periods=30)
    prices = _make_prices(index)
    chip_features = _make_chip_features(index, risky=False, days_since_update=999_999)

    events, _frame = _switch_returns(prices, chip_features, TEST_RULE)

    assert _defensive_switch_count(events) == 0


def test_fallback_enabled_recovers_entry_when_data_is_genuinely_stale() -> None:
    """Same price drop, same missing chip data (stale the whole window), but
    chip_data_fallback_max_stale_days=10 is now set. The gates should be
    bypassed and the price-driven entry should fire."""
    index = pd.bdate_range("2026-01-01", periods=30)
    prices = _make_prices(index)
    chip_features = _make_chip_features(index, risky=False, days_since_update=999_999)

    events, _frame = _switch_returns(prices, chip_features, TEST_RULE, chip_data_fallback_max_stale_days=10)

    assert _defensive_switch_count(events) >= 1


def test_fallback_does_not_override_genuine_total_risk_score_when_data_is_fresh() -> None:
    """Data is fresh (days_since_update=0, well under the 10-day threshold)
    and genuinely shows no risk (total_risk_score=0). The fallback must NOT
    fire in this case -- a calm, well-fed market should behave identically
    whether or not the fallback param is set."""
    index = pd.bdate_range("2026-01-01", periods=30)
    prices = _make_prices(index)
    chip_features = _make_chip_features(index, risky=False, days_since_update=0)

    events_without, _ = _switch_returns(prices, chip_features, TEST_RULE)
    events_with, _ = _switch_returns(prices, chip_features, TEST_RULE, chip_data_fallback_max_stale_days=10)

    assert _defensive_switch_count(events_without) == 0
    assert _defensive_switch_count(events_with) == 0
    assert events_without == events_with


def test_fallback_param_is_a_no_op_when_data_is_fresh_and_genuinely_risky() -> None:
    """Data is fresh and genuinely risky (total_risk_score=6, satisfying the
    rule on its own merits). Turning the fallback on must not change the
    result -- proves the opt-in param has zero effect on well-fed data,
    matching every existing a2111/a2118 call site's expectations."""
    index = pd.bdate_range("2026-01-01", periods=30)
    prices = _make_prices(index)
    chip_features = _make_chip_features(index, risky=True, days_since_update=0)

    events_without, frame_without = _switch_returns(prices, chip_features, TEST_RULE)
    events_with, frame_with = _switch_returns(prices, chip_features, TEST_RULE, chip_data_fallback_max_stale_days=10)

    assert events_without == events_with
    pd.testing.assert_frame_equal(frame_without, frame_with)
    assert _defensive_switch_count(events_without) >= 1


def test_fallback_uses_core_coverage_not_any_source_coverage() -> None:
    """A broad market source may be fresh while ETF/institutional/derivative
    core sources are stale. The fallback must key off core coverage; otherwise
    one always-present low-specificity table masks the outage."""
    index = pd.bdate_range("2026-01-01", periods=30)
    prices = _make_prices(index)
    chip_features = _make_chip_features(
        index,
        risky=False,
        days_since_update=0,
        core_days_since_update=999_999,
    )

    events, _ = _switch_returns(prices, chip_features, TEST_RULE, chip_data_fallback_max_stale_days=10)

    assert _defensive_switch_count(events) >= 1


def test_fallback_does_not_fire_when_core_coverage_is_fresh_even_if_any_clock_is_stale() -> None:
    index = pd.bdate_range("2026-01-01", periods=30)
    prices = _make_prices(index)
    chip_features = _make_chip_features(
        index,
        risky=False,
        days_since_update=999_999,
        core_days_since_update=0,
    )

    events, _ = _switch_returns(prices, chip_features, TEST_RULE, chip_data_fallback_max_stale_days=10)

    assert _defensive_switch_count(events) == 0
