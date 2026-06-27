"""Standardized runner for A21.8 candidate — Risk Override Entry.

A21.8 improvements over A21.7:
  - Inherits: entry_gap=0.003, ma_window=100, exit_gap=0.010 (all from A21.7)
  - NEW: Risk Override Entry
      If total_risk_score >= 9 AND drawdown <= -5%, enter defensive
      regardless of whether MA100 gap satisfies the normal entry threshold.
  Motivation: 2026-03-04/09 Trump tariff shock — total_risk=11/8, MA gap=+14/+10%,
  the system stayed in golden1 and lost -4.0% / -4.2% on those two days.
"""

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


A218_ID = "a218_risk_override_entry"


def _build_switch_rule() -> SwitchRule:
    """A21.8: A21.7 base + Risk Override Entry (risk>=9, dd<=-5%).

    Inherits all A21.7 parameters exactly:
      ma_window=100, enter_ma_gap=0.003, exit_ma_gap=0.010,
      enter_drawdown=-0.11, require_total_risk_score=6, exit_max_total_risk_score=6

    Adds override: if total_risk_score >= 9 AND drawdown <= -5%, enter defensive
    regardless of whether MA100 gap satisfies the normal entry threshold.
    """
    return SwitchRule(
        "risk_ma100_dd11_total6_eg3_xg10_override9_dd5",
        100,    # ma_window
        0.003,  # enter_ma_gap  (same as A21.7)
        0.010,  # exit_ma_gap   (same as A21.7)
        100,    # drawdown_window
        -0.11,  # enter_drawdown
        5, 5,   # exit_momentum_days, min_hold_days
        0, None, 0, None, 6, 6,  # require_chip=0, exit_max_chip=None, require_deriv=0, exit_max_deriv=None, require_total=6, exit_max_total=6
        None, None, None,         # enter/exit cost gap (unused)
        0, None,                  # require_tail_risk_score=0, exit_max_tail_risk_score=None
        override_risk_score=10,
        override_drawdown_threshold=-0.05,
    )


def _run_a218(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
    basket_name: str = "cash30",
    strategy_id: str = A218_ID,
    experiment: str = "group_a_plus_a218_risk_override",
    status: str = "candidate",
) -> tuple[dict, pd.DataFrame]:
    policy_signal, policy_signal_path = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))
    golden_signal_path = _resolve(DEFAULT_GOLDEN_SIGNAL)
    golden_signal = _load(golden_signal_path)
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS[basket_name])
    golden_weights = _normalize(_weights_from_group_a(golden_signal))

    load_start = _warmup_start(start, warmup_days)
    switch_rule = _build_switch_rule()
    full_prices = _load_prices(_resolve(db), list(TICKERS), load_start, end)
    full_chip = _load_chip_features(_resolve(db), full_prices.index, load_start, end)
    full_events, full_frame = _switch_returns(full_prices, full_chip, switch_rule)
    close_prices, frame, events = _trim_window(full_prices, full_frame, full_events, start, end)
    total_return_prices, dividend_coverage = _load_total_return_prices(_resolve(db), close_prices.index)

    execution_regime = _recovery_ramp_regime(frame["regime"], frame)
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
            "basket_name": basket_name,
            "ma_window": 100,
            "entry_gap": 0.003,
            "exit_gap": 0.010,
            "require_total_risk_score": 6,
            "exit_max_total_risk_score": 6,
            "override_risk_score": 10,
            "override_drawdown_threshold": -0.05,
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


def run_a218(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
) -> tuple[dict, pd.DataFrame]:
    return _run_a218(
        start=start, end=end, initial_value=initial_value, db=db,
        warmup_days=warmup_days, commission_rate=commission_rate,
        slippage_rate=slippage_rate, equity_etf_sell_tax=equity_etf_sell_tax,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2026-06-24")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default="results/group_a_plus_runner_a218.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a218_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a218")
    try:
        report, frame = run_a218(
            args.start, args.end, args.initial_value, Path(args.db),
            args.warmup_days, args.commission_rate,
            args.slippage_rate, args.equity_etf_sell_tax,
        )
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"A218 JSON:  {Path(args.output).resolve()}")
    print(f"A218 frame: {Path(args.frame_output).resolve()}")


if __name__ == "__main__":
    main()
