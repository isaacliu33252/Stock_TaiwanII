#!/usr/bin/env python3
"""Convert GroupA+ review votes into an executable decision and adjusted signal."""

from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

_SCRIPT_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPT_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_PROJECT_ROOT))

from group_a_plus_review_tools import PROJECT_ROOT, load_json, resolve_path
from group_a_plus.integrations.ncf import (
    load_ncf_signal,
    ncf_cross_ticker_consistency,
    ncf_dynamic_horizon_signal,
)


DEFAULT_BASELINE = PROJECT_ROOT / "GROUP_A_PLUS_CURRENT_BASELINE.json"
DEFAULT_REVIEW_POINTER = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "review.json"
DEFAULT_COMPARE_POINTER = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "strategy_compare.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "decision"
DEFAULT_LATEST = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "decision.json"
DEFAULT_NCF_ADVISORY_GLOB = PROJECT_ROOT / "results" / "ncf_advisory_panel_latest_*.csv"
DEFAULT_NCF_00631L_GLOB = PROJECT_ROOT / "results" / "ncf_00631l_latest_*.json"
DEFAULT_NCF_00632R_GLOB = PROJECT_ROOT / "results" / "ncf_00632r_latest_*.json"
TICKERS = ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO")
DEFAULT_TARGET_TOTAL_ASSETS = 1_000_000.0


