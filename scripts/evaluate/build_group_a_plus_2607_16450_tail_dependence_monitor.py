#!/usr/bin/env python3
"""Build a 2607.16450 tail-dependence monitor for GroupA+.

The paper lists dynamic copulas as future research. This monitor implements a
transparent empirical lower-tail co-exceedance proxy instead of a full copula:
for each rolling window, it estimates P(asset in lower tail | 0050 in lower
tail). The report is shadow-only and never changes live target weights.
"""

from __future__ import annotations

import argparse
import json
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

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_tail_dependence_monitor.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_16450_tail_dependence_monitor/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_close(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.pivot_table(index="dt", columns="ticker", values="close", aggfunc="last").sort_index()


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _tail_metrics(
    returns: pd.DataFrame,
    *,
    base: str,
    asset: str,
    alpha: float,
) -> dict[str, Any]:
    pair = returns[[base, asset]].dropna()
    if len(pair) < 30:
        return {"asset": asset, "status": "insufficient_data", "observations": int(len(pair))}
    base_q = float(pair[base].quantile(alpha))
    asset_q = float(pair[asset].quantile(alpha))
    base_tail = pair[base] <= base_q
    asset_tail = pair[asset] <= asset_q
    base_tail_n = int(base_tail.sum())
    co_n = int((base_tail & asset_tail).sum())
    cond = None if base_tail_n == 0 else float(co_n / base_tail_n)
    corr = pair.corr().iloc[0, 1]
    return {
        "asset": asset,
        "status": "available",
        "observations": int(len(pair)),
        "base_tail_threshold": _float(base_q),
        "asset_tail_threshold": _float(asset_q),
        "base_tail_days": base_tail_n,
        "co_exceedance_days": co_n,
        "lower_tail_dependence_proxy": _float(cond),
        "linear_correlation": _float(corr),
    }


def _rolling_snapshots(
    returns: pd.DataFrame,
    *,
    base: str,
    assets: tuple[str, ...],
    alpha: float,
    window: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if len(returns) < window:
        return out
    for end_idx in range(window, len(returns) + 1):
        frame = returns.iloc[end_idx - window : end_idx]
        snapshot = {"date": str(returns.index[end_idx - 1].date()), "window": window, "pairs": []}
        pairs = []
        for asset in assets:
            if asset == base or asset not in frame.columns:
                continue
            pairs.append(_tail_metrics(frame, base=base, asset=asset, alpha=alpha))
        snapshot["pairs"] = pairs
        out.append(snapshot)
    return out


def build_monitor(
    *,
    db_path: Path = DB_PATH,
    start: str = "2018-01-02",
    end: str = "latest",
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    base: str = "0050.TW",
    alpha: float = 0.10,
    window: int = 252,
    high_tail_dependence_threshold: float = 0.65,
) -> dict[str, Any]:
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" else end
    blockers: list[str] = []
    warnings: list[str] = []
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, tickers, start, end_resolved)
    if close.empty or base not in close.columns:
        blockers.append("price_panel_missing_or_base_unavailable")
        returns = pd.DataFrame()
    else:
        close = close.ffill(limit=3)
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
    available_tickers = tuple(col for col in tickers if col in returns.columns and returns[col].notna().sum() >= window)
    if base not in available_tickers:
        blockers.append("base_has_insufficient_history")
    assets = tuple(ticker for ticker in available_tickers if ticker != base)
    if not assets:
        blockers.append("no_comparison_assets_with_sufficient_history")

    snapshots = _rolling_snapshots(
        returns[list(available_tickers)] if available_tickers else returns,
        base=base,
        assets=assets,
        alpha=alpha,
        window=window,
    )
    latest = snapshots[-1] if snapshots else {"date": None, "pairs": []}
    latest_pairs = latest.get("pairs") if isinstance(latest.get("pairs"), list) else []
    high_pairs = [
        row
        for row in latest_pairs
        if isinstance(row, dict)
        and isinstance(row.get("lower_tail_dependence_proxy"), (int, float))
        and float(row["lower_tail_dependence_proxy"]) >= high_tail_dependence_threshold
    ]
    if high_pairs:
        warnings.append("high_lower_tail_dependence_pairs_present")
    if any(row.get("asset") == "00631L.TW" for row in high_pairs):
        warnings.append("00631l_lower_tail_dependence_high_vs_0050")

    decision_summary = (
        "Tail-dependence monitor is shadow-only; high lower-tail co-exceedance blocks using this future-research idea to add leverage."
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_16450_tail_dependence_monitor",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_monitoring",
        "as_of": end_resolved,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.16450.pdf",
            "future_research_concept": "dynamic_copula_tail_dependence",
            "implemented_as": "empirical_rolling_lower_tail_coexceedance_proxy",
            "paper_equivalent": False,
        },
        "parameters": {
            "tickers": list(tickers),
            "available_tickers": list(available_tickers),
            "base": base,
            "alpha": alpha,
            "window": window,
            "high_tail_dependence_threshold": high_tail_dependence_threshold,
        },
        "coverage": {
            "return_observations": int(len(returns)),
            "snapshot_count": len(snapshots),
            "actual_data_start": str(returns.index.min().date()) if not returns.empty else None,
            "actual_data_end": str(returns.index.max().date()) if not returns.empty else None,
        },
        "latest": latest,
        "high_tail_dependence_pairs": high_pairs,
        "decision": {
            "promote_dynamic_copula_gate": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add_from_tail_dependence": False,
            "summary": decision_summary,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2607_16450_tail_dependence_monitor_{stamp}.json"


def write_monitor(monitor: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(monitor, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, str(monitor.get("as_of"))).write_text(
            json.dumps(monitor, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2018-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--tickers", nargs="+", default=list(DEFAULT_TICKERS))
    parser.add_argument("--base", default="0050.TW")
    parser.add_argument("--alpha", type=float, default=0.10)
    parser.add_argument("--window", type=int, default=252)
    parser.add_argument("--high-tail-dependence-threshold", type=float, default=0.65)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    monitor = build_monitor(
        db_path=_resolve(args.db),
        start=args.start,
        end=args.end,
        tickers=tuple(args.tickers),
        base=args.base,
        alpha=float(args.alpha),
        window=int(args.window),
        high_tail_dependence_threshold=float(args.high_tail_dependence_threshold),
    )
    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_monitor(monitor, output, history_dir)
    print(f"2607.16450 tail-dependence monitor: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, str(monitor.get('as_of')))}")
    print(
        json.dumps(
            {
                "status": monitor["status"],
                "high_pairs": [row.get("asset") for row in monitor["high_tail_dependence_pairs"]],
                "allow_00631l_add": monitor["decision"]["allow_00631l_add_from_tail_dependence"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
