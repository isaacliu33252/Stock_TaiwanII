#!/usr/bin/env python3
"""Evaluate TSI alert as a shadow-only 00631L no-add guard.

Research-only follow-up for arXiv:2608.10788. This script answers two practical
questions:
- Does TSI add detector coverage beyond existing GroupA+ crash guards?
- If TSI alert only blocks incremental 00631L adds, does the shadow path improve?

It never changes live target weights, execution guards, or orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices
from group_a_plus.integrations.leveraged_compounding_regime import MEAN_REVERTING
from group_a_plus.integrations.triadic_stress_index import (
    DEFAULT_ALPHA_DOWN,
    DEFAULT_ALPHA_UP,
    DEFAULT_MIN_OBSERVATIONS,
    DEFAULT_TICKER_SOURCES,
    DEFAULT_WINDOW_DAYS,
    load_tsi_price_panel,
    rolling_tsi_frame,
)
from group_a_plus.runners.a2118 import (
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_00631l_compounding_regime_no_add_shadow import (
    _metric_delta,
    _simulate_baseline,
    simulate_no_add_guard,
)
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import PANEL_2025_2026, _resolve_end_date, _targets_from_report
from scripts.evaluate.evaluate_group_a_plus_crash_detector_overlap import (
    ALERT_ONLY_DETECTORS,
    BLOCKING_DETECTORS,
    DEFAULT_MARKET_STATE_FRAME,
    DEFAULT_NCF_PANEL,
    build_detector_frame,
    build_overlap_report,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/tsi_no_add_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/tsi_no_add_shadow.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/tsi_no_add_shadow/history"
DEFAULT_WINDOWS = (
    ("covid_2020", "2020-01-02", "2020-12-31", "results/ncf_00631l_panel_backfill_2020_20260716.csv", "out_of_sample"),
    ("recovery_2021", "2021-01-04", "2021-12-30", "results/ncf_00631l_panel_backfill_2021_20260726.csv", "out_of_sample"),
    (
        "rate_hike_2022",
        "2022-01-03",
        "2022-10-31",
        "results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv",
        "out_of_sample",
    ),
    ("rebound_2023", "2023-01-03", "2023-12-29", "results/ncf_00631l_panel_backfill_2023_20260726.csv", "out_of_sample"),
    ("full_2024", "2024-01-02", "2024-12-31", "results/ncf_00631l_panel_backfill_2024_20260726.csv", "out_of_sample"),
    ("active_2025_2026", "2025-01-02", "latest", PANEL_2025_2026, "tuning_window"),
    ("taiwan_2026_q1q2_stress", "2026-02-02", "2026-04-30", PANEL_2025_2026, "stress_window"),
    ("taiwan_2026_recent", "2026-05-15", "latest", PANEL_2025_2026, "recent_window"),
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _parse_windows(raw: str) -> list[tuple[str, str, str, str, str]]:
    if raw == "default":
        return list(DEFAULT_WINDOWS)
    windows: list[tuple[str, str, str, str, str]] = []
    for item in raw.split(";"):
        if not item.strip():
            continue
        parts = [part.strip() for part in item.split(",")]
        if len(parts) != 5:
            raise ValueError("Each window must be label,start,end,panel,kind")
        windows.append((parts[0], parts[1], parts[2], parts[3], parts[4]))
    return windows


def build_tsi_alert_series(
    prices: pd.DataFrame,
    *,
    threshold: float,
    window_days: int = DEFAULT_WINDOW_DAYS,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    alpha_up: float = DEFAULT_ALPHA_UP,
    alpha_down: float = DEFAULT_ALPHA_DOWN,
) -> pd.Series:
    frame, _metrics = rolling_tsi_frame(
        prices,
        window_days=window_days,
        min_observations=min_observations,
        alpha_up=alpha_up,
        alpha_down=alpha_down,
    )
    if frame.empty or "tsi_memory_percentile" not in frame:
        return pd.Series(dtype=bool, name="tsi_alert")
    alert = frame["tsi_memory_percentile"].astype(float) >= float(threshold)
    alert.name = "tsi_alert"
    return alert.astype(bool)


def add_tsi_to_detector_frame(detectors: pd.DataFrame, tsi_alert: pd.Series) -> pd.DataFrame:
    out = detectors.copy()
    out["tsi_stress_alert"] = tsi_alert.astype(bool).reindex(out.index, fill_value=False)
    return out


def build_tsi_overlap_report(detectors_with_tsi: pd.DataFrame) -> dict[str, Any]:
    base = build_overlap_report(detectors_with_tsi)
    any_existing_blocking = detectors_with_tsi[list(BLOCKING_DETECTORS)].any(axis=1)
    any_existing_alert = detectors_with_tsi[list(ALERT_ONLY_DETECTORS)].any(axis=1)
    tsi = detectors_with_tsi["tsi_stress_alert"].astype(bool)
    base["report_type"] = "group_a_plus_tsi_detector_overlap"
    base["alert_only_detectors"] = [*list(ALERT_ONLY_DETECTORS), "tsi_stress_alert"]
    base["tsi_unique_coverage"] = {
        "active_days": int(tsi.sum()),
        "days_active_while_no_blocking_guard_active": int((tsi & ~any_existing_blocking).sum()),
        "days_active_while_no_existing_alert_or_blocking_active": int((tsi & ~any_existing_blocking & ~any_existing_alert).sum()),
    }
    return base


def _tsi_alert_for_window(
    *,
    db_path: Path,
    start: str,
    end: str,
    threshold: float,
    warmup_days: int,
) -> pd.Series:
    warmup_start = (pd.Timestamp(start) - pd.Timedelta(days=int(warmup_days))).date().isoformat()
    prices, _status = load_tsi_price_panel(
        db_path=db_path,
        start=warmup_start,
        end=end,
        ticker_sources=DEFAULT_TICKER_SOURCES,
    )
    alert = build_tsi_alert_series(prices, threshold=threshold)
    return alert.loc[(alert.index >= pd.Timestamp(start)) & (alert.index <= pd.Timestamp(end))]


def evaluate_tsi_no_add_window(
    *,
    label: str,
    start: str,
    end: str,
    panel: str,
    kind: str,
    db_path: Path,
    initial_value: float,
    threshold: float,
    transaction_cost_bps: float,
    warmup_days: int,
    alert_mode: str = "tsi_only",
    detector_frame: pd.DataFrame | None = None,
    guard_add_fraction: float = 0.0,
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
    target_weights = _targets_from_report(frame.reindex(prices.index), report)
    tsi_alert = _tsi_alert_for_window(
        db_path=db_path,
        start=start,
        end=resolved_end,
        threshold=threshold,
        warmup_days=warmup_days,
    ).astype(bool).reindex(prices.index, fill_value=False)
    confirmation = pd.Series(True, index=prices.index)
    if alert_mode != "tsi_only":
        if detector_frame is None:
            confirmation = pd.Series(False, index=prices.index)
        else:
            aligned_detectors = detector_frame.astype(bool).reindex(prices.index, fill_value=False)
            if alert_mode == "tsi_and_existing_any":
                confirmation = aligned_detectors[list(BLOCKING_DETECTORS) + list(ALERT_ONLY_DETECTORS)].any(axis=1)
            elif alert_mode == "tsi_and_blocking":
                confirmation = aligned_detectors[list(BLOCKING_DETECTORS)].any(axis=1)
            else:
                raise ValueError(f"unknown alert_mode: {alert_mode}")
    guard_alert = tsi_alert & confirmation.astype(bool)
    regimes = pd.Series("TRANSITIONAL", index=prices.index)
    regimes.loc[guard_alert] = MEAN_REVERTING

    baseline = _simulate_baseline(prices, target_weights, initial_value, float(transaction_cost_bps))
    guarded = simulate_no_add_guard(
        prices=prices,
        target_weights=target_weights,
        regimes=regimes,
        initial_value=initial_value,
        baseline_add_fraction=1.0,
        mean_reversion_add_fraction=guard_add_fraction,
        transaction_cost_bps=transaction_cost_bps,
    )
    return {
        "label": label,
        "kind": kind,
        "window": {"start": start, "end": resolved_end, "rows": int(len(prices))},
        "tsi_threshold": float(threshold),
        "alert_mode": alert_mode,
        "guard_add_fraction": float(guard_add_fraction),
        "raw_tsi_alert_days": int(tsi_alert.sum()),
        "confirming_detector_days": int(confirmation.sum()) if len(confirmation) else 0,
        "tsi_alert_days": int(guard_alert.sum()),
        "tsi_alert_rate": float(guard_alert.mean()) if len(guard_alert) else None,
        "baseline": baseline,
        "tsi_no_add": guarded,
        "delta_vs_baseline": _metric_delta(guarded, baseline),
    }


def build_report(
    *,
    db_path: Path,
    windows: list[tuple[str, str, str, str, str]],
    initial_value: float,
    threshold: float,
    transaction_cost_bps: float,
    warmup_days: int,
    market_state_frame: Path,
    ncf_panel: Path,
    h20_max: float,
    mdd_min: float,
    alert_mode: str = "tsi_only",
    guard_add_fraction: float = 0.0,
) -> dict[str, Any]:
    print("Building TSI detector overlap")
    detectors = build_detector_frame(
        db_path=db_path,
        market_state_frame_path=market_state_frame,
        ncf_panel_path=ncf_panel,
        h20_max=h20_max,
        mdd_min=mdd_min,
    )
    overlap_start = str(detectors.index.min().date())
    overlap_end = str(detectors.index.max().date())
    tsi_alert = _tsi_alert_for_window(
        db_path=db_path,
        start=overlap_start,
        end=overlap_end,
        threshold=threshold,
        warmup_days=warmup_days,
    )
    overlap = build_tsi_overlap_report(add_tsi_to_detector_frame(detectors, tsi_alert))

    window_reports = []
    for label, start, end, panel, kind in windows:
        print(f"Evaluating TSI no-add {label}: {start}..{end}")
        window_reports.append(
            evaluate_tsi_no_add_window(
                label=label,
                start=start,
                end=end,
                panel=panel,
                kind=kind,
                db_path=db_path,
                initial_value=initial_value,
                threshold=threshold,
                transaction_cost_bps=transaction_cost_bps,
                warmup_days=warmup_days,
                alert_mode=alert_mode,
                detector_frame=detectors,
                guard_add_fraction=guard_add_fraction,
            )
        )

    totals = {
        "tsi_alert_days": int(sum(item["tsi_alert_days"] for item in window_reports)),
        "blocked_days": int(sum(item["tsi_no_add"]["blocked_days"] for item in window_reports)),
        "event_days": int(sum(item["tsi_no_add"]["event_days"] for item in window_reports)),
        "delta_final_value_sum": float(sum(item["delta_vs_baseline"]["final_value"] for item in window_reports)),
        "delta_sharpe_sum": float(sum(item["delta_vs_baseline"]["sharpe_ratio"] for item in window_reports)),
        "delta_max_drawdown_sum": float(sum(item["delta_vs_baseline"]["max_drawdown"] for item in window_reports)),
        "positive_final_value_windows": int(sum(item["delta_vs_baseline"]["final_value"] > 0.0 for item in window_reports)),
        "non_worse_drawdown_windows": int(sum(item["delta_vs_baseline"]["max_drawdown"] >= 0.0 for item in window_reports)),
    }
    blockers = [
        "research_only_coincident_stress_index",
        "no_live_weight_change_allowed",
        "requires_more_distinct_oos_windows_before_promotion",
    ]
    if totals["positive_final_value_windows"] < len(window_reports):
        blockers.append("not_positive_final_value_in_all_windows")
    if totals["non_worse_drawdown_windows"] < len(window_reports):
        blockers.append("drawdown_worsens_in_at_least_one_window")

    return {
        "schema_version": 1,
        "report_type": "group_a_plus_tsi_no_add_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "paper": "2608.10788",
        "paper_title": "The Triadic Stress Index in Financial Markets",
        "research_only": True,
        "production_effect": "none",
        "policy": "slow_or_block_incremental_00631l_add_only_when_tsi_stress_alert_active",
        "tsi_threshold": float(threshold),
        "alert_mode": alert_mode,
        "guard_add_fraction": float(guard_add_fraction),
        "transaction_cost_bps": float(transaction_cost_bps),
        "overlap": overlap,
        "windows": window_reports,
        "totals": totals,
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "promotion_allowed": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
    }


def _markdown(payload: dict[str, Any]) -> str:
    window_rows = []
    for item in payload.get("windows") or []:
        delta = item.get("delta_vs_baseline") or {}
        window_rows.append(
            "| {label} | {kind} | {alerts} | {blocked} | {dfv} | {dsharpe} | {dmdd} |".format(
                label=item.get("label"),
                kind=item.get("kind"),
                alerts=int(item.get("tsi_alert_days") or 0),
                blocked=int((item.get("tsi_no_add") or {}).get("blocked_days") or 0),
                dfv=f"{float(delta.get('final_value') or 0.0):,.0f}",
                dsharpe=f"{float(delta.get('sharpe_ratio') or 0.0):.4f}",
                dmdd=f"{float(delta.get('max_drawdown') or 0.0):.2%}",
            )
        )
    overlap = payload.get("overlap") or {}
    unique = overlap.get("tsi_unique_coverage") or {}
    return """# GroupA+ TSI No-Add Shadow

