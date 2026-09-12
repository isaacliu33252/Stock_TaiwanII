#!/usr/bin/env python3
"""CLI wrapper: TSMC concentration-divergence + top-5 breadth diagnostic.

Research-only, read-only. Does not change any live weight or execution
plan. See group_a_plus/integrations/tsmc_concentration_divergence.py for
the underlying math and its caveats (top-5 mega-cap proxy, not full
~50-constituent breadth; TSMC weight officially calibrated, other 4
weights are a research-only proxy).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.integrations.tsmc_concentration_divergence import top5_breadth_snapshot
from tw_output_standard import OutputStandardizer, write_standard_output

DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/tsmc_concentration_divergence_breadth.json"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    std = OutputStandardizer("scripts.evaluate.build_tsmc_concentration_divergence_breadth_snapshot")
    try:
        snapshot = top5_breadth_snapshot(_resolve(args.db), args.as_of)
        payload = std.success({
            "report_type": "tsmc_concentration_divergence_breadth",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "requested_as_of": args.as_of,
            "snapshot": snapshot,
        })
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"TSMC concentration divergence breadth: {_resolve(args.output)}")
    if payload.get("success"):
        print(json.dumps(payload["data"]["snapshot"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
