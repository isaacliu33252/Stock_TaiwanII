from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from group_a_plus.governance.latest import SUPPORTED_STRATEGIES
from group_a_plus.runners.a2118 import RECOVERY_00631L_BOOST_REGIME, _apply_recovery_boost_age_guard
from group_a_plus.runners.a2128 import (
    A2128_ID,
    A2128_RECOVERY_00631L_BOOST_FRACTION,
    A2128_RECOVERY_00631L_BOOST_MAX_AGE_DAYS,
    run_a2128,
)


def test_a2128_is_supported_as_shadow_candidate() -> None:
    assert SUPPORTED_STRATEGIES[A2128_ID] == "group_a_plus.runners.a2128"


def test_recovery_boost_age_guard_marks_only_first_n_recovery_days() -> None:
    index = pd.date_range("2026-01-01", periods=8, freq="D")
    regime = pd.Series(
        [
            "golden1",
            "group_a_plus_recovery",
            "group_a_plus_recovery",
            "group_a_plus_recovery",
            "golden1",
            "group_a_plus_recovery",
            "group_a_plus_recovery",
            "group_a_plus_recovery",
        ],
        index=index,
    )

    modified, info = _apply_recovery_boost_age_guard(regime, max_age_days=2)

    assert modified.tolist() == [
        "golden1",
        RECOVERY_00631L_BOOST_REGIME,
        RECOVERY_00631L_BOOST_REGIME,
        "group_a_plus_recovery",
        "golden1",
        RECOVERY_00631L_BOOST_REGIME,
        RECOVERY_00631L_BOOST_REGIME,
        "group_a_plus_recovery",
    ]
    assert info["recovery_00631l_boost_recovery_days"] == 6
    assert info["recovery_00631l_boost_days"] == 4


@patch("group_a_plus.runners.a2128.run_a2118")
def test_a2128_wraps_a2118_with_recovery_boost_age_guard(mock_run) -> None:
    mock_run.return_value = (
        {"design_notes": {}, "rules": {}, "metrics": {}, "execution": {}},
        pd.DataFrame({"portfolio_value": [1.0]}),
    )

    report, frame = run_a2128("2024-01-01", "2026-06-30", 1_000_000.0, Path("test.db"))

    kwargs = mock_run.call_args.kwargs
    assert kwargs["recovery_00631l_boost_fraction"] == A2128_RECOVERY_00631L_BOOST_FRACTION
    assert kwargs["recovery_00631l_boost_max_age_days"] == A2128_RECOVERY_00631L_BOOST_MAX_AGE_DAYS
    assert report["strategy"] == A2128_ID
    assert report["status"] == "research_candidate"
    assert frame["portfolio_value"].tolist() == [1.0]
