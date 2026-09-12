#!/usr/bin/env python3
"""Build Taiwan ETF erosion-persistence proxy shadow for GroupA+.

arXiv 2608.08405 requires an accumulation/erosion kernel before finite-hold
capacity evidence can be deattenuated. GroupA+ has no randomized deployment
experiment, so this script only estimates an OHLCV-based persistence proxy. It
is not a causal capacity kernel and cannot change target weights.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_erosion_persistence_shadow.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2608_08405_erosion_persistence_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2608_08405_erosion_persistence_shadow/history"
DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_ohlcv(db_path: Path, *, tickers: tuple[str, ...], as_of: str | None) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame(columns=["dt", "ticker", "close", "volume"])
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if "ohlcv" not in tables:
            return pd.DataFrame(columns=["dt", "ticker", "close", "volume"])
        placeholders = ",".join(["?"] * len(tickers))
        params: list[Any] = list(tickers)
        date_clause = ""
        if as_of:
            date_clause = "AND dt <= ?"
            params.append(as_of)
        return con.execute(
            f"""
            SELECT dt, ticker, close, volume
            FROM ohlcv
            WHERE ticker IN ({placeholders}) {date_clause}
            ORDER BY ticker, dt
            """,
            params,
        ).fetchdf()
    finally:
        con.close()


def _finite_hold_fraction(*, persistence: float, hold_periods: int) -> dict[str, Any]:
    if hold_periods <= 0 or not 0.0 <= persistence < 1.0:
        return {"hold_periods": hold_periods, "valid": False}
    terminal = 1.0 - persistence**hold_periods
    average = 1.0 - persistence * (1.0 - persistence**hold_periods) / (hold_periods * (1.0 - persistence))
    return {
        "hold_periods": int(hold_periods),
        "persistence": float(persistence),
        "terminal_fraction_f_l": float(terminal),
        "block_average_fraction_g_l": float(average),
        "steady_state_shortfall_block_average": float(1.0 - average),
    }


def _half_life(phi: float) -> float | None:
    if phi <= 0.0:
        return 0.0
    if phi >= 1.0:
        return None
    return float(math.log(0.5) / math.log(phi))


def _ticker_estimate(frame: pd.DataFrame, *, ticker: str, hold_periods: tuple[int, ...]) -> dict[str, Any]:
    local = frame[frame["ticker"] == ticker].copy()
    if local.empty or len(local) < 80:
        return {"ticker": ticker, "status": "insufficient_ohlcv_history", "row_count": int(len(local))}
    local["close"] = pd.to_numeric(local["close"], errors="coerce")
    local["volume"] = pd.to_numeric(local["volume"], errors="coerce")
    local = local.dropna(subset=["close", "volume"])
    local = local[(local["close"] > 0) & (local["volume"] > 0)].copy()
    local["log_return"] = local["close"].map(math.log).diff()
    local["erosion_proxy"] = local["log_return"].abs() * local["volume"].map(math.log1p)
    proxy = local["erosion_proxy"].replace([math.inf, -math.inf], pd.NA).dropna()
    if len(proxy) < 80 or float(proxy.std(ddof=0)) == 0.0:
        return {"ticker": ticker, "status": "insufficient_proxy_variation", "row_count": int(len(proxy))}
    phi_raw = float(proxy.autocorr(lag=1))
    phi_for_hold = min(max(phi_raw, 0.0), 0.995)
    return {
        "ticker": ticker,
        "status": "proxy_available_not_causal_kernel",
        "row_count": int(len(proxy)),
        "first_date": str(local["dt"].iloc[0])[:10],
        "last_date": str(local["dt"].iloc[-1])[:10],
        "proxy_definition": "abs(log_return) * log1p(volume)",
        "ar1_persistence_raw": phi_raw,
        "ar1_persistence_nonnegative_clipped": phi_for_hold,
        "half_life_days": _half_life(phi_for_hold),
        "finite_hold_attenuation_proxy": [
            _finite_hold_fraction(persistence=phi_for_hold, hold_periods=period) for period in hold_periods
        ],
    }


def build_report(
    *,
    db_path: Path,
    tickers: tuple[str, ...],
    as_of: str | None,
    hold_periods: tuple[int, ...],
) -> dict[str, Any]:
    frame = _load_ohlcv(db_path, tickers=tickers, as_of=as_of)
    estimates = [_ticker_estimate(frame, ticker=ticker, hold_periods=hold_periods) for ticker in tickers]
    available = [row for row in estimates if row.get("status") == "proxy_available_not_causal_kernel"]
    clipped = [float(row["ar1_persistence_nonnegative_clipped"]) for row in available]
    median_phi = float(pd.Series(clipped).median()) if clipped else None

    blockers = [
        "randomized_deployment_erosion_kernel_missing",
        "proxy_not_causal_capacity_evidence",
        "same_run_realized_deployment_not_used",
    ]
    if not available:
        blockers.append("ohlcv_proxy_persistence_unavailable")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2608_08405_erosion_persistence_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "proxy_available_not_calibrated_kernel" if available else "blocked",
        "policy": "research_only_erosion_persistence_proxy_no_weight_change",
        "as_of": as_of or (str(frame["dt"].max())[:10] if not frame.empty else None),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2608.08405_robustness_or_crowding_strategy_capacity.pdf",
            "concept": "finite_hold_capacity_requires_steady_state_erosion_kernel_or_declared_bridge",
        },
        "summary": {
            "ticker_count": len(tickers),
            "proxy_available_count": len(available),
            "median_ar1_persistence_proxy": median_phi,
            "median_half_life_days_proxy": _half_life(median_phi) if median_phi is not None else None,
        },
        "ticker_estimates": estimates,
        "blocking_reasons": blockers,
        "decision": {
            "steady_state_kernel_calibrated_to_group_a_plus": False,
            "proxy_can_replace_randomized_kernel": False,
            "capacity_deattenuation_allowed": False,
            "capacity_scaling_allowed": False,
            "latest_strategy_change_allowed": False,
            "target_weight_change_allowed": False,
            "summary": (
                "OHLCV persistence proxies are available for monitoring, but they are not the "
                "causal deployment-erosion kernel required by the paper. Do not deattenuate "
                "capacity or scale capital from this proxy."
            ),
        },
        "inputs": {"db": str(db_path), "tickers": list(tickers)},
    }


def _markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    decision = report["decision"]
    lines = [
        "# 2608.08405 Erosion Persistence Shadow",
        "",
        f"- status: {report['status']}",
        f"- as_of: {report.get('as_of')}",
        f"- policy: {report['policy']}",
        f"- proxy_available_count: {summary['proxy_available_count']}",
        f"- median_ar1_persistence_proxy: {summary['median_ar1_persistence_proxy']}",
        f"- median_half_life_days_proxy: {summary['median_half_life_days_proxy']}",
        f"- steady_state_kernel_calibrated_to_group_a_plus: {decision['steady_state_kernel_calibrated_to_group_a_plus']}",
        f"- capacity_deattenuation_allowed: {decision['capacity_deattenuation_allowed']}",
        "",
        "## Blocking Reasons",
    ]
    lines.extend(f"- {item}" for item in report["blocking_reasons"])
    lines.extend(["", "## Ticker Estimates"])
    for row in report["ticker_estimates"]:
        lines.append(
            "- {ticker}: status={status}, ar1={ar1}, half_life_days={half_life}".format(
                ticker=row["ticker"],
                status=row["status"],
                ar1=row.get("ar1_persistence_raw"),
                half_life=row.get("half_life_days"),
            )
        )
    lines.extend(["", "## Decision", decision["summary"], ""])
    return "\n".join(lines)


def _history_path(history_dir: Path, report: dict[str, Any]) -> Path:
    date = str(report.get("as_of") or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"2608_08405_erosion_persistence_shadow_{date}.json"


def write_report(report: dict[str, Any], *, output_path: Path, markdown_path: Path | None, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(_markdown(report), encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--hold-periods", type=int, nargs="+", default=[20, 60, 120])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    tickers = tuple(item.strip() for item in args.tickers.split(",") if item.strip())
    report = build_report(
        db_path=_resolve(args.db),
        tickers=tickers,
        as_of=args.as_of,
        hold_periods=tuple(args.hold_periods),
    )
    output = _resolve(args.output)
    markdown = _resolve(args.markdown) if args.markdown else None
    history = None if args.no_history else _resolve(args.history_dir)
    write_report(report, output_path=output, markdown_path=markdown, history_dir=history)
    print(f"2608.08405 erosion persistence shadow: {output}")
    print(json.dumps({"status": report["status"], "blockers": report["blocking_reasons"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
