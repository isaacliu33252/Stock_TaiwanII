#!/usr/bin/env python3
"""Build the TXO put overlay advisory shadow report (arXiv:2607.00883 pilot).

This is a pure information/advisory snapshot of what a rolled 10%-OTM TXO
(TAIEX index option) put overlay would be holding today, sized against the
current real portfolio NAV at a configurable annual premium budget. It
NEVER places any order, computes no margin requirement, and has no live
allocation impact -- Group A+ does not currently trade options, and this
script does not change that. It exists purely so the mechanism validated in
GROUP_A_PLUS_20260819_2607_00883_TXO_PUT_OVERLAY_HANDOFF.md (five layers of
robustness checks: single-window backtest, 7 independent calendar years,
premium-budget sensitivity grid, real bid-ask transaction costs, and 0050-
vs-TAIEX basis risk, all positive or directionally unchanged) can be
observed running against live data before anyone decides whether it is
worth the much larger step of building real options-execution
infrastructure (margin account, daily repricing, roll automation).

Roll convention (matches the backtest exactly, see the handoff doc Section
4.1 for why): roll every 21 trading days from a fixed anchor date so the
window schedule is reproducible; at each roll, buy the "next month" monthly
TXO contract (avoids ever holding a near-expiry contract) with strike
nearest to 0.90x the TAIEX spot on the roll date.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"
DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "txo_put_overlay_advisory_shadow.json"
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "txo_put_overlay_advisory_shadow.md"

ROLL_ANCHOR = pd.Timestamp("2020-01-02")  # must match the validated backtest's window schedule
ROLL_EVERY = 21  # trading days
ANNUAL_PREMIUM_BUDGET_DEFAULT = 0.015  # 1.5% of NAV/year, the validated pilot's setting
TXO_MULTIPLIER = 50  # NT$ per index point, standard TAIFEX TXO contract size


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _unwrap_standard(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def _load_nav(execution_plan_path: Path, live_signal_path: Path) -> tuple[float, str]:
    if execution_plan_path.exists():
        try:
            data = _unwrap_standard(json.loads(execution_plan_path.read_text(encoding="utf-8")))
            nav = data.get("current_total_assets")
            if nav:
                return float(nav), "execution_plan.current_total_assets"
        except Exception:
            pass
    if live_signal_path.exists():
        try:
            data = _unwrap_standard(json.loads(live_signal_path.read_text(encoding="utf-8")))
            nav = data.get("portfolio_value_input")
            if nav:
                return float(nav), "live_signal.portfolio_value_input"
        except Exception:
            pass
    return 1_000_000.0, "fallback_default"


def build_report(as_of: str | None, annual_premium_budget: float,
                  execution_plan_path: Path, live_signal_path: Path) -> dict[str, Any]:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    twii = con.execute(
        "select dt, close from external_market_ohlcv where ticker='^TWII' order by dt"
    ).fetchdf()
    twii["dt"] = pd.to_datetime(twii["dt"])
    twii = twii.set_index("dt").sort_index()

    as_of_ts = pd.Timestamp(as_of) if as_of else twii.index.max()
    trading_dates = twii.loc[ROLL_ANCHOR:as_of_ts].index
    if len(trading_dates) == 0:
        raise ValueError(f"no ^TWII trading calendar data between {ROLL_ANCHOR.date()} and {as_of_ts.date()}")
    effective_as_of = trading_dates[-1]

    n = len(trading_dates)
    window_idx = (n - 1) // ROLL_EVERY
    roll_dt = trading_dates[window_idx * ROLL_EVERY]
    is_roll_day = bool(effective_as_of == roll_dt)

    full_calendar = twii.loc[ROLL_ANCHOR:].index
    roll_start_pos = window_idx * ROLL_EVERY
    next_roll_is_estimated = roll_start_pos + ROLL_EVERY >= len(full_calendar)
    if not next_roll_is_estimated:
        next_roll_dt = str(full_calendar[roll_start_pos + ROLL_EVERY].date())
    else:
        # trading calendar data doesn't extend that far into the future yet;
        # ~21 trading days is ~29-30 calendar days including weekends
        next_roll_dt = str((roll_dt + pd.Timedelta(days=29)).date())

    spot_at_roll = float(twii.loc[roll_dt, "close"])
    target_strike = round(spot_at_roll * 0.90 / 100) * 100
    next_month = (roll_dt.month % 12) + 1
    next_year = roll_dt.year + (1 if roll_dt.month == 12 else 0)
    contract_month = f"{next_year:04d}{next_month:02d}"

    opt = con.execute(
        """
        select dt, strike_price, close, settlement_price, best_bid, best_ask, volume
        from taifex_options_daily
        where call_put='賣權' and trading_session='一般' and contract_month=?
        order by dt
        """,
        [contract_month],
    ).fetchdf()
    opt["dt"] = pd.to_datetime(opt["dt"])

    leg = opt[(opt["dt"] >= roll_dt) & (opt["strike_price"] == target_strike)].sort_values("dt")
    data_gap = leg.empty
    if not leg.empty:
        available_strikes = opt[opt["dt"] >= roll_dt]["strike_price"].unique()
        actual_strike = target_strike
    else:
        available_strikes = opt[opt["dt"] >= roll_dt]["strike_price"].unique()
        if len(available_strikes) == 0:
            actual_strike = None
        else:
            import numpy as np
            actual_strike = float(available_strikes[abs(available_strikes - target_strike).argmin()])
            leg = opt[(opt["dt"] >= roll_dt) & (opt["strike_price"] == actual_strike)].sort_values("dt")

    entry_row = leg.iloc[0] if not leg.empty else None
    latest_row = leg[leg["dt"] <= effective_as_of]
    latest_row = latest_row.iloc[-1] if not latest_row.empty else entry_row

    P0 = float(entry_row["settlement_price"] if entry_row is not None and entry_row["settlement_price"] > 0
               else (entry_row["close"] if entry_row is not None else float("nan")))
    P_now = float(latest_row["settlement_price"] if latest_row is not None and latest_row["settlement_price"] > 0
                  else (latest_row["close"] if latest_row is not None else float("nan")))
    unrealized_pnl_pct_of_premium = (P_now - P0) / P0 if P0 else None

    nav, nav_source = _load_nav(execution_plan_path, live_signal_path)
    q_per_roll = annual_premium_budget / (252 / ROLL_EVERY)
    premium_budget_dollar = nav * q_per_roll
    contracts = int(premium_budget_dollar // (P0 * TXO_MULTIPLIER)) if P0 else 0
    actual_premium_dollar = contracts * P0 * TXO_MULTIPLIER
    budget_rounds_to_zero_contracts = bool(contracts == 0 and P0 and premium_budget_dollar > 0)

    status = "data_gap" if data_gap or entry_row is None else ("roll_today" if is_roll_day else "holding")

    return {
        "as_of": str(effective_as_of.date()),
        "status": status,
        "advisory_only": True,
        "no_live_position": True,
        "no_execution_impact": True,
        "roll_schedule": {
            "roll_anchor": str(ROLL_ANCHOR.date()), "roll_every_trading_days": ROLL_EVERY,
            "current_roll_date": str(roll_dt.date()), "next_roll_date": next_roll_dt,
            "next_roll_date_estimated": next_roll_is_estimated,
            "is_roll_day_today": is_roll_day, "trading_days_until_next_roll": ROLL_EVERY - (n - 1 - roll_start_pos),
        },
        "contract": {
            "contract_month": contract_month, "target_strike": target_strike,
            "actual_strike_used": actual_strike, "strike_selection_gap": actual_strike != target_strike if actual_strike else None,
            "spot_at_roll": spot_at_roll, "call_put": "put",
        },
        "pricing": {
            "entry_price_at_roll": P0, "current_price": P_now,
            "unrealized_pnl_pct_of_initial_premium": unrealized_pnl_pct_of_premium,
            "latest_price_date": str(latest_row["dt"].date()) if latest_row is not None else None,
            "latest_bid": float(latest_row["best_bid"]) if latest_row is not None and latest_row["best_bid"] > 0 else None,
            "latest_ask": float(latest_row["best_ask"]) if latest_row is not None and latest_row["best_ask"] > 0 else None,
        },
        "sizing": {
            "nav": nav, "nav_source": nav_source,
            "annual_premium_budget_pct": annual_premium_budget,
            "premium_budget_this_roll_dollar": premium_budget_dollar,
            "txo_multiplier_ntd_per_point": TXO_MULTIPLIER,
            "recommended_contracts": contracts,
            "actual_premium_dollar_at_recommended_contracts": actual_premium_dollar,
            "budget_rounds_to_zero_contracts": budget_rounds_to_zero_contracts,
        },
        "validation_reference": {
            "handoff_doc": "GROUP_A_PLUS_20260819_2607_00883_TXO_PUT_OVERLAY_HANDOFF.md",
            "results_json": "results/2607_00883_txo_put_overlay_shadow.json",
            "summary": ("Five robustness layers (single-window, 7 independent calendar years, "
                        "0.5-3.0%/yr premium sensitivity, real bid-ask transaction costs, 0050-vs-TWII "
                        "basis risk) all positive or directionally unchanged as of 2026-08-19. "
                        "Not yet promoted -- Group A+ has no options-execution infrastructure."),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_markdown(payload: dict[str, Any]) -> str:
    rs = payload["roll_schedule"]
    c = payload["contract"]
    p = payload["pricing"]
    s = payload["sizing"]
    pnl = p["unrealized_pnl_pct_of_initial_premium"]
    lines = [
        "# TXO Put Overlay Advisory Shadow",
        "",
        f"- as_of: `{payload.get('as_of')}`",
        f"- status: `{payload.get('status')}`",
        "- **advisory only — no live position, no order placed, no live allocation impact**",
        "",
        "## Roll schedule",
        f"- current roll date: `{rs['current_roll_date']}` (next roll: `{rs['next_roll_date']}`, "
        f"in {rs['trading_days_until_next_roll']} trading days)",
        f"- is roll day today: `{rs['is_roll_day_today']}`",
        "",
        "## Contract",
        f"- TXO put, contract_month=`{c['contract_month']}`, strike=`{c['actual_strike_used']}` "
        f"(target 10% OTM was `{c['target_strike']}`)",
        f"- TAIEX spot at roll: `{c['spot_at_roll']:.1f}`",
        "",
        "## Pricing",
        f"- entry price at roll: `{p['entry_price_at_roll']}`  current price: `{p['current_price']}` "
        f"(as of `{p['latest_price_date']}`)",
        f"- unrealized P&L vs initial premium: `{pnl*100:.1f}%`" if pnl is not None else "- unrealized P&L: n/a",
        "",
        "## Sizing (theoretical, at recommended premium budget)",
        f"- NAV used: `${s['nav']:,.0f}` (source: `{s['nav_source']}`)",
        f"- annual premium budget: `{s['annual_premium_budget_pct']*100:.2f}%`, "
        f"this roll's budget: `${s['premium_budget_this_roll_dollar']:,.0f}`",
        f"- recommended contracts: `{s['recommended_contracts']}` "
        f"(actual premium at that size: `${s['actual_premium_dollar_at_recommended_contracts']:,.0f}`)",
        (f"- **budget rounds to 0 contracts at current option pricing** — the premium budget this roll "
         f"(`${s['premium_budget_this_roll_dollar']:,.0f}`) is smaller than one contract's premium "
         f"(`${p['entry_price_at_roll']*s['txo_multiplier_ntd_per_point']:,.0f}`)"
         if s.get("budget_rounds_to_zero_contracts") else ""),
        "",
        f"Validation reference: {payload['validation_reference']['summary']}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--annual-premium-budget", type=float, default=ANNUAL_PREMIUM_BUDGET_DEFAULT)
    parser.add_argument("--execution-plan", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args()

    payload = build_report(
        as_of=args.as_of, annual_premium_budget=args.annual_premium_budget,
        execution_plan_path=_resolve(args.execution_plan), live_signal_path=_resolve(args.live_signal),
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_md = _resolve(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(build_markdown(payload), encoding="utf-8")
    print(f"JSON: {output}")
    print(f"Markdown: {output_md}")
    print(f"status={payload['status']} roll_date={payload['roll_schedule']['current_roll_date']} "
          f"strike={payload['contract']['actual_strike_used']} pnl={payload['pricing']['unrealized_pnl_pct_of_initial_premium']}")


if __name__ == "__main__":
    main()
