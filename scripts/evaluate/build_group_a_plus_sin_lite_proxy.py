#!/usr/bin/env python3
"""Build a research-only SIN-lite proxy for GroupA+.

This is not the full arXiv 1510.08162 Speculative Influence Network. It uses
daily OHLCV only and approximates speculative concentration with correlation,
lagged correlation, and downside co-movement. The output is shadow-only and
cannot change live weights.
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
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/sin_lite_proxy.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/sin_lite_proxy/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _float_or_none(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _load_metadata(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    try:
        return conn.execute(
            """
            SELECT ticker, canonical_ticker, asset_type, sector, industry, group_a_plus_role
            FROM ticker_metadata
            WHERE included_in_sin_lite = TRUE
            ORDER BY ticker
            """
        ).fetchdf()
    except Exception:
        return pd.DataFrame()


def _load_close_panel(conn: duckdb.DuckDBPyConnection, tickers: list[str], as_of: str | None) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()
    placeholders = ", ".join(["?"] * len(tickers))
    date_filter = "AND dt <= ?" if as_of else ""
    params: list[Any] = [*tickers]
    if as_of:
        params.append(as_of)
    local = conn.execute(
        f"""
        SELECT ticker, dt, close
        FROM ohlcv
        WHERE ticker IN ({placeholders})
          AND close IS NOT NULL
          {date_filter}
        ORDER BY dt, ticker
        """,
        params,
    ).fetchdf()

    external_tickers = [ticker for ticker in tickers if ticker not in set(local["ticker"].unique())]
    external = pd.DataFrame()
    if external_tickers:
        ext_placeholders = ", ".join(["?"] * len(external_tickers))
        ext_params: list[Any] = [*external_tickers]
        if as_of:
            ext_params.append(as_of)
        external = conn.execute(
            f"""
            SELECT ticker, dt, close
            FROM external_market_ohlcv
            WHERE provider = 'yfinance'
              AND ticker IN ({ext_placeholders})
              AND close IS NOT NULL
              {date_filter}
            ORDER BY dt, ticker
            """,
            ext_params,
        ).fetchdf()

    rows = pd.concat([local, external], ignore_index=True)
    if rows.empty:
        return pd.DataFrame()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def _pair_edges(returns: pd.DataFrame, threshold: float) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    tickers = list(returns.columns)
    for source in tickers:
        src = returns[source].shift(1)
        for target in tickers:
            if source == target:
                continue
            corr = src.corr(returns[target])
            if pd.notna(corr) and abs(float(corr)) >= threshold:
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "lag": 1,
                        "proxy": "lag1_return_correlation",
                        "value": _float_or_none(corr),
                    }
                )
    return sorted(edges, key=lambda item: abs(float(item["value"] or 0.0)), reverse=True)


def _state(score: float | None) -> dict[str, Any]:
    if score is None:
        return {"state": "unavailable", "manual_review_required": False, "state_reasons": ["score_unavailable"]}
    if score >= 0.75:
        state = "blocked_for_leverage_add"
    elif score >= 0.60:
        state = "elevated"
    elif score >= 0.45:
        state = "watch"
    else:
        state = "normal"
    reasons = [f"sin_lite_score={score:.4f}"]
    return {"state": state, "manual_review_required": state in {"elevated", "blocked_for_leverage_add"}, "state_reasons": reasons}


def build_proxy(
    *,
    db_path: Path = DEFAULT_DB,
    as_of: str | None = None,
    lookback: int = 120,
    min_history: int = 80,
    edge_threshold: float = 0.35,
) -> dict[str, Any]:
    with duckdb.connect(str(db_path), read_only=True) as conn:
        metadata = _load_metadata(conn)
        tickers = metadata["ticker"].astype(str).tolist() if not metadata.empty else []
        close = _load_close_panel(conn, tickers, as_of)

    blockers: list[str] = []
    warnings: list[str] = []
    if metadata.empty:
        blockers.append("missing_ticker_metadata")
    if close.empty:
        blockers.append("missing_price_panel")

    returns_all = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    counts = returns_all.notna().sum()
    usable_tickers = [ticker for ticker in tickers if int(counts.get(ticker, 0)) >= min_history]
    returns = returns_all[usable_tickers].dropna(how="all").tail(lookback) if usable_tickers else pd.DataFrame()
    latest_dt = str(close.index.max().date()) if not close.empty else None
    if len(usable_tickers) < 6:
        blockers.append("insufficient_sin_lite_usable_tickers")
    if len(returns) < min_history:
        blockers.append("insufficient_sin_lite_lookback_history")

    corr = returns.corr() if not returns.empty else pd.DataFrame()
    avg_abs_corr = None
    max_abs_corr = None
    if len(corr) >= 2:
        mask = ~np.eye(len(corr), dtype=bool)
        values = corr.to_numpy(dtype=float)[mask]
        values = values[np.isfinite(values)]
        if len(values):
            avg_abs_corr = float(np.mean(np.abs(values)))
            max_abs_corr = float(np.max(np.abs(values)))

    edges = _pair_edges(returns, threshold=edge_threshold) if len(usable_tickers) >= 2 else []
    possible_edges = max(len(usable_tickers) * (len(usable_tickers) - 1), 1)
    edge_density = len(edges) / possible_edges
    influence_concentration = max((abs(float(edge["value"] or 0.0)) for edge in edges), default=None)

    downside_density = None
    if "0050.TW" in returns:
        downside_days = returns["0050.TW"] < 0.0
        downside_frame = returns.loc[downside_days]
        if not downside_frame.empty:
            downside_density = float((downside_frame < 0.0).mean(axis=1).mean())
    elif not returns.empty:
        market_proxy = returns.mean(axis=1)
        downside_frame = returns.loc[market_proxy < 0.0]
        if not downside_frame.empty:
            downside_density = float((downside_frame < 0.0).mean(axis=1).mean())
            warnings.append("0050_missing_used_equal_weight_market_proxy_for_downside_density")

    lead_2330_to_0050 = returns["2330.TW"].shift(1).corr(returns["0050.TW"]) if {"2330.TW", "0050.TW"} <= set(returns) else np.nan
    lead_2330_to_00631l = (
        returns["2330.TW"].shift(1).corr(returns["00631L.TW"]) if {"2330.TW", "00631L.TW"} <= set(returns) else np.nan
    )
    recent_2330_ret5 = None
    if "2330.TW" in close and close["2330.TW"].dropna().shape[0] >= 6:
        s2330 = close["2330.TW"].dropna()
        recent_2330_ret5 = float(s2330.iloc[-1] / s2330.iloc[-6] - 1.0)
    lead_corr_values = [abs(float(x)) for x in (lead_2330_to_0050, lead_2330_to_00631l) if pd.notna(x)]
    lead_2330_score = max(lead_corr_values) if lead_corr_values else None
    if recent_2330_ret5 is not None and recent_2330_ret5 < -0.03:
        lead_2330_score = min(1.0, (lead_2330_score or 0.0) + 0.15)

    components = {
        "correlation_density": min((avg_abs_corr or 0.0) / 0.75, 1.0) if avg_abs_corr is not None else None,
        "edge_density": min(edge_density / 0.25, 1.0),
        "downside_comovement": downside_density,
        "influence_concentration": influence_concentration,
        "tsmc_lead_risk": lead_2330_score,
    }
    component_values = [value for value in components.values() if value is not None and np.isfinite(float(value))]
    score = float(np.mean(component_values)) if component_values else None
    state_payload = _state(score)

    if state_payload["manual_review_required"]:
        warnings.append(f"sin_lite_state:{state_payload['state']}")
    warnings.append("daily_ohlcv_proxy_not_full_sin_no_hmm_no_transfer_entropy")
    blockers.append("sin_lite_proxy_not_validated_for_live_weight_change")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_sin_lite_proxy",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "actual_data_end": latest_dt,
        "policy": "research_only_sin_lite_proxy_no_weight_change",
        "status": "blocked" if blockers else "available_for_manual_review",
        "method": {
            "paper_equivalent": False,
            "proxy_type": "daily_ohlcv_correlation_lag_downside_comovement",
            "lookback": lookback,
            "min_history": min_history,
            "edge_threshold": edge_threshold,
        },
        "coverage": {
            "metadata_included_tickers": tickers,
            "usable_tickers": usable_tickers,
            "usable_ticker_count": len(usable_tickers),
            "lookback_observations": int(len(returns)),
            "latest_dt": latest_dt,
        },
        "latest": {
            "sin_lite_score": _float_or_none(score),
            "state": state_payload["state"],
            "manual_review_required": state_payload["manual_review_required"],
            "state_reasons": state_payload["state_reasons"],
            "components": {key: _float_or_none(value) for key, value in components.items()},
            "avg_abs_corr": _float_or_none(avg_abs_corr),
            "max_abs_corr": _float_or_none(max_abs_corr),
            "edge_count": len(edges),
            "edge_density": _float_or_none(edge_density),
            "downside_density": _float_or_none(downside_density),
            "lead_2330_to_0050_corr": _float_or_none(lead_2330_to_0050),
            "lead_2330_to_00631l_corr": _float_or_none(lead_2330_to_00631l),
            "recent_2330_ret5": _float_or_none(recent_2330_ret5),
            "top_edges": edges[:20],
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "sin_lite_available_for_shadow_review": bool(component_values),
            "paper_equivalent": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _history_path(history_dir: Path, as_of: str | None, actual_data_end: str | None) -> Path:
    stamp = str(as_of or actual_data_end or datetime.now().strftime("%Y-%m-%d")).replace("-", "")
    return history_dir / f"sin_lite_proxy_{stamp}.json"


def write_proxy(payload: dict[str, Any], output_path: Path, history_dir: Path | None = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, payload.get("as_of"), payload.get("actual_data_end")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--lookback", type=int, default=120)
    parser.add_argument("--min-history", type=int, default=80)
    parser.add_argument("--edge-threshold", type=float, default=0.35)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_proxy(
        db_path=_resolve(args.db),
        as_of=args.as_of,
        lookback=int(args.lookback),
        min_history=int(args.min_history),
        edge_threshold=float(args.edge_threshold),
    )
    write_proxy(payload, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(f"SIN-lite proxy: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "actual_data_end": payload["actual_data_end"],
                "sin_lite_score": payload["latest"]["sin_lite_score"],
                "state": payload["latest"]["state"],
                "usable_ticker_count": payload["coverage"]["usable_ticker_count"],
                "allow_00631l_add": payload["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
