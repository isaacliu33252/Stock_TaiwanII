from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from group_a_plus.governance.latest import SUPPORTED_STRATEGIES
from group_a_plus.runners.a2125 import (
    A2125_ID,
    A2125_OVERRIDE_TAIL_DRAWDOWN_THRESHOLD,
    A2125_OVERRIDE_TAIL_RISK_SCORE,
    A2125_OVERRIDE_TAIL_USE_VAR_BREACH,
    run_a2125,
)


def test_a2125_is_supported_as_shadow_candidate() -> None:
    assert SUPPORTED_STRATEGIES[A2125_ID] == "group_a_plus.runners.a2125"


@patch("group_a_plus.runners.a2125.run_a2118")
def test_a2125_wraps_a2118_with_tail_override(mock_run) -> None:
    mock_run.return_value = (
        {"design_notes": {}, "rules": {}, "metrics": {}, "execution": {}},
        pd.DataFrame({"portfolio_value": [1.0]}),
    )

    report, frame = run_a2125("2024-01-01", "2026-06-30", 1_000_000.0, Path("test.db"))

    kwargs = mock_run.call_args.kwargs
    assert kwargs["override_tail_risk_score"] == A2125_OVERRIDE_TAIL_RISK_SCORE
    assert kwargs["override_tail_drawdown_threshold"] == A2125_OVERRIDE_TAIL_DRAWDOWN_THRESHOLD
    assert kwargs["override_tail_use_var_breach"] is A2125_OVERRIDE_TAIL_USE_VAR_BREACH
    assert report["strategy"] == A2125_ID
    assert report["status"] == "research_candidate"
    assert frame["portfolio_value"].tolist() == [1.0]
