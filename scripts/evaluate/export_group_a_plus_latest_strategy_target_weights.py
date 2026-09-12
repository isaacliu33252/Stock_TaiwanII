#!/usr/bin/env python3
"""Export latest strategy historical target weights.

The latest Group A+ runner already emits an execution_regime series plus a
regime-to-weight map. This exporter expands those into a daily target-weight
table for trade-level shadow replay. It is research-only and creates no orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.runners.latest import run_latest


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "report/group_a_plus/latest/latest_strategy_historical_target_weights.json"
DEFAULT_OUTPUT_CSV = PROJECT_ROOT / "report/group_a_plus/latest/latest_strategy_historical_target_weights.csv"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/latest_strategy_historical_target_weights/history"
TARGET_ASSETS = ("0050", "00631L", "00632R", "00679B", "cash")
TICKER_ALIASES = {
    "0050.TW": "0050",
    "00631L.TW": "00631L",
    "00632R.TW": "00632R",
    "00679B.TWO": "00679B",
    "cash": "cash",
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _short_asset(raw: str) -> str:
    return TICKER_ALIASES.get(raw, raw.split(".", 1)[0])


def _normalize_weights(weights: dict[str, Any]) -> dict[str, float]:
    out = {asset: 0.0 for asset in TARGET_ASSETS}
    for raw, value in weights.items():
        asset = _short_asset(str(raw))
        if asset in out:
            out[asset] += float(value or 0.0)
    total = sum(v for v in out.values() if v > 0.0)
    if total <= 1e-12:
        return out
    return {asset: max(value, 0.0) / total for asset, value in out.items()}


def _resolve_latest_end(db_path: Path, requested_end: str, ticker: str = "0050.TW") -> str:
    if str(requested_end).lower() != "latest":
        return requested_end
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        max_dt = con.execute("SELECT MAX(dt) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()[0]
    finally:
        con.close()
    if max_dt is None:
        raise ValueError(f"No OHLCV rows found for {ticker}")
    return pd.Timestamp(max_dt).strftime("%Y-%m-%d")


def build_target_weight_export(
    *,
    latest_report: dict[str, Any],
    latest_frame: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame]:
    blockers: list[str] = []
    warnings: list[str] = []
    if latest_frame.empty:
        blockers.append("missing_latest_strategy_frame")
    if "execution_regime" not in latest_frame.columns:
        blockers.append("missing_execution_regime_column")
    regime_weights_raw = latest_report.get("base_weights") or latest_report.get("weights") or {}
    if not regime_weights_raw:
        blockers.append("missing_regime_weight_map")

    regime_weights = {
        str(regime): _normalize_weights(dict(weights or {}))
        for regime, weights in regime_weights_raw.items()
    }
    rows: list[dict[str, Any]] = []
    missing_regimes: set[str] = set()
    if not blockers:
        frame = latest_frame.copy()
        frame.index = pd.to_datetime(frame.index)
        for dt, row in frame.iterrows():
            regime = str(row.get("execution_regime"))
            weights = regime_weights.get(regime)
            if weights is None:
                missing_regimes.add(regime)
                weights = {asset: 0.0 for asset in TARGET_ASSETS}
            rows.append(
                {
                    "date": dt.strftime("%Y-%m-%d"),
                    "execution_regime": regime,
                    **{f"target_weight_{asset}": float(weights.get(asset, 0.0)) for asset in TARGET_ASSETS},
                }
            )
    if missing_regimes:
        blockers.append("missing_weights_for_execution_regimes")
    output_frame = pd.DataFrame(rows)
    if not output_frame.empty:
        sums = output_frame[[f"target_weight_{asset}" for asset in TARGET_ASSETS]].sum(axis=1)
        if bool((sums.sub(1.0).abs() > 1e-6).any()):
            warnings.append("some_target_weight_rows_do_not_sum_to_one")

    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_latest_strategy_historical_target_weights",
        "status": "blocked" if blockers else "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_latest_target_weight_export_no_weight_change",
        "active_strategy_id": latest_report.get("active_strategy_id") or latest_report.get("strategy"),
        "candidate_status": latest_report.get("candidate_status") or latest_report.get("status"),
        "target_assets": list(TARGET_ASSETS),
        "row_count": int(len(output_frame)),
        "date_window": (
            {}
            if output_frame.empty
            else {"start": str(output_frame["date"].iloc[0]), "end": str(output_frame["date"].iloc[-1])}
        ),
        "execution_regime_counts": (
            {} if output_frame.empty else output_frame["execution_regime"].value_counts().sort_index().to_dict()
        ),
        "regime_weight_map": regime_weights,
        "missing_execution_regimes": sorted(missing_regimes),
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "historical_target_weight_series_available": not blockers,
            "promotion_ready": False,
        },
    }
    return report, output_frame


def _write(
    *,
    report: dict[str, Any],
    frame: pd.DataFrame,
    output_json: Path,
    output_csv: Path,
    history_dir: Path | None,
) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    report = dict(report)
    report["csv_path"] = str(output_csv)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    frame.to_csv(output_csv, index=False, encoding="utf-8-sig")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        history_json = history_dir / f"latest_strategy_historical_target_weights_{stamp}.json"
        history_csv = history_dir / f"latest_strategy_historical_target_weights_{stamp}.csv"
        history_report = dict(report)
        history_report["csv_path"] = str(history_csv)
        history_json.write_text(
            json.dumps(history_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        frame.to_csv(history_csv, index=False, encoding="utf-8-sig")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-07-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = _resolve(args.db)
    resolved_end = _resolve_latest_end(db_path, args.end)
    latest_report, latest_frame = run_latest(args.start, resolved_end, args.initial_value, db_path)
    report, frame = build_target_weight_export(latest_report=latest_report, latest_frame=latest_frame)
    report["inputs"] = {
        "db": str(db_path),
        "start": args.start,
        "end": args.end,
        "resolved_end": resolved_end,
        "initial_value": args.initial_value,
    }
    _write(
        report=report,
        frame=frame,
        output_json=_resolve(args.output_json),
        output_csv=_resolve(args.output_csv),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "row_count": report["row_count"],
                "date_window": report["date_window"],
                "decision": report["decision"],
                "output_json": str(_resolve(args.output_json)),
                "output_csv": str(_resolve(args.output_csv)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
