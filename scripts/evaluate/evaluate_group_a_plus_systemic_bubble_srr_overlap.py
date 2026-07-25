#!/usr/bin/env python3
"""Evaluate systemic bubble time-at-risk overlap with SRR-lite labels.

Research-only. This turns the latest-only systemic bubble time-at-risk proxy
into a historical daily frame and compares it with SRR-lite forward no-add
labels. It does not change live signals, target weights, or strategy manifests.
"""

from __future__ import annotations

import argparse
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

from scripts.evaluate.evaluate_group_a_plus_systemic_bubble_time_at_risk_review import (  # noqa: E402
    DB_PATH,
    DEFAULT_TICKERS,
    _load_panel,
)


DEFAULT_DB = DB_PATH
DEFAULT_SRR_FRAME = PROJECT_ROOT / "results/srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/systemic_bubble_srr_overlap.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/systemic_bubble_srr_overlap/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _state_from_score(score: int) -> str:
    if score >= 2:
        return "elevated"
    if score == 1:
        return "watch"
    return "normal"


def _rolling_pct_rank(series: pd.Series, window: int = 252, min_periods: int = 80) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(window, min_periods=min_periods).rank(pct=True)


def _row_state(score: int) -> str:
    if pd.isna(score):
        return "research_watch"
    return "blocked_for_leverage_add" if int(score) >= 2 else "research_watch"


