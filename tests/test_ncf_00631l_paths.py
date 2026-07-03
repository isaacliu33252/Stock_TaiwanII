from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


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
