#!/usr/bin/env python3
"""Research sweep: fold ncf_2330 (TSMC individual-stock model) tail-risk output
into a2118's `total_risk_score` composite, instead of the already-rejected
price-return-based standalone trim (`_apply_tsmc_weakness_trim`, tested in
`a2118_ncf_2330_tsmc_overlay_sweep.py` and found to lose money with zero
max_drawdown improvement across all 324 swept variants).

Rationale: the 2330 individual-stock model's own validation history
(NCF_2330_*.md handoffs) found only the tail-risk output
(`prob_fwd_mdd_gt5_h20`) survives out-of-sample checks; the directional
output does not. `total_risk_score` already gates a2118's real defensive
entry (`require_total_risk_score=6`) and the bearish high-risk trim
(`total_risk_score>=9`), so this tests whether adding one more binary flag
to that existing, already-causally-connected score changes anything --
rather than inventing a new independent price-return trigger.

Read-only with respect to production strategy code: `_regime_features` is
monkeypatched inside this process only (restored after every run), never
edited on disk. Writes one JSON report to results/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import backtest_group_a_plus_switch_policy as switch_policy  # noqa: E402
from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.runners.a2118 import run_a2118  # noqa: E402

START = "2025-01-02"
END = "2026-07-03"
INITIAL_VALUE = 1_000_000.0

PANEL_631L = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
PANEL_2330 = PROJECT_ROOT / "results" / "ncf_2330_improved_panel_latest_20260703.csv"
OUT = PROJECT_ROOT / "results" / "ncf_2330_total_risk_score_overlay_sweep_20260705.json"

# Production a2118 params (report/group_a_plus/latest/strategy.json runner_params).
H20_MAX = 0.33
CONF_MIN = 0.55
H5_REENTRY_MIN = 0.55

TAIL_THRESHOLDS = [0.40, 0.45, 0.50, 0.55, 0.60]

_ORIGINAL_REGIME_FEATURES = switch_policy._regime_features


def _load_2330_tail(path: Path) -> pd.Series:
    df = pd.read_csv(path, index_col="date", parse_dates=True, encoding="utf-8-sig")
    df.index = pd.to_datetime(df.index).normalize()
    return df["prob_fwd_mdd_gt5_h20"].astype(float)


def _make_patched(tail_series: pd.Series, threshold: float):
    def patched(prices, rule, chip_features=None):
        frame = _ORIGINAL_REGIME_FEATURES(prices, rule, chip_features)
        flag = (tail_series.reindex(frame.index) >= threshold).fillna(False).astype(int)
        frame = frame.copy()
        frame["chip_tsmc_2330_tail_risk"] = flag
        frame["chip_score"] = frame["chip_score"] + flag
        frame["total_risk_score"] = frame["total_risk_score"] + flag
        return frame

    return patched


def _run_a2118(patched_fn=None) -> tuple[dict, pd.DataFrame]:
    if patched_fn is not None:
        switch_policy._regime_features = patched_fn
    try:
        report, frame = run_a2118(
            START,
            END,
            INITIAL_VALUE,
            DB_PATH,
            ncf_panel_631l_path=str(PANEL_631L),
            h20_max=H20_MAX,
            conf_min=CONF_MIN,
            h5_reentry_min=H5_REENTRY_MIN,
        )
    finally:
        switch_policy._regime_features = _ORIGINAL_REGIME_FEATURES
    return report, frame


def _defensive_days(frame: pd.DataFrame) -> int:
    return int((frame["execution_regime"] == "group_a_plus_defensive").sum())


def main() -> None:
    tail = _load_2330_tail(PANEL_2330)

    baseline_report, baseline_frame = _run_a2118()
    baseline_metrics = baseline_report["metrics"]
    baseline_defensive_days = _defensive_days(baseline_frame)

    variants: list[dict[str, Any]] = []
    for threshold in TAIL_THRESHOLDS:
        report, frame = _run_a2118(_make_patched(tail, threshold))
        m = report["metrics"]
        flagged_days = int((tail.reindex(baseline_frame.index) >= threshold).fillna(False).sum())
        defensive_days = _defensive_days(frame)
        variants.append(
            {
                "tail_threshold": threshold,
                "flagged_days": flagged_days,
                "defensive_days": defensive_days,
                "defensive_days_delta": defensive_days - baseline_defensive_days,
                "metrics": m,
                "late_bull_trigger_days": report["execution"].get("late_bull_trigger_days"),
                "delta_vs_baseline": {
                    "final_value": float(m["final_value"]) - float(baseline_metrics["final_value"]),
                    "sharpe_ratio": float(m["sharpe_ratio"]) - float(baseline_metrics["sharpe_ratio"]),
                    "max_drawdown": float(m["max_drawdown"]) - float(baseline_metrics["max_drawdown"]),
                },
            }
        )

    result = {
        "experiment": "ncf_2330_total_risk_score_overlay_sweep",
        "window": {"start": START, "end": END},
        "baseline": {
            "metrics": baseline_metrics,
            "defensive_days": baseline_defensive_days,
            "late_bull_trigger_days": baseline_report["execution"].get("late_bull_trigger_days"),
        },
        "variants": variants,
        "inputs": {
            "panel_631l": str(PANEL_631L.relative_to(PROJECT_ROOT)),
            "panel_2330": str(PANEL_2330.relative_to(PROJECT_ROOT)),
        },
        "mechanism": "chip_score/total_risk_score += 1 when prob_fwd_mdd_gt5_h20(2330) >= threshold",
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(
        json.dumps(
            {
                "saved": str(OUT),
                "baseline": {
                    "final_value": baseline_metrics["final_value"],
                    "sharpe_ratio": baseline_metrics["sharpe_ratio"],
                    "max_drawdown": baseline_metrics["max_drawdown"],
                    "defensive_days": baseline_defensive_days,
                },
                "variants": [
                    {
                        "tail_threshold": v["tail_threshold"],
                        "flagged_days": v["flagged_days"],
                        "defensive_days_delta": v["defensive_days_delta"],
                        "delta_vs_baseline": v["delta_vs_baseline"],
                    }
                    for v in variants
                ],
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
