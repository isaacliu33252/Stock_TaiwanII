#!/usr/bin/env python3
"""NCF late-bull-hedge h20-specific confidence shadow for GroupA+.

Research-only. The live A21.18 NCF late-bull de-leverage trigger is
`ma_gap > ma_gap_min and prob_up_h20 < h20_max and confidence > conf_min`
(production: h20_max=0.33, conf_min=0.55). `confidence` in the panel is a
composite built from `prob_magnitude = |ensemble_prob_up - 0.5| * 2`, where
`ensemble_prob_up` blends h1 (~20%) + h5 (~30%) + h20 (~49%) -- NOT h20
alone. Root-cause diagnosis (2026-08-19, on the freshest panel,
`ncf_00631l_panel_latest_20260818.csv`): across 394 days since 2025-01-02,
h20_prob_up<0.33 fires on 79 days, confidence>=0.55 fires on 37 days, but
the two NEVER co-occur (0/79). On the 79 h20-bearish days, prob_up_h1 and
prob_up_h5 average ~0.46-0.47 (near coin-flip, not bearish) -- the shorter
horizons dilute the blended ensemble_prob_up back toward 0.5, capping
confidence below 0.55 even when h20 alone is confidently bearish (max
observed confidence on those 79 days: 0.538). This mechanism has therefore
been structurally dormant (0 live trigger days) independent of which panel
snapshot is pinned in strategy.json.

This script tests the most surgical fix: replace the confidence measure fed
into the SAME unmodified trigger logic (`_apply_late_bull_overlay`, called
unmodified) with an h20-specific magnitude, `h20_confidence = |prob_up_h20
- 0.5| * 2`, instead of the ensemble-blended composite. Nothing else
changes -- same ma_gap_min/h20_max/conf_min/h5_reentry_min, same overlay
function, same cost model. Does not modify a2118.py, golden1_0531, or any
live signal/execution-plan/order file; writes only a variant copy of each
panel CSV with the `confidence` column replaced.
"""

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

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.runners.a2118 import (  # noqa: E402
    CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    MOMENTUM_FAST_EXIT_MA_GAP_MIN,
    MOMENTUM_FAST_EXIT_MIN,
    RISK_SCORE_LOOKBACK_DAYS,
    run_a2118,
)
from scripts.evaluate.evaluate_a2118_warning_cashflow_guard import _resolve_end_date  # noqa: E402

DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "results/a2118_h20_specific_confidence_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/a2118_h20_specific_confidence_shadow.md"

# Production NCF late-bull-hedge params (strategy.json active_strategy.runner_params).
PROD_H20_MAX = 0.33
PROD_CONF_MIN = 0.55
PROD_H5_REENTRY_MIN = 0.55

DEFAULT_WINDOWS = [
    ("backfill_2020_covid", "2020-01-02", "2020-12-31", "tuning_style", "results/ncf_00631l_panel_backfill_2020_20260716.csv"),
    ("backfill_2021_may_correction", "2021-01-04", "2021-12-30", "tuning_style", "results/ncf_00631l_panel_backfill_2021_20260726.csv"),
    ("backfill_2022_rate_hike", "2022-01-03", "2022-10-31", "tuning_style", "results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv"),
    ("backfill_2024_aug_unwind", "2024-01-02", "2024-12-31", "tuning_style", "results/ncf_00631l_panel_backfill_2024_20260726.csv"),
    ("active_2025_2026", "2025-01-02", "latest", "tuning_style", "results/ncf_00631l_panel_latest_20260818.csv"),
    ("holdout_2023", "2023-01-03", "2023-12-29", "holdout", "results/ncf_00631l_panel_backfill_2023_20260726.csv"),
    ("holdout_2026", "2026-01-02", "latest", "holdout", "results/ncf_00631l_panel_latest_20260818.csv"),
]


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _parse_windows(raw_windows: list[str]) -> list[tuple[str, str, str, str, str]]:
    if not raw_windows:
        return DEFAULT_WINDOWS
    parsed: list[tuple[str, str, str, str, str]] = []
    for raw in raw_windows:
        label, start, end, bucket, panel_path = [part.strip() for part in raw.split(":")]
        parsed.append((label, start, end, bucket, panel_path))
    return parsed


