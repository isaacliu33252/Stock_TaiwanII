#!/usr/bin/env python3
"""Fable 00631L direction #3: quantify the golden1 leverage-cap trigger's
opportunity cost specifically on days the tuned A21.20 compounding regime
classifier calls TREND_PERSISTENT.

Research-only. The a2126 golden1-leverage-cap shadow (group_a_plus/runners/
a2126.py, NOT wired into production a2118 -- golden_leverage_cap_enabled
defaults to False there) already shows a real, existing-but-truncated event
list and a mixed net effect across windows (results/a2126_shadow_candidate_
compare_latest.json: +$105,940 over 2020-2026, -$45,275 over 2024-2026,
only 20 of 33 trigger dates actually stored). This reruns run_a2126()
directly to get the FULL untruncated trigger-date list, cross-references
each against classify_compounding_regime() with the same tuned thresholds
already promoted-and-shadow-monitored for A21.20 (PREFERRED_THRESHOLDS from
evaluate_a2120_ce20_variant_a2119_overlap.py, imported not duplicated), and
reports forward 00631L returns split by regime label at trigger time -- a
direct, model-free measure of "how much upside did capping give up
specifically when the classifier said the trend was still persistent."

Does not touch target_weights or any production file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH, _load_prices
from group_a_plus.integrations.leveraged_compounding_regime import (
    build_compounding_features,
    classify_compounding_regime,
)
from group_a_plus.runners.a2126 import (
    A2126_DRAWDOWN_MAX,
    A2126_REALIZED_VOL_RATIO_MIN,
    A2126_TAIL_RISK_SCORE_MIN,
    run_a2126,
)
from scripts.evaluate.evaluate_a2118_decision_focused_action_shadow import _resolve_end_date
from scripts.evaluate.evaluate_a2120_ce20_variant_a2119_overlap import PREFERRED_THRESHOLDS

DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "a2126_leverage_cap_trend_persistent_overlap_20260822.json"
FORWARD_HORIZONS = (5, 10, 20)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    db_path = Path(args.db)
    resolved_end = _resolve_end_date(db_path, args.end)

    report, frame = run_a2126(
        start=args.start,
        end=resolved_end,
        initial_value=args.initial_value,
        db=db_path,
        tail_risk_score_min=A2126_TAIL_RISK_SCORE_MIN,
        realized_vol_ratio_min=A2126_REALIZED_VOL_RATIO_MIN,
        drawdown_max=A2126_DRAWDOWN_MAX,
    )
    trigger_dates = frame.index[frame["execution_regime"] == "golden1_leverage_cap"]
    print(f"Full trigger-day count: {len(trigger_dates)} (stored candidate-compare JSON only kept 20 of 33 historically)")

    prices = _load_prices(db_path, ["0050.TW", "00631L.TW"], "2019-01-02", resolved_end)
    features = build_compounding_features(prices["00631L.TW"], prices["0050.TW"])
    classified = classify_compounding_regime(features, thresholds=PREFERRED_THRESHOLDS)
    regime_by_date = classified["compounding_regime"]

    close_00631l = prices["00631L.TW"]
    rows: list[dict[str, Any]] = []
    for dt in trigger_dates:
        regime = str(regime_by_date.get(dt, "UNAVAILABLE"))
        row: dict[str, Any] = {"date": str(dt.date()), "tuned_compounding_regime": regime}
        idx = close_00631l.index.get_indexer([dt])[0]
        base_price = float(close_00631l.iloc[idx]) if idx >= 0 else None
        for h in FORWARD_HORIZONS:
            if idx < 0 or idx + h >= len(close_00631l) or base_price is None:
                row[f"forward_{h}d_00631l_return"] = None
                continue
            fwd_price = float(close_00631l.iloc[idx + h])
            row[f"forward_{h}d_00631l_return"] = fwd_price / base_price - 1.0
        rows.append(row)

    regimes_present = sorted({r["tuned_compounding_regime"] for r in rows})
    breakdown: dict[str, Any] = {"trigger_day_count": len(rows)}
    for regime in regimes_present:
        subset = [r for r in rows if r["tuned_compounding_regime"] == regime]
        breakdown[regime] = {"count": len(subset)}
        for h in FORWARD_HORIZONS:
            values = [r[f"forward_{h}d_00631l_return"] for r in subset if r[f"forward_{h}d_00631l_return"] is not None]
            if values:
                breakdown[regime][f"forward_{h}d_mean"] = float(np.mean(values))
                breakdown[regime][f"forward_{h}d_median"] = float(np.median(values))
                breakdown[regime][f"forward_{h}d_positive_rate"] = float(np.mean([v > 0 for v in values]))
                breakdown[regime][f"forward_{h}d_n"] = len(values)

    print("\n=== trigger-day tuned-regime breakdown ===")
    for regime in regimes_present:
        b = breakdown[regime]
        print(f"  {regime}: {b['count']} of {len(rows)} trigger days")
        for h in FORWARD_HORIZONS:
            if f"forward_{h}d_mean" in b:
                print(
                    f"    forward_{h}d: mean={b[f'forward_{h}d_mean']:+.4f} "
                    f"median={b[f'forward_{h}d_median']:+.4f} "
                    f"positive_rate={b[f'forward_{h}d_positive_rate']:.2f} "
                    f"(n={b[f'forward_{h}d_n']})"
                )

    payload = {
        "schema_version": 1,
        "experiment": "a2126_leverage_cap_trend_persistent_overlap",
        "research_only": True,
        "production_effect": "none",
        "purpose": (
            "Fable 00631L direction #3: does the golden1 leverage-cap trigger "
            "(realized_vol_ratio_20_60>=1.25 AND tail_risk_score>=1 AND drawdown<=-0.08) "
            "fire on days the tuned A21.20 regime classifier calls TREND_PERSISTENT, "
            "and if so, how much forward 00631L upside did capping give up on those "
            "specific days vs. trigger days classified otherwise."
        ),
        "window": {"start": args.start, "end": resolved_end},
        "trigger_dates": [str(dt.date()) for dt in trigger_dates],
        "per_event": rows,
        "breakdown_by_tuned_regime": breakdown,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
