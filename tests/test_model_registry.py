from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.model_registry import (
    build_checkpoint_metadata,
    load_model_registry,
    validate_model_card,
    validate_model_registry,
)


def test_default_model_registry_is_valid() -> None:
    registry = load_model_registry()

    assert validate_model_registry(registry) == []
    assert {item["model_id"] for item in registry["models"]} >= {
        "group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526",
        "group_a_production_2020_2025_100k",
        "group_a_plus_4tickers_2020_2025",
    }


def test_build_checkpoint_metadata_records_file_identity(tmp_path: Path) -> None:
    model = tmp_path / "model.zip"
    model.write_bytes(b"checkpoint")

    metadata = build_checkpoint_metadata(model, project_root=tmp_path)

    assert metadata["model_path"] == "model.zip"
    assert metadata["size_bytes"] == len(b"checkpoint")
    assert len(metadata["sha256"]) == 64


def test_validate_model_card_flags_hash_mismatch(tmp_path: Path) -> None:
    model = tmp_path / "model.zip"
    model.write_bytes(b"checkpoint")
    card = {
        "model_id": "unit",
        "status": "shadow",
        "role": "unit test",
        "model_path": "model.zip",
        "sha256": "0" * 64,
        "size_bytes": len(b"checkpoint"),
        "modified_at": model.stat().st_mtime_ns,
        "training": {},
        "evaluation": {},
        "lineage": {},
        "metadata_status": "partial",
    }

    assert validate_model_card(card, project_root=tmp_path) == ["sha256_mismatch:unit"]


def test_validate_model_registry_flags_duplicate_ids(tmp_path: Path) -> None:
    model = tmp_path / "model.zip"
    model.write_bytes(b"checkpoint")
    metadata = build_checkpoint_metadata(model, project_root=tmp_path)
    card = {
        "model_id": "duplicate",
        "status": "shadow",
        "role": "unit test",
        **metadata,
        "training": {},
        "evaluation": {},
        "lineage": {},
        "metadata_status": "partial",
    }
    registry = {"schema_version": 1, "models": [card, json.loads(json.dumps(card))]}

    errors = validate_model_registry(registry, project_root=tmp_path)

    assert "duplicate_model_id:duplicate" in errors
    assert "duplicate_model_path:model.zip" in errors
