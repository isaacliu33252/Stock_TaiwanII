#!/usr/bin/env python3
"""Build a 2607.15195 asymmetric utility shadow for GroupA+.

This imports the paper's asymmetric downside utility idea as a target-ranking
diagnostic. It compares fixed candidate weights on realized forward 20-day
returns with symmetric quadratic loss and expectile-style asymmetric loss.
It never changes live weights.
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
from scripts.evaluate.build_group_a_plus_2607_15195_soft_budget_cash_accounting_shadow import (  # noqa: E402
    _blend,
    _weights,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_expectile_utility_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_15195_expectile_utility_shadow/history"
DEFAULT_SOFT_BUDGET_SHADOW = PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_soft_budget_cash_accounting_shadow.json"


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


def _load_close_panel(db_path: Path, tickers: tuple[str, ...], start: str | None, end: str | None) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame()
    clauses = ["ticker IN (" + ", ".join(["?"] * len(tickers)) + ")"]
    params: list[Any] = list(tickers)
    if start:
        clauses.append("dt >= ?")
        params.append(start)
    if end:
        clauses.append("dt <= ?")
        params.append(end)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        df = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE {' AND '.join(clauses)}
            ORDER BY dt, ticker
            """,
            params,
        ).fetchdf()
    finally:
        con.close()
    if df.empty:
        return pd.DataFrame()
    panel = df.pivot(index="dt", columns="ticker", values="close").sort_index()
    return panel.dropna(how="all")


def _portfolio_forward_returns(
    close: pd.DataFrame,
    weights: dict[str, float],
    *,
    horizon: int,
) -> pd.Series:
    returns = close.pct_change(fill_method=None)
    weighted = pd.Series(0.0, index=returns.index)
    for ticker in DEFAULT_TICKERS:
        weight = float(weights.get(ticker, 0.0) or 0.0)
        if weight == 0.0:
            continue
        if ticker not in returns:
            return pd.Series(dtype=float)
        weighted = weighted.add(returns[ticker].fillna(0.0) * weight, fill_value=0.0)
    values = []
    dates = []
    for idx in range(0, len(weighted) - horizon):
        future = weighted.iloc[idx + 1 : idx + 1 + horizon]
        if len(future) < horizon or future.isna().any():
            continue
        dates.append(weighted.index[idx])
        values.append(float(np.prod(1.0 + future.to_numpy()) - 1.0))
    return pd.Series(values, index=dates, dtype=float)


def _expectile_loss(series: pd.Series, *, target_return: float, tau: float) -> float:
    delta = series.astype(float) - target_return
    shortfall = np.minimum(delta.to_numpy(), 0.0)
    surplus = np.maximum(delta.to_numpy(), 0.0)
    return float(np.mean(tau * shortfall * shortfall + (1.0 - tau) * surplus * surplus))


def _symmetric_loss(series: pd.Series, *, target_return: float) -> float:
    delta = series.astype(float) - target_return
    return float(np.mean(delta.to_numpy() * delta.to_numpy()))


def _review_target(
    *,
    name: str,
    weights: dict[str, float],
    close: pd.DataFrame,
    horizon: int,
    target_return: float,
    expectile_tau: float,
) -> dict[str, Any]:
    fwd = _portfolio_forward_returns(close, weights, horizon=horizon)
    if fwd.empty:
        return {
            "target_name": name,
            "target_weights": {key: float(weights.get(key, 0.0) or 0.0) for key in [*DEFAULT_TICKERS, "cash"]},
            "status": "blocked",
            "blocking_reason": "insufficient_forward_return_sample",
        }
    downside = fwd[fwd < target_return]
    worst_decile_threshold = fwd.quantile(0.10)
    worst_decile = fwd[fwd <= worst_decile_threshold]
    return {
        "target_name": name,
        "target_weights": {key: float(weights.get(key, 0.0) or 0.0) for key in [*DEFAULT_TICKERS, "cash"]},
        "status": "ok",
        "observations": int(len(fwd)),
        "sample_start": str(fwd.index.min()),
        "sample_end": str(fwd.index.max()),
        "mean_forward_return_20d": _float(fwd.mean()),
        "median_forward_return_20d": _float(fwd.median()),
        "vol_forward_return_20d": _float(fwd.std(ddof=0)),
        "min_forward_return_20d": _float(fwd.min()),
        "p05_forward_return_20d": _float(fwd.quantile(0.05)),
        "p10_forward_return_20d": _float(worst_decile_threshold),
        "shortfall_rate_vs_target": _float(float((fwd < target_return).mean())),
        "mean_shortfall_return_20d": _float(downside.mean()) if not downside.empty else None,
        "worst_decile_mean_return_20d": _float(worst_decile.mean()) if not worst_decile.empty else None,
        "symmetric_quadratic_loss": _float(_symmetric_loss(fwd, target_return=target_return), 10),
        "expectile_asymmetric_loss": _float(
            _expectile_loss(fwd, target_return=target_return, tau=expectile_tau),
            10,
        ),
    }


