# GroupA+ Point-in-Time Artifact Protection Handoff - 2026-07-30

## Status

Completed. The point-in-time archive is no longer limited to
`TargetWeightSignal`; it now supports generic JSON artifacts and the
execution-plan latest pointer is archived automatically.

This directly addresses the concern that the original 2026-07-26 PIT store
protected only one artifact class even though overwrite incidents also hit or
threatened:

- `report/group_a_plus/latest/execution_plan.json`
- `results/group_a_release_Golden1_0531.json`
- other production-sensitive JSON payloads that are written through "latest"
  pointers.

## Starting Point

Existing `group_a_plus/core/point_in_time_store.py`:

- Wrote `TargetWeightSignal` snapshots only.
- Stored under `results/ncf_snapshots/YYYY/MM/DD/`.
- Had append-only/idempotent behavior for signal snapshots.
- Did not provide a generic JSON artifact archive API.

Existing `scripts/run/run_ncf_daily_pipeline.py` already had a protected-output
guard that prevents the daily pipeline from writing the golden1 release files,
but that is not the same as preserving a point-in-time copy of the current
release payload for recovery/audit.

Existing `group_a_plus/operations/execution_plan.py` wrote:

- explicit output path, usually under `results/`;
- latest pointer, normally `report/group_a_plus/latest/execution_plan.json`;

but did not archive the exact payload before/after latest-pointer overwrite.

## Decision

Generalize the PIT store instead of creating one-off backups per artifact.

Rationale:

- The required invariant is the same across these artifacts:
  a later run should create an additional snapshot, never replace the only
  surviving historical payload.
- Keeping the archive additive preserves current live-path behavior.
- The golden1 release file should remain protected from daily pipeline writes;
  archiving it should be a read-only operation against the source file.

## Code Changes

### Generic JSON PIT Archive

File changed:

- `group_a_plus/core/point_in_time_store.py`

Added:

- `write_json_artifact_snapshot(...)`
- `archive_json_file(...)`
- `list_json_artifact_snapshots(...)`
- `read_json_artifact_snapshot(...)`

Storage path:

```text
results/point_in_time_artifacts/<artifact_name>/YYYY/MM/DD/<artifact>_<generated_at>_<hash12>.json
```

Properties:

- JSON content hash is computed from canonical sorted JSON.
- Same content + same generated_at is idempotent.
- Different content or generated_at creates a distinct file.
- Artifact name is slugged for filesystem safety.
- Existing `TargetWeightSignal` APIs are preserved.

### Execution Plan Auto-Archive

File changed:

- `group_a_plus/operations/execution_plan.py`

Added helper functions:

- `_execution_plan_pit_asof(...)`
- `_execution_plan_pit_generated_at(...)`
- `_write_execution_plan_pit_snapshot(...)`

`main()` now writes a PIT snapshot after writing the normal output and latest
pointer:

```python
write_standard_output(payload, args.output)
write_standard_output(payload, args.latest_pointer)
pit_snapshot = _write_execution_plan_pit_snapshot(payload, requested_as_of=args.as_of)
```

The archive as-of date uses:

1. `data.actual_data_date`;
2. else `data.requested_as_of_date`;
3. else CLI `--as-of`.

The archive generated timestamp uses:

1. `data.generated_at`;
2. else `metadata.timestamp`;
3. else current time.

## Existing Artifact Backfill

Archived current execution plan latest pointer:

```text
results/point_in_time_artifacts/execution_plan/2026/07/27/execution_plan_20260728T074526_c34b5c7635ad.json
```

Archived current golden1 release payload:

```text
results/point_in_time_artifacts/golden1_0531_release/2026/05/31/golden1_0531_release_20260730T084600_03a7ee22f97e.json
```

The source files were not modified by these archive operations.

## Tests

File changed:

- `tests/test_point_in_time_store.py`

Added coverage:

- Generic JSON artifact snapshots do not overwrite different content.
- Generic JSON artifact snapshots are idempotent for identical content.
- Existing golden1 release payloads can be archived read-only via
  `archive_json_file(...)`.

File changed:

- `tests/test_group_a_plus_execution_plan_v2.py`

Added coverage:

- Execution-plan PIT as-of uses `actual_data_date`.
- Execution-plan PIT generated_at uses plan `generated_at`.
- `_write_execution_plan_pit_snapshot(...)` calls the generic artifact archive
  with `artifact_name="execution_plan"`.

## Validation

Focused tests:

```bash
python3 -m pytest tests/test_point_in_time_store.py tests/test_group_a_plus_execution_plan_v2.py -q
```

Result:

```text
38 passed
```

Pipeline command tests:

```bash
python3 -m pytest tests/test_run_ncf_daily_pipeline.py -q
```

Result:

```text
21 passed
```

## Files Touched In This Session

- `group_a_plus/core/point_in_time_store.py`
- `group_a_plus/operations/execution_plan.py`
- `tests/test_point_in_time_store.py`
- `tests/test_group_a_plus_execution_plan_v2.py`
- `results/point_in_time_artifacts/execution_plan/2026/07/27/execution_plan_20260728T074526_c34b5c7635ad.json`
- `results/point_in_time_artifacts/golden1_0531_release/2026/05/31/golden1_0531_release_20260730T084600_03a7ee22f97e.json`
- `handoff/2026-07/GROUP_A_PLUS_POINT_IN_TIME_ARTIFACT_PROTECTION_HANDOFF_20260730.md`

## Residual Risk / Follow-Up

- Full repo test suite was not run.
- Only execution_plan is auto-archived in a production writer today.
- Golden1 release is protected and manually archived through `archive_json_file`;
  daily pipeline must continue not writing it.
- Future candidates for automatic generic PIT snapshots:
  - live signal latest pointer;
  - active strategy manifest;
  - alert state / final governance snapshot;
  - any report whose latest pointer has caused operational ambiguity.

