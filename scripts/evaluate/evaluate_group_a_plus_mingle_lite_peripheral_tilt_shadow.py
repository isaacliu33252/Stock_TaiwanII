#!/usr/bin/env python3
"""Evaluate MINGLE-lite peripheral tilts as a GroupA+ shadow.

Research-only follow-up for arXiv:2608.06618.  The baseline remains A21.18 /
Golden1_0531 latest targets.  Candidate paths move a capped fraction of risky
target weight toward MINGLE-lite peripheral assets, while prohibited assets
default to 00632R so the shadow never opens inverse exposure.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices, _metrics
from group_a_plus.integrations.mingle_lite_diversification import build_mingle_lite_frame
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.build_group_a_plus_mingle_lite_readiness_review import DEFAULT_TICKERS, load_price_panel
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import PANEL_2025_2026, _resolve_end_date, _targets_from_report
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import _simulate_daily_target_weights
from scripts.evaluate.evaluate_group_a_plus_tsi_no_add_shadow import _parse_windows, _resolve


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/mingle_lite_peripheral_tilt_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/mingle_lite_peripheral_tilt_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/mingle_lite_peripheral_tilt_shadow/history"
DEFAULT_WINDOWS = (
    "covid_2020,2020-01-02,2020-12-31,results/ncf_00631l_panel_backfill_2020_20260716.csv,out_of_sample;"
    "recovery_2021,2021-01-04,2021-12-30,results/ncf_00631l_panel_backfill_2021_20260726.csv,out_of_sample;"
    "rate_hike_2022,2022-01-03,2022-10-31,results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv,out_of_sample;"
    "rebound_2023,2023-01-03,2023-12-29,results/ncf_00631l_panel_backfill_2023_20260726.csv,out_of_sample;"
    "full_2024,2024-01-02,2024-12-31,results/ncf_00631l_panel_backfill_2024_20260726.csv,out_of_sample;"
    f"active_2025_2026,2025-01-02,latest,{PANEL_2025_2026},tuning_window;"
    f"taiwan_2026_q1q2_stress,2026-02-02,2026-04-30,{PANEL_2025_2026},stress_window;"
    f"taiwan_2026_recent,2026-05-15,latest,{PANEL_2025_2026},recent_window"
)


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _tilt_weights(
    base: dict[str, float],
    peripheral_score: pd.Series,
    *,
    tilt_fraction: float,
    prohibited_assets: set[str],
) -> dict[str, float]:
    risky_total = sum(max(float(base.get(ticker, 0.0) or 0.0), 0.0) for ticker in TICKERS)
    cash = max(float(base.get("cash", 0.0) or 0.0), 0.0)
    if risky_total <= 0.0 or float(tilt_fraction) <= 0.0:
        return {**{ticker: max(float(base.get(ticker, 0.0) or 0.0), 0.0) for ticker in TICKERS}, "cash": cash}
    allowed = [ticker for ticker in TICKERS if ticker not in prohibited_assets]
    score = peripheral_score.reindex(allowed).fillna(0.0).clip(lower=0.0)
    if float(score.sum()) <= 0.0:
        return {**{ticker: max(float(base.get(ticker, 0.0) or 0.0), 0.0) for ticker in TICKERS}, "cash": cash}
    peripheral_target = score / float(score.sum()) * risky_total
    out: dict[str, float] = {}
    frac = min(max(float(tilt_fraction), 0.0), 1.0)
    for ticker in TICKERS:
        current = max(float(base.get(ticker, 0.0) or 0.0), 0.0)
        if ticker in prohibited_assets:
            out[ticker] = current
        else:
            out[ticker] = (1.0 - frac) * current + frac * float(peripheral_target.get(ticker, 0.0))
    prohibited_weight = sum(out[ticker] for ticker in prohibited_assets if ticker in out)
    allowed_weight = sum(out[ticker] for ticker in allowed)
    desired_allowed = max(risky_total - prohibited_weight, 0.0)
    if allowed_weight > 0.0:
        scale = desired_allowed / allowed_weight
        for ticker in allowed:
            out[ticker] *= scale
    out["cash"] = cash
    total = sum(out.get(ticker, 0.0) for ticker in TICKERS) + cash
    if total > 0.0:
        for ticker in (*TICKERS, "cash"):
            out[ticker] = float(out.get(ticker, 0.0) / total)
    return out


def _metric_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    keys = ("final_value", "total_return", "annual_return", "sharpe_ratio", "sortino_ratio", "max_drawdown")
    return {key: float(candidate.get(key, 0.0) or 0.0) - float(baseline.get(key, 0.0) or 0.0) for key in keys}


def _monthly_peripheral_scores(
    *,
    db_path: Path,
    index: pd.DatetimeIndex,
    tickers: list[str],
    lookback_days: int,
    factor_count: int,
    decay: float,
    rebalance_every_days: int,
) -> dict[pd.Timestamp, pd.Series]:
    if len(index) == 0:
        return {}
    start = (index.min() - pd.Timedelta(days=int(lookback_days) + 30)).date().isoformat()
    end = index.max().date().isoformat()
    panel, status = load_price_panel(db_path=db_path, tickers=tickers, start=start, end=end)
    usable = [ticker for ticker, item in status.items() if int(item.get("rows") or 0) >= 60]
    scores: dict[pd.Timestamp, pd.Series] = {}
    for pos, dt in enumerate(index):
        if pos % int(rebalance_every_days) != 0:
            continue
        lookback = panel.loc[(panel.index <= dt) & (panel.index >= dt - pd.Timedelta(days=int(lookback_days))), usable]
        try:
            frame = build_mingle_lite_frame(lookback, factor_count=factor_count, decay=decay)
        except ValueError:
            continue
        scores[pd.Timestamp(dt)] = frame.peripheral_score
    return scores


def _build_tilt_targets(
    base_targets: pd.DataFrame,
    peripheral_scores: dict[pd.Timestamp, pd.Series],
    *,
    tilt_fraction: float,
    prohibited_assets: set[str],
) -> pd.DataFrame:
    out = []
    current_score = pd.Series(dtype=float)
    for dt, row in base_targets.iterrows():
        if pd.Timestamp(dt) in peripheral_scores:
            current_score = peripheral_scores[pd.Timestamp(dt)]
        out.append(_tilt_weights(row.to_dict(), current_score, tilt_fraction=tilt_fraction, prohibited_assets=prohibited_assets))
    return pd.DataFrame(out, index=base_targets.index).reindex(columns=[*TICKERS, "cash"]).fillna(0.0)


def _window_report(
    *,
    label: str,
    start: str,
    end: str,
    panel: str,
    kind: str,
    db_path: Path,
    initial_value: float,
    tilt_fractions: list[float],
    graph_tickers: list[str],
    prohibited_assets: set[str],
    lookback_days: int,
    factor_count: int,
    decay: float,
    rebalance_every_days: int,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    resolved_end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=resolved_end,
        initial_value=initial_value,
        db=db_path,
        ncf_panel_631l_path=panel,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
    )
    prices = _load_prices(db_path, list(TICKERS), start, resolved_end).reindex(frame.index).dropna()
    base_targets = _targets_from_report(frame.reindex(prices.index), report).reindex(prices.index).fillna(0.0)
    baseline_curve, baseline_exec = _simulate_daily_target_weights(
        prices,
        base_targets,
        initial_value,
        transaction_cost_bps / 10_000.0,
        0.0,
        0.0,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)
    peripheral_scores = _monthly_peripheral_scores(
        db_path=db_path,
        index=prices.index,
        tickers=graph_tickers,
        lookback_days=lookback_days,
        factor_count=factor_count,
        decay=decay,
        rebalance_every_days=rebalance_every_days,
    )
    candidates = []
    for tilt in tilt_fractions:
        tilted_targets = _build_tilt_targets(
            base_targets,
            peripheral_scores,
            tilt_fraction=tilt,
            prohibited_assets=prohibited_assets,
        )
        curve, execution = _simulate_daily_target_weights(
            prices,
            tilted_targets,
            initial_value,
            transaction_cost_bps / 10_000.0,
            0.0,
            0.0,
        )
        metrics = _metrics(curve, initial_value)
        avg_weights = {ticker: float(tilted_targets[ticker].mean()) for ticker in TICKERS}
        candidates.append(
            {
                "tilt_fraction": float(tilt),
                "metrics": metrics,
                "delta_vs_baseline": _metric_delta(metrics, baseline_metrics),
                "execution": execution,
                "avg_target_weights": avg_weights,
            }
        )
    return {
        "label": label,
        "kind": kind,
        "window": {"start": start, "end": resolved_end, "rows": int(len(prices))},
        "peripheral_rebalance_count": int(len(peripheral_scores)),
        "baseline": {"metrics": baseline_metrics, "execution": baseline_exec},
        "candidates": candidates,
    }


def build_report(
    *,
    db_path: Path,
    windows: list[tuple[str, str, str, str, str]],
    tilt_fractions: list[float],
    graph_tickers: list[str],
    prohibited_assets: set[str],
    initial_value: float,
    lookback_days: int,
    factor_count: int,
    decay: float,
    rebalance_every_days: int,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    window_reports = [
        _window_report(
            label=label,
            start=start,
            end=end,
            panel=panel,
            kind=kind,
            db_path=db_path,
            initial_value=initial_value,
            tilt_fractions=tilt_fractions,
            graph_tickers=graph_tickers,
            prohibited_assets=prohibited_assets,
            lookback_days=lookback_days,
            factor_count=factor_count,
            decay=decay,
            rebalance_every_days=rebalance_every_days,
            transaction_cost_bps=transaction_cost_bps,
        )
        for label, start, end, panel, kind in windows
    ]
    summaries = []
    for tilt in tilt_fractions:
        selected = [
            next(item for item in window["candidates"] if float(item["tilt_fraction"]) == float(tilt))
            for window in window_reports
        ]
        summaries.append(
            {
                "tilt_fraction": float(tilt),
                "delta_final_value_sum": float(sum(item["delta_vs_baseline"]["final_value"] for item in selected)),
                "delta_sharpe_sum": float(sum(item["delta_vs_baseline"]["sharpe_ratio"] for item in selected)),
                "delta_max_drawdown_sum": float(sum(item["delta_vs_baseline"]["max_drawdown"] for item in selected)),
                "positive_final_value_windows": int(sum(item["delta_vs_baseline"]["final_value"] > 0.0 for item in selected)),
                "non_worse_drawdown_windows": int(sum(item["delta_vs_baseline"]["max_drawdown"] >= 0.0 for item in selected)),
            }
        )
    best = max(summaries, key=lambda item: item["delta_final_value_sum"])
    blockers = ["research_only_no_live_weight_change", "mingle_lite_peripheral_tilt_not_promoted"]
    if best["positive_final_value_windows"] < len(window_reports):
        blockers.append("best_tilt_not_positive_in_all_windows")
    if best["delta_final_value_sum"] <= 0.0:
        blockers.append("best_tilt_does_not_improve_total_final_value")
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_mingle_lite_peripheral_tilt_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": "2608.06618",
        "research_only": True,
        "production_effect": "none",
        "policy": "mingle_lite_peripheral_tilt_shadow_no_live_weight_change",
        "configuration": {
            "tilt_fractions": tilt_fractions,
            "graph_tickers": graph_tickers,
            "prohibited_assets": sorted(prohibited_assets),
            "lookback_days": int(lookback_days),
            "factor_count": int(factor_count),
            "decay": float(decay),
            "rebalance_every_days": int(rebalance_every_days),
            "transaction_cost_bps": float(transaction_cost_bps),
        },
        "windows": window_reports,
        "summaries": summaries,
        "best_by_final_value": best,
        "blocking_reasons": blockers,
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    rows = []
    for item in payload.get("summaries") or []:
        rows.append(
            "| {tilt:.2f} | {dfv:,.0f} | {dsharpe:.4f} | {dmdd:.2%} | {pos} | {mdd_ok} |".format(
                tilt=float(item.get("tilt_fraction") or 0.0),
                dfv=float(item.get("delta_final_value_sum") or 0.0),
                dsharpe=float(item.get("delta_sharpe_sum") or 0.0),
                dmdd=float(item.get("delta_max_drawdown_sum") or 0.0),
                pos=int(item.get("positive_final_value_windows") or 0),
                mdd_ok=int(item.get("non_worse_drawdown_windows") or 0),
            )
        )
    return """# GroupA+ MINGLE-lite Peripheral Tilt Shadow

