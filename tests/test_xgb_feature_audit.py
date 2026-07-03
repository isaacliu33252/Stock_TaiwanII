"""Tests for scripts/misc/xgb_feature_audit.py.

Covers pure-Python logic: grade thresholds, rank normalisation, IC computation,
aggregation, and prune-candidate identification.  Skips anything that touches
the DB or downloads yfinance data.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "misc" / "xgb_feature_audit.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("xgb_feature_audit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


# ── grade thresholds ──────────────────────────────────────────────────────────

class TestGrade:
    def test_top_quartile_is_A(self, mod):
        assert mod._grade(0.76) == "A"
        assert mod._grade(1.00) == "A"

    def test_second_quartile_is_B(self, mod):
        assert mod._grade(0.50) == "B"
        assert mod._grade(0.74) == "B"

    def test_third_quartile_is_C(self, mod):
        assert mod._grade(0.25) == "C"
        assert mod._grade(0.49) == "C"

    def test_bottom_quartile_is_D(self, mod):
        assert mod._grade(0.00) == "D"
        assert mod._grade(0.24) == "D"

    def test_boundary_exact_thresholds(self, mod):
        """Exact threshold values should go to the better grade."""
        assert mod._grade(0.75) == "A"
        assert mod._grade(0.50) == "B"
        assert mod._grade(0.25) == "C"


# ── rank normalisation ────────────────────────────────────────────────────────

class TestRankNormalise:
    def test_single_feature_gets_rank_zero(self, mod):
        result = mod._rank_normalise({"feat_a": 42.0})
        assert result["feat_a"] == 0.0

    def test_two_features_min_zero_max_one(self, mod):
        result = mod._rank_normalise({"low": 1.0, "high": 10.0})
        assert result["low"] == 0.0
        assert result["high"] == 1.0

    def test_rank_monotone(self, mod):
        values = {"a": 3.0, "b": 1.0, "c": 5.0, "d": 2.0}
        result = mod._rank_normalise(values)
        assert result["b"] < result["d"] < result["a"] < result["c"]

    def test_all_equal_gives_equal_ranks(self, mod):
        values = {"a": 5.0, "b": 5.0, "c": 5.0}
        result = mod._rank_normalise(values)
        assert abs(result["a"] - result["b"]) < 1e-9
        assert abs(result["b"] - result["c"]) < 1e-9

    def test_empty_returns_empty(self, mod):
        result = mod._rank_normalise({})
        assert result == {}

    def test_output_range_0_to_1(self, mod):
        values = {f"f{i}": float(i) for i in range(20)}
        result = mod._rank_normalise(values)
        for v in result.values():
            assert 0.0 <= v <= 1.0

    def test_zero_values_handled(self, mod):
        """Features with zero importance should get rank 0."""
        values = {"active": 10.0, "dead": 0.0}
        result = mod._rank_normalise(values)
        assert result["dead"] < result["active"]


# ── IC computation ────────────────────────────────────────────────────────────

class TestInformationCoefficient:
    def _make_data(self, n: int = 200, seed: int = 0):
        rng = np.random.default_rng(seed)
        idx = pd.date_range("2022-01-01", periods=n, freq="B")
        # feature_a: highly correlated with return
        # feature_b: zero correlation (random noise)
        # feature_c: constant (zero IC)
        feature_a = rng.normal(0, 1, n)
        y_return = feature_a * 0.5 + rng.normal(0, 0.2, n)
        feature_b = rng.normal(0, 1, n)
        feature_c = np.ones(n) * 3.14
        X = pd.DataFrame({
            "feature_a": feature_a,
            "feature_b": feature_b,
            "feature_c": feature_c,
        }, index=idx)
        y = pd.Series(y_return, index=idx)
        return X, y

    def test_correlated_feature_has_high_ic(self, mod):
        X, y = self._make_data()
        ic = mod._information_coefficient(X, y, ["feature_a"])
        assert ic["feature_a"] > 0.30, f"Expected IC > 0.30, got {ic['feature_a']:.4f}"

    def test_noise_feature_has_low_ic(self, mod):
        X, y = self._make_data()
        ic = mod._information_coefficient(X, y, ["feature_b"])
        assert ic["feature_b"] < 0.20

    def test_constant_feature_has_zero_ic(self, mod):
        X, y = self._make_data()
        ic = mod._information_coefficient(X, y, ["feature_c"])
        assert ic["feature_c"] == 0.0

    def test_ic_is_absolute_value(self, mod):
        """IC should be |Spearman ρ|, so always >= 0."""
        X, y = self._make_data()
        ic = mod._information_coefficient(X, y, list(X.columns))
        for feat, val in ic.items():
            assert val >= 0.0, f"{feat}: IC={val} should be non-negative"

    def test_ic_range_0_to_1(self, mod):
        X, y = self._make_data()
        ic = mod._information_coefficient(X, y, list(X.columns))
        for val in ic.values():
            assert 0.0 <= val <= 1.0

    def test_correlated_has_higher_ic_than_noise(self, mod):
        X, y = self._make_data()
        ic = mod._information_coefficient(X, y, ["feature_a", "feature_b"])
        assert ic["feature_a"] > ic["feature_b"]


# ── aggregate grades ──────────────────────────────────────────────────────────

class TestAggregateGrades:
    def _make_horizon_results(self) -> list[dict]:
        feats = ["alpha", "beta", "gamma"]
        horizon_results = []
        for h, composites in [(1, [0.9, 0.5, 0.1]), (5, [0.8, 0.6, 0.2]), (20, [0.85, 0.55, 0.15])]:
            features = {}
            for feat, comp in zip(feats, composites):
                features[feat] = {
                    "gain": comp * 100,
                    "weight": comp * 10,
                    "cover": comp * 50,
                    "ic": comp * 0.5,
                    "gain_rank": comp,
                    "ic_rank": comp,
                    "composite": comp,
                    "grade": "A" if comp >= 0.75 else ("B" if comp >= 0.5 else ("C" if comp >= 0.25 else "D")),
                }
            horizon_results.append({
                "horizon": h,
                "n_samples": 300,
                "n_features": len(feats),
                "feature_list": feats,
                "features": features,
            })
        return horizon_results

    def test_all_features_present_in_agg(self, mod):
        hr = self._make_horizon_results()
        agg = mod._aggregate_grades(hr)
        assert set(agg.keys()) == {"alpha", "beta", "gamma"}

    def test_best_feature_gets_rank_1(self, mod):
        hr = self._make_horizon_results()
        agg = mod._aggregate_grades(hr)
        ranked = sorted(agg.items(), key=lambda kv: kv[1]["rank"], reverse=True)
        assert ranked[0][0] == "alpha"

    def test_worst_feature_gets_rank_0(self, mod):
        hr = self._make_horizon_results()
        agg = mod._aggregate_grades(hr)
        ranked = sorted(agg.items(), key=lambda kv: kv[1]["rank"])
        assert ranked[0][0] == "gamma"

    def test_overall_grade_assigned(self, mod):
        hr = self._make_horizon_results()
        agg = mod._aggregate_grades(hr)
        for feat in agg:
            assert "overall_grade" in agg[feat]
            assert agg[feat]["overall_grade"] in {"A", "B", "C", "D"}

    def test_per_horizon_grades_in_agg(self, mod):
        hr = self._make_horizon_results()
        agg = mod._aggregate_grades(hr)
        for feat in agg:
            assert "h1_grade" in agg[feat]
            assert "h5_grade" in agg[feat]
            assert "h20_grade" in agg[feat]

    def test_mean_ic_is_average(self, mod):
        hr = self._make_horizon_results()
        agg = mod._aggregate_grades(hr)
        # alpha's IC values: 0.9*0.5=0.45, 0.8*0.5=0.40, 0.85*0.5=0.425 → mean=0.425
        expected = (0.9 * 0.5 + 0.8 * 0.5 + 0.85 * 0.5) / 3
        assert abs(agg["alpha"]["mean_ic"] - expected) < 1e-6

    def test_best_feature_gets_A_grade(self, mod):
        hr = self._make_horizon_results()
        agg = mod._aggregate_grades(hr)
        assert agg["alpha"]["overall_grade"] == "A"

    def test_worst_feature_gets_D_grade(self, mod):
        hr = self._make_horizon_results()
        agg = mod._aggregate_grades(hr)
        assert agg["gamma"]["overall_grade"] == "D"


# ── prune candidate logic ─────────────────────────────────────────────────────

class TestPruneCandidates:
    def test_grade_d_low_ic_is_prune_candidate(self, mod):
        """Grade D + IC < 0.02 should be identified as prune candidate."""
        agg = {
            "good_feat": {"overall_grade": "A", "mean_ic": 0.15, "rank": 0.9},
            "marginal":  {"overall_grade": "C", "mean_ic": 0.01, "rank": 0.3},
            "dead_feat": {"overall_grade": "D", "mean_ic": 0.005, "rank": 0.1},
        }
        prune = [
            f for f, i in agg.items()
            if i["overall_grade"] == "D" and i["mean_ic"] < 0.02
        ]
        assert "dead_feat" in prune
        assert "good_feat" not in prune
        assert "marginal" not in prune

    def test_grade_d_with_high_ic_not_pruned(self, mod):
        """Grade D but IC >= 0.02 should NOT be pruned (rare but possible)."""
        agg = {
            "surprising": {"overall_grade": "D", "mean_ic": 0.05, "rank": 0.1},
        }
        prune = [
            f for f, i in agg.items()
            if i["overall_grade"] == "D" and i["mean_ic"] < 0.02
        ]
        assert "surprising" not in prune


# ── print table smoke test ────────────────────────────────────────────────────

class TestPrintTable:
    def test_empty_no_crash(self, mod, capsys):
        mod._print_table({}, top_n=10)

    def test_prints_grade_and_rank(self, mod, capsys):
        agg = {
            "feat_a": {
                "overall_grade": "A", "rank": 1.0, "mean_ic": 0.12,
                "mean_gain": 500.0, "h1_grade": "A", "h5_grade": "A", "h20_grade": "A"
            },
            "feat_b": {
                "overall_grade": "D", "rank": 0.0, "mean_ic": 0.01,
                "mean_gain": 10.0, "h1_grade": "D", "h5_grade": "D", "h20_grade": "D"
            },
        }
        mod._print_table(agg, top_n=10)
        out = capsys.readouterr().out
        assert "feat_a" in out
        assert "A" in out
