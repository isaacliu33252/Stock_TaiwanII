#!/usr/bin/env python3
"""Build a 2607.15195 cost-aware target-holding shadow for GroupA+.

The paper's transferable idea is not the oracle-signal SciPhyRL/PINN optimizer;
it is the target-holding control view with explicit execution costs. This
report evaluates whether the current A21.18 target is worth trading toward
after linear and quadratic impact costs. It never changes live weights.
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


DEFAULT_LIVE_SNAPSHOT = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_live_inference_snapshot.json"
DEFAULT_FORWARD_MONITOR = PROJECT_ROOT / "report/group_a_plus/latest/a2118_seed_averaging_forward_shadow_monitor.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2607_15195_cost_aware_target_holding_shadow.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2607_15195_cost_aware_target_holding_shadow/history"
DEFAULT_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _float(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(out):
        return None
    return round(out, digits)


def _load_adv(
    db_path: Path,
    *,
    tickers: tuple[str, ...],
    as_of: str,
    adv_window: int,
) -> dict[str, float]:
    if not db_path.exists():
        return {}
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT ticker, dt, close, volume
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt <= ?
            ORDER BY dt DESC
            """,
            [*tickers, as_of],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return {}
    rows["notional"] = rows["close"].astype(float) * rows["volume"].astype(float)
    out: dict[str, float] = {}
    for ticker, group in rows.groupby("ticker"):
        sample = group.sort_values("dt", ascending=False).head(adv_window)
        value = float(sample["notional"].mean())
        if np.isfinite(value) and value > 0:
            out[str(ticker)] = value
    return out


def _target_shares(total_assets: float, prices: dict[str, float], target_weights: dict[str, float]) -> dict[str, int]:
    out: dict[str, int] = {}
    for ticker, weight in target_weights.items():
        if ticker == "cash":
            continue
        price = float(prices.get(ticker, 0.0) or 0.0)
        if price <= 0:
            out[ticker] = 0
        else:
            out[ticker] = int(round(total_assets * float(weight or 0.0) / price))
    return out


def _scenario(
    *,
    name: str,
    target_weights: dict[str, float],
    current_shares: dict[str, float],
    current_weights: dict[str, float],
    prices: dict[str, float],
    total_assets: float,
    cash_balance: float,
    adv_notional: dict[str, float],
    linear_cost_bps: float,
    quadratic_impact_bps: float,
    min_trade_notional: float,
    max_turnover_for_low_cost: float,
) -> dict[str, Any]:
    target = {ticker: float(target_weights.get(ticker, 0.0) or 0.0) for ticker in [*DEFAULT_TICKERS, "cash"]}
    target_share_map = _target_shares(total_assets, prices, target)
    trades: list[dict[str, Any]] = []
    total_abs_notional = 0.0
    linear_cost = 0.0
    quadratic_cost = 0.0
    for ticker in DEFAULT_TICKERS:
        price = float(prices.get(ticker, 0.0) or 0.0)
        current = float(current_shares.get(ticker, 0.0) or 0.0)
        target_share = float(target_share_map.get(ticker, 0.0) or 0.0)
        delta = target_share - current
        notional = abs(delta) * price
        if notional < min_trade_notional:
            executable_delta = 0.0
            suppressed = True
        else:
            executable_delta = delta
            suppressed = False
        executable_notional = abs(executable_delta) * price
        adv = float(adv_notional.get(ticker, 0.0) or 0.0)
        participation = executable_notional / adv if adv > 0 else None
        linear = executable_notional * linear_cost_bps / 10000.0
        quadratic = 0.0 if participation is None else executable_notional * quadratic_impact_bps / 10000.0 * participation * participation
        total_abs_notional += executable_notional
        linear_cost += linear
        quadratic_cost += quadratic
        trades.append(
            {
                "ticker": ticker,
                "side": "buy" if executable_delta > 0 else "sell" if executable_delta < 0 else "hold",
                "current_shares": _float(current, 4),
                "target_shares": int(round(target_share)),
                "delta_shares": int(round(executable_delta)),
                "price": _float(price, 4),
                "trade_notional": _float(executable_notional),
                "adv_notional_20d": _float(adv),
                "participation_of_adv": _float(participation),
                "linear_cost": _float(linear),
                "quadratic_impact_cost": _float(quadratic),
                "suppressed_by_min_trade_notional": suppressed,
            }
        )
    total_cost = linear_cost + quadratic_cost
    turnover = total_abs_notional / total_assets if total_assets > 0 else np.nan
    total_cost_bps_assets = total_cost / total_assets * 10000.0 if total_assets > 0 else np.nan
    current_deviation = 0.5 * sum(abs(float(current_weights.get(k, 0.0) or 0.0) - target.get(k, 0.0)) for k in target)
    if total_abs_notional == 0:
        state = "NO_TRADE_NEEDED"
    elif turnover <= max_turnover_for_low_cost and total_cost_bps_assets <= linear_cost_bps * 1.5:
        state = "EXECUTION_LOW_COST"
    elif total_cost_bps_assets <= linear_cost_bps * 3.0:
        state = "EXECUTION_WEAK"
    else:
        state = "EXECUTION_COSTLY"
    return {
        "scenario": name,
        "target_weights": target,
        "current_deviation_l1_half": _float(current_deviation),
        "target_shares": target_share_map,
        "trade_count": int(sum(1 for row in trades if row["side"] != "hold")),
        "turnover": _float(turnover),
        "total_trade_notional": _float(total_abs_notional),
        "linear_cost": _float(linear_cost),
        "quadratic_impact_cost": _float(quadratic_cost),
        "total_estimated_cost": _float(total_cost),
        "total_estimated_cost_bps_of_assets": _float(total_cost_bps_assets),
        "cash_balance_before": _float(cash_balance),
        "execution_cost_state": state,
        "trades": trades,
    }


