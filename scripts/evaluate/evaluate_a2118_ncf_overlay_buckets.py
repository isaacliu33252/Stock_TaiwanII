#!/usr/bin/env python3
"""Bucket attribution for A21.18's 00631L NCF late-bull overlay.

This is read-only research. It compares:

1. A21.18 base path with no historical NCF panel.
2. A21.18 active NCF overlay using the production manifest parameters.

The report is intentionally bucketed around the promotion question: whether
the late-bull NCF rule adds value under high/low confidence and large/marginal
H20 downside readings, and whether older stress windows even have panel
coverage.
"""

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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY, resolve_latest
from group_a_plus.runners.a2118 import (
    NCF_LB_REGIME,
    NCF_LB_SOFT_REGIME,
    run_a2118,
)


DEFAULT_OUTPUT = Path("results/a2118_ncf_overlay_bucket_attribution_latest.json")
DEFAULT_WINDOWS = {
    "covid_2020": ("2020-01-02", "2020-06-30"),
    "bear_2022": ("2022-01-03", "2022-12-30"),
    "strong_bull_panel": ("2025-02-03", "2025-06-30"),
    "sideways_panel": ("2025-07-01", "2025-10-31"),
    "active_2025_2026": ("2025-01-02", "2026-07-06"),
}


def _load_manifest_params(manifest_path: Path) -> dict[str, Any]:
    manifest = resolve_latest(manifest_path)
    active = manifest["active_strategy"]
    if active["id"] != "a2118_a2111_ncf_late_bull_deleverage":
        raise ValueError(f"Manifest active strategy is not A21.18: {active['id']}")
    return dict(active.get("runner_params") or {})


def _metrics(values: pd.Series, initial_value: float) -> dict[str, float]:
    values = values.dropna().astype(float)
    if values.empty:
        return {
            "final_value": 0.0,
            "total_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
        }
    returns = values.pct_change().dropna()
    sharpe = (
        float(returns.mean() / returns.std(ddof=1) * np.sqrt(252))
        if len(returns) > 1 and returns.std(ddof=1) > 0
        else 0.0
    )
    return {
        "final_value": float(values.iloc[-1]),
        "total_return": float(values.iloc[-1] / initial_value - 1.0),
        "sharpe": sharpe,
        "max_drawdown": float((values / values.cummax() - 1.0).min()),
    }


def _return_summary(rows: pd.DataFrame) -> dict[str, Any]:
    if rows.empty:
        return {
            "rows": 0,
            "candidate_return_sum": 0.0,
            "baseline_return_sum": 0.0,
            "return_delta_sum": 0.0,
            "return_delta_mean": 0.0,
            "return_delta_hit_rate": None,
            "candidate_worst_day": None,
            "baseline_worst_day": None,
        }
    delta = rows["return_delta"].astype(float)
    return {
        "rows": int(len(rows)),
        "candidate_return_sum": float(rows["candidate_return"].sum()),
        "baseline_return_sum": float(rows["baseline_return"].sum()),
        "return_delta_sum": float(delta.sum()),
        "return_delta_mean": float(delta.mean()),
        "return_delta_hit_rate": float((delta > 0).mean()),
        "candidate_worst_day": str(rows["candidate_return"].idxmin().date()),
        "baseline_worst_day": str(rows["baseline_return"].idxmin().date()),
    }


def _bucket_summary(joined: pd.DataFrame, mask: pd.Series) -> dict[str, Any]:
    rows = joined[mask.fillna(False)]
    out = _return_summary(rows)
    if rows.empty:
        out.update(
            {
                "actual_hedge_days": 0,
                "trigger_days": 0,
                "forward_mdd_h20_mean": None,
                "forward_gain_h20_mean": None,
            }
        )
        return out
    actual_hedge = rows["candidate_regime"].isin({NCF_LB_REGIME, NCF_LB_SOFT_REGIME})
    trigger = rows.get("ncf_trigger", pd.Series(False, index=rows.index)).fillna(False)
    out.update(
        {
            "actual_hedge_days": int(actual_hedge.sum()),
            "trigger_days": int(trigger.sum()),
            "forward_mdd_h20_mean": (
                float(rows["forward_mdd_h20"].dropna().mean())
                if "forward_mdd_h20" in rows and rows["forward_mdd_h20"].notna().any()
                else None
            ),
            "forward_gain_h20_mean": (
                float(rows["forward_gain_h20"].dropna().mean())
                if "forward_gain_h20" in rows and rows["forward_gain_h20"].notna().any()
                else None
            ),
        }
    )
    return out


