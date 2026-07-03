#!/usr/bin/env python3
"""Build a multi-source signal alignment summary from GroupA+ live signal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from group_a_plus.integrations.signal_alignment import (  # noqa: E402
    DEFAULT_LIVE_SIGNAL_PATH,
    DEFAULT_OUTPUT_PATH,
    build_signal_alignment_from_file,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", type=Path, default=DEFAULT_LIVE_SIGNAL_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    result = build_signal_alignment_from_file(args.live_signal, output_path=args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