def _write_h20_confidence_variant(src_path: Path, dst_path: Path, *, mode: str) -> None:
    df = pd.read_csv(src_path)
    if mode == "h20_magnitude":
        df["confidence"] = (df["prob_up_h20"].astype(float) - 0.5).abs() * 2.0
    elif mode == "h1h5_agree":
        # Direction 3: instead of requiring the blended ensemble to be
        # extreme, only require the shorter horizons not to actively
        # contradict the h20 bearish call. Re-expressed as a confidence
        # value against the SAME unmodified `conf > conf_min` (0.55) gate:
        # 1.0 (always passes) when h1 and h5 both agree bearish-or-neutral,
        # 0.0 (never passes) otherwise.
        agree = (df["prob_up_h1"].astype(float) < 0.5) & (df["prob_up_h5"].astype(float) < 0.5)
        df["confidence"] = agree.astype(float)
    else:
        raise ValueError(f"unknown variant mode: {mode}")
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dst_path, index=False)


def evaluate_window(
    *,
    label: str,
    start: str,
    end: str,
    bucket: str,
    panel_path: Path,
    variant_panel_path: Path,
    db_path: Path,
    initial_value: float,
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> dict[str, Any]:
    resolved_end = _resolve_end_date(db_path, end)
    common_kwargs = dict(
        start=start,
        end=resolved_end,
        initial_value=initial_value,
        db=db_path,
        commission_rate=commission_rate,
        slippage_rate=slippage_rate,
        equity_etf_sell_tax=equity_etf_sell_tax,
        h20_max=PROD_H20_MAX,
        conf_min=PROD_CONF_MIN,
        h5_reentry_min=PROD_H5_REENTRY_MIN,
        chip_data_fallback_max_stale_days=CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
        risk_score_lookback_days=RISK_SCORE_LOOKBACK_DAYS,
        momentum_fast_exit_min=MOMENTUM_FAST_EXIT_MIN,
        momentum_fast_exit_ma_gap_min=MOMENTUM_FAST_EXIT_MA_GAP_MIN,
        exclude_zero_volume_rows=True,
    )
    baseline_report, _ = run_a2118(ncf_panel_631l_path=str(panel_path), **common_kwargs)
    variant_report, _ = run_a2118(ncf_panel_631l_path=str(variant_panel_path), **common_kwargs)

    baseline_metrics = baseline_report["metrics"]
    variant_metrics = variant_report["metrics"]
    baseline_trigger_days = int(baseline_report["execution"].get("late_bull_trigger_days", 0))
    variant_trigger_days = int(variant_report["execution"].get("late_bull_trigger_days", 0))

    return {
        "label": label,
        "bucket": bucket,
        "window": {"start": start, "end": resolved_end},
        "panel_path": str(panel_path),
        "baseline_trigger_days": baseline_trigger_days,
        "variant_trigger_days": variant_trigger_days,
        "variant_trigger_events": variant_report["execution"].get("late_bull_trigger_events", []),
        "baseline_metrics": baseline_metrics,
        "variant_metrics": variant_metrics,
        "delta_vs_baseline": {
            "final_value": float(variant_metrics["final_value"] - baseline_metrics["final_value"]),
            "sharpe_ratio": float(variant_metrics["sharpe_ratio"] - baseline_metrics["sharpe_ratio"]),
            "max_drawdown": float(variant_metrics["max_drawdown"] - baseline_metrics["max_drawdown"]),
        },
    }


def _candidate_pass(item: dict[str, Any]) -> bool:
    delta = item["delta_vs_baseline"]
    return bool(delta["final_value"] >= 0.0 and delta["sharpe_ratio"] >= 0.0 and delta["max_drawdown"] >= 0.0)


def _summarize(windows: list[dict[str, Any]]) -> dict[str, Any]:
    def _agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "window_count": int(len(rows)),
            "pass_windows": int(sum(_candidate_pass(w) for w in rows)),
            "total_final_value_delta": float(sum(w["delta_vs_baseline"]["final_value"] for w in rows)),
            "total_variant_trigger_days": int(sum(w["variant_trigger_days"] for w in rows)),
            "total_baseline_trigger_days": int(sum(w["baseline_trigger_days"] for w in rows)),
        }

    tuning_rows = [w for w in windows if w["bucket"] == "tuning_style"]
    holdout_rows = [w for w in windows if w["bucket"] == "holdout"]
    holdout_summary = _agg(holdout_rows)
    promotion_ready = bool(
        holdout_summary["window_count"] > 0
        and holdout_summary["pass_windows"] == holdout_summary["window_count"]
        and holdout_summary["total_variant_trigger_days"] > 0
    )
    return {
        "all": _agg(windows),
        "tuning_style": _agg(tuning_rows),
        "holdout": holdout_summary,
        "promotion_ready": promotion_ready,
        "decision": "research_only_not_promoted" if not promotion_ready else "holdout_passed_needs_further_review",
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    db_path = _resolve(args.db)
    variant_dir = _resolve(args.variant_dir)
    windows = []
    for label, start, end, bucket, panel_path in _parse_windows(args.window):
        src = _resolve(panel_path)
        variant_dst = variant_dir / f"{src.stem}_{args.variant_mode}_variant.csv"
        _write_h20_confidence_variant(src, variant_dst, mode=args.variant_mode)
        windows.append(
            evaluate_window(
                label=label,
                start=start,
                end=end,
                bucket=bucket,
                panel_path=src,
                variant_panel_path=variant_dst,
                db_path=db_path,
                initial_value=float(args.initial_value),
                commission_rate=float(args.commission_rate),
                slippage_rate=float(args.slippage_rate),
                equity_etf_sell_tax=float(args.equity_etf_sell_tax),
            )
        )
    return {
        "schema_version": 1,
        "report_type": "a2118_h20_specific_confidence_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_no_groupa_plus_live_change",
        "mechanism": "replace_ensemble_blended_confidence_with_h20_specific_magnitude_same_trigger_logic",
        "production_params": {
            "h20_max": PROD_H20_MAX,
            "conf_min": PROD_CONF_MIN,
            "h5_reentry_min": PROD_H5_REENTRY_MIN,
        },
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
        "# A21.18 NCF Late-Bull-Hedge h20-Specific Confidence Shadow",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Policy: `{report['policy']}`",
        f"- Production params: `{report['production_params']}`",
        "",
        "## Summary",
        "",
        "| Bucket | Windows | Pass | Total Final Delta | Baseline Trigger Days | Variant Trigger Days |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in ("all", "tuning_style", "holdout"):
        item = report["summary"][name]
        lines.append(
            f"| {name} | {item['window_count']} | {item['pass_windows']}/{item['window_count']} | "
            f"{item['total_final_value_delta']:.2f} | {item['total_baseline_trigger_days']} | "
            f"{item['total_variant_trigger_days']} |"
        )
    lines.extend(
        [
            "",
            "## Window Details",
            "",
            "| Window | Bucket | Final Delta | Sharpe Delta | MDD Delta | Baseline Days | Variant Days | Pass |",
            "|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for window in report["windows"]:
        delta = window["delta_vs_baseline"]
        lines.append(
            f"| {window['label']} | {window['bucket']} | {delta['final_value']:.2f} | "
            f"{delta['sharpe_ratio']:.4f} | {delta['max_drawdown']:.4f} | "
            f"{window['baseline_trigger_days']} | {window['variant_trigger_days']} | {_candidate_pass(window)} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Promotion ready: `{report['summary']['promotion_ready']}`",
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
    parser.add_argument("--variant-dir", default="results")
    parser.add_argument("--variant-mode", choices=["h20_magnitude", "h1h5_agree"], default="h20_magnitude")
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
                "total_variant_trigger_days": report["summary"]["all"]["total_variant_trigger_days"],
                "output_json": str(output_json),
                "output_md": str(output_md),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
