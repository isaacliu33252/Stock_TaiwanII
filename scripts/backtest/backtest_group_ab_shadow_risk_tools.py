#!/usr/bin/env python3
"""Shadow-test Taiwan turbulence, benchmark gate, impact cost, and promotion gate."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from backtest_group_ab_hold10_research import _load_hold10_ab
from finrl_meta_strategy_governance import ABGovernanceParams, StressGateParams, metrics, resolve_project_path, simulate_ab_governed


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_GROUP_A_SWEEP = PROJECT_ROOT / "results" / "group_a_00632r_dca_sweep_20240102_20260604_curve.csv"
DEFAULT_BASE_AB = PROJECT_ROOT / "results" / "group_ab_latest_no2884_backtest_20240101_20260605_curve.csv"
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_ab_shadow_risk_tools_20240102_20260604.json"
TURBULENCE_TICKERS = ["0050.TW", "00631L.TW", "00632R.TW"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-a-sweep-csv", default=str(DEFAULT_GROUP_A_SWEEP))
    parser.add_argument("--base-ab-curve-csv", default=str(DEFAULT_BASE_AB))
    parser.add_argument("--group-a-variant", default="hold_limit_00632r_10d_to_0050")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def _load_ohlcv(db_path: Path, tickers: list[str], start: str, end: str) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, ticker, close, volume
            FROM ohlcv
            WHERE ticker IN (SELECT * FROM UNNEST(?)) AND dt BETWEEN ? AND ?
            ORDER BY dt, ticker
            """,
            [tickers, start, end],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No OHLCV rows for {tickers} between {start} and {end}")
    rows["dt"] = pd.to_datetime(rows["dt"])
    return rows


def _turbulence_index(prices: pd.DataFrame, *, window: int = 252, min_periods: int = 126) -> pd.Series:
    returns = prices.pct_change().dropna(how="all").fillna(0.0)
    values = []
    for i, date in enumerate(returns.index):
        if i < min_periods:
            values.append((date, 0.0))
            continue
        start = max(0, i - window)
        hist = returns.iloc[start:i]
        diff = returns.iloc[i] - hist.mean()
        cov = hist.cov()
        inv_cov = np.linalg.pinv(cov.values)
        turb = float(diff.values @ inv_cov @ diff.values.T)
        values.append((date, max(turb, 0.0)))
    return pd.Series([v for _, v in values], index=[d for d, _ in values], dtype=float).shift(1).fillna(0.0)


def _sqrt_impact_cost(notional: float, daily_dollar_volume: float, volatility: float, *, y: float = 0.6) -> float:
    if notional <= 0.0 or daily_dollar_volume <= 0.0 or volatility <= 0.0:
        return 0.0
    participation = min(abs(notional) / daily_dollar_volume, 1.0)
    peak_frac = y * volatility * math.sqrt(participation)
    return float((2.0 / 3.0) * peak_frac * abs(notional))


