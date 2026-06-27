#!/usr/bin/env python3
"""RiskLabAI governance and execution-cost diagnostics for GroupA+.

Trial universe (v2):
  - Legacy universe : MA60–MA90 × {cash30, cash40, bond20}  (21 variants)
  - Tight-entry universe: A21.4 / A21.11 / A21.12            ( 3 variants)
  Total: 24 trials for PBO / DSR calculation.

Base  = A21.11 (current active)   — a2111_tight_entry_bond30c30
Candidate = A21.12 (new research) — a2112_ma80_tight_entry_bond30c30_lrx
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.risklab import load_risklab_components
from group_a_plus.runners.a213 import _run_recovery_strategy
from group_a_plus.runners.a214 import run_a214
from group_a_plus.runners.a2111 import run_a2111
from group_a_plus.runners.a2112 import run_a2112
from tw_output_standard import OutputStandardizer, write_standard_output


SEARCH_MA_WINDOWS = tuple(range(60, 91, 5))
SEARCH_BASKETS = ("cash30", "cash40", "bond20")
# Updated base/candidate: compare A21.11 (active) vs A21.12 (new candidate)
BASE_VARIANT = "a2111_tight_entry_bond30c30"
CANDIDATE_VARIANT = "a2112_ma80_tight_entry_bond30c30_lrx"


def _daily_sharpe(returns: pd.Series) -> float:
    clean = returns.dropna()
    std = float(clean.std(ddof=1))
    return float(clean.mean() / std) if std > 0 else 0.0


def _strategy_return_matrix(db: Path) -> tuple[pd.DataFrame, list[dict[str, Any]], pd.Series]:
    """Build trial universe: legacy MA/basket grid + tight-entry candidates."""
    returns: dict[str, pd.Series] = {}
    rows = []
    active_curve = pd.Series(dtype=float)

    # --- Legacy universe: MA60–90 × {cash30, cash40, bond20} ---
    for ma_window in SEARCH_MA_WINDOWS:
        for basket_name in SEARCH_BASKETS:
            variant = f"ma{ma_window}_{basket_name}"
            report, frame = _run_recovery_strategy(
                start="2020-01-02",
                end="2026-06-18",
                initial_value=1_000_000.0,
                db=db,
                basket_name=basket_name,
                ma_window=ma_window,
                strategy_id=variant,
                experiment="group_a_plus_risklab_trial_universe",
                status="research",
            )
            curve = frame["portfolio_value"].astype(float)
            returns[variant] = curve.pct_change().fillna(0.0)
            daily_sr = _daily_sharpe(returns[variant])
            rows.append(
                {
                    "variant": variant,
                    "ma_window": ma_window,
                    "basket_name": basket_name,
                    "universe": "legacy",
                    "daily_sharpe": daily_sr,
                    "annualized_sharpe": daily_sr * np.sqrt(252.0),
                    **report["metrics"],
                }
            )

    # --- Tight-entry universe: A21.4, A21.11, A21.12 ---
    tight_entry_runners = [
        ("a214_bond30c30_mw60",                run_a214,   60),
        ("a2111_tight_entry_bond30c30",         run_a2111, 100),
        ("a2112_ma80_tight_entry_bond30c30_lrx", run_a2112,  80),
    ]
    for variant, runner_fn, ma_window in tight_entry_runners:
        report, frame = runner_fn(
            start="2020-01-02",
            end="2026-06-18",
            initial_value=1_000_000.0,
            db=db,
        )
        curve = frame["portfolio_value"].astype(float)
        returns[variant] = curve.pct_change().fillna(0.0)
        daily_sr = _daily_sharpe(returns[variant])
        rows.append(
            {
                "variant": variant,
                "ma_window": ma_window,
                "basket_name": "bond30_cash30",
                "universe": "tight_entry",
                "daily_sharpe": daily_sr,
                "annualized_sharpe": daily_sr * np.sqrt(252.0),
                **report["metrics"],
            }
        )
        if variant == BASE_VARIANT:
            active_curve = curve

    return pd.DataFrame(returns).dropna(), rows, active_curve


def _overfit_diagnostics(components: dict[str, Any], matrix: pd.DataFrame) -> dict[str, Any]:
    psr_module = components["psr"]
    pbo_module = components["pbo"]
    overfit_module = components["overfit"]
    sharpe_by_variant = matrix.apply(_daily_sharpe)
    candidate_returns = matrix[CANDIDATE_VARIANT]
    base_sr = float(sharpe_by_variant[BASE_VARIANT])
    candidate_sr = float(sharpe_by_variant[CANDIDATE_VARIANT])
    expected_max_sr = float(
        overfit_module.expected_max_sharpe_ratio(
            len(sharpe_by_variant),
            float(sharpe_by_variant.mean()),
            float(sharpe_by_variant.std(ddof=0)),
        )
    )
    skewness = float(scipy_stats.skew(candidate_returns, bias=False))
    kurtosis = float(scipy_stats.kurtosis(candidate_returns, fisher=False, bias=False))
    psr_vs_a213 = float(
        psr_module.probabilistic_sharpe_ratio(
            candidate_sr, base_sr, len(candidate_returns), skewness, kurtosis
        )
    )
    deflated_sharpe_probability = float(
        psr_module.probabilistic_sharpe_ratio(
            candidate_sr,
            expected_max_sr,
            len(candidate_returns),
            skewness,
            kurtosis,
        )
    )
    pbo, logits = pbo_module.probability_of_backtest_overfitting(
        matrix.to_numpy(), n_partitions=8, n_jobs=1
    )
    return {
        "trial_count": len(sharpe_by_variant),
        "observation_count": len(matrix),
        "base_variant": BASE_VARIANT,
        "candidate_variant": CANDIDATE_VARIANT,
        "base_daily_sharpe": base_sr,
        "candidate_daily_sharpe": candidate_sr,
        "base_annualized_sharpe": base_sr * np.sqrt(252.0),
        "candidate_annualized_sharpe": candidate_sr * np.sqrt(252.0),
        "expected_max_daily_sharpe_after_trials": expected_max_sr,
        "psr_candidate_above_base": psr_vs_a213,
        "deflated_sharpe_probability": deflated_sharpe_probability,
        "probability_of_backtest_overfitting": float(pbo),
        "pbo_logit_median": float(np.median(logits)),
        "candidate_skewness": skewness,
        "candidate_kurtosis": kurtosis,
        "scope_note": (
            "PBO/DSR cover 24-trial universe (21 legacy MA/basket + 3 tight-entry: A21.4/A21.11/A21.12). "
            "Base=A21.11 (current active), Candidate=A21.12 (MA80+lrx). "
            "Excludes historical GroupA+ experiments predating this universe definition."
        ),
    }


def _risk_concentration(components: dict[str, Any], curve: pd.Series) -> dict[str, Any]:
    statistics = components["statistics"]
    returns = curve.pct_change().dropna()
    positive = statistics.calculate_hhi(returns[returns >= 0])
    negative = statistics.calculate_hhi(returns[returns < 0])
    monthly_counts = returns.groupby(pd.Grouper(freq="ME")).count()
    monthly = statistics.calculate_hhi(monthly_counts)
    monthly_returns = (1.0 + returns).groupby(pd.Grouper(freq="ME")).prod() - 1.0
    monthly_return_hhi = statistics.calculate_hhi(monthly_returns)
    drawdowns, underwater = statistics.compute_drawdowns_time_under_water(curve, dollars=False)
    return {
        "hhi_positive_returns": float(positive),
        "hhi_negative_returns": float(negative),
        "hhi_monthly_observation_concentration": float(monthly),
        "hhi_monthly_return_concentration": float(monthly_return_hhi),
        "drawdown_episode_count": int(len(drawdowns)),
        "worst_episode_drawdown": float(drawdowns.max()) if len(drawdowns) else 0.0,
        "longest_time_under_water_years": float(underwater.max()) if len(underwater) else 0.0,
        "median_time_under_water_years": float(underwater.median()) if len(underwater) else 0.0,
    }


def _load_ohlc(db: Path) -> dict[str, pd.DataFrame]:
    con = duckdb.connect(str(db), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, ticker, high, low
            FROM ohlcv
            WHERE ticker IN (?, ?, ?, ?) AND dt BETWEEN '2025-01-01' AND '2026-06-18'
            ORDER BY dt, ticker
            """,
            list(TICKERS),
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return {
        ticker: group.set_index("dt")[["high", "low"]].astype(float)
        for ticker, group in rows.groupby("ticker")
    }


