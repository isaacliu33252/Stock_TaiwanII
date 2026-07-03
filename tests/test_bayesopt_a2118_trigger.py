"""Tests for scripts/sweep/bayesopt_a2118_trigger.py.

Covers:
 - PBOUNDS shape and range validity
 - SEED_PROBES all within PBOUNDS
 - objective factory returns a callable with correct signature
 - _print_table works for empty and non-empty inputs
 - Score penalty logic: over-triggering lowers the score
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pandas as pd
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "sweep" / "bayesopt_a2118_trigger.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bayesopt_a2118_trigger", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    m = _load_module()
    # Register in sys.modules so patch("bayesopt_a2118_trigger.X") resolves correctly
    sys.modules["bayesopt_a2118_trigger"] = m
    return m


# ── bounds ────────────────────────────────────────────────────────────────────

class TestPBounds:
    def test_2d_has_two_keys(self, mod):
        assert set(mod.PBOUNDS_2D.keys()) == {"h20_max", "conf_min"}

    def test_3d_has_three_keys(self, mod):
        assert set(mod.PBOUNDS_3D.keys()) == {"h20_max", "conf_min", "h5_reentry_min"}

    def test_all_ranges_lo_lt_hi(self, mod):
        for key, (lo, hi) in {**mod.PBOUNDS_2D, **mod.PBOUNDS_3D}.items():
            assert lo < hi, f"{key}: lower bound {lo} >= upper bound {hi}"

    def test_h20_max_range_includes_default(self, mod):
        lo, hi = mod.PBOUNDS_3D["h20_max"]
        assert lo <= 0.45 <= hi

    def test_conf_min_range_includes_default(self, mod):
        lo, hi = mod.PBOUNDS_3D["conf_min"]
        assert lo <= 0.55 <= hi

    def test_h5_reentry_includes_zero(self, mod):
        lo, hi = mod.PBOUNDS_3D["h5_reentry_min"]
        assert lo == 0.0


# ── seed probes ───────────────────────────────────────────────────────────────

class TestSeedProbes:
    def test_seed_probes_non_empty(self, mod):
        assert len(mod.SEED_PROBES) > 0

    def test_seed_probes_within_3d_bounds(self, mod):
        for probe in mod.SEED_PROBES:
            for key, (lo, hi) in mod.PBOUNDS_3D.items():
                val = probe.get(key, 0.0)
                assert lo <= val <= hi, f"seed probe {probe}: {key}={val} out of [{lo}, {hi}]"

    def test_default_a2118_params_are_seed(self, mod):
        defaults = {"h20_max": 0.45, "conf_min": 0.55}
        found = any(
            p.get("h20_max") == defaults["h20_max"] and p.get("conf_min") == defaults["conf_min"]
            for p in mod.SEED_PROBES
        )
        assert found, "Default A21.18 params (h20=0.45, conf=0.55) should be a seed probe"


# ── objective factory ─────────────────────────────────────────────────────────

def _make_fake_static(n_days: int = 100) -> dict:
    idx = pd.date_range("2025-01-02", periods=n_days, freq="B")
    regime = pd.Series(["golden1"] * n_days, index=idx)
    ma_gap = pd.Series(np.random.uniform(0.05, 0.20, n_days), index=idx)
    tr_prices = pd.DataFrame(
        {
            "0050.TW": np.cumprod(1 + np.random.normal(0.0003, 0.01, n_days)) * 100,
            "00631L.TW": np.cumprod(1 + np.random.normal(0.0005, 0.018, n_days)) * 20,
            "00632R.TW": np.cumprod(1 + np.random.normal(-0.0003, 0.018, n_days)) * 10,
            "00679B.TWO": np.cumprod(1 + np.random.normal(0.0001, 0.002, n_days)) * 40,
        },
        index=idx,
    )
    weights = {
        "golden1": {"0050.TW": 0.60, "00631L.TW": 0.20, "cash": 0.20},
        "group_a_plus_defensive": {"0050.TW": 0.40, "00679B.TWO": 0.30, "cash": 0.30},
        "group_a_plus_recovery": {"0050.TW": 0.50, "00631L.TW": 0.10, "cash": 0.40},
        "ncf_late_bull_hedge": {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
        "ncf_late_bull_hedge_soft": {"0050.TW": 0.65, "00631L.TW": 0.15, "cash": 0.20},
    }
    return {
        "total_return_prices": tr_prices,
        "execution_regime": regime,
        "ma_gap_series": ma_gap,
        "weights_by_regime": weights,
        "n_days": n_days,
    }


def _make_fake_panel(n_days: int = 100) -> pd.DataFrame:
    idx = pd.date_range("2025-01-02", periods=n_days, freq="B")
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "prob_up_h20": rng.uniform(0.2, 0.8, n_days),
            "prob_up_h5": rng.uniform(0.2, 0.8, n_days),
            "confidence": rng.uniform(0.1, 0.5, n_days),
        },
        index=idx,
    )


class TestObjectiveFactory:
    def test_2d_objective_is_callable(self, mod):
        static = _make_fake_static()
        panel = _make_fake_panel()
        all_results = []
        with patch("bayesopt_a2118_trigger._metrics") as mock_m, \
             patch("bayesopt_a2118_trigger._simulate_costed_curve") as mock_s, \
             patch("bayesopt_a2118_trigger._apply_late_bull_overlay") as mock_ov:
            idx = static["execution_regime"].index
            mock_ov.return_value = (static["execution_regime"].copy(), {"late_bull_trigger_days": 2})
            mock_s.return_value = (pd.Series([1_000_000.0] * 10, index=idx[:10]), {})
            mock_m.return_value = {"sharpe_ratio": 1.2, "sortino_ratio": 1.5, "annual_return": 0.15, "max_drawdown": -0.08}
            obj = mod._objective_factory(
                static, panel,
                max_trigger_rate=0.05,
                trigger_penalty=1.0,
                search_h5=False,
                all_results=all_results,
            )
        assert callable(obj)

    def test_3d_objective_accepts_h5_param(self, mod):
        static = _make_fake_static()
        panel = _make_fake_panel()
        all_results = []
        with patch("bayesopt_a2118_trigger._metrics") as mock_m, \
             patch("bayesopt_a2118_trigger._simulate_costed_curve") as mock_s, \
             patch("bayesopt_a2118_trigger._apply_late_bull_overlay") as mock_ov:
            idx = static["execution_regime"].index
            mock_ov.return_value = (static["execution_regime"].copy(), {"late_bull_trigger_days": 3})
            mock_s.return_value = (pd.Series([1_000_000.0] * 10, index=idx[:10]), {})
            mock_m.return_value = {"sharpe_ratio": 1.0, "sortino_ratio": 1.2, "annual_return": 0.12, "max_drawdown": -0.10}
            obj = mod._objective_factory(
                static, panel,
                max_trigger_rate=0.05,
                trigger_penalty=1.0,
                search_h5=True,
                all_results=all_results,
            )
            import inspect
            sig = inspect.signature(obj)
            assert "h5_reentry_min" in sig.parameters

    def test_score_appended_to_all_results(self, mod):
        static = _make_fake_static(n_days=50)
        panel = _make_fake_panel(n_days=50)
        all_results = []
        with patch("bayesopt_a2118_trigger._metrics") as mock_m, \
             patch("bayesopt_a2118_trigger._simulate_costed_curve") as mock_s, \
             patch("bayesopt_a2118_trigger._apply_late_bull_overlay") as mock_ov:
            idx = static["execution_regime"].index
            mock_ov.return_value = (static["execution_regime"].copy(), {"late_bull_trigger_days": 1})
            mock_s.return_value = (pd.Series([1_000_000.0] * 10, index=idx[:10]), {})
            mock_m.return_value = {"sharpe_ratio": 0.9, "sortino_ratio": 1.1, "annual_return": 0.10, "max_drawdown": -0.12}
            obj = mod._objective_factory(
                static, panel,
                max_trigger_rate=0.05,
                trigger_penalty=1.0,
                search_h5=False,
                all_results=all_results,
            )
            obj(h20_max=0.40, conf_min=0.55)
        assert len(all_results) == 1
        assert "score" in all_results[0]
        assert "sharpe" in all_results[0]

    def test_over_trigger_penalty_reduces_score(self, mod):
        """When trigger_rate > max_trigger_rate, score should be < sharpe_ratio."""
        static = _make_fake_static(n_days=50)
        panel = _make_fake_panel(n_days=50)
        collected = []
        with patch("bayesopt_a2118_trigger._metrics") as mock_m, \
             patch("bayesopt_a2118_trigger._simulate_costed_curve") as mock_s, \
             patch("bayesopt_a2118_trigger._apply_late_bull_overlay") as mock_ov:
            idx = static["execution_regime"].index
            # 40 trigger days / 50 total = 80% trigger rate >> 5% cap
            mock_ov.return_value = (static["execution_regime"].copy(), {"late_bull_trigger_days": 40})
            mock_s.return_value = (pd.Series([1_000_000.0] * 10, index=idx[:10]), {})
            sharpe = 1.5
            mock_m.return_value = {"sharpe_ratio": sharpe, "sortino_ratio": 2.0, "annual_return": 0.20, "max_drawdown": -0.05}
            obj = mod._objective_factory(
                static, panel,
                max_trigger_rate=0.05,
                trigger_penalty=1.0,
                search_h5=False,
                all_results=collected,
            )
            score = obj(h20_max=0.45, conf_min=0.50)
        assert score < sharpe, f"Penalized score {score:.4f} should be < sharpe {sharpe:.4f}"

    def test_no_penalty_when_within_cap(self, mod):
        """When trigger_rate <= max_trigger_rate, score == sharpe_ratio."""
        static = _make_fake_static(n_days=100)
        panel = _make_fake_panel(n_days=100)
        collected = []
        with patch("bayesopt_a2118_trigger._metrics") as mock_m, \
             patch("bayesopt_a2118_trigger._simulate_costed_curve") as mock_s, \
             patch("bayesopt_a2118_trigger._apply_late_bull_overlay") as mock_ov:
            idx = static["execution_regime"].index
            # 3 trigger days / 100 total = 3% (below 5% cap)
            mock_ov.return_value = (static["execution_regime"].copy(), {"late_bull_trigger_days": 3})
            mock_s.return_value = (pd.Series([1_000_000.0] * 10, index=idx[:10]), {})
            sharpe = 1.3
            mock_m.return_value = {"sharpe_ratio": sharpe, "sortino_ratio": 1.7, "annual_return": 0.14, "max_drawdown": -0.09}
            obj = mod._objective_factory(
                static, panel,
                max_trigger_rate=0.05,
                trigger_penalty=1.0,
                search_h5=False,
                all_results=collected,
            )
            score = obj(h20_max=0.40, conf_min=0.55)
        assert abs(score - sharpe) < 1e-6, f"score={score:.6f} should equal sharpe={sharpe:.6f}"


# ── print table ───────────────────────────────────────────────────────────────

class TestPrintTable:
    def test_empty_results_no_crash(self, mod, capsys):
        mod._print_table([], top_n=5)
        # Should not raise; output should contain header
        out = capsys.readouterr().out
        assert "Top" in out or out == ""  # either prints header or nothing

    def test_non_empty_prints_rows(self, mod, capsys):
        results = [
            {
                "h20_max": 0.40, "conf_min": 0.55, "h5_reentry_min": 0.0,
                "sharpe": 1.2, "sortino": 1.5, "annual_return": 0.15,
                "max_drawdown": -0.08, "trigger_days": 4, "trigger_rate": 0.012,
                "score": 1.2,
            }
        ]
        mod._print_table(results, top_n=5)
        out = capsys.readouterr().out
        assert "0.400" in out or "1.2000" in out

    def test_ranks_by_score_descending(self, mod, capsys):
        results = [
            {"h20_max": 0.30, "conf_min": 0.55, "h5_reentry_min": 0.0,
             "sharpe": 0.8, "sortino": 1.0, "annual_return": 0.08,
             "max_drawdown": -0.12, "trigger_days": 2, "trigger_rate": 0.01, "score": 0.8},
            {"h20_max": 0.45, "conf_min": 0.55, "h5_reentry_min": 0.0,
             "sharpe": 1.5, "sortino": 2.0, "annual_return": 0.18,
             "max_drawdown": -0.05, "trigger_days": 4, "trigger_rate": 0.02, "score": 1.5},
        ]
        mod._print_table(results, top_n=2)
        out = capsys.readouterr().out
        lines = [l for l in out.split("\n") if "0.450" in l or "0.300" in l]
        assert len(lines) >= 1
        # The 0.45 row (score 1.5) should appear before 0.30 row (score 0.8)
        if len(lines) >= 2:
            idx_high = out.find("0.450")
            idx_low = out.find("0.300")
            assert idx_high < idx_low
