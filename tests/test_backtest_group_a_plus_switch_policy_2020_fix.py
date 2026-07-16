"""2026-07-06 fix: the A21.11/A21.18 switch rule was blind to the 2020
V-shaped COVID crash. Two independent, opt-in fixes to `_switch_returns`
(default `None` = zero behavior change for every existing caller unless
explicitly passed -- see GROUP_A_PLUS_2020_COVID_SWITCH_RULE_FIX_HANDOFF_
20260706.md for the full derivation):

1. `risk_score_lookback_days` (entry-side): `total_risk_score` and
   `drawdown`/`ma_gap` crossed their thresholds on different days during the
   2020 crash (total_risk_score peaked 2020-03-06, drawdown didn't clear
   -11% until 2020-03-09, and the two were never simultaneously true for the
   rest of the crash). A rolling max over the lookback window fixes this.
2. `momentum_fast_exit_min` + `momentum_fast_exit_ma_gap_min` (exit-side):
   `exit_momentum` recovered three weeks before `ma_gap` during the 2020
   rebound. A guarded fast-exit path releases exposure early -- but pure
   momentum magnitude cannot distinguish a genuine V-shaped recovery
   (2020-03-26: +12.6% 5-day return, ma_gap=-4.4%) from a dead-cat bounce
   deep in a bear market (2008-11-03: +14.4% 5-day return -- bigger than
   2020's -- but ma_gap=-23.7%, drawdown=-39.2%). The `ma_gap` co-condition
   is what tells them apart; these tests pin both directions.

These tests use small synthetic price paths (no historical DB access),
following the same pattern as
tests/test_backtest_group_a_plus_switch_policy_chip_fallback.py.
"""

from __future__ import annotations

import pandas as pd

from backtest_group_a_plus_switch_policy import SwitchRule, _switch_returns

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

# The exact 9-flag combination used by the 2026-07-04 chip-fallback test:
# chip_score=4 (inst/foreign/foreign_shareholding/tdcc), derivative_score=2,
# total_risk_score=6.
_RISKY_FLAGS = {
    "inst_0050_5d": -1.0,
    "foreign_0050_5d": -1.0,
    "foreign_shareholding_0050_ratio_chg_5d": -1.0,
    "tdcc_0050_minority_chg_1w": 1.0,
    "tdcc_0050_major_chg_1w": -1.0,
    "tx_foreign_net_oi": -1.0,
    "tx_foreign_net_oi_chg_5d": -1.0,
    "txo_foreign_put_call_net_oi": 1.0,
    "txo_foreign_put_call_net_oi_chg_5d": 1.0,
}


def _defensive_switch_count(events: list[dict]) -> int:
    return sum(1 for e in events if e["action"] == "switch_to_group_a_plus_defensive")


def _golden_switch_events(events: list[dict]) -> list[str]:
    return [e["date"] for e in events if e["action"] == "switch_to_golden"]


# ---------------------------------------------------------------------------
# Fix 1: risk_score_lookback_days (entry-side same-day misalignment)
# ---------------------------------------------------------------------------

_ENTRY_TEST_RULE = SwitchRule(
    name="test_2020_entry",
    ma_window=20,
    enter_ma_gap=-0.99,  # disabled -- entry driven by drawdown only
    exit_ma_gap=0.5,     # irrelevant, no exit reached in this test
    drawdown_window=20,
    enter_drawdown=-0.06,
    exit_momentum_days=5,
    min_hold_days=1,
    require_chip_score=0,
    require_derivative_score=0,
    require_total_risk_score=6,
    require_tail_risk_score=0,
)


