#!/usr/bin/env python3
"""Build a research-only market-impact readiness review for GroupA+.

This imports governance ideas from arXiv 2603.29086, not a DRL environment:
flat-fee backtests are not enough; any rebalance or optimizer proposal should
carry impact, turnover, participation-rate, and cost-model readiness checks.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report/group_a_plus/latest/live_signal_20260720_estimate.json"
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan.json"
DEFAULT_REBALANCE_REVIEW = PROJECT_ROOT / "report/group_a_plus/latest/rebalance_review_20260720.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review_20260720.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/market_impact_readiness/history"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else payload


def _latest_volume(db_path: Path, ticker: str, as_of: str | None) -> float | None:
    if not as_of or not db_path.exists():
        return None
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if "ohlcv" not in tables:
            return None
        row = con.execute(
            """
            SELECT volume
            FROM ohlcv
            WHERE ticker = ? AND dt <= ?
            ORDER BY dt DESC
            LIMIT 1
            """,
            [ticker, as_of],
        ).fetchone()
    finally:
        con.close()
    if row is None or row[0] is None:
        return None
    return float(row[0])


def _trade_rows(plan: dict[str, Any], db_path: Path, as_of: str | None) -> list[dict[str, Any]]:
    current = {str(k): int(v) for k, v in (plan.get("current_holdings") or {}).items()}
    target = {str(k): int(v) for k, v in (plan.get("target_shares") or {}).items()}
    prices = {str(k): float(v) for k, v in (plan.get("current_prices") or {}).items()}
    rows: list[dict[str, Any]] = []
    for ticker in sorted(set(current) | set(target)):
        if ticker == "cash":
            continue
        delta = int(target.get(ticker, 0)) - int(current.get(ticker, 0))
        price = float(prices.get(ticker, 0.0))
        notional = abs(delta) * price
        volume = _latest_volume(db_path, ticker, as_of)
        pov = abs(delta) / volume if volume and volume > 0 else None
        rows.append(
            {
                "ticker": ticker,
                "current_shares": int(current.get(ticker, 0)),
                "target_shares": int(target.get(ticker, 0)),
                "delta_shares": delta,
                "price": price,
                "trade_notional": float(notional),
                "latest_volume": volume,
                "participation_of_volume": float(pov) if pov is not None else None,
            }
        )
    return rows


def build_review(
    *,
    live_signal_path: Path,
    execution_plan_path: Path,
    rebalance_review_path: Path,
    db_path: Path,
    max_trade_pov: float,
    max_turnover: float,
) -> dict[str, Any]:
    live = _unwrap(_load(live_signal_path))
    plan = _unwrap(_load(execution_plan_path))
    rebalance = _load(rebalance_review_path)

    actual_date = live.get("actual_data_date")
    plan_date = plan.get("actual_data_date")
    total_assets = float(plan.get("current_total_assets") or 0.0)
    trade_rows = _trade_rows(plan, db_path, plan_date or actual_date)
    total_trade_notional = sum(float(row["trade_notional"]) for row in trade_rows)
    turnover = total_trade_notional / total_assets if total_assets > 0 else None
    max_pov_observed = max(
        (float(row["participation_of_volume"]) for row in trade_rows if row["participation_of_volume"] is not None),
        default=None,
    )

    rebalance_decision = rebalance.get("decision") or {}
    blockers: list[str] = []
    warnings: list[str] = []
    if not live.get("execution_allowed"):
        blockers.append("live_signal_execution_not_allowed")
    if plan_date and actual_date and plan_date != actual_date:
        blockers.append("execution_plan_stale_vs_live_signal")
    if rebalance_decision.get("auto_rebalance_allowed") is not True:
        blockers.append("rebalance_review_disallows_auto_rebalance")
    if turnover is None:
        blockers.append("turnover_unavailable")
    elif turnover > max_turnover:
        blockers.append("turnover_exceeds_limit")
    if max_pov_observed is None:
        warnings.append("pov_unavailable_from_ohlcv")
    elif max_pov_observed > max_trade_pov:
        blockers.append("participation_of_volume_exceeds_limit")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_market_impact_readiness_review",
        "status": "blocked" if blockers else "available_for_manual_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_pretrade_readiness_only_no_weight_change",
        "as_of": live.get("requested_as_of_date") or actual_date,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2603.29086.pdf",
            "title": "Realistic Market Impact Modeling for Reinforcement Learning Trading Environments",
            "imported_concepts": [
                "flat_bps_costs_can_misrank_strategies",
                "almgren_chriss_and_square_root_impact_readiness",
                "participation_of_volume_monitoring",
                "turnover_pathology_detection",
                "hpo_or_parameter_tuning_must_control_execution_behavior",
                "trade_level_logging_required",
            ],
            "not_imported": [
                "Gymnasium_DRL_environment",
                "A2C_PPO_DDPG_SAC_TD3_agents",
                "NASDAQ_100_results",
                "automatic_rebalance_or_live_execution",
            ],
        },
        "limits": {
            "max_trade_participation_of_volume": float(max_trade_pov),
            "max_total_turnover": float(max_turnover),
            "cost_model_required_before_live": "quadratic_or_square_root_impact_calibrated_to_taiwan_etf_liquidity",
        },
        "computed": {
            "execution_plan_actual_data_date": plan_date,
            "live_actual_data_date": actual_date,
            "execution_plan_stale_vs_live": bool(plan_date and actual_date and plan_date != actual_date),
            "current_total_assets": total_assets,
            "total_trade_notional": float(total_trade_notional),
            "turnover": float(turnover) if turnover is not None else None,
            "max_participation_of_volume": float(max_pov_observed) if max_pov_observed is not None else None,
            "trade_count_nonzero": int(sum(1 for row in trade_rows if row["delta_shares"] != 0)),
            "trade_rows": trade_rows,
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
        "decision": {
            "summary": (
                "Import market-impact readiness only. Current execution/rebalance gates are blocked, and "
                "the execution plan is stale, so no rebalance or optimizer-driven trade should be unlocked."
            ),
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "live_signal": str(live_signal_path),
            "execution_plan": str(execution_plan_path),
            "rebalance_review": str(rebalance_review_path),
            "db": str(db_path),
        },
    }


def _history_path(history_dir: Path, as_of: str) -> Path:
    stamp = str(as_of).replace("-", "")
    return history_dir / f"{stamp}.json"


def write_review(
    review: dict[str, Any],
    *,
    output_path: Path,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, str(review["as_of"])).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--rebalance-review", default=str(DEFAULT_REBALANCE_REVIEW))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--max-trade-pov", type=float, default=0.03)
    parser.add_argument("--max-turnover", type=float, default=0.50)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    review = build_review(
        live_signal_path=_resolve(args.live_signal),
        execution_plan_path=_resolve(args.execution_plan),
        rebalance_review_path=_resolve(args.rebalance_review),
        db_path=_resolve(args.db),
        max_trade_pov=float(args.max_trade_pov),
        max_turnover=float(args.max_turnover),
    )
    write_review(review, output_path=output, history_dir=history_dir)
    print(f"Market impact readiness review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review['as_of'])}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "turnover": review["computed"]["turnover"],
                "max_participation_of_volume": review["computed"]["max_participation_of_volume"],
                "target_weight_change_allowed": review["decision"]["target_weight_change_allowed"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "blocking_reasons": review["blocking_reasons"],
                "warning_reasons": review["warning_reasons"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
