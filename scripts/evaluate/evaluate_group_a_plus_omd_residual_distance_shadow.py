#!/usr/bin/env python3
"""Evaluate OMD residual-distance shadow against GroupA+ stress windows."""

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


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/omd_residual_distance_shadow_evaluation.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/omd_residual_distance_shadow_evaluation.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/omd_residual_distance_shadow_evaluation/history"
DEFAULT_WINDOWS = [
    {"label": "2018_correction", "start": "2018-01-02", "end": "2018-12-31"},
    {"label": "2020_covid", "start": "2020-01-02", "end": "2020-06-30"},
    {"label": "2022_rate_hike", "start": "2022-01-03", "end": "2022-12-30"},
    {"label": "2024_2026_live", "start": "2024-01-02", "end": "latest"},
    {"label": "2025_2026_active", "start": "2025-01-02", "end": "latest"},
]
HORIZONS = (5, 20, 40)


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


def _load_close_panel(db_path: Path, tickers: tuple[str, ...], as_of: str | None) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    placeholders = ", ".join("?" for _ in tickers)
    params: list[Any] = list(tickers)
    date_filter = ""
    if as_of:
        date_filter = "AND dt <= ?"
        params.append(as_of)
    with duckdb.connect(str(db_path), read_only=True) as conn:
        rows = conn.execute(
            f"""
            SELECT ticker, dt, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) {date_filter}
            ORDER BY dt, ticker
            """,
            params,
        ).fetchdf()
    if rows.empty:
        return pd.DataFrame()
    rows = rows.dropna(subset=["ticker", "dt", "close"]).copy()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def _resolve_windows(windows: list[dict[str, str]], latest_date: pd.Timestamp) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in windows:
        end = latest_date.strftime("%Y-%m-%d") if str(item["end"]).lower() == "latest" else item["end"]
        out.append({"label": item["label"], "start": item["start"], "end": end})
    return out


def _parse_windows(raw: str | None) -> list[dict[str, str]]:
    if not raw:
        return list(DEFAULT_WINDOWS)
    out: list[dict[str, str]] = []
    for item in raw.split(","):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 3 or not all(parts):
            raise ValueError("--windows format must be label:start:end,label:start:end")
        out.append({"label": parts[0], "start": parts[1], "end": parts[2]})
    return out


def _add_forward_outcomes(scores: pd.DataFrame, close: pd.DataFrame, target: str) -> pd.DataFrame:
    out = scores.copy()
    target_close = close[target].dropna().sort_index()
    target_close.index = pd.to_datetime(target_close.index)
    aligned_close = target_close.reindex(out["dt"]).to_numpy(dtype=float)
    full_dates = target_close.index
    close_values = target_close.to_numpy(dtype=float)
    pos_by_date = {date: idx for idx, date in enumerate(full_dates)}
    for horizon in HORIZONS:
        forward_returns: list[float | None] = []
        forward_max_drawdowns: list[float | None] = []
        for date, base_price in zip(out["dt"], aligned_close):
            idx = pos_by_date.get(pd.Timestamp(date))
            if idx is None or not np.isfinite(base_price) or idx + horizon >= len(close_values):
                forward_returns.append(None)
                forward_max_drawdowns.append(None)
                continue
            future = close_values[idx + 1 : idx + horizon + 1]
            if len(future) < horizon or not np.all(np.isfinite(future)):
                forward_returns.append(None)
                forward_max_drawdowns.append(None)
                continue
            forward_returns.append(float(future[-1] / base_price - 1.0))
            forward_max_drawdowns.append(float(np.min(future / base_price - 1.0)))
        out[f"fwd_return_h{horizon}"] = forward_returns
        out[f"fwd_max_drawdown_h{horizon}"] = forward_max_drawdowns
    return out


