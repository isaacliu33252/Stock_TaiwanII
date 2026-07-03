#!/usr/bin/env python3
"""Tests for the deterministic GroupA+ strategy bench signature."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.evaluate.group_a_plus_strategy_signature import build_strategy_signature


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_standard(path: Path, data: dict, timestamp: str = "2026-06-30T10:00:00") -> None:
    _write_json(
        path,
        {
            "success": True,
            "data": data,
            "metadata": {
                "script": "test",
                "timestamp": timestamp,
                "execution_time_ms": 1,
            },
            "error": None,
        },
    )


def _fixture_files(tmp_path: Path, weight_00631l: float = 0.05, timestamp: str = "2026-06-30T10:00:00") -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    live_signal = tmp_path / "live.json"
    runner = tmp_path / "runner.json"
    ncf = tmp_path / "ncf.json"
    panel = tmp_path / "panel.csv"
    manifest = tmp_path / "strategy.json"

    _write_standard(
        live_signal,
        {
            "signal_version": 2,
            "generated_at": "2026-06-30T09:00:00",
            "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
            "strategy_status": "active",
            "requested_as_of_date": "2026-06-30",
            "actual_data_date": "2026-06-29",
            "business_stale_days": 1,
            "execution_allowed": True,
            "execution_guard_reasons": [],
            "base_regime": "golden1",
            "execution_regime": "ncf_late_bull_hedge",
            "regime_reason": "active strategy regime",
            "last_transition_date": "2026-06-29",
            "strategy_transition_today": True,
            "action": "rebalance_to_target",
            "target_weights": {
                "0050.TW": 0.75,
                "00631L.TW": weight_00631l,
                "cash": 0.20,
            },
            "latest_features": {"ma_gap": 0.19, "total_risk_score": 9},
            "execution_risk": {"score": 0.26, "level": "low"},
            "ncf_live_overlay": {
                "a2118_late_bull_hard_overlay_applied": True,
                "a2118_late_bull_overlay_reason": "panel_trigger",
                "a2118_late_bull_hold_active": False,
                "a2118_h20_prob": 0.27,
                "a2118_h5_prob": 0.36,
                "a2118_confidence": 0.66,
                "files": {"00631L.TW": "/volatile/path.json"},
            },
            "factor_lens_gate": {"status": "available", "all_key_factors_pass": True},
        },
        timestamp=timestamp,
    )
    _write_standard(
        runner,
        {
            "experiment": "group_a_plus_a2118_ncf_late_bull_deleverage",
            "strategy": "a2118_a2111_ncf_late_bull_deleverage",
            "status": "active",
            "backtest_mode": "ncf_late_bull_regime_overlay",
            "window": {"start": "2025-01-02", "end": "2026-06-18", "rows": 352},
            "metrics": {"sharpe_ratio": 2.6, "max_drawdown": -0.13},
            "execution": {"rebalance_count": 4, "late_bull_trigger_days": 0},
        },
        timestamp=timestamp,
    )
    _write_json(
        ncf,
        {
            "ticker": "00631L.TW",
            "generated_at": "2026-06-30T09:00:00",
            "last_close_date": "2026-06-29",
            "last_close": 36.28,
            "current_regime": "BULL",
            "data_freshness": {"status": "ok"},
            "labeling_mode": "auto",
            "horizons": {
                "1": {"classification": {"probability_up": 0.46, "direction": "NEUTRAL", "val_auc": 0.57}, "regression": {"predicted_return": -0.01}},
                "5": {"classification": {"probability_up": 0.36, "direction": "DOWN", "val_auc": 0.68}, "regression": {"predicted_return": -0.02}},
                "20": {"classification": {"probability_up": 0.27, "direction": "DOWN", "val_auc": 0.66}, "regression": {"predicted_return": -0.03}},
            },
            "horizon_ensemble": {"calibrated_probability_up": 0.38, "confidence": 0.66},
            "forward_drawdown_risk": {"probability": 0.54},
            "forward_gain_opportunity": {"probability": 0.37},
        },
    )
    pd.DataFrame(
        [
            {
                "date": "2026-06-29",
                "prob_up_h1": 0.46,
                "prob_up_h5": 0.36,
                "prob_up_h20": 0.27,
                "h20_prob_up": 0.27,
                "confidence": 0.66,
                "is_live": True,
            }
        ]
    ).to_csv(panel, index=False)
    _write_json(
        manifest,
        {
            "schema_version": 2,
            "active_strategy": {
                "id": "a2118_a2111_ncf_late_bull_deleverage",
                "status": "active",
                "runner_params": {"h20_max": 0.33, "conf_min": 0.55},
            },
        },
    )
    return {
        "live_signal_path": live_signal,
        "runner_path": runner,
        "ncf_path": ncf,
        "panel_path": panel,
        "strategy_manifest_path": manifest,
    }


def test_signature_is_stable_when_only_volatile_timestamps_change(tmp_path: Path) -> None:
    paths = _fixture_files(tmp_path, timestamp="2026-06-30T10:00:00")
    first = build_strategy_signature(**paths)

    paths = _fixture_files(tmp_path, timestamp="2026-06-30T11:00:00")
    second = build_strategy_signature(**paths)

    assert first["signature"] == second["signature"]


def test_signature_changes_when_target_weight_changes(tmp_path: Path) -> None:
    first = build_strategy_signature(**_fixture_files(tmp_path / "a", weight_00631l=0.05))
    second = build_strategy_signature(**_fixture_files(tmp_path / "b", weight_00631l=0.10))

    assert first["signature"] != second["signature"]
