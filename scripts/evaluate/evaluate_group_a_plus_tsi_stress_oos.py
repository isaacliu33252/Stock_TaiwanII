#!/usr/bin/env python3
"""Evaluate GroupA+ TSI stress shadow out of sample.

Research-only validation for arXiv:2608.10788. TSI is treated as a coincident
stress-state detector, not as a directional alpha signal.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.triadic_stress_index import (
    DEFAULT_ALPHA_DOWN,
    DEFAULT_ALPHA_UP,
    DEFAULT_MIN_OBSERVATIONS,
    DEFAULT_TICKER_SOURCES,
    DEFAULT_WINDOW_DAYS,
    load_tsi_price_panel,
    rolling_tsi_frame,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/tsi_stress_oos.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/tsi_stress_oos.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/tsi_stress_oos/history"
DEFAULT_THRESHOLDS = (0.80, 0.85, 0.90, 0.95)
DEFAULT_HORIZONS = (5, 10, 20)
DEFAULT_TARGET_TICKERS = ("0050.TW", "00631L.TW")
DEFAULT_WINDOWS = (
    {"name": "taiwan_2020_covid_crash", "start": "2020-01-02", "end": "2020-06-30", "type": "crash_window"},
    {"name": "taiwan_2022_rate_hike_stress", "start": "2022-01-03", "end": "2022-10-31", "type": "stress_window"},
    {"name": "taiwan_2026_q1q2_stress", "start": "2026-02-02", "end": "2026-04-30", "type": "stress_window"},
    {"name": "taiwan_2026_recent", "start": "2026-05-15", "end": "2026-08-21", "type": "recent_window"},
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _window_mask(index: pd.DatetimeIndex, windows: list[dict[str, str]]) -> pd.Series:
    mask = pd.Series(False, index=index)
    for item in windows:
        mask |= (index >= pd.Timestamp(item["start"])) & (index <= pd.Timestamp(item["end"]))
    return mask


def _future_path_metrics(prices: pd.Series, dt: pd.Timestamp, horizon: int) -> dict[str, float | None]:
    clean = prices.replace([np.inf, -np.inf], np.nan).dropna().sort_index()
    if clean.empty:
        return {"return": None, "max_drawdown": None}
    entry_idx = clean.index.searchsorted(dt, side="right") - 1
    if entry_idx < 0 or entry_idx + horizon >= len(clean):
        return {"return": None, "max_drawdown": None}
    path = clean.iloc[entry_idx : entry_idx + horizon + 1]
    entry = float(path.iloc[0])
    if entry <= 0.0:
        return {"return": None, "max_drawdown": None}
    ret = float(path.iloc[-1] / entry - 1.0)
    curve = path / entry
    drawdown = curve / curve.cummax() - 1.0
    return {"return": ret, "max_drawdown": float(drawdown.min())}


def build_daily_scores(
    prices: pd.DataFrame,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    alpha_up: float = DEFAULT_ALPHA_UP,
    alpha_down: float = DEFAULT_ALPHA_DOWN,
) -> pd.DataFrame:
    frame, _metrics = rolling_tsi_frame(
        prices,
        window_days=window_days,
        min_observations=min_observations,
        alpha_up=alpha_up,
        alpha_down=alpha_down,
    )
    if frame.empty:
        return frame
    out = frame.reset_index().rename(columns={"index": "dt", "date": "dt"})
    out["dt"] = pd.to_datetime(out["dt"])
    return out


def _forward_summary_fixed(
    scores: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    alert: pd.Series,
    horizons: tuple[int, ...],
    target_tickers: tuple[str, ...],
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    alert = alert.reindex(scores.index).fillna(False).astype(bool)
    for ticker in target_tickers:
        if ticker not in prices:
            summary[ticker] = {"status": "missing_price_series"}
            continue
        ticker_summary: dict[str, Any] = {}
        for horizon in horizons:
            buckets = {
                "alert_return": [],
                "quiet_return": [],
                "alert_dd": [],
                "quiet_dd": [],
            }
            for idx, row in scores.iterrows():
                metrics = _future_path_metrics(prices[ticker], pd.Timestamp(row["dt"]), horizon)
                if metrics["return"] is None or metrics["max_drawdown"] is None:
                    continue
                prefix = "alert" if bool(alert.loc[idx]) else "quiet"
                buckets[f"{prefix}_return"].append(float(metrics["return"]))
                buckets[f"{prefix}_dd"].append(float(metrics["max_drawdown"]))
            ticker_summary[f"{horizon}d"] = {
                "alert_avg_return": _float_or_none(np.mean(buckets["alert_return"])) if buckets["alert_return"] else None,
                "quiet_avg_return": _float_or_none(np.mean(buckets["quiet_return"])) if buckets["quiet_return"] else None,
                "alert_avg_max_drawdown": _float_or_none(np.mean(buckets["alert_dd"])) if buckets["alert_dd"] else None,
                "quiet_avg_max_drawdown": _float_or_none(np.mean(buckets["quiet_dd"])) if buckets["quiet_dd"] else None,
                "alert_samples": len(buckets["alert_return"]),
                "quiet_samples": len(buckets["quiet_return"]),
            }
        summary[ticker] = ticker_summary
    return summary


def _threshold_summary(
    scores: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    windows: list[dict[str, str]],
    threshold: float,
    horizons: tuple[int, ...],
    target_tickers: tuple[str, ...],
) -> dict[str, Any]:
    valid = scores.dropna(subset=["tsi_memory_percentile"]).copy()
    if valid.empty:
        return {"threshold": threshold, "status": "no_valid_scores"}
    alert = valid["tsi_memory_percentile"].astype(float) >= threshold
    stress = _window_mask(pd.DatetimeIndex(valid["dt"]), windows).reset_index(drop=True)
    stress.index = valid.index
    stress_alert_rate = float(alert[stress].mean()) if bool(stress.any()) else None
    non_stress_alert_rate = float(alert[~stress].mean()) if bool((~stress).any()) else None
    forward = _forward_summary_fixed(
        valid,
        prices,
        alert=alert,
        horizons=horizons,
        target_tickers=target_tickers,
    )
    return {
        "threshold": float(threshold),
        "status": "available",
        "alert_days": int(alert.sum()),
        "total_days": int(len(valid)),
        "alert_rate": float(alert.mean()),
        "stress_window_days": int(stress.sum()),
        "non_window_days": int((~stress).sum()),
        "stress_window_alert_rate": _float_or_none(stress_alert_rate),
        "non_window_alert_rate": _float_or_none(non_stress_alert_rate),
        "forward_outcomes": forward,
    }


def _window_summary(scores: pd.DataFrame, windows: list[dict[str, str]], threshold: float) -> list[dict[str, Any]]:
    out = []
    for item in windows:
        start = pd.Timestamp(item["start"])
        end = pd.Timestamp(item["end"])
        subset = scores[(scores["dt"] >= start) & (scores["dt"] <= end)].copy()
        if subset.empty:
            out.append({**item, "status": "no_data", "available_days": 0})
            continue
        alert = subset["tsi_memory_percentile"].astype(float) >= threshold
        out.append(
            {
                **item,
                "status": "available",
                "available_days": int(len(subset)),
                "alert_days_at_primary_threshold": int(alert.sum()),
                "alert_rate_at_primary_threshold": _float_or_none(alert.mean()),
                "tsi_memory_percentile_max": _float_or_none(subset["tsi_memory_percentile"].max()),
                "tsi_memory_percentile_mean": _float_or_none(subset["tsi_memory_percentile"].mean()),
                "top_days": [
                    {
                        "dt": str(pd.Timestamp(row.dt).date()),
                        "tsi_memory_percentile": _float_or_none(row.tsi_memory_percentile),
                        "tsi_memory": _float_or_none(row.tsi_memory),
                        "tsi": _float_or_none(row.tsi),
                    }
                    for row in subset.sort_values("tsi_memory_percentile", ascending=False).head(5).itertuples(index=False)
                ],
            }
        )
    return out


def build_oos_report(
    *,
    prices: pd.DataFrame,
    as_of: str,
    start: str,
    end: str,
    windows: list[dict[str, str]] | None = None,
    thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    target_tickers: tuple[str, ...] = DEFAULT_TARGET_TICKERS,
    window_days: int = DEFAULT_WINDOW_DAYS,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    alpha_up: float = DEFAULT_ALPHA_UP,
    alpha_down: float = DEFAULT_ALPHA_DOWN,
    primary_threshold: float = 0.90,
) -> dict[str, Any]:
    windows = windows or list(DEFAULT_WINDOWS)
    clipped = prices.loc[pd.Timestamp(start) : pd.Timestamp(end)]
    scores = build_daily_scores(
        clipped,
        window_days=window_days,
        min_observations=min_observations,
        alpha_up=alpha_up,
        alpha_down=alpha_down,
    )
    if scores.empty:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_tsi_stress_oos",
            "status": "blocked",
            "as_of": as_of,
            "policy": "research_only_tsi_stress_oos_no_weight_change",
            "blocking_reasons": ["tsi_daily_scores_unavailable"],
            "decision": _decision(False),
        }
    threshold_summaries = [
        _threshold_summary(
            scores,
            clipped,
            windows=windows,
            threshold=threshold,
            horizons=horizons,
            target_tickers=target_tickers,
        )
        for threshold in thresholds
    ]
    primary = min(threshold_summaries, key=lambda item: abs(float(item["threshold"]) - primary_threshold))
    stress_rate = primary.get("stress_window_alert_rate")
    non_rate = primary.get("non_window_alert_rate")
    blockers = [
        "research_only_coincident_stress_index",
        "no_live_weight_change_allowed",
        "requires_daily_shadow_monitoring_before_promotion",
    ]
    if stress_rate is None or non_rate is None or stress_rate <= non_rate:
        blockers.append("stress_window_alert_rate_not_above_non_window_rate")
    if primary.get("alert_days", 0) < 20:
        blockers.append("too_few_alert_samples_for_promotion")
    latest = scores.iloc[-1].to_dict()
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_tsi_stress_oos",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_start": str(pd.Timestamp(scores["dt"].min()).date()),
        "actual_data_end": str(pd.Timestamp(scores["dt"].max()).date()),
        "paper": "2608.10788",
        "paper_title": "The Triadic Stress Index in Financial Markets",
        "status": "research_only",
        "policy": "research_only_tsi_stress_oos_no_weight_change",
        "method": {
            "window_days": int(window_days),
            "min_observations": int(min_observations),
            "alpha_up": float(alpha_up),
            "alpha_down": float(alpha_down),
            "primary_threshold": float(primary_threshold),
            "thresholds": [float(item) for item in thresholds],
            "horizons": [int(item) for item in horizons],
            "target_tickers": list(target_tickers),
        },
        "latest": {k: _float_or_none(v) if k != "dt" else str(pd.Timestamp(v).date()) for k, v in latest.items()},
        "windows": _window_summary(scores, windows, primary_threshold),
        "threshold_summaries": threshold_summaries,
        "blocking_reasons": sorted(set(blockers)),
        "decision": _decision(False),
    }


def _decision(promotion_allowed: bool) -> dict[str, bool]:
    return {
        "promotion_allowed": bool(promotion_allowed),
        "target_weight_change_allowed": False,
        "auto_rebalance_allowed": False,
        "allow_00631l_add": False,
        "allow_00632r_open": False,
        "keep_golden1_0531_unchanged": True,
    }


def write_report(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(payload), encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = str(payload.get("as_of") or payload.get("actual_data_end") or date.today().isoformat()).replace("-", "")
    history_path = history_dir / f"tsi_stress_oos_{stamp}.json"
    history_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _markdown(payload: dict[str, Any]) -> str:
    primary_threshold = (payload.get("method") or {}).get("primary_threshold")
    rows = []
    for item in payload.get("threshold_summaries") or []:
        rows.append(
            "| {threshold:.2f} | {alert_days} | {stress} | {non} |".format(
                threshold=float(item.get("threshold") or 0.0),
                alert_days=int(item.get("alert_days") or 0),
                stress="-"
                if item.get("stress_window_alert_rate") is None
                else f"{float(item['stress_window_alert_rate']):.2%}",
                non="-"
                if item.get("non_window_alert_rate") is None
                else f"{float(item['non_window_alert_rate']):.2%}",
            )
        )
    window_rows = []
    for item in payload.get("windows") or []:
        window_rows.append(
            "| {name} | {days} | {rate} | {max_pct} |".format(
                name=item.get("name"),
                days=int(item.get("available_days") or 0),
                rate="-"
                if item.get("alert_rate_at_primary_threshold") is None
                else f"{float(item['alert_rate_at_primary_threshold']):.2%}",
                max_pct="-"
                if item.get("tsi_memory_percentile_max") is None
                else f"{float(item['tsi_memory_percentile_max']):.2%}",
            )
        )
    forward_rows = []
    primary = min(
        payload.get("threshold_summaries") or [],
        key=lambda item: abs(float(item.get("threshold", 0.0)) - float(primary_threshold or 0.0)),
        default={},
    )
    for ticker, outcomes in (primary.get("forward_outcomes") or {}).items():
        if not isinstance(outcomes, dict):
            continue
        item = outcomes.get("20d") or {}
        if not item:
            continue
        forward_rows.append(
            "| {ticker} | {alert_ret} | {quiet_ret} | {alert_dd} | {quiet_dd} | {samples} |".format(
                ticker=ticker,
                alert_ret="-"
                if item.get("alert_avg_return") is None
                else f"{float(item['alert_avg_return']):.2%}",
                quiet_ret="-"
                if item.get("quiet_avg_return") is None
                else f"{float(item['quiet_avg_return']):.2%}",
                alert_dd="-"
                if item.get("alert_avg_max_drawdown") is None
                else f"{float(item['alert_avg_max_drawdown']):.2%}",
                quiet_dd="-"
                if item.get("quiet_avg_max_drawdown") is None
                else f"{float(item['quiet_avg_max_drawdown']):.2%}",
                samples=f"{int(item.get('alert_samples') or 0)}/{int(item.get('quiet_samples') or 0)}",
            )
        )
    return """# GroupA+ TSI Stress OOS

