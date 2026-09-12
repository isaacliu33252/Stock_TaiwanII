from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.evaluate.build_market_aligned_sentiment_shadow import (
    _full_ticker,
    _price_table,
    build_market_aligned_sentiment_shadow,
    dedupe_headlines,
    load_finmind_records,
    move_explained_by_news,
    rolling_alpha_corr,
    score_daily_sentiment,
)


class TestFullTicker(unittest.TestCase):
    def test_00679b_uses_twse_otc_suffix_not_tw(self) -> None:
        # 00679B trades on TPEx, not TWSE; ohlcv stores it as "00679B.TWO".
        # Regression guard for a bug caught during manual verification where
        # this ticker's price/return silently came back all-null.
        self.assertEqual(_full_ticker("00679B"), "00679B.TWO")

    def test_other_tickers_use_default_tw_suffix(self) -> None:
        for ticker in ["0050", "00631L", "00632R"]:
            self.assertEqual(_full_ticker(ticker), f"{ticker}.TW")


class TestPriceTable(unittest.TestCase):
    def test_2330_routes_to_external_market_ohlcv(self) -> None:
        # 2330's own OHLCV lives in external_market_ohlcv (yfinance-sourced),
        # not the main ohlcv table (confirmed during the LETF-paper review).
        # Querying the main table for 2330 silently returns zero rows, not
        # an error -- this regression guard is for exactly that.
        self.assertEqual(_price_table("2330"), "external_market_ohlcv")

    def test_other_tickers_use_main_ohlcv_table(self) -> None:
        for ticker in ["0050", "00631L", "00632R", "00679B"]:
            self.assertEqual(_price_table(ticker), "ohlcv")


class TestLoadFinmindRecords(unittest.TestCase):
    def test_unions_multiple_files_and_filters_by_ticker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path_a = Path(tmp_dir) / "a.jsonl"
            path_b = Path(tmp_dir) / "b.jsonl"
            path_a.write_text(
                json.dumps({"date": "2026-06-30", "finmind_stock_id": "0050", "title": "舊資料"}) + "\n",
                encoding="utf-8",
            )
            path_b.write_text(
                json.dumps({"date": "2026-08-05", "finmind_stock_id": "0050", "title": "新資料"}) + "\n"
                + json.dumps({"date": "2026-08-05", "finmind_stock_id": "2330", "title": "不在清單裡"}) + "\n",
                encoding="utf-8",
            )
            records = load_finmind_records([path_a, path_b], tickers=["0050"])
            self.assertEqual(len(records), 2)
            self.assertEqual({r["date"] for r in records}, {"2026-06-30", "2026-08-05"})

    def test_missing_file_is_skipped_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "does_not_exist.jsonl"
            records = load_finmind_records([missing], tickers=["0050"])
            self.assertEqual(records, [])


class TestDedupeHeadlines(unittest.TestCase):
    def test_drops_same_day_re_syndicated_copies(self) -> None:
        records = [
            {"date": "2026-08-01", "finmind_stock_id": "0050", "title": "0050創新高 - Yahoo奇摩股市"},
            {"date": "2026-08-01", "finmind_stock_id": "0050", "title": "0050創新高 - FTNN新聞網"},
            {"date": "2026-08-01", "finmind_stock_id": "0050", "title": "0050創新高 - 鏡週刊"},
            {"date": "2026-08-01", "finmind_stock_id": "0050", "title": "外資賣超0050 - Yahoo奇摩股市"},
        ]
        deduped = dedupe_headlines(records)
        self.assertEqual(len(deduped), 2)

    def test_keeps_same_headline_on_different_days_or_tickers(self) -> None:
        records = [
            {"date": "2026-08-01", "finmind_stock_id": "0050", "title": "利多消息 - A"},
            {"date": "2026-08-02", "finmind_stock_id": "0050", "title": "利多消息 - A"},
            {"date": "2026-08-01", "finmind_stock_id": "00631L", "title": "利多消息 - A"},
        ]
        deduped = dedupe_headlines(records)
        self.assertEqual(len(deduped), 3)


class TestScoreDailySentiment(unittest.TestCase):
    def test_aggregates_mean_score_and_count_per_day_ticker(self) -> None:
        records = [
            {"date": "2026-08-01", "finmind_stock_id": "0050", "title": "利多 大漲 大好"},
            {"date": "2026-08-01", "finmind_stock_id": "0050", "title": "普通新聞內容"},
            {"date": "2026-08-01", "finmind_stock_id": "00631L", "title": "利空 大跌 重挫"},
        ]
        panel = score_daily_sentiment(records)
        row_0050 = panel[(panel["ticker"] == "0050")].iloc[0]
        self.assertEqual(int(row_0050["news_intensity"]), 2)
        row_631l = panel[(panel["ticker"] == "00631L")].iloc[0]
        self.assertEqual(int(row_631l["news_intensity"]), 1)
        self.assertLess(row_631l["sentiment_score"], row_0050["sentiment_score"])

    def test_empty_input_returns_empty_frame_with_expected_columns(self) -> None:
        panel = score_daily_sentiment([])
        self.assertTrue(panel.empty)
        self.assertIn("sentiment_score", panel.columns)