def _load_latest(pointer_path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    pointer = load_json(pointer_path)
    return pointer, load_json(pointer["json"])


def _signal_weights(signal: dict[str, Any]) -> dict[str, float]:
    total_assets = float(signal.get("total_assets") or signal.get("current_total_portfolio_value") or 0.0)
    prices = dict(signal.get("latest_prices") or {})
    shares = dict(signal.get("target_shares") or {})
    weights = {
        ticker: float(shares.get(ticker, 0) or 0) * float(prices.get(ticker, 0.0) or 0.0) / max(total_assets, 1.0)
        for ticker in TICKERS
    }
    cash_after_cost = float((signal.get("execution_summary") or {}).get("cash_after_cost", 0.0) or 0.0)
    weights["cash"] = cash_after_cost / max(total_assets, 1.0)
    return weights


def _trade_summary(signal: dict[str, Any], target_shares: dict[str, int]) -> dict[str, float]:
    prices = dict(signal.get("latest_prices") or {})
    current_shares = dict(signal.get("current_shares") or {})
    total_assets = float(signal.get("total_assets") or signal.get("current_total_portfolio_value") or 0.0)
    commission_rate = float(signal.get("commission_rate", 0.001425) or 0.0)
    sell_tax_rate = float(signal.get("etf_sell_tax_rate", 0.001) or 0.0)
    slippage_rate = float(signal.get("slippage_rate", 0.0005) or 0.0)

    buy_notional = 0.0
    sell_notional = 0.0
    target_invested = 0.0
    for ticker in TICKERS:
        price = float(prices.get(ticker, 0.0) or 0.0)
        current = int(current_shares.get(ticker, 0) or 0)
        target = int(target_shares.get(ticker, 0) or 0)
        delta = target - current
        target_invested += target * price
        if delta > 0:
            buy_notional += delta * price
        elif delta < 0:
            sell_notional += abs(delta) * price

    commission = (buy_notional + sell_notional) * commission_rate
    sell_tax = sell_notional * sell_tax_rate
    slippage = (buy_notional + sell_notional) * slippage_rate
    total_execution_cost = commission + sell_tax + slippage
    cash_before_cost = total_assets - target_invested
    cash_after_cost = cash_before_cost - total_execution_cost
    turnover_notional = buy_notional + sell_notional
    return {
        "buy_notional": buy_notional,
        "sell_notional": sell_notional,
        "commission": commission,
        "sell_tax": sell_tax,
        "slippage": slippage,
        "total_execution_cost": total_execution_cost,
        "target_invested": target_invested,
        "cash_before_cost": cash_before_cost,
        "cash_after_cost": cash_after_cost,
        "turnover_notional": turnover_notional,
        "turnover_ratio": turnover_notional / max(total_assets, 1.0),
    }


def _shares_from_weights(signal: dict[str, Any], weights: dict[str, float]) -> dict[str, int]:
    total_assets = float(signal.get("total_assets") or signal.get("current_total_portfolio_value") or 0.0)
    prices = dict(signal.get("latest_prices") or {})
    return {
        ticker: int((total_assets * max(float(weights.get(ticker, 0.0) or 0.0), 0.0)) // max(float(prices.get(ticker, 0.0) or 0.0), 1e-12))
        for ticker in TICKERS
    }


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _resolve_latest_ncf_advisory_panel(explicit: str | Path | None = None) -> Path | None:
    if explicit:
        path = resolve_path(explicit)
        return path if path.exists() else None
    matches = sorted(glob.glob(str(DEFAULT_NCF_ADVISORY_GLOB)), key=lambda item: Path(item).stat().st_mtime)
    return Path(matches[-1]) if matches else None


def _resolve_latest_file(pattern: Path) -> Path | None:
    matches = sorted(glob.glob(str(pattern)), key=lambda item: Path(item).stat().st_mtime)
    return Path(matches[-1]) if matches else None


def _ncf_shadow_policy(row: dict[str, Any]) -> dict[str, Any]:
    market_direction = str(row.get("market_direction") or "").upper()
    agreement_score = float(row.get("agreement_score") or 0.0)
    conflict_flag = _parse_bool(row.get("conflict_flag"))
    if conflict_flag:
        policy = "conflict_reduce_20"
        risk_reduction = 0.20
        reason = "NCF 00631L/00632R conflict flag is active"
    elif market_direction == "DOWN":
        policy = "bearish_reduce_40"
        risk_reduction = 0.40
        reason = "NCF cross-ticker advisory market_direction is DOWN"
    else:
        policy = "baseline"
        risk_reduction = 0.0
        reason = "NCF cross-ticker advisory is not bearish"
    return {
        "policy": policy,
        "risk_reduction": risk_reduction,
        "defensive_destination": "00679B.TWO",
        "reason": reason,
        "promotion_status": "shadow_only",
        "implementation_status": "not_applied_to_live_weights",
        "agreement_score": agreement_score,
        "conflict_flag": conflict_flag,
        "market_direction": market_direction,
    }


def _load_ncf_advisory_context(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        live_context = _load_ncf_live_advisory_context()
        if live_context.get("status") == "available":
            return live_context
    panel_path = _resolve_latest_ncf_advisory_panel(path)
    if panel_path is None:
        return {"status": "unavailable", "reason": "ncf_advisory_panel_not_found"}
    with panel_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("date")]
    if not rows:
        return {"status": "unavailable", "file": str(panel_path), "reason": "ncf_advisory_panel_empty"}
    latest = sorted(rows, key=lambda row: row["date"])[-1]
    shadow = _ncf_shadow_policy(latest)
    return {
        "status": "available",
        "file": str(panel_path.relative_to(PROJECT_ROOT)) if panel_path.is_relative_to(PROJECT_ROOT) else str(panel_path),
        "date": latest.get("date"),
        "market_direction": latest.get("market_direction"),
        "market_probability_up": float(latest.get("market_probability_up") or 0.0),
        "agreement_score": float(latest.get("agreement_score") or 0.0),
        "conflict_flag": _parse_bool(latest.get("conflict_flag")),
        "cross_ticker_confidence": float(latest.get("cross_ticker_confidence") or 0.0),
        "dynamic_00631l_direction": latest.get("dynamic_00631l_direction"),
        "dynamic_00631l_prob_up": float(latest.get("dynamic_00631l_prob_up") or 0.0),
        "dynamic_00632r_direction": latest.get("dynamic_00632r_direction"),
        "dynamic_00632r_prob_up": float(latest.get("dynamic_00632r_prob_up") or 0.0),
        "shadow_recommendation": shadow,
        "decision_policy_effect": "report_only_no_weight_change",
    }


def _load_ncf_live_advisory_context(
    path_00631l: str | Path | None = None,
    path_00632r: str | Path | None = None,
) -> dict[str, Any]:
    p631 = resolve_path(path_00631l) if path_00631l else _resolve_latest_file(DEFAULT_NCF_00631L_GLOB)
    p632 = resolve_path(path_00632r) if path_00632r else _resolve_latest_file(DEFAULT_NCF_00632R_GLOB)
    missing = []
    if p631 is None or not p631.exists():
        missing.append("ncf_00631l")
    if p632 is None or not p632.exists():
        missing.append("ncf_00632r")
    if missing:
        return {"status": "unavailable", "reason": "ncf_live_json_missing", "missing": missing}

    sig631 = load_ncf_signal(p631)
    sig632 = load_ncf_signal(p632)
    dyn631 = ncf_dynamic_horizon_signal(sig631)
    dyn632 = ncf_dynamic_horizon_signal(sig632)
    cross = ncf_cross_ticker_consistency(sig631, sig632, use_dynamic_horizon=True)
    row = {
        "market_direction": cross["market_direction"],
        "agreement_score": cross["agreement_score"],
        "conflict_flag": cross["conflict_flag"],
    }
    shadow = _ncf_shadow_policy(row)
    date631 = sig631.get("date")
    date632 = sig632.get("date")
    return {
        "status": "available",
        "source": "live_ncf_json",
        "ncf_00631l_file": str(p631.relative_to(PROJECT_ROOT)) if p631.is_relative_to(PROJECT_ROOT) else str(p631),
        "ncf_00632r_file": str(p632.relative_to(PROJECT_ROOT)) if p632.is_relative_to(PROJECT_ROOT) else str(p632),
        "date": date631 if date631 == date632 else {"00631L": date631, "00632R": date632},
        "date_00631l": date631,
        "date_00632r": date632,
        "market_direction": cross["market_direction"],
        "market_probability_up": cross["market_probability_up"],
        "agreement_score": cross["agreement_score"],
        "conflict_flag": cross["conflict_flag"],
        "cross_ticker_confidence": cross["confidence"],
        "dynamic_00631l_direction": dyn631["direction"],
        "dynamic_00631l_prob_up": dyn631["probability_up"],
        "dynamic_00631l_confidence": dyn631["confidence"],
        "dynamic_00632r_direction": dyn632["direction"],
        "dynamic_00632r_prob_up": dyn632["probability_up"],
        "dynamic_00632r_confidence": dyn632["confidence"],
        "raw_00631l_ensemble_prob_up": sig631["calibrated_prob_up"],
        "raw_00632r_ensemble_prob_up": sig632["calibrated_prob_up"],
        "shadow_recommendation": shadow,
        "decision_policy_effect": "report_only_no_weight_change",
    }


def _scaled_signal(signal: dict[str, Any], target_total_assets: float | None) -> dict[str, Any]:
    if target_total_assets is None:
        return json.loads(json.dumps(signal, ensure_ascii=False))
    target_weights = _signal_weights(signal)
    scaled = json.loads(json.dumps(signal, ensure_ascii=False))
    prices = dict(scaled.get("latest_prices") or {})
    current_weights = dict(scaled.get("current_weights") or {})
    scaled["source_total_assets_before_policy_scale"] = float(
        signal.get("total_assets") or signal.get("current_total_portfolio_value") or 0.0
    )
    scaled["total_assets"] = float(target_total_assets)
    if "current_total_portfolio_value" in scaled:
        scaled["current_total_portfolio_value"] = float(target_total_assets)
    scaled["current_shares"] = {
        ticker: int((target_total_assets * max(float(current_weights.get(ticker, 0.0) or 0.0), 0.0)) // max(float(prices.get(ticker, 0.0) or 0.0), 1e-12))
        for ticker in TICKERS
    }
    scaled["target_shares"] = {
        ticker: int((target_total_assets * max(float(target_weights.get(ticker, 0.0) or 0.0), 0.0)) // max(float(prices.get(ticker, 0.0) or 0.0), 1e-12))
        for ticker in TICKERS
    }
    scaled["execution_summary"] = _trade_summary(scaled, scaled["target_shares"])
    scaled["policy_source_weights_before_capital_scale"] = target_weights
    scaled["policy_capital_scale"] = {
        "applied": True,
        "target_total_assets": float(target_total_assets),
        "method": "target and current shares re-estimated from source weights and latest prices",
    }
    return scaled


def _enforce_cash_after_cost(
    signal: dict[str, Any],
    base_weights: dict[str, float],
    min_cash_after_cost_weight: float,
) -> tuple[dict[str, int], dict[str, float], list[dict[str, Any]]]:
    total_assets = float(signal.get("total_assets") or signal.get("current_total_portfolio_value") or 0.0)
    required_cash = total_assets * min_cash_after_cost_weight
    original_shares = {ticker: int((signal.get("target_shares") or {}).get(ticker, 0) or 0) for ticker in TICKERS}
    original_summary = _trade_summary(signal, original_shares)
    if original_summary["cash_after_cost"] >= required_cash:
        return original_shares, dict(base_weights), []

    investable = max(1.0 - min_cash_after_cost_weight, 0.0)
    risky_sum = sum(max(float(base_weights.get(ticker, 0.0) or 0.0), 0.0) for ticker in TICKERS)
    scaled_weights = {
        ticker: (max(float(base_weights.get(ticker, 0.0) or 0.0), 0.0) / risky_sum * investable if risky_sum else 0.0)
        for ticker in TICKERS
    }
    shares = _shares_from_weights(signal, scaled_weights)
    adjustments = [
        {
            "type": "cash_after_cost_buffer",
            "from_weight": float(base_weights.get("cash", 0.0) or 0.0),
            "to_min_weight": min_cash_after_cost_weight,
            "reason": "review caution: cash_after_cost too thin",
        }
    ]

    prices = dict(signal.get("latest_prices") or {})
    summary = _trade_summary(signal, shares)
    while summary["cash_after_cost"] < required_cash:
        invested = {
            ticker: int(shares.get(ticker, 0) or 0) * float(prices.get(ticker, 0.0) or 0.0)
            for ticker in TICKERS
        }
        ticker = max(invested, key=invested.get)
        if invested[ticker] <= 0 or shares[ticker] <= 0:
            break
        shares[ticker] -= 1
        summary = _trade_summary(signal, shares)

    adjusted_weights = {
        ticker: int(shares.get(ticker, 0) or 0) * float(prices.get(ticker, 0.0) or 0.0) / max(total_assets, 1.0)
        for ticker in TICKERS
    }
    adjusted_weights["cash"] = summary["cash_after_cost"] / max(total_assets, 1.0)
    return shares, adjusted_weights, adjustments


def _apply_policy(
    baseline: dict[str, Any],
    review: dict[str, Any],
    compare: dict[str, Any],
    source_signal: dict[str, Any],
    *,
    min_cash_after_cost_weight: float,
    target_total_assets: float | None,
    ncf_advisory_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    vote = dict(review.get("vote") or {})
    decision = str(vote.get("decision", "block"))
    reason_codes: list[str] = []
    for item in review.get("research_reviews", []):
        agent = item.get("agent")
        if item.get("vote") in {"caution", "block", "shadow_only"}:
            reason_codes.append(str(agent))

    source_signal = _scaled_signal(source_signal, target_total_assets)
    source_weights = _signal_weights(source_signal)
    signal = json.loads(json.dumps(source_signal, ensure_ascii=False))
    signal["source_signal_json"] = str(resolve_path(baseline["latest_group_a_plus_final_signal"]))
    signal["policy_source_review"] = review.get("generated_at")
    signal["policy_source_strategy_compare"] = compare.get("generated_at")
    generated_at = datetime.now().isoformat(timespec="seconds")

    if decision == "block":
        policy_decision = "blocked"
        allowed_for_execution = False
        adjusted_shares = dict(source_signal.get("current_shares") or {})
        adjusted_weights = _signal_weights(source_signal)
        auto_adjustments = [{"type": "execution_block", "reason": "one or more review agents voted block"}]
    elif decision == "shadow_only":
        policy_decision = "shadow_only"
        allowed_for_execution = False
        adjusted_shares = dict(source_signal.get("target_shares") or {})
        adjusted_weights = source_weights
        auto_adjustments = [{"type": "shadow_only", "reason": "review result is research-only"}]
    elif decision == "caution":
        policy_decision = "caution_auto_adjusted"
        allowed_for_execution = True
        adjusted_shares, adjusted_weights, auto_adjustments = _enforce_cash_after_cost(
            source_signal,
            source_weights,
            min_cash_after_cost_weight,
        )
    else:
        policy_decision = "approved"
        allowed_for_execution = True
        adjusted_shares = dict(source_signal.get("target_shares") or {})
        adjusted_weights = source_weights
        auto_adjustments = []

    execution_summary = _trade_summary(source_signal, {ticker: int(adjusted_shares.get(ticker, 0) or 0) for ticker in TICKERS})
    signal.update(
        {
            "status": "policy_adjusted_signal",
            "policy_decision": policy_decision,
            "allowed_for_execution": allowed_for_execution,
            "policy_generated_at": generated_at,
            "policy_profile": baseline.get("profile"),
            "policy_reason_codes": reason_codes,
            "policy_auto_adjustments": auto_adjustments,
            "policy_source_weights": source_weights,
            "policy_adjusted_weights": adjusted_weights,
            "target_shares_before_policy": dict(source_signal.get("target_shares") or {}),
            "target_shares": {ticker: int(adjusted_shares.get(ticker, 0) or 0) for ticker in TICKERS},
            "execution_summary_before_policy": dict(source_signal.get("execution_summary") or {}),
            "execution_summary": execution_summary,
            "ncf_advisory_context": ncf_advisory_context or {"status": "not_loaded"},
        }
    )

    decision_report = {
        "generated_at": generated_at,
        "profile": baseline.get("profile"),
        "source_review_decision": decision,
        "decision": policy_decision,
        "allowed_for_execution": allowed_for_execution,
        "source_signal": baseline.get("latest_group_a_plus_final_signal"),
        "source_weights": source_weights,
        "target_total_assets": float(target_total_assets or source_signal.get("total_assets") or 0.0),
        "adjusted_weights": adjusted_weights,
        "target_shares_before_policy": dict(source_signal.get("target_shares") or {}),
        "target_shares_after_policy": signal["target_shares"],
        "execution_summary_before_policy": dict(source_signal.get("execution_summary") or {}),
        "execution_summary_after_policy": execution_summary,
        "ncf_advisory_context": ncf_advisory_context or {"status": "not_loaded"},
        "auto_adjustments": auto_adjustments,
        "reason_codes": reason_codes,
        "review_vote_counts": vote.get("vote_counts", {}),
        "inputs": {
            "baseline": "GROUP_A_PLUS_CURRENT_BASELINE.json",
            "review_generated_at": review.get("generated_at"),
            "strategy_compare_generated_at": compare.get("generated_at"),
        },
    }
    return decision_report, signal


def _fmt_pct(value: Any) -> str:
    return f"{float(value or 0.0):.2%}"


def _fmt_num(value: Any) -> str:
    return f"{float(value or 0.0):,.0f}"


def _render_html(report: dict[str, Any]) -> str:
    rows = []
    before = dict(report.get("source_weights") or {})
    after = dict(report.get("adjusted_weights") or {})
    before_shares = dict(report.get("target_shares_before_policy") or {})
    after_shares = dict(report.get("target_shares_after_policy") or {})
    for ticker in (*TICKERS, "cash"):
        rows.append(
            "<tr>"
            f"<td>{escape(ticker)}</td>"
            f"<td class=\"num\">{_fmt_pct(before.get(ticker, 0.0))}</td>"
            f"<td class=\"num\">{escape(str(before_shares.get(ticker, '-')))}</td>"
            f"<td class=\"num\">{_fmt_pct(after.get(ticker, 0.0))}</td>"
            f"<td class=\"num\">{escape(str(after_shares.get(ticker, '-')))}</td>"
            f"<td class=\"num\">{_fmt_pct(float(after.get(ticker, 0.0) or 0.0) - float(before.get(ticker, 0.0) or 0.0))}</td>"
            "</tr>"
        )
    before_exec = dict(report.get("execution_summary_before_policy") or {})
    after_exec = dict(report.get("execution_summary_after_policy") or {})
    ncf = dict(report.get("ncf_advisory_context") or {})
    ncf_shadow = dict(ncf.get("shadow_recommendation") or {})
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GroupA+ Decision Policy</title>
  <style>
    :root {{ --bg:#f6f7f9; --panel:#fff; --text:#20242a; --muted:#68717e; --line:#d9dee7; --accent:#2457a6; --warn:#9a5b00; --ok:#177245; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,"Noto Sans TC",sans-serif; line-height:1.45; }}
    main {{ width:min(1180px, calc(100% - 32px)); margin:24px auto 42px; }}
    header {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; padding:20px 0 18px; border-bottom:1px solid var(--line); }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    h2 {{ margin:0 0 14px; font-size:19px; letter-spacing:0; }}
    section,.decision {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:18px; }}
    section {{ margin-top:18px; }}
    .decision {{ min-width:250px; text-align:right; }}
    .decision .label,.subtle {{ color:var(--muted); font-size:14px; }}
    .decision .value {{ margin-top:4px; font-size:26px; font-weight:750; color:var(--warn); }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
    table {{ width:100%; border-collapse:collapse; font-size:14px; }}
    th,td {{ padding:10px 8px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-weight:650; }}
    .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
    code {{ font-family:"SFMono-Regular",Consolas,monospace; font-size:12px; overflow-wrap:anywhere; }}
    @media (max-width: 820px) {{ header,.grid {{ display:block; }} .decision {{ margin-top:14px; text-align:left; }} main {{ width:calc(100% - 20px); }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>GroupA+ Decision Policy</h1>
        <div class="subtle">Profile: <code>{escape(str(report.get("profile", "")))}</code></div>
        <div class="subtle">Generated: {escape(str(report.get("generated_at", "")))}</div>
      </div>
      <div class="decision">
        <div class="label">Decision</div>
        <div class="value">{escape(str(report.get("decision", "")))}</div>
        <div class="subtle">allowed_for_execution={escape(str(report.get("allowed_for_execution", False)).lower())}</div>
      </div>
    </header>
    <section class="grid">
      <div>
        <h2>Before Policy</h2>
        <p>Cash after cost: <strong>{_fmt_num(before_exec.get("cash_after_cost", 0.0))}</strong></p>
        <p>Turnover ratio: <strong>{_fmt_pct(before_exec.get("turnover_ratio", 0.0))}</strong></p>
      </div>
      <div>
        <h2>After Policy</h2>
        <p>Cash after cost: <strong>{_fmt_num(after_exec.get("cash_after_cost", 0.0))}</strong></p>
        <p>Turnover ratio: <strong>{_fmt_pct(after_exec.get("turnover_ratio", 0.0))}</strong></p>
      </div>
    </section>
    <section>
      <h2>Target Changes</h2>
      <table>
        <thead><tr><th>Ticker</th><th class="num">Before Weight</th><th class="num">Before Shares</th><th class="num">After Weight</th><th class="num">After Shares</th><th class="num">Delta</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    <section>
      <h2>NCF Advisory Shadow</h2>
      <p>Status: <strong>{escape(str(ncf.get("status", "not_loaded")))}</strong></p>
      <p>Date: <strong>{escape(str(ncf.get("date", "-")))}</strong> | Market: <strong>{escape(str(ncf.get("market_direction", "-")))}</strong> | Agreement: <strong>{_fmt_pct(ncf.get("agreement_score", 0.0))}</strong> | Conflict: <strong>{escape(str(ncf.get("conflict_flag", "-")).lower())}</strong></p>
      <p>Shadow policy: <strong>{escape(str(ncf_shadow.get("policy", "-")))}</strong> | Risk reduction: <strong>{_fmt_pct(ncf_shadow.get("risk_reduction", 0.0))}</strong> | Destination: <strong>{escape(str(ncf_shadow.get("defensive_destination", "-")))}</strong></p>
      <p class="subtle">Effect: {escape(str(ncf.get("decision_policy_effect", "report_only_no_weight_change")))}</p>
    </section>
    <section>
      <h2>Reason Codes</h2>
      <p><code>{escape(", ".join(report.get("reason_codes", [])))}</code></p>
    </section>
  </main>
</body>
</html>
"""


def _write_csv(path: Path, signal: dict[str, Any]) -> None:
    weights = dict(signal.get("policy_adjusted_weights") or {})
    shares = dict(signal.get("target_shares") or {})
    prices = dict(signal.get("latest_prices") or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ticker", "target_weight", "target_shares", "latest_price"])
        writer.writeheader()
        for ticker in (*TICKERS, "cash"):
            writer.writerow(
                {
                    "ticker": ticker,
                    "target_weight": weights.get(ticker, 0.0),
                    "target_shares": shares.get(ticker, ""),
                    "latest_price": prices.get(ticker, ""),
                }
            )


def _write_outputs(report: dict[str, Any], signal: dict[str, Any], output_dir: Path, latest_pointer: Path) -> dict[str, str]:
    stamp = str(report["generated_at"]).replace("-", "").replace(":", "").replace("T", "_")
    profile = str(report.get("profile") or "group_a_plus").replace("/", "_")
    json_dir = output_dir / "json"
    html_dir = output_dir / "html"
    signal_dir = PROJECT_ROOT / "results"
    json_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)
    decision_json = json_dir / f"decision_{profile}_{stamp}.json"
    decision_html = html_dir / f"decision_{profile}_{stamp}.html"
    signal_json = signal_dir / f"group_a_plus_policy_signal_{stamp}.json"
    signal_csv = signal_dir / f"group_a_plus_policy_signal_{stamp}.csv"
    decision_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    decision_html.write_text(_render_html(report), encoding="utf-8")
    signal_json.write_text(json.dumps(signal, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(signal_csv, signal)
    latest = {
        "report_type": "decision_policy",
        "generated_at": report["generated_at"],
        "profile": report.get("profile"),
        "decision": report["decision"],
        "allowed_for_execution": report["allowed_for_execution"],
        "html": str(decision_html.relative_to(PROJECT_ROOT)),
        "json": str(decision_json.relative_to(PROJECT_ROOT)),
        "signal_json": str(signal_json.relative_to(PROJECT_ROOT)),
        "signal_csv": str(signal_csv.relative_to(PROJECT_ROOT)),
    }
    latest_pointer.parent.mkdir(parents=True, exist_ok=True)
    latest_pointer.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "html": str(decision_html),
        "json": str(decision_json),
        "signal_json": str(signal_json),
        "signal_csv": str(signal_csv),
        "latest": str(latest_pointer),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    parser.add_argument("--review-pointer", default=str(DEFAULT_REVIEW_POINTER))
    parser.add_argument("--compare-pointer", default=str(DEFAULT_COMPARE_POINTER))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--latest-pointer", default=str(DEFAULT_LATEST))
    parser.add_argument("--min-cash-after-cost-weight", type=float, default=0.01)
    parser.add_argument("--target-total-assets", type=float, default=DEFAULT_TARGET_TOTAL_ASSETS)
    parser.add_argument(
        "--ncf-advisory-panel",
        default=None,
        help="Optional NCF advisory panel CSV. Default: latest results/ncf_advisory_panel_latest_*.csv.",
    )
    parser.add_argument("--disable-ncf-advisory-context", action="store_true")
    args = parser.parse_args()

    baseline = load_json(args.baseline)
    _review_pointer, review = _load_latest(args.review_pointer)
    _compare_pointer, compare = _load_latest(args.compare_pointer)
    source_signal = load_json(baseline["latest_group_a_plus_final_signal"])
    ncf_advisory_context = (
        {"status": "disabled"}
        if args.disable_ncf_advisory_context
        else _load_ncf_advisory_context(args.ncf_advisory_panel)
    )
    report, signal = _apply_policy(
        baseline,
        review,
        compare,
        source_signal,
        min_cash_after_cost_weight=args.min_cash_after_cost_weight,
        target_total_assets=args.target_total_assets,
        ncf_advisory_context=ncf_advisory_context,
    )
    paths = _write_outputs(report, signal, resolve_path(args.output_dir), resolve_path(args.latest_pointer))
    print(f"HTML: {paths['html']}")
    print(f"JSON: {paths['json']}")
    print(f"Signal JSON: {paths['signal_json']}")
    print(f"Signal CSV: {paths['signal_csv']}")
    print(f"Latest: {paths['latest']}")
    print(f"Decision: {report['decision']} allowed_for_execution={report['allowed_for_execution']}")
    print(f"Cash after cost: {report['execution_summary_after_policy']['cash_after_cost']:,.0f}")
    ncf = report.get("ncf_advisory_context") or {}
    shadow = ncf.get("shadow_recommendation") or {}
    print(f"NCF advisory: {ncf.get('status')} date={ncf.get('date')} shadow={shadow.get('policy')}")


if __name__ == "__main__":
    main()
