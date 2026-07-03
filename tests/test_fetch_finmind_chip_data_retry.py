#!/usr/bin/env python3
"""M8 (2026-07-02 Fable 5 audit) regression: FinMind fetch retry/backoff behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.fetch.fetch_finmind_chip_data import (
    _FETCH_FAILURES,
    _exit_if_fetch_failures,
    _get,
    _record_fetch_failure,
    fetch_stock_per,
)


def _mock_response(status_code: int, data: object = None, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"data": data if data is not None else []}
    resp.headers = headers or {}
    return resp


@patch("scripts.fetch.fetch_finmind_chip_data.time.sleep")
@patch("scripts.fetch.fetch_finmind_chip_data.requests.get")
def test_get_retries_on_429_then_succeeds(mock_get: MagicMock, mock_sleep: MagicMock) -> None:
    mock_get.side_effect = [
        _mock_response(429),
        _mock_response(200, [{"date": "2026-07-01"}]),
    ]

    rows = _get("TaiwanStockPER", "2330", "2026-06-01", "2026-07-01", "token")

    assert rows == [{"date": "2026-07-01"}]
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once()


@patch("scripts.fetch.fetch_finmind_chip_data.time.sleep")
@patch("scripts.fetch.fetch_finmind_chip_data.requests.get")
def test_get_respects_retry_after_header(mock_get: MagicMock, mock_sleep: MagicMock) -> None:
    mock_get.side_effect = [
        _mock_response(429, headers={"Retry-After": "7"}),
        _mock_response(200, [{"date": "2026-07-01"}]),
    ]

    _get("TaiwanStockPER", "2330", "2026-06-01", "2026-07-01", "token")

    mock_sleep.assert_called_once_with(7.0)


@patch("scripts.fetch.fetch_finmind_chip_data.time.sleep")
@patch("scripts.fetch.fetch_finmind_chip_data.requests.get")
def test_get_retries_on_5xx(mock_get: MagicMock, mock_sleep: MagicMock) -> None:
    mock_get.side_effect = [
        _mock_response(503),
        _mock_response(200, [{"date": "2026-07-01"}]),
    ]

    rows = _get("TaiwanStockPER", "2330", "2026-06-01", "2026-07-01", "token")

    assert rows == [{"date": "2026-07-01"}]
    assert mock_get.call_count == 2


@patch("scripts.fetch.fetch_finmind_chip_data.time.sleep")
@patch("scripts.fetch.fetch_finmind_chip_data.requests.get")
def test_get_does_not_retry_on_402_quota_error(mock_get: MagicMock, mock_sleep: MagicMock) -> None:
    """402 (FinMind quota/plan gate) is not transient -- must fail on the
    first attempt, not burn through retries before failing anyway."""
    mock_get.return_value = _mock_response(402, {"msg": "quota exceeded"})

    with pytest.raises(RuntimeError, match="HTTP 402"):
        _get("TaiwanStockPER", "2330", "2026-06-01", "2026-07-01", "token")

    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


@patch("scripts.fetch.fetch_finmind_chip_data.time.sleep")
@patch("scripts.fetch.fetch_finmind_chip_data.requests.get")
def test_get_raises_after_exhausting_retries(mock_get: MagicMock, mock_sleep: MagicMock) -> None:
    mock_get.return_value = _mock_response(429)

    with pytest.raises(RuntimeError):
        _get("TaiwanStockPER", "2330", "2026-06-01", "2026-07-01", "token", max_retries=3)

    assert mock_get.call_count == 3


@patch("scripts.fetch.fetch_finmind_chip_data.time.sleep")
@patch("scripts.fetch.fetch_finmind_chip_data.requests.get")
def test_get_retries_on_connection_error(mock_get: MagicMock, mock_sleep: MagicMock) -> None:
    mock_get.side_effect = [
        requests.exceptions.ConnectionError("boom"),
        _mock_response(200, [{"date": "2026-07-01"}]),
    ]

    rows = _get("TaiwanStockPER", "2330", "2026-06-01", "2026-07-01", "token")

    assert rows == [{"date": "2026-07-01"}]


@patch("scripts.fetch.fetch_finmind_chip_data.requests.get")
def test_get_succeeds_on_first_try_without_sleeping(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response(200, [{"date": "2026-07-01"}])

    rows = _get("TaiwanStockPER", "2330", "2026-06-01", "2026-07-01", "token")

    assert rows == [{"date": "2026-07-01"}]
    assert mock_get.call_count == 1


class TestFetchFailureVisibility:
    """M8-3 (2026-07-02 Fable 5 audit): a fetch_* function that swallows a
    RuntimeError per-item (skip + continue) must still make the failure
    visible to main()'s exit code, so run_ncf_daily_pipeline.py's
    subprocess.run(check=True) actually sees a partial-fetch failure instead
    of silently continuing with an exit code of 0."""

    def setup_method(self) -> None:
        _FETCH_FAILURES.clear()

    def teardown_method(self) -> None:
        _FETCH_FAILURES.clear()

    def test_exit_if_fetch_failures_is_noop_when_empty(self) -> None:
        _exit_if_fetch_failures()  # must not raise

    def test_exit_if_fetch_failures_raises_systemexit_when_recorded(self) -> None:
        _record_fetch_failure("per 2330: boom")

        with pytest.raises(SystemExit) as exc_info:
            _exit_if_fetch_failures()

        assert exc_info.value.code == 1

    @patch("scripts.fetch.fetch_finmind_chip_data.time.sleep")
    @patch("scripts.fetch.fetch_finmind_chip_data.requests.get")
    def test_fetch_stock_per_records_failure_on_exhausted_retries(
        self, mock_get: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_get.return_value = _mock_response(429)

        rows = fetch_stock_per(["2330"], "2026-06-01", "2026-07-01", "token")

        assert rows.empty
        assert len(_FETCH_FAILURES) == 1
        assert "2330" in _FETCH_FAILURES[0]

    @patch("scripts.fetch.fetch_finmind_chip_data.time.sleep")
    @patch("scripts.fetch.fetch_finmind_chip_data.requests.get")
    def test_fetch_stock_per_does_not_record_failure_on_success(
        self, mock_get: MagicMock, mock_sleep: MagicMock
    ) -> None:
        mock_get.return_value = _mock_response(200, [{"date": "2026-07-01", "PER": 15.0, "PBR": 2.0}])

        fetch_stock_per(["2330"], "2026-06-01", "2026-07-01", "token")

        assert _FETCH_FAILURES == []
