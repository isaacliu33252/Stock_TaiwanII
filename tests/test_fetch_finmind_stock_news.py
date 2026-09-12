from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import requests


def _load_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "fetch" / "fetch_finmind_stock_news.py"
    spec = importlib.util.spec_from_file_location("_test_fetch_finmind_stock_news", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any], timeout: int) -> _FakeResponse:
        self.calls.append(params)
        return self._responses.pop(0)


def test_finmind_stock_id_strips_market_suffix() -> None:
    assert mod._finmind_stock_id("0050.TW") == "0050"
    assert mod._finmind_stock_id("00679B.TWO") == "00679B"


def test_fetch_day_maps_finmind_rows_to_ltn_shaped_schema() -> None:
    session = _FakeSession(
        [
            _FakeResponse(
                200,
                {
                    "status": 200,
                    "data": [
                        {
                            "date": "2026-06-29 01:15:06",
                            "stock_id": "0050",
                            "link": "https://example.com/a",
                            "source": "自由時報",
                            "title": "台股開盤上漲",
                        }
                    ],
                },
            )
        ]
    )
    import datetime as _dt

    rows = mod.fetch_day("0050.TW", _dt.date(2026, 6, 29), token="", session=session)

    assert rows == [
        {
            "date": "2026-06-29",
            "source": "自由時報",
            "title": "台股開盤上漲",
            "url": "https://example.com/a",
            "category": "finmind_stock_news",
            "snippet": "",
            "match_scope": "0050.TW",
            "provider": "finmind",
            "finmind_stock_id": "0050",
        }
    ]


class _TimeoutThenOkSession:
    """First N calls raise a transient network error, then succeed -- models
    the ReadTimeout observed against the real API on long backfills."""

    def __init__(self, failures_before_success: int, response: _FakeResponse) -> None:
        self._failures_left = failures_before_success
        self._response = response
        self.call_count = 0

    def get(self, url: str, params: dict[str, Any], timeout: int) -> _FakeResponse:
        self.call_count += 1
        if self._failures_left > 0:
            self._failures_left -= 1
            raise requests.exceptions.ReadTimeout("simulated timeout")
        return self._response


def test_fetch_day_retries_transient_network_errors(monkeypatch) -> None:
    import datetime as _dt

    monkeypatch.setattr(mod.time, "sleep", lambda _seconds: None)
    session = _TimeoutThenOkSession(
        failures_before_success=2,
        response=_FakeResponse(200, {"status": 200, "data": []}),
    )

    rows = mod.fetch_day("0050.TW", _dt.date(2026, 6, 29), token="", session=session, max_retries=3)

    assert rows == []
    assert session.call_count == 3  # two failures + one success, within max_retries


def test_fetch_day_gives_up_after_max_retries(monkeypatch) -> None:
    import datetime as _dt

    monkeypatch.setattr(mod.time, "sleep", lambda _seconds: None)
    session = _TimeoutThenOkSession(
        failures_before_success=10,  # never succeeds within the retry budget
        response=_FakeResponse(200, {"status": 200, "data": []}),
    )

    with pytest.raises(requests.exceptions.ReadTimeout):
        mod.fetch_day("0050.TW", _dt.date(2026, 6, 29), token="", session=session, max_retries=3)

    assert session.call_count == 3


def test_fetch_range_stops_gracefully_on_quota_error_and_keeps_prior_rows(monkeypatch) -> None:
    import datetime as _dt

    calls = {"n": 0}

    def fake_fetch_day(ticker, day, *, token, session):
        calls["n"] += 1
        if calls["n"] == 1:
            return [{"date": "2026-06-29", "source": "s", "title": "t1", "url": "https://example.com/a",
                      "category": "finmind_stock_news", "snippet": "", "match_scope": ticker,
                      "provider": "finmind", "finmind_stock_id": "0050"}]
        response = _FakeResponse(402)
        raise requests.exceptions.HTTPError(response=response)

    monkeypatch.setattr(mod, "fetch_day", fake_fetch_day)

    rows, stop_reason = mod.fetch_range(
        ["0050.TW"], start=_dt.date(2026, 6, 29), end=_dt.date(2026, 6, 30), token="", request_delay=0.0
    )

    assert len(rows) == 1
    assert stop_reason is not None
    assert "quota_exceeded" in stop_reason
