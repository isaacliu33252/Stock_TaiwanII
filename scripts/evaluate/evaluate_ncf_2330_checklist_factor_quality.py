#!/usr/bin/env python3
"""Evaluate which ncf_2330 checklist layers have predictive value.

This is research-only. It rebuilds the TSMC checklist point-in-time for each
historical date, converts layer signals/values into factor series, and compares
them with future 2330.TW returns and forward drawdown.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.report.build_ncf_2330_checklist import (  # noqa: E402
    DEFAULT_DB,
    RESULTS_DIR,
    build_checklist,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / f"ncf_2330_checklist_factor_quality_{datetime.now().strftime('%Y%m%d')}.json"
SIGNAL_SCORE = {"bullish": 1.0, "neutral": 0.0, "bearish": -1.0}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _load_2330_close(db_path: Path, start: str, end: str) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, close
            FROM external_market_ohlcv
            WHERE provider = 'yfinance'
              AND ticker = '2330.TW'
              AND dt BETWEEN ? AND ?
              AND close IS NOT NULL
            ORDER BY dt
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No 2330.TW external_market_ohlcv rows between {start} and {end}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    return rows.set_index("dt")["close"].astype(float).sort_index()


def _forward_return(close: pd.Series, horizon: int) -> pd.Series:
    return close.shift(-horizon) / close - 1.0


def _forward_mdd(close: pd.Series, horizon: int) -> pd.Series:
    values = []
    arr = close.to_numpy(dtype=float)
    for i, current in enumerate(arr):
        end = min(i + horizon, len(arr) - 1)
        if i >= end or current <= 0:
            values.append(np.nan)
            continue
        future_min = np.nanmin(arr[i + 1 : end + 1])
        values.append(float(future_min / current - 1.0))
    return pd.Series(values, index=close.index, name=f"forward_mdd_h{horizon}")


def _spearman(x: pd.Series, y: pd.Series) -> float | None:
    frame = pd.concat([x, y], axis=1).dropna()
    if len(frame) < 10:
        return None
    if frame.iloc[:, 0].nunique() < 2 or frame.iloc[:, 1].nunique() < 2:
        return None
    rho = frame.iloc[:, 0].corr(frame.iloc[:, 1], method="spearman")
    return float(rho) if pd.notna(rho) and math.isfinite(float(rho)) else None


def _series_summary(series: pd.Series) -> dict[str, Any]:
    valid = series.dropna()
    if valid.empty:
        return {"coverage": 0.0, "count": 0}
    return {
        "coverage": round(float(len(valid) / len(series)), 6),
        "count": int(len(valid)),
        "mean": round(float(valid.mean()), 6),
        "std": round(float(valid.std(ddof=0)), 6),
        "min": round(float(valid.min()), 6),
        "max": round(float(valid.max()), 6),
    }


def _extract_factors(report: dict[str, Any]) -> dict[str, float | None]:
    factors: dict[str, float | None] = {
        "overall_layer_score": _as_float(report.get("available_layer_score")),
        "available_layer_count": _as_float(report.get("available_layer_count")),
    }
    layers = report.get("layers") or {}
    for layer_name, layer in layers.items():
        if not isinstance(layer, dict):
            continue
        status = str(layer.get("status") or "")
        signal = str(layer.get("signal") or "neutral")
        prefix = f"{layer_name}."
        factors[prefix + "signal_score"] = (
            SIGNAL_SCORE.get(signal)
            if status != "missing_source"
            else None
        )
        factors[prefix + "available"] = 0.0 if status == "missing_source" else 1.0
        values = layer.get("values") or {}
        if not isinstance(values, dict):
            continue
        for key, value in values.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    factors[f"{prefix}{key}.{sub_key}"] = _as_float(sub_value)
            elif isinstance(value, list):
                continue
            else:
                factors[prefix + key] = _as_float(value)
    return factors


def build_factor_frame(
    dates: pd.DatetimeIndex,
    *,
    db_path: Path,
    results_dir: Path,
    project_root: Path,
    mode: str,
    include_latest_ncf_snapshot: bool = False,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for dt in dates:
        report = build_checklist(
            db_path=db_path,
            results_dir=results_dir,
            project_root=project_root,
            mode=mode,
            as_of=str(pd.Timestamp(dt).date()),
        )
        row = {"date": pd.Timestamp(dt).normalize()}
        factors = _extract_factors(report)
        if not include_latest_ncf_snapshot:
            factors = {k: v for k, v in factors.items() if not k.startswith("ncf_2330.")}
        row.update(factors)
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("date").sort_index()


def evaluate_factors(
    factor_frame: pd.DataFrame,
    close: pd.Series,
    *,
    horizons: tuple[int, ...],
    mdd_horizon: int,
    mdd_threshold: float,
) -> dict[str, Any]:
    targets: dict[str, pd.Series] = {}
    for horizon in horizons:
        targets[f"return_h{horizon}"] = _forward_return(close, horizon).reindex(factor_frame.index)
    targets[f"mdd_h{mdd_horizon}"] = _forward_mdd(close, mdd_horizon).reindex(factor_frame.index)
    targets[f"tail_event_h{mdd_horizon}"] = (
        (targets[f"mdd_h{mdd_horizon}"] <= -abs(mdd_threshold)).astype(float)
    )

    out: dict[str, Any] = {}
    for factor in factor_frame.columns:
        series = factor_frame[factor].astype(float)
        summary = _series_summary(series)
        if summary["count"] < 10 or series.dropna().nunique() < 2:
            out[factor] = {**summary, "usable": False, "reason": "insufficient_variation_or_coverage"}
            continue
        metrics: dict[str, Any] = {**summary, "usable": True}
        for name, target in targets.items():
            rho = _spearman(series, target)
            metrics[f"ic_{name}"] = round(float(rho), 6) if rho is not None else None
        for horizon in horizons:
            ret = targets[f"return_h{horizon}"]
            joined = pd.concat([series.rename("factor"), ret.rename("ret")], axis=1).dropna()
            if len(joined) >= 10:
                pos = joined[joined["factor"] > 0]
                neg = joined[joined["factor"] < 0]
                metrics[f"win_rate_when_positive_h{horizon}"] = (
                    round(float((pos["ret"] > 0).mean()), 6) if len(pos) else None
                )
                metrics[f"mean_return_when_positive_h{horizon}"] = (
                    round(float(pos["ret"].mean()), 6) if len(pos) else None
                )
                metrics[f"mean_return_when_negative_h{horizon}"] = (
                    round(float(neg["ret"].mean()), 6) if len(neg) else None
                )
        tail = targets[f"tail_event_h{mdd_horizon}"]
        joined_tail = pd.concat([series.rename("factor"), tail.rename("tail")], axis=1).dropna()
        if len(joined_tail) >= 10:
            pos = joined_tail[joined_tail["factor"] > 0]
            neg = joined_tail[joined_tail["factor"] < 0]
            metrics[f"tail_rate_when_positive_h{mdd_horizon}"] = (
                round(float(pos["tail"].mean()), 6) if len(pos) else None
            )
            metrics[f"tail_rate_when_negative_h{mdd_horizon}"] = (
                round(float(neg["tail"].mean()), 6) if len(neg) else None
            )
        out[factor] = metrics
    return out


def _top_factors(results: dict[str, Any], target: str, limit: int = 15) -> list[dict[str, Any]]:
    rows = []
    key = f"ic_{target}"
    for name, metrics in results.items():
        value = metrics.get(key)
        if value is None:
            continue
        rows.append({
            "factor": name,
            "ic": value,
            "abs_ic": abs(float(value)),
            "coverage": metrics.get("coverage"),
            "count": metrics.get("count"),
        })
    rows.sort(key=lambda item: item["abs_ic"], reverse=True)
    return rows[:limit]


def parse_horizons(value: str) -> tuple[int, ...]:
    horizons = tuple(int(part.strip()) for part in value.split(",") if part.strip())
    if not horizons:
        raise ValueError("At least one horizon is required")
    return horizons


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--horizons", default="5,20")
    parser.add_argument("--mdd-horizon", type=int, default=20)
    parser.add_argument("--mdd-threshold", type=float, default=0.05)
    parser.add_argument(
        "--include-latest-ncf-snapshot",
        action="store_true",
        help="Include ncf_2330 JSON fields even though they are latest-snapshot, not historical point-in-time.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    close_end = datetime.now().strftime("%Y-%m-%d") if args.end == "latest" else args.end
    close = _load_2330_close(args.db_path, args.start, close_end)
    eval_close = close if args.end == "latest" else close.loc[: pd.Timestamp(args.end)]
    eval_dates = eval_close.loc[pd.Timestamp(args.start) :].index
    max_horizon = max(*parse_horizons(args.horizons), int(args.mdd_horizon))
    if len(eval_dates) > max_horizon:
        eval_dates = eval_dates[:-max_horizon]
    factor_frame = build_factor_frame(
        pd.DatetimeIndex(eval_dates),
        db_path=args.db_path,
        results_dir=args.results_dir,
        project_root=args.project_root,
        mode=args.mode,
        include_latest_ncf_snapshot=bool(args.include_latest_ncf_snapshot),
    )
    horizons = parse_horizons(args.horizons)
    results = evaluate_factors(
        factor_frame,
        close,
        horizons=horizons,
        mdd_horizon=int(args.mdd_horizon),
        mdd_threshold=float(args.mdd_threshold),
    )
    report = {
        "schema_version": 1,
        "report": "ncf_2330_checklist_factor_quality",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_weight_change",
        "method_note": (
            "Point-in-time rebuild of ncf_2330 checklist layers. IC is Spearman "
            "correlation between checklist factor values and subsequent 2330.TW outcomes."
        ),
        "include_latest_ncf_snapshot": bool(args.include_latest_ncf_snapshot),
        "window": {
            "start": str(pd.Timestamp(eval_dates.min()).date()) if len(eval_dates) else None,
            "end": str(pd.Timestamp(eval_dates.max()).date()) if len(eval_dates) else None,
            "rows": int(len(eval_dates)),
        },
        "horizons": list(horizons),
        "mdd_horizon": int(args.mdd_horizon),
        "mdd_threshold": float(args.mdd_threshold),
        "factor_count": int(len(factor_frame.columns)),
        "top_by_return_h5": _top_factors(results, "return_h5") if 5 in horizons else [],
        "top_by_return_h20": _top_factors(results, "return_h20") if 20 in horizons else [],
        "top_by_mdd": _top_factors(results, f"mdd_h{int(args.mdd_horizon)}"),
        "top_by_tail_event": _top_factors(results, f"tail_event_h{int(args.mdd_horizon)}"),
        "factors": results,
    }
    output = args.output
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved: {output}")
    print(
        f"window={report['window']['start']}~{report['window']['end']} "
        f"rows={report['window']['rows']} factors={report['factor_count']}"
    )


if __name__ == "__main__":
    main()
