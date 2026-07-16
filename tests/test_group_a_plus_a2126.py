from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd

from group_a_plus.governance.latest import SUPPORTED_STRATEGIES
from group_a_plus.runners.a2126 import (
    A2126_DRAWDOWN_MAX,
    A2126_EFFECTIVE_MAX_00631L_WEIGHT,
    A2126_ID,
    A2126_LEGACY_MAX_00631L_WEIGHT,
    A2126_MAX_00631L_WEIGHT,
    A2126_REALIZED_VOL_RATIO_MIN,
    A2126_TAIL_RISK_SCORE_MIN,
    run_a2126,
)


def test_a2126_is_supported_as_shadow_candidate() -> None:
    assert SUPPORTED_STRATEGIES[A2126_ID] == "group_a_plus.runners.a2126"


def test_a2126_tracks_legacy_default_and_effective_research_cap() -> None:
    assert A2126_MAX_00631L_WEIGHT == A2126_LEGACY_MAX_00631L_WEIGHT
    assert A2126_EFFECTIVE_MAX_00631L_WEIGHT < A2126_LEGACY_MAX_00631L_WEIGHT
    assert A2126_EFFECTIVE_MAX_00631L_WEIGHT == 0.10


@patch("group_a_plus.runners.a2126.run_a2118")
def test_a2126_wraps_a2118_with_golden_leverage_cap(mock_run) -> None:
    mock_run.return_value = (
        {"design_notes": {}, "rules": {}, "metrics": {}, "execution": {}},
        pd.DataFrame({"portfolio_value": [1.0]}),
    )

    report, frame = run_a2126("2024-01-01", "2026-06-30", 1_000_000.0, Path("test.db"))

    kwargs = mock_run.call_args.kwargs
    assert kwargs["golden_leverage_cap_enabled"] is True
    assert kwargs["golden_leverage_cap_max_00631l_weight"] == A2126_MAX_00631L_WEIGHT
    assert kwargs["golden_leverage_cap_tail_risk_score_min"] == A2126_TAIL_RISK_SCORE_MIN
    assert kwargs["golden_leverage_cap_realized_vol_ratio_min"] == A2126_REALIZED_VOL_RATIO_MIN
    assert kwargs["golden_leverage_cap_drawdown_max"] == A2126_DRAWDOWN_MAX
    assert report["strategy"] == A2126_ID
    assert report["status"] == "research_candidate"
    assert frame["portfolio_value"].tolist() == [1.0]


@patch("group_a_plus.runners.a2126.run_a2118")
def test_a2126_allows_legacy_cap_for_comparison(mock_run) -> None:
    mock_run.return_value = (
        {"design_notes": {}, "rules": {}, "metrics": {}, "execution": {}},
        pd.DataFrame({"portfolio_value": [1.0]}),
    )

    run_a2126(
        "2024-01-01",
        "2026-06-30",
        1_000_000.0,
        Path("test.db"),
        max_00631l_weight=A2126_LEGACY_MAX_00631L_WEIGHT,
    )

    kwargs = mock_run.call_args.kwargs
    assert kwargs["golden_leverage_cap_max_00631l_weight"] == A2126_LEGACY_MAX_00631L_WEIGHT