def _microstructure_costs(
    components: dict[str, Any], db: Path, execution_plan: Path
) -> dict[str, Any]:
    corwin = components["corwin"]
    bekker = components["bekker"]
    estimates = {}
    for ticker, frame in _load_ohlc(db).items():
        spread = corwin.corwin_schultz_estimator(frame["high"], frame["low"], window_span=20)
        volatility = bekker.bekker_parkinson_volatility_estimates(
            frame["high"], frame["low"], window_span=20
        )
        recent_spread = spread.dropna().tail(20)
        recent_volatility = volatility.dropna().tail(20)
        median_spread = float(recent_spread.median()) if len(recent_spread) else 0.0
        percentile_75_spread = float(recent_spread.quantile(0.75)) if len(recent_spread) else 0.0
        latest_spread = float(recent_spread.iloc[-1]) if len(recent_spread) else 0.0
        estimates[ticker] = {
            "latest_spread": latest_spread,
            "median_spread_20d": median_spread,
            "percentile_75_spread_20d": percentile_75_spread,
            "zero_estimate_ratio_20d": float((recent_spread == 0.0).mean()) if len(recent_spread) else None,
            "latest_bekker_parkinson_volatility": (
                float(recent_volatility.iloc[-1]) if len(recent_volatility) else None
            ),
            "median_based_one_way_slippage": min(max(0.0005, 0.5 * median_spread), 0.01),
            "p75_based_one_way_slippage": min(max(0.0005, 0.5 * percentile_75_spread), 0.01),
            "latest_based_one_way_slippage": min(max(0.0005, 0.5 * latest_spread), 0.01),
        }

    payload = json.loads(execution_plan.read_text(encoding="utf-8"))
    plan = payload.get("data", payload)
    trades = plan.get("trades", [])
    base_slippage = float(plan.get("execution_controls", {}).get("base_slippage_rate", 0.0005))
    base_cost = sum(float(trade["notional"]) * base_slippage for trade in trades)
    def scenario_cost(field: str) -> float:
        return sum(
            float(trade["notional"])
            * float(estimates.get(trade["ticker"], {}).get(field, base_slippage))
            for trade in trades
        )

    median_cost = scenario_cost("median_based_one_way_slippage")
    p75_cost = scenario_cost("p75_based_one_way_slippage")
    latest_cost = scenario_cost("latest_based_one_way_slippage")
    return {
        "estimates": estimates,
        "trade_count": len(trades),
        "base_slippage_cost": base_cost,
        "median_based_slippage_cost": median_cost,
        "p75_based_slippage_cost": p75_cost,
        "latest_based_slippage_cost": latest_cost,
        "p75_incremental_slippage_cost": p75_cost - base_cost,
        "latest_incremental_slippage_cost": latest_cost - base_cost,
        "method": "one-way slippage=max(0.05%, half of Corwin-Schultz spread statistic), capped at 1%",
        "decision_note": "High zero-estimate ratios make median estimates uninformative; retain fixed production slippage and use p75/latest only as research stress scenarios.",
        "research_only": True,
    }


