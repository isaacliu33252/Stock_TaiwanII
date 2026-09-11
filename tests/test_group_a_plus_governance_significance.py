from __future__ import annotations

import numpy as np
import pandas as pd

import pytest

from group_a_plus.governance.significance import (
    bonferroni_grid_significance,
    bootstrap_final_value_ci,
    gt_score,
    james_stein_shrink_best_sharpe,
    jobson_korkie_memmel_test,
)


def _synthetic_returns(n: int, mean: float, std: float, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.Series(rng.normal(mean, std, size=n), index=idx)


def test_jk_test_similar_distribution_series_is_not_significant() -> None:
    # Two independent draws from the SAME distribution -- not literally
    # identical (which makes the JK asymptotic variance theta exactly 0, an
    # undefined edge case handled separately below), but no real Sharpe gap.
    a = _synthetic_returns(2000, 0.0005, 0.01, seed=1)
    b = _synthetic_returns(2000, 0.0005, 0.01, seed=101)
    a.index = b.index

    result = jobson_korkie_memmel_test(a, b)

    assert result["status"] == "ok"
    assert result["significant_at_5pct"] is False


def test_jk_test_identical_series_reports_degenerate_variance() -> None:
    """theta (the JK asymptotic variance) is exactly 0 when a==b -- a real
    edge case of the formula, not a bug -- and must be reported, not raise."""
    a = _synthetic_returns(300, 0.0005, 0.01, seed=1)

    result = jobson_korkie_memmel_test(a, a.copy())

    assert result["status"] == "degenerate_variance"


def test_jk_test_detects_large_sharpe_difference() -> None:
    a = _synthetic_returns(1000, 0.003, 0.005, seed=2)  # high mean, low vol -> high Sharpe
    b = _synthetic_returns(1000, -0.001, 0.02, seed=3)  # negative mean, high vol -> negative Sharpe
    a.index = b.index

    result = jobson_korkie_memmel_test(a, b)

    assert result["status"] == "ok"
    assert result["sharpe_a"] > result["sharpe_b"]
    assert result["significant_at_1pct"] is True


def test_jk_test_reports_insufficient_data() -> None:
    a = _synthetic_returns(10, 0.0, 0.01, seed=4)
    b = _synthetic_returns(10, 0.0, 0.01, seed=5)

    result = jobson_korkie_memmel_test(a, b)

    assert result["status"] == "insufficient_data"


def test_bootstrap_ci_contains_one_for_identical_series() -> None:
    a = _synthetic_returns(400, 0.0005, 0.01, seed=6)
    result = bootstrap_final_value_ci(a, a.copy(), n_boot=200, block_size=20)

    assert result["status"] == "ok"
    assert result["ci_lower"] <= 1.0 <= result["ci_upper"]
    assert result["a_significantly_better"] is False
    assert result["a_significantly_worse"] is False


def test_bootstrap_ci_detects_clear_outperformance() -> None:
    a = _synthetic_returns(400, 0.004, 0.01, seed=7)
    b = _synthetic_returns(400, -0.004, 0.01, seed=8)
    a.index = b.index

    result = bootstrap_final_value_ci(a, b, n_boot=200, block_size=20)

    assert result["status"] == "ok"
    assert result["point_final_value_ratio_a_over_b"] > 1.0
    assert result["a_significantly_better"] is True


def test_bootstrap_ci_insufficient_data() -> None:
    a = _synthetic_returns(10, 0.0, 0.01, seed=9)
    b = _synthetic_returns(10, 0.0, 0.01, seed=10)

    result = bootstrap_final_value_ci(a, b, block_size=20)

    assert result["status"] == "insufficient_data"


def test_bonferroni_grid_significance_survives_correction_when_effect_is_large() -> None:
    a = _synthetic_returns(1000, 0.003, 0.005, seed=2)
    b = _synthetic_returns(1000, -0.001, 0.02, seed=3)
    a.index = b.index
    jk = jobson_korkie_memmel_test(a, b)

    result = bonferroni_grid_significance({"cand_1": jk}, candidate_grid_size=20)

    assert result["corrected_alpha"] == pytest.approx(0.05 / 20)
    assert result["candidates"]["cand_1"]["significant"] is True
    assert result["candidates"]["cand_1"]["significant_improvement"] is True
    assert result["any_significant"] is True
    assert result["any_significant_improvement"] is True


def test_bonferroni_grid_significance_flags_significant_worsening_separately() -> None:
    # jobson_korkie_memmel_test is two-sided: a candidate significantly WORSE
    # than baseline also sets `significant` True. A promotion decision must
    # not read that as evidence for promoting -- `significant_improvement`
    # is the field that actually encodes direction, and must be False here
    # even though the raw two-sided test fires.
    a = _synthetic_returns(1000, -0.001, 0.02, seed=3)  # worse: low/negative mean, high vol
    b = _synthetic_returns(1000, 0.003, 0.005, seed=2)  # baseline: better
    a.index = b.index
    jk = jobson_korkie_memmel_test(a, b)
    assert jk["status"] == "ok"
    assert jk["sharpe_diff"] < 0

    result = bonferroni_grid_significance({"cand_1": jk}, candidate_grid_size=20)

    assert result["candidates"]["cand_1"]["significant"] is True
    assert result["candidates"]["cand_1"]["significant_improvement"] is False
    assert result["any_significant_improvement"] is False


def test_bonferroni_grid_significance_rejects_marginal_effect_after_correction() -> None:
    # A pair whose uncorrected JK test is significant at 5% but not at a much
    # smaller Bonferroni-corrected alpha for a large search grid: this is the
    # exact case Prop 3.12 warns about -- a single winner from a wide search
    # that would look significant standalone.
    a = _synthetic_returns(2000, 0.0009, 0.01, seed=20)
    b = _synthetic_returns(2000, 0.0005, 0.01, seed=56)
    a.index = b.index
    jk = jobson_korkie_memmel_test(a, b)
    assert jk["status"] == "ok"
    assert jk["p_value"] < 0.05  # uncorrected test passes

    result = bonferroni_grid_significance({"cand_1": jk}, candidate_grid_size=200)

    assert result["candidates"]["cand_1"]["significant"] is False
    assert result["any_significant"] is False


def test_bonferroni_grid_significance_passes_through_non_ok_status() -> None:
    result = bonferroni_grid_significance(
        {"cand_1": {"status": "insufficient_data"}}, candidate_grid_size=5
    )

    assert result["candidates"]["cand_1"]["status"] == "insufficient_data"
    assert result["candidates"]["cand_1"]["significant"] is False


def test_bonferroni_grid_significance_rejects_grid_size_smaller_than_results() -> None:
    with pytest.raises(ValueError):
        bonferroni_grid_significance(
            {"cand_1": {"status": "ok", "p_value": 0.01}, "cand_2": {"status": "ok", "p_value": 0.02}},
            candidate_grid_size=1,
        )


def test_james_stein_shrink_on_real_direction5_sweep_matches_desk_review() -> None:
    """Regression check against the 2026-09-11 desk review of arXiv:2606.01650:
    3 of 4 historical windows of the direction-5 momentum_fast_exit_min sweep
    should shrink to s=0 (pure noise), inflation_2022 should be the one
    exception with a materially positive shrinkage factor."""
    import json
    from pathlib import Path

    sweep_path = Path("results/reentry_momentum_threshold_sweep_20260908.json")
    if not sweep_path.exists():
        pytest.skip("direction5 sweep results file not present in this checkout")
    data = json.loads(sweep_path.read_text())
    n_obs_by_window = {
        "covid_2020": 260,
        "inflation_2022": 259,
        "live_2024_2026": 698,
        "active_2025_2026": 436,
    }

    for window, n_obs in n_obs_by_window.items():
        candidate_sharpes = {str(c["threshold"]): c["sharpe_ratio"] for c in data[window]["sweep"]}
        result = james_stein_shrink_best_sharpe(candidate_sharpes, n_obs=n_obs)
        assert result["status"] == "ok"
        if window == "inflation_2022":
            assert result["shrinkage_factor"] > 0.5
            assert result["grid_has_real_signal"] is True
        else:
            assert result["shrinkage_factor"] == pytest.approx(0.0, abs=1e-6)
            assert result["grid_has_real_signal"] is False


def test_james_stein_shrink_tied_candidates_no_spread_to_shrink() -> None:
    result = james_stein_shrink_best_sharpe({"a": 1.0, "b": 1.0, "c": 1.0}, n_obs=250)

    assert result["status"] == "ok"
    assert result["shrinkage_factor"] == 0.0
    assert result["shrunk_estimate"] == pytest.approx(1.0)


def test_james_stein_shrink_requires_at_least_three_candidates() -> None:
    result = james_stein_shrink_best_sharpe({"a": 1.0, "b": 2.0}, n_obs=250)

    assert result["status"] == "insufficient_candidates"


def test_james_stein_shrink_rejects_non_positive_n_obs() -> None:
    with pytest.raises(ValueError):
        james_stein_shrink_best_sharpe({"a": 1.0, "b": 2.0, "c": 3.0}, n_obs=0)


def test_gt_score_penalizes_underperformance_more_than_marginal_outperformance() -> None:
    good = _synthetic_returns(300, 0.0008, 0.009, seed=11)
    marginal = _synthetic_returns(300, 0.00035, 0.0098, seed=12)
    bad = _synthetic_returns(300, -0.0008, 0.01, seed=13)
    bench = _synthetic_returns(300, 0.0002, 0.01, seed=14)
    good.index = marginal.index = bad.index = bench.index

    good_result = gt_score(good, bench)
    marginal_result = gt_score(marginal, bench)
    bad_result = gt_score(bad, bench)

    assert good_result["status"] == "ok"
    assert bad_result["regime"] == "underperforms_benchmark"
    # Piecewise definition guarantees every underperform/marginal score is
    # non-positive, and underperformance is penalized more harshly than a
    # marginal outperformer sitting in the smooth-transition band.
    assert bad_result["gt_score"] < marginal_result["gt_score"] <= 0
    assert good_result["gt_score"] > bad_result["gt_score"]


def test_gt_score_reports_degenerate_variance_for_constant_returns() -> None:
    constant = pd.Series([0.001] * 100, index=pd.date_range("2020-01-01", periods=100, freq="B"))
    bench = _synthetic_returns(100, 0.0, 0.01, seed=15)
    bench.index = constant.index

    result = gt_score(constant, bench)

    assert result["status"] == "degenerate_variance"


def test_gt_score_reports_insufficient_data() -> None:
    tiny = pd.Series([0.001], index=pd.date_range("2020-01-01", periods=1, freq="B"))
    bench = pd.Series([0.0], index=tiny.index)

    result = gt_score(tiny, bench)

    assert result["status"] == "insufficient_data"
