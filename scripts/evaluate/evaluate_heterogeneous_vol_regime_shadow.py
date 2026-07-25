#!/usr/bin/env python3
"""Sparse heterogeneous volatility-regime shadow evaluator for GroupA+.

Research-only proxy inspired by arXiv 2603.16035. This is not a Bayesian
SVAR-HMSH implementation. It imports the paper's useful operational idea:
different shocks/sources should have their own volatility process, and a
source should pass a simple heteroskedasticity check before it is treated as
useful risk context.

Outputs diagnostics only. It must not be wired into live target weights.
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
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "heterogeneous_vol_regime_shadow_20250102_20260717.json"

LOCAL_SOURCES = {
    "0050_local": ("ohlcv", None, "0050.TW"),
    "00631l_levered": ("ohlcv", None, "00631L.TW"),
    "00632r_inverse": ("ohlcv", None, "00632R.TW"),
}

EXTERNAL_SOURCES = {
    "twii_market": ("external_market_ohlcv", "yfinance", "^TWII"),
    "soxx_semiconductor": ("external_market_ohlcv", "yfinance", "SOXX"),
    "qqq_growth": ("external_market_ohlcv", "yfinance", "QQQ"),
    "tsm_adr": ("external_market_ohlcv", "yfinance", "TSM"),
    "usdtwd_fx": ("external_market_ohlcv", "yfinance", "TWD=X"),
}


def _safe_rate(num: int, den: int) -> float | None:
    return None if den == 0 else float(num / den)


def _table_exists(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    try:
        con.execute(f"DESCRIBE {table}").fetchall()
        return True
    except Exception:
        return False


def _load_close(
    con: duckdb.DuckDBPyConnection,
    *,
    table: str,
    provider: str | None,
    ticker: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    if not _table_exists(con, table):
        return pd.Series(dtype=float, name=ticker)
    if table == "external_market_ohlcv" and provider is not None:
        query = """
            SELECT dt, close
            FROM external_market_ohlcv
            WHERE provider = ? AND ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
        """
        params: list[Any] = [provider, ticker, str(start.date()), str(end.date())]
    else:
        query = f"""
            SELECT dt, close
            FROM {table}
            WHERE ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
        """
        params = [ticker, str(start.date()), str(end.date())]
    rows = con.execute(query, params).fetchdf()
    if rows.empty:
        return pd.Series(dtype=float, name=ticker)
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    return rows.set_index("dt")["close"].astype(float).sort_index().rename(ticker)


def _load_source_panel(db_path: Path, start: str, end: str, warmup_days: int) -> pd.DataFrame:
    start_ts = pd.Timestamp(start).normalize() - pd.Timedelta(days=warmup_days)
    end_ts = pd.Timestamp(end).normalize()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        local_anchor = _load_close(
            con,
            table="ohlcv",
            provider=None,
            ticker="00631L.TW",
            start=start_ts,
            end=end_ts,
        )
        if local_anchor.empty:
            raise RuntimeError(f"No 00631L.TW data from {start_ts.date()} to {end_ts.date()}")
        target_index = local_anchor.index
        frame = pd.DataFrame(index=target_index)

        for name, (table, provider, ticker) in LOCAL_SOURCES.items():
            close = _load_close(con, table=table, provider=provider, ticker=ticker, start=start_ts, end=end_ts)
            frame[name] = close.reindex(target_index)

        for name, (table, provider, ticker) in EXTERNAL_SOURCES.items():
            close = _load_close(con, table=table, provider=provider, ticker=ticker, start=start_ts, end=end_ts)
            # Strict live timing proxy: Taiwan date d can only use source closes
            # with source_dt < d. This avoids same-date US-market lookahead.
            shifted = close.copy()
            shifted.index = shifted.index + pd.Timedelta(days=1)
            frame[name] = shifted.reindex(target_index, method="ffill")
    finally:
        con.close()
    return frame


def _rolling_percentile_latest(window: pd.Series) -> float:
    clean = pd.to_numeric(window, errors="coerce").dropna()
    if clean.empty:
        return float("nan")
    return float((clean <= clean.iloc[-1]).mean())


def _regime_from_percentile(value: float) -> str:
    if not np.isfinite(value):
        return "Unknown"
    if value < 0.20:
        return "Dormant"
    if value < 0.40:
        return "Low"
    if value < 0.70:
        return "Normal"
    if value < 0.90:
        return "Elevated"
    return "Crisis"


def _regime_code(value: str) -> int:
    return {"Dormant": 0, "Low": 1, "Normal": 2, "Elevated": 3, "Crisis": 4}.get(value, -1)


def _forward_min_drawdown(close: pd.Series, horizon: int) -> pd.Series:
    future = pd.concat([close.shift(-step) for step in range(1, horizon + 1)], axis=1)
    return future.min(axis=1) / close - 1.0


def _confusion(pred: pd.Series, label: pd.Series) -> dict[str, Any]:
    valid = pred.notna() & label.notna()
    p = pred[valid].fillna(False).astype(bool)
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


def _score_signal(frame: pd.DataFrame, signal: pd.Series, horizon: int) -> dict[str, Any]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    return {
        "horizon_days": int(horizon),
        "confusion": _confusion(signal, frame[f"no_add_label_h{horizon}"]),
        "active_mean_forward_ret_00631l": (
            float(frame.loc[signal, f"forward_ret_00631l_h{horizon}"].mean()) if signal.any() else None
        ),
        "active_mean_relative_vs_0050": (
            float(frame.loc[signal, f"forward_rel_00631l_vs_0050_h{horizon}"].mean()) if signal.any() else None
        ),
        "active_mean_forward_mdd_00631l": (
            float(frame.loc[signal, f"forward_mdd_00631l_h{horizon}"].mean()) if signal.any() else None
        ),
    }


def _summarize_signal(frame: pd.DataFrame, signal: pd.Series) -> dict[str, Any]:
    signal = signal.reindex(frame.index).fillna(False).astype(bool)
    return {
        "active_days": int(signal.sum()),
        "active_dates": [str(pd.Timestamp(dt).date()) for dt in frame.index[signal]],
        "h5": _score_signal(frame, signal, 5),
        "h10": _score_signal(frame, signal, 10),
    }


def _source_diagnostics(
    ret: pd.Series,
    *,
    vol_window: int,
    percentile_window: int,
    min_active_share: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    vol = ret.rolling(vol_window, min_periods=max(5, vol_window // 2)).std(ddof=0)
    vol_pct = vol.rolling(percentile_window, min_periods=min(60, percentile_window)).apply(
        _rolling_percentile_latest,
        raw=False,
    )
    regime = vol_pct.map(_regime_from_percentile)
    regime_code = regime.map(_regime_code)

    recent_var = ret.rolling(vol_window, min_periods=max(5, vol_window // 2)).var(ddof=0)
    long_var = ret.rolling(percentile_window, min_periods=min(60, percentile_window)).var(ddof=0)
    variance_ratio = recent_var / long_var.replace(0.0, np.nan)
    heteroskedastic_active = (variance_ratio >= 1.5) | (vol_pct >= 0.85)

    counts = regime.value_counts(dropna=False)
    active_regimes = {
        str(name): int(count)
        for name, count in counts.items()
        if str(name) != "Unknown" and int(count) >= max(1, int(len(regime.dropna()) * min_active_share))
    }
    diagnostic = {
        "rows": int(ret.notna().sum()),
        "vol_window": int(vol_window),
        "percentile_window": int(percentile_window),
        "active_regimes": active_regimes,
        "latest_regime": str(regime.dropna().iloc[-1]) if len(regime.dropna()) else None,
        "latest_vol_percentile": float(vol_pct.dropna().iloc[-1]) if len(vol_pct.dropna()) else None,
        "latest_variance_ratio": float(variance_ratio.dropna().iloc[-1]) if len(variance_ratio.dropna()) else None,
        "heteroskedastic_active_days": int(heteroskedastic_active.fillna(False).sum()),
        "heteroskedastic_active_share": (
            float(heteroskedastic_active.fillna(False).mean()) if len(heteroskedastic_active) else None
        ),
        "passes_shadow_verification": bool(
            len(active_regimes) >= 2 and int(heteroskedastic_active.fillna(False).sum()) >= 5
        ),
    }
    return (
        pd.DataFrame(
            {
                "vol": vol,
                "vol_percentile": vol_pct,
                "regime": regime,
                "regime_code": regime_code,
                "variance_ratio": variance_ratio,
                "heteroskedastic_active": heteroskedastic_active.fillna(False),
            }
        ),
        diagnostic,
    )


def _add_forward_labels(
    frame: pd.DataFrame,
    prices: pd.DataFrame,
    *,
    underperform_threshold: float,
    mdd_threshold: float,
) -> pd.DataFrame:
    out = frame.copy()
    ret_631l = prices["00631l_levered"].pct_change(fill_method=None)
    ret_0050 = prices["0050_local"].pct_change(fill_method=None)
    for horizon in (5, 10):
        fwd_631l = prices["00631l_levered"].shift(-horizon) / prices["00631l_levered"] - 1.0
        fwd_0050 = prices["0050_local"].shift(-horizon) / prices["0050_local"] - 1.0
        fwd_mdd = _forward_min_drawdown(prices["00631l_levered"], horizon)
        out[f"forward_ret_00631l_h{horizon}"] = fwd_631l
        out[f"forward_ret_0050_h{horizon}"] = fwd_0050
        out[f"forward_rel_00631l_vs_0050_h{horizon}"] = fwd_631l - fwd_0050
        out[f"forward_mdd_00631l_h{horizon}"] = fwd_mdd
        out[f"no_add_label_h{horizon}"] = (
            (out[f"forward_rel_00631l_vs_0050_h{horizon}"] <= underperform_threshold)
            | (out[f"forward_mdd_00631l_h{horizon}"] <= mdd_threshold)
        )
    out["abs_ret_00631l"] = ret_631l.abs()
    out["abs_ret_0050"] = ret_0050.abs()
    return out


def build_report(
    *,
    db_path: Path,
    start: str,
    end: str,
    warmup_days: int,
    vol_window: int,
    percentile_window: int,
    min_active_share: float,
    hetero_source_min_count: int,
    crisis_source_min_count: int,
    underperform_threshold: float,
    mdd_threshold: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    prices = _load_source_panel(db_path, start, end, warmup_days)
    frame = pd.DataFrame(index=prices.index)
    diagnostics: dict[str, Any] = {}
    source_stress_cols: list[str] = []
    source_crisis_cols: list[str] = []
    source_hetero_cols: list[str] = []

    for source in prices.columns:
        ret = prices[source].pct_change(fill_method=None)
        diag_frame, diagnostic = _source_diagnostics(
            ret,
            vol_window=vol_window,
            percentile_window=percentile_window,
            min_active_share=min_active_share,
        )
        diagnostics[source] = diagnostic
        prefix = f"src_{source}"
        frame[f"{prefix}_vol_percentile"] = diag_frame["vol_percentile"]
        frame[f"{prefix}_regime"] = diag_frame["regime"]
        frame[f"{prefix}_regime_code"] = diag_frame["regime_code"]
        frame[f"{prefix}_variance_ratio"] = diag_frame["variance_ratio"]
        frame[f"{prefix}_heteroskedastic_active"] = diag_frame["heteroskedastic_active"]
        frame[f"{prefix}_stress_active"] = diag_frame["regime_code"].ge(3).fillna(False)
        frame[f"{prefix}_crisis_active"] = diag_frame["regime_code"].ge(4).fillna(False)
        source_stress_cols.append(f"{prefix}_stress_active")
        source_crisis_cols.append(f"{prefix}_crisis_active")
        source_hetero_cols.append(f"{prefix}_heteroskedastic_active")

    frame = frame.loc[pd.Timestamp(start).normalize() : pd.Timestamp(end).normalize()].copy()
    prices = prices.reindex(frame.index)
    stress_count = frame[source_stress_cols].sum(axis=1)
    crisis_count = frame[source_crisis_cols].sum(axis=1)
    hetero_count = frame[source_hetero_cols].sum(axis=1)
    verified_sources = [
        source for source, diagnostic in diagnostics.items() if bool(diagnostic["passes_shadow_verification"])
    ]
    verified_stress_cols = [f"src_{source}_stress_active" for source in verified_sources if f"src_{source}_stress_active" in frame]
    verified_crisis_cols = [f"src_{source}_crisis_active" for source in verified_sources if f"src_{source}_crisis_active" in frame]

    frame["heterogeneous_stress_count"] = stress_count.astype(int)
    frame["heterogeneous_crisis_count"] = crisis_count.astype(int)
    frame["heteroskedastic_source_count"] = hetero_count.astype(int)
    frame["verified_stress_count"] = frame[verified_stress_cols].sum(axis=1).astype(int) if verified_stress_cols else 0
    frame["verified_crisis_count"] = frame[verified_crisis_cols].sum(axis=1).astype(int) if verified_crisis_cols else 0
    frame["heterogeneous_stress_active"] = (
        (frame["verified_stress_count"] >= int(hetero_source_min_count))
        & (frame["heteroskedastic_source_count"] >= int(hetero_source_min_count))
    )
    frame["sparse_crisis_active"] = frame["verified_crisis_count"] >= int(crisis_source_min_count)
    frame["local_levered_stress_active"] = (
        frame["src_0050_local_stress_active"].fillna(False)
        & frame["src_00631l_levered_stress_active"].fillna(False)
    )
    frame = _add_forward_labels(
        frame,
        prices,
        underperform_threshold=underperform_threshold,
        mdd_threshold=mdd_threshold,
    )

    summary = {
        "heterogeneous_stress_active": _summarize_signal(frame, frame["heterogeneous_stress_active"]),
        "sparse_crisis_active": _summarize_signal(frame, frame["sparse_crisis_active"]),
        "local_levered_stress_active": _summarize_signal(frame, frame["local_levered_stress_active"]),
    }
    for source in prices.columns:
        summary[f"source_{source}_stress_active"] = _summarize_signal(
            frame,
            frame[f"src_{source}_stress_active"],
        )

    latest_row = frame.iloc[-1] if len(frame) else pd.Series(dtype=object)
    report = {
        "report_type": "heterogeneous_vol_regime_shadow",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2603.16035.pdf",
            "title": (
                "Identification Verification for Structural Vector Autoregressions "
                "with Sparse Heterogeneous Markov Switching Heteroskedasticity"
            ),
            "implementation_note": (
                "Transparent realized-volatility proxy. Not a Bayesian SVAR-HMSH "
                "implementation and not a live allocation rule."
            ),
        },
        "policy": "shadow_only_no_weight_change",
        "window": {
            "start": str(frame.index.min().date()) if len(frame) else start,
            "end": str(frame.index.max().date()) if len(frame) else end,
            "rows": int(len(frame)),
        },
        "parameters": {
            "warmup_days": int(warmup_days),
            "vol_window": int(vol_window),
            "percentile_window": int(percentile_window),
            "min_active_share": float(min_active_share),
            "hetero_source_min_count": int(hetero_source_min_count),
            "crisis_source_min_count": int(crisis_source_min_count),
            "underperform_threshold": float(underperform_threshold),
            "mdd_threshold": float(mdd_threshold),
        },
        "source_diagnostics": diagnostics,
        "verified_sources": verified_sources,
        "latest_snapshot": {
            "date": str(frame.index[-1].date()) if len(frame) else None,
            "heterogeneous_stress_count": int(latest_row.get("heterogeneous_stress_count", 0) or 0),
            "heterogeneous_crisis_count": int(latest_row.get("heterogeneous_crisis_count", 0) or 0),
            "heteroskedastic_source_count": int(latest_row.get("heteroskedastic_source_count", 0) or 0),
            "verified_stress_count": int(latest_row.get("verified_stress_count", 0) or 0),
            "verified_crisis_count": int(latest_row.get("verified_crisis_count", 0) or 0),
            "heterogeneous_stress_active": bool(latest_row.get("heterogeneous_stress_active", False)),
            "sparse_crisis_active": bool(latest_row.get("sparse_crisis_active", False)),
        },
        "summary": summary,
        "interpretation": (
            "Use as a source-level volatility health dashboard. Any promotion would "
            "require separate purged walk-forward validation and live-boundary review."
        ),
    }
    return report, frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2025-01-02")
    parser.add_argument("--end", default="2026-07-17")
    parser.add_argument("--warmup-days", type=int, default=500)
    parser.add_argument("--vol-window", type=int, default=20)
    parser.add_argument("--percentile-window", type=int, default=252)
    parser.add_argument("--min-active-share", type=float, default=0.03)
    parser.add_argument("--hetero-source-min-count", type=int, default=3)
    parser.add_argument("--crisis-source-min-count", type=int, default=2)
    parser.add_argument("--underperform-threshold", type=float, default=-0.01)
    parser.add_argument("--mdd-threshold", type=float, default=-0.05)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    report, frame = build_report(
        db_path=Path(args.db),
        start=args.start,
        end=args.end,
        warmup_days=int(args.warmup_days),
        vol_window=int(args.vol_window),
        percentile_window=int(args.percentile_window),
        min_active_share=float(args.min_active_share),
        hetero_source_min_count=int(args.hetero_source_min_count),
        crisis_source_min_count=int(args.crisis_source_min_count),
        underperform_threshold=float(args.underperform_threshold),
        mdd_threshold=float(args.mdd_threshold),
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
