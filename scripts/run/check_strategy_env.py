#!/usr/bin/env python3
"""Check GroupA+ strategy runtime environment and required artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from group_a_plus.operations.strategy_env import (  # noqa: E402
    DEFAULT_OUTPUT_PATH,
    PROJECT_ROOT,
    build_strategy_env_health,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--fail-on-warning", action="store_true")
    args = parser.parse_args()

    report = build_strategy_env_health(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["status"] == "error" or (args.fail_on_warning and report["status"] == "warning"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
