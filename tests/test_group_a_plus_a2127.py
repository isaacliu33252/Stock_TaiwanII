from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from group_a_plus.governance.latest import SUPPORTED_STRATEGIES
from group_a_plus.runners.a2127 import (
    A2127_ID,
    A2127_RECOVERY_00631L_BOOST_FRACTION,
    run_a2127,
)


def test_a2127_is_supported_as_shadow_candidate() -> None:
    assert SUPPORTED_STRATEGIES[A2127_ID] == "group_a_plus.runners.a2127"


@patch("group_a_plus.runners.a2127.run_a2118")
def test_a2127_wraps_a2118_with_recovery_boost(mock_run) -> None:
    mock_run.return_value = (
        {"design_notes": {}, "rules": {}, "metrics": {}, "execution": {}},
        pd.DataFrame({"portfolio_value": [1.0]}),
    )

    report, frame = run_a2127("2024-01-01", "2026-06-30", 1_000_000.0, Path("test.db"))

    kwargs = mock_run.call_args.kwargs
    assert kwargs["recovery_00631l_boost_fraction"] == A2127_RECOVERY_00631L_BOOST_FRACTION
    assert report["strategy"] == A2127_ID
    assert report["status"] == "research_candidate"
    assert frame["portfolio_value"].tolist() == [1.0]
