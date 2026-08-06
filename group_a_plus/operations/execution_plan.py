"""Build a guarded A21.3 trade plan from the Group A++ workbook holdings."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from backtest_group_a_plus_policy_signal import TICKERS
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY
from group_a_plus.core.point_in_time_store import write_json_artifact_snapshot
from group_a_plus.operations.daily_signal import build_daily_signal
from group_a_plus.operations.execution_guard import (
    apply_compounding_regime_pre_trade_guard,
    apply_risk_add_pre_trade_guard,
    apply_volatility_gate_pre_trade_guard,
)
from group_a_plus.paths import PROJECT_ROOT
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_WORKBOOK = PROJECT_ROOT / "taiwan_stock_20260619.xlsx"
DEFAULT_EXECUTION_PLAN = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"
BOND_ETFS = {"00679B.TWO", "00751B.TWO"}
GROUP_A_PLUS_TICKERS = set(TICKERS)
PORTFOLIO_VALUE_ABS_TOLERANCE = 100.0
PORTFOLIO_VALUE_REL_TOLERANCE = 0.005


def _execution_plan_pit_asof(payload: dict[str, Any], fallback_as_of: str) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return str(data.get("actual_data_date") or data.get("requested_as_of_date") or fallback_as_of)


def _execution_plan_pit_generated_at(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return str(data.get("generated_at") or metadata.get("timestamp") or datetime.now().isoformat(timespec="seconds"))


def _write_execution_plan_pit_snapshot(payload: dict[str, Any], *, requested_as_of: str) -> Path:
    return write_json_artifact_snapshot(
        "execution_plan",
        payload,
        artifact_asof=_execution_plan_pit_asof(payload, requested_as_of),
        generated_at=_execution_plan_pit_generated_at(payload),
    )


def _extract_code(value: object) -> str | None:
    text = "" if pd.isna(value) else str(value).upper()
    matches = re.findall(r"\b\d{4,5}[A-Z]?\b", text)
    return matches[-1] if matches else None


def _normalize_ticker(code: str) -> str:
    return f"{code}.TWO" if code in {"00679B", "00751B"} else f"{code}.TW"


def _parse_group_a_plus_holdings(frame: pd.DataFrame, row_label: str = "即時庫存") -> dict[str, int]:
    group_row = group_start = None
    for row_idx in range(len(frame)):
        for col_idx in range(frame.shape[1]):
            if str(frame.iloc[row_idx, col_idx]).strip() in {"Group A++", "Group A+"}:
                group_row, group_start = row_idx, col_idx
                break
        if group_start is not None:
            break
    if group_row is None or group_start is None:
        raise ValueError("Workbook has no Group A++ section")
    group_end = frame.shape[1]
    for col_idx in range(group_start + 1, frame.shape[1]):
        value = str(frame.iloc[group_row, col_idx]).strip()
        if value.startswith("Group "):
            group_end = col_idx
            break
    holdings_row = None
    for row_idx in range(len(frame)):
        if any(str(value).strip() == row_label for value in frame.iloc[row_idx].tolist()):
            holdings_row = row_idx
            break
    if holdings_row is None:
        raise ValueError(f"Workbook row not found: {row_label}")
    header_row = group_row + 1
    holdings: dict[str, int] = {}
    for col_idx in range(group_start, group_end):
        code = _extract_code(frame.iloc[header_row, col_idx])
        if code is None:
            continue
        ticker = _normalize_ticker(code)
        if ticker not in GROUP_A_PLUS_TICKERS:
            continue
        value = frame.iloc[holdings_row, col_idx]
        holdings[ticker] = 0 if pd.isna(value) else int(round(float(value)))
    if not holdings:
        raise ValueError("No Group A++ holdings parsed from workbook")
    return holdings


def load_group_a_plus_holdings(path: Path, row_label: str = "即時庫存") -> dict[str, int]:
    return _parse_group_a_plus_holdings(pd.read_excel(path, sheet_name=0, header=None), row_label)


def load_group_a_plus_holdings_json(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_holdings = payload.get("holdings") if isinstance(payload, dict) else None
    if not isinstance(raw_holdings, dict):
        raise ValueError("Holdings JSON must contain a holdings object")
    holdings: dict[str, int] = {}
    for ticker, shares in raw_holdings.items():
        normalized = str(ticker).upper().strip()
        if normalized not in GROUP_A_PLUS_TICKERS:
            continue
        holdings[normalized] = int(round(float(shares)))
    if not holdings:
        raise ValueError("No Group A++ holdings parsed from holdings JSON")
    return holdings


def _latest_prices(db_path: Path, tickers: list[str], as_of: str) -> dict[str, float]:
    if not tickers:
        return {}
    placeholders = ", ".join(["?"] * len(tickers))
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT ticker, arg_max(close, dt) AS latest_close
            FROM ohlcv
            WHERE ticker IN ({placeholders}) AND dt <= ?
            GROUP BY ticker
            """,
            [*tickers, as_of],
        ).fetchdf()
    finally:
        con.close()
    return {
        str(row.ticker): float(row.latest_close)
        for row in rows.itertuples(index=False)
        if pd.notna(row.latest_close)
    }


