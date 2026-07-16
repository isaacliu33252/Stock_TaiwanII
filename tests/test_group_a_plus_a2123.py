from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from group_a_plus.governance.latest import SUPPORTED_STRATEGIES
from group_a_plus.runners.a2123 import (
    A2123_HOLD_DAYS,
    A2123_ID,
    A2123_PREVIOUS_DRAWDOWN_MAX,
    A2123_PREVIOUS_RETURN_FLOOR,
    A2123_PREVIOUS_RETURN_MAX,
    A2123_PREVIOUS_TAIL_RISK_SCORE_MIN,
    A2123_TRIM_FRACTION,
    run_a2123,
)


def test_a2123_is_supported_as_shadow_candidate() -> None:
    assert SUPPORTED_STRATEGIES[A2123_ID] == "group_a_plus.runners.a2123"


@patch("group_a_plus.runners.a2123.run_a2118")
def test_a2123_wraps_a2118_with_follow_through_trim(mock_run) -> None:
    mock_run.return_value = (
        {"design_notes": {}, "rules": {}, "metrics": {}, "execution": {}},
        pd.DataFrame({"portfolio_value": [1.0]}),
    )

    report, frame = run_a2123("2024-01-01", "2026-06-30", 1_000_000.0, Path("test.db"))

    kwargs = mock_run.call_args.kwargs
    assert kwargs["golden_follow_through_trim_enabled"] is True
    assert kwargs["golden_follow_through_trim_fraction"] == A2123_TRIM_FRACTION
    assert kwargs["golden_follow_through_previous_return_max"] == A2123_PREVIOUS_RETURN_MAX
    assert kwargs["golden_follow_through_previous_return_floor"] == A2123_PREVIOUS_RETURN_FLOOR
    assert kwargs["golden_follow_through_previous_tail_risk_score_min"] == A2123_PREVIOUS_TAIL_RISK_SCORE_MIN
    assert kwargs["golden_follow_through_previous_drawdown_max"] == A2123_PREVIOUS_DRAWDOWN_MAX
    assert kwargs["golden_follow_through_hold_days"] == A2123_HOLD_DAYS
    assert report["strategy"] == A2123_ID
    assert report["status"] == "research_candidate"
    assert frame["portfolio_value"].tolist() == [1.0]
