"""Standardized runner for the promotion-ready A21.3 recovery-ramp candidate."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from backtest_group_a_plus_defensive_basket import (
    DEFENSIVE_BASKETS,
    _load_total_return_prices,
    _recovery_ramp_regime,
    _simulate_costed_curve,
)
from backtest_group_a_plus_policy_signal import (
    DEFAULT_DECISION_POINTER,
    DEFAULT_GOLDEN_SIGNAL,
    TICKERS,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import (
    DB_PATH,
    SwitchRule,
    _load_chip_features,
    _load_prices,
    _metrics,
    _switch_returns,
)
from backtest_group_a_plus_warmup_consistency import _trim_window, _warmup_start
from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


A213_ID = "a213_cash30_recovery_ramp"


def _build_switch_rule(ma_window: int = 60) -> SwitchRule:
    """Build A207-style rule with configurable MA window."""
    return SwitchRule(
        f"risk_ma{ma_window}_dd11_total6_hold5_eg0175_xg020",
        ma_window,
        -0.0175,
        0.02,
        ma_window,
        -0.11,
        5,
        5,
        0,
        None,
        0,
        None,
        6,
        6,
    )


def _run_recovery_strategy(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
    trend_vol_threshold: float | None = None,
    trend_ma_gap_persist_days: int | None = None,
    basket_name: str = "cash30",
    vol_enter_threshold: float | None = None,
    ma_window: int = 75,
    strategy_id: str = A213_ID,
    experiment: str = "group_a_plus_a213_standard_runner",
    status: str = "active",
) -> tuple[dict, pd.DataFrame]:
    policy_signal, policy_signal_path = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))
    golden_signal_path = _resolve(DEFAULT_GOLDEN_SIGNAL)
    golden_signal = _load(golden_signal_path)
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS[basket_name])
    golden_weights = _normalize(_weights_from_group_a(golden_signal))

    load_start = _warmup_start(start, warmup_days)
    switch_rule = _build_switch_rule(ma_window)
    full_prices = _load_prices(_resolve(db), list(TICKERS), load_start, end)
    full_chip = _load_chip_features(_resolve(db), full_prices.index, load_start, end)
    full_events, full_frame = _switch_returns(full_prices, full_chip, switch_rule)
    close_prices, frame, events = _trim_window(full_prices, full_frame, full_events, start, end)
    total_return_prices, dividend_coverage = _load_total_return_prices(_resolve(db), close_prices.index)

    # Vol-based early entry into defensive
    if vol_enter_threshold is not None:
        vol_col = "realized_vol_0050_20d"
        if vol_col in frame.columns:
            frame["vol_override"] = frame[vol_col] > vol_enter_threshold
        else:
            frame["vol_override"] = False
    else:
        frame["vol_override"] = False

    execution_regime = _recovery_ramp_regime(
        frame["regime"],
        frame,
        trend_vol_threshold,
        trend_ma_gap_persist_days,
        vol_enter_threshold,
    )
    weights_by_regime = {
        "golden1": golden_weights,
        "group_a_plus_defensive": basket,
        "group_a_plus_recovery": current_defensive,
    }
    curve, execution = _simulate_costed_curve(
        total_return_prices,
        execution_regime,
        weights_by_regime,
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
    recovery_dates = [
        str(dt.date())
        for dt in execution_regime.index
        if execution_regime.loc[dt] == "group_a_plus_recovery"
        and (dt == execution_regime.index[0] or execution_regime.shift(1).loc[dt] != "group_a_plus_recovery")
    ]
    out_frame = frame.copy()
    out_frame = out_frame.rename(columns={"regime": "base_regime"})
    out_frame["execution_regime"] = execution_regime
    out_frame["portfolio_value"] = curve
    report = {
        "experiment": experiment,
        "strategy": strategy_id,
        "status": status,
        "window": {
            "start": str(close_prices.index[0].date()),
            "end": str(close_prices.index[-1].date()),
            "rows": int(len(close_prices)),
        },
        "metrics": _metrics(curve, initial_value),
        "execution": execution,
        "a207_events": events,
        "recovery_ramp_dates": recovery_dates,
        "rules": {
            "base": switch_rule.name,
            "warmup_days": warmup_days,
            "recovery_trigger": "base defensive and ma_gap >= 0 and exit_momentum > 0",
            "recovery_is_one_shot": True,
            "trend_vol_threshold": trend_vol_threshold,
            "trend_ma_gap_persist_days": trend_ma_gap_persist_days,
            "basket_name": basket_name,
            "vol_enter_threshold": vol_enter_threshold,
            "ma_window": ma_window,
        },
        "cost_assumptions": {
            "commission_rate": commission_rate,
            "slippage_rate": slippage_rate,
            "equity_etf_sell_tax": equity_etf_sell_tax,
            "bond_etf_sell_tax": 0.0,
        },
        "dividend_coverage": dividend_coverage,
        "weights": weights_by_regime,
        "inputs": {
            "policy_signal": str(policy_signal_path.relative_to(PROJECT_ROOT)),
            "golden_signal": str(golden_signal_path.relative_to(PROJECT_ROOT)),
        },
    }
    return report, out_frame


def run_a213(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
) -> tuple[dict, pd.DataFrame]:
    """Run the immutable active A21.3 specification."""
    return _run_recovery_strategy(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db,
        warmup_days=warmup_days,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        basket_name="cash30",
        ma_window=75,
        strategy_id=A213_ID,
        experiment="group_a_plus_a213_standard_runner",
        status="active",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default="results/group_a_plus_runner_a213.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a213_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a213")
    try:
        report, frame = run_a213(
            args.start,
            args.end,
            args.initial_value,
            Path(args.db),
            args.warmup_days,
            args.commission_rate,
            args.slippage_rate,
            args.equity_etf_sell_tax,
        )
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Runner JSON: {Path(args.output).resolve()}")
    print(f"Runner frame: {Path(args.frame_output).resolve()}")


if __name__ == "__main__":
    main()
