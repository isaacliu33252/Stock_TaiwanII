#!/usr/bin/env python3
"""Replay the saved Group A PPO model with selected payload overrides."""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from backtest_group_a_tdcc_latest import _run_base_backtest


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RESULT_JSON = PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260525_20260526_193252.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_full_replay_override_sweep_20240102_20260604.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-json", default=str(DEFAULT_RESULT_JSON))
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-06-04")
    parser.add_argument("--download-end", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--variants",
        default="baseline,buydip090,buydip085,cap18,cap15,clear5_6,clear7_8",
        help="Comma-separated variant names.",
    )
    return parser.parse_args()


def _resolve(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _variant_payload(base: dict[str, Any], variant: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = copy.deepcopy(base)
    overrides: dict[str, Any] = {}
    if variant == "baseline":
        return payload, overrides

    if variant.startswith("buydip"):
        strength = float(variant.replace("buydip", "")) / 100.0
        payload.setdefault("group_a_pva_sigmoid_config", {})["pva_buy_dip_strength"] = strength
        overrides["pva_buy_dip_strength"] = strength
        return payload, overrides

    if variant.startswith("cap"):
        cap = float(variant.replace("cap", "")) / 100.0
        payload.setdefault("group_a_exposure_caps", {})["00631L.TW"] = cap
        overrides["00631L_cap"] = cap
        return payload, overrides

    if variant.startswith("clear"):
        raw = variant.replace("clear", "")
        risk_clear, severe_clear = [int(item) for item in raw.split("_", 1)]
        cfg = payload.setdefault("group_a_local_regime_gate_config", {})
        cfg["risk_off_clear_days"] = risk_clear
        cfg["severe_clear_days"] = severe_clear
        overrides["risk_off_clear_days"] = risk_clear
        overrides["severe_clear_days"] = severe_clear
        return payload, overrides

    raise ValueError(f"Unsupported variant: {variant}")


def main() -> None:
    args = _parse_args()
    result_json = _resolve(args.result_json)
    base_payload = json.loads(result_json.read_text(encoding="utf-8"))
    download_end = args.download_end or args.end
    variants = [item.strip() for item in str(args.variants).split(",") if item.strip()]
    results = []
    for variant in variants:
        payload, overrides = _variant_payload(base_payload, variant)
        summary, _, _, _ = _run_base_backtest(
            payload,
            result_json,
            start=str(args.start),
            end=str(args.end),
            download_end=str(download_end),
        )
        results.append(
            {
                "variant": variant,
                "overrides": overrides,
                "metrics": {
                    key: summary[key]
                    for key in [
                        "actual_start",
                        "actual_end",
                        "rows",
                        "final_value",
                        "annual_return",
                        "sharpe_ratio",
                        "max_drawdown",
                        "volatility",
                        "num_trades",
                        "fees_paid_estimate",
                        "dca_purchase_count",
                        "dca_total_contributions",
                        "total_invested_capital",
                        "net_profit",
                        "contribution_return",
                    ]
                },
            }
        )
        m = results[-1]["metrics"]
        print(
            f"{variant}: final={m['final_value']:.2f}, sharpe={m['sharpe_ratio']:.4f}, "
            f"mdd={m['max_drawdown']:.4%}, trades={m['num_trades']}, fees={m['fees_paid_estimate']:.2f}"
        )

    baseline = next((item for item in results if item["variant"] == "baseline"), results[0])
    base_metrics = baseline["metrics"]
    for item in results:
        metrics = item["metrics"]
        item["delta_vs_baseline"] = {
            "final_value": metrics["final_value"] - base_metrics["final_value"],
            "sharpe_ratio": metrics["sharpe_ratio"] - base_metrics["sharpe_ratio"],
            "max_drawdown": metrics["max_drawdown"] - base_metrics["max_drawdown"],
            "num_trades": metrics["num_trades"] - base_metrics["num_trades"],
            "fees_paid_estimate": metrics["fees_paid_estimate"] - base_metrics["fees_paid_estimate"],
        }

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "experiment": "group_a_full_replay_override_sweep",
        "method_note": "No retraining. Replays the saved Group A PPO model while overriding selected payload parameters.",
        "source_result_json": str(result_json.resolve()),
        "requested_window": {"start": args.start, "end": args.end, "download_end": download_end},
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "results": results,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for item in results:
        rows.append(
            {
                "variant": item["variant"],
                **item["metrics"],
                **{f"delta_{key}": value for key, value in item["delta_vs_baseline"].items()},
            }
        )
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")


if __name__ == "__main__":
    main()
