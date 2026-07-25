#!/usr/bin/env python3
"""Compare simple GroupA+ baselines under FinStressTS-style scenarios.

Research-only follow-up to the fixed-weight counterfactual shadow. It compares
the 7/20 reference weights, no-00631L, reduced leverage, and two transparent
dynamic gates under the same mechanism-specific stress scenarios. No live
allocation or strategy manifest is changed.
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

from scripts.evaluate.evaluate_group_a_plus_finstressts_counterfactual_shadow import (  # noqa: E402
    DB_PATH,
    SCENARIOS,
    _load_close_panel,
    _max_drawdown,
    _returns,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results/group_a_plus_finstressts_baseline_compare_shadow_20260717.json"
DEFAULT_LATEST = PROJECT_ROOT / "report/group_a_plus/latest/finstressts_baseline_compare_shadow.json"

STATIC_PORTFOLIOS: dict[str, dict[str, float]] = {
    "reference_20260720": {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30},
    "no_00631l_reference_cash": {"0050.TW": 0.50, "00631L.TW": 0.00, "cash": 0.50},
    "reduced_leverage": {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _expected_shortfall_loss(losses: np.ndarray, confidence: float) -> float | None:
    clean = losses[np.isfinite(losses)]
    if len(clean) == 0:
        return None
    var = float(np.quantile(clean, confidence))
    tail = clean[clean >= var]
    return float(np.mean(tail)) if len(tail) else var


def _summarize(returns: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    losses = -clean.to_numpy(dtype=float)
    ann_ret = float((1.0 + clean).prod() ** (252.0 / len(clean)) - 1.0) if len(clean) else None
    ann_vol = float(clean.std(ddof=1) * np.sqrt(252.0)) if len(clean) > 1 else None
    es95 = _expected_shortfall_loss(losses, 0.95)
    mdd = _max_drawdown(clean) if len(clean) else None
    return {
        "rows": int(len(clean)),
        "cumulative_return": float((1.0 + clean).prod() - 1.0) if len(clean) else None,
        "annualized_return": ann_ret,
        "annualized_volatility": ann_vol,
        "max_drawdown": mdd,
        "expected_shortfall_loss_95": es95,
        "starr_95": None if not ann_ret or not es95 else float(ann_ret / es95),
        "days_loss_gt_2pct": int((clean <= -0.02).sum()),
        "days_loss_gt_3pct": int((clean <= -0.03).sum()),
    }


def _static_returns(asset_returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    out = pd.Series(0.0, index=asset_returns.index)
    for ticker, weight in weights.items():
        if ticker == "cash":
            continue
        out = out + float(weight) * asset_returns[ticker].fillna(0.0)
    return out


def _synthetic_close(asset_returns: pd.DataFrame) -> pd.DataFrame:
    return (1.0 + asset_returns).cumprod()


def _dynamic_gate_returns(asset_returns: pd.DataFrame, mode: str) -> tuple[pd.Series, dict[str, Any]]:
    close = _synthetic_close(asset_returns)
    ret20 = close["00631L.TW"].pct_change(20)
    ma60 = close["00631L.TW"].rolling(60, min_periods=20).mean()
    vol20 = asset_returns["00631L.TW"].rolling(20, min_periods=10).std()
    vol_percentile = vol20.rolling(252, min_periods=60).rank(pct=True)

    if mode == "rolling_vol_gate":
        no_add = vol_percentile >= 0.80
    elif mode == "trend_gate":
        no_add = (close["00631L.TW"] < ma60) | (ret20 < 0.0)
    elif mode == "combined_vol_trend_gate":
        no_add = (vol_percentile >= 0.80) | (close["00631L.TW"] < ma60) | (ret20 < 0.0)
    else:
        raise ValueError(f"Unsupported dynamic mode: {mode}")

    no_add = no_add.fillna(False)
    reference = _static_returns(asset_returns, STATIC_PORTFOLIOS["reference_20260720"])
    defensive = _static_returns(asset_returns, STATIC_PORTFOLIOS["no_00631l_reference_cash"])
    out = reference.where(~no_add, defensive)
    metadata = {
        "active_no_add_days": int(no_add.sum()),
        "active_no_add_rate": float(no_add.mean()),
        "mode": mode,
    }
    return out.rename(mode), metadata


def evaluate_baselines(close: pd.DataFrame) -> dict[str, Any]:
    base_returns = _returns(close)
    scenario_results: dict[str, Any] = {}
    wins_vs_no_add: dict[str, int] = {
        "reference_20260720": 0,
        "reduced_leverage": 0,
        "rolling_vol_gate": 0,
        "trend_gate": 0,
        "combined_vol_trend_gate": 0,
    }
    tail_failures: dict[str, int] = {name: 0 for name in wins_vs_no_add}

    for scenario_name, transform in SCENARIOS.items():
        scenario_returns = transform(base_returns)
        portfolio_returns: dict[str, tuple[pd.Series, dict[str, Any]]] = {}
        for name, weights in STATIC_PORTFOLIOS.items():
            portfolio_returns[name] = (_static_returns(scenario_returns, weights), {"mode": "static", "weights": weights})
        for mode in ("rolling_vol_gate", "trend_gate", "combined_vol_trend_gate"):
            portfolio_returns[mode] = _dynamic_gate_returns(scenario_returns, mode)

        summaries = {name: _summarize(series) | {"metadata": metadata} for name, (series, metadata) in portfolio_returns.items()}
        no_add = summaries["no_00631l_reference_cash"]
        no_add_es = float(no_add["expected_shortfall_loss_95"] or np.inf)
        no_add_mdd_abs = abs(float(no_add["max_drawdown"] or 0.0))

        comparisons: dict[str, Any] = {}
        for name in wins_vs_no_add:
            row = summaries[name]
            es = float(row["expected_shortfall_loss_95"] or np.inf)
            mdd_abs = abs(float(row["max_drawdown"] or 0.0))
            wins = es <= no_add_es and mdd_abs <= no_add_mdd_abs
            tail_fail = es >= 0.025 or mdd_abs >= 0.35
            wins_vs_no_add[name] += int(wins)
            tail_failures[name] += int(tail_fail)
            comparisons[name] = {
                "beats_no_00631l_on_es95_and_mdd": bool(wins),
                "es95_minus_no_00631l": float(es - no_add_es),
                "mdd_abs_minus_no_00631l": float(mdd_abs - no_add_mdd_abs),
                "tail_failure": bool(tail_fail),
            }

        scenario_results[scenario_name] = {
            "summaries": summaries,
            "comparisons_vs_no_00631l": comparisons,
        }

    best_candidate = min(
        wins_vs_no_add,
        key=lambda name: (-wins_vs_no_add[name], tail_failures[name], name),
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_finstressts_baseline_compare_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_baseline_compare_no_weight_change",
        "source_paper": "C:/Users/isaac/Downloads/2606.03184.pdf",
        "input_window": {
            "start": str(base_returns.index.min().date()),
            "end": str(base_returns.index.max().date()),
            "rows": int(len(base_returns)),
        },
        "scenario_count": int(len(SCENARIOS)),
        "wins_vs_no_00631l": wins_vs_no_add,
        "tail_failures": tail_failures,
        "best_shadow_candidate": best_candidate,
        "scenarios": scenario_results,
        "decision": {
            "summary": (
                "No tested baseline is promoted. The comparison is useful for research, but no rule "
                "beats no-00631L cleanly enough to unlock 00631L add or rebalance."
            ),
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def write_report(report: dict[str, Any], output: Path, latest: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if latest is not None:
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="2026-07-17")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--latest", default=str(DEFAULT_LATEST))
    parser.add_argument("--no-latest", action="store_true")
    args = parser.parse_args()

    close = _load_close_panel(_resolve(args.db), args.start, args.end)
    report = evaluate_baselines(close)
    latest = None if args.no_latest else _resolve(args.latest)
    write_report(report, _resolve(args.output), latest)
    print(f"FinStressTS baseline compare shadow: {_resolve(args.output)}")
    if latest is not None:
        print(f"Latest pointer: {latest}")
    print(
        json.dumps(
            {
                "best_shadow_candidate": report["best_shadow_candidate"],
                "wins_vs_no_00631l": report["wins_vs_no_00631l"],
                "tail_failures": report["tail_failures"],
                "allow_00631l_add": report["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
