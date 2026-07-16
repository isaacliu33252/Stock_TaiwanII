#!/usr/bin/env python3
"""Regression checks for GroupA+ pre-trade guards."""

from __future__ import annotations

import unittest

from group_a_plus.operations.execution_guard import (
    a2118_extreme_risk_blocks_new_adds,
    apply_compounding_regime_pre_trade_guard,
    apply_risk_add_pre_trade_guard,
    apply_volatility_gate_pre_trade_guard,
    compounding_regime_blocks_00631l_add,
    volatility_gate_blocks_00631l_add,
)


HIGH_VOL_SIGNAL = {
    "signal_alerts": [
        {
            "type": "volatility_gate_high_vol",
            "level": "medium",
            "metadata": {
                "allow_00631l_add": False,
                "trade_policy": "advisory_no_auto_weight_change",
                "reference_00631l_scale": 0.5,
                "volatility_gate": "high_vol_defensive",
            },
        }
    ]
}

EXTREME_WARNING_SIGNAL = {
    "signal_alerts": [
        {
            "type": "a2118_extreme_risk_warning",
            "level": "medium",
            "metadata": {
                "policy": "warning_only_no_weight_change",
                "recommended_action": "pause_new_risk_adds",
                "allow_new_0050_add": False,
                "allow_new_00631l_add": False,
            },
        }
    ]
}

TAIL_CONFORMAL_SIGNAL = {
    "signal_alerts": [
        {
            "type": "tail_specific_conformal_warning",
            "level": "medium",
            "metadata": {
                "policy": "diagnostic_warning_only_no_weight_change",
                "recommended_action": "pause_new_00631l_adds_and_monitor_trough",
                "allow_00631l_add": False,
                "auto_reduce_00631l": False,
                "min_lower_tail_confidence_bound": -0.09,
                "max_prob_mdd_lt_8pct": 0.42,
            },
        }
    ]
}

MEAN_REVERTING_COMPOUNDING = {
    "latest": {
        "date": "2026-07-09",
        "compounding_regime": "MEAN_REVERTING",
        "recommended_policy": "prohibit_new_leverage_or_reduce_rebalance_frequency",
    }
}


