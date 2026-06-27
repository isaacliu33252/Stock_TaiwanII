#!/usr/bin/env python3
"""Run the Group A Golden1_0531 shadow candidate with a TDCC crowding overlay."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from run_group_a_shareholding_shadow import (
    _load_weekly_features,
    _ticker_snapshot,
    assess_shadow_signal,
)


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = PROJECT_ROOT / "group_a_tdcc_improved_config_destination_primary.json"
DEFAULT_CONDITIONAL_INVERSE_OVERLAY_CONFIG = PROJECT_ROOT / "group_a_00632r_conditional_cap_overlay_config.json"
DEFAULT_INVERSE_HOLD_OVERLAY_CONFIG = PROJECT_ROOT / "group_a_00632r_hold10_overlay_config.json"
DEFAULT_RESULT_JSON = (
    PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260525_20260526_193252.json"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "results"
LATEST_JSON = DEFAULT_OUTPUT_DIR / "group_a_tdcc_improved_live_latest.json"
LATEST_CSV = DEFAULT_OUTPUT_DIR / "group_a_tdcc_improved_live_latest.csv"
LATEST_MANIFEST = DEFAULT_OUTPUT_DIR / "group_a_tdcc_improved_bundle_latest.json"
DEFAULT_INVERSE_HOLD_STATE = DEFAULT_OUTPUT_DIR / "group_a_00632r_hold10_overlay_state.json"
DEFAULT_COMMISSION_RATE = 0.001425
DEFAULT_ETF_SELL_TAX_RATE = 0.001
DEFAULT_SLIPPAGE_RATE = 0.0005


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--result-json", default=str(DEFAULT_RESULT_JSON))
    parser.add_argument("--base-signal-json", default=None)
    parser.add_argument("--xlsx", default=None)
    parser.add_argument("--holdings-row-label", default="即時庫存")
    parser.add_argument("--simulation-start", default=None)
    parser.add_argument("--history-start", default=None)
    parser.add_argument("--download-end", default=None)
    parser.add_argument("--as-of-date", default=str(date.today()))
    parser.add_argument("--extra-cash", type=float, default=1_000_000.0)
    parser.add_argument("--override-holdings-json", default=None)
    parser.add_argument("--action-threshold", type=float, default=0.01)
    parser.add_argument("--max-stale-days", type=int, default=3)
    parser.add_argument("--max-strategy-drawdown", type=float, default=0.27)
    parser.add_argument("--max-underperformance-vs-0050", type=float, default=0.10)
    parser.add_argument("--strategy-replay", action="store_true")
    parser.add_argument(
        "--conditional-inverse-overlay-config",
        default=str(DEFAULT_CONDITIONAL_INVERSE_OVERLAY_CONFIG),
        help="Optional conditional 00632R cap overlay config. Use empty string to disable.",
    )
    parser.add_argument(
        "--inverse-hold-overlay-config",
        default=str(DEFAULT_INVERSE_HOLD_OVERLAY_CONFIG),
        help="Optional post-target 00632R hold-limit overlay config. Use empty string to disable.",
    )
    parser.add_argument("--inverse-hold-state-json", default=str(DEFAULT_INVERSE_HOLD_STATE))
    return parser.parse_args()


def _extract_output_path(stdout: str, label: str) -> Path:
    match = re.search(rf"^{label}:\s+(.+)$", stdout, flags=re.MULTILINE)
    if not match:
        raise RuntimeError(f"Unable to parse {label} path from base signal output")
    return Path(match.group(1).strip())


def _generate_base_signal(args: argparse.Namespace) -> Path:
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "generate_dual_group_signal.py"),
        "--group",
        "group_a",
        "--result-json",
        str(Path(args.result_json).resolve()),
        "--holdings-row-label",
        str(args.holdings_row_label),
        "--as-of-date",
        str(args.as_of_date),
        "--extra-cash",
        f"{float(args.extra_cash):.6f}",
        "--action-threshold",
        f"{float(args.action_threshold):.6f}",
        "--max-stale-days",
        str(int(args.max_stale_days)),
        "--max-strategy-drawdown",
        f"{float(args.max_strategy_drawdown):.6f}",
        "--max-underperformance-vs-0050",
        f"{float(args.max_underperformance_vs_0050):.6f}",
    ]
    if not args.strategy_replay:
        cmd.append("--live-start")
    if args.xlsx:
        cmd.extend(["--xlsx", str(args.xlsx)])
    if args.simulation_start:
        cmd.extend(["--simulation-start", str(args.simulation_start)])
    if args.history_start:
        cmd.extend(["--history-start", str(args.history_start)])
    if args.download_end:
        cmd.extend(["--download-end", str(args.download_end)])
    if args.override_holdings_json:
        cmd.extend(["--override-holdings-json", str(args.override_holdings_json)])

    completed = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return _extract_output_path(completed.stdout, "JSON")


def _build_tdcc_assessment(
    config: dict[str, object],
    *,
    db_path: Path,
    as_of_date: str,
) -> dict[str, object]:
    lag_days = int(config["availability_lag_days"])
    cutoff = date.fromisoformat(as_of_date) - timedelta(days=lag_days)
    snapshots = {
        str(ticker): _ticker_snapshot(
            _load_weekly_features(db_path, str(ticker), str(cutoff)),
            int(config["lookback_weeks"]),
        )
        for ticker in config["tickers"]
    }
    assessment = assess_shadow_signal(config, snapshots)
    return {
        **assessment,
        "requested_as_of_date": as_of_date,
        "availability_cutoff_date": str(cutoff),
        "availability_lag_days": lag_days,
        "snapshots": snapshots,
    }


def apply_tdcc_overlay(
    base_signal: dict[str, object],
    assessment: dict[str, object],
    config: dict[str, object],
) -> dict[str, object]:
    """Cap crowded leverage exposure and reallocate released budget by config."""
    base_weights = {
        str(ticker): float(weight)
        for ticker, weight in dict(base_signal["target_weights"]).items()
    }
    base_cash_weight = float(base_signal["target_cash_weight"])
    target_weights = dict(base_weights)
    target_cash_weight = base_cash_weight
    state = str(assessment["state"])
    leverage_ticker = f"{config['leverage_ticker']}.TW"
    primary_ticker = f"{config.get('primary_ticker', '0050')}.TW"
    inverse_ticker = f"{config.get('inverse_ticker', '00632R')}.TW"
    cap = None
    released_budget = 0.0
    if state in {"caution", "risk_off"}:
        cap = float(dict(config[state])["leverage_weight_cap"])
        prior_weight = float(target_weights.get(leverage_ticker, 0.0))
        target_weights[leverage_ticker] = min(prior_weight, cap)
        released_budget = prior_weight - target_weights[leverage_ticker]

        destination = str(config.get("released_leverage_budget_destination", "cash"))
        primary_fraction = float(config.get("released_to_primary_fraction", 0.5))
        primary_fraction = max(0.0, min(primary_fraction, 1.0))
        if destination == "primary":
            target_weights[primary_ticker] = target_weights.get(primary_ticker, 0.0) + released_budget
        elif destination == "split_primary_cash":
            target_weights[primary_ticker] = target_weights.get(primary_ticker, 0.0) + released_budget * primary_fraction
            target_cash_weight += released_budget * (1.0 - primary_fraction)
        else:
            target_cash_weight += released_budget

    inverse_cfg = dict(config.get("inverse_hedge_on_tdcc_risk_off", {}))
    inverse_added = 0.0
    if state == "risk_off" and inverse_cfg.get("enabled", False):
        inverse_weight = float(inverse_cfg.get("weight", 0.0))
        require_local_risk = bool(inverse_cfg.get("require_base_local_risk_off", True))
        decision = dict(base_signal.get("decision", {}))
        local_state = str(decision.get("local_regime_state", "")).lower()
        local_ok = (not require_local_risk) or local_state in {"risk_off", "severe"}
        if inverse_weight > 0.0 and local_ok:
            available_cash = max(target_cash_weight, 0.0)
            inverse_added = min(inverse_weight, available_cash)
            target_weights[inverse_ticker] = target_weights.get(inverse_ticker, 0.0) + inverse_added
            target_cash_weight -= inverse_added

    changed = any(
        abs(target_weights[ticker] - base_weights[ticker]) > 1e-12
        for ticker in base_weights
    ) or abs(target_cash_weight - base_cash_weight) > 1e-12
    signal_status = str(base_signal["signal_status"])
    signal_reason = str(base_signal["signal_reason"])
    if changed:
        signal_status = "rebalance"
        signal_reason = f"tdcc_shareholding_{state}"

    return {
        "state": state,
        "changed": changed,
        "leverage_weight_cap": cap,
        "released_leverage_budget": released_budget,
        "released_leverage_budget_destination": config.get("released_leverage_budget_destination", "cash"),
        "inverse_added_weight": inverse_added,
        "signal_status": signal_status,
        "signal_reason": signal_reason,
        "base_target_weights": base_weights,
        "base_target_cash_weight": base_cash_weight,
        "target_weights": target_weights,
        "target_cash_weight": target_cash_weight,
    }


def _load_inverse_hold_overlay_config(raw_path: str | None) -> dict[str, object] | None:
    if raw_path is None or str(raw_path).strip() == "":
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Inverse hold overlay config not found: {path}")
    config = json.loads(path.read_text(encoding="utf-8"))
    if str(config.get("overlay_type", "")) != "post_target_inverse_hold_limit":
        raise ValueError(f"Unsupported inverse hold overlay type: {config.get('overlay_type')}")
    return config


def _load_conditional_inverse_overlay_config(raw_path: str | None) -> dict[str, object] | None:
    if raw_path is None or str(raw_path).strip() == "":
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Conditional inverse overlay config not found: {path}")
    config = json.loads(path.read_text(encoding="utf-8"))
    if str(config.get("overlay_type", "")) != "conditional_inverse_cap":
        raise ValueError(f"Unsupported conditional inverse overlay type: {config.get('overlay_type')}")
    return config


def _load_close_series(db_path: Path, ticker: str, end_date: str, *, lookback_rows: int = 90) -> pd.Series:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, close
            FROM ohlcv
            WHERE ticker = ? AND dt <= ?
            ORDER BY dt DESC
            LIMIT ?
            """,
            [ticker, end_date, int(lookback_rows)],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        raise RuntimeError(f"No close data found for {ticker} through {end_date}")
    rows["dt"] = pd.to_datetime(rows["dt"])
    rows = rows.sort_values("dt")
    return pd.Series(rows["close"].astype(float).to_numpy(), index=rows["dt"], name=ticker)