def _build_joined(
    baseline_frame: pd.DataFrame,
    candidate_frame: pd.DataFrame,
    panel_path: Path | None,
    *,
    ma_gap_min: float,
    h20_max: float,
    conf_min: float,
) -> pd.DataFrame:
    joined = baseline_frame[["portfolio_value", "execution_regime", "ma_gap", "drawdown"]].join(
        candidate_frame[["portfolio_value", "execution_regime"]],
        how="inner",
        lsuffix="_baseline",
        rsuffix="_candidate",
    )
    joined = joined.rename(
        columns={
            "portfolio_value_baseline": "baseline_value",
            "portfolio_value_candidate": "candidate_value",
            "execution_regime_baseline": "baseline_regime",
            "execution_regime_candidate": "candidate_regime",
        }
    )
    joined["baseline_return"] = joined["baseline_value"].pct_change().fillna(0.0)
    joined["candidate_return"] = joined["candidate_value"].pct_change().fillna(0.0)
    joined["return_delta"] = joined["candidate_return"] - joined["baseline_return"]

    if panel_path and panel_path.exists():
        panel = pd.read_csv(panel_path, parse_dates=["date"]).set_index("date").sort_index()
        panel.index = pd.to_datetime(panel.index).normalize()
        cols = [
            "prob_up_h20",
            "h20_prob_up",
            "confidence",
            "prob_up_h5",
            "forward_mdd_h20",
            "forward_gain_h20",
        ]
        joined = joined.join(panel[[c for c in cols if c in panel.columns]], how="left")
        if "h20_prob_up" not in joined.columns and "prob_up_h20" in joined.columns:
            joined["h20_prob_up"] = joined["prob_up_h20"]
        joined["ncf_trigger"] = (
            (joined["baseline_regime"].astype(str) == "golden1")
            & (joined["ma_gap"].astype(float) > float(ma_gap_min))
            & (joined["h20_prob_up"].astype(float) < float(h20_max))
            & (joined["confidence"].astype(float) > float(conf_min))
        )
    else:
        joined["h20_prob_up"] = np.nan
        joined["confidence"] = np.nan
        joined["prob_up_h5"] = np.nan
        joined["forward_mdd_h20"] = np.nan
        joined["forward_gain_h20"] = np.nan
        joined["ncf_trigger"] = False
    return joined


def _bucket_report(joined: pd.DataFrame, *, h20_max: float, conf_min: float) -> dict[str, Any]:
    panel_available = joined["h20_prob_up"].notna()
    late_bull = (joined["baseline_regime"].astype(str) == "golden1") & (joined["ma_gap"] > 0.10)
    strong_bull = (joined["baseline_regime"].astype(str) == "golden1") & (joined["ma_gap"] > 0.10) & (joined["drawdown"] > -0.05)
    sideways = (joined["baseline_regime"].astype(str) == "golden1") & (joined["ma_gap"].abs() <= 0.03)
    high_conf = panel_available & (joined["confidence"] >= conf_min)
    low_conf = panel_available & (joined["confidence"] < conf_min)
    large_negative_h20 = panel_available & (joined["h20_prob_up"] < h20_max)
    marginal_h20 = panel_available & (joined["h20_prob_up"] >= h20_max) & (joined["h20_prob_up"] < 0.45)

    buckets = {
        "all_days": pd.Series(True, index=joined.index),
        "panel_available_days": panel_available,
        "late_bull_all": late_bull,
        "strong_bull": strong_bull,
        "sideways": sideways,
        "high_confidence": high_conf,
        "low_confidence": low_conf,
        "large_negative_h20": large_negative_h20,
        "marginal_h20_0p33_to_0p45": marginal_h20,
        "late_bull_high_conf_large_negative_h20": late_bull & high_conf & large_negative_h20,
        "late_bull_low_conf_large_negative_h20": late_bull & low_conf & large_negative_h20,
        "late_bull_high_conf_marginal_h20": late_bull & high_conf & marginal_h20,
        "actual_ncf_hedge_days": joined["candidate_regime"].isin({NCF_LB_REGIME, NCF_LB_SOFT_REGIME}),
        "trigger_condition_days": joined["ncf_trigger"].fillna(False),
    }
    return {name: _bucket_summary(joined, mask) for name, mask in buckets.items()}


