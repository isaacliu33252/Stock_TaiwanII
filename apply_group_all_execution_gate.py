#!/usr/bin/env python3
"""Apply intraday execution gates to latest Group All raw targets.

The raw All strategy target is still the source of truth for portfolio weights.
This helper only stages execution when the reference 0050 price action is weak.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RAW_SIGNAL = PROJECT_ROOT / "results" / "signal_group_all_latest_20260608_total2m_from_20260607_holdings.json"
DEFAULT_0050_CACHE = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "0050_TW_20200101_20260606_1d_raw_v1.parquet"
RISK_INCREASING_BUY_TICKERS = {"0050.TW", "00631L.TW"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-signal-json", default=str(DEFAULT_RAW_SIGNAL))
    parser.add_argument("--0050-cache", dest="cache_0050", default=str(DEFAULT_0050_CACHE))
    parser.add_argument("--reference-date", default=None)
    parser.add_argument("--reference-close", type=float, default=None)
    parser.add_argument("--reference-low", type=float, default=None)
    parser.add_argument("--0050-open", type=float, default=None)
    parser.add_argument("--0050-low", type=float, default=None)
    parser.add_argument("--0050-last", type=float, default=None)
    parser.add_argument("--0050-close", type=float, default=None)
    parser.add_argument("--output-prefix", default=None)
    return parser.parse_args()


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _load_reference_bar(cache_path: Path, reference_date: str) -> dict[str, float | str]:
    if not cache_path.exists():
        raise FileNotFoundError(f"0050 cache not found: {cache_path}")
    df = pd.read_parquet(cache_path)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    matched = df[df["date"] == reference_date]
    if matched.empty:
        raise RuntimeError(f"0050 reference date {reference_date} not found in {cache_path}")
    row = matched.iloc[-1]
    return {
        "date": str(row["date"]),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
    }


def _execution_gate_decision(
    *,
    reference_close: float,
    reference_low: float,
    observed_open: float | None,
    observed_low: float | None,
    observed_last: float | None,
    observed_close: float | None,
) -> dict[str, Any]:
    latest = observed_close if observed_close is not None else observed_last
    open_gap_pct = None
    if observed_open is not None and reference_close > 0:
        open_gap_pct = observed_open / reference_close - 1.0

    if observed_low is not None and observed_low < reference_low:
        return {
            "trigger": "pause_break_reference_low",
            "risk_buy_fraction": 0.0,
            "reason": "0050_low_below_reference_low",
            "open_gap_pct": open_gap_pct,
        }
    if latest is not None and latest < reference_low:
        return {
            "trigger": "pause_below_reference_low",
            "risk_buy_fraction": 0.0,
            "reason": "0050_latest_below_reference_low",
            "open_gap_pct": open_gap_pct,
        }
    if observed_close is not None and observed_close > reference_close:
        return {
            "trigger": "close_above_reference_close",
            "risk_buy_fraction": 0.5,
            "reason": "0050_close_above_reference_close",
            "open_gap_pct": open_gap_pct,
        }
    if latest is not None and latest >= reference_close:
        return {
            "trigger": "intraday_recovery_to_reference_close",
            "risk_buy_fraction": 0.25,
            "reason": "0050_recovered_to_reference_close",
            "open_gap_pct": open_gap_pct,
        }
    if latest is not None and latest >= reference_low:
        return {
            "trigger": "partial_recovery_above_reference_low",
            "risk_buy_fraction": 0.10,
            "reason": "0050_recovered_above_reference_low_but_below_close",
            "open_gap_pct": open_gap_pct,
        }
    return {
        "trigger": "hold_deferred_risk_buys",
        "risk_buy_fraction": 0.0,
        "reason": "no_recovery_confirmation",
        "open_gap_pct": open_gap_pct,
    }


def _apply_execution_gate(raw_rows: list[dict[str, Any]], decision: dict[str, Any]) -> list[dict[str, Any]]:
    buy_fraction = min(max(float(decision["risk_buy_fraction"]), 0.0), 1.0)
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        out = dict(row)
        ticker = str(row["ticker"])
        current = int(row["current_shares"])
        raw_target = int(row["target_shares"])
        raw_delta = raw_target - current
        target = raw_target
        if ticker in RISK_INCREASING_BUY_TICKERS and raw_delta > 0:
            target = current + int(math.floor(raw_delta * buy_fraction))
        delta = target - current
        out["raw_target_shares"] = raw_target
        out["raw_delta_shares"] = raw_delta
        out["target_shares"] = target
        out["delta_shares"] = delta
        out["action_hint"] = "buy" if delta > 0 else "sell" if delta < 0 else "hold"
        out["execution_gate_applied"] = target != raw_target
        rows.append(out)
    return rows


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    d = payload["decision"]
    lines = [
        "# Group All Execution-Gated Signal",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Raw signal: `{payload['raw_signal_json']}`",
        "",
        "## Gate",
        "",
        f"- Trigger: `{d['trigger']}`",
        f"- Reason: `{d['reason']}`",
        f"- Risk-buy fraction: `{d['risk_buy_fraction']:.2%}`",
        f"- Reference low: `{payload['reference']['low']:.2f}`",
        f"- Reference close: `{payload['reference']['close']:.2f}`",
        "",
        "## Targets",
        "",
        "| Ticker | Current | Raw target | Gated target | Delta | Action |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            "| {ticker} | {current_shares:,} | {raw_target_shares:,} | {target_shares:,} | {delta_shares:,} | {action_hint} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            f"- Target cash value: `{payload['target_cash_value']:,.0f}`",
            f"- Target cash weight: `{payload['target_cash_account_weight']:.2%}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = _parse_args()
    raw_path = _resolve(args.raw_signal_json)
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    reference_date = str(args.reference_date or raw.get("actual_data_date"))
    cache_0050 = _resolve(args.cache_0050)
    reference = _load_reference_bar(cache_0050, reference_date)
    if args.reference_close is not None:
        reference["close"] = float(args.reference_close)
    if args.reference_low is not None:
        reference["low"] = float(args.reference_low)

    decision = _execution_gate_decision(
        reference_close=float(reference["close"]),
        reference_low=float(reference["low"]),
        observed_open=args.__dict__["0050_open"],
        observed_low=args.__dict__["0050_low"],
        observed_last=args.__dict__["0050_last"],
        observed_close=args.__dict__["0050_close"],
    )
    rows = _apply_execution_gate(list(raw["rows"]), decision)
    prices = dict(raw["latest_prices"])
    observed_price = args.__dict__["0050_close"] or args.__dict__["0050_last"] or args.__dict__["0050_open"]
    if observed_price is not None:
        prices["0050.TW"] = float(observed_price)
        for row in rows:
            if row["ticker"] == "0050.TW":
                row["latest_price"] = float(observed_price)
                row["current_value"] = int(row["current_shares"]) * float(observed_price)
    total_assets = float(raw.get("total_assets_assumption") or raw.get("current_total_portfolio_value"))
    target_invested = sum(int(row["target_shares"]) * float(prices[row["ticker"]]) for row in rows)
    target_cash = total_assets - target_invested

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = Path(args.output_prefix) if args.output_prefix else PROJECT_ROOT / "results" / f"group_all_execution_gated_{timestamp}"
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    md_path = prefix.with_suffix(".md")

    payload = {
        "strategy_name": raw.get("strategy_name"),
        "status": "execution_gated",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "raw_signal_json": str(raw_path),
        "as_of_date": raw.get("as_of_date"),
        "actual_data_date": raw.get("actual_data_date"),
        "total_assets_assumption": total_assets,
        "reference": reference,
        "observed": {
            "0050_open": args.__dict__["0050_open"],
            "0050_low": args.__dict__["0050_low"],
            "0050_last": args.__dict__["0050_last"],
            "0050_close": args.__dict__["0050_close"],
        },
        "decision": decision,
        "latest_prices": prices,
        "target_cash_value": target_cash,
        "target_cash_account_weight": target_cash / total_assets if total_assets else 0.0,
        "target_shares": {str(row["ticker"]): int(row["target_shares"]) for row in rows},
        "rows": rows,
        "outputs": {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)},
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    _write_markdown(md_path, payload)

    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    print(f"MD:   {md_path}")
    print(f"Trigger: {decision['trigger']}")
    print(f"Risk-buy fraction: {decision['risk_buy_fraction']:.2%}")
    print(f"Target cash: {target_cash:,.0f}")


if __name__ == "__main__":
    main()
