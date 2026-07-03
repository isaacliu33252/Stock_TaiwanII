#!/usr/bin/env python3
"""Write the GroupA+ read-only ops health report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from group_a_plus.operations.ops_health import DEFAULT_OUTPUT_PATH, PROJECT_ROOT, build_ops_health


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    report = build_ops_health(Path(args.root))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Ops health: {output.resolve()}")
    print(f"Status: {report['status']}")


if __name__ == "__main__":
    main()
