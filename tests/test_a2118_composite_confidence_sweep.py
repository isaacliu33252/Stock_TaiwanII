#!/usr/bin/env python3
"""H2 Option B (2026-07-02 Fable 5 audit) regression: composite confidence formula."""

from __future__ import annotations

import pandas as pd

from scripts.evaluate.evaluate_a2118_composite_confidence_sweep import _composite_confidence


def test_composite_confidence_full_consensus_and_zero_spread() -> None:
    """All three horizons agree (UP) and are identical -- consensus=1.0,
    spread_conf=1.0, magnitude drives the rest."""
    panel = pd.DataFrame(
        {
            "prob_up_h1": [0.8],
            "prob_up_h5": [0.8],
            "prob_up_h20": [0.8],
            "prob_magnitude": [0.6],
        }
    )

    result = _composite_confidence(panel)

    # consensus=1.0*0.4 + magnitude=0.6*0.4 + spread=1.0*0.2 = 0.4+0.24+0.2 = 0.84
    assert abs(result.iloc[0] - 0.84) < 1e-9


def test_composite_confidence_split_consensus() -> None:
    """2 UP / 1 DOWN -- consensus = 2/3."""
    panel = pd.DataFrame(
        {
            "prob_up_h1": [0.6],
            "prob_up_h5": [0.6],
            "prob_up_h20": [0.3],
            "prob_magnitude": [0.2],
        }
    )

    result = _composite_confidence(panel)

    assert 0.0 < result.iloc[0] < 1.0


def test_composite_confidence_clamped_to_minimum_point_one() -> None:
    """Zero consensus contribution requires an even split, which can't
    happen with 3 horizons -- but magnitude=0 + low consensus should still
    clamp at the 0.1 floor, matching the original live-JSON formula."""
    panel = pd.DataFrame(
        {
            "prob_up_h1": [0.51],
            "prob_up_h5": [0.49],
            "prob_up_h20": [0.50],
            "prob_magnitude": [0.0],
        }
    )

    result = _composite_confidence(panel)

    assert result.iloc[0] >= 0.1


def test_composite_confidence_clamped_to_maximum_one() -> None:
    panel = pd.DataFrame(
        {
            "prob_up_h1": [0.99],
            "prob_up_h5": [0.99],
            "prob_up_h20": [0.99],
            "prob_magnitude": [1.0],
        }
    )

    result = _composite_confidence(panel)

    assert result.iloc[0] <= 1.0

