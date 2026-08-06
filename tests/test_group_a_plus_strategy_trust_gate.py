from __future__ import annotations

import json
import tempfile
from pathlib import Path

from group_a_plus.integrations.strategy_trust_gate import (
    append_strategy_trust_shadow_log,
    classify_strategy_trust,
)


def _risk_mechanism(mechanism: str) -> dict:
    return {"mechanism": mechanism, "reasons": [], "components": {}}


def _signal_alignment(alignment: str, divergent_sources: list | None = None) -> dict:
    return {"alignment": alignment, "divergent_sources": divergent_sources or []}


def _ops_health(
    module_health: str = "ok",
    feature_table_sync: str = "ok",
    external_data_freshness: str = "ok",
) -> dict:
    return {
        "status": "ok",
        "module_health": {"status": module_health},
        "feature_table_sync": {"status": feature_table_sync},
        "external_data_freshness": {"status": external_data_freshness},
    }


def test_trust_when_normal_regime_aligned_ensemble_and_clean_data() -> None:
    result = classify_strategy_trust(
        _risk_mechanism("NORMAL"), _signal_alignment("aligned"), _ops_health()
    )
    assert result["trust_level"] == "TRUST"
    assert result["components"]["uncertain_regime"] is False
    assert result["components"]["ensemble_disagrees"] is False
    assert result["components"]["data_quality_problem"] is False


def test_shadow_only_on_fast_crash_regime() -> None:
    result = classify_strategy_trust(
        _risk_mechanism("FAST_CRASH"), _signal_alignment("aligned"), _ops_health()
    )
    assert result["trust_level"] == "SHADOW_ONLY"
    assert result["components"]["uncertain_regime"] is True


def test_shadow_only_on_persistent_drawdown_regime() -> None:
    result = classify_strategy_trust(
        _risk_mechanism("PERSISTENT_DRAWDOWN"), _signal_alignment("aligned"), _ops_health()
    )
    assert result["trust_level"] == "SHADOW_ONLY"


def test_shadow_only_on_ensemble_disagreement_via_alignment() -> None:
    result = classify_strategy_trust(
        _risk_mechanism("NORMAL"), _signal_alignment("mixed"), _ops_health()
    )
    assert result["trust_level"] == "SHADOW_ONLY"
    assert result["components"]["ensemble_disagrees"] is True


def test_shadow_only_on_divergent_sources_even_if_alignment_label_is_ok() -> None:
    result = classify_strategy_trust(
        _risk_mechanism("NORMAL"),
        _signal_alignment("aligned", divergent_sources=["ncf_00631l"]),
        _ops_health(),
    )
    assert result["trust_level"] == "SHADOW_ONLY"
    assert result["components"]["ensemble_disagrees"] is True


def test_abstain_when_module_health_degraded() -> None:
    result = classify_strategy_trust(
        _risk_mechanism("NORMAL"), _signal_alignment("aligned"), _ops_health(module_health="warning")
    )
    assert result["trust_level"] == "ABSTAIN"
    assert result["components"]["data_quality_problem"] is True


def test_abstain_when_feature_table_sync_error() -> None:
    result = classify_strategy_trust(
        _risk_mechanism("NORMAL"), _signal_alignment("aligned"), _ops_health(feature_table_sync="error")
    )
    assert result["trust_level"] == "ABSTAIN"


def test_abstain_when_external_data_freshness_not_ok() -> None:
    result = classify_strategy_trust(
        _risk_mechanism("NORMAL"),
        _signal_alignment("aligned"),
        _ops_health(external_data_freshness="degraded"),
    )
    assert result["trust_level"] == "ABSTAIN"


def test_abstain_wins_over_shadow_only_conditions() -> None:
    """Data-quality problems are a floor that dominates even an otherwise
    uncertain-but-loggable regime/disagreement condition."""
    result = classify_strategy_trust(
        _risk_mechanism("FAST_CRASH"),
        _signal_alignment("mixed"),
        _ops_health(module_health="warning"),
    )
    assert result["trust_level"] == "ABSTAIN"


def test_missing_ops_health_does_not_force_abstain() -> None:
    """Unknown data-quality status must not silently degrade to ABSTAIN --
    only an explicit not-ok status does. Absence of the ops_health report
    itself (e.g. step ran before ops_health in the pipeline) should not be
    conflated with a confirmed data-quality problem."""
    result = classify_strategy_trust(_risk_mechanism("NORMAL"), _signal_alignment("aligned"), None)
    assert result["trust_level"] == "TRUST"
    assert result["components"]["module_health_status"] == "unknown"


def test_append_strategy_trust_shadow_log_is_idempotent_per_date() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_path = Path(tmp_dir) / "strategy_trust_shadow_log.jsonl"
        day1 = classify_strategy_trust(_risk_mechanism("FAST_CRASH"), _signal_alignment("aligned"), _ops_health())
        day2 = classify_strategy_trust(_risk_mechanism("NORMAL"), _signal_alignment("aligned"), _ops_health())
        day1_rerun = classify_strategy_trust(
            _risk_mechanism("NORMAL"), _signal_alignment("mixed"), _ops_health()
        )

        append_strategy_trust_shadow_log(log_path, day1, date="2026-08-01")
        append_strategy_trust_shadow_log(log_path, day2, date="2026-08-02")
        append_strategy_trust_shadow_log(log_path, day1_rerun, date="2026-08-01")

        lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(lines) == 2
    by_date = {row["date"]: row for row in lines}
    assert by_date["2026-08-01"]["trust_level"] == "SHADOW_ONLY"
    assert by_date["2026-08-02"]["trust_level"] == "TRUST"