def _conditional_inverse_stress_assessment(
    base_signal: dict[str, object],
    config: dict[str, object],
    *,
    db_path: Path,
) -> dict[str, object]:
    actual_data_date = str(base_signal["actual_data_date"])
    primary_ticker = str(config.get("primary_ticker", "0050.TW"))
    lag_days = int(config.get("signal_lag_trading_days", 1))
    ma_window = int(config.get("ma_window", 60))
    momentum_window = int(config.get("momentum_window", 21))
    drawdown_threshold = float(config.get("group_drawdown_threshold", -0.10))
    close = _load_close_series(
        db_path,
        primary_ticker,
        actual_data_date,
        lookback_rows=max(ma_window + momentum_window + lag_days + 10, 100),
    )
    eval_idx = len(close) - 1 - max(lag_days, 0)
    if eval_idx < max(ma_window - 1, momentum_window):
        raise RuntimeError(
            f"Not enough {primary_ticker} history for conditional inverse overlay through {actual_data_date}"
        )
    eval_date = pd.Timestamp(close.index[eval_idx]).date()
    eval_close = float(close.iloc[eval_idx])
    ma = float(close.iloc[eval_idx - ma_window + 1 : eval_idx + 1].mean())
    momentum = float(close.iloc[eval_idx] / close.iloc[eval_idx - momentum_window] - 1.0)
    below_ma = bool(eval_close < ma)
    negative_momentum = bool(momentum < 0.0)
    group_drawdown = float(base_signal.get("strategy_drawdown", 0.0))
    group_drawdown_trigger = bool(group_drawdown <= drawdown_threshold)
    condition = str(config.get("condition", "stress_any"))
    if condition == "stress_any":
        active = below_ma or negative_momentum or group_drawdown_trigger
    elif condition == "stress_strict":
        active = below_ma and (negative_momentum or group_drawdown_trigger)
    elif condition == "stress_price_only":
        active = below_ma or negative_momentum
    elif condition == "below_ma60":
        active = below_ma
    elif condition == "negative_mom21":
        active = negative_momentum
    elif condition == "group_dd10":
        active = group_drawdown_trigger
    else:
        raise ValueError(f"Unsupported conditional inverse stress condition: {condition}")
    return {
        "condition": condition,
        "active": active,
        "actual_data_date": actual_data_date,
        "evaluation_date": str(eval_date),
        "signal_lag_trading_days": lag_days,
        "primary_ticker": primary_ticker,
        "primary_close": eval_close,
        "primary_ma": ma,
        "ma_window": ma_window,
        "primary_momentum": momentum,
        "momentum_window": momentum_window,
        "below_ma": below_ma,
        "negative_momentum": negative_momentum,
        "group_drawdown": group_drawdown,
        "group_drawdown_threshold": drawdown_threshold,
        "group_drawdown_trigger": group_drawdown_trigger,
    }


