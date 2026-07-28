#!/usr/bin/env python3
"""Shadow diagnostic: today's direction_confidence / decision_confidence.

Research-only. Does not change any live signal, target weight, or the
`a2118_dfl_advisory.json` this reads from. See
`group_a_plus/integrations/ncf_decision_calibration.py`'s module docstring
for what these two fields do and do not mean -- in particular,
`decision_confidence` is a rank proxy against a 46-candidate historical
distribution, not a validated outcome-calibrated probability.

Usage:
    PYTHONPATH=. python3 scripts/evaluate/evaluate_ncf_decision_calibration.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.ncf_decision_calibration import (  # noqa: E402
    DEFAULT_DFL_SHADOW_PATH,
    build_snapshot,
    fit_regret_calibration,
    load_calibration_pairs,
    load_historical_regret_distribution,
)

DEFAULT_PANEL = PROJECT_ROOT / "results" / "ncf_00631l_panel_latest_20260707.csv"
DEFAULT_ADVISORY = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_dfl_advisory.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "ncf_decision_calibration_shadow_latest.json"


def _load_latest_panel_row(panel_path: Path) -> tuple[str, dict]:
    panel = pd.read_csv(panel_path, encoding="utf-8-sig")
    row = panel.iloc[-1]
    return str(row["date"]), row.to_dict()


def _load_advisory_decision(advisory_path: Path) -> tuple[str | None, float | None]:
    if not advisory_path.exists():
        return None, None
    payload = json.loads(advisory_path.read_text(encoding="utf-8"))
    selected = payload.get("selected_decision")
    if not selected:
        return None, None
    return selected.get("action"), selected.get("predicted_regret")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", default=str(DEFAULT_PANEL))
    parser.add_argument("--advisory", default=str(DEFAULT_ADVISORY))
    parser.add_argument("--dfl-shadow", default=str(DEFAULT_DFL_SHADOW_PATH))
    parser.add_argument(
        "--use-calibration-model",
        action="store_true",
        help=(
            "Fit the Phase 2 empirical regret calibration (binned P(realized_regret>0) "
            "from calibration_pairs) and use it instead of the Phase 1 percentile-rank "
            "proxy when available. Default off: out-of-sample validation on "
            "2017/2018/2019 (2026-07-27) found CAP10's calibrated probabilities do not "
            "reliably transfer across regimes (direction is right, magnitude is not) -- "
            "see GROUP_A_PLUS_DFL_ACTION_VALUE_CALIBRATION_PHASE2_20260727.md. Kept as an "
            "opt-in research path, not a default, until that improves."
        ),
    )
    parser.add_argument("--calibration-bins", type=int, default=5)
    parser.add_argument("--calibration-min-bin-size", type=int, default=20)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    panel_date, panel_row = _load_latest_panel_row(Path(args.panel))
    action, predicted_regret = _load_advisory_decision(Path(args.advisory))

    calibration_model = None
    if args.use_calibration_model:
        pairs = load_calibration_pairs(Path(args.dfl_shadow))
        calibration_model = fit_regret_calibration(
            pairs,
            n_bins=int(args.calibration_bins),
            min_bin_size=int(args.calibration_min_bin_size),
        )

    snapshot = build_snapshot(
        as_of=panel_date,
        ncf_panel_row=panel_row,
        dfl_action=action,
        dfl_predicted_regret=predicted_regret,
        dfl_shadow_path=Path(args.dfl_shadow),
        calibration_model=calibration_model,
    )

    print(f"as_of: {snapshot.as_of}")
    print(f"direction_confidence: {snapshot.direction_confidence}")
    print(f"decision_confidence: {snapshot.decision_confidence}")
    print(f"calibration_method: {snapshot.calibration_method}")
    print(f"action: {snapshot.action}")
    print(f"basis: {snapshot.basis}")

    historical = load_historical_regret_distribution(Path(args.dfl_shadow))
    print("\nHistorical candidate distribution (shadow-only sanity check, NOT a calibration curve):")
    for act, values in sorted(historical.items()):
        arr = pd.Series(values)
        print(
            f"  {act}: n={len(values)}, predicted_regret "
            f"min={arr.min():.4f} p50={arr.median():.4f} max={arr.max():.4f}"
        )

    output = {
        "report_type": "ncf_decision_calibration_shadow",
        "status": "research_only",
        "snapshot": snapshot.to_json_dict(),
        "historical_distribution_summary": {
            act: {
                "n": len(values),
                "min": min(values),
                "median": float(pd.Series(values).median()),
                "max": max(values),
            }
            for act, values in historical.items()
        },
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