def _make_delayed_confirmation_fixtures() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reproduces the 2020-03-06 vs. 2020-03-09 misalignment: total_risk_score
    spikes to 6 on day 10 (drawdown only -3%, not yet breaching -6%); by day
    14, drawdown has breached -6%, but total_risk_score is back to 0."""
    index = pd.bdate_range("2026-01-01", periods=15)
    closes = [100.0] * 10 + [97.0, 96.5, 96.0, 95.5, 93.0]
    prices = pd.DataFrame({"0050.TW": closes}, index=index)

    chip = pd.DataFrame(0.0, index=index, columns=_ZERO_RAW_CHIP_COLUMNS)
    chip["smart_money_cost_risk"] = 0
    spike_day = index[10]
    for col, val in _RISKY_FLAGS.items():
        chip.loc[spike_day, col] = val
    return prices, chip


def test_entry_never_fires_when_risk_score_and_drawdown_never_align() -> None:
    """Baseline (risk_score_lookback_days=None, i.e. today-only, matches every
    caller before this fix and every caller that doesn't opt in): the risk
    confirmation and the price confirmation never land on the same day, so
    entry never fires -- this reproduces the 2020 bug."""
    prices, chip = _make_delayed_confirmation_fixtures()
    events, frame = _switch_returns(prices, chip, _ENTRY_TEST_RULE)

    assert frame["total_risk_score"].tolist().count(6) == 1  # spikes exactly once
    assert _defensive_switch_count(events) == 0


def test_risk_score_lookback_catches_delayed_price_confirmation() -> None:
    """Same fixtures, risk_score_lookback_days=5 (the value a2118 now ships
    with): the rolling max carries day 10's total_risk_score=6 forward far
    enough to overlap day 14's drawdown breach, so entry fires."""
    prices, chip = _make_delayed_confirmation_fixtures()
    events, _frame = _switch_returns(prices, chip, _ENTRY_TEST_RULE, risk_score_lookback_days=5)

    assert _defensive_switch_count(events) == 1
    assert events[0]["date"] == str(prices.index[-1].date())


# ---------------------------------------------------------------------------
# Fix 2: momentum_fast_exit_min + momentum_fast_exit_ma_gap_min (exit-side)
# ---------------------------------------------------------------------------

_EXIT_TEST_RULE = SwitchRule(
    name="test_2020_exit",
    ma_window=60,
    enter_ma_gap=-0.05,
    exit_ma_gap=0.01,
    drawdown_window=80,
    enter_drawdown=-0.99,  # disabled -- entry driven by ma_gap only
    exit_momentum_days=5,
    min_hold_days=1,
    require_chip_score=0,
    require_derivative_score=0,
    require_total_risk_score=0,
    require_tail_risk_score=0,
)


def test_momentum_fast_exit_recovers_earlier_than_ma_gap_on_genuine_rebound() -> None:
    """Shallow-pullback, genuine-recovery shape (mirrors 2020-03-26: shallow
    ma_gap, strong momentum). A sustained low anchors ma_gap deeply negative;
    a gradual rebound lets exit_momentum (5-day, reacts fast) cross +10%
    before ma_gap (60-day average, reacts slowly) clears the normal
    exit_ma_gap=0.01 threshold. The guarded fast-exit path should release
    one trading day earlier than the baseline ma_gap-only exit."""
    index = pd.bdate_range("2026-01-01", periods=90)
    flat = [100.0] * 40
    decline = [96, 92, 88, 85, 83, 82, 81, 80, 80, 80]
    hold = [80] * 25
    rebound = [82, 84, 86, 88, 90, 92, 93, 94, 95, 96, 97, 97, 97, 97, 97]
    prices = pd.DataFrame({"0050.TW": flat + decline + hold + rebound}, index=index)

    baseline_events, _ = _switch_returns(prices, None, _EXIT_TEST_RULE)
    fast_exit_events, _ = _switch_returns(
        prices, None, _EXIT_TEST_RULE, momentum_fast_exit_min=0.10, momentum_fast_exit_ma_gap_min=-0.08
    )

    baseline_exits = _golden_switch_events(baseline_events)
    fast_exits = _golden_switch_events(fast_exit_events)
    assert len(baseline_exits) == 1
    assert len(fast_exits) == 1
    assert pd.Timestamp(fast_exits[0]) < pd.Timestamp(baseline_exits[0])


def test_momentum_fast_exit_ma_gap_guard_blocks_dead_cat_bounce() -> None:
    """Deep-bear dead-cat-bounce shape (mirrors 2008-11-03: a bigger momentum
    burst than the genuine-recovery test above, but still deep in the
    decline). Without the ma_gap guard, the fast-exit path whipsaws in and
    out of defensive on the bounce and the market keeps falling afterward.
    With the guard, it correctly stays defensive through the entire
    continued decline -- this is the actual regression this fix must not
    reintroduce."""
    index = pd.bdate_range("2026-01-01", periods=70)
    flat = [100.0] * 30
    decline = [96, 92, 88, 85, 83, 82, 81, 80, 79, 78, 77, 76, 75, 74, 73, 72, 71, 70, 69, 68]
    bounce = [72, 75, 78, 80, 82]
    continued_decline = [78, 74, 70, 66, 62, 58, 55, 52, 50, 48, 46, 44, 42, 40, 38]
    prices = pd.DataFrame(
        {"0050.TW": flat + decline + bounce + continued_decline}, index=index
    )

    unguarded_events, _ = _switch_returns(prices, None, _EXIT_TEST_RULE, momentum_fast_exit_min=0.10)
    guarded_events, guarded_frame = _switch_returns(
        prices, None, _EXIT_TEST_RULE, momentum_fast_exit_min=0.10, momentum_fast_exit_ma_gap_min=-0.08
    )

    # Without the guard: the bounce's momentum burst triggers a costly
    # whipsaw (exit, re-enter, exit, re-enter) while the market is still
    # falling -- the exact failure mode 2008-11-03 would have caused.
    assert len(_golden_switch_events(unguarded_events)) >= 2

    # With the guard: only the single initial entry event; stays defensive
    # through the entire continued decline.
    assert _defensive_switch_count(guarded_events) == 1
    assert len(_golden_switch_events(guarded_events)) == 0
    assert guarded_frame["regime"].iloc[-1] == "group_a_plus_defensive"


def test_momentum_fast_exit_is_a_no_op_when_disabled() -> None:
    """momentum_fast_exit_min=None (the default, matching every existing
    caller): behavior must be bit-identical to omitting the parameter
    entirely, on both the genuine-recovery and the dead-cat-bounce fixtures."""
    index = pd.bdate_range("2026-01-01", periods=70)
    flat = [100.0] * 30
    decline = [96, 92, 88, 85, 83, 82, 81, 80, 79, 78, 77, 76, 75, 74, 73, 72, 71, 70, 69, 68]
    bounce = [72, 75, 78, 80, 82]
    continued_decline = [78, 74, 70, 66, 62, 58, 55, 52, 50, 48, 46, 44, 42, 40, 38]
    prices = pd.DataFrame(
        {"0050.TW": flat + decline + bounce + continued_decline}, index=index
    )

    events_implicit, frame_implicit = _switch_returns(prices, None, _EXIT_TEST_RULE)
    events_explicit, frame_explicit = _switch_returns(
        prices, None, _EXIT_TEST_RULE, momentum_fast_exit_min=None, momentum_fast_exit_ma_gap_min=None
    )

    assert events_implicit == events_explicit
    pd.testing.assert_frame_equal(frame_implicit, frame_explicit)
