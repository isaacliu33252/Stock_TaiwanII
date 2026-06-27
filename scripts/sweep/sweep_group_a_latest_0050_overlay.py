#!/usr/bin/env python3
"""Sweep lightweight 0050 execution overlays for the latest Group A payload."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from compare_group_a_0050_only_2025_20260611 import (
    LATEST_PAYLOAD,
    PROJECT_ROOT,
    START,
    END,
    _capture_events,
    _replay_0050_only,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_latest_0050_overlay_sweep_20250102_20260611.json"


def _parse_float_list(value: str) -> list[float | None]:
    items: list[float | None] = []
    for raw in value.split(","):
        text = raw.strip().lower()
        if not text:
            continue
        if text in {"none", "off", "null"}:
            items.append(None)
        else:
            items.append(float(text))
    if not items:
        raise ValueError("list must contain at least one value")
    return items


def _parse_int_list(value: str) -> list[int | None]:
    items: list[int | None] = []
    for raw in value.split(","):
        text = raw.strip().lower()
        if not text:
            continue
        if text in {"none", "off", "null"}:
            items.append(None)
        else:
            items.append(int(text))
    if not items:
        raise ValueError("list must contain at least one value")
    return items


def _variant_name(
    *,
    step: float | None,
    ma_window: int | None,
    ma_cap: float | None,
    ma_ratio: float,
    min_delta: float,
) -> str:
    step_part = "step_off" if step is None else f"step{int(round(step * 10000)):04d}bp"
    if ma_window is None or ma_cap is None:
        ma_part = "ma_off"
    else:
        ratio_part = f"r{int(round(ma_ratio * 1000)):04d}"
        ma_part = f"ma{ma_window}_{ratio_part}_cap{int(round(ma_cap * 100)):02d}"
    delta_part = f"mindelta{int(round(min_delta * 1000)):03d}bp"
    return f"{step_part}_{ma_part}_{delta_part}"


def _score(row: dict[str, Any], baseline: dict[str, Any]) -> float:
    final_delta_pct = float(row["final_value"]) / max(float(baseline["final_value"]), 1.0) - 1.0
    sharpe_delta = float(row["sharpe_ratio"]) - float(baseline["sharpe_ratio"])
    mdd_improvement = float(row["max_drawdown"]) - float(baseline["max_drawdown"])
    cost_delta_pct = (float(row["total_cost"]) - float(baseline["total_cost"])) / max(
        float(baseline["final_value"]),
        1.0,
    )
    return float(final_delta_pct + 0.10 * sharpe_delta + 0.50 * mdd_improvement - 0.25 * cost_delta_pct)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    parser.add_argument("--payload", default=str(LATEST_PAYLOAD))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--steps", default="none,0.02,0.03,0.04,0.05")
    parser.add_argument("--ma-windows", default="none,40,60,80")
    parser.add_argument("--ma-ratios", default="1.0")
    parser.add_argument("--ma-caps", default="0.45,0.47,0.50")
    parser.add_argument("--min-deltas", default="0.0,0.005,0.01")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    payload_path = Path(args.payload)
    if not payload_path.is_absolute():
        payload_path = (PROJECT_ROOT / payload_path).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = (PROJECT_ROOT / output).resolve()

    captured = _capture_events("latest_group_a", payload_path, args.start, args.end)
    baseline_result = _replay_0050_only(captured)
    baseline_metrics = baseline_result["metrics"]

    steps = _parse_float_list(args.steps)
    ma_windows = _parse_int_list(args.ma_windows)
    ma_ratios = [float(item) for item in _parse_float_list(args.ma_ratios) if item is not None]
    ma_caps = _parse_float_list(args.ma_caps)
    min_deltas = [float(item) for item in _parse_float_list(args.min_deltas) if item is not None]

    rows: list[dict[str, Any]] = [
        {
            "variant": "latest_group_a_raw",
            "max_weight_step": None,
            "ma_brake_window": None,
            "ma_brake_max_weight": None,
            "min_rebalance_delta": 0.0,
            **baseline_metrics,
            "score": 0.0,
            "changed_events": 0,
            "skipped_small_delta_events": 0,
            "ma_brake_events": 0,
        }
    ]
    details: dict[str, Any] = {"latest_group_a_raw": baseline_result}

    for step in steps:
        for min_delta in min_deltas:
            overlay = {
                "max_weight_step": step,
                "min_rebalance_delta": min_delta,
            }
            name = _variant_name(step=step, ma_window=None, ma_cap=None, ma_ratio=1.0, min_delta=min_delta)
            result = _replay_0050_only(captured, weight_overlay=overlay)
            report = result["weight_overlay"]
            row = {
                "variant": name,
                "max_weight_step": step,
                "ma_brake_window": None,
                "ma_brake_max_weight": None,
                "min_rebalance_delta": min_delta,
                **result["metrics"],
                "changed_events": int(report.get("changed_events", 0)),
                "skipped_small_delta_events": int(report.get("skipped_small_delta_events", 0)),
                "ma_brake_events": int(report.get("ma_brake_events", 0)),
            }
            row["score"] = _score(row, baseline_metrics)
            rows.append(row)
            details[name] = result

            for ma_window in ma_windows:
                if ma_window is None:
                    continue
                for ma_ratio in ma_ratios:
                    for ma_cap in ma_caps:
                        if ma_cap is None:
                            continue
                        overlay = {
                            "max_weight_step": step,
                            "min_rebalance_delta": min_delta,
                            "ma_brake_window": ma_window,
                            "ma_brake_ratio": ma_ratio,
                            "ma_brake_max_weight": ma_cap,
                        }
                        name = _variant_name(
                            step=step,
                            ma_window=ma_window,
                            ma_cap=ma_cap,
                            ma_ratio=ma_ratio,
                            min_delta=min_delta,
                        )
                        result = _replay_0050_only(captured, weight_overlay=overlay)
                        report = result["weight_overlay"]
                        row = {
                            "variant": name,
                            "max_weight_step": step,
                            "ma_brake_window": ma_window,
                            "ma_brake_ratio": ma_ratio,
                            "ma_brake_max_weight": ma_cap,
                            "min_rebalance_delta": min_delta,
                            **result["metrics"],
                            "changed_events": int(report.get("changed_events", 0)),
                            "skipped_small_delta_events": int(report.get("skipped_small_delta_events", 0)),
                            "ma_brake_events": int(report.get("ma_brake_events", 0)),
                        }
                        row["score"] = _score(row, baseline_metrics)
                        rows.append(row)
                        details[name] = result

    ranked = sorted(
        rows,
        key=lambda item: (
            float(item["score"]),
            float(item["final_value"]),
            float(item["sharpe_ratio"]),
            float(item["max_drawdown"]),
        ),
        reverse=True,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.with_suffix(".csv")
    payload = {
        "experiment": "group_a_latest_0050_overlay_sweep",
        "method": (
            "Replay latest Group A target 0050 weight only; non-0050 exposure is cash. "
            "Sweep step limits, MA trend brake, and small-delta trade suppression."
        ),
        "payload": str(payload_path),
        "requested_window": {"start": args.start, "end": args.end},
        "actual_window": {"start": captured["actual_start"], "end": captured["actual_end"]},
        "baseline": "latest_group_a_raw",
        "score": "final_delta_pct + 0.10*sharpe_delta + 0.50*mdd_improvement - 0.25*cost_delta_pct, all versus raw latest_group_a",
        "top_variants": ranked[:20],
        "rows": rows,
        "details": {name: details[name] for name in [item["variant"] for item in ranked[:10]]},
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).sort_values("score", ascending=False).to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    print("Top variants:")
    for row in ranked[:10]:
        print(
            f"{row['variant']}: score={row['score']:.5f}, final={row['final_value']:.2f}, "
            f"sharpe={row['sharpe_ratio']:.4f}, mdd={row['max_drawdown']:.4%}, "
            f"cost={row['total_cost']:.2f}, rebalances={row['num_rebalances']}"
        )


if __name__ == "__main__":
    main()
