#!/usr/bin/env python3
"""Second-stage execution helper for GroupA+ deferred risk-off buys."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

from group_a_00679b_continuous_shadow import _execution_rows


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_STAGE_ONE_JSON = PROJECT_ROOT / "results" / "group_a_plus_dynamic_20260608.json"
DEFAULT_GROUP_A_PLUS_CONFIG = PROJECT_ROOT / "group_a_plus_config.json"
DEFAULT_0050_CACHE = (
    PROJECT_ROOT
    / "FinRL"
    / "data"
    / "portfolio_cache"
    / "0050_TW_20200101_20260606_1d_raw_v1.parquet"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Release part of GroupA+ risk-off deferred buys after intraday/close confirmation."
    )
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
    parser.add_argument(
        "--twii-recovered",
        action="store_true",
        help="Treat TAIEX intraday recovery as a partial confirmation trigger.",
    )
    parser.add_argument("--min-trade-value", type=float, default=None)
    parser.add_argument("--commission-rate", type=float, default=None)
    parser.add_argument("--etf-sell-tax-rate", type=float, default=None)
    parser.add_argument("--slippage-rate", type=float, default=None)
    parser.add_argument("--output-prefix", default=None)
    return parser.parse_args()


def _load_json(path: str | Path) -> dict:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return json.loads(candidate.read_text(encoding="utf-8"))


def _load_reference_bar(cache_path: Path, reference_date: str) -> dict:
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


def _second_stage_control(config: dict) -> dict:
    return dict(config.get("second_stage_control", {}) or {})


def _release_decision(
    *,
    reference_close: float,
    reference_low: float,
    observed_open: float | None,
    observed_low: float | None,
    observed_last: float | None,
    observed_close: float | None,
    twii_recovered: bool,
    control: dict,
) -> dict:
    fractions = dict(control.get("release_fraction_by_trigger", {}) or {})
    break_buffer = float(control.get("break_low_buffer", 0.0))
    price_tolerance = float(control.get("price_tolerance", 0.01))
    gap_down_threshold = float(control.get("pause_open_gap_down_pct", -0.015))
    pause_on_break = bool(control.get("pause_on_break_reference_low", True))
    pause_on_gap_down = bool(control.get("pause_on_open_gap_down", True))
    break_level = reference_low * (1.0 - break_buffer)
    open_gap_pct = None
    if observed_open is not None and reference_close > 0:
        open_gap_pct = (float(observed_open) / float(reference_close)) - 1.0

    if pause_on_break and observed_low is not None and observed_low < break_level:
        return {
            "trigger": "pause_break_reference_low",
            "release_fraction": 0.0,
            "reason": "0050_low_below_reference_low",
            "break_level": break_level,
            "open_gap_pct": open_gap_pct,
            "gap_down_threshold": gap_down_threshold,
        }

    if observed_close is not None and observed_close > reference_close + price_tolerance:
        return {
            "trigger": "close_above_reference_close",
            "release_fraction": float(fractions.get("close_above_reference_close", 0.50)),
            "reason": "0050_close_above_reference_close",
            "break_level": break_level,
            "open_gap_pct": open_gap_pct,
            "gap_down_threshold": gap_down_threshold,
        }

    if pause_on_gap_down and open_gap_pct is not None and open_gap_pct <= gap_down_threshold:
        return {
            "trigger": "pause_open_gap_down",
            "release_fraction": 0.0,
            "reason": "0050_open_gap_down_too_large",
            "break_level": break_level,
            "open_gap_pct": open_gap_pct,
            "gap_down_threshold": gap_down_threshold,
        }

    latest_intraday = observed_last if observed_last is not None else observed_open
    intraday_recovered = latest_intraday is not None and latest_intraday >= reference_close - price_tolerance
    if intraday_recovered or bool(twii_recovered):
        return {
            "trigger": "intraday_recovery",
            "release_fraction": float(fractions.get("intraday_recovery", 0.25)),
            "reason": "0050_or_twii_intraday_recovery",
            "break_level": break_level,
            "open_gap_pct": open_gap_pct,
            "gap_down_threshold": gap_down_threshold,
        }

    return {
        "trigger": "hold_deferred_buys",
        "release_fraction": float(fractions.get("hold_deferred_buys", 0.0)),
        "reason": "no_recovery_confirmation",
        "break_level": break_level,
        "open_gap_pct": open_gap_pct,
        "gap_down_threshold": gap_down_threshold,
    }


def _build_second_stage_targets(
    current_stage_targets: dict[str, int],
    full_targets_before_execution_control: dict[str, int],
    *,
    release_fraction: float,
) -> tuple[dict[str, int], dict[str, int]]:
    release_fraction = min(max(float(release_fraction), 0.0), 1.0)
    next_targets: dict[str, int] = {}
    released: dict[str, int] = {}
    for ticker, current_target in current_stage_targets.items():
        current_target = int(current_target)
        full_target = int(full_targets_before_execution_control.get(ticker, current_target))
        deferred_buy = max(full_target - current_target, 0)
        release_shares = int(math.floor(deferred_buy * release_fraction))
        next_targets[ticker] = current_target + release_shares
        released[ticker] = release_shares
    return next_targets, released


def _write_markdown(path: Path, payload: dict, rows: list[dict]) -> None:
    decision = payload["decision"]
    s = payload["execution_summary"]
    lines = [
        "# GroupA+ Second-Stage Execution",
        "",
        f"Date: {payload['generated_at']}",
        "Status: Shadow research only",
        "",
        "## Trigger",
        "",
        f"- Trigger: `{decision['trigger']}`",
        f"- Reason: `{decision['reason']}`",
        f"- Release fraction: `{decision['release_fraction']:.2%}`",
        f"- Reference close: `{payload['reference']['close']:.2f}`",
        f"- Reference low: `{payload['reference']['low']:.2f}`",
        f"- 0050 open gap: `{decision['open_gap_pct']:.2%}`" if decision["open_gap_pct"] is not None else "- 0050 open gap: `n/a`",
        "",
        "## Second-Stage Orders",
        "",
        "| Ticker | Stage-1 target | Stage-2 target | Delta | Side | Trade notional |",
        "| --- | ---: | ---: | ---: | --- | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {ticker} | {current_shares:,} | {target_shares:,} | {delta_shares:,} | {side} | {trade_notional:,.0f} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Costs",
            "",
            f"- Buy notional: `{s['buy_notional']:,.0f}`",
            f"- Sell notional: `{s['sell_notional']:,.0f}`",
            f"- Total execution cost: `{s['total_execution_cost']:,.0f}`",
            f"- Cash after cost estimate: `{s['cash_after_cost']:,.0f}`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = _parse_args()
    stage_one = _load_json(args.stage_one_json)
    config = _load_json(args.group_a_plus_config)
    control = _second_stage_control(config)

    reference_date = str(args.reference_date or stage_one["actual_data_date"])
    cache_0050 = Path(args.cache_0050)
    if not cache_0050.is_absolute():
        cache_0050 = (PROJECT_ROOT / cache_0050).resolve()
    reference = _load_reference_bar(cache_0050, reference_date)
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
        control=control,
    )
    stage_one_targets = {k: int(v) for k, v in stage_one["target_shares"].items()}
    full_targets = {
        k: int(v)
        for k, v in stage_one["target_shares_before_execution_control"].items()
    }
    stage_two_targets, released = _build_second_stage_targets(
        stage_one_targets,
        full_targets,
        release_fraction=float(decision["release_fraction"]),
    )

    prices = {k: float(v) for k, v in stage_one["latest_prices"].items()}
    execution_price_0050 = args.__dict__["0050_close"] or args.__dict__["0050_last"] or args.__dict__["0050_open"]
    if execution_price_0050 is not None and "0050.TW" in prices:
        prices["0050.TW"] = float(execution_price_0050)

    min_trade_value = float(
        args.min_trade_value
        if args.min_trade_value is not None
        else stage_one.get("min_trade_value", 0.0)
    )
    commission_rate = float(
        args.commission_rate
        if args.commission_rate is not None
        else stage_one.get("commission_rate", 0.001425)
    )
    etf_sell_tax_rate = float(
        args.etf_sell_tax_rate
        if args.etf_sell_tax_rate is not None
        else stage_one.get("etf_sell_tax_rate", 0.001)
    )
    slippage_rate = float(
        args.slippage_rate
        if args.slippage_rate is not None
        else stage_one.get("slippage_rate", 0.0005)
    )
    rows, execution_summary = _execution_rows(
        stage_one_targets,
        stage_two_targets,
        prices,
        {},
        float(stage_one["total_assets"]),
        commission_rate=commission_rate,
        etf_sell_tax_rate=etf_sell_tax_rate,
        slippage_rate=slippage_rate,
        min_trade_value=min_trade_value,
        batch_count=1,
        batch_threshold=float("inf"),
    )
    executable_targets = {str(row["ticker"]): int(row["target_shares"]) for row in rows}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = Path(args.output_prefix) if args.output_prefix else PROJECT_ROOT / "results" / f"group_a_plus_second_stage_{timestamp}"
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = prefix.with_suffix(".csv")
    json_path = prefix.with_suffix(".json")
    md_path = prefix.with_suffix(".md")

    payload = {
        "study": "GroupA+ second-stage execution",
        "strategy_name": stage_one.get("strategy_name", config.get("name", "GroupA+")),
        "status": "shadow_research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_stage_one_json": str(Path(args.stage_one_json).resolve() if Path(args.stage_one_json).is_absolute() else (PROJECT_ROOT / args.stage_one_json).resolve()),
        "actual_data_date": stage_one.get("actual_data_date"),
        "requested_as_of_date": stage_one.get("requested_as_of_date"),
        "reference": reference,
        "observed": {
            "0050_open": args.__dict__["0050_open"],
            "0050_low": args.__dict__["0050_low"],
            "0050_last": args.__dict__["0050_last"],
            "0050_close": args.__dict__["0050_close"],
            "twii_recovered": bool(args.twii_recovered),
        },
        "decision": decision,
        "stage_one_target_shares": stage_one_targets,
        "full_target_shares_before_execution_control": full_targets,
        "released_deferred_buy_shares": released,
        "target_shares": executable_targets,
        "latest_prices": prices,
        "min_trade_value": min_trade_value,
        "commission_rate": commission_rate,
        "etf_sell_tax_rate": etf_sell_tax_rate,
        "slippage_rate": slippage_rate,
        "execution_summary": execution_summary,
        "outputs": {
            "csv": str(csv_path),
            "json": str(json_path),
            "markdown": str(md_path),
        },
    }
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(md_path, payload, rows)

    print(f"CSV:  {csv_path}")
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")
    print(f"Trigger: {decision['trigger']}")
    print(f"Release fraction: {decision['release_fraction']:.2%}")
    print(f"Buy notional: {execution_summary['buy_notional']:,.0f}")
    print(f"Cash after cost: {execution_summary['cash_after_cost']:,.0f}")


if __name__ == "__main__":
    main()
