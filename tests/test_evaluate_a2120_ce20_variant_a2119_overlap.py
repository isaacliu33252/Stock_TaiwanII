from pathlib import Path

from scripts.evaluate import evaluate_a2120_ce20_variant_a2119_overlap as mod


def test_ce20_variant_overlap_audit_flags_slowed_hurt_events(monkeypatch) -> None:
    overlap_report = {
        "overlap_event_rows": [
            {
                "date": "2026-01-02",
                "window_label": "w",
                "event_types": ["00631l_target_increase"],
                "delta_00631l_weight": 0.1,
                "realized_regret": {"NO_ADD": -0.02},
            },
            {
                "date": "2026-01-03",
                "window_label": "w",
                "event_types": ["00631l_target_increase"],
                "delta_00631l_weight": 0.1,
                "realized_regret": {"NO_ADD": 0.01},
            },
        ],
        "non_overlap_event_rows": [],
    }
    monkeypatch.setattr(
        mod,
        "_classified_by_window",
        lambda db_path: {
            "w": {
                "2026-01-02": {
                    "compounding_regime": "TREND_PERSISTENT",
                    "compounding_effect_20d": -0.01,
                    "trend_score": 3,
                    "mean_reversion_score": 2,
                    "relative_momentum_20d": 0.02,
                },
                "2026-01-03": {
                    "compounding_regime": "TREND_PERSISTENT",
                    "compounding_effect_20d": 0.01,
                    "trend_score": 4,
                    "mean_reversion_score": 1,
                    "relative_momentum_20d": 0.03,
                },
            }
        },
    )

    out = mod.build_audit(overlap_report=overlap_report, db_path=Path("dummy.duckdb"))

    assert out["summary"]["a2119_00631l_increase_events"] == 2
    assert out["summary"]["a2120_main_fast_reentry_overlap_events"] == 2
    assert out["summary"]["ce20_variant_slowed_overlap_events"] == 1
    assert out["summary"]["ce20_variant_slowed_no_add_hurt_events"] == 1
    assert out["summary"]["ce20_variant_slowed_no_add_help_events"] == 0
    assert out["summary"]["pass"] is True