def build_shadow(
    *,
    db_path: Path = DB_PATH,
    live_snapshot_path: Path = DEFAULT_LIVE_SNAPSHOT,
    forward_monitor_path: Path = DEFAULT_FORWARD_MONITOR,
    linear_cost_bps: float = 5.0,
    quadratic_impact_bps: float = 25.0,
    adv_window: int = 20,
    min_trade_notional: float = 5000.0,
    max_turnover_for_low_cost: float = 0.05,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    live_snapshot = _load_json(_resolve(live_snapshot_path))
    forward_monitor = _load_json(_resolve(forward_monitor_path))
    portfolio = live_snapshot.get("portfolio_state") if isinstance(live_snapshot.get("portfolio_state"), dict) else {}
    live_signal = forward_monitor.get("live_signal") if isinstance(forward_monitor.get("live_signal"), dict) else {}
    current_shares = portfolio.get("shares") if isinstance(portfolio.get("shares"), dict) else {}
    current_weights = portfolio.get("weights") if isinstance(portfolio.get("weights"), dict) else {}
    if "cash_weight" in portfolio:
        current_weights = {**current_weights, "cash": float(portfolio.get("cash_weight") or 0.0)}
    prices = portfolio.get("latest_prices") if isinstance(portfolio.get("latest_prices"), dict) else {}
    total_assets = float(portfolio.get("total_assets", 0.0) or 0.0)
    cash_balance = float(portfolio.get("cash_balance", 0.0) or 0.0)
    as_of = str(live_snapshot.get("as_of") or forward_monitor.get("as_of") or datetime.now().date())
    guarded_target = live_signal.get("target_weights") if isinstance(live_signal.get("target_weights"), dict) else {}
    raw_target = (
        live_snapshot.get("target_weights_for_action")
        if isinstance(live_snapshot.get("target_weights_for_action"), dict)
        else {}
    )

    if not portfolio:
        blockers.append("live_inference_portfolio_state_missing")
    if total_assets <= 0:
        blockers.append("portfolio_total_assets_missing")
    if not guarded_target:
        blockers.append("guarded_live_target_weights_missing")
    if not raw_target:
        warnings.append("raw_a2118_target_weights_missing")

    adv = _load_adv(db_path, tickers=DEFAULT_TICKERS, as_of=as_of, adv_window=adv_window)
    if len(adv) < len(DEFAULT_TICKERS):
        warnings.append("adv_notional_incomplete")

    scenarios: list[dict[str, Any]] = []
    if not blockers:
        scenarios.append(
            _scenario(
                name="guarded_live_target",
                target_weights=guarded_target,
                current_shares={str(k): float(v) for k, v in current_shares.items()},
                current_weights={str(k): float(v) for k, v in current_weights.items()},
                prices={str(k): float(v) for k, v in prices.items()},
                total_assets=total_assets,
                cash_balance=cash_balance,
                adv_notional=adv,
                linear_cost_bps=linear_cost_bps,
                quadratic_impact_bps=quadratic_impact_bps,
                min_trade_notional=min_trade_notional,
                max_turnover_for_low_cost=max_turnover_for_low_cost,
            )
        )
        if raw_target:
            scenarios.append(
                _scenario(
                    name="raw_a2118_seed_ensemble_target",
                    target_weights=raw_target,
                    current_shares={str(k): float(v) for k, v in current_shares.items()},
                    current_weights={str(k): float(v) for k, v in current_weights.items()},
                    prices={str(k): float(v) for k, v in prices.items()},
                    total_assets=total_assets,
                    cash_balance=cash_balance,
                    adv_notional=adv,
                    linear_cost_bps=linear_cost_bps,
                    quadratic_impact_bps=quadratic_impact_bps,
                    min_trade_notional=min_trade_notional,
                    max_turnover_for_low_cost=max_turnover_for_low_cost,
                )
            )
    guarded = next((row for row in scenarios if row["scenario"] == "guarded_live_target"), {})
    raw = next((row for row in scenarios if row["scenario"] == "raw_a2118_seed_ensemble_target"), {})
    if raw and guarded and float(raw.get("turnover") or 0.0) > float(guarded.get("turnover") or 0.0) * 5:
        warnings.append("raw_a2118_target_is_much_more_costly_than_guarded_live_target")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2607_15195_cost_aware_target_holding_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "status": "blocked" if blockers else "available_for_shadow_monitoring",
        "as_of": as_of,
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2607.15195.pdf",
            "paper_title": "SciPhy Reinforcement Learning for Portfolio Optimization",
            "imported_concept": "target_holding_control_with_explicit_linear_and_quadratic_execution_costs",
            "not_imported": ["oracle_signal", "pinn_hjb_optimizer", "live_policy_replacement"],
        },
        "parameters": {
            "linear_cost_bps": linear_cost_bps,
            "quadratic_impact_bps": quadratic_impact_bps,
            "adv_window": adv_window,
            "min_trade_notional": min_trade_notional,
            "max_turnover_for_low_cost": max_turnover_for_low_cost,
        },
        "current_context": {
            "portfolio_total_assets": _float(total_assets),
            "cash_balance": _float(cash_balance),
            "current_weights": current_weights,
            "guarded_live_target_weights": guarded_target,
            "raw_a2118_target_weights": raw_target,
            "live_strategy_id": live_signal.get("strategy_id"),
            "market_state": live_signal.get("market_state"),
        },
        "scenarios": scenarios,
        "decision": {
            "preferred_target_for_execution_review": "guarded_live_target",
            "cost_aware_execution_state": guarded.get("execution_cost_state"),
            "raw_a2118_target_allowed_to_override_guarded_target": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "replace_a2118": False,
            "summary": "Evaluate target-holding execution cost only; do not change A21.18 target weights or execution permissions.",
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
    }


def write_shadow(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    as_of = str(report.get("as_of") or datetime.now().date())
    (history_dir / f"2607_15195_cost_aware_target_holding_shadow_{as_of.replace('-', '')}.json").write_text(
        text + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--live-snapshot", default=str(DEFAULT_LIVE_SNAPSHOT))
    parser.add_argument("--forward-monitor", default=str(DEFAULT_FORWARD_MONITOR))
    parser.add_argument("--linear-cost-bps", type=float, default=5.0)
    parser.add_argument("--quadratic-impact-bps", type=float, default=25.0)
    parser.add_argument("--adv-window", type=int, default=20)
    parser.add_argument("--min-trade-notional", type=float, default=5000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_shadow(
        db_path=_resolve(args.db_path),
        live_snapshot_path=_resolve(args.live_snapshot),
        forward_monitor_path=_resolve(args.forward_monitor),
        linear_cost_bps=args.linear_cost_bps,
        quadratic_impact_bps=args.quadratic_impact_bps,
        adv_window=args.adv_window,
        min_trade_notional=args.min_trade_notional,
    )
    write_shadow(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
