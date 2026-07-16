from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from group_a_plus.governance.latest import SUPPORTED_STRATEGIES
from group_a_plus.runners.a2121 import (
    A2121_ID,
    A2121_LOW_RISK_EXIT_MA_GAP,
    A2121_LOW_RISK_EXIT_SCORE_THRESHOLD,
    run_a2121,
)


def test_a2121_is_supported_as_shadow_candidate() -> None:
    assert SUPPORTED_STRATEGIES[A2121_ID] == "group_a_plus.runners.a2121"


@patch("group_a_plus.runners.a2121.run_a2118")
def test_a2121_wraps_a2118_with_low_risk_exit(mock_run) -> None:
    mock_run.return_value = (
        {"design_notes": {}, "rules": {}, "metrics": {}, "execution": {}},
        pd.DataFrame({"portfolio_value": [1.0]}),
    )

    report, frame = run_a2121("2024-01-01", "2026-06-30", 1_000_000.0, Path("test.db"))

    kwargs = mock_run.call_args.kwargs
    assert kwargs["low_risk_exit_ma_gap"] == A2121_LOW_RISK_EXIT_MA_GAP
    assert kwargs["low_risk_exit_score_threshold"] == A2121_LOW_RISK_EXIT_SCORE_THRESHOLD
    assert report["strategy"] == A2121_ID
    assert report["status"] == "research_candidate"
    assert frame["portfolio_value"].tolist() == [1.0]
