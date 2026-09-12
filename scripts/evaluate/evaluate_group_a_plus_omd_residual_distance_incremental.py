#!/usr/bin/env python3
"""Check whether OMD residual distance adds risk information beyond simple baselines."""

from __future__ import annotations

import argparse
import json
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

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.omd_residual_distance_shadow import (
    DEFAULT_TICKERS,
    build_omd_residual_distance_score_frame,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/omd_residual_distance_incremental_review.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/omd_residual_distance_incremental_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/omd_residual_distance_incremental_review/history"
HORIZONS = (5, 20, 40)
BROAD_PROXY_TICKERS = (
    "0050.TW",
    "00631L.TW",
    "00632R.TW",
    "00679B.TWO",
    "2330.TW",
    "2317.TW",
    "2454.TW",
    "2308.TW",
    "2382.TW",
    "^TWII",
    "SOXX",
    "TSM",
    "QQQ",
    "^IXIC",
    "^GSPC",
    "^VIX",
    "TWD=X",
    "HYG",
    "SHY",
    "^N225",
    "^KS11",
    "^HSI",
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _float_or_none(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _load_close_panel(
    db_path: Path,
    tickers: tuple[str, ...],
    as_of: str | None,
    *,
    start: str | None = None,
) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    placeholders = ", ".join("?" for _ in tickers)
    tables: set[str]
    if as_of:
        as_of_clause = "AND dt <= ?"
    else:
        as_of_clause = ""
    start_clause = "AND dt >= ?" if start else ""
    with duckdb.connect(str(db_path), read_only=True) as conn:
        tables = {str(row[0]) for row in conn.execute("SHOW TABLES").fetchall()}
        frames: list[pd.DataFrame] = []
        for table, source_priority in (("ohlcv", 1), ("external_market_ohlcv", 0)):
            if table not in tables:
                continue
            params: list[Any] = list(tickers)
            if as_of:
                params.append(as_of)
            if start:
                params.append(start)
            frames.append(
                conn.execute(
                    f"""
                    SELECT ticker, dt, close, {source_priority} AS source_priority, '{table}' AS source_table
                    FROM {table}
                    WHERE ticker IN ({placeholders}) {as_of_clause} {start_clause}
                    ORDER BY dt, ticker
                    """,
                    params,
                ).fetchdf()
            )
    rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if rows.empty:
        return pd.DataFrame()
    rows = rows.dropna(subset=["ticker", "dt", "close"]).copy()
    rows["dt"] = pd.to_datetime(rows["dt"])
    rows = rows.sort_values(["dt", "ticker", "source_priority"]).drop_duplicates(["dt", "ticker"], keep="first")
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def _rolling_percentile(series: pd.Series, lookback: int, *, higher_is_riskier: bool = True) -> pd.Series:
    values: list[float | None] = []
    raw = pd.to_numeric(series, errors="coerce")
    for idx, value in enumerate(raw):
        start = max(0, idx - lookback + 1)
        hist = raw.iloc[start : idx + 1].dropna()
        if pd.isna(value) or hist.empty:
            values.append(None)
        elif higher_is_riskier:
            values.append(float((hist <= value).mean()))
        else:
            values.append(float((hist >= value).mean()))
    return pd.Series(values, index=series.index, dtype=float)


def _add_baseline_features(scores: pd.DataFrame, close: pd.DataFrame, target: str, percentile_lookback: int) -> pd.DataFrame:
    out = scores.copy()
    target_close = close[target].dropna().sort_index()
    target_ret = target_close.pct_change(fill_method=None)
    realized_vol_20 = target_ret.rolling(20, min_periods=10).std() * np.sqrt(252)
    drawdown_depth = target_close / target_close.rolling(252, min_periods=20).max() - 1.0
    drawdown_risk_depth = -drawdown_depth
    features = pd.DataFrame(
        {
            "dt": target_close.index,
            "realized_vol_20": realized_vol_20,
            "drawdown_depth": drawdown_depth,
            "drawdown_risk_depth": drawdown_risk_depth,
            "realized_vol_20_pct": _rolling_percentile(realized_vol_20, percentile_lookback),
            "drawdown_depth_pct": _rolling_percentile(drawdown_risk_depth, percentile_lookback),
        }
    ).reset_index(drop=True)
    out = out.merge(features, on="dt", how="left")
    return out


def _add_forward_outcomes(scores: pd.DataFrame, close: pd.DataFrame, target: str) -> pd.DataFrame:
    out = scores.copy()
    target_close = close[target].dropna().sort_index()
    full_dates = target_close.index
    close_values = target_close.to_numpy(dtype=float)
    pos_by_date = {date: idx for idx, date in enumerate(full_dates)}
    for horizon in HORIZONS:
        forward_returns: list[float | None] = []
        forward_max_drawdowns: list[float | None] = []
        for date in out["dt"]:
            idx = pos_by_date.get(pd.Timestamp(date))
            if idx is None or idx + horizon >= len(close_values):
                forward_returns.append(None)
                forward_max_drawdowns.append(None)
                continue
            base = close_values[idx]
            future = close_values[idx + 1 : idx + horizon + 1]
            if not np.isfinite(base) or base <= 0 or len(future) < horizon or not np.all(np.isfinite(future)):
                forward_returns.append(None)
                forward_max_drawdowns.append(None)
                continue
            forward_returns.append(float(future[-1] / base - 1.0))
            forward_max_drawdowns.append(float(np.min(future / base - 1.0)))
        out[f"fwd_return_h{horizon}"] = forward_returns
        out[f"fwd_max_drawdown_h{horizon}"] = forward_max_drawdowns
    return out


def _classifier_metrics(frame: pd.DataFrame, signal_col: str, outcome_col: str, threshold: float) -> dict[str, Any]:
    valid = frame[[signal_col, outcome_col]].dropna()
    if valid.empty:
        return {"n": 0, "status": "no_data"}
    signal = valid[signal_col].astype(bool)
    event = pd.to_numeric(valid[outcome_col], errors="coerce") <= threshold
    tp = int((signal & event).sum())
    fp = int((signal & ~event).sum())
    fn = int((~signal & event).sum())
    tn = int((~signal & ~event).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    fpr = fp / (fp + tn) if fp + tn else None
    base_rate = float(event.mean()) if len(event) else None
    return {
        "n": int(len(valid)),
        "event_threshold": threshold,
        "event_rate": _float_or_none(base_rate),
        "signal_rate": _float_or_none(signal.mean()),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": _float_or_none(precision),
        "recall": _float_or_none(recall),
        "false_positive_rate": _float_or_none(fpr),
        "precision_lift_vs_base_rate": _float_or_none((precision / base_rate) if precision is not None and base_rate else None),
    }


def _bucket_summary(frame: pd.DataFrame, mask: pd.Series, label: str) -> dict[str, Any]:
    subset = frame[mask.reindex(frame.index).fillna(False)].copy()
    if subset.empty:
        return {"label": label, "days": 0, "status": "no_data"}
    out: dict[str, Any] = {
        "label": label,
        "days": int(len(subset)),
        "status": "available",
        "mean_omd_risk_pct": _float_or_none(subset["low_distance_risk_percentile"].mean()),
        "mean_vol_pct": _float_or_none(subset["realized_vol_20_pct"].mean()),
        "mean_drawdown_pct": _float_or_none(subset["drawdown_depth_pct"].mean()),
    }
    for horizon in HORIZONS:
        dd = pd.to_numeric(subset[f"fwd_max_drawdown_h{horizon}"], errors="coerce").dropna()
        ret = pd.to_numeric(subset[f"fwd_return_h{horizon}"], errors="coerce").dropna()
        out[f"h{horizon}"] = {
            "n": int(len(dd)),
            "mean_forward_max_drawdown": _float_or_none(dd.mean()) if len(dd) else None,
            "tail_5pct_forward_max_drawdown": _float_or_none(dd.quantile(0.05)) if len(dd) else None,
            "mean_forward_return": _float_or_none(ret.mean()) if len(ret) else None,
        }
    return out


def build_incremental_review(
    *,
    db_path: Path = DB_PATH,
    as_of: str | None = "2026-08-20",
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    target: str = "0050.TW",
    window: int = 126,
    min_history: int = 126,
    baseline_lookback: int = 252,
    risk_threshold: float = 0.75,
    severe_drawdown_h20: float = -0.05,
    start: str | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings = [
        "research_only_no_live_weight_change",
        "incremental_review_uses_simple_rebuildable_vol_drawdown_baselines",
        "not_full_omd_portfolio",
    ]
    if target not in tickers:
        tickers = (*tickers, target)
    close = _load_close_panel(db_path, tickers, as_of, start=start)
    if close.empty:
        blockers.append("price_panel_missing")
    elif target not in close.columns:
        blockers.append("target_price_missing")

    frame = pd.DataFrame()
    if not blockers:
        frame = build_omd_residual_distance_score_frame(
            close,
            as_of=as_of,
            tickers=tickers,
            window=window,
            analysis_lookback=None,
            min_history=min_history,
            baseline_lookback=baseline_lookback,
        )
        if frame.empty:
            blockers.append("omd_score_frame_unavailable")
    if blockers:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_omd_residual_distance_incremental_review",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": as_of,
            "status": "blocked",
            "blocking_reasons": sorted(set(blockers)),
            "warning_reasons": sorted(set(warnings)),
            "decision": {
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        }

    frame = _add_baseline_features(frame, close, target, baseline_lookback)
    frame = _add_forward_outcomes(frame, close, target)
    frame["omd_high"] = frame["low_distance_risk_percentile"] >= risk_threshold
    frame["vol_high"] = frame["realized_vol_20_pct"] >= risk_threshold
    frame["drawdown_high"] = frame["drawdown_depth_pct"] >= risk_threshold
    frame["baseline_high"] = frame["vol_high"] | frame["drawdown_high"]
    frame["omd_only"] = frame["omd_high"] & ~frame["baseline_high"]
    frame["baseline_only"] = frame["baseline_high"] & ~frame["omd_high"]
    frame["both_high"] = frame["omd_high"] & frame["baseline_high"]
    frame["neither_high"] = ~frame["omd_high"] & ~frame["baseline_high"]

    metrics = {
        "omd_high": _classifier_metrics(frame, "omd_high", "fwd_max_drawdown_h20", severe_drawdown_h20),
        "vol_high": _classifier_metrics(frame, "vol_high", "fwd_max_drawdown_h20", severe_drawdown_h20),
        "drawdown_high": _classifier_metrics(frame, "drawdown_high", "fwd_max_drawdown_h20", severe_drawdown_h20),
        "baseline_high": _classifier_metrics(frame, "baseline_high", "fwd_max_drawdown_h20", severe_drawdown_h20),
        "omd_only": _classifier_metrics(frame, "omd_only", "fwd_max_drawdown_h20", severe_drawdown_h20),
        "both_high": _classifier_metrics(frame, "both_high", "fwd_max_drawdown_h20", severe_drawdown_h20),
    }
    buckets = {
        key: _bucket_summary(frame, frame[key].astype(bool), key)
        for key in ("omd_only", "baseline_only", "both_high", "neither_high", "omd_high", "baseline_high")
    }

    blockers_out = ["not_promoted_shadow_only"]
    omd_lift = metrics["omd_high"].get("precision_lift_vs_base_rate")
    baseline_lift = metrics["baseline_high"].get("precision_lift_vs_base_rate")
    omd_only_lift = metrics["omd_only"].get("precision_lift_vs_base_rate")
    if omd_lift is None or baseline_lift is None or float(omd_lift) <= float(baseline_lift):
        blockers_out.append("omd_precision_lift_not_above_vol_drawdown_baseline")
    if omd_only_lift is None or float(omd_only_lift) <= 1.0:
        blockers_out.append("omd_only_days_do_not_improve_severe_drawdown_precision")
    omd_only_h20 = (buckets["omd_only"].get("h20") or {}).get("mean_forward_max_drawdown")
    neither_h20 = (buckets["neither_high"].get("h20") or {}).get("mean_forward_max_drawdown")
    if omd_only_h20 is None or neither_h20 is None or float(omd_only_h20) >= float(neither_h20):
        blockers_out.append("omd_only_h20_drawdown_not_worse_than_neither_bucket")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_omd_residual_distance_incremental_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_start": str(frame["dt"].min().date()),
        "actual_data_end": str(frame["dt"].max().date()),
        "status": "research_complete_do_not_promote",
        "policy": "research_only_no_weight_change",
        "method": {
            "target": target,
            "tickers": list(tickers),
            "start": start,
            "window_trading_days": window,
            "baseline_lookback": baseline_lookback,
            "risk_threshold": risk_threshold,
            "severe_drawdown_h20_threshold": severe_drawdown_h20,
            "baseline_high": "realized_vol_20_pct >= threshold OR drawdown_depth_pct >= threshold",
            "incremental_bucket": "omd_high AND NOT baseline_high",
        },
        "coverage": {
            "rows": int(len(frame)),
            "rows_with_h20_outcome": int(frame["fwd_max_drawdown_h20"].notna().sum()),
        },
        "classifier_metrics_h20_severe_drawdown": metrics,
        "bucket_forward_outcomes": buckets,
        "blocking_reasons": sorted(set(blockers_out)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "direction_trade_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_latest_strategy_unchanged": True,
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    metrics = payload.get("classifier_metrics_h20_severe_drawdown") or {}
    buckets = payload.get("bucket_forward_outcomes") or {}
    lines = [
        "# OMD Residual-Distance Incremental Review",
        "",
        f"- as_of: `{payload.get('as_of')}`",
        f"- actual data: `{payload.get('actual_data_start')}` to `{payload.get('actual_data_end')}`",
        f"- status: `{payload.get('status')}`",
        f"- policy: `{payload.get('policy')}`",
        "",
        "## H20 Severe Drawdown Classifier",
        "",
        "| signal | signal rate | precision | recall | FPR | lift |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in ("omd_high", "vol_high", "drawdown_high", "baseline_high", "omd_only", "both_high"):
        item = metrics.get(key) or {}
        lines.append(
            f"| `{key}` | `{item.get('signal_rate')}` | `{item.get('precision')}` | "
            f"`{item.get('recall')}` | `{item.get('false_positive_rate')}` | "
            f"`{item.get('precision_lift_vs_base_rate')}` |"
        )
    lines.extend(["", "## Buckets", "", "| bucket | days | H20 mean fwd DD | H20 mean fwd return |", "| --- | ---: | ---: | ---: |"])
    for key in ("omd_only", "baseline_only", "both_high", "neither_high", "omd_high", "baseline_high"):
        item = buckets.get(key) or {}
        h20 = item.get("h20") or {}
        lines.append(
            f"| `{key}` | `{item.get('days')}` | `{h20.get('mean_forward_max_drawdown')}` | `{h20.get('mean_forward_return')}` |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- promote_to_live: `{(payload.get('decision') or {}).get('promote_to_live')}`",
            f"- target_weight_change_allowed: `{(payload.get('decision') or {}).get('target_weight_change_allowed')}`",
            f"- allow_00631l_add: `{(payload.get('decision') or {}).get('allow_00631l_add')}`",
            f"- blockers: `{', '.join(payload.get('blocking_reasons') or [])}`",
            "",
        ]
    )
    return "\n".join(lines)


def _history_path(history_dir: Path, payload: dict[str, Any], suffix: str) -> Path:
    stamp = str(payload.get("as_of") or payload.get("actual_data_end") or datetime.now().strftime("%Y-%m-%d"))
    return history_dir / f"omd_residual_distance_incremental_review_{stamp.replace('-', '')}.{suffix}"


def write_outputs(payload: dict[str, Any], *, output: Path, markdown: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = render_markdown(payload)
    markdown.write_text(md, encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, payload, "json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _history_path(history_dir, payload, "md").write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--as-of", default="2026-08-20")
    parser.add_argument("--tickers", nargs="+", default=list(DEFAULT_TICKERS))
    parser.add_argument("--broad-proxy-pool", action="store_true")
    parser.add_argument("--start", default=None)
    parser.add_argument("--target", default="0050.TW")
    parser.add_argument("--window", type=int, default=126)
    parser.add_argument("--min-history", type=int, default=126)
    parser.add_argument("--baseline-lookback", type=int, default=252)
    parser.add_argument("--risk-threshold", type=float, default=0.75)
    parser.add_argument("--severe-drawdown-h20", type=float, default=-0.05)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_incremental_review(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        tickers=tuple(BROAD_PROXY_TICKERS if args.broad_proxy_pool else tuple(str(ticker) for ticker in args.tickers)),
        target=args.target,
        window=int(args.window),
        min_history=int(args.min_history),
        baseline_lookback=int(args.baseline_lookback),
        risk_threshold=float(args.risk_threshold),
        severe_drawdown_h20=float(args.severe_drawdown_h20),
        start=args.start,
    )
    write_outputs(
        payload,
        output=_resolve(args.output),
        markdown=_resolve(args.markdown),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    metrics = payload.get("classifier_metrics_h20_severe_drawdown") or {}
    print(f"OMD residual-distance incremental review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": payload.get("status"),
                "actual_data_end": payload.get("actual_data_end"),
                "omd_lift": (metrics.get("omd_high") or {}).get("precision_lift_vs_base_rate"),
                "baseline_lift": (metrics.get("baseline_high") or {}).get("precision_lift_vs_base_rate"),
                "omd_only_lift": (metrics.get("omd_only") or {}).get("precision_lift_vs_base_rate"),
                "blockers": payload.get("blocking_reasons"),
                "target_weight_change_allowed": (payload.get("decision") or {}).get("target_weight_change_allowed"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
