#!/usr/bin/env python3
"""Review arXiv 2609.02014 for a GroupA++ 00679B spectral hedge shadow.

Research-only. This script does not change live weights, strategy manifests,
or order generation. It tests whether funding a 00679B.TWO hedge sleeve from
cash improves tail-sensitive outcomes versus the current GroupA++ policy.
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

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.runners.a2118 import run_a2118

DEFAULT_MANIFEST = PROJECT_ROOT / "report/group_a_plus/latest/strategy.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_02014_spectral_00679b_hedge_review.json"
DEFAULT_MD_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2609_02014_spectral_00679b_hedge_review.md"
TICKER = "00679B.TWO"
SPECTRAL_PROFILES = {
    # Main profile used for promotion checks: balanced tail sensitivity.
    "moderate_tail_sensitive": ((0.50, 0.95), (0.30, 0.975), (0.20, 0.99)),
    # Log/power-like: puts more weight on the deepest observed losses.
    "deep_tail_sensitive": ((0.20, 0.95), (0.30, 0.975), (0.50, 0.99)),
    # Saturating-like: still tail-aware but less dominated by rare 99% samples.
    "extreme_tail_saturating": ((0.70, 0.95), (0.25, 0.975), (0.05, 0.99)),
}
WINDOWS = [
    ("2020_covid", "2020-01-02", "2020-06-30"),
    ("2022_rate_hike", "2022-01-03", "2022-10-31"),
    ("2024_2026_live", "2024-01-02", "2026-09-04"),
    ("2025_2026_live", "2025-01-02", "2026-09-04"),
]


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("active_strategy", {}).get("runner_params", {})


def _load_returns(db_path: Path, ticker: str, start: str, end: str, warmup_days: int = 5) -> pd.Series:
    start_ts = pd.Timestamp(start) - pd.Timedelta(days=warmup_days)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, close
            FROM ohlcv
            WHERE ticker = ?
              AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, str(start_ts.date()), end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {ticker} from {start_ts.date()} to {end}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    close = rows.set_index("dt")["close"].astype(float).sort_index().ffill()
    return close.pct_change().rename(f"{ticker}_return")


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _expected_shortfall_loss(returns: pd.Series, confidence: float) -> float | None:
    losses = -pd.to_numeric(returns, errors="coerce").dropna().to_numpy(dtype=float)
    losses = losses[np.isfinite(losses)]
    if len(losses) == 0:
        return None
    var = float(np.quantile(losses, confidence))
    tail = losses[losses >= var]
    return float(tail.mean()) if len(tail) else var


def _spectral_loss(
    returns: pd.Series,
    profile: tuple[tuple[float, float], ...] = SPECTRAL_PROFILES["moderate_tail_sensitive"],
) -> float | None:
    """Discrete spectral loss: heavier weight on deeper loss tails."""
    components = [(weight, _expected_shortfall_loss(returns, confidence)) for weight, confidence in profile]
    if any(value is None for _, value in components):
        return None
    return float(sum(weight * float(value) for weight, value in components))


def _max_drawdown(returns: pd.Series) -> float | None:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return None
    wealth = (1.0 + clean).cumprod()
    return float((wealth / wealth.cummax() - 1.0).min())


def _final_value_per_1m(returns: pd.Series) -> float | None:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return None
    return float(1_000_000.0 * (1.0 + clean).prod())


def _metrics(returns: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return {}
    wealth = (1.0 + clean).cumprod()
    years = len(clean) / 252.0
    ann_return = float(wealth.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 else None
    ann_vol = float(clean.std(ddof=1) * np.sqrt(252.0)) if len(clean) > 1 else None
    downside = clean[clean < 0.0]
    ann_downside = float(downside.std(ddof=1) * np.sqrt(252.0)) if len(downside) > 1 else None
    es95 = _expected_shortfall_loss(clean, 0.95)
    es99 = _expected_shortfall_loss(clean, 0.99)
    spectral_by_profile = {
        name: _spectral_loss(clean, profile)
        for name, profile in SPECTRAL_PROFILES.items()
    }
    spectral = spectral_by_profile["moderate_tail_sensitive"]
    rolling_5d = clean.rolling(5).sum().dropna()
    rolling_20d = clean.rolling(20).sum().dropna()
    return {
        "rows": int(len(clean)),
        "cumulative_return": float(wealth.iloc[-1] - 1.0),
        "final_value_per_1m": float(1_000_000.0 * wealth.iloc[-1]),
        "annualized_return": ann_return,
        "annualized_volatility": ann_vol,
        "sharpe_ratio": None if not ann_vol else float((ann_return or 0.0) / ann_vol),
        "sortino_ratio": None if not ann_downside else float((ann_return or 0.0) / ann_downside),
        "max_drawdown": _max_drawdown(clean),
        "expected_shortfall_loss_95": es95,
        "expected_shortfall_loss_99": es99,
        "spectral_loss_95_975_99": spectral,
        "spectral_loss_profiles": spectral_by_profile,
        "spectral_starr": None if not spectral else float((ann_return or 0.0) / spectral),
        "rolling_5d_expected_shortfall_loss_95": _expected_shortfall_loss(rolling_5d, 0.95),
        "rolling_5d_spectral_loss": _spectral_loss(rolling_5d),
        "rolling_20d_expected_shortfall_loss_95": _expected_shortfall_loss(rolling_20d, 0.95),
        "rolling_20d_spectral_loss": _spectral_loss(rolling_20d),
        "worst_5d_return": float(rolling_5d.min()) if len(rolling_5d) else None,
        "worst_20d_return": float(rolling_20d.min()) if len(rolling_20d) else None,
    }


def _paired_block_bootstrap(
    base_returns: pd.Series,
    candidate_returns: pd.Series,
    *,
    iterations: int,
    block_size: int,
    seed: int,
) -> dict[str, Any]:
    aligned = pd.concat([base_returns.rename("base"), candidate_returns.rename("candidate")], axis=1).dropna()
    if len(aligned) < max(40, block_size * 3):
        return {"status": "insufficient_rows", "rows": int(len(aligned))}
    rng = np.random.default_rng(seed)
    base_arr = aligned["base"].to_numpy(dtype=float)
    candidate_arr = aligned["candidate"].to_numpy(dtype=float)
    n = len(aligned)
    spectral_deltas: list[float] = []
    final_deltas: list[float] = []
    mdd_deltas: list[float] = []
    for _ in range(iterations):
        starts = rng.integers(0, n, size=int(np.ceil(n / block_size)))
        idx = np.concatenate([(np.arange(start, start + block_size) % n) for start in starts])[:n]
        sample_base = pd.Series(base_arr[idx])
        sample_candidate = pd.Series(candidate_arr[idx])
        base_spectral = _spectral_loss(sample_base)
        candidate_spectral = _spectral_loss(sample_candidate)
        base_final = _final_value_per_1m(sample_base)
        candidate_final = _final_value_per_1m(sample_candidate)
        base_mdd = _max_drawdown(sample_base)
        candidate_mdd = _max_drawdown(sample_candidate)
        if base_spectral is not None and candidate_spectral is not None:
            spectral_deltas.append(float(candidate_spectral - base_spectral))
        if base_final is not None and candidate_final is not None:
            final_deltas.append(float(candidate_final - base_final))
        if base_mdd is not None and candidate_mdd is not None:
            mdd_deltas.append(float(candidate_mdd - base_mdd))

    def summarize(values: list[float], improve_predicate: str) -> dict[str, Any]:
        arr = np.asarray(values, dtype=float)
        if len(arr) == 0:
            return {"status": "unavailable"}
        if improve_predicate == "negative":
            p_improve = float(np.mean(arr < 0.0))
        else:
            p_improve = float(np.mean(arr > 0.0))
        return {
            "mean": float(np.mean(arr)),
            "p05": float(np.quantile(arr, 0.05)),
            "p50": float(np.quantile(arr, 0.50)),
            "p95": float(np.quantile(arr, 0.95)),
            "p_improve": p_improve,
        }

    return {
        "status": "ok",
        "rows": int(n),
        "iterations": int(iterations),
        "block_size": int(block_size),
        "seed": int(seed),
        "spectral_loss_delta": summarize(spectral_deltas, "negative"),
        "final_value_delta": summarize(final_deltas, "positive"),
        "max_drawdown_delta": summarize(mdd_deltas, "positive"),
    }


def _stress_path_scenarios(base_returns: pd.Series, bond_returns: pd.Series) -> dict[str, pd.Series]:
    """Deterministic stress paths inspired by initial-state perturbation tests."""
    aligned = pd.concat([base_returns.rename("base"), bond_returns.rename("bond")], axis=1).fillna(0.0)
    base = aligned["base"]
    bond = aligned["bond"]
    down_mask = base < 0.0
    shock_mask = base <= base.quantile(0.10)
    scenarios = {
        "historical": bond,
        # Favorable hedge world: bonds rally mildly when the base portfolio is hit.
        "negative_corr_hedge": bond.where(~down_mask, bond + (-0.25 * base.clip(upper=0.0))),
        # 2022-like world: long-duration bonds fall together with equity-risk assets.
        "stock_bond_down": bond.where(~shock_mask, bond + (0.50 * base.clip(upper=0.0))),
        # Carry-drag world: small daily bond drag while the base path is unchanged.
        "carry_drag": bond - 0.00015,
    }
    return {name: series.rename(name) for name, series in scenarios.items()}


def _stress_path_check(
    base_returns: pd.Series,
    bond_returns: pd.Series,
    cash_capacity: pd.Series,
    sleeve: pd.Series,
    *,
    cost_bps: float,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    base_metrics = _metrics(base_returns)
    for name, stressed_bond in _stress_path_scenarios(base_returns, bond_returns).items():
        stressed = _apply_cash_funded_bond_sleeve(
            base_returns,
            stressed_bond,
            cash_capacity,
            sleeve,
            cost_bps=cost_bps,
        )
        metrics = _metrics(stressed)
        out[name] = {
            "metrics": metrics,
            "delta_vs_base": {
                "final_value_per_1m": None
                if metrics.get("final_value_per_1m") is None
                else float(metrics["final_value_per_1m"] - base_metrics["final_value_per_1m"]),
                "max_drawdown": None
                if metrics.get("max_drawdown") is None
                else float(metrics["max_drawdown"] - base_metrics["max_drawdown"]),
                "spectral_loss_95_975_99": None
                if metrics.get("spectral_loss_95_975_99") is None
                else float(metrics["spectral_loss_95_975_99"] - base_metrics["spectral_loss_95_975_99"]),
                "rolling_20d_spectral_loss": None
                if metrics.get("rolling_20d_spectral_loss") is None
                else float(metrics["rolling_20d_spectral_loss"] - base_metrics["rolling_20d_spectral_loss"]),
            },
        }
    return out


def _cost_sensitivity_check(
    base_returns: pd.Series,
    bond_returns: pd.Series,
    cash_capacity: pd.Series,
    sleeve: pd.Series,
    *,
    cost_bps_values: tuple[float, ...],
) -> dict[str, Any]:
    base_metrics = _metrics(base_returns)
    out: dict[str, Any] = {}
    for cost_bps in cost_bps_values:
        simulated = _apply_cash_funded_bond_sleeve(
            base_returns,
            bond_returns,
            cash_capacity,
            sleeve,
            cost_bps=cost_bps,
        )
        metrics = _metrics(simulated)
        out[str(cost_bps)] = {
            "metrics": metrics,
            "delta_vs_base": {
                "final_value_per_1m": None
                if metrics.get("final_value_per_1m") is None
                else float(metrics["final_value_per_1m"] - base_metrics["final_value_per_1m"]),
                "max_drawdown": None
                if metrics.get("max_drawdown") is None
                else float(metrics["max_drawdown"] - base_metrics["max_drawdown"]),
                "spectral_loss_95_975_99": None
                if metrics.get("spectral_loss_95_975_99") is None
                else float(metrics["spectral_loss_95_975_99"] - base_metrics["spectral_loss_95_975_99"]),
            },
        }
    return out


def _cash_capacity(frame: pd.DataFrame, report: dict[str, Any]) -> pd.Series:
    weights_by_regime = report.get("base_weights") or {}
    out = pd.Series(0.0, index=frame.index, dtype=float)
    for dt, regime in frame["execution_regime"].items():
        raw = weights_by_regime.get(str(regime), {}) or {}
        out.loc[dt] = max(float(raw.get("cash", 0.0) or 0.0), 0.0)
    return out


def _apply_cash_funded_bond_sleeve(
    base_returns: pd.Series,
    bond_returns: pd.Series,
    cash_capacity: pd.Series,
    sleeve: pd.Series,
    *,
    cost_bps: float,
) -> pd.Series:
    aligned = pd.concat(
        [
            base_returns.rename("base"),
            bond_returns.rename("bond"),
            cash_capacity.rename("cash_capacity"),
            sleeve.rename("sleeve"),
        ],
        axis=1,
    ).dropna(subset=["base"])
    aligned["bond"] = aligned["bond"].fillna(0.0)
    aligned["sleeve"] = aligned["sleeve"].clip(lower=0.0)
    aligned["effective_sleeve"] = np.minimum(aligned["sleeve"], aligned["cash_capacity"].clip(lower=0.0))
    lagged = aligned["effective_sleeve"].shift(1).fillna(aligned["effective_sleeve"].iloc[0])
    turnover = aligned["effective_sleeve"].diff().abs().fillna(aligned["effective_sleeve"].iloc[0])
    return aligned["base"] + lagged * aligned["bond"] - turnover * (cost_bps / 10000.0)


def _rolling_spectral_sleeve(
    base_returns: pd.Series,
    bond_returns: pd.Series,
    cash_capacity: pd.Series,
    *,
    candidates: tuple[float, ...],
    lookback: int,
    min_lookback: int,
    rebalance_every: int,
    cost_bps: float,
) -> pd.Series:
    index = base_returns.index
    selected = pd.Series(0.0, index=index, dtype=float)
    current = 0.0
    for i, dt in enumerate(index):
        if i >= min_lookback and (i - min_lookback) % rebalance_every == 0:
            history_base = base_returns.iloc[max(0, i - lookback):i]
            history_bond = bond_returns.reindex(history_base.index).fillna(0.0)
            history_cash = cash_capacity.reindex(history_base.index).fillna(0.0)
            scores: list[tuple[float, float, float]] = []
            for candidate in candidates:
                hist_sleeve = pd.Series(candidate, index=history_base.index)
                simulated = _apply_cash_funded_bond_sleeve(
                    history_base,
                    history_bond,
                    history_cash,
                    hist_sleeve,
                    cost_bps=cost_bps,
                )
                spectral = _spectral_loss(simulated)
                mean_return = float(simulated.mean()) if len(simulated) else -np.inf
                scores.append((float(spectral if spectral is not None else np.inf), -mean_return, candidate))
            current = min(scores)[2]
        selected.loc[dt] = current
    return selected


def _conditional_corr_sleeve(
    base_returns: pd.Series,
    bond_returns: pd.Series,
    *,
    target_weight: float,
    corr_window: int,
    corr_max: float,
    bond_momentum_window: int,
    bond_momentum_min: float,
) -> pd.Series:
    """Causal hedge-availability filter for 00679B.

    The sleeve is active only after 00679B has recently behaved like a hedge
    and is not itself in a negative trend. Signals are shifted one day to avoid
    using today's close in today's allocation.
    """
    aligned = pd.concat([base_returns.rename("base"), bond_returns.rename("bond")], axis=1).fillna(0.0)
    corr = aligned["base"].rolling(corr_window, min_periods=max(20, corr_window // 2)).corr(aligned["bond"])
    bond_momentum = (1.0 + aligned["bond"]).rolling(
        bond_momentum_window,
        min_periods=max(20, bond_momentum_window // 2),
    ).apply(np.prod, raw=True) - 1.0
    active = ((corr <= corr_max) & (bond_momentum >= bond_momentum_min)).astype(bool)
    active = active.shift(1, fill_value=False).astype(bool)
    return pd.Series(np.where(active, target_weight, 0.0), index=base_returns.index, dtype=float)


def _hedge_readiness_state(
    base_returns: pd.Series,
    bond_returns: pd.Series,
    cash_capacity: pd.Series,
    sleeve: pd.Series,
) -> pd.DataFrame:
    """Daily 00679B hedge-state diagnostics, shifted to be live-usable."""
    aligned = pd.concat(
        [
            base_returns.rename("base"),
            bond_returns.rename("bond"),
            cash_capacity.rename("cash_capacity"),
            sleeve.rename("sleeve"),
        ],
        axis=1,
    ).fillna(0.0)
    base_wealth = (1.0 + aligned["base"]).cumprod()
    bond_wealth = (1.0 + aligned["bond"]).cumprod()
    state = pd.DataFrame(index=aligned.index)
    state["corr_63"] = aligned["base"].rolling(63, min_periods=32).corr(aligned["bond"])
    state["corr_126"] = aligned["base"].rolling(126, min_periods=63).corr(aligned["bond"])
    state["bond_return_63"] = bond_wealth / bond_wealth.shift(63) - 1.0
    state["bond_drawdown_126"] = bond_wealth / bond_wealth.rolling(126, min_periods=63).max() - 1.0
    state["base_drawdown_126"] = base_wealth / base_wealth.rolling(126, min_periods=63).max() - 1.0
    state["base_realized_vol_20"] = aligned["base"].rolling(20, min_periods=10).std() * np.sqrt(252.0)
    state["cash_capacity"] = aligned["cash_capacity"].clip(0.0, 1.0)
    state["previous_sleeve"] = aligned["sleeve"].shift(1, fill_value=0.0).clip(0.0, 1.0)
    readiness = (
        0.25 * ((-state["corr_63"]).clip(0.0, 0.40) / 0.40)
        + 0.15 * ((-state["corr_126"]).clip(0.0, 0.30) / 0.30)
        + 0.20 * ((state["bond_return_63"] + 0.02).clip(0.0, 0.08) / 0.08)
        + 0.15 * ((state["bond_drawdown_126"] + 0.12).clip(0.0, 0.12) / 0.12)
        + 0.10 * ((-state["base_drawdown_126"]).clip(0.0, 0.20) / 0.20)
        + 0.10 * (state["base_realized_vol_20"].clip(0.05, 0.35) - 0.05) / 0.30
        + 0.05 * (state["cash_capacity"].clip(0.0, 0.20) / 0.20)
    )
    state["readiness_score"] = readiness.clip(0.0, 1.0).shift(1).fillna(0.0)
    state["readiness_level"] = np.select(
        [state["readiness_score"] >= 0.70, state["readiness_score"] >= 0.45],
        ["high", "medium"],
        default="low",
    )
    return state


def _run_window(
    *,
    name: str,
    start: str,
    end: str,
    db_path: Path,
    runner_params: dict[str, Any],
    cost_bps: float,
    lookback: int,
    min_lookback: int,
    rebalance_every: int,
) -> dict[str, Any]:
    report, frame = run_a2118(
        start=start,
        end=end,
        initial_value=1_000_000.0,
        db=db_path,
        **runner_params,
    )
    values = pd.to_numeric(frame["portfolio_value"], errors="coerce")
    base_returns = values.pct_change().fillna(0.0).rename("base_return")
    bond_returns = _load_returns(db_path, TICKER, start, end).reindex(base_returns.index).fillna(0.0)
    cash_capacity = _cash_capacity(frame, report).reindex(base_returns.index).fillna(0.0)
    variants: dict[str, pd.Series] = {"base_latest": pd.Series(0.0, index=base_returns.index)}
    for weight in (0.05, 0.10, 0.15, 0.20):
        variants[f"static_00679b_{int(weight * 100):02d}pct"] = pd.Series(weight, index=base_returns.index)
    for weight in (0.05, 0.10):
        variants[f"conditional_corr_00679b_{int(weight * 100):02d}pct"] = _conditional_corr_sleeve(
            base_returns,
            bond_returns,
            target_weight=weight,
            corr_window=63,
            corr_max=-0.05,
            bond_momentum_window=63,
            bond_momentum_min=-0.02,
        )
    variants["dynamic_spectral_min_loss"] = _rolling_spectral_sleeve(
        base_returns,
        bond_returns,
        cash_capacity,
        candidates=(0.0, 0.05, 0.10, 0.15, 0.20),
        lookback=lookback,
        min_lookback=min_lookback,
        rebalance_every=rebalance_every,
        cost_bps=cost_bps,
    )

    rows = {}
    returns_by_variant: dict[str, pd.Series] = {}
    for variant, sleeve in variants.items():
        simulated = _apply_cash_funded_bond_sleeve(
            base_returns,
            bond_returns,
            cash_capacity,
            sleeve,
            cost_bps=cost_bps,
        )
        returns_by_variant[variant] = simulated
        rows[variant] = {
            "metrics": _metrics(simulated),
            "avg_00679b_sleeve": float(sleeve.mean()),
            "active_days": int((sleeve > 0.0).sum()),
            "turnover_sleeve": float(sleeve.diff().abs().fillna(sleeve.iloc[0]).sum()),
        }
    readiness_state = _hedge_readiness_state(
        base_returns,
        bond_returns,
        cash_capacity,
        variants["dynamic_spectral_min_loss"],
    )

    base = rows["base_latest"]["metrics"]
    for variant, row in rows.items():
        metrics = row["metrics"]
        row["delta_vs_base"] = {
            "final_value_per_1m": None
            if metrics.get("final_value_per_1m") is None
            else float(metrics["final_value_per_1m"] - base["final_value_per_1m"]),
            "max_drawdown": None
            if metrics.get("max_drawdown") is None
            else float(metrics["max_drawdown"] - base["max_drawdown"]),
            "expected_shortfall_loss_95": None
            if metrics.get("expected_shortfall_loss_95") is None
            else float(metrics["expected_shortfall_loss_95"] - base["expected_shortfall_loss_95"]),
            "spectral_loss_95_975_99": None
            if metrics.get("spectral_loss_95_975_99") is None
            else float(metrics["spectral_loss_95_975_99"] - base["spectral_loss_95_975_99"]),
            "rolling_5d_spectral_loss": None
            if metrics.get("rolling_5d_spectral_loss") is None
            else float(metrics["rolling_5d_spectral_loss"] - base["rolling_5d_spectral_loss"]),
            "rolling_20d_spectral_loss": None
            if metrics.get("rolling_20d_spectral_loss") is None
            else float(metrics["rolling_20d_spectral_loss"] - base["rolling_20d_spectral_loss"]),
        }

    candidates = {k: v for k, v in rows.items() if k != "base_latest"}
    best_by_spectral = min(
        candidates,
        key=lambda key: candidates[key]["metrics"].get("spectral_loss_95_975_99") or np.inf,
    )
    best_by_profile: dict[str, dict[str, Any]] = {}
    for profile_name in SPECTRAL_PROFILES:
        best_key = min(
            candidates,
            key=lambda key: (candidates[key]["metrics"].get("spectral_loss_profiles") or {}).get(profile_name) or np.inf,
        )
        best_metrics = candidates[best_key]["metrics"]
        base_profile_loss = (rows["base_latest"]["metrics"].get("spectral_loss_profiles") or {}).get(profile_name)
        best_profile_loss = (best_metrics.get("spectral_loss_profiles") or {}).get(profile_name)
        best_delta = candidates[best_key]["delta_vs_base"]
        best_by_profile[profile_name] = {
            "variant": best_key,
            "loss": best_profile_loss,
            "delta_loss_vs_base": None if best_profile_loss is None or base_profile_loss is None else float(best_profile_loss - base_profile_loss),
            "delta_final_value_per_1m": best_delta.get("final_value_per_1m"),
            "delta_max_drawdown": best_delta.get("max_drawdown"),
            "promote_candidate": bool(
                (best_delta.get("final_value_per_1m") or -np.inf) >= 0.0
                and (best_delta.get("max_drawdown") or -np.inf) >= 0.0
                and (
                    best_profile_loss is not None
                    and base_profile_loss is not None
                    and best_profile_loss <= base_profile_loss
                )
                and candidates[best_key]["active_days"] > 0
            ),
        }
    best_by_final = max(
        candidates,
        key=lambda key: candidates[key]["metrics"].get("final_value_per_1m") or -np.inf,
    )
    best = rows[best_by_spectral]
    bootstrap = _paired_block_bootstrap(
        returns_by_variant["base_latest"],
        returns_by_variant[best_by_spectral],
        iterations=500,
        block_size=20,
        seed=260902014 + sum(ord(ch) for ch in name),
    )
    stress_check = _stress_path_check(
        base_returns,
        bond_returns,
        cash_capacity,
        variants[best_by_spectral],
        cost_bps=cost_bps,
    )
    cost_sensitivity = _cost_sensitivity_check(
        base_returns,
        bond_returns,
        cash_capacity,
        variants[best_by_spectral],
        cost_bps_values=(0.0, 10.0, 20.0, 50.0),
    )
    promotes = bool(
        (best["delta_vs_base"]["final_value_per_1m"] or -np.inf) >= 0.0
        and (best["delta_vs_base"]["max_drawdown"] or -np.inf) >= 0.0
        and (best["delta_vs_base"]["spectral_loss_95_975_99"] or np.inf) <= 0.0
        and best["active_days"] > 0
    )
    return {
        "window": name,
        "start": start,
        "end": str(report.get("window", {}).get("end", end)),
        "rows": rows,
        "best_by_spectral_loss": best_by_spectral,
        "best_by_spectral_profile": best_by_profile,
        "best_by_final_value": best_by_final,
        "best_spectral_block_bootstrap": bootstrap,
        "best_spectral_stress_path_check": stress_check,
        "best_spectral_cost_sensitivity": cost_sensitivity,
        "hedge_readiness": {
            "latest": {
                key: (
                    None
                    if pd.isna(readiness_state.iloc[-1][key])
                    else (
                        str(readiness_state.iloc[-1][key])
                        if key == "readiness_level"
                        else float(readiness_state.iloc[-1][key])
                    )
                )
                for key in readiness_state.columns
            },
            "level_counts": {
                str(key): int(value)
                for key, value in readiness_state["readiness_level"].value_counts().sort_index().items()
            },
            "mean_score": float(readiness_state["readiness_score"].mean()),
            "high_days": int((readiness_state["readiness_level"] == "high").sum()),
        },
        "spectral_promote_candidate": promotes,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    runner_params = _load_manifest(_resolve(args.manifest))
    allowed = {
        "ncf_panel_631l_path",
        "ncf_00713_path",
        "h20_max",
        "conf_min",
        "h5_reentry_min",
        "chip_data_fallback_max_stale_days",
        "risk_score_lookback_days",
        "momentum_fast_exit_min",
        "momentum_fast_exit_ma_gap_min",
        "group_a_plusplus_00713_cash_sleeve_weight",
        "group_a_plusplus_00713_ncf_enabled",
        "exclude_zero_volume_rows",
    }
    runner_params = {key: value for key, value in runner_params.items() if key in allowed}
    windows = [
        _run_window(
            name=name,
            start=start,
            end=end,
            db_path=db_path,
            runner_params=runner_params,
            cost_bps=args.cost_bps,
            lookback=args.lookback,
            min_lookback=args.min_lookback,
            rebalance_every=args.rebalance_every,
        )
        for name, start, end in WINDOWS
    ]
    pass_count = sum(1 for row in windows if row["spectral_promote_candidate"])
    profile_pass_counts = {
        profile_name: sum(
            1
            for row in windows
            if row["best_by_spectral_profile"][profile_name]["promote_candidate"]
        )
        for profile_name in SPECTRAL_PROFILES
    }
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_2609_02014_spectral_00679b_hedge_review",
        "status": "research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2609.02014.pdf",
            "title": "Insights on Time-consistent Deep Hedging under Elicitable Dynamic Risk Measures",
            "adapted_concepts": [
                "dynamic CVaR / spectral tail objective",
                "time-consistent rolling risk-to-go proxy",
                "short-horizon hedge evaluation",
                "tail-sensitive scoring before live promotion",
            ],
            "not_imported": [
                "full actor-critic deep hedging policy",
                "basket option pricing surrogate",
                "DCC-GARCH path simulator",
            ],
        },
        "policy": "shadow_only_no_live_weight_change",
        "parameters": {
            "manifest": str(_resolve(args.manifest).relative_to(PROJECT_ROOT)),
            "db": str(db_path.relative_to(PROJECT_ROOT)),
            "cost_bps_per_abs_weight_change": args.cost_bps,
            "lookback": args.lookback,
            "min_lookback": args.min_lookback,
            "rebalance_every": args.rebalance_every,
            "conditional_corr_rule": "active when lagged 63d corr(base,00679B)<=-0.05 and lagged 63d 00679B return>=-2%",
            "spectral_loss": "0.50*ES95 + 0.30*ES97.5 + 0.20*ES99 of daily losses",
            "spectral_profiles": {
                name: [{"weight": weight, "confidence": confidence} for weight, confidence in profile]
                for name, profile in SPECTRAL_PROFILES.items()
            },
            "sleeve_candidates": [0.0, 0.05, 0.10, 0.15, 0.20],
            "funding": "00679B.TWO sleeve is funded only from available cash capacity.",
            "runner_params": runner_params,
        },
        "windows": windows,
        "aggregate": {
            "windows": len(windows),
            "spectral_promote_candidate_windows": pass_count,
            "spectral_profile_promote_candidate_windows": profile_pass_counts,
            "all_windows_pass": pass_count == len(windows),
        },
        "decision": {
            "promote_to_latest_strategy": False,
            "reason": (
                "Keep research-only unless a 00679B sleeve improves final value, max drawdown, "
                "and spectral loss versus base GroupA++ in every tested window after costs."
            ),
            "best_import": "spectral_tail_scorecard_for_00679b_hedge_capacity",
            "creates_orders": False,
            "changes_target_weights": False,
        },
    }


def _fmt(value: Any, digits: int = 4) -> str:
    number = _finite(value)
    return "NA" if number is None else f"{number:.{digits}f}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2609.02014 Spectral 00679B Hedge Review",
        "",
        f"- Status: `{report['status']}`",
        f"- Policy: `{report['policy']}`",
        f"- Decision: promote_to_latest_strategy=`{report['decision']['promote_to_latest_strategy']}`",
        f"- Spectral loss: `{report['parameters']['spectral_loss']}`",
        "",
        "## Interpretation",
        "",
        "The paper's useful import is the objective, not the full deep-hedging machinery. "
        "GroupA++ does not trade a high-dimensional option book, so this review treats 00679B.TWO "
        "as a cash-funded hedge sleeve and scores it with a dynamic rolling spectral-loss proxy.",
        "",
        "## Window Results",
        "",
        "| window | best spectral | promote? | base final | best final | delta final | base MDD | best MDD | base spectral | best spectral loss |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for window in report["windows"]:
        rows = window["rows"]
        base = rows["base_latest"]["metrics"]
        best_key = window["best_by_spectral_loss"]
        best = rows[best_key]["metrics"]
        delta = rows[best_key]["delta_vs_base"]
        lines.append(
            "| {window} | `{best_key}` | `{promote}` | {base_final} | {best_final} | {delta_final} | {base_mdd} | {best_mdd} | {base_spec} | {best_spec} |".format(
                window=window["window"],
                best_key=best_key,
                promote=window["spectral_promote_candidate"],
                base_final=_fmt(base.get("final_value_per_1m"), 2),
                best_final=_fmt(best.get("final_value_per_1m"), 2),
                delta_final=_fmt(delta.get("final_value_per_1m"), 2),
                base_mdd=_fmt(base.get("max_drawdown")),
                best_mdd=_fmt(best.get("max_drawdown")),
                base_spec=_fmt(base.get("spectral_loss_95_975_99")),
                best_spec=_fmt(best.get("spectral_loss_95_975_99")),
            )
        )
    lines.extend(
        [
            "",
            "## Conditional-Correlation Check",
            "",
            "This check tries to avoid the known 2022 stock-bond hedge failure by opening 00679B only when lagged 63-day correlation versus the base strategy is negative and 00679B's own 63-day return is not worse than -2%.",
            "",
            "| window | variant | active days | avg sleeve | delta final | delta MDD | delta spectral |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for window in report["windows"]:
        for key in ("conditional_corr_00679b_05pct", "conditional_corr_00679b_10pct"):
            row = window["rows"][key]
            delta = row["delta_vs_base"]
            lines.append(
                "| {window} | `{variant}` | {days} | {avg} | {delta_final} | {delta_mdd} | {delta_spec} |".format(
                    window=window["window"],
                    variant=key,
                    days=row["active_days"],
                    avg=_fmt(row["avg_00679b_sleeve"]),
                    delta_final=_fmt(delta.get("final_value_per_1m"), 2),
                    delta_mdd=_fmt(delta.get("max_drawdown")),
                    delta_spec=_fmt(delta.get("spectral_loss_95_975_99")),
                )
            )
    lines.extend(
        [
            "",
            "## Spectral Profile Sensitivity",
            "",
            "| window | profile | best variant | promote? | delta final | delta MDD | delta spectral loss |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for window in report["windows"]:
        for profile_name, row in window["best_by_spectral_profile"].items():
            lines.append(
                "| {window} | `{profile}` | `{variant}` | `{promote}` | {delta_final} | {delta_mdd} | {delta_loss} |".format(
                    window=window["window"],
                    profile=profile_name,
                    variant=row["variant"],
                    promote=row["promote_candidate"],
                    delta_final=_fmt(row.get("delta_final_value_per_1m"), 2),
                    delta_mdd=_fmt(row.get("delta_max_drawdown")),
                    delta_loss=_fmt(row.get("delta_loss_vs_base")),
                )
            )
    lines.extend(
        [
            "",
            "## Short-Horizon Dynamic Risk Check",
            "",
            "This follows the paper's finding that dynamic risk objectives can be more useful at shorter horizons. Negative delta means the 00679B variant reduced rolling-horizon spectral loss versus base GroupA++.",
            "",
            "| window | best spectral variant | delta 5d spectral | delta 20d spectral |",
            "|---|---|---:|---:|",
        ]
    )
    for window in report["windows"]:
        key = window["best_by_spectral_loss"]
        delta = window["rows"][key]["delta_vs_base"]
        lines.append(
            "| {window} | `{variant}` | {d5} | {d20} |".format(
                window=window["window"],
                variant=key,
                d5=_fmt(delta.get("rolling_5d_spectral_loss")),
                d20=_fmt(delta.get("rolling_20d_spectral_loss")),
            )
        )
    lines.extend(
        [
            "",
            "## Block Bootstrap Stability",
            "",
            "Paired 20-day block bootstrap on the best-spectral variant in each window. Higher `p spectral improve` means spectral-loss reduction is more stable under resampling; higher `p final improve` means final-value improvement is more stable.",
            "",
            "| window | variant | p spectral improve | spectral delta p05 | spectral delta p95 | p final improve | final delta p05 | final delta p95 | p MDD improve |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for window in report["windows"]:
        bootstrap = window["best_spectral_block_bootstrap"]
        if bootstrap.get("status") != "ok":
            lines.append(
                f"| {window['window']} | `{window['best_by_spectral_loss']}` | NA | NA | NA | NA | NA | NA | NA |"
            )
            continue
        spectral = bootstrap["spectral_loss_delta"]
        final = bootstrap["final_value_delta"]
        mdd = bootstrap["max_drawdown_delta"]
        lines.append(
            "| {window} | `{variant}` | {ps} | {sp05} | {sp95} | {pf} | {fp05} | {fp95} | {pmdd} |".format(
                window=window["window"],
                variant=window["best_by_spectral_loss"],
                ps=_fmt(spectral.get("p_improve")),
                sp05=_fmt(spectral.get("p05")),
                sp95=_fmt(spectral.get("p95")),
                pf=_fmt(final.get("p_improve")),
                fp05=_fmt(final.get("p05"), 2),
                fp95=_fmt(final.get("p95"), 2),
                pmdd=_fmt(mdd.get("p_improve")),
            )
        )
    lines.extend(
        [
            "",
            "## 00679B Hedge Readiness State",
            "",
            "Daily diagnostic state adapted from the paper's state-design idea. This is lagged one day and does not trade. `high_days` counts days whose readiness score is at least 0.70.",
            "",
            "| window | latest level | latest score | corr63 | corr126 | bond 63d return | bond DD126 | base DD126 | base vol20 | cash capacity | high days |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for window in report["windows"]:
        readiness = window["hedge_readiness"]
        latest = readiness["latest"]
        lines.append(
            "| {window} | `{level}` | {score} | {corr63} | {corr126} | {bond_ret} | {bond_dd} | {base_dd} | {base_vol} | {cash} | {high_days} |".format(
                window=window["window"],
                level=latest.get("readiness_level"),
                score=_fmt(latest.get("readiness_score")),
                corr63=_fmt(latest.get("corr_63")),
                corr126=_fmt(latest.get("corr_126")),
                bond_ret=_fmt(latest.get("bond_return_63")),
                bond_dd=_fmt(latest.get("bond_drawdown_126")),
                base_dd=_fmt(latest.get("base_drawdown_126")),
                base_vol=_fmt(latest.get("base_realized_vol_20")),
                cash=_fmt(latest.get("cash_capacity")),
                high_days=readiness["high_days"],
            )
        )
    lines.extend(
        [
            "",
            "## Stress Path Perturbation",
            "",
            "Deterministic stress scenarios adapted from the paper's perturbed-path validation. Each row applies the window's best-spectral 00679B sleeve to a modified 00679B return path while keeping the base GroupA++ path fixed.",
            "",
            "| window | variant | scenario | delta final | delta MDD | delta spectral | delta 20d spectral |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for window in report["windows"]:
        variant = window["best_by_spectral_loss"]
        for scenario, row in window["best_spectral_stress_path_check"].items():
            delta = row["delta_vs_base"]
            lines.append(
                "| {window} | `{variant}` | `{scenario}` | {delta_final} | {delta_mdd} | {delta_spec} | {delta_20d} |".format(
                    window=window["window"],
                    variant=variant,
                    scenario=scenario,
                    delta_final=_fmt(delta.get("final_value_per_1m"), 2),
                    delta_mdd=_fmt(delta.get("max_drawdown")),
                    delta_spec=_fmt(delta.get("spectral_loss_95_975_99")),
                    delta_20d=_fmt(delta.get("rolling_20d_spectral_loss")),
                )
            )
    lines.extend(
        [
            "",
            "## Transaction Cost Sensitivity",
            "",
            "Cost sensitivity on each window's best-spectral 00679B sleeve. This follows the paper's explicit inclusion of proportional transaction costs. The base GroupA++ path is unchanged; only the cash-funded 00679B sleeve cost changes.",
            "",
            "| window | variant | cost bps | delta final | delta MDD | delta spectral |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for window in report["windows"]:
        variant = window["best_by_spectral_loss"]
        for cost_bps, row in window["best_spectral_cost_sensitivity"].items():
            delta = row["delta_vs_base"]
            lines.append(
                "| {window} | `{variant}` | {cost_bps} | {delta_final} | {delta_mdd} | {delta_spec} |".format(
                    window=window["window"],
                    variant=variant,
                    cost_bps=cost_bps,
                    delta_final=_fmt(delta.get("final_value_per_1m"), 2),
                    delta_mdd=_fmt(delta.get("max_drawdown")),
                    delta_spec=_fmt(delta.get("spectral_loss_95_975_99")),
                )
            )
    lines.extend(
        [
            "",
            "## Imported Advantages",
            "",
            "- Use spectral risk instead of only Sharpe/MDD when judging a hedge sleeve.",
            "- Evaluate short-horizon hedge behavior separately from terminal wealth.",
            "- Keep dynamic decisions time-consistent by using rolling past data only.",
            "- Treat 00679B capacity as state-dependent and funded only from cash.",
            "",
            "## Not Imported",
            "",
            "- No actor-critic live allocator.",
            "- No option-pricing surrogate.",
            "- No DCC-GARCH simulator in production.",
            "- No automatic 00679B target-weight change.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT))
    parser.add_argument("--cost-bps", type=float, default=20.0)
    parser.add_argument("--lookback", type=int, default=252)
    parser.add_argument("--min-lookback", type=int, default=126)
    parser.add_argument("--rebalance-every", type=int, default=21)
    args = parser.parse_args()
    report = build_report(args)
    output = _resolve(args.output)
    md_output = _resolve(args.md_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, md_output)
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))
    print(output)
    print(md_output)


if __name__ == "__main__":
    main()
