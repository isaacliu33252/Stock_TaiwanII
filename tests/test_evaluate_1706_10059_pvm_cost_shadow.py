"""Unit tests for evaluate_1706_10059_pvm_cost_shadow.py's pure logic functions.

Most functions here don't require a live DB / a2118 backtest (turnover math,
the two PVM gating policies, and the summary/decision rule).
build_workbook_aware_snapshot()'s missing-field early-return is also pure,
but its real-data path needs the actual DB (real trading-day closes) --
that one small DB-backed test is kept fast by using a tiny lookback window.
evaluate_window()/build_report() are integration-level and already exercised
by real end-to-end runs recorded in
docs/1706_10059_DEEP_PORTFOLIO_MANAGEMENT_GROUPA_PLUS_REVIEW_20260808.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_1706_10059_pvm_cost_shadow import (
    _pvm_cost_recovery_targets,
    _pvm_delay_targets,
    _summarize,
    _weight_turnover,
    build_workbook_aware_snapshot,
)


def _weights(**kw) -> dict[str, float]:
    row = {ticker: 0.0 for ticker in TICKERS}
    row["cash"] = 0.0
    row.update(kw)
    return row


def _weights_frame(rows: list[dict[str, float]], dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=pd.to_datetime(dates))


class TestWeightTurnover:
    def test_identical_weights_zero_turnover(self):
        a = _weights(**{"0050.TW": 0.5, "cash": 0.5})
        assert _weight_turnover(a, a) == pytest.approx(0.0)

    def test_full_flip_sums_absolute_deltas(self):
        a = _weights(**{"00631L.TW": 0.3, "cash": 0.7})
        b = _weights(**{"00632R.TW": 0.3, "cash": 0.7})
        # 0.3 out of 00631L + 0.3 into 00632R = 0.6 total turnover
        assert _weight_turnover(a, b) == pytest.approx(0.6)


class TestPvmDelayTargets:
    def test_small_change_passes_through_immediately(self):
        dates = ["2026-01-01", "2026-01-02", "2026-01-03"]
        rows = [
            _weights(**{"0050.TW": 0.5, "cash": 0.5}),
            _weights(**{"0050.TW": 0.52, "cash": 0.48}),
            _weights(**{"0050.TW": 0.55, "cash": 0.45}),
        ]
        frame = _weights_frame(rows, dates)
        adjusted, meta = _pvm_delay_targets(
            frame, turnover_threshold=0.25, flip_threshold=0.05, max_delay_days=2
        )
        pd.testing.assert_frame_equal(adjusted, frame)
        assert meta["event_count"] == 0

    def test_large_631l_to_632r_flip_delays_then_applies(self):
        dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
        rows = [
            _weights(**{"00631L.TW": 0.3, "cash": 0.7}),
            _weights(**{"00632R.TW": 0.3, "cash": 0.7}),  # large flip, should be delayed
            _weights(**{"00632R.TW": 0.3, "cash": 0.7}),  # unchanged proposal during delay
            _weights(**{"00632R.TW": 0.3, "cash": 0.7}),
        ]
        frame = _weights_frame(rows, dates)
        adjusted, meta = _pvm_delay_targets(
            frame, turnover_threshold=0.25, flip_threshold=0.05, max_delay_days=1
        )
        # day 1 (flip proposed): still holding day-0 weights
        assert adjusted.iloc[1]["00631L.TW"] == pytest.approx(0.3)
        assert adjusted.iloc[1]["00632R.TW"] == pytest.approx(0.0)
        # day 2: delay_remaining counts down to 0 on this row (still emits
        # the held prior weights this same row), so the pending flip only
        # becomes visible in the output starting day 3.
        assert adjusted.iloc[2]["00631L.TW"] == pytest.approx(0.3)
        assert adjusted.iloc[3]["00632R.TW"] == pytest.approx(0.3)
        assert meta["event_count"] == 1
        assert meta["max_delay_days"] == 1

    def test_zero_max_delay_days_never_delays(self):
        dates = ["2026-01-01", "2026-01-02"]
        rows = [
            _weights(**{"00631L.TW": 0.3, "cash": 0.7}),
            _weights(**{"00632R.TW": 0.3, "cash": 0.7}),
        ]
        frame = _weights_frame(rows, dates)
        adjusted, meta = _pvm_delay_targets(
            frame, turnover_threshold=0.25, flip_threshold=0.05, max_delay_days=0
        )
        pd.testing.assert_frame_equal(adjusted, frame)
        assert meta["event_count"] == 0


class TestPvmCostRecoveryTargets:
    COST_KW = dict(commission_rate=0.001425, slippage_rate=0.0005, equity_etf_sell_tax=0.001)

    def _prices(self, dates: list[str], **series: list[float]) -> pd.DataFrame:
        data = {ticker: [100.0] * len(dates) for ticker in TICKERS}
        data.update(series)
        return pd.DataFrame(data, index=pd.to_datetime(dates))

    def test_non_flip_change_passes_immediately_regardless_of_cost(self):
        dates = ["2026-01-01", "2026-01-02"]
        rows = [
            _weights(**{"0050.TW": 0.5, "cash": 0.5}),
            _weights(**{"0050.TW": 0.52, "cash": 0.48}),
        ]
        frame = _weights_frame(rows, dates)
        prices = self._prices(dates)
        adjusted, meta = _pvm_cost_recovery_targets(
            prices,
            frame,
            turnover_threshold=0.25,
            flip_threshold=0.05,
            lookback_days=5,
            cost_multiplier=3.0,
            max_block_days=20,
            **self.COST_KW,
        )
        pd.testing.assert_frame_equal(adjusted, frame)
        assert meta["event_count"] == 0

    def test_flip_blocked_when_prior_advantage_below_cost_threshold(self):
        # 00631L and 00632R move identically -> no realized advantage from
        # switching, so the estimated cost is never "recovered" and the
        # flip should stay blocked. The same flip is re-proposed and
        # re-blocked on both day 1 and day 2 (one event per day it's still
        # proposed and not yet allowed).
        dates = ["2026-01-01", "2026-01-02", "2026-01-03"]
        rows = [
            _weights(**{"00631L.TW": 0.3, "cash": 0.7}),
            _weights(**{"00632R.TW": 0.3, "cash": 0.7}),
            _weights(**{"00632R.TW": 0.3, "cash": 0.7}),
        ]
        frame = _weights_frame(rows, dates)
        prices = self._prices(
            dates,
            **{"00631L.TW": [100.0, 100.0, 100.0], "00632R.TW": [100.0, 100.0, 100.0]},
        )
        adjusted, meta = _pvm_cost_recovery_targets(
            prices,
            frame,
            turnover_threshold=0.25,
            flip_threshold=0.05,
            lookback_days=1,
            cost_multiplier=3.0,
            max_block_days=20,
            **self.COST_KW,
        )
        assert adjusted.iloc[1]["00631L.TW"] == pytest.approx(0.3)
        assert adjusted.iloc[1]["00632R.TW"] == pytest.approx(0.0)
        assert adjusted.iloc[2]["00631L.TW"] == pytest.approx(0.3)
        assert meta["event_count"] == 2
        assert meta["allow_count"] == 0

    def test_flip_allowed_when_prior_advantage_covers_cost(self):
        # 00632R has strongly outperformed 00631L over the lookback window,
        # so the proposed flip's trailing advantage should clear the
        # cost_multiplier * estimated_cost bar and be allowed through.
        dates = ["2026-01-01", "2026-01-02", "2026-01-03"]
        rows = [
            _weights(**{"00631L.TW": 0.3, "cash": 0.7}),
            _weights(**{"00632R.TW": 0.3, "cash": 0.7}),
            _weights(**{"00632R.TW": 0.3, "cash": 0.7}),
        ]
        frame = _weights_frame(rows, dates)
        prices = self._prices(
            dates,
            **{"00631L.TW": [100.0, 80.0, 80.0], "00632R.TW": [100.0, 130.0, 130.0]},
        )
        adjusted, meta = _pvm_cost_recovery_targets(
            prices,
            frame,
            turnover_threshold=0.25,
            flip_threshold=0.05,
            lookback_days=1,
            cost_multiplier=3.0,
            max_block_days=20,
            **self.COST_KW,
        )
        assert adjusted.iloc[1]["00632R.TW"] == pytest.approx(0.3)
        assert meta["event_count"] == 0
        assert meta["allow_count"] == 1

    def test_max_block_days_eventually_forces_the_flip_through(self):
        dates = [f"2026-01-{d:02d}" for d in range(1, 6)]
        rows = [_weights(**{"00631L.TW": 0.3, "cash": 0.7})]
        rows += [_weights(**{"00632R.TW": 0.3, "cash": 0.7})] * 4
        frame = _weights_frame(rows, dates)
        prices = self._prices(
            dates,
            **{"00631L.TW": [100.0] * 5, "00632R.TW": [100.0] * 5},
        )
        adjusted, meta = _pvm_cost_recovery_targets(
            prices,
            frame,
            turnover_threshold=0.25,
            flip_threshold=0.05,
            lookback_days=1,
            cost_multiplier=3.0,
            max_block_days=2,
            **self.COST_KW,
        )
        # blocked on day1 and day2 (consecutive_blocks 1, 2), then forced
        # through on day3 once consecutive_blocks == max_block_days
        assert adjusted.iloc[1]["00631L.TW"] == pytest.approx(0.3)
        assert adjusted.iloc[2]["00631L.TW"] == pytest.approx(0.3)
        assert adjusted.iloc[3]["00632R.TW"] == pytest.approx(0.3)
        assert meta["event_count"] == 2


class TestSummarize:
    def _window(
        self,
        *,
        final_value_delta=1.0,
        sharpe_delta=0.1,
        drawdown_delta=0.0,
        cost_delta=-10.0,
        turnover_delta=-100.0,
        event_count=1,
    ) -> dict:
        return {
            "delta_vs_baseline": {
                "final_value": final_value_delta,
                "sharpe_ratio": sharpe_delta,
                "max_drawdown": drawdown_delta,
                "transaction_cost": cost_delta,
                "turnover_value": turnover_delta,
            },
            "pvm_policy": {"event_count": event_count},
        }

    def test_no_windows_blocked(self):
        assert _summarize([])["decision"] == "blocked_no_windows"

    def test_all_pass_and_net_cost_pass_promotes_to_shadow_queue(self):
        windows = [self._window(), self._window()]
        summary = _summarize(windows)
        assert summary["all_windows_triple_pass"] is True
        assert summary["net_cost_pass"] is True
        assert summary["decision"] == "candidate_for_latest_strategy_shadow_queue"

    def test_metric_pass_but_cost_increase_needs_refinement(self):
        windows = [self._window(cost_delta=50.0, turnover_delta=100.0)]
        summary = _summarize(windows)
        assert summary["all_windows_triple_pass"] is True
        assert summary["net_cost_pass"] is False
        assert summary["decision"] == "research_only_rule_refinement_needed_cost_or_turnover_increased"

    def test_metric_regression_not_promoted(self):
        windows = [self._window(sharpe_delta=-0.1)]
        summary = _summarize(windows)
        assert summary["all_windows_triple_pass"] is False
        assert summary["decision"] == "research_only_not_promoted"

    def test_zero_events_not_promoted_even_if_metrics_pass(self):
        windows = [self._window(event_count=0)]
        summary = _summarize(windows)
        assert summary["decision"] == "research_only_not_promoted"

    def test_golden1_flag_always_true(self):
        assert _summarize([self._window()])["golden1_0531_unchanged"] is True


class TestBuildWorkbookAwareSnapshot:
    def test_missing_fields_returns_unavailable_without_touching_db(self):
        result = build_workbook_aware_snapshot(
            {},
            db_path=DB_PATH,
            lookback_days=5,
            cost_multiplier=3.0,
            turnover_threshold=0.25,
            flip_threshold=0.05,
            commission_rate=0.001425,
            slippage_rate=0.0005,
            equity_etf_sell_tax=0.001,
        )
        assert result == {"status": "unavailable", "reason": "execution_plan_missing_required_fields"}

    def test_no_631l_position_never_trips_the_flip_gate(self):
        # Current holdings have no 00631L or 00632R at all; target proposes
        # a 00632R entry funded from cash. This is a real, large rebalance
        # (high turnover) but it is not a 00631L<->00632R flip, so the gate
        # -- scoped specifically to that pattern -- should stay inactive.
        execution_plan = {
            "actual_data_date": "2026-08-07",
            "current_holdings": {"0050.TW": 3994, "00679B.TWO": 3000},
            "current_prices": {
                "0050.TW": 102.85,
                "00631L.TW": 33.68,
                "00632R.TW": 10.35,
                "00679B.TWO": 26.41,
            },
            "current_total_assets": 1_000_000.0,
            "target_weights": {
                "0050.TW": 0.3,
                "00631L.TW": 0.0,
                "00632R.TW": 0.27,
                "00679B.TWO": 0.0,
                "cash": 0.43,
            },
        }
        result = build_workbook_aware_snapshot(
            execution_plan,
            db_path=DB_PATH,
            lookback_days=5,
            cost_multiplier=3.0,
            turnover_threshold=0.25,
            flip_threshold=0.05,
            commission_rate=0.001425,
            slippage_rate=0.0005,
            equity_etf_sell_tax=0.001,
        )
        assert result["status"] == "ok"
        assert result["turnover_current_to_full_target"] > 0.25
        assert result["large_flip_detected"] is False
        assert result["cost_recovery_would_block"] is False

    def test_real_631l_to_632r_flip_engages_the_gate(self):
        # Current holdings hold 00631L only; target flips fully into
        # 00632R. This IS the pattern the gate is scoped to -- it must
        # either block or explicitly allow, not stay inactive.
        execution_plan = {
            "actual_data_date": "2026-08-07",
            "current_holdings": {"00631L.TW": 8000},  # ~0.3 weight at ~33.68
            "current_prices": {
                "0050.TW": 102.85,
                "00631L.TW": 33.68,
                "00632R.TW": 10.35,
                "00679B.TWO": 26.41,
            },
            "current_total_assets": 1_000_000.0,
            "target_weights": {
                "0050.TW": 0.0,
                "00631L.TW": 0.0,
                "00632R.TW": 0.3,
                "00679B.TWO": 0.0,
                "cash": 0.7,
            },
        }
        result = build_workbook_aware_snapshot(
            execution_plan,
            db_path=DB_PATH,
            lookback_days=5,
            cost_multiplier=3.0,
            turnover_threshold=0.25,
            flip_threshold=0.05,
            commission_rate=0.001425,
            slippage_rate=0.0005,
            equity_etf_sell_tax=0.001,
        )
        assert result["status"] == "ok"
        assert result["large_flip_detected"] is True
        assert result["cost_recovery_would_block"] != result["cost_recovery_would_allow"]
