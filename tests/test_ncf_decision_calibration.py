from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from group_a_plus.integrations.ncf_decision_calibration import (
    build_snapshot,
    decision_confidence_from_regret,
    direction_confidence_from_panel_row,
    fit_regret_calibration,
    load_calibration_pairs,
    load_historical_regret_distribution,
    predict_calibrated_probability,
)


def _sample_panel_row(**overrides) -> dict:
    base = {
        "prob_up_h1": 0.6,
        "prob_up_h5": 0.65,
        "prob_up_h20": 0.7,
        "prob_magnitude": 0.5,
    }
    base.update(overrides)
    return base


def _write_dfl_shadow(tmp_path: Path, decisions_by_window: list[list[dict]]) -> Path:
    path = tmp_path / "dfl_shadow.json"
    payload = {
        "results": [
            {"label": f"window_{i}", "non_keep_decisions": decisions}
            for i, decisions in enumerate(decisions_by_window)
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_dfl_shadow_with_pairs(tmp_path: Path, windows: list[tuple[str, str, list[dict]]]) -> Path:
    path = tmp_path / "dfl_shadow_pairs.json"
    payload = {
        "results": [
            {"label": label, "bucket": bucket, "calibration_pairs": pairs}
            for label, bucket, pairs in windows
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_direction_confidence_high_when_all_horizons_agree_strongly() -> None:
    row = _sample_panel_row(prob_up_h1=0.9, prob_up_h5=0.9, prob_up_h20=0.9, prob_magnitude=0.9)
    conf = direction_confidence_from_panel_row(row)
    assert conf is not None
    assert conf > 0.7


def test_direction_confidence_low_when_horizons_disagree() -> None:
    row = _sample_panel_row(prob_up_h1=0.9, prob_up_h5=0.1, prob_up_h20=0.9, prob_magnitude=0.1)
    conf = direction_confidence_from_panel_row(row)
    assert conf is not None
    assert conf < 0.5


def test_direction_confidence_missing_columns_returns_none() -> None:
    assert direction_confidence_from_panel_row({}) is None


def test_direction_confidence_clipped_to_range() -> None:
    row = _sample_panel_row(prob_up_h1=1.0, prob_up_h5=1.0, prob_up_h20=1.0, prob_magnitude=1.0)
    conf = direction_confidence_from_panel_row(row)
    assert 0.1 <= conf <= 1.0


def test_load_historical_regret_distribution_pools_across_windows(tmp_path: Path) -> None:
    path = _write_dfl_shadow(
        tmp_path,
        [
            [{"action": "CAP10", "predicted_regret": 0.01}, {"action": "CAP10", "predicted_regret": 0.02}],
            [{"action": "CAP10", "predicted_regret": 0.03}, {"action": "REENTER", "predicted_regret": 0.005}],
        ],
    )
    dist = load_historical_regret_distribution(path)
    assert dist["CAP10"] == [0.01, 0.02, 0.03]
    assert dist["REENTER"] == [0.005]


def test_load_historical_regret_distribution_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_historical_regret_distribution(tmp_path / "missing.json") == {}


def test_decision_confidence_none_for_keep_action() -> None:
    assert decision_confidence_from_regret("KEEP", 0.01, {"CAP10": [0.01, 0.02]}) is None


def test_decision_confidence_none_when_no_historical_distribution() -> None:
    assert decision_confidence_from_regret("CAP10", 0.01, {}) is None


def test_decision_confidence_is_percentile_rank() -> None:
    dist = {"CAP10": [0.0, 0.01, 0.02, 0.03, 0.04]}
    # 0.02 is the 3rd of 5 values (all <= 0.02): rank = 3/5 = 0.6
    conf = decision_confidence_from_regret("CAP10", 0.02, dist)
    assert conf == 0.6


def test_decision_confidence_at_distribution_max_is_one() -> None:
    dist = {"CAP10": [0.0, 0.01, 0.02]}
    assert decision_confidence_from_regret("CAP10", 0.02, dist) == 1.0


def test_build_snapshot_no_dfl_action_gives_none_decision_confidence(tmp_path: Path) -> None:
    path = _write_dfl_shadow(tmp_path, [[{"action": "CAP10", "predicted_regret": 0.01}]])
    snapshot = build_snapshot(
        as_of="2026-07-26",
        ncf_panel_row=_sample_panel_row(),
        dfl_action=None,
        dfl_predicted_regret=None,
        dfl_shadow_path=path,
    )
    assert snapshot.decision_confidence is None
    assert "no DFL candidate" in snapshot.basis
    assert snapshot.direction_confidence is not None


def test_build_snapshot_keep_action_gives_none_decision_confidence(tmp_path: Path) -> None:
    path = _write_dfl_shadow(tmp_path, [[{"action": "CAP10", "predicted_regret": 0.01}]])
    snapshot = build_snapshot(
        as_of="2026-07-26",
        ncf_panel_row=_sample_panel_row(),
        dfl_action="KEEP",
        dfl_predicted_regret=0.0,
        dfl_shadow_path=path,
    )
    assert snapshot.decision_confidence is None
    assert "KEEP" in snapshot.basis


def test_build_snapshot_with_real_candidate_produces_rank(tmp_path: Path) -> None:
    path = _write_dfl_shadow(
        tmp_path,
        [[{"action": "CAP10", "predicted_regret": v} for v in [0.001, 0.005, 0.01, 0.015, 0.02]]],
    )
    snapshot = build_snapshot(
        as_of="2026-07-26",
        ncf_panel_row=_sample_panel_row(),
        dfl_action="CAP10",
        dfl_predicted_regret=0.01,
        dfl_shadow_path=path,
    )
    assert snapshot.decision_confidence == 0.6
    assert snapshot.historical_candidate_count == 5
    assert "NOT an outcome-calibrated probability" in snapshot.basis


def test_snapshot_to_json_dict_roundtrip_shape(tmp_path: Path) -> None:
    path = _write_dfl_shadow(tmp_path, [[{"action": "CAP10", "predicted_regret": 0.01}]])
    snapshot = build_snapshot(
        as_of="2026-07-26",
        ncf_panel_row=_sample_panel_row(),
        dfl_action="CAP10",
        dfl_predicted_regret=0.01,
        dfl_shadow_path=path,
    )
    payload = snapshot.to_json_dict()
    assert payload["as_of"] == "2026-07-26"
    assert set(payload.keys()) == {
        "as_of",
        "direction_confidence",
        "decision_confidence",
        "action",
        "predicted_regret",
        "historical_candidate_count",
        "basis",
        "extra",
        "calibration_method",
    }
    assert payload["calibration_method"] == "predicted_regret_percentile_rank_proxy"


def _synthetic_pairs(bucket: str, n: int, *, action: str = "CAP10", seed: int = 0) -> list[dict]:
    rng = np.random.default_rng(seed)
    predicted = rng.uniform(-0.02, 0.02, size=n)
    # Realized regret correlated with predicted_regret plus noise, so a
    # monotonic calibration curve genuinely exists to be fit.
    realized = predicted + rng.normal(0.0, 0.005, size=n)
    return [
        {
            "date": f"2020-01-{(i % 28) + 1:02d}",
            "action": action,
            "predicted_regret": float(p),
            "realized_regret": float(r),
        }
        for i, (p, r) in enumerate(zip(predicted, realized))
    ]


def test_load_calibration_pairs_pools_bucket_and_window(tmp_path: Path) -> None:
    pairs_a = [{"date": "2020-01-01", "action": "CAP10", "predicted_regret": 0.01, "realized_regret": 0.02}]
    pairs_b = [{"date": "2018-01-01", "action": "CAP10", "predicted_regret": -0.01, "realized_regret": -0.02}]
    path = _write_dfl_shadow_with_pairs(
        tmp_path,
        [("live_2024_2026", "tuning_window", pairs_a), ("2018_correction", "out_of_sample", pairs_b)],
    )

    df = load_calibration_pairs(path)

    assert len(df) == 2
    assert set(df["bucket"]) == {"tuning_window", "out_of_sample"}
    assert set(df["window"]) == {"live_2024_2026", "2018_correction"}


def test_load_calibration_pairs_missing_file_returns_empty_frame(tmp_path: Path) -> None:
    df = load_calibration_pairs(tmp_path / "does_not_exist.json")
    assert df.empty


def test_fit_regret_calibration_only_uses_tuning_window_bucket(tmp_path: Path) -> None:
    train_pairs = _synthetic_pairs("tuning_window", 200, seed=1)
    # OOS pairs deliberately reversed-sign so a leaking fit would look very
    # different from a fit that correctly ignored them.
    oos_pairs = [
        {**row, "predicted_regret": -row["predicted_regret"], "realized_regret": -row["realized_regret"]}
        for row in _synthetic_pairs("out_of_sample", 200, seed=2)
    ]
    path = _write_dfl_shadow_with_pairs(
        tmp_path,
        [("live_2024_2026", "tuning_window", train_pairs), ("2018_correction", "out_of_sample", oos_pairs)],
    )
    pairs = load_calibration_pairs(path)

    model = fit_regret_calibration(pairs, n_bins=5, min_bin_size=10)

    assert model.fit_bucket == "tuning_window"
    assert model.fit_sample_size == 200
    assert "CAP10" in model.by_action
    entry = model.by_action["CAP10"]["__all__"]
    assert sum(entry["counts"]) == 200
    # Higher predicted_regret bins should have higher (or equal) win rate --
    # the synthetic data was constructed to be monotonically related.
    rates = entry["win_rates"]
    assert rates == sorted(rates)


def test_fit_regret_calibration_skips_actions_below_min_bin_size(tmp_path: Path) -> None:
    tiny_pairs = _synthetic_pairs("tuning_window", 5, action="REENTER", seed=3)
    path = _write_dfl_shadow_with_pairs(tmp_path, [("live_2024_2026", "tuning_window", tiny_pairs)])
    pairs = load_calibration_pairs(path)

    model = fit_regret_calibration(pairs, n_bins=5, min_bin_size=20)

    assert "REENTER" not in model.by_action


def test_predict_calibrated_probability_uses_correct_bin(tmp_path: Path) -> None:
    train_pairs = _synthetic_pairs("tuning_window", 300, seed=4)
    path = _write_dfl_shadow_with_pairs(tmp_path, [("live_2024_2026", "tuning_window", train_pairs)])
    pairs = load_calibration_pairs(path)
    model = fit_regret_calibration(pairs, n_bins=5, min_bin_size=10)

    low_prob = predict_calibrated_probability("CAP10", -0.019, model)
    high_prob = predict_calibrated_probability("CAP10", 0.019, model)

    assert low_prob is not None and high_prob is not None
    assert high_prob >= low_prob


def test_predict_calibrated_probability_none_for_keep_or_missing_action(tmp_path: Path) -> None:
    train_pairs = _synthetic_pairs("tuning_window", 300, seed=5)
    path = _write_dfl_shadow_with_pairs(tmp_path, [("live_2024_2026", "tuning_window", train_pairs)])
    model = fit_regret_calibration(load_calibration_pairs(path), n_bins=5, min_bin_size=10)

    assert predict_calibrated_probability("KEEP", 0.01, model) is None
    assert predict_calibrated_probability("NO_ADD", 0.01, model) is None
    assert predict_calibrated_probability("CAP10", 0.01, None) is None


def test_build_snapshot_uses_calibration_model_when_available(tmp_path: Path) -> None:
    train_pairs = _synthetic_pairs("tuning_window", 300, seed=6)
    dfl_shadow_path = _write_dfl_shadow(tmp_path, [[{"action": "CAP10", "predicted_regret": 0.015}]])
    pairs_path = _write_dfl_shadow_with_pairs(tmp_path, [("live_2024_2026", "tuning_window", train_pairs)])
    model = fit_regret_calibration(load_calibration_pairs(pairs_path), n_bins=5, min_bin_size=10)

    snapshot = build_snapshot(
        as_of="2026-07-27",
        ncf_panel_row=_sample_panel_row(),
        dfl_action="CAP10",
        dfl_predicted_regret=0.015,
        dfl_shadow_path=dfl_shadow_path,
        calibration_model=model,
    )

    assert snapshot.calibration_method == "empirical_realized_regret_calibration"
    assert snapshot.decision_confidence is not None
    assert "empirical calibration" in snapshot.basis


def test_build_snapshot_falls_back_to_rank_proxy_when_no_calibration_data(tmp_path: Path) -> None:
    dfl_shadow_path = _write_dfl_shadow(
        tmp_path, [[{"action": "CAP10", "predicted_regret": v} for v in [0.001, 0.002, 0.003, 0.004, 0.005]]]
    )
    model = fit_regret_calibration(pd.DataFrame(), n_bins=5, min_bin_size=10)

    snapshot = build_snapshot(
        as_of="2026-07-27",
        ncf_panel_row=_sample_panel_row(),
        dfl_action="CAP10",
        dfl_predicted_regret=0.003,
        dfl_shadow_path=dfl_shadow_path,
        calibration_model=model,
    )

    assert snapshot.calibration_method == "predicted_regret_percentile_rank_proxy"


def _synthetic_pairs_with_regime(bucket: str, n: int, *, action: str = "CAP10", seed: int = 0) -> list[dict]:
    rng = np.random.default_rng(seed)
    risk_score = rng.uniform(0.0, 14.0, size=n)
    predicted = rng.uniform(-0.02, 0.02, size=n)
    realized = predicted + rng.normal(0.0, 0.005, size=n)
    return [
        {
            "date": f"2020-01-{(i % 28) + 1:02d}",
            "action": action,
            "predicted_regret": float(p),
            "realized_regret": float(r),
            "total_risk_score": float(s),
        }
        for i, (p, r, s) in enumerate(zip(predicted, realized, risk_score))
    ]


def test_fit_regret_calibration_with_regime_column_fits_separate_bins_per_bucket(tmp_path: Path) -> None:
    train_pairs = _synthetic_pairs_with_regime("tuning_window", 600, seed=10)
    path = _write_dfl_shadow_with_pairs(tmp_path, [("live_2024_2026", "tuning_window", train_pairs)])
    pairs = load_calibration_pairs(path)

    model = fit_regret_calibration(
        pairs, n_bins=5, min_bin_size=10, regime_column="total_risk_score", regime_edges=(6.0, 9.0)
    )

    assert model.regime_column == "total_risk_score"
    assert "CAP10" in model.by_action
    regimes = set(model.by_action["CAP10"].keys())
    # 600 uniform(0,14) draws should populate all three risk buckets.
    assert regimes == {"low", "elevated", "severe"}


def test_predict_calibrated_probability_uses_matching_regime_bucket(tmp_path: Path) -> None:
    train_pairs = _synthetic_pairs_with_regime("tuning_window", 600, seed=11)
    path = _write_dfl_shadow_with_pairs(tmp_path, [("live_2024_2026", "tuning_window", train_pairs)])
    pairs = load_calibration_pairs(path)
    model = fit_regret_calibration(
        pairs, n_bins=5, min_bin_size=10, regime_column="total_risk_score", regime_edges=(6.0, 9.0)
    )

    low_regime_prob = predict_calibrated_probability("CAP10", 0.01, model, regime_value=2.0)
    severe_regime_prob = predict_calibrated_probability("CAP10", 0.01, model, regime_value=12.0)

    assert low_regime_prob is not None
    assert severe_regime_prob is not None


def test_predict_calibrated_probability_regime_mismatch_returns_none_not_pooled(tmp_path: Path) -> None:
    # Only "low" regime has enough samples -- "severe" should have no fitted
    # bins and must NOT silently fall back to a pooled estimate.
    train_pairs = _synthetic_pairs_with_regime("tuning_window", 50, action="CAP10", seed=12)
    train_pairs = [{**row, "total_risk_score": 1.0} for row in train_pairs]  # force all into "low"
    path = _write_dfl_shadow_with_pairs(tmp_path, [("live_2024_2026", "tuning_window", train_pairs)])
    pairs = load_calibration_pairs(path)
    model = fit_regret_calibration(
        pairs, n_bins=5, min_bin_size=10, regime_column="total_risk_score", regime_edges=(6.0, 9.0)
    )

    assert predict_calibrated_probability("CAP10", 0.01, model, regime_value=12.0) is None
    assert predict_calibrated_probability("CAP10", 0.01, model, regime_value=1.0) is not None


def test_build_snapshot_passes_through_regime_value_to_calibration(tmp_path: Path) -> None:
    train_pairs = _synthetic_pairs_with_regime("tuning_window", 600, seed=13)
    dfl_shadow_path = _write_dfl_shadow(tmp_path, [[{"action": "CAP10", "predicted_regret": 0.015}]])
    pairs_path = _write_dfl_shadow_with_pairs(tmp_path, [("live_2024_2026", "tuning_window", train_pairs)])
    model = fit_regret_calibration(
        load_calibration_pairs(pairs_path),
        n_bins=5,
        min_bin_size=10,
        regime_column="total_risk_score",
        regime_edges=(6.0, 9.0),
    )

    snapshot = build_snapshot(
        as_of="2026-07-27",
        ncf_panel_row=_sample_panel_row(),
        dfl_action="CAP10",
        dfl_predicted_regret=0.015,
        dfl_shadow_path=dfl_shadow_path,
        calibration_model=model,
        dfl_total_risk_score=12.0,
    )

    assert snapshot.calibration_method == "empirical_realized_regret_calibration"
    assert "regime=severe" in snapshot.basis
