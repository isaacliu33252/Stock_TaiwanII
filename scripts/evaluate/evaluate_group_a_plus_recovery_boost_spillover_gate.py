#!/usr/bin/env python3
"""Evaluate a network-spillover gate on GroupA+ recovery boost shadows."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve
from backtest_group_a_plus_policy_signal import _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.integrations.network_volatility_spillover_shadow import (
    DEFAULT_TICKERS,
    build_log_realized_variance_panel,
    build_spillover_network_frame,
)
from group_a_plus.runners.a2118 import RECOVERY_00631L_BOOST_REGIME, _recovery_boost_weights, run_a2118
from scripts.evaluate.evaluate_group_a_plus_reentry_accelerator_clean import COMMON_KW, PANEL_2017_2019, PANEL_2025_2026
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _metric_delta


WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31", PANEL_2025_2026, "tuning_window"),
    ("inflation_2022", "2022-01-03", "2022-12-30", PANEL_2025_2026, "tuning_window"),
    ("live_2024_2026", "2024-01-02", "2026-07-09", PANEL_2025_2026, "tuning_window"),
    ("active_2025_2026", "2025-01-02", "2026-07-09", PANEL_2025_2026, "tuning_window"),
    ("2017_bull", "2017-01-03", "2017-12-29", PANEL_2017_2019, "out_of_sample"),
    ("2018_correction", "2018-01-02", "2018-12-31", PANEL_2017_2019, "out_of_sample"),
    ("2019_recovery", "2019-01-02", "2019-12-31", PANEL_2017_2019, "out_of_sample"),
]


def _load_ohlcv(db_path: Path, tickers: tuple[str, ...], start: str, end: str) -> pd.DataFrame:
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(
            f"""
            SELECT dt, ticker, open, high, low, close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [*tickers, start, end],
        ).fetchdf()
    finally:
        con.close()


def _age_guard_mask(regime: pd.Series, max_age_days: int) -> pd.Series:
    allowed: list[bool] = []
    age = 0
    for state in regime.astype(str):
        if state == "group_a_plus_recovery":
            age += 1
            allowed.append(age <= max_age_days)
        else:
            age = 0
            allowed.append(False)
    return pd.Series(allowed, index=regime.index, dtype=bool)


def _simulate_spillover_gate_variant(
    baseline: dict[str, Any],
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    boost_fraction: float,
    max_age_days: int,
    max_systemic_percentile: float,
    max_target_in_percentile: float,
) -> dict[str, Any]:
    warmup_start = str((pd.Timestamp(start) - pd.Timedelta(days=560)).date())
    ohlcv = _load_ohlcv(Path(DB_PATH), DEFAULT_TICKERS, warmup_start, end)
    log_rv = build_log_realized_variance_panel(ohlcv, tickers=DEFAULT_TICKERS)
    spillover = build_spillover_network_frame(log_rv).reindex(frame.index).ffill().fillna(0.0)
    regimes = frame["execution_regime"].astype(str).copy()
    age_allowed = _age_guard_mask(regimes, max_age_days)
    spillover_allowed = (
        (spillover["spillover_systemic_percentile_252d"] <= float(max_systemic_percentile))
        & (spillover["spillover_in_percentile_252d_0050.TW"] <= float(max_target_in_percentile))
        & (spillover["spillover_crisis_regime"] == 0)
    )
    boost_allowed = age_allowed & spillover_allowed
    guarded_regimes = regimes.copy()
    guarded_regimes.loc[boost_allowed] = RECOVERY_00631L_BOOST_REGIME

    weights = {name: dict(value) for name, value in baseline["base_weights"].items()}
    weights["group_a_plus_recovery"] = _normalize(weights["group_a_plus_recovery"])
    weights[RECOVERY_00631L_BOOST_REGIME] = _recovery_boost_weights(weights["group_a_plus_recovery"], boost_fraction)
    prices, _coverage = _load_total_return_prices(Path(DB_PATH), frame.index)
    curve, execution = _simulate_costed_curve(prices, guarded_regimes, weights, 1_000_000.0, 0.001425, 0.0005, 0.001)
    blocked_recovery_days = int((age_allowed & ~spillover_allowed).sum())
    return {
        "metrics": _metrics(curve, 1_000_000.0),
        "execution": execution,
        "changed_days": int(boost_allowed.sum()),
        "age_allowed_days": int(age_allowed.sum()),
        "spillover_blocked_recovery_days": blocked_recovery_days,
        "policy": {
            "boost_fraction": boost_fraction,
            "max_age_days": max_age_days,
            "max_systemic_percentile": max_systemic_percentile,
            "max_target_in_percentile": max_target_in_percentile,
        },
    }


