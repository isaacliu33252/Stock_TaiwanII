"""Generate an execution-guarded daily signal from the active latest strategy."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest_group_a_plus_policy_signal import TICKERS, _normalize
from backtest_group_a_plus_switch_policy import DB_PATH
from group_a_plus.governance.latest import DEFAULT_LATEST_STRATEGY
from group_a_plus.integrations.factor_lens import factor_passes_gate
from group_a_plus.integrations.finbert import load_finbert_daily_snapshot
from group_a_plus.integrations.lm_dictionary_sentiment import build_lm_dictionary_snapshot
from group_a_plus.integrations.signal_alignment import build_signal_alignment
from group_a_plus.utils.symbols import build_symbol_metadata
from group_a_plus.integrations.ncf import load_ncf_signal, ncf_overlay_summary
from group_a_plus.integrations.tbrain_features import (
    kdj_j_quantile_snapshot,
    latest_tbrain_snapshot,
    weekly_ma_bull_snapshot,
)
from group_a_plus.operations.market_state import classify_market_state
from group_a_plus.paths import PROJECT_ROOT
from group_a_plus.runners.latest import run_latest
from tw_output_standard import OutputStandardizer, write_standard_output


DEFAULT_LIVE_SIGNAL = Path("report/group_a_plus/latest/live_signal.json")
OPTIONAL_SOURCE_SPECS = {
    "institutional_0050": ("institutional_data", "ticker = '0050.TW'", 0),
    "margin_0050": ("margin_data", "ticker = '0050.TW'", 1),
    "market_margin": ("market_margin_data", "1 = 1", 1),
    "tdcc_0050": ("shareholding_distribution", "stock_id = '0050'", 10),
    "foreign_shareholding_0050": ("foreign_shareholding_data", "ticker = '0050.TW'", 1),
    "short_balance_0050": ("short_sale_balance_data", "ticker = '0050.TW'", 1),
    "securities_lending_0050": ("securities_lending_data", "ticker = '0050.TW'", 1),
    "day_trading_0050": ("day_trading_data", "ticker = '0050.TW'", 0),
    "dealer_tx": ("dealer_futures_data", "futures_id = 'TX' AND is_after_hour = 0", 3),
    "dealer_txo": ("dealer_options_data", "option_id = 'TXO' AND is_after_hour = 0", 3),
    "foreign_tx_oi": (
        "derivative_institutional_data",
        "market = 'futures' AND product_id = 'TX' AND institutional_investors = '外資'",
        3,
    ),
    "foreign_txo_oi": (
        "derivative_institutional_data",
        "market = 'options' AND product_id = 'TXO' AND institutional_investors = '外資'",
        3,
    ),
}
SOFT_OPTIONAL_SOURCES = {
    "securities_lending_0050",
}
NCF_TICKER_TAGS = {
    "00631L.TW": "00631l",
    "00632R.TW": "00632r",
}
# M5 (2026-07-02 Fable 5 audit): previously only 2026-06-19 was listed here.
# Expanded to a best-effort TWSE trading-holiday calendar for 2025-2026
# (standard Taiwan public holidays observed by the exchange; does not
# include ad hoc typhoon/earthquake closures, which are announced same-day
# and can't be pre-listed). An earlier attempt to *infer* holidays from
# ohlcv-table gaps was reverted: it silently masked genuine staleness
# whenever the table wasn't densely populated for every trading day
# (confirmed by two existing unit tests breaking against sparse fixtures) --
# a bad failure mode for a risk-management staleness gate. A hand-maintained
# explicit list is safer even though it needs periodic upkeep.
TAIWAN_MARKET_HOLIDAYS = {
    pd.Timestamp(d)
    for d in [
        # 2025
        "2025-01-01",  # New Year's Day
        "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",
        "2025-02-03",  # Lunar New Year (observed dates around 2025-01-29)
        "2025-02-28",  # Peace Memorial Day
        "2025-04-03", "2025-04-04",  # Tomb Sweeping Day / Children's Day
        "2025-05-01",  # Labor Day
        "2025-05-30", "2025-05-31",  # Dragon Boat Festival (observed)
        "2025-10-06",  # Mid-Autumn Festival
        "2025-10-10",  # National Day
        # 2026
        "2026-01-01",  # New Year's Day
        "2026-02-14", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
        # Lunar New Year 2026 (CNY falls 2026-02-17)
        "2026-02-27",  # Peace Memorial Day (observed, 02-28 is a Saturday)
        "2026-04-03", "2026-04-06",  # Tomb Sweeping Day / Children's Day (observed)
        "2026-05-01",  # Labor Day
        "2026-06-19",  # Dragon Boat Festival
        "2026-09-25",  # Mid-Autumn Festival
        "2026-10-09",  # National Day (observed, 10-10 is a Saturday)
    ]
}


def _business_days_between(start: str | pd.Timestamp, end: str | pd.Timestamp) -> int:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    if end_ts <= start_ts:
        return 0
    weekdays = pd.bdate_range(start_ts + pd.Timedelta(days=1), end_ts)
    return int(sum(day.normalize() not in TAIWAN_MARKET_HOLIDAYS for day in weekdays))


def _resolve_weights(report: dict[str, Any], regime: str) -> dict[str, float]:
    # a2111-style: report["weights"][regime]
    # a2118-style: report["base_weights"][regime]  (base_weights is the fallback)
    weights = report.get("weights") or report.get("base_weights") or {}
    if regime in weights:
        return _normalize(dict(weights[regime]))
    aliases = {
        "golden1": "golden1_0531_1m",
        "group_a_plus_defensive": "group_a_plus_defensive_1m",
    }
    alias = aliases.get(regime)
    if alias and alias in weights:
        return _normalize(dict(weights[alias]))
    raise ValueError(f"No target weights for execution regime: {regime}")


def _latest_ncf_path(ticker_tag: str, project_root: Path = PROJECT_ROOT) -> Path | None:
    results = project_root / "results"
    patterns = [
        f"ncf_{ticker_tag}_latest_*.json",
        f"ncf_{ticker_tag}_2*.json",
    ]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(results.glob(pattern))
    candidates = [
        path
        for path in candidates
        if path.is_file()
        and "panel" not in path.name
        and "advisory" not in path.name
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime).resolve()


def _apply_ncf_live_overlay(
    target_weights: dict[str, float],
    execution_regime: str,
    actual_date: pd.Timestamp,
    latest_row: pd.Series,
    project_root: Path = PROJECT_ROOT,
) -> tuple[dict[str, float], dict[str, Any], list[str]]:
    paths = {
        ticker: _latest_ncf_path(tag, project_root)
        for ticker, tag in NCF_TICKER_TAGS.items()
    }
    missing = sorted(ticker for ticker, path in paths.items() if path is None)
    if missing:
        return dict(target_weights), {
            "status": "unavailable",
            "reason": "missing_ncf_files",
            "missing_tickers": missing,
        }, [f"NCF live overlay unavailable: missing {missing}"]

    assert paths["00631L.TW"] is not None
    assert paths["00632R.TW"] is not None
    sig_631l = load_ncf_signal(paths["00631L.TW"])
    sig_632r = load_ncf_signal(paths["00632R.TW"])
    actual = str(pd.Timestamp(actual_date).date())
    ncf_dates = {
        "00631L.TW": sig_631l.get("date"),
        "00632R.TW": sig_632r.get("date"),
    }
    if any(str(date) != actual for date in ncf_dates.values()):
        return dict(target_weights), {
            "status": "stale",
            "reason": "ncf_date_mismatch",
            "actual_data_date": actual,
            "ncf_dates": ncf_dates,
            "files": {ticker: str(path) for ticker, path in paths.items() if path is not None},
        }, [f"NCF live overlay skipped: date mismatch {ncf_dates}, actual {actual}"]

    summary = ncf_overlay_summary(
        sig_631l,
        sig_632r,
        target_weights,
        execution_regime,
        ma_gap=float(latest_row.get("ma_gap", 0.0)),
    )
    summary["status"] = "applied" if execution_regime == "golden1" else "not_applicable"
    summary["files"] = {ticker: str(path) for ticker, path in paths.items() if path is not None}
    if execution_regime != "golden1":
        return dict(target_weights), summary, []
    return _normalize(dict(summary["adjusted_golden1_weights"])), summary, []


def _a2118_live_signal_is_current(ncf_live_signal: dict[str, Any], actual_date: pd.Timestamp) -> bool:
    if ncf_live_signal.get("status", "ok") != "ok":
        return False
    signal_date = ncf_live_signal.get("signal_date")
    if signal_date is None:
        return True
    return str(pd.Timestamp(signal_date).date()) == str(pd.Timestamp(actual_date).date())


def _load_previous_live_signal(path: Path = DEFAULT_LIVE_SIGNAL) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        data = dict(data)
        data["_payload_metadata"] = payload.get("metadata") if isinstance(payload, dict) else None
        return data
    return None


def _previous_a2118_hold_active(
    previous_signal: dict[str, Any] | None,
    actual_date: pd.Timestamp,
    min_generated_at: datetime | None = None,
) -> bool:
    if not previous_signal:
        return False
    if min_generated_at is not None:
        previous_generated_at = (previous_signal.get("_payload_metadata") or {}).get("timestamp")
        if not previous_generated_at:
            return False
        try:
            if datetime.fromisoformat(str(previous_generated_at)) < min_generated_at:
                return False
        except ValueError:
            return False
    if previous_signal.get("strategy_id") != "a2118_a2111_ncf_late_bull_deleverage":
        return False
    try:
        previous_date = pd.Timestamp(previous_signal.get("actual_data_date")).normalize()
    except Exception:
        return False
    if previous_date >= pd.Timestamp(actual_date).normalize():
        return False
    overlay = previous_signal.get("ncf_live_overlay") or {}
    return bool(
        overlay.get("a2118_late_bull_hard_overlay_applied")
        or overlay.get("a2118_late_bull_hold_active")
    )


def _a2118_live_hard_overlay_reason(
    *,
    report: dict[str, Any],
    execution_regime: str,
    actual_date: pd.Timestamp,
    previous_signal: dict[str, Any] | None = None,
    min_previous_generated_at: datetime | None = None,
) -> str | None:
    if str(report.get("active_strategy_id", "")) != "a2118_a2111_ncf_late_bull_deleverage":
        return None
    if execution_regime != "golden1":
        return None
    ncf_live_signal = report.get("ncf_live_signal", {})
    if not _a2118_live_signal_is_current(ncf_live_signal, actual_date):
        # Fail closed, not open: if a hedge/hold was already active as of
        # yesterday, keep it rather than silently reverting to full-leverage
        # golden1 just because today's NCF signal is stale/missing/date-
        # mismatched. NCF outages tend to coincide with market disruption --
        # exactly when the previous day's defensive posture matters most.
        if _previous_a2118_hold_active(
            previous_signal,
            actual_date,
            min_generated_at=min_previous_generated_at,
        ):
            return "stale_fail_closed"
        return None
    # M4 (2026-07-02 Fable 5 audit): use effective_hedge_active (=
    # late_bull_triggered AND NOT rally_suppressed) when present, not raw
    # late_bull_triggered alone -- otherwise, if rally_suppress_min is ever
    # enabled, a rally-suppressed trigger day would still apply hard-hedge
    # weights here (ncf_live_signal["effective_weights"] already accounts
    # for suppression, but this reason-check didn't), and the next day's
    # _previous_a2118_hold_active would wrongly extend an h5_hold chain from
    # a hedge that was never actually supposed to be active. Falls back to
    # late_bull_triggered for older payloads that predate this field.
    if ncf_live_signal.get("effective_hedge_active", ncf_live_signal.get("late_bull_triggered")):
        return "trigger"
    if not _previous_a2118_hold_active(
        previous_signal,
        actual_date,
        min_generated_at=min_previous_generated_at,
    ):
        return None
    h5_prob = ncf_live_signal.get("h5_prob_up")
    h5_reentry = (report.get("rules") or {}).get("ncf_late_bull_h5_reentry_min")
    if h5_prob is None or h5_reentry in (None, 0):
        return None
    try:
        if float(h5_prob) < float(h5_reentry):
            return "h5_hold"
    except (TypeError, ValueError):
        return None
    return None


def _a2118_live_hard_overlay_weights(report: dict[str, Any], reason: str) -> dict[str, float] | None:
    ncf_live_signal = report.get("ncf_live_signal", {})
    base_weights = report.get("base_weights") or {}
    hedge_weights = base_weights.get("ncf_late_bull_hedge")
    if reason in ("h5_hold", "stale_fail_closed") and hedge_weights:
        return _normalize(dict(hedge_weights))
    effective_weights = ncf_live_signal.get("effective_weights")
    if effective_weights:
        return _normalize(dict(effective_weights))
    if hedge_weights:
        return _normalize(dict(hedge_weights))
    return None


def _apply_bearish_high_risk_trim(
    target_weights: dict[str, float],
    latest_features: dict[str, float | int],
    signal_alignment: dict[str, Any],
    ncf_live_overlay: dict[str, Any],
    *,
    trim_fraction: float = 0.20,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Trim live 00631L exposure when broad risk is high and sources lean bearish.

    trim_fraction scales with total_risk_score:
      risk=9  → trim_fraction × 1.0  (e.g. 20%)
      risk=10 → trim_fraction × 1.5  (e.g. 30%)
    """
    if ncf_live_overlay.get("current_regime") != "golden1":
        return dict(target_weights), ncf_live_overlay
    total_risk_score = int(latest_features.get("total_risk_score", 0) or 0)
    if total_risk_score < 9:
        return dict(target_weights), ncf_live_overlay
    if signal_alignment.get("dominant_direction") != "bearish":
        return dict(target_weights), ncf_live_overlay
    if signal_alignment.get("alignment") not in {"wide_divergence", "bearish_alignment", "mixed"}:
        return dict(target_weights), ncf_live_overlay

    weights = dict(target_weights)
    current_00631l = float(weights.get("00631L.TW", 0.0) or 0.0)
    # Scale trim with risk severity: risk=9 → base, risk=10 → base × 1.5
    raw_risk = int(latest_features.get("total_risk_score", 0) or 0)
    scale = 1.0 + 0.5 * max(0, raw_risk - 9)
    trim_fraction = min(max(float(trim_fraction) * scale, 0.0), 1.0)
    reduction = current_00631l * trim_fraction
    if reduction <= 0.0005:
        return weights, ncf_live_overlay

    weights["00631L.TW"] = current_00631l - reduction
    weights["cash"] = float(weights.get("cash", 0.0) or 0.0) + reduction
    weights = _normalize(weights)

    overlay = dict(ncf_live_overlay)
    overlay["bearish_high_risk_trim_applied"] = True
    overlay["bearish_high_risk_trim_fraction"] = trim_fraction
    overlay["bearish_high_risk_trim_reduction"] = round(reduction, 4)
    overlay["bearish_high_risk_trim_reason"] = (
        f"total_risk_score={total_risk_score}, "
        f"alignment={signal_alignment.get('alignment')}, "
        f"dominant={signal_alignment.get('dominant_direction')}"
    )
    overlay["adjusted_golden1_weights_before_high_risk_trim"] = ncf_live_overlay.get("adjusted_golden1_weights")
    overlay["adjusted_golden1_weights"] = weights
    overlay["00631l_reduction"] = round(
        float((ncf_live_overlay.get("base_golden1_weights") or {}).get("00631L.TW", current_00631l)) - weights.get("00631L.TW", 0.0),
        4,
    )
    overlay["action"] = "reduce_00631l_high_risk"
    return weights, overlay


