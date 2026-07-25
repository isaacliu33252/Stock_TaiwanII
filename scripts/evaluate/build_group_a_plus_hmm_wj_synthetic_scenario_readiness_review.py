#!/usr/bin/env python3
"""Build a research-only HMM-WJ synthetic scenario readiness review.

Inspired by arXiv 2603.10202. This checks whether GroupA+ has enough local data
and governance coverage to begin a future hybrid-HMM-with-jump-duration
synthetic scenario harness. It does not generate synthetic paths and never
changes target weights.
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
DEFAULT_FINSTRESSTS = PROJECT_ROOT / "report/group_a_plus/latest/finstressts_decision_snapshot.json"
DEFAULT_TRIGATE = PROJECT_ROOT / "report/group_a_plus/latest/trigate_vol_memory_shadow.json"
DEFAULT_SYSTEMIC_BUBBLE = PROJECT_ROOT / "report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/hmm_wj_synthetic_scenario_readiness/history"
DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "2330.TW")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _load_close_panel(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if "ohlcv" in tables:
            rows = con.execute(
                """
                SELECT dt, ticker, close, 'ohlcv' AS source_table
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
                SELECT dt, ticker, close, 'external_market_ohlcv' AS source_table
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
        return pd.DataFrame()
    rows = pd.concat(frames, ignore_index=True)
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    rows["_source_priority"] = rows["source_table"].map({"ohlcv": 0, "external_market_ohlcv": 1}).fillna(9)
    rows = rows.sort_values(["dt", "ticker", "_source_priority"]).drop_duplicates(["dt", "ticker"], keep="first")
    return rows.pivot(index="dt", columns="ticker", values="close").sort_index().astype(float)


def _series_stats(close: pd.Series, *, min_rows: int, min_tail_obs: int) -> dict[str, Any]:
    clean = close.dropna()
    returns = clean.pct_change(fill_method=None).dropna()
    if returns.empty:
        return {
            "rows": int(len(clean)),
            "return_rows": 0,
            "first_date": str(clean.index.min().date()) if len(clean) else None,
            "last_date": str(clean.index.max().date()) if len(clean) else None,
            "tail_obs_low_5pct": 0,
            "tail_obs_high_95pct": 0,
            "tail_transition_count": 0,
            "data_ready": False,
        }
    low = returns.quantile(0.05)
    high = returns.quantile(0.95)
    low_tail = returns <= low
    high_tail = returns >= high
    tail = low_tail | high_tail
    tail_transition_count = int((tail & tail.shift(1, fill_value=False)).sum())
    tail_obs_low = int(low_tail.sum())
    tail_obs_high = int(high_tail.sum())
    data_ready = bool(len(returns) >= min_rows and tail_obs_low >= min_tail_obs and tail_obs_high >= min_tail_obs)
    return {
        "rows": int(len(clean)),
        "return_rows": int(len(returns)),
        "first_date": str(clean.index.min().date()),
        "last_date": str(clean.index.max().date()),
        "tail_obs_low_5pct": tail_obs_low,
        "tail_obs_high_95pct": tail_obs_high,
        "tail_transition_count": tail_transition_count,
        "ann_vol": float(returns.std() * np.sqrt(252.0)) if len(returns) > 1 else None,
        "excess_kurtosis": float(returns.kurt()) if len(returns) > 3 else None,
        "abs_return_acf_1d": None if len(returns) < 20 else float(returns.abs().autocorr(lag=1)),
        "data_ready": data_ready,
    }