def _summarize_subset(subset: pd.DataFrame, label: str) -> dict[str, Any]:
    if subset.empty:
        return {"label": label, "days": 0, "status": "no_data"}
    out: dict[str, Any] = {
        "label": label,
        "days": int(len(subset)),
        "status": "available",
        "manual_review_rate": _float_or_none(subset["manual_review_required"].mean()),
        "mean_low_distance_risk_percentile": _float_or_none(subset["low_distance_risk_percentile"].mean()),
        "max_low_distance_risk_percentile": _float_or_none(subset["low_distance_risk_percentile"].max()),
        "mean_pairwise_residual_distance": _float_or_none(subset["mean_pairwise_residual_distance"].mean()),
        "min_pairwise_residual_distance": _float_or_none(subset["mean_pairwise_residual_distance"].min()),
        "state_counts": {str(k): int(v) for k, v in subset["state"].value_counts().to_dict().items()},
    }
    for horizon in HORIZONS:
        returns = pd.to_numeric(subset[f"fwd_return_h{horizon}"], errors="coerce").dropna()
        drawdowns = pd.to_numeric(subset[f"fwd_max_drawdown_h{horizon}"], errors="coerce").dropna()
        out[f"h{horizon}"] = {
            "days_with_forward_return": int(len(returns)),
            "mean_forward_return": _float_or_none(returns.mean()) if len(returns) else None,
            "median_forward_return": _float_or_none(returns.median()) if len(returns) else None,
            "mean_forward_max_drawdown": _float_or_none(drawdowns.mean()) if len(drawdowns) else None,
            "tail_5pct_forward_max_drawdown": _float_or_none(drawdowns.quantile(0.05)) if len(drawdowns) else None,
        }
    return out


def _window_summary(scores: pd.DataFrame, window: dict[str, str]) -> dict[str, Any]:
    start = pd.Timestamp(window["start"])
    end = pd.Timestamp(window["end"])
    subset = scores[(scores["dt"] >= start) & (scores["dt"] <= end)]
    summary = _summarize_subset(subset, window["label"])
    summary.update({"start": window["start"], "end": window["end"]})
    if not subset.empty:
        top = subset.sort_values("low_distance_risk_percentile", ascending=False).head(8)
        summary["top_risk_days"] = [
            {
                "dt": str(row.dt.date()),
                "state": str(row.state),
                "low_distance_risk_percentile": _float_or_none(row.low_distance_risk_percentile),
                "mean_pairwise_residual_distance": _float_or_none(row.mean_pairwise_residual_distance),
                "fwd_max_drawdown_h20": _float_or_none(row.fwd_max_drawdown_h20),
            }
            for row in top.itertuples(index=False)
        ]
    return summary


