#!/usr/bin/env python3
"""Log live-forward observations for the 2410.00288 weak NCF00631L no-add gate.

Research-only. This records whether the best weak shadow gate
(`realized_var_20_top25_and_weak_ncf`) would have fired on the latest live
NCF00631L row. It never blocks orders, changes target weights, or edits
strategy/golden artifacts.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402

BASE_SCRIPT = PROJECT_ROOT / "scripts/evaluate/evaluate_group_a_plus_2410_00288_ginn_ncf00631l_shadow.py"
DEFAULT_PANEL = PROJECT_ROOT / "results/ncf_00631l_panel_latest_20260907.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2410_00288_ginn_no_add_forward_shadow.json"
DEFAULT_LOG = PROJECT_ROOT / "results/2410_00288_ginn_no_add_forward_shadow_log.jsonl"


def _load_base_module():
    spec = importlib.util.spec_from_file_location("ginn_ncf00631l_shadow", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = _load_base_module()


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _latest_live_row(panel_path: Path) -> pd.Series:
    panel = pd.read_csv(panel_path, encoding="utf-8-sig")
    if "date" not in panel.columns:
        raise ValueError("panel is missing date column")
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce").dt.normalize()
    panel = panel.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if "is_live" in panel.columns:
        live = panel[panel["is_live"].astype(bool)].copy()
    else:
        live = panel.copy()
    if live.empty:
        raise ValueError("panel has no live rows")
    return live.iloc[-1]


def _threshold_from_realized_rows(panel_path: Path, db_path: Path, ticker: str, feature: str, quantile: float) -> tuple[float, int]:
    frame, _ = BASE._load_model_frame(panel_path, db_path, ticker)
    realized = frame.dropna(subset=["actual_up_h20", feature]).copy()
    bullish = realized[
        (pd.to_numeric(realized["baseline_prob_up_h20"], errors="coerce") >= 0.55)
        & (pd.to_numeric(realized["confidence"], errors="coerce") >= 0.10)
    ]
    if bullish.empty:
        raise ValueError("no realized bullish rows for threshold")
    return float(pd.to_numeric(bullish[feature], errors="coerce").quantile(quantile)), int(len(bullish))


def build_snapshot(
    panel_path: Path,
    db_path: Path,
    *,
    ticker: str,
    bullish_prob_min: float,
    weak_prob_max: float,
    confidence_min: float,
) -> dict[str, Any]:
    live_row = _latest_live_row(panel_path)
    signal_date = str(pd.Timestamp(live_row["date"]).date())
    panel = pd.read_csv(panel_path, encoding="utf-8-sig")
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce").dt.normalize()
    panel = panel.dropna(subset=["date"]).sort_values("date")
    close_start = str((panel["date"].min() - pd.Timedelta(days=1000)).date())
    close = BASE._load_close(db_path, ticker, close_start, signal_date)
    returns = close.pct_change().dropna()
    vol = BASE._base_vol_features(returns)
    garch = BASE._fit_fold_garch_features(returns.tail(756), returns)
    latest_dt = min(pd.Timestamp(signal_date), vol.index.max())
    vol_row = vol.loc[latest_dt]
    garch_row = garch.loc[latest_dt]
    threshold, threshold_rows = _threshold_from_realized_rows(panel_path, db_path, ticker, "realized_var_20", 0.75)
    prob_h20 = float(live_row.get("prob_up_h20"))
    ensemble_prob = float(live_row.get("ensemble_prob_up"))
    confidence = float(live_row.get("confidence"))
    realized_var_20 = float(vol_row["realized_var_20"])
    is_bullish = prob_h20 >= bullish_prob_min and confidence >= confidence_min
    is_weak_bull = bullish_prob_min <= prob_h20 <= weak_prob_max
    is_high_realized_var = realized_var_20 >= threshold
    would_trigger = bool(is_bullish and is_weak_bull and is_high_realized_var)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2410_00288_ginn_no_add_forward_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2410.00288",
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "gate": "realized_var_20_top25_and_weak_ncf",
        "ticker": ticker,
        "signal_date": signal_date,
        "volatility_feature_date": str(latest_dt.date()),
        "inputs": {
            "panel": str(panel_path),
            "db_path": str(db_path),
            "bullish_prob_min": bullish_prob_min,
            "weak_prob_max": weak_prob_max,
            "confidence_min": confidence_min,
            "realized_var_20_threshold_quantile": 0.75,
            "threshold_realized_bullish_rows": threshold_rows,
        },
        "latest_signal": {
            "prob_up_h20": prob_h20,
            "ensemble_prob_up": ensemble_prob,
            "direction": live_row.get("direction"),
            "h20_direction": live_row.get("h20_direction"),
            "confidence": confidence,
        },
        "latest_volatility": {
            "realized_var_20": realized_var_20,
            "realized_var_20_threshold": threshold,
            "realized_vol_ratio_20_60": None
            if pd.isna(vol_row.get("realized_vol_ratio_20_60"))
            else float(vol_row["realized_vol_ratio_20_60"]),
            "vol_cluster_score": None
            if pd.isna(vol_row.get("vol_cluster_score"))
            else float(vol_row["vol_cluster_score"]),
            "garch_sym_var": None if pd.isna(garch_row.get("garch_sym_var")) else float(garch_row["garch_sym_var"]),
            "garch_gjr_var": None if pd.isna(garch_row.get("garch_gjr_var")) else float(garch_row["garch_gjr_var"]),
            "garch_gjr_over_sym": None
            if pd.isna(garch_row.get("garch_gjr_over_sym"))
            else float(garch_row["garch_gjr_over_sym"]),
        },
        "gate_state": {
            "is_bullish": bool(is_bullish),
            "is_weak_bull": bool(is_weak_bull),
            "is_high_realized_var_20": bool(is_high_realized_var),
            "would_trigger_shadow_no_add": would_trigger,
            "production_action": "none",
            "target_weight_change_allowed": False,
        },
        "forward_label_pending": {
            "h20_label_date_available_after": str((pd.Timestamp(signal_date) + pd.Timedelta(days=35)).date()),
            "actual_up_h20": None,
            "forward_gain_h20": None,
            "forward_mdd_h20": None,
            "actual_fwd_mdd_gt5_h20": None,
        },
    }


def append_log(log_path: Path, snapshot: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("signal_date") != snapshot.get("signal_date") or row.get("gate") != snapshot.get("gate"):
                rows.append(row)
    rows.append(snapshot)
    rows.sort(key=lambda item: str(item.get("signal_date") or ""))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--ticker", default="00631L.TW")
    parser.add_argument("--bullish-prob-min", type=float, default=0.55)
    parser.add_argument("--weak-prob-max", type=float, default=0.65)
    parser.add_argument("--confidence-min", type=float, default=0.10)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--no-log", action="store_true")
    args = parser.parse_args()

    snapshot = build_snapshot(
        _resolve(args.panel),
        _resolve(args.db),
        ticker=args.ticker,
        bullish_prob_min=args.bullish_prob_min,
        weak_prob_max=args.weak_prob_max,
        confidence_min=args.confidence_min,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.no_log:
        append_log(_resolve(args.log), snapshot)
    print(f"signal_date={snapshot['signal_date']}")
    print(f"would_trigger_shadow_no_add={snapshot['gate_state']['would_trigger_shadow_no_add']}")
    print(f"production_action={snapshot['gate_state']['production_action']}")
    print(f"Output: {output}")
    print(f"Log: {_resolve(args.log) if not args.no_log else 'disabled'}")


if __name__ == "__main__":
    main()
