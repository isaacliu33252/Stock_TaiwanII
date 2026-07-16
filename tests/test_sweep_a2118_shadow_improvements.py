from __future__ import annotations

from scripts.sweep.sweep_a2118_shadow_improvements import (
    parse_float_list,
    parse_int_list,
    parse_optional_float_list,
    _score,
)


def test_parse_grid_values() -> None:
    assert parse_float_list("0.28, 0.33") == [0.28, 0.33]
    assert parse_int_list("0, 1") == [0, 1]
    assert parse_optional_float_list("none,0.30,null") == [None, 0.30, None]


def test_score_rewards_sharpe_and_mdd_improvements() -> None:
    baseline = {
        "final_value": 100.0,
        "sharpe_ratio": 1.0,
        "sortino_ratio": 1.0,
        "max_drawdown": -0.20,
    }
    candidate = {
        "final_value": 101.0,
        "sharpe_ratio": 1.1,
        "sortino_ratio": 1.05,
        "max_drawdown": -0.18,
    }

    assert _score(candidate, baseline) > 0.0
