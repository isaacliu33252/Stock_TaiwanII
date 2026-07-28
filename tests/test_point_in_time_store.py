from __future__ import annotations

from pathlib import Path

import pandas as pd

from group_a_plus.core.point_in_time_store import (
    latest_snapshot_for_date,
    list_snapshots_for_date,
    read_snapshot,
    write_snapshot,
)
from group_a_plus.core.signal_contract import TargetWeightSignal


def _sample_signal(**overrides) -> TargetWeightSignal:
    base = dict(
        strategy_id="a2118_a2111_ncf_late_bull_deleverage",
        signal_asof=pd.Timestamp("2026-07-25"),
        generated_at=pd.Timestamp("2026-07-26T08:00:00"),
        execution_date=pd.Timestamp("2026-07-26"),
        weights={"0050.TW": 0.5, "00631L.TW": 0.2, "cash": 0.3},
        model_version="panel_631l.csv@2026-07-24",
        feature_version="unversioned",
        data_snapshot_hash="a" * 64,
        signal_reason="golden1 regime, no gate triggered",
    )
    base.update(overrides)
    return TargetWeightSignal(**base)


def test_write_snapshot_creates_yyyy_mm_dd_directory_structure(tmp_path: Path) -> None:
    signal = _sample_signal()
    path = write_snapshot(signal, root=tmp_path)

    assert path.exists()
    assert path.parent == tmp_path / "2026" / "07" / "25"


def test_write_snapshot_never_overwrites_a_different_generated_at(tmp_path: Path) -> None:
    signal_1 = _sample_signal(generated_at=pd.Timestamp("2026-07-26T08:00:00"), data_snapshot_hash="a" * 64)
    signal_2 = _sample_signal(generated_at=pd.Timestamp("2026-07-26T09:00:00"), data_snapshot_hash="b" * 64)

    path_1 = write_snapshot(signal_1, root=tmp_path)
    path_2 = write_snapshot(signal_2, root=tmp_path)

    assert path_1 != path_2
    assert path_1.exists()
    assert path_2.exists()
    assert len(list_snapshots_for_date(pd.Timestamp("2026-07-25"), root=tmp_path)) == 2


def test_write_snapshot_is_idempotent_for_identical_content(tmp_path: Path) -> None:
    signal = _sample_signal()
    path_1 = write_snapshot(signal, root=tmp_path)
    original_mtime = path_1.stat().st_mtime_ns

    path_2 = write_snapshot(signal, root=tmp_path)

    assert path_1 == path_2
    assert path_2.stat().st_mtime_ns == original_mtime


def test_read_snapshot_roundtrips(tmp_path: Path) -> None:
    signal = _sample_signal()
    path = write_snapshot(signal, root=tmp_path)

    restored = read_snapshot(path)

    assert restored == signal


def test_list_snapshots_for_date_empty_when_none_written(tmp_path: Path) -> None:
    assert list_snapshots_for_date(pd.Timestamp("2026-01-01"), root=tmp_path) == []


def test_latest_snapshot_for_date_returns_most_recent_by_filename_order(tmp_path: Path) -> None:
    signal_1 = _sample_signal(generated_at=pd.Timestamp("2026-07-26T08:00:00"), data_snapshot_hash="a" * 64)
    signal_2 = _sample_signal(generated_at=pd.Timestamp("2026-07-26T09:00:00"), data_snapshot_hash="b" * 64)
    write_snapshot(signal_1, root=tmp_path)
    write_snapshot(signal_2, root=tmp_path)

    latest = latest_snapshot_for_date(pd.Timestamp("2026-07-25"), root=tmp_path)

    assert latest == signal_2


def test_latest_snapshot_for_date_none_when_no_snapshots(tmp_path: Path) -> None:
    assert latest_snapshot_for_date(pd.Timestamp("2026-01-01"), root=tmp_path) is None


def test_write_snapshot_accepts_string_root(tmp_path: Path) -> None:
    signal = _sample_signal()
    path = write_snapshot(signal, root=str(tmp_path))
    assert path.exists()


def test_different_signal_asof_dates_go_to_different_directories(tmp_path: Path) -> None:
    signal_a = _sample_signal(signal_asof=pd.Timestamp("2026-07-25"))
    signal_b = _sample_signal(signal_asof=pd.Timestamp("2026-08-01"))

    write_snapshot(signal_a, root=tmp_path)
    write_snapshot(signal_b, root=tmp_path)

    assert list_snapshots_for_date(pd.Timestamp("2026-07-25"), root=tmp_path) != []
    assert list_snapshots_for_date(pd.Timestamp("2026-08-01"), root=tmp_path) != []
    assert (tmp_path / "2026" / "07" / "25").exists()
    assert (tmp_path / "2026" / "08" / "01").exists()