def evaluate(risklab_root: Path, db: Path, execution_plan: Path) -> tuple[dict[str, Any], pd.DataFrame, list[dict[str, Any]]]:
    components = load_risklab_components(risklab_root)
    matrix, trial_rows, active_curve = _strategy_return_matrix(db)
    report = {
        "experiment": "group_a_plus_risklab_diagnostics_v2",
        "trial_universe": "24 variants: 21 legacy (MA60-90 × cash30/cash40/bond20) + 3 tight-entry (A21.4/A21.11/A21.12)",
        "base_variant": BASE_VARIANT,
        "candidate_variant": CANDIDATE_VARIANT,
        "risklab_root": str(risklab_root.resolve()),
        "risklab_license": components["license"],
        "overfit_diagnostics": _overfit_diagnostics(components, matrix),
        "a2111_risk_concentration": _risk_concentration(components, active_curve),
        "microstructure_costs": _microstructure_costs(components, db, execution_plan),
        "decision_policy": "Research diagnostics only; no active strategy or production cost assumptions are changed.",
    }
    return report, matrix, trial_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--risklab-root",
        default="/mnt/c/Users/isaac/Downloads/RiskLabAI.py-main/RiskLabAI.py-main",
    )
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument(
        "--execution-plan", default="results/group_a_plus_execution_plan_controls_20260622.json"
    )
    parser.add_argument("--output-prefix", default="results/group_a_plus_risklab_20260622")
    args = parser.parse_args()
    prefix = Path(args.output_prefix)
    std = OutputStandardizer("evaluate_group_a_plus_risklab.py")
    try:
        report, matrix, trial_rows = evaluate(
            Path(args.risklab_root), Path(args.db), Path(args.execution_plan)
        )
        matrix.to_csv(prefix.parent / f"{prefix.name}_returns.csv", encoding="utf-8-sig")
        pd.DataFrame(trial_rows).to_csv(
            prefix.parent / f"{prefix.name}_trials.csv", index=False, encoding="utf-8-sig"
        )
        payload = std.success(report)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, str(prefix.with_suffix(".json")))


if __name__ == "__main__":
    main()
