from __future__ import annotations

import pandas as pd

from generate_dual_group_signal import _env_kwargs_from_payload
from train_dual_group_2024_2026 import (
    GROUP_B_INSTITUTIONAL_FEATURE_COLUMNS,
    GROUP_B_MARGIN_FEATURE_COLUMNS,
    _align_panel,
    payload_uses_group_b_institutional_features,
    payload_uses_group_b_margin_features,
)


def test_group_b_payload_flags_round_trip() -> None:
    payload = {
        "group_b_profile": "balanced",
        "group_b_action_schema": "core6_cash20_v1",
        "group_b_use_llm_sentiment": True,
        "group_b_institutional_config": {"enabled": True},
        "group_b_margin_config": {"enabled": True},
        "group_b": {
            "shared_feature_cols": [
                "llm_sentiment_score",
                "llm_sentiment_confidence",
                "llm_risk_off_score",
                "llm_news_intensity",
            ]
        },
    }
    env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_b")
    assert env_kwargs["group_b_action_schema"] == "core6_cash20_v1"
    assert payload_uses_group_b_institutional_features(payload) is True
    assert payload_uses_group_b_margin_features(payload) is True
    assert "llm_sentiment_score" in shared_feature_cols


def test_group_b_align_panel_keeps_institutional_and_margin_features() -> None:
    dates = pd.date_range("2025-01-02", periods=4, freq="B")
    stock_data = {}
    tickers = [
        "0056.TW",
        "00713.TW",
        "00646.TW",
        "00679B.TWO",
        "00751B.TWO",
    ]
    for i, ticker in enumerate(tickers, start=1):
        stock_data[ticker] = pd.DataFrame(
            {
                "date": dates,
                "open": [10.0 + i, 10.1 + i, 10.2 + i, 10.3 + i],
                "high": [10.3 + i, 10.4 + i, 10.5 + i, 10.6 + i],
                "low": [9.9 + i, 10.0 + i, 10.1 + i, 10.2 + i],
                "close": [10.2 + i, 10.3 + i, 10.4 + i, 10.5 + i],
                "volume": [1000, 1100, 1200, 1300],
                "dividends": [0.0, 0.0, 0.0, 0.0],
                "foreign_net_buy": [10.0, 12.0, 8.0, 6.0],
                "investment_trust_net_buy": [2.0, 1.0, 0.0, -1.0],
                "dealer_net_buy": [1.0, 0.0, 1.0, 0.0],
                "institutional_total_net_buy": [13.0, 13.0, 9.0, 5.0],
                "margin_buy": [50.0, 55.0, 45.0, 40.0],
                "margin_sell": [20.0, 18.0, 22.0, 21.0],
                "margin_repayment": [5.0, 6.0, 5.0, 4.0],
                "margin_limit": [1000.0, 1000.0, 1000.0, 1000.0],
                "margin_balance": [300.0, 305.0, 310.0, 315.0],
                "margin_prev_balance": [290.0, 300.0, 305.0, 310.0],
                "offset_loan_short": [0.0, 0.0, 0.0, 0.0],
                "short_buy": [6.0, 5.0, 4.0, 5.0],
                "short_sell": [9.0, 8.0, 10.0, 11.0],
                "short_repayment": [1.0, 1.0, 1.0, 1.0],
                "short_limit": [500.0, 500.0, 500.0, 500.0],
                "short_balance": [60.0, 62.0, 63.0, 65.0],
                "short_prev_balance": [58.0, 60.0, 62.0, 63.0],
            }
        )

    panel = _align_panel(
        stock_data,
        tickers,
        "2025-01-02",
        "2025-01-31",
        shared_feature_cols=None,
    )
    assert not panel.empty
    assert f"{tickers[0]}_{GROUP_B_INSTITUTIONAL_FEATURE_COLUMNS[0]}" in panel.columns
    assert f"{tickers[0]}_{GROUP_B_MARGIN_FEATURE_COLUMNS[0]}" in panel.columns
