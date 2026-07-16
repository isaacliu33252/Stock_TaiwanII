from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def _load_ncf_2330_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "ncf_2330.py"
    spec = importlib.util.spec_from_file_location("_test_ncf_2330", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_expanding_horizon_panel_does_not_rewrite_prior_rows() -> None:
    module = _load_ncf_2330_module()
    idx = pd.date_range("2026-01-01", periods=90, freq="B")
    labels = pd.Series(([0, 1] * 45), index=idx)
    probs = {
        1: pd.Series([0.25 if y == 0 else 0.75 for y in labels], index=idx),
        5: pd.Series([0.45 if y == 0 else 0.55 for y in labels], index=idx),
        20: pd.Series([0.75 if y == 0 else 0.25 for y in labels], index=idx),
    }
    labels_by_horizon = {1: labels, 5: labels, 20: labels}

    base = module._build_expanding_horizon_ensemble_panel(
        probs, labels_by_horizon, min_history=10,
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
        extended_probs, extended_labels, min_history=10,
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
    """M1 embargo fix, ported from ncf_00631l.py (2026-07-07): label_df[horizon]
    .iloc[i] needs `horizon` days of future price data to resolve, so as of
    position `pos` only rows up to `pos - horizon` are actually known. Before
    the fix, ncf_2330.py's own copy of this function (never patched alongside
    ncf_00631l.py on 2026-07-02) could use up to `horizon - 1` days of
    still-unresolved forward labels near the training frontier."""
    module = _load_ncf_2330_module()
    idx = pd.date_range("2026-01-01", periods=90, freq="B")
    labels = pd.Series(([0, 1] * 45), index=idx)
    probs = {
        1: pd.Series([0.25 if y == 0 else 0.75 for y in labels], index=idx),
        20: pd.Series([0.30 if y == 0 else 0.70 for y in labels], index=idx),
    }
    labels_by_horizon = {1: labels, 20: labels}
    min_history = 10

    panel = module._build_expanding_horizon_ensemble_panel(
        probs, labels_by_horizon, min_history=min_history,
    )

    assert panel["ensemble_weight_h1"].iloc[min_history + 1] != 0.5
    assert panel["ensemble_weight_h20"].iloc[min_history + 1] == 0.0
    assert panel["ensemble_weight_h1"].iloc[min_history + 1] == 1.0
    assert panel["ensemble_weight_h20"].iloc[min_history + 20 - 1] == 0.0
    assert panel["ensemble_weight_h20"].iloc[min_history + 20] > 0.0


def test_expanding_model_ensemble_uses_equal_weights_before_min_history() -> None:
    module = _load_ncf_2330_module()
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
    when more rows are appended after it."""
    module = _load_ncf_2330_module()
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
    module = _load_ncf_2330_module()
    n = 90
    y_val = np.array(([0, 1] * (n // 2)))
    probas = {
        "rf": np.array([0.10 if y == 0 else 0.90 for y in y_val]),
        "et": np.array([0.45 if y == 0 else 0.55 for y in y_val]),
    }
    min_history = 10
    full_confidence_history = 20
    horizon = 20

    _, weight_rows = module._expanding_model_ensemble_weights(
        probas, y_val, horizon=horizon, min_history=min_history,
        full_confidence_history=full_confidence_history,
    )

    assert weight_rows[min_history + horizon - 1] == {"rf": 0.5, "et": 0.5}
    assert weight_rows[horizon + full_confidence_history]["rf"] > weight_rows[horizon + full_confidence_history]["et"]


def test_expanding_model_ensemble_shrinkage_ramps_gradually() -> None:
    module = _load_ncf_2330_module()
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
    assert all(b >= a for a, b in zip(rf_weights_during_ramp, rf_weights_during_ramp[1:]))
    assert rf_weights_during_ramp[0] == pytest.approx(0.5, abs=1e-9)
    assert rf_weights_during_ramp[-1] > 0.9


def test_expanding_model_weights_flag_off_matches_current_behavior() -> None:
    """train_classifier's own default (expanding_model_weights=False) must be
    bit-for-bit unaffected -- only the CLI's parser.set_defaults flips the
    production script's behavior, not the function's own default."""
    module = _load_ncf_2330_module()
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

    np.testing.assert_allclose(
        clf_default["ensemble"]["proba"], clf_explicit_off["ensemble"]["proba"], rtol=1e-4, atol=1e-6,
    )
    for name, w in clf_default["ensemble"]["weights"].items():
        assert clf_explicit_off["ensemble"]["weights"][name] == pytest.approx(w, abs=1e-6)
    assert clf_explicit_off["ensemble"]["ensemble_weight_method"] == "global"


def test_expanding_model_weights_flag_on_changes_ensemble_weight_method() -> None:
    module = _load_ncf_2330_module()
    rng = np.random.default_rng(2)
    n = 260
    X_train = pd.DataFrame(rng.normal(size=(200, 5)), columns=[f"f{i}" for i in range(5)])
    y_train = rng.integers(0, 2, size=200)
    X_val = pd.DataFrame(rng.normal(size=(n - 200, 5)), columns=[f"f{i}" for i in range(5)])
    y_val = rng.integers(0, 2, size=n - 200)

    clf_on = module.train_classifier(
        X_train, y_train, X_val, y_val, calib_frac=0.0,
        horizon=1, expanding_model_weights=True,
    )
    assert clf_on["ensemble"]["ensemble_weight_method"] == "expanding_prior"
