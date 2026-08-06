"""Strategy trust gate for GroupA+ (2026-08-02 user proposal).

Motivation: NCF's own `confidence`/`decision_confidence` outputs answer "how
sure is the model", not "is today a day this model's output should be
believed at all". The user proposed a `strategy_trust_score` combining
calibration error, RankIC/Brier drift, feature drift, regime-in-distribution,
panel data quality, prediction disagreement, and recent action-value
performance into TRUST / SHADOW_ONLY / ABSTAIN.

This module deliberately does NOT build that full score. Several of the
proposed inputs already have a documented history in this codebase of being
individually noisy or overfitting when turned into a discrete decision:

- Calibration-based gating has failed OOS twice: `h20` calibration +
  relief-gate looked good across 7 historical windows but a fresh 2021 OOS
  check found plain CAP10 better (see project memory
  h20_calibration_drift_gate_deadlock_20260726). `decision_confidence`
  Phase2 calibration was paused after two rounds because calibrated
  probabilities do not transfer across regimes
  (dfl_decision_confidence_phase2_calibration_20260727).
- A discrete regime-conditioned overlay (FAST_CRASH / PERSISTENT_DRAWDOWN
  switching) was OOS-tested across 4 windows on 2026-08-01 and lost to the
  plain golden1 baseline in 2018/2022 via whipsaw
  (risk_mechanism_regime_overlay_rejected_20260801) -- see
  `scripts/misc/risk_mechanism_regime_overlay_backtest.py`.
- Panel-drift "outcome-aware" evaluation (2026-07-27) found drift correlates
  with retraining noise, not real predictive signal (matched real outcomes
  only 42-49% of the time) -- so raw panel-drift flags are deliberately
  excluded here as a trust input.
- `ops_health.status` folds in `system_resources` (disk usage), which is an
  infra concern orthogonal to whether today's model output should be
  trusted; this module reads only the sub-statuses relevant to input-data
  quality (`module_health`, `feature_table_sync`, `external_data_freshness`)
  and ignores `system_resources` and the top-level `status` field.
- NCF calibration-error / RankIC drift and "recent action-value performance"
  are excluded for now: there is no *daily* latest-report source for either
  yet. `evaluate_ncf_blend_live_auc_archive.py` computes something adjacent
  but needs an accumulated forward-realized sample (`min_samples=30`) and
  runs research-only, not as part of the daily pipeline's latest-report set.
  Forcing a same-day proxy for these would just reintroduce the calibration
  gating failure mode above.

What this module does instead: compose three diagnostics that ARE already
computed daily and individually validated for their own narrow purpose --
`risk_mechanism_classifier.classify_risk_mechanism` (regime-in-distribution /
crash detection), `signal_alignment.build_signal_alignment` (cross-model
prediction disagreement), and `ops_health`'s data-quality sub-statuses (panel
staleness / sync) -- into a coarse TRUST / SHADOW_ONLY / ABSTAIN label using
simple boolean composition, no new thresholds to tune. Like
`risk_mechanism_classifier.py`, this is diagnostic and shadow-logging only:
its output must never be read by any function that computes
`target_weights`, `target_shares`, `execution_regime`, or `base_regime`.
Promoting it to influence weights requires the same bar as every other
candidate in this codebase: an out-of-sample backtest showing it actually
helps, run via `scripts/evaluate/evaluate_model_trust_gate.py` once the
shadow log (`results/strategy_trust_shadow_log.jsonl`) has accumulated
enough history -- do not wire this into weights before that evaluation
exists and passes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TRUST_LEVELS = ("TRUST", "SHADOW_ONLY", "ABSTAIN")

# risk_mechanism values that mean today's regime is the kind this codebase
# has repeatedly found hardest to model reliably (acute crash, or a
# persistent drawdown regime that historically triggers whipsaw when acted
# on -- see risk_mechanism_regime_overlay_rejected_20260801).
UNCERTAIN_REGIME_MECHANISMS = frozenset({"FAST_CRASH", "PERSISTENT_DRAWDOWN"})

# signal_alignment.alignment values that indicate the model ensemble itself
# disagrees on direction today.
DISAGREEMENT_ALIGNMENTS = frozenset({"mixed", "conflicted", "divergent"})

# ops_health sub-report statuses treated as "not ok". Deliberately excludes
# the top-level ops_health["status"] and ops_health["system_resources"] --
# see module docstring.
DEGRADED_DATA_STATUSES = frozenset({"warning", "degraded", "error", "critical"})


def _sub_status(ops_health: dict[str, Any], key: str) -> str:
    section = ops_health.get(key)
    if not isinstance(section, dict):
        return "unknown"
    return str(section.get("status") or "unknown")


def classify_strategy_trust(
    risk_mechanism: dict[str, Any],
    signal_alignment: dict[str, Any],
    ops_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify today into TRUST / SHADOW_ONLY / ABSTAIN.

    Args:
        risk_mechanism: today's `classify_risk_mechanism(...)` output.
        signal_alignment: today's `build_signal_alignment(...)` output.
        ops_health: today's ops_health report, or None if unavailable. Only
            `module_health`, `feature_table_sync`, and
            `external_data_freshness` sub-statuses are read (see module
            docstring for why `system_resources`/top-level `status` are
            excluded).

    Rule (simple boolean composition, no new tunable thresholds):
        ABSTAIN: any of the three data-quality sub-statuses report an
            outright problem the daily pipeline itself flags as
            warning-or-worse. This is a floor on data trustworthiness, not a
            market-condition judgement.
        SHADOW_ONLY: regime is FAST_CRASH/PERSISTENT_DRAWDOWN, OR the model
            ensemble itself disagrees on direction today (signal_alignment
            not aligned). Either condition means today's output is exactly
            the kind this codebase's history says to log but not act on
            further without OOS evidence.
        TRUST: otherwise.
    """
    ops_health = ops_health or {}
    mechanism = str(risk_mechanism.get("mechanism") or "")
    alignment = str(signal_alignment.get("alignment") or "")
    divergent_sources = signal_alignment.get("divergent_sources") or []

    module_health_status = _sub_status(ops_health, "module_health")
    feature_table_sync_status = _sub_status(ops_health, "feature_table_sync")
    external_freshness_status = _sub_status(ops_health, "external_data_freshness")

    data_quality_problem = (
        module_health_status in DEGRADED_DATA_STATUSES
        or feature_table_sync_status in DEGRADED_DATA_STATUSES
        or external_freshness_status in DEGRADED_DATA_STATUSES
    )
    uncertain_regime = mechanism in UNCERTAIN_REGIME_MECHANISMS
    ensemble_disagrees = alignment in DISAGREEMENT_ALIGNMENTS or bool(divergent_sources)

    if data_quality_problem:
        trust_level = "ABSTAIN"
    elif uncertain_regime or ensemble_disagrees:
        trust_level = "SHADOW_ONLY"
    else:
        trust_level = "TRUST"

    reasons: list[str] = [f"risk_mechanism={mechanism}", f"signal_alignment={alignment}"]
    if uncertain_regime:
        reasons.append(f"regime {mechanism} is a historically hard-to-model mechanism")
    if ensemble_disagrees:
        reasons.append(
            f"model ensemble disagrees on direction (alignment={alignment}, "
            f"divergent_sources={divergent_sources})"
        )
    if data_quality_problem:
        reasons.append(
            "data-quality sub-status not ok: "
            f"module_health={module_health_status} "
            f"feature_table_sync={feature_table_sync_status} "
            f"external_data_freshness={external_freshness_status}"
        )

    return {
        "trust_level": trust_level,
        "reasons": reasons,
        "components": {
            "risk_mechanism": mechanism,
            "signal_alignment": alignment,
            "divergent_sources": divergent_sources,
            "module_health_status": module_health_status,
            "feature_table_sync_status": feature_table_sync_status,
            "external_data_freshness_status": external_freshness_status,
            "uncertain_regime": uncertain_regime,
            "ensemble_disagrees": ensemble_disagrees,
            "data_quality_problem": data_quality_problem,
        },
    }


def append_strategy_trust_shadow_log(
    log_path: Path,
    result: dict[str, Any],
    *,
    date: str,
) -> None:
    """Append one day's trust classification to a JSON-lines shadow log,
    idempotent per date (mirrors
    `risk_mechanism_classifier.append_risk_mechanism_shadow_log`).
    Measurement-only: does not change target_weights or execution_regime.
    This log is the prerequisite for
    `scripts/evaluate/evaluate_model_trust_gate.py`'s OOS evaluation -- do
    not wire this module's output into weights before that evaluation
    exists and passes.
    """
    row = {
        "date": date,
        "trust_level": result.get("trust_level"),
        "reasons": result.get("reasons"),
        "components": result.get("components"),
    }
    rows: list[dict[str, Any]] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if existing.get("date") != row["date"]:
                rows.append(existing)
    rows.append(row)
    rows.sort(key=lambda r: r.get("date", ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