def _apply_target_overlay(
    ab: pd.DataFrame,
    base_targets: pd.Series,
    risk: pd.DataFrame,
    *,
    name: str,
    turbulence_cap: float | None,
    benchmark_cap: float | None,
) -> tuple[pd.Series, list[dict[str, Any]], pd.DataFrame]:
    params = ABGovernanceParams(strategy_name=name, stress_gate=StressGateParams(enabled=False))
    targets = base_targets.copy().astype(float)
    if turbulence_cap is not None:
        targets[risk["turbulence_state"].eq("risk_off")] = targets[risk["turbulence_state"].eq("risk_off")].clip(upper=turbulence_cap)
    if benchmark_cap is not None:
        targets[risk["benchmark_relative_state"].eq("underperform")] = targets[risk["benchmark_relative_state"].eq("underperform")].clip(upper=benchmark_cap)

    a_returns = ab["group_a_value"].pct_change().fillna(0.0)
    b_returns = ab["group_b_value"].pct_change().fillna(0.0)
    a_value = params.initial_capital * float(targets.iloc[0])
    b_value = params.initial_capital * (1.0 - float(targets.iloc[0]))
    last_target = float(targets.iloc[0])
    last_rebalance = None
    previous = None
    events: list[dict[str, Any]] = []
    curve = []
    for date in ab.index:
        a_value *= 1.0 + float(a_returns.loc[date])
        b_value *= 1.0 + float(b_returns.loc[date])
        total = a_value + b_value
        current_a = a_value / total if total > 0 else 0.0
        target_a = float(targets.loc[date])
        target_changed = abs(target_a - last_target) > 1e-12
        calendar = previous is None or date.year != previous.year or (date.month - 1) // 3 != (previous.month - 1) // 3
        drift = abs(current_a - target_a) >= params.drift_threshold
        transfer = abs(total * target_a - a_value)
        cooldown = last_rebalance is None or (date - last_rebalance).days >= params.cooldown_days
        if (target_changed or calendar or drift) and transfer >= params.min_transfer_notional and cooldown:
            cost = transfer * (params.cost.commission_rate + params.cost.slippage_rate)
            sell_notional = max(a_value - total * target_a, 0.0)
            cost += sell_notional * params.cost.sell_tax_rate
            total -= cost
            a_value = total * target_a
            b_value = total * (1.0 - target_a)
            events.append(
                {
                    "date": str(date.date()),
                    "reason": "target_change" if target_changed else ("calendar" if calendar else "drift"),
                    "turbulence_state": str(risk.loc[date, "turbulence_state"]),
                    "benchmark_relative_state": str(risk.loc[date, "benchmark_relative_state"]),
                    "pre_group_a_weight": float(current_a),
                    "target_group_a_weight": target_a,
                    "transfer_notional": float(transfer),
                    "sell_notional": float(sell_notional),
                    "total_cost": float(cost),
                }
            )
            last_target = target_a
            last_rebalance = date
        curve.append((date, a_value + b_value))
        previous = date
    diagnostic = risk.copy()
    diagnostic["target_a_weight"] = targets
    return pd.Series([v for _, v in curve], index=[d for d, _ in curve], dtype=float), events, diagnostic


def _promotion_gate(
    rows: list[dict[str, Any]],
    *,
    group_a_2008_json: Path,
    min_sharpe: float = 2.50,
    max_mdd: float = -0.20,
) -> dict[str, Any]:
    best = max(rows, key=lambda row: (row["sharpe_ratio"], row["final_value"]))
    checks = [
        {"name": "2024_2026_sharpe", "passed": bool(best["sharpe_ratio"] >= min_sharpe), "value": best["sharpe_ratio"], "threshold": min_sharpe},
        {"name": "2024_2026_mdd", "passed": bool(best["max_drawdown"] >= max_mdd), "value": best["max_drawdown"], "threshold": max_mdd},
    ]
    if group_a_2008_json.exists():
        stress = json.loads(group_a_2008_json.read_text(encoding="utf-8"))
        baseline = stress.get("best", {}).get("best_final", {})
        checks.append(
            {
                "name": "group_a_2008_keeps_00632r_baseline_best",
                "passed": str(baseline.get("variant")) == "baseline_payload",
                "value": baseline.get("variant"),
                "threshold": "baseline_payload",
            }
        )
    return {"candidate": best["variant"], "passed": all(item["passed"] for item in checks), "checks": checks}


