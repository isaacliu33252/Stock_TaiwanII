#!/usr/bin/env python3
"""Systemic bubble time-at-risk review for GroupA+.

Research-only implementation inspired by 1212.2833. It maps the paper's
time-at-risk, ETF coupling, and market reflexivity ideas into transparent daily
proxies for Taiwan ETF governance. It never changes target weights.
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
DEFAULT_OUTPUT = PROJECT_ROOT / "results/group_a_plus_systemic_bubble_time_at_risk_review_20260718.json"
DEFAULT_LATEST = PROJECT_ROOT / "report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/systemic_bubble_time_at_risk/history"
DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "2330.TW")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_panel(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if "ohlcv" in tables:
            rows = con.execute(
                """
                SELECT dt, ticker, close, volume, 'ohlcv' AS source_table
                FROM ohlcv
                WHERE ticker IN (SELECT * FROM UNNEST(?))
                  AND dt BETWEEN ? AND ?
                  AND close IS NOT NULL
                """,
                [list(tickers), start, end],
            ).fetchdf()
            if not rows.empty:
                frames.append(rows)
        if "external_market_ohlcv" in tables:
            rows = con.execute(
                """
                SELECT dt, ticker, close, volume, 'external_market_ohlcv' AS source_table
                FROM external_market_ohlcv
                WHERE provider = 'yfinance'
                  AND ticker IN (SELECT * FROM UNNEST(?))
                  AND dt BETWEEN ? AND ?
                  AND close IS NOT NULL
                """,
                [list(tickers), start, end],
            ).fetchdf()
            if not rows.empty:
                frames.append(rows)
    finally:
        con.close()
    if not frames:
        raise RuntimeError(f"No OHLCV data for {tickers} from {start} to {end}")
    rows = pd.concat(frames, ignore_index=True)
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    source_priority = {"ohlcv": 0, "external_market_ohlcv": 1}
    rows["_source_priority"] = rows["source_table"].map(source_priority).fillna(9)
    rows = rows.sort_values(["dt", "ticker", "_source_priority"]).drop_duplicates(["dt", "ticker"], keep="first")
    close = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    volume = rows.pivot(index="dt", columns="ticker", values="volume").sort_index()
    panel = pd.concat({"close": close, "volume": volume}, axis=1)
    panel = panel.dropna(subset=[("close", "0050.TW"), ("close", "00631L.TW")])
    if panel.empty:
        raise RuntimeError("No overlapping 0050/00631L OHLCV rows after alignment")
    return panel.astype(float)


def _rank_last(series: pd.Series, window: int = 252) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    tail = clean.tail(window)
    if len(tail) < max(40, window // 4):
        return None
    return float(tail.rank(pct=True).iloc[-1])


def _last_float(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return None if clean.empty else float(clean.iloc[-1])


def _safe_corr(a: pd.Series, b: pd.Series) -> float | None:
    frame = pd.concat([a, b], axis=1).dropna()
    if len(frame) < 20:
        return None
    value = frame.iloc[:, 0].corr(frame.iloc[:, 1])
    return None if pd.isna(value) else float(value)


def _bool_score(*flags: bool) -> int:
    return int(sum(1 for flag in flags if flag))


def _state_from_score(score: int) -> str:
    if score >= 2:
        return "elevated"
    if score == 1:
        return "watch"
    return "normal"


def build_review(panel: pd.DataFrame) -> dict[str, Any]:
    close = panel["close"]
    volume = panel["volume"]
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    returns = returns.dropna(subset=["0050.TW", "00631L.TW"])

    ret_00631l = returns["00631L.TW"]
    ret_0050 = returns["0050.TW"]
    vol20 = ret_00631l.rolling(20, min_periods=10).std() * np.sqrt(252.0)
    vol60 = ret_00631l.rolling(60, min_periods=30).std() * np.sqrt(252.0)
    ret60 = close["0050.TW"].pct_change(60)
    ma_gap = close["0050.TW"] / close["0050.TW"].rolling(120, min_periods=60).mean() - 1.0
    accel = ret60 - close["0050.TW"].pct_change(120)
    fragile = (
        ((vol20.rolling(252, min_periods=80).rank(pct=True) >= 0.80) & (ma_gap > 0.08))
        | ((ret60.rolling(252, min_periods=80).rank(pct=True) >= 0.85) & (accel > 0.0))
    )
    time_at_risk_days_60 = int(fragile.tail(60).fillna(False).sum())

    corr_0050_00631l_60 = returns["0050.TW"].rolling(60, min_periods=30).corr(returns["00631L.TW"])
    corr_0050_00632r_60 = (
        returns["0050.TW"].rolling(60, min_periods=30).corr(returns["00632R.TW"])
        if "00632R.TW" in returns
        else pd.Series(dtype=float)
    )
    corr_2330_0050_60 = (
        returns["2330.TW"].rolling(60, min_periods=30).corr(returns["0050.TW"])
        if "2330.TW" in returns
        else pd.Series(dtype=float)
    )
    coupling_score = pd.concat(
        [
            corr_0050_00631l_60.abs(),
            corr_0050_00632r_60.abs(),
            corr_2330_0050_60.abs(),
        ],
        axis=1,
    ).mean(axis=1, skipna=True)

    volume_z = (
        (volume["00631L.TW"] - volume["00631L.TW"].rolling(60, min_periods=30).mean())
        / volume["00631L.TW"].rolling(60, min_periods=30).std()
    ).replace([np.inf, -np.inf], np.nan)
    absret_z = (
        (ret_00631l.abs() - ret_00631l.abs().rolling(60, min_periods=30).mean())
        / ret_00631l.abs().rolling(60, min_periods=30).std()
    ).replace([np.inf, -np.inf], np.nan)
    same_direction = (np.sign(ret_00631l) == np.sign(ret_0050)).astype(float).rolling(20, min_periods=10).mean()
    reflexivity_proxy = pd.concat([volume_z.clip(lower=0), absret_z.clip(lower=0), same_direction], axis=1).mean(
        axis=1,
        skipna=True,
    )

    high_time_at_risk = time_at_risk_days_60 >= 20 or (_rank_last(vol20, 252) or 0.0) >= 0.85
    high_coupling = (_last_float(coupling_score) or 0.0) >= 0.75
    high_reflexivity = (_rank_last(reflexivity_proxy, 252) or 0.0) >= 0.80
    high_ma_extension = (_last_float(ma_gap) or 0.0) >= 0.10

    time_score = _bool_score(high_time_at_risk, high_ma_extension)
    coupling_state = _state_from_score(_bool_score(high_coupling, (_rank_last(coupling_score, 252) or 0.0) >= 0.80))
    reflexivity_state = _state_from_score(
        _bool_score(high_reflexivity, (_last_float(volume_z) or 0.0) >= 2.0, (_last_float(absret_z) or 0.0) >= 2.0)
    )
    systemic_score = _bool_score(time_score >= 1, coupling_state == "elevated", reflexivity_state == "elevated")
    overall_state = "blocked_for_leverage_add" if systemic_score >= 2 else "research_watch"

    latest_date = str(returns.index.max().date())
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_systemic_bubble_time_at_risk_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_systemic_bubble_time_at_risk_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/1212.2833.pdf",
            "title": "The Illusion of the Perpetual Money Machine",
            "imported_concepts": [
                "time_at_risk",
                "ETF_coupling_network_fragility",
                "market_reflexivity_proxy",
                "scenario_discipline_and_ex_post_review",
            ],
            "not_imported": [
                "LPPL_live_trading_signal",
                "macro_debt_market_timing",
                "commodity_or_real_asset_allocation_change",
                "automatic_target_weight_change",
            ],
        },
        "input_window": {
            "start": str(returns.index.min().date()),
            "end": latest_date,
            "rows": int(len(returns)),
            "tickers": list(close.columns),
        },
        "latest": {
            "date": latest_date,
            "00631l_vol20_ann": _last_float(vol20),
            "00631l_vol20_percentile_252d": _rank_last(vol20, 252),
            "00631l_vol20_vs_vol60_ratio": None
            if (_last_float(vol60) in {None, 0.0} or _last_float(vol20) is None)
            else float((_last_float(vol20) or 0.0) / (_last_float(vol60) or 1.0)),
            "0050_return_60d": _last_float(ret60),
            "0050_ma120_gap": _last_float(ma_gap),
            "time_at_risk_days_60": time_at_risk_days_60,
            "0050_00631l_corr_60d": _safe_corr(returns["0050.TW"].tail(60), returns["00631L.TW"].tail(60)),
            "0050_00632r_corr_60d": _safe_corr(returns["0050.TW"].tail(60), returns.get("00632R.TW", pd.Series(dtype=float))),
            "2330_0050_corr_60d": _safe_corr(returns.get("2330.TW", pd.Series(dtype=float)), returns["0050.TW"].tail(60)),
            "etf_coupling_score": _last_float(coupling_score),
            "etf_coupling_percentile_252d": _rank_last(coupling_score, 252),
            "00631l_volume_z_60d": _last_float(volume_z),
            "00631l_abs_return_z_60d": _last_float(absret_z),
            "reflexivity_proxy_score": _last_float(reflexivity_proxy),
            "reflexivity_proxy_percentile_252d": _rank_last(reflexivity_proxy, 252),
        },
        "states": {
            "time_at_risk_state": _state_from_score(time_score),
            "etf_coupling_state": coupling_state,
            "reflexivity_proxy_state": reflexivity_state,
            "systemic_score": systemic_score,
            "overall_state": overall_state,
        },
        "decision": {
            "summary": (
                "Import 1212.2833 as systemic-risk governance only. This diagnostic can support manual review "
                "and 00631L add-blocking evidence, but it never unlocks execution or changes target weights."
            ),
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"{stamp}.json"


def write_report(report: dict[str, Any], output: Path, latest: Path | None, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if latest is not None:
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report["latest"]["date"]).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="2100-01-01")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--latest", default=str(DEFAULT_LATEST))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-latest", action="store_true")
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    panel = _load_panel(_resolve(args.db), DEFAULT_TICKERS, args.start, args.end)
    report = build_review(panel)
    latest = None if args.no_latest else _resolve(args.latest)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    output = _resolve(args.output)
    write_report(report, output, latest, history_dir)
    print(f"Systemic bubble time-at-risk review: {output}")
    if latest is not None:
        print(f"Latest pointer: {latest}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, report['latest']['date'])}")
    print(
        json.dumps(
            {
                "overall_state": report["states"]["overall_state"],
                "systemic_score": report["states"]["systemic_score"],
                "allow_00631l_add": report["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
