#!/usr/bin/env python3
"""Update persistent GroupA+ alert state from the latest live signal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from group_a_plus.operations.alert_state import (  # noqa: E402
    DEFAULT_ALERT_STATE_PATH,
    DEFAULT_LIVE_SIGNAL_PATH,
    DEFAULT_NETWORK_SPILLOVER_PATH,
    update_alert_state_from_files,
)
from group_a_plus.operations.push_notifications import send_alert_notifications  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", type=Path, default=DEFAULT_LIVE_SIGNAL_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_ALERT_STATE_PATH)
    parser.add_argument("--network-spillover", type=Path, default=DEFAULT_NETWORK_SPILLOVER_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--now", default=None, help="Override current time for deterministic tests, ISO format.")
    args = parser.parse_args()

    state = update_alert_state_from_files(
        live_signal_path=args.live_signal,
        state_path=args.state,
        network_spillover_path=args.network_spillover,
        output_path=args.output,
        now_iso=args.now,
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    send_alert_notifications(state)


if __name__ == "__main__":
    main()