def _candidate_targets(
    *,
    live_snapshot: dict[str, Any],
    forward_monitor: dict[str, Any],
    soft_budget_shadow: dict[str, Any],
) -> list[dict[str, Any]]:
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
    targets: list[dict[str, Any]] = []
    if current:
        targets.append({"name": "current_live_weights", "weights": current})
    if guarded:
        targets.append({"name": "guarded_live_target", "weights": guarded})
    if raw:
        targets.append({"name": "raw_a2118_seed_ensemble_target", "weights": raw})
    decision = soft_budget_shadow.get("decision") if isinstance(soft_budget_shadow.get("decision"), dict) else {}
    guarded_fraction = decision.get("guarded_live_target_best_shadow_fraction")
    raw_fraction = decision.get("raw_a2118_best_shadow_fraction")
    if current and guarded and guarded_fraction is not None:
        targets.append(
            {
                "name": "soft_budget_best_guarded_partial",
                "weights": _blend(current, guarded, float(guarded_fraction)),
            }
        )
    if current and raw and raw_fraction is not None:
        targets.append(
            {
                "name": "soft_budget_best_raw_partial",
                "weights": _blend(current, raw, float(raw_fraction)),
            }
        )
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in targets:
        if item["name"] in seen:
            continue
        seen.add(item["name"])
        unique.append(item)
    return unique


