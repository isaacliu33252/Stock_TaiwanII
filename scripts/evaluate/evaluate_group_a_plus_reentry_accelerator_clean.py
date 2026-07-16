#!/usr/bin/env python3
"""Clean re-entry accelerator tests for GroupA+.

Direction-4 no-add/cooldown tests showed that blocking the 2020-06-03 and
2025-06-09/10 re-entry points hurts. This script tests the opposite, without
mixing in de-risk trims:

1. make `group_a_plus_recovery` more like golden1, or mildly boost 00631L;
2. enable rebound recapture only, with no follow-through trim.

Research-only. It writes a JSON report and does not touch live targets.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import duckdb
import pandas as pd

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve, _trade_cost
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.integrations.foundation_volatility_shadow import build_foundation_vol_shadow_frame
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_group_a_plus_volatility_gate_shadow import _metric_delta

PANEL_2025_2026 = "results/ncf_00631l_panel_latest_20260707.csv"
PANEL_2017_2019 = "results/ncf_00631l_panel_backfill_2017_2019_20260710.csv"

WINDOWS = [
    ("covid_2020", "2020-01-02", "2020-12-31", PANEL_2025_2026, "tuning_window"),
    ("inflation_2022", "2022-01-03", "2022-12-30", PANEL_2025_2026, "tuning_window"),
    ("live_2024_2026", "2024-01-02", "2026-07-09", PANEL_2025_2026, "tuning_window"),
    ("active_2025_2026", "2025-01-02", "2026-07-09", PANEL_2025_2026, "tuning_window"),
    ("2017_bull", "2017-01-03", "2017-12-29", PANEL_2017_2019, "out_of_sample"),
    ("2018_correction", "2018-01-02", "2018-12-31", PANEL_2017_2019, "out_of_sample"),
    ("2019_recovery", "2019-01-02", "2019-12-31", PANEL_2017_2019, "out_of_sample"),
]

COMMON_KW = dict(
    h20_max=0.33,
    conf_min=0.55,
    h5_reentry_min=0.55,
    chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
    momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
    momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
)


def _boost_00631l_from_0050(weights: dict[str, float], boost_fraction: float) -> dict[str, float]:
    out = dict(weights)
    boost_fraction = min(max(float(boost_fraction), 0.0), 1.0)
    shift = float(out.get("0050.TW", 0.0)) * boost_fraction
    out["0050.TW"] = float(out.get("0050.TW", 0.0)) - shift
    out["00631L.TW"] = float(out.get("00631L.TW", 0.0)) + shift
    return _normalize(out)


def _recovery_weight_variant(report: dict[str, Any], frame, variant_name: str) -> tuple[dict, Any]:
    weights = {name: dict(value) for name, value in report["base_weights"].items()}
    if variant_name == "recovery_as_golden1":
        weights["group_a_plus_recovery"] = dict(weights["golden1"])
    elif variant_name == "recovery_boost_005":
        weights["group_a_plus_recovery"] = _boost_00631l_from_0050(weights["group_a_plus_recovery"], 0.05)
    elif variant_name == "recovery_boost_010":
        weights["group_a_plus_recovery"] = _boost_00631l_from_0050(weights["group_a_plus_recovery"], 0.10)
    else:
        raise ValueError(variant_name)

    prices, _coverage = _load_total_return_prices(Path(DB_PATH), frame.index)
    curve, execution = _simulate_costed_curve(
        prices,
        frame["execution_regime"].astype(str),
        weights,
        1_000_000.0,
        0.001425,
        0.0005,
        0.001,
    )
    metrics = _metrics(curve, 1_000_000.0)
    return {
        "metrics": metrics,
        "execution": execution,
        "changed_days": int((frame["execution_regime"].astype(str) == "group_a_plus_recovery").sum()),
        "recovery_weights": weights["group_a_plus_recovery"],
    }, frame


def _load_ohlc(db_path: Path, ticker: str, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, open, high, low, close
            FROM ohlcv
            WHERE ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, start, end],
        ).fetchdf()
    finally:
        con.close()
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows.set_index("dt")


def _simulate_recovery_boost_with_vol_quality(
    report: dict[str, Any],
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    boost_fraction: float,
    max_percentile: float,
    max_uncertainty_ratio: float,
) -> dict[str, Any]:
    prices, _coverage = _load_total_return_prices(Path(DB_PATH), frame.index)
    ohlc = _load_ohlc(Path(DB_PATH), "0050.TW", start, end)
    vol_frame = build_foundation_vol_shadow_frame(ohlc).reindex(frame.index)
    percentile = vol_frame["ensemble_h10_percentile_252d"].fillna(1.0)
    uncertainty = vol_frame["ensemble_h10_uncertainty_ratio"].fillna(1.0)
    allow_boost = (percentile <= float(max_percentile)) & (uncertainty <= float(max_uncertainty_ratio))

    weights = {name: dict(value) for name, value in report["base_weights"].items()}
    recovery_base = _normalize(weights["group_a_plus_recovery"])
    recovery_boost = _boost_00631l_from_0050(recovery_base, boost_fraction)
    regimes = frame["execution_regime"].astype(str)

    shares = {ticker: 0.0 for ticker in TICKERS}
    cash = 1_000_000.0
    current_regime: str | None = None
    current_recovery_boost_allowed: bool | None = None
    values: list[float] = []
    total_cost = 0.0
    total_turnover = 0.0
    rebalance_count = 0
    boosted_days = 0
    recovery_days = 0
    events: list[dict[str, Any]] = []

    for dt, price_row in prices.iterrows():
        gross_value = cash + sum(shares[ticker] * float(price_row[ticker]) for ticker in TICKERS)
        next_regime = str(regimes.loc[dt])
        boost_allowed = bool(allow_boost.loc[dt]) if next_regime == "group_a_plus_recovery" else None
        should_rebalance = next_regime != current_regime or (
            next_regime == "group_a_plus_recovery" and boost_allowed != current_recovery_boost_allowed
        )
        if should_rebalance:
            if next_regime == "group_a_plus_recovery":
                recovery_days += 1
                target_weights = recovery_boost if boost_allowed else recovery_base
                if boost_allowed:
                    boosted_days += 1
                events.append(
                    {
                        "date": str(pd.Timestamp(dt).date()),
                        "boost_allowed": boost_allowed,
                        "percentile_h10": round(float(percentile.loc[dt]), 6),
                        "uncertainty_h10": round(float(uncertainty.loc[dt]), 6),
                    }
                )
            else:
                target_weights = _normalize(weights[next_regime])

            current_values = {ticker: shares[ticker] * float(price_row[ticker]) for ticker in TICKERS}
            net_value = gross_value
            cost = 0.0
            turnover = 0.0
            for _iteration in range(3):
                target_values = {ticker: net_value * target_weights.get(ticker, 0.0) for ticker in TICKERS}
                cost, turnover = _trade_cost(current_values, target_values, 0.001425, 0.0005, 0.001)
                net_value = max(gross_value - cost, 0.0)
            shares = {
                ticker: net_value * target_weights.get(ticker, 0.0) / max(float(price_row[ticker]), 1e-12)
                for ticker in TICKERS
            }
            cash = net_value * target_weights.get("cash", 0.0)
            gross_value = net_value
            total_cost += cost
            total_turnover += turnover
            rebalance_count += 1
            current_regime = next_regime
            current_recovery_boost_allowed = boost_allowed
        values.append(gross_value)

    curve = pd.Series(values, index=prices.index, dtype=float)
    return {
        "metrics": _metrics(curve, 1_000_000.0),
        "execution": {
            "transaction_cost": float(total_cost),
            "turnover_value": float(total_turnover),
            "rebalance_count": int(rebalance_count),
            "recovery_quality_policy": {
                "boost_fraction": float(boost_fraction),
                "max_percentile": float(max_percentile),
                "max_uncertainty_ratio": float(max_uncertainty_ratio),
            },
        },
        "changed_days": int(boosted_days),
        "recovery_days_checked": int(recovery_days),
        "events": events,
    }


RECAPTURE_ONLY_VARIANTS = {
    "recapture_only_default": dict(
        golden_rebound_recapture_enabled=True,
        golden_rebound_recapture_boost_fraction=0.10,
        golden_rebound_recapture_previous_return_min=0.03,
        golden_rebound_recapture_previous_drawdown_max=-0.08,
        golden_rebound_recapture_lookback_days=3,
        golden_rebound_recapture_hold_days=1,
        golden_rebound_recapture_shock_tail_risk_score_min=2,
        golden_rebound_recapture_shock_return_max=-0.03,
    ),
    "recapture_only_loose_005": dict(
        golden_rebound_recapture_enabled=True,
        golden_rebound_recapture_boost_fraction=0.05,
        golden_rebound_recapture_previous_return_min=0.02,
        golden_rebound_recapture_previous_drawdown_max=-0.05,
        golden_rebound_recapture_lookback_days=5,
        golden_rebound_recapture_hold_days=1,
        golden_rebound_recapture_shock_tail_risk_score_min=1,
        golden_rebound_recapture_shock_return_max=-0.02,
    ),
    "recapture_only_loose_010": dict(
        golden_rebound_recapture_enabled=True,
        golden_rebound_recapture_boost_fraction=0.10,
        golden_rebound_recapture_previous_return_min=0.02,
        golden_rebound_recapture_previous_drawdown_max=-0.05,
        golden_rebound_recapture_lookback_days=5,
        golden_rebound_recapture_hold_days=1,
        golden_rebound_recapture_shock_tail_risk_score_min=1,
        golden_rebound_recapture_shock_return_max=-0.02,
    ),
}


def evaluate_window(label: str, start: str, end: str, panel: str, kind: str) -> dict[str, Any]:
    db_path = Path(DB_PATH)
    baseline, frame = run_a2118(
        start=start,
        end=end,
        initial_value=1_000_000.0,
        db=db_path,
        ncf_panel_631l_path=panel,
        **COMMON_KW,
    )
    baseline_metrics = dict(baseline["metrics"])
    variants: dict[str, Any] = {}

    for variant_name in ("recovery_as_golden1", "recovery_boost_005", "recovery_boost_010"):
        variant, _ = _recovery_weight_variant(baseline, frame, variant_name)
        variants[variant_name] = {
            **variant,
            "delta_vs_baseline": _metric_delta(variant["metrics"], baseline_metrics),
        }

    for boost_fraction in (0.05, 0.10, 0.15):
        for threshold in (0.50, 0.65, 0.80):
            variant_name = f"recovery_boost_{int(boost_fraction * 1000):03d}_vol_quality_p{int(threshold * 100)}"
            variant = _simulate_recovery_boost_with_vol_quality(
                baseline,
                frame,
                start=start,
                end=end,
                boost_fraction=boost_fraction,
                max_percentile=threshold,
                max_uncertainty_ratio=0.50,
            )
            variants[variant_name] = {
                **variant,
                "delta_vs_baseline": _metric_delta(variant["metrics"], baseline_metrics),
            }
    for uncertainty in (0.25, 0.75):
        variant_name = f"recovery_boost_100_vol_quality_p65_u{int(uncertainty * 100)}"
        variant = _simulate_recovery_boost_with_vol_quality(
            baseline,
            frame,
            start=start,
            end=end,
            boost_fraction=0.10,
            max_percentile=0.65,
            max_uncertainty_ratio=uncertainty,
        )
        variants[variant_name] = {
            **variant,
            "delta_vs_baseline": _metric_delta(variant["metrics"], baseline_metrics),
        }

    for boost_fraction in (0.05, 0.10, 0.15):
        for max_age_days in (10, 20, 30):
            variant_name = f"recovery_boost_{int(boost_fraction * 1000):03d}_age{max_age_days}"
            report, guarded_frame = run_a2118(
                start=start,
                end=end,
                initial_value=1_000_000.0,
                db=db_path,
                ncf_panel_631l_path=panel,
                **COMMON_KW,
                recovery_00631l_boost_fraction=boost_fraction,
                recovery_00631l_boost_max_age_days=max_age_days,
            )
            metrics = dict(report["metrics"])
            variants[variant_name] = {
                "metrics": metrics,
                "execution": dict(report["execution"]),
                "delta_vs_baseline": _metric_delta(metrics, baseline_metrics),
                "changed_days": int(report["execution"].get("recovery_00631l_boost_days", 0)),
                "recovery_days_checked": int(report["execution"].get("recovery_00631l_boost_recovery_days", 0)),
                "boosted_regime_days": int(
                    (guarded_frame["execution_regime"].astype(str) == "group_a_plus_recovery_00631l_boost").sum()
                ),
            }

    for variant_name, kwargs in RECAPTURE_ONLY_VARIANTS.items():
        report, recapture_frame = run_a2118(
            start=start,
            end=end,
            initial_value=1_000_000.0,
            db=db_path,
            ncf_panel_631l_path=panel,
            **COMMON_KW,
            **kwargs,
        )
        metrics = dict(report["metrics"])
        variants[variant_name] = {
            "metrics": metrics,
            "execution": dict(report["execution"]),
            "delta_vs_baseline": _metric_delta(metrics, baseline_metrics),
            "recapture_days": int((recapture_frame["execution_regime"].astype(str) == "golden1_rebound_recapture").sum()),
            "overlay_info": {
                key: value
                for key, value in report.get("overlay_info", {}).items()
                if key.startswith("golden_rebound_recapture")
            },
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
    variant_names = sorted(windows[0]["variants"])
    summary: dict[str, dict[str, float]] = {}
    for variant in variant_names:
        tuning = [w for w in windows if w["kind"] == "tuning_window"]
        oos = [w for w in windows if w["kind"] == "out_of_sample"]
        summary[variant] = {
            "tuning_sum_delta_final_value": sum(w["variants"][variant]["delta_vs_baseline"]["delta_final_value"] for w in tuning),
            "tuning_sum_delta_sharpe_ratio": sum(w["variants"][variant]["delta_vs_baseline"]["delta_sharpe_ratio"] for w in tuning),
            "oos_sum_delta_final_value": sum(w["variants"][variant]["delta_vs_baseline"]["delta_final_value"] for w in oos),
            "oos_sum_delta_sharpe_ratio": sum(w["variants"][variant]["delta_vs_baseline"]["delta_sharpe_ratio"] for w in oos),
            "changed_days": sum(
                int(w["variants"][variant].get("changed_days", w["variants"][variant].get("recapture_days", 0)))
                for w in windows
            ),
        }
        print(variant, summary[variant])

    payload = {
        "strategy": "group_a_plus_clean_reentry_accelerator_shadow",
        "research_only": True,
        "summary": summary,
        "windows": windows,
        "promotion_review": {
            "decision": "do_not_promote_keep_shadow",
            "reason": "Needs positive tuning and OOS evidence with enough event count.",
        },
    }
    output = PROJECT_ROOT / "results" / "group_a_plus_reentry_accelerator_clean_20260710.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