class GroupAPlusExecutionGuardTests(unittest.TestCase):
    def test_high_vol_blocks_00631l_add_only(self) -> None:
        targets, guard = apply_volatility_gate_pre_trade_guard(
            {"00631L.TW": 100, "0050.TW": 20},
            {"00631L.TW": 150, "0050.TW": 40},
            HIGH_VOL_SIGNAL,
        )

        self.assertEqual(targets["00631L.TW"], 100)
        self.assertEqual(targets["0050.TW"], 40)
        self.assertEqual(guard["status"], "blocked")
        self.assertFalse(guard["allow_00631l_add"])
        self.assertEqual(guard["blocked_trades"][0]["blocked_delta_shares"], 50)

    def test_high_vol_allows_hold_and_reduction(self) -> None:
        hold_targets, hold_guard = apply_volatility_gate_pre_trade_guard(
            {"00631L.TW": 100},
            {"00631L.TW": 100},
            HIGH_VOL_SIGNAL,
        )
        sell_targets, sell_guard = apply_volatility_gate_pre_trade_guard(
            {"00631L.TW": 100},
            {"00631L.TW": 60},
            HIGH_VOL_SIGNAL,
        )

        self.assertEqual(hold_targets["00631L.TW"], 100)
        self.assertEqual(hold_guard["status"], "active_allowed")
        self.assertEqual(hold_guard["blocked_trades"], [])
        self.assertEqual(sell_targets["00631L.TW"], 60)
        self.assertEqual(sell_guard["status"], "active_allowed")
        self.assertEqual(sell_guard["blocked_trades"], [])

    def test_tail_conformal_blocks_00631l_add_only(self) -> None:
        targets, guard = apply_volatility_gate_pre_trade_guard(
            {"00631L.TW": 100, "0050.TW": 20},
            {"00631L.TW": 150, "0050.TW": 40},
            TAIL_CONFORMAL_SIGNAL,
        )

        self.assertTrue(volatility_gate_blocks_00631l_add(TAIL_CONFORMAL_SIGNAL))
        self.assertEqual(targets["00631L.TW"], 100)
        self.assertEqual(targets["0050.TW"], 40)
        self.assertEqual(guard["status"], "blocked")
        self.assertEqual("tail_specific_conformal_warning", guard["source_alert_type"])
        self.assertEqual("tail_conformal_no_00631l_add", guard["blocked_trades"][0]["reason"])

    def test_low_vol_does_not_block_00631l_add(self) -> None:
        targets, guard = apply_volatility_gate_pre_trade_guard(
            {"00631L.TW": 100},
            {"00631L.TW": 150},
            {"signal_alerts": []},
        )

        self.assertEqual(targets["00631L.TW"], 150)
        self.assertEqual(guard["status"], "inactive")
        self.assertTrue(guard["allow_00631l_add"])

    def test_garch_shadow_high_vol_blocks_even_without_alert_metadata(self) -> None:
        self.assertTrue(
            volatility_gate_blocks_00631l_add(
                {
                    "garch_regime_shadow": {
                        "volatility_gate": {
                            "high_vol_gate": True,
                            "gate": "high_vol_defensive",
                        }
                    }
                }
            )
        )

    def test_a2118_extreme_warning_blocks_0050_and_00631l_adds_only(self) -> None:
        targets, guard = apply_risk_add_pre_trade_guard(
            {"0050.TW": 100, "00631L.TW": 20, "00679B.TWO": 10},
            {"0050.TW": 150, "00631L.TW": 30, "00679B.TWO": 20},
            EXTREME_WARNING_SIGNAL,
        )

        self.assertTrue(a2118_extreme_risk_blocks_new_adds(EXTREME_WARNING_SIGNAL))
        self.assertEqual(targets["0050.TW"], 100)
        self.assertEqual(targets["00631L.TW"], 20)
        self.assertEqual(targets["00679B.TWO"], 20)
        self.assertEqual(guard["status"], "blocked")
        self.assertEqual({trade["ticker"] for trade in guard["blocked_trades"]}, {"0050.TW", "00631L.TW"})

    def test_a2118_extreme_warning_allows_holds_and_sells(self) -> None:
        targets, guard = apply_risk_add_pre_trade_guard(
            {"0050.TW": 100, "00631L.TW": 20},
            {"0050.TW": 80, "00631L.TW": 20},
            EXTREME_WARNING_SIGNAL,
        )

        self.assertEqual(targets["0050.TW"], 80)
        self.assertEqual(targets["00631L.TW"], 20)
        self.assertEqual(guard["status"], "active_allowed")
        self.assertEqual(guard["blocked_trades"], [])

    def test_a2118_extreme_warning_overlay_fallback_blocks_new_adds(self) -> None:
        self.assertTrue(
            a2118_extreme_risk_blocks_new_adds(
                {
                    "ncf_live_overlay": {
                        "a2118_extreme_risk_warning": {
                            "active": True,
                            "recommended_action": "pause_new_risk_adds",
                        }
                    }
                }
            )
        )

    def test_mean_reverting_compounding_regime_blocks_00631l_add_only(self) -> None:
        targets, guard = apply_compounding_regime_pre_trade_guard(
            {"00631L.TW": 100, "0050.TW": 20},
            {"00631L.TW": 150, "0050.TW": 40},
            MEAN_REVERTING_COMPOUNDING,
        )

        self.assertTrue(compounding_regime_blocks_00631l_add(MEAN_REVERTING_COMPOUNDING))
        self.assertEqual(targets["00631L.TW"], 100)
        self.assertEqual(targets["0050.TW"], 40)
        self.assertEqual(guard["status"], "blocked")
        self.assertFalse(guard["allow_00631l_add"])
        self.assertEqual(guard["blocked_trades"][0]["reason"], "compounding_regime_no_00631l_add")

    def test_trend_persistent_compounding_regime_does_not_block_add(self) -> None:
        targets, guard = apply_compounding_regime_pre_trade_guard(
            {"00631L.TW": 100},
            {"00631L.TW": 150},
            {
                "latest": {
                    "date": "2026-07-09",
                    "compounding_regime": "TREND_PERSISTENT",
                    "recommended_policy": "do_not_reduce_for_high_volatility_alone",
                }
            },
        )

        self.assertEqual(targets["00631L.TW"], 150)
        self.assertEqual(guard["status"], "inactive")
        self.assertTrue(guard["allow_00631l_add"])


if __name__ == "__main__":
    unittest.main()
