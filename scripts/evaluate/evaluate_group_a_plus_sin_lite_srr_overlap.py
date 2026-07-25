#!/usr/bin/env python3
"""Evaluate SIN-lite overlap with SRR-lite no-add shadow signals.

Research-only. This script compares SIN-lite variants against the existing
SRR-lite frame using the SRR forward no-add labels. It does not change live
signals, target weights, or strategy manifests.
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

from scripts.evaluate.build_group_a_plus_sin_lite_proxy import _load_close_panel, _load_metadata
from scripts.evaluate.sweep_group_a_plus_sin_lite_params import _fast_daily_scores_from_close


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_SRR_FRAME = PROJECT_ROOT / "results/srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv"
DEFAULT_PARAM_SWEEP = PROJECT_ROOT / "report/group_a_plus/latest/sin_lite_param_sweep.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/sin_lite_srr_overlap.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/sin_lite_srr_overlap/history"
DEFAULT_FRAME_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/sin_lite_srr_overlap_frame.csv"

DEFAULT_PARAMS = {"lookback": 120, "min_history": 80, "edge_threshold": 0.35}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


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


def _score_forward_summary(frame: pd.DataFrame, active: pd.Series, horizon: int) -> dict[str, Any]:
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


def _summarize_signal(frame: pd.DataFrame, signal: pd.Series) -> dict[str, Any]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    return {
        "active_days": int(signal.sum()),
        "active_dates": [str(pd.Timestamp(dt).date()) for dt in frame.index[signal]],
        "h5": _score_forward_summary(frame, signal, 5),
        "h10": _score_forward_summary(frame, signal, 10),
    }


def _read_srr_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    frame.index = pd.to_datetime(frame.index).normalize()
    return frame


def _load_best_params(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"lookback": 60, "min_history": 40, "edge_threshold": 0.2}
    payload = json.loads(path.read_text(encoding="utf-8"))
    params = ((payload.get("best_candidate") or {}).get("params") or {}).copy()
    return {
        "lookback": int(params.get("lookback", 60)),
        "min_history": int(params.get("min_history", 40)),
        "edge_threshold": float(params.get("edge_threshold", 0.2)),
    }


def _load_close_once(db_path: Path, tickers_as_of: str | None) -> pd.DataFrame:
    with duckdb.connect(str(db_path), read_only=True) as conn:
        metadata = _load_metadata(conn)
        tickers = metadata["ticker"].astype(str).tolist() if not metadata.empty else []
        return _load_close_panel(conn, tickers, tickers_as_of)


def _sin_scores(close: pd.DataFrame, *, params: dict[str, Any]) -> pd.DataFrame:
    scores = _fast_daily_scores_from_close(
        close,
        windows=[],
        lookback=int(params["lookback"]),
        min_history=int(params["min_history"]),
        edge_threshold=float(params["edge_threshold"]),
        non_window_sample_step=1,
    )
    if scores.empty:
        return scores
    scores = scores.set_index(pd.to_datetime(scores["dt"]).dt.normalize()).sort_index()
    return scores[["state", "sin_lite_score", "usable_ticker_count"]]


def build_overlap_report(
    *,
    db_path: Path = DEFAULT_DB,
    srr_frame_path: Path = DEFAULT_SRR_FRAME,
    param_sweep_path: Path = DEFAULT_PARAM_SWEEP,
    as_of: str | None = "2026-07-20",
) -> tuple[dict[str, Any], pd.DataFrame]:
    srr = _read_srr_frame(srr_frame_path)
    close = _load_close_once(db_path, as_of)
    tuned_params = _load_best_params(param_sweep_path)
    variants = {
        "sin_default_watch": (DEFAULT_PARAMS, "watch"),
        "sin_default_elevated": (DEFAULT_PARAMS, "elevated"),
        "sin_tuned_watch": (tuned_params, "watch"),
        "sin_tuned_elevated": (tuned_params, "elevated"),
    }

    frame = srr.copy()
    srr_no_add = frame["no_add_active"].fillna(False).astype(bool)
    frame["srr_no_add_active"] = srr_no_add
    for variant, (params, active_state) in variants.items():
        scores = _sin_scores(close, params=params)
        aligned = scores.reindex(frame.index)
        frame[f"{variant}_score"] = aligned["sin_lite_score"]
        frame[f"{variant}_state"] = aligned["state"]
        if active_state == "elevated":
            frame[variant] = aligned["state"].isin(["elevated", "blocked_for_leverage_add"]).fillna(False)
        else:
            frame[variant] = aligned["state"].isin(["watch", "elevated", "blocked_for_leverage_add"]).fillna(False)

    signals: dict[str, pd.Series] = {
        "srr_no_add_active": srr_no_add,
    }
    for variant in variants:
        sin_active = frame[variant].fillna(False).astype(bool)
        signals[variant] = sin_active
        signals[f"union_srr_or_{variant}"] = srr_no_add | sin_active
        signals[f"intersection_srr_and_{variant}"] = srr_no_add & sin_active
        signals[f"{variant}_without_srr"] = sin_active & ~srr_no_add
        signals[f"srr_without_{variant}"] = srr_no_add & ~sin_active

    for name, signal in signals.items():
        frame[name] = signal.reindex(frame.index).fillna(False).astype(bool)

    summary = {name: _summarize_signal(frame, signal) for name, signal in signals.items()}
    tuned_union = summary["union_srr_or_sin_tuned_watch"]["h10"]["confusion"]
    srr_h10 = summary["srr_no_add_active"]["h10"]["confusion"]
    tuned_only_h10 = summary["sin_tuned_watch_without_srr"]["h10"]["confusion"]
    blockers = [
        "sin_lite_overlap_research_only",
        "sin_lite_not_paper_equivalent",
        "no_live_weight_change_allowed",
    ]
    if (tuned_union.get("false_positive_rate") or 0.0) > (srr_h10.get("false_positive_rate") or 0.0) + 0.03:
        blockers.append("tuned_union_raises_h10_false_positive_rate_too_much")
    if int(tuned_only_h10.get("active_days") or 0) and (tuned_only_h10.get("precision") or 0.0) < (
        srr_h10.get("precision") or 0.0
    ):
        blockers.append("sin_tuned_only_precision_below_srr")

    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_sin_lite_srr_overlap",
        "status": "blocked",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "window": {
            "start": str(frame.index.min().date()),
            "end": str(frame.index.max().date()),
            "rows": int(len(frame)),
        },
        "inputs": {
            "db_path": str(db_path),
            "srr_frame": str(srr_frame_path),
            "param_sweep": str(param_sweep_path),
        },
        "params": {
            "default": DEFAULT_PARAMS,
            "tuned": tuned_params,
        },
        "summary": summary,
        "systemic_bubble_overlap": {
            "status": "not_available",
            "reason": "systemic_bubble_time_at_risk currently has latest snapshot artifacts but no daily frame aligned to SRR labels",
        },
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "interpretation": (
            "Use this only to assess incremental information. SIN-lite should improve SRR-lite precision "
            "or add high-quality missed dates without materially increasing false positives before any gate discussion."
        ),
    }
    return report, frame


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"sin_lite_srr_overlap_{stamp}.json"


def write_overlap(
    report: dict[str, Any],
    frame: pd.DataFrame,
    output_path: Path,
    frame_output_path: Path,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame_output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(frame_output_path, encoding="utf-8-sig")
    report["frame_output"] = str(frame_output_path)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, report.get("as_of")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--srr-frame", default=str(DEFAULT_SRR_FRAME))
    parser.add_argument("--param-sweep", default=str(DEFAULT_PARAM_SWEEP))
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--frame-output", default=str(DEFAULT_FRAME_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report, frame = build_overlap_report(
        db_path=_resolve(args.db),
        srr_frame_path=_resolve(args.srr_frame),
        param_sweep_path=_resolve(args.param_sweep),
        as_of=args.as_of,
    )
    write_overlap(
        report,
        frame,
        _resolve(args.output),
        _resolve(args.frame_output),
        None if args.no_history else _resolve(args.history_dir),
    )
    compact = {
        key: {
            "active_days": value["active_days"],
            "h10_precision": value["h10"]["confusion"]["precision"],
            "h10_recall": value["h10"]["confusion"]["recall"],
            "h10_fpr": value["h10"]["confusion"]["false_positive_rate"],
        }
        for key, value in report["summary"].items()
        if key
        in {
            "srr_no_add_active",
            "sin_tuned_watch",
            "union_srr_or_sin_tuned_watch",
            "intersection_srr_and_sin_tuned_watch",
            "sin_tuned_watch_without_srr",
        }
    }
    print(f"SIN-lite/SRR overlap: {_resolve(args.output)}")
    print(f"Frame: {_resolve(args.frame_output)}")
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
