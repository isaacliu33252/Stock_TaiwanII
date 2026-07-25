#!/usr/bin/env python3
"""Backtest the live-only NCF overlay layers that a2118.py never simulates.

Research-only. Does not update the active strategy, latest pointer, live
signal, or execution plan.

CANONICAL TOOLING (2026-07-24): this script is the standing, required
citation companion whenever a2118's headline Sharpe/annual-return numbers
are used to justify a promotion, revert, or "keep as-is" decision -- see
GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md item 5 (added from
the arXiv:2603.21330 FinRL-X architecture-paper review). It exists because
run_a2118()'s own backtest was never refactored to call the same live NCF
overlay daily_signal.py's live path calls -- a full refactor of
run_a2118() was explicitly scoped out as a separate, larger task (too many
existing callers/tests to safely restructure its simulation engine in one
sitting); this script is the interim, lower-risk fix: it reuses the real
production overlay functions (not a reimplementation) against run_a2118()'s
own price/regime path, so its output can be reported alongside
run_a2118()'s plain numbers without touching run_a2118() itself.

Context (2026-07-23 Fable audit, direction 1): daily_signal.py applies three
weight-adjustment layers on top of a2118's regime/hedge logic that only run
in the live pipeline, never in group_a_plus.runners.a2118.run_a2118's
backtest:

  1. NCF continuous downside overlay (ncf.py::ncf_overlay_summary /
     adjust_golden1_weights) -- scales 00631L down continuously with the
     gated downside signal on every golden1 day, independent of a2118's own
     late-bull-hedge trigger.
  2. TSMC weakness trim (daily_signal.py::_apply_tsmc_weakness_trim) -- an
     extra 25% 00631L cut when ncf_2330 + the 0050-ex-TSMC price proxy both
     confirm TSMC weakness. CORRECTION (2026-07-23, found while building this
     script): despite being fully implemented, unit-tested, and even having a
     dead downstream alert hook waiting on its output flag,
     _apply_tsmc_weakness_trim is never actually called from
     build_daily_signal -- grep confirms zero call sites in daily_signal.py
     outside its own def. It is NOT live; it is very likely the "weight trim"
     integration attempt already rejected in the 2026-07-05 ncf_2330 five-way
     rejection (see scripts/misc/ncf_2330_total_risk_score_overlay_sweep.py's
     docstring, which calls it "already-rejected"). Included here ONLY as an
     opt-in side variant (--include-tsmc-trim) for completeness; the default
     run excludes it since it does not affect any real decision today.
  3. Bearish high-risk trim (daily_signal.py::_apply_bearish_high_risk_trim)
     -- needs live signal_alignment, which a2118.py's own
     backtest_live_discrepancy field already documents as "not
     reconstructable historically". NOT attempted here; that conclusion is
     inherited from a2118.py, not re-derived.

This script reconstructs (1) and (2) historically from the NCF panel CSVs
(results/ncf_00631l_panel_*.csv, ncf_00632r_panel_*.csv, ncf_2330_panel_*.csv)
by calling the *actual* production functions (ncf_overlay_summary,
_apply_tsmc_weakness_trim, _tsmc_0050_health_snapshot) with panel-row-derived
signal dicts, not a reimplementation. Coverage is limited to whatever date
range all three panels share (typically 2025-01 onward) -- there is no NCF
model before that, so this cannot speak to crash windows like 2020 or 2008.

`direction_conflict` is not a panel column (it is a live-only
classification-vs-return-head diagnostic); every historical day is treated
as direction_conflict=False, a mild optimistic bias versus live.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices
from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.integrations.ncf import ncf_overlay_summary
from group_a_plus.operations.daily_signal import _apply_tsmc_weakness_trim, _tsmc_0050_health_snapshot
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import (
    _simulate_daily_target_weights,
    _targets_from_report,
)

PANEL_00631L = "results/ncf_00631l_panel_latest_20260716.csv"
PANEL_00632R = "results/ncf_00632r_panel_latest_20260722.csv"
PANEL_2330 = "results/ncf_2330_panel_latest_20260722.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2118_live_overlay_backtest_gap_latest.json"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _load_panel(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(_resolve(path))
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def _row_to_ncf_signal(date: pd.Timestamp, row: pd.Series) -> dict[str, Any]:
    def _f(col: str) -> float | None:
        val = row.get(col)
        return float(val) if pd.notna(val) else None

    return {
        "date": str(date.date()),
        "direction": row.get("direction"),
        "calibrated_prob_up": float(row["ensemble_prob_up"]),
        "confidence": float(row["confidence"]),
        "votes_up": None,
        "tail_reward_risk_score": _f("tail_reward_risk_score_h20"),
        "prob_fwd_mdd_gt5_h20": _f("prob_fwd_mdd_gt5_h20"),
        "prob_fwd_mdd_gt8_h20": _f("prob_fwd_mdd_gt8_h20"),
        "prob_fwd_gain_gt5_h20": _f("prob_fwd_gain_gt5_h20"),
        "direction_conflict": False,  # not a panel column; see module docstring
        "horizon_prob_up": {
            "1": _f("prob_up_h1"),
            "5": _f("prob_up_h5"),
            "20": _f("prob_up_h20"),
        },
    }


def build_overlay_weights(
    frame: pd.DataFrame,
    baseline_targets: pd.DataFrame,
    base_golden1_weights: dict[str, float],
    panel_631l: pd.DataFrame,
    panel_632r: pd.DataFrame,
    panel_2330: pd.DataFrame,
    db_path: Path,
    *,
    include_tsmc_trim: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    overlay_targets = baseline_targets.copy()
    daily_log: list[dict[str, Any]] = []
    common_days = sorted(set(panel_631l.index) & set(panel_632r.index) & set(frame.index))
    for day in common_days:
        if str(frame.loc[day, "execution_regime"]) != "golden1":
            continue  # a2118's own hedge/soft-hedge already relabels these away from golden1
        sig_631l = _row_to_ncf_signal(day, panel_631l.loc[day])
        sig_632r = _row_to_ncf_signal(day, panel_632r.loc[day])
        ma_gap = float(frame.loc[day, "ma_gap"]) if "ma_gap" in frame.columns else 0.0
        summary = ncf_overlay_summary(sig_631l, sig_632r, base_golden1_weights, "golden1", ma_gap=ma_gap)
        weights = dict(summary["adjusted_golden1_weights"])
        tsmc_applied = False
        if include_tsmc_trim and day in panel_2330.index:
            sig_2330 = _row_to_ncf_signal(day, panel_2330.loc[day])
            health = _tsmc_0050_health_snapshot(db_path, day, sig_2330)
            ncf_live_overlay = {
                "current_regime": "golden1",
                "tsmc_0050_health": health,
                "ncf_00631l": sig_631l,
            }
            weights, updated_overlay = _apply_tsmc_weakness_trim(weights, ncf_live_overlay)
            tsmc_applied = bool(updated_overlay.get("tsmc_weakness_trim_applied"))
        overlay_targets.loc[day, list(weights.keys())] = pd.Series(weights)
        reduction = float(base_golden1_weights.get("00631L.TW", 0.0)) - float(weights.get("00631L.TW", 0.0))
        if reduction > 0.0005:
            daily_log.append(
                {
                    "date": str(day.date()),
                    "gated_downside_signal": summary.get("gated_downside_signal"),
                    "00631l_reduction": round(reduction, 4),
                    "tsmc_weakness_trim_applied": tsmc_applied,
                }
            )
    return overlay_targets, daily_log


def _apply_no_trade_band(targets: pd.DataFrame, ticker: str, band: float) -> pd.DataFrame:
    """Carry forward the last executed weight until a ticker's target drifts past `band`.

    Mirrors execution_plan.py's _apply_execution_controls min_weight_deviation
    suppression (per-ticker, compares against the last *executed* weight, not
    the previous day's raw target -- deviations accumulate across no-trade
    days). band=0.0 is a no-op (matches current default behavior elsewhere in
    this script, i.e. rebalance on every change).
    """
    if band <= 0.0:
        return targets
    out = targets.copy()
    last_executed = None
    for dt in out.index:
        target_val = float(out.loc[dt, ticker])
        # 2026-07-25: `band - 1e-9` tolerance, not a bare `>= band` -- a sibling
        # copy of this helper in evaluate_a2119_continuous_defensive_tilt_shadow.py
        # found a real floating-point boundary bug where a drift exactly equal
        # to the band (e.g. 0.5->0.4 against band=0.10) computes as
        # 0.09999999999999998 < 0.10 and silently never executes. See
        # GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md's
        # 2026-07-25 addendum.
        if last_executed is None or abs(target_val - last_executed) >= band - 1e-9:
            last_executed = target_val
        else:
            out.loc[dt, ticker] = last_executed
            # keep the two-way trim/cash split balanced when 00631L is frozen
            if "cash" in out.columns:
                drift = target_val - last_executed
                out.loc[dt, "cash"] = float(out.loc[dt, "cash"]) + drift
    return out


def evaluate(
    *,
    start: str,
    end: str,
    initial_value: float,
    db_path: Path,
    include_tsmc_trim: bool = False,
    no_trade_band: float = 0.0,
    panel_631l: str = PANEL_00631L,
    panel_632r: str = PANEL_00632R,
    panel_2330: str = PANEL_2330,
) -> dict[str, Any]:
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=initial_value,
        db=db_path,
        ncf_panel_631l_path=str(_resolve(panel_631l)),
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
    )
    total_return_prices, _dividend_coverage = _load_total_return_prices(db_path, frame.index)
    baseline_targets = _targets_from_report(frame, report)
    base_golden1_weights = {
        key: float(value) for key, value in report["base_weights"]["golden1"].items()
    }
    panel_631l_df = _load_panel(panel_631l)
    panel_632r_df = _load_panel(panel_632r)
    panel_2330_df = _load_panel(panel_2330)
    overlay_targets, daily_log = build_overlay_weights(
        frame,
        baseline_targets,
        base_golden1_weights,
        panel_631l_df,
        panel_632r_df,
        panel_2330_df,
        db_path,
        include_tsmc_trim=include_tsmc_trim,
    )
    overlay_targets = _apply_no_trade_band(overlay_targets, "00631L.TW", no_trade_band)

    baseline_curve, baseline_execution = _simulate_daily_target_weights(
        total_return_prices, baseline_targets, initial_value, 0.001425, 0.0005, 0.001
    )
    overlay_curve, overlay_execution = _simulate_daily_target_weights(
        total_return_prices, overlay_targets, initial_value, 0.001425, 0.0005, 0.001
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    overlay_metrics = _metrics(overlay_curve, initial_value)

    golden1_days = int((frame["execution_regime"] == "golden1").sum())
    panel_covered_golden1_days = len(
        [d for d in frame.index if str(frame.loc[d, "execution_regime"]) == "golden1" and d in panel_631l_df.index and d in panel_632r_df.index]
    )
    tsmc_trim_days = sum(1 for entry in daily_log if entry["tsmc_weakness_trim_applied"])

    return {
        "schema_version": 1,
        "experiment": "a2118_live_overlay_backtest_gap",
        "research_only": True,
        "production_effect": "none",
        "context": "2026-07-23 Fable audit direction 1 (priority 2): NCF continuous downside overlay (genuinely live, confirmed called from build_daily_signal) reconstructed historically and run through a2118's own price/regime path. TSMC weakness trim included only if --include-tsmc-trim was passed (default off): it is defined and unit-tested but never called from build_daily_signal, so it is not live today. bearish_high_risk_trim intentionally excluded (a2118.py's own backtest_live_discrepancy field already documents it as not reconstructable).",
        "include_tsmc_trim": include_tsmc_trim,
        "no_trade_band": no_trade_band,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "coverage": {
            "golden1_days": golden1_days,
            "golden1_days_with_ncf_632r_panel_coverage": panel_covered_golden1_days,
            "overlay_active_days": len(daily_log),
            "tsmc_weakness_trim_days": tsmc_trim_days,
            "note": "NCF panels only exist from ~2025-01 onward; this window cannot speak to pre-2025 or crash regimes such as 2020/2008.",
        },
        "baseline_metrics": baseline_metrics,
        "overlay_metrics": overlay_metrics,
        "metric_deltas": {
            key: round(float(overlay_metrics[key]) - float(baseline_metrics[key]), 6)
            for key in ("final_value", "annual_return", "sharpe_ratio", "sortino_ratio", "max_drawdown")
            if key in baseline_metrics and key in overlay_metrics
        },
        "baseline_execution": baseline_execution,
        "overlay_execution": overlay_execution,
        "daily_overlay_log": daily_log,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--panel-631l", default=PANEL_00631L, help="00631L NCF panel path (override for OOS windows, e.g. the 2017-2019 backfill).")
    parser.add_argument("--panel-632r", default=PANEL_00632R, help="00632R NCF panel path (override for OOS windows).")
    parser.add_argument("--panel-2330", default=PANEL_2330, help="2330 NCF panel path (only used with --include-tsmc-trim).")
    parser.add_argument(
        "--include-tsmc-trim",
        action="store_true",
        default=False,
        help="Also apply _apply_tsmc_weakness_trim, even though it is not actually called from build_daily_signal today.",
    )
    parser.add_argument(
        "--no-trade-band",
        type=float,
        default=0.0,
        help="Suppress 00631L trades until the target drifts this far from the last executed weight (0.0 = rebalance on any change). Set to 0.005 to mirror execution_plan.py's live min_weight_deviation.",
    )
    args = parser.parse_args()

    end = args.end
    if end == "latest":
        con_end = pd.Timestamp.now().strftime("%Y-%m-%d")
        end = con_end

    result = evaluate(
        start=args.start,
        end=end,
        initial_value=args.initial_value,
        db_path=Path(args.db),
        include_tsmc_trim=args.include_tsmc_trim,
        no_trade_band=args.no_trade_band,
        panel_631l=args.panel_631l,
        panel_632r=args.panel_632r,
        panel_2330=args.panel_2330,
    )
    result["generated_at"] = datetime.now().isoformat(timespec="seconds")
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Output: {Path(args.output).resolve()}")
    print(json.dumps(result["metric_deltas"], ensure_ascii=False, indent=2))
    print(json.dumps(result["coverage"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