def build_evaluation(
    *,
    db_path: Path = DB_PATH,
    as_of: str | None = "2026-08-20",
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    target: str = "0050.TW",
    window: int = 126,
    min_history: int = 126,
    baseline_lookback: int = 252,
    windows: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings = [
        "research_only_no_live_weight_change",
        "small_etf_universe_not_full_omd_portfolio",
        "residual_distance_is_diagnostic_not_trade_signal",
    ]
    if target not in tickers:
        tickers = (*tickers, target)
    close = _load_close_panel(db_path, tickers, as_of)
    if close.empty:
        blockers.append("price_panel_missing")
    elif target not in close.columns:
        blockers.append("target_price_missing")

    scores = pd.DataFrame()
    if not blockers:
        scores = build_omd_residual_distance_score_frame(
            close,
            as_of=as_of,
            tickers=tickers,
            window=window,
            analysis_lookback=None,
            min_history=min_history,
            baseline_lookback=baseline_lookback,
        )
        if scores.empty:
            blockers.append("omd_residual_distance_scores_unavailable")
    if blockers:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_omd_residual_distance_shadow_evaluation",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "as_of": as_of,
            "status": "blocked",
            "policy": "research_only_no_weight_change",
            "blocking_reasons": sorted(set(blockers)),
            "warning_reasons": sorted(set(warnings)),
            "decision": {
                "promote_to_live": False,
                "target_weight_change_allowed": False,
                "auto_rebalance_allowed": False,
                "allow_00631l_add": False,
                "allow_00632r_open": False,
            },
        }

    scores = _add_forward_outcomes(scores, close, target)
    latest_date = pd.Timestamp(scores["dt"].max())
    resolved_windows = _resolve_windows(windows or DEFAULT_WINDOWS, latest_date)
    stress_mask = pd.Series(False, index=scores.index)
    for item in resolved_windows:
        stress_mask |= (scores["dt"] >= pd.Timestamp(item["start"])) & (scores["dt"] <= pd.Timestamp(item["end"]))
    stress = scores[stress_mask]
    non_stress = scores[~stress_mask]
    high_risk = scores[scores["low_distance_risk_percentile"] >= 0.75]
    normal = scores[scores["low_distance_risk_percentile"] < 0.75]

    aggregate = {
        "total_days": int(len(scores)),
        "stress_days": int(len(stress)),
        "non_stress_days": int(len(non_stress)),
        "stress_manual_review_rate": _float_or_none(stress["manual_review_required"].mean()) if not stress.empty else None,
        "non_stress_manual_review_rate": _float_or_none(non_stress["manual_review_required"].mean()) if not non_stress.empty else None,
        "high_risk_days_ge_0p75": int(len(high_risk)),
        "high_risk_rate_ge_0p75": _float_or_none(len(high_risk) / len(scores)),
        "state_counts_all": {str(k): int(v) for k, v in scores["state"].value_counts().to_dict().items()},
    }
    conditional = {
        "high_risk_ge_0p75": _summarize_subset(high_risk, "high_risk_ge_0p75"),
        "normal_lt_0p75": _summarize_subset(normal, "normal_lt_0p75"),
        "stress_windows": _summarize_subset(stress, "stress_windows"),
        "non_stress": _summarize_subset(non_stress, "non_stress"),
    }

    blockers_out = ["not_promoted_shadow_only"]
    stress_rate = aggregate.get("stress_manual_review_rate") or 0.0
    non_stress_rate = aggregate.get("non_stress_manual_review_rate") or 0.0
    if stress_rate <= non_stress_rate:
        blockers_out.append("manual_review_rate_not_higher_in_stress_windows")
    high_h20 = conditional["high_risk_ge_0p75"].get("h20", {})
    normal_h20 = conditional["normal_lt_0p75"].get("h20", {})
    high_dd = high_h20.get("mean_forward_max_drawdown")
    normal_dd = normal_h20.get("mean_forward_max_drawdown")
    if high_dd is None or normal_dd is None or float(high_dd) >= float(normal_dd):
        blockers_out.append("high_risk_bucket_does_not_have_worse_h20_forward_drawdown")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_omd_residual_distance_shadow_evaluation",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_start": str(scores["dt"].min().date()),
        "actual_data_end": str(scores["dt"].max().date()),
        "status": "research_complete_do_not_promote",
        "policy": "research_only_no_weight_change",
        "source_paper": {
            "arxiv": "2607.27461",
            "implemented_as": "residual_distance_crowding_validation_not_full_omd_portfolio",
        },
        "method": {
            "paper_equivalent": False,
            "tickers": list(tickers),
            "target": target,
            "window_trading_days": window,
            "min_history": min_history,
            "baseline_lookback": baseline_lookback,
            "high_risk_definition": "low_distance_risk_percentile >= 0.75",
            "outcomes": [f"H{horizon}_forward_return_and_max_drawdown" for horizon in HORIZONS],
        },
        "aggregate": aggregate,
        "conditional": conditional,
        "windows": [_window_summary(scores, item) for item in resolved_windows],
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


def _history_json_path(history_dir: Path, payload: dict[str, Any]) -> Path:
    stamp = str(payload.get("as_of") or payload.get("actual_data_end") or datetime.now().strftime("%Y-%m-%d"))
    return history_dir / f"omd_residual_distance_shadow_evaluation_{stamp.replace('-', '')}.json"


