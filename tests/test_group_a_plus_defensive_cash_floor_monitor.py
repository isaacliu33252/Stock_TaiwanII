from __future__ import annotations

import pandas as pd

from group_a_plus.integrations.defensive_cash_floor_monitor import build_defensive_cash_floor_monitor


def _prices(dates: list[str], closes: dict[str, list[float]]) -> pd.DataFrame:
    rows = []
    for ticker, values in closes.items():
        for dt, close in zip(dates, values):
            rows.append({"dt": dt, "ticker": ticker, "close": close})
    return pd.DataFrame(rows)


def _trigger(date: str, raw_cash: float = 0.30, candidate_cash: float = 0.55) -> dict:
    raw_0050 = 1.0 - raw_cash
    candidate_0050 = 1.0 - candidate_cash
    return {
        "date": date,
        "triggered": True,
        "changed": True,
        "can_apply_to_formal_target": True,
        "formal_reference": {"target_weights": {"0050.TW": raw_0050, "cash": raw_cash}},
        "candidate": {"target_weights": {"0050.TW": candidate_0050, "cash": candidate_cash}},
    }


def test_monitor_reports_no_trigger_without_live_action() -> None:
    report = build_defensive_cash_floor_monitor(
        candidate_log_rows=[],
        price_frame=_prices(["2026-01-01"], {"0050.TW": [100.0]}),
        as_of="2026-08-07",
    )

    assert report["summary"]["no_trigger_yet"] is True
    assert report["input_counts"]["evaluated_trigger_rows"] == 0
    assert report["decision"]["target_weight_change_allowed"] is False


def test_monitor_evaluates_next_day_candidate_delta() -> None:
    report = build_defensive_cash_floor_monitor(
        candidate_log_rows=[_trigger("2026-01-01")],
        price_frame=_prices(["2026-01-01", "2026-01-02"], {"0050.TW": [100.0, 90.0]}),
        as_of="2026-01-02",
    )

    event = report["evaluated_events"][0]
    assert round(event["raw_return"], 4) == -0.07
    assert round(event["candidate_return"], 4) == -0.045
    assert round(event["delta"], 4) == 0.025
    assert report["rollback"]["disable_candidate"] is False


def test_monitor_flags_rollback_after_first_10_underperform() -> None:
    dates = [f"2026-01-{day:02d}" for day in range(1, 22)]
    # A steady +1% 0050 path makes the higher-cash candidate lag raw exposure.
    closes = [100.0]
    for _ in range(20):
        closes.append(closes[-1] * 1.01)
    trigger_rows = [_trigger(dates[idx]) for idx in range(0, 20, 2)]

    report = build_defensive_cash_floor_monitor(
        candidate_log_rows=trigger_rows,
        price_frame=_prices(dates, {"0050.TW": closes}),
        as_of="2026-01-21",
    )

    assert report["first_trigger_window"]["complete"] is True
    assert report["first_trigger_window"]["cumulative_delta"] < -0.005
    assert report["rollback"]["disable_candidate"] is True
    assert "first_10_trigger_days_variant_underperforms_raw_by_more_than_0_50pct_cumulative" in report["rollback"]["reasons"]
