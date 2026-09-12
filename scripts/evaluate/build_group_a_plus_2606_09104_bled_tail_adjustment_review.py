#!/usr/bin/env python3
"""Build a 2606.09104 BLED tail-adjustment review for GroupA+.

This imports the paper's elliptical Black-Litterman heavy-tail risk idea as a
review layer only. It compares normal covariance risk with Student-t adjusted
dispersion for fixed GroupA+ target candidates and never produces live weights.
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
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import (  # noqa: E402
    DEFAULT_FORWARD_MONITOR,
    DEFAULT_LIVE_SNAPSHOT,
    DEFAULT_TICKERS,
    _load_json,
)
from scripts.evaluate.evaluate_a2118_mpc_path_shadow import _resolve_end_date  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2606_09104_bled_tail_adjustment_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2606_09104_bled_tail_adjustment_review/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _weights(payload: dict[str, Any]) -> dict[str, float]:
    return {str(k): float(v or 0.0) for k, v in payload.items()}


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


def _tail_factor(returns: pd.Series, *, normal_var_level: float = 0.05) -> dict[str, Any]:
    clean = returns.dropna()
    if len(clean) < 60:
        return {"status": "insufficient_data", "tail_factor": 1.0}
    mean = float(clean.mean())
    std = float(clean.std(ddof=0))
    if std <= 0:
        return {"status": "zero_volatility", "tail_factor": 1.0}
    empirical_var = abs(float(clean.quantile(normal_var_level)))
    normal_proxy_var = abs(mean - 1.645 * std)
    factor = empirical_var / normal_proxy_var if normal_proxy_var > 0 else 1.0
    factor = max(1.0, min(float(factor), 3.0))
    return {
        "status": "available",
        "empirical_var_5pct": _float(-empirical_var),
        "normal_proxy_var_5pct": _float(-normal_proxy_var),
        "tail_factor": _float(factor),
    }


def _target_candidates(live_snapshot: dict[str, Any], forward_monitor: dict[str, Any]) -> list[dict[str, Any]]:
    portfolio = live_snapshot.get("portfolio_state") if isinstance(live_snapshot.get("portfolio_state"), dict) else {}
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    current = _weights(portfolio.get("weights") if isinstance(portfolio.get("weights"), dict) else {})
    if "cash_weight" in portfolio:
        current["cash"] = float(portfolio.get("cash_weight") or 0.0)
    guarded = _weights(live_signal.get("target_weights") if isinstance(live_signal.get("target_weights"), dict) else {})
    raw = _weights(
        live_snapshot.get("target_weights_for_action")
        if isinstance(live_snapshot.get("target_weights_for_action"), dict)
        else {}
    )
    out = []
    if current:
        out.append({"target_name": "current_live_weights", "weights": current})
    if guarded:
        out.append({"target_name": "guarded_live_target", "weights": guarded})
    if raw:
        out.append({"target_name": "raw_a2118_seed_ensemble_target", "weights": raw})
    return out


def _portfolio_returns(returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    out = pd.Series(0.0, index=returns.index)
    for ticker in DEFAULT_TICKERS:
        weight = float(weights.get(ticker, 0.0) or 0.0)
        if weight and ticker in returns:
            out = out.add(returns[ticker].fillna(0.0) * weight, fill_value=0.0)
    return out.dropna()


def _review_target(
    *,
    name: str,
    weights: dict[str, float],
    returns: pd.DataFrame,
    tail_factors: dict[str, float],
    normal_cov: pd.DataFrame,
) -> dict[str, Any]:
    vector = np.asarray([float(weights.get(ticker, 0.0) or 0.0) for ticker in DEFAULT_TICKERS], dtype=float)
    cov = normal_cov.reindex(index=DEFAULT_TICKERS, columns=DEFAULT_TICKERS).fillna(0.0).to_numpy(dtype=float)
    scale = np.diag([np.sqrt(float(tail_factors.get(ticker, 1.0))) for ticker in DEFAULT_TICKERS])
    t_cov = scale @ cov @ scale
    normal_daily_vol = float(np.sqrt(max(vector @ cov @ vector, 0.0)))
    t_daily_vol = float(np.sqrt(max(vector @ t_cov @ vector, 0.0)))
    port = _portfolio_returns(returns, weights)
    normal_var95 = float(port.quantile(0.05)) if not port.empty else np.nan
    normal_es95 = float(port[port <= normal_var95].mean()) if not port.empty else np.nan
    adjusted_var95 = normal_var95 * (t_daily_vol / normal_daily_vol) if normal_daily_vol > 0 else normal_var95
    adjusted_es95 = normal_es95 * (t_daily_vol / normal_daily_vol) if normal_daily_vol > 0 else normal_es95
    return {
        "target_name": name,
        "target_weights": {key: float(weights.get(key, 0.0) or 0.0) for key in [*DEFAULT_TICKERS, "cash"]},
        "gross_risky_weight": _float(sum(abs(float(weights.get(t, 0.0) or 0.0)) for t in DEFAULT_TICKERS)),
        "normal_annual_vol": _float(normal_daily_vol * np.sqrt(252.0)),
        "student_t_adjusted_annual_vol": _float(t_daily_vol * np.sqrt(252.0)),
        "vol_inflation_ratio": _float(t_daily_vol / normal_daily_vol if normal_daily_vol > 0 else np.nan),
        "empirical_daily_var95": _float(normal_var95),
        "empirical_daily_es95": _float(normal_es95),
        "student_t_adjusted_daily_var95": _float(adjusted_var95),
        "student_t_adjusted_daily_es95": _float(adjusted_es95),
    }


def build_review(
    *,
    db_path: Path = DB_PATH,
    start: str = "2020-01-01",
    end: str = "latest",
    lookback_days: int = 756,
    live_snapshot_path: Path = DEFAULT_LIVE_SNAPSHOT,
    forward_monitor_path: Path = DEFAULT_FORWARD_MONITOR,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    end_resolved = _resolve_end_date(db_path, end) if end == "latest" and db_path.exists() else end
    live_snapshot = _load_json(_resolve(live_snapshot_path))
    forward_monitor = _load_json(_resolve(forward_monitor_path))
    if not db_path.exists():
        blockers.append("stock_database_missing")
        close = pd.DataFrame()
    else:
        close = _load_close(db_path, DEFAULT_TICKERS, start, str(end_resolved)).ffill(limit=3)
    if close.empty:
        blockers.append("price_panel_missing")
        returns = pd.DataFrame()
    else:
        returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).tail(lookback_days)
    targets = _target_candidates(live_snapshot, forward_monitor)
    if not targets:
        blockers.append("target_candidates_missing")
    if len(returns) < 252:
        blockers.append("insufficient_tail_review_history")
    tail_reviews: dict[str, Any] = {}
    target_reviews: list[dict[str, Any]] = []
    if not blockers:
        normal_cov = returns[list(DEFAULT_TICKERS)].cov()
        for ticker in DEFAULT_TICKERS:
            tail_reviews[ticker] = _tail_factor(returns[ticker])
        tail_factors = {
            ticker: float(payload.get("tail_factor", 1.0) or 1.0)
            for ticker, payload in tail_reviews.items()
            if isinstance(payload, dict)
        }
        for item in targets:
            target_reviews.append(
                _review_target(
                    name=item["target_name"],
                    weights=item["weights"],
                    returns=returns,
                    tail_factors=tail_factors,
                    normal_cov=normal_cov,
                )
            )
    raw = next((row for row in target_reviews if row["target_name"] == "raw_a2118_seed_ensemble_target"), {})
    guarded = next((row for row in target_reviews if row["target_name"] == "guarded_live_target"), {})
    if raw and guarded:
        raw_es = abs(float(raw.get("student_t_adjusted_daily_es95") or 0.0))
        guarded_es = abs(float(guarded.get("student_t_adjusted_daily_es95") or 0.0))
        if guarded_es > 0 and raw_es / guarded_es >= 2.0:
            warnings.append("raw_a2118_tail_adjusted_es95_materially_exceeds_guarded_target")
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2606_09104_bled_tail_adjustment_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "review_only_no_black_litterman_optimizer_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_tail_review",
        "as_of": str(end_resolved),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2606.09104.pdf",
            "paper_title": "Addressing Market Regime Changes and Heavy-Tailed Returns in Portfolio Optimization via Bayesian VAR and Elliptical Black-Litterman",
            "imported_concept": "Student_t_elliptical_dispersion_tail_adjustment",
            "not_imported": ["short_selling", "BLED_optimizer_live_weights", "TD3_actor_refinement", "zero_market_impact_assumption"],
        },
        "guardrails": {
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "unconstrained_black_litterman_optimizer_allowed": False,
            "short_selling_allowed": False,
            "forbid_simultaneous_00631l_00632r_offset": True,
        },
        "parameters": {
            "start": start,
            "end": str(end_resolved),
            "lookback_days": lookback_days,
            "tail_factor_cap": 3.0,
            "normal_var_level": 0.05,
        },
        "latest_a2118_context": {
            "strategy_id": live_signal.get("strategy_id"),
            "target_weights": live_signal.get("target_weights"),
            "market_state": live_signal.get("market_state"),
            "execution_regime": live_signal.get("execution_regime"),
        },
        "asset_tail_factors": tail_reviews,
        "target_tail_reviews": target_reviews,
        "decision": {
            "student_t_tail_adjustment_flags_raw_target": "raw_a2118_tail_adjusted_es95_materially_exceeds_guarded_target" in warnings,
            "use_as_tail_review_layer": bool(not blockers),
            "promote_bled_optimizer_to_live": False,
            "train_td3_or_bavar_bled_optimizer_now": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": "Student-t BLED adjustment is useful as a tail review layer only; it cannot generate live weights.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_review(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2606_09104_bled_tail_adjustment_review_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--lookback-days", type=int, default=756)
    parser.add_argument("--live-snapshot", default=str(DEFAULT_LIVE_SNAPSHOT))
    parser.add_argument("--forward-monitor", default=str(DEFAULT_FORWARD_MONITOR))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_review(
        db_path=_resolve(args.db_path),
        start=args.start,
        end=args.end,
        lookback_days=args.lookback_days,
        live_snapshot_path=_resolve(args.live_snapshot),
        forward_monitor_path=_resolve(args.forward_monitor),
    )
    write_review(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
