#!/usr/bin/env python3
"""Unit tests for NCF integration into Group A+ strategy (A21.13)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from group_a_plus.integrations.ncf import (
    adjust_golden1_weights,
    load_ncf_signal,
    ncf_downside_signal,
    ncf_overlay_summary,
    ncf_regime_gated_signal,
    ncf_upside_signal,
)
from group_a_plus.governance.latest import SUPPORTED_STRATEGIES
from group_a_plus.runners.a2113 import A2113_ID, _resolve_ncf_path


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
        "horizons": {},
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