def _history_md_path(history_dir: Path, payload: dict[str, Any]) -> Path:
    stamp = str(payload.get("as_of") or payload.get("actual_data_end") or datetime.now().strftime("%Y-%m-%d"))
    return history_dir / f"omd_residual_distance_shadow_evaluation_{stamp.replace('-', '')}.md"


def render_markdown(payload: dict[str, Any]) -> str:
    agg = payload.get("aggregate") or {}
    cond = payload.get("conditional") or {}
    high_h20 = ((cond.get("high_risk_ge_0p75") or {}).get("h20") or {})
    normal_h20 = ((cond.get("normal_lt_0p75") or {}).get("h20") or {})
    lines = [
        "# OMD Residual-Distance Shadow Evaluation",
        "",
        f"- as_of: `{payload.get('as_of')}`",
        f"- actual data: `{payload.get('actual_data_start')}` to `{payload.get('actual_data_end')}`",
        f"- status: `{payload.get('status')}`",
        f"- policy: `{payload.get('policy')}`",
        "",
        "## Aggregate",
        "",
        f"- total days: `{agg.get('total_days')}`",
        f"- stress manual review rate: `{agg.get('stress_manual_review_rate')}`",
        f"- non-stress manual review rate: `{agg.get('non_stress_manual_review_rate')}`",
        f"- high-risk days >= 0.75: `{agg.get('high_risk_days_ge_0p75')}`",
        f"- high-risk rate >= 0.75: `{agg.get('high_risk_rate_ge_0p75')}`",
        "",
        "## H20 Forward Drawdown Check",
        "",
        f"- high-risk mean H20 forward max drawdown: `{high_h20.get('mean_forward_max_drawdown')}`",
        f"- normal mean H20 forward max drawdown: `{normal_h20.get('mean_forward_max_drawdown')}`",
        "",
        "## Windows",
        "",
        "| window | days | manual review rate | max risk pct | mean H20 fwd drawdown |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for item in payload.get("windows") or []:
        h20 = item.get("h20") or {}
        lines.append(
            "| {label} | {days} | {review} | {risk} | {dd} |".format(
                label=item.get("label"),
                days=item.get("days"),
                review=item.get("manual_review_rate"),
                risk=item.get("max_low_distance_risk_percentile"),
                dd=h20.get("mean_forward_max_drawdown"),
            )
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


def write_outputs(payload: dict[str, Any], *, output: Path, markdown: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = render_markdown(payload)
    markdown.write_text(md, encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_json_path(history_dir, payload).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _history_md_path(history_dir, payload).write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--as-of", default="2026-08-20")
    parser.add_argument("--tickers", nargs="+", default=list(DEFAULT_TICKERS))
    parser.add_argument("--target", default="0050.TW")
    parser.add_argument("--window", type=int, default=126)
    parser.add_argument("--min-history", type=int, default=126)
    parser.add_argument("--baseline-lookback", type=int, default=252)
    parser.add_argument("--windows", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_evaluation(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        tickers=tuple(str(ticker) for ticker in args.tickers),
        target=str(args.target),
        window=int(args.window),
        min_history=int(args.min_history),
        baseline_lookback=int(args.baseline_lookback),
        windows=_parse_windows(args.windows),
    )
    write_outputs(
        payload,
        output=_resolve(args.output),
        markdown=_resolve(args.markdown),
        history_dir=None if args.no_history else _resolve(args.history_dir),
    )
    print(f"OMD residual-distance evaluation: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": payload.get("status"),
                "actual_data_end": payload.get("actual_data_end"),
                "stress_manual_review_rate": (payload.get("aggregate") or {}).get("stress_manual_review_rate"),
                "non_stress_manual_review_rate": (payload.get("aggregate") or {}).get("non_stress_manual_review_rate"),
                "blockers": payload.get("blocking_reasons"),
                "target_weight_change_allowed": (payload.get("decision") or {}).get("target_weight_change_allowed"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

