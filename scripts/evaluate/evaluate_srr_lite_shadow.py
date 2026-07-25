#!/usr/bin/env python3
"""Backtest SRR-lite as a 00631L no-add shadow detector.

Research-only. This script does not change live signals, target weights, or
strategy manifests. For each historical date it computes the SRR-lite
correlation-network fragility snapshot using only data available up to that
date, then evaluates whether the no-add flag anticipated 00631L forward
underperformance or drawdown.
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

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.srr_lite_shadow import (
    CORE_SYMBOLS,
    CRASH_WATCH_DENSITY_THRESHOLD,
    CRASH_WATCH_THRESHOLD,
    DEFAULT_SYMBOLS,
    HIGH_FRAGILITY_THRESHOLD,
    NO_ADD_DENSITY_THRESHOLD,
    NO_ADD_THRESHOLD,
    NO_ADD_VELOCITY_THRESHOLD,
    _avg_abs_corr,
    _centrality,
    _clip01,
    _density,
    _load_close_panel_from_db,
    _safe_corr,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "srr_lite_shadow_backtest_latest.json"


def _forward_min_drawdown(close: pd.Series, horizon: int) -> pd.Series:
    future = pd.concat([close.shift(-step) for step in range(1, horizon + 1)], axis=1)
    return future.min(axis=1) / close - 1.0


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _confusion(pred: pd.Series, label: pd.Series) -> dict[str, Any]:
    valid = pred.notna() & label.notna()
    p = pred[valid].astype(bool)
    y = label[valid].astype(bool)
    tp = int((p & y).sum())
    fp = int((p & ~y).sum())
    tn = int((~p & ~y).sum())
    fn = int((~p & y).sum())
    return {
        "rows": int(valid.sum()),
        "active_days": int(p.sum()),
        "event_days": int(y.sum()),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": _safe_rate(tp, tp + fp),
        "recall": _safe_rate(tp, tp + fn),
        "false_positive_rate": _safe_rate(fp, fp + tn),
    }


def _srr_lite_frame_from_prices(
    prices: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    corr_window: int,
    baseline_window: int,
    edge_threshold: float = 0.50,
) -> pd.DataFrame:
    returns = prices.pct_change(fill_method=None).replace([float("inf"), float("-inf")], pd.NA)
    returns = returns.dropna(how="all").dropna(axis=1, thresh=max(corr_window, 6)).fillna(0.0)
    rows: list[dict[str, Any]] = []
    density_history: list[float] = []
    for pos in range(corr_window, len(returns) + 1):
        dt = pd.Timestamp(returns.index[pos - 1]).normalize()
        if dt < start or dt > end:
            # Still keep pre-start density in history so baseline is warm.
            include_output = False
        else:
            include_output = True
        latest_returns = returns.iloc[pos - corr_window:pos]
        prev_returns = returns.iloc[pos - corr_window - 1:pos - 1] if pos > corr_window else latest_returns
        corr = _safe_corr(latest_returns)
        prev_corr = _safe_corr(prev_returns).reindex_like(corr).fillna(0.0)
        density = _density(corr, edge_threshold)
        avg_corr = _avg_abs_corr(corr)
        velocity = float(abs(corr.to_numpy(dtype=float) - prev_corr.to_numpy(dtype=float)).mean())
        density_history.append(density)
        hist = pd.Series(density_history[-baseline_window:], dtype=float)
        hist_mean = float(hist.mean()) if len(hist) else density
        hist_std = float(hist.std(ddof=0)) if len(hist) else 0.0
        density_z = 0.0 if hist_std <= 1e-12 else float((density - hist_mean) / hist_std)
        centrality = _centrality(corr)
        core_centrality = max((centrality.get(symbol, 0.0) for symbol in CORE_SYMBOLS), default=0.0)
        components = {
            "density": _clip01((density - 0.35) / 0.35),
            "avg_abs_corr": _clip01((avg_corr - 0.35) / 0.35),
            "density_spike": _clip01(density_z / 3.0),
            "graph_velocity": _clip01(velocity / 0.35),
            "core_centrality": _clip01((core_centrality - 0.35) / 0.35),
        }
        score = (
            0.25 * components["density"]
            + 0.25 * components["avg_abs_corr"]
            + 0.20 * components["density_spike"]
            + 0.15 * components["graph_velocity"]
            + 0.15 * components["core_centrality"]
        )
        if not include_output:
            continue
        level = "high" if score >= HIGH_FRAGILITY_THRESHOLD else "elevated" if score >= 0.55 else "normal"
        rows.append(
            {
                "date": dt,
                "systemic_fragility_score": round(float(score), 4),
                "fragility_level": level,
                "no_add_active": bool(
                    score >= NO_ADD_THRESHOLD
                    and density >= NO_ADD_DENSITY_THRESHOLD
                    and velocity >= NO_ADD_VELOCITY_THRESHOLD
                ),
                "crash_watch_active": bool(
                    score >= CRASH_WATCH_THRESHOLD
                    and density >= CRASH_WATCH_DENSITY_THRESHOLD
                ),
                "graph_density": round(density, 4),
                "avg_abs_corr": round(avg_corr, 4),
                "density_z": round(density_z, 4),
                "graph_velocity": round(velocity, 4),
                "core_max_centrality": round(core_centrality, 4),
            }
        )
    return pd.DataFrame(rows).set_index("date").sort_index()


def _score_forward_summary(frame: pd.DataFrame, horizon: int) -> dict[str, Any]:
    active = frame["no_add_active"].astype(bool)
    return _score_forward_summary_for_signal(frame, active, horizon)


def _score_forward_summary_for_signal(
    frame: pd.DataFrame,
    active: pd.Series,
    horizon: int,
) -> dict[str, Any]:
    active = active.reindex(frame.index).fillna(False).astype(bool)
    ret_col = f"forward_ret_00631l_h{horizon}"
    rel_col = f"forward_rel_00631l_vs_0050_h{horizon}"
    mdd_col = f"forward_mdd_00631l_h{horizon}"
    label_col = f"no_add_label_h{horizon}"
    return {
        "horizon_days": horizon,
        "confusion": _confusion(active, frame[label_col]),
        "active_mean_forward_ret_00631l": float(frame.loc[active, ret_col].mean()) if active.any() else None,
        "inactive_mean_forward_ret_00631l": float(frame.loc[~active, ret_col].mean()) if (~active).any() else None,
        "active_mean_relative_vs_0050": float(frame.loc[active, rel_col].mean()) if active.any() else None,
        "inactive_mean_relative_vs_0050": float(frame.loc[~active, rel_col].mean()) if (~active).any() else None,
        "active_mean_forward_mdd_00631l": float(frame.loc[active, mdd_col].mean()) if active.any() else None,
        "inactive_mean_forward_mdd_00631l": float(frame.loc[~active, mdd_col].mean()) if (~active).any() else None,
    }


def _sweep_rules(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Rank simple no-add shadow rules without changing live policy."""
    if frame.empty:
        return []
    score_thresholds = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80)
    density_thresholds: tuple[float | None, ...] = (None, 0.60, 0.65, 0.70)
    velocity_thresholds: tuple[float | None, ...] = (None, 0.18, 0.22)
    rows: list[dict[str, Any]] = []
    for score_threshold in score_thresholds:
        for density_threshold in density_thresholds:
            for velocity_threshold in velocity_thresholds:
                signal = frame["systemic_fragility_score"] >= score_threshold
                rule_parts = [f"score>={score_threshold:.2f}"]
                if density_threshold is not None:
                    signal &= frame["graph_density"] >= density_threshold
                    rule_parts.append(f"density>={density_threshold:.2f}")
                if velocity_threshold is not None:
                    signal &= frame["graph_velocity"] >= velocity_threshold
                    rule_parts.append(f"velocity>={velocity_threshold:.2f}")
                active_days = int(signal.sum())
                if active_days < 5:
                    continue
                h5 = _score_forward_summary_for_signal(frame, signal, 5)
                h10 = _score_forward_summary_for_signal(frame, signal, 10)
                rows.append(
                    {
                        "rule": " and ".join(rule_parts),
                        "active_days": active_days,
                        "h5_precision": h5["confusion"]["precision"],
                        "h5_recall": h5["confusion"]["recall"],
                        "h5_false_positive_rate": h5["confusion"]["false_positive_rate"],
                        "h5_active_mean_relative_vs_0050": h5["active_mean_relative_vs_0050"],
                        "h5_active_mean_forward_mdd_00631l": h5["active_mean_forward_mdd_00631l"],
                        "h10_precision": h10["confusion"]["precision"],
                        "h10_recall": h10["confusion"]["recall"],
                        "h10_false_positive_rate": h10["confusion"]["false_positive_rate"],
                        "h10_active_mean_relative_vs_0050": h10["active_mean_relative_vs_0050"],
                        "h10_active_mean_forward_mdd_00631l": h10["active_mean_forward_mdd_00631l"],
                    }
                )
    return sorted(
        rows,
        key=lambda row: (
            row["h10_precision"] if row["h10_precision"] is not None else -1.0,
            row["h5_precision"] if row["h5_precision"] is not None else -1.0,
            -(row["h10_false_positive_rate"] if row["h10_false_positive_rate"] is not None else 1.0),
            row["active_days"],
        ),
        reverse=True,
    )


