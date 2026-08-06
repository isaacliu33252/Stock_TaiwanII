from __future__ import annotations

import json
import subprocess

import pandas as pd

from group_a_plus.dashboard.update_dashboard import infer_price_freshness_path, refresh_fubon_snapshot, update_dashboard


def _write_inputs(tmp_path):
    signal_path = tmp_path / "live_signal.json"
    holdings_path = tmp_path / "holdings.json"
    freshness_dir = tmp_path / "results"
    freshness_dir.mkdir()
    parquet_path = tmp_path / "0056.parquet"
    pd.DataFrame(
        [
            {"date": "2026-07-27", "close": 50.0, "adj close": 50.0},
        ]
    ).to_parquet(parquet_path)
    freshness_path = freshness_dir / "ohlcv_freshness_20260727.json"
    freshness_path.write_text(
        json.dumps(
            {
                "target_date": "2026-07-27",
                "tickers": [
                    {
                        "ticker": "0056.TW",
                        "target_date": "2026-07-27",
                        "raw_cache": {"path": str(parquet_path), "exists": True},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    signal_path.write_text(
        json.dumps(
            {
                "success": True,
                "data": {
                    "strategy_id": "a2118",
                    "strategy_status": "active",
                    "generated_at": "2026-07-28T07:13:10",
                    "actual_data_date": "2026-07-27",
                    "requested_as_of_date": "2026-07-27",
                    "execution_allowed": True,
                    "target_weights": {"0056.TW": 0.0, "cash": 1.0},
                    "latest_prices": {},
                },
            }
        ),
        encoding="utf-8",
    )
    holdings_path.write_text(
        json.dumps({"current_shares": {"0056.TW": 1000}, "cash": 100000}),
        encoding="utf-8",
    )
    return signal_path, holdings_path, freshness_path


def test_infer_price_freshness_path_uses_signal_actual_data_date(tmp_path) -> None:
    signal_path, _, _ = _write_inputs(tmp_path)

    assert infer_price_freshness_path(signal_path, tmp_path / "results").name == "ohlcv_freshness_20260727.json"


def test_update_dashboard_builds_private_outputs_without_refreshing_fubon(tmp_path) -> None:
    signal_path, holdings_path, freshness_path = _write_inputs(tmp_path)
    rebalance_path = tmp_path / "rebalance_plan_latest.json"
    dashboard_path = tmp_path / "dashboard.html"

    result = update_dashboard(
        signal_path=signal_path,
        holdings_path=holdings_path,
        price_freshness_path=freshness_path,
        rebalance_path=rebalance_path,
        dashboard_path=dashboard_path,
    )

    assert result["refresh_fubon"] is False
    assert result["manual_approval_required"] is True
    assert rebalance_path.exists()
    assert dashboard_path.exists()
    assert "Group A+ Dashboard" in dashboard_path.read_text(encoding="utf-8")


def test_refresh_fubon_snapshot_interactive_mode_does_not_capture_prompt(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = refresh_fubon_snapshot(
        holdings_path=tmp_path / "holdings.json",
        local_config_dir=tmp_path / "fubon",
        interactive=True,
    )

    assert result.returncode == 0
    _, kwargs = calls[0]
    assert kwargs["text"] is True
    assert kwargs["check"] is False
    assert "capture_output" not in kwargs


def test_refresh_fubon_snapshot_noninteractive_mode_captures_errors(monkeypatch, tmp_path) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 1, stderr="manual terminal required")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = refresh_fubon_snapshot(
        holdings_path=tmp_path / "holdings.json",
        local_config_dir=tmp_path / "fubon",
        interactive=False,
    )

    assert result.returncode == 1
    assert result.stderr == "manual terminal required"
    _, kwargs = calls[0]
    assert kwargs["capture_output"] is True
