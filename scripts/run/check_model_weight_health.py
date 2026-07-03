#!/usr/bin/env python3
"""Write GroupA+ read-only model weight health shadow report."""

from __future__ import annotations

import argparse
from pathlib import Path

from group_a_plus.operations.model_weight_health import (
    DEFAULT_MODEL_PATH,
    DEFAULT_OUTPUT_PATH,
    build_model_weight_health,
)
from tw_output_standard import OutputStandardizer, write_standard_output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=str(DEFAULT_MODEL_PATH))
    parser.add_argument("--model-type", choices=["auto", "torch", "sb3"], default="auto")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    std = OutputStandardizer("scripts.run.check_model_weight_health")
    try:
        report = build_model_weight_health(args.model, model_type=args.model_type)
        payload = std.success(report)
    except Exception as exc:  # noqa: BLE001
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    print(f"Model weight health: {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