def main() -> None:
    args = _parse_args()
    output = resolve_project_path(PROJECT_ROOT, args.output)
    ab = _load_hold10_ab(
        resolve_project_path(PROJECT_ROOT, args.group_a_sweep_csv),
        resolve_project_path(PROJECT_ROOT, args.base_ab_curve_csv),
        str(args.group_a_variant),
    )
    db_path = resolve_project_path(PROJECT_ROOT, args.db)
    ohlcv = _load_ohlcv(db_path, TURBULENCE_TICKERS, str(ab.index[0].date()), str(ab.index[-1].date()))
    closes = ohlcv.pivot(index="dt", columns="ticker", values="close").reindex(ab.index).ffill()
    volumes = ohlcv.pivot(index="dt", columns="ticker", values="volume").reindex(ab.index).ffill()
    dollar_volume_0050 = (closes["0050.TW"] * volumes["0050.TW"]).replace(0, np.nan).ffill()
    turbulence = _turbulence_index(closes)
    turb_threshold = turbulence.rolling(252, min_periods=126).quantile(0.95).fillna(turbulence.quantile(0.95))

    base_params = ABGovernanceParams(strategy_name="base_dynamic_no_stress_for_shadow", stress_gate=StressGateParams(enabled=False))
    base_curve, base_events, base_diag = simulate_ab_governed(ab, base_params)
    benchmark = 2_000_000.0 * (closes["0050.TW"] / closes["0050.TW"].iloc[0])
    relative = (base_curve / base_curve.iloc[0]) / (benchmark / benchmark.iloc[0]) - 1.0
    relative_lag = relative.shift(1).fillna(0.0)
    base_targets = base_diag["target_a_weight"].astype(float)

    risk = pd.DataFrame(index=ab.index)
    risk["turbulence"] = turbulence.reindex(ab.index).fillna(0.0)
    risk["turbulence_threshold_95"] = turb_threshold.reindex(ab.index).ffill().fillna(float(turbulence.quantile(0.95)))
    risk["turbulence_state"] = np.where(risk["turbulence"] >= risk["turbulence_threshold_95"], "risk_off", "normal")
    risk["relative_vs_0050_lag1"] = relative_lag
    risk["benchmark_relative_state"] = np.where(relative_lag <= -0.10, "underperform", "normal")

    variants = [
        ("base_dynamic_no_stress", None, None),
        ("turbulence_cap55_shadow", 0.55, None),
        ("benchmark_underperf_cap55_shadow", None, 0.55),
        ("turbulence_or_benchmark_cap55_shadow", 0.55, 0.55),
    ]
    rows: list[dict[str, Any]] = []
    curves = pd.DataFrame(index=ab.index)
    diagnostics: dict[str, Any] = {}
    impact_rows = []
    for name, turb_cap, bench_cap in variants:
        if name == "base_dynamic_no_stress":
            curve, events, diag = base_curve, base_events, base_diag.join(risk, how="left")
        else:
            curve, events, diag = _apply_target_overlay(ab, base_targets, risk, name=name, turbulence_cap=turb_cap, benchmark_cap=bench_cap)
        shadow_impact_cost = 0.0
        returns_0050 = closes["0050.TW"].pct_change().rolling(21).std().fillna(closes["0050.TW"].pct_change().std())
        for event in events:
            dt = pd.Timestamp(event["date"])
            impact = _sqrt_impact_cost(
                float(event["transfer_notional"]),
                float(dollar_volume_0050.loc[dt]),
                float(returns_0050.loc[dt]),
            )
            shadow_impact_cost += impact
            impact_rows.append({"variant": name, **event, "sqrt_impact_cost_estimate": impact})
        row = {
            "variant": name,
            **metrics(curve, events=len(events), total_cost=sum(float(e.get("total_cost", 0.0)) for e in events)),
            "sqrt_impact_cost_estimate": float(shadow_impact_cost),
            "turbulence_risk_off_days": int(risk["turbulence_state"].eq("risk_off").sum()),
            "benchmark_underperform_days": int(risk["benchmark_relative_state"].eq("underperform").sum()),
        }
        rows.append(row)
        curves[name] = curve
        diagnostics[name] = {
            "target_counts": {str(k): int(v) for k, v in diag["target_a_weight"].value_counts().sort_index().to_dict().items()},
            "events": events,
        }
        print(
            f"{name}: final={row['final_value']:.2f}, sharpe={row['sharpe_ratio']:.4f}, "
            f"mdd={row['max_drawdown']:.4%}, impact={row['sqrt_impact_cost_estimate']:.2f}",
            flush=True,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    curve_path = output.with_name(output.stem + "_curve.csv")
    risk_path = output.with_name(output.stem + "_risk_diagnostic.csv")
    impact_path = output.with_name(output.stem + "_impact_log.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    curves.index.name = "date"
    curves.to_csv(curve_path, encoding="utf-8-sig")
    risk.index.name = "date"
    risk.to_csv(risk_path, encoding="utf-8-sig")
    pd.DataFrame(impact_rows).to_csv(impact_path, index=False, encoding="utf-8-sig")
    promotion = _promotion_gate(rows, group_a_2008_json=PROJECT_ROOT / "results" / "group_a_twii_proxy_2008_inverse_sweep_20070701_20101231.json")
    report = {
        "experiment": "group_ab_shadow_risk_tools",
        "method_note": "Shadow import of Taiwan turbulence, benchmark-relative gate, sqrt market impact cost, and promotion gate. Does not replace the main strategy.",
        "window": {"start": str(ab.index[0].date()), "end": str(ab.index[-1].date()), "rows": int(len(ab))},
        "results": rows,
        "promotion_gate": promotion,
        "diagnostics": diagnostics,
        "outputs": {"json": str(output), "csv": str(csv_path), "curve_csv": str(curve_path), "risk_diagnostic_csv": str(risk_path), "impact_log_csv": str(impact_path)},
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"CSV: {csv_path}")
    print(f"Risk diagnostic: {risk_path}")
    print(f"Promotion passed: {promotion['passed']}")


if __name__ == "__main__":
    main()
