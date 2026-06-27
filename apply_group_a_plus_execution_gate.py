#!/usr/bin/env python3
"""Apply an intraday first-stage execution gate to GroupA+ targets."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from group_a_00679b_continuous_shadow import _execution_rows
from group_a_plus_second_stage_execution import _load_reference_bar, _release_decision


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_STAGE_ONE_JSON = PROJECT_ROOT / "results" / "group_a_plus_dynamic_20260608_live_config.json"
DEFAULT_GROUP_A_PLUS_CONFIG = PROJECT_ROOT / "group_a_plus_config.json"
DEFAULT_0050_CACHE = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "0050_TW_20200101_20260606_1d_raw_v1.parquet"
RISK_BUY_TICKERS = {"0050.TW", "00631L.TW"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-one-json", default=str(DEFAULT_STAGE_ONE_JSON))
    parser.add_argument("--group-a-plus-config", default=str(DEFAULT_GROUP_A_PLUS_CONFIG))
    parser.add_argument("--0050-cache", dest="cache_0050", default=str(DEFAULT_0050_CACHE))
    parser.add_argument("--reference-date", default=None)
    parser.add_argument("--reference-close", type=float, default=None)
    parser.add_argument("--reference-low", type=float, default=None)
    parser.add_argument("--0050-open", type=float, default=None)
    parser.add_argument("--0050-low", type=float, default=None)
    parser.add_argument("--0050-last", type=float, default=None)
    parser.add_argument("--0050-close", type=float, default=None)
    parser.add_argument("--twii-recovered", action="store_true")
    parser.add_argument("--min-trade-value", type=float, default=None)
    parser.add_argument("--commission-rate", type=float, default=None)
    parser.add_argument("--etf-sell-tax-rate", type=float, default=None)
    parser.add_argument("--slippage-rate", type=float, default=None)
    parser.add_argument("--output-prefix", default=None)
    return parser.parse_args()


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return candidate


def _first_stage_fractions(decision: dict[str, Any]) -> dict[str, float]:
    trigger = str(decision["trigger"])
    release_fraction = float(decision.get("release_fraction", 0.0))
    if trigger in {"pause_break_reference_low", "pause_open_gap_down", "hold_deferred_buys"}:
        risk_buy_fraction = 0.0
    else:
        risk_buy_fraction = release_fraction
    return {
        "risk_buy_fraction": min(max(risk_buy_fraction, 0.0), 1.0),
        "defensive_sleeve_sell_fraction": min(max(risk_buy_fraction, 0.0), 1.0),
    }


def _apply_first_stage_gate(
    current_shares: dict[str, int],
    stage_one_targets: dict[str, int],
    *,
    risk_buy_fraction: float,
    defensive_sleeve_sell_fraction: float,
    defensive_ticker: str = "00679B.TWO",
) -> tuple[dict[str, int], dict[str, Any]]:
    gated: dict[str, int] = {}
    staged: dict[str, dict[str, int | float | bool]] = {}
    for ticker, raw_target in stage_one_targets.items():
        current = int(current_shares.get(ticker, 0))
        raw_target = int(raw_target)
        raw_delta = raw_target - current
        target = raw_target
        fraction = 1.0
        if ticker in RISK_BUY_TICKERS and raw_delta > 0:
            fraction = risk_buy_fraction
            target = current + int(raw_delta * risk_buy_fraction)
        elif ticker == defensive_ticker and raw_delta < 0:
            fraction = defensive_sleeve_sell_fraction
            target = current - int(abs(raw_delta) * defensive_sleeve_sell_fraction)
        gated[ticker] = target
        staged[ticker] = {
            "current_shares": current,
            "raw_target_shares": raw_target,
            "raw_delta_shares": raw_delta,
            "gated_target_shares": target,
            "gated_delta_shares": target - current,
            "execution_fraction": fraction,
            "gate_applied": target != raw_target,
        }
    return gated, staged


def _write_markdown(path: Path, payload: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    d = payload["decision"]
    lines = [
        "# GroupA+ First-Stage Execution Gate",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Stage-one source: `{payload['source_stage_one_json']}`",
        "",
        "## Gate",
        "",
        f"- Trigger: `{d['trigger']}`",
        f"- Reason: `{d['reason']}`",
        f"- Risk-buy fraction: `{payload['gate_fractions']['risk_buy_fraction']:.2%}`",
        f"- Defensive-sleeve sell fraction: `{payload['gate_fractions']['defensive_sleeve_sell_fraction']:.2%}`",
        f"- Reference low: `{payload['reference']['low']:.2f}`",
        f"- Reference close: `{payload['reference']['close']:.2f}`",
        "",
        "## Orders",
        "",
        "| Ticker | Current | Raw target | Gated target | Delta | Side | Trade notional |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    staged = payload["staged_targets"]
    for row in rows:
        info = staged[row["ticker"]]
        lines.append(
            "| {ticker} | {current_shares:,} | {raw_target_shares:,} | {target_shares:,} | {delta_shares:,} | {side} | {trade_notional:,.0f} |".format(
                ticker=row["ticker"],
                current_shares=info["current_shares"],
                raw_target_shares=info["raw_target_shares"],
                target_shares=row["target_shares"],
                delta_shares=row["delta_shares"],
                side=row["side"],
                trade_notional=row["trade_notional"],
            )
        )
    lines.extend(
        [
            "",
            f"- Buy notional: `{payload['execution_summary']['buy_notional']:,.0f}`",
            f"- Sell notional: `{payload['execution_summary']['sell_notional']:,.0f}`",
            f"- Cash after cost: `{payload['execution_summary']['cash_after_cost']:,.0f}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = _parse_args()
    stage_one_path = _resolve(args.stage_one_json)
    config_path = _resolve(args.group_a_plus_config)
    stage_one = json.loads(stage_one_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    reference_date = str(args.reference_date or stage_one["actual_data_date"])
    reference = _load_reference_bar(_resolve(args.cache_0050), reference_date)
    if args.reference_close is not None:
        reference["close"] = float(args.reference_close)
    if args.reference_low is not None:
        reference["low"] = float(args.reference_low)
    decision = _release_decision(
        reference_close=float(reference["close"]),
        reference_low=float(reference["low"]),
        observed_open=args.__dict__["0050_open"],
        observed_low=args.__dict__["0050_low"],
        observed_last=args.__dict__["0050_last"],
        observed_close=args.__dict__["0050_close"],
        twii_recovered=bool(args.twii_recovered),
        control=dict(config.get("second_stage_control", {}) or {}),
    )
    fractions = _first_stage_fractions(decision)
    current_shares = {str(k): int(v) for k, v in stage_one["current_shares"].items()}
    raw_targets = {str(k): int(v) for k, v in stage_one["target_shares"].items()}
    gated_targets, staged = _apply_first_stage_gate(
        current_shares,
        raw_targets,
        risk_buy_fraction=float(fractions["risk_buy_fraction"]),
        defensive_sleeve_sell_fraction=float(fractions["defensive_sleeve_sell_fraction"]),
        defensive_ticker=str(dict(config.get("overlay", {}) or {}).get("ticker") or "00679B.TWO"),
    )
    prices = {str(k): float(v) for k, v in stage_one["latest_prices"].items()}
    observed_0050 = args.__dict__["0050_close"] or args.__dict__["0050_last"] or args.__dict__["0050_open"]
    if observed_0050 is not None:
        prices["0050.TW"] = float(observed_0050)
    min_trade_value = float(args.min_trade_value if args.min_trade_value is not None else stage_one.get("min_trade_value", 0.0))
    commission_rate = float(args.commission_rate if args.commission_rate is not None else stage_one.get("commission_rate", 0.001425))
    etf_sell_tax_rate = float(args.etf_sell_tax_rate if args.etf_sell_tax_rate is not None else stage_one.get("etf_sell_tax_rate", 0.001))
    slippage_rate = float(args.slippage_rate if args.slippage_rate is not None else stage_one.get("slippage_rate", 0.0005))
    rows, execution_summary = _execution_rows(
        current_shares,
        gated_targets,
        prices,
        {},
        float(stage_one["total_assets"]),
        commission_rate=commission_rate,
        etf_sell_tax_rate=etf_sell_tax_rate,
        slippage_rate=slippage_rate,
        min_trade_value=min_trade_value,
        batch_count=int(stage_one.get("batch_count", 3)),
        batch_threshold=float(stage_one.get("batch_threshold", 100000.0)),
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = Path(args.output_prefix) if args.output_prefix else PROJECT_ROOT / "results" / f"group_a_plus_first_stage_gate_{timestamp}"
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    md_path = prefix.with_suffix(".md")
    payload = {
        "strategy_name": stage_one.get("strategy_name", "GroupA+"),
        "status": "first_stage_execution_gated",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_stage_one_json": str(stage_one_path),
        "actual_data_date": stage_one.get("actual_data_date"),
        "requested_as_of_date": stage_one.get("requested_as_of_date"),
        "total_assets": float(stage_one["total_assets"]),
        "reference": reference,
        "observed": {
            "0050_open": args.__dict__["0050_open"],
            "0050_low": args.__dict__["0050_low"],
            "0050_last": args.__dict__["0050_last"],
            "0050_close": args.__dict__["0050_close"],
        },
        "decision": decision,
        "gate_fractions": fractions,
        "latest_prices": prices,
        "current_shares": current_shares,
        "raw_target_shares": raw_targets,
        "target_shares": {str(row["ticker"]): int(row["target_shares"]) for row in rows},
        "staged_targets": staged,
        "execution_summary": execution_summary,
        "outputs": {"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)},
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    _write_markdown(md_path, payload, rows)
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    print(f"MD:   {md_path}")
    print(f"Trigger: {decision['trigger']}")
    print(f"Risk-buy fraction: {fractions['risk_buy_fraction']:.2%}")
    print(f"Defensive sell fraction: {fractions['defensive_sleeve_sell_fraction']:.2%}")
    print(f"Cash after cost: {execution_summary['cash_after_cost']:,.0f}")


if __name__ == "__main__":
    main()