- status: `{status}`
- as_of: `{as_of}`
- actual_data: `{start}` to `{end}`
- policy: `{policy}`
- primary_threshold: `{primary}`
- promotion_allowed: `{promotion}`
- target_weight_change_allowed: `{weight_change}`

## Threshold Sweep

| threshold | alert_days | stress_window_alert_rate | non_window_alert_rate |
|---:|---:|---:|---:|
{rows}

## Stress Windows

| window | days | alert_rate_at_primary_threshold | max_tsi_memory_percentile |
|---|---:|---:|---:|
{window_rows}

## 20D Forward Outcome

Primary threshold only. Samples are alert/quiet.

| ticker | alert_avg_return | quiet_avg_return | alert_avg_max_drawdown | quiet_avg_max_drawdown | samples |
|---|---:|---:|---:|---:|---:|
{forward_rows}

## Governance

TSI remains research-only. The paper frames it as a coincident stress-state
index, not a forecast. Golden1_0531 and latest strategy weights remain
unchanged.
""".format(
        status=payload.get("status"),
        as_of=payload.get("as_of"),
        start=payload.get("actual_data_start"),
        end=payload.get("actual_data_end"),
        policy=payload.get("policy"),
        primary=primary_threshold,
        promotion=payload.get("decision", {}).get("promotion_allowed"),
        weight_change=payload.get("decision", {}).get("target_weight_change_allowed"),
        rows="\n".join(rows) if rows else "| - | - | - | - |",
        window_rows="\n".join(window_rows) if window_rows else "| - | - | - | - |",
        forward_rows="\n".join(forward_rows) if forward_rows else "| - | - | - | - | - |",
    )


def main() -> None:
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--start", default=(today - timedelta(days=365 * 6)).isoformat())
    parser.add_argument("--end", default=today.isoformat())
    parser.add_argument("--as-of", default=today.isoformat())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    prices, _source_status = load_tsi_price_panel(
        db_path=_resolve(args.db),
        start=args.start,
        end=args.end,
        ticker_sources=DEFAULT_TICKER_SOURCES,
    )
    payload = build_oos_report(
        prices=prices,
        as_of=args.as_of,
        start=args.start,
        end=args.end,
    )
    write_report(
        payload,
        _resolve(args.output),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    primary = min(
        payload.get("threshold_summaries") or [],
        key=lambda item: abs(float(item.get("threshold", 0.0)) - 0.90),
        default={},
    )
    print(f"TSI OOS: status={payload.get('status')} output={_resolve(args.output)}")
    print(
        json.dumps(
            {
                "stress_window_alert_rate": primary.get("stress_window_alert_rate"),
                "non_window_alert_rate": primary.get("non_window_alert_rate"),
                "promotion_allowed": payload.get("decision", {}).get("promotion_allowed"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
