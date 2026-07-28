"""Point-in-time signal contract for GroupA+ target-weight outputs.

Motivated by a recurring failure class already seen multiple times in this
project's history, not a hypothetical concern: the golden1_0531 backtest
payload referenced by a release manifest was silently overwritten by a
later pipeline run using a different model, making the original release-
time evidence unrecoverable
(`GOLDEN_00631L_HANDOFF_20260620.md`-adjacent memory,
project_golden1_0531_payload_overwrite_discovery_20260725); a2118's
original promotion evidence could only be approximately reconstructed, not
exactly reproduced (project_a2118_original_promotion_evidence_reconstructed_20260725);
NCF ensemble weights were trained on the full sample rather than a rolling
window, so predictions for a fixed historical date silently drifted every
time the model was retrained (project_ncf_panel_global_weight_drift_20260702);
and `a2118.py`'s backtest once did not call the same NCF-overlay function
`daily_signal.py`'s live path calls, so a headline Sharpe number was never
actually produced by the code that ran live (see checklist item 5 in
`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`). `TargetWeightSignal`
is a typed, frozen record of "what a signal actually was, and what
produced it" -- intended to make each of those four failure classes
detectable (drift, overwrite, non-reproducibility) after the fact instead
of requiring after-the-fact reconstruction.

This module is additive only. It does not change `build_daily_signal()`,
`build_execution_plan()`, or any decision logic -- `from_daily_signal()`
below is a pure mapping from the live-signal dict those functions already
return into this typed contract, called as a best-effort post-processing
step (see `point_in_time_store.py` and its call site in
`daily_signal.py::main()`). A larger refactor that makes signal generation
itself construct a `TargetWeightSignal` natively was deliberately not
attempted here -- `run_a2118()` and its callers were already flagged
(2026-07-24, FinRL-X citation-rule addendum) as too large to safely
restructure outside a dedicated session; this stays a wrapper.

Known gap, documented rather than hidden: `feature_version` has no
existing tracked concept anywhere in this codebase (grepped for
`model_version`/`feature_version`/`panel_hash` before writing this --
none exist). It is populated as `"unversioned"` until a real feature-set
versioning scheme exists; do not treat that string as a meaningful
version identifier.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

UNVERSIONED = "unversioned"


@dataclass(frozen=True)
class TargetWeightSignal:
    strategy_id: str
    signal_asof: pd.Timestamp
    generated_at: pd.Timestamp
    execution_date: pd.Timestamp
    weights: dict[str, float]
    model_version: str
    feature_version: str
    data_snapshot_hash: str
    signal_reason: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "signal_asof": str(self.signal_asof.date()),
            "generated_at": self.generated_at.isoformat(),
            "execution_date": str(self.execution_date.date()),
            "weights": dict(self.weights),
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "data_snapshot_hash": self.data_snapshot_hash,
            "signal_reason": self.signal_reason,
            "extra": self.extra,
        }

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> "TargetWeightSignal":
        return cls(
            strategy_id=str(payload["strategy_id"]),
            signal_asof=pd.Timestamp(payload["signal_asof"]),
            generated_at=pd.Timestamp(payload["generated_at"]),
            execution_date=pd.Timestamp(payload["execution_date"]),
            weights=dict(payload["weights"]),
            model_version=str(payload["model_version"]),
            feature_version=str(payload["feature_version"]),
            data_snapshot_hash=str(payload["data_snapshot_hash"]),
            signal_reason=str(payload.get("signal_reason", "")),
            extra=dict(payload.get("extra") or {}),
        )


def _panel_file_digest(panel_path_raw: str | None) -> str | None:
    """SHA-256 of the NCF panel file's bytes, if it exists and is resolvable.

    This is the file the live signal's NCF overlay was actually computed
    from (`report["ncf_panel_coverage"]["panel_631l_path"]`) -- hashing its
    bytes (not just its path or mtime) means a silent overwrite with a
    different model's output (the exact golden1_0531 failure mode) changes
    the hash even if the filename and modification time are unchanged.
    """
    if not panel_path_raw:
        return None
    path = Path(panel_path_raw)
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model_version(daily_signal: dict[str, Any]) -> str:
    """Best-effort model identity: panel path + its last-covered date.

    Not a real semantic version (none exists in this codebase yet -- see
    module docstring) but is at least stable and comparable: two signals
    built from the same panel file report the same `model_version`, and a
    panel swap (retrain, rollback, or a silent overwrite) changes it.
    """
    coverage = daily_signal.get("ncf_panel_coverage") or {}
    panel_path = coverage.get("panel_631l_path")
    panel_last_date = coverage.get("panel_631l_last_date")
    if not panel_path:
        return UNVERSIONED
    return f"{Path(panel_path).name}@{panel_last_date}"


def _data_snapshot_hash(daily_signal: dict[str, Any]) -> str:
    """SHA-256 combining the NCF panel file digest (if any) with the
    resolved target weights and the market data date the signal is based
    on. Two independently-produced signals with an identical hash used the
    same panel bytes and arrived at the same decision for the same date --
    a mismatch is either a real model/data change or a bug, and is now
    detectable instead of silently unrecoverable.
    """
    coverage = daily_signal.get("ncf_panel_coverage") or {}
    panel_digest = _panel_file_digest(coverage.get("panel_631l_path"))
    canonical = json.dumps(
        {
            "actual_data_date": daily_signal.get("actual_data_date"),
            "execution_regime": daily_signal.get("execution_regime"),
            "target_weights": {
                k: round(float(v), 8) for k, v in sorted((daily_signal.get("target_weights") or {}).items())
            },
            "panel_digest": panel_digest,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def from_daily_signal(
    daily_signal: dict[str, Any],
    *,
    execution_date: str | pd.Timestamp | None = None,
) -> TargetWeightSignal:
    """Build a `TargetWeightSignal` from `daily_signal.py::build_daily_signal()`'s
    return dict. Pure mapping -- does not recompute or alter the signal.

    `execution_date` has no existing distinct concept in this codebase
    (the live pipeline treats "the date it was run" and "the date it is
    executed" as the same thing); defaults to `requested_as_of_date` if not
    given explicitly. Pass it explicitly when a caller (e.g.
    `execution_plan.py`) knows the actual planned execution date and it
    differs.
    """
    resolved_execution_date = (
        pd.Timestamp(execution_date) if execution_date is not None else pd.Timestamp(daily_signal["requested_as_of_date"])
    )
    return TargetWeightSignal(
        strategy_id=str(daily_signal["strategy_id"]),
        signal_asof=pd.Timestamp(daily_signal["actual_data_date"]),
        generated_at=pd.Timestamp(daily_signal["generated_at"]),
        execution_date=resolved_execution_date,
        weights=dict(daily_signal.get("target_weights") or {}),
        model_version=_model_version(daily_signal),
        feature_version=UNVERSIONED,
        data_snapshot_hash=_data_snapshot_hash(daily_signal),
        signal_reason=str(daily_signal.get("regime_reason", "")),
        extra={
            "execution_regime": daily_signal.get("execution_regime"),
            "strategy_status": daily_signal.get("strategy_status"),
            "signal_version": daily_signal.get("signal_version"),
        },
    )
