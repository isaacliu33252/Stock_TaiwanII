#!/usr/bin/env python3
"""Lightweight multi-scale volatility-regime shadow evaluator for GroupA+.

Research-only implementation inspired by the multi-scale MS-GARCH paper
2606.06190v1. This is not a full Markov-Switching GARCH implementation. It
uses causal rolling realized-volatility percentiles at 5/20/60 day scales to
approximate Calm/Turbulent/Crisis regimes, then evaluates whether the resulting
cross-scale states help 00631L no-add/crash review.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "multi_scale_vol_regime_shadow_20250102_20260716.json"


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


def _load_close_panel(db_path: Path, symbols: tuple[str, ...], start: str, end: str, warmup_days: int) -> pd.DataFrame:
    start_ts = pd.Timestamp(start).normalize() - pd.Timedelta(days=warmup_days)
    end_ts = pd.Timestamp(end).normalize()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?))
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [list(symbols), str(start_ts.date()), str(end_ts.date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No close data for {symbols} from {start_ts.date()} to {end_ts.date()}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    return rows.pivot(index="dt", columns="ticker", values="close").sort_index().astype(float)


def _rolling_percentile_latest(window: pd.Series) -> float:
    clean = pd.to_numeric(window, errors="coerce").dropna()
    if clean.empty:
        return float("nan")
    return float((clean <= clean.iloc[-1]).mean())


def _regime_from_percentile(value: float) -> str:
    if not np.isfinite(value):
        return "Unknown"
    if value < 0.50:
        return "Calm"
    if value < 0.85:
        return "Turbulent"
    return "Crisis"


def _regime_code(value: str) -> int:
    return {"Calm": 0, "Turbulent": 1, "Crisis": 2}.get(value, -1)


def _state_entropy(states: list[str]) -> float:
    codes = [state for state in states if state in {"Calm", "Turbulent", "Crisis"}]
    if not codes:
        return float("nan")
    counts = pd.Series(codes).value_counts(normalize=True).to_numpy(dtype=float)
    entropy = -float(np.sum(counts * np.log(counts)))
    return entropy / float(np.log(3.0))


def _forward_min_drawdown(close: pd.Series, horizon: int) -> pd.Series:
    future = pd.concat([close.shift(-step) for step in range(1, horizon + 1)], axis=1)
    return future.min(axis=1) / close - 1.0


def _score_forward_summary(frame: pd.DataFrame, signal: pd.Series, horizon: int) -> dict[str, Any]:
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


def _summarize_signal(frame: pd.DataFrame, signal: pd.Series) -> dict[str, Any]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    return {
        "active_days": int(signal.sum()),
        "active_dates": [str(pd.Timestamp(dt).date()) for dt in frame.index[signal]],
        "h5": _score_forward_summary(frame, signal, 5),
        "h10": _score_forward_summary(frame, signal, 10),
    }


def _brier_skill_score(prob: pd.Series, label: pd.Series) -> dict[str, Any]:
    valid = prob.notna() & label.notna()
    if int(valid.sum()) == 0:
        return {"rows": 0, "brier": None, "reference_brier": None, "brier_skill_score": None}
    p = prob[valid].clip(0.0, 1.0).astype(float)
    y = label[valid].astype(float)
    base = float(y.mean())
    brier = float(((p - y) ** 2).mean())
    ref = float(((base - y) ** 2).mean())
    return {
        "rows": int(valid.sum()),
        "event_rate": base,
        "brier": brier,
        "reference_brier": ref,
        "brier_skill_score": None if ref <= 1e-12 else float(1.0 - brier / ref),
    }


def _build_vol_frame(
    prices: pd.DataFrame,
    *,
    start: str,
    end: str,
    vol_symbol: str,
    percentile_window: int,
) -> pd.DataFrame:
    close = prices[vol_symbol].astype(float)
    ret = close.pct_change(fill_method=None)
    vol = {
        "short": ret.rolling(5, min_periods=4).std(ddof=0),
        "medium": ret.rolling(20, min_periods=10).std(ddof=0),
        "long": ret.rolling(60, min_periods=30).std(ddof=0),
    }
    rows: list[dict[str, Any]] = []
    for scale, series in vol.items():
        pct = series.rolling(percentile_window, min_periods=min(60, percentile_window)).apply(
            _rolling_percentile_latest,
            raw=False,
        )
        rows.append(pd.DataFrame({f"{scale}_vol": series, f"{scale}_vol_percentile": pct}))
    frame = pd.concat(rows, axis=1)
    for scale in ("short", "medium", "long"):
        frame[f"{scale}_regime"] = frame[f"{scale}_vol_percentile"].map(_regime_from_percentile)
        frame[f"{scale}_regime_code"] = frame[f"{scale}_regime"].map(_regime_code)
    frame = frame.loc[pd.Timestamp(start).normalize() : pd.Timestamp(end).normalize()].copy()
    entropies: list[float] = []
    disagreements: list[float] = []
    crisis_scores: list[float] = []
    for _, row in frame.iterrows():
        states = [str(row[f"{scale}_regime"]) for scale in ("short", "medium", "long")]
        codes = [code for code in (_regime_code(state) for state in states) if code >= 0]
        entropies.append(_state_entropy(states))
        disagreements.append(float(np.std(codes) / 2.0) if codes else float("nan"))
        crisis_scores.append(float(sum(state == "Crisis" for state in states) / 3.0))
    frame["regime_entropy"] = entropies
    frame["cross_scale_disagreement"] = disagreements
    frame["crisis_probability_proxy"] = crisis_scores
    frame["all_crisis_active"] = (
        frame["short_regime"].eq("Crisis") & frame["medium_regime"].eq("Crisis") & frame["long_regime"].eq("Crisis")
    )
    frame["synchronized_turbulence_active"] = (
        frame["short_regime_code"].ge(1) & frame["medium_regime_code"].ge(1) & frame["long_regime_code"].ge(1)
    )
    frame["micro_shock_active"] = frame["short_regime"].eq("Crisis") & ~frame["long_regime"].eq("Crisis")
    frame["macro_stress_divergence_active"] = frame["long_regime"].eq("Crisis") & frame["short_regime"].eq("Calm")
    frame["high_uncertainty_active"] = frame["regime_entropy"] >= 0.95
    frame["vol_no_add_active"] = frame["all_crisis_active"] | frame["synchronized_turbulence_active"]
    return frame


def _add_forward_labels(
    frame: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    underperform_threshold: float,
    mdd_threshold: float,
) -> pd.DataFrame:
    out = frame.copy()
    for horizon in (5, 10):
        ret_631l = prices["00631L.TW"].shift(-horizon) / prices["00631L.TW"] - 1.0
        ret_0050 = prices["0050.TW"].shift(-horizon) / prices["0050.TW"] - 1.0
        mdd_631l = _forward_min_drawdown(prices["00631L.TW"], horizon)
        out[f"forward_ret_00631l_h{horizon}"] = ret_631l.reindex(out.index)
        out[f"forward_ret_0050_h{horizon}"] = ret_0050.reindex(out.index)
        out[f"forward_rel_00631l_vs_0050_h{horizon}"] = (ret_631l - ret_0050).reindex(out.index)
        out[f"forward_mdd_00631l_h{horizon}"] = mdd_631l.reindex(out.index)
        out[f"no_add_label_h{horizon}"] = (
            (out[f"forward_rel_00631l_vs_0050_h{horizon}"] <= underperform_threshold)
            | (out[f"forward_mdd_00631l_h{horizon}"] <= mdd_threshold)
        )
    abs_ret = prices["00631L.TW"].pct_change(fill_method=None).abs()
    next_abs = abs_ret.shift(-1)
    threshold = abs_ret.rolling(252, min_periods=60).quantile(0.85)
    out["next_abs_return_high_vol_label"] = (next_abs >= threshold).reindex(out.index)
    return out


def _read_external_signal(path: Path, signal_col: str) -> pd.Series | None:
    if not path.exists():
        return None
    frame = pd.read_csv(path, encoding="utf-8-sig")
    date_col = "date" if "date" in frame.columns else "dt" if "dt" in frame.columns else frame.columns[0]
    frame[date_col] = pd.to_datetime(frame[date_col])
    frame = frame.set_index(date_col).sort_index()
    frame.index = pd.to_datetime(frame.index).normalize()
    if signal_col not in frame:
        return None
    return frame[signal_col].astype(bool)


def _overlap_summary(frame: pd.DataFrame, paths: dict[str, tuple[Path, str]]) -> dict[str, Any]:
    base = frame["vol_no_add_active"].astype(bool)
    out: dict[str, Any] = {"vol_no_add_active": _summarize_signal(frame, base)}
    for name, (path, signal_col) in paths.items():
        series = _read_external_signal(path, signal_col)
        if series is None:
            out[name] = {"status": "skipped", "reason": "missing_file_or_signal_column", "path": str(path)}
            continue
        signal = series.reindex(frame.index, fill_value=False).astype(bool)
        out[name] = _summarize_signal(frame, signal)
        out[f"union_vol_or_{name}"] = _summarize_signal(frame, base | signal)
        out[f"intersection_vol_and_{name}"] = _summarize_signal(frame, base & signal)
    return out


def build_report(
    *,
    db_path: Path,
    start: str,
    end: str,
    warmup_days: int,
    percentile_window: int,
    underperform_threshold: float,
    mdd_threshold: float,
    vol_symbol: str,
    overlap: bool,
) -> tuple[dict[str, Any], pd.DataFrame]:
    prices = _load_close_panel(db_path, ("0050.TW", "00631L.TW"), start, end, warmup_days)
    frame = _build_vol_frame(prices, start=start, end=end, vol_symbol=vol_symbol, percentile_window=percentile_window)
    frame = _add_forward_labels(
        frame,
        prices,
        underperform_threshold=underperform_threshold,
        mdd_threshold=mdd_threshold,
    )
    signals = {
        "vol_no_add_active": frame["vol_no_add_active"],
        "all_crisis_active": frame["all_crisis_active"],
        "synchronized_turbulence_active": frame["synchronized_turbulence_active"],
        "micro_shock_active": frame["micro_shock_active"],
        "macro_stress_divergence_active": frame["macro_stress_divergence_active"],
        "high_uncertainty_active": frame["high_uncertainty_active"],
    }
    summary = {name: _summarize_signal(frame, signal) for name, signal in signals.items()}
    summary["brier_skill_next_high_abs_return"] = _brier_skill_score(
        frame["crisis_probability_proxy"],
        frame["next_abs_return_high_vol_label"],
    )
    overlap_summary: dict[str, Any] = {}
    if overlap:
        overlap_summary = _overlap_summary(
            frame,
            {
                "srr_no_add": (
                    PROJECT_ROOT / "results" / "srr_lite_shadow_backtest_20250102_20260716_tuned_frame.csv",
                    "no_add_active",
                ),
                "qgms_endpoint": (
                    PROJECT_ROOT / "results" / "qgms_lite_structural_endpoint_shadow_20250102_20260716_frame.csv",
                    "endpoint_watch_active",
                ),
                "cross_market_no_add": (
                    PROJECT_ROOT / "results" / "cross_market_directed_graph_shadow_prediction_frame_full_20260716.csv",
                    "no_add_active",
                ),
            },
        )
        # Convert CSM probability column to low-probability signal if present.
        csm_path = PROJECT_ROOT / "results" / "csm_lite_00631l_shadow_20250102_20260716_frame.csv"
        if csm_path.exists():
            csm = pd.read_csv(csm_path, encoding="utf-8-sig")
            date_col = "date" if "date" in csm.columns else "dt" if "dt" in csm.columns else csm.columns[0]
            csm[date_col] = pd.to_datetime(csm[date_col])
            csm = csm.set_index(date_col).sort_index()
            csm.index = pd.to_datetime(csm.index).normalize()
            if "hgb_csm_lite_prob_up_h20" in csm:
                signal = (csm["hgb_csm_lite_prob_up_h20"].astype(float) <= 0.45).reindex(frame.index, fill_value=False)
                base = frame["vol_no_add_active"].astype(bool)
                overlap_summary["csm_hgb_low_prob"] = _summarize_signal(frame, signal)
                overlap_summary["union_vol_or_csm_hgb_low_prob"] = _summarize_signal(frame, base | signal)
                overlap_summary["intersection_vol_and_csm_hgb_low_prob"] = _summarize_signal(frame, base & signal)

    report = {
        "report_type": "multi_scale_vol_regime_shadow",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.06190v1.pdf",
            "title": "Multi-Scale Markov-Switching GARCH: Volatility Regime Detection in EUR/USD",
            "implementation_note": "Lightweight realized-volatility percentile proxy, not full MS-GARCH/TVTP.",
        },
        "policy": "shadow_only_no_weight_change",
        "window": {
            "start": str(frame.index.min().date()) if len(frame) else start,
            "end": str(frame.index.max().date()) if len(frame) else end,
            "rows": int(len(frame)),
        },
        "parameters": {
            "vol_symbol": vol_symbol,
            "scales": {"short": 5, "medium": 20, "long": 60},
            "calm_percentile_lt": 0.50,
            "crisis_percentile_gte": 0.85,
            "percentile_window": int(percentile_window),
            "warmup_days": int(warmup_days),
            "underperform_threshold": underperform_threshold,
            "mdd_threshold": mdd_threshold,
        },
        "summary": summary,
        "overlap_summary": overlap_summary,
        "interpretation": (
            "This tests whether cross-scale volatility regimes provide a no-add/crash-review "
            "shadow. It is diagnostic only and does not implement full MS-GARCH."
        ),
    }
    return report, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-07-16")
    parser.add_argument("--warmup-days", type=int, default=500)
    parser.add_argument("--percentile-window", type=int, default=252)
    parser.add_argument("--underperform-threshold", type=float, default=-0.01)
    parser.add_argument("--mdd-threshold", type=float, default=-0.05)
    parser.add_argument("--vol-symbol", default="00631L.TW")
    parser.add_argument("--overlap", action="store_true")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report, frame = build_report(
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        warmup_days=int(args.warmup_days),
        percentile_window=int(args.percentile_window),
        underperform_threshold=float(args.underperform_threshold),
        mdd_threshold=float(args.mdd_threshold),
        vol_symbol=str(args.vol_symbol),
        overlap=bool(args.overlap),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_output = output.with_name(output.stem + "_frame.csv")
    frame.to_csv(frame_output, encoding="utf-8-sig")
    report["frame_output"] = str(frame_output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = {
        name: {
            "active_days": value.get("active_days"),
            "h10_precision": ((value.get("h10") or {}).get("confusion") or {}).get("precision"),
            "h10_recall": ((value.get("h10") or {}).get("confusion") or {}).get("recall"),
            "h10_fpr": ((value.get("h10") or {}).get("confusion") or {}).get("false_positive_rate"),
        }
        for name, value in report["summary"].items()
        if isinstance(value, dict) and "h10" in value
    }
    print(f"Saved: {output}")
    print(f"Frame: {frame_output}")
    print(json.dumps(compact, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
