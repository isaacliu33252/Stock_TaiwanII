import pandas as pd

from FinRL import portfolio_data_loader as loader


def test_repair_missing_twse_close_rows_uses_official_unadjusted(monkeypatch):
    yahoo = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-09-09")],
            "open": [37.779999],
            "high": [38.200001],
            "low": [37.459999],
            "close": [float("nan")],
            "adj close": [float("nan")],
            "volume": [129_547_164],
        }
    )

    def fake_official(ticker, start_date, end_date, *, apply_split_adjustments=True):
        assert ticker == "00631L.TW"
        assert start_date == "2026-09-09"
        assert end_date == "2026-09-09"
        assert apply_split_adjustments is False
        return pd.DataFrame(
            {
                "date": [pd.Timestamp("2026-09-09")],
                "open": [37.78],
                "high": [38.20],
                "low": [37.46],
                "close": [37.54],
                "volume": [130_034_284],
            }
        )

    monkeypatch.setattr(loader, "_download_twse_monthly_history", fake_official)

    repaired = loader._repair_missing_twse_close_rows(yahoo, "00631L.TW")

    assert repaired.loc[0, "close"] == 37.54
    assert repaired.loc[0, "adj close"] == 37.54
    assert repaired.loc[0, "volume"] == 130_034_284


def test_repair_missing_twse_close_rows_skips_tpex(monkeypatch):
    yahoo = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-09-09")],
            "open": [25.58],
            "high": [25.60],
            "low": [25.53],
            "close": [float("nan")],
            "volume": [17_810_000],
        }
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("TWSE repair should not be used for TPEX tickers")

    monkeypatch.setattr(loader, "_download_twse_monthly_history", fail_if_called)

    repaired = loader._repair_missing_twse_close_rows(yahoo, "00679B.TWO")

    assert pd.isna(repaired.loc[0, "close"])
