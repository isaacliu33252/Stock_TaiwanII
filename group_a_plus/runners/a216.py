"""A21.6 severity-scaled defense candidate built on the active A21.3 rules."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from backtest_group_a_plus_defensive_basket import (
    DEFENSIVE_BASKETS,
    _load_total_return_prices,
    _simulate_costed_curve,
)
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.runners.a213 import run_a213
from tw_output_standard import OutputStandardizer, write_standard_output


A216_ID = "a216_severity_scaled_cash40"
SEVERE_RISK_SCORE = 8
SEVERE_DRAWDOWN = -0.15
SEVERE_TAIL_SCORE = 2


def _severity_regime(execution_regime: pd.Series, features: pd.DataFrame) -> pd.Series:
    """Escalate once per defense episode and hold until recovery or formal exit."""
    severe_latched = False
    output = []
    for dt, regime in execution_regime.astype(str).items():
        if regime != "group_a_plus_defensive":
            severe_latched = False
            output.append(regime)
            continue
        row = features.loc[dt]
        severe_now = (
            int(row.get("total_risk_score", 0)) >= SEVERE_RISK_SCORE
            or float(row.get("drawdown", 0.0)) <= SEVERE_DRAWDOWN
            or int(row.get("tail_risk_score", 0)) >= SEVERE_TAIL_SCORE
        )
        severe_latched = severe_latched or severe_now
        output.append("group_a_plus_severe" if severe_latched else regime)
    return pd.Series(output, index=execution_regime.index, dtype=object)


def run_a216(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
) -> tuple[dict, pd.DataFrame]:
    base_report, frame = run_a213(
        start,
        end,
        initial_value,
        db,
        warmup_days,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
    regimes = _severity_regime(frame["execution_regime"], frame)
    weights = dict(base_report["weights"])
    weights["group_a_plus_severe"] = dict(DEFENSIVE_BASKETS["cash40"])
    prices, dividend_coverage = _load_total_return_prices(db, frame.index)
    curve, execution = _simulate_costed_curve(
        prices,
        regimes,
        weights,
        initial_value,
        commission_rate,
        slippage_rate,
        equity_etf_sell_tax,
    )
    out_frame = frame.copy()
    out_frame["a213_execution_regime"] = frame["execution_regime"]
    out_frame["execution_regime"] = regimes
    out_frame["portfolio_value"] = curve
    severe_dates = [str(dt.date()) for dt in regimes.index[regimes == "group_a_plus_severe"]]
    report = {
        **base_report,
        "experiment": "group_a_plus_a216_severity_scaled_defense",
        "strategy": A216_ID,
        "status": "research_candidate",
        "metrics": _metrics(curve, initial_value),
        "execution": execution,
        "weights": weights,
        "dividend_coverage": dividend_coverage,
        "severity_rule": {
            "total_risk_score_gte": SEVERE_RISK_SCORE,
            "drawdown_lte": SEVERE_DRAWDOWN,
            "tail_risk_score_gte": SEVERE_TAIL_SCORE,
            "logic": "OR; escalation is latched until recovery or formal exit",
            "severe_target": "cash40",
        },
        "severe_dates": severe_dates,
        "severe_day_count": len(severe_dates),
    }
    return report, out_frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-18")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default="results/group_a_plus_runner_a216.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a216_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a216")
    try:
        report, frame = run_a216(args.start, args.end, args.initial_value, Path(args.db))
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)


if __name__ == "__main__":
    main()
