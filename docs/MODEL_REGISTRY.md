# Model Registry

## Decision

Model checkpoint versioning is required for production-grade reproducibility.

Current state:

- `models/portfolio/` contains many `.zip` checkpoints.
- There was no model card, file hash, lineage record, or registry.
- Some release and signal artifacts reference specific model files directly.

New standard:

- Registry path: `models/MODEL_REGISTRY.json`
- Helper module: `group_a_plus.model_registry`
- New models should be registered before being cited in promotion, release, or live-signal decisions.

`.gitignore` keeps checkpoint artifacts ignored, but explicitly allows `models/MODEL_REGISTRY.json` so registry metadata can be versioned.

## Required Model Card Fields

Each registry entry must include:

- `model_id`
- `status`
- `role`
- `model_path`
- `sha256`
- `size_bytes`
- `modified_at`
- `training`
- `evaluation`
- `lineage`
- `metadata_status`

`metadata_status` values:

- `complete`: training range, evaluation metrics, lineage, and file identity are known.
- `partial`: file identity is verified, but some training/evaluation lineage fields are unknown.
- `stub`: placeholder only; do not use for production decisions.

## Seeded Models

The first registry version tracks:

- `group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526`
- `group_a_production_2020_2025_100k`
- `group_a_plus_4tickers_2020_2025`

Only the Golden1_0531 release checkpoint is marked `complete`. The other two are intentionally marked `partial` because their full training/evaluation lineage still needs reconstruction.

## Validation

Use:

```bash
.venv/bin/python -m pytest -q tests/test_model_registry.py
```

The validator checks:

- required fields
- model file exists
- `size_bytes` matches disk
- `sha256` matches disk
- duplicate model ids
- duplicate model paths

## Migration Rule

For every future model training script:

1. Save the checkpoint.
2. Compute `sha256`, `size_bytes`, and `modified_at`.
3. Record training range and feature set.
4. Record evaluation window and metrics source.
5. Add lineage notes linking to result JSON, release manifest, or handoff.
6. Add or update `models/MODEL_REGISTRY.json`.

Do not overwrite a registered model file in place.
