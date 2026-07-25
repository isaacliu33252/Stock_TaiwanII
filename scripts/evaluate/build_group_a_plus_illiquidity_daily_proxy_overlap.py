#!/usr/bin/env python3
"""Compare daily illiquidity proxy states with SRR-lite and latest crash alert.

Research-only. The daily OHLCV proxy is not paper-equivalent to the
high-frequency illiquidity-network method from arXiv 2004.01917, so this report
only checks overlap and incremental information against existing diagnostics.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_group_a_plus_illiquidity_daily_proxy_backtest import (  # noqa: E402
    STATE_RANK,
    _load_daily_proxy_frame,
)


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_SRR_FRAME = PROJECT_ROOT / "results/srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv"
DEFAULT_CRASH_ALERT = PROJECT_ROOT / "report/group_a_plus/latest/crash_risk_alert.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/illiquidity_daily_proxy_overlap.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/illiquidity_daily_proxy_overlap/history"

SRR_CRASH_WATCH_SCORE_THRESHOLD = 0.75
SRR_CRASH_WATCH_DENSITY_THRESHOLD = 0.65


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_srr_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    frame.index = pd.to_datetime(frame.index).normalize()
    if "crash_watch_active" not in frame:
        frame["crash_watch_active"] = (
            (pd.to_numeric(frame["systemic_fragility_score"], errors="coerce") >= SRR_CRASH_WATCH_SCORE_THRESHOLD)
            & (pd.to_numeric(frame["graph_density"], errors="coerce") >= SRR_CRASH_WATCH_DENSITY_THRESHOLD)
        ).fillna(False)
    return frame


def _state_at_or_above(series: pd.Series, state: str) -> pd.Series:
    threshold = STATE_RANK[state]
    return series.map(lambda value: STATE_RANK.get(str(value), -1) >= threshold)


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


def _forward_summary(frame: pd.DataFrame, signal: pd.Series, horizon: int) -> dict[str, Any]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    ret_col = f"srr_forward_ret_00631l_h{horizon}"
    rel_col = f"srr_forward_rel_00631l_vs_0050_h{horizon}"
    mdd_col = f"srr_forward_mdd_00631l_h{horizon}"
    label_col = f"srr_no_add_label_h{horizon}"
    return {
        "horizon_days": horizon,
        "confusion": _confusion(signal, frame[label_col]),
        "active_mean_forward_ret_00631l": float(frame.loc[signal, ret_col].mean()) if signal.any() else None,
        "inactive_mean_forward_ret_00631l": float(frame.loc[~signal, ret_col].mean()) if (~signal).any() else None,
        "active_mean_relative_vs_0050": float(frame.loc[signal, rel_col].mean()) if signal.any() else None,
        "inactive_mean_relative_vs_0050": float(frame.loc[~signal, rel_col].mean()) if (~signal).any() else None,
        "active_mean_forward_mdd_00631l": float(frame.loc[signal, mdd_col].mean()) if signal.any() else None,
        "inactive_mean_forward_mdd_00631l": float(frame.loc[~signal, mdd_col].mean()) if (~signal).any() else None,
    }


def _signal_summary(frame: pd.DataFrame, signal: pd.Series) -> dict[str, Any]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    return {
        "active_days": int(signal.sum()),
        "active_rate": _safe_rate(int(signal.sum()), int(len(signal))),
        "active_dates": [str(pd.Timestamp(dt).date()) for dt in frame.index[signal]],
        "h5": _forward_summary(frame, signal, 5),
        "h10": _forward_summary(frame, signal, 10),
    }


def _overlap_counts(a: pd.Series, b: pd.Series) -> dict[str, Any]:
    a = a.fillna(False).astype(bool)
    b = b.fillna(False).astype(bool)
    both = a & b
    a_only = a & ~b
    b_only = b & ~a
    either = a | b
    return {
        "a_active_days": int(a.sum()),
        "b_active_days": int(b.sum()),
        "both_active_days": int(both.sum()),
        "a_only_days": int(a_only.sum()),
        "b_only_days": int(b_only.sum()),
        "either_active_days": int(either.sum()),
        "a_overlap_share": _safe_rate(int(both.sum()), int(a.sum())),
        "b_overlap_share": _safe_rate(int(both.sum()), int(b.sum())),
        "jaccard": _safe_rate(int(both.sum()), int(either.sum())),
    }


def _latest_alignment(frame: pd.DataFrame, crash_alert: dict[str, Any]) -> dict[str, Any]:
    if frame.empty:
        return {}
    latest = frame.iloc[-1]
    return {
        "date": str(pd.Timestamp(frame.index[-1]).date()),
        "illiquidity_stress_state": str(latest["illiquidity_stress_state"]),
        "illiquidity_stress_score": float(latest["illiquidity_stress_score"]),
        "illiquidity_elevated_or_worse": bool(latest["illiquidity_elevated_or_worse"]),
        "srr_no_add_active": bool(latest["srr_no_add_active"]),
        "srr_crash_watch_active": bool(latest["srr_crash_watch_active"]),
        "crash_risk_alert_as_of": crash_alert.get("as_of"),
        "crash_risk_alert_watch_level": crash_alert.get("watch_level"),
        "crash_risk_alert_active": crash_alert.get("alert_active"),
        "crash_risk_category_score": crash_alert.get("category_score"),
        "alignment_note": (
            "crash_risk_alert is latest snapshot only; historical overlap is computed against SRR-lite frame."
        ),
    }


def build_overlap(
    *,
    db_path: Path = DEFAULT_DB,
    srr_frame_path: Path = DEFAULT_SRR_FRAME,
    crash_alert_path: Path = DEFAULT_CRASH_ALERT,
    as_of: str | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    proxy = _load_daily_proxy_frame(db_path, as_of)
    srr = _read_srr_frame(srr_frame_path)
    if proxy.empty:
        raise RuntimeError("Daily illiquidity proxy frame is unavailable")
    if srr.empty:
        raise RuntimeError("SRR-lite frame is unavailable")

    proxy = proxy.rename(
        columns={
            "stress_score": "illiquidity_stress_score",
            "stress_state": "illiquidity_stress_state",
            "coverage_tickers": "illiquidity_coverage_tickers",
        }
    ).set_index("dt")
    proxy.index = pd.to_datetime(proxy.index).normalize()
    frame = srr.add_prefix("srr_").join(proxy, how="inner").sort_index()
    if frame.empty:
        raise RuntimeError("SRR-lite and daily illiquidity proxy frames have no overlapping dates")

    frame["illiquidity_watch_or_worse"] = _state_at_or_above(frame["illiquidity_stress_state"], "watch")
    frame["illiquidity_elevated_or_worse"] = _state_at_or_above(frame["illiquidity_stress_state"], "elevated")
    frame["illiquidity_stress"] = _state_at_or_above(frame["illiquidity_stress_state"], "stress")
    frame["srr_no_add_active"] = frame["srr_no_add_active"].fillna(False).astype(bool)
    frame["srr_crash_watch_active"] = frame["srr_crash_watch_active"].fillna(False).astype(bool)

    signals = {
        "illiquidity_watch_or_worse": frame["illiquidity_watch_or_worse"],
        "illiquidity_elevated_or_worse": frame["illiquidity_elevated_or_worse"],
        "illiquidity_stress": frame["illiquidity_stress"],
        "srr_no_add_active": frame["srr_no_add_active"],
        "srr_crash_watch_active": frame["srr_crash_watch_active"],
        "union_illiquidity_elevated_or_srr_no_add": frame["illiquidity_elevated_or_worse"]
        | frame["srr_no_add_active"],
        "intersection_illiquidity_elevated_and_srr_no_add": frame["illiquidity_elevated_or_worse"]
        & frame["srr_no_add_active"],
        "illiquidity_elevated_without_srr_no_add": frame["illiquidity_elevated_or_worse"]
        & ~frame["srr_no_add_active"],
        "srr_no_add_without_illiquidity_elevated": frame["srr_no_add_active"]
        & ~frame["illiquidity_elevated_or_worse"],
    }
    for name, signal in signals.items():
        frame[name] = signal.reindex(frame.index).fillna(False).astype(bool)

    overlap = {
        "illiquidity_elevated_vs_srr_no_add": _overlap_counts(
            frame["illiquidity_elevated_or_worse"], frame["srr_no_add_active"]
        ),
        "illiquidity_elevated_vs_srr_crash_watch": _overlap_counts(
            frame["illiquidity_elevated_or_worse"], frame["srr_crash_watch_active"]
        ),
        "illiquidity_watch_vs_srr_no_add": _overlap_counts(
            frame["illiquidity_watch_or_worse"], frame["srr_no_add_active"]
        ),
    }
    crash_alert = _load_json(crash_alert_path)
    blockers = [
        "daily_ohlcv_proxy_not_paper_equivalent",
        "overlap_is_research_only",
        "no_live_weight_change_allowed",
    ]
    illiq_summary = _signal_summary(frame, frame["illiquidity_elevated_or_worse"])
    srr_summary = _signal_summary(frame, frame["srr_no_add_active"])
    union_summary = _signal_summary(frame, frame["union_illiquidity_elevated_or_srr_no_add"])
    if (illiq_summary["h10"]["confusion"]["precision"] or 0.0) <= (srr_summary["h10"]["confusion"]["precision"] or 0.0):
        blockers.append("illiquidity_elevated_h10_precision_not_above_srr_no_add")
    if (union_summary["h10"]["confusion"]["false_positive_rate"] or 0.0) > (
        srr_summary["h10"]["confusion"]["false_positive_rate"] or 0.0
    ):
        blockers.append("union_with_illiquidity_increases_h10_false_positive_rate")

    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_illiquidity_daily_proxy_overlap",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_overlap_start": str(frame.index.min().date()),
        "actual_overlap_end": str(frame.index.max().date()),
        "rows": int(len(frame)),
        "policy": "research_only_illiquidity_proxy_overlap_no_weight_change",
        "status": "blocked",
        "inputs": {
            "db_path": str(db_path),
            "srr_frame": str(srr_frame_path),
            "crash_risk_alert": str(crash_alert_path),
            "crash_risk_alert_historical_scope": "latest_snapshot_only",
        },
        "summary": {
            name: _signal_summary(frame, signal)
            for name, signal in signals.items()
        },
        "overlap": overlap,
        "latest_alignment": _latest_alignment(frame, crash_alert),
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "incremental_signal_promotable": False,
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }
    return report, frame


def _history_path(history_dir: Path, as_of: str | None, actual_overlap_end: str | None) -> Path:
    stamp = str(as_of or actual_overlap_end or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"illiquidity_daily_proxy_overlap_{stamp}.json"


def write_overlap(
    report: dict[str, Any],
    frame: pd.DataFrame,
    output_path: Path,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame_output = output_path.with_name(output_path.stem + "_frame.csv")
    frame.to_csv(frame_output, encoding="utf-8-sig")
    report["frame_output"] = str(frame_output)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, report.get("as_of"), report.get("actual_overlap_end")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--srr-frame", default=str(DEFAULT_SRR_FRAME))
    parser.add_argument("--crash-risk-alert", default=str(DEFAULT_CRASH_ALERT))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report, frame = build_overlap(
        db_path=_resolve(args.db),
        srr_frame_path=_resolve(args.srr_frame),
        crash_alert_path=_resolve(args.crash_risk_alert),
        as_of=args.as_of,
    )
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_overlap(report, frame, _resolve(args.output), history_dir)
    compact = {
        "status": report["status"],
        "actual_overlap_end": report["actual_overlap_end"],
        "illiquidity_elevated_active_days": report["summary"]["illiquidity_elevated_or_worse"]["active_days"],
        "srr_no_add_active_days": report["summary"]["srr_no_add_active"]["active_days"],
        "jaccard_elevated_vs_srr_no_add": report["overlap"]["illiquidity_elevated_vs_srr_no_add"]["jaccard"],
        "incremental_signal_promotable": report["decision"]["incremental_signal_promotable"],
    }
    print(f"Illiquidity daily proxy overlap: {_resolve(args.output)}")
    print(json.dumps(compact, ensure_ascii=False))


if __name__ == "__main__":
    main()
