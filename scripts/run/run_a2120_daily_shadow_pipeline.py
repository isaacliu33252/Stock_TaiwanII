#!/usr/bin/env python3
"""Run A21.20 LETF compounding daily shadow-only artifacts.

This pipeline writes advisory artifacts only.  It does not mutate production
strategy manifests, execution plans, or holdings.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate.build_a2120_letf_compounding_shadow_scorecard import (  # noqa: E402
    DEFAULT_COST20,
    DEFAULT_OVERLAP,
    DEFAULT_ROLLING,
    DEFAULT_7WIN,
    build_scorecard,
)
from scripts.evaluate.evaluate_00631l_compounding_execution_replay_shadow import build_report as build_replay_report  # noqa: E402
from scripts.evaluate.evaluate_00631l_leveraged_compounding_regime import build_report as build_diagnostic_report  # noqa: E402
from scripts.evaluate.evaluate_turnover_capped_execution_shadow import _read_plan, turnover_capped_shadow  # noqa: E402
from scripts.evaluate.evaluate_a2119_a2120_combined_policy_shadow import build_report as build_combined_report  # noqa: E402


DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results"
DEFAULT_LATEST_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "latest"
DEFAULT_SHADOW_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "shadow"
DEFAULT_DB = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_A2119 = PROJECT_ROOT / "results" / "a2119_reentry_regret_gate_7win_20260715.json"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _stamp() -> str:
    return date.today().strftime("%Y%m%d")


def _diagnostic_args(args: argparse.Namespace, output: Path, csv: Path) -> SimpleNamespace:
    return SimpleNamespace(
        db=args.db,
        start=args.start,
        end=args.end,
        recent_days=args.recent_days,
        ar1_trend_min=0.00,
        ar1_revert_max=-0.15,
        variance_ratio_trend_min=1.02,
        variance_ratio_revert_max=0.98,
        trend_persistence_min=0.50,
        trend_persistence_revert_max=0.55,
        reversal_speed_revert_min=0.55,
        reversal_speed_trend_max=0.50,
        drawdown_recovery_revert_min=0.50,
        trend_score_min=3,
        mean_reversion_score_min=5,
        output=str(output),
        csv=str(csv),
    )


def _replay_args(args: argparse.Namespace, compounding_path: Path, output: Path) -> SimpleNamespace:
    return SimpleNamespace(
        execution_plan=str(args.execution_plan),
        compounding_regime=str(compounding_path),
        baseline_add_fraction=0.40,
        mean_reversion_add_fraction=0.00,
        trend_persistent_add_fraction=1.00,
        weak_trend_edge_gate="none",
        weak_trend_add_fraction=0.90,
        output=str(output),
    )


def _risk_sensitive_replay_args(args: argparse.Namespace, compounding_path: Path, output: Path) -> SimpleNamespace:
    return SimpleNamespace(
        execution_plan=str(args.execution_plan),
        compounding_regime=str(compounding_path),
        baseline_add_fraction=0.40,
        mean_reversion_add_fraction=0.00,
        trend_persistent_add_fraction=1.00,
        weak_trend_edge_gate="ce20_negative",
        weak_trend_add_fraction=0.90,
        output=str(output),
    )


def build_latest_summary(
    *,
    date_stamp: str,
    diagnostic: dict[str, Any],
    replay: dict[str, Any],
    turnover: dict[str, Any],
    scorecard: dict[str, Any],
    combined: dict[str, Any] | None = None,
    risk_sensitive_replay: dict[str, Any] | None = None,
    risk_sensitive_turnover: dict[str, Any] | None = None,
    artifacts: dict[str, str],
) -> dict[str, Any]:
    latest = diagnostic.get("latest") if isinstance(diagnostic.get("latest"), dict) else {}
    replay_payload = replay.get("replay") if isinstance(replay.get("replay"), dict) else {}
    shadow_plan = ((turnover.get("result") or {}).get("shadow_plan") or {}) if isinstance(turnover.get("result"), dict) else {}
    risk_payload = (
        risk_sensitive_replay.get("replay")
        if isinstance(risk_sensitive_replay, dict) and isinstance(risk_sensitive_replay.get("replay"), dict)
        else {}
    )
    risk_shadow_plan = (
        ((risk_sensitive_turnover.get("result") or {}).get("shadow_plan") or {})
        if isinstance(risk_sensitive_turnover, dict) and isinstance(risk_sensitive_turnover.get("result"), dict)
        else {}
    )
    return {
        "schema_version": 1,
        "report_type": "a2120_letf_compounding_daily_shadow",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "date_stamp": date_stamp,
        "research_only": True,
        "production_effect": "none",
        "candidate": scorecard.get("candidate"),
        "daily_state": {
            "date": latest.get("date"),
            "compounding_regime": latest.get("compounding_regime"),
            "raw_action": replay_payload.get("raw_action"),
            "recommended_action": replay_payload.get("recommended_action"),
            "hard_blockers": replay_payload.get("hard_blockers"),
            "shadow_target_00631l_before_hard_guards": replay_payload.get("shadow_target_shares_before_hard_guards"),
            "turnover50_target_00631l": (shadow_plan.get("target_shares") or {}).get("00631L.TW"),
            "turnover50_ratio": shadow_plan.get("turnover_ratio"),
            "combined_action": ((combined or {}).get("combined") or {}).get("combined_action"),
        },
        "risk_sensitive_variant": {
            "name": "ce20_negative_to_trend90",
            "raw_action": risk_payload.get("raw_action"),
            "recommended_action": risk_payload.get("recommended_action"),
            "weak_trend_edge_gate": risk_payload.get("weak_trend_edge_gate"),
            "weak_trend_edge_active": risk_payload.get("weak_trend_edge_active"),
            "allowed_fraction_for_regime": risk_payload.get("allowed_fraction_for_regime"),
            "shadow_target_00631l_before_hard_guards": risk_payload.get("shadow_target_shares_before_hard_guards"),
            "turnover50_target_00631l": (risk_shadow_plan.get("target_shares") or {}).get("00631L.TW"),
            "turnover50_ratio": risk_shadow_plan.get("turnover_ratio"),
        },
        "scorecard_decision": scorecard.get("decision"),
        "artifacts": artifacts,
    }


def _combined_args(args: argparse.Namespace, a2120_latest_path: Path, output: Path) -> SimpleNamespace:
    return SimpleNamespace(
        a2119_report=str(args.a2119_report),
        a2120_latest=str(a2120_latest_path),
        a2119_action=None,
        output=str(output),
    )


def run_pipeline(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = Path(args.output_dir)
    latest_dir = Path(args.latest_dir)
    shadow_dir = Path(args.shadow_dir)
    date_stamp = args.date_stamp

    diagnostic_path = output_dir / f"00631l_leveraged_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_{date_stamp}.json"
    diagnostic_csv = output_dir / f"00631l_leveraged_compounding_regime_tunedtrend_score3_ar0_persist50_rev50_{date_stamp}.csv"
    diagnostic = build_diagnostic_report(_diagnostic_args(args, diagnostic_path, diagnostic_csv))
    _write_json(diagnostic_path, diagnostic)

    replay_path = output_dir / f"00631l_compounding_execution_replay_shadow_tunedtrend_score3_ar0_persist50_rev50_{date_stamp}.json"
    replay = build_replay_report(_replay_args(args, diagnostic_path, replay_path))
    _write_json(replay_path, replay)

    risk_replay_path = output_dir / (
        f"00631l_compounding_execution_replay_shadow_tunedtrend_score3_ar0_persist50_rev50"
        f"_ce20neg_to_trend90_{date_stamp}.json"
    )
    risk_replay = build_replay_report(_risk_sensitive_replay_args(args, diagnostic_path, risk_replay_path))
    _write_json(risk_replay_path, risk_replay)

    replay_payload = replay["replay"]
    target_00631l = int(replay_payload.get("shadow_target_shares_before_hard_guards") or 0)
    turnover_path = output_dir / f"turnover_capped_execution_shadow_{date_stamp}_tunedtrend_00631l{target_00631l}_risk_first.json"
    turnover_result = turnover_capped_shadow(
        _read_plan(Path(args.execution_plan)),
        cap_ratio=float(args.turnover_cap),
        priority_mode="risk_first",
        target_overrides={"00631L.TW": target_00631l},
    )
    turnover = {
        "schema_version": 1,
        "experiment": "turnover_capped_execution_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "execution_plan_path": str(args.execution_plan),
        "result": turnover_result,
    }
    _write_json(turnover_path, turnover)

    risk_replay_payload = risk_replay["replay"]
    risk_target_00631l = int(risk_replay_payload.get("shadow_target_shares_before_hard_guards") or 0)
    risk_turnover_path = output_dir / (
        f"turnover_capped_execution_shadow_{date_stamp}_tunedtrend_ce20neg90_"
        f"00631l{risk_target_00631l}_risk_first.json"
    )
    risk_turnover_result = turnover_capped_shadow(
        _read_plan(Path(args.execution_plan)),
        cap_ratio=float(args.turnover_cap),
        priority_mode="risk_first",
        target_overrides={"00631L.TW": risk_target_00631l},
    )
    risk_turnover = {
        "schema_version": 1,
        "experiment": "turnover_capped_execution_shadow",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_only": True,
        "production_effect": "none",
        "execution_plan_path": str(args.execution_plan),
        "variant": "ce20_negative_to_trend90",
        "result": risk_turnover_result,
    }
    _write_json(risk_turnover_path, risk_turnover)

    scorecard_path = shadow_dir / f"a2120_letf_compounding_shadow_scorecard_{date_stamp}.json"
    scorecard = build_scorecard(
        seven_window_report=_read_json(Path(args.seven_window_report)),
        cost20_report=_read_json(Path(args.cost20_report)),
        turnover_report=turnover,
        overlap_report=_read_json(Path(args.overlap_report)),
        replay_report=replay,
        rolling_report=_read_json(Path(args.rolling_report)),
    )
    scorecard["inputs"] = {
        "seven_window_report": str(Path(args.seven_window_report)),
        "cost20_report": str(Path(args.cost20_report)),
        "turnover_report": str(turnover_path),
        "overlap_report": str(Path(args.overlap_report)),
        "replay_report": str(replay_path),
        "rolling_report": str(Path(args.rolling_report)),
    }
    _write_json(scorecard_path, scorecard)

    latest_path = latest_dir / "a2120_letf_compounding_shadow.json"
    artifacts = {
        "diagnostic": str(diagnostic_path),
        "diagnostic_csv": str(diagnostic_csv),
        "execution_replay": str(replay_path),
        "risk_sensitive_execution_replay": str(risk_replay_path),
        "turnover_capped_replay": str(turnover_path),
        "risk_sensitive_turnover_capped_replay": str(risk_turnover_path),
        "scorecard": str(scorecard_path),
    }
    latest = build_latest_summary(
        date_stamp=date_stamp,
        diagnostic=diagnostic,
        replay=replay,
        turnover=turnover,
        scorecard=scorecard,
        combined=None,
        risk_sensitive_replay=risk_replay,
        risk_sensitive_turnover=risk_turnover,
        artifacts=artifacts,
    )
    _write_json(latest_path, latest)

    combined_path = shadow_dir / f"a2119_a2120_combined_policy_shadow_{date_stamp}.json"
    combined = build_combined_report(_combined_args(args, latest_path, combined_path))
    _write_json(combined_path, combined)
    artifacts["combined_policy"] = str(combined_path)
    latest = build_latest_summary(
        date_stamp=date_stamp,
        diagnostic=diagnostic,
        replay=replay,
        turnover=turnover,
        scorecard=scorecard,
        combined=combined,
        risk_sensitive_replay=risk_replay,
        risk_sensitive_turnover=risk_turnover,
        artifacts=artifacts,
    )
    _write_json(latest_path, latest)

    return {
        "diagnostic": diagnostic_path,
        "execution_replay": replay_path,
        "risk_sensitive_execution_replay": risk_replay_path,
        "turnover_capped_replay": turnover_path,
        "risk_sensitive_turnover_capped_replay": risk_turnover_path,
        "scorecard": scorecard_path,
        "combined_policy": combined_path,
        "latest": latest_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-stamp", default=_stamp())
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--start", default="2015-01-05")
    parser.add_argument("--end", default="latest")
    parser.add_argument("--recent-days", type=int, default=20)
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--turnover-cap", type=float, default=0.50)
    parser.add_argument("--seven-window-report", default=str(DEFAULT_7WIN))
    parser.add_argument("--cost20-report", default=str(DEFAULT_COST20))
    parser.add_argument("--rolling-report", default=str(DEFAULT_ROLLING))
    parser.add_argument("--overlap-report", default=str(DEFAULT_OVERLAP))
    parser.add_argument("--a2119-report", default=str(DEFAULT_A2119))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--latest-dir", default=str(DEFAULT_LATEST_DIR))
    parser.add_argument("--shadow-dir", default=str(DEFAULT_SHADOW_DIR))
    args = parser.parse_args()

    paths = run_pipeline(args)
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
