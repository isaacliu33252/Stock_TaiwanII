"""Riccati/mean-variance inspired GroupA+ portfolio risk shadow.

Research-only diagnostic inspired by arXiv:2608.07977.  The paper's full
continuous-time SRE/BSDE solver is intentionally not implemented here: GroupA+
needs a daily, auditable, discrete-share trading workflow.  This module keeps
the transferable part only: state-dependent expected return proxies,
rolling/shrunk cross-asset covariance, and a constrained mean-variance
allocation comparison.

It never changes target weights, execution guards, or orders.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


GROUP_A_PLUS_TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
DEFAULT_MAX_WEIGHTS = {
    "0050.TW": 0.80,
    "00631L.TW": 0.20,
    "00632R.TW": 0.25,
    "00679B.TWO": 0.40,
}


@dataclass(frozen=True)
class MeanVarianceSpec:
    lookback_days: int = 252
    min_observations: int = 126
    shrinkage: float = 0.30
    grid_step: float = 0.025
    min_cash: float = 0.20
    max_weights: dict[str, float] | None = None
    target_return_fraction: float = 0.80
    variance_penalty: float = 35.0


def unwrap_standard_json(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def load_close_panel(db_path: Path, tickers: tuple[str, ...], end: str, *, lookback_calendar_days: int = 520) -> pd.DataFrame:
    end_ts = pd.Timestamp(end)
    start_ts = end_ts - pd.Timedelta(days=lookback_calendar_days)
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ({placeholders})
              AND dt BETWEEN ? AND ?
              AND volume > 0
            ORDER BY dt, ticker
            """,
            [*tickers, str(start_ts.date()), str(end_ts.date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} up to {end}")
    rows["dt"] = pd.to_datetime(rows["dt"])
    panel = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    return panel.dropna(subset=list(tickers))


def _latest_ncf_path(results_dir: Path, ticker: str) -> Path | None:
    stem = ticker.split(".", 1)[0].lower()
    matches = sorted(results_dir.glob(f"ncf_{stem}_latest_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _read_ncf_expected_return(path: Path | None, *, as_of: str) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"status": "missing", "expected_return": None, "source_path": None}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    ensemble = payload.get("horizon_ensemble") if isinstance(payload.get("horizon_ensemble"), dict) else {}
    date = str(payload.get("last_close_date") or "")
    stale_days = None
    if date:
        stale_days = int((pd.Timestamp(as_of) - pd.Timestamp(date)).days)
    return {
        "status": "ok" if stale_days is not None and stale_days <= 3 else "stale",
        "expected_return": ensemble.get("weighted_return"),
        "direction": ensemble.get("direction"),
        "calibrated_probability_up": ensemble.get("calibrated_probability_up"),
        "confidence": ensemble.get("confidence"),
        "last_close_date": date or None,
        "stale_days": stale_days,
        "source_path": str(path),
    }


def build_expected_return_proxy(
    returns: pd.DataFrame,
    *,
    as_of: str,
    results_dir: Path,
    tickers: tuple[str, ...] = GROUP_A_PLUS_TICKERS,
) -> tuple[pd.Series, dict[str, Any]]:
    hist_mu = returns.tail(63).mean().reindex(tickers).fillna(0.0)
    mu = hist_mu.copy()
    sources: dict[str, Any] = {}
    for ticker in tickers:
        ncf = _read_ncf_expected_return(_latest_ncf_path(results_dir, ticker), as_of=as_of)
        sources[ticker] = ncf
        if ncf["status"] == "ok" and ncf["expected_return"] is not None:
            try:
                ncf_mu = float(ncf["expected_return"])
            except (TypeError, ValueError):
                continue
            confidence = max(0.0, min(1.0, float(ncf.get("confidence") or 0.5)))
            blend = 0.25 + 0.50 * confidence
            mu.loc[ticker] = blend * ncf_mu + (1.0 - blend) * float(hist_mu.loc[ticker])
    return mu, {"historical_lookback_days": 63, "ncf_sources": sources}


def shrink_covariance(returns: pd.DataFrame, *, shrinkage: float) -> pd.DataFrame:
    sample = returns.cov().fillna(0.0)
    diagonal = pd.DataFrame(np.diag(np.diag(sample.to_numpy())), index=sample.index, columns=sample.columns)
    alpha = max(0.0, min(1.0, float(shrinkage)))
    return (1.0 - alpha) * sample + alpha * diagonal


def portfolio_stats(weights: dict[str, float], mu: pd.Series, cov: pd.DataFrame) -> dict[str, float]:
    tickers = list(cov.columns)
    w = np.array([float(weights.get(t, 0.0)) for t in tickers], dtype=float)
    mu_vec = mu.reindex(tickers).fillna(0.0).to_numpy(dtype=float)
    cov_mat = cov.reindex(index=tickers, columns=tickers).fillna(0.0).to_numpy(dtype=float)
    expected = float(np.dot(w, mu_vec))
    variance = float(np.dot(w, np.dot(cov_mat, w)))
    daily_vol = math.sqrt(max(variance, 0.0))
    return {
        "expected_daily_return": expected,
        "daily_variance": variance,
        "daily_volatility": daily_vol,
        "annualized_volatility": daily_vol * math.sqrt(252.0),
    }


def realized_volatility_ratio(returns: pd.DataFrame, *, short_window: int = 20, long_window: int = 60) -> float | None:
    anchor = returns.get("00631L.TW")
    if anchor is None or len(anchor.dropna()) < long_window:
        return None
    short_vol = float(anchor.dropna().tail(short_window).std())
    long_vol = float(anchor.dropna().tail(long_window).std())
    if not math.isfinite(short_vol) or not math.isfinite(long_vol) or long_vol <= 0.0:
        return None
    return short_vol / long_vol


def stability_tuned_re_evaluation_gate(
    *,
    latest_features: dict[str, Any],
    realized_vol_ratio_20_60: float | None,
    tail_risk_min: int = 2,
    drawdown_max: float = -0.10,
    vol_ratio_min: float = 1.25,
    cap_beta: float = 0.5,
) -> dict[str, Any]:
    tail_risk = int(float(latest_features.get("tail_risk_score") or 0))
    drawdown = float(latest_features.get("drawdown") or 0.0)
    vol_ratio = float(realized_vol_ratio_20_60) if realized_vol_ratio_20_60 is not None else None
    tail_ok = tail_risk >= tail_risk_min
    drawdown_ok = drawdown <= drawdown_max
    vol_ok = vol_ratio is not None and vol_ratio >= vol_ratio_min
    active = bool(tail_ok and (drawdown_ok or vol_ok))
    reasons = []
    if tail_ok:
        reasons.append("tail_risk_threshold_met")
    if drawdown_ok:
        reasons.append("drawdown_threshold_met")
    if vol_ok:
        reasons.append("volatility_ratio_threshold_met")
    if not active:
        reasons.append("stability_tuned_gate_inactive")
    return {
        "source_paper": {
            "id": "2608.17808",
            "transferable_use": "current_policy_re_evaluation_trigger_stability",
        },
        "policy": "research_only_no_weight_change",
        "gate_active": active,
        "params": {
            "cap_tickers": ["00631L.TW"],
            "tail_risk_min": tail_risk_min,
            "drawdown_max": drawdown_max,
            "vol_ratio_20_60_min": vol_ratio_min,
            "cap_beta": cap_beta,
        },
        "observed": {
            "tail_risk_score": tail_risk,
            "drawdown": drawdown,
            "realized_vol_ratio_20_60": vol_ratio,
        },
        "reasons": reasons,
    }


def low_risk_negative_control(
    *,
    tuned_gate: dict[str, Any],
    latest_features: dict[str, Any],
    realized_vol_ratio_20_60: float | None,
    tail_risk_max: int = 0,
    drawdown_min: float = -0.05,
    vol_ratio_max: float = 1.0,
) -> dict[str, Any]:
    """Check that the cap mechanism stays inactive in benign states."""
    tail_risk = int(float(latest_features.get("tail_risk_score") or 0))
    drawdown = float(latest_features.get("drawdown") or 0.0)
    vol_ratio = float(realized_vol_ratio_20_60) if realized_vol_ratio_20_60 is not None else None
    low_risk_state = bool(
        tail_risk <= tail_risk_max
        and drawdown >= drawdown_min
        and (vol_ratio is None or vol_ratio <= vol_ratio_max)
    )
    gate_active = bool(tuned_gate.get("gate_active"))
    passed = not (low_risk_state and gate_active)
    return {
        "source_paper": {
            "id": "2608.17808",
            "transferable_use": "negative_control_for_policy_re_evaluation",
        },
        "policy": "research_only_no_weight_change",
        "low_risk_state": low_risk_state,
        "gate_active": gate_active,
        "passed": passed,
        "params": {
            "tail_risk_max": tail_risk_max,
            "drawdown_min": drawdown_min,
            "vol_ratio_20_60_max": vol_ratio_max,
        },
        "observed": {
            "tail_risk_score": tail_risk,
            "drawdown": drawdown,
            "realized_vol_ratio_20_60": vol_ratio,
        },
        "verdict": "negative_control_passed" if passed else "negative_control_failed",
        "promotion_decision": "diagnostic_only_blocks_promotion_if_failed",
    }


def damped_cap_weights(
    target_weights: dict[str, float],
    cap_weights: dict[str, float],
    *,
    cap_tickers: tuple[str, ...] = ("00631L.TW",),
    excess_destination: str = "cash",
    cap_beta: float = 0.5,
) -> dict[str, float]:
    cap_beta = max(0.0, min(1.0, float(cap_beta)))
    weights = {ticker: float(target_weights.get(ticker, 0.0) or 0.0) for ticker in (*GROUP_A_PLUS_TICKERS, "cash")}
    for ticker in cap_tickers:
        baseline = float(weights.get(ticker, 0.0) or 0.0)
        cap = min(baseline, float(cap_weights.get(ticker, baseline) or 0.0))
        if cap + 1e-12 < baseline:
            applied = baseline - cap_beta * (baseline - cap)
            moved = baseline - applied
            weights[ticker] = applied
            weights[excess_destination] = float(weights.get(excess_destination, 0.0) or 0.0) + moved
    return weights


def _grid_values(limit: float, step: float) -> list[float]:
    count = int(math.floor((limit + 1e-12) / step))
    return [round(i * step, 10) for i in range(count + 1)]


def constrained_mv_shadow_weights(
    mu: pd.Series,
    cov: pd.DataFrame,
    *,
    baseline_weights: dict[str, float],
    spec: MeanVarianceSpec,
) -> tuple[dict[str, float], dict[str, Any]]:
    max_weights = spec.max_weights or DEFAULT_MAX_WEIGHTS
    tickers = list(GROUP_A_PLUS_TICKERS)
    baseline_stats = portfolio_stats(baseline_weights, mu, cov)
    min_expected = baseline_stats["expected_daily_return"] * spec.target_return_fraction
    mu_vec = mu.reindex(tickers).fillna(0.0).to_numpy(dtype=float)
    cov_mat = cov.reindex(index=tickers, columns=tickers).fillna(0.0).to_numpy(dtype=float)
    best: tuple[float, dict[str, float], dict[str, float]] | None = None
    feasible_count = 0

    grids = [_grid_values(float(max_weights[t]), spec.grid_step) for t in tickers]
    for w0 in grids[0]:
        for w1 in grids[1]:
            if w0 + w1 > 1.0 - spec.min_cash + 1e-12:
                continue
            for w2 in grids[2]:
                if w0 + w1 + w2 > 1.0 - spec.min_cash + 1e-12:
                    continue
                remaining = 1.0 - spec.min_cash - w0 - w1 - w2
                for w3 in _grid_values(min(float(max_weights[tickers[3]]), remaining), spec.grid_step):
                    cash = 1.0 - w0 - w1 - w2 - w3
                    if cash < spec.min_cash - 1e-12:
                        continue
                    w = np.array([w0, w1, w2, w3], dtype=float)
                    expected = float(np.dot(w, mu_vec))
                    if expected < min_expected:
                        continue
                    variance = float(np.dot(w, np.dot(cov_mat, w)))
                    daily_vol = math.sqrt(max(variance, 0.0))
                    weights = {tickers[0]: w0, tickers[1]: w1, tickers[2]: w2, tickers[3]: w3, "cash": cash}
                    feasible_count += 1
                    stats = {
                        "expected_daily_return": expected,
                        "daily_variance": variance,
                        "daily_volatility": daily_vol,
                        "annualized_volatility": daily_vol * math.sqrt(252.0),
                    }
                    score = expected - spec.variance_penalty * variance
                    if best is None or score > best[0]:
                        best = (score, weights, stats)

    if best is None:
        weights = {ticker: 0.0 for ticker in tickers}
        weights["cash"] = 1.0
        return weights, {
            "status": "fallback_all_cash",
            "reason": "no_grid_candidate_met_target_return_and_cash_constraints",
            "feasible_count": 0,
            "baseline_expected_daily_return": baseline_stats["expected_daily_return"],
            "min_expected_daily_return": min_expected,
        }

    return best[1], {
        "status": "ok",
        "feasible_count": feasible_count,
        "objective": "maximize_expected_return_minus_variance_penalty",
        "variance_penalty": spec.variance_penalty,
        "baseline_expected_daily_return": baseline_stats["expected_daily_return"],
        "min_expected_daily_return": min_expected,
        "best_score": best[0],
    }


def cap_only_shadow_weights(
    target_weights: dict[str, float],
    shadow_weights: dict[str, float],
    *,
    cap_tickers: tuple[str, ...] = ("00631L.TW", "00632R.TW"),
    excess_destination: str = "cash",
) -> tuple[dict[str, float], list[dict[str, float]]]:
    if excess_destination not in {*GROUP_A_PLUS_TICKERS, "cash"}:
        raise ValueError(f"unsupported excess destination: {excess_destination}")
    guarded = {ticker: float(target_weights.get(ticker, 0.0) or 0.0) for ticker in (*GROUP_A_PLUS_TICKERS, "cash")}
    events: list[dict[str, float]] = []
    for ticker in cap_tickers:
        baseline = float(guarded.get(ticker, 0.0) or 0.0)
        shadow_cap = float(shadow_weights.get(ticker, 0.0) or 0.0)
        capped = min(baseline, shadow_cap)
        if capped + 1e-12 < baseline:
            moved = baseline - capped
            guarded[ticker] = capped
            guarded[excess_destination] = float(guarded.get(excess_destination, 0.0) or 0.0) + moved
            events.append(
                {
                    "ticker": ticker,
                    "baseline_weight": baseline,
                    "shadow_cap_weight": shadow_cap,
                    "cap_only_weight": capped,
                    "excess_weight_moved": moved,
                }
            )
    return guarded, events


def two_pass_re_evaluation_shadow(
    mu: pd.Series,
    cov: pd.DataFrame,
    *,
    target_weights: dict[str, float],
    spec: MeanVarianceSpec,
) -> dict[str, Any]:
    """Run a second constrained shadow pass from the first cap-only policy.

    This is a lightweight transfer from arXiv:2608.17808.  It does not implement
    the paper's continuous-time adjoint/HJB solver; it audits whether a
    constrained risk-budget recommendation remains stable after applying the
    first pass's cap-only policy as the deployed baseline.
    """
    first_shadow, first_optimizer = constrained_mv_shadow_weights(
        mu,
        cov,
        baseline_weights=target_weights,
        spec=spec,
    )
    first_cap, first_events = cap_only_shadow_weights(target_weights, first_shadow)
    second_shadow, second_optimizer = constrained_mv_shadow_weights(
        mu,
        cov,
        baseline_weights=first_cap,
        spec=spec,
    )
    second_cap, second_events = cap_only_shadow_weights(first_cap, second_shadow)

    first_stats = portfolio_stats(first_cap, mu, cov)
    second_stats = portfolio_stats(second_cap, mu, cov)
    target_stats = portfolio_stats(target_weights, mu, cov)
    cap_delta = {
        ticker: float(second_cap.get(ticker, 0.0)) - float(first_cap.get(ticker, 0.0))
        for ticker in (*GROUP_A_PLUS_TICKERS, "cash")
    }
    stable = all(abs(value) <= spec.grid_step + 1e-12 for value in cap_delta.values())
    persistent_cap_tickers = sorted(
        {
            str(event["ticker"])
            for event in [*first_events, *second_events]
            if event.get("excess_weight_moved", 0.0) > 1e-12
        }
    )
    recommendations: list[str] = []
    if stable and persistent_cap_tickers:
        recommendations.append("persistent_cap_recommendation_after_re_evaluation")
    if second_stats["annualized_volatility"] + 1e-12 < target_stats["annualized_volatility"]:
        recommendations.append("two_pass_cap_only_lowers_annualized_volatility")
    if not recommendations:
        recommendations.append("no_stable_two_pass_action")

    return {
        "source_paper": {
            "id": "2608.17808",
            "title": "Self-Consistent Adjoint Policy Iteration for Constrained Dynamic Portfolio Choice",
            "transferable_use": "current_policy_re_evaluation_stability_audit",
        },
        "policy": "research_only_no_weight_change",
        "implementation_note": (
            "Discrete two-pass cap-only stability audit; not the paper's full "
            "continuous-time OL-BPTT/HJB policy iteration."
        ),
        "first_pass": {
            "shadow_weights": first_shadow,
            "cap_only_weights": first_cap,
            "cap_only_events": first_events,
            "cap_only_stats": first_stats,
            "optimizer": first_optimizer,
        },
        "second_pass": {
            "shadow_weights": second_shadow,
            "cap_only_weights": second_cap,
            "cap_only_events": second_events,
            "cap_only_stats": second_stats,
            "optimizer": second_optimizer,
        },
        "cap_delta_second_minus_first": cap_delta,
        "stable_within_grid_step": stable,
        "persistent_cap_tickers": persistent_cap_tickers,
        "recommendations": recommendations,
        "promotion_decision": "shadow_only_requires_multi_window_backtest_before_guard_use",
    }


def active_set_stability_audit(
    mu: pd.Series,
    cov: pd.DataFrame,
    *,
    target_weights: dict[str, float],
    spec: MeanVarianceSpec,
    cap_tickers: tuple[str, ...] = ("00631L.TW",),
    mu_perturbation: float = 0.0005,
    cov_scale_delta: float = 0.10,
) -> dict[str, Any]:
    """Audit whether constrained cap recommendations survive small input shocks."""
    base_shadow, base_optimizer = constrained_mv_shadow_weights(mu, cov, baseline_weights=target_weights, spec=spec)
    base_flags = {
        ticker: float(base_shadow.get(ticker, 0.0)) + 1e-12 < float(target_weights.get(ticker, 0.0) or 0.0)
        for ticker in cap_tickers
    }
    scenarios: list[dict[str, Any]] = []

    def add_scenario(name: str, scenario_mu: pd.Series, scenario_cov: pd.DataFrame) -> None:
        shadow, optimizer = constrained_mv_shadow_weights(scenario_mu, scenario_cov, baseline_weights=target_weights, spec=spec)
        flags = {
            ticker: float(shadow.get(ticker, 0.0)) + 1e-12 < float(target_weights.get(ticker, 0.0) or 0.0)
            for ticker in cap_tickers
        }
        scenarios.append(
            {
                "name": name,
                "optimizer_status": optimizer.get("status"),
                "cap_flags": flags,
                "shadow_weights": shadow,
                "matches_base_active_set": flags == base_flags,
            }
        )

    for ticker in cap_tickers:
        bumped = mu.copy()
        bumped.loc[ticker] = float(bumped.get(ticker, 0.0)) + mu_perturbation
        add_scenario(f"{ticker}_mu_plus", bumped, cov)
        bumped = mu.copy()
        bumped.loc[ticker] = float(bumped.get(ticker, 0.0)) - mu_perturbation
        add_scenario(f"{ticker}_mu_minus", bumped, cov)
    add_scenario("covariance_scale_up", mu, cov * (1.0 + cov_scale_delta))
    add_scenario("covariance_scale_down", mu, cov * max(0.0, 1.0 - cov_scale_delta))

    matches = sum(1 for scenario in scenarios if scenario["matches_base_active_set"])
    scenario_count = len(scenarios)
    stability_ratio = matches / scenario_count if scenario_count else None
    verdict = (
        "stable_active_set"
        if stability_ratio is not None and stability_ratio >= 0.80
        else "unstable_active_set_do_not_promote"
    )
    return {
        "source_paper": {
            "id": "2608.17808",
            "transferable_use": "active_set_boundary_stability_audit",
        },
        "policy": "research_only_no_weight_change",
        "base_optimizer_status": base_optimizer.get("status"),
        "base_cap_flags": base_flags,
        "base_shadow_weights": base_shadow,
        "perturbation": {
            "mu_perturbation": mu_perturbation,
            "cov_scale_delta": cov_scale_delta,
        },
        "stability_ratio": stability_ratio,
        "scenario_count": scenario_count,
        "matching_scenarios": matches,
        "verdict": verdict,
        "scenarios": scenarios,
        "promotion_decision": "diagnostic_only_requires_walk_forward_confirmation",
    }


def matched_budget_re_evaluation_comparator(
    mu: pd.Series,
    cov: pd.DataFrame,
    *,
    target_weights: dict[str, float],
    spec: MeanVarianceSpec,
    re_evaluation_shadow: dict[str, Any],
    cap_tickers: tuple[str, ...] = ("00631L.TW",),
    mu_perturbation: float = 0.0005,
    cov_scale_delta: float = 0.10,
) -> dict[str, Any]:
    """Compare current-policy re-evaluation to same-budget frozen-policy refinement."""
    second_cap = re_evaluation_shadow.get("second_pass", {}).get("cap_only_weights", {})
    current_flags = {
        ticker: float(second_cap.get(ticker, 0.0)) + 1e-12 < float(target_weights.get(ticker, 0.0) or 0.0)
        for ticker in cap_tickers
    }
    scenarios: list[tuple[str, pd.Series, pd.DataFrame]] = []
    for ticker in cap_tickers:
        bumped = mu.copy()
        bumped.loc[ticker] = float(bumped.get(ticker, 0.0)) + mu_perturbation
        scenarios.append((f"{ticker}_mu_plus_frozen", bumped, cov))
        bumped = mu.copy()
        bumped.loc[ticker] = float(bumped.get(ticker, 0.0)) - mu_perturbation
        scenarios.append((f"{ticker}_mu_minus_frozen", bumped, cov))
    scenarios.append(("covariance_scale_up_frozen", mu, cov * (1.0 + cov_scale_delta)))
    scenarios.append(("covariance_scale_down_frozen", mu, cov * max(0.0, 1.0 - cov_scale_delta)))

    frozen_results: list[dict[str, Any]] = []
    frozen_votes = {ticker: 0 for ticker in cap_tickers}
    for name, scenario_mu, scenario_cov in scenarios:
        shadow, optimizer = constrained_mv_shadow_weights(scenario_mu, scenario_cov, baseline_weights=target_weights, spec=spec)
        cap_weights, events = cap_only_shadow_weights(target_weights, shadow, cap_tickers=cap_tickers)
        flags = {
            ticker: float(cap_weights.get(ticker, 0.0)) + 1e-12 < float(target_weights.get(ticker, 0.0) or 0.0)
            for ticker in cap_tickers
        }
        for ticker, active in flags.items():
            frozen_votes[ticker] += int(active)
        frozen_results.append(
            {
                "name": name,
                "optimizer_status": optimizer.get("status"),
                "cap_flags": flags,
                "cap_only_weights": cap_weights,
                "cap_events": events,
            }
        )

    denominator = len(frozen_results) or 1
    frozen_consensus = {ticker: frozen_votes[ticker] / denominator >= 0.75 for ticker in cap_tickers}
    agrees = frozen_consensus == current_flags
    verdict = "current_policy_re_evaluation_supported" if agrees else "current_policy_re_evaluation_not_supported"
    return {
        "source_paper": {
            "id": "2608.17808",
            "transferable_use": "matched_budget_re_evaluation_comparator",
        },
        "policy": "research_only_no_weight_change",
        "current_policy_cap_flags": current_flags,
        "frozen_policy_consensus_flags": frozen_consensus,
        "frozen_policy_vote_fraction": {ticker: frozen_votes[ticker] / denominator for ticker in cap_tickers},
        "agrees_with_frozen_budget": agrees,
        "verdict": verdict,
        "frozen_policy_scenarios": frozen_results,
        "promotion_decision": "diagnostic_only_not_a_trade_signal",
    }


def error_decomposition_snapshot(
    *,
    target_weights: dict[str, float],
    shadow_weights: dict[str, float],
    optimizer: dict[str, Any],
    expected_return_sources: dict[str, Any],
    cov: pd.DataFrame,
    active_set_stability: dict[str, Any],
    matched_budget: dict[str, Any],
    tuned_gate: dict[str, Any],
    cap_only_vol_reduction: float,
) -> dict[str, Any]:
    """Summarize why a shadow recommendation should or should not be trusted."""
    ncf_sources = expected_return_sources.get("ncf_sources") if isinstance(expected_return_sources, dict) else {}
    stale_or_missing = [
        ticker
        for ticker, source in ncf_sources.items()
        if not isinstance(source, dict) or source.get("status") != "ok"
    ]
    corr_631_632 = None
    if {"00631L.TW", "00632R.TW"}.issubset(set(cov.index)) and {"00631L.TW", "00632R.TW"}.issubset(set(cov.columns)):
        var_631 = float(cov.loc["00631L.TW", "00631L.TW"])
        var_632 = float(cov.loc["00632R.TW", "00632R.TW"])
        if var_631 > 0.0 and var_632 > 0.0:
            corr_631_632 = float(cov.loc["00631L.TW", "00632R.TW"]) / math.sqrt(var_631 * var_632)
    raw_delta_631 = float(shadow_weights.get("00631L.TW", 0.0)) - float(target_weights.get("00631L.TW", 0.0))
    near_constraint = abs(raw_delta_631) <= 2.0 * float(optimizer.get("grid_step", 0.025) or 0.025)
    blockers: list[str] = []
    if stale_or_missing:
        blockers.append("expected_return_source_stale_or_missing")
    if not bool(active_set_stability.get("verdict") == "stable_active_set"):
        blockers.append("active_set_unstable")
    if not bool(matched_budget.get("agrees_with_frozen_budget")):
        blockers.append("matched_budget_disagreement")
    if not bool(tuned_gate.get("gate_active")):
        blockers.append("stability_tuned_gate_inactive")
    if cap_only_vol_reduction <= 0.0:
        blockers.append("cap_only_does_not_reduce_volatility")
    verdict = "diagnostic_supported_but_not_actionable" if blockers == ["stability_tuned_gate_inactive"] else "diagnostic_blocked"
    return {
        "source_paper": {
            "id": "2608.17808",
            "transferable_use": "decomposed_error_certificate",
        },
        "policy": "research_only_no_weight_change",
        "components": {
            "mu_error": {
                "status": "review" if stale_or_missing else "ok",
                "stale_or_missing_ncf_sources": stale_or_missing,
            },
            "cov_error": {
                "status": "review" if corr_631_632 is not None and abs(corr_631_632) > 0.98 else "ok",
                "00631l_00632r_covariance_correlation": corr_631_632,
            },
            "constraint_error": {
                "status": "review" if near_constraint else "ok",
                "00631l_shadow_minus_target": raw_delta_631,
                "near_grid_boundary": near_constraint,
            },
            "re_evaluation_error": {
                "active_set_verdict": active_set_stability.get("verdict"),
                "matched_budget_verdict": matched_budget.get("verdict"),
            },
            "execution_error": {
                "status": "blocked" if not tuned_gate.get("gate_active") else "review",
                "stability_tuned_gate_active": tuned_gate.get("gate_active"),
                "cap_only_annualized_volatility_reduction": cap_only_vol_reduction,
            },
        },
        "blockers": blockers,
        "verdict": verdict,
        "promotion_decision": "diagnostic_only_do_not_trade_from_this_snapshot",
    }


def build_riccati_mv_shadow_report(
    *,
    db_path: Path,
    as_of: str,
    execution_plan: dict[str, Any],
    results_dir: Path,
    spec: MeanVarianceSpec | None = None,
) -> dict[str, Any]:
    spec = spec or MeanVarianceSpec()
    plan = unwrap_standard_json(execution_plan)
    target_weights = plan.get("target_weights") if isinstance(plan.get("target_weights"), dict) else {}
    if not target_weights:
        raise ValueError("execution plan has no target_weights")

    panel = load_close_panel(db_path, GROUP_A_PLUS_TICKERS, as_of)
    returns = panel.pct_change().dropna().tail(spec.lookback_days)
    if len(returns) < spec.min_observations:
        raise RuntimeError(f"not enough return observations: {len(returns)} < {spec.min_observations}")
    mu, mu_sources = build_expected_return_proxy(returns, as_of=as_of, results_dir=results_dir)
    cov = shrink_covariance(returns.reindex(columns=list(GROUP_A_PLUS_TICKERS)), shrinkage=spec.shrinkage)

    latest_stats = portfolio_stats(target_weights, mu, cov)
    shadow_weights, optimizer = constrained_mv_shadow_weights(mu, cov, baseline_weights=target_weights, spec=spec)
    shadow_stats = portfolio_stats(shadow_weights, mu, cov)
    cap_only_weights, cap_only_events = cap_only_shadow_weights(target_weights, shadow_weights)
    cap_only_stats = portfolio_stats(cap_only_weights, mu, cov)
    re_evaluation_shadow = two_pass_re_evaluation_shadow(mu, cov, target_weights=target_weights, spec=spec)
    latest_features = plan.get("latest_features") if isinstance(plan.get("latest_features"), dict) else {}
    vol_ratio_20_60 = realized_volatility_ratio(returns)
    tuned_gate = stability_tuned_re_evaluation_gate(
        latest_features=latest_features,
        realized_vol_ratio_20_60=vol_ratio_20_60,
    )
    negative_control = low_risk_negative_control(
        tuned_gate=tuned_gate,
        latest_features=latest_features,
        realized_vol_ratio_20_60=vol_ratio_20_60,
    )
    tuned_weights = (
        damped_cap_weights(
            target_weights,
            re_evaluation_shadow["second_pass"]["cap_only_weights"],
            cap_beta=float(tuned_gate["params"]["cap_beta"]),
        )
        if tuned_gate["gate_active"]
        else target_weights
    )
    active_set_stability = active_set_stability_audit(mu, cov, target_weights=target_weights, spec=spec)
    matched_budget = matched_budget_re_evaluation_comparator(
        mu,
        cov,
        target_weights=target_weights,
        spec=spec,
        re_evaluation_shadow=re_evaluation_shadow,
    )

    latest_vol = latest_stats["annualized_volatility"]
    shadow_vol = shadow_stats["annualized_volatility"]
    cap_only_vol = cap_only_stats["annualized_volatility"]
    vol_reduction = latest_vol - shadow_vol
    cap_only_vol_reduction = latest_vol - cap_only_vol
    latest_631 = float(target_weights.get("00631L.TW", 0.0))
    shadow_631 = float(shadow_weights.get("00631L.TW", 0.0))
    latest_632 = float(target_weights.get("00632R.TW", 0.0))
    shadow_632 = float(shadow_weights.get("00632R.TW", 0.0))

    recommendations: list[str] = []
    if shadow_631 + 1e-12 < latest_631:
        recommendations.append("review_00631l_add_or_cap")
    if shadow_632 + 1e-12 < latest_632:
        recommendations.append("review_00632r_hedge_size")
    if vol_reduction > 0.02:
        recommendations.append("shadow_allocation_has_materially_lower_annualized_volatility")
    if not recommendations:
        recommendations.append("no_action_shadow_only")
    cap_only_recommendations = [
        f"cap_{event['ticker'].lower().replace('.', '_')}_to_shadow_budget"
        for event in cap_only_events
    ]
    if cap_only_vol_reduction > 0.02:
        cap_only_recommendations.append("cap_only_has_materially_lower_annualized_volatility")
    if not cap_only_recommendations:
        cap_only_recommendations.append("no_action_cap_only")

    corr = returns.corr().reindex(index=GROUP_A_PLUS_TICKERS, columns=GROUP_A_PLUS_TICKERS)
    error_decomposition = error_decomposition_snapshot(
        target_weights=target_weights,
        shadow_weights=shadow_weights,
        optimizer={**optimizer, "grid_step": spec.grid_step},
        expected_return_sources=mu_sources,
        cov=cov,
        active_set_stability=active_set_stability,
        matched_budget=matched_budget,
        tuned_gate=tuned_gate,
        cap_only_vol_reduction=cap_only_vol_reduction,
    )
    return {
        "report_type": "riccati_mv_shadow",
        "status": "ok",
        "policy": "research_only_no_weight_change",
        "source_paper": {
            "id": "2608.07977",
            "title": "A Computable Stochastic Riccati Equations Framework for Mean-Variance Portfolio Selection with Multifactor Stochastic Volatility Model",
            "transferable_use": "state_dependent_mean_variance_risk_budget_shadow",
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "price_window": {
            "start": str(returns.index.min().date()),
            "end": str(returns.index.max().date()),
            "observations": int(len(returns)),
        },
        "spec": {
            "lookback_days": spec.lookback_days,
            "min_observations": spec.min_observations,
            "shrinkage": spec.shrinkage,
            "grid_step": spec.grid_step,
            "min_cash": spec.min_cash,
            "max_weights": spec.max_weights or DEFAULT_MAX_WEIGHTS,
            "target_return_fraction": spec.target_return_fraction,
            "variance_penalty": spec.variance_penalty,
        },
        "expected_return_proxy": {
            "daily_by_ticker": {k: float(v) for k, v in mu.items()},
            **mu_sources,
        },
        "risk_state": {
            "latest_target_stats": latest_stats,
            "shadow_target_stats": shadow_stats,
            "cap_only_shadow_stats": cap_only_stats,
            "annualized_volatility_reduction": vol_reduction,
            "cap_only_annualized_volatility_reduction": cap_only_vol_reduction,
            "correlation_matrix": {
                idx: {col: float(corr.loc[idx, col]) for col in corr.columns if pd.notna(corr.loc[idx, col])}
                for idx in corr.index
            },
        },
        "latest_strategy_weights": {str(k): float(v) for k, v in target_weights.items()},
        "shadow_mean_variance_weights": shadow_weights,
        "cap_only_shadow_weights": cap_only_weights,
        "cap_only_events": cap_only_events,
        "adjoint_policy_iteration_shadow": re_evaluation_shadow,
        "two_pass_cap_only_weights": re_evaluation_shadow["second_pass"]["cap_only_weights"],
        "two_pass_recommendations": re_evaluation_shadow["recommendations"],
        "stability_tuned_re_evaluation_gate": tuned_gate,
        "stability_tuned_two_pass_weights": tuned_weights,
        "stability_tuned_recommendations": (
            re_evaluation_shadow["recommendations"] if tuned_gate["gate_active"] else ["no_action_stability_gate_inactive"]
        ),
        "negative_control": negative_control,
        "active_set_stability": active_set_stability,
        "matched_budget_re_evaluation_comparator": matched_budget,
        "error_decomposition": error_decomposition,
        "weight_delta_shadow_minus_latest": {
            ticker: float(shadow_weights.get(ticker, 0.0)) - float(target_weights.get(ticker, 0.0))
            for ticker in (*GROUP_A_PLUS_TICKERS, "cash")
        },
        "weight_delta_cap_only_minus_latest": {
            ticker: float(cap_only_weights.get(ticker, 0.0)) - float(target_weights.get(ticker, 0.0))
            for ticker in (*GROUP_A_PLUS_TICKERS, "cash")
        },
        "optimizer": optimizer,
        "recommendations": recommendations,
        "cap_only_recommendations": cap_only_recommendations,
        "promotion_decision": "shadow_only_needs_backtest_before_any_guard_or_strategy_change",
        "paper_limitations_for_group_a_plus": [
            "paper_backtest_uses_us_sector_etfs_not_taiwan_leveraged_inverse_etfs",
            "continuous_time_no_transaction_cost_assumption_does_not_match_live_execution",
            "expected_return_estimation_error_can_dominate_mean_variance_optimization",
            "full_deep_bsde_solver_is_too_heavy_for_daily_production_without_separate_validation",
        ],
    }
