#!/usr/bin/env python3
"""Build a cross-market confirmation monitor for arXiv 2605.17307 and GroupA+.

The paper's cross-market lesson is imported as confirmation-only evidence.
This monitor consumes existing cross-market artifacts and emits a GOOD/WEAK/
FAILED state. It never allocates to foreign ETFs and never changes GroupA+
target weights.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.cross_market_graph_shadow import load_cross_market_graph_shadow  # noqa: E402
from scripts.evaluate.build_group_a_plus_2607_15195_cost_aware_target_holding_shadow import _load_json  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2605_17307_cross_market_confirmation_monitor.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/2605_17307_cross_market_confirmation_monitor/history"
DEFAULT_STRATEGY = PROJECT_ROOT / "report/group_a_plus/latest/strategy.json"
DEFAULT_TSI = PROJECT_ROOT / "report/group_a_plus/latest/tsi_stress_shadow.json"
DEFAULT_MINGLE = PROJECT_ROOT / "report/group_a_plus/latest/mingle_lite_readiness_review.json"
DEFAULT_CROSS_GRAPH = PROJECT_ROOT / "results/cross_market_directed_graph_shadow_latest.json"


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _days_stale(as_of: date, value: Any) -> int | None:
    parsed = _parse_date(value)
    if parsed is None:
        return None
    return max((as_of - parsed).days, 0)


def _active_strategy_id(path: Path) -> str | None:
    strategy = _load_json(path)
    active = strategy.get("active_strategy") if isinstance(strategy.get("active_strategy"), dict) else {}
    value = active.get("id")
    return str(value) if value else None


def _source_freshness(source_status: dict[str, Any], as_of: date, watched: tuple[str, ...]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    max_stale = 0
    missing: list[str] = []
    for ticker in watched:
        item = source_status.get(ticker) if isinstance(source_status.get(ticker), dict) else {}
        stale = _days_stale(as_of, item.get("latest_date"))
        if stale is None:
            missing.append(ticker)
        else:
            max_stale = max(max_stale, stale)
        rows[ticker] = {
            "status": item.get("status", "missing"),
            "latest_date": item.get("latest_date"),
            "days_stale": stale,
            "source_table": item.get("source_table"),
        }
    return {"watched_sources": rows, "max_days_stale": max_stale, "missing_sources": missing}


def _tsi_summary(tsi: dict[str, Any]) -> dict[str, Any]:
    latest = tsi.get("latest") if isinstance(tsi.get("latest"), dict) else {}
    return {
        "status": tsi.get("status", "missing"),
        "date": tsi.get("date") or tsi.get("requested_as_of"),
        "alarm_active": bool(tsi.get("alarm_active")),
        "tsi_percentile": latest.get("tsi_percentile"),
        "tsi_memory_percentile": latest.get("tsi_memory_percentile"),
        "observations": latest.get("observations"),
        "recommended_use": tsi.get("recommended_use"),
    }


def _mingle_summary(mingle: dict[str, Any], as_of: date) -> dict[str, Any]:
    dates = mingle.get("dates") if isinstance(mingle.get("dates"), dict) else {}
    decision = mingle.get("decision") if isinstance(mingle.get("decision"), dict) else {}
    target = mingle.get("target_diversification") if isinstance(mingle.get("target_diversification"), dict) else {}
    return {
        "status": "available" if mingle else "missing",
        "end": dates.get("end"),
        "days_stale": _days_stale(as_of, dates.get("end")),
        "target_weight_change_allowed": decision.get("target_weight_change_allowed"),
        "promotion_allowed": decision.get("promotion_allowed"),
        "weighted_graph_degree": target.get("weighted_graph_degree"),
        "peripheral_alignment": target.get("peripheral_alignment"),
    }


def _graph_summary(graph: dict[str, Any], as_of: date) -> dict[str, Any]:
    source = graph.get("source") if isinstance(graph.get("source"), dict) else {}
    metrics = graph.get("metrics") if isinstance(graph.get("metrics"), dict) else {}
    no_add_metrics = metrics.get("NO_ADD") if isinstance(metrics.get("NO_ADD"), dict) else {}
    reenter_metrics = metrics.get("REENTER") if isinstance(metrics.get("REENTER"), dict) else {}
    return {
        "status": graph.get("status"),
        "generated_at": graph.get("generated_at"),
        "source_end": source.get("end"),
        "source_days_stale": _days_stale(as_of, source.get("end")),
        "latest_shadow_action": graph.get("latest_shadow_action"),
        "no_add_active": bool(graph.get("no_add_active")),
        "latest_probabilities": graph.get("latest_probabilities"),
        "no_add_auc": no_add_metrics.get("auc"),
        "reenter_auc": reenter_metrics.get("auc"),
        "selected_features": graph.get("selected_features") or [],
        "allow_auto_weight_change": bool(graph.get("allow_auto_weight_change")),
    }


def _confirmation_state(*, tsi: dict[str, Any], mingle: dict[str, Any], graph: dict[str, Any], freshness: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if freshness["missing_sources"]:
        reasons.append("required_cross_market_sources_missing")
    if freshness["max_days_stale"] > 7:
        reasons.append("cross_market_source_data_stale")
    if tsi["alarm_active"] or (tsi.get("tsi_memory_percentile") is not None and float(tsi["tsi_memory_percentile"]) >= 0.90):
        reasons.append("cross_market_network_stress_high")
    if graph["no_add_active"]:
        reasons.append("cross_market_graph_no_add_active")
    if graph.get("source_days_stale") is None or graph.get("source_days_stale", 999) > 14:
        reasons.append("directed_graph_shadow_stale_for_daily_confirmation")
    if mingle.get("days_stale") is None or mingle.get("days_stale", 999) > 7:
        reasons.append("mingle_exposure_graph_stale")

    hard = {
        "required_cross_market_sources_missing",
        "cross_market_source_data_stale",
        "cross_market_network_stress_high",
        "cross_market_graph_no_add_active",
    }
    if any(reason in hard for reason in reasons):
        return "FAILED", reasons
    if reasons:
        return "WEAK", reasons
    return "GOOD", ["cross_market_confirmation_available_no_stress_alarm_no_no_add_alert"]


def build_monitor(
    *,
    strategy_path: Path = DEFAULT_STRATEGY,
    tsi_path: Path = DEFAULT_TSI,
    mingle_path: Path = DEFAULT_MINGLE,
    cross_graph_path: Path = DEFAULT_CROSS_GRAPH,
    as_of: str | None = None,
) -> dict[str, Any]:
    tsi_raw = _load_json(_resolve(tsi_path))
    as_of_date = _parse_date(as_of) or _parse_date(tsi_raw.get("date")) or date.today()
    mingle_raw = _load_json(_resolve(mingle_path))
    graph_raw = load_cross_market_graph_shadow(report_path=_resolve(cross_graph_path))
    watched = ("SOXX", "QQQ", "NVDA", "TSM", "^VIX", "TWD=X", "^TNX", "0050.TW", "00631L.TW", "2330.TW")
    freshness = _source_freshness(
        tsi_raw.get("source_status") if isinstance(tsi_raw.get("source_status"), dict) else {},
        as_of_date,
        watched,
    )
    tsi = _tsi_summary(tsi_raw)
    mingle = _mingle_summary(mingle_raw, as_of_date)
    graph = _graph_summary(graph_raw, as_of_date)
    state, reasons = _confirmation_state(tsi=tsi, mingle=mingle, graph=graph, freshness=freshness)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2605_17307_cross_market_confirmation_monitor",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of_date.isoformat(),
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2605.17307.pdf",
            "imported_concept": "cross_market_confirmation_monitor_only",
        },
        "latest_strategy": _active_strategy_id(_resolve(strategy_path)),
        "cross_market_confirmation": {
            "state": state,
            "reasons": reasons,
            "production_effect": "none",
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "foreign_etf_allocation_allowed": False,
        },
        "components": {
            "source_freshness": freshness,
            "tsi_stress_shadow": tsi,
            "mingle_lite_exposure_graph": mingle,
            "directed_graph_shadow": graph,
        },
        "decision": {
            "use_as_shadow_confirmation": True,
            "can_confirm_new_risk_adds": state == "GOOD",
            "blocks_live_trade": False,
            "train_sac_now": False,
            "target_weight_change_allowed": False,
            "replace_a2118": False,
            "summary": f"Cross-market confirmation state is {state}. This is confirmation-only and has no production trading effect.",
        },
    }


def write_monitor(report: dict[str, Any], output: Path = DEFAULT_OUTPUT, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    output.write_text(text + "\n", encoding="utf-8")
    stamp = str(report.get("as_of") or datetime.now().date()).replace("-", "")
    (history_dir / f"2605_17307_cross_market_confirmation_monitor_{stamp}.json").write_text(text + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", default=str(DEFAULT_STRATEGY))
    parser.add_argument("--tsi", default=str(DEFAULT_TSI))
    parser.add_argument("--mingle", default=str(DEFAULT_MINGLE))
    parser.add_argument("--cross-graph", default=str(DEFAULT_CROSS_GRAPH))
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_monitor(
        strategy_path=_resolve(args.strategy),
        tsi_path=_resolve(args.tsi),
        mingle_path=_resolve(args.mingle),
        cross_graph_path=_resolve(args.cross_graph),
        as_of=args.as_of,
    )
    write_monitor(report, _resolve(args.output), _resolve(args.history_dir))
    print(json.dumps(report["decision"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
