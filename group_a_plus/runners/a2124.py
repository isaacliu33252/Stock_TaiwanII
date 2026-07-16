"""A21.24 runner — A21.23 plus rebound recapture.

This is a shadow candidate. It combines a small prior-day shock trim with a
brief 00631L recapture after a strong rebound confirms stabilization.
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


A2124_ID = "a2124_follow_through_trim_rebound_recapture_shadow"
A2124_H20_MAX = 0.33
A2124_H5_REENTRY = 0.55
A2124_TRIM_FRACTION = 0.05
A2124_RECAPTURE_BOOST_FRACTION = 0.10


def run_a2124(
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
    h20_max: float = A2124_H20_MAX,
    conf_min: float = NCF_LB_CONF_MIN,
    h5_reentry_min: float = A2124_H5_REENTRY,
    chip_data_fallback_max_stale_days: int | None = CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    trim_fraction: float = A2124_TRIM_FRACTION,
    recapture_boost_fraction: float = A2124_RECAPTURE_BOOST_FRACTION,
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
        golden_follow_through_previous_return_max=-0.03,
        golden_follow_through_previous_return_floor=-0.08,
        golden_follow_through_previous_tail_risk_score_min=2,
        golden_follow_through_previous_drawdown_max=-0.08,
        golden_follow_through_hold_days=1,
        golden_rebound_recapture_enabled=True,
        golden_rebound_recapture_boost_fraction=recapture_boost_fraction,
        golden_rebound_recapture_previous_return_min=0.03,
        golden_rebound_recapture_previous_drawdown_max=-0.08,
        golden_rebound_recapture_lookback_days=3,
        golden_rebound_recapture_hold_days=1,
    )
    report["experiment"] = "group_a_plus_a2124_follow_through_trim_rebound_recapture_shadow"
    report["strategy"] = A2124_ID
    report["status"] = "research_candidate"
    report["design_notes"]["a2124_rebound_recapture"] = (
        "A21.24 keeps A21.18's NCF overlay, applies a small prior-day shock trim, "
        "then briefly boosts 00631L after a strong rebound appears within a recent shock window."
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
    parser.add_argument("--h20-max", type=float, default=A2124_H20_MAX)
    parser.add_argument("--conf-min", type=float, default=NCF_LB_CONF_MIN)
    parser.add_argument("--h5-reentry-min", type=float, default=A2124_H5_REENTRY)
    parser.add_argument("--chip-data-fallback-max-stale-days", type=int, default=CHIP_DATA_FALLBACK_MAX_STALE_DAYS)
    parser.add_argument("--trim-fraction", type=float, default=A2124_TRIM_FRACTION)
    parser.add_argument("--recapture-boost-fraction", type=float, default=A2124_RECAPTURE_BOOST_FRACTION)
    parser.add_argument("--output", default="results/group_a_plus_runner_a2124.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2124_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2124")
    try:
        report, frame = run_a2124(
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
            recapture_boost_fraction=args.recapture_boost_fraction,
        )
        Path(args.frame_output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.frame_output, encoding="utf-8-sig")
        payload = std.success(report, frame_output=args.frame_output)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"A2124 JSON:  {Path(args.output).resolve()}")
    print(f"A2124 frame: {Path(args.frame_output).resolve()}")


if __name__ == "__main__":
    main()
