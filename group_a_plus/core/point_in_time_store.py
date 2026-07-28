"""Append-only point-in-time archive for `TargetWeightSignal` snapshots.

Writes to `results/ncf_snapshots/YYYY/MM/DD/`, one file per
(strategy_id, generated_at) pair -- **never overwritten**. This is the
specific property the golden1_0531 payload-overwrite incident needed and
didn't have: the old payload was silently replaced in place by a later
pipeline run, so there was no way afterward to tell that had happened, let
alone recover the original. Writing a new, uniquely-named file per snapshot
instead of updating a single "latest" file means a later run using a
different model/panel is an *additional* file, not a replacement -- drift
or an unexpected overwrite becomes a visible diff between snapshot files
(different `data_snapshot_hash` for the same `signal_asof`) instead of
unrecoverable.

This module only writes/reads plain JSON files. It does not touch any
`report/group_a_plus/latest/*` pointer file, and nothing currently reads
from this store in the live decision path -- see `signal_contract.py`'s
module docstring for the explicit scope decision to keep this additive.
"""

from __future__ import annotations

import json
from pathlib import Path

from group_a_plus.core.signal_contract import TargetWeightSignal
from group_a_plus.paths import PROJECT_ROOT

DEFAULT_SNAPSHOT_ROOT = PROJECT_ROOT / "results" / "ncf_snapshots"


def _snapshot_dir(signal_asof, root: Path) -> Path:
    root = Path(root)
    return root / f"{signal_asof.year:04d}" / f"{signal_asof.month:02d}" / f"{signal_asof.day:02d}"


def _snapshot_filename(signal: TargetWeightSignal) -> str:
    # generated_at (not just signal_asof) makes the filename unique across
    # same-day reruns -- two runs for the same signal_asof produce two
    # files, not one overwritten file.
    stamp = signal.generated_at.strftime("%Y%m%dT%H%M%S")
    return f"{signal.strategy_id}_{stamp}_{signal.data_snapshot_hash[:12]}.json"


def write_snapshot(signal: TargetWeightSignal, root: Path = DEFAULT_SNAPSHOT_ROOT) -> Path:
    """Write `signal` as a new, uniquely-named JSON file. Never overwrites
    an existing snapshot -- if the exact same (strategy_id, generated_at,
    hash) combination is written twice, the second write is a no-op
    returning the existing path, since the content would be identical.
    """
    directory = _snapshot_dir(signal.signal_asof, root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _snapshot_filename(signal)
    if not path.exists():
        path.write_text(json.dumps(signal.to_json_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_snapshot(path: Path) -> TargetWeightSignal:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return TargetWeightSignal.from_json_dict(payload)


def list_snapshots_for_date(signal_asof, root: Path = DEFAULT_SNAPSHOT_ROOT) -> list[Path]:
    """All snapshot files for a given `signal_asof` date, oldest first.
    Multiple results for the same date is not an error -- it means the
    pipeline ran more than once for that date (a rerun, a backfill, or a
    genuine model/panel change); compare their `data_snapshot_hash` to see
    whether the signal actually changed between runs.
    """
    import pandas as pd

    directory = _snapshot_dir(pd.Timestamp(signal_asof), root)
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def latest_snapshot_for_date(signal_asof, root: Path = DEFAULT_SNAPSHOT_ROOT) -> TargetWeightSignal | None:
    paths = list_snapshots_for_date(signal_asof, root)
    if not paths:
        return None
    return read_snapshot(paths[-1])