def evaluate_window(label: str, start: str, end: str, panel: str, kind: str) -> dict[str, Any]:
    baseline, frame = run_a2118(
        start=start,
        end=end,
        initial_value=1_000_000.0,
        db=Path(DB_PATH),
        ncf_panel_631l_path=panel,
        **COMMON_KW,
    )
    baseline_metrics = dict(baseline["metrics"])
    variants: dict[str, Any] = {}
    for boost_fraction, name_prefix in ((0.10, "recovery_boost_100"), (0.15, "recovery_boost_150")):
        for threshold in (0.80, 0.90, 0.95):
            variant_name = f"{name_prefix}_age20_spillover_p{int(threshold * 100)}"
            variant = _simulate_spillover_gate_variant(
                baseline,
                frame,
                start=start,
                end=end,
                boost_fraction=boost_fraction,
                max_age_days=20,
                max_systemic_percentile=threshold,
                max_target_in_percentile=threshold,
            )
            variants[variant_name] = {
                **variant,
                "delta_vs_baseline": _metric_delta(variant["metrics"], baseline_metrics),
            }
    return {
        "label": label,
        "kind": kind,
        "window": {"start": start, "end": end, "rows": int(len(frame))},
        "baseline": baseline_metrics,
        "recovery_days": int((frame["execution_regime"].astype(str) == "group_a_plus_recovery").sum()),
        "variants": variants,
    }


def main() -> None:
    windows = [evaluate_window(*window) for window in WINDOWS]
    summary: dict[str, dict[str, float]] = {}
    for variant in sorted(windows[0]["variants"]):
        tuning = [w for w in windows if w["kind"] == "tuning_window"]
        oos = [w for w in windows if w["kind"] == "out_of_sample"]
        summary[variant] = {
            "tuning_sum_delta_final_value": sum(w["variants"][variant]["delta_vs_baseline"]["delta_final_value"] for w in tuning),
            "tuning_sum_delta_sharpe_ratio": sum(w["variants"][variant]["delta_vs_baseline"]["delta_sharpe_ratio"] for w in tuning),
            "oos_sum_delta_final_value": sum(w["variants"][variant]["delta_vs_baseline"]["delta_final_value"] for w in oos),
            "oos_sum_delta_sharpe_ratio": sum(w["variants"][variant]["delta_vs_baseline"]["delta_sharpe_ratio"] for w in oos),
            "changed_days": sum(int(w["variants"][variant]["changed_days"]) for w in windows),
            "spillover_blocked_recovery_days": sum(int(w["variants"][variant]["spillover_blocked_recovery_days"]) for w in windows),
        }
        print(variant, summary[variant])

    payload = {
        "strategy": "group_a_plus_recovery_boost_spillover_gate_shadow",
        "research_only": True,
        "summary": summary,
        "windows": windows,
        "promotion_review": {
            "decision": "do_not_promote_shadow_only",
            "reason": "First-pass rolling lagged spillover gate; requires five-crisis and live shadow validation.",
        },
    }
    output = PROJECT_ROOT / "results" / "group_a_plus_recovery_boost_spillover_gate_20260711.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
