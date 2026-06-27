from unittest.mock import patch

import pandas as pd

from train_dual_group_2024_2026 import (
    GROUP_A_MARGIN_SHARED_FEATURE_COLUMNS,
    attach_group_a_margin_shared_features_db_first,
    payload_uses_group_a_margin_shared_features,
)


def _sample_margin_frame(dates: pd.DatetimeIndex, scale: float) -> pd.DataFrame:
    base = pd.DataFrame({"dt": dates})
    base["margin_buy"] = [10_000 * scale, 11_000 * scale, 12_000 * scale, 9_000 * scale, 13_000 * scale, 14_000 * scale]
    base["margin_sell"] = [8_000 * scale, 8_500 * scale, 9_500 * scale, 7_500 * scale, 9_000 * scale, 10_000 * scale]
    base["margin_repayment"] = [400 * scale, 450 * scale, 300 * scale, 350 * scale, 500 * scale, 450 * scale]
    base["margin_limit"] = [300_000 * scale] * len(base)
    base["margin_balance"] = [12_000 * scale, 12_300 * scale, 12_900 * scale, 12_700 * scale, 13_400 * scale, 13_900 * scale]
    base["margin_prev_balance"] = [11_800 * scale, 12_000 * scale, 12_300 * scale, 12_900 * scale, 12_700 * scale, 13_400 * scale]
    base["offset_loan_short"] = [40 * scale, 35 * scale, 38 * scale, 42 * scale, 44 * scale, 46 * scale]
    base["short_buy"] = [70 * scale, 65 * scale, 60 * scale, 58 * scale, 62 * scale, 64 * scale]
    base["short_sell"] = [90 * scale, 88 * scale, 84 * scale, 80 * scale, 86 * scale, 90 * scale]
    base["short_repayment"] = [5 * scale, 4 * scale, 3 * scale, 5 * scale, 4 * scale, 3 * scale]
    base["short_limit"] = [300_000 * scale] * len(base)
    base["short_balance"] = [2_400 * scale, 2_450 * scale, 2_520 * scale, 2_500 * scale, 2_560 * scale, 2_610 * scale]
    base["short_prev_balance"] = [2_350 * scale, 2_400 * scale, 2_450 * scale, 2_520 * scale, 2_500 * scale, 2_560 * scale]
    return base


def test_attach_group_a_margin_shared_features_adds_columns():
    dates = pd.date_range("2026-05-01", periods=6, freq="B")
    stock_data = {
        "0050.TW": pd.DataFrame({"date": dates, "volume": [1_000_000, 1_020_000, 1_010_000, 980_000, 1_030_000, 1_040_000]}),
        "00631L.TW": pd.DataFrame({"date": dates, "volume": [1_500_000, 1_520_000, 1_510_000, 1_480_000, 1_530_000, 1_540_000]}),
        "00632R.TW": pd.DataFrame({"date": dates, "volume": [800_000, 780_000, 790_000, 760_000, 810_000, 820_000]}),
    }
    sample_frames = {
        "0050.TW": _sample_margin_frame(dates, 1.0),
        "00631L.TW": _sample_margin_frame(dates, 2.0),
        "00632R.TW": _sample_margin_frame(dates, 1.5),
    }

    with patch(
        "train_dual_group_2024_2026.query_margin_data",
        side_effect=lambda ticker, start, end: sample_frames[ticker].copy(),
    ):
        out = attach_group_a_margin_shared_features_db_first(
            stock_data,
            ["0050.TW", "00631L.TW", "00632R.TW"],
            "2026-05-01",
            "2026-05-31",
        )

    for ticker in ["0050.TW", "00631L.TW", "00632R.TW"]:
        for column in GROUP_A_MARGIN_SHARED_FEATURE_COLUMNS:
            assert column in out[ticker].columns
            assert out[ticker][column].notna().all()


def test_payload_margin_shared_flag_defaults_false():
    assert not payload_uses_group_a_margin_shared_features({})
    assert not payload_uses_group_a_margin_shared_features(
        {"group_a_margin_shared_config": {"enabled": False}}
    )


def test_payload_margin_shared_flag_reads_payload_config():
    payload = {"group_a_margin_shared_config": {"enabled": True}}
    assert payload_uses_group_a_margin_shared_features(payload)
