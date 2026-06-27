import pandas as pd

from FinRL.data.stock_db import (
    _parse_tpex_institutional_csv,
    _parse_tpex_margin_csv,
    parse_shareholding_distribution_rows,
)


def test_parse_tpex_institutional_csv_smoke() -> None:
    text = """115年05月26日 三大法人買賣超日報(股)
代號,名稱,外資及陸資(不含外資自營商)-買進股數,外資及陸資(不含外資自營商)-賣出股數,外資及陸資(不含外資自營商)-買賣超股數,外資自營商-買進股數,外資自營商-賣出股數,外資自營商-買賣超股數,外資及陸資-買進股數,外資及陸資-賣出股數,外資及陸資-買賣超股數,投信-買進股數,投信-賣出股數,投信-買賣超股數,自營商(自行買賣)-買進股數,自營商(自行買賣)-賣出股數,自營商(自行買賣)-買賣超股數,自營商(避險)-買進股數,自營商(避險)-賣出股數,自營商(避險)-買賣超股數,自營商-買進股數,自營商-賣出股數,自營商-買賣超股數,三大法人買賣超股數合計
00679B,元大美債20年,1694039,3658000,-1963961,0,0,0,1694039,3658000,-1963961,0,0,0,0,0,0,16428007,1506000,14922007,16428007,1506000,14922007,12958046
"""
    frame = _parse_tpex_institutional_csv(text, pd.Timestamp("2026-05-26"))
    assert list(frame["ticker"]) == ["00679B.TWO"]
    assert float(frame.loc[0, "foreign_net_buy"]) == -1963961.0
    assert float(frame.loc[0, "dealer_net_buy"]) == 14922007.0
    assert float(frame.loc[0, "institutional_total_net_buy"]) == 12958046.0
    assert frame.loc[0, "source"] == "tpex_3itrade_hedge"


def test_parse_tpex_margin_csv_smoke() -> None:
    text = """上櫃股票融資融券餘額
資料日期:115/05/26
代號,名稱,前資餘(張),資買,資賣,現償,資餘,資限額,資使用率(%),券前餘,券賣,券買,券償,券餘,券限額,券使用率(%),資券互抵,成交值(仟元),資佔成交值比重(%),註記
00679B,元大美債20年,6127,77,21,1,6182,46,0.34,0,1,0,0,1,0,0.0,0,1813673,0,
"""
    frame = _parse_tpex_margin_csv(text, pd.Timestamp("2026-05-26"))
    assert list(frame["ticker"]) == ["00679B.TWO"]
    assert float(frame.loc[0, "margin_prev_balance"]) == 6127.0
    assert float(frame.loc[0, "margin_buy"]) == 77.0
    assert float(frame.loc[0, "margin_balance"]) == 6182.0
    assert float(frame.loc[0, "short_sell"]) == 1.0
    assert float(frame.loc[0, "short_balance"]) == 1.0
    assert frame.loc[0, "source"] == "tpex_margin_bal"


def test_parse_tdcc_shareholding_distribution_rows() -> None:
    frame = parse_shareholding_distribution_rows(
        [
            {
                "\ufeff資料日期": "20260529",
                "證券代號": "2330",
                "持股分級": "15",
                "人數": "100",
                "股數": "2000000",
                "占集保庫存數比例%": "7.50",
            }
        ]
    )
    assert list(frame["stock_id"]) == ["2330"]
    assert str(frame.loc[0, "dt"]) == "2026-05-29"
    assert int(frame.loc[0, "holding_level"]) == 15
    assert int(frame.loc[0, "people"]) == 100
    assert int(frame.loc[0, "shares"]) == 2000000
    assert float(frame.loc[0, "percent"]) == 7.50


def test_parse_finmind_shareholding_distribution_rows() -> None:
    frame = parse_shareholding_distribution_rows(
        {
            "data": [
                {
                    "date": "2026-05-29",
                    "stock_id": "2330",
                    "HoldingSharesLevel": "more than 1,000,001",
                    "people": 100,
                    "unit": 2000000,
                    "percent": 7.50,
                }
            ]
        },
        source="finmind",
    )
    assert list(frame["stock_id"]) == ["2330"]
    assert int(frame.loc[0, "holding_level"]) == 15
    assert frame.loc[0, "source"] == "finmind"
