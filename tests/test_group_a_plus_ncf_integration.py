#!/usr/bin/env python3
"""Unit tests for NCF integration into Group A+ strategy (A21.13)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from group_a_plus.integrations.ncf import (
    adjust_golden1_weights,
    load_ncf_2330_checklist,
    load_ncf_signal,
    ncf_cross_ticker_consistency,
    ncf_downside_signal,
    ncf_dynamic_horizon_signal,
    ncf_overlay_summary,
    ncf_regime_gated_signal,
    ncf_tail_downside_signal,
    ncf_tail_upside_signal,
    ncf_upside_signal,
)
from group_a_plus.governance.latest import SUPPORTED_STRATEGIES
from group_a_plus.runners.a2113 import A2113_ID, _resolve_ncf_path
from group_a_plus.runners.a2118 import (
    NCF_LB_REGIME,
    _apply_late_bull_overlay,
    _ncf_panel_metadata,
    _signal_date_matches,
)


def _make_ncf_json(
    ticker: str,
    direction: str,
    calibrated_prob_up: float,
    confidence: float,
    votes_up: int = 2,
) -> dict:
    return {
        "ticker": ticker,
        "last_close_date": "2026-06-25",
        "last_close": 100.0,
        "current_regime": "BULL",
        "horizon_ensemble": {
            "direction": direction,
            "combined_probability_up": calibrated_prob_up,
            "calibrated_probability_up": calibrated_prob_up,
            "confidence": confidence,
            "shrinkage": 0.6,
            "weighted_return": -0.005,
            "predicted_close": 99.5,
            "votes_up": votes_up,
            "direction_weights": {"1": 0.4, "5": 0.35, "20": 0.25},
            "return_weights": {"1": 0.4, "5": 0.35, "20": 0.25},
            "horizon_aucs": {"1": 0.58, "5": 0.55, "20": 0.52},
            "wf_h1_rf_accuracy": None,
            "wf_confidence_component": None,
            "wf_confidence_used": False,
        },
        "horizons": {
            "1": {"classification": {"probability_up": calibrated_prob_up, "val_auc": 0.56}},
            "5": {"classification": {"probability_up": calibrated_prob_up, "val_auc": 0.62}},
            "20": {"classification": {"probability_up": calibrated_prob_up, "val_auc": 0.68}},
        },
    }


class NCFSignalLoadTests(unittest.TestCase):
    def _write_ncf(self, tmp_dir: str, ticker: str, prob: float, conf: float, direction: str) -> Path:
        path = Path(tmp_dir) / f"ncf_{ticker}.json"
        path.write_text(json.dumps(_make_ncf_json(ticker, direction, prob, conf)), encoding="utf-8")
        return path

    def test_load_ncf_signal_extracts_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_ncf(tmp, "00631L.TW", 0.35, 0.6, "DOWN")
            sig = load_ncf_signal(p)
        self.assertEqual(sig["ticker"], "00631L.TW")
        self.assertEqual(sig["direction"], "DOWN")
        self.assertAlmostEqual(sig["calibrated_prob_up"], 0.35, places=3)
        self.assertAlmostEqual(sig["confidence"], 0.6, places=3)
        self.assertEqual(sig["date"], "2026-06-25")

    def test_load_ncf_signal_votes_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_ncf(tmp, "00631L.TW", 0.7, 0.8, "UP")
            sig = load_ncf_signal(p)
        self.assertEqual(sig["votes_up"], 2)

    def test_load_ncf_signal_confidence_panel_aligned_absent_is_none(self) -> None:
        """H2 (2026-07-02 Fable 5 audit, Option A): payloads without the new
        prob_magnitude_panel_aligned field must yield None, not silently
        fall back to the differently-scaled composite `confidence`."""
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_ncf(tmp, "00631L.TW", 0.35, 0.6, "DOWN")
            sig = load_ncf_signal(p)
        self.assertIsNone(sig["confidence_panel_aligned"])

    def test_load_ncf_signal_confidence_panel_aligned_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _make_ncf_json("00631L.TW", "DOWN", 0.35, 0.6)
            payload["horizon_ensemble"]["prob_magnitude_panel_aligned"] = 0.04
            path = Path(tmp) / "ncf_00631L.TW.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            sig = load_ncf_signal(path)
        self.assertAlmostEqual(sig["confidence_panel_aligned"], 0.04, places=4)

    def test_load_ncf_signal_extracts_horizon_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_ncf(tmp, "00632R.TW", 0.7, 0.8, "UP")
            sig = load_ncf_signal(p)
        self.assertAlmostEqual(sig["horizon_prob_up"]["5"], 0.7, places=4)
        self.assertAlmostEqual(sig["horizon_val_auc"]["20"], 0.68, places=4)

    def test_load_ncf_signal_extracts_tsmc_market_state_and_severe_risk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _make_ncf_json("2330.TW", "UP", 0.58, 0.49)
            payload["forward_drawdown_risk"] = {"available": True, "probability": 0.36}
            payload["forward_severe_drawdown_risk"] = {"available": True, "probability": 0.10}
            payload["tsmc_market_state"] = {
                "state": 2,
                "label_zh": "高檔震盪",
                "policy": "diagnostic_only_no_weight_change",
            }
            path = Path(tmp) / "ncf_2330.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            sig = load_ncf_signal(path)

        self.assertAlmostEqual(sig["prob_fwd_mdd_gt5_h20"], 0.36, places=4)
        self.assertAlmostEqual(sig["prob_fwd_mdd_gt8_h20"], 0.10, places=4)
        self.assertEqual(sig["tsmc_market_state"]["state"], 2)
        self.assertEqual(sig["tsmc_market_state"]["label_zh"], "高檔震盪")

    def test_load_ncf_signal_adds_direction_magnitude_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_ncf(tmp, "00631L.TW", 0.7, 0.8, "UP")
            sig = load_ncf_signal(p)

        self.assertIn("direction_magnitude_gate", sig)
        self.assertFalse(sig["direction_magnitude_gate"]["passed"])
        self.assertEqual("DOWN", sig["direction_magnitude_gate"]["return_side"])

    def test_load_ncf_2330_checklist_extracts_factor_quality_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ncf_2330_checklist.json"
            path.write_text(
                json.dumps(
                    {
                        "report": "ncf_2330_checklist",
                        "mode": "daily",
                        "as_of": "2026-07-03",
                        "overall_signal": "neutral",
                        "available_layer_score": 1,
                        "available_layer_count": 9,
                        "policy": "diagnostic_only_no_weight_change",
                        "factor_quality_overlay": {
                            "status": "research_only",
                            "signal": "bearish",
                            "label": "risk_off",
                            "risk_score": 6.0,
                            "opportunity_score": 1.0,
                            "net_score": -5.0,
                        },
                        "layers": {"technical": {"signal": "neutral"}},
                    }
                ),
                encoding="utf-8",
            )
            checklist = load_ncf_2330_checklist(path)

        self.assertEqual("ncf_2330_checklist", checklist["report"])
        self.assertEqual("bearish", checklist["factor_quality_signal"])
        self.assertEqual("risk_off", checklist["factor_quality_label"])
        self.assertEqual(6.0, checklist["factor_quality_risk_score"])
        self.assertEqual("technical", next(iter(checklist["layers"])))


class A2118LateBullHoldTests(unittest.TestCase):
    def test_ncf_panel_metadata_records_content_fingerprint(self) -> None:
        idx = pd.to_datetime(["2026-02-23", "2026-02-24"])
        panel = pd.DataFrame(
            {
                "prob_up_h20": [0.28, 0.40],
                "confidence": [0.60, 0.40],
            },
            index=idx,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "panel.csv"
            panel.rename_axis("date").to_csv(path)
            meta = _ncf_panel_metadata(path, panel)

        self.assertEqual(2, meta["panel_631l_rows"])
        self.assertEqual("2026-02-23", meta["panel_631l_first_date"])
        self.assertEqual("2026-02-24", meta["panel_631l_last_date"])
        self.assertRegex(meta["panel_631l_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(meta["panel_631l_modified_at"].endswith("Z"))

    def test_signal_date_must_match_frame_date(self) -> None:
        self.assertTrue(_signal_date_matches({"date": "2026-06-29"}, pd.Timestamp("2026-06-29")))
        self.assertFalse(_signal_date_matches({"date": "2026-06-29"}, pd.Timestamp("2026-06-18")))
        self.assertFalse(_signal_date_matches({}, pd.Timestamp("2026-06-29")))

    def test_missing_required_panel_columns_skip_overlay(self) -> None:
        idx = pd.to_datetime(["2026-02-23"])
        regime = pd.Series(["golden1"], index=idx)
        ma_gap = pd.Series([0.19], index=idx)
        panel = pd.DataFrame({"prob_up_h20": [0.28]}, index=idx)

        modified, info = _apply_late_bull_overlay(
            regime,
            panel,
            ma_gap,
            h20_max=0.33,
            conf_min=0.55,
        )

        self.assertEqual(["golden1"], modified.tolist())
        self.assertEqual("missing_required_panel_columns", info["skipped_reason"])
        self.assertEqual(["confidence"], info["missing_columns"])

    def test_nan_panel_values_skip_overlay(self) -> None:
        idx = pd.to_datetime(["2026-02-23"])
        regime = pd.Series(["golden1"], index=idx)
        ma_gap = pd.Series([0.19], index=idx)
        panel = pd.DataFrame(
            {"prob_up_h20": [0.28], "confidence": [float("nan")], "prob_up_h5": [0.30]},
            index=idx,
        )

        modified, info = _apply_late_bull_overlay(
            regime,
            panel,
            ma_gap,
            h20_max=0.33,
            conf_min=0.55,
        )

        self.assertEqual(["golden1"], modified.tolist())
        self.assertEqual(["2026-02-23"], info["skipped_days"])

    def test_h5_hold_keeps_hedge_until_reentry_signal(self) -> None:
        idx = pd.to_datetime(["2026-02-23", "2026-02-24", "2026-02-25", "2026-02-26"])
        regime = pd.Series(["golden1"] * 4, index=idx)
        ma_gap = pd.Series([0.19, 0.21, 0.22, 0.23], index=idx)
        panel = pd.DataFrame(
            {
                "prob_up_h20": [0.28, 0.40, 0.42, 0.43],
                "confidence": [0.60, 0.40, 0.40, 0.40],
                "prob_up_h5": [0.30, 0.35, 0.54, 0.56],
            },
            index=idx,
        )

        modified, info = _apply_late_bull_overlay(
            regime,
            panel,
            ma_gap,
            h20_max=0.33,
            conf_min=0.55,
            h5_reentry_min=0.55,
        )

        self.assertEqual(
            [NCF_LB_REGIME, NCF_LB_REGIME, NCF_LB_REGIME, "golden1"],
            modified.tolist(),
        )
        self.assertEqual(1, info["late_bull_trigger_days"])
        self.assertEqual(["2026-02-24", "2026-02-25"], info["hold_days"])
        self.assertEqual(3, info["total_hedge_days"])

    def test_h5_hold_resets_when_base_regime_leaves_golden1(self) -> None:
        idx = pd.to_datetime(["2026-02-23", "2026-02-24", "2026-02-25"])
        regime = pd.Series(["golden1", "group_a_plus_defensive", "golden1"], index=idx)
        ma_gap = pd.Series([0.19, 0.21, 0.22], index=idx)
        panel = pd.DataFrame(
            {
                "prob_up_h20": [0.28, 0.40, 0.42],
                "confidence": [0.60, 0.40, 0.40],
                "prob_up_h5": [0.30, 0.30, 0.30],
            },
            index=idx,
        )

        modified, info = _apply_late_bull_overlay(
            regime,
            panel,
            ma_gap,
            h20_max=0.33,
            conf_min=0.55,
            h5_reentry_min=0.55,
        )

        self.assertEqual(
            [NCF_LB_REGIME, "group_a_plus_defensive", "golden1"],
            modified.tolist(),
        )
        self.assertEqual([], info["hold_days"])


class A2120RallyAwareGateTests(unittest.TestCase):
    """Tests for the 3-tier rally-aware gate introduced in A21.20."""

    def test_a2120_h20_default_matches_active_a2118_threshold(self) -> None:
        from group_a_plus.runners.a2120 import A2120_H20_MAX

        self.assertAlmostEqual(0.33, A2120_H20_MAX)

    def _make_panel(
        self, h20_probs, confs, h5_probs, gain_probs, dates=None
    ) -> pd.DataFrame:
        if dates is None:
            dates = pd.date_range("2026-02-23", periods=len(h20_probs))
        return pd.DataFrame(
            {
                "prob_up_h20": h20_probs,
                "confidence": confs,
                "prob_up_h5": h5_probs,
                "prob_fwd_gain_gt5_h20": gain_probs,
            },
            index=dates,
        )

    def test_rally_suppression_prevents_hedge_when_gain_prob_high(self) -> None:
        """When gain_prob >= rally_suppress_min, hedge must be suppressed entirely."""
        idx = pd.to_datetime(["2026-04-30"])
        regime = pd.Series(["golden1"], index=idx)
        ma_gap = pd.Series([0.23], index=idx)
        panel = self._make_panel(
            h20_probs=[0.26],
            confs=[0.58],
            h5_probs=[0.50],
            gain_probs=[0.55],  # >= 0.50 → should suppress
            dates=idx,
        )

        modified, info = _apply_late_bull_overlay(
            regime, panel, ma_gap,
            h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55,
            gain_prob_soft_min=0.30, rally_suppress_min=0.50,
        )

        self.assertEqual(["golden1"], modified.tolist())
        # Trigger condition fired but hedge NOT entered (rally suppressed)
        self.assertEqual(0, info["late_bull_trigger_days"])
        self.assertEqual(["2026-04-30"], info["suppressed_days"])
        self.assertEqual(0, info["total_hedge_days"])

    def test_soft_hedge_applied_when_gain_prob_in_middle_tier(self) -> None:
        """When gain_prob in [0.30, 0.50), apply soft hedge regime."""
        from group_a_plus.runners.a2118 import NCF_LB_SOFT_REGIME
        idx = pd.to_datetime(["2026-04-30"])
        regime = pd.Series(["golden1"], index=idx)
        ma_gap = pd.Series([0.23], index=idx)
        panel = self._make_panel(
            h20_probs=[0.26],
            confs=[0.58],
            h5_probs=[0.50],
            gain_probs=[0.43],  # in [0.30, 0.50) → soft hedge
            dates=idx,
        )

        modified, info = _apply_late_bull_overlay(
            regime, panel, ma_gap,
            h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55,
            gain_prob_soft_min=0.30, rally_suppress_min=0.50,
        )

        self.assertEqual([NCF_LB_SOFT_REGIME], modified.tolist())
        self.assertEqual(1, info["late_bull_trigger_days"])
        self.assertEqual(["2026-04-30"], info["soft_hedge_days"])
        self.assertEqual([], info["suppressed_days"])

    def test_hard_hedge_applied_when_gain_prob_low(self) -> None:
        """When gain_prob < 0.30, apply full hard hedge (same as A21.18)."""
        idx = pd.to_datetime(["2026-02-23"])
        regime = pd.Series(["golden1"], index=idx)
        ma_gap = pd.Series([0.19], index=idx)
        panel = self._make_panel(
            h20_probs=[0.17],
            confs=[0.56],
            h5_probs=[0.30],
            gain_probs=[0.25],  # < 0.30 → hard hedge
            dates=idx,
        )

        modified, info = _apply_late_bull_overlay(
            regime, panel, ma_gap,
            h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55,
            gain_prob_soft_min=0.30, rally_suppress_min=0.50,
        )

        self.assertEqual([NCF_LB_REGIME], modified.tolist())
        self.assertEqual(1, info["late_bull_trigger_days"])
        self.assertEqual([], info["suppressed_days"])
        self.assertEqual([], info["soft_hedge_days"])

    def test_rally_suppression_exits_hold_early(self) -> None:
        """When in hold and gain_prob rises above rally_suppress_min, exit hold early."""
        idx = pd.to_datetime(["2026-02-23", "2026-02-24", "2026-02-25", "2026-02-26"])
        regime = pd.Series(["golden1"] * 4, index=idx)
        ma_gap = pd.Series([0.19, 0.20, 0.21, 0.22], index=idx)
        panel = self._make_panel(
            h20_probs=[0.28, 0.40, 0.42, 0.43],
            confs=[0.60, 0.40, 0.40, 0.40],
            h5_probs=[0.30, 0.35, 0.35, 0.35],
            gain_probs=[0.25, 0.30, 0.52, 0.55],
            # Day 3: gain_prob >= 0.50 → rally exit of hold
            dates=idx,
        )

        modified, info = _apply_late_bull_overlay(
            regime, panel, ma_gap,
            h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55,
            gain_prob_soft_min=0.30, rally_suppress_min=0.50,
        )

        # Day 0: hard hedge (gain_prob=0.25 < 0.30)
        # Day 1: hold (soft, gain_prob=0.30)
        # Day 2: hold exit by rally suppression (gain_prob=0.52 >= 0.50)
        # Day 3: back to golden1
        self.assertEqual("golden1", modified.iloc[2])
        self.assertEqual("golden1", modified.iloc[3])
        self.assertEqual(1, info["late_bull_trigger_days"])


class NCFDynamicHorizonTests(unittest.TestCase):
    def test_dynamic_horizon_weights_use_multi_year_prior(self) -> None:
        sig = {
            "ticker": "00632R.TW",
            "calibrated_prob_up": 0.5,
            "confidence": 1.0,
            "horizon_prob_up": {"1": 0.95, "5": 0.65, "20": 0.70},
            "horizon_val_auc": {"1": 0.55, "5": 0.55, "20": 0.55},
        }

        result = ncf_dynamic_horizon_signal(sig, blend_live_auc=0.0)

        self.assertGreater(result["weights"]["5"], result["weights"]["1"])
        self.assertGreater(result["weights"]["20"], result["weights"]["1"])
        self.assertEqual(result["direction"], "UP")

    def test_dynamic_horizon_falls_back_to_ensemble_when_no_horizon_data(self) -> None:
        sig = {"ticker": "00631L.TW", "calibrated_prob_up": 0.42, "confidence": 0.5}

        result = ncf_dynamic_horizon_signal(sig)

        self.assertEqual(result["source"], "ensemble_fallback")
        self.assertAlmostEqual(result["probability_up"], 0.42, places=4)


class NCFCrossTickerConsistencyTests(unittest.TestCase):
    def _sig(self, ticker: str, probs: dict[str, float], conf: float = 0.8) -> dict:
        return {
            "ticker": ticker,
            "calibrated_prob_up": sum(probs.values()) / len(probs),
            "confidence": conf,
            "horizon_prob_up": probs,
            "horizon_val_auc": {"1": 0.58, "5": 0.64, "20": 0.66},
        }

    def test_consistent_market_up_signal(self) -> None:
        l = self._sig("00631L.TW", {"1": 0.65, "5": 0.70, "20": 0.68})
        r = self._sig("00632R.TW", {"1": 0.35, "5": 0.30, "20": 0.32})

        result = ncf_cross_ticker_consistency(l, r)

        self.assertEqual(result["market_direction"], "UP")
        self.assertFalse(result["conflict_flag"])
        self.assertGreater(result["agreement_score"], 0.6)

    def test_conflicting_same_direction_etf_outputs(self) -> None:
        l = self._sig("00631L.TW", {"1": 0.70, "5": 0.70, "20": 0.70})
        r = self._sig("00632R.TW", {"1": 0.70, "5": 0.70, "20": 0.70})

        result = ncf_cross_ticker_consistency(l, r)

        self.assertTrue(result["conflict_flag"])
        self.assertLess(result["agreement_score"], 0.5)


class NCFDownsideSignalTests(unittest.TestCase):
    def _sig(self, ticker: str, prob: float, conf: float, direction: str = "DOWN") -> dict:
        return {
            "ticker": ticker,
            "calibrated_prob_up": prob,
            "confidence": conf,
            "direction": direction,
            "votes_up": 1,
        }

    def test_both_bearish_gives_strong_signal(self) -> None:
        # 00631L bearish (prob=0.2) + 00632R bullish (prob=0.8) = max downside
        sig_l = self._sig("00631L.TW", 0.2, 1.0)
        sig_r = self._sig("00632R.TW", 0.8, 1.0, "UP")
        down = ncf_downside_signal(sig_l, sig_r)
        self.assertGreater(down, 0.5)

    def test_both_bullish_gives_zero_downside(self) -> None:
        # 00631L bullish (prob=0.8) + 00632R bearish (prob=0.2) = no downside
        sig_l = self._sig("00631L.TW", 0.8, 1.0, "UP")
        sig_r = self._sig("00632R.TW", 0.2, 1.0, "DOWN")
        down = ncf_downside_signal(sig_l, sig_r)
        self.assertEqual(down, 0.0)

    def test_neutral_prob_gives_zero(self) -> None:
        sig_l = self._sig("00631L.TW", 0.5, 1.0)
        sig_r = self._sig("00632R.TW", 0.5, 1.0)
        self.assertEqual(ncf_downside_signal(sig_l, sig_r), 0.0)

    def test_low_confidence_reduces_signal(self) -> None:
        sig_l_high_conf = self._sig("00631L.TW", 0.2, 0.9)
        sig_l_low_conf  = self._sig("00631L.TW", 0.2, 0.1)
        sig_r = self._sig("00632R.TW", 0.5, 0.0)
        d_high = ncf_downside_signal(sig_l_high_conf, sig_r)
        d_low  = ncf_downside_signal(sig_l_low_conf, sig_r)
        self.assertGreater(d_high, d_low)

    def test_signal_clipped_to_0_1(self) -> None:
        sig_l = self._sig("00631L.TW", 0.0, 1.0)  # extreme bearish
        sig_r = self._sig("00632R.TW", 1.0, 1.0, "UP")  # extreme inverse
        down = ncf_downside_signal(sig_l, sig_r)
        self.assertLessEqual(down, 1.0)
        self.assertGreaterEqual(down, 0.0)

    def test_downside_upside_complement(self) -> None:
        sig_l = self._sig("00631L.TW", 0.4, 0.6)
        sig_r = self._sig("00632R.TW", 0.6, 0.6, "UP")
        down = ncf_downside_signal(sig_l, sig_r)
        up   = ncf_upside_signal(sig_l, sig_r)
        # Both can be simultaneously low when signals are weak — not guaranteed to sum to 1
        self.assertGreaterEqual(down, 0.0)
        self.assertGreaterEqual(up, 0.0)

    def test_00631l_weighted_higher_than_00632r(self) -> None:
        """00631L contributes 60%, 00632R 40% — pure 00631L signal > pure 00632R signal."""
        base_r = {"ticker": "00632R.TW", "calibrated_prob_up": 0.5, "confidence": 0.0, "direction": "DOWN"}
        # Only 00631L bearish
        sig_l_bear = self._sig("00631L.TW", 0.2, 0.8)
        d_only_l = ncf_downside_signal(sig_l_bear, base_r)
        # Only 00632R bullish (inverse going up = market down)
        base_l = {"ticker": "00631L.TW", "calibrated_prob_up": 0.5, "confidence": 0.0, "direction": "DOWN"}
        sig_r_bull = self._sig("00632R.TW", 0.8, 0.8, "UP")
        d_only_r = ncf_downside_signal(base_l, sig_r_bull)
        self.assertGreater(d_only_l, d_only_r)

    def test_both_conflict_falls_back_to_full_tail_weight(self) -> None:
        # Both models internally disagree (direction vs. return sign), so
        # directional is forced to 0 -- the composite should use tail at full
        # weight (not diluted to 25%) instead of collapsing to 0.
        sig_l = {
            **self._sig("00631L.TW", 0.55, 0.5),
            "direction_conflict": True,
            "prob_fwd_mdd_gt5_h20": 0.70,
            "tail_reward_risk_score": -0.40,
        }
        sig_r = {
            **self._sig("00632R.TW", 0.60, 0.5, "UP"),
            "direction_conflict": True,
            "prob_fwd_gain_gt5_h20": 0.55,
            "tail_reward_risk_score": 0.10,
        }

        down = ncf_downside_signal(sig_l, sig_r)
        tail_only = ncf_tail_downside_signal(sig_l, sig_r)

        self.assertGreater(down, 0.0)
        self.assertAlmostEqual(down, tail_only, places=6)

    def test_both_conflict_with_no_tail_risk_stays_zero(self) -> None:
        # Same as above but no tail-risk inputs available -- should still be
        # a clean 0.0, not an error, matching pre-fix behavior.
        sig_l = {**self._sig("00631L.TW", 0.55, 0.5), "direction_conflict": True}
        sig_r = {**self._sig("00632R.TW", 0.60, 0.5, "UP"), "direction_conflict": True}

        self.assertEqual(ncf_downside_signal(sig_l, sig_r), 0.0)

    def test_single_conflict_unaffected_by_fix(self) -> None:
        # Only one side conflicts -- behavior must be identical to before
        # this fix (still uses the 0.75/0.25 blend, not full tail weight).
        sig_l = {
            **self._sig("00631L.TW", 0.2, 0.8),
            "prob_fwd_mdd_gt5_h20": 0.70,
            "tail_reward_risk_score": -0.40,
        }
        sig_r = {
            **self._sig("00632R.TW", 0.60, 0.5, "UP"),
            "direction_conflict": True,
            "prob_fwd_gain_gt5_h20": 0.55,
            "tail_reward_risk_score": 0.10,
        }

        down = ncf_downside_signal(sig_l, sig_r)
        directional = ncf_downside_signal(sig_l, sig_r, include_tail_risk=False)
        tail = ncf_tail_downside_signal(sig_l, sig_r)
        expected = min(max(0.75 * directional + 0.25 * tail, 0.0), 1.0)

        self.assertAlmostEqual(down, expected, places=6)

    def test_tail_risk_boosts_downside_signal(self) -> None:
        sig_l = {
            **self._sig("00631L.TW", 0.42, 0.6),
            "prob_fwd_mdd_gt5_h20": 0.70,
            "tail_reward_risk_score": -0.40,
        }
        sig_r = {
            **self._sig("00632R.TW", 0.62, 0.5, "UP"),
            "prob_fwd_gain_gt5_h20": 0.55,
            "tail_reward_risk_score": 0.10,
        }

        directional = ncf_downside_signal(sig_l, sig_r, include_tail_risk=False)
        boosted = ncf_downside_signal(sig_l, sig_r)

        self.assertGreater(boosted, directional)
        self.assertGreater(ncf_tail_downside_signal(sig_l, sig_r), 0.0)


class NCFUpsideSignalTailTests(unittest.TestCase):
    """Mirror of NCFDownsideSignalTests' tail-risk/both-conflict coverage,
    for the 2026-07-11 fix that gave ncf_upside_signal the same tail-risk
    fallback ncf_downside_signal already had."""

    def _sig(self, ticker: str, prob: float, conf: float, direction: str = "UP") -> dict:
        return {
            "ticker": ticker,
            "calibrated_prob_up": prob,
            "confidence": conf,
            "direction": direction,
            "votes_up": 1,
        }

    def test_tail_risk_boosts_upside_signal(self) -> None:
        sig_l = {
            **self._sig("00631L.TW", 0.58, 0.6),
            "prob_fwd_gain_gt5_h20": 0.70,
            "tail_reward_risk_score": 0.40,
        }
        sig_r = {
            **self._sig("00632R.TW", 0.38, 0.5, "DOWN"),
            "prob_fwd_mdd_gt5_h20": 0.55,
            "tail_reward_risk_score": -0.10,
        }

        directional = ncf_upside_signal(sig_l, sig_r, include_tail_risk=False)
        boosted = ncf_upside_signal(sig_l, sig_r)

        self.assertGreater(boosted, directional)
        self.assertGreater(ncf_tail_upside_signal(sig_l, sig_r), 0.0)

    def test_both_conflict_falls_back_to_full_tail_weight(self) -> None:
        sig_l = {
            **self._sig("00631L.TW", 0.45, 0.5),
            "direction_conflict": True,
            "prob_fwd_gain_gt5_h20": 0.70,
            "tail_reward_risk_score": 0.40,
        }
        sig_r = {
            **self._sig("00632R.TW", 0.40, 0.5, "DOWN"),
            "direction_conflict": True,
            "prob_fwd_mdd_gt5_h20": 0.55,
            "tail_reward_risk_score": -0.10,
        }

        up = ncf_upside_signal(sig_l, sig_r)
        tail_only = ncf_tail_upside_signal(sig_l, sig_r)

        self.assertGreater(up, 0.0)
        self.assertAlmostEqual(up, tail_only, places=6)

    def test_both_conflict_with_no_tail_risk_stays_zero(self) -> None:
        sig_l = {**self._sig("00631L.TW", 0.45, 0.5), "direction_conflict": True}
        sig_r = {**self._sig("00632R.TW", 0.40, 0.5, "DOWN"), "direction_conflict": True}

        self.assertEqual(ncf_upside_signal(sig_l, sig_r), 0.0)

    def test_single_conflict_unaffected_by_fix(self) -> None:
        sig_l = {
            **self._sig("00631L.TW", 0.58, 0.6),
            "prob_fwd_gain_gt5_h20": 0.70,
            "tail_reward_risk_score": 0.40,
        }
        sig_r = {
            **self._sig("00632R.TW", 0.40, 0.5, "DOWN"),
            "direction_conflict": True,
            "prob_fwd_mdd_gt5_h20": 0.55,
            "tail_reward_risk_score": -0.10,
        }

        up = ncf_upside_signal(sig_l, sig_r)
        directional = ncf_upside_signal(sig_l, sig_r, include_tail_risk=False)
        tail = ncf_tail_upside_signal(sig_l, sig_r)
        expected = min(max(0.75 * directional + 0.25 * tail, 0.0), 1.0)

        self.assertAlmostEqual(up, expected, places=6)


class AdjustGolden1WeightsTests(unittest.TestCase):
    BASE = {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20}

    def test_zero_signal_no_change(self) -> None:
        result = adjust_golden1_weights(self.BASE, downside_signal=0.0)
        self.assertAlmostEqual(result["00631L.TW"], 0.20, places=6)
        self.assertAlmostEqual(result["cash"], 0.20, places=6)

    def test_max_signal_halves_00631l(self) -> None:
        result = adjust_golden1_weights(self.BASE, downside_signal=1.0)
        self.assertAlmostEqual(result["00631L.TW"], 0.10, places=6)
        self.assertAlmostEqual(result["cash"], 0.30, places=6)

    def test_weights_sum_to_one(self) -> None:
        for signal in [0.0, 0.3, 0.6, 1.0]:
            result = adjust_golden1_weights(self.BASE, downside_signal=signal)
            total = result["0050.TW"] + result.get("00631L.TW", 0.0) + result["cash"]
            self.assertAlmostEqual(total, 1.0, places=6, msg=f"signal={signal}")

    def test_0050_unchanged(self) -> None:
        result = adjust_golden1_weights(self.BASE, downside_signal=0.8)
        self.assertAlmostEqual(result["0050.TW"], 0.60, places=6)

    def test_00631l_never_goes_below_half(self) -> None:
        result = adjust_golden1_weights(self.BASE, downside_signal=1.0, max_reduction_fraction=0.5)
        self.assertGreaterEqual(result["00631L.TW"], 0.10 - 1e-9)

    def test_missing_00631l_key_returns_unchanged(self) -> None:
        weights = {"0050.TW": 0.70, "cash": 0.30}
        result = adjust_golden1_weights(weights, downside_signal=0.8)
        self.assertEqual(result, weights)

    def test_mid_signal_proportional(self) -> None:
        result = adjust_golden1_weights(self.BASE, downside_signal=0.5)
        expected_l = 0.20 * (1 - 0.5 * 0.5)  # 0.20 * 0.75 = 0.15
        self.assertAlmostEqual(result["00631L.TW"], expected_l, places=6)


class NCFOverlaySummaryTests(unittest.TestCase):
    def _make_sigs(self) -> tuple[dict, dict]:
        return (
            {"ticker": "00631L.TW", "date": "2026-06-25", "direction": "DOWN",
             "calibrated_prob_up": 0.35, "confidence": 0.5, "votes_up": 1,
             "weighted_return": -0.005, "raw_combined_prob_up": 0.38},
            {"ticker": "00632R.TW", "date": "2026-06-25", "direction": "UP",
             "calibrated_prob_up": 0.65, "confidence": 0.5, "votes_up": 2,
             "weighted_return": 0.005, "raw_combined_prob_up": 0.62},
        )

    def test_summary_contains_required_keys(self) -> None:
        sig_l, sig_r = self._make_sigs()
        base = {"0050.TW": 0.6, "00631L.TW": 0.2, "cash": 0.2}
        summary = ncf_overlay_summary(sig_l, sig_r, base, "golden1")
        for key in ["composite_downside_signal", "action", "base_golden1_weights",
                    "adjusted_golden1_weights", "00631l_reduction"]:
            self.assertIn(key, summary)

    def test_confidence_panel_aligned_passes_through_when_present(self) -> None:
        sig_l, sig_r = self._make_sigs()
        sig_l["confidence_panel_aligned"] = 0.07
        sig_r["confidence_panel_aligned"] = 0.09
        base = {"0050.TW": 0.6, "00631L.TW": 0.2, "cash": 0.2}
        summary = ncf_overlay_summary(sig_l, sig_r, base, "golden1")
        self.assertEqual(summary["ncf_00631l"]["confidence_panel_aligned"], 0.07)
        self.assertEqual(summary["ncf_00632r"]["confidence_panel_aligned"], 0.09)

    def test_confidence_panel_aligned_absent_is_none(self) -> None:
        sig_l, sig_r = self._make_sigs()
        base = {"0050.TW": 0.6, "00631L.TW": 0.2, "cash": 0.2}
        summary = ncf_overlay_summary(sig_l, sig_r, base, "golden1")
        self.assertIsNone(summary["ncf_00631l"]["confidence_panel_aligned"])
        self.assertIsNone(summary["ncf_00632r"]["confidence_panel_aligned"])

    def test_defensive_regime_no_adjustment(self) -> None:
        sig_l, sig_r = self._make_sigs()
        base = {"0050.TW": 0.6, "00631L.TW": 0.2, "cash": 0.2}
        summary = ncf_overlay_summary(sig_l, sig_r, base, "group_a_plus_defensive")
        self.assertEqual(summary["adjusted_golden1_weights"], base)
        self.assertIn("n/a", summary["action"])

    def test_golden1_with_bearish_signals_reduces_00631l(self) -> None:
        sig_l, sig_r = self._make_sigs()
        base = {"0050.TW": 0.6, "00631L.TW": 0.2, "cash": 0.2}
        summary = ncf_overlay_summary(sig_l, sig_r, base, "golden1")
        adj = summary["adjusted_golden1_weights"]
        self.assertLess(adj["00631L.TW"], 0.20)
        self.assertGreater(summary["00631l_reduction"], 0.0)


class NCFGovernanceTests(unittest.TestCase):
    def test_a2113_registered_in_governance(self) -> None:
        self.assertIn(A2113_ID, SUPPORTED_STRATEGIES)

    def test_a2113_points_to_correct_runner(self) -> None:
        self.assertEqual(SUPPORTED_STRATEGIES[A2113_ID], "group_a_plus.runners.a2113")

    def test_a2113_id_constant(self) -> None:
        self.assertEqual(A2113_ID, "a2113_a2111_ncf_overlay")


class NCFPathResolutionTests(unittest.TestCase):
    def test_explicit_path_returned_when_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "ncf_00631l_test.json"
            p.write_text("{}", encoding="utf-8")
            result = _resolve_ncf_path(str(p), "00631l")
            self.assertEqual(result, p)

    def test_explicit_nonexistent_returns_none(self) -> None:
        result = _resolve_ncf_path("/nonexistent/path/ncf.json", "00631l")
        self.assertIsNone(result)


class NCFTailScoreLoadTests(unittest.TestCase):
    """Test that load_ncf_signal extracts v5+ tail reward/risk fields."""

    def _write_ncf_with_tail(self, tmp_dir: str, ticker: str) -> Path:
        payload = _make_ncf_json(ticker, "DOWN", 0.38, 0.66)
        payload["tail_reward_risk_score"] = -0.3828
        payload["forward_drawdown_risk"] = {
            "available": True,
            "horizon_days": 20,
            "threshold": 0.05,
            "probability": 0.6297,
        }
        payload["forward_upside_reward"] = {
            "available": True,
            "horizon_days": 20,
            "threshold": 0.05,
            "probability": 0.2470,
        }
        path = Path(tmp_dir) / f"ncf_{ticker}_tail.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _write_ncf_without_tail(self, tmp_dir: str, ticker: str) -> Path:
        payload = _make_ncf_json(ticker, "UP", 0.65, 0.55)
        path = Path(tmp_dir) / f"ncf_{ticker}_notail.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_tail_score_extracted_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_ncf_with_tail(tmp, "00631L.TW")
            sig = load_ncf_signal(p)
        self.assertAlmostEqual(sig["tail_reward_risk_score"], -0.3828, places=4)
        self.assertAlmostEqual(sig["prob_fwd_mdd_gt5_h20"], 0.6297, places=4)
        self.assertAlmostEqual(sig["prob_fwd_gain_gt5_h20"], 0.2470, places=4)

    def test_tail_score_none_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_ncf_without_tail(tmp, "00631L.TW")
            sig = load_ncf_signal(p)
        self.assertIsNone(sig["tail_reward_risk_score"])
        self.assertIsNone(sig["prob_fwd_mdd_gt5_h20"])
        self.assertIsNone(sig["prob_fwd_gain_gt5_h20"])


class NCFMaGapSuppressionTests(unittest.TestCase):
    """Test bull-trend suppression of ncf_downside_signal."""

    def _bearish_sigs(self) -> tuple[dict, dict]:
        return (
            {"ticker": "00631L.TW", "calibrated_prob_up": 0.25, "confidence": 0.8, "direction": "DOWN"},
            {"ticker": "00632R.TW", "calibrated_prob_up": 0.75, "confidence": 0.8, "direction": "UP"},
        )

    def test_no_ma_gap_no_suppression(self) -> None:
        l, r = self._bearish_sigs()
        raw = ncf_downside_signal(l, r)
        gated = ncf_downside_signal(l, r, ma_gap=None)
        self.assertAlmostEqual(raw, gated, places=6)

    def test_ma_gap_below_threshold_no_suppression(self) -> None:
        l, r = self._bearish_sigs()
        raw = ncf_downside_signal(l, r)
        gated = ncf_downside_signal(l, r, ma_gap=0.10, ma_gap_bull_threshold=0.15)
        self.assertAlmostEqual(raw, gated, places=6)

    def test_ma_gap_above_threshold_reduces_signal(self) -> None:
        l, r = self._bearish_sigs()
        raw = ncf_downside_signal(l, r)
        gated = ncf_downside_signal(l, r, ma_gap=0.20, ma_gap_bull_threshold=0.15)
        self.assertLess(gated, raw)

    def test_ma_gap_at_double_threshold_zeroes_signal(self) -> None:
        l, r = self._bearish_sigs()
        gated = ncf_downside_signal(l, r, ma_gap=0.30, ma_gap_bull_threshold=0.15)
        self.assertAlmostEqual(gated, 0.0, places=6)

    def test_upside_signal_unaffected_by_ma_gap(self) -> None:
        """ncf_upside_signal has no ma_gap param — always returns raw value."""
        l, r = self._bearish_sigs()
        up = ncf_upside_signal(l, r)
        self.assertGreaterEqual(up, 0.0)
        self.assertLessEqual(up, 1.0)


class NCFRegimeGatedSignalTests(unittest.TestCase):
    """Test ncf_regime_gated_signal composite output."""

    def _sigs(self, prob_l: float, prob_r: float, conf: float = 0.8) -> tuple[dict, dict]:
        return (
            {"ticker": "00631L.TW", "calibrated_prob_up": prob_l, "confidence": conf,
             "direction": "DOWN", "tail_reward_risk_score": -0.38},
            {"ticker": "00632R.TW", "calibrated_prob_up": prob_r, "confidence": conf,
             "direction": "UP", "tail_reward_risk_score": 0.16},
        )

    def test_gated_equals_raw_when_no_ma_gap(self) -> None:
        l, r = self._sigs(0.25, 0.75)
        result = ncf_regime_gated_signal(l, r)
        self.assertAlmostEqual(result["gated_downside_signal"], result["raw_downside_signal"], places=6)
        self.assertFalse(result["bull_suppression_applied"])

    def test_suppression_applied_in_strong_bull(self) -> None:
        l, r = self._sigs(0.25, 0.75)
        result = ncf_regime_gated_signal(l, r, ma_gap=0.20, ma_gap_bull_threshold=0.15)
        self.assertTrue(result["bull_suppression_applied"])
        self.assertLess(result["gated_downside_signal"], result["raw_downside_signal"])

    def test_full_suppression_at_double_threshold(self) -> None:
        l, r = self._sigs(0.25, 0.75)
        result = ncf_regime_gated_signal(l, r, ma_gap=0.30, ma_gap_bull_threshold=0.15)
        self.assertAlmostEqual(result["gated_downside_signal"], 0.0, places=6)
        self.assertAlmostEqual(result["bull_suppression"], 1.0, places=6)

    def test_tail_scores_passed_through(self) -> None:
        l, r = self._sigs(0.30, 0.70)
        result = ncf_regime_gated_signal(l, r)
        self.assertAlmostEqual(result["tail_score_631l"], -0.38, places=4)
        self.assertAlmostEqual(result["tail_score_632r"], 0.16, places=4)

    def test_tail_scores_none_when_absent(self) -> None:
        l = {"ticker": "00631L.TW", "calibrated_prob_up": 0.3, "confidence": 0.7, "direction": "DOWN"}
        r = {"ticker": "00632R.TW", "calibrated_prob_up": 0.7, "confidence": 0.7, "direction": "UP"}
        result = ncf_regime_gated_signal(l, r)
        self.assertIsNone(result["tail_score_631l"])
        self.assertIsNone(result["tail_score_632r"])

    def test_result_keys_present(self) -> None:
        l, r = self._sigs(0.4, 0.6)
        result = ncf_regime_gated_signal(l, r, ma_gap=0.10)
        for key in ["raw_downside_signal", "raw_upside_signal", "gated_downside_signal",
                    "directional_downside_signal", "tail_downside_signal",
                    "ma_gap", "bull_suppression", "bull_suppression_applied",
                    "tail_score_631l", "tail_score_632r"]:
            self.assertIn(key, result)


class NCFOverlaySummaryMaGapTests(unittest.TestCase):
    """Test that ncf_overlay_summary passes ma_gap through and uses gated signal."""

    BASE = {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20}

    def _sigs(self) -> tuple[dict, dict]:
        return (
            {"ticker": "00631L.TW", "date": "2026-06-26", "direction": "DOWN",
             "calibrated_prob_up": 0.25, "confidence": 0.8, "votes_up": 1,
             "weighted_return": -0.01, "raw_combined_prob_up": 0.28,
             "tail_reward_risk_score": -0.38, "prob_fwd_mdd_gt5_h20": 0.63,
             "prob_fwd_gain_gt5_h20": 0.25},
            {"ticker": "00632R.TW", "date": "2026-06-26", "direction": "UP",
             "calibrated_prob_up": 0.75, "confidence": 0.8, "votes_up": 2,
             "weighted_return": 0.01, "raw_combined_prob_up": 0.72,
             "tail_reward_risk_score": 0.16, "prob_fwd_mdd_gt5_h20": 0.38,
             "prob_fwd_gain_gt5_h20": 0.54},
        )

    def test_summary_includes_gated_fields(self) -> None:
        l, r = self._sigs()
        summary = ncf_overlay_summary(l, r, self.BASE, "golden1")
        for key in ["gated_downside_signal", "bull_suppression", "bull_suppression_applied", "ma_gap"]:
            self.assertIn(key, summary)

    def test_summary_includes_advisory_dynamic_and_consistency_fields(self) -> None:
        l, r = self._sigs()
        summary = ncf_overlay_summary(l, r, self.BASE, "golden1")

        self.assertIn("dynamic_horizon_00631l", summary)
        self.assertIn("dynamic_horizon_00632r", summary)
        self.assertIn("cross_ticker_consistency", summary)
        self.assertIn("market_direction", summary["cross_ticker_consistency"])
        self.assertIn("conflict_flag", summary["cross_ticker_consistency"])

    def test_advisory_fields_do_not_change_existing_reduction_logic(self) -> None:
        l, r = self._sigs()
        summary = ncf_overlay_summary(l, r, self.BASE, "golden1")
        expected = adjust_golden1_weights(self.BASE, summary["gated_downside_signal"])

        self.assertEqual(summary["adjusted_golden1_weights"], expected)

    def test_strong_bull_suppresses_reduction(self) -> None:
        l, r = self._sigs()
        no_gap = ncf_overlay_summary(l, r, self.BASE, "golden1")
        bull = ncf_overlay_summary(l, r, self.BASE, "golden1", ma_gap=0.30, ma_gap_bull_threshold=0.15)
        self.assertGreater(no_gap["00631l_reduction"], bull["00631l_reduction"])
        self.assertAlmostEqual(bull["00631l_reduction"], 0.0, places=6)

    def test_summary_tail_fields_in_ncf_blocks(self) -> None:
        l, r = self._sigs()
        summary = ncf_overlay_summary(l, r, self.BASE, "golden1")
        self.assertAlmostEqual(summary["ncf_00631l"]["tail_reward_risk_score"], -0.38, places=4)
        self.assertAlmostEqual(summary["ncf_00632r"]["tail_reward_risk_score"], 0.16, places=4)
        self.assertAlmostEqual(summary["ncf_00631l"]["prob_fwd_mdd_gt5_h20"], 0.63, places=4)


if __name__ == "__main__":
    unittest.main()
