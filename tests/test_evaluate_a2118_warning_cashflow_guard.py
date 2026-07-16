import pandas as pd

from scripts.evaluate.evaluate_a2118_warning_cashflow_guard import (
    _contribution_dates,
    _simulate_cashflow_guard,
    _warning_series,
)


def test_contribution_dates_monthly_uses_first_trading_day() -> None:
    index = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-02-02", "2026-02-03"])

    dates = _contribution_dates(pd.DatetimeIndex(index), "monthly")

    assert dates == {pd.Timestamp("2026-01-05"), pd.Timestamp("2026-02-02")}


def test_warning_series_requires_golden1_and_thresholds() -> None:
    frame = pd.DataFrame(
        {
            "base_regime": ["golden1", "golden1", "risk_off"],
        },
        index=pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
    )
    panel = pd.DataFrame(
        {
            "prob_up_h20": [0.21, 0.23, 0.10],
            "prob_fwd_mdd_gt5_h20": [0.86, 0.90, 0.99],
        },
        index=frame.index,
    )

    warning = _warning_series(frame, panel, h20_max=0.22, mdd_min=0.85)

    assert warning.tolist() == [True, False, False]


def test_cashflow_guard_blocks_new_0050_00631l_adds_but_keeps_other_buy() -> None:
    index = pd.to_datetime(["2026-01-05", "2026-01-06"])
    prices = pd.DataFrame(
        {
            "0050.TW": [100.0, 100.0],
            "00631L.TW": [50.0, 50.0],
            "00632R.TW": [10.0, 10.0],
            "00679B.TWO": [25.0, 25.0],
        },
        index=index,
    )
    target_weights = pd.DataFrame(
        {
            "0050.TW": [0.4, 0.4],
            "00631L.TW": [0.2, 0.2],
            "00632R.TW": [0.0, 0.0],
            "00679B.TWO": [0.2, 0.2],
            "cash": [0.2, 0.2],
        },
        index=index,
    )
    warning = pd.Series([False, True], index=index)

    baseline_curve, baseline_exec = _simulate_cashflow_guard(
        prices,
        target_weights,
        warning,
        initial_value=1_000.0,
        contribution_amount=100.0,
        contribution_frequency="daily",
        guarded=False,
        commission_rate=0.0,
        slippage_rate=0.0,
        equity_etf_sell_tax=0.0,
    )
    guarded_curve, guarded_exec = _simulate_cashflow_guard(
        prices,
        target_weights,
        warning,
        initial_value=1_000.0,
        contribution_amount=100.0,
        contribution_frequency="daily",
        guarded=True,
        commission_rate=0.0,
        slippage_rate=0.0,
        equity_etf_sell_tax=0.0,
    )

    assert baseline_curve.iloc[-1] == guarded_curve.iloc[-1]
    assert baseline_exec["blocked_days"] == 0
    assert guarded_exec["blocked_days"] == 1
    assert guarded_exec["blocked_buy_value_estimate"] > 0.0
    assert guarded_exec["turnover_value"] < baseline_exec["turnover_value"]
