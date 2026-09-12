#!/usr/bin/env python3
"""Build the GroupA+ review for arXiv:2605.20636 continuous timing signals."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PDF = Path("/mnt/c/Users/isaac/Downloads/2605.20636.pdf")
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2605_20636_continuous_timing_review.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report/group_a_plus/latest/2605_20636_continuous_timing_review.md"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2605_20636_continuous_timing_review/history"
DEFAULT_LATEST_STRATEGY = PROJECT_ROOT / "results/group_a_plus_latest_strategy_predict_20260831_from_20260828_total1000000.json"
DEFAULT_CHECKLIST = PROJECT_ROOT / "GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md"
DEFAULT_A2119_HANDOFF = PROJECT_ROOT / "GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md"
DEFAULT_A2119_SCRIPT = PROJECT_ROOT / "scripts/evaluate/evaluate_a2119_continuous_defensive_tilt_shadow.py"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _target_weights(payload: dict[str, Any]) -> dict[str, float]:
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("target_weights"), dict):
        return {str(k): float(v) for k, v in data["target_weights"].items()}
    weights = payload.get("target_weights")
    if isinstance(weights, dict):
        return {str(k): float(v) for k, v in weights.items()}
    return {}


def _contains(path: Path, text: str) -> bool:
    if not path.exists():
        return False
    return text in path.read_text(encoding="utf-8", errors="ignore")


def build_review(
    *,
    pdf_path: Path = DEFAULT_PDF,
    latest_strategy_path: Path = DEFAULT_LATEST_STRATEGY,
    checklist_path: Path = DEFAULT_CHECKLIST,
    a2119_handoff_path: Path = DEFAULT_A2119_HANDOFF,
    a2119_script_path: Path = DEFAULT_A2119_SCRIPT,
    as_of: str = "2026-08-28",
) -> dict[str, Any]:
    latest_strategy = _load_optional_json(latest_strategy_path)
    weights = _target_weights(latest_strategy)
    checklist_adopted = _contains(checklist_path, "Continuous Timing Signals for")
    a2119_shadow_exists = a2119_script_path.exists()
    a2119_final_rejected = _contains(a2119_handoff_path, "do not promote")

    blockers = [
        "asset_universe_mismatch_growth_defensive_us_etfs_vs_groupa_plus_taiwan_letf_bond_cash",
        "continuous_score_replacement_of_discrete_regime_not_validated_for_latest_strategy",
        "a2119_shadow_candidate_not_promoted",
        "growth_crowding_penalty_tested_and_rejected",
        "credit_and_vix_credit_components_remain_shadow_only",
        "high_turnover_risk_from_continuous_timing_style",
        "research_only_review_no_target_weight_change",
    ]
    if not checklist_adopted:
        blockers.append("validation_checklist_not_found")
    if not a2119_shadow_exists:
        blockers.append("a2119_shadow_script_not_found")
    if not a2119_final_rejected:
        blockers.append("a2119_final_rejection_not_confirmed")

    imported_process = checklist_adopted
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2605_20636_continuous_timing_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked_for_live_promotion",
        "source_paper": {
            "path": str(pdf_path),
            "exists": pdf_path.exists(),
            "title": "Continuous Timing Signals for Growth-Defensive Style Allocation: Factor Attribution, Risk Matching, and Out-of-Sample Evidence",
            "arxiv": "2605.20636v2",
            "author": "Zheli Xiong",
            "paper_date": "2026-05-29",
            "main_idea": "continuous smooth-score timing between a growth/technology ETF basket and a defensive income/value ETF basket",
        },
        "paper_takeaways": [
            {
                "concept": "three-tier OOS validation plus crisis-independence and cost sensitivity",
                "groupa_plus_action": "adopted_as_process_checklist",
                "live_impact": "none",
                "artifact": str(checklist_path),
                "usable": imported_process,
            },
            {
                "concept": "continuous tanh-mapped growth/defensive allocation score",
                "groupa_plus_action": "tested_as_a2119_continuous_defensive_tilt_shadow",
                "live_impact": "none",
                "artifact": str(a2119_handoff_path),
                "usable": False,
                "reason": "closest GroupA+ analog was mixed/negative and not promoted",
            },
            {
                "concept": "growth-crowding penalty",
                "groupa_plus_action": "implemented_and_backtested_in_a2119_shadow",
                "live_impact": "none",
                "usable": False,
                "reason": "standalone IC was real but blended backtests worsened across key windows",
            },
            {
                "concept": "credit relief/stress via HYG-SHY and VIX-credit interaction",
                "groupa_plus_action": "tested_after_related_RGRR_review",
                "live_impact": "none",
                "usable": False,
                "reason": "interesting shadow evidence but final A21.19 line remained unpromoted",
            },
        ],
        "latest_strategy_context": {
            "path": str(latest_strategy_path),
            "strategy_id": (latest_strategy.get("data") or {}).get("strategy_id"),
            "requested_as_of_date": (latest_strategy.get("data") or {}).get("requested_as_of_date"),
            "actual_data_date": (latest_strategy.get("data") or {}).get("actual_data_date"),
            "target_weights": weights,
        },
        "assessment": {
            "has_importable_advantage": True,
            "best_import": "validation_checklist_only",
            "strategy_logic_importable": False,
            "latest_strategy_weight_change_supported": False,
            "notes": [
                "The paper is about US growth-versus-defensive style timing, not Taiwan LETF hedge sizing.",
                "GroupA+ already tested the closest continuous defensive-tilt analog as A21.19 and did not promote it.",
                "The durable benefit is evaluation discipline: multi-window OOS, crisis-independence, incremental admission, and cost sensitivity.",
            ],
        },
        "experiment_scope_decision": {
            "groupa_plus_importability_complete": True,
            "full_paper_replication_complete": False,
            "full_paper_replication_required_for_strategy_decision": False,
            "completed_evidence": [
                "local PDF extraction and method review",
                "existing A21.19 continuous defensive tilt lineage review",
                "validation checklist adoption confirmation",
                "latest strategy target-weight cross-check",
                "live-promotion blocker audit",
            ],
            "not_replicated": [
                "exact US ETF basket backtest tables",
                "paper's full factor attribution suite",
                "paper's full benchmark grid",
            ],
            "reason": (
                "The remaining unreproduced paper experiments validate the author's US "
                "growth/defensive ETF universe, not a GroupA+ Taiwan LETF/inverse/bond/cash "
                "allocation rule."
            ),
        },
        "blocking_reasons": sorted(set(blockers)),
        "decision": {
            "review_complete": True,
            "process_checklist_already_imported": imported_process,
            "promote_continuous_score_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "checklist": str(checklist_path),
            "a2119_handoff": str(a2119_handoff_path),
            "a2119_shadow_script": str(a2119_script_path),
        },
    }


def render_markdown(review: dict[str, Any]) -> str:
    decision = review.get("decision") or {}
    weights = (review.get("latest_strategy_context") or {}).get("target_weights") or {}
    lines = [
        "# 2605.20636 Continuous Timing Review",
        "",
        f"Generated: `{review.get('generated_at')}`",
        f"As of: `{review.get('as_of')}`",
        f"Status: `{review.get('status')}`",
        "",
        "## Decision",
        "",
        "- Do not import the continuous smooth-score allocation as live strategy logic.",
        "- Keep the validation checklist as the only adopted benefit.",
        "- Do not change latest strategy target weights.",
        "- Do not open or increase `00632R.TW`; do not unlock `00631L.TW`.",
        "- Keep `Golden1_0531` unchanged.",
        "",
        "## Latest Strategy Context",
        "",
    ]
    lines.extend(f"- `{ticker}`: `{weight:.6f}`" for ticker, weight in weights.items())
    lines.extend(
        [
            "",
            "## Imported Benefit",
            "",
            "- Adopted: multi-window OOS / crisis-independence / cost-sensitivity validation discipline.",
            "- Rejected for live: continuous tanh timing score, growth-crowding penalty, credit/VIX-credit overlays.",
            "",
            "## Experiment Scope",
            "",
            "- GroupA+ importability experiments: `complete`.",
            "- Full paper replication: `not complete` and `not required` for this strategy decision.",
            "- Reason: remaining paper tables validate the author's US ETF universe, not GroupA+ Taiwan LETF/inverse/bond/cash allocation.",
            "",
            "## Decision Flags",
            "",
            f"- `process_checklist_already_imported`: `{decision.get('process_checklist_already_imported')}`",
            f"- `target_weight_change_allowed`: `{decision.get('target_weight_change_allowed')}`",
            f"- `allow_00631l_add`: `{decision.get('allow_00631l_add')}`",
            f"- `allow_00632r_open`: `{decision.get('allow_00632r_open')}`",
            "",
            "## Blockers",
            "",
        ]
    )
    lines.extend(f"- `{reason}`" for reason in review.get("blocking_reasons", []))
    lines.append("")
    return "\n".join(lines)


def _history_path(history_dir: Path, as_of: str) -> Path:
    return history_dir / f"2605_20636_continuous_timing_review_{as_of.replace('-', '')}.json"


def write_review(
    review: dict[str, Any],
    output_path: Path,
    output_md_path: Path | None = DEFAULT_OUTPUT_MD,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md_path is not None:
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
        output_md_path.write_text(render_markdown(review) + "\n", encoding="utf-8")
    if history_dir is None:
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    _history_path(history_dir, str(review.get("as_of") or datetime.now().strftime("%Y-%m-%d"))).write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--latest-strategy", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--checklist", default=str(DEFAULT_CHECKLIST))
    parser.add_argument("--a2119-handoff", default=str(DEFAULT_A2119_HANDOFF))
    parser.add_argument("--a2119-script", default=str(DEFAULT_A2119_SCRIPT))
    parser.add_argument("--as-of", default="2026-08-28")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        pdf_path=_resolve(args.pdf),
        latest_strategy_path=_resolve(args.latest_strategy),
        checklist_path=_resolve(args.checklist),
        a2119_handoff_path=_resolve(args.a2119_handoff),
        a2119_script_path=_resolve(args.a2119_script),
        as_of=args.as_of,
    )
    output_md = None if not args.output_md else _resolve(args.output_md)
    write_review(review, _resolve(args.output), output_md, None if args.no_history else _resolve(args.history_dir))
    print(f"2605.20636 continuous timing review: {_resolve(args.output)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "best_import": review["assessment"]["best_import"],
                "process_checklist_already_imported": review["decision"]["process_checklist_already_imported"],
                "target_weight_change_allowed": review["decision"]["target_weight_change_allowed"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
                "allow_00632r_open": review["decision"]["allow_00632r_open"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