def build_review(
    *,
    db_path: Path,
    finstressts_path: Path,
    trigate_path: Path,
    systemic_bubble_path: Path,
    start: str = "2015-01-05",
    end: str = "2100-01-01",
    min_rows: int = 1000,
    min_tail_obs: int = 50,
) -> dict[str, Any]:
    close = _load_close_panel(db_path, DEFAULT_TICKERS, start, end)
    coverage = {
        ticker: _series_stats(close[ticker], min_rows=min_rows, min_tail_obs=min_tail_obs)
        if ticker in close
        else {
            "rows": 0,
            "return_rows": 0,
            "first_date": None,
            "last_date": None,
            "tail_obs_low_5pct": 0,
            "tail_obs_high_95pct": 0,
            "tail_transition_count": 0,
            "data_ready": False,
        }
        for ticker in DEFAULT_TICKERS
    }
    data_ready = all(row["data_ready"] for row in coverage.values())

    finstressts = _load_json(finstressts_path)
    trigate = _load_json(trigate_path)
    systemic = _load_json(systemic_bubble_path)
    tri_state = trigate.get("tri_gate_state") or {}
    systemic_states = systemic.get("states") or {}

    blockers: list[str] = []
    warnings: list[str] = []
    if not data_ready:
        blockers.append("insufficient_local_tail_state_data")
    if not finstressts:
        blockers.append("missing_finstressts_decision_snapshot")
    if not trigate:
        blockers.append("missing_trigate_vol_memory_shadow")
    if not systemic:
        blockers.append("missing_systemic_bubble_time_at_risk_review")
    if finstressts.get("status") == "blocked":
        blockers.append("finstressts_snapshot_blocked")
    if tri_state.get("state") == "blocked_for_leverage_add":
        blockers.append("trigate_vol_memory_blocks_leverage_add")
    if systemic_states.get("overall_state") == "blocked_for_leverage_add":
        blockers.append("systemic_bubble_time_at_risk_blocks_leverage_add")

    blockers.append("hmm_wj_generator_not_implemented")
    blockers.append("taiwan_etf_walkforward_validation_missing")
    warnings.append("readiness_only_no_synthetic_paths_generated")

    latest_dates = [row["last_date"] for row in coverage.values() if row.get("last_date")]
    as_of = max(latest_dates) if latest_dates else None
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_hmm_wj_synthetic_scenario_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_hmm_wj_readiness_no_synthetic_alpha_no_weight_change",
        "status": "blocked" if blockers else "research_ready",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2603.10202.pdf",
            "title": "Hybrid Hidden Markov Model for Modeling Equity Excess Growth Rate Dynamics: A Discrete-State Approach with Jump-Diffusion",
            "imported_concepts": [
                "synthetic_scenario_quality_gate",
                "jump_duration_tail_state_dwell_times",
                "direct_counting_quantile_state_transitions",
                "student_t_copula_dependence_concept",
            ],
            "not_imported": [
                "HMM_WJ_live_trading_signal",
                "synthetic_paths_as_alpha",
                "SPY_or_SP500_hyperparameters_for_Taiwan_ETFs",
                "automatic_target_weight_change",
            ],
        },
        "readiness_thresholds": {
            "min_return_rows_per_ticker": min_rows,
            "min_low_tail_obs_per_ticker": min_tail_obs,
            "min_high_tail_obs_per_ticker": min_tail_obs,
            "tail_definition": "empirical 5pct / 95pct returns per ticker",
        },
        "data_readiness": {
            "tickers": coverage,
            "all_required_tickers_ready": data_ready,
        },
        "validation_readiness": {
            "generator_implemented": False,
            "synthetic_paths_generated": False,
            "ks_ad_wasserstein_hellinger_acf_mae_available": False,
            "taiwan_etf_walkforward_validated": False,
            "student_t_copula_validated": False,
        },
        "existing_research_blockers": {
            "finstressts_status": finstressts.get("status"),
            "finstressts_allow_00631l_add": _decision(finstressts).get("allow_00631l_add"),
            "trigate_state": tri_state.get("state"),
            "trigate_stress_gate_count": tri_state.get("stress_gate_count"),
            "systemic_bubble_state": systemic_states.get("overall_state"),
            "systemic_bubble_score": systemic_states.get("systemic_score"),
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "HMM-WJ scenario readiness is diagnostic only. Local data may be sufficient for future research, "
                "but no synthetic generator or Taiwan ETF walk-forward validation is available, so it cannot "
                "affect execution."
            ),
            "can_generate_scenarios_for_decision": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "db": str(db_path),
            "finstressts": str(finstressts_path),
            "trigate_vol_memory": str(trigate_path),
            "systemic_bubble_time_at_risk": str(systemic_bubble_path),
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, review.get("as_of")).write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--finstressts", default=str(DEFAULT_FINSTRESSTS))
    parser.add_argument("--trigate", default=str(DEFAULT_TRIGATE))
    parser.add_argument("--systemic-bubble", default=str(DEFAULT_SYSTEMIC_BUBBLE))
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="2100-01-01")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        db_path=_resolve(args.db),
        finstressts_path=_resolve(args.finstressts),
        trigate_path=_resolve(args.trigate),
        systemic_bubble_path=_resolve(args.systemic_bubble),
        start=args.start,
        end=args.end,
    )
    history_dir = None if args.no_history else _resolve(args.history_dir)
    output = _resolve(args.output)
    write_review(review, output, history_dir)
    print(f"HMM-WJ synthetic scenario readiness review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review.get('as_of'))}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "all_required_tickers_ready": review["data_readiness"]["all_required_tickers_ready"],
                "can_generate_scenarios_for_decision": review["decision"]["can_generate_scenarios_for_decision"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
