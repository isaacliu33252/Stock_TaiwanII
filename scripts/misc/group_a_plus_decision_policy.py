#!/usr/bin/env python3
"""Convert GroupA+ review votes into an executable decision and adjusted signal."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from group_a_plus_review_tools import PROJECT_ROOT, load_json, resolve_path


DEFAULT_BASELINE = PROJECT_ROOT / "GROUP_A_PLUS_CURRENT_BASELINE.json"
DEFAULT_REVIEW_POINTER = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "review.json"
DEFAULT_COMPARE_POINTER = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "strategy_compare.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "decision"
DEFAULT_LATEST = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "decision.json"
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
    args = parser.parse_args()

    baseline = load_json(args.baseline)
    _review_pointer, review = _load_latest(args.review_pointer)
    _compare_pointer, compare = _load_latest(args.compare_pointer)
    source_signal = load_json(baseline["latest_group_a_plus_final_signal"])
    report, signal = _apply_policy(
        baseline,
        review,
        compare,
        source_signal,
        min_cash_after_cost_weight=args.min_cash_after_cost_weight,
        target_total_assets=args.target_total_assets,
    )
    paths = _write_outputs(report, signal, resolve_path(args.output_dir), resolve_path(args.latest_pointer))
    print(f"HTML: {paths['html']}")
    print(f"JSON: {paths['json']}")
    print(f"Signal JSON: {paths['signal_json']}")
    print(f"Signal CSV: {paths['signal_csv']}")
    print(f"Latest: {paths['latest']}")
    print(f"Decision: {report['decision']} allowed_for_execution={report['allowed_for_execution']}")
    print(f"Cash after cost: {report['execution_summary_after_policy']['cash_after_cost']:,.0f}")


if __name__ == "__main__":
    main()
