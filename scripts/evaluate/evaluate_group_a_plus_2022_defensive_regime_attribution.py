#!/usr/bin/env python3
"""Research-only attribution for GroupA+ 2022 defensive-regime losses."""

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

from backtest_group_a_plus_defensive_basket import _load_total_return_prices, _simulate_costed_curve
from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics
from group_a_plus.runners.latest import run_latest
from scripts.evaluate.sweep_group_a_plus_conditional_defensive_cash_floor import _clean_metric_delta


def _move_weight(weights: dict[str, float], source: str, dest: str) -> dict[str, float]:
    adjusted = dict(weights)
    moved = float(adjusted.get(source, 0.0) or 0.0)
    adjusted[source] = 0.0
    adjusted[dest] = float(adjusted.get(dest, 0.0) or 0.0) + moved
    return _normalize(adjusted)


def _defensive_variants(base_weights: dict[str, dict[str, float]]) -> dict[str, dict[str, dict[str, float]]]:
    defensive = _normalize(base_weights["group_a_plus_defensive"])
    recovery = _normalize(base_weights.get("group_a_plus_recovery", defensive))
    variants: dict[str, dict[str, dict[str, float]]] = {}

    def clone() -> dict[str, dict[str, float]]:
        return {name: _normalize(weights) for name, weights in base_weights.items()}

    # Codex 2026-08-14: attribution-only variants. These isolate whether the
    # 2022 defensive loss came from bond exposure, equity exposure, cash level,
    # or recovery timing. They must not be promoted directly to live weights.
    weights = clone()
    weights["group_a_plus_defensive"] = _move_weight(defensive, "00679B.TWO", "cash")
    variants["defensive_bond_to_cash"] = weights

    weights = clone()
    weights["group_a_plus_defensive"] = _move_weight(defensive, "00679B.TWO", "0050.TW")
    variants["defensive_bond_to_0050"] = weights

    weights = clone()
    weights["group_a_plus_defensive"] = _normalize({"cash": 1.0})
    variants["defensive_all_cash"] = weights

    weights = clone()
    weights["group_a_plus_defensive"] = _normalize({"0050.TW": 0.70, "cash": 0.30})
    variants["defensive_0050_70_cash30"] = weights

    weights = clone()
    weights["group_a_plus_defensive"] = _normalize({"00679B.TWO": 0.30, "cash": 0.70})
    variants["defensive_bond30_cash70"] = weights

    weights = clone()
    weights["group_a_plus_recovery"] = defensive
    weights["group_a_plus_recovery_00631l_boost"] = defensive
    variants["recovery_replaced_by_defensive"] = weights

    weights = clone()
    weights["group_a_plus_recovery"] = recovery
    weights["group_a_plus_defensive"] = recovery
    variants["defensive_replaced_by_recovery"] = weights

    return variants


def _regime_variants(frame: pd.DataFrame) -> dict[str, pd.Series]:
    regime = frame["execution_regime"].astype(str)
    out = {"baseline": regime.copy()}
    out["defensive_to_cash_regime"] = regime.mask(regime == "group_a_plus_defensive", "attribution_cash_only")
    out["defensive_to_golden1"] = regime.mask(regime == "group_a_plus_defensive", "golden1")
    out["recovery_to_defensive_regime"] = regime.mask(regime.str.startswith("group_a_plus_recovery"), "group_a_plus_defensive")
    out["recovery_to_golden1"] = regime.mask(regime.str.startswith("group_a_plus_recovery"), "golden1")
    return out