def build_systemic_daily_frame(panel: pd.DataFrame) -> pd.DataFrame:
    close = panel["close"]
    volume = panel["volume"]
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    returns = returns.dropna(subset=["0050.TW", "00631L.TW"])
    dates = returns.index

    ret_00631l = returns["00631L.TW"]
    ret_0050 = returns["0050.TW"]
    vol20 = (ret_00631l.rolling(20, min_periods=10).std() * np.sqrt(252.0)).reindex(dates)
    vol60 = (ret_00631l.rolling(60, min_periods=30).std() * np.sqrt(252.0)).reindex(dates)
    ret60 = close["0050.TW"].pct_change(60).reindex(dates)
    ma_gap = (close["0050.TW"] / close["0050.TW"].rolling(120, min_periods=60).mean() - 1.0).reindex(
        dates
    )
    accel = (ret60 - close["0050.TW"].pct_change(120).reindex(dates)).reindex(dates)
    ret60_pct = _rolling_pct_rank(ret60, 252, 80)
    vol20_pct = _rolling_pct_rank(vol20, 252, 80)
    fragile = (((vol20_pct >= 0.80) & (ma_gap > 0.08)) | ((ret60_pct >= 0.85) & (accel > 0.0))).fillna(False)
    time_at_risk_days_60 = fragile.astype(int).rolling(60, min_periods=1).sum()

    corr_0050_00631l_60 = returns["0050.TW"].rolling(60, min_periods=30).corr(returns["00631L.TW"])
    corr_0050_00632r_60 = (
        returns["0050.TW"].rolling(60, min_periods=30).corr(returns["00632R.TW"])
        if "00632R.TW" in returns
        else pd.Series(index=dates, dtype=float)
    )
    corr_2330_0050_60 = (
        returns["2330.TW"].rolling(60, min_periods=30).corr(returns["0050.TW"])
        if "2330.TW" in returns
        else pd.Series(index=dates, dtype=float)
    )
    coupling_score = pd.concat(
        [corr_0050_00631l_60.abs(), corr_0050_00632r_60.abs(), corr_2330_0050_60.abs()],
        axis=1,
    ).mean(axis=1, skipna=True)
    coupling_pct = _rolling_pct_rank(coupling_score, 252, 80)

    volume_z = (
        (volume["00631L.TW"].reindex(returns.index) - volume["00631L.TW"].rolling(60, min_periods=30).mean())
        / volume["00631L.TW"].rolling(60, min_periods=30).std()
    ).replace([np.inf, -np.inf], np.nan).reindex(dates)
    absret_z = (
        (ret_00631l.abs() - ret_00631l.abs().rolling(60, min_periods=30).mean())
        / ret_00631l.abs().rolling(60, min_periods=30).std()
    ).replace([np.inf, -np.inf], np.nan).reindex(dates)
    same_direction = (np.sign(ret_00631l) == np.sign(ret_0050)).astype(float).rolling(20, min_periods=10).mean()
    same_direction = same_direction.reindex(dates)
    reflexivity_proxy = pd.concat([volume_z.clip(lower=0), absret_z.clip(lower=0), same_direction], axis=1).mean(
        axis=1,
        skipna=True,
    )
    reflexivity_pct = _rolling_pct_rank(reflexivity_proxy, 252, 80)

    high_time_at_risk = (time_at_risk_days_60 >= 20) | (vol20_pct >= 0.85)
    high_ma_extension = ma_gap >= 0.10
    high_coupling = coupling_score >= 0.75
    high_reflexivity = reflexivity_pct >= 0.80

    time_score = high_time_at_risk.astype(int) + high_ma_extension.astype(int)
    coupling_score_count = high_coupling.astype(int) + (coupling_pct >= 0.80).astype(int)
    reflexivity_score_count = (
        high_reflexivity.astype(int) + (volume_z >= 2.0).astype(int) + (absret_z >= 2.0).astype(int)
    )
    coupling_state = coupling_score_count.map(_state_from_score)
    reflexivity_state = reflexivity_score_count.map(_state_from_score)
    systemic_score = (
        (time_score >= 1).astype(int)
        + (coupling_state == "elevated").astype(int)
        + (reflexivity_state == "elevated").astype(int)
    ).fillna(0).astype(int)

    frame = pd.DataFrame(
        {
            "date": pd.Series(dates, index=dates),
            "00631l_vol20_ann": vol20.reindex(dates),
            "00631l_vol20_percentile_252d": vol20_pct.reindex(dates),
            "00631l_vol20_vs_vol60_ratio": (vol20 / vol60.replace(0.0, np.nan)).reindex(dates),
            "0050_return_60d": ret60.reindex(dates),
            "0050_ma120_gap": ma_gap.reindex(dates),
            "time_at_risk_days_60": time_at_risk_days_60.reindex(dates),
            "0050_00631l_corr_60d": corr_0050_00631l_60.reindex(dates),
            "0050_00632r_corr_60d": corr_0050_00632r_60.reindex(dates),
            "2330_0050_corr_60d": corr_2330_0050_60.reindex(dates),
            "etf_coupling_score": coupling_score.reindex(dates),
            "etf_coupling_percentile_252d": coupling_pct.reindex(dates),
            "00631l_volume_z_60d": volume_z.reindex(dates),
            "00631l_abs_return_z_60d": absret_z.reindex(dates),
            "reflexivity_proxy_score": reflexivity_proxy.reindex(dates),
            "reflexivity_proxy_percentile_252d": reflexivity_pct.reindex(dates),
            "time_at_risk_state": time_score.map(_state_from_score).reindex(dates),
            "etf_coupling_state": coupling_state.reindex(dates),
            "reflexivity_proxy_state": reflexivity_state.reindex(dates),
            "systemic_score": systemic_score.reindex(dates),
            "overall_state": systemic_score.map(_row_state).reindex(dates),
        }
    ).dropna(subset=["systemic_score"])
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame.sort_values("date").reset_index(drop=True)


