from __future__ import annotations

from pathlib import Path

import pandas as pd

from group_a_plus.core.signal_contract import (
    UNVERSIONED,
    TargetWeightSignal,
    from_daily_signal,
)


def _sample_daily_signal(**overrides) -> dict:
    base = {
        "strategy_id": "a2118_a2111_ncf_late_bull_deleverage",
        "generated_at": "2026-07-26T08:00:00",
        "requested_as_of_date": "2026-07-26",
        "actual_data_date": "2026-07-25",
        "execution_regime": "golden1",
        "regime_reason": "golden1 regime, no gate triggered",
        "target_weights": {"0050.TW": 0.5, "00631L.TW": 0.2, "cash": 0.3},
        "ncf_panel_coverage": {
            "panel_631l_path": None,
            "panel_631l_last_date": "2026-07-24",
        },
        "signal_version": 2,
        "strategy_status": "active",
    }
    base.update(overrides)
    return base


def test_from_daily_signal_maps_core_fields() -> None:
    signal = from_daily_signal(_sample_daily_signal())

    assert signal.strategy_id == "a2118_a2111_ncf_late_bull_deleverage"
    assert signal.signal_asof == pd.Timestamp("2026-07-25")
    assert signal.generated_at == pd.Timestamp("2026-07-26T08:00:00")
    assert signal.execution_date == pd.Timestamp("2026-07-26")
    assert signal.weights == {"0050.TW": 0.5, "00631L.TW": 0.2, "cash": 0.3}
    assert signal.signal_reason == "golden1 regime, no gate triggered"
    assert signal.feature_version == UNVERSIONED


def test_from_daily_signal_explicit_execution_date_overrides_default() -> None:
    signal = from_daily_signal(_sample_daily_signal(), execution_date="2026-07-27")
    assert signal.execution_date == pd.Timestamp("2026-07-27")


def test_missing_panel_path_falls_back_to_unversioned_model() -> None:
    signal = from_daily_signal(_sample_daily_signal())
    assert signal.model_version == UNVERSIONED


def test_panel_path_present_gives_stable_non_unversioned_model_version(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel_631l.csv"
    panel_path.write_text("dt,h20_prob_up\n2026-07-24,0.6\n", encoding="utf-8")
    signal = from_daily_signal(
        _sample_daily_signal(
            ncf_panel_coverage={"panel_631l_path": str(panel_path), "panel_631l_last_date": "2026-07-24"}
        )
    )
    assert signal.model_version != UNVERSIONED
    assert panel_path.name in signal.model_version


def test_data_snapshot_hash_changes_when_target_weights_change() -> None:
    signal_a = from_daily_signal(_sample_daily_signal())
    signal_b = from_daily_signal(_sample_daily_signal(target_weights={"0050.TW": 0.9, "cash": 0.1}))
    assert signal_a.data_snapshot_hash != signal_b.data_snapshot_hash


def test_data_snapshot_hash_changes_when_panel_bytes_change(tmp_path: Path) -> None:
    panel_path = tmp_path / "panel_631l.csv"
    panel_path.write_text("dt,h20_prob_up\n2026-07-24,0.6\n", encoding="utf-8")
    signal_before = from_daily_signal(
        _sample_daily_signal(ncf_panel_coverage={"panel_631l_path": str(panel_path), "panel_631l_last_date": "2026-07-24"})
    )
    # Simulate a silent overwrite by a different model run -- same path,
    # different bytes (the exact golden1_0531 failure mode).
    panel_path.write_text("dt,h20_prob_up\n2026-07-24,0.9\n", encoding="utf-8")
    signal_after = from_daily_signal(
        _sample_daily_signal(ncf_panel_coverage={"panel_631l_path": str(panel_path), "panel_631l_last_date": "2026-07-24"})
    )
    assert signal_before.data_snapshot_hash != signal_after.data_snapshot_hash


def test_data_snapshot_hash_is_deterministic_for_identical_input(tmp_path: Path) -> None:
    signal_a = from_daily_signal(_sample_daily_signal())
    signal_b = from_daily_signal(_sample_daily_signal())
    assert signal_a.data_snapshot_hash == signal_b.data_snapshot_hash


def test_roundtrip_json_dict_preserves_all_fields() -> None:
    signal = from_daily_signal(_sample_daily_signal())
    restored = TargetWeightSignal.from_json_dict(signal.to_json_dict())
    assert restored == signal


def test_frozen_dataclass_is_immutable() -> None:
    signal = from_daily_signal(_sample_daily_signal())
    try:
        signal.strategy_id = "different"  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised, "TargetWeightSignal must be frozen (immutable)"