def _rank_rows(rows: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    ok = [row for row in rows if row.get("status") == "ok" and row.get(metric) is not None]
    ranked = sorted(ok, key=lambda row: float(row[metric]))
    return [
        {"rank": idx + 1, "target_name": row["target_name"], metric: row[metric]}
        for idx, row in enumerate(ranked)
    ]


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    live_snapshot_path: Path = DEFAULT_LIVE_SNAPSHOT,
    forward_monitor_path: Path = DEFAULT_FORWARD_MONITOR,
    soft_budget_shadow_path: Path = DEFAULT_SOFT_BUDGET_SHADOW,
    start: str = "2020-01-01",
    end: str | None = None,
    horizon: int = 20,
    target_return: float = 0.0,
    expectile_tau: float = 0.90,
    min_observations: int = 250,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    live_snapshot = _load_json(_resolve(live_snapshot_path))
    forward_monitor = _load_json(_resolve(forward_monitor_path))
    soft_budget_shadow = _load_json(_resolve(soft_budget_shadow_path))
    as_of = str(live_snapshot.get("as_of") or forward_monitor.get("as_of") or end or datetime.now().date())
    if not db_path.exists():
        blockers.append("ohlcv_db_missing")
    targets = _candidate_targets(
        live_snapshot=live_snapshot,
        forward_monitor=forward_monitor,
        soft_budget_shadow=soft_budget_shadow,
    )
    if not targets:
        blockers.append("candidate_targets_missing")
    close = _load_close_panel(_resolve(db_path), DEFAULT_TICKERS, start, end or as_of) if not blockers else pd.DataFrame()
    if not close.empty and len(close) <= horizon + min_observations:
        blockers.append("insufficient_ohlcv_history")
    reviews: list[dict[str, Any]] = []
    if not blockers:
        for item in targets:
            reviews.append(
                _review_target(
                    name=item["name"],
                    weights=item["weights"],
                    close=close,
                    horizon=horizon,
                    target_return=target_return,
                    expectile_tau=expectile_tau,
                )
            )
        if any(row.get("status") == "blocked" for row in reviews):
            warnings.append("some_targets_have_insufficient_forward_return_sample")
    symmetric_rank = _rank_rows(reviews, "symmetric_quadratic_loss")
    expectile_rank = _rank_rows(reviews, "expectile_asymmetric_loss")
    best_symmetric = symmetric_rank[0]["target_name"] if symmetric_rank else None
    best_expectile = expectile_rank[0]["target_name"] if expectile_rank else None
    rank_changed = bool(best_symmetric and best_expectile and best_symmetric != best_expectile)
    if rank_changed:
        warnings.append("expectile_ranking_differs_from_symmetric_quadratic_ranking")
    upstream_blocks: list[str] = []
    if (PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_real_signal_quality_gate.json").exists():
        signal_gate = _load_json(PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_real_signal_quality_gate.json")
        if signal_gate.get("status") != "passed":
            upstream_blocks.append("real_signal_quality_gate_not_passed")
    if (PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_quadratic_impact_turnover_gate.json").exists():
        turnover_gate = _load_json(PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_quadratic_impact_turnover_gate.json")
        if turnover_gate.get("status") != "passed":
            upstream_blocks.append("quadratic_impact_turnover_gate_not_passed")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_15195_expectile_utility_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_reward_review",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.15195.pdf",
            "paper_title": "SciPhy Reinforcement Learning for Portfolio Optimization",
            "imported_concept": "expectile_style_asymmetric_downside_utility",
            "not_imported": ["oracle_signal", "pinn_hjb_optimizer", "live_reward_retraining"],
        },
        "parameters": {
            "start": start,
            "end": end or as_of,
            "horizon_trading_days": horizon,
            "target_return_20d": target_return,
            "expectile_tau": expectile_tau,
            "min_observations": min_observations,
        },
        "target_reviews": reviews,
        "rankings": {
            "symmetric_quadratic_loss_lower_is_better": symmetric_rank,
            "expectile_asymmetric_loss_lower_is_better": expectile_rank,
            "rank_changed_by_asymmetric_utility": rank_changed,
        },
        "decision": {
            "best_target_by_expectile_shadow": best_expectile,
            "best_target_by_symmetric_quadratic_shadow": best_symmetric,
            "expectile_utility_adds_target_ranking_information": rank_changed,
            "train_reward_model_now": False,
            "allow_sciphyrl_optimizer_research": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "replace_a2118": False,
            "summary": (
                "Expectile utility is a reward-review diagnostic only; upstream signal and turnover gates must pass "
                "before any SciPhyRL/PINN optimizer research or live target changes."
            ),
        },
        "upstream_blocking_reasons": sorted(set(upstream_blocks)),
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_shadow(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2607_15195_expectile_utility_shadow_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--live-snapshot", default=str(DEFAULT_LIVE_SNAPSHOT))
    parser.add_argument("--forward-monitor", default=str(DEFAULT_FORWARD_MONITOR))
    parser.add_argument("--soft-budget-shadow", default=str(DEFAULT_SOFT_BUDGET_SHADOW))
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--horizon", type=int, default=20)
    parser.add_argument("--target-return", type=float, default=0.0)
    parser.add_argument("--expectile-tau", type=float, default=0.90)
    parser.add_argument("--min-observations", type=int, default=250)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_shadow(
        db_path=_resolve(args.db_path),
        live_snapshot_path=_resolve(args.live_snapshot),
        forward_monitor_path=_resolve(args.forward_monitor),
        soft_budget_shadow_path=_resolve(args.soft_budget_shadow),
        start=args.start,
        end=args.end,
        horizon=args.horizon,
        target_return=args.target_return,
        expectile_tau=args.expectile_tau,
        min_observations=args.min_observations,
    )
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
