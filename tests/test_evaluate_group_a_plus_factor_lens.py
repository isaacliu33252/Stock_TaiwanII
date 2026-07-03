from __future__ import annotations

import pandas as pd

from scripts.evaluate.evaluate_group_a_plus_factor_lens import (
    build_event_masks,
    build_factor_series,
    parse_horizons,
)


def test_build_factor_series_maps_00632r_to_inverse_market_view() -> None:
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    advisory = pd.DataFrame(
        {
            "market_probability_up": [0.6, 0.4, 0.7],
            "agreement_score": [0.8, 0.9, 0.5],
            "dynamic_00631l_prob_up": [0.65, 0.45, 0.75],
            "dynamic_00632r_prob_up": [0.3, 0.7, 0.2],
        },
        index=dates,
    )

    factors = build_factor_series(advisory)

    assert factors["ncf_00632r_inverse_market_up"].tolist() == [0.7, 0.30000000000000004, 0.8]
    assert factors["ncf_cross_ticker_market_up"].round(4).tolist() == [0.675, 0.375, 0.775]
    assert factors["ncf_signed_market_score"].round(4).tolist() == [0.16, -0.18, 0.2]


def test_build_event_masks_and_parse_horizons() -> None:
    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    advisory = pd.DataFrame(
        {
            "market_direction": ["UP", "DOWN", "UP", "DOWN"],
            "agreement_score": [0.7, 0.8, 0.4, 0.6],
            "conflict_flag": [False, True, False, False],
        },
        index=dates,
    )

    masks = build_event_masks(advisory)

    assert masks["high_agreement_bullish"].tolist() == [True, False, False, False]
    assert masks["high_agreement_bearish"].tolist() == [False, True, False, False]
    assert masks["conflict_flag"].tolist() == [False, True, False, False]
    assert parse_horizons("1,5,20") == (1, 5, 20)
