from __future__ import annotations

import pandas as pd

from scripts.misc.shadow_ncf_2330_factor_quality_tier_overlay import (
    OverlaySpec,
    _affected_summary,
    apply_factor_quality_overlay_to_tiers,
)


def test_factor_quality_overlay_downgrades_only_addable_tiers() -> None:
    frame = pd.DataFrame(
        {
            "tier": [0, 1, 2, 3, 3],
            "factor_quality_signal": ["bearish", "bearish", "bearish", "bearish", "neutral"],
            "factor_quality_risk_score": [6.0, 6.0, 6.0, 6.0, 6.0],
            "factor_quality_net_score": [-5.0, -5.0, -5.0, -5.0, -5.0],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"]),
    )

    adjusted = apply_factor_quality_overlay_to_tiers(
        frame,
        OverlaySpec(name="test", min_risk_score=4.0, max_net_score=-3.0, require_bearish_signal=True),
    )

    assert adjusted["tier"].tolist() == [0, 1, 1, 2, 3]
    assert adjusted["factor_quality_tier_cut"].tolist() == [0, 0, 1, 1, 0]
    assert adjusted["factor_quality_overlay_trigger"].tolist() == [True, True, True, True, False]


def test_factor_quality_overlay_no_add_only_caps_tier3() -> None:
    frame = pd.DataFrame(
        {
            "tier": [0, 1, 2, 3, 3],
            "factor_quality_signal": ["bearish", "bearish", "bearish", "bearish", "neutral"],
            "factor_quality_risk_score": [6.0, 6.0, 6.0, 6.0, 6.0],
            "factor_quality_net_score": [-5.0, -5.0, -5.0, -5.0, -5.0],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"]),
    )

    adjusted = apply_factor_quality_overlay_to_tiers(
        frame,
        OverlaySpec(
            name="test_noadd",
            min_risk_score=4.0,
            max_net_score=-3.0,
            require_bearish_signal=True,
            mode="no_add",
        ),
    )

    assert adjusted["tier"].tolist() == [0, 1, 2, 2, 3]
    assert adjusted["factor_quality_tier_cut"].tolist() == [0, 0, 0, 1, 0]


def test_factor_quality_overlay_momentum_confirm_only_upgrades_tier2() -> None:
    frame = pd.DataFrame(
        {
            "tier": [0, 1, 2, 3, 2],
            "factor_quality_signal": ["bearish", "bearish", "bearish", "bearish", "neutral"],
            "factor_quality_risk_score": [6.0, 6.0, 6.0, 6.0, 6.0],
            "factor_quality_net_score": [-5.0, -5.0, -5.0, -5.0, -5.0],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"]),
    )

    adjusted = apply_factor_quality_overlay_to_tiers(
        frame,
        OverlaySpec(
            name="test_momentum",
            min_risk_score=4.0,
            max_net_score=-3.0,
            require_bearish_signal=True,
            mode="momentum_confirm",
        ),
    )

    assert adjusted["tier"].tolist() == [0, 1, 3, 3, 2]
    assert adjusted["factor_quality_tier_cut"].tolist() == [0, 0, -1, 0, 0]


def test_affected_summary_counts_upgrades_and_downgrades() -> None:
    frame = pd.DataFrame(
        {
            "base_tier": [2, 3],
            "tier": [3, 2],
            "factor_quality_tier_cut": [-1, 1],
            "fwd_00631L_vs_0050_excess_20d": [0.10, -0.04],
            "fwd_00631L.TW_mdd_20d": [-0.01, -0.08],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    summary = _affected_summary(frame)

    assert summary["changed_days"] == 2
    assert summary["mean_tier_delta"] == 0.0
    assert summary["bad_mdd_gt5_20d"] == 0.5