def _source_freshness(
    db_path: Path,
    requested_as_of: pd.Timestamp,
    price_as_of: pd.Timestamp,
) -> dict[str, Any]:
    requested_as_of = pd.Timestamp(requested_as_of).normalize()
    price_as_of = pd.Timestamp(price_as_of).normalize()
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {
            row[0]
            for row in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
        }
        ticker_rows = con.execute(
            """
            SELECT ticker, max(dt) AS latest_dt, arg_max(close, dt) AS latest_close
            FROM ohlcv
            WHERE ticker IN (?, ?, ?, ?) AND dt <= ?
            GROUP BY ticker
            ORDER BY ticker
            """,
            [*TICKERS, str(price_as_of.date())],
        ).fetchdf()
        optional = {}
        for source, (table, where, max_stale) in OPTIONAL_SOURCE_SPECS.items():
            severity = "soft" if source in SOFT_OPTIONAL_SOURCES else "hard"
            if table not in tables:
                optional[source] = {
                    "table": table,
                    "severity": severity,
                    "exists": False,
                    "latest_date": None,
                    "business_stale_days": None,
                    "max_business_stale_days": max_stale,
                    "status": "warn" if severity == "soft" else "block",
                }
                continue
            latest = con.execute(
                f"SELECT max(dt) FROM {table} WHERE {where} AND dt <= ?",
                [str(requested_as_of.date())],
            ).fetchone()[0]
            stale_days = _business_days_between(latest, price_as_of) if latest is not None else None
            optional[source] = {
                "table": table,
                "severity": severity,
                "exists": True,
                "latest_date": str(latest) if latest is not None else None,
                "freshness_as_of": str(price_as_of.date()),
                "business_stale_days": stale_days,
                "max_business_stale_days": max_stale,
                "status": (
                    "ok"
                    if stale_days is not None and stale_days <= max_stale
                    else "warn"
                    if severity == "soft"
                    else "block"
                ),
            }
    finally:
        con.close()
    ticker_dates = {
        str(row.ticker): str(pd.Timestamp(row.latest_dt).date())
        for row in ticker_rows.itertuples(index=False)
        if pd.notna(row.latest_dt)
    }
    latest_prices = {
        str(row.ticker): float(row.latest_close)
        for row in ticker_rows.itertuples(index=False)
        if pd.notna(row.latest_close)
    }
    return {
        "price_data_as_of": str(price_as_of.date()),
        "ohlcv_by_ticker": ticker_dates,
        "latest_prices": latest_prices,
        "optional_sources": optional,
    }


