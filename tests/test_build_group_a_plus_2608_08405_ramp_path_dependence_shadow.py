from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate import build_group_a_plus_2608_08405_ramp_path_dependence_shadow as module


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_ramp_path_dependence_blocks_target_history_without_realized_fills(tmp_path: Path) -> None:
    history = tmp_path / "history.json"
    assigned = tmp_path / "assigned.json"
    _write_json(
        history,
        {
            "history_type": "system_observed_daily_status_not_broker_fills",
            "coverage": {"last_check_date": "2026-09-03"},
            "entries": [
                {"ticker": "0050.TW", "target_delta_shares": 100, "filled_trade": False},
                {"ticker": "0050.TW", "target_delta_shares": -50, "filled_trade": False},
                {"ticker": "00631L.TW", "target_delta_shares": 20, "filled_trade": False},
                {"ticker": "00631L.TW", "target_delta_shares": -10, "filled_trade": False},
            ],
        },
    )
    _write_json(assigned, {"status": "blocked"})

    report = module.build_report(
        intervention_history_path=history,
        assigned_realized_path=assigned,
        minimum_two_sided_tickers=2,
    )

    assert report["status"] == "blocked_shadow_only"
    assert report["coverage"]["two_sided_target_path_ticker_count"] == 2
    assert report["coverage"]["realized_two_sided_path_ticker_count"] == 0
    assert report["checks"]["target_ramp_paths_observed"] is True
    assert report["checks"]["realized_ramp_paths_observed"] is False
    assert "intervention_history_is_target_status_not_realized_fills" in report["blocking_reasons"]
    assert "realized_two_sided_ramp_paths_missing" in report["blocking_reasons"]
    assert report["decision"]["latest_strategy_change_allowed"] is False


def test_ramp_path_dependence_stays_separate_even_with_empty_history(tmp_path: Path) -> None:
    history = tmp_path / "history.json"
    assigned = tmp_path / "assigned.json"
    _write_json(history, {"entries": []})
    _write_json(assigned, {"status": "ready_for_capacity_shadow_review"})

    report = module.build_report(
        intervention_history_path=history,
        assigned_realized_path=assigned,
        minimum_two_sided_tickers=1,
    )
    markdown = module._markdown(report)

    assert "intervention_history_missing" in report["blocking_reasons"]
    assert "capacity_level_grid_cannot_substitute_for_ramp_experiment" in report["blocking_reasons"]
    assert report["decision"]["capacity_scaling_allowed"] is False
    assert "## Ticker Sequences" in markdown
