from __future__ import annotations

import pytest

from taifex_futures_data import (
    _to_float,
    normalize_daily_rows,
    normalize_historical_daily_csv,
    normalize_institutional_rows,
)


def test_to_float_handles_taifex_nulls_commas_and_percentages() -> None:
    assert _to_float("1,234") == pytest.approx(1234.0)
    assert _to_float("-") == pytest.approx(0.0)
    assert _to_float("NULL") == pytest.approx(0.0)
    assert _to_float("1.23%") == pytest.approx(0.0123)


def test_normalize_daily_rows_keeps_tx_sessions() -> None:
    rows = [
        {
            "Date": "20260605",
            "Contract": "TX",
            "ContractMonth(Week)": "202606",
            "Open": "21600",
            "High": "21700",
            "Low": "21500",
            "Last": "21680",
            "Change": "-10",
            "%": "-0.05%",
            "Volume": "82,100",
            "SettlementPrice": "21675",
            "OpenInterest": "90,000",
            "BestBid": "21679",
            "BestAsk": "21680",
            "HistoricalHigh": "24400",
            "HistoricalLow": "12000",
            "TradingSession": "一般",
        },
        {
            "Date": "20260605",
            "Contract": "MTX",
            "ContractMonth(Week)": "202606",
            "Last": "21680",
            "TradingSession": "一般",
        },
    ]

    normalized = normalize_daily_rows(rows, ["TX"])

    assert len(normalized) == 1
    row = normalized.iloc[0]
    assert str(row["dt"]) == "2026-06-05"
    assert row["contract"] == "TX"
    assert row["trading_session"] == "一般"
    assert row["last"] == pytest.approx(21680.0)
    assert row["pct_change"] == pytest.approx(-0.0005)
    assert row["volume"] == pytest.approx(82100.0)


def test_normalize_historical_daily_csv_maps_chinese_columns() -> None:
    raw = (
        "交易日期,契約,到期月份(週別),開盤價,最高價,最低價,收盤價,漲跌價,漲跌%,成交量,"
        "結算價,未沖銷契約數,最後最佳買價,最後最佳賣價,歷史最高價,歷史最低價,交易時段\n"
        "20240102,TX,202401,17500,17600,17480,17580,80,0.46%,100000,17575,90000,17579,17580,20000,10000,一般\n"
        "20240102,TE,202401,900,910,895,905,5,0.55%,1000,904,500,904,905,1000,800,一般\n"
    ).encode("big5")

    normalized = normalize_historical_daily_csv(raw, ["TX"])

    assert len(normalized) == 1
    row = normalized.iloc[0]
    assert str(row["dt"]) == "2024-01-02"
    assert row["contract"] == "TX"
    assert row["contract_month"] == "202401"
    assert row["trading_session"] == "一般"
    assert row["last"] == pytest.approx(17580.0)
    assert row["pct_change"] == pytest.approx(0.0046)
    assert row["source"] == "taifex_fut_data_down"


def test_normalize_institutional_rows_keeps_tx_contract_code() -> None:
    rows = [
        {
            "Date": "20260605",
            "ContractCode": "臺股期貨",
            "Item": "外資及陸資",
            "TradingVolume(Long)": "37,391",
            "TradingValue(Long)(Thousands)": "81,412,431",
            "TradingVolume(Short)": "36,375",
            "TradingValue(Short)(Thousands)": "79,260,844",
            "TradingVolume(Net)": "1,016",
            "TradingValue(Net)(Thousands)": "2,151,587",
            "OpenInterest(Long)": "39,647",
            "ContractValueofOpenInterest(Long)(Thousands)": "86,534,753",
            "OpenInterest(Short)": "108,793",
            "ContractValueofOpenInterest(Short)(Thousands)": "237,508,657",
            "OpenInterest(Net)": "-69,146",
            "ContractValueofOpenInterest(Net)(Thousands)": "-150,973,904",
        },
        {
            "Date": "20260605",
            "ContractCode": "小型臺指期貨",
            "Item": "外資及陸資",
            "TradingVolume(Net)": "999",
        },
    ]

    normalized = normalize_institutional_rows(rows, ["臺股期貨"])

    assert len(normalized) == 1
    row = normalized.iloc[0]
    assert str(row["dt"]) == "2026-06-05"
    assert row["contract_code"] == "臺股期貨"
    assert row["institution"] == "外資及陸資"
    assert row["trading_volume_net"] == pytest.approx(1016.0)
    assert row["open_interest_net"] == pytest.approx(-69146.0)
