#!/usr/bin/env python3
"""Regression checks for the schema-v2 GroupA+ latest manifest."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import TICKERS
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY, resolve_latest
from group_a_plus.integrations.finbert import load_finbert_daily_snapshot
from group_a_plus.operations.daily_signal import (
    _apply_ncf_live_overlay,
    _build_signal_alerts,
    _execution_risk_assessment,
    _source_freshness,
)
from group_a_plus.runners.a213 import A213_ID, run_a213
from group_a_plus.runners.a214 import A214_ID, run_a214
from group_a_plus.runners.a2111 import A2111_ID, _resolve_golden_signal_path
from group_a_plus.runners.a2112 import A2112_ID
from group_a_plus.runners.a2118 import A2118_ID
from group_a_plus.runners.a2119 import A2119_ID, _apply_finbert_gate
from group_a_plus.runners.a2120 import A2120_ID
from group_a_plus.runners.latest import run_latest


class LatestStrategyTests(unittest.TestCase):
    def test_repository_manifest_activates_a2118(self) -> None:
        manifest = resolve_latest(DEFAULT_LATEST_STRATEGY)
        active = manifest["active_strategy"]
        runner_params = active["runner_params"]

        self.assertEqual(A2118_ID, active["id"])
        self.assertEqual("group_a_plus.runners.a2118", active["runner"])
        self.assertEqual("results/ncf_00631l_panel_latest_20260630.csv", runner_params["ncf_panel_631l_path"])
        self.assertAlmostEqual(0.33, runner_params["h20_max"], places=4)
        self.assertAlmostEqual(0.55, runner_params["conf_min"], places=4)
        self.assertAlmostEqual(0.55, runner_params["h5_reentry_min"], places=4)
        self.assertEqual(A2111_ID, active["promoted_from"])
        self.assertNotEqual(A2111_ID, A213_ID)
        self.assertNotEqual(A2111_ID, A2112_ID)
        self.assertTrue(manifest["compatibility"]["legacy_pointer_unchanged"])

    def test_unknown_strategy_is_rejected(self) -> None:
        manifest = {
            "schema_version": 2,
            "active_strategy": {"id": "unknown", "runner": "unknown.runner"},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "strategy.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Unsupported active strategy"):
                resolve_latest(path)

    def test_a2119_finbert_gate_is_supported(self) -> None:
        manifest = {
            "schema_version": 2,
            "active_strategy": {"id": A2119_ID, "runner": "group_a_plus.runners.a2119"},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "strategy.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            resolved = resolve_latest(path)

        self.assertEqual(A2119_ID, resolved["active_strategy"]["id"])

    def test_a2120_rally_aware_candidate_is_supported(self) -> None:
        manifest = {
            "schema_version": 2,
            "active_strategy": {"id": A2120_ID, "runner": "group_a_plus.runners.a2120"},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "strategy.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            resolved = resolve_latest(path)

        self.assertEqual(A2120_ID, resolved["active_strategy"]["id"])

    @patch("group_a_plus.runners.a2119.run_a2119")
    def test_latest_runner_dispatches_manifest_runner_params(self, runner) -> None:
        runner.return_value = ({"status": "candidate_ok"}, pd.DataFrame({"value": [1.0]}))
        manifest = {
            "schema_version": 2,
            "active_strategy": {
                "id": A2119_ID,
                "runner": "group_a_plus.runners.a2119",
                "status": "active",
                "runner_params": {
                    "finbert_on_consecutive": 2,
                    "finbert_off_consecutive": 3,
                },
            },
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "strategy.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            report, frame = run_latest(
                "2025-01-02",
                "2026-06-18",
                1_000_000,
                Path("test.db"),
                path,
            )

        runner.assert_called_once_with(
            "2025-01-02",
            "2026-06-18",
            1_000_000,
            Path("test.db"),
            finbert_on_consecutive=2,
            finbert_off_consecutive=3,
        )
        self.assertEqual(A2119_ID, report["active_strategy_id"])
        self.assertEqual("candidate_ok", report["candidate_status"])
        self.assertEqual("active", report["status"])
        self.assertEqual([1.0], frame["value"].tolist())

    def test_a2119_finbert_gate_forces_defensive_near_boundary(self) -> None:
        idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
        regime = pd.Series(["golden1", "golden1", "golden1"], index=idx)
        ma_gap = pd.Series([0.02, 0.02, 0.10], index=idx)
        risk = pd.Series([0.70, 0.70, 0.30], index=idx)

        modified, info = _apply_finbert_gate(
            regime,
            ma_gap,
            risk,
            pd.Series([-0.01, -0.01, -0.01], index=idx),
            risk_on_threshold=0.65,
            risk_off_threshold=0.45,
            ma_gap_max=0.05,
            ma_gap_trigger_max=0.03,
            exit_momentum_max=0.0,
            on_consecutive=2,
            off_consecutive=1,
        )

        self.assertEqual("golden1", modified.iloc[0])
        self.assertEqual("group_a_plus_defensive", modified.iloc[1])
        self.assertEqual("golden1", modified.iloc[2])
        self.assertEqual(1, info["finbert_gate_activations"])

    def test_a2119_finbert_gate_respects_ma_gap_trigger_floor(self) -> None:
        idx = pd.to_datetime(["2026-01-02", "2026-01-05"])
        regime = pd.Series(["golden1", "golden1"], index=idx)
        ma_gap = pd.Series([-0.005, -0.005], index=idx)
        risk = pd.Series([0.70, 0.70], index=idx)
        momentum = pd.Series([-0.02, -0.02], index=idx)

        modified, info = _apply_finbert_gate(
            regime,
            ma_gap,
            risk,
            momentum,
            risk_on_threshold=0.65,
            risk_off_threshold=0.45,
            ma_gap_max=0.05,
            ma_gap_trigger_max=-0.015,
            exit_momentum_max=0.0,
            on_consecutive=1,
            off_consecutive=1,
        )

        self.assertEqual(["golden1", "golden1"], modified.tolist())
        self.assertEqual(0, info["finbert_gate_activations"])

    def test_a2119_finbert_gate_uses_entry_quality_only_for_entry(self) -> None:
        idx = pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"])
        regime = pd.Series(["golden1", "golden1", "golden1"], index=idx)
        ma_gap = pd.Series([-0.03, -0.03, -0.03], index=idx)
        risk = pd.Series([0.70, 0.40, 0.40], index=idx)
        momentum = pd.Series([-0.02, -0.02, -0.02], index=idx)
        quality = pd.Series([True, False, False], index=idx)

        modified, info = _apply_finbert_gate(
            regime,
            ma_gap,
            risk,
            momentum,
            quality,
            risk_on_threshold=0.65,
            risk_off_threshold=0.45,
            ma_gap_max=0.05,
            ma_gap_trigger_max=-0.015,
            exit_momentum_max=0.0,
            quality_risk_override_threshold=0.75,
            on_consecutive=1,
            off_consecutive=2,
        )

        self.assertEqual(
            ["group_a_plus_defensive", "group_a_plus_defensive", "golden1"],
            modified.tolist(),
        )
        self.assertEqual(1, info["finbert_gate_activations"])

    @patch("group_a_plus.runners.a213._run_recovery_strategy")
    def test_a213_parameters_are_immutable(self, core) -> None:
        core.return_value = ({}, None)

        run_a213("2025-01-02", "2026-06-18", 1_000_000, Path("test.db"))

        kwargs = core.call_args.kwargs
        self.assertEqual(kwargs["strategy_id"], "a213_cash30_recovery_ramp")
        self.assertEqual(kwargs["basket_name"], "cash30")
        self.assertEqual(kwargs["ma_window"], 75)

    @patch("group_a_plus.runners.a214._run_recovery_strategy")
    def test_a214_parameters_are_isolated(self, core) -> None:
        core.return_value = ({}, None)

        run_a214("2025-01-02", "2026-06-18", 1_000_000, Path("test.db"))

        kwargs = core.call_args.kwargs
        self.assertEqual(kwargs["strategy_id"], "a214_bond30c30_mw60")
        self.assertEqual(kwargs["basket_name"], "bond30_cash30")
        self.assertEqual(kwargs["ma_window"], 60)

    def test_daily_signal_uses_common_actual_date_prices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.duckdb"
            con = duckdb.connect(str(db_path))
            try:
                con.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
                for ticker in TICKERS:
                    con.execute(
                        "INSERT INTO ohlcv VALUES (?, ?, ?)",
                        [ticker, "2026-06-25", 100.0],
                    )
                con.execute(
                    "UPDATE ohlcv SET close = ? WHERE ticker = ? AND dt = ?",
                    [27.37, "00679B.TWO", "2026-06-25"],
                )
                con.execute(
                    "INSERT INTO ohlcv VALUES (?, ?, ?)",
                    ["00679B.TWO", "2026-06-26", 27.44],
                )
            finally:
                con.close()

            freshness = _source_freshness(
                db_path,
                pd.Timestamp("2026-06-29"),
                pd.Timestamp("2026-06-25"),
            )

        self.assertEqual("2026-06-25", freshness["price_data_as_of"])
        self.assertEqual("2026-06-25", freshness["ohlcv_by_ticker"]["00679B.TWO"])
        self.assertEqual(27.37, freshness["latest_prices"]["00679B.TWO"])

    def test_securities_lending_is_soft_freshness_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "prices.duckdb"
            con = duckdb.connect(str(db_path))
            try:
                con.execute("CREATE TABLE ohlcv (ticker VARCHAR, dt DATE, close DOUBLE)")
                for ticker in TICKERS:
                    con.execute(
                        "INSERT INTO ohlcv VALUES (?, ?, ?)",
                        [ticker, "2026-06-25", 100.0],
                    )
            finally:
                con.close()

            freshness = _source_freshness(
                db_path,
                pd.Timestamp("2026-06-29"),
                pd.Timestamp("2026-06-25"),
            )

        lending = freshness["optional_sources"]["securities_lending_0050"]
        self.assertEqual("soft", lending["severity"])
        self.assertEqual("warn", lending["status"])

    def test_a2111_uses_latest_group_a_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            results = root / "results"
            results.mkdir()
            older = results / "group_a_combined_live_latest.json"
            newer = results / "signal_group_a_20260627_211552.json"
            older.write_text("{}", encoding="utf-8")
            newer.write_text("{}", encoding="utf-8")
            older_ts = 1_700_000_000
            newer_ts = older_ts + 10
            os.utime(older, (older_ts, older_ts))
            os.utime(newer, (newer_ts, newer_ts))

            with patch("group_a_plus.runners.a2111.PROJECT_ROOT", root), patch(
                "group_a_plus.runners.a2111.LATEST_GROUP_A_SIGNAL",
                older,
            ):
                self.assertEqual(newer.resolve(), _resolve_golden_signal_path())

    def test_daily_signal_ncf_overlay_reduces_00631l_to_cash(self) -> None:
        def ncf_payload(ticker: str, direction: str, prob: float, conf: float) -> dict:
            return {
                "ticker": ticker,
                "last_close_date": "2026-06-25",
                "horizon_ensemble": {
                    "direction": direction,
                    "combined_probability_up": prob,
                    "calibrated_probability_up": prob,
                    "confidence": conf,
                    "weighted_return": -0.01,
                    "votes_up": 0,
                },
                "horizons": {},
            }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            results = root / "results"
            results.mkdir()
            (results / "ncf_00631l_latest_20260627.json").write_text(
                json.dumps(ncf_payload("00631L.TW", "DOWN", 0.35, 0.8)),
                encoding="utf-8",
            )
            (results / "ncf_00632r_latest_20260627.json").write_text(
                json.dumps(ncf_payload("00632R.TW", "UP", 0.65, 0.8)),
                encoding="utf-8",
            )

            weights, overlay, warnings = _apply_ncf_live_overlay(
                {"0050.TW": 0.7, "00631L.TW": 0.1, "00632R.TW": 0.0, "00679B.TWO": 0.0, "cash": 0.2},
                "golden1",
                pd.Timestamp("2026-06-25"),
                pd.Series({"ma_gap": 0.2}),
                root,
            )

        self.assertEqual([], warnings)
        self.assertEqual("applied", overlay["status"])
        self.assertLess(weights["00631L.TW"], 0.1)
        self.assertGreater(weights["cash"], 0.2)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)

    def test_execution_risk_assessment_levels(self) -> None:
        low = _execution_risk_assessment(
            execution_allowed=True,
            business_stale=0,
            calendar_stale=0,
            optional_warnings=[],
            target_weights={"00631L.TW": 0.0},
            latest_features={"total_risk_score": 0},
            ncf_live_overlay={"gated_downside_signal": 0.0, "tail_downside_signal": 0.0},
            finbert_sentiment={"risk_score": 0.0},
        )
        high = _execution_risk_assessment(
            execution_allowed=False,
            business_stale=4,
            calendar_stale=7,
            optional_warnings=["x"],
            target_weights={"00631L.TW": 0.2},
            latest_features={"total_risk_score": 8},
            ncf_live_overlay={"gated_downside_signal": 0.5, "tail_downside_signal": 0.5},
            finbert_sentiment={"risk_score": 1.0},
        )

        self.assertEqual("low", low["level"])
        self.assertEqual("high", high["level"])
        self.assertGreater(high["score"], low["score"])

    def test_finbert_snapshot_feeds_execution_risk_component(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "finbert_market_sentiment_daily.csv"
            pd.DataFrame(
                [
                    {
                        "date": "2026-06-25",
                        "finbert_sentiment_score": -0.4,
                        "finbert_negative_ratio": 0.5,
                        "finbert_positive_ratio": 0.1,
                        "finbert_neutral_ratio": 0.4,
                        "finbert_confidence": 0.8,
                        "finbert_news_intensity": 2.0,
                    }
                ]
            ).to_csv(path, index=False)

            snapshot = load_finbert_daily_snapshot("2026-06-29", "2026-06-25", path=path)
            risk = _execution_risk_assessment(
                execution_allowed=True,
                business_stale=0,
                calendar_stale=0,
                optional_warnings=[],
                target_weights={"00631L.TW": 0.0},
                latest_features={"total_risk_score": 0},
                ncf_live_overlay={"gated_downside_signal": 0.0, "tail_downside_signal": 0.0},
                finbert_sentiment=snapshot,
            )

        self.assertEqual("ok", snapshot["status"])
        self.assertGreater(snapshot["risk_score"], 0.0)
        self.assertEqual(1.0, snapshot["freshness_scale"])
        self.assertGreater(risk["components"]["finbert_sentiment_risk"], 0.0)

    def test_finbert_snapshot_discounts_stale_news(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "finbert_market_sentiment_daily.csv"
            pd.DataFrame(
                [
                    {
                        "date": "2026-06-08",
                        "finbert_sentiment_score": -0.4,
                        "finbert_negative_ratio": 0.5,
                        "finbert_positive_ratio": 0.1,
                        "finbert_neutral_ratio": 0.4,
                        "finbert_confidence": 0.8,
                        "finbert_news_intensity": 3.0,
                    }
                ]
            ).to_csv(path, index=False)

            snapshot = load_finbert_daily_snapshot("2026-06-29", "2026-06-25", path=path)

        self.assertEqual("ok", snapshot["status"])
        self.assertEqual(17, snapshot["actual_calendar_stale_days"])
        self.assertLess(snapshot["freshness_scale"], 1.0)
        self.assertLess(snapshot["risk_score"], snapshot["raw_risk_score"])

    def test_signal_alerts_include_stable_cooldown_keys(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2111_tight_entry_bond30c30",
            actual_date=pd.Timestamp("2026-06-25"),
            execution_allowed=False,
            execution_regime="group_a_plus_defensive",
            changed_today=True,
            execution_risk={"level": "high", "score": 0.75},
            latest_features={"total_risk_score": 7},
            finbert_sentiment={"risk_score": 0.6},
        )

        alert_types = {alert["type"] for alert in alerts}
        self.assertIn("execution_blocked", alert_types)
        self.assertIn("regime_transition", alert_types)
        self.assertIn("finbert_sentiment_risk", alert_types)
        self.assertIn("total_risk_score", alert_types)
        total_risk_alert = next(alert for alert in alerts if alert["type"] == "total_risk_score")
        self.assertEqual("medium", total_risk_alert["level"])
        self.assertTrue(
            all(str(alert["cooldown_key"]).startswith("a2111_tight_entry_bond30c30:2026-06-25:") for alert in alerts)
        )
        self.assertTrue(all(alert["cooldown_minutes"] == 5 for alert in alerts))

    def test_signal_alerts_raise_high_for_extreme_total_risk(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2118_a2111_ncf_late_bull_deleverage",
            actual_date=pd.Timestamp("2026-06-30"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.25},
            latest_features={"total_risk_score": 10},
            finbert_sentiment={"risk_score": 0.1},
        )

        total_risk_alert = next(alert for alert in alerts if alert["type"] == "total_risk_score")
        self.assertEqual("high", total_risk_alert["level"])

    def test_signal_alerts_include_alignment_and_factor_freshness(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2118_a2111_ncf_late_bull_deleverage",
            actual_date=pd.Timestamp("2026-06-30"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.25},
            latest_features={"total_risk_score": 1},
            finbert_sentiment={"risk_score": 0.1},
            factor_lens_gate={"status": "available", "report_generated_at": "2026-06-29T17:09:25"},
            ncf_live_overlay={
                "bearish_high_risk_trim_applied": True,
                "bearish_high_risk_trim_reason": "total_risk_score=10, alignment=wide_divergence, dominant=bearish",
            },
            signal_alignment={"alignment": "wide_divergence", "dominant_direction": "bearish"},
        )

        alert_types = {alert["type"] for alert in alerts}
        self.assertIn("signal_wide_divergence", alert_types)
        self.assertIn("factor_lens_stale", alert_types)
        self.assertIn("bearish_high_risk_trim", alert_types)

    def test_signal_alerts_flag_stale_ncf_panel(self) -> None:
        """M3 (2026-07-02 Fable 5 audit): a panel pinned in strategy.json
        runner_params stops advancing its mtime, so warn on content age
        (panel_631l_last_date) instead."""
        alerts = _build_signal_alerts(
            strategy_id="a2118_a2111_ncf_late_bull_deleverage",
            actual_date=pd.Timestamp("2026-07-15"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.25},
            latest_features={"total_risk_score": 1},
            finbert_sentiment={"risk_score": 0.1},
            ncf_panel_coverage={"panel_631l_last_date": "2026-06-30"},
        )

        panel_alert = next(alert for alert in alerts if alert["type"] == "ncf_panel_stale")
        self.assertEqual("high", panel_alert["level"])

    def test_signal_alerts_ignore_fresh_ncf_panel(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2118_a2111_ncf_late_bull_deleverage",
            actual_date=pd.Timestamp("2026-06-30"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.25},
            latest_features={"total_risk_score": 1},
            finbert_sentiment={"risk_score": 0.1},
            ncf_panel_coverage={"panel_631l_last_date": "2026-06-29"},
        )

        alert_types = {alert["type"] for alert in alerts}
        self.assertNotIn("ncf_panel_stale", alert_types)

    def test_signal_alerts_stay_empty_for_low_risk_hold(self) -> None:
        alerts = _build_signal_alerts(
            strategy_id="a2111_tight_entry_bond30c30",
            actual_date=pd.Timestamp("2026-06-25"),
            execution_allowed=True,
            execution_regime="golden1",
            changed_today=False,
            execution_risk={"level": "low", "score": 0.05},
            latest_features={"total_risk_score": 1},
            finbert_sentiment={"risk_score": 0.1},
        )

        self.assertEqual([], alerts)


if __name__ == "__main__":
    unittest.main()
