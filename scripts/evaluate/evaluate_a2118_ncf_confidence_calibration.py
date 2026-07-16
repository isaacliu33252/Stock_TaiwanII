#!/usr/bin/env python3
"""Confidence calibration and event-level value for A21.18's NCF overlay."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY, resolve_latest
from group_a_plus.runners.a2118 import run_a2118


DEFAULT_OUTPUT = Path("results/a2118_ncf_confidence_calibration_20260713.json")
DEFAULT_EVENT_CSV = Path("results/a2118_ncf_event_overlay_value_20260713.csv")
DEFAULT_PLOT = Path("results/a2118_ncf_h20_confidence_joint_20260713.png")
TICKERS = ["0050.TW", "00631L.TW"]


def _safe_brier(y: pd.Series, p: pd.Series) -> float | None:
    valid = y.notna() & p.notna()
    if not valid.any():
        return None
    return float(((p[valid].astype(float) - y[valid].astype(float)) ** 2).mean())


def _confidence_stats(panel: pd.DataFrame) -> dict[str, float]:
    s = panel["confidence"].dropna().astype(float)
    qs = s.quantile([0.10, 0.25, 0.50, 0.75, 0.90])
    return {
        "min": float(s.min()),
        "p10": float(qs.loc[0.10]),
        "p25": float(qs.loc[0.25]),
        "median": float(qs.loc[0.50]),
        "p75": float(qs.loc[0.75]),
        "p90": float(qs.loc[0.90]),
        "max": float(s.max()),
    }


def _bucket_calibration(panel: pd.DataFrame) -> list[dict[str, Any]]:
    bins = [-0.001, 0.10, 0.20, 0.30, 0.40, 0.50, 0.55, 0.65, 1.0]
    labels = ["0-0.10", "0.10-0.20", "0.20-0.30", "0.30-0.40", "0.40-0.50", "0.50-0.55", "0.55-0.65", "0.65-1.00"]
    work = panel.copy()
    work["confidence_bucket"] = pd.cut(work["confidence"], bins=bins, labels=labels)
    rows: list[dict[str, Any]] = []
    for bucket, part in work.groupby("confidence_bucket", observed=False):
        if part.empty:
            rows.append({"bucket": str(bucket), "rows": 0})
            continue
        y = part["actual_fwd_gain_gt5_h20"] if "actual_fwd_gain_gt5_h20" in part else pd.Series(index=part.index, dtype=float)
        p = part["prob_up_h20"]
        bearish = part[p < 0.5]
        rows.append(
            {
                "bucket": str(bucket),
                "rows": int(len(part)),
                "mean_confidence": float(part["confidence"].mean()),
                "mean_prob_up_h20": float(p.mean()),
                "h20_hit_rate_up": float(y.dropna().mean()) if y.notna().any() else None,
                "h20_brier_up": _safe_brier(y, p),
                "bearish_rows": int(len(bearish)),
                "bearish_actual_down_hit_rate": (
                    float((1.0 - bearish["actual_fwd_gain_gt5_h20"]).dropna().mean())
                    if len(bearish) and bearish["actual_fwd_gain_gt5_h20"].notna().any()
                    else None
                ),
                "bearish_forward_mdd_mean": (
                    float(bearish["forward_mdd_h20"].dropna().mean())
                    if len(bearish) and bearish["forward_mdd_h20"].notna().any()
                    else None
                ),
                "bearish_forward_gain_mean": (
                    float(bearish["forward_gain_h20"].dropna().mean())
                    if len(bearish) and bearish["forward_gain_h20"].notna().any()
                    else None
                ),
            }
        )
    return rows


def _event_overlay_rows(
    joined: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    conf_min: float,
    h20_max: float,
    h5_reentry_min: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    idx = list(joined.index)
    in_event = False
    start_pos = 0
    start_dt: pd.Timestamp | None = None

    def is_trigger(row: pd.Series) -> bool:
        return bool(
            str(row["base_regime"]) == "golden1"
            and float(row["ma_gap"]) > 0.10
            and float(row["prob_up_h20"]) < h20_max
            and float(row["confidence"]) >= conf_min
        )

    for pos, dt in enumerate(idx):
        row = joined.loc[dt]
        trigger = is_trigger(row)
        if not in_event:
            if trigger:
                in_event = True
                start_pos = pos
                start_dt = dt
            continue

        h5 = float(row["prob_up_h5"]) if pd.notna(row.get("prob_up_h5")) else 1.0
        if trigger:
            continue
        if h5 >= h5_reentry_min:
            end_pos = pos
            end_dt = dt
            entry = prices.loc[start_dt]
            exit_ = prices.loc[end_dt]
            r50 = float(exit_["0050.TW"] / entry["0050.TW"])
            r631l = float(exit_["00631L.TW"] / entry["00631L.TW"])
            buy_cost = commission_rate + slippage_rate
            sell_cost = commission_rate + slippage_rate + equity_etf_sell_tax
            shifted_final = (1.0 - sell_cost) * (1.0 - buy_cost) * r50 * (1.0 - sell_cost) * (1.0 - buy_cost)
            delta_per_shifted_dollar = shifted_final - r631l
            start_row = joined.loc[start_dt]
            events.append(
                {
                    "entry_date": str(start_dt.date()),
                    "exit_date": str(end_dt.date()),
                    "holding_trading_days": int(end_pos - start_pos),
                    "entry_ma_gap": float(start_row["ma_gap"]),
                    "entry_h20_prob_up": float(start_row["prob_up_h20"]),
                    "entry_confidence": float(start_row["confidence"]),
                    "entry_prob_up_h5": float(start_row["prob_up_h5"]) if pd.notna(start_row.get("prob_up_h5")) else None,
                    "exit_prob_up_h5": h5,
                    "return_0050": r50 - 1.0,
                    "return_00631l": r631l - 1.0,
                    "overlay_value_per_shifted_dollar_net_cost": delta_per_shifted_dollar,
                    "overlay_value_per_shifted_dollar_gross": r50 - r631l,
                    "forward_mdd_h20": float(start_row["forward_mdd_h20"]) if pd.notna(start_row.get("forward_mdd_h20")) else None,
                    "forward_gain_h20": float(start_row["forward_gain_h20"]) if pd.notna(start_row.get("forward_gain_h20")) else None,
                }
            )
            in_event = False
            start_dt = None

    return events


def _plot_joint(panel: pd.DataFrame, output: Path) -> str | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        return f"plot_unavailable: {exc}"

    valid = panel.dropna(subset=["prob_up_h20", "confidence", "actual_fwd_gain_gt5_h20"])
    colors = valid["actual_fwd_gain_gt5_h20"].map({1.0: "#2ca02c", 0.0: "#d62728"}).fillna("#7f7f7f")
    fig, ax = plt.subplots(figsize=(8, 5), dpi=140)
    ax.scatter(valid["prob_up_h20"], valid["confidence"], c=colors, alpha=0.72, s=22, edgecolors="none")
    ax.axvline(0.33, color="#1f77b4", linestyle="--", linewidth=1.2, label="h20_max=0.33")
    ax.axhline(0.55, color="#9467bd", linestyle="--", linewidth=1.2, label="conf_min=0.55")
    ax.set_xlabel("prob_up_h20")
    ax.set_ylabel("confidence = abs(panel ensemble prob - 0.5) * 2")
    ax.set_title("A21.18 NCF H20 probability vs confidence")
    ax.legend(loc="upper left", frameon=False)
    ax.grid(True, alpha=0.2)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output)
    plt.close(fig)
    return None


def build_report(
    *,
    manifest_path: Path,
    db_path: Path,
    output_plot: Path,
    event_csv: Path,
) -> dict[str, Any]:
    manifest = resolve_latest(manifest_path)
    params = dict(manifest["active_strategy"].get("runner_params") or {})
    panel_path = Path(params["ncf_panel_631l_path"])
    if not panel_path.is_absolute():
        panel_path = PROJECT_ROOT / panel_path
    panel = pd.read_csv(panel_path, parse_dates=["date"]).set_index("date").sort_index()
    panel.index = pd.to_datetime(panel.index).normalize()

    start = str(panel.index.min().date())
    end = str(panel.index.max().date())
    _report, frame = run_a2118(
        start,
        end,
        1_000_000.0,
        db_path,
        ncf_panel_631l_path=None,
        h20_max=float(params.get("h20_max", 0.33)),
        conf_min=float(params.get("conf_min", 0.55)),
        h5_reentry_min=float(params.get("h5_reentry_min", 0.55)),
        chip_data_fallback_max_stale_days=params.get("chip_data_fallback_max_stale_days", 10),
        risk_score_lookback_days=params.get("risk_score_lookback_days", 5),
        momentum_fast_exit_min=params.get("momentum_fast_exit_min", 0.10),
        momentum_fast_exit_ma_gap_min=params.get("momentum_fast_exit_ma_gap_min", -0.08),
        exclude_zero_volume_rows=bool(params.get("exclude_zero_volume_rows", False)),
    )
    joined = frame[["base_regime", "ma_gap", "drawdown"]].join(panel, how="inner")
    prices = _load_prices(db_path, TICKERS, start, end, exclude_zero_volume=bool(params.get("exclude_zero_volume_rows", False)))
    prices = prices.reindex(joined.index).dropna()
    joined = joined.loc[prices.index]

    stats = _confidence_stats(joined)
    corr = {
        "pearson_prob_up_h20_confidence": float(joined["prob_up_h20"].corr(joined["confidence"], method="pearson")),
        "spearman_prob_up_h20_confidence": float(joined["prob_up_h20"].corr(joined["confidence"], method="spearman")),
    }
    calibration = _bucket_calibration(joined)

    event_sets: dict[str, list[dict[str, Any]]] = {}
    for conf_min in [0.55, 0.50, 0.45, 0.40, 0.30]:
        event_sets[f"conf_min_{conf_min:.2f}"] = _event_overlay_rows(
            joined,
            prices,
            conf_min=conf_min,
            h20_max=float(params.get("h20_max", 0.33)),
            h5_reentry_min=float(params.get("h5_reentry_min", 0.55)),
            commission_rate=0.001425,
            slippage_rate=0.0005,
            equity_etf_sell_tax=0.001,
        )

    csv_rows = []
    for name, rows in event_sets.items():
        for row in rows:
            csv_rows.append({"event_set": name, **row})
    event_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(csv_rows).to_csv(event_csv, index=False, encoding="utf-8-sig")

    event_summary = {}
    for name, rows in event_sets.items():
        vals = [r["overlay_value_per_shifted_dollar_net_cost"] for r in rows]
        event_summary[name] = {
            "events": len(rows),
            "net_value_sum_per_shifted_dollar": float(sum(vals)) if vals else 0.0,
            "net_value_mean_per_shifted_dollar": float(np.mean(vals)) if vals else None,
            "positive_event_rate": float(np.mean([v > 0 for v in vals])) if vals else None,
            "events_detail_csv": str(event_csv),
        }

    plot_error = _plot_joint(joined, output_plot)
    return {
        "schema_version": 1,
        "report_type": "a2118_ncf_confidence_calibration",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "active_allocation_impact": "none",
        "panel": {
            "path": str(panel_path),
            "rows": int(len(joined)),
            "start": start,
            "end": end,
        },
        "confidence_definition": {
            "used_by_a2118": "panel-aligned prob_magnitude",
            "formula": "abs(ensemble_prob_up - 0.5) * 2",
            "not": [
                "not model agreement",
                "not model standard deviation",
                "not entropy",
                "not validation score",
            ],
        },
        "confidence_distribution": stats,
        "prob_up_h20_confidence_correlation": corr,
        "confidence_bucket_calibration": calibration,
        "event_overlay_value": {
            "definition": "PnL of moving one shifted dollar from 00631L to 0050 from trigger close to H5 reentry close, minus round-trip sell/buy costs, compared with holding 00631L.",
            "h20_max": float(params.get("h20_max", 0.33)),
            "h5_reentry_min": float(params.get("h5_reentry_min", 0.55)),
            "summary": event_summary,
            "csv": str(event_csv),
        },
        "joint_distribution_plot": {
            "path": str(output_plot),
            "error": plot_error,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--event-csv", default=str(DEFAULT_EVENT_CSV))
    parser.add_argument("--plot", default=str(DEFAULT_PLOT))
    args = parser.parse_args()

    report = build_report(
        manifest_path=Path(args.manifest),
        db_path=Path(args.db),
        output_plot=Path(args.plot),
        event_csv=Path(args.event_csv),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"A21.18 NCF confidence calibration: {output.resolve()}")
    print(f"A21.18 NCF event values: {Path(args.event_csv).resolve()}")
    print(f"A21.18 NCF joint plot: {Path(args.plot).resolve()}")


if __name__ == "__main__":
    main()
