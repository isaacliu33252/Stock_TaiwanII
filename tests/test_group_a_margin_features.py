import pandas as pd

from train_dual_group_2024_2026 import (
    GROUP_A_MARGIN_FEATURE_COLUMNS,
    _compute_features,
    payload_uses_group_a_margin_features,
)


def test_compute_features_adds_group_a_margin_columns():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-05-01", periods=6, freq="B"),
            "open": [100, 101, 102, 103, 104, 105],
            "high": [101, 102, 103, 104, 105, 106],
            "low": [99, 100, 101, 102, 103, 104],
            "close": [100, 101, 102, 103, 104, 105],
            "volume": [1_000_000, 1_050_000, 980_000, 1_100_000, 1_030_000, 1_020_000],
            "margin_buy": [10_000, 12_000, 8_000, 15_000, 11_000, 13_000],
            "margin_sell": [7_000, 9_000, 10_000, 8_000, 7_500, 9_500],
            "margin_repayment": [500, 400, 300, 600, 450, 350],
            "margin_limit": [250_000, 250_000, 250_000, 255_000, 255_000, 255_000],
            "margin_balance": [3_200, 3_450, 3_300, 3_650, 3_780, 3_910],
            "margin_prev_balance": [3_100, 3_200, 3_450, 3_300, 3_650, 3_780],
            "offset_loan_short": [20, 10, 15, 25, 30, 20],
            "short_buy": [40, 38, 45, 35, 30, 28],
            "short_sell": [55, 50, 52, 48, 44, 42],
            "short_repayment": [2, 1, 0, 3, 2, 1],
            "short_limit": [250_000, 250_000, 250_000, 255_000, 255_000, 255_000],
            "short_balance": [1_300, 1_320, 1_310, 1_340, 1_360, 1_355],
            "short_prev_balance": [1_280, 1_300, 1_320, 1_310, 1_340, 1_360],
        }
    )

    out = _compute_features(df)

    for column in GROUP_A_MARGIN_FEATURE_COLUMNS:
        assert column in out.columns
        assert out[column].notna().all()


def test_payload_margin_flag_defaults_false():
    assert not payload_uses_group_a_margin_features({})
    assert not payload_uses_group_a_margin_features(
        {"group_a_margin_config": {"enabled": False}}
    )


def test_payload_margin_flag_reads_payload_config():
    payload = {"group_a_margin_config": {"enabled": True}}
    assert payload_uses_group_a_margin_features(payload)