def _episode_rows(frame: pd.DataFrame, total_return_prices: pd.DataFrame) -> list[dict[str, Any]]:
    regime = frame["execution_regime"].astype(str)
    active = regime.isin(["group_a_plus_defensive", "group_a_plus_recovery", "group_a_plus_recovery_00631l_boost"])
    rows: list[dict[str, Any]] = []
    start: pd.Timestamp | None = None
    episode_id = 0
    for dt, is_active in active.items():
        if is_active and start is None:
            start = pd.Timestamp(dt)
        elif not is_active and start is not None:
            end = pd.Timestamp(active.index[active.index.get_loc(dt) - 1])
            episode_id += 1
            rows.append(_episode_summary(episode_id, start, end, frame, total_return_prices))
            start = None
    if start is not None:
        episode_id += 1
        rows.append(_episode_summary(episode_id, start, pd.Timestamp(active.index[-1]), frame, total_return_prices))
    return rows


def _episode_summary(
    episode_id: int,
    start: pd.Timestamp,
    end: pd.Timestamp,
    frame: pd.DataFrame,
    total_return_prices: pd.DataFrame,
) -> dict[str, Any]:
    segment = frame.loc[start:end]
    prices = total_return_prices.loc[start:end]
    ticker_returns = {
        ticker: float(prices[ticker].iloc[-1] / prices[ticker].iloc[0] - 1.0)
        for ticker in TICKERS
    }
    portfolio_return = float(segment["portfolio_value"].iloc[-1] / segment["portfolio_value"].iloc[0] - 1.0)
    return {
        "episode": int(episode_id),
        "start": str(start.date()),
        "end": str(end.date()),
        "trading_days": int(len(segment)),
        "regime_counts": {str(k): int(v) for k, v in segment["execution_regime"].astype(str).value_counts().to_dict().items()},
        "portfolio_return": portfolio_return,
        "ticker_total_returns": ticker_returns,
        "min_drawdown": float(pd.to_numeric(segment["drawdown"], errors="coerce").min()),
        "mean_ma_gap": float(pd.to_numeric(segment["ma_gap"], errors="coerce").mean()),
        "mean_total_risk_score": float(pd.to_numeric(segment["total_risk_score"], errors="coerce").mean()),
        "mean_tail_risk_score": float(pd.to_numeric(segment["tail_risk_score"], errors="coerce").mean()),
    }


def _simulate_variant(
    name: str,
    prices: pd.DataFrame,
    regimes: pd.Series,
    weights_by_regime: dict[str, dict[str, float]],
    initial_value: float,
    costs: dict[str, Any],
    baseline_metrics: dict[str, Any],
) -> dict[str, Any]:
    curve, execution = _simulate_costed_curve(
        prices,
        regimes,
        weights_by_regime,
        initial_value,
        float(costs["commission_rate"]),
        float(costs["slippage_rate"]),
        float(costs["equity_etf_sell_tax"]),
    )
    metrics = _metrics(curve, initial_value)
    return {
        "variant": name,
        **metrics,
        **_clean_metric_delta(metrics, baseline_metrics),
        **{f"execution_{key}": value for key, value in execution.items()},
    }


