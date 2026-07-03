#!/usr/bin/env python3
"""H3 (2026-07-02 Fable 5 audit) regression: golden1 backtest reproducibility metadata."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from group_a_plus.runners.a2111 import _golden_signal_metadata


def test_golden_signal_metadata_reports_path_hash_and_weights(tmp_path: Path) -> None:
    signal_path = tmp_path / "signal_group_a_20260702_120000.json"
    signal_path.write_text(json.dumps({"weights": {"0050.TW": 0.6}}), encoding="utf-8")

    metadata = _golden_signal_metadata(signal_path, {"0050.TW": 0.6, "00631L.TW": 0.2, "cash": 0.2})

    assert metadata["golden_signal_path"] == str(signal_path.resolve())
    assert metadata["golden_signal_sha256"] == hashlib.sha256(signal_path.read_bytes()).hexdigest()
    assert metadata["golden_weights"] == {"0050.TW": 0.6, "00631L.TW": 0.2, "cash": 0.2}
    assert metadata["golden_signal_modified_at"].endswith("Z")
    assert "not the" in metadata["caveat"]


def test_golden_signal_metadata_sha256_changes_with_content(tmp_path: Path) -> None:
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps({"weights": {"0050.TW": 0.6}}), encoding="utf-8")
    path_b.write_text(json.dumps({"weights": {"0050.TW": 0.7}}), encoding="utf-8")

    meta_a = _golden_signal_metadata(path_a, {})
    meta_b = _golden_signal_metadata(path_b, {})

    assert meta_a["golden_signal_sha256"] != meta_b["golden_signal_sha256"]