- status: `research_only`
- paper: `2608.06618`
- production_effect: `none`
- promotion_allowed: `{promotion}`
- allow_00632r_open: `{allow_inverse}`

## Summary

| tilt_fraction | delta_final_value_sum | delta_sharpe_sum | delta_max_drawdown_sum | positive_windows | non_worse_mdd_windows |
|---:|---:|---:|---:|---:|---:|
{rows}

## Best By Final Value

```json
{best}
```

## Blocking Reasons

```json
{blockers}
```

## Governance

This is a shadow-only peripheral tilt. It does not change Golden1_0531, target
weights, execution regimes, or live 00631L/00632R permissions.
""".format(
        promotion=payload.get("decision", {}).get("promotion_allowed"),
        allow_inverse=payload.get("decision", {}).get("allow_00632r_open"),
        rows="\n".join(rows) if rows else "| - | - | - | - | - | - |",
        best=json.dumps(payload.get("best_by_final_value") or {}, ensure_ascii=False, indent=2),
        blockers=json.dumps(payload.get("blocking_reasons") or [], ensure_ascii=False, indent=2),
    )


def write_report(payload: dict[str, Any], output: Path, output_md: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(payload), encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    (history_dir / f"mingle_lite_peripheral_tilt_shadow_{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default=DEFAULT_WINDOWS)
    parser.add_argument("--tilt-fractions", default="0,0.05,0.10,0.20")
    parser.add_argument("--graph-tickers", default=DEFAULT_TICKERS)
    parser.add_argument("--prohibited-assets", default="00632R.TW")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--lookback-days", type=int, default=730)
    parser.add_argument("--factor-count", type=int, default=3)
    parser.add_argument("--decay", type=float, default=0.997)
    parser.add_argument("--rebalance-every-days", type=int, default=21)
    parser.add_argument("--transaction-cost-bps", type=float, default=0.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_report(
        db_path=_resolve(args.db),
        windows=_parse_windows(args.windows),
        tilt_fractions=[float(item) for item in _parse_csv(args.tilt_fractions)],
        graph_tickers=_parse_csv(args.graph_tickers),
        prohibited_assets=set(_parse_csv(args.prohibited_assets)),
        initial_value=float(args.initial_value),
        lookback_days=int(args.lookback_days),
        factor_count=int(args.factor_count),
        decay=float(args.decay),
        rebalance_every_days=int(args.rebalance_every_days),
        transaction_cost_bps=float(args.transaction_cost_bps),
    )
    write_report(payload, _resolve(args.output), _resolve(args.output_md), None if args.no_history else _resolve(args.history_dir))
    print(f"MINGLE-lite peripheral tilt shadow: {_resolve(args.output)}")
    print(json.dumps(payload["best_by_final_value"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
