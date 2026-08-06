#!/usr/bin/env python3
"""Review realized 00631L/0050 relative re-entry shadow candidates.

This is a research/advisory-readiness artifact. It reviews historical
SHIFT_00631L_* rows emitted by the opportunity shadow and never changes live
target weights.
"""

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

from backtest_group_a_plus_defensive_basket import _load_total_return_prices  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402


DEFAULT_INPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_opportunity_shadow.json"
DEFAULT_ADVISORY = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_advisory_shadow.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_candidate_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_candidate_review.md"
HORIZONS = (5, 10, 20)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _load_complete_index(db_path: Path, start: str, end: str) -> pd.DatetimeIndex:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        frame = con.execute(
            """
            SELECT dt, count(DISTINCT ticker) AS ticker_count
            FROM ohlcv
            WHERE ticker IN ('0050.TW', '00631L.TW', '00632R.TW', '00679B.TWO')
              AND dt BETWEEN ? AND ?
            GROUP BY dt
            HAVING ticker_count = 4
            ORDER BY dt
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        raise RuntimeError(f"No complete GroupA price dates between {start} and {end}")
    return pd.DatetimeIndex(pd.to_datetime(frame["dt"]))


def _candidate_rows(opportunity: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window in opportunity.get("results", []) or []:
        if not isinstance(window, dict):
            continue
        label = str(window.get("label") or "")
        bucket = str(window.get("bucket") or "")
        for row in window.get("non_keep_decisions", []) or []:
            if not isinstance(row, dict) or str(row.get("action") or "KEEP") == "KEEP":
                continue
            item = dict(row)
            item["window_label"] = label
            item["window_bucket"] = bucket
            rows.append(item)
    return rows


def _forward_edges(prices: pd.DataFrame, dt: pd.Timestamp, shift_weight: float) -> dict[str, Any]:
    if dt not in prices.index:
        return {"available": False, "reason": "date_missing_from_price_index"}
    pos = int(prices.index.get_loc(dt))
    out: dict[str, Any] = {"available": True}
    path_edges: list[float] = []
    for step in range(1, max(HORIZONS) + 1):
        if pos + step >= len(prices.index):
            break
        start_0050 = float(prices.iloc[pos]["0050.TW"])
        start_00631l = float(prices.iloc[pos]["00631L.TW"])
        end_0050 = float(prices.iloc[pos + step]["0050.TW"])
        end_00631l = float(prices.iloc[pos + step]["00631L.TW"])
        ret_0050 = end_0050 / max(start_0050, 1e-12) - 1.0
        ret_00631l = end_00631l / max(start_00631l, 1e-12) - 1.0
        path_edges.append(float(shift_weight) * (ret_00631l - ret_0050))
        if step in HORIZONS:
            out[f"edge_{step}d"] = path_edges[-1]
    out["min_path_edge_20d"] = min(path_edges) if path_edges else None
    out["max_path_edge_20d"] = max(path_edges) if path_edges else None
    out["observed_path_days"] = len(path_edges)
    return out


def _stats(values: list[float]) -> dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return {"count": 0, "mean": None, "positive_rate": None, "worst": None, "p10": None, "median": None, "p90": None}
    return {
        "count": int(len(arr)),
        "mean": float(np.mean(arr)),
        "positive_rate": float(np.mean(arr > 0.0)),
        "worst": float(np.min(arr)),
        "p10": float(np.quantile(arr, 0.10)),
        "median": float(np.median(arr)),
        "p90": float(np.quantile(arr, 0.90)),
    }


def _by_window(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    labels = sorted({str(row["window_label"]) for row in rows})
    for label in labels:
        subset = [row for row in rows if row["window_label"] == label]
        out[label] = {
            "candidate_rows": int(len(subset)),
            "unique_dates": int(len({row["date"] for row in subset})),
            "edge_5d": _stats([row["forward"].get("edge_5d") for row in subset if row.get("forward")]),
            "edge_10d": _stats([row["forward"].get("edge_10d") for row in subset if row.get("forward")]),
            "edge_20d": _stats([row["forward"].get("edge_20d") for row in subset if row.get("forward")]),
            "min_path_edge_20d": _stats(
                [row["forward"].get("min_path_edge_20d") for row in subset if row.get("forward")]
            ),
        }
    return out


def _clusters(rows: list[dict[str, Any]], price_index: pd.DatetimeIndex) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for label in sorted({str(row["window_label"]) for row in rows}):
        subset = sorted([row for row in rows if row["window_label"] == label], key=lambda row: row["date"])
        current: list[dict[str, Any]] = []
        prev_pos: int | None = None
        for row in subset:
            dt = pd.Timestamp(row["date"])
            if dt not in price_index:
                continue
            pos = int(price_index.get_loc(dt))
            if current and prev_pos is not None and pos - prev_pos > 1:
                out.append(_cluster_summary(label, current))
                current = []
            current.append(row)
            prev_pos = pos
        if current:
            out.append(_cluster_summary(label, current))
    return out


def _cluster_summary(label: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "window_label": label,
        "start": rows[0]["date"],
        "end": rows[-1]["date"],
        "length": int(len(rows)),
        "edge_20d_mean": _stats([row["forward"].get("edge_20d") for row in rows if row.get("forward")]).get("mean"),
        "edge_20d_worst": _stats([row["forward"].get("edge_20d") for row in rows if row.get("forward")]).get("worst"),
    }


def build_review(*, input_path: Path, advisory_path: Path | None, db_path: Path) -> dict[str, Any]:
    opportunity = _load_json(input_path)
    candidates = _candidate_rows(opportunity)
    if not candidates:
        return {
            "schema_version": 1,
            "report_type": "00631l_0050_relative_reentry_candidate_review",
            "status": "available",
            "policy": "shadow_only_no_auto_weight_change",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "candidate_rows": 0,
            "recommendation": "no_candidates_to_review",
        }
    dates = sorted(str(row["date"]) for row in candidates)
    index = _load_complete_index(db_path, min(dates), _max_price_date(db_path))
    prices, _coverage = _load_total_return_prices(db_path, index)
    reviewed: list[dict[str, Any]] = []
    for row in candidates:
        shift_weight = float(row.get("shift_00631l_weight") or 0.0)
        item = dict(row)
        item["forward"] = _forward_edges(prices, pd.Timestamp(row["date"]), shift_weight)
        reviewed.append(item)
    advisory = _load_json(advisory_path) if advisory_path is not None and advisory_path.exists() else None
    edge20_values = [row["forward"].get("edge_20d") for row in reviewed if row.get("forward")]
    clusters = _clusters(reviewed, prices.index)
    worst = sorted(
        [row for row in reviewed if row.get("forward", {}).get("edge_20d") is not None],
        key=lambda row: float(row["forward"]["edge_20d"]),
    )[:10]
    summary = {
        "candidate_rows": int(len(reviewed)),
        "unique_candidate_dates": int(len({row["date"] for row in reviewed})),
        "edge_5d": _stats([row["forward"].get("edge_5d") for row in reviewed if row.get("forward")]),
        "edge_10d": _stats([row["forward"].get("edge_10d") for row in reviewed if row.get("forward")]),
        "edge_20d": _stats(edge20_values),
        "min_path_edge_20d": _stats([row["forward"].get("min_path_edge_20d") for row in reviewed if row.get("forward")]),
        "cluster_count": int(len(clusters)),
        "max_cluster_length": int(max((cluster["length"] for cluster in clusters), default=0)),
    }
    recommendation = "keep_shadow_only_not_advisory_ready"
    if (
        summary["edge_20d"]["positive_rate"] is not None
        and summary["edge_20d"]["positive_rate"] >= 0.65
        and summary["edge_20d"]["p10"] is not None
        and summary["edge_20d"]["p10"] > -0.002
        and advisory
        and advisory.get("advisory_allowed") is True
    ):
        recommendation = "eligible_for_manual_advisory_review"
    return {
        "schema_version": 1,
        "report_type": "00631l_0050_relative_reentry_candidate_review",
        "status": "available",
        "policy": "shadow_only_no_auto_weight_change",
        "active_allocation_impact": "none",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(input_path),
        "advisory": str(advisory_path) if advisory_path is not None else None,
        "source_summary": opportunity.get("summary"),
        "advisory_state": {
            "recommended_action": advisory.get("recommended_action") if advisory else None,
            "advisory_allowed": advisory.get("advisory_allowed") if advisory else None,
            "blockers": (advisory.get("gates") or {}).get("blockers") if advisory else None,
        },
        "summary": summary,
        "by_window": _by_window(reviewed),
        "clusters": sorted(clusters, key=lambda row: (-int(row["length"]), row["window_label"], row["start"]))[:20],
        "worst_edge_20d_rows": worst,
        "review_findings": [
            "Historical candidates exist, but review remains shadow-only and does not change latest strategy weights.",
            "Live/active windows have positive mean edge but weak positive-rate and negative p10/worst tails after coverage extension.",
            "Latest advisory state must pass strategy trust and model internal gates before candidate promotion.",
        ],
        "recommendation": recommendation,
    }


def _max_price_date(db_path: Path) -> str:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        value = con.execute("SELECT max(dt) FROM ohlcv WHERE ticker = '00631L.TW'").fetchone()[0]
    finally:
        con.close()
    return str(value)


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def build_markdown(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    edge20 = summary.get("edge_20d") if isinstance(summary.get("edge_20d"), dict) else {}
    min_path = summary.get("min_path_edge_20d") if isinstance(summary.get("min_path_edge_20d"), dict) else {}
    lines = [
        "# Relative Reentry Candidate Review",
        "",
        f"- recommendation: `{payload.get('recommendation')}`",
        f"- candidate_rows: `{summary.get('candidate_rows')}`",
        f"- unique_candidate_dates: `{summary.get('unique_candidate_dates')}`",
        f"- edge_20d_mean: `{_fmt(edge20.get('mean'))}`",
        f"- edge_20d_positive_rate: `{_fmt(edge20.get('positive_rate'))}`",
        f"- edge_20d_worst: `{_fmt(edge20.get('worst'))}`",
        f"- edge_20d_p10: `{_fmt(edge20.get('p10'))}`",
        f"- min_path_edge_20d_worst: `{_fmt(min_path.get('worst'))}`",
        f"- cluster_count: `{summary.get('cluster_count')}`",
        f"- max_cluster_length: `{summary.get('max_cluster_length')}`",
        f"- advisory_blockers: `{payload.get('advisory_state', {}).get('blockers')}`",
        "",
        "This report is shadow-only and has no live allocation impact.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--advisory", default=str(DEFAULT_ADVISORY))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    payload = build_review(
        input_path=_resolve(args.input),
        advisory_path=_resolve(args.advisory),
        db_path=_resolve(args.db),
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md = _resolve(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(build_markdown(payload), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"Markdown: {output_md}")
    print(f"Recommendation: {payload.get('recommendation')}")


if __name__ == "__main__":
    main()