def build_attribution(
    start: str,
    end: str,
    initial_value: float,
    db: Path,
    output_prefix: Path | None = None,
) -> dict[str, Any]:
    latest_report, frame = run_latest(start, end, initial_value, db)
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()
    base_weights = {name: _normalize(weights) for name, weights in dict(latest_report["base_weights"]).items()}
    costs = dict(latest_report["cost_assumptions"])
    prices, dividend_coverage = _load_total_return_prices(db, frame.index)

    baseline_curve, baseline_execution = _simulate_costed_curve(
        prices,
        frame["execution_regime"].astype(str),
        base_weights,
        initial_value,
        float(costs["commission_rate"]),
        float(costs["slippage_rate"]),
        float(costs["equity_etf_sell_tax"]),
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)

    rows = [
        {
            "variant": "baseline",
            **baseline_metrics,
            **{f"execution_{key}": value for key, value in baseline_execution.items()},
            "delta_final": 0.0,
            "delta_total_return": 0.0,
            "delta_sharpe": 0.0,
            "delta_sortino": 0.0,
            "delta_mdd": 0.0,
        }
    ]
    for name, weights in _defensive_variants(base_weights).items():
        rows.append(
            _simulate_variant(name, prices, frame["execution_regime"].astype(str), weights, initial_value, costs, baseline_metrics)
        )

    regime_weights = dict(base_weights)
    regime_weights["attribution_cash_only"] = _normalize({"cash": 1.0})
    for name, regimes in _regime_variants(frame).items():
        if name == "baseline":
            continue
        rows.append(_simulate_variant(name, prices, regimes, regime_weights, initial_value, costs, baseline_metrics))

    ranked = sorted(
        [row for row in rows if row["variant"] != "baseline"],
        key=lambda row: (row["delta_final"], row["delta_sortino"], row["delta_mdd"]),
        reverse=True,
    )
    episodes = _episode_rows(frame, prices)
    report = {
        "experiment": "group_a_plus_2022_defensive_regime_attribution",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "implementation_note": (
            "Codex 2026-08-14: research-only attribution. Variants isolate "
            "defensive basket composition and recovery timing; no live target "
            "weights or manifests are written."
        ),
        "window": {
            "requested_start": start,
            "requested_end": end,
            "actual_start": str(frame.index[0].date()),
            "actual_end": str(frame.index[-1].date()),
            "rows": int(len(frame)),
        },
        "baseline": {"metrics": baseline_metrics, "execution": baseline_execution},
        "base_weights": base_weights,
        "cost_assumptions": costs,
        "dividend_coverage": dividend_coverage,
        "rows": rows,
        "ranked_variants": ranked,
        "episodes": episodes,
        "decision": {
            "promotion_ready": False,
            "reason": "diagnostic attribution only; use results to choose a smaller candidate mechanism",
        },
    }
    if output_prefix is not None:
        prefix = output_prefix if output_prefix.is_absolute() else PROJECT_ROOT / output_prefix
        prefix.parent.mkdir(parents=True, exist_ok=True)
        prefix.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        pd.DataFrame(rows).to_csv(prefix.with_suffix(".csv"), index=False, encoding="utf-8-sig")
        pd.DataFrame(episodes).to_csv(prefix.with_name(f"{prefix.name}_episodes.csv"), index=False, encoding="utf-8-sig")
        _write_markdown(report, prefix.with_suffix(".md"))
    return report


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    rows = report["ranked_variants"][:8]
    episodes = report["episodes"]
    lines = [
        "# GroupA+ 2022 Defensive Regime Attribution",
        "",
        "Codex 2026-08-14 research-only diagnostic. No live strategy change.",
        "",
        "## Top Variants",
        "",
        "| Variant | Final Delta | Sortino Delta | MDD Delta | Final Value |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| `{row['variant']}` | {row['delta_final']:.2f} | {row['delta_sortino']:.4f} | "
            f"{row['delta_mdd']:.4f} | {row['final_value']:.2f} |"
        )
    lines.extend(["", "## Episodes", "", "| Episode | Start | End | Days | Portfolio Return | 00679B Return | 0050 Return |", "|---:|---|---|---:|---:|---:|---:|"])
    for row in episodes:
        ticker = row["ticker_total_returns"]
        lines.append(
            f"| {row['episode']} | {row['start']} | {row['end']} | {row['trading_days']} | "
            f"{row['portfolio_return']:.2%} | {ticker.get('00679B.TWO', 0.0):.2%} | {ticker.get('0050.TW', 0.0):.2%} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2022-01-03")
    parser.add_argument("--end", default="2022-12-30")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--output-prefix", default="results/group_a_plus_2022_defensive_regime_attribution")
    args = parser.parse_args()

    report = build_attribution(args.start, args.end, args.initial_value, Path(args.db), Path(args.output_prefix))
    best = report["ranked_variants"][0]
    print(f"JSON: {(PROJECT_ROOT / args.output_prefix).with_suffix('.json')}")
    print(
        f"Best: {best['variant']} final_delta={best['delta_final']:.2f} "
        f"sortino_delta={best['delta_sortino']:.4f} mdd_delta={best['delta_mdd']:.4f}"
    )


if __name__ == "__main__":
    main()
