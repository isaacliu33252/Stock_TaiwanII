#!/usr/bin/env python3
"""Research-only: H2 Option B — sweep conf_min against a composite confidence.

Context (2026-07-02 Fable 5 audit, H2): the live JSON's "confidence" field
used to be a composite of direction-consensus, probability-magnitude, and
inter-horizon spread (consensus*0.4 + magnitude*0.4 + spread*0.2), on a
different scale from the panel's own prob_magnitude that a2118's
conf_min=0.55 was actually calibrated against. Option A (shipped) unified
live and backtest on prob_magnitude, keeping conf_min=0.55 valid. Option B
(this script) asks the opposite question: is the composite metric actually
a *better* trigger criterion than plain magnitude, if conf_min is properly
re-swept against it?

This script does NOT touch any live/production file. It:
  1. Loads the pinned production panel CSV.
  2. Computes a composite-confidence column purely from columns already in
     that CSV (prob_up_h1/h5/h20 for consensus+spread, prob_magnitude for
     the magnitude component) -- same formula as the old live JSON
     composite, recomputed panel-side so it can be swept.
  3. Writes a temp copy of the panel with `confidence` replaced by the
     composite value (never modifies the real panel file).
  4. Runs a2118's actual backtest (`run_a2118`) once per conf_min in a grid,
     against the temp panel.
  5. Reports Sharpe/MDD/annual_return/trigger_count per conf_min, and
     compares the best composite candidate against the Option A baseline
     (today's real panel, conf_min=0.55, prob_magnitude).

Usage:
    PYTHONPATH=. .venv/bin/python scripts/evaluate/evaluate_a2118_composite_confidence_sweep.py
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.runners.a2118 import CHIP_DATA_FALLBACK_MAX_STALE_DAYS, _resolve_end_date, run_a2118

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260630.csv"
PRODUCTION_H20_MAX = 0.33
PRODUCTION_H5_REENTRY_MIN = 0.55
PRODUCTION_CONF_MIN = 0.55  # Option A's calibrated value, on prob_magnitude
# Explicit, not just inherited from run_a2118's default: pin to whatever
# strategy.json's production runner_params actually use, so this sweep can't
# silently start reflecting a different chip-data-outage policy than
# production just because a2118.py's own default changed (2026-07-06).
PRODUCTION_CHIP_DATA_FALLBACK_MAX_STALE_DAYS = CHIP_DATA_FALLBACK_MAX_STALE_DAYS


def _composite_confidence(panel: pd.DataFrame) -> pd.Series:
    """Recompute the old live-JSON composite confidence formula from
    columns already in the panel CSV -- consensus*0.4 + magnitude*0.4 +
    spread*0.2, matching scripts/misc/ncf_00631l.py's historical formula
    (no walk-forward-accuracy 4th component available panel-side)."""
    probs = panel[["prob_up_h1", "prob_up_h5", "prob_up_h20"]].to_numpy(dtype=float)
    directions_up = (probs > 0.5).sum(axis=1)  # 0..3
    max_votes = np.maximum(directions_up, 3 - directions_up)
    consensus = max_votes / 3.0

    magnitude = panel["prob_magnitude"].to_numpy(dtype=float)

    prob_std = probs.std(axis=1)
    spread_conf = np.clip(1.0 - prob_std * 4.0, 0.0, None)

    confidence = consensus * 0.4 + magnitude * 0.4 + spread_conf * 0.2
    return pd.Series(np.clip(confidence, 0.1, 1.0), index=panel.index)


def _write_composite_panel(source_panel: Path, tmp_dir: Path) -> Path:
    panel = pd.read_csv(source_panel)
    panel["confidence"] = _composite_confidence(panel)
    out_path = tmp_dir / f"composite_{source_panel.name}"
    panel.to_csv(out_path, index=False)
    return out_path


def _run_one(panel_path: Path, conf_min: float, *, label: str, end: str) -> dict:
    report, _frame = run_a2118(
        start="2025-01-02",
        end=end,
        initial_value=1_000_000.0,
        db=DB_PATH,
        ncf_panel_631l_path=str(panel_path),
        h20_max=PRODUCTION_H20_MAX,
        conf_min=conf_min,
        h5_reentry_min=PRODUCTION_H5_REENTRY_MIN,
        chip_data_fallback_max_stale_days=PRODUCTION_CHIP_DATA_FALLBACK_MAX_STALE_DAYS,
    )
    metrics = report["metrics"]
    execution = report["execution"]
    return {
        "label": label,
        "conf_min": conf_min,
        "sharpe_ratio": metrics["sharpe_ratio"],
        "sortino_ratio": metrics["sortino_ratio"],
        "annual_return": metrics["annual_return"],
        "max_drawdown": metrics["max_drawdown"],
        "late_bull_trigger_days": execution.get("late_bull_trigger_days"),
        "late_bull_trigger_events": execution.get("late_bull_trigger_events"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument(
        "--conf-min-grid",
        default="0.30,0.40,0.50,0.55,0.60,0.65,0.70,0.75,0.80",
        help="comma-separated conf_min values to sweep against the composite metric",
    )
    parser.add_argument("--output", default="results/a2118_h2_option_b_composite_sweep_20260703.json")
    args = parser.parse_args()

    source_panel = Path(args.panel)
    grid = [float(x) for x in args.conf_min_grid.split(",")]
    resolved_end = _resolve_end_date(Path(DB_PATH), "latest")

    with tempfile.TemporaryDirectory() as tmp:
        composite_panel_path = _write_composite_panel(source_panel, Path(tmp))

        baseline = _run_one(
            source_panel, PRODUCTION_CONF_MIN, label="option_a_baseline_prob_magnitude", end=resolved_end
        )

        sweep_results = [
            _run_one(composite_panel_path, conf_min, label="option_b_composite_confidence", end=resolved_end)
            for conf_min in grid
        ]

    best = max(sweep_results, key=lambda r: r["sharpe_ratio"])

    result = {
        "schema_version": 1,
        "report_type": "a2118_h2_option_b_composite_confidence_sweep",
        "status": "research_only",
        "active_allocation_impact": "none",
        "note": (
            "H2 Option B research: does the old composite confidence "
            "(consensus+magnitude+spread) beat prob_magnitude (Option A, "
            "shipped) as a2118's late-bull trigger criterion, if conf_min "
            "is properly re-swept against it? Does not touch any live "
            "file; a temp copy of the panel is used for the sweep."
        ),
        "panel": str(source_panel),
        "conf_min_grid": grid,
        "option_a_baseline": baseline,
        "option_b_sweep": sweep_results,
        "option_b_best": best,
        "decision": (
            "option_b_better"
            if best["sharpe_ratio"] > baseline["sharpe_ratio"]
            else "option_a_still_better_or_equal"
        ),
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Option A baseline (prob_magnitude, conf_min={PRODUCTION_CONF_MIN}):")
    print(f"  Sharpe={baseline['sharpe_ratio']:.4f} Annual={baseline['annual_return']:.4f} "
          f"MDD={baseline['max_drawdown']:.4f} triggers={baseline['late_bull_trigger_days']}")
    print("\nOption B sweep (composite confidence):")
    for r in sweep_results:
        print(f"  conf_min={r['conf_min']:.2f}  Sharpe={r['sharpe_ratio']:.4f}  "
              f"Annual={r['annual_return']:.4f}  MDD={r['max_drawdown']:.4f}  "
              f"triggers={r['late_bull_trigger_days']}")
    print(f"\nBest Option B: conf_min={best['conf_min']:.2f} Sharpe={best['sharpe_ratio']:.4f}")
    print(f"Decision: {result['decision']}")
    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
