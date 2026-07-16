import pandas as pd

from scripts.evaluate.evaluate_a2118_decision_focused_overlap import _extreme_warning_proxy


def test_extreme_warning_proxy_requires_h20_and_mdd_thresholds() -> None:
    index = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"])
    panel = pd.DataFrame(
        {
            "prob_up_h20": [0.21, 0.21, 0.40],
            "prob_fwd_mdd_gt5_h20": [0.86, 0.80, 0.90],
        },
        index=index,
    )

    out = _extreme_warning_proxy(panel, pd.DatetimeIndex(index), h20_max=0.22, mdd_min=0.85)

    assert out.tolist() == [True, False, False]


def test_extreme_warning_proxy_missing_panel_is_false() -> None:
    index = pd.to_datetime(["2026-01-05"])

    out = _extreme_warning_proxy(None, pd.DatetimeIndex(index), h20_max=0.22, mdd_min=0.85)

    assert out.tolist() == [False]
