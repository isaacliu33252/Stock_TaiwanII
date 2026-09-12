#!/usr/bin/env python3
"""LETF profit-harvest shadow for GroupA+ (arXiv:2506.19200).

Research-only review. The paper argues that broad-market LETF outcomes are
not just about volatility drag but about *how gains, once realized through
compounding, get managed* -- some simple systematic de-risk-after-gains
policies improve the risk-return profile of LETF-containing portfolios more
than naive buy-and-hold or naive vol-based trims.

This is deliberately a NARROW, different mechanism from every other 00631L
overlay already in a2118.py (`_golden_tail_trim_weights`,
`_apply_golden_follow_through_trim_overlay`, `_golden_leverage_cap_weights`,
`_apply_golden_rebound_recapture_overlay`): those are all *risk-triggered*
(drawdown, tail_risk_score, realized-vol-ratio, VaR breach) -- the LETF
analogue of "H20 bearish -> trim". This tests the opposite direction: a
*profit-triggered* harvest --

    00631L has accumulated a significant trailing gain
    AND the leveraged-compounding tailwind itself has been real (not just a
        rising market -- 00631L's excess return over 2x 0050 is positive)
    AND 00631L's relative momentum vs 0050 has started rolling over from a
        recent peak
    -> small proportional trim of 00631L inside golden1, shifted to 0050
       (not cash).

No new price data source, no PPO/RL, no lookahead: every feature below is
computed from `prices` alone using only `.shift`/`.rolling`/`.pct_change`
with no forward information, and the trigger is evaluated causally on each
day's own already-known state. Does not modify a2118.py, golden1_0531, or
any live signal/execution-plan/order file.
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

from backtest_group_a_plus_defensive_basket import _load_total_return_prices  # noqa: E402
from backtest_group_a_plus_policy_signal import TICKERS, _load_prices, _normalize  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH, _metrics  # noqa: E402
from backtest_group_a_plus_warmup_consistency import _warmup_start  # noqa: E402
from group_a_plus.runners.a2118 import (  # noqa: E402
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    _golden_tail_trim_weights,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_warning_cashflow_guard import _resolve_end_date  # noqa: E402
from scripts.evaluate.evaluate_adaptive_review_interval_shadow import (  # noqa: E402
    _simulate_targets,
    _targets_from_report,
)

DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results/2506_19200_letf_profit_harvest_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2506_19200_letf_profit_harvest_shadow.md"

HARVEST_REGIME = "golden1_profit_harvest"

# Same six windows used for arXiv:2510.14985's shadow (tuning-style: mix of
# live/recent and known 00631L-stress backfills), plus the same three true
# holdout windows (2022 full year, 2023, 2026) used to close that line out.
# Reused verbatim rather than re-picked, so any apparent edge here can't be
# an artifact of window selection.
DEFAULT_WINDOWS = [
    ("live_2024_2026", "2024-01-02", "latest", "tuning_style", None),
    ("active_2025_2026", "2025-01-02", "latest", "tuning_style", None),
    (
        "backfill_2020_covid",
        "2020-01-02",
        "2020-12-31",
        "tuning_style",
        "results/ncf_00631l_panel_backfill_2020_20260716.csv",
    ),
    (
        "backfill_2021_may_correction",
        "2021-01-04",
        "2021-12-30",
        "tuning_style",
        "results/ncf_00631l_panel_backfill_2021_20260726.csv",
    ),
    (
        "backfill_2022_rate_hike",
        "2022-01-03",
        "2022-10-31",
        "tuning_style",
        "results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv",
    ),
    (
        "backfill_2024_aug_unwind",
        "2024-01-02",
        "2024-12-31",
        "tuning_style",
        "results/ncf_00631l_panel_backfill_2024_20260726.csv",
    ),
    ("holdout_2022_full", "2022-01-03", "2022-12-30", "holdout", None),
    ("holdout_2023", "2023-01-03", "2023-12-29", "holdout", None),
    ("holdout_2026", "2026-01-02", "latest", "holdout", None),
]


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _parse_windows(raw_windows: list[str]) -> list[tuple[str, str, str, str, str | None]]:
    if not raw_windows:
        return DEFAULT_WINDOWS
    parsed: list[tuple[str, str, str, str, str | None]] = []
    for raw in raw_windows:
        parts = [part.strip() for part in raw.split(":")]
        if len(parts) not in {3, 4, 5}:
            raise ValueError("--window must be label:start:end[:bucket[:ncf_panel_631l_path]]")
        label, start, end = parts[:3]
        bucket = parts[3] if len(parts) >= 4 else "custom"
        panel_path = parts[4] if len(parts) == 5 and parts[4] else None
        parsed.append((label, start, end, bucket, panel_path))
    return parsed


def _build_harvest_features(
    prices: pd.DataFrame,
    *,
    gain_window: int,
    momentum_window: int,
    momentum_peak_lookback: int,
) -> pd.DataFrame:
    """Causal, backward-looking features only -- no forward information."""

    price_631l = prices["00631L.TW"].astype(float)
    price_0050 = prices["0050.TW"].astype(float)
    ret_631l = price_631l.pct_change(fill_method=None)
    ret_0050 = price_0050.pct_change(fill_method=None)

    trailing_gain = price_631l.pct_change(gain_window, fill_method=None)
    trailing_gain_0050 = price_0050.pct_change(gain_window, fill_method=None)
    compounding_effect = trailing_gain - 2.0 * trailing_gain_0050

    cum_631l = (1.0 + ret_631l).rolling(momentum_window, min_periods=momentum_window).apply(np.prod, raw=True) - 1.0
    cum_0050 = (1.0 + ret_0050).rolling(momentum_window, min_periods=momentum_window).apply(np.prod, raw=True) - 1.0
    relative_momentum = cum_631l - cum_0050
    momentum_peak = relative_momentum.rolling(momentum_peak_lookback, min_periods=1).max()
    momentum_decay = momentum_peak - relative_momentum

    return pd.DataFrame(
        {
            "trailing_gain": trailing_gain,
            "compounding_effect": compounding_effect,
            "relative_momentum": relative_momentum,
            "momentum_decay": momentum_decay,
        },
        index=prices.index,
    )


def _apply_profit_harvest_overlay(
    execution_regime: pd.Series,
    features: pd.DataFrame,
    *,
    gain_threshold: float,
    leverage_contribution_threshold: float,
    momentum_decay_threshold: float,
) -> tuple[pd.Series, dict[str, Any]]:
    modified = execution_regime.copy()
    events: list[dict[str, Any]] = []
    for dt in execution_regime.index:
        if str(execution_regime.loc[dt]) != "golden1" or dt not in features.index:
            continue
        row = features.loc[dt]
        gain = float(row.get("trailing_gain", np.nan))
        compounding = float(row.get("compounding_effect", np.nan))
        decay = float(row.get("momentum_decay", np.nan))
        if any(np.isnan(v) for v in (gain, compounding, decay)):
            continue
        triggered = (
            gain >= float(gain_threshold)
            and compounding >= float(leverage_contribution_threshold)
            and decay >= float(momentum_decay_threshold)
        )
        if not triggered:
            continue
        modified.loc[dt] = HARVEST_REGIME
        events.append(
            {
                "date": str(dt.date()),
                "trailing_gain": round(gain, 4),
                "compounding_effect": round(compounding, 4),
                "momentum_decay": round(decay, 4),
            }
        )
    return modified, {"profit_harvest_days": len(events), "profit_harvest_events": events}


def _targets_with_harvest(
    frame: pd.DataFrame,
    report: dict[str, Any],
    execution_regime: pd.Series,
    harvest_weights: dict[str, float],
) -> pd.DataFrame:
    base_weights = {key: _normalize(dict(value)) for key, value in report["base_weights"].items()}
    golden = base_weights["golden1"]
    rows: list[dict[str, float]] = []
    for dt in frame.index:
        regime = str(execution_regime.loc[dt])
        weights = harvest_weights if regime == HARVEST_REGIME else base_weights.get(
            regime, base_weights.get("group_a_plus_defensive", golden)
        )
        rows.append({key: float(weights.get(key, 0.0) or 0.0) for key in (*TICKERS, "cash")})
    return pd.DataFrame(rows, index=frame.index)


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    bucket: str,
    db_path: Path,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
    ncf_panel_631l_path: str | None,
    gain_window: int,
    momentum_window: int,
    momentum_peak_lookback: int,
    gain_threshold: float,
    leverage_contribution_threshold: float,
    momentum_decay_threshold: float,
    trim_fraction: float,
    feature_warmup_days: int,
) -> dict[str, Any]:
    resolved_end = _resolve_end_date(db_path, end)
    report, frame = run_a2118(
        start=start,
        end=resolved_end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        h20_max=0.33,
        conf_min=0.55,
        h5_reentry_min=0.55,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
        ncf_panel_631l_path=ncf_panel_631l_path,
    )
    prices, coverage = _load_total_return_prices(db_path, frame.index)
    baseline_targets = _targets_from_report(frame, report).reindex(prices.index).ffill()
    frame_aligned = frame.reindex(prices.index).ffill()
    execution_regime = frame_aligned["execution_regime"].astype(str)

    baseline_curve, baseline_execution = _simulate_targets(
        prices,
        baseline_targets,
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    baseline_metrics = _metrics(baseline_curve, initial_value)

    # Features need lookback beyond `start` (gain_window + momentum_peak_lookback
    # trading days) to be valid from day 1 of the window -- reindexing `prices`
    # (which is truncated exactly at `start`) would otherwise leave the first
    # ~2-3 months of every window artificially NaN-gated (can't trigger), even
    # though a live system on those dates would have real prior-year data.
    feature_start = _warmup_start(start, feature_warmup_days)
    warmup_close = _load_prices(db_path, list(TICKERS), feature_start, resolved_end)
    warmup_total_return, _ = _load_total_return_prices(db_path, warmup_close.index)
    features_full = _build_harvest_features(
        warmup_total_return,
        gain_window=gain_window,
        momentum_window=momentum_window,
        momentum_peak_lookback=momentum_peak_lookback,
    )
    features = features_full.reindex(prices.index)
    harvest_regime, harvest_info = _apply_profit_harvest_overlay(
        execution_regime,
        features,
        gain_threshold=gain_threshold,
        leverage_contribution_threshold=leverage_contribution_threshold,
        momentum_decay_threshold=momentum_decay_threshold,
    )
    base_weights = {key: _normalize(dict(value)) for key, value in report["base_weights"].items()}
    harvest_weights = _golden_tail_trim_weights(base_weights["golden1"], trim_fraction=trim_fraction)
    effective_trim_weight = max(
        float(base_weights["golden1"].get("00631L.TW", 0.0) or 0.0)
        - float(harvest_weights.get("00631L.TW", 0.0) or 0.0),
        0.0,
    )
    candidate_targets = _targets_with_harvest(frame_aligned, report, harvest_regime, harvest_weights)

    candidate_curve, candidate_execution = _simulate_targets(
        prices,
        candidate_targets,
        initial_value=initial_value,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
    )
    candidate_metrics = _metrics(candidate_curve, initial_value)

    delta = {
        "final_value": float(candidate_metrics["final_value"] - baseline_metrics["final_value"]),
        "sharpe_ratio": float(candidate_metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]),
        "max_drawdown": float(candidate_metrics["max_drawdown"] - baseline_metrics["max_drawdown"]),
        "transaction_cost": float(candidate_execution["transaction_cost"] - baseline_execution["transaction_cost"]),
        "turnover_value": float(candidate_execution["turnover_value"] - baseline_execution["turnover_value"]),
    }

    return {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": resolved_end},
        "harvest_weights": harvest_weights,
        "baseline": {"metrics": baseline_metrics, "execution": baseline_execution},
        "candidate": {"metrics": candidate_metrics, "execution": candidate_execution},
        "delta_vs_baseline": delta,
        "profit_harvest_info": harvest_info,
        "effective_trim_weight": float(effective_trim_weight),
        "dividend_coverage": coverage,
    }


def _candidate_pass(item: dict[str, Any]) -> bool:
    delta = item["delta_vs_baseline"]
    if (
        item["profit_harvest_info"]["profit_harvest_days"] > 0
        and float(item.get("effective_trim_weight", 0.0) or 0.0) <= 1e-12
    ):
        return False
    return bool(
        delta["final_value"] >= 0.0
        and delta["sharpe_ratio"] >= 0.0
        and delta["max_drawdown"] >= 0.0
    )


def _summarize(windows: list[dict[str, Any]]) -> dict[str, Any]:
    all_rows = windows
    tuning_rows = [w for w in windows if w["bucket"] == "tuning_style"]
    holdout_rows = [w for w in windows if w["bucket"] == "holdout"]

    def _agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
        pass_count = int(sum(_candidate_pass(w) for w in rows))
        total_harvest_days = int(sum(w["profit_harvest_info"]["profit_harvest_days"] for w in rows))
        effective_harvest_days = int(
            sum(
                w["profit_harvest_info"]["profit_harvest_days"]
                for w in rows
                if float(w.get("effective_trim_weight", 0.0) or 0.0) > 1e-12
            )
        )
        return {
            "window_count": int(len(rows)),
            "pass_windows": pass_count,
            "total_final_value_delta": float(sum(w["delta_vs_baseline"]["final_value"] for w in rows)),
            "total_transaction_cost_delta": float(sum(w["delta_vs_baseline"]["transaction_cost"] for w in rows)),
            "total_turnover_delta": float(sum(w["delta_vs_baseline"]["turnover_value"] for w in rows)),
            "total_profit_harvest_days": total_harvest_days,
            "total_effective_harvest_days": effective_harvest_days,
        }

    all_summary = _agg(all_rows)
    tuning_summary = _agg(tuning_rows)
    holdout_summary = _agg(holdout_rows)
    promotion_ready = bool(
        holdout_summary["pass_windows"] == holdout_summary["window_count"]
        and holdout_summary["window_count"] > 0
        and holdout_summary["total_profit_harvest_days"] > 0
        and holdout_summary["total_effective_harvest_days"] > 0
    )
    return {
        "all": all_summary,
        "tuning_style": tuning_summary,
        "holdout": holdout_summary,
        "promotion_ready": promotion_ready,
        "decision": "research_only_not_promoted" if not promotion_ready else "holdout_passed_needs_further_review",
        "reason": (
            "Profit-harvest trigger never fired on any holdout window (2022/2023/2026) -- "
            "no adaptive-vs-baseline economic claim can be evaluated there."
            if holdout_summary["total_profit_harvest_days"] == 0
            else "Profit-harvest trigger fired, but current golden1 has no effective 00631L trim exposure."
            if holdout_summary["total_effective_harvest_days"] == 0
            else "See per-window deltas."
        ),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    params = dict(
        gain_window=int(args.gain_window),
        momentum_window=int(args.momentum_window),
        momentum_peak_lookback=int(args.momentum_peak_lookback),
        gain_threshold=float(args.gain_threshold),
        leverage_contribution_threshold=float(args.leverage_contribution_threshold),
        momentum_decay_threshold=float(args.momentum_decay_threshold),
        trim_fraction=float(args.trim_fraction),
        feature_warmup_days=int(args.feature_warmup_days),
    )
    windows = [
        evaluate_window(
            label=label,
            start=start,
            end=end,
            bucket=bucket,
            db_path=db_path,
            initial_value=float(args.initial_value),
            commission_rate=float(args.commission_rate),
            slippage_rate=float(args.slippage_rate),
            equity_etf_sell_tax=float(args.equity_etf_sell_tax),
            ncf_panel_631l_path=panel_path,
            **params,
        )
        for label, start, end, bucket, panel_path in _parse_windows(args.window)
    ]
    return {
        "schema_version": 1,
        "report_type": "2506_19200_letf_profit_harvest_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": "arXiv:2506.19200 (LETF dynamic portfolio policy / de-risk-after-gains)",
        "policy": "research_only_no_groupa_plus_live_change",
        "mechanism": "profit_triggered_trim_not_risk_triggered",
        "params": params,
        "scope": {
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_a2118_decision_rule": False,
            "creates_orders": False,
        },
        "summary": _summarize(windows),
        "windows": windows,
    }


def _write_md(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2506.19200 LETF Profit-Harvest Shadow",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Policy: `{report['policy']}`",
        f"- Params: `{report['params']}`",
        "",
        "## Summary",
        "",
        "| Bucket | Windows | Pass | Total Final Delta | Total Cost Delta | Total Turnover Delta | Harvest Days | Effective Harvest Days |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("all", "tuning_style", "holdout"):
        item = report["summary"][name]
        lines.append(
            f"| {name} | {item['window_count']} | {item['pass_windows']}/{item['window_count']} | "
            f"{item['total_final_value_delta']:.2f} | {item['total_transaction_cost_delta']:.2f} | "
            f"{item['total_turnover_delta']:.2f} | {item['total_profit_harvest_days']} | "
            f"{item['total_effective_harvest_days']} |"
        )
    lines.extend(
        [
            "",
            "## Window Details",
            "",
            "| Window | Bucket | Final Delta | Sharpe Delta | MDD Delta | Cost Delta | Turnover Delta | Harvest Days | Effective Trim Weight | Pass |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for window in report["windows"]:
        delta = window["delta_vs_baseline"]
        lines.append(
            f"| {window['label']} | {window['bucket']} | {delta['final_value']:.2f} | "
            f"{delta['sharpe_ratio']:.4f} | {delta['max_drawdown']:.4f} | "
            f"{delta['transaction_cost']:.2f} | {delta['turnover_value']:.2f} | "
            f"{window['profit_harvest_info']['profit_harvest_days']} | "
            f"{float(window.get('effective_trim_weight', 0.0) or 0.0):.4f} | {_candidate_pass(window)} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Promotion ready: `{report['summary']['promotion_ready']}`",
            f"- Reason: {report['summary']['reason']}",
            "- Recommended use: `research_only`",
            "- No latest strategy, golden1_0531, live signal, execution plan, or order file was changed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--window", action="append", default=[])
    parser.add_argument("--gain-window", type=int, default=60)
    parser.add_argument("--momentum-window", type=int, default=20)
    parser.add_argument("--momentum-peak-lookback", type=int, default=20)
    parser.add_argument("--gain-threshold", type=float, default=0.20)
    parser.add_argument("--leverage-contribution-threshold", type=float, default=0.03)
    parser.add_argument("--momentum-decay-threshold", type=float, default=0.03)
    parser.add_argument("--trim-fraction", type=float, default=0.25)
    parser.add_argument("--feature-warmup-days", type=int, default=150)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    output_json = _resolve(args.output_json)
    output_md = _resolve(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_md(report, output_md)
    print(
        json.dumps(
            {
                "promotion_ready": report["summary"]["promotion_ready"],
                "reason": report["summary"]["reason"],
                "output_json": str(output_json),
                "output_md": str(output_md),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
