#!/usr/bin/env python3
"""Research-only LightGBM advisory overlay backtest for Group A+."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from evaluate_lightgbm_baseline import (
    DEFAULT_PANEL,
    attach_cross_asset_relation_features,
    attach_fourier_price_features,
    attach_llm_sentiment_features,
    _feature_frame,
    _make_model,
    _target_from_panel,
)
from group_a_plus.validation.purged_walk_forward import PurgedWalkForwardSplit
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_RUNNER_JSON = PROJECT_ROOT / "results" / "group_a_plus_runner_latest_20260630_fixed.json"
DEFAULT_RUNNER_FRAME = PROJECT_ROOT / "results" / "group_a_plus_runner_latest_20260630_fixed_frame.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_lightgbm_advisory_backtest_latest.json"


def load_runner_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not payload.get("success", False):
        raise ValueError(f"runner payload is not successful: {path}")
    data = payload.get("data", {})
    if "base_weights" not in data or "metrics" not in data:
        raise ValueError("runner payload is missing base_weights or metrics")
    return data


def load_runner_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "dt" not in frame.columns or "execution_regime" not in frame.columns:
        raise ValueError("runner frame must include dt and execution_regime")
    frame["dt"] = pd.to_datetime(frame["dt"], errors="coerce").dt.normalize()
    frame = frame.dropna(subset=["dt"]).sort_values("dt").set_index("dt")
    return frame


def load_panel_for_advisory(
    panel_path: Path,
    *,
    llm_sentiment_path: Path | None = None,
    fourier_ticker: str | None = None,
    cross_asset_relations: bool = False,
    db_path: Path = DB_PATH,
) -> pd.DataFrame:
    panel = pd.read_csv(panel_path, encoding="utf-8-sig")
    if "date" not in panel.columns:
        raise ValueError("panel is missing date column")
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce").dt.normalize()
    panel = panel.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if "is_live" in panel.columns:
        panel = panel[~panel["is_live"].astype(bool)].reset_index(drop=True)
    if llm_sentiment_path is not None:
        panel = attach_llm_sentiment_features(panel, llm_sentiment_path, date_column="date", lag_days=1)
    if fourier_ticker:
        panel = attach_fourier_price_features(panel, db_path=db_path, ticker=fourier_ticker)
    if cross_asset_relations:
        panel = attach_cross_asset_relation_features(panel, db_path=db_path)
    return panel


def oos_lightgbm_probabilities(
    panel: pd.DataFrame,
    *,
    target_column: str = "forward_gain_h20",
    baseline_column: str = "prob_up_h20",
    n_splits: int = 4,
    test_size: int | None = None,
    train_size: int | None = None,
    purge: int = 20,
    min_train_size: int = 80,
) -> tuple[pd.DataFrame, list[dict[str, Any]], str]:
    y = _target_from_panel(panel, target_column)
    x = _feature_frame(panel, target_column)
    valid = y.notna()
    x = x.loc[valid].reset_index(drop=True)
    y = y.loc[valid].reset_index(drop=True)
    dates = pd.to_datetime(panel.loc[valid, "date"]).reset_index(drop=True)
    baseline = (
        pd.to_numeric(panel.loc[valid, baseline_column], errors="coerce").fillna(0.5).clip(0.0, 1.0).reset_index(drop=True)
        if baseline_column in panel.columns
        else pd.Series(0.5, index=x.index)
    )
    splitter = PurgedWalkForwardSplit(
        n_splits=n_splits,
        test_size=test_size,
        train_size=train_size,
        purge=purge,
        min_train_size=min_train_size,
    )

    rows: list[dict[str, Any]] = []
    folds: list[dict[str, Any]] = []
    model_kind = "unknown"
    for fold, (train_idx, test_idx) in enumerate(splitter.split(x), start=1):
        model, model_kind = _make_model(random_state=701 + fold)
        model.fit(x.iloc[train_idx], y.iloc[train_idx])
        proba = model.predict_proba(x.iloc[test_idx])[:, 1]
        for local_pos, prob in zip(test_idx, proba):
            rows.append(
                {
                    "date": dates.iloc[local_pos],
                    "oos_prob_up": float(prob),
                    "truth": int(y.iloc[local_pos]),
                    "baseline_prob_up": float(baseline.iloc[local_pos]),
                    "fold": int(fold),
                }
            )
        folds.append(
            {
                "fold": fold,
                "train_start": str(dates.iloc[train_idx[0]].date()),
                "train_end": str(dates.iloc[train_idx[-1]].date()),
                "test_start": str(dates.iloc[test_idx[0]].date()),
                "test_end": str(dates.iloc[test_idx[-1]].date()),
                "train_rows": int(len(train_idx)),
                "test_rows": int(len(test_idx)),
                "purge_rows": int(purge),
            }
        )
    probs = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    return probs, folds, model_kind


def advisory_weight_frame(
    frame: pd.DataFrame,
    weights_by_regime: dict[str, dict[str, float]],
    oos_prob: pd.DataFrame,
    *,
    down_threshold: float,
    trim_fraction: float,
    execution_lag_days: int = 1,
    apply_regimes: tuple[str, ...] = ("golden1",),
) -> pd.DataFrame:
    probs = oos_prob.set_index("date")["oos_prob_up"].sort_index()
    used_prob = probs.reindex(frame.index).shift(execution_lag_days)
    rows: list[dict[str, Any]] = []
    for dt, row in frame.iterrows():
        regime = str(row["execution_regime"])
        weights = dict(_normalize(weights_by_regime[regime]))
        prob = used_prob.loc[dt]
        applied_trim = 0.0
        if regime in apply_regimes and pd.notna(prob) and float(prob) < down_threshold:
            applied_trim = float(trim_fraction)
            old_lev = float(weights.get("00631L.TW", 0.0))
            reduction = old_lev * applied_trim
            weights["00631L.TW"] = old_lev - reduction
            weights["cash"] = float(weights.get("cash", 0.0)) + reduction
            weights = dict(_normalize(weights))
        out = {
            "dt": dt,
            "execution_regime": regime,
            "advisory_prob_used": None if pd.isna(prob) else float(prob),
            "trim_fraction_applied": applied_trim,
        }
        out.update({f"weight_{ticker}": float(weights.get(ticker, 0.0)) for ticker in TICKERS})
        out["weight_cash"] = float(weights.get("cash", 0.0))
        rows.append(out)
    return pd.DataFrame(rows).set_index("dt")


def simulate_dynamic_weight_curve(
    prices: pd.DataFrame,
    weight_frame: pd.DataFrame,
    *,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    rebalance_tolerance: float = 1e-10,
) -> tuple[pd.Series, dict[str, float]]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    previous_weights: dict[str, float] | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        weights = {ticker: float(weight_frame.loc[dt, f"weight_{ticker}"]) for ticker in TICKERS}
        weights["cash"] = float(weight_frame.loc[dt, "weight_cash"])
        weights = dict(_normalize(weights))
        should_rebalance = previous_weights is None or any(
            abs(weights.get(key, 0.0) - previous_weights.get(key, 0.0)) > rebalance_tolerance
            for key in (*TICKERS, "cash")
        )
        if should_rebalance:
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _iteration in range(3):
                target_values = {ticker: net_value * weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover = _trade_cost(
                    current_values,
                    target_values,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
                )
                net_value = max(gross_value - cost, 0.0)
            shares = {
                ticker: net_value * weights.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
                for ticker in TICKERS
            }
            cash = net_value * weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            previous_weights = weights
        values.append(gross_value)
    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
    }


def _deltas(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    return {
        "delta_final_value": float(candidate["final_value"] - baseline["final_value"]),
        "delta_sharpe": float(candidate["sharpe_ratio"] - baseline["sharpe_ratio"]),
        "delta_sortino": float(candidate["sortino_ratio"] - baseline["sortino_ratio"]),
        "delta_max_drawdown": float(candidate["max_drawdown"] - baseline["max_drawdown"]),
        "delta_worst_20d_return": float(candidate["worst_20d_return"] - baseline["worst_20d_return"]),
    }


def _dominates(candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
    return bool(
        candidate["final_value"] >= baseline["final_value"]
        and candidate["sharpe_ratio"] >= baseline["sharpe_ratio"]
        and candidate["max_drawdown"] >= baseline["max_drawdown"]
    )


def build_report(
    *,
    panel_path: Path,
    runner_json_path: Path,
    runner_frame_path: Path,
    db_path: Path = DB_PATH,
    llm_sentiment_path: Path | None = None,
    fourier_ticker: str | None = None,
    cross_asset_relations: bool = False,
    target_column: str = "forward_gain_h20",
    n_splits: int = 4,
    test_size: int | None = None,
    train_size: int | None = None,
    purge: int = 20,
    min_train_size: int = 80,
    thresholds: tuple[float, ...] = (0.35, 0.40, 0.45, 0.50),
    trim_fractions: tuple[float, ...] = (0.15, 0.25, 0.35, 0.50),
) -> tuple[dict[str, Any], pd.DataFrame]:
    runner = load_runner_payload(runner_json_path)
    frame = load_runner_frame(runner_frame_path)
    panel = load_panel_for_advisory(
        panel_path,
        llm_sentiment_path=llm_sentiment_path,
        fourier_ticker=fourier_ticker,
        cross_asset_relations=cross_asset_relations,
        db_path=db_path,
    )
    oos_prob, folds, model_kind = oos_lightgbm_probabilities(
        panel,
        target_column=target_column,
        n_splits=n_splits,
        test_size=test_size,
        train_size=train_size,
        purge=purge,
        min_train_size=min_train_size,
    )

    cost = runner.get("cost_assumptions", {})
    initial_value = float(runner["metrics"]["initial_value"])
    commission_rate = float(cost.get("commission_rate", 0.001425))
    slippage_rate = float(cost.get("slippage_rate", 0.0005))
    equity_etf_sell_tax = float(cost.get("equity_etf_sell_tax", 0.001))
    prices, dividend_coverage = _load_total_return_prices(db_path, frame.index)
    weights_by_regime = runner["base_weights"]

    baseline_weights = advisory_weight_frame(
        frame,
        weights_by_regime,
        pd.DataFrame({"date": [], "oos_prob_up": []}),
        down_threshold=0.0,
        trim_fraction=0.0,
    )
    baseline_curve, baseline_exec = simulate_dynamic_weight_curve(
        prices,
        baseline_weights,
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    baseline_metrics = {**_metrics(baseline_curve, initial_value), **baseline_exec}

    rows: list[dict[str, Any]] = []
    best_daily = pd.DataFrame()
    best_key: tuple[float, float, float] | None = None
    best_label = ""
    for threshold in thresholds:
        for trim in trim_fractions:
            weight_frame = advisory_weight_frame(
                frame,
                weights_by_regime,
                oos_prob,
                down_threshold=float(threshold),
                trim_fraction=float(trim),
            )
            curve, execution = simulate_dynamic_weight_curve(
                prices,
                weight_frame,
                initial_value=initial_value,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                equity_etf_sell_tax=equity_etf_sell_tax,
            )
            metrics = {**_metrics(curve, initial_value), **execution}
            deltas = _deltas(metrics, baseline_metrics)
            row = {
                "variant": f"lgbm_reduce_l_when_p_lt_{threshold:.2f}_trim_{trim:.2f}",
                "down_threshold": float(threshold),
                "trim_fraction": float(trim),
                "advisory_days": int((weight_frame["trim_fraction_applied"] > 0.0).sum()),
                "joint_pass": _dominates(metrics, baseline_metrics),
                **metrics,
                **deltas,
            }
            rows.append(row)
            rank_key = (
                float(row["delta_final_value"]),
                float(row["delta_sharpe"]),
                float(row["delta_max_drawdown"]),
            )
            if best_key is None or rank_key > best_key:
                best_key = rank_key
                best_label = str(row["variant"])
                best_daily = weight_frame.copy()
                best_daily["baseline_value"] = baseline_curve
                best_daily["advisory_value"] = curve
                best_daily["advisory_variant"] = best_label

    ranked = sorted(rows, key=lambda row: (row["delta_final_value"], row["delta_sharpe"], row["delta_max_drawdown"]), reverse=True)
    best = ranked[0] if ranked else None
    report = {
        "schema_version": 1,
        "report_type": "group_a_plus_lightgbm_advisory_backtest",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "panel": str(panel_path),
            "runner_json": str(runner_json_path),
            "runner_frame": str(runner_frame_path),
            "db": str(db_path),
            "llm_sentiment": {"enabled": llm_sentiment_path is not None, "path": str(llm_sentiment_path) if llm_sentiment_path else None},
            "fourier": {"enabled": bool(fourier_ticker), "ticker": fourier_ticker},
            "cross_asset_relations": {"enabled": bool(cross_asset_relations)},
        },
        "validation": {
            "method": "purged_walk_forward_oos_probabilities",
            "model_kind": model_kind,
            "target_column": target_column,
            "n_splits": n_splits,
            "test_size": test_size,
            "train_size": train_size,
            "purge": purge,
            "min_train_size": min_train_size,
            "folds": folds,
            "oos_probability_rows": int(len(oos_prob)),
        },
        "policy": {
            "type": "reduce_only_00631L_to_cash",
            "execution_lag_days": 1,
            "apply_regimes": ["golden1"],
            "thresholds": list(thresholds),
            "trim_fractions": list(trim_fractions),
        },
        "baseline": baseline_metrics,
        "runner_reported_metrics": runner["metrics"],
        "dividend_coverage": dividend_coverage,
        "sweep": ranked,
        "best_variant": best,
        "promotion_decision": "research_only" if not best or not best["joint_pass"] else "candidate_for_deeper_ablation",
        "active_allocation_impact": "none",
    }
    return report, best_daily.reset_index()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--runner-json", default=str(DEFAULT_RUNNER_JSON))
    parser.add_argument("--runner-frame", default=str(DEFAULT_RUNNER_FRAME))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--llm-sentiment", default=None)
    parser.add_argument("--fourier-ticker", default=None)
    parser.add_argument("--cross-asset-relations", action="store_true")
    parser.add_argument("--target-column", default="forward_gain_h20")
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--test-size", type=int, default=None)
    parser.add_argument("--train-size", type=int, default=None)
    parser.add_argument("--purge", type=int, default=20)
    parser.add_argument("--min-train-size", type=int, default=80)
    parser.add_argument("--thresholds", default="0.35,0.40,0.45,0.50")
    parser.add_argument("--trim-fractions", default="0.15,0.25,0.35,0.50")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--daily-output", default=None)
    args = parser.parse_args()

    std = OutputStandardizer("evaluate_lightgbm_advisory_backtest")
    try:
        thresholds = tuple(float(x.strip()) for x in args.thresholds.split(",") if x.strip())
        trim_fractions = tuple(float(x.strip()) for x in args.trim_fractions.split(",") if x.strip())
        report, daily = build_report(
            panel_path=Path(args.panel),
            runner_json_path=Path(args.runner_json),
            runner_frame_path=Path(args.runner_frame),
            db_path=Path(args.db),
            llm_sentiment_path=Path(args.llm_sentiment) if args.llm_sentiment else None,
            fourier_ticker=args.fourier_ticker,
            cross_asset_relations=args.cross_asset_relations,
            target_column=args.target_column,
            n_splits=args.n_splits,
            test_size=args.test_size,
            train_size=args.train_size,
            purge=args.purge,
            min_train_size=args.min_train_size,
            thresholds=thresholds,
            trim_fractions=trim_fractions,
        )
        payload = std.success(report)
        if args.daily_output:
            daily.to_csv(args.daily_output, index=False, encoding="utf-8-sig")
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"LightGBM advisory backtest report: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
