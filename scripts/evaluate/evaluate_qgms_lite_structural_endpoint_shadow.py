#!/usr/bin/env python3
"""Backtest QGMS-lite structural endpoint as a 00631L no-add shadow signal.

Research-only. This is not the proprietary QGMS model from the paper. It
implements a transparent, no-lookahead proxy using online swing confirmation,
leg symmetry, duration symmetry, volatility-adjusted extension, and 00631L/0050
relative overextension. It never changes live weights or strategy manifests.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "qgms_lite_structural_endpoint_shadow_latest.json"
DEFAULT_SYMBOLS = ("0050.TW", "00631L.TW")


@dataclass(frozen=True)
class ConfirmedPivot:
    confirmed_at: pd.Timestamp
    pivot_at: pd.Timestamp
    price: float
    kind: str


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _clip01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _forward_min_drawdown(close: pd.Series, horizon: int) -> pd.Series:
    future = pd.concat([close.shift(-step) for step in range(1, horizon + 1)], axis=1)
    return future.min(axis=1) / close - 1.0


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


def _load_close_panel_from_db(
    db_path: Path,
    *,
    symbols: tuple[str, ...],
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        for table in ("ohlcv", "external_market_ohlcv"):
            if table not in tables:
                continue
            rows = con.execute(
                f"""
                SELECT dt, ticker, close
                FROM {table}
                WHERE ticker IN (SELECT * FROM UNNEST(?))
                  AND dt BETWEEN ? AND ?
                """,
                [list(symbols), str(start_date.date()), str(end_date.date())],
            ).fetchdf()
            if not rows.empty:
                frames.append(rows)
    finally:
        con.close()
    if not frames:
        return pd.DataFrame()
    rows = pd.concat(frames, ignore_index=True)
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    rows = rows.dropna(subset=["dt", "ticker", "close"])
    rows = rows.sort_values(["dt", "ticker"]).drop_duplicates(["dt", "ticker"], keep="last")
    return rows.pivot(index="dt", columns="ticker", values="close").sort_index()


def _symmetry_score(value: float | None, target: float = 1.0, tolerance: float = 0.75) -> float:
    if value is None or not np.isfinite(value) or value <= 0:
        return 0.0
    distance = abs(float(value) - target)
    return _clip01(1.0 - distance / tolerance)


def _online_qgms_lite_frame(
    prices: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    min_swing_pct: float,
    vol_window: int,
    endpoint_threshold: float,
    strong_endpoint_threshold: float,
) -> pd.DataFrame:
    series = prices["00631L.TW"].dropna().astype(float)
    base = prices["0050.TW"].dropna().astype(float)
    aligned = pd.concat({"00631L.TW": series, "0050.TW": base}, axis=1).dropna().sort_index()
    returns = aligned["00631L.TW"].pct_change(fill_method=None)
    realized_vol = returns.rolling(vol_window, min_periods=max(5, vol_window // 2)).std(ddof=0)
    rel_momentum_20 = (
        aligned["00631L.TW"].pct_change(20, fill_method=None)
        - aligned["0050.TW"].pct_change(20, fill_method=None)
    )

    pivots: list[ConfirmedPivot] = []
    trend: str | None = None
    pivot_at = pd.Timestamp(aligned.index[0])
    pivot_price = float(aligned.iloc[0]["00631L.TW"])
    extreme_at = pivot_at
    extreme_price = pivot_price
    rows: list[dict[str, Any]] = []

    for dt, row in aligned.iterrows():
        dt = pd.Timestamp(dt).normalize()
        price = float(row["00631L.TW"])
        if trend is None:
            up_move = price / pivot_price - 1.0
            down_move = price / pivot_price - 1.0
            if up_move >= min_swing_pct:
                trend = "up"
                extreme_at = dt
                extreme_price = price
                pivots.append(ConfirmedPivot(dt, pivot_at, pivot_price, "low"))
            elif down_move <= -min_swing_pct:
                trend = "down"
                extreme_at = dt
                extreme_price = price
                pivots.append(ConfirmedPivot(dt, pivot_at, pivot_price, "high"))
        elif trend == "up":
            if price >= extreme_price:
                extreme_at = dt
                extreme_price = price
            elif price / extreme_price - 1.0 <= -min_swing_pct:
                pivots.append(ConfirmedPivot(dt, extreme_at, extreme_price, "high"))
                pivot_at = extreme_at
                pivot_price = extreme_price
                trend = "down"
                extreme_at = dt
                extreme_price = price
        else:
            if price <= extreme_price:
                extreme_at = dt
                extreme_price = price
            elif price / extreme_price - 1.0 >= min_swing_pct:
                pivots.append(ConfirmedPivot(dt, extreme_at, extreme_price, "low"))
                pivot_at = extreme_at
                pivot_price = extreme_price
                trend = "up"
                extreme_at = dt
                extreme_price = price

        if dt < start or dt > end:
            continue
        known = [pivot for pivot in pivots if pivot.confirmed_at <= dt]
        last = known[-1] if known else None
        prev = known[-2] if len(known) >= 2 else None
        prev2 = known[-3] if len(known) >= 3 else None
        current_direction = 0
        current_leg_return = np.nan
        current_leg_days = np.nan
        previous_leg_return = np.nan
        previous_leg_days = np.nan
        leg_ratio = np.nan
        duration_ratio = np.nan
        slope_ratio = np.nan
        if last is not None:
            current_leg_return = price / last.price - 1.0
            current_leg_days = max((dt - last.pivot_at).days, 1)
            current_direction = 1 if current_leg_return > 0 else -1 if current_leg_return < 0 else 0
        if prev is not None and last is not None:
            previous_leg_return = last.price / prev.price - 1.0
            previous_leg_days = max((last.pivot_at - prev.pivot_at).days, 1)
        if np.isfinite(current_leg_return) and np.isfinite(previous_leg_return) and abs(previous_leg_return) > 1e-9:
            leg_ratio = abs(current_leg_return / previous_leg_return)
        if np.isfinite(current_leg_days) and np.isfinite(previous_leg_days) and previous_leg_days > 0:
            duration_ratio = float(current_leg_days / previous_leg_days)
        if (
            np.isfinite(current_leg_return)
            and np.isfinite(current_leg_days)
            and np.isfinite(previous_leg_return)
            and np.isfinite(previous_leg_days)
            and abs(previous_leg_return / previous_leg_days) > 1e-12
        ):
            slope_ratio = abs((current_leg_return / current_leg_days) / (previous_leg_return / previous_leg_days))

        vol = float(realized_vol.reindex([dt]).iloc[0]) if dt in realized_vol.index else np.nan
        vol_adjusted_extension = (
            abs(float(current_leg_return)) / max(vol * np.sqrt(max(float(current_leg_days), 1.0)), 1e-9)
            if np.isfinite(current_leg_return) and np.isfinite(current_leg_days) and np.isfinite(vol) and vol > 0
            else np.nan
        )
        rel_overextension = float(rel_momentum_20.reindex([dt]).iloc[0]) if dt in rel_momentum_20.index else np.nan
        harmonic_score = 0.5 * _symmetry_score(leg_ratio) + 0.5 * _symmetry_score(duration_ratio)
        extension_score = _clip01((float(vol_adjusted_extension) - 1.0) / 1.8) if np.isfinite(vol_adjusted_extension) else 0.0
        relative_score = _clip01((float(rel_overextension) - 0.025) / 0.10) if np.isfinite(rel_overextension) else 0.0
        deceleration_score = _clip01((1.0 - float(slope_ratio)) / 0.8) if np.isfinite(slope_ratio) else 0.0
        hierarchy_score = 0.0
        if prev2 is not None and prev is not None and last is not None and np.isfinite(current_leg_return):
            parent_return = last.price / prev2.price - 1.0
            hierarchy_score = _symmetry_score(abs(current_leg_return / parent_return), target=0.5, tolerance=0.5) if abs(parent_return) > 1e-9 else 0.0
        endpoint_score = (
            0.28 * harmonic_score
            + 0.24 * extension_score
            + 0.20 * relative_score
            + 0.18 * deceleration_score
            + 0.10 * hierarchy_score
        )
        endpoint_watch_active = bool(current_direction > 0 and endpoint_score >= endpoint_threshold)
        strong_endpoint_active = bool(current_direction > 0 and endpoint_score >= strong_endpoint_threshold)
        rows.append(
            {
                "date": dt,
                "qgms_lite_endpoint_score": round(float(endpoint_score), 4),
                "endpoint_watch_active": endpoint_watch_active,
                "strong_endpoint_active": strong_endpoint_active,
                "current_direction": int(current_direction),
                "current_leg_return": round(float(current_leg_return), 6) if np.isfinite(current_leg_return) else np.nan,
                "current_leg_days": int(current_leg_days) if np.isfinite(current_leg_days) else np.nan,
                "previous_leg_return": round(float(previous_leg_return), 6) if np.isfinite(previous_leg_return) else np.nan,
                "previous_leg_days": int(previous_leg_days) if np.isfinite(previous_leg_days) else np.nan,
                "leg_ratio": round(float(leg_ratio), 6) if np.isfinite(leg_ratio) else np.nan,
                "duration_ratio": round(float(duration_ratio), 6) if np.isfinite(duration_ratio) else np.nan,
                "slope_ratio": round(float(slope_ratio), 6) if np.isfinite(slope_ratio) else np.nan,
                "vol_adjusted_extension": round(float(vol_adjusted_extension), 6)
                if np.isfinite(vol_adjusted_extension)
                else np.nan,
                "relative_momentum_20d": round(float(rel_overextension), 6) if np.isfinite(rel_overextension) else np.nan,
                "harmonic_score": round(float(harmonic_score), 4),
                "extension_score": round(float(extension_score), 4),
                "relative_score": round(float(relative_score), 4),
                "deceleration_score": round(float(deceleration_score), 4),
                "hierarchy_score": round(float(hierarchy_score), 4),
                "confirmed_pivots": int(len(known)),
            }
        )
    return pd.DataFrame(rows).set_index("date").sort_index()


def _score_forward_summary_for_signal(frame: pd.DataFrame, active: pd.Series, horizon: int) -> dict[str, Any]:
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
    rows: list[dict[str, Any]] = []
    if frame.empty:
        return rows
    for threshold in (0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
        for min_ext in (None, 1.2, 1.5, 1.8):
            signal = (frame["current_direction"] > 0) & (frame["qgms_lite_endpoint_score"] >= threshold)
            rule_parts = [f"score>={threshold:.2f}", "up_leg"]
            if min_ext is not None:
                signal &= frame["vol_adjusted_extension"] >= min_ext
                rule_parts.append(f"vol_ext>={min_ext:.1f}")
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
                    "h10_precision": h10["confusion"]["precision"],
                    "h10_recall": h10["confusion"]["recall"],
                    "h10_false_positive_rate": h10["confusion"]["false_positive_rate"],
                    "h10_active_mean_relative_vs_0050": h10["active_mean_relative_vs_0050"],
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


def build_qgms_lite_backtest(
    *,
    db_path: Path,
    start: str,
    end: str,
    load_lookback_days: int,
    min_swing_pct: float,
    vol_window: int,
    endpoint_threshold: float,
    strong_endpoint_threshold: float,
    underperform_threshold: float,
    mdd_threshold: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    prices = _load_close_panel_from_db(
        db_path,
        symbols=DEFAULT_SYMBOLS,
        start_date=start_ts - pd.Timedelta(days=load_lookback_days),
        end_date=end_ts,
    )
    if prices.empty or not set(DEFAULT_SYMBOLS).issubset(prices.columns):
        raise RuntimeError("No 0050/00631L prices loaded for QGMS-lite backtest")
    frame = _online_qgms_lite_frame(
        prices,
        start=start_ts,
        end=end_ts,
        min_swing_pct=min_swing_pct,
        vol_window=vol_window,
        endpoint_threshold=endpoint_threshold,
        strong_endpoint_threshold=strong_endpoint_threshold,
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

    endpoint_active = frame["endpoint_watch_active"].astype(bool) if len(frame) else pd.Series(dtype=bool)
    strong_active = frame["strong_endpoint_active"].astype(bool) if len(frame) else pd.Series(dtype=bool)
    report = {
        "report_type": "qgms_lite_structural_endpoint_shadow_backtest",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2511.16319v1.pdf",
            "title": "Quantitative Geometric Market Structuralism (QGMS)",
            "implementation_note": "Transparent proxy only; proprietary Phi(Si) operator is not disclosed in the paper.",
        },
        "window": {
            "start": str(frame.index.min().date()) if len(frame) else start,
            "end": str(frame.index.max().date()) if len(frame) else end,
            "rows": int(len(frame)),
        },
        "policy": "shadow_only_no_weight_change",
        "parameters": {
            "symbols": list(DEFAULT_SYMBOLS),
            "min_swing_pct": min_swing_pct,
            "vol_window": vol_window,
            "endpoint_threshold": endpoint_threshold,
            "strong_endpoint_threshold": strong_endpoint_threshold,
            "underperform_threshold": underperform_threshold,
            "mdd_threshold": mdd_threshold,
        },
        "summary": {
            "endpoint_active_days": int(endpoint_active.sum()) if len(frame) else 0,
            "strong_endpoint_active_days": int(strong_active.sum()) if len(frame) else 0,
            "mean_score": float(frame["qgms_lite_endpoint_score"].mean()) if len(frame) else None,
            "max_score": float(frame["qgms_lite_endpoint_score"].max()) if len(frame) else None,
            "endpoint_watch_by_horizon": {
                "h5": _score_forward_summary_for_signal(frame, endpoint_active, 5),
                "h10": _score_forward_summary_for_signal(frame, endpoint_active, 10),
            },
            "strong_endpoint_by_horizon": {
                "h5": _score_forward_summary_for_signal(frame, strong_active, 5),
                "h10": _score_forward_summary_for_signal(frame, strong_active, 10),
            },
            "rule_sweep_top10": _sweep_rules(frame)[:10],
        },
        "interpretation": (
            "QGMS-lite should only be considered useful if endpoint days show worse forward 00631L "
            "relative returns or drawdowns with acceptable false positives. This report is diagnostic "
            "and does not validate automatic trading."
        ),
    }
    return report, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-07-16")
    parser.add_argument("--load-lookback-days", type=int, default=900)
    parser.add_argument("--min-swing-pct", type=float, default=0.035)
    parser.add_argument("--vol-window", type=int, default=20)
    parser.add_argument("--endpoint-threshold", type=float, default=0.55)
    parser.add_argument("--strong-endpoint-threshold", type=float, default=0.65)
    parser.add_argument("--underperform-threshold", type=float, default=-0.01)
    parser.add_argument("--mdd-threshold", type=float, default=-0.05)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report, frame = build_qgms_lite_backtest(
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        load_lookback_days=int(args.load_lookback_days),
        min_swing_pct=float(args.min_swing_pct),
        vol_window=int(args.vol_window),
        endpoint_threshold=float(args.endpoint_threshold),
        strong_endpoint_threshold=float(args.strong_endpoint_threshold),
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