def _read_srr_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    frame.index = pd.to_datetime(frame.index).normalize()
    return frame


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
    ret_col = f"forward_ret_00631l_h{horizon}"
    rel_col = f"forward_rel_00631l_vs_0050_h{horizon}"
    mdd_col = f"forward_mdd_00631l_h{horizon}"
    label_col = f"no_add_label_h{horizon}"
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
    either = a | b
    return {
        "a_active_days": int(a.sum()),
        "b_active_days": int(b.sum()),
        "both_active_days": int(both.sum()),
        "a_only_days": int((a & ~b).sum()),
        "b_only_days": int((b & ~a).sum()),
        "either_active_days": int(either.sum()),
        "a_overlap_share": _safe_rate(int(both.sum()), int(a.sum())),
        "b_overlap_share": _safe_rate(int(both.sum()), int(b.sum())),
        "jaccard": _safe_rate(int(both.sum()), int(either.sum())),
    }


def build_overlap_report(
    *,
    db_path: Path = DEFAULT_DB,
    srr_frame_path: Path = DEFAULT_SRR_FRAME,
    as_of: str | None = "2026-07-20",
    start: str = "2015-01-05",
) -> tuple[dict[str, Any], pd.DataFrame]:
    srr = _read_srr_frame(srr_frame_path)
    end = as_of or str(pd.Timestamp(srr.index.max()).date())
    panel = _load_panel(db_path, DEFAULT_TICKERS, start, end)
    systemic = build_systemic_daily_frame(panel).set_index("date")
    frame = srr.join(systemic.add_prefix("systemic_"), how="inner").sort_index()
    if frame.empty:
        raise RuntimeError("SRR-lite and systemic bubble daily frames have no overlapping dates")

    frame["srr_no_add_active"] = frame["no_add_active"].fillna(False).astype(bool)
    frame["systemic_watch_or_worse"] = (pd.to_numeric(frame["systemic_systemic_score"], errors="coerce") >= 1).fillna(
        False
    )
    frame["systemic_blocked_for_leverage_add"] = (
        pd.to_numeric(frame["systemic_systemic_score"], errors="coerce") >= 2
    ).fillna(False)
    frame["systemic_time_at_risk_watch"] = frame["systemic_time_at_risk_state"].isin(["watch", "elevated"])
    frame["systemic_coupling_elevated"] = frame["systemic_etf_coupling_state"].eq("elevated")
    frame["systemic_reflexivity_elevated"] = frame["systemic_reflexivity_proxy_state"].eq("elevated")

    signals = {
        "srr_no_add_active": frame["srr_no_add_active"],
        "systemic_watch_or_worse": frame["systemic_watch_or_worse"],
        "systemic_blocked_for_leverage_add": frame["systemic_blocked_for_leverage_add"],
        "systemic_time_at_risk_watch": frame["systemic_time_at_risk_watch"],
        "systemic_coupling_elevated": frame["systemic_coupling_elevated"],
        "systemic_reflexivity_elevated": frame["systemic_reflexivity_elevated"],
        "systemic_time_watch_and_coupling_elevated": frame["systemic_time_at_risk_watch"]
        & frame["systemic_coupling_elevated"],
        "systemic_time_watch_and_reflexivity_elevated": frame["systemic_time_at_risk_watch"]
        & frame["systemic_reflexivity_elevated"],
        "srr_confirmed_by_systemic_blocked": frame["srr_no_add_active"]
        & frame["systemic_blocked_for_leverage_add"],
        "union_srr_or_systemic_watch": frame["srr_no_add_active"] | frame["systemic_watch_or_worse"],
        "intersection_srr_and_systemic_watch": frame["srr_no_add_active"] & frame["systemic_watch_or_worse"],
        "systemic_watch_without_srr": frame["systemic_watch_or_worse"] & ~frame["srr_no_add_active"],
        "srr_without_systemic_watch": frame["srr_no_add_active"] & ~frame["systemic_watch_or_worse"],
    }
    for name, signal in signals.items():
        frame[name] = signal.reindex(frame.index).fillna(False).astype(bool)

    summary = {name: _signal_summary(frame, signal) for name, signal in signals.items()}
    overlap = {
        "systemic_watch_vs_srr_no_add": _overlap_counts(
            frame["systemic_watch_or_worse"], frame["srr_no_add_active"]
        ),
        "systemic_blocked_vs_srr_no_add": _overlap_counts(
            frame["systemic_blocked_for_leverage_add"], frame["srr_no_add_active"]
        ),
    }

    blockers = [
        "systemic_bubble_overlap_research_only",
        "systemic_bubble_proxy_not_paper_equivalent",
        "no_live_weight_change_allowed",
    ]
    srr_h10 = summary["srr_no_add_active"]["h10"]["confusion"]
    systemic_h10 = summary["systemic_watch_or_worse"]["h10"]["confusion"]
    union_h10 = summary["union_srr_or_systemic_watch"]["h10"]["confusion"]
    if (systemic_h10.get("precision") or 0.0) <= (srr_h10.get("precision") or 0.0):
        blockers.append("systemic_watch_h10_precision_not_above_srr_no_add")
    if (union_h10.get("false_positive_rate") or 0.0) > (srr_h10.get("false_positive_rate") or 0.0) + 0.03:
        blockers.append("union_with_systemic_watch_raises_h10_false_positive_rate")
    strict_h10 = summary["systemic_time_watch_and_coupling_elevated"]["h10"]["confusion"]
    if int(strict_h10.get("active_days") or 0) < 20:
        blockers.append("strict_systemic_confirmation_sample_too_small")

    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_systemic_bubble_srr_overlap",
        "status": "blocked",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_overlap_start": str(frame.index.min().date()),
        "actual_overlap_end": str(frame.index.max().date()),
        "rows": int(len(frame)),
        "policy": "research_only_systemic_bubble_srr_overlap_no_weight_change",
        "inputs": {
            "db_path": str(db_path),
            "srr_frame": str(srr_frame_path),
            "daily_frame_source": "recomputed_from_systemic_bubble_time_at_risk_proxy",
        },
        "summary": summary,
        "overlap": overlap,
        "blocking_reasons": sorted(set(blockers)),
        "candidate_improvement": {
            "signal": "systemic_time_watch_and_coupling_elevated",
            "use_case": "manual_review_confirmation_only",
            "h10_confusion": strict_h10,
            "rationale": (
                "Combining time-at-risk watch with elevated ETF coupling reduces false positives, "
                "but the active sample is too small to promote into a live no-add gate."
            ),
        },
        "decision": {
            "incremental_signal_promotable": False,
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "interpretation": (
            "Systemic bubble time-at-risk can remain a governance dashboard. It should not widen SRR-lite "
            "unless it improves precision or adds high-quality missed no-add dates without materially raising FPR."
        ),
    }
    return report, frame


