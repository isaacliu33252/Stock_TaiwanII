#!/usr/bin/env python3
"""Regression checks for Group A++ workbook execution planning."""

from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from group_a_plus.operations import execution_plan
from group_a_plus.operations.execution_plan import (
    _apply_execution_controls,
    _apply_buy_staging,
    _build_guard_impact_summary,
    _combine_guarded_targets,
    _execution_plan_pit_asof,
    _execution_plan_pit_generated_at,
    _latest_prices,
    _write_execution_plan_pit_snapshot,
    _trough_high_vol_override_watch,
    _trough_nowcast_buy_fraction,
    build_execution_plan,
    _build_trades,
    load_group_a_plus_holdings_json,
    _parse_group_a_plus_holdings,
)
from group_a_plus.operations.execution_guard import (
    apply_risk_add_pre_trade_guard,
    apply_volatility_gate_pre_trade_guard,
)


class ExecutionPlanV2Tests(unittest.TestCase):
    def test_execution_plan_pit_snapshot_uses_actual_data_date_and_generated_at(self) -> None:
        payload = {
            "success": True,
            "data": {
                "actual_data_date": "2026-07-27",
                "requested_as_of_date": "2026-07-30",
                "generated_at": "2026-07-30T21:30:00",
                "target_shares": {"00631L.TW": 100},
            },
            "metadata": {"timestamp": "2026-07-30T21:31:00"},
        }

        self.assertEqual(_execution_plan_pit_asof(payload, "2026-07-30"), "2026-07-27")
        self.assertEqual(_execution_plan_pit_generated_at(payload), "2026-07-30T21:30:00")

    def test_execution_plan_pit_snapshot_writes_append_only_artifact(self) -> None:
        payload = {
            "success": True,
            "data": {
                "actual_data_date": "2026-07-27",
                "generated_at": "2026-07-30T21:30:00",
                "target_shares": {"00631L.TW": 100},
            },
            "metadata": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(execution_plan, "write_json_artifact_snapshot") as writer:
                writer.return_value = Path(tmp) / "execution_plan.json"
                path = _write_execution_plan_pit_snapshot(payload, requested_as_of="2026-07-30")

        self.assertEqual(path.name, "execution_plan.json")
        writer.assert_called_once()
        _, args, kwargs = writer.mock_calls[0]
        self.assertEqual(args[0], "execution_plan")
        self.assertEqual(args[1], payload)
        self.assertEqual(kwargs["artifact_asof"], "2026-07-27")
        self.assertEqual(kwargs["generated_at"], "2026-07-30T21:30:00")

    def test_latest_prices_returns_empty_dict_for_empty_ticker_list(self) -> None:
        # 2026-07-24: an all-zero-holdings scenario (e.g. a fresh-cash cold
        # start) produces an empty held_tickers list, which used to build an
        # invalid `WHERE ticker IN ()` SQL clause and crash with a
        # ParserException. Guard against regressing that fix -- must not
        # touch the DB at all when there are no tickers to look up.
        self.assertEqual(_latest_prices(Path("unused.db"), [], "2026-07-24"), {})

    def test_parser_stops_before_group_b(self) -> None:
        frame = pd.DataFrame(
            [
                [None, "Group A++", None, None, "Group B", None],
                [None, "ETF 0050", "Bond 00679B", "Bond 00751B", "ETF 0056", "ETF 00878"],
                ["即時庫存", 100, 200, 300, 400, 500],
            ]
        )

        holdings = _parse_group_a_plus_holdings(frame)

        self.assertEqual(holdings, {"0050.TW": 100, "00679B.TWO": 200})

    def test_load_holdings_json_filters_to_group_a_plus_tickers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "holdings.json"
            path.write_text(
                json.dumps(
                    {
                        "holdings": {
                            "0050.TW": 2794,
                            "00631L.TW": 500,
                            "00632R.TW": 0,
                            "00679B.TWO": 3000,
                            "2330.TW": 99,
                        }
                    }
                ),
                encoding="utf-8",
            )

            holdings = load_group_a_plus_holdings_json(path)

        self.assertEqual(
            holdings,
            {
                "0050.TW": 2794,
                "00631L.TW": 500,
                "00632R.TW": 0,
                "00679B.TWO": 3000,
            },
        )

    def test_execution_plan_can_use_holdings_json_instead_of_workbook(self) -> None:
        signal = {
            "strategy_id": "a2118",
            "actual_data_date": "2026-07-17",
            "execution_regime": "golden1",
            "target_weights": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
            "reference_target_shares_before_cost": {"0050.TW": 40, "00631L.TW": 150},
            "latest_prices": {"0050.TW": 120.0, "00631L.TW": 40.0, "00679B.TWO": 30.0},
            "execution_guard_reasons": [],
            "execution_allowed": True,
            "signal_alerts": [],
            "portfolio_value_input": 31_000.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            holdings_json = Path(tmp) / "holdings.json"
            holdings_json.write_text(
                json.dumps({"holdings": {"0050.TW": 20, "00631L.TW": 100, "00679B.TWO": 5}}),
                encoding="utf-8",
            )
            with (
                patch.object(execution_plan, "load_group_a_plus_holdings") as workbook_loader,
                patch.object(execution_plan, "_latest_prices", return_value={"0050.TW": 120.0, "00631L.TW": 40.0, "00679B.TWO": 30.0}),
                patch.object(execution_plan, "build_daily_signal", return_value=signal),
            ):
                plan = build_execution_plan(
                    Path("dummy.xlsx"),
                    "2026-07-17",
                    cash_balance=24_450.0,
                    max_business_stale_days=3,
                    db_path=Path("dummy.db"),
                    manifest_path=Path("strategy.json"),
                    min_trade_notional=0.0,
                    min_weight_deviation=0.0,
                    min_staged_buy_notional=999_999.0,
                    holdings_json_path=holdings_json,
                )

        workbook_loader.assert_not_called()
        self.assertEqual(plan["current_holdings"], {"0050.TW": 20, "00631L.TW": 100, "00679B.TWO": 5})
        self.assertEqual(plan["holdings_source"], str(holdings_json))

    def test_bond_etf_sale_has_no_tax(self) -> None:
        trades, totals = _build_trades(
            {"00751B.TWO": 10},
            {"00751B.TWO": 0},
            {"00751B.TWO": 30.0},
            commission_rate=0.0,
            slippage_rate=0.0,
            equity_etf_sell_tax=0.001,
        )

        self.assertEqual(trades[0]["sell_tax"], 0.0)
        self.assertEqual(totals["sell_tax"], 0.0)

    def test_small_trade_inside_band_is_suppressed(self) -> None:
        targets, suppressed = _apply_execution_controls(
            {"0050.TW": 100},
            {"0050.TW": 102},
            {"0050.TW": 100.0},
            total_assets=100_000.0,
            min_trade_notional=500.0,
            min_weight_deviation=0.01,
            share_lot_size=1,
        )

        self.assertEqual(targets["0050.TW"], 100)
        self.assertEqual(suppressed[0]["ticker"], "0050.TW")

    def test_liquidation_bypasses_execution_bands(self) -> None:
        targets, suppressed = _apply_execution_controls(
            {"00679B.TWO": 1},
            {"00679B.TWO": 0},
            {"00679B.TWO": 27.0},
            total_assets=100_000.0,
            min_trade_notional=5000.0,
            min_weight_deviation=0.1,
            share_lot_size=1,
        )

        self.assertEqual(targets["00679B.TWO"], 0)
        self.assertEqual(suppressed, [])

    def test_large_buy_is_staged_but_sells_are_not_deferred(self) -> None:
        targets, staged = _apply_buy_staging(
            {"0050.TW": 2074, "00631L.TW": 90, "00679B.TWO": 1000},
            {"0050.TW": 2074, "00631L.TW": 861, "00679B.TWO": 0},
            {"0050.TW": 108.8, "00631L.TW": 38.88, "00679B.TWO": 26.96},
            max_initial_buy_fraction=0.4,
            min_staged_buy_notional=20_000.0,
            share_lot_size=1,
        )

        self.assertEqual(targets["00631L.TW"], 398)
        self.assertEqual(targets["00679B.TWO"], 0)
        self.assertEqual(staged[0]["ticker"], "00631L.TW")
        self.assertEqual(staged[0]["staged_delta_shares"], 308)
        self.assertEqual(staged[0]["deferred_delta_shares"], 463)

    def test_buy_staging_respects_lot_size_and_notional_floor(self) -> None:
        targets, staged = _apply_buy_staging(
            {"00631L.TW": 90, "0050.TW": 100},
            {"00631L.TW": 861, "0050.TW": 120},
            {"00631L.TW": 38.88, "0050.TW": 108.8},
            max_initial_buy_fraction=0.4,
            min_staged_buy_notional=20_000.0,
            share_lot_size=100,
        )

        self.assertEqual(targets["00631L.TW"], 390)
        self.assertEqual(targets["0050.TW"], 120)
        self.assertEqual(staged[0]["staged_delta_shares"], 300)

    def test_combined_guards_keep_most_conservative_targets(self) -> None:
        combined = _combine_guarded_targets(
            {"0050.TW": 40, "00631L.TW": 150, "00679B.TWO": 0},
            [
                {"0050.TW": 40, "00631L.TW": 100, "00679B.TWO": 0},
                {"0050.TW": 20, "00631L.TW": 150, "00679B.TWO": 0},
            ],
        )

        self.assertEqual(combined["0050.TW"], 20)
        self.assertEqual(combined["00631L.TW"], 100)
        self.assertEqual(combined["00679B.TWO"], 0)

    def test_trough_nowcast_partial_reentry_raises_buy_staging_fraction(self) -> None:
        fraction, diagnostic = _trough_nowcast_buy_fraction(
            {
                "trough_nowcast": {
                    "state": "PARTIAL_REENTRY",
                    "recommended_execution_staging_fraction": 0.7,
                    "policy": "diagnostic_reentry_timing_only_no_target_weight_change",
                }
            },
            0.4,
        )

        self.assertEqual(fraction, 0.7)
        self.assertTrue(diagnostic["applied"])
        self.assertEqual(diagnostic["state"], "PARTIAL_REENTRY")

    def test_trough_nowcast_capitulation_warning_does_not_raise_staging_fraction(self) -> None:
        fraction, diagnostic = _trough_nowcast_buy_fraction(
            {
                "trough_nowcast": {
                    "state": "CAPITULATION_WARNING",
                    "recommended_execution_staging_fraction": None,
                }
            },
            0.4,
        )

        self.assertEqual(fraction, 0.4)
        self.assertFalse(diagnostic["applied"])

    def test_trough_high_vol_override_watch_is_research_only_when_conditions_match(self) -> None:
        watch = _trough_high_vol_override_watch(
            signal={
                "trough_nowcast": {
                    "state": "PARTIAL_REENTRY",
                    "inputs": {
                        "market_proxy": {
                            "no_fresh_0050_lower_low_3d": True,
                            "latest_0050_close": 104.45,
                            "prior_0050_3d_low": 103.10,
                        }
                    },
                }
            },
            volatility_guard={
                "status": "blocked",
                "blocked_trades": [
                    {
                        "ticker": "00631L.TW",
                        "side": "buy",
                        "blocked_delta_shares": 40,
                    }
                ],
            },
            risk_guard={"status": "inactive", "blocked_trades": []},
            compounding_guard={"status": "inactive", "blocked_trades": []},
        )

        self.assertEqual(watch["status"], "watch")
        self.assertTrue(watch["research_only"])
        self.assertEqual(watch["live_execution_effect"], "none")
        self.assertEqual(watch["research_candidate_00631l_shares"], 10)

    def test_trough_high_vol_override_watch_stays_inactive_when_other_guard_blocks_00631l(self) -> None:
        watch = _trough_high_vol_override_watch(
            signal={
                "trough_nowcast": {
                    "state": "PARTIAL_REENTRY",
                    "inputs": {"market_proxy": {"no_fresh_0050_lower_low_3d": True}},
                }
            },
            volatility_guard={
                "status": "blocked",
                "blocked_trades": [{"ticker": "00631L.TW", "side": "buy", "blocked_delta_shares": 40}],
            },
            risk_guard={
                "status": "blocked",
                "blocked_trades": [{"ticker": "00631L.TW", "side": "buy", "blocked_delta_shares": 40}],
            },
            compounding_guard={"status": "inactive", "blocked_trades": []},
        )

        self.assertEqual(watch["status"], "inactive")
        self.assertEqual(watch["research_candidate_00631l_shares"], 0)
        self.assertTrue(watch["risk_guard_blocks_00631l"])

    def test_guard_impact_summary_deduplicates_combined_blocked_buys(self) -> None:
        summary = _build_guard_impact_summary(
            {"00631L.TW": 0},
            {"00631L.TW": 100},
            {"00631L.TW": 0},
            {"00631L.TW": 40.0},
            [
                {
                    "name": "volatility_gate_no_00631l_add",
                    "status": "blocked",
                    "allow_00631l_add": False,
                    "blocked_trades": [
                        {
                            "ticker": "00631L.TW",
                            "blocked_delta_shares": 100,
                        }
                    ],
                },
                {
                    "name": "compounding_regime_no_00631l_add",
                    "status": "blocked",
                    "allow_00631l_add": False,
                    "blocked_trades": [
                        {
                            "ticker": "00631L.TW",
                            "blocked_delta_shares": 100,
                        }
                    ],
                },
            ],
        )

        self.assertEqual(summary["blocked_guard_names"], ["volatility_gate_no_00631l_add", "compounding_regime_no_00631l_add"])
        self.assertEqual(len(summary["by_guard"]), 2)
        self.assertEqual(summary["combined_blocked_trade_count"], 1)
        self.assertEqual(summary["combined_blocked_buy_notional"], 4000.0)
        self.assertEqual(summary["by_guard"][0]["blocked_buy_notional"], 4000.0)
        self.assertEqual(summary["by_guard"][1]["blocked_buy_notional"], 4000.0)

    def test_volatility_guard_removes_00631l_buy_before_trade_build(self) -> None:
        guarded_targets, guard = apply_volatility_gate_pre_trade_guard(
            {"00631L.TW": 100, "0050.TW": 20},
            {"00631L.TW": 150, "0050.TW": 40},
            {
                "signal_alerts": [
                    {
                        "type": "volatility_gate_high_vol",
                        "metadata": {
                            "allow_00631l_add": False,
                            "trade_policy": "advisory_no_auto_weight_change",
                        },
                    }
                ]
            },
        )
        trades, _totals = _build_trades(
            {"00631L.TW": 100, "0050.TW": 20},
            guarded_targets,
            {"00631L.TW": 40.0, "0050.TW": 120.0},
            commission_rate=0.0,
            slippage_rate=0.0,
            equity_etf_sell_tax=0.001,
        )

        self.assertEqual(guard["status"], "blocked")
        self.assertEqual(guarded_targets["00631L.TW"], 100)
        self.assertEqual([trade["ticker"] for trade in trades], ["0050.TW"])
        self.assertEqual(trades[0]["side"], "buy")

    def test_extreme_warning_guard_removes_0050_and_00631l_buys_before_trade_build(self) -> None:
        guarded_targets, guard = apply_risk_add_pre_trade_guard(
            {"00631L.TW": 100, "0050.TW": 20, "00679B.TWO": 5},
            {"00631L.TW": 150, "0050.TW": 40, "00679B.TWO": 10},
            {
                "signal_alerts": [
                    {
                        "type": "a2118_extreme_risk_warning",
                        "metadata": {
                            "policy": "warning_only_no_weight_change",
                            "recommended_action": "pause_new_risk_adds",
                            "allow_new_0050_add": False,
                            "allow_new_00631l_add": False,
                        },
                    }
                ]
            },
        )
        trades, _totals = _build_trades(
            {"00631L.TW": 100, "0050.TW": 20, "00679B.TWO": 5},
            guarded_targets,
            {"00631L.TW": 40.0, "0050.TW": 120.0, "00679B.TWO": 30.0},
            commission_rate=0.0,
            slippage_rate=0.0,
            equity_etf_sell_tax=0.001,
        )

        self.assertEqual(guard["status"], "blocked")
        self.assertEqual(guarded_targets["00631L.TW"], 100)
        self.assertEqual(guarded_targets["0050.TW"], 20)
        self.assertEqual(guarded_targets["00679B.TWO"], 10)
        self.assertEqual([trade["ticker"] for trade in trades], ["00679B.TWO"])
        self.assertEqual(trades[0]["side"], "buy")

    def test_execution_plan_applies_extreme_warning_guard_end_to_end(self) -> None:
        signal = {
            "strategy_id": "a2118",
            "actual_data_date": "2026-02-26",
            "execution_regime": "golden1",
            "target_weights": {"0050.TW": 0.60, "00631L.TW": 0.20, "00679B.TWO": 0.05, "cash": 0.15},
            "reference_target_shares_before_cost": {"0050.TW": 40, "00631L.TW": 150, "00679B.TWO": 10},
            "latest_prices": {"0050.TW": 120.0, "00631L.TW": 40.0, "00679B.TWO": 30.0},
            "execution_guard_reasons": [],
            "execution_allowed": True,
            "signal_alerts": [
                {
                    "type": "a2118_extreme_risk_warning",
                    "metadata": {
                        "policy": "warning_only_no_weight_change",
                        "recommended_action": "pause_new_risk_adds",
                        "allow_new_0050_add": False,
                        "allow_new_00631l_add": False,
                    },
                }
            ],
        }
        with (
            patch.object(execution_plan, "load_group_a_plus_holdings", return_value={"0050.TW": 20, "00631L.TW": 100, "00679B.TWO": 5}),
            patch.object(execution_plan, "_latest_prices", return_value={"0050.TW": 120.0, "00631L.TW": 40.0, "00679B.TWO": 30.0}),
            patch.object(execution_plan, "build_daily_signal", return_value=signal),
        ):
            plan = build_execution_plan(
                Path("dummy.xlsx"),
                "2026-02-26",
                cash_balance=10_000.0,
                max_business_stale_days=3,
                db_path=Path("dummy.db"),
                manifest_path=Path("strategy.json"),
                min_trade_notional=0.0,
                min_weight_deviation=0.0,
                min_staged_buy_notional=999_999.0,
            )

        self.assertEqual(plan["target_shares"]["0050.TW"], 20)
        self.assertEqual(plan["target_shares"]["00631L.TW"], 100)
        self.assertEqual(plan["target_shares"]["00679B.TWO"], 10)
        self.assertEqual(plan["risk_add_pre_trade_guard"]["status"], "blocked")
        self.assertEqual([trade["ticker"] for trade in plan["trades"]], ["00679B.TWO"])

    def test_execution_plan_applies_compounding_regime_guard_end_to_end(self) -> None:
        signal = {
            "strategy_id": "a2118",
            "actual_data_date": "2026-07-09",
            "execution_regime": "golden1",
            "target_weights": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
            "reference_target_shares_before_cost": {"0050.TW": 40, "00631L.TW": 150},
            "latest_prices": {"0050.TW": 120.0, "00631L.TW": 40.0},
            "execution_guard_reasons": [],
            "execution_allowed": True,
            "signal_alerts": [],
            "portfolio_value_input": 16_400.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            compounding_path = Path(tmp) / "compounding.json"
            compounding_path.write_text(
                json.dumps(
                    {
                        "latest": {
                            "date": "2026-07-09",
                            "compounding_regime": "MEAN_REVERTING",
                            "recommended_policy": "prohibit_new_leverage_or_reduce_rebalance_frequency",
                        }
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(execution_plan, "load_group_a_plus_holdings", return_value={"0050.TW": 20, "00631L.TW": 100}),
                patch.object(execution_plan, "_latest_prices", return_value={"0050.TW": 120.0, "00631L.TW": 40.0}),
                patch.object(execution_plan, "build_daily_signal", return_value=signal),
            ):
                plan = build_execution_plan(
                    Path("dummy.xlsx"),
                    "2026-07-09",
                    cash_balance=10_000.0,
                    max_business_stale_days=3,
                    db_path=Path("dummy.db"),
                    manifest_path=Path("strategy.json"),
                    min_trade_notional=0.0,
                    min_weight_deviation=0.0,
                    min_staged_buy_notional=999_999.0,
                    compounding_regime_path=compounding_path,
                )

        self.assertEqual(plan["target_shares"]["00631L.TW"], 100)
        self.assertEqual(plan["target_shares"]["0050.TW"], 40)
        self.assertEqual(plan["compounding_regime_pre_trade_guard"]["status"], "blocked")
        self.assertEqual([trade["ticker"] for trade in plan["trades"]], ["0050.TW"])

    def test_execution_plan_advisory_guards_do_not_block_when_not_enforced(self) -> None:
        signal = {
            "strategy_id": "a2118",
            "actual_data_date": "2026-07-09",
            "execution_regime": "golden1",
            "target_weights": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
            "reference_target_shares_before_cost": {"0050.TW": 40, "00631L.TW": 150},
            "latest_prices": {"0050.TW": 120.0, "00631L.TW": 40.0},
            "execution_guard_reasons": [],
            "execution_allowed": True,
            "signal_alerts": [
                {
                    "type": "volatility_gate_high_vol",
                    "metadata": {
                        "allow_00631l_add": False,
                        "trade_policy": "advisory_no_auto_weight_change",
                    },
                }
            ],
            "portfolio_value_input": 16_400.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            compounding_path = Path(tmp) / "compounding.json"
            compounding_path.write_text(
                json.dumps(
                    {
                        "latest": {
                            "date": "2026-07-09",
                            "compounding_regime": "MEAN_REVERTING",
                            "recommended_policy": "prohibit_new_leverage_or_reduce_rebalance_frequency",
                        }
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(execution_plan, "load_group_a_plus_holdings", return_value={"0050.TW": 20, "00631L.TW": 100}),
                patch.object(execution_plan, "_latest_prices", return_value={"0050.TW": 120.0, "00631L.TW": 40.0}),
                patch.object(execution_plan, "build_daily_signal", return_value=signal),
            ):
                plan = build_execution_plan(
                    Path("dummy.xlsx"),
                    "2026-07-09",
                    cash_balance=10_000.0,
                    max_business_stale_days=3,
                    db_path=Path("dummy.db"),
                    manifest_path=Path("strategy.json"),
                    min_trade_notional=0.0,
                    min_weight_deviation=0.0,
                    min_staged_buy_notional=999_999.0,
                    compounding_regime_path=compounding_path,
                    enforce_advisory_pre_trade_guards=False,
                )

        # Both guards would have blocked the 00631L add, but since all orders are
        # placed manually there is no automated execution to guard -- the full
        # recommended target is kept for human review instead of being zeroed.
        self.assertFalse(plan["advisory_pre_trade_guards_enforced"])
        self.assertEqual(plan["target_shares"]["00631L.TW"], 150)
        self.assertEqual(plan["pre_trade_guard"]["status"], "flagged_advisory_only")
        self.assertFalse(plan["pre_trade_guard"]["enforced"])
        self.assertEqual(plan["pre_trade_guard"]["blocked_trades"], [])
        self.assertEqual(plan["pre_trade_guard"]["advisory_trades"][0]["blocked_delta_shares"], 50)
        self.assertEqual(plan["compounding_regime_pre_trade_guard"]["status"], "flagged_advisory_only")
        self.assertFalse(plan["compounding_regime_pre_trade_guard"]["enforced"])
        self.assertEqual(plan["compounding_regime_pre_trade_guard"]["blocked_trades"], [])
        self.assertEqual(
            {trade["ticker"] for trade in plan["trades"]},
            {"0050.TW", "00631L.TW"},
        )
        self.assertEqual(plan["guard_impact_summary"]["blocked_guard_names"], [])

    def test_execution_plan_reports_cross_market_graph_advisory_without_guarding_trades(self) -> None:
        signal = {
            "strategy_id": "a2118",
            "actual_data_date": "2026-07-15",
            "execution_regime": "golden1",
            "target_weights": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
            "reference_target_shares_before_cost": {"0050.TW": 40, "00631L.TW": 150},
            "latest_prices": {"0050.TW": 120.0, "00631L.TW": 40.0},
            "execution_guard_reasons": [],
            "execution_allowed": True,
            "signal_alerts": [],
            "portfolio_value_input": 16_400.0,
            "cross_market_graph_shadow": {
                "status": "available",
                "policy": "shadow_only_no_weight_change",
                "latest_shadow_action": "NO_ADD",
                "no_add_active": True,
                "recommended_action": "pause_new_risk_adds_manual_review",
                "latest_probabilities": {"REENTER": 0.40, "NO_ADD": 0.67},
                "thresholds": {"no_add_alert_probability": 0.65},
                "metrics": {"NO_ADD": {"auc": 0.53}, "REENTER": {"auc": 0.48}},
                "metrics_by_year": {
                    "2022": {
                        "NO_ADD": {"auc": 0.56, "balanced_accuracy": 0.54},
                        "REENTER": {"auc": 0.45},
                    }
                },
                "metrics_by_condition": {
                    "condition_0050_5d_abs_ge_2pct": {
                        "condition_rows": 100,
                        "condition_frequency": 0.20,
                        "NO_ADD": {"auc": 0.54, "balanced_accuracy": 0.52},
                        "REENTER": {"auc": 0.50},
                    }
                },
                "promotion_assessment": {
                    "recommended_use": "NO_ADD_ONLY_SHADOW_FILTER",
                    "promote_to_execution_guard": False,
                    "promote_to_reentry_signal": False,
                    "minimum_live_alert_policy": {"auto_weight_change": False},
                },
                "selected_features": ["src_SOXX_ret1d"],
                "report_path": "results/cross_market_directed_graph_shadow_default_tuned_yearly_20260715.json",
            },
        }
        with (
            patch.object(execution_plan, "load_group_a_plus_holdings", return_value={"0050.TW": 20, "00631L.TW": 100}),
            patch.object(execution_plan, "_latest_prices", return_value={"0050.TW": 120.0, "00631L.TW": 40.0}),
            patch.object(execution_plan, "build_daily_signal", return_value=signal),
        ):
            plan = build_execution_plan(
                Path("dummy.xlsx"),
                "2026-07-15",
                cash_balance=10_000.0,
                max_business_stale_days=3,
                db_path=Path("dummy.db"),
                manifest_path=Path("strategy.json"),
                min_trade_notional=0.0,
                min_weight_deviation=0.0,
                min_staged_buy_notional=999_999.0,
            )

        self.assertTrue(plan["execution_allowed"])
        self.assertEqual(plan["target_shares"]["00631L.TW"], 150)
        self.assertEqual(plan["cross_market_graph_advisory"]["recommended_use"], "NO_ADD_ONLY_SHADOW_FILTER")
        self.assertTrue(plan["cross_market_graph_advisory"]["no_add_active"])
        self.assertFalse(plan["cross_market_graph_advisory"]["promote_to_execution_guard"])
        self.assertFalse(plan["cross_market_graph_advisory"]["promote_to_reentry_signal"])
        self.assertFalse(plan["cross_market_graph_advisory"]["auto_weight_change"])
        self.assertEqual(plan["cross_market_graph_advisory"]["stress_year_metrics"]["2022"]["NO_ADD_auc"], 0.56)
        self.assertEqual(
            plan["cross_market_graph_advisory"]["condition_metrics"]["condition_0050_5d_abs_ge_2pct"]["NO_ADD_auc"],
            0.54,
        )
        self.assertTrue(plan["execution_summary"]["cross_market_graph_no_add_active"])

    def test_execution_plan_reports_both_volatility_and_compounding_guards_when_both_block(self) -> None:
        signal = {
            "strategy_id": "a2118",
            "actual_data_date": "2026-07-09",
            "execution_regime": "golden1",
            "target_weights": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
            "reference_target_shares_before_cost": {"0050.TW": 40, "00631L.TW": 150},
            "latest_prices": {"0050.TW": 120.0, "00631L.TW": 40.0},
            "execution_guard_reasons": [],
            "execution_allowed": True,
            "signal_alerts": [
                {
                    "type": "volatility_gate_high_vol",
                    "metadata": {
                        "allow_00631l_add": False,
                        "trade_policy": "advisory_no_auto_weight_change",
                    },
                }
            ],
            "portfolio_value_input": 16_400.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            compounding_path = Path(tmp) / "compounding.json"
            compounding_path.write_text(
                json.dumps(
                    {
                        "latest": {
                            "date": "2026-07-09",
                            "compounding_regime": "MEAN_REVERTING",
                            "recommended_policy": "prohibit_new_leverage_or_reduce_rebalance_frequency",
                        }
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(execution_plan, "load_group_a_plus_holdings", return_value={"0050.TW": 20, "00631L.TW": 100}),
                patch.object(execution_plan, "_latest_prices", return_value={"0050.TW": 120.0, "00631L.TW": 40.0}),
                patch.object(execution_plan, "build_daily_signal", return_value=signal),
            ):
                plan = build_execution_plan(
                    Path("dummy.xlsx"),
                    "2026-07-09",
                    cash_balance=10_000.0,
                    max_business_stale_days=3,
                    db_path=Path("dummy.db"),
                    manifest_path=Path("strategy.json"),
                    min_trade_notional=0.0,
                    min_weight_deviation=0.0,
                    min_staged_buy_notional=999_999.0,
                    compounding_regime_path=compounding_path,
                )

        self.assertEqual(plan["target_shares"]["00631L.TW"], 100)
        self.assertEqual(plan["pre_trade_guard"]["status"], "blocked")
        self.assertEqual(plan["compounding_regime_pre_trade_guard"]["status"], "blocked")
        self.assertEqual(plan["pre_trade_guard"]["blocked_trades"][0]["blocked_delta_shares"], 50)
        self.assertEqual(plan["compounding_regime_pre_trade_guard"]["blocked_trades"][0]["blocked_delta_shares"], 50)
        self.assertEqual(
            plan["guard_impact_summary"]["blocked_guard_names"],
            ["volatility_gate_no_00631l_add", "compounding_regime_no_00631l_add"],
        )
        self.assertEqual(plan["guard_impact_summary"]["combined_blocked_trade_count"], 1)
        self.assertEqual(plan["guard_impact_summary"]["combined_blocked_buy_notional"], 2000.0)
        self.assertEqual([trade["ticker"] for trade in plan["trades"]], ["0050.TW"])

    def test_execution_plan_blocks_misaligned_compounding_regime_date(self) -> None:
        signal = {
            "strategy_id": "a2118",
            "actual_data_date": "2026-07-09",
            "execution_regime": "golden1",
            "target_weights": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
            "reference_target_shares_before_cost": {"0050.TW": 20, "00631L.TW": 100},
            "latest_prices": {"0050.TW": 120.0, "00631L.TW": 40.0},
            "execution_guard_reasons": [],
            "execution_allowed": True,
            "signal_alerts": [],
            "portfolio_value_input": 16_400.0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            compounding_path = Path(tmp) / "compounding.json"
            compounding_path.write_text(
                json.dumps({"latest": {"date": "2026-07-08", "compounding_regime": "TREND_PERSISTENT"}}),
                encoding="utf-8",
            )
            with (
                patch.object(execution_plan, "load_group_a_plus_holdings", return_value={"0050.TW": 20, "00631L.TW": 100}),
                patch.object(execution_plan, "_latest_prices", return_value={"0050.TW": 120.0, "00631L.TW": 40.0}),
                patch.object(execution_plan, "build_daily_signal", return_value=signal),
            ):
                plan = build_execution_plan(
                    Path("dummy.xlsx"),
                    "2026-07-09",
                    cash_balance=10_000.0,
                    max_business_stale_days=3,
                    db_path=Path("dummy.db"),
                    manifest_path=Path("strategy.json"),
                    compounding_regime_path=compounding_path,
                )

        self.assertFalse(plan["execution_allowed"])
        self.assertEqual(plan["planning_status"], "manual_review_required")
        self.assertTrue(any("compounding regime date does not align" in reason for reason in plan["execution_guard_reasons"]))

    def test_execution_plan_blocks_portfolio_value_mismatch(self) -> None:
        signal = {
            "strategy_id": "a2118",
            "actual_data_date": "2026-07-09",
            "execution_regime": "golden1",
            "target_weights": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
            "reference_target_shares_before_cost": {"0050.TW": 20, "00631L.TW": 100},
            "latest_prices": {"0050.TW": 120.0, "00631L.TW": 40.0},
            "execution_guard_reasons": [],
            "execution_allowed": True,
            "signal_alerts": [],
            "portfolio_value_input": 1_000_000.0,
        }
        with (
            patch.object(execution_plan, "load_group_a_plus_holdings", return_value={"0050.TW": 20, "00631L.TW": 100}),
            patch.object(execution_plan, "_latest_prices", return_value={"0050.TW": 120.0, "00631L.TW": 40.0}),
            patch.object(execution_plan, "build_daily_signal", return_value=signal),
        ):
            plan = build_execution_plan(
                Path("dummy.xlsx"),
                "2026-07-09",
                cash_balance=10_000.0,
                max_business_stale_days=3,
                db_path=Path("dummy.db"),
                manifest_path=Path("strategy.json"),
            )

        self.assertFalse(plan["execution_allowed"])
        self.assertTrue(any("portfolio snapshot mismatch" in reason for reason in plan["execution_guard_reasons"]))


if __name__ == "__main__":
    unittest.main()
