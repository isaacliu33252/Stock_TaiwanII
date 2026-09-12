#!/usr/bin/env python3
"""Build a GJR-GARCH post-trigger severity shadow advisory.

GJR-GARCH is not used as a crash trigger here. It is only evaluated as a
severity modifier after an existing leverage-cap trigger is already active.
No live weights, signal pointers, or execution plans are changed.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.gjr_garch_shadow import compute_gjr_garch_shadow  # noqa: E402
from group_a_plus.runners.a2126 import (  # noqa: E402
    A2126_DRAWDOWN_MAX,
    A2126_REALIZED_VOL_RATIO_MIN,
    A2126_TAIL_RISK_SCORE_MIN,
)

DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_OOS = PROJECT_ROOT / "results" / "gjr_garch_oos_forecast_quality_00631l.json"
DEFAULT_OPPORTUNITY = PROJECT_ROOT / "results" / "a2126_leverage_cap_trend_persistent_overlap_20260822.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gjr_post_trigger_severity_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gjr_post_trigger_severity_shadow.md"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "results"
SIGNAL_GLOB = "results/group_a_plus_live_signal_v2_*.json"


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _latest_signal_path(pattern: str = SIGNAL_GLOB) -> Path:
    paths = [
        Path(path)
        for path in glob.glob(str(_resolve(pattern)))
        if not path.endswith("_pointer.json")
    ]
    if not paths:
        raise FileNotFoundError(f"No signal files matched {pattern!r}")
    return max(paths, key=lambda path: path.stat().st_mtime)


def _load_signal(path: str | Path) -> dict[str, Any]:
    payload = _load_json(path)
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _realized_vol_ratio_20_60(db_path: Path, ticker: str, as_of: str) -> float | None:
    as_of_ts = pd.Timestamp(as_of).normalize()
    start = (as_of_ts - pd.Timedelta(days=180)).strftime("%Y-%m-%d")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, close
            FROM ohlcv
            WHERE ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, start, str(as_of_ts.date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return None
    rows["dt"] = pd.to_datetime(rows["dt"]).dt.normalize()
    ret = rows.set_index("dt")["close"].astype(float).pct_change().dropna()
    if len(ret) < 60:
        return None
    vol60 = float(ret.tail(60).std())
    if vol60 <= 0.0:
        return None
    return float(ret.tail(20).std() / vol60)


def _oos_gate(oos: dict[str, Any]) -> dict[str, Any]:
    overall = oos.get("overall") if isinstance(oos.get("overall"), dict) else {}
    tail = oos.get("tail_5pct_worst_realized_days") if isinstance(oos.get("tail_5pct_worst_realized_days"), dict) else {}
    overall_dm = overall.get("qlike_diebold_mariano") if isinstance(overall.get("qlike_diebold_mariano"), dict) else {}
    tail_dm = tail.get("qlike_diebold_mariano") if isinstance(tail.get("qlike_diebold_mariano"), dict) else {}
    return {
        "overall_qlike_significant": bool(overall_dm.get("significant_at_5pct") is True and overall_dm.get("a_more_accurate") is True),
        "tail_qlike_significant": bool(tail_dm.get("significant_at_5pct") is True and tail_dm.get("a_more_accurate") is True),
        "overall_qlike_p_value": overall_dm.get("p_value"),
        "tail_qlike_p_value": tail_dm.get("p_value"),
        "tail_underpred_frac_gjr": tail.get("underpred_frac_gjr"),
    }


def _opportunity_context(opportunity: dict[str, Any]) -> dict[str, Any]:
    breakdown = opportunity.get("breakdown_by_tuned_regime") if isinstance(opportunity.get("breakdown_by_tuned_regime"), dict) else {}
    trend = breakdown.get("TREND_PERSISTENT") if isinstance(breakdown.get("TREND_PERSISTENT"), dict) else {}
    return {
        "trigger_day_count": breakdown.get("trigger_day_count"),
        "trend_persistent_count": trend.get("count"),
        "trend_persistent_forward_20d_mean": trend.get("forward_20d_mean"),
        "trend_persistent_forward_20d_positive_rate": trend.get("forward_20d_positive_rate"),
        "interpretation": "A21.26 cap triggers can have material opportunity cost in TREND_PERSISTENT regimes.",
    }


def build_gjr_post_trigger_shadow(
    *,
    signal: dict[str, Any],
    gjr_shadow: dict[str, Any],
    oos_report: dict[str, Any],
    opportunity_report: dict[str, Any],
    realized_vol_ratio_20_60: float | None,
) -> dict[str, Any]:
    latest = signal.get("latest_features") if isinstance(signal.get("latest_features"), dict) else {}
    actual = str(signal.get("actual_data_date") or "")
    tail_score = int(_num(latest.get("tail_risk_score"), 0.0))
    drawdown = _num(latest.get("drawdown"), 0.0)
    vol_ratio = realized_vol_ratio_20_60
    trigger_reasons: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []

    if tail_score >= A2126_TAIL_RISK_SCORE_MIN:
        trigger_reasons.append("tail_risk_score_ge_threshold")
    else:
        blockers.append("a2126_tail_risk_condition_inactive")
    if vol_ratio is not None and vol_ratio >= A2126_REALIZED_VOL_RATIO_MIN:
        trigger_reasons.append("realized_vol_ratio_20_60_ge_threshold")
    else:
        blockers.append("a2126_realized_vol_ratio_condition_inactive")
    if drawdown <= A2126_DRAWDOWN_MAX:
        trigger_reasons.append("drawdown_le_threshold")
    else:
        blockers.append("a2126_drawdown_condition_inactive")
    if str(signal.get("execution_regime") or "") != "golden1":
        blockers.append("execution_regime_not_golden1")
    if gjr_shadow.get("status") != "available":
        blockers.append("gjr_shadow_unavailable")

    oos = _oos_gate(oos_report)
    if not oos["overall_qlike_significant"]:
        blockers.append("gjr_overall_oos_gate_not_significant")
    if not oos["tail_qlike_significant"]:
        warnings.append("gjr_tail_oos_gate_not_significant_so_severity_only")

    trigger_active = not any(item.startswith("a2126_") or item == "execution_regime_not_golden1" for item in blockers)
    gjr_ratio = _num(gjr_shadow.get("forecast_variance_ratio_gjr_over_symmetric"), 1.0)
    asymmetry_shock = bool(gjr_shadow.get("gjr_asymmetry_shock") is True)
    evidence_level = str(gjr_shadow.get("evidence_level") or "none")

    if not trigger_active:
        recommended = "inactive_no_existing_trigger"
        severity_cap = None
    elif asymmetry_shock:
        recommended = "full_existing_leverage_cap_allowed"
        severity_cap = 1.0
    elif evidence_level == "watch" or gjr_ratio >= 1.05:
        recommended = "medium_severity_partial_cap_only"
        severity_cap = 0.50
    else:
        recommended = "low_severity_defer_or_minimal_cap"
        severity_cap = 0.25

    active = trigger_active and gjr_shadow.get("status") == "available" and oos["overall_qlike_significant"]
    return {
        "schema_version": 1,
        "report_type": "gjr_post_trigger_severity_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "shadow_only_no_live_weight_change",
        "live_execution_effect": "none",
        "status": "active_shadow_candidate" if active else "inactive",
        "actual_data_date": actual or None,
        "candidate_policy": "gjr_garch_as_severity_modifier_after_existing_a2126_trigger_only",
        "recommended_shadow_action": recommended,
        "severity_cap_fraction_of_existing_leverage_cap": severity_cap,
        "trigger_active": trigger_active,
        "trigger_reasons": trigger_reasons,
        "blockers": blockers,
        "warnings": warnings,
        "inputs": {
            "a2126_thresholds": {
                "tail_risk_score_min": A2126_TAIL_RISK_SCORE_MIN,
                "realized_vol_ratio_20_60_min": A2126_REALIZED_VOL_RATIO_MIN,
                "drawdown_max": A2126_DRAWDOWN_MAX,
            },
            "latest_features": {
                "tail_risk_score": tail_score,
                "drawdown": drawdown,
                "ma_gap": latest.get("ma_gap"),
                "exit_momentum_5d": latest.get("exit_momentum_5d"),
            },
            "realized_vol_ratio_20_60": vol_ratio,
            "gjr_shadow": {
                "date": gjr_shadow.get("date"),
                "evidence_level": evidence_level,
                "forecast_variance_ratio_gjr_over_symmetric": gjr_shadow.get("forecast_variance_ratio_gjr_over_symmetric"),
                "gjr_asymmetry_shock": gjr_shadow.get("gjr_asymmetry_shock"),
                "latest_return": gjr_shadow.get("latest_return"),
                "lr_p_value": (gjr_shadow.get("likelihood_ratio_test") or {}).get("p_value"),
            },
            "oos_gate": oos,
            "opportunity_context": _opportunity_context(opportunity_report),
        },
        "promotion_requirements": [
            "historical replay of GJR severity caps on A21.26 trigger dates",
            "tail-subset OOS variance forecast evidence must clear 5pct significance or remain severity-only",
            "must not create a new trigger; only modify severity after an existing trigger",
        ],
    }


def _write_md(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# GJR Post-Trigger Severity Shadow",
        "",
        f"- Status: `{payload['status']}`",
        f"- Recommended shadow action: `{payload['recommended_shadow_action']}`",
        f"- Trigger active: `{payload['trigger_active']}`",
        f"- Live effect: `{payload['live_execution_effect']}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in payload["blockers"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- `{item}`" for item in payload["warnings"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", default=None)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--oos-report", default=str(DEFAULT_OOS))
    parser.add_argument("--opportunity-report", default=str(DEFAULT_OPPORTUNITY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    args = parser.parse_args()

    signal_path = _resolve(args.signal) if args.signal else _latest_signal_path()
    signal = _load_signal(signal_path)
    actual = str(signal.get("actual_data_date") or "")
    db_path = _resolve(args.db)
    gjr = compute_gjr_garch_shadow(db_path, actual) if actual else {"status": "unavailable", "reason": "missing_actual_date"}
    vol_ratio = _realized_vol_ratio_20_60(db_path, "00631L.TW", actual) if actual else None
    payload = build_gjr_post_trigger_shadow(
        signal=signal,
        gjr_shadow=gjr,
        oos_report=_load_json(args.oos_report),
        opportunity_report=_load_json(args.opportunity_report),
        realized_vol_ratio_20_60=vol_ratio,
    )
    payload["source_signal_path"] = str(signal_path)

    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_md(_resolve(args.output_md), payload)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = _resolve(args.results_dir) / f"gjr_post_trigger_severity_shadow_{stamp}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "result_path": str(result_path), "status": payload["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
