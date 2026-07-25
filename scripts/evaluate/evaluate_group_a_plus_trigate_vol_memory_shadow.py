#!/usr/bin/env python3
"""Tri-gate volatility-memory shadow for GroupA+.

Research-only implementation inspired by 2512.02166. It does not estimate the
paper's full TG-Vol/QMLE model. Instead, it maps the paper's level/shape/tempo
decomposition into transparent Taiwan ETF diagnostics for 00631L and 0050.
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
DB_PATH = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/group_a_plus_trigate_vol_memory_shadow_20260717.json"
DEFAULT_LATEST = PROJECT_ROOT / "report/group_a_plus/latest/trigate_vol_memory_shadow.json"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load_close_panel(db_path: Path, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, ticker, close, volume
            FROM ohlcv
            WHERE ticker IN ('0050.TW', '00631L.TW')
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV data from {start} to {end}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    close = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    volume = rows.pivot(index="dt", columns="ticker", values="volume").sort_index()
    frame = pd.concat(
        {
            "close": close,
            "volume": volume,
        },
        axis=1,
    ).dropna(subset=[("close", "0050.TW"), ("close", "00631L.TW")])
    if frame.empty:
        raise RuntimeError("No overlapping 0050/00631L data after alignment")
    return frame.astype(float)


def _safe_corr(a: pd.Series, b: pd.Series) -> float | None:
    frame = pd.concat([a, b], axis=1).dropna()
    if len(frame) < 20:
        return None
    value = frame.iloc[:, 0].corr(frame.iloc[:, 1])
    return None if pd.isna(value) else float(value)


def _rank_last(series: pd.Series, window: int) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    tail = clean.tail(window)
    if len(tail) < max(20, window // 4):
        return None
    return float(tail.rank(pct=True).iloc[-1])


def _memory_shape_score(vol: pd.Series) -> pd.Series:
    # A transparent long-memory proxy: mean positive autocorrelation across
    # short/medium volatility lags. This is not a FIGARCH estimate.
    out = pd.Series(index=vol.index, dtype=float)
    for idx in range(len(vol)):
        window = vol.iloc[max(0, idx - 252 + 1) : idx + 1].dropna()
        if len(window) < 80:
            continue
        cors = []
        for lag in (1, 5, 20):
            corr = window.autocorr(lag=lag)
            if pd.notna(corr):
                cors.append(max(0.0, float(corr)))
        out.iloc[idx] = float(np.mean(cors)) if cors else np.nan
    return out


def build_shadow(panel: pd.DataFrame) -> dict[str, Any]:
    close = panel["close"]
    volume = panel["volume"]
    returns = close.pct_change().replace([np.inf, -np.inf], np.nan).dropna(how="any")
    vol20 = returns.rolling(20, min_periods=10).std() * np.sqrt(252.0)
    vol60 = returns.rolling(60, min_periods=30).std() * np.sqrt(252.0)
    vol_level = vol20["00631L.TW"]
    level_percentile = vol_level.rolling(252, min_periods=80).rank(pct=True)
    shape_score = _memory_shape_score(vol20["00631L.TW"])
    tempo_proxy = (
        (returns["00631L.TW"].abs() / returns["00631L.TW"].abs().rolling(252, min_periods=80).median())
        .replace([np.inf, -np.inf], np.nan)
        .clip(upper=10.0)
    )
    volume_tempo = (
        (volume["00631L.TW"] / volume["00631L.TW"].rolling(252, min_periods=80).median())
        .replace([np.inf, -np.inf], np.nan)
        .clip(upper=10.0)
    )
    tempo_score = pd.concat([tempo_proxy, volume_tempo], axis=1).mean(axis=1)
    tempo_percentile = tempo_score.rolling(252, min_periods=80).rank(pct=True)

    latest_date = str(returns.index.max().date())
    latest = {
        "date": latest_date,
        "vol_level_20d_ann": None if pd.isna(vol_level.iloc[-1]) else float(vol_level.iloc[-1]),
        "vol_level_percentile_252d": _rank_last(vol_level, 252),
        "memory_shape_score": None if pd.isna(shape_score.iloc[-1]) else float(shape_score.iloc[-1]),
        "memory_shape_percentile_252d": _rank_last(shape_score, 252),
        "tempo_score": None if pd.isna(tempo_score.iloc[-1]) else float(tempo_score.iloc[-1]),
        "tempo_percentile_252d": _rank_last(tempo_score, 252),
        "vol20_vs_vol60_ratio": None
        if pd.isna(vol20["00631L.TW"].iloc[-1]) or pd.isna(vol60["00631L.TW"].iloc[-1]) or vol60["00631L.TW"].iloc[-1] == 0
        else float(vol20["00631L.TW"].iloc[-1] / vol60["00631L.TW"].iloc[-1]),
        "0050_00631l_return_corr_60d": _safe_corr(returns["0050.TW"].tail(60), returns["00631L.TW"].tail(60)),
    }

    active_level = (latest["vol_level_percentile_252d"] or 0.0) >= 0.80
    active_shape = (latest["memory_shape_percentile_252d"] or 0.0) >= 0.70
    active_tempo = (latest["tempo_percentile_252d"] or 0.0) >= 0.80
    tri_gate_stress = int(active_level) + int(active_shape) + int(active_tempo)

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_trigate_vol_memory_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_vol_memory_decomposition_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2512.02166.pdf",
            "title": "The Three-Dimensional Decomposition of Volatility Memory",
            "imported_concepts": [
                "volatility_memory_level_gate",
                "volatility_memory_shape_or_long_memory_proxy",
                "volatility_memory_tempo_or_business_time_proxy",
                "equity_volatility_memory_can_be_regime_and_tempo_dominated",
            ],
            "not_imported": [
                "full_TG_Vol_QMLE_estimator",
                "G_FIGARCH_fractional_order_estimation",
                "SPY_EURUSD_empirical_parameters",
                "automatic_target_weight_change",
            ],
        },
        "input_window": {
            "start": str(returns.index.min().date()),
            "end": latest_date,
            "rows": int(len(returns)),
        },
        "latest": latest,
        "tri_gate_state": {
            "level_gate_active": bool(active_level),
            "shape_gate_active": bool(active_shape),
            "tempo_gate_active": bool(active_tempo),
            "stress_gate_count": int(tri_gate_stress),
            "state": "blocked_for_leverage_add" if tri_gate_stress >= 2 else "research_watch",
        },
        "decision": {
            "summary": (
                "Import level/shape/tempo volatility-memory decomposition as a shadow diagnostic only. "
                "It does not overcome existing GroupA+ execution, rebalance, option-state, and FinStressTS blockers."
            ),
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def write_report(report: dict[str, Any], output: Path, latest: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if latest is not None:
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="2026-07-17")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--latest", default=str(DEFAULT_LATEST))
    parser.add_argument("--no-latest", action="store_true")
    args = parser.parse_args()

    panel = _load_close_panel(_resolve(args.db), args.start, args.end)
    report = build_shadow(panel)
    latest = None if args.no_latest else _resolve(args.latest)
    write_report(report, _resolve(args.output), latest)
    print(f"Tri-gate vol memory shadow: {_resolve(args.output)}")
    if latest is not None:
        print(f"Latest pointer: {latest}")
    print(
        json.dumps(
            {
                "state": report["tri_gate_state"]["state"],
                "stress_gate_count": report["tri_gate_state"]["stress_gate_count"],
                "allow_00631l_add": report["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
