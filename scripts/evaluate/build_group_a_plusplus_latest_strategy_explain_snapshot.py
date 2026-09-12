#!/usr/bin/env python3
"""Build a stable explanation snapshot for the current GroupA++ strategy."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LATEST_DIR = PROJECT_ROOT / "report/group_a_plus/latest"
DEFAULT_WATCHLIST = PROJECT_ROOT / "config/group_a_plus_watchlist.json"
DEFAULT_TARGET_WEIGHTS = LATEST_DIR / "latest_strategy_historical_target_weights.json"
DEFAULT_RESEARCH_GOVERNANCE = LATEST_DIR / "research_governance_gate.json"
DEFAULT_SHADOW_REGISTRY = LATEST_DIR / "shadow_artifact_registry.json"
DEFAULT_OUTPUT = LATEST_DIR / "group_a_plusplus_latest_strategy_explain_snapshot.json"
DEFAULT_OUTPUT_MD = LATEST_DIR / "group_a_plusplus_latest_strategy_explain_snapshot.md"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")


def _watchlist_symbols(watchlist: dict[str, Any]) -> list[str]:
    symbols = watchlist.get("symbols") or []
    if not isinstance(symbols, list):
        return []
    out = []
    for item in symbols:
        if isinstance(item, dict) and item.get("symbol"):
            out.append(str(item["symbol"]))
    return out


def _short_symbol(symbol: str) -> str:
    if symbol == "cash":
        return "cash"
    return symbol.split(".", 1)[0]


def _governance_status(payload: dict[str, Any]) -> dict[str, Any]:
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    return {
        "status": payload.get("status"),
        "policy": payload.get("policy"),
        "promotion_allowed": decision.get("promotion_allowed"),
        "target_weight_change_allowed": decision.get("target_weight_change_allowed"),
        "changes_latest_strategy": decision.get("changes_latest_strategy"),
        "changes_golden1_0531": decision.get("changes_golden1_0531"),
        "changes_golden2_0830": decision.get("changes_golden2_0830"),
        "order_generation_allowed": decision.get("order_generation_allowed"),
    }


def build_snapshot(
    *,
    watchlist_path: Path,
    target_weights_path: Path,
    research_governance_path: Path,
    shadow_registry_path: Path,
    as_of: str | None,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    watchlist = _load_json(watchlist_path)
    target_weights = _load_json(target_weights_path)
    research_governance = _load_json(research_governance_path)
    shadow_registry = _load_json(shadow_registry_path)

    if not watchlist:
        blockers.append("missing_group_a_plusplus_watchlist")
    if not target_weights:
        blockers.append("missing_latest_strategy_historical_target_weights")
    if not research_governance:
        warnings.append("missing_research_governance_gate")
    if not shadow_registry:
        warnings.append("missing_shadow_artifact_registry")

    watchlist_symbols = _watchlist_symbols(watchlist)
    target_assets = [str(item) for item in (target_weights.get("target_assets") or [])]
    target_asset_set = set(target_assets)
    watchlist_short = {_short_symbol(symbol) for symbol in watchlist_symbols if symbol != "2330.TW"}
    missing_watchlist_assets = sorted(asset for asset in watchlist_short if asset not in target_asset_set and asset != "cash")
    if missing_watchlist_assets:
        warnings.append("watchlist_assets_missing_from_latest_target_weight_export")

    regime_weight_map = target_weights.get("regime_weight_map") if isinstance(target_weights.get("regime_weight_map"), dict) else {}
    regime_sums = {
        str(regime): round(sum(float(value or 0.0) for value in weights.values()), 10)
        for regime, weights in regime_weight_map.items()
        if isinstance(weights, dict)
    }
    bad_regime_sums = sorted(regime for regime, total in regime_sums.items() if abs(total - 1.0) > 1e-6)
    if bad_regime_sums:
        warnings.append("some_regime_weight_maps_do_not_sum_to_one")

    target_decision = target_weights.get("decision") if isinstance(target_weights.get("decision"), dict) else {}
    research_status = _governance_status(research_governance)
    shadow_summary = shadow_registry.get("summary") if isinstance(shadow_registry.get("summary"), dict) else {}

    status = "blocked" if blockers else ("warning" if warnings else "available")
    return {
        "schema_version": 1,
        "report_type": "group_a_plusplus_latest_strategy_explain_snapshot",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "policy": "explain_snapshot_only_no_weight_change_no_orders",
        "status": status,
        "inputs": {
            "watchlist": {"path": _rel(watchlist_path), "mtime_utc": _mtime(watchlist_path)},
            "target_weights": {"path": _rel(target_weights_path), "mtime_utc": _mtime(target_weights_path)},
            "research_governance": {"path": _rel(research_governance_path), "mtime_utc": _mtime(research_governance_path)},
            "shadow_registry": {"path": _rel(shadow_registry_path), "mtime_utc": _mtime(shadow_registry_path)},
        },
        "strategy_identity": {
            "watchlist_name": watchlist.get("name"),
            "active_strategy_id": target_weights.get("active_strategy_id"),
            "candidate_status": target_weights.get("candidate_status"),
            "target_weight_status": target_weights.get("status"),
            "date_window": target_weights.get("date_window"),
            "row_count": target_weights.get("row_count"),
        },
        "asset_scope": {
            "watchlist_symbols": watchlist_symbols,
            "target_assets": target_assets,
            "missing_watchlist_assets_from_target_weights": missing_watchlist_assets,
        },
        "regime_summary": {
            "execution_regime_counts": target_weights.get("execution_regime_counts") or {},
            "regime_weight_map": regime_weight_map,
            "regime_weight_sums": regime_sums,
            "bad_regime_weight_sums": bad_regime_sums,
        },
        "governance_summary": {
            "target_weight_export_decision": target_decision,
            "research_governance_gate": research_status,
            "shadow_artifact_registry": {
                "status": shadow_registry.get("status"),
                "artifact_count": shadow_summary.get("artifact_count"),
                "live_mutation_true_count": shadow_summary.get("live_mutation_true_count"),
                "promotion_true_count": shadow_summary.get("promotion_true_count"),
            },
        },
        "decision": {
            "creates_orders": False,
            "changes_latest_strategy": False,
            "changes_golden1_0531": False,
            "changes_golden2_0830": False,
            "target_weight_change_allowed": False,
            "promotion_allowed": False,
        },
        "blocking_reasons": blockers,
        "warning_reasons": warnings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    identity = report["strategy_identity"]
    scope = report["asset_scope"]
    governance = report["governance_summary"]
    lines = [
        "# GroupA++ Latest Strategy Explain Snapshot",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- As of: `{report.get('as_of')}`",
        f"- Status: `{report['status']}`",
        f"- Policy: `{report['policy']}`",
        f"- Active strategy: `{identity.get('active_strategy_id')}`",
        f"- Candidate status: `{identity.get('candidate_status')}`",
        f"- Target-weight window: `{identity.get('date_window')}`",
        f"- Target-weight rows: `{identity.get('row_count')}`",
        "",
        "## Asset Scope",
        "",
        f"- Watchlist symbols: `{scope.get('watchlist_symbols')}`",
        f"- Target assets: `{scope.get('target_assets')}`",
        f"- Missing watchlist assets from target weights: `{scope.get('missing_watchlist_assets_from_target_weights')}`",
        "",
        "## Governance",
        "",
        f"- Research governance status: `{governance['research_governance_gate'].get('status')}`",
        f"- Research promotion allowed: `{governance['research_governance_gate'].get('promotion_allowed')}`",
        f"- Shadow registry artifacts: `{governance['shadow_artifact_registry'].get('artifact_count')}`",
        f"- Shadow registry live mutation true: `{governance['shadow_artifact_registry'].get('live_mutation_true_count')}`",
        "",
        "## Decision",
        "",
        "- Creates orders: `False`",
        "- Changes latest strategy: `False`",
        "- Changes golden1/golden2: `False`",
        "- Promotion allowed: `False`",
        "",
        "## Blockers",
        "",
    ]
    blockers = report.get("blocking_reasons") or []
    lines.extend([f"- `{item}`" for item in blockers] or ["- None"])
    lines.extend(["", "## Warnings", ""])
    warnings = report.get("warning_reasons") or []
    lines.extend([f"- `{item}`" for item in warnings] or ["- None"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST))
    parser.add_argument("--target-weights", default=str(DEFAULT_TARGET_WEIGHTS))
    parser.add_argument("--research-governance", default=str(DEFAULT_RESEARCH_GOVERNANCE))
    parser.add_argument("--shadow-registry", default=str(DEFAULT_SHADOW_REGISTRY))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    report = build_snapshot(
        watchlist_path=_resolve(args.watchlist),
        target_weights_path=_resolve(args.target_weights),
        research_governance_path=_resolve(args.research_governance),
        shadow_registry_path=_resolve(args.shadow_registry),
        as_of=args.as_of,
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md = _resolve(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()
