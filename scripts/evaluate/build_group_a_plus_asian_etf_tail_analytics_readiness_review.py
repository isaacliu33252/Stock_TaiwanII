#!/usr/bin/env python3
"""Build a research-only Asian ETF tail analytics readiness review.

Inspired by arXiv 2511.12476. This reviews whether GroupA+ can import the
paper's Asian ETF risk analytics, CVaR/STARR/Rachev/Hill tail diagnostics, and
optimization benchmark discipline. It never optimizes live weights.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_CVAR = PROJECT_ROOT / "report/group_a_plus/latest/cvar_tail_risk_diagnostic.json"
DEFAULT_MARKET_IMPACT = PROJECT_ROOT / "report/group_a_plus/latest/market_impact_readiness_review.json"
DEFAULT_REBALANCE = PROJECT_ROOT / "report/group_a_plus/latest/rebalance_review_20260720.json"
DEFAULT_LETF = PROJECT_ROOT / "report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/asian_etf_tail_analytics_readiness/history"

PAPER_ETFS = (
    "AAXJ",
    "ACWX",
    "AIA",
    "ASEA",
    "CHIQ",
    "DVYA",
    "DVYE",
    "EDIV",
    "EEM",
    "EEMA",
    "EEMS",
    "EIDO",
    "EPHE",
    "EWM",
    "EWT",
    "EWX",
    "EWY",
    "FM",
    "GMF",
    "GXC",
    "HAUZ",
    "HYEM",
    "INDA",
    "KBWB",
    "KWEB",
    "MCHI",
    "THD",
    "VNM",
    "VWO",
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _available_tickers(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    with duckdb.connect(str(db_path), read_only=True) as conn:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        tickers: set[str] = set()
        if "ohlcv" in tables:
            tickers.update(row[0] for row in conn.execute("SELECT DISTINCT ticker FROM ohlcv").fetchall())
        if "external_market_ohlcv" in tables:
            tickers.update(row[0] for row in conn.execute("SELECT DISTINCT ticker FROM external_market_ohlcv").fetchall())
        return tickers


def _paper_ticker_aliases(ticker: str) -> set[str]:
    return {ticker, f"{ticker}.US", f"{ticker} US Equity"}


def _paper_coverage(available: set[str]) -> dict[str, Any]:
    present: list[str] = []
    missing: list[str] = []
    for ticker in PAPER_ETFS:
        if _paper_ticker_aliases(ticker) & available:
            present.append(ticker)
        else:
            missing.append(ticker)
    return {
        "paper_etf_count": len(PAPER_ETFS),
        "available_paper_etf_count": len(present),
        "available_paper_etfs": present,
        "missing_paper_etfs": missing,
        "paper_universe_ready": len(present) >= 20,
    }


def _tail_reward_risk_monitor(
    *,
    golden1_rachev_95_95: float | None,
    l31_rachev_95_95: float | None,
) -> dict[str, Any]:
    if golden1_rachev_95_95 is None or l31_rachev_95_95 is None:
        return {
            "status": "missing",
            "tier": "unavailable",
            "golden1_rachev_95_95": golden1_rachev_95_95,
            "00631l_rachev_95_95": l31_rachev_95_95,
            "golden1_beats_00631l_by_rachev": None,
            "00631l_rachev_below_one": None,
            "interpretation": "Rachev comparison is unavailable because one or more required values are missing.",
        }

    golden1_beats_l31 = golden1_rachev_95_95 > l31_rachev_95_95
    l31_below_one = l31_rachev_95_95 < 1.0
    if golden1_beats_l31 and l31_below_one:
        tier = "defensive_preference"
        interpretation = (
            "Golden1 has stronger tail gain/loss balance than 00631L, while 00631L is below 1.0; "
            "keep the current defensive preference and do not add leveraged exposure automatically."
        )
    elif golden1_beats_l31:
        tier = "golden1_preferred"
        interpretation = (
            "Golden1 has stronger tail gain/loss balance than 00631L; use as research warning only."
        )
    elif l31_below_one:
        tier = "00631l_tail_reward_unfavorable"
        interpretation = "00631L Rachev is below 1.0; leveraged exposure remains research-only."
    else:
        tier = "watch"
        interpretation = "Rachev comparison is not defensive enough to change the existing policy gate."
    return {
        "status": "available",
        "tier": tier,
        "golden1_rachev_95_95": golden1_rachev_95_95,
        "00631l_rachev_95_95": l31_rachev_95_95,
        "golden1_beats_00631l_by_rachev": golden1_beats_l31,
        "00631l_rachev_below_one": l31_below_one,
        "interpretation": interpretation,
    }


def build_review(
    *,
    db_path: Path = DEFAULT_DB,
    cvar_path: Path = DEFAULT_CVAR,
    market_impact_path: Path = DEFAULT_MARKET_IMPACT,
    rebalance_path: Path = DEFAULT_REBALANCE,
    letf_path: Path = DEFAULT_LETF,
) -> dict[str, Any]:
    available = _available_tickers(db_path)
    coverage = _paper_coverage(available)
    cvar = _load(cvar_path)
    market_impact = _load(market_impact_path)
    rebalance = _load(rebalance_path)
    letf = _load(letf_path)
    market_decision = _decision(market_impact)
    rebalance_decision = _decision(rebalance)
    letf_decision = _decision(letf)

    blockers: list[str] = []
    warnings: list[str] = []
    missing_inputs = [
        name
        for name, payload in {
            "cvar_tail_risk_diagnostic": cvar,
            "market_impact_readiness_review": market_impact,
            "rebalance_review": rebalance,
            "letf_tracking_error_effective_fee_readiness_review": letf,
        }.items()
        if not payload
    ]
    if missing_inputs:
        blockers.append("missing_required_inputs:" + ",".join(sorted(missing_inputs)))
    if not coverage["paper_universe_ready"]:
        blockers.append("asian_29_etf_universe_not_available")
    if coverage["available_paper_etf_count"] == 0:
        blockers.append("no_paper_asian_etf_price_history_available")

    if cvar.get("promotion_decision") != "research_only":
        warnings.append("cvar_tail_risk_promotion_state_unexpected")
    else:
        blockers.append("cvar_tail_risk_diagnostic_research_only")

    if market_impact.get("status") == "blocked":
        blockers.append("market_impact_readiness_blocked")
    if market_decision.get("auto_rebalance_allowed") is not True:
        blockers.append("market_impact_disallows_auto_rebalance")
    if rebalance_decision.get("auto_rebalance_allowed") is not True:
        blockers.append("rebalance_review_disallows_auto_rebalance")
    if rebalance_decision.get("target_weight_change_allowed") is not True:
        blockers.append("rebalance_review_disallows_target_weight_change")
    if letf_decision.get("allow_00631l_add") is not True:
        blockers.append("letf_tracking_error_review_disallows_00631l_add")

    golden1_starr_95 = next(
        (
            row.get("starr_95")
            for row in cvar.get("ranking_by_starr95", [])
            if isinstance(row, dict) and row.get("strategy") == "golden1_frozen_proxy_50_20_30"
        ),
        None,
    )
    golden1_rachev_95_95 = next(
        (
            row.get("rachev_95_95")
            for row in cvar.get("ranking_by_starr95", [])
            if isinstance(row, dict) and row.get("strategy") == "golden1_frozen_proxy_50_20_30"
        ),
        None,
    )
    l31_rachev_95_95 = _nested(cvar, "00631l_only_tail_diagnostics", "rachev_95_95")
    tail_reward_risk_monitor = _tail_reward_risk_monitor(
        golden1_rachev_95_95=golden1_rachev_95_95,
        l31_rachev_95_95=l31_rachev_95_95,
    )
    if tail_reward_risk_monitor["golden1_beats_00631l_by_rachev"] is True:
        warnings.append("rachev_prefers_golden1_over_00631l")
    if tail_reward_risk_monitor["00631l_rachev_below_one"] is True:
        warnings.append("00631l_rachev_below_one_tail_reward_unfavorable")

    blockers.extend(
        [
            "long_short_etf_strategy_not_allowed",
            "leverage_10_20_30_percent_not_portable_to_group_a_plus",
            "transaction_borrow_financing_costs_missing",
            "rachev_starr_hill_optimizer_not_implemented",
            "asian_etf_walkforward_validation_missing",
        ]
    )

    as_of = _nested(rebalance, "dates", "requested_as_of_date") or "2026-07-20"
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_asian_etf_tail_analytics_readiness_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "status": "blocked" if blockers else "research_ready",
        "policy": "research_only_asian_etf_tail_analytics_no_optimizer_no_weight_change",
        "source_paper": {
            "file": "C:/Users/isaac/Downloads/2511.12476.pdf",
            "title": "Performance and Risk Analytics of Asian Exchange-Traded Funds",
            "arxiv": "2511.12476v1",
            "imported_concepts": [
                "equal_weight_etf_benchmark",
                "markowitz_and_cvar_frontier_as_research_benchmark",
                "sharpe_rachev_starr_reward_risk_ratios",
                "hill_tail_index_as_extreme_loss_diagnostic",
                "friction_cost_caution_for_long_short_leverage",
            ],
            "not_imported": [
                "29_us_listed_asian_etf_allocation",
                "long_short_10_20_30_percent_leverage",
                "markowitz_or_cvar_live_optimizer",
                "automatic_rebalance",
            ],
        },
        "data_readiness": {
            "available_ticker_count": len(available),
            "paper_etf_coverage": coverage,
        },
        "component_readiness": {
            "cvar_tail_risk": {
                "status": cvar.get("status"),
                "promotion_decision": cvar.get("promotion_decision"),
                "golden1_starr_95": golden1_starr_95,
                "golden1_rachev_95_95": golden1_rachev_95_95,
                "00631l_expected_shortfall_loss_95": _nested(
                    cvar,
                    "00631l_only_tail_diagnostics",
                    "expected_shortfall_loss_95",
                ),
                "00631l_rachev_95_95": l31_rachev_95_95,
                "00631l_hill_xi_95": _nested(cvar, "00631l_only_tail_diagnostics", "hill_95", "hill_xi"),
            },
            "market_impact": {
                "status": market_impact.get("status"),
                "auto_rebalance_allowed": market_decision.get("auto_rebalance_allowed"),
            },
            "rebalance": {
                "status": rebalance.get("status"),
                "auto_rebalance_allowed": rebalance_decision.get("auto_rebalance_allowed"),
                "target_weight_change_allowed": rebalance_decision.get("target_weight_change_allowed"),
                "allow_00631l_add": rebalance_decision.get("allow_00631l_add"),
            },
            "letf_tracking_error": {
                "status": letf.get("status"),
                "allow_00631l_add": letf_decision.get("allow_00631l_add"),
                "allow_00632r_open": letf_decision.get("allow_00632r_open"),
            },
        },
        "tail_reward_risk_monitor": tail_reward_risk_monitor,
        "validation_readiness": {
            "markowitz_frontier_implemented": False,
            "cvar_frontier_implemented": False,
            "starr_rachev_ratio_monitor_implemented": bool(
                any(isinstance(row, dict) and row.get("rachev_95_95") is not None for row in cvar.get("ranking_by_starr95", []))
            ),
            "hill_tail_index_monitor_implemented": False,
            "long_short_cost_model_implemented": False,
            "taiwan_group_a_plus_walkforward_validated": False,
        },
        "blocking_reasons": sorted(set(blockers)),
        "warning_reasons": sorted(set(warnings)),
        "decision": {
            "summary": (
                "Use 2511.12476 as ETF tail-risk analytics governance only. Current GroupA+ lacks the "
                "paper's 29-ETF Asian universe, long-short cost model, and optimizer validation; live "
                "weights remain unchanged."
            ),
            "tail_analytics_ready": False,
            "optimizer_ready": False,
            "promote_to_live": False,
            "target_weight_change_allowed": False,
            "auto_rebalance_allowed": False,
            "allow_00631l_add": False,
            "allow_00632r_open": False,
            "keep_golden1_0531_unchanged": True,
        },
        "inputs": {
            "db_path": str(db_path),
            "cvar_tail_risk": str(cvar_path),
            "market_impact": str(market_impact_path),
            "rebalance": str(rebalance_path),
            "letf_tracking_error": str(letf_path),
        },
    }


def _history_path(history_dir: Path, as_of: str | None) -> Path:
    stamp = str(as_of or datetime.now().strftime("%Y%m%d")).replace("-", "")
    return history_dir / f"asian_etf_tail_analytics_readiness_{stamp}.json"


def write_review(review: dict[str, Any], output_path: Path, history_dir: Path | None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, review.get("as_of")).write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--cvar", default=str(DEFAULT_CVAR))
    parser.add_argument("--market-impact", default=str(DEFAULT_MARKET_IMPACT))
    parser.add_argument("--rebalance", default=str(DEFAULT_REBALANCE))
    parser.add_argument("--letf", default=str(DEFAULT_LETF))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    review = build_review(
        db_path=_resolve(args.db),
        cvar_path=_resolve(args.cvar),
        market_impact_path=_resolve(args.market_impact),
        rebalance_path=_resolve(args.rebalance),
        letf_path=_resolve(args.letf),
    )
    output = _resolve(args.output)
    history_dir = None if args.no_history else _resolve(args.history_dir)
    write_review(review, output, history_dir)
    print(f"Asian ETF tail analytics readiness review: {output}")
    if history_dir is not None:
        print(f"History snapshot: {_history_path(history_dir, review.get('as_of'))}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "available_paper_etfs": review["data_readiness"]["paper_etf_coverage"][
                    "available_paper_etf_count"
                ],
                "tail_analytics_ready": review["decision"]["tail_analytics_ready"],
                "auto_rebalance_allowed": review["decision"]["auto_rebalance_allowed"],
                "allow_00631l_add": review["decision"]["allow_00631l_add"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
