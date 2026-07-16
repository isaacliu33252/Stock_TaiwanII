"""A21.22 runner — A21.18 plus golden1 tail-risk trim.

This is a shadow candidate. It keeps A21.18's NCF late-bull de-leverage overlay
and adds a small, regime-local trim when golden1 is already under acute tail
stress. The trim moves part of 00631L into 0050; it does not force a full
defensive state.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    NCF_LB_CONF_MIN,
    NCF_LB_MA_GAP_MIN,
    run_a2118,
)
from tw_output_standard import OutputStandardizer, write_standard_output


A2122_ID = "a2122_golden1_tail_risk_trim_shadow"
A2122_H20_MAX = 0.33
A2122_H5_REENTRY = 0.55
A2122_TAIL_TRIM_FRACTION = 0.5
A2122_TAIL_RISK_SCORE_MIN = 2
A2122_DRAWDOWN_MAX = -0.08
A2122_RETURN_VAR_BREACH = True


def run_a2122(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    warmup_days: int = 180,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
    ncf_00631l_path: str | None = None,
    ncf_panel_631l_path: str | None = None,
    ma_gap_min: float = NCF_LB_MA_GAP_MIN,
    h20_max: float = A2122_H20_MAX,
    conf_min: float = NCF_LB_CONF_MIN,
    h5_reentry_min: float = A2122_H5_REENTRY,
    regime_execution_delay_days: int = 0,
    chip_data_fallback_max_stale_days: int | None = CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    tail_trim_fraction: float = A2122_TAIL_TRIM_FRACTION,
    tail_risk_score_min: int = A2122_TAIL_RISK_SCORE_MIN,
    drawdown_max: float = A2122_DRAWDOWN_MAX,
    return_var_breach: bool = A2122_RETURN_VAR_BREACH,
) -> tuple[dict, "pd.DataFrame"]:  # type: ignore[name-defined]
    import pandas as pd  # noqa: F401

    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db,
        warmup_days=warmup_days,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        ncf_00631l_path=ncf_00631l_path,
        ncf_panel_631l_path=ncf_panel_631l_path,
        ma_gap_min=ma_gap_min,
        h20_max=h20_max,
        conf_min=conf_min,
        h5_reentry_min=h5_reentry_min,
        regime_execution_delay_days=regime_execution_delay_days,
        chip_data_fallback_max_stale_days=chip_data_fallback_max_stale_days,
        golden_tail_trim_enabled=True,
        golden_tail_trim_fraction=tail_trim_fraction,
        golden_tail_trim_tail_risk_score_min=tail_risk_score_min,
        golden_tail_trim_drawdown_max=drawdown_max,
        golden_tail_trim_return_var_breach=return_var_breach,
    )
    report["experiment"] = "group_a_plus_a2122_golden1_tail_risk_trim_shadow"
    report["strategy"] = A2122_ID
    report["status"] = "research_candidate"
    report["design_notes"]["a2122_golden_tail_trim"] = (
        "A21.22 keeps A21.18's NCF overlay and trims golden1 leverage only when "
        f"tail_risk_score >= {tail_risk_score_min} and drawdown <= {drawdown_max} "
        f"or return_0050_1d breaches the rolling 5% historical VaR. The trim moves "
        f"{tail_trim_fraction:.0%} of 00631L weight into 0050."
    )
    return report, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-06-30")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--ncf-00631l", default=None)
    parser.add_argument("--ncf-panel-631l", default=str(PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"))
    parser.add_argument("--ma-gap-min", type=float, default=NCF_LB_MA_GAP_MIN)
    parser.add_argument("--h20-max", type=float, default=A2122_H20_MAX)
    parser.add_argument("--conf-min", type=float, default=NCF_LB_CONF_MIN)
    parser.add_argument("--h5-reentry-min", type=float, default=A2122_H5_REENTRY)
    parser.add_argument("--regime-execution-delay-days", type=int, default=0)
    parser.add_argument("--chip-data-fallback-max-stale-days", type=int, default=CHIP_DATA_FALLBACK_MAX_STALE_DAYS)
    parser.add_argument("--tail-trim-fraction", type=float, default=A2122_TAIL_TRIM_FRACTION)
    parser.add_argument("--tail-risk-score-min", type=int, default=A2122_TAIL_RISK_SCORE_MIN)
    parser.add_argument("--drawdown-max", type=float, default=A2122_DRAWDOWN_MAX)
    parser.add_argument("--return-var-breach", action=argparse.BooleanOptionalAction, default=A2122_RETURN_VAR_BREACH)
    parser.add_argument("--output", default="results/group_a_plus_runner_a2122.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2122_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2122")
    try:
        report, frame = run_a2122(
            args.start,
            args.end,
            args.initial_value,
            Path(args.db),
            args.warmup_days,
            args.commission_rate,
            args.slippage_rate,
            args.equity_etf_sell_tax,
            ncf_00631l_path=args.ncf_00631l,
            ncf_panel_631l_path=args.ncf_panel_631l,
            ma_gap_min=args.ma_gap_min,
            h20_max=args.h20_max,
            conf_min=args.conf_min,
            h5_reentry_min=args.h5_reentry_min,
            regime_execution_delay_days=args.regime_execution_delay_days,
            chip_data_fallback_max_stale_days=args.chip_data_fallback_max_stale_days,
            tail_trim_fraction=args.tail_trim_fraction,
            tail_risk_score_min=args.tail_risk_score_min,
            drawdown_max=args.drawdown_max,
            return_var_breach=args.return_var_breach,
        )
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"A2122 JSON:  {Path(args.output).resolve()}")
    print(f"A2122 frame: {Path(args.frame_output).resolve()}")


if __name__ == "__main__":
    main()
