"""A21.26 runner — A21.18 plus golden1 dynamic 00631L cap.

This is a shadow candidate. It keeps A21.18's regime logic and only caps the
00631L weight inside golden1 when volatility and tail-risk conditions are high.
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


A2126_ID = "a2126_golden1_dynamic_leverage_cap_shadow"
A2126_H20_MAX = 0.33
A2126_H5_REENTRY = 0.55
A2126_LEGACY_MAX_00631L_WEIGHT = 0.15
A2126_EFFECTIVE_MAX_00631L_WEIGHT = 0.10
A2126_MAX_00631L_WEIGHT = A2126_LEGACY_MAX_00631L_WEIGHT
A2126_TAIL_RISK_SCORE_MIN = 1
A2126_REALIZED_VOL_RATIO_MIN = 1.25
A2126_DRAWDOWN_MAX = -0.08


def run_a2126(
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
    h20_max: float = A2126_H20_MAX,
    conf_min: float = NCF_LB_CONF_MIN,
    h5_reentry_min: float = A2126_H5_REENTRY,
    chip_data_fallback_max_stale_days: int | None = CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    max_00631l_weight: float = A2126_MAX_00631L_WEIGHT,
    tail_risk_score_min: int = A2126_TAIL_RISK_SCORE_MIN,
    realized_vol_ratio_min: float = A2126_REALIZED_VOL_RATIO_MIN,
    drawdown_max: float | None = A2126_DRAWDOWN_MAX,
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
        golden_leverage_cap_enabled=True,
        golden_leverage_cap_max_00631l_weight=max_00631l_weight,
        golden_leverage_cap_tail_risk_score_min=tail_risk_score_min,
        golden_leverage_cap_realized_vol_ratio_min=realized_vol_ratio_min,
        golden_leverage_cap_drawdown_max=drawdown_max,
    )
    report["experiment"] = "group_a_plus_a2126_golden1_dynamic_leverage_cap_shadow"
    report["strategy"] = A2126_ID
    report["status"] = "research_candidate"
    report["design_notes"]["a2126_dynamic_leverage_cap"] = (
        "A21.26 keeps A21.18's regime logic and caps 00631L inside golden1 "
        f"at {max_00631l_weight:.0%} when tail_risk_score >= {tail_risk_score_min}, "
        f"realized_vol_ratio_20_60 >= {realized_vol_ratio_min}, and drawdown <= {drawdown_max}."
    )
    report["design_notes"]["a2126_default_review_20260710"] = (
        f"The historical shadow default remains {A2126_LEGACY_MAX_00631L_WEIGHT:.0%}. "
        f"An effective {A2126_EFFECTIVE_MAX_00631L_WEIGHT:.0%} cap is evaluated separately "
        "because it has not shown enough out-of-sample evidence to become the default."
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
    parser.add_argument("--h20-max", type=float, default=A2126_H20_MAX)
    parser.add_argument("--conf-min", type=float, default=NCF_LB_CONF_MIN)
    parser.add_argument("--h5-reentry-min", type=float, default=A2126_H5_REENTRY)
    parser.add_argument("--chip-data-fallback-max-stale-days", type=int, default=CHIP_DATA_FALLBACK_MAX_STALE_DAYS)
    parser.add_argument("--max-00631l-weight", type=float, default=A2126_MAX_00631L_WEIGHT)
    parser.add_argument("--tail-risk-score-min", type=int, default=A2126_TAIL_RISK_SCORE_MIN)
    parser.add_argument("--realized-vol-ratio-min", type=float, default=A2126_REALIZED_VOL_RATIO_MIN)
    parser.add_argument("--drawdown-max", type=float, default=A2126_DRAWDOWN_MAX)
    parser.add_argument("--output", default="results/group_a_plus_runner_a2126.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2126_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2126")
    try:
        report, frame = run_a2126(
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
            max_00631l_weight=args.max_00631l_weight,
            tail_risk_score_min=args.tail_risk_score_min,
            realized_vol_ratio_min=args.realized_vol_ratio_min,
            drawdown_max=args.drawdown_max,
        )
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"A2126 JSON:  {Path(args.output).resolve()}")
    print(f"A2126 frame: {Path(args.frame_output).resolve()}")


if __name__ == "__main__":
    main()