def evaluate_window(
    name: str,
    start: str,
    end: str,
    *,
    db: Path,
    initial_value: float,
    manifest_params: dict[str, Any],
) -> dict[str, Any]:
    params = dict(manifest_params)
    panel_raw = params.pop("ncf_panel_631l_path", None)
    panel_path = Path(panel_raw) if panel_raw else None
    if panel_path and not panel_path.is_absolute():
        panel_path = Path.cwd() / panel_path

    common_kwargs = {
        "start": start,
        "end": end,
        "initial_value": initial_value,
        "db": db,
        "h20_max": float(params.get("h20_max", 0.33)),
        "conf_min": float(params.get("conf_min", 0.55)),
        "h5_reentry_min": float(params.get("h5_reentry_min", 0.55)),
        "chip_data_fallback_max_stale_days": params.get("chip_data_fallback_max_stale_days", 10),
        "risk_score_lookback_days": params.get("risk_score_lookback_days", 5),
        "momentum_fast_exit_min": params.get("momentum_fast_exit_min", 0.10),
        "momentum_fast_exit_ma_gap_min": params.get("momentum_fast_exit_ma_gap_min", -0.08),
        "exclude_zero_volume_rows": bool(params.get("exclude_zero_volume_rows", False)),
    }
    baseline_report, baseline_frame = run_a2118(ncf_panel_631l_path=None, **common_kwargs)
    candidate_report, candidate_frame = run_a2118(ncf_panel_631l_path=str(panel_path) if panel_path else None, **common_kwargs)

    joined = _build_joined(
        baseline_frame,
        candidate_frame,
        panel_path,
        ma_gap_min=0.10,
        h20_max=common_kwargs["h20_max"],
        conf_min=common_kwargs["conf_min"],
    )
    final_delta = float(candidate_frame["portfolio_value"].iloc[-1] - baseline_frame["portfolio_value"].iloc[-1])
    return {
        "window": {"name": name, "start": start, "end": end, "rows": int(len(joined))},
        "panel": {
            "path": str(panel_path) if panel_path else None,
            "available_rows_in_window": int(joined["h20_prob_up"].notna().sum()),
            "first_panel_date_in_window": (
                str(joined.index[joined["h20_prob_up"].notna()].min().date())
                if joined["h20_prob_up"].notna().any()
                else None
            ),
            "last_panel_date_in_window": (
                str(joined.index[joined["h20_prob_up"].notna()].max().date())
                if joined["h20_prob_up"].notna().any()
                else None
            ),
        },
        "baseline_metrics": _metrics(baseline_frame["portfolio_value"], initial_value),
        "candidate_metrics": _metrics(candidate_frame["portfolio_value"], initial_value),
        "candidate_minus_baseline": {
            "final_value_delta": final_delta,
            "total_return_delta": float(
                candidate_frame["portfolio_value"].iloc[-1] / baseline_frame["portfolio_value"].iloc[-1] - 1.0
            ),
            "regime_different_days": int((joined["baseline_regime"] != joined["candidate_regime"]).sum()),
            "actual_ncf_hedge_days": int(joined["candidate_regime"].isin({NCF_LB_REGIME, NCF_LB_SOFT_REGIME}).sum()),
            "trigger_condition_days": int(joined["ncf_trigger"].fillna(False).sum()),
        },
        "buckets": _bucket_report(
            joined,
            h20_max=common_kwargs["h20_max"],
            conf_min=common_kwargs["conf_min"],
        ),
        "trigger_events": [
            {
                "date": str(dt.date()),
                "ma_gap": round(float(row["ma_gap"]), 4),
                "drawdown": round(float(row["drawdown"]), 4),
                "h20_prob_up": round(float(row["h20_prob_up"]), 4),
                "confidence": round(float(row["confidence"]), 4),
                "prob_up_h5": round(float(row["prob_up_h5"]), 4) if pd.notna(row.get("prob_up_h5")) else None,
                "candidate_regime": str(row["candidate_regime"]),
                "return_delta": float(row["return_delta"]),
                "forward_mdd_h20": float(row["forward_mdd_h20"]) if pd.notna(row.get("forward_mdd_h20")) else None,
                "forward_gain_h20": float(row["forward_gain_h20"]) if pd.notna(row.get("forward_gain_h20")) else None,
            }
            for dt, row in joined[joined["ncf_trigger"].fillna(False)].iterrows()
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    manifest_params = _load_manifest_params(Path(args.manifest))
    report = {
        "schema_version": 1,
        "report_type": "a2118_ncf_overlay_bucket_attribution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "active_allocation_impact": "none",
        "question": "Does the A21.18 NCF late-bull overlay add net value by market state and NCF confidence/H20 buckets?",
        "manifest": str(Path(args.manifest)),
        "manifest_runner_params": manifest_params,
        "windows": [
            evaluate_window(
                name,
                start,
                end,
                db=Path(args.db),
                initial_value=args.initial_value,
                manifest_params=manifest_params,
            )
            for name, (start, end) in DEFAULT_WINDOWS.items()
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"A21.18 NCF overlay bucket attribution: {output.resolve()}")


if __name__ == "__main__":
    main()
