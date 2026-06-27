#!/usr/bin/env python3
"""Replay the current production Group A stepgate + TDCC overlay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from compare_group_a_0050_only_2025_20260611 import LATEST_PAYLOAD, PROJECT_ROOT, START, END, _capture_events
from evaluate_group_a_tdcc_overlay_variants import Variant, _apply_hysteresis, _overlay_weights, _raw_tdcc_state
from sweep_group_a_latest_multiticker_overlay import _overlay_events, _replay_multiticker


DEFAULT_CONFIG = PROJECT_ROOT / "group_a_tdcc_improved_config_destination_primary.json"
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "results" / "group_a_latest_stepgate105_tdcc_replay_20250102_20260611.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    parser.add_argument("--payload", default=str(LATEST_PAYLOAD))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--caution-caps", default=None)
    parser.add_argument("--risk-off-caps", default=None)
    parser.add_argument("--destinations", default=None)
    return parser.parse_args()


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


def _parse_float_list(raw: str | None, default: list[float]) -> list[float]:
    if raw is None:
        return default
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_str_list(raw: str | None, default: list[str]) -> list[str]:
    if raw is None:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _apply_tdcc_to_events(
    captured: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    config: dict[str, Any],
    db_path: Path,
    raw_by_date: dict[pd.Timestamp, dict[str, Any]] | None = None,
    effective_states_by_date: dict[tuple[float, float, str], dict[pd.Timestamp, str]] | None = None,
    caution_cap: float | None = None,
    risk_off_cap: float | None = None,
    destination: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    caution_cap = float(config["caution"]["leverage_weight_cap"] if caution_cap is None else caution_cap)
    risk_off_cap = float(config["risk_off"]["leverage_weight_cap"] if risk_off_cap is None else risk_off_cap)
    destination = str(config.get("released_leverage_budget_destination", "cash") if destination is None else destination)
    variant = Variant(
        "production_tdcc_destination_primary",
        risk_off_cap=risk_off_cap,
        caution_cap=caution_cap,
        destination=destination,
        primary_fraction=float(config.get("released_to_primary_fraction", 0.5)),
    )
    dates = list(captured["prices"].index)
    raw = raw_by_date if raw_by_date is not None else {dt: _raw_tdcc_state(config, db_path, dt) for dt in dates}
    cache_key = (caution_cap, risk_off_cap, destination)
    if effective_states_by_date is not None and cache_key in effective_states_by_date:
        state_by_date = effective_states_by_date[cache_key]
    else:
        raw_states = [str(raw[dt]["state"]) for dt in dates]
        effective_states = _apply_hysteresis(raw_states, variant)
        state_by_date = dict(zip(dates, effective_states))
        if effective_states_by_date is not None:
            effective_states_by_date[cache_key] = state_by_date
    event_out = []
    changed = 0
    state_counts: dict[str, int] = {}
    for event in events:
        dt = pd.Timestamp(event["date"]).normalize()
        state = str(state_by_date.get(dt, "normal"))
        state_counts[state] = state_counts.get(state, 0) + 1
        weights = {ticker: float(weight) for ticker, weight in dict(event["target_weights"]).items()}
        cash = float(event.get("target_cash_weight", max(0.0, 1.0 - sum(weights.values()))))
        adjusted_weights, adjusted_cash = _overlay_weights(
            weights,
            cash,
            state,
            variant,
            config,
            raw[dt],
        )
        if any(abs(adjusted_weights.get(t, 0.0) - weights.get(t, 0.0)) > 1e-12 for t in set(weights) | set(adjusted_weights)):
            changed += 1
        item = dict(event)
        item["pre_tdcc_target_weights"] = weights
        item["pre_tdcc_target_cash_weight"] = cash
        item["tdcc_state"] = state
        item["target_weights"] = adjusted_weights
        item["target_cash_weight"] = adjusted_cash
        event_out.append(item)
    return event_out, {
        "changed_events": changed,
        "event_state_counts": state_counts,
        "caution_cap": caution_cap,
        "risk_off_cap": risk_off_cap,
        "destination": destination,
    }


def main() -> None:
    args = _parse_args()
    payload_path = _resolve(args.payload)
    config_path = _resolve(args.config)
    db_path = _resolve(args.db)
    output = _resolve(args.output)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    captured = _capture_events("latest_group_a", payload_path, args.start, args.end)
    raw_by_date = {dt: _raw_tdcc_state(config, db_path, dt) for dt in captured["prices"].index}
    effective_states_by_date: dict[tuple[float, float, str], dict[pd.Timestamp, str]] = {}
    raw_result = _replay_multiticker(captured)
    step_events, step_report = _overlay_events(
        captured,
        max_0050_step=0.03,
        step_mode="both",
        step_active_max_ma_ratio=1.05,
        min_0050_delta=0.0,
        ma_window=60,
        ma_ratio=1.0,
        ma_0050_cap=0.30,
        ma_00631l_cap=0.0,
    )
    step_captured = dict(captured)
    step_captured["events"] = step_events
    step_result = _replay_multiticker(step_captured)

    rows = [
        {"strategy": "latest_group_a_raw", **raw_result["metrics"]},
        {"strategy": "latest_stepgate105_ma60_brake", **step_result["metrics"]},
    ]
    details = {
        "latest_group_a_raw": raw_result,
        "latest_stepgate105_ma60_brake": step_result,
    }

    caution_caps = _parse_float_list(args.caution_caps, [float(config["caution"]["leverage_weight_cap"])])
    risk_off_caps = _parse_float_list(args.risk_off_caps, [float(config["risk_off"]["leverage_weight_cap"])])
    destinations = _parse_str_list(args.destinations, [str(config.get("released_leverage_budget_destination", "cash"))])
    tdcc_reports: dict[str, Any] = {}
    for caution_cap in caution_caps:
        for risk_off_cap in risk_off_caps:
            for destination in destinations:
                name = f"latest_stepgate105_tdcc_caution{int(round(caution_cap * 100)):02d}_riskoff{int(round(risk_off_cap * 100)):02d}_{destination}"
                tdcc_events, tdcc_report = _apply_tdcc_to_events(
                    captured,
                    step_events,
                    config=config,
                    db_path=db_path,
                    raw_by_date=raw_by_date,
                    effective_states_by_date=effective_states_by_date,
                    caution_cap=caution_cap,
                    risk_off_cap=risk_off_cap,
                    destination=destination,
                )
                tdcc_captured = dict(captured)
                tdcc_captured["events"] = tdcc_events
                tdcc_result = _replay_multiticker(tdcc_captured)
                rows.append({"strategy": name, **tdcc_result["metrics"]})
                details[name] = tdcc_result
                tdcc_reports[name] = tdcc_report

    rows = sorted(rows, key=lambda row: (row["sharpe_ratio"], row["final_value"]), reverse=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "experiment": "group_a_latest_stepgate105_tdcc_replay",
                "payload": str(payload_path),
                "config": str(config_path),
                "actual_window": {"start": captured["actual_start"], "end": captured["actual_end"]},
                "step_overlay": step_report,
                "tdcc_overlays": tdcc_reports,
                "rows": rows,
                "details": details,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    csv_path = output.with_suffix(".csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"JSON: {output}")
    print(f"CSV:  {csv_path}")
    for row in rows:
        print(
            f"{row['strategy']}: final={row['final_value']:.2f}, "
            f"sharpe={row['sharpe_ratio']:.4f}, mdd={row['max_drawdown']:.4%}, "
            f"vol={row['volatility']:.4f}, cost={row['total_cost']:.2f}"
        )


if __name__ == "__main__":
    main()
