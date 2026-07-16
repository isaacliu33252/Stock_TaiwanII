from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from group_a_plus.governance.latest import SUPPORTED_STRATEGIES
from group_a_plus.runners.a2129 import (
    A2129_ID,
    A2129_RECOVERY_00631L_BOOST_FRACTION,
    A2129_RECOVERY_00631L_BOOST_MAX_AGE_DAYS,
    run_a2129,
)


def test_a2129_is_supported_as_shadow_candidate() -> None:
    assert SUPPORTED_STRATEGIES[A2129_ID] == "group_a_plus.runners.a2129"


@patch("group_a_plus.runners.a2129.run_a2118")
def test_a2129_wraps_a2118_with_aggressive_recovery_boost_age_guard(mock_run) -> None:
    mock_run.return_value = (
        {"design_notes": {}, "rules": {}, "metrics": {}, "execution": {}},
        pd.DataFrame({"portfolio_value": [1.0]}),
    )

    report, frame = run_a2129("2024-01-01", "2026-06-30", 1_000_000.0, Path("test.db"))

    kwargs = mock_run.call_args.kwargs
    assert kwargs["recovery_00631l_boost_fraction"] == A2129_RECOVERY_00631L_BOOST_FRACTION
    assert kwargs["recovery_00631l_boost_max_age_days"] == A2129_RECOVERY_00631L_BOOST_MAX_AGE_DAYS
    assert report["strategy"] == A2129_ID
    assert report["status"] == "research_candidate"
    assert frame["portfolio_value"].tolist() == [1.0]
