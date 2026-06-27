import pandas as pd

from train_dual_group_2024_2026 import (
    GROUP_A_INSTITUTIONAL_FEATURE_COLUMNS,
    _compute_features,
    payload_uses_group_a_institutional_features,
)


def test_compute_features_adds_group_a_institutional_columns():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-05-01", periods=6, freq="B"),
            "open": [100, 101, 102, 103, 104, 105],
            "high": [101, 102, 103, 104, 105, 106],
            "low": [99, 100, 101, 102, 103, 104],
            "close": [100, 101, 102, 103, 104, 105],
            "volume": [1_000_000, 1_050_000, 980_000, 1_100_000, 1_030_000, 1_020_000],
            "foreign_net_buy": [10_000, 12_000, -3_000, 5_000, 8_000, 7_000],
            "investment_trust_net_buy": [0, 2_000, 1_000, 0, 3_000, 0],
            "dealer_net_buy": [1_000, -500, 2_000, 1_500, 0, 2_500],
            "institutional_total_net_buy": [11_000, 13_500, 0, 6_500, 11_000, 9_500],
        }
    )

    out = _compute_features(df)

    for column in GROUP_A_INSTITUTIONAL_FEATURE_COLUMNS:
        assert column in out.columns
        assert out[column].notna().all()


def test_payload_institutional_flag_defaults_false():
    assert not payload_uses_group_a_institutional_features({})
    assert not payload_uses_group_a_institutional_features(
        {"group_a_institutional_config": {"enabled": False}}
    )


def test_payload_institutional_flag_reads_payload_config():
    payload = {"group_a_institutional_config": {"enabled": True}}
    assert payload_uses_group_a_institutional_features(payload)
