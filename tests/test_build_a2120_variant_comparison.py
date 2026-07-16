from scripts.evaluate.build_a2120_variant_comparison import build_comparison


def _report(delta: float, positive: int = 1) -> dict:
    return {
        "totals": {
            "delta_final_value_sum": delta,
            "positive_final_value_windows": positive,
        },
        "windows": [
            {
                "label": "w1",
                "delta_vs_baseline": {"final_value": delta, "max_drawdown": 0.1},
                "mean_reversion_no_add": {"event_days": 3},
            }
        ],
    }


def test_build_variant_comparison_keeps_main_primary_and_reports_delta() -> None:
    out = build_comparison(
        main_7win=_report(100.0, 7),
        main_cost20=_report(80.0, 7),
        variant_7win=_report(90.0, 7),
        variant_cost20=_report(70.0, 7),
    )

    assert out["production_effect"] == "none"
    assert out["decision"]["main_candidate"] == "keep_as_primary_shadow_candidate"
    assert out["decision"]["variant_candidate"] == "keep_as_risk_sensitive_shadow_variant"
    assert out["summary"]["variant_minus_main_7win_delta_final_value_sum"] == -10.0
    assert out["summary"]["variant_minus_main_cost20_delta_final_value_sum"] == -10.0
    assert out["cost20_windows"][0]["variant_minus_main_final_value"] == -10.0
    assert out["cost20_windows"][0]["variant_event_days"] == 3
