"""A21.20 runner — A21.11 + NCF Late-Bull 3-Tier Rally-Aware Gate.

Problem solved
--------------
A21.18 applies a hard de-leverage (00631L: 20%→10%) whenever h20_prob < 0.33
and conf > 0.55 in late-bull. But NCF simultaneously predicts 20-day forward
drawdown risk AND gain probability. When both signals fire together:
  h20_prob < 0.33 (downside expected)
  prob_fwd_gain_gt5_h20 >= 0.50 (strong rally also expected)
it means the market is in a volatile correction-then-rally pattern. Hard
de-leveraging in this scenario costs opportunity (e.g., 2026-04-30 event,
gain_prob=0.430 → market rallied, hedge was net negative).

3-Tier response (avoids binary hard/no-hedge):
  Tier 1 (gain_prob < 0.30):  Hard hedge — pure downside, no rally signal.
                               00631L cut from ~10% → ~5% (intensity=1.0)
  Tier 2 (0.30 ≤ gp < 0.50): Soft hedge — mixed signal, reduce exposure lightly.
                               00631L cut by 25% intensity → ~9%
  Tier 3 (gain_prob ≥ 0.50):  Suppress — rally too likely to de-leverage.
                               Stay in golden1 (no NCF hedge applied)

Parameter defaults
------------------
  h20_max=0.33, conf_min=0.55, h5_reentry_min=0.55 — same as active A21.18
  gain_prob_soft_min=0.30, soft_hedge_intensity=0.25 — from tiered shadow sweep
  rally_suppress_min=0.50 — new: suppress hard/soft hedge when rally very likely

Relationship to A21.18
----------------------
A21.18 (active):       no gain_prob tiers — hard hedge whenever trigger fires
A21.20 (shadow):       adds rally_suppress and tiered soft hedge as defaults
                       When rally_suppress_min=None, behavior identical to A21.18
                       with gain_prob_soft_min=0.30 and soft_hedge_intensity=0.25

Sample size warning: 2 initial triggers in 357-day backtest window.
Do NOT promote to active until at least 5 trigger events with mixed tier outcomes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from group_a_plus.runners.a2118 import (
    NCF_LB_CONF_MIN,
    NCF_LB_MA_GAP_MIN,
    run_a2118,
)
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


A2120_ID = "a2120_a2111_ncf_late_bull_rally_aware"

# 3-tier thresholds (confirmed from opportunity-cost sweep 2026-06-29)
A2120_H20_MAX = 0.33             # match active A21.18 manifest threshold
A2120_SOFT_GATE_MIN = 0.30       # gain_prob >= this → soft hedge
A2120_RALLY_SUPPRESS_MIN = 0.50  # gain_prob >= this → suppress hedge entirely
A2120_SOFT_INTENSITY = 0.25      # soft hedge reduction intensity
A2120_H5_REENTRY = 0.55          # exit hold when H=5 prob_up recovers


def run_a2120(
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
    h20_max: float = A2120_H20_MAX,
    conf_min: float = NCF_LB_CONF_MIN,
    h5_reentry_min: float = A2120_H5_REENTRY,
    gain_prob_soft_min: float = A2120_SOFT_GATE_MIN,
    soft_hedge_intensity: float = A2120_SOFT_INTENSITY,
    rally_suppress_min: float = A2120_RALLY_SUPPRESS_MIN,
) -> tuple[dict, "pd.DataFrame"]:  # type: ignore[name-defined]
    """Run A21.20: A21.18 base with 3-tier rally-aware gate applied by default.

    Thin wrapper around run_a2118 with A21.20 defaults.
    Pass rally_suppress_min=None to fall back to plain tiered soft hedge.
    """
    import pandas as pd  # noqa: F401 (type annotation stub)

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
        gain_prob_soft_min=gain_prob_soft_min,
        soft_hedge_intensity=soft_hedge_intensity,
        rally_suppress_min=rally_suppress_min,
    )
    report["experiment"] = "group_a_plus_a2120_ncf_late_bull_rally_aware"
    report["strategy"] = A2120_ID
    report["status"] = "research_candidate"
    report["design_notes"]["a2120_tiers"] = (
        f"Tier1: gain_prob<{gain_prob_soft_min} → hard hedge (intensity=1.0). "
        f"Tier2: {gain_prob_soft_min}≤gain_prob<{rally_suppress_min} → "
        f"soft hedge (intensity={soft_hedge_intensity}). "
        f"Tier3: gain_prob≥{rally_suppress_min} → suppress (stay golden1)."
    )
    return report, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-06-26")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--warmup-days", type=int, default=180)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--ncf-00631l", default=None)
    parser.add_argument("--ncf-panel-631l",
                        default=str(PROJECT_ROOT / "results" / "ncf_00631l_v5_tabnet_panel.csv"),
                        help="val-prediction panel CSV for 00631L")
    parser.add_argument("--ma-gap-min", type=float, default=NCF_LB_MA_GAP_MIN)
    parser.add_argument("--h20-max", type=float, default=A2120_H20_MAX)
    parser.add_argument("--conf-min", type=float, default=NCF_LB_CONF_MIN)
    parser.add_argument("--h5-reentry-min", type=float, default=A2120_H5_REENTRY)
    parser.add_argument("--gain-prob-soft-min", type=float, default=A2120_SOFT_GATE_MIN)
    parser.add_argument("--soft-hedge-intensity", type=float, default=A2120_SOFT_INTENSITY)
    parser.add_argument("--rally-suppress-min", type=float, default=A2120_RALLY_SUPPRESS_MIN)
    parser.add_argument("--output", default="results/group_a_plus_runner_a2120.json")
    parser.add_argument("--frame-output", default="results/group_a_plus_runner_a2120_frame.csv")
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.runners.a2120")
    try:
        report, frame = run_a2120(
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
            gain_prob_soft_min=args.gain_prob_soft_min,
            soft_hedge_intensity=args.soft_hedge_intensity,
            rally_suppress_min=args.rally_suppress_min,
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
