from scripts.evaluate.backfill_group_a_plus_specialist_routing_shadow import (
    _volatility_gate_from_garch,
    build_backfill_rows,
)


def test_volatility_gate_from_legacy_garch_row_reconstructs_gate() -> None:
    gate = _volatility_gate_from_garch(
        {
            "status": "available",
            "high_vol_flag": True,
            "garch_proxy_vol_ratio": 1.2,
            "garch_proxy_vol_percentile": 0.8,
            "return_0050_5d": -0.03,
        }
    )

    assert gate is not None
    assert gate["gate"] == "high_vol_defensive"
    assert gate["high_vol_gate"] is True


def test_build_backfill_rows_routes_from_existing_logs() -> None:
    rows = build_backfill_rows(
        garch_rows={
            "2026-07-09": {
                "status": "available",
                "high_vol_flag": True,
                "garch_proxy_vol_ratio": 1.2,
                "garch_proxy_vol_percentile": 0.8,
                "return_0050_5d": -0.03,
                "logged_execution_regime": "golden1",
            }
        },
        market_rows={
            "2026-07-09": {
                "state": "late_bull_overheat",
                "bucket": "bull_trend",
                "inputs": {"total_risk_score": 7, "tail_risk_score": 0, "drawdown": -0.04},
            }
        },
        alignment_rows={
            "2026-07-09": {"alignment": "wide_divergence", "dominant_direction": "bearish"}
        },
    )

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-07-09"
    assert rows[0]["routing"]["route"] == "high_volatility"
    assert rows[0]["execution_regime"] == "golden1"
