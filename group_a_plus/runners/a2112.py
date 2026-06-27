"""Standardized runner for A21.12 candidate — MA80 Tight Entry + Bond Defensive + Low-Risk Exit.

Bridges A21.4 (MA60, Sharpe 2.600) and A21.11 (MA100, Sharpe 2.522) with three enhancements:

  1. ma_window = 80  — more responsive than MA100, less whipsaw-prone than MA60
  2. bond30_cash30   — defensive basket (0050 40% / 00679B 30% / cash 30%), same as A21.11
  3. low_risk_exit   — when total_risk_score ≤ 1 (risk has dissipated), exit defensive after
                       only 0.3% recovery above MA80 (vs standard 1.0%), reducing drag in
                       brief defensive periods where the market recovers quickly

Design rationale:
  - A21.4 (MA60 + bond30_cash30): highest Sharpe (2.600) but more false defensive entries
  - A21.11 (MA100 + bond30_cash30): most stable (MDD -13.92%) but slower regime response
  - A21.12 (MA80 + bond30_cash30 + low_risk_exit): targets Sharpe 2.55–2.58 by combining
    faster trend signal with early exit when risk environment normalises quickly

Switch rule: risk_ma80_dd11_total6_eg3_xg10_lrx3
  ma_window:                80
  entry_gap (enter_ma_gap): +0.003  — enter defensive when price within 0.3% of MA80
  exit_gap  (exit_ma_gap):  +0.010  — standard exit requires 1% above MA80
  low_risk_exit_ma_gap:     +0.003  — fast exit when total_risk_score ≤ 1
  dd_threshold:             -11%
  require_total_risk_score: 6       — strict gate, same as A21.11
  hold_days:                5
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


A2112_ID = "a2112_ma80_tight_entry_bond30c30_lrx"


def _build_switch_rule() -> SwitchRule:
    """A21.12: MA80 + tight entry (0.003) + bond30_cash30 + low-risk fast exit (0.003 when score ≤ 1)."""
    return SwitchRule(
        "risk_ma80_dd11_total6_eg3_xg10_lrx3",
        80,     # ma_window
        0.003,  # enter_ma_gap  — tight: enter defensive when price within 0.3% of MA80
        0.010,  # exit_ma_gap   — standard: require 1% above MA80 to leave defensive
        80,     # drawdown_window
        -0.11,  # enter_drawdown (dd_threshold)
        5,      # exit_momentum_days
        5,      # min_hold_days
        0, None,   # require_chip_score / exit_max_chip_score (not used)
        0, None,   # require_derivative_score / exit_max_derivative_score (not used)
        6, 6,      # require_total_risk_score=6, exit_max_total_risk_score=6
        low_risk_exit_ma_gap=0.003,    # fast exit: 0.3% gap suffices when risk has dissipated
        low_risk_exit_score_threshold=1,  # "low risk" = total_risk_score ≤ 1
    )


def run_a2112(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
) -> tuple[dict, pd.DataFrame]:
    """Run A21.12: MA80 tight-entry switch rule + bond30_cash30 basket + low-risk fast exit."""
    policy_signal, policy_signal_path = _load_policy_signal(_resolve(DEFAULT_DECISION_POINTER))
    golden_signal_path = _resolve(DEFAULT_GOLDEN_SIGNAL)
    golden_signal = _load(golden_signal_path)
    current_defensive = _normalize(_weights_from_group_a_plus(policy_signal))
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
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
        "experiment": "group_a_plus_a2112_ma80_tight_entry_bond30c30_lrx",
        "strategy": A2112_ID,
        "status": "research_candidate",
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
            "basket_name": "bond30_cash30",
            "ma_window": 80,
            "entry_gap": 0.003,
            "exit_gap": 0.010,
            "low_risk_exit_ma_gap": 0.003,
            "low_risk_exit_score_threshold": 1,
            "require_total_risk_score": 6,
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
        "design_notes": {
            "vs_a2111": "MA80 (vs 100) gives faster trend response; low_risk_exit reduces drag in brief defensive spells",
            "vs_a214": "Same bond30_cash30 basket; MA80 vs MA60 reduces whipsaw; tight entry (0.003) vs free entry",
            "bond_risk_note": "00679B sensitive to rate hikes (2022 episode); long-window MDD includes this risk",
        },
    }
    return report, out_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-25")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default="results/group_a_plus_runner_a2112.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2112_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2112")
    try:
        report, frame = run_a2112(
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
