#!/usr/bin/env python3
"""GBM + market-impact staging shadow for GroupA+.

Research-only follow-up for arXiv:2307.07694. This script uses GBM as a
repeatable stress-test environment, not as a return forecast. It compares the
current execution plan's full target against staged target execution under a
simple Bertsimas-Lo-inspired quadratic impact cost.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = PROJECT_ROOT / "report/group_a_plus/latest/execution_plan.json"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results/2307_07694_gbm_market_impact_staging_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2307_07694_gbm_market_impact_staging_shadow.md"
EQUITY_ETF_SELL_TAX_TICKERS = {"0050.TW", "00631L.TW", "00632R.TW"}
SCENARIOS = {
    "neutral": {"annual_mu": 0.06, "annual_vol_scale": 1.0},
    "bull": {"annual_mu": 0.18, "annual_vol_scale": 1.0},
    "bear": {"annual_mu": -0.18, "annual_vol_scale": 1.2},
    "high_vol_flat": {"annual_mu": 0.00, "annual_vol_scale": 2.0},
}


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _load_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    required = ["current_holdings", "current_cash_input", "current_prices", "theoretical_target_shares"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"execution plan missing keys: {missing}")
    return data


def _target_from_plan(data: dict[str, Any], mode: str) -> dict[str, int]:
    if mode == "full":
        return {str(k): int(v) for k, v in data["theoretical_target_shares"].items()}
    if mode == "staged":
        raw = data.get("staged_target_shares_before_guards") or data.get("target_shares") or {}
        return {str(k): int(v) for k, v in raw.items()}
    raise ValueError(f"unknown target mode: {mode}")


def _portfolio_value(shares: dict[str, float], cash: float, prices: dict[str, float]) -> float:
    return float(cash + sum(float(shares.get(ticker, 0.0)) * float(price) for ticker, price in prices.items()))


def _trade_to_target(
    shares: dict[str, float],
    cash: float,
    prices: dict[str, float],
    target: dict[str, int],
    *,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    impact_scale: float,
) -> tuple[dict[str, float], float, dict[str, float]]:
    value_before = _portfolio_value(shares, cash, prices)
    total_cost = 0.0
    total_notional = 0.0
    out = dict(shares)
    for ticker in sorted(set(out) | set(target)):
        current = float(out.get(ticker, 0.0))
        wanted = float(target.get(ticker, 0))
        delta = wanted - current
        if abs(delta) < 1e-12:
            continue
        price = float(prices[ticker])
        notional = abs(delta) * price
        sell_tax = equity_etf_sell_tax if delta < 0.0 and ticker in EQUITY_ETF_SELL_TAX_TICKERS else 0.0
        linear_cost = notional * (commission_rate + slippage_rate + sell_tax)
        # Bertsimas-Lo-lite: larger one-shot trades pay convex impact.
        impact_cost = impact_scale * notional * (notional / max(value_before, 1e-12)) ** 2
        total_cost += linear_cost + impact_cost
        total_notional += notional
        cash -= delta * price
        out[ticker] = wanted
    cash -= total_cost
    return out, float(cash), {"transaction_cost": float(total_cost), "turnover_notional": float(total_notional)}


def _simulate_prices(
    *,
    tickers: list[str],
    start_prices: dict[str, float],
    horizon_days: int,
    paths: int,
    annual_mu: float,
    annual_vol_scale: float,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = len(tickers)
    base_vol = np.array([0.18 if ticker != "00631L.TW" else 0.38 for ticker in tickers], dtype=float)
    annual_vol = base_vol * float(annual_vol_scale)
    corr = np.full((n, n), 0.55, dtype=float)
    np.fill_diagonal(corr, 1.0)
    cov = np.outer(annual_vol, annual_vol) * corr / 252.0
    drift = (float(annual_mu) - 0.5 * annual_vol**2) / 252.0
    shocks = rng.multivariate_normal(drift, cov, size=(paths, horizon_days))
    prices = np.empty((paths, horizon_days + 1, n), dtype=float)
    prices[:, 0, :] = np.array([start_prices[ticker] for ticker in tickers], dtype=float)
    prices[:, 1:, :] = prices[:, :1, :] * np.exp(np.cumsum(shocks, axis=1))
    return prices


def _run_policy(
    *,
    price_path: np.ndarray,
    tickers: list[str],
    current_shares: dict[str, int],
    current_cash: float,
    staged_target: dict[str, int],
    full_target: dict[str, int],
    policy: str,
    defer_days: int,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    impact_scale: float,
) -> dict[str, float]:
    shares = {ticker: float(current_shares.get(ticker, 0)) for ticker in tickers}
    cash = float(current_cash)
    costs = 0.0
    turnover = 0.0
    day0_prices = {ticker: float(price_path[0, i]) for i, ticker in enumerate(tickers)}
    if policy == "full_day0":
        shares, cash, execution = _trade_to_target(
            shares,
            cash,
            day0_prices,
            full_target,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
            impact_scale=impact_scale,
        )
        costs += execution["transaction_cost"]
        turnover += execution["turnover_notional"]
    elif policy == "staged_then_full":
        shares, cash, execution = _trade_to_target(
            shares,
            cash,
            day0_prices,
            staged_target,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
            impact_scale=impact_scale,
        )
        costs += execution["transaction_cost"]
        turnover += execution["turnover_notional"]
        if defer_days < len(price_path):
            deferred_prices = {ticker: float(price_path[defer_days, i]) for i, ticker in enumerate(tickers)}
            shares, cash, execution = _trade_to_target(
                shares,
                cash,
                deferred_prices,
                full_target,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                equity_etf_sell_tax=equity_etf_sell_tax,
                impact_scale=impact_scale,
            )
            costs += execution["transaction_cost"]
            turnover += execution["turnover_notional"]
    else:
        raise ValueError(f"unknown policy: {policy}")
    final_prices = {ticker: float(price_path[-1, i]) for i, ticker in enumerate(tickers)}
    return {
        "final_value": _portfolio_value(shares, cash, final_prices),
        "transaction_cost": float(costs),
        "turnover_notional": float(turnover),
    }


def _summarize(values: list[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    return {
        "mean": float(arr.mean()),
        "p05": float(np.quantile(arr, 0.05)),
        "p50": float(np.quantile(arr, 0.50)),
        "p95": float(np.quantile(arr, 0.95)),
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    plan = _load_plan(_resolve(args.execution_plan))
    current_shares = {str(k): int(v) for k, v in plan["current_holdings"].items()}
    start_prices = {str(k): float(v) for k, v in plan["current_prices"].items()}
    full_target = _target_from_plan(plan, "full")
    staged_target = _target_from_plan(plan, "staged")
    tickers = sorted(set(current_shares) | set(start_prices) | set(full_target) | set(staged_target))
    scenario_rows: list[dict[str, Any]] = []
    for i, (name, params) in enumerate(SCENARIOS.items()):
        price_paths = _simulate_prices(
            tickers=tickers,
            start_prices=start_prices,
            horizon_days=int(args.horizon_days),
            paths=int(args.paths),
            annual_mu=float(params["annual_mu"]),
            annual_vol_scale=float(params["annual_vol_scale"]),
            seed=int(args.seed) + i,
        )
        full_rows: list[dict[str, float]] = []
        staged_rows: list[dict[str, float]] = []
        for path in price_paths:
            full_rows.append(
                _run_policy(
                    price_path=path,
                    tickers=tickers,
                    current_shares=current_shares,
                    current_cash=float(plan["current_cash_input"]),
                    staged_target=staged_target,
                    full_target=full_target,
                    policy="full_day0",
                    defer_days=int(args.defer_days),
                    commission_rate=float(args.commission_rate),
                    slippage_rate=float(args.slippage_rate),
                    equity_etf_sell_tax=float(args.equity_etf_sell_tax),
                    impact_scale=float(args.impact_scale),
                )
            )
            staged_rows.append(
                _run_policy(
                    price_path=path,
                    tickers=tickers,
                    current_shares=current_shares,
                    current_cash=float(plan["current_cash_input"]),
                    staged_target=staged_target,
                    full_target=full_target,
                    policy="staged_then_full",
                    defer_days=int(args.defer_days),
                    commission_rate=float(args.commission_rate),
                    slippage_rate=float(args.slippage_rate),
                    equity_etf_sell_tax=float(args.equity_etf_sell_tax),
                    impact_scale=float(args.impact_scale),
                )
            )
        final_delta = [staged["final_value"] - full["final_value"] for staged, full in zip(staged_rows, full_rows)]
        cost_delta = [staged["transaction_cost"] - full["transaction_cost"] for staged, full in zip(staged_rows, full_rows)]
        turnover_delta = [staged["turnover_notional"] - full["turnover_notional"] for staged, full in zip(staged_rows, full_rows)]
        scenario_rows.append(
            {
                "scenario": name,
                "params": params,
                "staged_minus_full": {
                    "final_value": _summarize(final_delta),
                    "transaction_cost": _summarize(cost_delta),
                    "turnover_notional": _summarize(turnover_delta),
                    "staged_beats_full_final_rate": float(np.mean(np.asarray(final_delta) >= 0.0)),
                    "staged_saves_cost_rate": float(np.mean(np.asarray(cost_delta) <= 0.0)),
                },
            }
        )
    return {
        "schema_version": 1,
        "report_type": "2307_07694_gbm_market_impact_staging_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_gbm_stress_no_live_weight_change",
        "source_paper": "arXiv:2307.07694v3 Evaluation of Deep Reinforcement Learning Algorithms for Portfolio Optimisation",
        "execution_plan": str(_resolve(args.execution_plan)),
        "settings": {
            "paths": int(args.paths),
            "horizon_days": int(args.horizon_days),
            "defer_days": int(args.defer_days),
            "impact_scale": float(args.impact_scale),
            "commission_rate": float(args.commission_rate),
            "slippage_rate": float(args.slippage_rate),
            "equity_etf_sell_tax": float(args.equity_etf_sell_tax),
            "seed": int(args.seed),
        },
        "plan_snapshot": {
            "actual_data_date": plan.get("actual_data_date"),
            "execution_regime": plan.get("execution_regime"),
            "current_holdings": current_shares,
            "full_target_shares": full_target,
            "staged_target_shares": staged_target,
        },
        "scenarios": scenario_rows,
        "decision": {
            "recommended_use": "shadow_stress_test_only",
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "keep_golden1_0531_unchanged": True,
            "summary": "GBM is useful here as a repeatable execution stress test, not as an alpha or weight source.",
        },
    }


def _write_md(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2307.07694 GBM Market-Impact Staging Shadow",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Policy: `{report['policy']}`",
        f"- Execution plan: `{report['execution_plan']}`",
        f"- Settings: `{report['settings']}`",
        "",
        "## Scenario Summary",
        "",
        "| Scenario | Mean Final Delta | P05 Final Delta | Cost Delta Mean | Cost Save Rate | Staged Win Rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["scenarios"]:
        delta = row["staged_minus_full"]
        lines.append(
            f"| {row['scenario']} | {delta['final_value']['mean']:.2f} | {delta['final_value']['p05']:.2f} | "
            f"{delta['transaction_cost']['mean']:.2f} | {delta['staged_saves_cost_rate']:.3f} | "
            f"{delta['staged_beats_full_final_rate']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Recommended use: `{report['decision']['recommended_use']}`",
            f"- Promote to live: `{report['decision']['promote_to_live']}`",
            f"- Target weight change allowed: `{report['decision']['target_weight_change_allowed']}`",
            f"- Auto rebalance allowed: `{report['decision']['auto_rebalance_allowed']}`",
            "- No latest strategy, live signal, execution plan, or order file was changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-plan", default=str(DEFAULT_PLAN))
    parser.add_argument("--paths", type=int, default=2000)
    parser.add_argument("--horizon-days", type=int, default=20)
    parser.add_argument("--defer-days", type=int, default=5)
    parser.add_argument("--impact-scale", type=float, default=3.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=230707694)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = evaluate(args)
    output_json = _resolve(args.output_json)
    output_md = _resolve(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(report, output_md)
    print(json.dumps({"output_json": str(output_json), "output_md": str(output_md)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
