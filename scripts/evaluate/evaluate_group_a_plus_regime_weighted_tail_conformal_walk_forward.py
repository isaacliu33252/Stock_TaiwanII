#!/usr/bin/env python3
"""Walk-forward compare current tail conformal vs 2602.03903 TWC/RWC shadow.

Research-only. This script checks realized lower-tail breaches for 00631L.TW
and does not promote, block, or change production guard settings.
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

from group_a_plus.integrations.regime_weighted_tail_conformal import (  # noqa: E402
    DEFAULT_TARGET_TICKER,
    _calibration_weights,
    _prediction_from_past_labels as _weighted_prediction_from_past_labels,
    _regime_features,
    build_regime_weighted_tail_conformal_shadow,
    effective_sample_size,
    weighted_quantile,
)
from group_a_plus.integrations.tail_conformal import (  # noqa: E402
    _conformal_quantile,
    _forward_mdd,
    _prediction_from_past_labels,
    _risk_bucket,
    _walk_forward_aci_alpha,
    compute_tail_conformal_diagnostic,
)


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/regime_weighted_tail_conformal_walk_forward.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/regime_weighted_tail_conformal_walk_forward/history"
DEFAULT_YEARS = "2018,2020,2022,2024,2025,2026"
HORIZONS = ("h5", "h10")
STATIC_CALIBRATION_WINDOW = 252
WEIGHTED_CALIBRATION_WINDOW = 504
MIN_CALIBRATION = 120


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _load_close(db_path: Path, ticker: str, start: str, end: str | None) -> pd.Series:
    params: list[Any] = [ticker, start]
    end_clause = ""
    if end:
        end_clause = "AND dt <= ?"
        params.append(end)
    query = f"""
        SELECT dt, close
        FROM ohlcv
        WHERE ticker = ?
          AND dt >= ?
          {end_clause}
        ORDER BY dt
    """
    with duckdb.connect(str(db_path), read_only=True) as conn:
        rows = conn.execute(query, params).fetchdf()
    if rows.empty:
        return pd.Series(dtype=float)
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    return rows.set_index("dt")["close"].astype(float).sort_index()


def _selected_dates(close: pd.Series, years: set[int], end: str | None) -> list[pd.Timestamp]:
    dates = [pd.Timestamp(dt) for dt in close.index if pd.Timestamp(dt).year in years]
    if end:
        cutoff = pd.Timestamp(end)
        dates = [dt for dt in dates if dt <= cutoff]
    latest_with_h10_outcome = close.index[-11] if len(close) > 11 else close.index[-1]
    return [dt for dt in dates if dt <= latest_with_h10_outcome]


def _actual_forward_return(close: pd.Series, dt: pd.Timestamp, horizon: int) -> float | None:
    if dt not in close.index:
        return None
    pos = close.index.get_loc(dt)
    if not isinstance(pos, int) or pos + horizon >= len(close):
        return None
    start = float(close.iloc[pos])
    end = float(close.iloc[pos + horizon])
    return end / start - 1.0 if start else None


def _actual_forward_mdd(close: pd.Series, dt: pd.Timestamp, horizon: int) -> float | None:
    if dt not in close.index:
        return None
    pos = close.index.get_loc(dt)
    if not isinstance(pos, int) or pos + horizon >= len(close):
        return None
    start = float(close.iloc[pos])
    future = close.iloc[pos + 1 : pos + horizon + 1].astype(float)
    if not start or future.empty:
        return None
    return float(future.min() / start - 1.0)


def _append_row(
    rows: list[dict[str, Any]],
    *,
    close: pd.Series,
    dt: pd.Timestamp,
    method: str,
    horizon: int,
    lower_tail_bound: float | None,
    tail_high: bool,
    effective_sample_size_value: float | None,
    weight_mode: str | None,
) -> None:
    actual = _actual_forward_return(close, dt, horizon)
    mdd = _actual_forward_mdd(close, dt, horizon)
    if lower_tail_bound is None or actual is None or mdd is None:
        return
    rows.append(
        {
            "date": str(dt.date()),
            "year": int(dt.year),
            "method": method,
            "horizon": f"h{horizon}",
            "lower_tail_bound": float(lower_tail_bound),
            "actual_forward_return": float(actual),
            "actual_forward_mdd": float(mdd),
            "breach": bool(actual < float(lower_tail_bound)),
            "severe_mdd_8pct": bool(mdd <= -0.08),
            "tail_high": bool(tail_high),
            "effective_sample_size": effective_sample_size_value,
            "weight_mode": weight_mode,
        }
    )


def _weighted_conformal_level(alpha: float, weights: pd.Series) -> float:
    total = float(weights.sum())
    if total <= 0.0:
        return 1.0 - alpha
    return min(1.0, (1.0 - alpha) * (1.0 + 1.0 / total))


def _append_existing_rows_fast(
    rows: list[dict[str, Any]],
    *,
    close: pd.Series,
    dates: list[pd.Timestamp],
    adaptive: bool,
    alpha: float = 0.10,
) -> None:
    method = "existing_aci_gamma_0_005" if adaptive else "existing_static_bucket"
    bucket = _risk_bucket(close)
    for horizon in (5, 10):
        fwd_ret = close.shift(-horizon) / close - 1.0
        fwd_mdd = _forward_mdd(close, horizon)
        pred = _prediction_from_past_labels(fwd_ret, horizon, STATIC_CALIBRATION_WINDOW, 80)
        residual = pred - fwd_ret
        aci_alpha = (
            _walk_forward_aci_alpha(
                residual,
                base_alpha=alpha,
                gamma=0.005,
                min_alpha=0.02,
                max_alpha=0.40,
                calibration_window=STATIC_CALIBRATION_WINDOW,
                warmup=80,
            )
            if adaptive
            else pd.Series(dtype=float)
        )
        for dt in dates:
            known_cutoff = dt - pd.Timedelta(days=horizon)
            eligible = residual.index <= known_cutoff
            if adaptive:
                alpha_hist = aci_alpha.loc[aci_alpha.index <= known_cutoff].dropna()
                effective_alpha = float(alpha_hist.iloc[-1]) if len(alpha_hist) else alpha
                cal_resid = residual[eligible].tail(STATIC_CALIBRATION_WINDOW)
                cal_mdd = fwd_mdd[eligible].tail(STATIC_CALIBRATION_WINDOW)
                weight_mode = "aci_adaptive_no_bucket"
            else:
                current_bucket = str(bucket.loc[dt]) if dt in bucket.index else "normal"
                bucket_match = bucket == current_bucket
                cal_resid = residual[eligible & bucket_match].tail(STATIC_CALIBRATION_WINDOW)
                cal_mdd = fwd_mdd[eligible & bucket_match].tail(STATIC_CALIBRATION_WINDOW)
                weight_mode = current_bucket
                if len(cal_resid.dropna()) < 80:
                    cal_resid = residual[eligible].tail(STATIC_CALIBRATION_WINDOW)
                    cal_mdd = fwd_mdd[eligible].tail(STATIC_CALIBRATION_WINDOW)
                    weight_mode = "all_buckets_fallback"
                effective_alpha = alpha
            if len(cal_resid.dropna()) < 80:
                continue
            q_resid = _conformal_quantile(cal_resid, effective_alpha)
            pred_hist = pred.loc[pred.index <= dt].dropna()
            if q_resid is None or pred_hist.empty:
                continue
            lower = float(pred_hist.iloc[-1]) - float(q_resid)
            mdd_clean = pd.to_numeric(cal_mdd, errors="coerce").dropna()
            mdd_prob = float((mdd_clean <= -0.08).mean()) if len(mdd_clean) else 0.0
            _append_row(
                rows,
                close=close,
                dt=dt,
                method=method,
                horizon=horizon,
                lower_tail_bound=lower,
                tail_high=lower <= -0.08 or mdd_prob >= 0.35,
                effective_sample_size_value=None,
                weight_mode=weight_mode,
            )


def _append_weighted_rows_fast(
    rows: list[dict[str, Any]],
    *,
    close: pd.Series,
    dates: list[pd.Timestamp],
    method: str,
    use_regime_kernel: bool,
    alpha: float = 0.10,
    calibration_window: int = WEIGHTED_CALIBRATION_WINDOW,
    min_calibration: int = MIN_CALIBRATION,
    half_life: float = 126.0,
    bandwidth: float = 1.0,
    min_effective_sample_size: int = 60,
) -> None:
    features = _regime_features(close)
    for horizon in (5, 10):
        fwd_ret = close.shift(-horizon) / close - 1.0
        pred = _weighted_prediction_from_past_labels(fwd_ret, horizon, calibration_window, min_calibration)
        residual = pred - fwd_ret
        for dt in dates:
            known_cutoff = dt - pd.Timedelta(days=horizon)
            cal_resid = residual[residual.index <= known_cutoff].dropna().tail(calibration_window)
            if len(cal_resid) < min_calibration:
                continue
            weights, weight_diag = _calibration_weights(
                close=close.loc[close.index <= dt],
                calibration_index=cal_resid.index,
                target_dt=dt,
                half_life=half_life,
                bandwidth=bandwidth,
                min_effective_sample_size=min_effective_sample_size,
                use_regime_kernel=use_regime_kernel,
                features=features,
            )
            level = _weighted_conformal_level(alpha, weights)
            buffer = weighted_quantile(cal_resid, weights, level)
            pred_hist = pred.loc[pred.index <= dt].dropna()
            if buffer is None or pred_hist.empty:
                continue
            lower = float(pred_hist.iloc[-1]) - float(buffer)
            _append_row(
                rows,
                close=close,
                dt=dt,
                method=method,
                horizon=horizon,
                lower_tail_bound=lower,
                tail_high=lower <= -0.08,
                effective_sample_size_value=weight_diag.get("effective_sample_size"),
                weight_mode=weight_diag.get("mode"),
            )


def _append_existing_rows(
    rows: list[dict[str, Any]],
    *,
    db_path: Path,
    close: pd.Series,
    dates: list[pd.Timestamp],
    adaptive: bool,
) -> None:
    method = "existing_aci_gamma_0_005" if adaptive else "existing_static_bucket"
    for dt in dates:
        diag = compute_tail_conformal_diagnostic(db_path=db_path, actual_date=dt, adaptive=adaptive, aci_gamma=0.005)
        if diag.get("status") != "ok":
            continue
        for key in HORIZONS:
            horizon = int(key[1:])
            h = (diag.get("diagnostics") or {}).get(key) or {}
            bound = h.get("lower_tail_confidence_bound")
            _append_row(
                rows,
                close=close,
                dt=dt,
                method=method,
                horizon=horizon,
                lower_tail_bound=float(bound) if bound is not None else None,
                tail_high=bool(diag.get("state") == "TAIL_RISK_HIGH"),
                effective_sample_size_value=None,
                weight_mode=h.get("calibration_scope"),
            )


def _append_weighted_rows(
    rows: list[dict[str, Any]],
    *,
    close: pd.Series,
    dates: list[pd.Timestamp],
    method: str,
    use_regime_kernel: bool,
) -> None:
    for dt in dates:
        report = build_regime_weighted_tail_conformal_shadow(
            close=close.loc[close.index <= dt],
            as_of=str(dt.date()),
            use_regime_kernel=use_regime_kernel,
        )
        if report.get("status") != "ok":
            continue
        for key in HORIZONS:
            horizon = int(key[1:])
            h = (report.get("diagnostics") or {}).get(key) or {}
            if h.get("status") != "ok":
                continue
            bound = h.get("lower_tail_confidence_bound")
            weight_diag = h.get("weight_diagnostics") or {}
            _append_row(
                rows,
                close=close,
                dt=dt,
                method=method,
                horizon=horizon,
                lower_tail_bound=float(bound) if bound is not None else None,
                tail_high=bool((report.get("summary") or {}).get("state") == "TAIL_RISK_SHADOW_HIGH"),
                effective_sample_size_value=weight_diag.get("effective_sample_size"),
                weight_mode=weight_diag.get("mode"),
            )


def _summarize(rows: list[dict[str, Any]], alpha: float) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"status": "unavailable", "reason": "no_rows"}
    summary: dict[str, Any] = {}
    for (method, horizon), group in frame.groupby(["method", "horizon"]):
        rows_n = int(len(group))
        breaches = int(group["breach"].sum())
        breach_rate = _safe_rate(breaches, rows_n)
        summary[f"{method}:{horizon}"] = {
            "method": method,
            "horizon": horizon,
            "rows": rows_n,
            "breaches": breaches,
            "alpha": float(alpha),
            "breach_rate": breach_rate,
            "breach_rate_minus_alpha": None if breach_rate is None else breach_rate - alpha,
            "absolute_calibration_error": None if breach_rate is None else abs(breach_rate - alpha),
            "tail_high_rate": _safe_rate(int(group["tail_high"].sum()), rows_n),
            "mean_lower_tail_bound": float(group["lower_tail_bound"].mean()),
            "mean_effective_sample_size": None
            if group["effective_sample_size"].dropna().empty
            else float(group["effective_sample_size"].dropna().mean()),
            "by_year": {
                str(year): {
                    "rows": int(len(year_group)),
                    "breach_rate": _safe_rate(int(year_group["breach"].sum()), int(len(year_group))),
                    "tail_high_rate": _safe_rate(int(year_group["tail_high"].sum()), int(len(year_group))),
                }
                for year, year_group in group.groupby("year")
            },
        }
    return summary


def _side_summary(group: pd.DataFrame) -> dict[str, Any]:
    rows_n = int(len(group))
    if rows_n == 0:
        return {
            "rows": 0,
            "mean_forward_return": None,
            "median_forward_return": None,
            "mean_forward_mdd": None,
            "severe_mdd_8pct_rate": None,
            "negative_forward_return_rate": None,
            "breach_rate": None,
        }
    return {
        "rows": rows_n,
        "mean_forward_return": float(group["actual_forward_return"].mean()),
        "median_forward_return": float(group["actual_forward_return"].median()),
        "mean_forward_mdd": float(group["actual_forward_mdd"].mean()),
        "severe_mdd_8pct_rate": _safe_rate(int(group["severe_mdd_8pct"].sum()), rows_n),
        "negative_forward_return_rate": _safe_rate(int((group["actual_forward_return"] < 0.0).sum()), rows_n),
        "breach_rate": _safe_rate(int(group["breach"].sum()), rows_n),
    }


def _warning_cost(rows: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"status": "unavailable", "reason": "no_rows"}
    out: dict[str, Any] = {}
    for (method, horizon), group in frame.groupby(["method", "horizon"]):
        high = group[group["tail_high"]]
        normal = group[~group["tail_high"]]
        high_summary = _side_summary(high)
        normal_summary = _side_summary(normal)
        severe_lift = None
        if high_summary["severe_mdd_8pct_rate"] is not None and normal_summary["severe_mdd_8pct_rate"] is not None:
            severe_lift = high_summary["severe_mdd_8pct_rate"] - normal_summary["severe_mdd_8pct_rate"]
        return_spread = None
        if high_summary["mean_forward_return"] is not None and normal_summary["mean_forward_return"] is not None:
            return_spread = high_summary["mean_forward_return"] - normal_summary["mean_forward_return"]
        out[f"{method}:{horizon}"] = {
            "method": method,
            "horizon": horizon,
            "tail_high": high_summary,
            "tail_normal": normal_summary,
            "tail_high_minus_normal_mean_forward_return": return_spread,
            "tail_high_minus_normal_severe_mdd_8pct_rate": severe_lift,
            "interpretation": (
                "Positive severe-mdd lift and negative return spread mean the warning "
                "selects worse forward windows; high row count is the opportunity cost."
            ),
        }
    return out


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    years = {int(part.strip()) for part in str(args.years).split(",") if part.strip()}
    close = _load_close(db_path, args.ticker, args.start, args.end)
    dates = _selected_dates(close, years, args.end)
    if args.max_dates and len(dates) > args.max_dates:
        step = max(1, len(dates) // int(args.max_dates))
        dates = dates[::step][: int(args.max_dates)]

    rows: list[dict[str, Any]] = []
    if args.slow_reference:
        _append_existing_rows(rows, db_path=db_path, close=close, dates=dates, adaptive=False)
        _append_existing_rows(rows, db_path=db_path, close=close, dates=dates, adaptive=True)
        _append_weighted_rows(rows, close=close, dates=dates, method="paper_2602_twc", use_regime_kernel=False)
        _append_weighted_rows(rows, close=close, dates=dates, method="paper_2602_rwc", use_regime_kernel=True)
        replay_mode = "slow_reference_per_date"
    else:
        _append_existing_rows_fast(rows, close=close, dates=dates, adaptive=False)
        _append_existing_rows_fast(rows, close=close, dates=dates, adaptive=True)
        _append_weighted_rows_fast(rows, close=close, dates=dates, method="paper_2602_twc", use_regime_kernel=False)
        _append_weighted_rows_fast(rows, close=close, dates=dates, method="paper_2602_rwc", use_regime_kernel=True)
        replay_mode = "fast_vectorized_single_close_load"

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_regime_weighted_tail_conformal_walk_forward",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "walk_forward_shadow_only_no_weight_change_no_guard_promotion",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2602.03903.pdf",
            "title": "Taming Tail Risk in Financial Markets: Conformal Calibration for Nonstationary Portfolio VaR",
        },
        "inputs": {
            "db": str(db_path),
            "ticker": args.ticker,
            "start": args.start,
            "end": args.end,
            "years": sorted(years),
            "date_count": int(len(dates)),
            "sampled_max_dates": args.max_dates,
            "replay_mode": replay_mode,
        },
        "summary": _summarize(rows, alpha=0.10),
        "warning_cost": _warning_cost(rows),
        "rows_preview": rows[:40],
        "decision": {
            "creates_orders": False,
            "changes_target_weights": False,
            "blocks_trades": False,
            "production_guard_changed": False,
            "promotion_ready": False,
            "promotion_blocker": "needs_review_of_walk_forward_calibration_and_warning_cost",
        },
    }


def _write_report(report: dict[str, Any], output: Path, history_dir: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_path = history_dir / f"regime_weighted_tail_conformal_walk_forward_{stamp}.json"
    history_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--ticker", default=DEFAULT_TARGET_TICKER)
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-08-07")
    parser.add_argument("--years", default=DEFAULT_YEARS)
    parser.add_argument("--max-dates", type=int, default=0)
    parser.add_argument("--slow-reference", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    _write_report(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps({"status": report["status"], "date_count": report["inputs"]["date_count"], "output": str(_resolve(args.output))}))


if __name__ == "__main__":
    main()
