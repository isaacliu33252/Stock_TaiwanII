#!/usr/bin/env python3
"""Diagnose execution delay and missed rebounds for H20 tail-score shadow.

Read-only research.  This does not change the active A21.18 strategy.
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

from backtest_group_a_plus_defensive_basket import (  # noqa: E402
    _delayed_regime,
    _load_total_return_prices,
    _simulate_costed_curve,
)
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from group_a_plus.runners.a2118 import run_a2118  # noqa: E402
from scripts.evaluate.evaluate_a2118_h20_tail_score_shadow import (  # noqa: E402
    CONFIDENCE_GATES,
    PANELS,
    _apply_shadow_regime,
    _build_weights_by_regime,
    _load_panel,
)


DEFAULT_OUTPUT = Path("results/a2118_h20_delay_missed_rebound_20260713.json")
DEFAULT_EPISODE_CSV = Path("results/a2118_h20_delay_missed_rebound_episodes_20260713.csv")
DEFAULT_DELAY_CSV = Path("results/a2118_h20_delay_missed_rebound_portfolio_delay_20260713.csv")
HORIZONS = (5, 10, 20)


def _extract_periods(regime: pd.Series, shadow_regime: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    active = False
    start: pd.Timestamp | None = None
    periods: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    idx = list(regime.index)
    for dt in idx:
        is_shadow = str(regime.loc[dt]) == shadow_regime
        if is_shadow and not active:
            active = True
            start = dt
        elif active and not is_shadow:
            if start is not None:
                periods.append((start, dt))
            active = False
            start = None
    if active and start is not None:
        periods.append((start, idx[-1]))
    return periods


def _forward_return(series: pd.Series, dt: pd.Timestamp, horizon: int) -> float | None:
    if dt not in series.index:
        return None
    pos = series.index.get_loc(dt)
    if not isinstance(pos, int):
        return None
    end_pos = pos + horizon
    if end_pos >= len(series):
        return None
    return float(series.iloc[end_pos] / series.iloc[pos] - 1.0)


def _episode_rows(
    *,
    panel_name: str,
    panel_path: Path,
    destination: str,
    intensity: float,
    confidence_min: float | None,
    initial_value: float,
    db_path: Path,
    h20_max: float,
    tail_score_max: float,
    h5_reentry_min: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    panel = _load_panel(panel_path)
    start = str(panel.index.min().date())
    end = str(panel.index.max().date())
    _baseline_report, baseline_frame = run_a2118(
        start,
        end,
        initial_value,
        db_path,
        ncf_panel_631l_path=None,
        chip_data_fallback_max_stale_days=10,
        risk_score_lookback_days=5,
        momentum_fast_exit_min=0.10,
        momentum_fast_exit_ma_gap_min=-0.08,
        exclude_zero_volume_rows=False,
    )
    weights_by_regime, shadow_regime = _build_weights_by_regime(
        destination=destination,
        intensity=intensity,
    )
    base_regime = baseline_frame["execution_regime"].astype(str)
    target_regime, overlay_info = _apply_shadow_regime(
        base_regime,
        panel,
        shadow_regime,
        h20_max=h20_max,
        tail_score_max=tail_score_max,
        confidence_min=confidence_min,
        h5_reentry_min=h5_reentry_min,
    )
    delayed_regime = _delayed_regime(target_regime, 1)
    total_return_prices, _coverage = _load_total_return_prices(db_path, baseline_frame.index)
    delayed_baseline_regime = _delayed_regime(base_regime, 1)
    delayed_baseline_curve, delayed_baseline_sim = _simulate_costed_curve(
        total_return_prices,
        delayed_baseline_regime,
        weights_by_regime,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    no_delay_curve, no_delay_sim = _simulate_costed_curve(
        total_return_prices,
        target_regime,
        weights_by_regime,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    delay_curve, delay_sim = _simulate_costed_curve(
        total_return_prices,
        delayed_regime,
        weights_by_regime,
        initial_value,
        commission_rate=0.001425,
        slippage_rate=0.0005,
        equity_etf_sell_tax=0.001,
    )
    baseline_curve = baseline_frame["portfolio_value"].astype(float)
    no_delay_overlay_delta = float(no_delay_curve.iloc[-1] - baseline_curve.iloc[-1])
    delay_overlay_delta = float(delay_curve.iloc[-1] - delayed_baseline_curve.iloc[-1])
    delay_summary = {
        "panel": panel_name,
        "destination": destination,
        "intensity": float(intensity),
        "confidence_min": confidence_min,
        "entry_events": int(overlay_info["entry_event_count"]),
        "shadow_days": int(overlay_info["total_shadow_days"]),
        "delay_days": 1,
        "no_delay_final_value": float(no_delay_curve.iloc[-1]),
        "delay_final_value": float(delay_curve.iloc[-1]),
        "delay_minus_no_delay_final_value": float(delay_curve.iloc[-1] - no_delay_curve.iloc[-1]),
        "baseline_no_delay_final_value": float(baseline_curve.iloc[-1]),
        "baseline_delay_final_value": float(delayed_baseline_curve.iloc[-1]),
        "no_delay_overlay_final_value_delta_vs_baseline": no_delay_overlay_delta,
        "delay_overlay_final_value_delta_vs_delayed_baseline": delay_overlay_delta,
        "overlay_delay_incremental_final_value": float(delay_overlay_delta - no_delay_overlay_delta),
        "no_delay_total_return": float(_metrics(no_delay_curve, initial_value)["total_return"]),
        "delay_total_return": float(_metrics(delay_curve, initial_value)["total_return"]),
        "delay_transaction_cost_delta": float(delay_sim["transaction_cost"] - no_delay_sim["transaction_cost"]),
        "overlay_delay_incremental_transaction_cost": float(
            (delay_sim["transaction_cost"] - delayed_baseline_sim["transaction_cost"])
            - (no_delay_sim["transaction_cost"] - _baseline_report["execution"]["transaction_cost"])
        ),
        "delay_rebalance_count_delta": int(delay_sim["rebalance_count"] - no_delay_sim["rebalance_count"]),
    }

    periods = _extract_periods(target_regime, shadow_regime)
    delayed_periods = _extract_periods(delayed_regime, shadow_regime)
    p631l = total_return_prices["00631L.TW"].dropna()
    rows: list[dict[str, Any]] = []
    for i, (entry_dt, exit_dt) in enumerate(periods):
        if entry_dt not in p631l.index or exit_dt not in p631l.index:
            continue
        segment = p631l.loc[entry_dt:exit_dt]
        if len(segment) < 2:
            continue
        trough_dt = segment.idxmin()
        peak_after_trough = segment.loc[trough_dt:].max()
        delayed_entry_dt = delayed_periods[i][0] if i < len(delayed_periods) else None
        delayed_exit_dt = delayed_periods[i][1] if i < len(delayed_periods) else None
        entry_delay_return = (
            float(p631l.loc[delayed_entry_dt] / p631l.loc[entry_dt] - 1.0)
            if delayed_entry_dt is not None
            and delayed_entry_dt in p631l.index
            and delayed_entry_dt >= entry_dt
            else None
        )
        exit_delay_return = (
            float(p631l.loc[delayed_exit_dt] / p631l.loc[exit_dt] - 1.0)
            if delayed_exit_dt is not None
            and delayed_exit_dt in p631l.index
            and delayed_exit_dt >= exit_dt
            else None
        )
        row = panel.loc[entry_dt] if entry_dt in panel.index else pd.Series(dtype=float)
        out = {
            "panel": panel_name,
            "destination": destination,
            "intensity": float(intensity),
            "confidence_min": confidence_min,
            "episode_id": i + 1,
            "entry_date": str(entry_dt.date()),
            "exit_signal_date": str(exit_dt.date()),
            "delayed_entry_date": str(delayed_entry_dt.date()) if delayed_entry_dt is not None else None,
            "delayed_exit_date": str(delayed_exit_dt.date()) if delayed_exit_dt is not None else None,
            "holding_trading_days": int(len(segment) - 1),
            "entry_prob_up_h20": float(row["prob_up_h20"]) if "prob_up_h20" in row and pd.notna(row["prob_up_h20"]) else None,
            "entry_prob_up_h5": float(row["prob_up_h5"]) if "prob_up_h5" in row and pd.notna(row["prob_up_h5"]) else None,
            "entry_confidence": float(row["confidence"]) if "confidence" in row and pd.notna(row["confidence"]) else None,
            "entry_tail_reward_risk_score_h20": (
                float(row["tail_reward_risk_score_h20"])
                if "tail_reward_risk_score_h20" in row and pd.notna(row["tail_reward_risk_score_h20"])
                else None
            ),
            "trough_date": str(trough_dt.date()),
            "entry_to_trough_00631l_return": float(segment.loc[trough_dt] / segment.iloc[0] - 1.0),
            "trough_to_exit_00631l_rebound": float(segment.iloc[-1] / segment.loc[trough_dt] - 1.0),
            "trough_to_hold_peak_00631l_rebound": float(peak_after_trough / segment.loc[trough_dt] - 1.0),
            "entry_to_exit_00631l_return": float(segment.iloc[-1] / segment.iloc[0] - 1.0),
            "trough_to_exit_trading_days": int(segment.index.get_loc(exit_dt) - segment.index.get_loc(trough_dt)),
            "entry_delay_00631l_return_before_execution": entry_delay_return,
            "exit_delay_00631l_return_missed_by_t_plus_1_reentry": exit_delay_return,
        }
        for horizon in HORIZONS:
            out[f"post_exit_00631l_return_{horizon}d"] = _forward_return(p631l, exit_dt, horizon)
        rows.append(out)
    return rows, delay_summary


def _summarize_episodes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"episodes": 0}
    df = pd.DataFrame(rows)
    numeric_cols = [
        "entry_to_trough_00631l_return",
        "trough_to_exit_00631l_rebound",
        "trough_to_hold_peak_00631l_rebound",
        "entry_to_exit_00631l_return",
        "entry_delay_00631l_return_before_execution",
        "exit_delay_00631l_return_missed_by_t_plus_1_reentry",
        "post_exit_00631l_return_5d",
        "post_exit_00631l_return_10d",
        "post_exit_00631l_return_20d",
    ]
    summary: dict[str, Any] = {"episodes": int(len(df))}
    for col in numeric_cols:
        if col in df:
            s = df[col].dropna().astype(float)
            summary[col] = {
                "mean": float(s.mean()) if len(s) else None,
                "median": float(s.median()) if len(s) else None,
                "sum": float(s.sum()) if len(s) else None,
                "positive_count": int((s > 0).sum()) if len(s) else 0,
            }
    return summary


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    episode_rows: list[dict[str, Any]] = []
    delay_rows: list[dict[str, Any]] = []
    for panel_name, panel_path in PANELS.items():
        for destination in ("cash", "00679B.TWO"):
            for intensity in (0.5, 1.0):
                for confidence_min in CONFIDENCE_GATES:
                    rows, delay = _episode_rows(
                        panel_name=panel_name,
                        panel_path=panel_path,
                        destination=destination,
                        intensity=intensity,
                        confidence_min=confidence_min,
                        initial_value=args.initial_value,
                        db_path=Path(args.db),
                        h20_max=args.h20_max,
                        tail_score_max=args.tail_score_max,
                        h5_reentry_min=args.h5_reentry_min,
                    )
                    episode_rows.extend(rows)
                    delay_rows.append(delay)
    episode_csv = Path(args.episode_csv)
    episode_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(episode_rows).to_csv(episode_csv, index=False, encoding="utf-8-sig")
    delay_csv = Path(args.delay_csv)
    delay_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(delay_rows).to_csv(delay_csv, index=False, encoding="utf-8-sig")
    return {
        "schema_version": 1,
        "report_type": "a2118_h20_delay_missed_rebound",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "active_allocation_impact": "none",
        "method": (
            "For each H20 tail-score shadow variant, compare same-day target execution "
            "with a one-trading-day delayed regime, then decompose each shadow episode "
            "into entry-to-trough defense, trough-to-exit missed rebound, t+1 re-entry "
            "slippage, and post-exit 00631L returns."
        ),
        "params": {
            "h20_max": float(args.h20_max),
            "tail_score_max": float(args.tail_score_max),
            "h5_reentry_min": float(args.h5_reentry_min),
            "confidence_gates": list(CONFIDENCE_GATES),
        },
        "episode_summary_all_variants": _summarize_episodes(episode_rows),
        "portfolio_delay_summary": delay_rows,
        "episode_csv": str(episode_csv),
        "delay_csv": str(delay_csv),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--h20-max", type=float, default=0.33)
    parser.add_argument("--tail-score-max", type=float, default=-0.30)
    parser.add_argument("--h5-reentry-min", type=float, default=0.55)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--episode-csv", default=str(DEFAULT_EPISODE_CSV))
    parser.add_argument("--delay-csv", default=str(DEFAULT_DELAY_CSV))
    args = parser.parse_args()
    report = build_report(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.resolve())
    print(Path(args.episode_csv).resolve())
    print(Path(args.delay_csv).resolve())


if __name__ == "__main__":
    main()