def apply_conditional_inverse_overlay(
    overlay: dict[str, object],
    base_signal: dict[str, object],
    cap_config: dict[str, object] | None,
    *,
    db_path: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    if cap_config is None:
        return overlay, {"enabled": False}

    ticker = str(cap_config.get("ticker", "00632R.TW"))
    release_to = str(cap_config.get("release_to", "0050.TW"))
    cap = float(cap_config.get("cap", 0.10))
    target_weights = {
        str(key): float(value)
        for key, value in dict(overlay["target_weights"]).items()
    }
    prior_weight = float(target_weights.get(ticker, 0.0))
    assessment = _conditional_inverse_stress_assessment(base_signal, cap_config, db_path=db_path)
    allowed_cap = cap if bool(assessment["active"]) else 0.0
    capped_weight = min(prior_weight, allowed_cap)
    released_weight = prior_weight - capped_weight
    changed = released_weight > 1e-12
    if changed:
        target_weights[ticker] = capped_weight
        target_weights[release_to] = float(target_weights.get(release_to, 0.0)) + released_weight
        overlay["target_weights"] = target_weights
        overlay["changed"] = True
        overlay["signal_status"] = "rebalance"
        overlay["signal_reason"] = (
            f"{overlay['signal_reason']}; conditional_inverse_cap_{ticker}_{cap:.2f}"
        )
    details = {
        "enabled": True,
        "config": cap_config,
        "ticker": ticker,
        "release_to": release_to,
        "cap": cap,
        "stress_active": bool(assessment["active"]),
        "allowed_cap": allowed_cap,
        "prior_weight": prior_weight,
        "target_weight_after": float(target_weights.get(ticker, 0.0)),
        "released_weight": released_weight,
        "changed": changed,
        "assessment": assessment,
    }
    overlay["conditional_inverse_overlay"] = details
    return overlay, details


def apply_inverse_hold_overlay(
    overlay: dict[str, object],
    base_signal: dict[str, object],
    hold_config: dict[str, object] | None,
    *,
    state_path: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    if hold_config is None:
        return overlay, {"enabled": False}

    ticker = str(hold_config.get("ticker", "00632R.TW"))
    release_to = str(hold_config.get("release_to", "0050.TW"))
    max_days = int(hold_config.get("max_holding_calendar_days", 10))
    as_of = pd.Timestamp(base_signal["actual_data_date"]).normalize()
    target_weights = {
        str(key): float(value)
        for key, value in dict(overlay["target_weights"]).items()
    }
    base_target_weights = {
        str(key): float(value)
        for key, value in dict(overlay["base_target_weights"]).items()
    }
    current_shares = {
        str(key): int(value)
        for key, value in dict(base_signal.get("current_shares", {})).items()
    }
    target_inverse = float(target_weights.get(ticker, 0.0))
    current_inverse_active = int(current_shares.get(ticker, 0)) > 0
    state: dict[str, object] = {}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))

    previous_seen_raw = state.get("last_seen_date")
    previous_seen = date.fromisoformat(str(previous_seen_raw)) if previous_seen_raw else None
    date_regression_blocked = bool(previous_seen and as_of.date() < previous_seen)
    if date_regression_blocked:
        details = {
            "enabled": True,
            "config": hold_config,
            "state_json": str(state_path.resolve()),
            "state_before": state,
            "state_after": state,
            "ticker": ticker,
            "release_to": release_to,
            "max_holding_calendar_days": max_days,
            "holding_start_date": state.get("holding_start_date"),
            "holding_days": 0,
            "days_remaining": None,
            "capped": False,
            "released_weight": 0.0,
            "base_target_weight": float(base_target_weights.get(ticker, 0.0)),
            "target_weight_after": float(target_weights.get(ticker, 0.0)),
            "date_regression_blocked": True,
            "block_reason": (
                f"actual_data_date {as_of.date()} is older than state last_seen_date {previous_seen}"
            ),
        }
        overlay["inverse_hold_overlay"] = details
        return overlay, details

    previous_active = bool(state.get("active", False))
    previous_start = state.get("holding_start_date")
    holding_start = str(previous_start) if previous_active and previous_start else None
    if target_inverse > 1e-12 and holding_start is None:
        holding_start = str(as_of.date())
    elif target_inverse <= 1e-12 and current_inverse_active and holding_start is None:
        holding_start = str(as_of.date())

    holding_days = 0
    capped = False
    released_weight = 0.0
    if target_inverse > 1e-12 and holding_start:
        holding_days = max((as_of.date() - date.fromisoformat(holding_start)).days, 0)
        if holding_days > max_days:
            capped = True
            released_weight = target_inverse
            target_weights[ticker] = 0.0
            target_weights[release_to] = float(target_weights.get(release_to, 0.0)) + released_weight
            overlay["target_weights"] = target_weights
            overlay["changed"] = True
            overlay["signal_status"] = "rebalance"
            overlay["signal_reason"] = f"{overlay['signal_reason']}; inverse_hold_limit_{ticker}_{max_days}d"

    days_remaining = max(max_days - holding_days, 0) if holding_start else None
    next_active = bool(target_weights.get(ticker, 0.0) > 1e-12 or current_inverse_active)
    next_state = {
        "active": next_active,
        "ticker": ticker,
        "holding_start_date": holding_start if next_active else None,
        "last_seen_date": str(as_of.date()),
        "last_target_weight": float(target_weights.get(ticker, 0.0)),
        "last_current_shares": int(current_shares.get(ticker, 0)),
        "max_holding_calendar_days": max_days,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(next_state, ensure_ascii=False, indent=2), encoding="utf-8")
    details = {
        "enabled": True,
        "config": hold_config,
        "state_json": str(state_path.resolve()),
        "state_before": state,
        "state_after": next_state,
        "ticker": ticker,
        "release_to": release_to,
        "max_holding_calendar_days": max_days,
        "holding_start_date": holding_start,
        "holding_days": holding_days,
        "days_remaining": days_remaining,
        "capped": capped,
        "released_weight": released_weight,
        "base_target_weight": float(base_target_weights.get(ticker, 0.0)),
        "target_weight_after": float(target_weights.get(ticker, 0.0)),
        "date_regression_blocked": False,
    }
    overlay["inverse_hold_overlay"] = details
    return overlay, details


