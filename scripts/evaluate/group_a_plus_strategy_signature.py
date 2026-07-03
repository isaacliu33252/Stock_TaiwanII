#!/usr/bin/env python3
"""Build a deterministic bench signature for the latest GroupA+ strategy."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, OutputType, write_standard_output


DEFAULT_LIVE_SIGNAL_PATH = PROJECT_ROOT / "results/group_a_plus_live_signal_v2.json"
DEFAULT_RUNNER_PATH = PROJECT_ROOT / "results/group_a_plus_runner_latest_20260620.json"
DEFAULT_NCF_PATH = PROJECT_ROOT / "results/ncf_00631l_20260630.json"
DEFAULT_PANEL_PATH = PROJECT_ROOT / "results/ncf_00631l_panel_latest_20260630.csv"
DEFAULT_STRATEGY_MANIFEST_PATH = PROJECT_ROOT / "report/group_a_plus/latest/strategy.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "results/group_a_plus_strategy_bench_signature.json"

VOLATILE_KEYS = {
    "generated_at",
    "timestamp",
    "execution_time_ms",
    "requested_as_of_date",
    "path",
    "files",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _unwrap_standard_json(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _round_number(value: Any, ndigits: int = 10) -> Any:
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, ndigits)
    return value


def stable_value(value: Any) -> Any:
    """Return a JSON-stable value, excluding timestamps and other volatile keys."""

    if isinstance(value, dict):
        return {
            str(key): stable_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in VOLATILE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [stable_value(item) for item in value]
    if pd.isna(value):
        return None
    return _round_number(value)


def signature_for_payload(payload: dict[str, Any]) -> str:
    stable_payload = stable_value(payload)
    text = json.dumps(stable_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _get_path(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cursor: Any = data
    for key in keys:
        if not isinstance(cursor, dict) or key not in cursor:
            return default
        cursor = cursor[key]
    return cursor


def _horizon_snapshot(ncf: dict[str, Any], horizon: str) -> dict[str, Any]:
    classification = _get_path(ncf, "horizons", horizon, "classification", default={}) or {}
    regression = _get_path(ncf, "horizons", horizon, "regression", default={}) or {}
    return {
        "probability_up": classification.get("probability_up"),
        "direction": classification.get("direction"),
        "val_auc": classification.get("val_auc"),
        "predicted_return": regression.get("predicted_return"),
    }


def latest_panel_snapshot(panel_path: Path, signal_date: str | None) -> dict[str, Any]:
    if not panel_path.exists():
        return {"status": "missing", "path": str(panel_path)}

    panel = pd.read_csv(panel_path, encoding="utf-8-sig")
    if panel.empty:
        return {"status": "empty", "path": str(panel_path)}

    if signal_date and "date" in panel.columns:
        matched = panel.loc[panel["date"].astype(str) == str(signal_date)]
        row = matched.iloc[-1] if not matched.empty else panel.iloc[-1]
        date_match = not matched.empty
    else:
        row = panel.iloc[-1]
        date_match = False

    fields = [
        "date",
        "prob_up_h1",
        "prob_up_h5",
        "prob_up_h20",
        "h20_prob_up",
        "confidence",
        "is_live",
        "tail_reward_risk_score_h20",
        "prob_fwd_mdd_gt5_h20",
        "prob_fwd_gain_gt5_h20",
    ]
    snapshot = {field: row[field] for field in fields if field in row.index}
    snapshot["status"] = "ok"
    snapshot["date_match"] = date_match
    snapshot["row_count"] = int(len(panel))
    return snapshot


def build_strategy_signature(
    *,
    live_signal_path: Path = DEFAULT_LIVE_SIGNAL_PATH,
    runner_path: Path = DEFAULT_RUNNER_PATH,
    ncf_path: Path = DEFAULT_NCF_PATH,
    panel_path: Path = DEFAULT_PANEL_PATH,
    strategy_manifest_path: Path = DEFAULT_STRATEGY_MANIFEST_PATH,
) -> dict[str, Any]:
    live = _unwrap_standard_json(_read_json(live_signal_path))
    runner = _unwrap_standard_json(_read_json(runner_path))
    ncf = _read_json(ncf_path)
    strategy_manifest = _read_json(strategy_manifest_path)

    actual_data_date = live.get("actual_data_date") or ncf.get("last_close_date")
    panel = latest_panel_snapshot(panel_path, actual_data_date)

    ncf_horizons = {horizon: _horizon_snapshot(ncf, horizon) for horizon in ("1", "5", "20")}
    signature_payload = {
        "active_strategy": _get_path(strategy_manifest, "active_strategy", default={}),
        "live_signal": {
            "signal_version": live.get("signal_version"),
            "strategy_id": live.get("strategy_id"),
            "strategy_status": live.get("strategy_status"),
            "actual_data_date": actual_data_date,
            "business_stale_days": live.get("business_stale_days"),
            "execution_allowed": live.get("execution_allowed"),
            "execution_guard_reasons": live.get("execution_guard_reasons"),
            "base_regime": live.get("base_regime"),
            "execution_regime": live.get("execution_regime"),
            "regime_reason": live.get("regime_reason"),
            "last_transition_date": live.get("last_transition_date"),
            "strategy_transition_today": live.get("strategy_transition_today"),
            "action": live.get("action"),
            "target_weights": live.get("target_weights"),
            "latest_features": live.get("latest_features"),
            "execution_risk": live.get("execution_risk"),
            "ncf_live_overlay": live.get("ncf_live_overlay"),
            "factor_lens_gate": live.get("factor_lens_gate"),
            "signal_alignment": live.get("signal_alignment"),
        },
        "runner": {
            "experiment": runner.get("experiment"),
            "strategy": runner.get("strategy"),
            "status": runner.get("status"),
            "backtest_mode": runner.get("backtest_mode"),
            "window": runner.get("window"),
            "metrics": runner.get("metrics"),
            "execution": runner.get("execution"),
        },
        "ncf_00631l": {
            "ticker": ncf.get("ticker"),
            "last_close_date": ncf.get("last_close_date"),
            "last_close": ncf.get("last_close"),
            "current_regime": ncf.get("current_regime"),
            "data_freshness": ncf.get("data_freshness"),
            "labeling_mode": ncf.get("labeling_mode"),
            "horizons": ncf_horizons,
            "horizon_ensemble": ncf.get("horizon_ensemble"),
            "forward_drawdown_risk": ncf.get("forward_drawdown_risk"),
            "forward_gain_opportunity": ncf.get("forward_gain_opportunity"),
        },
        "panel_latest": panel,
    }

    signature = signature_for_payload(signature_payload)
    summary = {
        "signature": signature,
        "strategy_id": live.get("strategy_id"),
        "actual_data_date": actual_data_date,
        "execution_regime": live.get("execution_regime"),
        "execution_allowed": live.get("execution_allowed"),
        "target_weights": live.get("target_weights"),
        "a2118_overlay": {
            "applied": _get_path(live, "ncf_live_overlay", "a2118_late_bull_hard_overlay_applied"),
            "reason": _get_path(live, "ncf_live_overlay", "a2118_late_bull_overlay_reason"),
            "hold_active": _get_path(live, "ncf_live_overlay", "a2118_late_bull_hold_active"),
            "h20_prob": _get_path(live, "ncf_live_overlay", "a2118_h20_prob"),
            "h5_prob": _get_path(live, "ncf_live_overlay", "a2118_h5_prob"),
            "confidence": _get_path(live, "ncf_live_overlay", "a2118_confidence"),
        },
        "ncf": {
            "h1_probability_up": _get_path(ncf_horizons, "1", "probability_up"),
            "h5_probability_up": _get_path(ncf_horizons, "5", "probability_up"),
            "h20_probability_up": _get_path(ncf_horizons, "20", "probability_up"),
            "ensemble_probability_up": _get_path(ncf, "horizon_ensemble", "calibrated_probability_up"),
            "ensemble_confidence": _get_path(ncf, "horizon_ensemble", "confidence"),
        },
        "panel_latest": panel,
        "runner_metrics": runner.get("metrics"),
        "runner_execution": runner.get("execution"),
        "signal_alignment": live.get("signal_alignment"),
        "source_files": {
            "live_signal": str(live_signal_path),
            "runner": str(runner_path),
            "ncf_00631l": str(ncf_path),
            "panel": str(panel_path),
            "strategy_manifest": str(strategy_manifest_path),
        },
    }
    return {
        "signature": signature,
        "summary": stable_value(summary),
        "signature_payload": stable_value(signature_payload),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", type=Path, default=DEFAULT_LIVE_SIGNAL_PATH)
    parser.add_argument("--runner", type=Path, default=DEFAULT_RUNNER_PATH)
    parser.add_argument("--ncf", type=Path, default=DEFAULT_NCF_PATH)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL_PATH)
    parser.add_argument("--strategy-manifest", type=Path, default=DEFAULT_STRATEGY_MANIFEST_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    standardizer = OutputStandardizer("group_a_plus_strategy_signature")
    try:
        result = build_strategy_signature(
            live_signal_path=args.live_signal,
            runner_path=args.runner,
            ncf_path=args.ncf,
            panel_path=args.panel,
            strategy_manifest_path=args.strategy_manifest,
        )
        payload = standardizer.success(result, OutputType.DICT)
    except Exception as exc:  # pragma: no cover - CLI safety wrapper
        payload = standardizer.error(exc)

    write_standard_output(payload, str(args.output))
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