def _history_path(history_dir: Path, as_of: str | None, actual_overlap_end: str | None) -> Path:
    stamp = str(as_of or actual_overlap_end or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"systemic_bubble_srr_overlap_{stamp}.json"


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
    parser.add_argument("--as-of", default="2026-07-20")
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    report, frame = build_overlap_report(
        db_path=_resolve(args.db),
        srr_frame_path=_resolve(args.srr_frame),
        as_of=args.as_of,
        start=args.start,
    )
    write_overlap(report, frame, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    compact = {
        "status": report["status"],
        "actual_overlap_end": report["actual_overlap_end"],
        "systemic_watch_active_days": report["summary"]["systemic_watch_or_worse"]["active_days"],
        "systemic_blocked_active_days": report["summary"]["systemic_blocked_for_leverage_add"]["active_days"],
        "srr_no_add_active_days": report["summary"]["srr_no_add_active"]["active_days"],
        "systemic_watch_h10_precision": report["summary"]["systemic_watch_or_worse"]["h10"]["confusion"][
            "precision"
        ],
        "systemic_watch_h10_fpr": report["summary"]["systemic_watch_or_worse"]["h10"]["confusion"][
            "false_positive_rate"
        ],
        "incremental_signal_promotable": report["decision"]["incremental_signal_promotable"],
    }
    print(f"Systemic bubble/SRR overlap: {_resolve(args.output)}")
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