class TestMoveExplainedByNews(unittest.TestCase):
    def test_below_threshold_move_is_null_not_false(self) -> None:
        self.assertIsNone(move_explained_by_news(0.5, 0.001, alpha_threshold=0.005))

    def test_same_direction_above_threshold_is_true(self) -> None:
        self.assertTrue(move_explained_by_news(0.3, 0.02, alpha_threshold=0.005))

    def test_opposite_direction_above_threshold_is_false(self) -> None:
        self.assertFalse(move_explained_by_news(0.3, -0.02, alpha_threshold=0.005))

    def test_missing_inputs_return_none(self) -> None:
        self.assertIsNone(move_explained_by_news(float("nan"), 0.02, alpha_threshold=0.005))
        self.assertIsNone(move_explained_by_news(0.3, float("nan"), alpha_threshold=0.005))

    def test_exactly_zero_sentiment_is_null_not_biased_toward_down_days(self) -> None:
        # Regression: score_text_finbert_proxy returns exactly 0.0 (not near-zero
        # noise) whenever a headline has zero keyword hits either way -- the
        # common "no signal" case. The naive `(score > 0) == (return > 0)`
        # comparison silently agreed with every down day (False == False) and
        # disagreed with every up day (False == True), an asymmetric bug: a
        # score carrying no information must not be counted as "explaining"
        # any move, regardless of its sign.
        self.assertIsNone(move_explained_by_news(0.0, -0.02, alpha_threshold=0.005))
        self.assertIsNone(move_explained_by_news(0.0, 0.02, alpha_threshold=0.005))


class TestRollingAlphaCorr(unittest.TestCase):
    def test_returns_none_when_too_few_observations(self) -> None:
        dates = pd.bdate_range("2026-07-01", periods=5)
        sentiment = pd.Series([0.1, 0.2, -0.1, 0.0, 0.3], index=dates)
        returns = pd.Series([0.01, 0.02, -0.01, 0.0, 0.03], index=dates)
        self.assertIsNone(rolling_alpha_corr(sentiment, returns, window=63))

    def test_perfectly_aligned_series_gives_corr_near_one(self) -> None:
        dates = pd.bdate_range("2026-01-01", periods=40)
        returns = pd.Series(range(40), index=dates, dtype=float) * 0.001
        sentiment = returns * 2.0
        corr = rolling_alpha_corr(sentiment, returns, window=30)
        self.assertIsNotNone(corr)
        self.assertGreater(corr, 0.99)


class TestBuildMarketAlignedSentimentShadow(unittest.TestCase):
    def test_next_day_prediction_field_is_always_null(self) -> None:
        as_of = pd.Timestamp("2026-08-01")
        sentiment_panel = pd.DataFrame(
            {
                "date": [as_of],
                "ticker": ["0050"],
                "sentiment_score": [0.2],
                "news_intensity": [3],
            }
        )
        price_returns = {"0050": pd.Series([0.01], index=[as_of])}
        payload = build_market_aligned_sentiment_shadow(
            sentiment_panel=sentiment_panel,
            price_returns=price_returns,
            tickers=["0050"],
            as_of=as_of,
        )
        self.assertIsNone(payload["next_day_prediction"])
        self.assertIn("intentionally null", payload["next_day_prediction_note"])
        self.assertTrue(payload["research_only"])
        self.assertEqual(payload["production_effect"], "none")

    def test_ticker_with_no_news_that_day_has_null_sentiment_fields(self) -> None:
        as_of = pd.Timestamp("2026-08-01")
        sentiment_panel = pd.DataFrame(columns=["date", "ticker", "sentiment_score", "news_intensity"])
        price_returns = {"00679B": pd.Series([-0.002], index=[as_of])}
        payload = build_market_aligned_sentiment_shadow(
            sentiment_panel=sentiment_panel,
            price_returns=price_returns,
            tickers=["00679B"],
            as_of=as_of,
        )
        entry = payload["per_ticker"]["00679B.TWO"]
        self.assertIsNone(entry["same_day_sentiment_score"])
        self.assertEqual(entry["same_day_news_intensity"], 0)
        self.assertIsNone(entry["move_explained_by_news"])


if __name__ == "__main__":
    unittest.main()