def _load_ohlcv_window(
    db_path: Path,
    ticker: str,
    end: pd.Timestamp,
    *,
    lookback_days: int = 220,
) -> pd.DataFrame:
    start = pd.Timestamp(end).normalize() - pd.Timedelta(days=lookback_days)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = con.execute(
            """
            SELECT dt, open, high, low, close, volume
            FROM ohlcv
            WHERE ticker = ? AND dt BETWEEN ? AND ?
            ORDER BY dt
            """,
            [ticker, str(start.date()), str(pd.Timestamp(end).date())],
        ).fetchdf()
    finally:
        con.close()
    if rows.empty:
        return pd.DataFrame()
    rows["date"] = pd.to_datetime(rows["dt"])
    return rows.set_index("date")[["open", "high", "low", "close", "volume"]].astype(float)


def _tbrain_shadow_snapshot(db_path: Path, actual_date: pd.Timestamp) -> dict[str, Any]:
    """Build a compact TBrain-style diagnostic block for the live signal JSON."""
    try:
        df = _load_ohlcv_window(db_path, "0050.TW", actual_date)
        if df.empty:
            return {"status": "unavailable", "reason": "missing_ohlcv_0050"}
        snapshot = latest_tbrain_snapshot(df)
        features = {**snapshot, **kdj_j_quantile_snapshot(df)}
        # Weekly MA needs more trailing history than the 220-day daily window above.
        weekly_df = _load_ohlcv_window(db_path, "0050.TW", actual_date, lookback_days=400)
        weekly_ma = weekly_ma_bull_snapshot(weekly_df if not weekly_df.empty else df)
        return {
            "status": "available",
            "ticker": "0050.TW",
            "date": str(pd.Timestamp(df.index[-1]).date()),
            "features": features,
            "weekly_ma": weekly_ma,
            "method": "tbrain_multi_kdj_location_shadow_v1",
        }
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}