def _action_hint(delta_shares: int, signal_status: str) -> str:
    if signal_status != "rebalance" or delta_shares == 0:
        return "hold"
    return "buy" if delta_shares > 0 else "sell"


def _estimate_trade_cost(delta_shares: int, price: float) -> dict[str, float]:
    buy_notional = max(delta_shares, 0) * price
    sell_notional = max(-delta_shares, 0) * price
    trade_notional = buy_notional + sell_notional
    commission = trade_notional * DEFAULT_COMMISSION_RATE
    sell_tax = sell_notional * DEFAULT_ETF_SELL_TAX_RATE
    slippage = trade_notional * DEFAULT_SLIPPAGE_RATE
    return {
        "buy_notional": float(buy_notional),
        "sell_notional": float(sell_notional),
        "trade_notional": float(trade_notional),
        "commission_estimate": float(commission),
        "sell_tax_estimate": float(sell_tax),
        "slippage_estimate": float(slippage),
        "total_cost_estimate": float(commission + sell_tax + slippage),
    }


def _write_improved_signal(
    base_signal_path: Path,
    base_signal: dict[str, object],
    assessment: dict[str, object],
    overlay: dict[str, object],
    config: dict[str, object],
) -> tuple[Path, Path, dict[str, object]]:
    prices = {str(k): float(v) for k, v in dict(base_signal["latest_prices"]).items()}
    current_shares = {str(k): int(v) for k, v in dict(base_signal["current_shares"]).items()}
    total_value = float(base_signal["current_total_portfolio_value"])
    target_weights = {str(k): float(v) for k, v in dict(overlay["target_weights"]).items()}
    base_weights = {str(k): float(v) for k, v in dict(overlay["base_target_weights"]).items()}
    target_shares: dict[str, int] = {}
    rows = []
    trade_log = []
    for ticker, target_weight in target_weights.items():
        shares = int(round(total_value * target_weight / prices[ticker])) if prices[ticker] > 0 else 0
        delta_shares = shares - current_shares.get(ticker, 0)
        action_hint = _action_hint(delta_shares, str(overlay["signal_status"]))
        costs = _estimate_trade_cost(delta_shares, prices[ticker])
        target_shares[ticker] = shares
        row = {
            "date": base_signal["actual_data_date"],
            "ticker": ticker,
            "latest_price": prices[ticker],
            "current_shares": current_shares.get(ticker, 0),
            "base_target_weight": base_weights.get(ticker, 0.0),
            "tdcc_target_weight": target_weight,
            "target_shares": shares,
            "delta_shares": delta_shares,
            "action_hint": action_hint,
            "signal_status": overlay["signal_status"],
            "signal_reason": overlay["signal_reason"],
            "tdcc_state": overlay["state"],
            **costs,
        }
        rows.append(row)
        if action_hint in {"buy", "sell"}:
            trade_log.append(row)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = DEFAULT_OUTPUT_DIR / f"group_a_tdcc_improved_signal_{stamp}"
    csv_path = prefix.with_suffix(".csv")
    json_path = prefix.with_suffix(".json")
    trade_log_path = prefix.with_name(prefix.name + "_trade_log.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(trade_log).to_csv(trade_log_path, index=False, encoding="utf-8-sig")
    execution_cost_summary = {
        "commission_estimate": float(sum(row["commission_estimate"] for row in rows)),
        "sell_tax_estimate": float(sum(row["sell_tax_estimate"] for row in rows)),
        "slippage_estimate": float(sum(row["slippage_estimate"] for row in rows)),
        "total_cost_estimate": float(sum(row["total_cost_estimate"] for row in rows)),
        "gross_trade_notional": float(sum(row["trade_notional"] for row in rows)),
        "buy_notional": float(sum(row["buy_notional"] for row in rows)),
        "sell_notional": float(sum(row["sell_notional"] for row in rows)),
        "trade_count": int(len(trade_log)),
        "cost_model": {
            "commission_rate": DEFAULT_COMMISSION_RATE,
            "etf_sell_tax_rate": DEFAULT_ETF_SELL_TAX_RATE,
            "slippage_rate": DEFAULT_SLIPPAGE_RATE,
        },
    }
    summary = {
        "strategy_name": config["strategy_name"],
        "strategy_status": config["status"],
        "base_strategy": config["base_strategy"],
        "base_signal_json": str(base_signal_path.resolve()),
        "requested_as_of_date": base_signal["requested_as_of_date"],
        "actual_data_date": base_signal["actual_data_date"],
        "signal_status": overlay["signal_status"],
        "signal_reason": overlay["signal_reason"],
        "latest_prices": prices,
        "current_shares": current_shares,
        "current_total_portfolio_value": total_value,
        "base_target_weights": base_weights,
        "base_target_cash_weight": overlay["base_target_cash_weight"],
        "target_weights": target_weights,
        "target_cash_weight": overlay["target_cash_weight"],
        "target_shares": target_shares,
        "execution_cost_summary": execution_cost_summary,
        "trade_log_csv": str(trade_log_path.resolve()),
        "trade_log": trade_log,
        "tdcc_overlay": overlay,
        "tdcc_assessment": assessment,
        "config": config,
        "output_csv": str(csv_path.resolve()),
    }
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(json_path, LATEST_JSON)
    shutil.copy2(csv_path, LATEST_CSV)
    return json_path, csv_path, summary


def main() -> None:
    args = _parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    base_signal_path = (
        Path(args.base_signal_json).resolve()
        if args.base_signal_json
        else _generate_base_signal(args).resolve()
    )
    base_signal = json.loads(base_signal_path.read_text(encoding="utf-8"))
    assessment = _build_tdcc_assessment(
        config,
        db_path=PROJECT_ROOT / "FinRL" / "data" / "stock_data.db",
        as_of_date=str(args.as_of_date),
    )
    overlay = apply_tdcc_overlay(base_signal, assessment, config)
    conditional_config = _load_conditional_inverse_overlay_config(args.conditional_inverse_overlay_config)
    overlay, conditional_inverse_overlay = apply_conditional_inverse_overlay(
        overlay,
        base_signal,
        conditional_config,
        db_path=PROJECT_ROOT / "FinRL" / "data" / "stock_data.db",
    )
    hold_config = _load_inverse_hold_overlay_config(args.inverse_hold_overlay_config)
    state_path = Path(args.inverse_hold_state_json)
    if not state_path.is_absolute():
        state_path = (PROJECT_ROOT / state_path).resolve()
    overlay, inverse_hold_overlay = apply_inverse_hold_overlay(
        overlay,
        base_signal,
        hold_config,
        state_path=state_path,
    )
    json_path, csv_path, summary = _write_improved_signal(
        base_signal_path,
        base_signal,
        assessment,
        overlay,
        config,
    )
    manifest = {
        "strategy_name": config["strategy_name"],
        "strategy_status": config["status"],
        "base_strategy": config["base_strategy"],
        "stable_signal_json": str(LATEST_JSON.resolve()),
        "stable_signal_csv": str(LATEST_CSV.resolve()),
        "generated_signal_json": str(json_path.resolve()),
        "generated_signal_csv": str(csv_path.resolve()),
        "generated_trade_log_csv": summary["trade_log_csv"],
        "actual_data_date": summary["actual_data_date"],
        "signal_status": summary["signal_status"],
        "signal_reason": summary["signal_reason"],
        "tdcc_state": assessment["state"],
        "conditional_inverse_overlay": conditional_inverse_overlay,
        "inverse_hold_overlay": inverse_hold_overlay,
        "execution_cost_summary": summary["execution_cost_summary"],
        "target_shares": summary["target_shares"],
    }
    LATEST_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 72)
    print(f"Strategy:      {config['strategy_name']} ({config['status']})")
    print(f"TDCC state:    {assessment['state']}")
    if conditional_inverse_overlay.get("enabled"):
        print(
            "00632R cap:    "
            f"stress={conditional_inverse_overlay.get('stress_active')} "
            f"prior={float(conditional_inverse_overlay.get('prior_weight', 0.0)):.2%} "
            f"after={float(conditional_inverse_overlay.get('target_weight_after', 0.0)):.2%}"
        )
    if inverse_hold_overlay.get("enabled"):
        print(
            "00632R hold:   "
            f"{inverse_hold_overlay.get('holding_days', 0)}d/"
            f"{inverse_hold_overlay.get('max_holding_calendar_days')}d "
            f"capped={inverse_hold_overlay.get('capped')}"
        )
    print(f"Signal status: {summary['signal_status']}")
    print(f"Reason:        {summary['signal_reason']}")
    print(f"JSON:          {json_path}")
    print(f"CSV:           {csv_path}")
    print(f"Stable JSON:   {LATEST_JSON}")
    print(f"Manifest:      {LATEST_MANIFEST}")
    print("=" * 72)


if __name__ == "__main__":
    main()