- status: `research_only`
- policy: `{policy}`
- threshold: `{threshold}`
- alert_mode: `{alert_mode}`
- guard_add_fraction: `{guard_add_fraction}`
- production_effect: `{production_effect}`
- promotion_allowed: `{promotion}`
- target_weight_change_allowed: `{weight_change}`

## Detector Coverage

- TSI active days: `{tsi_active}`
- TSI days active while no blocking guard active: `{tsi_unique_blocking}`
- TSI days active while no existing alert/blocking active: `{tsi_unique_all}`
- overlap window: `{overlap_start}` to `{overlap_end}`

## No-Add Counterfactual

| window | kind | tsi_alert_days | blocked_days | delta_final_value | delta_sharpe | delta_max_drawdown |
|---|---|---:|---:|---:|---:|---:|
{window_rows}

## Totals

```json
{totals}
```

## Governance

TSI remains shadow-only. It does not output target weights, execution regimes,
orders, or live permission to add 00631L. Golden1_0531 remains unchanged.
""".format(
        policy=payload.get("policy"),
        threshold=payload.get("tsi_threshold"),
        alert_mode=payload.get("alert_mode"),
        guard_add_fraction=payload.get("guard_add_fraction"),
        production_effect=payload.get("production_effect"),
        promotion=payload.get("decision", {}).get("promotion_allowed"),
        weight_change=payload.get("decision", {}).get("target_weight_change_allowed"),
        tsi_active=unique.get("active_days"),
        tsi_unique_blocking=unique.get("days_active_while_no_blocking_guard_active"),
        tsi_unique_all=unique.get("days_active_while_no_existing_alert_or_blocking_active"),
        overlap_start=(overlap.get("window") or {}).get("start"),
        overlap_end=(overlap.get("window") or {}).get("end"),
        window_rows="\n".join(window_rows) if window_rows else "| - | - | - | - | - | - | - |",
        totals=json.dumps(payload.get("totals") or {}, ensure_ascii=False, indent=2),
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
    (history_dir / f"tsi_no_add_shadow_{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--windows", default="default", help="default or semicolon-separated label,start,end,panel,kind")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--threshold", type=float, default=0.90)
    parser.add_argument(
        "--alert-mode",
        choices=("tsi_only", "tsi_and_existing_any", "tsi_and_blocking"),
        default="tsi_only",
    )
    parser.add_argument("--transaction-cost-bps", type=float, default=0.0)
    parser.add_argument(
        "--guard-add-fraction",
        type=float,
        default=0.0,
        help="Fraction of requested incremental 00631L add allowed while the TSI guard is active.",
    )
    parser.add_argument("--warmup-days", type=int, default=420)
    parser.add_argument("--market-state-frame", default=str(DEFAULT_MARKET_STATE_FRAME))
    parser.add_argument("--ncf-panel", default=str(DEFAULT_NCF_PANEL))
    parser.add_argument("--h20-max", type=float, default=0.22)
    parser.add_argument("--mdd-min", type=float, default=0.85)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_report(
        db_path=_resolve(args.db),
        windows=_parse_windows(args.windows),
        initial_value=float(args.initial_value),
        threshold=float(args.threshold),
        transaction_cost_bps=float(args.transaction_cost_bps),
        warmup_days=int(args.warmup_days),
        market_state_frame=_resolve(args.market_state_frame),
        ncf_panel=_resolve(args.ncf_panel),
        h20_max=float(args.h20_max),
        mdd_min=float(args.mdd_min),
        alert_mode=str(args.alert_mode),
        guard_add_fraction=float(args.guard_add_fraction),
    )
    write_report(
        payload,
        _resolve(args.output),
        _resolve(args.output_md),
        None if args.no_history else _resolve(args.history_dir),
    )
    print(f"TSI no-add shadow: {_resolve(args.output)}")
    print(json.dumps(payload["totals"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
