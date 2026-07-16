#!/usr/bin/env python3
"""Convert the risk-score-lookback candidate results into multi-window-gate-
compatible per-window report files.

Reads `results/group_a_plus_risk_score_lookback_candidate_20260706.json`
(produced by `scripts/misc/evaluate_risk_score_lookback_candidate_20260706.py`)
and writes one JSON per window in the shape
`evaluate_group_a_plus_multi_window_gate.py` already knows how to parse
(`baseline` + `summary.best_by_*`), so the same governance gate used for
every other GroupA+ candidate in this repo can score this one too.

lookback_days=3/5/10 were bit-identical in every window this session, so all
three `summary.best_by_*` keys point at the lookback=5 variant (arbitrary
pick among the identical set) -- there is only one meaningfully distinct
candidate here, not three.

Research-only. Does not touch any production file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_LOOKBACK_DAYS = "5"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="results/group_a_plus_risk_score_lookback_candidate_20260706.json",
    )
    parser.add_argument(
        "--output-dir",
        default="results/risk_score_lookback_multi_window_reports_20260706",
    )
    args = parser.parse_args()

    input_path = PROJECT_ROOT / args.input
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for window_name, window_result in payload["windows"].items():
        baseline_metrics = window_result["lookback_days"]["0"]["metrics"]
        candidate_metrics = window_result["lookback_days"][CANDIDATE_LOOKBACK_DAYS]["metrics"]
        report = {
            "experiment": f"risk_score_lookback_candidate_{window_name}",
            "window": window_name,
            "baseline": {"metrics": baseline_metrics},
            "summary": {
                "best_by_final_value": {"metrics": candidate_metrics},
                "best_by_max_drawdown": {"metrics": candidate_metrics},
                "best_by_sharpe": {"metrics": candidate_metrics},
            },
        }
        out_path = output_dir / f"{window_name}.json"
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(str(out_path.relative_to(PROJECT_ROOT)))

    print(f"Wrote {len(written)} per-window reports to {output_dir.relative_to(PROJECT_ROOT)}:")
    for path in written:
        print(f"  {path}")


if __name__ == "__main__":
    main()
