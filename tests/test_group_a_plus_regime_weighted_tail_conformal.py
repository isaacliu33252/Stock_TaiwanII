from __future__ import annotations

import numpy as np
import pandas as pd

from group_a_plus.integrations.regime_weighted_tail_conformal import (
    build_regime_weighted_tail_conformal_shadow,
    effective_sample_size,
    weighted_quantile,
)


def test_weighted_quantile_respects_weight_concentration() -> None:
    values = pd.Series([0.0, 1.0, 10.0])
    weights = pd.Series([1.0, 1.0, 20.0])

    assert weighted_quantile(values, weights, 0.50) == 10.0
    assert weighted_quantile(values, weights, 0.01) == 0.0


def test_effective_sample_size_matches_equal_weights() -> None:
    weights = pd.Series([1.0, 1.0, 1.0, 1.0])

    assert effective_sample_size(weights) == 4.0


def test_regime_weighted_shadow_falls_back_to_time_weighted_when_ess_low() -> None:
    dates = pd.bdate_range("2023-01-02", periods=760)
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0005, 0.015, size=len(dates))
    returns[-20:] = rng.normal(-0.002, 0.08, size=20)
    close = pd.Series(100.0 * np.cumprod(1.0 + returns), index=dates)

    report = build_regime_weighted_tail_conformal_shadow(
        close=close,
        as_of=str(dates[-1].date()),
        calibration_window=300,
        min_calibration=120,
        bandwidth=0.05,
        min_effective_sample_size=100,
    )

    assert report["status"] == "ok"
    assert report["policy"] == "shadow_only_no_weight_change"
    assert report["decision"]["changes_target_weights"] is False
    assert report["decision"]["blocks_trades"] is False
    modes = {
        diag["weight_diagnostics"]["mode"]
        for diag in report["diagnostics"].values()
        if diag.get("status") == "ok"
    }
    assert "time_weighted_conformal_fallback" in modes


def test_regime_weighted_shadow_reports_lower_tail_bounds() -> None:
    dates = pd.bdate_range("2023-01-02", periods=760)
    rng = np.random.default_rng(7)
    close = pd.Series(100.0 * np.cumprod(1.0 + rng.normal(0.0004, 0.02, size=len(dates))), index=dates)

    report = build_regime_weighted_tail_conformal_shadow(
        close=close,
        as_of=str(dates[-1].date()),
        calibration_window=300,
        min_calibration=120,
        bandwidth=2.0,
        min_effective_sample_size=30,
    )

    assert report["status"] == "ok"
    assert report["source_paper"]["file"].endswith("2602.03903.pdf")
    assert report["diagnostics"]["h5"]["lower_tail_confidence_bound"] is not None
    assert report["diagnostics"]["h10"]["weight_diagnostics"]["effective_sample_size"] is not None


def test_shadow_can_run_pure_time_weighted_mode() -> None:
    dates = pd.bdate_range("2023-01-02", periods=760)
    rng = np.random.default_rng(11)
    close = pd.Series(100.0 * np.cumprod(1.0 + rng.normal(0.0002, 0.018, size=len(dates))), index=dates)

    report = build_regime_weighted_tail_conformal_shadow(
        close=close,
        as_of=str(dates[-1].date()),
        calibration_window=300,
        min_calibration=120,
        use_regime_kernel=False,
    )

    assert report["status"] == "ok"
    assert report["diagnostics"]["h5"]["weight_diagnostics"]["mode"] == "time_weighted_conformal"
    assert report["diagnostics"]["h5"]["weight_diagnostics"]["bandwidth"] is None
