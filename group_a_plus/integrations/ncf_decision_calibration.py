"""Shadow-only direction_confidence / decision_confidence split for NCF.

Motivated by arXiv:2601.07852's utility-weighted-calibration philosophy
(model confidence should be calibrated against decision loss, not just
prediction accuracy) applied to a specific gap the user identified: the
NCF panel's existing `confidence` field measures only direction/magnitude
agreement across horizons, not whether a specific A21.18 overlay action
(trimming 00631L into 0050) is actually worth its transaction cost and
missed-rebound risk relative to KEEP.

**Phase 1, shadow-only, does not touch any weight** (per the user's own
scoping). Two fields:

- `direction_confidence`: the existing composite-confidence formula
  (consensus*0.4 + magnitude*0.4 + spread*0.2, see
  `scripts/evaluate/evaluate_a2118_composite_confidence_sweep.py::_composite_confidence`,
  itself documented there as recomputing an older live-JSON formula) --
  purely about H1/H5/H20 direction agreement, unaware of cost or utility.
- `decision_confidence`: a percentile-rank proxy against pooled
  `predicted_regret` values, explicitly NOT an outcome-calibrated
  probability.

Closed Phase 2 probability-calibration attempt: `scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py`
now exports a `calibration_pairs` field per window (added 2026-07-27) --
every (date, action) pair with sufficient training history gets both its
`predicted_regret` (from the same expanding-window ridge model that drives
the live shadow) and its `realized_regret` (the label the model was
trained against). This is a much larger, unbiased sample than the 46
*selected* non-KEEP days Phase 1 was limited to -- every date x action
combination is included, not just the days the regret-argmax happened to
pick. `fit_regret_calibration()` bins `predicted_regret` into quantiles
*within the `tuning_window` bucket only* (matching this project's existing
in-sample/out-of-sample split -- see `DEFAULT_WINDOWS` in that evaluator)
and computes each bin's empirical `P(realized_regret > 0)`. This is
deliberately a simple, auditable binned-empirical-rate model (consistent
with this evaluator's own "First version deliberately avoids neural
networks" design choice), not a parametric fit. However, CAP10 empirical
calibration failed out-of-sample validation and the later
`total_risk_score` regime-conditioned calibration also failed to improve it
(documented OOS error worsened from 0.129 to 0.158). Therefore this path is
formally closed as `closed_failed_oos`: it may be used only to reproduce
research diagnostics, not as production `decision_confidence`, not as a
promotion gate, and not as a target-weight or rebalance input.

Sample-size caveat (Phase 1, retained for the fallback path): the rank-
proxy distribution has only 46 candidate decisions total across all 7
backtest windows as of 2026-07-26 (see
`GROUP_A_PLUS_DFL_ADVISORY_STALE_INPUT_FIX_20260726.md`), most for the
CAP10 action. Phase 2's calibration_pairs-based approach does not have
this limitation (thousands of pairs), but see
`GROUP_A_PLUS_DFL_ACTION_VALUE_CALIBRATION_PHASE2_20260727.md` for the
out-of-sample validation result before trusting it -- a large in-sample
fit is not the same as a validated one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from group_a_plus.paths import PROJECT_ROOT

DEFAULT_DFL_SHADOW_PATH = PROJECT_ROOT / "results" / "a2118_decision_focused_action_shadow_dfl_main_latest.json"
CALIBRATION_MODEL_GOVERNANCE = {
    "status": "closed_failed_oos",
    "closed_at": "2026-07-29",
    "closed_reason": (
        "Empirical realized-regret probability calibration failed OOS validation; "
        "the total_risk_score regime-conditioned attempt worsened error from 0.129 to 0.158."
    ),
    "decision_confidence_contract": "predicted_regret_percentile_rank_proxy_not_calibrated_probability",
    "calibration_model_default_enabled": False,
    "promotion_allowed": False,
    "training_allowed": False,
    "target_weight_change_allowed": False,
    "auto_rebalance_allowed": False,
    "live_gate_allowed": False,
}


def calibration_governance_summary() -> dict[str, Any]:
    return dict(CALIBRATION_MODEL_GOVERNANCE)


@dataclass(frozen=True)
class DecisionCalibrationSnapshot:
    as_of: str
    direction_confidence: float | None
    decision_confidence: float | None
    action: str | None
    predicted_regret: float | None
    historical_candidate_count: int
    basis: str
    extra: dict[str, Any] = field(default_factory=dict)
    calibration_method: str = "predicted_regret_percentile_rank_proxy"

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "direction_confidence": self.direction_confidence,
            "decision_confidence": self.decision_confidence,
            "action": self.action,
            "predicted_regret": self.predicted_regret,
            "historical_candidate_count": self.historical_candidate_count,
            "basis": self.basis,
            "extra": self.extra,
            "calibration_method": self.calibration_method,
            "governance": calibration_governance_summary(),
        }


def direction_confidence_from_panel_row(row: dict[str, Any] | pd.Series) -> float | None:
    """Composite direction/magnitude confidence for a single NCF panel row.

    Reuses `evaluate_a2118_composite_confidence_sweep.py`'s formula
    verbatim (consensus*0.4 + magnitude*0.4 + spread*0.2) -- kept as a
    small, independently-inlined copy rather than an import, consistent
    with that script's own precedent (it documents itself as recomputing
    an older live-JSON formula panel-side; this is a third, equally small
    restatement of the same well-established formula, not new drift risk).
    """
    try:
        probs = np.array(
            [float(row["prob_up_h1"]), float(row["prob_up_h5"]), float(row["prob_up_h20"])],
            dtype=float,
        )
        magnitude = float(row["prob_magnitude"])
    except (KeyError, TypeError, ValueError):
        return None
    directions_up = int((probs > 0.5).sum())
    max_votes = max(directions_up, 3 - directions_up)
    consensus = max_votes / 3.0
    spread_conf = max(1.0 - float(probs.std()) * 4.0, 0.0)
    confidence = consensus * 0.4 + magnitude * 0.4 + spread_conf * 0.2
    return float(np.clip(confidence, 0.1, 1.0))


def load_historical_regret_distribution(dfl_shadow_path: Path = DEFAULT_DFL_SHADOW_PATH) -> dict[str, list[float]]:
    """Per-action list of historical `predicted_regret` values, pooled
    across every window in the DFL shadow result. Source of the ranking
    distribution for `decision_confidence` -- see module docstring for why
    this is a rank proxy, not an outcome-calibrated probability.
    """
    if not dfl_shadow_path.exists():
        return {}
    import json

    payload = json.loads(dfl_shadow_path.read_text(encoding="utf-8"))
    by_action: dict[str, list[float]] = {}
    for window in payload.get("results", []) or []:
        for decision in window.get("non_keep_decisions", []) or []:
            action = decision.get("action")
            regret = decision.get("predicted_regret")
            if action and action != "KEEP" and regret is not None:
                by_action.setdefault(str(action), []).append(float(regret))
    return by_action


def decision_confidence_from_regret(
    action: str | None,
    predicted_regret: float | None,
    historical_by_action: dict[str, list[float]],
) -> float | None:
    """Percentile rank of `predicted_regret` against this action's
    historical predicted-regret distribution. `None` when action is KEEP
    (regret is defined relative to KEEP, so KEEP has no meaningful rank) or
    when there is no historical distribution for this action yet.
    """
    if action is None or action == "KEEP" or predicted_regret is None:
        return None
    distribution = historical_by_action.get(action)
    if not distribution:
        return None
    arr = np.asarray(distribution, dtype=float)
    rank = float((arr <= predicted_regret).mean())
    return rank


def load_calibration_pairs(dfl_shadow_path: Path = DEFAULT_DFL_SHADOW_PATH) -> pd.DataFrame:
    """Long-format (date, action, predicted_regret, realized_regret, bucket,
    window) table pooled across every window's `calibration_pairs` export
    (see `evaluate_a2118_decision_focused_action_shadow.py::evaluate_window`).

    Unlike `load_historical_regret_distribution` (46 *selected* non-KEEP
    days), this covers every (date, action) pair with sufficient training
    history regardless of whether the regret-argmax picked it -- the input
    to Phase 2's real calibration, not the Phase 1 rank proxy.
    """
    columns = ["date", "action", "predicted_regret", "realized_regret", "bucket", "window"]
    if not dfl_shadow_path.exists():
        return pd.DataFrame(columns=columns)
    import json

    payload = json.loads(dfl_shadow_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for window in payload.get("results", []) or []:
        bucket = window.get("bucket")
        label = window.get("label")
        for pair in window.get("calibration_pairs", []) or []:
            rows.append({**pair, "bucket": bucket, "window": label})
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


def calibration_pair_readiness_summary(dfl_shadow_path: Path = DEFAULT_DFL_SHADOW_PATH) -> dict[str, Any]:
    """Machine-readable check that the DFL shadow artifact carries the
    realized-regret labels needed for outcome probability calibration.

    This deliberately does not bless the closed_failed_oos calibration model
    for production use. It only prevents a stale/pre-2026-07-27 DFL result
    from looking equivalent to one that actually contains the realized-label
    export (`calibration_pairs`).
    """
    if not dfl_shadow_path.exists():
        return {
            "status": "missing_dfl_shadow",
            "dfl_shadow_path": str(dfl_shadow_path),
            "window_count": 0,
            "windows_with_calibration_pairs_key": 0,
            "total_pairs": 0,
            "pairs_with_realized_regret": 0,
            "pairs_with_total_risk_score": 0,
            "actions": {},
            "recommended_action": "regenerate_dfl_shadow_with_current_evaluator",
        }
    import json

    payload = json.loads(dfl_shadow_path.read_text(encoding="utf-8"))
    windows = payload.get("results", []) or []
    windows_with_key = 0
    total_pairs = 0
    realized_pairs = 0
    total_risk_pairs = 0
    actions: dict[str, int] = {}
    missing_realized_examples: list[dict[str, Any]] = []
    for window in windows:
        if not isinstance(window, dict):
            continue
        if "calibration_pairs" in window:
            windows_with_key += 1
        for pair in window.get("calibration_pairs", []) or []:
            if not isinstance(pair, dict):
                continue
            total_pairs += 1
            action = str(pair.get("action", "unknown"))
            actions[action] = actions.get(action, 0) + 1
            if pair.get("realized_regret") is not None:
                realized_pairs += 1
            elif len(missing_realized_examples) < 5:
                missing_realized_examples.append(
                    {
                        "window": window.get("label"),
                        "date": pair.get("date"),
                        "action": pair.get("action"),
                    }
                )
            if pair.get("total_risk_score") is not None:
                total_risk_pairs += 1

    if total_pairs <= 0:
        status = "missing_calibration_pairs"
        recommended_action = "regenerate_dfl_shadow_with_current_evaluator"
    elif realized_pairs < total_pairs:
        status = "partial_realized_labels"
        recommended_action = "inspect_dfl_calibration_pairs_missing_realized_regret"
    else:
        status = "available"
        recommended_action = "no_data_export_action_needed"

    return {
        "status": status,
        "dfl_shadow_path": str(dfl_shadow_path),
        "window_count": int(len(windows)),
        "windows_with_calibration_pairs_key": int(windows_with_key),
        "total_pairs": int(total_pairs),
        "pairs_with_realized_regret": int(realized_pairs),
        "pairs_with_total_risk_score": int(total_risk_pairs),
        "actions": actions,
        "missing_realized_examples": missing_realized_examples,
        "recommended_action": recommended_action,
    }


GLOBAL_REGIME_LABEL = "__all__"


def _regime_label(value: float | None, regime_edges: tuple[float, ...] | None) -> str:
    """Bucket a `total_risk_score`-like value into a label matching this
    project's existing risk-tier vocabulary (see the >=6/7/8/9
    `total_risk_score` gate thresholds already in production, and
    `tail_conformal.py`'s low/elevated/severe risk buckets). Default edges
    (6.0, 9.0) yield 3 buckets: low (<6), elevated ([6,9)), severe (>=9).
    """
    if value is None or not np.isfinite(value):
        return "unknown"
    edges = regime_edges or (6.0, 9.0)
    idx = int(np.digitize([float(value)], edges)[0])
    names = ["low", "elevated", "severe"][: len(edges) + 1]
    return names[idx] if idx < len(names) else names[-1]


@dataclass(frozen=True)
class RegretCalibrationModel:
    """Per-action (optionally per-regime) empirical win-rate calibration,
    fit on binned `predicted_regret` from a training subset only (see
    `fit_regret_calibration`).

    `by_action[action][regime_label]` holds `bin_edges` (strictly
    increasing, length n_bins+1, computed from *training* quantiles only
    within that regime -- no leakage), `win_rates` (fraction of training
    pairs in that bin with `realized_regret > 0`), and `counts` (training
    sample size per bin). `regime_label` is `GLOBAL_REGIME_LABEL` when
    `regime_column` was not used (single pooled calibration, Phase 2's
    original behavior).
    """

    by_action: dict[str, dict[str, dict[str, Any]]]
    n_bins: int
    fit_bucket: str
    fit_sample_size: int
    regime_column: str | None = None
    regime_edges: tuple[float, ...] | None = None


def _fit_one_bin_set(values: np.ndarray, realized: np.ndarray, *, n_bins: int, min_bin_size: int) -> dict[str, Any] | None:
    if len(values) < min_bin_size * 2:
        return None
    edges = np.unique(np.quantile(values, np.linspace(0.0, 1.0, n_bins + 1)))
    if len(edges) < 3:
        return None
    bin_idx = np.clip(np.digitize(values, edges[1:-1], right=False), 0, len(edges) - 2)
    win_rates: list[float | None] = []
    counts: list[int] = []
    for b in range(len(edges) - 1):
        mask = bin_idx == b
        counts.append(int(mask.sum()))
        win_rates.append(float((realized[mask] > 0.0).mean()) if mask.any() else None)
    return {"bin_edges": edges.tolist(), "win_rates": win_rates, "counts": counts}


def fit_regret_calibration(
    pairs: pd.DataFrame,
    *,
    fit_bucket: str = "tuning_window",
    n_bins: int = 5,
    min_bin_size: int = 20,
    regime_column: str | None = None,
    regime_edges: tuple[float, ...] | None = None,
) -> RegretCalibrationModel:
    """Fit a simple binned-empirical-rate calibration per action.

    Deliberately not a parametric model (isotonic/logistic) -- consistent
    with this project's preference for simple, auditable methods over
    models that are easy to overfit with a modest sample. Bin edges and
    win-rates come *only* from `fit_bucket` rows (default `tuning_window`,
    this project's existing in-sample bucket label) so that any subsequent
    out-of-sample check is a genuine one, not circular.

    `regime_column` (optional, e.g. `"total_risk_score"`): when given, fits
    a *separate* set of bins per regime bucket (see `_regime_label`)
    instead of one pooled calibration -- motivated by the 2026-07-27
    finding that a single global CAP10 calibration does not transfer
    out-of-sample (direction right, magnitude wrong). A regime/action
    combination with fewer than `min_bin_size * 2` training rows is simply
    omitted (no fitted bins), matching the pooled path's own behavior.
    """
    if pairs.empty or "bucket" not in pairs.columns:
        return RegretCalibrationModel(
            by_action={},
            n_bins=n_bins,
            fit_bucket=fit_bucket,
            fit_sample_size=0,
            regime_column=regime_column,
            regime_edges=regime_edges,
        )
    train = pairs[pairs["bucket"] == fit_bucket]
    by_action: dict[str, dict[str, dict[str, Any]]] = {}
    for action, group in train.groupby("action"):
        by_regime: dict[str, dict[str, Any]] = {}
        if regime_column and regime_column in group.columns:
            labels = group[regime_column].apply(lambda v: _regime_label(v, regime_edges))
            for regime_label, sub in group.groupby(labels):
                values = sub["predicted_regret"].to_numpy(dtype=float)
                realized = sub["realized_regret"].to_numpy(dtype=float)
                fitted = _fit_one_bin_set(values, realized, n_bins=n_bins, min_bin_size=min_bin_size)
                if fitted is not None:
                    by_regime[str(regime_label)] = fitted
        else:
            values = group["predicted_regret"].to_numpy(dtype=float)
            realized = group["realized_regret"].to_numpy(dtype=float)
            fitted = _fit_one_bin_set(values, realized, n_bins=n_bins, min_bin_size=min_bin_size)
            if fitted is not None:
                by_regime[GLOBAL_REGIME_LABEL] = fitted
        if by_regime:
            by_action[str(action)] = by_regime
    return RegretCalibrationModel(
        by_action=by_action,
        n_bins=n_bins,
        fit_bucket=fit_bucket,
        fit_sample_size=int(len(train)),
        regime_column=regime_column,
        regime_edges=regime_edges,
    )


def predict_calibrated_probability(
    action: str | None,
    predicted_regret: float | None,
    model: RegretCalibrationModel | None,
    *,
    regime_value: float | None = None,
) -> float | None:
    """Look up the calibrated `P(realized_regret > 0)` for this action's
    predicted_regret bin (within the matching regime bucket, if the model
    was fit with `regime_column`). `None` for KEEP, missing inputs, or an
    action/regime/bin the model has no data for -- callers should fall
    back to the Phase 1 rank proxy in that case. Deliberately does not fall
    back to a pooled/global bin when the specific regime bucket is missing
    data -- silently blending would hide exactly the regime-dependence gap
    this was built to test.
    """
    if model is None or action is None or action == "KEEP" or predicted_regret is None:
        return None
    by_regime = model.by_action.get(action)
    if not by_regime:
        return None
    regime_label = (
        _regime_label(regime_value, model.regime_edges) if model.regime_column else GLOBAL_REGIME_LABEL
    )
    entry = by_regime.get(regime_label)
    if not entry:
        return None
    edges = np.asarray(entry["bin_edges"], dtype=float)
    if len(edges) < 3:
        return None
    b = int(np.clip(np.digitize([float(predicted_regret)], edges[1:-1], right=False)[0], 0, len(edges) - 2))
    rate = entry["win_rates"][b]
    return float(rate) if rate is not None else None


def build_snapshot(
    *,
    as_of: str,
    ncf_panel_row: dict[str, Any] | pd.Series | None,
    dfl_action: str | None = None,
    dfl_predicted_regret: float | None = None,
    dfl_shadow_path: Path = DEFAULT_DFL_SHADOW_PATH,
    calibration_model: RegretCalibrationModel | None = None,
    dfl_total_risk_score: float | None = None,
) -> DecisionCalibrationSnapshot:
    direction_conf = direction_confidence_from_panel_row(ncf_panel_row) if ncf_panel_row is not None else None
    historical = load_historical_regret_distribution(dfl_shadow_path)
    candidate_count = sum(len(v) for v in historical.values())

    calibrated = predict_calibrated_probability(
        dfl_action, dfl_predicted_regret, calibration_model, regime_value=dfl_total_risk_score
    )
    if calibrated is not None:
        decision_conf = calibrated
        calibration_method = "empirical_realized_regret_calibration"
    else:
        decision_conf = decision_confidence_from_regret(dfl_action, dfl_predicted_regret, historical)
        calibration_method = "predicted_regret_percentile_rank_proxy"

    if dfl_action is None:
        basis = "no DFL candidate action available for this date"
    elif dfl_action == "KEEP":
        basis = "action is KEEP; decision_confidence undefined (regret is measured relative to KEEP)"
    elif calibrated is not None:
        regime_label = (
            _regime_label(dfl_total_risk_score, calibration_model.regime_edges)
            if calibration_model and calibration_model.regime_column
            else GLOBAL_REGIME_LABEL
        )
        entry = ((calibration_model.by_action.get(dfl_action) if calibration_model else None) or {}).get(
            regime_label, {}
        )
        basis = (
            f"decision_confidence is P(realized_regret > 0) from a {calibration_model.n_bins}-bin "
            f"empirical calibration fit on {calibration_model.fit_sample_size} {calibration_model.fit_bucket} "
            f"pairs (regime={regime_label}, this action/regime's bin n={entry.get('counts')}); "
            "closed_failed_oos research reproduction only, not a production calibrated probability"
        )
    elif decision_conf is None:
        basis = f"no historical predicted_regret distribution for action={dfl_action} yet"
    else:
        basis = (
            f"decision_confidence is a percentile rank of predicted_regret against "
            f"{len(historical.get(dfl_action, []))} historical {dfl_action} candidates "
            "(NOT an outcome-calibrated probability -- see module docstring)"
        )

    return DecisionCalibrationSnapshot(
        as_of=as_of,
        direction_confidence=direction_conf,
        decision_confidence=decision_conf,
        action=dfl_action,
        predicted_regret=dfl_predicted_regret,
        historical_candidate_count=candidate_count,
        basis=basis,
        extra={"historical_counts_by_action": {k: len(v) for k, v in historical.items()}},
        calibration_method=calibration_method,
    )
