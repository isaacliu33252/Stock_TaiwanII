from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from group_a_plus.governance.latest import SUPPORTED_STRATEGIES
from group_a_plus.runners.a2122 import (
    A2122_DRAWDOWN_MAX,
    A2122_ID,
    A2122_RETURN_VAR_BREACH,
    A2122_TAIL_RISK_SCORE_MIN,
    A2122_TAIL_TRIM_FRACTION,
    run_a2122,
)


def test_a2122_is_supported_as_shadow_candidate() -> None:
    assert SUPPORTED_STRATEGIES[A2122_ID] == "group_a_plus.runners.a2122"


@patch("group_a_plus.runners.a2122.run_a2118")
def test_a2122_wraps_a2118_with_golden_tail_trim(mock_run) -> None:
    mock_run.return_value = (
        {"design_notes": {}, "rules": {}, "metrics": {}, "execution": {}},
        pd.DataFrame({"portfolio_value": [1.0]}),
    )

    report, frame = run_a2122("2024-01-01", "2026-06-30", 1_000_000.0, Path("test.db"))

    kwargs = mock_run.call_args.kwargs
    assert kwargs["golden_tail_trim_enabled"] is True
    assert kwargs["golden_tail_trim_fraction"] == A2122_TAIL_TRIM_FRACTION
    assert kwargs["golden_tail_trim_tail_risk_score_min"] == A2122_TAIL_RISK_SCORE_MIN
    assert kwargs["golden_tail_trim_drawdown_max"] == A2122_DRAWDOWN_MAX
    assert kwargs["golden_tail_trim_return_var_breach"] is A2122_RETURN_VAR_BREACH
    assert report["strategy"] == A2122_ID
    assert report["status"] == "research_candidate"
    assert frame["portfolio_value"].tolist() == [1.0]
