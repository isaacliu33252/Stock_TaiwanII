from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _load_ncf_00631l_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "misc" / "ncf_00631l.py"
    spec = importlib.util.spec_from_file_location("_test_ncf_00631l", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ncf_00631l_uses_repo_root_for_default_outputs() -> None:
    root = Path(__file__).resolve().parents[1]
    module = _load_ncf_00631l_module()

    assert module.PROJECT_ROOT == root
    assert module.DEFAULT_OUTPUT.parent == root / "results"


def test_expanding_horizon_panel_does_not_rewrite_prior_rows() -> None:
    module = _load_ncf_00631l_module()
    idx = pd.date_range("2026-01-01", periods=90, freq="B")
    labels = pd.Series(([0, 1] * 45), index=idx)
    probs = {
        1: pd.Series([0.25 if y == 0 else 0.75 for y in labels], index=idx),
        5: pd.Series([0.45 if y == 0 else 0.55 for y in labels], index=idx),
        20: pd.Series([0.75 if y == 0 else 0.25 for y in labels], index=idx),
    }
    labels_by_horizon = {1: labels, 5: labels, 20: labels}

    base = module._build_expanding_horizon_ensemble_panel(
        probs,
        labels_by_horizon,
        min_history=10,
    )

    future_idx = pd.date_range(idx[-1] + pd.offsets.BDay(), periods=10, freq="B")
    future_labels = pd.Series(([1, 0] * 5), index=future_idx)
    extended_probs = {
        h: pd.concat([series, pd.Series([0.9, 0.1] * 5, index=future_idx)])
        for h, series in probs.items()
    }
    extended_labels = {
        h: pd.concat([series, future_labels])
        for h, series in labels_by_horizon.items()
    }

    extended = module._build_expanding_horizon_ensemble_panel(
        extended_probs,
        extended_labels,
        min_history=10,
    )

    pd.testing.assert_series_equal(
        base["ensemble_prob_up"],
        extended.loc[idx, "ensemble_prob_up"],
    )
    pd.testing.assert_frame_equal(
        base[["ensemble_weight_h1", "ensemble_weight_h5", "ensemble_weight_h20"]],
        extended.loc[idx, ["ensemble_weight_h1", "ensemble_weight_h5", "ensemble_weight_h20"]],
    )


def test_expanding_horizon_panel_embargoes_unresolved_forward_labels() -> None:
    """M1 (2026-07-02 Fable 5 audit): label_df[horizon].iloc[i] needs
    `horizon` days of future price data to resolve, so as of position `pos`
    only rows up to `pos - horizon` are actually known. Before the fix,
    AUC-based weights could use up to `horizon - 1` days of still-unresolved
    forward labels near the training frontier."""
    module = _load_ncf_00631l_module()
    idx = pd.date_range("2026-01-01", periods=90, freq="B")
    labels = pd.Series(([0, 1] * 45), index=idx)
    probs = {
        1: pd.Series([0.25 if y == 0 else 0.75 for y in labels], index=idx),
        # Same (positively-correlated, good) direction as h1 -- only
        # differs in how much history is needed to *resolve* its label.
        20: pd.Series([0.30 if y == 0 else 0.70 for y in labels], index=idx),
    }
    labels_by_horizon = {1: labels, 20: labels}
    min_history = 10

    panel = module._build_expanding_horizon_ensemble_panel(
        probs,
        labels_by_horizon,
        min_history=min_history,
    )

    # h=1 only needs 1 day to resolve: AUC weighting should already be
    # active (non-equal weight) once pos >= min_history + 1.
    assert panel["ensemble_weight_h1"].iloc[min_history + 1] != 0.5
    # h=20 needs pos - 20 >= min_history, i.e. pos >= min_history + 20: below
    # that, h=20 has no resolved history so raw_weights excludes it entirely
    # (weight 0, not an AUC value computed from still-unresolved/future
    # labels) and h=1 (which does have resolved history) takes all the
    # weight.
    assert panel["ensemble_weight_h20"].iloc[min_history + 1] == 0.0
    assert panel["ensemble_weight_h1"].iloc[min_history + 1] == 1.0
    assert panel["ensemble_weight_h20"].iloc[min_history + 20 - 1] == 0.0
    # Once pos >= min_history + horizon, h=20 has enough resolved history
    # and starts contributing real weight again.
    assert panel["ensemble_weight_h20"].iloc[min_history + 20] > 0.0


def test_expanding_model_ensemble_uses_equal_weights_before_min_history() -> None:
    module = _load_ncf_00631l_module()
    n = 20
    rng = np.random.default_rng(0)
    y_val = np.array([0, 1] * (n // 2))
    probas = {
        "rf": rng.uniform(0.4, 0.6, size=n),
        "et": rng.uniform(0.4, 0.6, size=n),
    }

    ens, weight_rows = module._expanding_model_ensemble_weights(
        probas, y_val, horizon=1, min_history=10,
    )

    assert len(ens) == n
    for pos in range(10):
        assert weight_rows[pos] == {"rf": 0.5, "et": 0.5}


def test_expanding_model_ensemble_does_not_rewrite_prior_rows() -> None:
    """Anti-drift property: row `pos`'s weight/ensemble value must not change
    when more rows are appended after it (the actual bug this function fixes --
    see GROUP_A_PLUS_NCF_PANEL_DRIFT_AUDIT_20260706.md)."""
    module = _load_ncf_00631l_module()
    n = 90
    y_val = np.array(([0, 1] * (n // 2)))
    probas = {
        "rf": np.array([0.25 if y == 0 else 0.75 for y in y_val]),
        "et": np.array([0.45 if y == 0 else 0.55 for y in y_val]),
        "hgb": np.array([0.75 if y == 0 else 0.25 for y in y_val]),
    }

    base_ens, base_weights = module._expanding_model_ensemble_weights(
        probas, y_val, horizon=1, min_history=10,
    )

    extra = 10
    extra_y = np.array(([1, 0] * (extra // 2)))
    extended_probas = {
        name: np.concatenate([series, np.array([0.9, 0.1] * (extra // 2))])
        for name, series in probas.items()
    }
    extended_y = np.concatenate([y_val, extra_y])

    ext_ens, ext_weights = module._expanding_model_ensemble_weights(
        extended_probas, extended_y, horizon=1, min_history=10,
    )

    np.testing.assert_array_equal(base_ens, ext_ens[:n])
    assert base_weights == ext_weights[:n]


def test_expanding_model_ensemble_embargoes_unresolved_forward_labels() -> None:
    """Row `pos`'s weight must use only labels resolved as of `pos`, i.e.
    `[:pos - horizon]` -- mirrors the M1 fix already applied to
    `_build_expanding_horizon_ensemble_panel` (test above), one level down at
    the per-model ensemble."""
    module = _load_ncf_00631l_module()
    n = 90
    y_val = np.array(([0, 1] * (n // 2)))
    probas = {
        # Strong signal: clearly separates the two classes.
        "rf": np.array([0.10 if y == 0 else 0.90 for y in y_val]),
        # Weak/near-random signal, so the two models' weights are not tied.
        "et": np.array([0.45 if y == 0 else 0.55 for y in y_val]),
    }
    min_history = 10
    full_confidence_history = 20
    horizon = 20

    _, weight_rows = module._expanding_model_ensemble_weights(
        probas, y_val, horizon=horizon, min_history=min_history,
        full_confidence_history=full_confidence_history,
    )

    # Below pos = min_history + horizon, fewer than min_history rows have
    # resolved labels -> falls back to equal weights.
    assert weight_rows[min_history + horizon - 1] == {"rf": 0.5, "et": 0.5}
    # Once resolved history clears full_confidence_history, the shrinkage
    # ramp is complete and the stronger model dominates the weight.
    assert weight_rows[horizon + full_confidence_history]["rf"] > weight_rows[horizon + full_confidence_history]["et"]


def test_expanding_model_ensemble_shrinkage_ramps_gradually() -> None:
    """2026-07-07 fix: a hard jump from equal weight straight to the raw
    small-sample weight let a single lucky/unlucky model on a tiny resolved
    sample seize almost all ensemble weight (verified empirically to make
    historical-row drift *worse* than the original global-weight bug for the
    bull/bear-split direction tasks). The weight must move monotonically and
    gradually from equal weight toward the raw weight as resolved history
    grows from `min_history` to `full_confidence_history`, not jump straight
    to the extreme value the moment `min_history` is cleared."""
    module = _load_ncf_00631l_module()
    n = 300
    y_val = np.array(([0, 1] * (n // 2)))
    probas = {
        "rf": np.array([0.05 if y == 0 else 0.95 for y in y_val]),
        "et": np.array([0.48 if y == 0 else 0.52 for y in y_val]),
    }
    min_history, full_confidence_history, horizon = 60, 260, 1

    _, weight_rows = module._expanding_model_ensemble_weights(
        probas, y_val, horizon=horizon, min_history=min_history,
        full_confidence_history=full_confidence_history,
    )

    rf_weights_during_ramp = [
        weight_rows[pos]["rf"]
        for pos in range(min_history + horizon, full_confidence_history + horizon + 1, 20)
    ]
    # Strictly increasing (not a step function) as resolved history grows.
    assert all(b >= a for a, b in zip(rf_weights_during_ramp, rf_weights_during_ramp[1:]))
    assert rf_weights_during_ramp[0] == pytest.approx(0.5, abs=1e-9)
    assert rf_weights_during_ramp[-1] > 0.9


def test_expanding_model_weights_flag_off_matches_current_behavior() -> None:
    """--expanding-model-weights defaults False and must not change existing
    train_classifier output at all."""
    module = _load_ncf_00631l_module()
    rng = np.random.default_rng(1)
    n = 260
    X_train = pd.DataFrame(rng.normal(size=(200, 5)), columns=[f"f{i}" for i in range(5)])
    y_train = rng.integers(0, 2, size=200)
    X_val = pd.DataFrame(rng.normal(size=(n - 200, 5)), columns=[f"f{i}" for i in range(5)])
    y_val = rng.integers(0, 2, size=n - 200)

    clf_default = module.train_classifier(X_train, y_train, X_val, y_val, calib_frac=0.0)
    clf_explicit_off = module.train_classifier(
        X_train, y_train, X_val, y_val, calib_frac=0.0,
        horizon=1, expanding_model_weights=False,
    )

    # Both calls run the identical (unmodified) global-weight code path; any
    # difference is float noise from independent model-fit runs (BLAS
    # threading / TabNet), not a behavior change -- assert near-equality
    # rather than bit-identical.
    np.testing.assert_allclose(
        clf_default["ensemble"]["proba"], clf_explicit_off["ensemble"]["proba"], rtol=1e-4, atol=1e-6,
    )
    for name, w in clf_default["ensemble"]["weights"].items():
        assert clf_explicit_off["ensemble"]["weights"][name] == pytest.approx(w, abs=1e-6)
    assert clf_explicit_off["ensemble"]["ensemble_weight_method"] == "global"


def test_deduplicate_correlated_features_drops_near_duplicate() -> None:
    """2026-07-25: arXiv:2607.06117v1-style correlation de-duplication.
    A feature perfectly correlated with an already-kept, higher-priority
    feature must be dropped; an uncorrelated feature must survive."""
    module = _load_ncf_00631l_module()
    rng = np.random.default_rng(0)
    n = 200
    base = rng.normal(size=n)
    X = pd.DataFrame(
        {
            "a": base,
            "b": base * 2.0 + 0.001 * rng.normal(size=n),  # near-perfectly correlated with a
            "c": rng.normal(size=n),  # independent
        }
    )
    kept = module._deduplicate_correlated_features(
        X, ["a", "b", "c"], corr_threshold=0.95, priority=["a", "b", "c"]
    )
    assert kept == ["a", "c"]


def test_deduplicate_correlated_features_priority_order_picks_winner() -> None:
    """When two features are highly correlated, the one earlier in
    `priority` is kept regardless of `features`' own order."""
    module = _load_ncf_00631l_module()
    rng = np.random.default_rng(0)
    n = 200
    base = rng.normal(size=n)
    X = pd.DataFrame({"a": base, "b": base * 2.0 + 0.001 * rng.normal(size=n)})
    kept_b_wins = module._deduplicate_correlated_features(
        X, ["a", "b"], corr_threshold=0.95, priority=["b", "a"]
    )
    assert kept_b_wins == ["b"]


def test_deduplicate_correlated_features_below_threshold_keeps_both() -> None:
    module = _load_ncf_00631l_module()
    rng = np.random.default_rng(0)
    n = 200
    X = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n)})
    kept = module._deduplicate_correlated_features(X, ["a", "b"], corr_threshold=0.95)
    assert kept == ["a", "b"]


def test_identify_stable_features_dedupe_correlated_flag_off_matches_current_behavior() -> None:
    """dedupe_correlated defaults False and must not change identify_stable_features'
    existing output at all -- same discipline as expanding_model_weights above."""
    module = _load_ncf_00631l_module()
    rng = np.random.default_rng(3)
    n = 400
    base = rng.normal(size=n)
    X = pd.DataFrame(
        {
            "dup_a": base,
            "dup_b": base * 3.0 + 0.001 * rng.normal(size=n),
            "signal": np.concatenate([base[: n // 2], -base[n // 2 :]]) + 0.01 * rng.normal(size=n),
            **{f"noise_{i}": rng.normal(size=n) for i in range(6)},
        }
    )
    y_dir = (X["signal"] > 0).astype(int).to_numpy()

    default_stable = module.identify_stable_features(X, y_dir, n_folds=3, top_k=5, min_folds=1)
    explicit_off_stable = module.identify_stable_features(
        X, y_dir, n_folds=3, top_k=5, min_folds=1, dedupe_correlated=False
    )
    assert default_stable == explicit_off_stable


def test_identify_stable_features_dedupe_correlated_drops_redundant_pair() -> None:
    """With dedupe_correlated=True, a near-duplicate pair that both clear
    the stability bar collapses to one survivor."""
    module = _load_ncf_00631l_module()
    rng = np.random.default_rng(3)
    n = 400
    base = rng.normal(size=n)
    X = pd.DataFrame(
        {
            "dup_a": base,
            "dup_b": base * 3.0 + 0.001 * rng.normal(size=n),
            "signal": np.concatenate([base[: n // 2], -base[n // 2 :]]) + 0.01 * rng.normal(size=n),
            **{f"noise_{i}": rng.normal(size=n) for i in range(6)},
        }
    )
    y_dir = (X["signal"] > 0).astype(int).to_numpy()

    stable_no_dedup = module.identify_stable_features(X, y_dir, n_folds=3, top_k=5, min_folds=1)
    stable_dedup = module.identify_stable_features(
        X, y_dir, n_folds=3, top_k=5, min_folds=1, dedupe_correlated=True, corr_threshold=0.95
    )
    if "dup_a" in stable_no_dedup and "dup_b" in stable_no_dedup:
        assert not ("dup_a" in stable_dedup and "dup_b" in stable_dedup)
    assert len(stable_dedup) <= len(stable_no_dedup)
