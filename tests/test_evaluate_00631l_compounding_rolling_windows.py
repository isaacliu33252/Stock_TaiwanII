from argparse import Namespace
from pathlib import Path

from scripts.evaluate import evaluate_00631l_compounding_rolling_windows as mod


def test_build_rolling_windows_uses_recent_max_windows_and_panel() -> None:
    dates = [f"2020-01-{day:02d}" for day in range(1, 11)]

    windows = mod.build_rolling_windows(dates, window_days=4, step_days=2, max_windows=2)

    assert windows == [
        ("roll_2020-01-05_2020-01-08", "2020-01-05", "2020-01-08", mod.PANEL_2025_2026, "rolling_window"),
        ("roll_2020-01-07_2020-01-10", "2020-01-07", "2020-01-10", mod.PANEL_2025_2026, "rolling_window"),
    ]


def test_summary_reports_positive_rate_and_distribution() -> None:
    summary = mod._summary([10.0, -2.0, 0.0, 8.0])

    assert summary == {
        "count": 4,
        "positive_count": 2,
        "positive_rate": 0.5,
        "median": 4.0,
        "min": -2.0,
        "max": 10.0,
    }


def test_evaluate_rolling_windows_compares_preferred_against_robust(monkeypatch) -> None:
    monkeypatch.setattr(mod, "_resolve_end_date", lambda db_path, requested_end: "2020-01-10")
    monkeypatch.setattr(
        mod,
        "_trading_dates",
        lambda db_path, start, end: [f"2020-01-{day:02d}" for day in range(1, 11)],
    )

    def fake_evaluate_window(**kwargs):
        is_preferred = kwargs["thresholds"].trend_score_min == mod.PREFERRED_THRESHOLDS.trend_score_min
        label = kwargs["label"]
        base = 120.0 if label.endswith("01-04") else 80.0
        delta = base if is_preferred else 50.0
        return {
            "delta_vs_baseline": {
                "final_value": delta,
                "sharpe_ratio": delta / 100.0,
                "max_drawdown": 1.0 if is_preferred else -1.0,
            },
            "mean_reversion_no_add": {
                "event_days": 3 if is_preferred else 2,
                "metrics": {"final_value": 1_000_000.0 + delta},
            },
        }

    monkeypatch.setattr(mod, "evaluate_window", fake_evaluate_window)
    args = Namespace(
        db=str(Path("dummy.duckdb")),
        start="2020-01-01",
        end="latest",
        initial_value=1_000_000.0,
        window_days=4,
        step_days=4,
        max_windows=0,
        transaction_cost_bps=20.0,
        baseline_add_fraction=0.40,
        mean_reversion_add_fraction=0.00,
        trend_persistent_add_fraction=1.00,
        weak_trend_edge_gate="none",
        weak_trend_add_fraction=0.90,
        preferred_trend_score_min=mod.PREFERRED_THRESHOLDS.trend_score_min,
        preferred_ar1_trend_min=mod.PREFERRED_THRESHOLDS.ar1_trend_min,
        preferred_trend_persistence_min=mod.PREFERRED_THRESHOLDS.trend_persistence_min,
        preferred_reversal_speed_trend_max=mod.PREFERRED_THRESHOLDS.reversal_speed_trend_max,
        min_positive_rate=0.65,
        worst_delta_floor=-2500.0,
        include_reports=False,
    )

    payload = mod.evaluate_rolling_windows(args)

    assert payload["summary"]["windows"] == 2
    assert payload["summary"]["pass"] is True
    assert payload["summary"]["preferred_delta_final_value"]["positive_rate"] == 1.0
    assert payload["summary"]["incremental_delta_final_value"]["min"] == 30.0
    assert payload["rows"][0]["preferred_event_days"] == 3
    assert payload["rows"][0]["transaction_cost_bps"] == 20.0
    assert payload["reports"] == []