def _factor_lens_gate_check(
    project_root: Path = PROJECT_ROOT,
    key_factors: tuple[str, ...] = (
        "ncf_00631l_prob_up",
        "ncf_cross_ticker_market_up",
        "ncf_market_probability_up",
    ),
) -> dict[str, Any]:
    """Load the latest factor lens report and return gate status per factor.

    This is advisory only — it does not block execution.
    Returns {"status": "unavailable"} when no report file is found.
    """
    candidates = sorted(
        (project_root / "results").glob("group_a_plus_factor_lens_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return {"status": "unavailable", "reason": "no_factor_lens_report"}
    report_path = candidates[0]
    try:
        import json as _json
        report = _json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}
    factors_section = report.get("factors", {})
    gates: dict[str, Any] = {}
    for name in key_factors:
        if name not in factors_section:
            gates[name] = {"passed": None, "reason": "not_in_report"}
            continue
        gates[name] = factor_passes_gate(factors_section[name])
    all_pass = all(g.get("passed") is True for g in gates.values())
    return {
        "status": "available",
        "report_file": report_path.name,
        "report_generated_at": report.get("generated_at"),
        "all_key_factors_pass": all_pass,
        "factors": gates,
    }


def _execution_risk_assessment(
    *,
    execution_allowed: bool,
    business_stale: int,
    calendar_stale: int,
    optional_warnings: list[str],
    target_weights: dict[str, float],
    latest_features: dict[str, float | int],
    ncf_live_overlay: dict[str, Any],
    finbert_sentiment: dict[str, Any],
) -> dict[str, Any]:
    components = {
        "blocked_guard": 1.0 if not execution_allowed else 0.0,
        "business_stale": min(max(float(business_stale), 0.0) / 3.0, 1.0),
        "calendar_stale": min(max(float(calendar_stale), 0.0) / 7.0, 1.0),
        "soft_data_warnings": min(len(optional_warnings) / 3.0, 1.0),
        "leverage_weight": min(max(float(target_weights.get("00631L.TW", 0.0)), 0.0) / 0.2, 1.0),
        # Normalized to /10.0 (system max is 10, not 8); weight raised to reflect primacy
        "total_risk_score": min(max(float(latest_features.get("total_risk_score", 0.0)), 0.0) / 10.0, 1.0),
        "ncf_downside": min(max(float(ncf_live_overlay.get("gated_downside_signal", 0.0) or 0.0), 0.0), 1.0),
        "ncf_tail_downside": min(max(float(ncf_live_overlay.get("tail_downside_signal", 0.0) or 0.0), 0.0), 1.0),
        "finbert_sentiment_risk": min(max(float(finbert_sentiment.get("risk_score", 0.0) or 0.0), 0.0), 1.0),
    }
    score = (
        0.28 * components["blocked_guard"]
        + 0.12 * components["business_stale"]
        + 0.05 * components["calendar_stale"]
        + 0.08 * components["soft_data_warnings"]
        + 0.12 * components["leverage_weight"]
        + 0.20 * components["total_risk_score"]
        + 0.08 * components["ncf_downside"]
        + 0.04 * components["ncf_tail_downside"]
        + 0.03 * components["finbert_sentiment_risk"]
    )
    score = round(float(min(max(score, 0.0), 1.0)), 4)
    raw_risk_score = int(latest_features.get("total_risk_score", 0) or 0)
    if not execution_allowed or score >= 0.55:
        level = "high"
    elif score >= 0.30 or raw_risk_score >= 9:
        # Floor: composite market risk at max range → at least medium, even if weighted score is low
        level = "medium"
    else:
        level = "low"
    return {
        "score": score,
        "level": level,
        "components": {key: round(value, 4) for key, value in components.items()},
        "method": "weighted_daily_execution_risk_v2",
    }


def _build_signal_alerts(
    *,
    strategy_id: str,
    actual_date: pd.Timestamp,
    execution_allowed: bool,
    execution_regime: str,
    changed_today: bool,
    execution_risk: dict[str, Any],
    latest_features: dict[str, float | int],
    finbert_sentiment: dict[str, Any],
    factor_lens_gate: dict[str, Any] | None = None,
    ncf_live_signal: dict[str, Any] | None = None,
    ncf_live_overlay: dict[str, Any] | None = None,
    signal_alignment: dict[str, Any] | None = None,
    ncf_panel_coverage: dict[str, Any] | None = None,
    cooldown_minutes: int = 5,
) -> list[dict[str, Any]]:
    """Build stable alert payloads for downstream notification/cooldown layers."""
    date_key = str(pd.Timestamp(actual_date).date())
    alerts: list[dict[str, Any]] = []

    def add(alert_type: str, level: str, title: str, reason: str) -> None:
        alerts.append(
            {
                "type": alert_type,
                "level": level,
                "title": title,
                "reason": reason,
                "cooldown_key": f"{strategy_id}:{date_key}:{alert_type}",
                "cooldown_minutes": cooldown_minutes,
            }
        )

    risk_level = str(execution_risk.get("level", "low"))
    risk_score = float(execution_risk.get("score", 0.0) or 0.0)
    if not execution_allowed:
        add("execution_blocked", "high", "Execution blocked", "Execution guard is not satisfied.")
    if changed_today:
        add("regime_transition", "medium", "Regime transition", f"Execution regime changed to {execution_regime}.")
    if risk_level in {"medium", "high"}:
        add("execution_risk", risk_level, "Execution risk elevated", f"Daily execution risk score is {risk_score:.4f}.")
    if float(finbert_sentiment.get("risk_score", 0.0) or 0.0) >= 0.55:
        add("finbert_sentiment_risk", "medium", "FinBERT sentiment risk", "Market-news sentiment risk is elevated.")
    total_risk_score = int(latest_features.get("total_risk_score", 0) or 0)
    if total_risk_score >= 9:
        add("total_risk_score", "high", "Total risk score high", "Composite market risk score is high.")
    elif total_risk_score >= 6:
        add("total_risk_score", "medium", "Total risk score elevated", "Composite market risk score is elevated.")
    if (signal_alignment or {}).get("alignment") == "wide_divergence":
        dominant = (signal_alignment or {}).get("dominant_direction")
        add(
            "signal_wide_divergence",
            "medium",
            "Signal alignment diverged",
            f"Cross-source signals show wide divergence; dominant direction is {dominant}.",
        )
    if (ncf_live_overlay or {}).get("bearish_high_risk_trim_applied"):
        add(
            "bearish_high_risk_trim",
            "medium",
            "Bearish high-risk trim applied",
            str((ncf_live_overlay or {}).get("bearish_high_risk_trim_reason", "High-risk bearish trim applied.")),
        )
    if (ncf_live_overlay or {}).get("a2118_ncf_stale_fail_closed"):
        add(
            "a2118_ncf_stale_fail_closed",
            "high",
            "NCF stale -- previous hedge preserved (manual review)",
            (
                "Today's NCF signal is stale/missing/date-mismatched. Instead of reverting to"
                " full-leverage golden1, yesterday's a2118 late-bull hedge was carried forward."
                " Confirm the NCF pipeline and this holdover decision manually."
            ),
        )
    # M3 (2026-07-02 Fable 5 audit): the NCF panel_631l can be pinned to a
    # fixed file in strategy.json's runner_params (e.g. results/ncf_00631l_
    # panel_latest_20260630.csv) -- when pinned, its mtime stops advancing,
    # which also silently neuters the `min_previous_generated_at` guard that
    # exists to invalidate a stale hold once the panel is regenerated (see
    # _previous_a2118_hold_active). Warn explicitly as the panel's *content*
    # (last_date) ages, independent of that mtime-based mechanism.
    panel_last_date_raw = (ncf_panel_coverage or {}).get("panel_631l_last_date")
    if panel_last_date_raw:
        try:
            panel_last_date = pd.Timestamp(panel_last_date_raw).normalize()
            panel_age_days = _business_days_between(panel_last_date, actual_date)
        except Exception:
            panel_age_days = None
        if panel_age_days is not None and panel_age_days >= 3:
            add(
                "ncf_panel_stale",
                "high" if panel_age_days >= 10 else "medium",
                "NCF panel stale",
                (
                    f"ncf_panel_631l last covers {panel_last_date.date()}, "
                    f"{panel_age_days} trading day(s) behind signal date {date_key}. "
                    "If this panel is pinned in strategy.json runner_params, the "
                    "reproducibility guard that invalidates stale holds on panel "
                    "regeneration is not firing -- confirm whether to refresh the panel."
                ),
            )
    factor_generated_at = (factor_lens_gate or {}).get("report_generated_at")
    if factor_generated_at:
        try:
            factor_date = pd.Timestamp(factor_generated_at).normalize()
            if factor_date < pd.Timestamp(actual_date).normalize():
                add(
                    "factor_lens_stale",
                    "medium",
                    "Factor lens report stale",
                    f"Factor lens report is dated {factor_date.date()}, older than signal date {date_key}.",
                )
        except Exception:
            pass

    # 20d IC 可靠性警告
    gate_factors = (factor_lens_gate or {}).get("factors", {})
    any_20d_warning = any(
        bool(v.get("ic_20d_warning"))
        for v in gate_factors.values()
        if isinstance(v, dict)
    )
    late_bull_triggered = bool((ncf_live_signal or {}).get("late_bull_triggered"))
    ma_gap = float(latest_features.get("ma_gap", 0.0))

    if any_20d_warning and late_bull_triggered:
        ic_20d = next(
            (v.get("ic_20d_recent_mean") for v in gate_factors.values()
             if isinstance(v, dict) and v.get("ic_20d_warning")),
            None,
        )
        add(
            "ncf_20d_ic_unreliable_with_trigger",
            "high",
            "NCF 20d IC 不可信：a2118 觸發中",
            (
                f"近期 rolling 20d IC={ic_20d:.3f}（< 0），模型 20d 方向預測反向。"
                " a2118 正依據此信號調整倉位，建議改以 1d/5d 信號為準，"
                " 並手動確認 00631L 倉位是否合理。"
            ),
        )
    elif any_20d_warning and ma_gap > 0.10:
        add(
            "ncf_20d_ic_unreliable_late_bull",
            "medium",
            "NCF 20d IC 不可信：處於 late-bull 區間",
            (
                f"近期 rolling 20d IC 為負，20d 預測不可靠。"
                f" 目前 ma_gap={ma_gap:.3f}（late-bull 區間）。"
                " 建議主動將 00631L 降至正常配置的 50%，不等 NCF 觸發。"
                " 改以技術面（MA20/MA100 跌破）作為備援停損。"
            ),
        )
    elif any_20d_warning:
        add(
            "ncf_20d_ic_unreliable",
            "low",
            "NCF 20d IC 不可信",
            "近期 rolling 20d IC 為負，月度展望請勿依賴 NCF 判斷，改看 1d/5d 信號。",
        )

    return alerts


def build_daily_signal(
    requested_as_of: str,
    portfolio_value: float,
    max_business_stale_days: int,
    lookback_days: int,
    db_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    as_of = pd.Timestamp(requested_as_of).normalize()
    start = str((as_of - pd.Timedelta(days=lookback_days)).date())
    report, frame = run_latest(start, str(as_of.date()), portfolio_value, db_path, manifest_path)
    if frame.empty:
        raise RuntimeError("Latest strategy runner returned an empty frame")
    actual = pd.Timestamp(frame.index[-1]).normalize()
    regime_column = "execution_regime" if "execution_regime" in frame.columns else "regime"
    regimes = frame[regime_column].astype(str)
    execution_regime = str(regimes.iloc[-1])
    base_regime = str(frame["base_regime"].iloc[-1]) if "base_regime" in frame.columns else execution_regime
    target_weights = _resolve_weights(report, execution_regime)
    latest_row = frame.iloc[-1]
    target_weights, ncf_live_overlay, ncf_warnings = _apply_ncf_live_overlay(
        target_weights,
        execution_regime,
        actual,
        latest_row,
    )
    # a2118 hard overlay: when late-bull trigger fires, use the binary de-leverage weights
    # (soft overlay underestimates the required de-leverage; a2118 does a full 00631L halving)
    ncf_live_signal = report.get("ncf_live_signal", {})
    previous_signal = _load_previous_live_signal()
    min_previous_generated_at = None
    panel_path_raw = (report.get("ncf_panel_coverage") or {}).get("panel_631l_path")
    if panel_path_raw:
        panel_path = Path(panel_path_raw)
        if panel_path.exists():
            min_previous_generated_at = datetime.fromtimestamp(panel_path.stat().st_mtime)
    a2118_overlay_reason = _a2118_live_hard_overlay_reason(
        report=report,
        execution_regime=execution_regime,
        actual_date=actual,
        previous_signal=previous_signal,
        min_previous_generated_at=min_previous_generated_at,
    )
    if a2118_overlay_reason is not None:
        hard_weights = _a2118_live_hard_overlay_weights(report, a2118_overlay_reason)
        if hard_weights:
            target_weights = hard_weights
            ncf_live_overlay["a2118_late_bull_hard_overlay_applied"] = True
            ncf_live_overlay["a2118_late_bull_overlay_reason"] = a2118_overlay_reason
            ncf_live_overlay["a2118_late_bull_hold_active"] = a2118_overlay_reason in (
                "h5_hold",
                "stale_fail_closed",
            )
            ncf_live_overlay["a2118_h20_prob"] = ncf_live_signal.get("h20_prob_up")
            ncf_live_overlay["a2118_h5_prob"] = ncf_live_signal.get("h5_prob_up")
            ncf_live_overlay["a2118_confidence"] = ncf_live_signal.get("confidence")
            if a2118_overlay_reason == "stale_fail_closed":
                # H1/H5 (2026-07-02 Fable 5 audit): NCF was stale/mismatched
                # today, but yesterday's hedge is preserved instead of
                # silently falling back to full-leverage golden1. Surfaced
                # as an alert (see _build_signal_alerts) so it gets manual
                # review rather than passing silently.
                ncf_live_overlay["a2118_ncf_stale_fail_closed"] = True
    elif (
        str(report.get("active_strategy_id", "")) == "a2118_a2111_ncf_late_bull_deleverage"
        and execution_regime == "ncf_late_bull_hedge"
        and _a2118_live_signal_is_current(ncf_live_signal, actual)
    ):
        ncf_live_overlay["a2118_late_bull_hard_overlay_applied"] = True
        ncf_live_overlay["a2118_late_bull_overlay_reason"] = "panel_trigger"
        ncf_live_overlay["a2118_late_bull_hold_active"] = False
        ncf_live_overlay["a2118_h20_prob"] = ncf_live_signal.get("h20_prob_up")
        ncf_live_overlay["a2118_h5_prob"] = ncf_live_signal.get("h5_prob_up")
        ncf_live_overlay["a2118_confidence"] = ncf_live_signal.get("confidence")
    source_freshness = _source_freshness(db_path, as_of, actual)
    ticker_dates = source_freshness["ohlcv_by_ticker"]
    latest_prices = source_freshness["latest_prices"]
    optional_blocks = sorted(
        source
        for source, detail in source_freshness["optional_sources"].items()
        if detail["status"] == "block"
    )
    optional_warnings = sorted(
        source
        for source, detail in source_freshness["optional_sources"].items()
        if detail["status"] == "warn"
    )
    missing_tickers = sorted(set(TICKERS) - set(ticker_dates))
    ticker_misaligned = sorted(
        ticker for ticker, date in ticker_dates.items() if pd.Timestamp(date).normalize() != actual
    )
    business_stale = _business_days_between(actual, as_of)
    calendar_stale = max(int((as_of - actual).days), 0)
    execution_allowed = (
        report["status"] == "active"
        and
        business_stale <= max_business_stale_days
        and not missing_tickers
        and not ticker_misaligned
        and not optional_blocks
    )
    changed = regimes.ne(regimes.shift())
    transition_date = pd.Timestamp(changed[changed].index[-1]).normalize()
    changed_today = bool(transition_date == actual)
    reason = {
        "golden1": "A20.7 formal defensive state is inactive",
        "group_a_plus_defensive": "A20.7 defensive state is active and recovery ramp has not triggered",
        "group_a_plus_recovery": "A20.7 remains defensive; MA75 gap and five-day momentum triggered recovery ramp",
    }.get(execution_regime, "active strategy regime")
    latest_features = {
        "ma_gap": float(latest_row.get("ma_gap", 0.0)),
        "drawdown": float(latest_row.get("drawdown", 0.0)),
        "exit_momentum_5d": float(latest_row.get("exit_momentum", 0.0)),
        "chip_score": int(latest_row.get("chip_score", 0)),
        "derivative_score": int(latest_row.get("derivative_score", 0)),
        "total_risk_score": int(latest_row.get("total_risk_score", 0)),
        "tail_risk_score": int(latest_row.get("tail_risk_score", 0)),
    }
    finbert_sentiment = load_finbert_daily_snapshot(as_of, actual)
    lm_dictionary_sentiment = build_lm_dictionary_snapshot(str(actual.date()))
    latest_features["finbert_sentiment_risk"] = float(finbert_sentiment.get("risk_score", 0.0) or 0.0)
    tbrain_shadow = _tbrain_shadow_snapshot(db_path, actual)
    factor_lens_gate = _factor_lens_gate_check()
    signal_alignment = build_signal_alignment(
        {
            "strategy_id": str(report["active_strategy_id"]),
            "actual_data_date": str(actual.date()),
            "execution_regime": execution_regime,
            "latest_features": latest_features,
            "finbert_sentiment": finbert_sentiment,
            "lm_dictionary_sentiment": lm_dictionary_sentiment,
            "ncf_live_overlay": ncf_live_overlay,
            "factor_lens_gate": factor_lens_gate,
            "tbrain_shadow": tbrain_shadow,
        }
    )
    target_weights, ncf_live_overlay = _apply_bearish_high_risk_trim(
        target_weights,
        latest_features,
        signal_alignment,
        ncf_live_overlay,
    )
    market_state = classify_market_state(
        execution_regime,
        latest_features,
        signal_alignment=signal_alignment,
    )
    execution_risk = _execution_risk_assessment(
        execution_allowed=execution_allowed,
        business_stale=business_stale,
        calendar_stale=calendar_stale,
        optional_warnings=optional_warnings,
        target_weights=target_weights,
        latest_features=latest_features,
        ncf_live_overlay=ncf_live_overlay,
        finbert_sentiment=finbert_sentiment,
    )
    signal_alerts = _build_signal_alerts(
        strategy_id=str(report["active_strategy_id"]),
        actual_date=actual,
        execution_allowed=execution_allowed,
        execution_regime=execution_regime,
        changed_today=changed_today,
        execution_risk=execution_risk,
        latest_features=latest_features,
        finbert_sentiment=finbert_sentiment,
        factor_lens_gate=factor_lens_gate,
        ncf_live_signal=ncf_live_signal,
        ncf_live_overlay=ncf_live_overlay,
        signal_alignment=signal_alignment,
        ncf_panel_coverage=report.get("ncf_panel_coverage"),
    )
    target_shares = {
        ticker: (
            int((portfolio_value * target_weights.get(ticker, 0.0)) // latest_prices[ticker])
            if latest_prices.get(ticker, 0.0) > 0.0
            else 0
        )
        for ticker in TICKERS
    }
    target_market_values = {
        ticker: target_shares[ticker] * latest_prices.get(ticker, 0.0)
        for ticker in TICKERS
    }
    estimated_cash_after_rounding = portfolio_value - sum(target_market_values.values())
    return {
        "signal_version": 2,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "strategy_id": report["active_strategy_id"],
        "strategy_status": report["status"],
        "requested_as_of_date": str(as_of.date()),
        "actual_data_date": str(actual.date()),
        "business_stale_days": business_stale,
        "calendar_stale_days": calendar_stale,
        "max_business_stale_days": max_business_stale_days,
        "execution_allowed": execution_allowed,
        "execution_guard_reasons": [
            reason
            for condition, reason in (
                (business_stale > max_business_stale_days, f"OHLCV is {business_stale} business days stale"),
                (bool(missing_tickers), f"missing OHLCV tickers: {missing_tickers}"),
                (bool(ticker_misaligned), f"OHLCV dates do not align: {ticker_misaligned}"),
                (bool(optional_blocks), f"required strategy sources are stale or missing: {optional_blocks}"),
                (report["status"] != "active", f"strategy status is {report['status']}; shadow signals are non-executable"),
            )
            if condition
        ],
        "execution_warning_reasons": [
            reason
            for condition, reason in (
                (bool(optional_warnings), f"soft strategy sources are stale or missing: {optional_warnings}"),
            )
            if condition
        ] + ncf_warnings,
        "base_regime": base_regime,
        "execution_regime": execution_regime,
        "regime_reason": reason,
        "last_transition_date": str(transition_date.date()),
        "strategy_transition_today": changed_today,
        "action": "rebalance_to_target" if changed_today else "hold_or_align_to_target",
        "target_weights": target_weights,
        "target_values": {key: portfolio_value * value for key, value in target_weights.items()},
        "reference_target_shares_before_cost": target_shares,
        "reference_target_market_values": target_market_values,
        "estimated_cash_after_rounding_before_cost": estimated_cash_after_rounding,
        "latest_prices": latest_prices,
        "symbol_metadata": build_symbol_metadata(tuple(target_weights.keys())),
        "portfolio_value_input": float(portfolio_value),
        "latest_features": latest_features,
        "market_state": market_state,
        "execution_risk": execution_risk,
        "signal_alerts": signal_alerts,
        "signal_alignment": signal_alignment,
        "finbert_sentiment": finbert_sentiment,
        "lm_dictionary_sentiment": lm_dictionary_sentiment,
        "tbrain_shadow": tbrain_shadow,
        "ncf_live_overlay": ncf_live_overlay,
        "factor_lens_gate": factor_lens_gate,
        "data_freshness": source_freshness,
        "manifest": str(manifest_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--portfolio-value", type=float, default=1_000_000.0)
    parser.add_argument("--max-business-stale-days", type=int, default=3)
    parser.add_argument("--lookback-days", type=int, default=730)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_LATEST_STRATEGY))
    parser.add_argument("--output", default="results/group_a_plus_live_signal_v2.json")
    parser.add_argument("--latest-pointer", default=str(DEFAULT_LIVE_SIGNAL))
    args = parser.parse_args()
    std = OutputStandardizer("group_a_plus.operations.daily_signal")
    try:
        signal = build_daily_signal(
            args.as_of,
            args.portfolio_value,
            args.max_business_stale_days,
            args.lookback_days,
            Path(args.db),
            Path(args.manifest),
        )
        payload = std.success(signal)
    except Exception as exc:
        payload = std.error(exc)
    write_standard_output(payload, args.output)
    write_standard_output(payload, args.latest_pointer)
    print(f"Live signal: {Path(args.output).resolve()}")
    print(f"Latest pointer: {Path(args.latest_pointer).resolve()}")


if __name__ == "__main__":
    main()