def _latest_compounding_regime_path() -> Path | None:
    candidates = [
        path
        for path in (PROJECT_ROOT / "results").glob("00631l_leveraged_compounding_regime_*.json")
        if path.is_file()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def _load_compounding_regime(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    candidate = _latest_compounding_regime_path() if str(path) == "latest" else path
    if candidate is None:
        return None
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    if not candidate.exists():
        return None
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    payload["_source_path"] = str(candidate)
    return payload


def _compounding_regime_date(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    latest = payload.get("latest") if isinstance(payload.get("latest"), dict) else payload
    date = latest.get("date")
    return str(date) if date else None


def _portfolio_value_mismatch_reason(signal: dict[str, Any], total_assets: float) -> str | None:
    value = signal.get("portfolio_value_input")
    if value is None:
        return None
    signal_value = float(value)
    tolerance = max(PORTFOLIO_VALUE_ABS_TOLERANCE, abs(total_assets) * PORTFOLIO_VALUE_REL_TOLERANCE)
    diff = abs(signal_value - total_assets)
    if diff <= tolerance:
        return None
    return (
        "portfolio snapshot mismatch: workbook/cash total_assets="
        f"{total_assets:.2f}, live_signal portfolio_value_input={signal_value:.2f}, diff={diff:.2f}"
    )


def _build_trades(
    current_shares: dict[str, int],
    target_shares: dict[str, int],
    prices: dict[str, float],
    commission_rate: float,
    slippage_rate: float,
    equity_etf_sell_tax: float,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    trades: list[dict[str, Any]] = []
    totals = {"buy_notional": 0.0, "sell_notional": 0.0, "commission": 0.0, "sell_tax": 0.0, "slippage": 0.0}
    for ticker in sorted(set(current_shares) | set(target_shares)):
        current = int(current_shares.get(ticker, 0))
        target = int(target_shares.get(ticker, 0))
        delta = target - current
        if delta == 0:
            continue
        price = float(prices[ticker])
        notional = abs(delta) * price
        side = "buy" if delta > 0 else "sell"
        commission = notional * commission_rate
        slippage = notional * slippage_rate
        sell_tax_rate = 0.0 if ticker in BOND_ETFS else equity_etf_sell_tax
        sell_tax = notional * sell_tax_rate if side == "sell" else 0.0
        totals[f"{side}_notional"] += notional
        totals["commission"] += commission
        totals["slippage"] += slippage
        totals["sell_tax"] += sell_tax
        trades.append(
            {
                "ticker": ticker,
                "side": side,
                "current_shares": current,
                "target_shares": target,
                "delta_shares": delta,
                "price": price,
                "notional": notional,
                "commission": commission,
                "slippage": slippage,
                "sell_tax_rate": sell_tax_rate,
                "sell_tax": sell_tax,
                "estimated_cost": commission + slippage + sell_tax,
            }
        )
    totals["total_execution_cost"] = totals["commission"] + totals["slippage"] + totals["sell_tax"]
    totals["turnover_notional"] = totals["buy_notional"] + totals["sell_notional"]
    trades.sort(key=lambda row: (0 if row["side"] == "sell" else 1, row["ticker"]))
    return trades, totals


def _apply_execution_controls(
    current_shares: dict[str, int],
    theoretical_target_shares: dict[str, int],
    prices: dict[str, float],
    total_assets: float,
    min_trade_notional: float,
    min_weight_deviation: float,
    share_lot_size: int,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    if share_lot_size < 1:
        raise ValueError("share_lot_size must be at least 1")
    targets: dict[str, int] = {}
    suppressed: list[dict[str, Any]] = []
    for ticker in sorted(set(current_shares) | set(theoretical_target_shares)):
        current = int(current_shares.get(ticker, 0))
        theoretical = int(theoretical_target_shares.get(ticker, 0))
        controlled = theoretical if theoretical == 0 else (theoretical // share_lot_size) * share_lot_size
        price = float(prices.get(ticker, 0.0))
        delta_notional = abs(controlled - current) * price
        weight_deviation = delta_notional / total_assets if total_assets > 0 else 0.0
        if controlled == current:
            targets[ticker] = current
            continue
        liquidation = theoretical == 0 and current != 0
        reasons = []
        if controlled != theoretical:
            reasons.append(f"rounded_to_{share_lot_size}_share_lot")
        if not liquidation and delta_notional < min_trade_notional:
            reasons.append("below_min_trade_notional")
        if not liquidation and weight_deviation < min_weight_deviation:
            reasons.append("inside_weight_deviation_band")
        if reasons and ("below_min_trade_notional" in reasons or "inside_weight_deviation_band" in reasons):
            targets[ticker] = current
            suppressed.append(
                {
                    "ticker": ticker,
                    "current_shares": current,
                    "theoretical_target_shares": theoretical,
                    "controlled_target_before_band": controlled,
                    "delta_notional": delta_notional,
                    "weight_deviation": weight_deviation,
                    "reasons": reasons,
                }
            )
        else:
            targets[ticker] = controlled
    return targets, suppressed


def _apply_buy_staging(
    current_shares: dict[str, int],
    target_shares: dict[str, int],
    prices: dict[str, float],
    max_initial_buy_fraction: float,
    min_staged_buy_notional: float,
    share_lot_size: int,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    if share_lot_size < 1:
        raise ValueError("share_lot_size must be at least 1")
    if not 0.0 < max_initial_buy_fraction <= 1.0:
        raise ValueError("max_initial_buy_fraction must be in (0, 1]")
    if max_initial_buy_fraction >= 1.0:
        return dict(target_shares), []

    staged_targets = dict(target_shares)
    staged: list[dict[str, Any]] = []
    for ticker in sorted(set(current_shares) | set(target_shares)):
        current = int(current_shares.get(ticker, 0))
        target = int(target_shares.get(ticker, current))
        delta = target - current
        if delta <= 0:
            continue
        price = float(prices.get(ticker, 0.0))
        buy_notional = delta * price
        if buy_notional < min_staged_buy_notional:
            continue

        staged_delta = int(delta * max_initial_buy_fraction)
        staged_delta = max(share_lot_size, (staged_delta // share_lot_size) * share_lot_size)
        staged_delta = min(delta, staged_delta)
        staged_target = current + staged_delta
        if staged_target >= target:
            continue

        staged_targets[ticker] = staged_target
        staged.append(
            {
                "ticker": ticker,
                "current_shares": current,
                "full_target_shares": target,
                "staged_target_shares": staged_target,
                "full_delta_shares": delta,
                "staged_delta_shares": staged_delta,
                "deferred_delta_shares": target - staged_target,
                "price": price,
                "full_buy_notional": buy_notional,
                "staged_buy_notional": staged_delta * price,
                "deferred_buy_notional": (target - staged_target) * price,
                "max_initial_buy_fraction": max_initial_buy_fraction,
                "reason": "large_buy_staged",
            }
        )
    return staged_targets, staged


def _combine_guarded_targets(
    base_targets: dict[str, int],
    guarded_target_sets: list[dict[str, int]],
) -> dict[str, int]:
    """Combine independently evaluated no-add guards into one target map.

    Guard functions are evaluated against the same staged target so their
    diagnostics remain visible even when another guard would already block the
    same buy. Share targets are long-only, so the most conservative executable
    result is the minimum target proposed by any guard for each ticker.
    """

    combined = dict(base_targets)
    for ticker in sorted(set(base_targets) | set().union(*(set(targets) for targets in guarded_target_sets))):
        candidates = [int(base_targets.get(ticker, 0))]
        candidates.extend(int(targets.get(ticker, base_targets.get(ticker, 0))) for targets in guarded_target_sets)
        combined[ticker] = min(candidates)
    return combined


def _build_guard_impact_summary(
    current_shares: dict[str, int],
    staged_target_shares: dict[str, int],
    final_target_shares: dict[str, int],
    prices: dict[str, float],
    guards: list[dict[str, Any]],
) -> dict[str, Any]:
    by_guard: list[dict[str, Any]] = []
    for guard in guards:
        blocked = [trade for trade in guard.get("blocked_trades", []) or [] if isinstance(trade, dict)]
        blocked_notional = 0.0
        for trade in blocked:
            ticker = str(trade.get("ticker") or "")
            blocked_notional += abs(int(trade.get("blocked_delta_shares", 0) or 0)) * float(prices.get(ticker, 0.0))
        by_guard.append(
            {
                "name": guard.get("name"),
                "status": guard.get("status"),
                "allow_00631l_add": guard.get("allow_00631l_add"),
                "blocked_trade_count": len(blocked),
                "blocked_buy_notional": blocked_notional,
                "blocked_trades": blocked,
            }
        )

    combined_blocked_buys: list[dict[str, Any]] = []
    for ticker in sorted(set(current_shares) | set(staged_target_shares) | set(final_target_shares)):
        current = int(current_shares.get(ticker, 0) or 0)
        staged = int(staged_target_shares.get(ticker, current) or 0)
        final = int(final_target_shares.get(ticker, current) or 0)
        if staged <= current or final >= staged:
            continue
        blocked_shares = staged - final
        price = float(prices.get(ticker, 0.0))
        combined_blocked_buys.append(
            {
                "ticker": ticker,
                "current_shares": current,
                "staged_target_shares": staged,
                "final_target_shares": final,
                "blocked_delta_shares": blocked_shares,
                "blocked_notional": blocked_shares * price,
                "price": price,
            }
        )

    active_guards = [
        str(item.get("name"))
        for item in by_guard
        if item.get("status") not in {None, "inactive", "unavailable"}
    ]
    return {
        "active_guard_names": active_guards,
        "blocked_guard_names": [str(item.get("name")) for item in by_guard if item.get("status") == "blocked"],
        "by_guard": by_guard,
        "combined_blocked_buys": combined_blocked_buys,
        "combined_blocked_buy_notional": sum(item["blocked_notional"] for item in combined_blocked_buys),
        "combined_blocked_trade_count": len(combined_blocked_buys),
    }


def _trough_nowcast_buy_fraction(signal: dict[str, Any], default_fraction: float) -> tuple[float, dict[str, Any]]:
    trough = signal.get("trough_nowcast") or {}
    if not isinstance(trough, dict):
        return default_fraction, {
            "state": "NO_TROUGH",
            "default_max_initial_buy_fraction": default_fraction,
            "effective_max_initial_buy_fraction": default_fraction,
            "applied": False,
        }
    state = str(trough.get("state") or "NO_TROUGH")
    recommended = trough.get("recommended_execution_staging_fraction")
    effective = default_fraction
    applied = False
    if state in {"PARTIAL_REENTRY", "FULL_REENTRY"} and recommended is not None:
        effective = max(default_fraction, min(float(recommended), 1.0))
        applied = effective != default_fraction
    return effective, {
        "state": state,
        "default_max_initial_buy_fraction": default_fraction,
        "recommended_execution_staging_fraction": recommended,
        "effective_max_initial_buy_fraction": effective,
        "applied": applied,
        "policy": trough.get("policy"),
        "capitulation_score": trough.get("capitulation_score"),
        "reentry_confirmation_score": trough.get("reentry_confirmation_score"),
    }


def _trough_high_vol_override_watch(
    *,
    signal: dict[str, Any],
    volatility_guard: dict[str, Any],
    risk_guard: dict[str, Any],
    compounding_guard: dict[str, Any],
    max_override_fraction: float = 0.25,
) -> dict[str, Any]:
    """Research-only diagnostic for a possible high-vol trough override.

    This deliberately does not alter target shares, trades, or guard decisions.
    It only records whether the current blocked 00631L buy resembles the
    two-event shadow candidate.
    """

    trough = signal.get("trough_nowcast") if isinstance(signal.get("trough_nowcast"), dict) else {}
    market_proxy = ((trough or {}).get("inputs") or {}).get("market_proxy") or {}
    blocked = [
        trade
        for trade in (volatility_guard.get("blocked_trades") or [])
        if isinstance(trade, dict) and trade.get("ticker") == "00631L.TW" and trade.get("side") == "buy"
    ]
    risk_blocks_631l = any(
        isinstance(trade, dict) and trade.get("ticker") == "00631L.TW"
        for trade in (risk_guard.get("blocked_trades") or [])
    )
    compounding_blocks_631l = any(
        isinstance(trade, dict) and trade.get("ticker") == "00631L.TW"
        for trade in (compounding_guard.get("blocked_trades") or [])
    )
    blocked_delta = int(blocked[0].get("blocked_delta_shares", 0) or 0) if blocked else 0
    no_lower_low = market_proxy.get("no_fresh_0050_lower_low_3d") is True
    active = bool(
        (trough or {}).get("state") == "PARTIAL_REENTRY"
        and volatility_guard.get("status") == "blocked"
        and blocked_delta > 0
        and no_lower_low
        and not risk_blocks_631l
        and not compounding_blocks_631l
    )
    research_shares = int(blocked_delta * max_override_fraction) if active else 0
    return {
        "name": "trough_high_vol_00631l_override_watch",
        "research_only": True,
        "live_execution_effect": "none",
        "status": "watch" if active else "inactive",
        "candidate_policy": "partial_reentry_high_vol_no_lower_low_3d_cap_25pct",
        "max_override_fraction_of_blocked_00631l_buy": max_override_fraction,
        "trough_state": (trough or {}).get("state", "NO_TROUGH"),
        "volatility_guard_status": volatility_guard.get("status"),
        "risk_guard_blocks_00631l": risk_blocks_631l,
        "compounding_guard_blocks_00631l": compounding_blocks_631l,
        "blocked_00631l_buy_shares": blocked_delta,
        "research_candidate_00631l_shares": research_shares,
        "no_fresh_0050_lower_low_3d": no_lower_low,
        "latest_0050_close": market_proxy.get("latest_0050_close"),
        "prior_0050_3d_low": market_proxy.get("prior_0050_3d_low"),
        "reason": (
            "research_candidate_only_not_applied"
            if active
            else "conditions_not_met_or_other_guard_blocks_00631l"
        ),
    }


def _cross_market_graph_advisory_summary(signal: dict[str, Any]) -> dict[str, Any]:
    graph = signal.get("cross_market_graph_shadow")
    if not isinstance(graph, dict):
        return {
            "status": "unavailable",
            "policy": "shadow_only_no_weight_change",
            "live_execution_effect": "none",
            "reason": "missing_cross_market_graph_shadow",
        }
    assessment = graph.get("promotion_assessment") if isinstance(graph.get("promotion_assessment"), dict) else {}
    metrics = graph.get("metrics") if isinstance(graph.get("metrics"), dict) else {}
    by_year = graph.get("metrics_by_year") if isinstance(graph.get("metrics_by_year"), dict) else {}
    by_condition = graph.get("metrics_by_condition") if isinstance(graph.get("metrics_by_condition"), dict) else {}
    stress_years = {
        year: {
            "NO_ADD_auc": ((detail.get("NO_ADD") or {}).get("auc") if isinstance(detail, dict) else None),
            "NO_ADD_balanced_accuracy": (
                (detail.get("NO_ADD") or {}).get("balanced_accuracy") if isinstance(detail, dict) else None
            ),
            "REENTER_auc": ((detail.get("REENTER") or {}).get("auc") if isinstance(detail, dict) else None),
        }
        for year, detail in by_year.items()
        if year in {"2020", "2021", "2022", "2026"} and isinstance(detail, dict)
    }
    return {
        "status": graph.get("status", "available"),
        "policy": graph.get("policy", "shadow_only_no_weight_change"),
        "live_execution_effect": "none",
        "latest_shadow_action": graph.get("latest_shadow_action"),
        "no_add_active": bool(graph.get("no_add_active") is True),
        "recommended_action": graph.get("recommended_action"),
        "latest_probabilities": graph.get("latest_probabilities"),
        "thresholds": graph.get("thresholds"),
        "recommended_use": assessment.get("recommended_use", "NO_ADD_ONLY_SHADOW_FILTER"),
        "promote_to_execution_guard": bool(assessment.get("promote_to_execution_guard") is True),
        "promote_to_reentry_signal": bool(assessment.get("promote_to_reentry_signal") is True),
        "auto_weight_change": bool(
            ((assessment.get("minimum_live_alert_policy") or {}).get("auto_weight_change") is True)
        ),
        "overall_metrics": {
            "NO_ADD_auc": ((metrics.get("NO_ADD") or {}).get("auc") if isinstance(metrics.get("NO_ADD"), dict) else None),
            "REENTER_auc": (
                (metrics.get("REENTER") or {}).get("auc") if isinstance(metrics.get("REENTER"), dict) else None
            ),
        },
        "stress_year_metrics": stress_years,
        "condition_metrics": {
            condition: {
                "rows": detail.get("condition_rows"),
                "frequency": detail.get("condition_frequency"),
                "NO_ADD_auc": ((detail.get("NO_ADD") or {}).get("auc") if isinstance(detail, dict) else None),
                "NO_ADD_balanced_accuracy": (
                    (detail.get("NO_ADD") or {}).get("balanced_accuracy") if isinstance(detail, dict) else None
                ),
                "REENTER_auc": ((detail.get("REENTER") or {}).get("auc") if isinstance(detail, dict) else None),
            }
            for condition, detail in by_condition.items()
            if isinstance(detail, dict)
        },
        "selected_features": graph.get("selected_features"),
        "report_path": graph.get("report_path"),
        "rationale": assessment.get(
            "rationale",
            "NO_ADD-only shadow advisory; do not use as automatic re-entry or allocation rule.",
        ),
    }


def build_execution_plan(
    workbook: Path,
    requested_as_of: str,
    cash_balance: float,
    max_business_stale_days: int,
    db_path: Path,
    manifest_path: Path,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
    max_turnover_ratio: float = 0.5,
    commission_discount: float = 1.0,
    min_trade_notional: float = 5_000.0,
    min_weight_deviation: float = 0.005,
    share_lot_size: int = 1,
    max_initial_buy_fraction: float = 0.4,
    min_staged_buy_notional: float = 20_000.0,
    compounding_regime_path: Path | None = None,
    holdings_json_path: Path | None = None,
    enforce_advisory_pre_trade_guards: bool = True,
) -> dict[str, Any]:
    if not 0.0 <= commission_discount <= 1.0:
        raise ValueError("commission_discount must be between 0 and 1")
    holdings = (
        load_group_a_plus_holdings_json(holdings_json_path)
        if holdings_json_path is not None
        else load_group_a_plus_holdings(workbook)
    )
    held_tickers = sorted(ticker for ticker, shares in holdings.items() if shares != 0)
    held_prices = _latest_prices(db_path, held_tickers, requested_as_of)
    unknown_prices = sorted(set(held_tickers) - set(held_prices))
    holdings_market_value = sum(holdings[ticker] * held_prices.get(ticker, 0.0) for ticker in holdings)
    total_assets = holdings_market_value + cash_balance
    if total_assets <= 0.0:
        raise ValueError("Current holdings plus cash must have positive value")
    signal = build_daily_signal(
        requested_as_of,
        total_assets,
        max_business_stale_days,
        730,
        db_path,
        manifest_path,
    )
    all_prices = {**held_prices, **signal["latest_prices"]}
    theoretical_target_shares = {
        **{ticker: 0 for ticker in holdings},
        **{ticker: int(shares) for ticker, shares in signal["reference_target_shares_before_cost"].items()},
    }
    target_shares, suppressed_trades = _apply_execution_controls(
        holdings,
        theoretical_target_shares,
        all_prices,
        total_assets,
        min_trade_notional,
        min_weight_deviation,
        share_lot_size,
    )
    effective_buy_fraction, trough_reentry_staging = _trough_nowcast_buy_fraction(
        signal,
        max_initial_buy_fraction,
    )
    target_shares, staged_buys = _apply_buy_staging(
        holdings,
        target_shares,
        all_prices,
        effective_buy_fraction,
        min_staged_buy_notional,
        share_lot_size,
    )
    staged_target_shares = dict(target_shares)
    volatility_guarded_targets, pre_trade_guard = apply_volatility_gate_pre_trade_guard(
        holdings,
        staged_target_shares,
        signal,
    )
    risk_guarded_targets, risk_add_pre_trade_guard = apply_risk_add_pre_trade_guard(
        holdings,
        staged_target_shares,
        signal,
    )
    compounding_regime = _load_compounding_regime(compounding_regime_path)
    compounding_guarded_targets, compounding_regime_pre_trade_guard = apply_compounding_regime_pre_trade_guard(
        holdings,
        staged_target_shares,
        compounding_regime,
    )
    if not enforce_advisory_pre_trade_guards:
        # All orders are placed manually (no automated execution exists yet), so
        # these two guards were designed to be a human-review prompt, not an
        # automatic block -- see 2026-07-23 audit. Downgrading them here keeps
        # apply_volatility_gate_pre_trade_guard / apply_compounding_regime_pre_trade_guard
        # (and their unit tests) unchanged; only the enforcement decision made in
        # this function changes. The full recommended target is kept in
        # target_shares for manual review; what the guard would have blocked is
        # preserved under advisory_trades instead of being silently zeroed out.
        for guard in (pre_trade_guard, compounding_regime_pre_trade_guard):
            guard["enforced"] = False
            if guard.get("status") == "blocked":
                guard["advisory_trades"] = guard.get("blocked_trades", [])
                guard["blocked_trades"] = []
                guard["status"] = "flagged_advisory_only"
                guard["guarded_target_shares"] = guard.get("requested_target_shares")
                guard["review_note"] = (
                    "Advisory only: full target kept for manual review instead of being auto-blocked."
                )
        volatility_guarded_targets = dict(staged_target_shares)
        compounding_guarded_targets = dict(staged_target_shares)
    else:
        for guard in (pre_trade_guard, compounding_regime_pre_trade_guard):
            guard["enforced"] = True

    target_shares = _combine_guarded_targets(
        staged_target_shares,
        [volatility_guarded_targets, risk_guarded_targets, compounding_guarded_targets],
    )
    pre_trade_guards = [
        pre_trade_guard,
        risk_add_pre_trade_guard,
        compounding_regime_pre_trade_guard,
    ]
    guard_impact_summary = _build_guard_impact_summary(
        holdings,
        staged_target_shares,
        target_shares,
        all_prices,
        pre_trade_guards,
    )
    trough_high_vol_override_watch = _trough_high_vol_override_watch(
        signal=signal,
        volatility_guard=pre_trade_guard,
        risk_guard=risk_add_pre_trade_guard,
        compounding_guard=compounding_regime_pre_trade_guard,
    )
    cross_market_graph_advisory = _cross_market_graph_advisory_summary(signal)
    missing_trade_prices = sorted(
        ticker
        for ticker in set(holdings) | set(target_shares)
        if holdings.get(ticker, 0) != target_shares.get(ticker, 0) and ticker not in all_prices
    )
    trades: list[dict[str, Any]] = []
    totals = {"buy_notional": 0.0, "sell_notional": 0.0, "total_execution_cost": 0.0, "turnover_notional": 0.0}
    if not missing_trade_prices:
        trades, totals = _build_trades(
            holdings,
            target_shares,
            all_prices,
            commission_rate * commission_discount,
            slippage_rate,
            equity_etf_sell_tax,
        )
    estimated_cash_after_execution = (
        cash_balance
        + totals["sell_notional"]
        - totals["buy_notional"]
        - totals["total_execution_cost"]
    )
    turnover_ratio = totals["turnover_notional"] / total_assets
    guard_reasons = list(signal["execution_guard_reasons"])
    portfolio_mismatch = _portfolio_value_mismatch_reason(signal, total_assets)
    if portfolio_mismatch:
        guard_reasons.append(portfolio_mismatch)
    compounding_date = _compounding_regime_date(compounding_regime)
    if compounding_regime is not None and compounding_date != str(signal["actual_data_date"]):
        guard_reasons.append(
            "compounding regime date does not align with live signal actual_data_date: "
            f"{compounding_date} != {signal['actual_data_date']}"
        )
    if unknown_prices:
        guard_reasons.append(f"missing current-holding prices: {unknown_prices}")
    if missing_trade_prices:
        guard_reasons.append(f"missing trade prices: {missing_trade_prices}")
    if estimated_cash_after_execution < 0.0:
        guard_reasons.append(f"estimated cash after execution is negative: {estimated_cash_after_execution:.2f}")
    if turnover_ratio > max_turnover_ratio:
        guard_reasons.append(
            f"turnover ratio {turnover_ratio:.2%} exceeds automatic limit {max_turnover_ratio:.2%}"
        )
    execution_allowed = bool(signal["execution_allowed"] and not guard_reasons)
    return {
        "plan_version": 2,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "strategy_id": signal["strategy_id"],
        "requested_as_of_date": requested_as_of,
        "actual_data_date": signal["actual_data_date"],
        "workbook": str(workbook),
        "holdings_source": str(holdings_json_path or workbook),
        "holdings_row": "即時庫存",
        "current_holdings": holdings,
        "current_cash_input": cash_balance,
        "cash_assumption": "workbook has no cash field; using explicit --cash-balance input",
        "current_holdings_market_value": holdings_market_value,
        "current_total_assets": total_assets,
        "current_prices": all_prices,
        "execution_regime": signal["execution_regime"],
        "target_weights": signal["target_weights"],
        "theoretical_target_shares": theoretical_target_shares,
        "target_shares": target_shares,
        "suppressed_trades": suppressed_trades,
        "staged_buys": staged_buys,
        "staged_target_shares_before_guards": staged_target_shares,
        "advisory_pre_trade_guards_enforced": enforce_advisory_pre_trade_guards,
        "pre_trade_guard": pre_trade_guard,
        "risk_add_pre_trade_guard": risk_add_pre_trade_guard,
        "compounding_regime_pre_trade_guard": compounding_regime_pre_trade_guard,
        "pre_trade_guards": pre_trade_guards,
        "guard_impact_summary": guard_impact_summary,
        "trough_high_vol_override_watch": trough_high_vol_override_watch,
        "cross_market_graph_advisory": cross_market_graph_advisory,
        "execution_controls": {
            "published_commission_rate": commission_rate,
            "commission_discount": commission_discount,
            "effective_commission_rate": commission_rate * commission_discount,
            "min_trade_notional": min_trade_notional,
            "min_weight_deviation": min_weight_deviation,
            "share_lot_size": share_lot_size,
            "forced_liquidations_bypass_bands": True,
            "max_initial_buy_fraction": max_initial_buy_fraction,
            "effective_max_initial_buy_fraction": effective_buy_fraction,
            "trough_reentry_staging": trough_reentry_staging,
            "min_staged_buy_notional": min_staged_buy_notional,
            "buy_staging_applies_to_sells": False,
            "compounding_regime_source": (
                compounding_regime.get("_source_path") if isinstance(compounding_regime, dict) else None
            ),
        },
        "trades": trades,
        "execution_summary": {
            **totals,
            "estimated_cash_after_execution": estimated_cash_after_execution,
            "turnover_ratio": turnover_ratio,
            "max_automatic_turnover_ratio": max_turnover_ratio,
            "cross_market_graph_no_add_active": cross_market_graph_advisory.get("no_add_active"),
            "cross_market_graph_recommended_use": cross_market_graph_advisory.get("recommended_use"),
        },
        "planning_status": "ready" if execution_allowed else "manual_review_required",
        "manual_confirmation_required": not execution_allowed,
        "execution_allowed": execution_allowed,
        "execution_guard_reasons": guard_reasons,
        "source_live_signal": signal,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--as-of", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--cash-balance", type=float, default=0.0)
    parser.add_argument("--max-business-stale-days", type=int, default=3)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--max-turnover-ratio", type=float, default=0.5)
    parser.add_argument("--commission-discount", type=float, default=1.0)
    parser.add_argument("--min-trade-notional", type=float, default=5000.0)
    parser.add_argument("--min-weight-deviation", type=float, default=0.005)
    parser.add_argument("--share-lot-size", type=int, default=1)
    parser.add_argument("--max-initial-buy-fraction", type=float, default=0.4)
    parser.add_argument("--min-staged-buy-notional", type=float, default=20_000.0)
    parser.add_argument(
        "--holdings-json",
        default=None,
        help="Optional holdings JSON with a holdings object. When set, this replaces workbook holdings parsing.",
    )
    parser.add_argument(
        "--compounding-regime",
        default=None,
        help="Optional 00631L leveraged compounding regime JSON. Use 'latest' for the newest matching result.",
    )
    parser.add_argument("--output", default="results/group_a_plus_execution_plan_v2.json")
    parser.add_argument("--latest-pointer", default=str(DEFAULT_EXECUTION_PLAN))
    parser.add_argument(
        "--enforce-advisory-pre-trade-guards",
        action="store_true",
        default=False,
        help=(
            "Let the volatility-gate and compounding-regime guards auto-zero the 00631L target "
            "(pre-2026-07-23 behavior). Default is off: all orders are placed manually, so these "
            "two guards only flag a warning and the full recommended target is kept for review."
        ),
    )
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.operations.execution_plan")
    try:
        plan = build_execution_plan(
            Path(args.workbook),
            args.as_of,
            args.cash_balance,
            args.max_business_stale_days,
            Path(args.db),
            Path(args.manifest),
            args.commission_rate,
            args.slippage_rate,
            args.equity_etf_sell_tax,
            args.max_turnover_ratio,
            args.commission_discount,
            args.min_trade_notional,
            args.min_weight_deviation,
            args.share_lot_size,
            args.max_initial_buy_fraction,
            args.min_staged_buy_notional,
            Path(args.compounding_regime) if args.compounding_regime else None,
            Path(args.holdings_json) if args.holdings_json else None,
            args.enforce_advisory_pre_trade_guards,
        )
        payload = std.success(plan)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    write_standard_output(payload, args.latest_pointer)
    pit_snapshot = _write_execution_plan_pit_snapshot(payload, requested_as_of=args.as_of)
    print(f"Execution plan: {Path(args.output).resolve()}")
    print(f"Latest pointer: {Path(args.latest_pointer).resolve()}")
    print(f"PIT snapshot: {pit_snapshot.resolve()}")


if __name__ == "__main__":
    main()