def build_srr_lite_backtest(
    *,
    db_path: Path,
    start: str,
    end: str,
    symbols: tuple[str, ...],
    load_lookback_days: int,
    corr_window: int,
    baseline_window: int,
    underperform_threshold: float,
    mdd_threshold: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    prices = _load_close_panel_from_db(
        db_path,
        symbols=symbols,
        end_date=end_ts,
        lookback_days=load_lookback_days,
    )
    if prices.empty:
        raise RuntimeError("No prices loaded for SRR-lite backtest")
    prices = prices.sort_index()
    frame = _srr_lite_frame_from_prices(
        prices,
        start=start_ts,
        end=end_ts,
        corr_window=corr_window,
        baseline_window=baseline_window,
    )
    for horizon in (5, 10):
        ret_631l = prices["00631L.TW"].shift(-horizon) / prices["00631L.TW"] - 1.0
        ret_0050 = prices["0050.TW"].shift(-horizon) / prices["0050.TW"] - 1.0
        mdd_631l = _forward_min_drawdown(prices["00631L.TW"], horizon)
        frame[f"forward_ret_00631l_h{horizon}"] = ret_631l.reindex(frame.index)
        frame[f"forward_ret_0050_h{horizon}"] = ret_0050.reindex(frame.index)
        frame[f"forward_rel_00631l_vs_0050_h{horizon}"] = (ret_631l - ret_0050).reindex(frame.index)
        frame[f"forward_mdd_00631l_h{horizon}"] = mdd_631l.reindex(frame.index)
        frame[f"no_add_label_h{horizon}"] = (
            (frame[f"forward_rel_00631l_vs_0050_h{horizon}"] <= underperform_threshold)
            | (frame[f"forward_mdd_00631l_h{horizon}"] <= mdd_threshold)
        )

    report = {
        "report_type": "srr_lite_shadow_backtest",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window": {
            "start": str(frame.index.min().date()) if len(frame) else start,
            "end": str(frame.index.max().date()) if len(frame) else end,
            "rows": int(len(frame)),
        },
        "policy": "shadow_only_no_weight_change",
        "parameters": {
            "symbols": list(symbols),
            "corr_window": corr_window,
            "baseline_window": baseline_window,
            "no_add_score_threshold": NO_ADD_THRESHOLD,
            "no_add_density_threshold": NO_ADD_DENSITY_THRESHOLD,
            "no_add_velocity_threshold": NO_ADD_VELOCITY_THRESHOLD,
            "crash_watch_score_threshold": CRASH_WATCH_THRESHOLD,
            "crash_watch_density_threshold": CRASH_WATCH_DENSITY_THRESHOLD,
            "underperform_threshold": underperform_threshold,
            "mdd_threshold": mdd_threshold,
        },
        "summary": {
            "active_days": int(frame["no_add_active"].sum()) if len(frame) else 0,
            "mean_score": float(frame["systemic_fragility_score"].mean()) if len(frame) else None,
            "max_score": float(frame["systemic_fragility_score"].max()) if len(frame) else None,
            "by_horizon": {
                "h5": _score_forward_summary(frame, 5),
                "h10": _score_forward_summary(frame, 10),
            },
            "rule_sweep_top10": _sweep_rules(frame)[:10],
        },
        "interpretation": (
            "A useful no-add shadow should have active days with worse forward 00631L relative returns "
            "or drawdowns than inactive days, while keeping false positives tolerable. This report is "
            "diagnostic only and does not validate automatic trading."
        ),
    }
    return report, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-07-16")
    parser.add_argument("--load-lookback-days", type=int, default=900)
    parser.add_argument("--corr-window", type=int, default=7)
    parser.add_argument("--baseline-window", type=int, default=60)
    parser.add_argument("--underperform-threshold", type=float, default=-0.01)
    parser.add_argument("--mdd-threshold", type=float, default=-0.05)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report, frame = build_srr_lite_backtest(
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        symbols=DEFAULT_SYMBOLS,
        load_lookback_days=int(args.load_lookback_days),
        corr_window=int(args.corr_window),
        baseline_window=int(args.baseline_window),
        underperform_threshold=float(args.underperform_threshold),
        mdd_threshold=float(args.mdd_threshold),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_output = output.with_name(output.stem + "_frame.csv")
    frame.to_csv(frame_output, encoding="utf-8-sig")
    report["frame_output"] = str(frame_output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(f"Frame: {frame_output}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
