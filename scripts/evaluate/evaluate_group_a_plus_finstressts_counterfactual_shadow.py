#!/usr/bin/env python3
"""FinStressTS-style counterfactual stress shadow for GroupA+ fixed weights.

Research-only harness inspired by 2606.03184. It does not train a synthetic
alpha model. It perturbs the historical 0050/00631L return panel into a few
mechanism-specific stress scenarios and compares fixed GroupA+ candidate
allocations on tail-risk metrics.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results/group_a_plus_finstressts_counterfactual_shadow_20260717.json"
DEFAULT_LATEST = PROJECT_ROOT / "report/group_a_plus/latest/finstressts_counterfactual_shadow.json"

PORTFOLIOS: dict[str, dict[str, float]] = {
    "reference_20260720": {"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30},
    "no_00631l_reference_cash": {"0050.TW": 0.50, "00631L.TW": 0.00, "cash": 0.50},
    "0050_only_full": {"0050.TW": 1.00, "00631L.TW": 0.00, "cash": 0.00},
    "reduced_leverage": {"0050.TW": 0.70, "00631L.TW": 0.10, "cash": 0.20},
    "cash": {"0050.TW": 0.00, "00631L.TW": 0.00, "cash": 1.00},
}


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _load_close_panel(db_path: Path, start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, ticker, close
            FROM ohlcv
            WHERE ticker IN ('0050.TW', '00631L.TW')
              AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV close data from {start} to {end}")
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    close = rows.pivot(index="dt", columns="ticker", values="close").sort_index()
    close = close.dropna(subset=["0050.TW", "00631L.TW"])
    if close.empty:
        raise RuntimeError("No overlapping 0050/00631L close data after alignment")
    return close.astype(float)


def _returns(close: pd.DataFrame) -> pd.DataFrame:
    return close.pct_change().replace([np.inf, -np.inf], np.nan).dropna(how="any")


def _scenario_baseline(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.copy()


def _scenario_heavy_tail(returns: pd.DataFrame) -> pd.DataFrame:
    stressed = returns.copy()
    losses = stressed.min(axis=1)
    threshold = float(losses.quantile(0.05))
    mask = losses <= threshold
    stressed.loc[mask] = stressed.loc[mask] * 1.75
    stressed["00631L.TW"] = stressed["00631L.TW"].clip(lower=-0.22, upper=0.22)
    stressed["0050.TW"] = stressed["0050.TW"].clip(lower=-0.11, upper=0.11)
    return stressed


def _scenario_regime_switch_down(returns: pd.DataFrame) -> pd.DataFrame:
    stressed = returns.copy()
    windows = [(160, 25), (760, 30), (1380, 25), (2140, 20)]
    neg_pool = returns[returns["0050.TW"] <= returns["0050.TW"].quantile(0.25)]
    template = neg_pool[["0050.TW", "00631L.TW"]].mean()
    for start, length in windows:
        if start >= len(stressed):
            continue
        end = min(len(stressed), start + length)
        ramp = np.linspace(1.00, 1.35, end - start)
        stressed.iloc[start:end, stressed.columns.get_loc("0050.TW")] = float(template["0050.TW"]) * ramp
        stressed.iloc[start:end, stressed.columns.get_loc("00631L.TW")] = float(template["00631L.TW"]) * ramp * 1.15
    return stressed.clip(lower={"0050.TW": -0.10, "00631L.TW": -0.20}, upper={"0050.TW": 0.10, "00631L.TW": 0.20})


def _scenario_self_exciting_jumps(returns: pd.DataFrame) -> pd.DataFrame:
    stressed = returns.copy()
    cluster_starts = [220, 690, 1210, 1780, 2400]
    for start in cluster_starts:
        if start >= len(stressed):
            continue
        length = min(5, len(stressed) - start)
        decay = np.array([1.00, 0.80, 0.65, 0.50, 0.35], dtype=float)[:length]
        stressed.iloc[start : start + length, stressed.columns.get_loc("0050.TW")] += -0.030 * decay
        stressed.iloc[start : start + length, stressed.columns.get_loc("00631L.TW")] += -0.065 * decay
    return stressed.clip(lower={"0050.TW": -0.12, "00631L.TW": -0.24}, upper={"0050.TW": 0.12, "00631L.TW": 0.24})


def _scenario_zero_inflated_sparse_jumps(returns: pd.DataFrame) -> pd.DataFrame:
    stressed = returns.copy() * 0.35
    jump_idx = [180, 520, 970, 1430, 1900, 2280, 2600]
    for idx in jump_idx:
        if idx >= len(stressed):
            continue
        stressed.iloc[idx, stressed.columns.get_loc("0050.TW")] = -0.060
        stressed.iloc[idx, stressed.columns.get_loc("00631L.TW")] = -0.125
    return stressed


SCENARIOS = {
    "historical_baseline": _scenario_baseline,
    "heavy_tailed_shocks": _scenario_heavy_tail,
    "regime_switch_down": _scenario_regime_switch_down,
    "self_exciting_jumps": _scenario_self_exciting_jumps,
    "zero_inflated_sparse_jumps": _scenario_zero_inflated_sparse_jumps,
}


def _portfolio_returns(asset_returns: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    out = pd.Series(0.0, index=asset_returns.index)
    for ticker, weight in weights.items():
        if ticker == "cash":
            continue
        out = out + float(weight) * asset_returns[ticker].fillna(0.0)
    return out


def _max_drawdown(returns: pd.Series) -> float:
    wealth = (1.0 + returns).cumprod()
    dd = wealth / wealth.cummax() - 1.0
    return float(dd.min())


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
        "var_loss_95": float(np.quantile(losses, 0.95)) if len(losses) else None,
        "expected_shortfall_loss_95": es95,
        "starr_95": None if not ann_ret or not es95 else float(ann_ret / es95),
        "days_loss_gt_2pct": int((clean <= -0.02).sum()),
        "days_loss_gt_3pct": int((clean <= -0.03).sum()),
    }


def evaluate_counterfactuals(close: pd.DataFrame) -> dict[str, Any]:
    base_returns = _returns(close)
    scenario_results: dict[str, Any] = {}
    reference_loses_to_no_add = 0
    reference_tail_failures = 0

    for scenario_name, transform in SCENARIOS.items():
        scenario_returns = transform(base_returns)
        portfolios = {
            name: _summarize(_portfolio_returns(scenario_returns, weights))
            for name, weights in PORTFOLIOS.items()
        }
        reference = portfolios["reference_20260720"]
        no_add = portfolios["no_00631l_reference_cash"]
        ref_es = reference["expected_shortfall_loss_95"]
        no_add_es = no_add["expected_shortfall_loss_95"]
        ref_mdd = reference["max_drawdown"]
        no_add_mdd = no_add["max_drawdown"]
        loses_to_no_add = bool(
            ref_es is not None
            and no_add_es is not None
            and ref_mdd is not None
            and no_add_mdd is not None
            and (ref_es > no_add_es or abs(ref_mdd) > abs(no_add_mdd))
        )
        tail_failure = bool((ref_es or 0.0) >= 0.025 or abs(ref_mdd or 0.0) >= 0.35)
        reference_loses_to_no_add += int(loses_to_no_add)
        reference_tail_failures += int(tail_failure)
        scenario_results[scenario_name] = {
            "portfolios": portfolios,
            "reference_vs_no_00631l": {
                "reference_has_higher_tail_risk_or_drawdown": loses_to_no_add,
                "reference_es95_minus_no_add_es95": None if ref_es is None or no_add_es is None else float(ref_es - no_add_es),
                "reference_mdd_abs_minus_no_add_mdd_abs": None
                if ref_mdd is None or no_add_mdd is None
                else float(abs(ref_mdd) - abs(no_add_mdd)),
            },
            "reference_tail_failure": tail_failure,
        }

    promote = reference_loses_to_no_add == 0 and reference_tail_failures == 0
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_finstressts_counterfactual_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_counterfactual_stress_no_weight_change",
        "source_paper": "C:/Users/isaac/Downloads/2606.03184.pdf",
        "input_window": {
            "start": str(base_returns.index.min().date()),
            "end": str(base_returns.index.max().date()),
            "rows": int(len(base_returns)),
        },
        "portfolios": PORTFOLIOS,
        "scenarios": scenario_results,
        "decision": {
            "summary": (
                "Reference 7/20 weights do not pass the FinStressTS-style counterfactual stress review "
                "against the no-00631L reference."
            )
            if not promote
            else "Reference 7/20 weights pass this narrow counterfactual stress review for manual review only.",
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "keep_golden1_0531_unchanged": True,
            "reference_loses_to_no_00631l_scenarios": int(reference_loses_to_no_add),
            "reference_tail_failure_scenarios": int(reference_tail_failures),
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
    report = evaluate_counterfactuals(close)
    latest = None if args.no_latest else _resolve(args.latest)
    write_report(report, _resolve(args.output), latest)
    print(f"FinStressTS counterfactual shadow: {_resolve(args.output)}")
    if latest is not None:
        print(f"Latest pointer: {latest}")
    print(
        json.dumps(
            {
                "reference_loses_to_no_00631l_scenarios": report["decision"]["reference_loses_to_no_00631l_scenarios"],
                "reference_tail_failure_scenarios": report["decision"]["reference_tail_failure_scenarios"],
                "allow_00631l_add": report["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
