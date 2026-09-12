#!/usr/bin/env python3
"""Backtest Riccati/MV-inspired cap-to-cash risk budget for GroupA+.

Research-only follow-up for arXiv:2608.07977.  This evaluates a conservative
translation of the paper's transferable idea: rolling mean-variance risk
budgeting under cross-asset covariance.  It does not use today's NCF files in
historical replay.  Each day uses only trailing returns available before that
day; when the MV shadow allocation is lower than the active latest target for
00631L or 00632R, the excess weight is moved to cash.

This script never changes live strategy weights, execution guards, signals, or
orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS, _normalize  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices  # noqa: E402
from group_a_plus.integrations.riccati_mv_shadow import (  # noqa: E402
    MeanVarianceSpec,
    constrained_mv_shadow_weights,
    portfolio_stats,
    shrink_covariance,
)
from group_a_plus.runners.latest import run_latest  # noqa: E402
from scripts.evaluate.evaluate_00631l_compounding_regime_no_add_shadow import (  # noqa: E402
    _metric_delta,
    _simulate_baseline,
    simulate_no_add_guard,
)
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import _resolve_end_date, _targets_from_report  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_riccati_mv_risk_budget_shadow_2608_07977.json"
DEFAULT_CSV = PROJECT_ROOT / "results" / "group_a_plus_riccati_mv_risk_budget_shadow_2608_07977.csv"
DEFAULT_LATEST_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "riccati_mv_risk_budget_shadow.json"
DEFAULT_WINDOWS = (
    ("covid_2020", "2020-01-02", "2020-12-31", "out_of_sample"),
    ("rate_hike_2022", "2022-01-03", "2022-10-31", "out_of_sample"),
    ("full_2024", "2024-01-02", "2024-12-31", "out_of_sample"),
    ("active_2025_2026", "2025-01-02", "latest", "tuning_window"),
    ("taiwan_2026_q1q2_stress", "2026-02-02", "2026-04-30", "stress_window"),
    ("taiwan_2026_recent", "2026-05-15", "latest", "recent_window"),
)
DEFAULT_CAP_TICKERS = ("00631L.TW", "00632R.TW")


def _parse_windows(raw: str) -> list[tuple[str, str, str, str]]:
    if raw == "default":
        return list(DEFAULT_WINDOWS)
    windows: list[tuple[str, str, str, str]] = []
    for item in raw.split(";"):
        if not item.strip():
            continue
        parts = [part.strip() for part in item.split(",")]
        if len(parts) != 4:
            raise ValueError("Each window must be label,start,end,kind")
        windows.append((parts[0], parts[1], parts[2], parts[3]))
    return windows


def _trailing_mu(returns: pd.DataFrame, dt: pd.Timestamp, *, lookback: int) -> pd.Series | None:
    trailing = returns.loc[returns.index < dt].tail(lookback)
    if trailing.empty:
        return None
    return trailing.mean().reindex(TICKERS).fillna(0.0)


def _trailing_cov(returns: pd.DataFrame, dt: pd.Timestamp, *, spec: MeanVarianceSpec) -> pd.DataFrame | None:
    trailing = returns.loc[returns.index < dt].tail(spec.lookback_days)
    if len(trailing) < spec.min_observations:
        return None
    return shrink_covariance(trailing.reindex(columns=list(TICKERS)), shrinkage=spec.shrinkage)


def apply_riccati_mv_caps_to_targets(
    prices: pd.DataFrame,
    target_weights: pd.DataFrame,
    *,
    spec: MeanVarianceSpec,
    mu_lookback: int = 63,
    confirmation: pd.Series | None = None,
    cap_tickers: tuple[str, ...] = DEFAULT_CAP_TICKERS,
    excess_destination: str = "cash",
    re_evaluate_current_policy: bool = False,
    cap_beta: float = 1.0,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if excess_destination not in {"cash", "0050.TW"}:
        raise ValueError(f"unsupported excess destination: {excess_destination}")
    cap_beta = max(0.0, min(1.0, float(cap_beta)))
    prices = prices[list(TICKERS)].astype(float).sort_index()
    live_index = target_weights.index.intersection(prices.index)
    target_weights = target_weights.reindex(live_index).fillna(0.0)
    confirmation = (
        confirmation.reindex(live_index, fill_value=False).astype(bool)
        if confirmation is not None
        else pd.Series(True, index=live_index, dtype=bool)
    )
    returns = prices.pct_change().dropna()
    guarded_rows: list[dict[str, float]] = []
    events: list[dict[str, Any]] = []

    for dt, base_row in target_weights.iterrows():
        baseline = {ticker: float(base_row.get(ticker, 0.0) or 0.0) for ticker in (*TICKERS, "cash")}
        if not bool(confirmation.loc[dt]):
            guarded_rows.append(_normalize(baseline))
            continue
        mu = _trailing_mu(returns, dt, lookback=mu_lookback)
        cov = _trailing_cov(returns, dt, spec=spec)
        if mu is None or cov is None:
            guarded_rows.append(_normalize(baseline))
            continue

        shadow, diagnostic = constrained_mv_shadow_weights(mu, cov, baseline_weights=baseline, spec=spec)
        guarded = dict(baseline)
        moved_to_cash = 0.0
        capped: dict[str, dict[str, float]] = {}
        for ticker in cap_tickers:
            base_weight = float(baseline.get(ticker, 0.0) or 0.0)
            shadow_weight = float(shadow.get(ticker, 0.0) or 0.0)
            cap = min(base_weight, shadow_weight)
            if cap + 1e-12 < base_weight:
                applied_cap = base_weight - cap_beta * (base_weight - cap)
                guarded[ticker] = applied_cap
                moved = base_weight - applied_cap
                moved_to_cash += moved
                capped[ticker] = {
                    "baseline": base_weight,
                    "shadow_cap": cap,
                    "applied_cap": applied_cap,
                    "cap_beta": cap_beta,
                    "moved_to_cash": moved,
                }
        if moved_to_cash > 0.0:
            guarded[excess_destination] = float(guarded.get(excess_destination, 0.0) or 0.0) + moved_to_cash
        re_evaluation: dict[str, Any] | None = None
        if re_evaluate_current_policy:
            second_shadow, second_diagnostic = constrained_mv_shadow_weights(mu, cov, baseline_weights=guarded, spec=spec)
            second_moved_to_cash = 0.0
            second_capped: dict[str, dict[str, float]] = {}
            for ticker in cap_tickers:
                base_weight = float(guarded.get(ticker, 0.0) or 0.0)
                shadow_weight = float(second_shadow.get(ticker, 0.0) or 0.0)
                cap = min(base_weight, shadow_weight)
                if cap + 1e-12 < base_weight:
                    applied_cap = base_weight - cap_beta * (base_weight - cap)
                    guarded[ticker] = applied_cap
                    moved = base_weight - applied_cap
                    second_moved_to_cash += moved
                    second_capped[ticker] = {
                        "baseline": base_weight,
                        "shadow_cap": cap,
                        "applied_cap": applied_cap,
                        "cap_beta": cap_beta,
                        "moved_to_cash": moved,
                    }
            if second_moved_to_cash > 0.0:
                guarded[excess_destination] = float(guarded.get(excess_destination, 0.0) or 0.0) + second_moved_to_cash
            re_evaluation = {
                "second_optimizer_status": second_diagnostic.get("status"),
                "second_shadow_weights": second_shadow,
                "second_capped": second_capped,
                "second_excess_weight_moved": second_moved_to_cash,
                "stable_after_re_evaluation": second_moved_to_cash <= spec.grid_step + 1e-12,
            }
            for ticker, event in second_capped.items():
                capped[ticker] = {
                    "baseline": float(baseline.get(ticker, 0.0) or 0.0),
                    "shadow_cap": event["shadow_cap"],
                    "applied_cap": event["applied_cap"],
                    "cap_beta": cap_beta,
                    "moved_to_cash": float(baseline.get(ticker, 0.0) or 0.0) - event["applied_cap"],
                }
            moved_to_cash += second_moved_to_cash
        if moved_to_cash > 0.0:
            latest_stats = portfolio_stats(baseline, mu, cov)
            guarded_stats = portfolio_stats(guarded, mu, cov)
            event = {
                "date": str(pd.Timestamp(dt).date()),
                "capped": capped,
                "excess_destination": excess_destination,
                "excess_weight_moved": moved_to_cash,
                "optimizer_status": diagnostic.get("status"),
                "cap_beta": cap_beta,
                "latest_annualized_volatility": latest_stats["annualized_volatility"],
                "guarded_annualized_volatility": guarded_stats["annualized_volatility"],
            }
            if re_evaluation is not None:
                event["current_policy_re_evaluation"] = re_evaluation
            events.append(event)
        guarded_rows.append(_normalize(guarded))

    return pd.DataFrame(guarded_rows, index=target_weights.index), events


def build_confirmation_series(
    frame: pd.DataFrame,
    *,
    mode: str,
    total_risk_min: int,
    tail_risk_min: int,
    drawdown_max: float,
    vol_ratio_min: float,
) -> pd.Series:
    if mode == "always":
        return pd.Series(True, index=frame.index, dtype=bool)
    if mode == "total_risk":
        return frame["total_risk_score_lookback_max"].fillna(0).astype(float) >= float(total_risk_min)
    if mode == "tail_or_drawdown":
        tail = frame["tail_risk_score"].fillna(0).astype(float) >= float(tail_risk_min)
        drawdown = frame["drawdown"].fillna(0.0).astype(float) <= float(drawdown_max)
        return tail | drawdown
    if mode == "tail_only":
        return frame["tail_risk_score"].fillna(0).astype(float) >= float(tail_risk_min)
    if mode == "tail_drawdown_vol":
        tail = frame["tail_risk_score"].fillna(0).astype(float) >= float(tail_risk_min)
        drawdown = frame["drawdown"].fillna(0.0).astype(float) <= float(drawdown_max)
        vol = frame["realized_vol_ratio_20_60"].fillna(0.0).astype(float) >= float(vol_ratio_min)
        return tail & (drawdown | vol)
    raise ValueError(f"unknown confirmation mode: {mode}")


def evaluate_window(
    *,
    db_path: Path,
    label: str,
    start: str,
    end: str,
    kind: str,
    initial_value: float,
    transaction_cost_bps: float,
    spec: MeanVarianceSpec,
    confirmation_mode: str,
    total_risk_min: int,
    tail_risk_min: int,
    drawdown_max: float,
    vol_ratio_min: float,
    cap_tickers: tuple[str, ...],
    excess_destination: str,
    re_evaluate_current_policy: bool,
    cap_beta: float,
) -> dict[str, Any]:
    resolved_end = _resolve_end_date(db_path, end)
    report, frame = run_latest(start, resolved_end, initial_value, db_path)
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index).normalize()
    warmup_start = (pd.Timestamp(start) - pd.Timedelta(days=max(420, spec.lookback_days * 2))).date().isoformat()
    prices_with_warmup = _load_prices(
        db_path,
        list(TICKERS),
        warmup_start,
        resolved_end,
        exclude_zero_volume=True,
    )
    prices = prices_with_warmup.reindex(frame.index).dropna()
    target_weights = _targets_from_report(frame.reindex(prices.index), report)
    confirmation = build_confirmation_series(
        frame.reindex(prices.index),
        mode=confirmation_mode,
        total_risk_min=total_risk_min,
        tail_risk_min=tail_risk_min,
        drawdown_max=drawdown_max,
        vol_ratio_min=vol_ratio_min,
    )
    guarded_targets, events = apply_riccati_mv_caps_to_targets(
        prices_with_warmup,
        target_weights,
        spec=spec,
        confirmation=confirmation,
        cap_tickers=cap_tickers,
        excess_destination=excess_destination,
        re_evaluate_current_policy=re_evaluate_current_policy,
        cap_beta=cap_beta,
    )

    baseline = _simulate_baseline(prices, target_weights, initial_value, transaction_cost_bps)
    guarded = simulate_no_add_guard(
        prices=prices,
        target_weights=guarded_targets,
        regimes=pd.Series("TRANSITIONAL", index=prices.index),
        initial_value=initial_value,
        baseline_add_fraction=1.0,
        transaction_cost_bps=transaction_cost_bps,
    )
    delta = _metric_delta(guarded, baseline)
    return {
        "label": label,
        "kind": kind,
        "window": {"start": start, "end": resolved_end, "rows": int(len(prices))},
        "active_strategy_id": report.get("active_strategy_id"),
        "baseline": baseline,
        "riccati_mv_cap_to_cash": guarded,
        "delta_vs_baseline": delta,
        "confirmation_mode": confirmation_mode,
        "cap_tickers": list(cap_tickers),
        "excess_destination": excess_destination,
        "re_evaluate_current_policy": re_evaluate_current_policy,
        "cap_beta": cap_beta,
        "confirmation_days": int(confirmation.sum()),
        "cap_event_days": int(len(events)),
        "cap_events_sample": events[:120],
    }


def _decision(windows: list[dict[str, Any]]) -> dict[str, Any]:
    deltas = [item["delta_vs_baseline"] for item in windows]
    improves_mdd = sum(1 for delta in deltas if delta["max_drawdown"] > 0.0)
    improves_sharpe = sum(1 for delta in deltas if delta["sharpe_ratio"] > 0.0)
    improves_final = sum(1 for delta in deltas if delta["final_value"] > 0.0)
    severe_final_loss = any(delta["final_value"] < -0.03 * item["baseline"]["metrics"]["final_value"] for item, delta in zip(windows, deltas))
    promotion_allowed = improves_mdd == len(windows) and improves_sharpe >= len(windows) - 1 and not severe_final_loss
    return {
        "promotion_allowed": promotion_allowed,
        "decision": "eligible_for_manual_review_not_auto_promote" if promotion_allowed else "do_not_promote_keep_shadow",
        "improves_max_drawdown_windows": improves_mdd,
        "improves_sharpe_windows": improves_sharpe,
        "improves_final_value_windows": improves_final,
        "window_count": len(windows),
        "severe_final_value_loss": severe_final_loss,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    spec = MeanVarianceSpec(
        lookback_days=int(args.lookback_days),
        min_observations=int(args.min_observations),
        shrinkage=float(args.shrinkage),
        grid_step=float(args.grid_step),
        min_cash=float(args.min_cash),
        target_return_fraction=float(args.target_return_fraction),
        variance_penalty=float(args.variance_penalty),
    )
    cap_tickers = tuple(item.strip().upper() for item in str(args.cap_tickers).split(",") if item.strip())
    invalid = sorted(set(cap_tickers) - set(TICKERS))
    if invalid:
        raise ValueError(f"unknown cap tickers: {invalid}")
    windows = [
        evaluate_window(
            db_path=Path(args.db),
            label=label,
            start=start,
            end=end,
            kind=kind,
            initial_value=float(args.initial_value),
            transaction_cost_bps=float(args.transaction_cost_bps),
            spec=spec,
            confirmation_mode=str(args.confirmation_mode),
            total_risk_min=int(args.total_risk_min),
            tail_risk_min=int(args.tail_risk_min),
            drawdown_max=float(args.drawdown_max),
            vol_ratio_min=float(args.vol_ratio_min),
            cap_tickers=cap_tickers,
            excess_destination=str(args.excess_destination),
            re_evaluate_current_policy=bool(args.re_evaluate_current_policy),
            cap_beta=float(args.cap_beta),
        )
        for label, start, end, kind in _parse_windows(args.windows)
    ]
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_riccati_mv_risk_budget_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2608.07977",
        "secondary_source_paper": "arXiv:2608.17808",
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "method": "trailing_return_mean_variance_cap_00631l_00632r_to_cash_no_ncf_lookahead",
        "re_evaluation_method": (
            "current_policy_two_pass_cap_re_evaluation_2608_17808"
            if args.re_evaluate_current_policy
            else "disabled"
        ),
        "confirmation": {
            "mode": str(args.confirmation_mode),
            "total_risk_min": int(args.total_risk_min),
            "tail_risk_min": int(args.tail_risk_min),
            "drawdown_max": float(args.drawdown_max),
            "vol_ratio_min": float(args.vol_ratio_min),
            "cap_tickers": list(cap_tickers),
            "excess_destination": str(args.excess_destination),
            "re_evaluate_current_policy": bool(args.re_evaluate_current_policy),
            "cap_beta": float(args.cap_beta),
        },
        "spec": {
            "lookback_days": spec.lookback_days,
            "min_observations": spec.min_observations,
            "shrinkage": spec.shrinkage,
            "grid_step": spec.grid_step,
            "min_cash": spec.min_cash,
            "target_return_fraction": spec.target_return_fraction,
            "variance_penalty": spec.variance_penalty,
        },
        "decision": _decision(windows),
        "windows": windows,
    }


def write_outputs(report: dict[str, Any], *, output: Path, csv_output: Path, latest_output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest_output.parent.mkdir(parents=True, exist_ok=True)
    latest_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = []
    for item in report["windows"]:
        delta = item["delta_vs_baseline"]
        rows.append(
            {
                "label": item["label"],
                "kind": item["kind"],
                "start": item["window"]["start"],
                "end": item["window"]["end"],
                "rows": item["window"]["rows"],
                "confirmation_mode": item["confirmation_mode"],
                "cap_tickers": ",".join(item["cap_tickers"]),
                "excess_destination": item["excess_destination"],
                "re_evaluate_current_policy": item["re_evaluate_current_policy"],
                "cap_beta": item["cap_beta"],
                "confirmation_days": item["confirmation_days"],
                "cap_event_days": item["cap_event_days"],
                "delta_final_value": delta["final_value"],
                "delta_sharpe_ratio": delta["sharpe_ratio"],
                "delta_sortino_ratio": delta["sortino_ratio"],
                "delta_max_drawdown": delta["max_drawdown"],
                "delta_worst_20d_return": delta["worst_20d_return"],
            }
        )
    pd.DataFrame(rows).to_csv(csv_output, index=False, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default="default")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--lookback-days", type=int, default=252)
    parser.add_argument("--min-observations", type=int, default=126)
    parser.add_argument("--shrinkage", type=float, default=0.30)
    parser.add_argument("--grid-step", type=float, default=0.05)
    parser.add_argument("--min-cash", type=float, default=0.20)
    parser.add_argument("--target-return-fraction", type=float, default=0.80)
    parser.add_argument("--variance-penalty", type=float, default=35.0)
    parser.add_argument(
        "--confirmation-mode",
        default="always",
        choices=["always", "total_risk", "tail_only", "tail_or_drawdown", "tail_drawdown_vol"],
    )
    parser.add_argument("--total-risk-min", type=int, default=5)
    parser.add_argument("--tail-risk-min", type=int, default=1)
    parser.add_argument("--drawdown-max", type=float, default=-0.08)
    parser.add_argument("--vol-ratio-min", type=float, default=1.15)
    parser.add_argument("--cap-tickers", default="00631L.TW,00632R.TW")
    parser.add_argument("--excess-destination", default="cash", choices=["cash", "0050.TW"])
    parser.add_argument("--re-evaluate-current-policy", action="store_true")
    parser.add_argument("--cap-beta", type=float, default=1.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--csv-output", default=str(DEFAULT_CSV))
    parser.add_argument("--latest-output", default=str(DEFAULT_LATEST_OUTPUT))
    args = parser.parse_args()

    report = build_report(args)
    write_outputs(report, output=Path(args.output), csv_output=Path(args.csv_output), latest_output=Path(args.latest_output))
    print(f"decision={report['decision']['decision']} promotion_allowed={report['decision']['promotion_allowed']}")
    for item in report["windows"]:
        delta = item["delta_vs_baseline"]
        print(
            f"{item['label']}: cap_days={item['cap_event_days']} "
            f"dFV={delta['final_value']:.2f} dSharpe={delta['sharpe_ratio']:.4f} dMDD={delta['max_drawdown']:.4%}"
        )
    print(f"Output: {Path(args.output).resolve()}")
    print(f"Latest: {Path(args.latest_output).resolve()}")


if __name__ == "__main__":
    main()
