"""A21.23 runner — A21.18 plus prior-day shock follow-through trim.

This is a shadow candidate. It keeps A21.18's NCF late-bull de-leverage overlay
and trims golden1 leverage for a short hold after the previous trading day had
an acute, observable selloff. Unlike A21.22, the trigger uses prior close data.
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


A2123_ID = "a2123_golden1_follow_through_trim_shadow"
A2123_H20_MAX = 0.33
A2123_H5_REENTRY = 0.55
A2123_TRIM_FRACTION = 0.5
A2123_PREVIOUS_RETURN_MAX = -0.03
A2123_PREVIOUS_RETURN_FLOOR = -0.08
A2123_PREVIOUS_TAIL_RISK_SCORE_MIN = 2
A2123_PREVIOUS_DRAWDOWN_MAX = -0.08
A2123_HOLD_DAYS = 1


def run_a2123(
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
    h20_max: float = A2123_H20_MAX,
    conf_min: float = NCF_LB_CONF_MIN,
    h5_reentry_min: float = A2123_H5_REENTRY,
    chip_data_fallback_max_stale_days: int | None = CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    trim_fraction: float = A2123_TRIM_FRACTION,
    previous_return_max: float = A2123_PREVIOUS_RETURN_MAX,
    previous_return_floor: float | None = A2123_PREVIOUS_RETURN_FLOOR,
    previous_tail_risk_score_min: int = A2123_PREVIOUS_TAIL_RISK_SCORE_MIN,
    previous_drawdown_max: float = A2123_PREVIOUS_DRAWDOWN_MAX,
    hold_days: int = A2123_HOLD_DAYS,
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
        chip_data_fallback_max_stale_days=chip_data_fallback_max_stale_days,
        golden_follow_through_trim_enabled=True,
        golden_follow_through_trim_fraction=trim_fraction,
        golden_follow_through_previous_return_max=previous_return_max,
        golden_follow_through_previous_return_floor=previous_return_floor,
        golden_follow_through_previous_tail_risk_score_min=previous_tail_risk_score_min,
        golden_follow_through_previous_drawdown_max=previous_drawdown_max,
        golden_follow_through_hold_days=hold_days,
    )
    report["experiment"] = "group_a_plus_a2123_golden1_follow_through_trim_shadow"
    report["strategy"] = A2123_ID
    report["status"] = "research_candidate"
    report["design_notes"]["a2123_follow_through_trim"] = (
        "A21.23 keeps A21.18's NCF overlay and trims golden1 leverage for "
        f"{hold_days} trading day(s) after the previous day has return_0050_1d <= "
        f"{previous_return_max} or breaches rolling VaR, but not below "
        f"{previous_return_floor}, with tail_risk_score >= "
        f"{previous_tail_risk_score_min} and drawdown <= {previous_drawdown_max}. "
        f"The trim moves {trim_fraction:.0%} of 00631L weight into 0050."
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
    parser.add_argument("--h20-max", type=float, default=A2123_H20_MAX)
    parser.add_argument("--conf-min", type=float, default=NCF_LB_CONF_MIN)
    parser.add_argument("--h5-reentry-min", type=float, default=A2123_H5_REENTRY)
    parser.add_argument("--chip-data-fallback-max-stale-days", type=int, default=CHIP_DATA_FALLBACK_MAX_STALE_DAYS)
    parser.add_argument("--trim-fraction", type=float, default=A2123_TRIM_FRACTION)
    parser.add_argument("--previous-return-max", type=float, default=A2123_PREVIOUS_RETURN_MAX)
    parser.add_argument("--previous-return-floor", type=float, default=A2123_PREVIOUS_RETURN_FLOOR)
    parser.add_argument("--previous-tail-risk-score-min", type=int, default=A2123_PREVIOUS_TAIL_RISK_SCORE_MIN)
    parser.add_argument("--previous-drawdown-max", type=float, default=A2123_PREVIOUS_DRAWDOWN_MAX)
    parser.add_argument("--hold-days", type=int, default=A2123_HOLD_DAYS)
    parser.add_argument("--output", default="results/group_a_plus_runner_a2123.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2123_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2123")
    try:
        report, frame = run_a2123(
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
            chip_data_fallback_max_stale_days=args.chip_data_fallback_max_stale_days,
            trim_fraction=args.trim_fraction,
            previous_return_max=args.previous_return_max,
            previous_return_floor=args.previous_return_floor,
            previous_tail_risk_score_min=args.previous_tail_risk_score_min,
            previous_drawdown_max=args.previous_drawdown_max,
            hold_days=args.hold_days,
        )
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"A2123 JSON:  {Path(args.output).resolve()}")
    print(f"A2123 frame: {Path(args.frame_output).resolve()}")


if __name__ == "__main__":
    main()
