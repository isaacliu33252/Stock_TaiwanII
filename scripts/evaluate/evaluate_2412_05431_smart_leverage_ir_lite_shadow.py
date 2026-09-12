#!/usr/bin/env python3
"""Taiwan IR-lite smart-leverage shadow for arXiv:2412.05431v2.

Research-only. This does not modify latest strategy, golden1_0531, target
weights, execution plans, or order files.

The paper's portable idea is not "hold LETF forever"; it is dynamic,
benchmark-relative, contrarian LETF sizing. This script implements a small
causal approximation:

  - benchmark: 70% 0050 / 30% 00679B
  - assets: 0050, 00631L, 00679B, cash
  - rebalance: monthly or quarterly
  - optimizer: choose a no-portfolio-leverage grid weight that maximizes
    trailing 252-day information ratio versus the benchmark, subject to
    effective equity beta and tail/drawdown filters.

It is deliberately simple and auditable; no neural network is trained here.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices  # noqa: E402
from backtest_group_a_plus_defensive_basket import _trade_cost  # noqa: E402
from backtest_group_a_plus_policy_signal import TICKERS, _normalize  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _metrics  # noqa: E402
from group_a_plus.runners.a2118 import (  # noqa: E402
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_warning_cashflow_guard import _resolve_end_date  # noqa: E402
from scripts.evaluate.evaluate_adaptive_review_interval_shadow import (  # noqa: E402
    _simulate_targets,
    _targets_from_report,
)


OUTPUT_JSON = PROJECT_ROOT / "results/2412_05431_smart_leverage_ir_lite_shadow.json"
OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2412_05431_smart_leverage_ir_lite_shadow.md"

BENCHMARK_WEIGHTS = {"0050.TW": 0.70, "00631L.TW": 0.0, "00632R.TW": 0.0, "00679B.TWO": 0.30, "cash": 0.0}
ASSET_COLUMNS = (*TICKERS, "cash")
DEFAULT_WINDOWS = [
    ("live_2024_2026", "2024-01-02", "latest", "recent"),
    ("active_2025_2026", "2025-01-02", "latest", "recent"),
    ("holdout_2022_full", "2022-01-03", "2022-12-30", "holdout"),
    ("holdout_2023", "2023-01-03", "2023-12-29", "holdout"),
    ("holdout_2026", "2026-01-02", "latest", "holdout"),
    ("backfill_2020_covid", "2020-01-02", "2020-12-31", "stress"),
    ("backfill_2021_may_correction", "2021-01-04", "2021-12-30", "stress"),
]


@dataclass(frozen=True)
class CandidateWeights:
    name: str
    weights: dict[str, float]

    @property
    def effective_equity_beta(self) -> float:
        return float(self.weights.get("0050.TW", 0.0)) + 2.0 * float(self.weights.get("00631L.TW", 0.0))


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def candidate_grid(
    *,
    max_00631l_weight: float = 0.30,
    max_effective_beta: float = 1.10,
    step: float = 0.05,
) -> list[CandidateWeights]:
    candidates: list[CandidateWeights] = []
    values = [round(i * step, 10) for i in range(int(round(1.0 / step)) + 1)]
    for w_631l in values:
        if w_631l > max_00631l_weight + 1e-12:
            continue
        for w_0050 in values:
            if w_0050 + 2.0 * w_631l > max_effective_beta + 1e-12:
                continue
            for w_bond in values:
                used = w_0050 + w_631l + w_bond
                if used > 1.0 + 1e-12:
                    continue
                weights = _normalize(
                    {
                        "0050.TW": w_0050,
                        "00631L.TW": w_631l,
                        "00632R.TW": 0.0,
                        "00679B.TWO": w_bond,
                        "cash": max(1.0 - used, 0.0),
                    }
                )
                if weights["0050.TW"] == 0.0 and weights["00631L.TW"] == 0.0:
                    continue
                name = f"w0050_{weights['0050.TW']:.2f}_w631l_{weights['00631L.TW']:.2f}_w679b_{weights['00679B.TWO']:.2f}"
                candidates.append(CandidateWeights(name=name, weights=weights))
    return candidates


def _portfolio_returns(returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    return (
        returns["0050.TW"].fillna(0.0) * float(weights.get("0050.TW", 0.0))
        + returns["00631L.TW"].fillna(0.0) * float(weights.get("00631L.TW", 0.0))
        + returns["00679B.TWO"].fillna(0.0) * float(weights.get("00679B.TWO", 0.0))
    )


def _max_drawdown_from_returns(returns: pd.Series) -> float:
    curve = (1.0 + returns.fillna(0.0)).cumprod()
    return float((curve / curve.cummax() - 1.0).min())


def information_ratio(candidate_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    excess = (candidate_returns - benchmark_returns).dropna()
    if len(excess) < 40:
        return float("-inf")
    std = float(excess.std(ddof=1))
    if std <= 1e-12:
        return float("-inf")
    return float(excess.mean() / std * np.sqrt(252.0))


def select_ir_lite_weights(
    returns: pd.DataFrame,
    candidates: list[CandidateWeights],
    *,
    benchmark_weights: dict[str, float] = BENCHMARK_WEIGHTS,
    benchmark_mdd_slack: float = 0.05,
    worst_20d_slack: float = 0.03,
    drawdown_penalty: float = 5.0,
    worst_20d_penalty: float = 3.0,
) -> tuple[CandidateWeights, dict[str, Any]]:
    benchmark_returns = _portfolio_returns(returns, benchmark_weights)
    benchmark_mdd = _max_drawdown_from_returns(benchmark_returns)
    benchmark_worst_20d = float((1.0 + benchmark_returns).rolling(20).apply(np.prod, raw=True).min() - 1.0)
    ranked: list[dict[str, Any]] = []
    fallback: dict[str, Any] | None = None
    for candidate in candidates:
        cand_ret = _portfolio_returns(returns, candidate.weights)
        ir = information_ratio(cand_ret, benchmark_returns)
        mdd = _max_drawdown_from_returns(cand_ret)
        worst_20d = float((1.0 + cand_ret).rolling(20).apply(np.prod, raw=True).min() - 1.0)
        drawdown_degradation = max(0.0, benchmark_mdd - mdd)
        worst_20d_degradation = max(0.0, benchmark_worst_20d - worst_20d)
        objective_score = float(
            ir - drawdown_penalty * drawdown_degradation - worst_20d_penalty * worst_20d_degradation
        )
        row = {
            "candidate": candidate,
            "information_ratio": ir,
            "objective_score": objective_score,
            "max_drawdown": mdd,
            "worst_20d_return": worst_20d,
            "drawdown_degradation": drawdown_degradation,
            "worst_20d_degradation": worst_20d_degradation,
            "passes_tail": bool(mdd >= benchmark_mdd - benchmark_mdd_slack and worst_20d >= benchmark_worst_20d - worst_20d_slack),
        }
        ranked.append(row)
        if fallback is None or objective_score > fallback["objective_score"]:
            fallback = row
    passing = [row for row in ranked if row["passes_tail"]]
    selected = max(passing or ranked, key=lambda row: row["objective_score"])
    selected_candidate: CandidateWeights = selected["candidate"]
    return selected_candidate, {
        "selected": {
            "name": selected_candidate.name,
            "weights": selected_candidate.weights,
            "effective_equity_beta": selected_candidate.effective_equity_beta,
            "information_ratio": float(selected["information_ratio"]),
            "objective_score": float(selected["objective_score"]),
            "max_drawdown": float(selected["max_drawdown"]),
            "worst_20d_return": float(selected["worst_20d_return"]),
            "drawdown_degradation": float(selected["drawdown_degradation"]),
            "worst_20d_degradation": float(selected["worst_20d_degradation"]),
            "passes_tail": bool(selected["passes_tail"]),
        },
        "benchmark_training": {
            "max_drawdown": benchmark_mdd,
            "worst_20d_return": benchmark_worst_20d,
        },
        "passing_candidates": int(sum(1 for row in ranked if row["passes_tail"])),
        "candidate_count": int(len(ranked)),
    }


def _weight_turnover(left: dict[str, float], right: dict[str, float]) -> float:
    return float(sum(abs(float(left.get(key, 0.0)) - float(right.get(key, 0.0))) for key in ASSET_COLUMNS))


def _cap_weight_move(
    current: dict[str, float],
    target: dict[str, float],
    *,
    max_turnover: float | None,
    no_trade_band: float,
) -> tuple[dict[str, float], dict[str, Any]]:
    turnover = _weight_turnover(current, target)
    if turnover <= no_trade_band:
        return dict(current), {
            "turnover_to_selected": turnover,
            "applied_turnover": 0.0,
            "turnover_cap_applied": False,
            "no_trade_band_applied": True,
        }
    if max_turnover is None or max_turnover <= 0.0 or turnover <= max_turnover:
        return dict(target), {
            "turnover_to_selected": turnover,
            "applied_turnover": turnover,
            "turnover_cap_applied": False,
            "no_trade_band_applied": False,
        }
    scale = max_turnover / max(turnover, 1e-12)
    capped = {
        key: float(current.get(key, 0.0)) + (float(target.get(key, 0.0)) - float(current.get(key, 0.0))) * scale
        for key in ASSET_COLUMNS
    }
    return _normalize(capped), {
        "turnover_to_selected": turnover,
        "applied_turnover": _weight_turnover(current, capped),
        "turnover_cap_applied": True,
        "no_trade_band_applied": False,
    }


def build_ir_lite_targets(
    prices: pd.DataFrame,
    *,
    candidates: list[CandidateWeights],
    lookback_days: int,
    rebalance_frequency: str,
    drawdown_penalty: float,
    worst_20d_penalty: float,
    max_rebalance_turnover: float | None,
    no_trade_band: float,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    returns = prices[list(TICKERS)].pct_change(fill_method=None).fillna(0.0)
    targets: list[dict[str, float]] = []
    decisions: list[dict[str, Any]] = []
    current = dict(BENCHMARK_WEIGHTS)
    last_period: str | None = None
    for i, dt in enumerate(prices.index):
        period = dt.strftime("%Y-%m") if rebalance_frequency == "monthly" else f"{dt.year}-Q{((dt.month - 1) // 3) + 1}"
        can_rebalance = i >= lookback_days and period != last_period
        if can_rebalance:
            training = returns.iloc[i - lookback_days : i]
            selected, info = select_ir_lite_weights(
                training,
                candidates,
                drawdown_penalty=drawdown_penalty,
                worst_20d_penalty=worst_20d_penalty,
            )
            applied, execution_gate = _cap_weight_move(
                current,
                selected.weights,
                max_turnover=max_rebalance_turnover,
                no_trade_band=no_trade_band,
            )
            current = applied
            decisions.append(
                {
                    "date": str(dt.date()),
                    "period": period,
                    **info["selected"],
                    "applied_weights": dict(current),
                    **execution_gate,
                }
            )
            last_period = period
        elif last_period is None:
            last_period = period
        targets.append({key: float(current.get(key, 0.0) or 0.0) for key in ASSET_COLUMNS})
    return pd.DataFrame(targets, index=prices.index), decisions


def _target_weight_summary(targets: pd.DataFrame) -> dict[str, float]:
    return {col: float(targets[col].mean()) for col in ASSET_COLUMNS if col in targets.columns}


def _simulate_targets_lot_rounded(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    lot_size: int,
) -> tuple[pd.Series, dict[str, Any]]:
    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = float(initial_value)
    current_key: tuple[float, ...] | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    lot = max(int(lot_size), 1)

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        weights = _normalize(target_weights.loc[dt].to_dict())
        target_key = tuple(round(float(weights.get(key, 0.0)), 8) for key in ASSET_COLUMNS)
        cost = 0.0
        turnover = 0.0
        if target_key != current_key:
            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            net_value = gross_value
            target_shares: dict[str, float] = {}
            target_values: dict[str, float] = {}
            for _iteration in range(3):
                target_shares = {}
                target_values = {}
                for ticker in TICKERS:
                    raw_shares = net_value * weights.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
                    rounded_shares = np.floor(raw_shares / lot) * lot
                    target_shares[ticker] = float(max(rounded_shares, 0.0))
                    target_values[ticker] = target_shares[ticker] * float(price_row[ticker])
                cost, turnover = _trade_cost(
                    current_values,
                    target_values,
                    commission_rate,
                    slippage_rate,
                    equity_etf_sell_tax,
                )
                net_value = max(gross_value - cost, 0.0)
            cash = max(net_value - sum(target_values.values()), 0.0)
            shares = dict(target_shares)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            current_key = target_key
        values.append(gross_value)

    return pd.Series(values, index=prices.index, dtype=float), {
        "transaction_cost": float(total_cost),
        "turnover_value": float(total_turnover),
        "rebalance_count": int(rebalance_count),
        "lot_size": lot,
    }


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    bucket: str,
    db_path: Path,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    lookback_days: int,
    rebalance_frequency: str,
    drawdown_penalty: float,
    worst_20d_penalty: float,
    max_rebalance_turnover: float | None,
    no_trade_band: float,
    lot_size: int | None,
    candidates: list[CandidateWeights],
) -> dict[str, Any]:
    resolved_end = _resolve_end_date(db_path, end)
    warmup_start = (pd.Timestamp(start) - pd.offsets.BDay(lookback_days + 40)).strftime("%Y-%m-%d")
    warmup_close = _load_prices(db_path, list(TICKERS), warmup_start, resolved_end)
    warmup_prices, coverage = _load_total_return_prices(db_path, warmup_close.index)
    prices = warmup_prices.loc[pd.Timestamp(start) : pd.Timestamp(resolved_end)].copy()
    if len(warmup_prices.loc[: prices.index[0]]) < lookback_days:
        raise RuntimeError(f"Not enough warmup rows for {label}")

    # Use warmup prices to build targets causally, then trim to requested window.
    ir_targets_full, decisions = build_ir_lite_targets(
        warmup_prices,
        candidates=candidates,
        lookback_days=lookback_days,
        rebalance_frequency=rebalance_frequency,
        drawdown_penalty=drawdown_penalty,
        worst_20d_penalty=worst_20d_penalty,
        max_rebalance_turnover=max_rebalance_turnover,
        no_trade_band=no_trade_band,
    )
    ir_targets = ir_targets_full.reindex(prices.index).ffill()
    benchmark_targets = pd.DataFrame([BENCHMARK_WEIGHTS for _ in prices.index], index=prices.index)

    latest_report, latest_frame = run_a2118(
        start=start,
        end=resolved_end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
    )
    latest_targets = _targets_from_report(latest_frame, latest_report).reindex(prices.index).ffill()

    benchmark_curve, benchmark_execution = _simulate_targets(
        prices,
        benchmark_targets,
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    latest_curve, latest_execution = _simulate_targets(
        prices,
        latest_targets,
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    ir_curve, ir_execution = _simulate_targets(
        prices,
        ir_targets,
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )

    benchmark_metrics = _metrics(benchmark_curve, initial_value)
    latest_metrics = _metrics(latest_curve, initial_value)
    ir_metrics = _metrics(ir_curve, initial_value)
    lot_rounded: dict[str, Any] | None = None
    if lot_size is not None and lot_size > 0:
        lot_curve, lot_execution = _simulate_targets_lot_rounded(
            prices,
            ir_targets,
            initial_value=initial_value,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            equity_etf_sell_tax=equity_etf_sell_tax,
            lot_size=int(lot_size),
        )
        lot_metrics = _metrics(lot_curve, initial_value)
        lot_rounded = {
            "metrics": lot_metrics,
            "execution": lot_execution,
            "delta_vs_fractional_ir_lite": {
                "final_value": float(lot_metrics["final_value"] - ir_metrics["final_value"]),
                "sharpe_ratio": float(lot_metrics["sharpe_ratio"] - ir_metrics["sharpe_ratio"]),
                "max_drawdown": float(lot_metrics["max_drawdown"] - ir_metrics["max_drawdown"]),
            },
        }

    payload = {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": resolved_end},
        "rebalance_frequency": rebalance_frequency,
        "lookback_days": lookback_days,
        "drawdown_penalty": drawdown_penalty,
        "worst_20d_penalty": worst_20d_penalty,
        "max_rebalance_turnover": max_rebalance_turnover,
        "no_trade_band": no_trade_band,
        "decision_count": len([d for d in decisions if pd.Timestamp(start) <= pd.Timestamp(d["date"]) <= pd.Timestamp(resolved_end)]),
        "turnover_cap_applied_count": int(
            sum(
                bool(d.get("turnover_cap_applied"))
                for d in decisions
                if pd.Timestamp(start) <= pd.Timestamp(d["date"]) <= pd.Timestamp(resolved_end)
            )
        ),
        "no_trade_band_applied_count": int(
            sum(
                bool(d.get("no_trade_band_applied"))
                for d in decisions
                if pd.Timestamp(start) <= pd.Timestamp(d["date"]) <= pd.Timestamp(resolved_end)
            )
        ),
        "target_weight_average": _target_weight_summary(ir_targets),
        "benchmark": {"metrics": benchmark_metrics, "execution": benchmark_execution},
        "latest_a2118": {"metrics": latest_metrics, "execution": latest_execution},
        "ir_lite": {"metrics": ir_metrics, "execution": ir_execution},
        "delta_vs_benchmark": {
            "final_value": float(ir_metrics["final_value"] - benchmark_metrics["final_value"]),
            "sharpe_ratio": float(ir_metrics["sharpe_ratio"] - benchmark_metrics["sharpe_ratio"]),
            "max_drawdown": float(ir_metrics["max_drawdown"] - benchmark_metrics["max_drawdown"]),
        },
        "delta_vs_latest_a2118": {
            "final_value": float(ir_metrics["final_value"] - latest_metrics["final_value"]),
            "sharpe_ratio": float(ir_metrics["sharpe_ratio"] - latest_metrics["sharpe_ratio"]),
            "max_drawdown": float(ir_metrics["max_drawdown"] - latest_metrics["max_drawdown"]),
        },
        "recent_decisions": [
            d for d in decisions if pd.Timestamp(start) <= pd.Timestamp(d["date"]) <= pd.Timestamp(resolved_end)
        ][-8:],
        "dividend_coverage": coverage,
    }
    if lot_rounded is not None:
        payload["lot_rounded_ir_lite"] = lot_rounded
    return payload


def _parse_windows(raw: list[str]) -> list[tuple[str, str, str, str]]:
    if not raw:
        return DEFAULT_WINDOWS
    parsed = []
    for item in raw:
        parts = [part.strip() for part in item.split(":")]
        if len(parts) != 4:
            raise ValueError("--window must be label:start:end:bucket")
        parsed.append((parts[0], parts[1], parts[2], parts[3]))
    return parsed


def _candidate_pass(window: dict[str, Any]) -> bool:
    delta_b = window["delta_vs_benchmark"]
    delta_l = window["delta_vs_latest_a2118"]
    return bool(
        delta_b["final_value"] > 0.0
        and delta_b["sharpe_ratio"] >= 0.0
        and delta_b["max_drawdown"] >= -0.02
        and delta_l["max_drawdown"] >= -0.03
    )


def _summarize(windows: list[dict[str, Any]]) -> dict[str, Any]:
    buckets = sorted({w["bucket"] for w in windows})
    out: dict[str, Any] = {}
    for bucket in ["all", *buckets]:
        rows = windows if bucket == "all" else [w for w in windows if w["bucket"] == bucket]
        out[bucket] = {
            "window_count": len(rows),
            "pass_windows": int(sum(_candidate_pass(w) for w in rows)),
            "total_delta_final_vs_benchmark": float(sum(w["delta_vs_benchmark"]["final_value"] for w in rows)),
            "total_delta_final_vs_latest_a2118": float(sum(w["delta_vs_latest_a2118"]["final_value"] for w in rows)),
            "avg_00631l_weight": float(np.mean([w["target_weight_average"].get("00631L.TW", 0.0) for w in rows])) if rows else 0.0,
        }
    holdout = out.get("holdout", {"window_count": 0, "pass_windows": 0})
    promotion_ready = bool(holdout["window_count"] > 0 and holdout["pass_windows"] == holdout["window_count"])
    out["promotion_ready"] = promotion_ready
    out["decision"] = "holdout_passed_needs_governance_review" if promotion_ready else "do_not_promote_keep_shadow"
    return out


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    candidates = candidate_grid(
        max_00631l_weight=float(args.max_00631l_weight),
        max_effective_beta=float(args.max_effective_beta),
        step=float(args.grid_step),
    )
    windows = [
        evaluate_window(
            label=label,
            start=start,
            end=end,
            bucket=bucket,
            db_path=_resolve(args.db),
            initial_value=float(args.initial_value),
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
            lookback_days=int(args.lookback_days),
            rebalance_frequency=str(args.rebalance_frequency),
            drawdown_penalty=float(args.drawdown_penalty),
            worst_20d_penalty=float(args.worst_20d_penalty),
            max_rebalance_turnover=(
                None if args.max_rebalance_turnover is None else float(args.max_rebalance_turnover)
            ),
            no_trade_band=float(args.no_trade_band),
            lot_size=args.lot_size,
            candidates=candidates,
        )
        for label, start, end, bucket in _parse_windows(args.window)
    ]
    return {
        "schema_version": 1,
        "report_type": "2412_05431_smart_leverage_ir_lite_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2412.05431v2 Smart leverage?",
        "policy": "research_only_no_groupa_plus_live_change",
        "scope": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_target_weights": False,
            "creates_orders": False,
        },
        "params": {
            "lookback_days": int(args.lookback_days),
            "rebalance_frequency": str(args.rebalance_frequency),
            "max_00631l_weight": float(args.max_00631l_weight),
            "max_effective_beta": float(args.max_effective_beta),
            "grid_step": float(args.grid_step),
            "drawdown_penalty": float(args.drawdown_penalty),
            "worst_20d_penalty": float(args.worst_20d_penalty),
            "max_rebalance_turnover": None if args.max_rebalance_turnover is None else float(args.max_rebalance_turnover),
            "no_trade_band": float(args.no_trade_band),
            "lot_size": args.lot_size,
            "candidate_count": len(candidates),
            "benchmark_weights": BENCHMARK_WEIGHTS,
        },
        "summary": _summarize(windows),
        "windows": windows,
    }


def _write_md(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2412.05431 Smart Leverage IR-lite Shadow",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['summary']['decision']}`",
        f"- Promotion ready: `{report['summary']['promotion_ready']}`",
        f"- Params: `{report['params']}`",
        "",
        "## Summary",
        "",
        "| Bucket | Windows | Pass | Delta Final vs Benchmark | Delta Final vs Latest A21.18 | Avg 00631L Weight |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for bucket, item in report["summary"].items():
        if not isinstance(item, dict) or "window_count" not in item:
            continue
        lines.append(
            f"| {bucket} | {item['window_count']} | {item['pass_windows']}/{item['window_count']} | "
            f"{item['total_delta_final_vs_benchmark']:.2f} | {item['total_delta_final_vs_latest_a2118']:.2f} | "
            f"{item['avg_00631l_weight']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Window Details",
            "",
            "| Window | Bucket | IR Final | Benchmark Final | Latest A21.18 Final | dFinal vs Benchmark | dSharpe vs Benchmark | dMDD vs Benchmark | dFinal vs Latest | Avg 00631L | Pass |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for window in report["windows"]:
        db = window["delta_vs_benchmark"]
        dl = window["delta_vs_latest_a2118"]
        lines.append(
            f"| {window['label']} | {window['bucket']} | {window['ir_lite']['metrics']['final_value']:.2f} | "
            f"{window['benchmark']['metrics']['final_value']:.2f} | {window['latest_a2118']['metrics']['final_value']:.2f} | "
            f"{db['final_value']:.2f} | {db['sharpe_ratio']:.4f} | {db['max_drawdown']:.4f} | "
            f"{dl['final_value']:.2f} | {window['target_weight_average'].get('00631L.TW', 0.0):.4f} | {_candidate_pass(window)} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "- Research-only. No latest strategy, golden1_0531, target weights, execution plan, or order file was changed.",
            "- Promotion requires holdout pass plus separate governance, lot-rounding, turnover, and incident replay review.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--lookback-days", type=int, default=252)
    parser.add_argument("--rebalance-frequency", choices=("monthly", "quarterly"), default="quarterly")
    parser.add_argument("--max-00631l-weight", type=float, default=0.30)
    parser.add_argument("--max-effective-beta", type=float, default=1.10)
    parser.add_argument("--grid-step", type=float, default=0.05)
    parser.add_argument("--drawdown-penalty", type=float, default=5.0)
    parser.add_argument("--worst-20d-penalty", type=float, default=3.0)
    parser.add_argument("--max-rebalance-turnover", type=float, default=None)
    parser.add_argument("--no-trade-band", type=float, default=0.0)
    parser.add_argument("--lot-size", type=int, default=None)
    parser.add_argument("--window", action="append", default=[])
    parser.add_argument("--output-json", default=str(OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    output_json = _resolve(args.output_json)
    output_md = _resolve(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(report, output_md)
    print(
        json.dumps(
            {
                "promotion_ready": report["summary"]["promotion_ready"],
                "decision": report["summary"]["decision"],
                "output_json": str(output_json),
                "output_md": str(output_md),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
