#!/usr/bin/env python3
"""Walk-forward evaluation for the 4-ETF PPO portfolio allocator."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from stable_baselines3 import PPO


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_data_loader import download_all_stocks
from train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026 import (
    ACTION_LABELS,
    BACKTEST_END,
    ACTIVE_MARKET_DERIVED_FEATURE_COLUMNS,
    BENCHMARK_SHORTFALL_PENALTY_CAP,
    BENCHMARK_SHORTFALL_PENALTY_WEIGHT,
    BENCHMARK_SHORTFALL_STRESS_SCALE,
    BENCHMARK_WEIGHT,
    DCA_DEFAULT_AMOUNTS,
    DOWNLOAD_END,
    FEATURE_COLUMNS,
    SHARED_MARKET_FEATURE_COLUMNS,
    STRESS_BUDGET_CAUTION_0050_CAP,
    STRESS_BUDGET_CAUTION_INVESTED_CAP,
    STRESS_BUDGET_DEEP_RISK_OFF_0050_CAP,
    STRESS_BUDGET_DEEP_RISK_OFF_INVESTED_CAP,
    STRESS_BUDGET_RISK_OFF_0050_CAP,
    STRESS_BUDGET_RISK_OFF_INVESTED_CAP,
    TICKERS,
    ETFPortfolioEnv,
    _align_panel,
    _buy_and_hold,
    get_active_derived_features,
    _run_model,
    build_env_kwargs,
)


def _slice_panel(panel: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    dates = pd.to_datetime(panel["date"])
    mask = (dates >= start) & (dates <= end)
    return panel.loc[mask].copy().reset_index(drop=True)


def _generate_windows(
    panel: pd.DataFrame,
    *,
    start: str,
    end: str,
    train_months: int,
    test_months: int,
    step_months: int,
    max_windows: int = 0,
) -> list[dict]:
    windows = []
    cursor = pd.Timestamp(start)
    hard_end = pd.Timestamp(end)

    while True:
        train_start = cursor
        train_end = train_start + pd.DateOffset(months=train_months) - pd.Timedelta(days=1)
        test_start = train_end + pd.Timedelta(days=1)
        test_end = test_start + pd.DateOffset(months=test_months) - pd.Timedelta(days=1)
        if test_end > hard_end:
            break

        train_panel = _slice_panel(panel, train_start, train_end)
        test_panel = _slice_panel(panel, test_start, test_end)
        if len(train_panel) >= 100 and len(test_panel) >= 20:
            windows.append(
                {
                    "train_start": str(train_start.date()),
                    "train_end": str(train_end.date()),
                    "test_start": str(test_start.date()),
                    "test_end": str(test_end.date()),
                }
            )

        if max_windows and len(windows) >= max_windows:
            break
        cursor = cursor + pd.DateOffset(months=step_months)
        if cursor > hard_end:
            break

    return windows


def _train_model(train_panel: pd.DataFrame, env_kwargs: dict, timesteps: int, seed: int, verbose: int) -> PPO:
    train_env = ETFPortfolioEnv(train_panel, **env_kwargs)
    model = PPO(
        "MlpPolicy",
        train_env,
        learning_rate=3e-4,
        n_steps=1024,
        batch_size=128,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.01,
        seed=seed,
        verbose=verbose,
    )
    model.learn(total_timesteps=timesteps)
    return model


def _window_row(
    *,
    window_id: int,
    train_panel: pd.DataFrame,
    test_panel: pd.DataFrame,
    result: dict,
    equal_bh: dict,
    bh_0050: dict,
    use_dca_score: bool,
) -> dict:
    score_return = (
        float(result["investment_summary"]["simple_return_on_total_invested"])
        if use_dca_score
        else float(result["rl_metrics"]["total_return"])
    )
    return {
        "window_id": window_id,
        "actual_train_start": str(pd.to_datetime(train_panel["date"]).min().date()),
        "actual_train_end": str(pd.to_datetime(train_panel["date"]).max().date()),
        "actual_test_start": str(pd.to_datetime(test_panel["date"]).min().date()),
        "actual_test_end": str(pd.to_datetime(test_panel["date"]).max().date()),
        "train_rows": int(len(train_panel)),
        "test_rows": int(len(test_panel)),
        "score_return": score_return,
        "final_value": float(result["final_value"]),
        "total_return": float(result["rl_metrics"]["total_return"]),
        "annual_return": float(result["rl_metrics"]["annual_return"]),
        "sharpe": float(result["rl_metrics"]["sharpe"]),
        "max_drawdown": float(result["rl_metrics"]["max_drawdown"]),
        "num_trades": int(result["num_trades"]),
        "range_harvest_count": int(result["range_harvest_count"]),
        "pva_sigmoid_count": int(result["pva_sigmoid_count"]),
        "market_stress_count": int(result.get("market_stress_count", 0)),
        "stress_budget_count": int(result.get("stress_budget_count", 0)),
        "fees_paid_estimate": float(result["fees_paid_estimate"]),
        "excess_return_vs_equal_bh": float(
            result["rl_metrics"]["total_return"] - equal_bh["metrics"]["total_return"]
        ),
        "excess_return_vs_0050_bh": float(
            result["rl_metrics"]["total_return"] - bh_0050["metrics"]["total_return"]
        ),
        "beat_equal_bh": bool(result["rl_metrics"]["total_return"] > equal_bh["metrics"]["total_return"]),
        "beat_0050_bh": bool(result["rl_metrics"]["total_return"] > bh_0050["metrics"]["total_return"]),
    }


def _summarize(rows: list[dict], *, use_dca_score: bool) -> dict:
    if not rows:
        return {}

    score_label = "return_on_invested" if use_dca_score else "total_return"
    score_values = [float(row["score_return"]) for row in rows]
    sharpe_values = [float(row["sharpe"]) for row in rows]
    drawdowns = [float(row["max_drawdown"]) for row in rows]
    trade_counts = [int(row["num_trades"]) for row in rows]
    beat_equal = [bool(row["beat_equal_bh"]) for row in rows]
    beat_0050 = [bool(row["beat_0050_bh"]) for row in rows]

    return {
        "windows": len(rows),
        "score_metric": score_label,
        "mean_score_return": float(np.mean(score_values)),
        "median_score_return": float(np.median(score_values)),
        "worst_score_return": float(np.min(score_values)),
        "best_score_return": float(np.max(score_values)),
        "mean_sharpe": float(np.mean(sharpe_values)),
        "mean_max_drawdown": float(np.mean(drawdowns)),
        "worst_max_drawdown": float(np.min(drawdowns)),
        "mean_trades": float(np.mean(trade_counts)),
        "beat_rate_equal_bh": float(np.mean(beat_equal)),
        "beat_rate_0050_bh": float(np.mean(beat_0050)),
        "mean_market_stress_count": float(np.mean([row["market_stress_count"] for row in rows])),
        "mean_stress_budget_count": float(np.mean([row["stress_budget_count"] for row in rows])),
        "mean_pva_sigmoid_count": float(np.mean([row["pva_sigmoid_count"] for row in rows])),
        "mean_range_harvest_count": float(np.mean([row["range_harvest_count"] for row in rows])),
    }


def _write_outputs(rows: list[dict], payload: dict, *, seed: int) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_id = f"seed{seed}_{timestamp}"
    out_json = PROJECT_ROOT / "results" / f"walk_forward_portfolio_4etf_{run_id}.json"
    out_csv = PROJECT_ROOT / "results" / f"walk_forward_portfolio_4etf_{run_id}.csv"
    out_json.parent.mkdir(parents=True, exist_ok=True)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return out_json, out_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward validation for the 4-ETF PPO strategy.")
    parser.add_argument("--train-start", default="2009-01-01")
    parser.add_argument("--end", default=BACKTEST_END)
    parser.add_argument("--download-end", default=DOWNLOAD_END)
    parser.add_argument("--window-train-months", type=int, default=60)
    parser.add_argument("--window-test-months", type=int, default=6)
    parser.add_argument("--window-step-months", type=int, default=6)
    parser.add_argument("--max-windows", type=int, default=0)
    parser.add_argument("--timesteps", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--turnover-penalty", type=float, default=0.08)
    parser.add_argument("--benchmark-weight", type=float, default=BENCHMARK_WEIGHT)
    parser.add_argument(
        "--benchmark-shortfall-penalty-weight",
        type=float,
        default=BENCHMARK_SHORTFALL_PENALTY_WEIGHT,
    )
    parser.add_argument(
        "--benchmark-shortfall-penalty-cap",
        type=float,
        default=BENCHMARK_SHORTFALL_PENALTY_CAP,
    )
    parser.add_argument(
        "--benchmark-shortfall-stress-scale",
        type=float,
        default=BENCHMARK_SHORTFALL_STRESS_SCALE,
    )
    parser.add_argument("--stress-budget-caution-invested-cap", type=float, default=STRESS_BUDGET_CAUTION_INVESTED_CAP)
    parser.add_argument("--stress-budget-caution-0050-cap", type=float, default=STRESS_BUDGET_CAUTION_0050_CAP)
    parser.add_argument("--stress-budget-risk-off-invested-cap", type=float, default=STRESS_BUDGET_RISK_OFF_INVESTED_CAP)
    parser.add_argument("--stress-budget-risk-off-0050-cap", type=float, default=STRESS_BUDGET_RISK_OFF_0050_CAP)
    parser.add_argument(
        "--stress-budget-deep-risk-off-invested-cap",
        type=float,
        default=STRESS_BUDGET_DEEP_RISK_OFF_INVESTED_CAP,
    )
    parser.add_argument(
        "--stress-budget-deep-risk-off-0050-cap",
        type=float,
        default=STRESS_BUDGET_DEEP_RISK_OFF_0050_CAP,
    )
    parser.add_argument("--min-rebalance-days", type=int, default=60)
    parser.add_argument(
        "--stress-rebalance-cooldown-days",
        type=int,
        default=0,
        help="cooldown used only for market-stress cash-defense overrides; 0 means no extra delay",
    )
    parser.add_argument(
        "--stress-confirm-days",
        type=int,
        default=3,
        help="number of consecutive stress days required before cash-defense can override PPO",
    )
    parser.add_argument("--min-weight", type=float, default=0.05)
    parser.add_argument("--max-weight", type=float, default=0.70)
    parser.add_argument("--use-rsi-features", action="store_true")
    parser.add_argument(
        "--disable-market-regime-features",
        action="store_true",
        help="fall back to the legacy feature set without shared market-regime signals",
    )
    parser.add_argument("--enable-dca", action="store_true")
    parser.add_argument("--dca-day", type=int, default=26)
    parser.add_argument("--dca-0050", type=float, default=DCA_DEFAULT_AMOUNTS["0050.TW"])
    parser.add_argument("--dca-0056", type=float, default=DCA_DEFAULT_AMOUNTS["0056.TW"])
    parser.add_argument("--dca-00713", type=float, default=DCA_DEFAULT_AMOUNTS["00713.TW"])
    parser.add_argument("--dca-00878", type=float, default=DCA_DEFAULT_AMOUNTS["00878.TW"])
    parser.add_argument("--enable-range-harvest", action="store_true")
    parser.add_argument("--range-drift-threshold", type=float, default=0.05)
    parser.add_argument("--enable-pva-sigmoid", action="store_true")
    parser.add_argument("--pva-weight", type=float, default=0.20)
    parser.add_argument("--pva-drift-threshold", type=float, default=0.08)
    parser.add_argument("--ppo-verbose", type=int, default=0)
    args = parser.parse_args()
    use_market_regime_features = not args.disable_market_regime_features

    print("=" * 72)
    print("Walk-forward 4 ETF PPO validation")
    print(f"Range: {args.train_start} ~ {args.end}")
    print(
        f"Window: train={args.window_train_months}m "
        f"test={args.window_test_months}m step={args.window_step_months}m"
    )
    print(f"Timesteps: {args.timesteps:,}, Seed: {args.seed}")
    print(f"Actions: {len(ACTION_LABELS)} discrete actions")
    print("=" * 72)

    stock_data = download_all_stocks(TICKERS, args.train_start, args.download_end)
    missing = [ticker for ticker in TICKERS if ticker not in stock_data]
    if missing:
        raise RuntimeError(f"Unable to load data for {missing}")

    full_panel = _align_panel(stock_data, args.train_start, args.end)
    windows = _generate_windows(
        full_panel,
        start=args.train_start,
        end=args.end,
        train_months=args.window_train_months,
        test_months=args.window_test_months,
        step_months=args.window_step_months,
        max_windows=args.max_windows,
    )
    if not windows:
        raise RuntimeError("No valid walk-forward windows were generated")

    train_env_kwargs = build_env_kwargs(
        turnover_penalty=args.turnover_penalty,
        benchmark_weight=args.benchmark_weight,
        benchmark_shortfall_penalty_weight=args.benchmark_shortfall_penalty_weight,
        benchmark_shortfall_penalty_cap=args.benchmark_shortfall_penalty_cap,
        benchmark_shortfall_stress_scale=args.benchmark_shortfall_stress_scale,
        stress_budget_caution_invested_cap=args.stress_budget_caution_invested_cap,
        stress_budget_caution_0050_cap=args.stress_budget_caution_0050_cap,
        stress_budget_risk_off_invested_cap=args.stress_budget_risk_off_invested_cap,
        stress_budget_risk_off_0050_cap=args.stress_budget_risk_off_0050_cap,
        stress_budget_deep_risk_off_invested_cap=args.stress_budget_deep_risk_off_invested_cap,
        stress_budget_deep_risk_off_0050_cap=args.stress_budget_deep_risk_off_0050_cap,
        min_rebalance_days=args.min_rebalance_days,
        stress_rebalance_cooldown_days=args.stress_rebalance_cooldown_days,
        stress_confirm_days=args.stress_confirm_days,
        min_weight=args.min_weight,
        max_weight=args.max_weight,
        use_rsi_features=args.use_rsi_features,
        use_market_regime_features=use_market_regime_features,
        enable_range_harvest=args.enable_range_harvest,
        range_drift_threshold=args.range_drift_threshold,
        enable_pva_sigmoid=args.enable_pva_sigmoid,
        pva_weight=args.pva_weight,
        pva_drift_threshold=args.pva_drift_threshold,
    )
    dca_amounts = {
        "0050.TW": args.dca_0050,
        "0056.TW": args.dca_0056,
        "00713.TW": args.dca_00713,
        "00878.TW": args.dca_00878,
    }
    eval_env_kwargs = build_env_kwargs(
        turnover_penalty=args.turnover_penalty,
        benchmark_weight=args.benchmark_weight,
        benchmark_shortfall_penalty_weight=args.benchmark_shortfall_penalty_weight,
        benchmark_shortfall_penalty_cap=args.benchmark_shortfall_penalty_cap,
        benchmark_shortfall_stress_scale=args.benchmark_shortfall_stress_scale,
        stress_budget_caution_invested_cap=args.stress_budget_caution_invested_cap,
        stress_budget_caution_0050_cap=args.stress_budget_caution_0050_cap,
        stress_budget_risk_off_invested_cap=args.stress_budget_risk_off_invested_cap,
        stress_budget_risk_off_0050_cap=args.stress_budget_risk_off_0050_cap,
        stress_budget_deep_risk_off_invested_cap=args.stress_budget_deep_risk_off_invested_cap,
        stress_budget_deep_risk_off_0050_cap=args.stress_budget_deep_risk_off_0050_cap,
        min_rebalance_days=args.min_rebalance_days,
        stress_rebalance_cooldown_days=args.stress_rebalance_cooldown_days,
        stress_confirm_days=args.stress_confirm_days,
        min_weight=args.min_weight,
        max_weight=args.max_weight,
        use_rsi_features=args.use_rsi_features,
        use_market_regime_features=use_market_regime_features,
        enable_range_harvest=args.enable_range_harvest,
        range_drift_threshold=args.range_drift_threshold,
        enable_pva_sigmoid=args.enable_pva_sigmoid,
        pva_weight=args.pva_weight,
        pva_drift_threshold=args.pva_drift_threshold,
        dca_monthly_amounts=dca_amounts if args.enable_dca else None,
        dca_day=args.dca_day,
    )

    rows = []
    for idx, window in enumerate(windows, start=1):
        train_panel = _slice_panel(
            full_panel,
            pd.Timestamp(window["train_start"]),
            pd.Timestamp(window["train_end"]),
        )
        test_panel = _slice_panel(
            full_panel,
            pd.Timestamp(window["test_start"]),
            pd.Timestamp(window["test_end"]),
        )
        print(
            f"[{idx}/{len(windows)}] "
            f"train={window['train_start']}~{window['train_end']} "
            f"test={window['test_start']}~{window['test_end']} "
            f"rows={len(train_panel)}/{len(test_panel)}"
        )
        model = _train_model(
            train_panel,
            env_kwargs=train_env_kwargs,
            timesteps=args.timesteps,
            seed=args.seed,
            verbose=args.ppo_verbose,
        )
        result = _run_model(model, test_panel, eval_env_kwargs)
        equal_bh = _buy_and_hold(test_panel, np.array([0.25, 0.25, 0.25, 0.25], dtype=float))
        bh_0050 = _buy_and_hold(test_panel, np.array([1.0, 0.0, 0.0, 0.0], dtype=float))
        row = {
            **window,
            **_window_row(
                window_id=idx,
                train_panel=train_panel,
                test_panel=test_panel,
                result=result,
                equal_bh=equal_bh,
                bh_0050=bh_0050,
                use_dca_score=args.enable_dca,
            ),
        }
        rows.append(row)
        print(
            f"  score={row['score_return']:.2%} "
            f"sharpe={row['sharpe']:.3f} "
            f"mdd={row['max_drawdown']:.2%} "
            f"trades={row['num_trades']} "
            f"stress={row['market_stress_count']} "
            f"budget={row['stress_budget_count']}"
        )

    summary = _summarize(rows, use_dca_score=args.enable_dca)
    payload = {
        "config": {
            "tickers": TICKERS,
            "train_start": args.train_start,
            "end": args.end,
            "download_end": args.download_end,
            "window_train_months": args.window_train_months,
            "window_test_months": args.window_test_months,
            "window_step_months": args.window_step_months,
            "max_windows": args.max_windows,
            "timesteps": args.timesteps,
            "seed": args.seed,
            "turnover_penalty": args.turnover_penalty,
            "benchmark_weight": args.benchmark_weight,
            "benchmark_shortfall_penalty_weight": args.benchmark_shortfall_penalty_weight,
            "benchmark_shortfall_penalty_cap": args.benchmark_shortfall_penalty_cap,
            "benchmark_shortfall_stress_scale": args.benchmark_shortfall_stress_scale,
            "stress_budget_caution_invested_cap": args.stress_budget_caution_invested_cap,
            "stress_budget_caution_0050_cap": args.stress_budget_caution_0050_cap,
            "stress_budget_risk_off_invested_cap": args.stress_budget_risk_off_invested_cap,
            "stress_budget_risk_off_0050_cap": args.stress_budget_risk_off_0050_cap,
            "stress_budget_deep_risk_off_invested_cap": args.stress_budget_deep_risk_off_invested_cap,
            "stress_budget_deep_risk_off_0050_cap": args.stress_budget_deep_risk_off_0050_cap,
            "min_rebalance_days": args.min_rebalance_days,
            "stress_rebalance_cooldown_days": args.stress_rebalance_cooldown_days,
            "stress_confirm_days": args.stress_confirm_days,
            "min_weight": args.min_weight,
            "max_weight": args.max_weight,
            "use_rsi_features": bool(args.use_rsi_features),
            "use_market_regime_features": bool(use_market_regime_features),
            "enable_dca": bool(args.enable_dca),
            "enable_range_harvest": bool(args.enable_range_harvest),
            "enable_pva_sigmoid": bool(args.enable_pva_sigmoid),
            "pva_weight": args.pva_weight,
            "pva_drift_threshold": args.pva_drift_threshold,
            "actions": ACTION_LABELS,
        },
        "feature_config": {
            "base_features_per_ticker": FEATURE_COLUMNS,
            "active_derived_portfolio_features": get_active_derived_features(
                args.use_rsi_features,
                use_market_regime_features,
            ),
            "active_market_regime_features": (
                ACTIVE_MARKET_DERIVED_FEATURE_COLUMNS if use_market_regime_features else []
            ),
            "shared_market_inputs": SHARED_MARKET_FEATURE_COLUMNS,
            "rsi_features_enabled": bool(args.use_rsi_features),
            "market_regime_features_enabled": bool(use_market_regime_features),
        },
        "stress_guardrail_config": {
            "enabled": True,
            "stress_rebalance_cooldown_days": int(args.stress_rebalance_cooldown_days),
            "stress_confirm_days": int(args.stress_confirm_days),
        },
        "reward_config": {
            "benchmark_weight": args.benchmark_weight,
            "benchmark_shortfall_penalty_weight": args.benchmark_shortfall_penalty_weight,
            "benchmark_shortfall_penalty_cap": args.benchmark_shortfall_penalty_cap,
            "benchmark_shortfall_stress_scale": args.benchmark_shortfall_stress_scale,
        },
        "risk_budget_config": {
            "caution_invested_cap": args.stress_budget_caution_invested_cap,
            "caution_0050_cap": args.stress_budget_caution_0050_cap,
            "risk_off_invested_cap": args.stress_budget_risk_off_invested_cap,
            "risk_off_0050_cap": args.stress_budget_risk_off_0050_cap,
            "deep_risk_off_invested_cap": args.stress_budget_deep_risk_off_invested_cap,
            "deep_risk_off_0050_cap": args.stress_budget_deep_risk_off_0050_cap,
        },
        "summary": summary,
        "rows": rows,
    }
    out_json, out_csv = _write_outputs(rows, payload, seed=args.seed)

    print("=" * 72)
    print("Walk-forward complete")
    print(f"JSON: {out_json}")
    print(f"CSV:  {out_csv}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("=" * 72)


if __name__ == "__main__":
    main()
