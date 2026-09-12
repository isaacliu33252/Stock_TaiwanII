from __future__ import annotations

import json
import tempfile
from pathlib import Path

from group_a_plus.integrations.adaptive_quantile_risk_gate import (
    append_adaptive_quantile_risk_gate_shadow_log,
    classify_adaptive_quantile_risk_gate,
)
from scripts.evaluate.build_group_a_plus_adaptive_quantile_risk_gate_shadow import (
    build_report,
    write_report,
)


def _live_signal(**overrides):
    signal = {
        "actual_data_date": "2026-08-06",
        "business_stale_days": 0,
        "calendar_stale_days": 0,
        "execution_allowed": True,
        "execution_regime": "golden1",
        "base_regime": "golden1",
        "target_weights": {"0050.TW": 0.3, "00631L.TW": 0.0, "00632R.TW": 0.0, "cash": 0.7},
        "ncf_live_overlay": {"status": "applied"},
        "signal_alignment": {
            "alignment": "bullish_alignment",
            "divergent_sources": [],
            "leverage_suitability": {"tier": 2},
        },
        "tail_conformal": {"state": "TAIL_RISK_NORMAL", "allow_00631l_add": True},
        "garch_regime_shadow": {"volatility_gate": {"high_vol_gate": False}},
    }
    signal.update(overrides)
    return signal


def _ops_health(status: str = "ok"):
    return {
        "module_health": {"status": status},
        "feature_table_sync": {"status": "ok"},
        "external_data_freshness": {"status": "ok"},
    }


def test_stale_blocked_signal_maps_to_defensive_or_pessimistic() -> None:
    result = classify_adaptive_quantile_risk_gate(
        _live_signal(
            execution_allowed=False,
            business_stale_days=2,
            calendar_stale_days=4,
            ncf_live_overlay={"status": "stale"},
            signal_alignment={
                "alignment": "bullish_alignment",
                "divergent_sources": [],
                "leverage_suitability": {"tier": 1},
            },
        ),
        ops_health=_ops_health("warning"),
        strategy_trust={"trust_level": "ABSTAIN"},
    )

    assert result["policy"] == "shadow_only_no_target_weight_change"
    assert result["risk_posture"] in {"defensive_0.35", "pessimistic_0.20"}
    assert result["recommended_shadow_limits"]["allow_new_leverage_long"] is False
    assert result["decision"]["target_weight_change_allowed"] is False
    assert "execution_guard_not_satisfied" in result["reason_codes"]
    assert "ncf_live_overlay_stale" in result["reason_codes"]


def test_clean_fresh_signal_can_reach_controlled_exploration() -> None:
    result = classify_adaptive_quantile_risk_gate(
        _live_signal(),
        ops_health=_ops_health(),
        strategy_trust={"trust_level": "TRUST"},
        regime_analog_count=80,
    )

    assert result["risk_posture"] == "controlled_exploration_0.65"
    assert result["quantile_level"] == 0.65
    assert result["recommended_shadow_limits"]["allow_new_leverage_long"] is True
    assert result["recommended_shadow_limits"]["max_00631l_weight"] == 0.20


def test_yesterday_forecast_miss_reduces_risk_posture() -> None:
    result = classify_adaptive_quantile_risk_gate(
        _live_signal(),
        ops_health=_ops_health(),
        strategy_trust={"trust_level": "TRUST"},
        yesterday_review={"return_pct": -0.012, "direction_miss": True},
    )

    assert result["risk_posture"] in {"neutral_0.50", "defensive_0.35"}
    assert "yesterday_loss_ge_1pct" in result["reason_codes"]
    assert "yesterday_direction_miss" in result["reason_codes"]


def test_append_shadow_log_is_idempotent_per_date() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_path = Path(tmp_dir) / "aq_gate.jsonl"
        day1 = classify_adaptive_quantile_risk_gate(_live_signal(), strategy_trust={"trust_level": "TRUST"})
        day1_rerun = classify_adaptive_quantile_risk_gate(
            _live_signal(execution_allowed=False, business_stale_days=3, ncf_live_overlay={"status": "stale"})
        )

        append_adaptive_quantile_risk_gate_shadow_log(log_path, day1, date="2026-08-06")
        append_adaptive_quantile_risk_gate_shadow_log(log_path, day1_rerun, date="2026-08-06")

        lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

    assert len(lines) == 1
    assert lines[0]["date"] == "2026-08-06"
    assert lines[0]["risk_posture"] == day1_rerun["risk_posture"]


def test_build_and_write_report_support_wrapped_live_signal(tmp_path: Path) -> None:
    live_path = tmp_path / "live_signal.json"
    ops_path = tmp_path / "ops.json"
    trust_path = tmp_path / "trust.json"
    output = tmp_path / "latest" / "adaptive.json"
    history = tmp_path / "history"
    log = tmp_path / "aq.jsonl"

    live_path.write_text(json.dumps({"success": True, "data": _live_signal()}, ensure_ascii=False), encoding="utf-8")
    ops_path.write_text(json.dumps(_ops_health(), ensure_ascii=False), encoding="utf-8")
    trust_path.write_text(json.dumps({"as_of": "2026-08-06", "trust_level": "TRUST"}, ensure_ascii=False), encoding="utf-8")

    report = build_report(live_signal_path=live_path, ops_health_path=ops_path, strategy_trust_path=trust_path)
    write_report(report, output_path=output, history_dir=history, log_path=log)

    assert json.loads(output.read_text(encoding="utf-8"))["report_type"] == "group_a_plus_adaptive_quantile_risk_gate_shadow"
    assert (history / "adaptive_quantile_risk_gate_shadow_20260806.json").exists()
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1
