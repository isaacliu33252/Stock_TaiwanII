#!/usr/bin/env python3
"""FinRL-Meta Style Promotion Gate — Group A+ rolling retrain trigger.

Reads the latest backtest JSON, evaluates promotion_gate, and:
  - decision=promotion_candidate  → print promotion recommendation
  - decision=retrain_candidate     → log + schedule retrain cron
  - decision=shadow_risk_control_only → log risk-control-only status
  - decision=no_action            → log and do nothing

Usage:
  python check_promotion_gate.py
  python check_promotion_gate.py --backtest results/group_a_plus_vix_turbulence_backtest_20250101_20260608.json
  python check_promotion_gate.py --watch  # continuous monitoring mode (cron)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_BACKTEST = (
    PROJECT_ROOT
    / "results"
    / "group_a_plus_vix_turbulence_backtest_20250101_20260608.json"
)
DEFAULT_RECOMMENDATION_LOG = PROJECT_ROOT / "results" / "retrain_recommendations.json"


def _load_backtest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Backtest JSON not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _evaluate_gate(gate: dict[str, Any]) -> str:
    """Evaluate promotion gate and return action recommendation."""
    decision = str(gate.get("decision") or "")
    thresholds = gate.get("thresholds", {})

    if decision == "retrain_candidate":
        return "schedule_retrain"
    elif decision == "promotion_candidate":
        return "promote_and_deploy"
    elif decision == "shadow_risk_control_only":
        return "risk_control_mode"
    elif decision == "no_action":
        return "monitor"
    else:
        return "unknown"


def _build_recommendation(report: dict[str, Any]) -> dict[str, Any]:
    """Build a structured recommendation from backtest report."""
    gate = report.get("summary", {}).get("promotion_gate", {})
    decision = str(gate.get("decision") or "")
    rationale = str(gate.get("rationale") or "")
    thresholds = gate.get("thresholds", {})
    variants = gate.get("variants", [])

    # Find best variant by final value
    best_final = max(variants, key=lambda v: v.get("final_drag_pct", 0), default=None)
    best_sharpe = max(variants, key=lambda v: v.get("sharpe_delta", -999), default=None)

    # Collect metrics from summary
    summary = report.get("summary", {})
    best_plus = summary.get("best_plus_by_final_value", "unknown")

    recommendation = {
        "generated_at": datetime.now().isoformat(),
        "decision": decision,
        "rationale": rationale,
        "thresholds_applied": {
            "promotion_max_final_drag_pct": thresholds.get("promotion_max_final_drag_pct"),
            "promotion_min_sharpe_delta": thresholds.get("promotion_min_sharpe_delta"),
            "risk_control_min_volatility_reduction": thresholds.get(
                "risk_control_min_volatility_reduction"
            ),
            "risk_control_max_final_drag_pct": thresholds.get("risk_control_max_final_drag_pct"),
            "retrain_min_mdd_improvement": thresholds.get("retrain_min_mdd_improvement"),
            "retrain_max_final_drag_pct": thresholds.get("retrain_max_final_drag_pct"),
        },
        "best_return_variant": gate.get("best_return_variant", best_plus),
        "best_risk_variant": gate.get("best_risk_variant", best_plus),
        "all_variants_tested": [
            {
                "variant": v.get("variant"),
                "final_drag_pct": round(v.get("final_drag_pct", 0), 4),
                "sharpe_delta": round(v.get("sharpe_delta", 0), 4),
                "mdd_improvement": round(v.get("mdd_improvement", 0), 4),
                "volatility_reduction": round(v.get("volatility_reduction", 0), 4),
                "return_upgrade_candidate": v.get("return_upgrade_candidate", False),
                "risk_control_candidate": v.get("risk_control_candidate", False),
                "retrain_candidate": v.get("retrain_candidate", False),
            }
            for v in variants
        ],
    }

    # Base reference metrics
    base_ref = gate.get("base_reference", {})
    recommendation["base_reference"] = {
        "final_value": round(base_ref.get("final_value", 0), 2),
        "sharpe_ratio": round(base_ref.get("sharpe_ratio", 0), 4),
        "max_drawdown": round(base_ref.get("max_drawdown", 0), 4),
        "volatility": round(base_ref.get("volatility", 0), 4),
    }

    return recommendation


def _print_recommendation(rec: dict[str, Any]) -> None:
    decision = rec["decision"]
    rationale = rec["rationale"]

    print("=" * 60)
    print(f"  PROMOTION GATE REPORT  —  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    print(f"  Decision:       {decision}")
    print(f"  Rationale:      {rationale}")
    print()
    print(f"  Base reference: final={rec['base_reference']['final_value']:,.0f}, "
          f"sharpe={rec['base_reference']['sharpe_ratio']:.4f}, "
          f"mdd={rec['base_reference']['max_drawdown']:.4f}")
    print()
    print(f"  Best return variant: {rec['best_return_variant']}")
    print(f"  Best risk variant:   {rec['best_risk_variant']}")
    print()

    if decision == "retrain_candidate":
        print("  >>> ACTION REQUIRED: Schedule new training run!")
        print("  Recommendation: re-run training with current config and")
        print("                   re-evaluate via backtest_group_a_plus_overlay.py")
    elif decision == "promotion_candidate":
        print("  >>> PROMOTION RECOMMENDED: Ready for production deployment.")
    elif decision == "shadow_risk_control_only":
        print("  >>> Risk-control mode only: GroupA+ reduces volatility but")
        print("      Sharpe/return drag too large for promotion. Use as hedge.")
    elif decision == "no_action":
        print("  >>> No action needed: current model is performing well.")

    print()
    print("  Variant summary:")
    for v in rec["all_variants_tested"]:
        flags = []
        if v["return_upgrade_candidate"]:
            flags.append("UPGRADE")
        if v["risk_control_candidate"]:
            flags.append("RISK_CTRL")
        if v["retrain_candidate"]:
            flags.append("RETRAIN")
        flag_str = f"[{','.join(flags)}]" if flags else ""
        print(
            f"    {v['variant']:<50} "
            f"drag={v['final_drag_pct']:+.4f}  "
            f"sharpe={v['sharpe_delta']:+.4f}  "
            f"vol={v['volatility_reduction']:+.4f}  "
            f"{flag_str}"
        )
    print("=" * 60)


def _save_recommendation(rec: dict[str, Any], log_path: Path) -> None:
    """Append recommendation to a rolling log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing log or start fresh
    if log_path.exists():
        try:
            with open(log_path, encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []
    else:
        existing = []

    # Keep last 30 entries
    existing = existing[-29:] + [rec]

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def _schedule_retrain_cron(rec: dict[str, Any]) -> None:
    """Schedule a retrain cron job via Hermes scheduler if decision is retrain_candidate."""
    decision = rec["decision"]
    if decision != "retrain_candidate":
        return

    print("\n[promotion-gate] Decision=retrain_candidate — manual cron setup required.")
    print("[promotion-gate] To schedule automatically, run:")
    print("  hermes cron create \\")
    print("    --name group_a_retrain_triggered \\")
    print("    --schedule '0 9 * * 1,4' \\")
    print("    --prompt 'Retrain Group A after promotion gate retrain_candidate. "
          "Best variant: {}'".format(rec.get("best_return_variant", "unknown")))


def _check_sac_ddpg_availability() -> dict[str, bool]:
    """Check if SAC/DDPG models are available in the project."""
    available = {"sac": False, "ddpg": False}

    # Check for SAC/DDPG checkpoint patterns
    patterns = {
        "sac": ["*sac*.zip", "*SAC*.zip"],
        "ddpg": ["*ddpg*.zip", "*DDPG*.zip"],
    }

    for model, pats in patterns.items():
        for pat in pats:
            matches = list(PROJECT_ROOT.glob(f"**/{pat}"))
            if matches:
                available[model] = True

    # Also check stable_baselines3
    try:
        from stable_baselines3 import SAC, DDPG
        available["sac"] = True
        available["ddpg"] = True
    except ImportError:
        pass

    return available


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backtest",
        default=str(DEFAULT_BACKTEST),
        help="Path to backtest_group_a_plus_overlay.py output JSON",
    )
    parser.add_argument(
        "--log",
        default=str(DEFAULT_RECOMMENDATION_LOG),
        help="Path to save recommendation log (append mode)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode: run check every 6 hours (for long-running monitoring)",
    )
    parser.add_argument(
        "--no-cron",
        action="store_true",
        help="Skip automatic cron scheduling even if retrain_candidate",
    )
    args = parser.parse_args()

    backtest_path = Path(args.backtest)
    log_path = Path(args.log)

    print(f"Checking promotion gate: {backtest_path}")

    # Check SAC/DDPG availability
    models_avail = _check_sac_ddpg_availability()
    if models_avail["sac"] or models_avail["ddpg"]:
        print(f"[ensemble] Available models: SAC={models_avail['sac']}, DDPG={models_avail['ddpg']}")

    # Load backtest
    try:
        report = _load_backtest(backtest_path)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Build recommendation
    rec = _build_recommendation(report)

    # Print human-readable report
    _print_recommendation(rec)

    # Save to log
    _save_recommendation(rec, log_path)
    print(f"\nRecommendation saved to: {log_path}")

    # Schedule cron if retrain_candidate
    if not args.no_cron and rec["decision"] == "retrain_candidate":
        _schedule_retrain_cron(rec)

    # Watch mode loop
    if args.watch:
        import time

        print("\n[watch] Running in watch mode — check every 6 hours. Press Ctrl+C to stop.")
        interval = 6 * 3600
        while True:
            time.sleep(interval)
            print(f"\n[{datetime.now().isoformat()}] Re-checking promotion gate...")
            try:
                report = _load_backtest(backtest_path)
                rec = _build_recommendation(report)
                _print_recommendation(rec)
                _save_recommendation(rec, log_path)
            except Exception as e:
                print(f"[watch] Error: {e}")

    # Exit with appropriate code
    if rec["decision"] in ("retrain_candidate", "promotion_candidate"):
        sys.exit(0)  # Action available
    else:
        sys.exit(0)  # No error, just informational


if __name__ == "__main__":
    main()