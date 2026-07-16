#!/usr/bin/env python3
"""Build an alert-only 00631L crash-risk snapshot.

This uses the conservative 2-of-3 multi-source stress rule from
evaluate_00631l_multisource_crash_risk.py. It is advisory-only: no target
weights, execution gate, or live signal decision is changed here.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH
from scripts.evaluate.evaluate_00631l_multisource_crash_risk import (
    FAMILY_STRESS_CONDITIONS,
    build_multisource_features,
    family_condition_flags_for_row,
    _load_external_close,
)
from scripts.evaluate.evaluate_group_a_plus_00631l_downside_race_classifier import _load_ohlc

DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "crash_risk_alert.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report" / "group_a_plus" / "crash_risk_alert" / "history"

FAMILY_COLUMNS = {
    "options_tail": [
        "txo_pcr_volume_z20",
        "txo_pcr_oi_z20",
        "txo_foreign_put_call_net_oi_chg5_z60",
    ],
    "liquidity_forced_selling": [
        "market_margin_forced_repay_z60",
        "market_margin_balance_chg20_z252",
        "securities_lending_0050_volume_z60",
    ],
    "cross_market_shock": [
        "vix_level_z60",
        "vix_chg5_z60",
        "soxx_ret1",
        "soxx_realized_vol20_z60",
        "soxx_downside_vol20_z60",
        "vix_soxx_realized_vol_gap_z60",
        "soxx_atm_iv30_raw",
        "soxx_options_dte",
        "soxx_options_contract_count",
        "soxx_put_call_iv_skew_raw",
        "soxx_put_call_volume_ratio_raw",
        "soxx_put_call_oi_ratio_raw",
        "soxx_atm_iv30_z252",
        "soxx_iv_rank_252",
        "soxx_iv_minus_rv20_z252",
        "soxx_put_call_iv_skew_z252",
        "soxx_put_call_volume_ratio_z60",
        "soxx_put_call_oi_ratio_z60",
        "qqq_ret1",
        "us_taiwan_gap1",
        "usdtwd_ret5_z60",
    ],
}

CONDITION_LABELS = {
    "txo_pcr_volume_z20_ge_1": "TXO market put/call volume ratio is elevated",
    "txo_pcr_oi_z20_ge_1": "TXO market put/call open-interest ratio is elevated",
    "txo_foreign_put_call_net_oi_chg5_z60_ge_1": "Foreign TXO put-vs-call net OI increased sharply",
    "market_margin_forced_repay_z60_ge_1": "Market margin repayment pressure is elevated",
    "market_margin_balance_chg20_z252_le_minus_1": "Market margin balance has contracted sharply",
    "securities_lending_0050_volume_z60_ge_1": "0050 securities-lending volume is elevated",
    "vix_level_z60_ge_1": "VIX level is elevated",
    "vix_chg5_z60_ge_1": "VIX 5-day change is elevated",
    "soxx_ret1_le_minus_3pct": "SOXX fell more than 3% on the prior US session",
    "soxx_realized_vol20_z60_ge_1": "SOXX 20-day realized volatility is elevated",
    "soxx_downside_vol20_z60_ge_1": "SOXX 20-day downside volatility is elevated",
    "vix_soxx_realized_vol_gap_z60_ge_1": "VIX implied-risk proxy is elevated versus SOXX realized volatility",
    "soxx_atm_iv30_raw_ge_55pct": "SOXX 30-day ATM implied volatility is above 55%",
    "soxx_put_call_volume_ratio_raw_ge_3": "SOXX options put/call volume ratio is above 3",
    "soxx_put_call_oi_ratio_raw_ge_3": "SOXX options put/call open-interest ratio is above 3",
    "soxx_atm_iv30_z252_ge_1": "SOXX 30-day ATM implied volatility is elevated",
    "soxx_iv_rank_252_ge_80pct": "SOXX implied-volatility rank is above 80%",
    "soxx_iv_minus_rv20_z252_ge_1": "SOXX implied volatility is elevated versus realized volatility",
    "soxx_put_call_iv_skew_z252_ge_1": "SOXX put-call implied-volatility skew is elevated",
    "soxx_put_call_volume_ratio_z60_ge_1": "SOXX options put/call volume ratio is elevated",
    "soxx_put_call_oi_ratio_z60_ge_1": "SOXX options put/call open-interest ratio is elevated",
    "qqq_ret1_le_minus_2_5pct": "QQQ fell more than 2.5% on the prior US session",
    "us_taiwan_gap1_le_minus_3pct": "SOXX underperformed TWII by more than 3% on the prior session",
    "usdtwd_ret5_z60_ge_1": "USD/TWD 5-day move indicates Taiwan FX risk-off",
}

FAMILY_LABELS = {
    "options_tail": "Options tail demand",
    "liquidity_forced_selling": "Liquidity / forced selling",
    "cross_market_shock": "Cross-market shock",
}

# cross_market_shock mixes plain price/FX risk-off signals with SOXX
# options-implied-volatility signals. These do not change the family's
# 2-of-3 vote (still one family, one flag) -- this only controls how active
# reasons are grouped in human-readable output, so price/FX moves and
# options-market stress aren't lumped into one indistinguishable line.
CROSS_MARKET_SUBFAMILY = {
    "vix_level_z60_ge_1": "cross_market_price_fx",
    "vix_chg5_z60_ge_1": "cross_market_price_fx",
    "soxx_ret1_le_minus_3pct": "cross_market_price_fx",
    "soxx_realized_vol20_z60_ge_1": "cross_market_price_fx",
    "soxx_downside_vol20_z60_ge_1": "cross_market_price_fx",
    "qqq_ret1_le_minus_2_5pct": "cross_market_price_fx",
    "us_taiwan_gap1_le_minus_3pct": "cross_market_price_fx",
    "usdtwd_ret5_z60_ge_1": "cross_market_price_fx",
    "vix_soxx_realized_vol_gap_z60_ge_1": "cross_market_implied_vol",
    "soxx_atm_iv30_raw_ge_55pct": "cross_market_implied_vol",
    "soxx_put_call_volume_ratio_raw_ge_3": "cross_market_implied_vol",
    "soxx_put_call_oi_ratio_raw_ge_3": "cross_market_implied_vol",
    "soxx_atm_iv30_z252_ge_1": "cross_market_implied_vol",
    "soxx_iv_rank_252_ge_80pct": "cross_market_implied_vol",
    "soxx_iv_minus_rv20_z252_ge_1": "cross_market_implied_vol",
    "soxx_put_call_iv_skew_z252_ge_1": "cross_market_implied_vol",
    "soxx_put_call_volume_ratio_z60_ge_1": "cross_market_implied_vol",
    "soxx_put_call_oi_ratio_z60_ge_1": "cross_market_implied_vol",
}

CROSS_MARKET_SUBFAMILY_LABELS = {
    "cross_market_price_fx": "Cross-market price/FX",
    "cross_market_implied_vol": "Cross-market implied volatility",
}

# Raw external_market_ohlcv tickers backing cross_market_shock. The engineered
# feature columns for this family are forward-filled (to bridge US/TW calendar
# gaps) before z-scoring, so checking their non-null dates cannot detect
# staleness. Freshness for this family must be computed from these raw,
# non-ffilled closes instead.
CROSS_MARKET_RAW_TICKERS = ["^VIX", "SOXX", "QQQ", "^TWII", "TSM", "TWD=X"]

# Raw source tables backing options_tail / liquidity_forced_selling. Each
# family mixes columns from more than one underlying table with independent
# refresh cadences (e.g. options_tail's txo_pcr_*_z20 come from
# taifex_options_daily, but txo_foreign_put_call_net_oi_chg5_z60 comes from
# derivative_institutional_data). Checking the engineered feature columns'
# non-null dates picks whichever source is freshest and hides the other
# going stale (the same masking pattern as cross_market_shock's ffill issue,
# just without the ffill). Freshness must be the worst-case (oldest) date
# across each family's raw sources, not the best-case.
RAW_FRESHNESS_SOURCES: dict[str, list[tuple[str, str]]] = {
    "options_tail": [
        ("taifex_options_daily", "contract = 'TXO' AND trading_session = '一般'"),
        ("derivative_institutional_data", "product_id IN ('TX', 'TXO') AND institutional_investors = '外資'"),
    ],
    "liquidity_forced_selling": [
        ("market_margin_data", "1=1"),
        ("securities_lending_data", "ticker = '0050.TW'"),
    ],
}


def _raw_table_latest_date(db_path: Path, table: str, where_sql: str, as_of_dt: pd.Timestamp) -> str | None:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        if table not in tables:
            return None
        row = con.execute(
            f"SELECT max(dt) FROM {table} WHERE {where_sql} AND dt <= ?",
            [str(as_of_dt.date())],
        ).fetchone()
    finally:
        con.close()
    if row is None or row[0] is None:
        return None
    return str(pd.Timestamp(row[0]).date())


def _raw_sources_worst_case_date(db_path: Path, sources: list[tuple[str, str]], as_of_dt: pd.Timestamp) -> str | None:
    dates = []
    for table, where_sql in sources:
        found = _raw_table_latest_date(db_path, table, where_sql, as_of_dt)
        if found is not None:
            dates.append(pd.Timestamp(found))
    if not dates:
        return None
    return str(min(dates).date())


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _has_family_data(features: pd.DataFrame) -> pd.Series:
    ok = pd.Series(True, index=features.index)
    for cols in FAMILY_COLUMNS.values():
        available = features[[col for col in cols if col in features.columns]].notna().any(axis=1)
        ok = ok & available
    return ok


def _resolve_as_of(features: pd.DataFrame, requested: str) -> pd.Timestamp:
    valid_index = features.index[_has_family_data(features)]
    if len(valid_index) == 0:
        raise ValueError("No feature date has all crash-risk source families available")
    if str(requested).lower() == "latest":
        return pd.Timestamp(valid_index.max())
    target = pd.Timestamp(requested)
    eligible = valid_index[valid_index <= target]
    if len(eligible) == 0:
        raise ValueError(f"No available feature date on or before {requested}")
    return pd.Timestamp(eligible.max())


def _float_or_none(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _latest_non_null_date(features: pd.DataFrame, columns: list[str]) -> str | None:
    dates = []
    for col in columns:
        if col in features and features[col].notna().any():
            dates.append(features[col].dropna().index.max())
    if not dates:
        return None
    return str(max(dates).date())


def _latest_non_null_date_at_or_before(features: pd.DataFrame, columns: list[str], as_of_dt: pd.Timestamp) -> str | None:
    dates = []
    for col in columns:
        if col not in features:
            continue
        series = features.loc[features.index <= as_of_dt, col].dropna()
        if not series.empty:
            dates.append(series.index.max())
    if not dates:
        return None
    return str(max(dates).date())


def _history_path(history_dir: Path, as_of_dt: pd.Timestamp) -> Path:
    return history_dir / f"{as_of_dt.strftime('%Y%m%d')}.json"


def _load_previous_snapshot(history_dir: Path | None, as_of_dt: pd.Timestamp) -> dict[str, Any] | None:
    if history_dir is None or not history_dir.exists():
        return None
    candidates = []
    for path in history_dir.glob("*.json"):
        try:
            dt = pd.Timestamp(path.stem)
        except Exception:
            continue
        if dt < as_of_dt:
            candidates.append((dt, path))
    if not candidates:
        return None
    _dt, path = max(candidates, key=lambda item: item[0])
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _cross_market_raw_latest_date(db_path: Path, as_of_dt: pd.Timestamp) -> str | None:
    raw = _load_external_close(db_path, CROSS_MARKET_RAW_TICKERS)
    if raw.empty:
        return None
    raw = raw.loc[raw.index <= as_of_dt]
    # Worst-case (oldest) last-update date across tickers: ^TWII updates on
    # the Taiwan calendar while VIX/SOXX/QQQ/TSM/TWD=X update on the US
    # calendar, so taking the newest ticker would mask US-side staleness.
    per_ticker_dates = []
    for ticker in CROSS_MARKET_RAW_TICKERS:
        if ticker not in raw.columns:
            continue
        valid = raw[ticker].dropna()
        if not valid.empty:
            per_ticker_dates.append(valid.index.max())
    if not per_ticker_dates:
        return None
    return str(min(per_ticker_dates).date())


def _family_freshness(features: pd.DataFrame, as_of_dt: pd.Timestamp, db_path: Path) -> dict[str, Any]:
    by_family = {}
    stale_count = 0
    for name, cols in FAMILY_COLUMNS.items():
        if name == "cross_market_shock":
            # The engineered columns are forward-filled, so their non-null
            # dates cannot reveal staleness. Use the raw source closes.
            family_date = _cross_market_raw_latest_date(db_path, as_of_dt)
        elif name in RAW_FRESHNESS_SOURCES:
            # This family mixes columns from multiple raw tables; the
            # engineered columns' non-null dates would pick whichever table
            # is freshest and hide the others going stale.
            family_date = _raw_sources_worst_case_date(db_path, RAW_FRESHNESS_SOURCES[name], as_of_dt)
        else:
            family_date = _latest_non_null_date_at_or_before(features, cols, as_of_dt)
        lag_days = None
        stale = True
        if family_date is not None:
            lag_days = int((as_of_dt.normalize() - pd.Timestamp(family_date).normalize()).days)
            stale = lag_days > 1
        stale_count += int(stale)
        by_family[name] = {
            "latest_date_at_or_before_as_of": family_date,
            "lag_days_vs_as_of": lag_days,
            "stale": stale,
        }
    return {
        "status": "degraded" if stale_count else "ok",
        "stale_family_count": stale_count,
        "families": by_family,
    }


def _soxx_iv_health(db_path: Path, as_of_dt: pd.Timestamp) -> dict[str, Any]:
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
            if "external_options_iv" not in tables:
                return {"status": "unavailable", "reason": "external_options_iv table missing"}
            latest = con.execute(
                """
                SELECT *
                FROM external_options_iv
                WHERE provider = 'yfinance' AND underlying = 'SOXX'
                ORDER BY dt DESC
                LIMIT 1
                """
            ).fetchdf()
            asof = con.execute(
                """
                SELECT *
                FROM external_options_iv
                WHERE provider = 'yfinance' AND underlying = 'SOXX' AND dt <= ?
                ORDER BY dt DESC
                LIMIT 1
                """,
                [str(as_of_dt.date())],
            ).fetchdf()
        finally:
            con.close()
    except Exception as exc:
        return {"status": "unavailable", "reason": f"query_failed: {exc}"}

    if latest.empty:
        return {"status": "unavailable", "reason": "no SOXX IV snapshots"}

    row = latest.iloc[0]
    latest_dt = pd.Timestamp(row["dt"]).normalize()
    generated_dt = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    lag_days = int((generated_dt - latest_dt).days)
    warnings: list[str] = []
    dte = _float_or_none(row.get("dte"))
    atm_iv = _float_or_none(row.get("atm_iv"))
    contract_count = _float_or_none(row.get("contract_count"))
    put_call_volume = _float_or_none(row.get("put_call_volume_ratio"))
    put_call_oi = _float_or_none(row.get("put_call_oi_ratio"))

    if lag_days > 3:
        warnings.append("latest_snapshot_stale_gt_3_calendar_days")
    if dte is None or dte < 7 or dte > 60:
        warnings.append("dte_outside_7_60")
    if atm_iv is None or atm_iv < 0.05 or atm_iv > 2.0:
        warnings.append("atm_iv_outside_5pct_200pct")
    if contract_count is None or contract_count < 20:
        warnings.append("low_contract_count")
    if put_call_volume is not None and put_call_volume > 20:
        warnings.append("put_call_volume_ratio_extreme")
    if put_call_oi is not None and put_call_oi > 20:
        warnings.append("put_call_oi_ratio_extreme")

    asof_available = not asof.empty
    if not asof_available:
        warnings.append("no_snapshot_at_or_before_alert_as_of")

    return {
        "status": "ok" if not warnings else "warning",
        "warnings": warnings,
        "latest_snapshot": {
            "date": str(latest_dt.date()),
            "lag_days_vs_generated_date": lag_days,
            "spot": _float_or_none(row.get("spot")),
            "expiry": str(pd.Timestamp(row["expiry"]).date()) if pd.notna(row.get("expiry")) else None,
            "dte": dte,
            "atm_iv": atm_iv,
            "put_call_iv_skew": _float_or_none(row.get("put_call_iv_skew")),
            "put_call_volume_ratio": put_call_volume,
            "put_call_oi_ratio": put_call_oi,
            "contract_count": contract_count,
        },
        "as_of_snapshot": (
            None
            if asof.empty
            else {
                "date": str(pd.Timestamp(asof.iloc[0]["dt"]).date()),
                "atm_iv": _float_or_none(asof.iloc[0].get("atm_iv")),
                "put_call_volume_ratio": _float_or_none(asof.iloc[0].get("put_call_volume_ratio")),
                "put_call_oi_ratio": _float_or_none(asof.iloc[0].get("put_call_oi_ratio")),
            }
        ),
    }


def _category_flags(row: pd.Series) -> tuple[dict[str, bool], dict[str, Any]]:
    # Thresholds live in evaluate_00631l_multisource_crash_risk.FAMILY_STRESS_CONDITIONS
    # (single source of truth -- see the Fable audit note there).
    details = {family: family_condition_flags_for_row(row, family) for family in FAMILY_STRESS_CONDITIONS}
    flags = {family: any(conditions.values()) for family, conditions in details.items()}
    return flags, details


def _active_reason_lines(details: dict[str, Any]) -> list[str]:
    lines = []
    for family, conditions in details.items():
        if family == "cross_market_shock":
            # Split into price/FX vs options-implied-volatility subfamilies
            # so a plain risk-off move and an options-market stress signal
            # aren't lumped into one indistinguishable line. This is a
            # presentation-only split -- the family still casts one vote in
            # the 2-of-3 ensemble.
            by_subfamily: dict[str, list[str]] = {}
            for name, value in conditions.items():
                if not value:
                    continue
                subfamily = CROSS_MARKET_SUBFAMILY.get(name, "cross_market_price_fx")
                by_subfamily.setdefault(subfamily, []).append(CONDITION_LABELS.get(name, name))
            for subfamily, active in by_subfamily.items():
                lines.append(f"{CROSS_MARKET_SUBFAMILY_LABELS.get(subfamily, subfamily)}: " + "; ".join(active))
            continue
        active = [CONDITION_LABELS.get(name, name) for name, value in conditions.items() if value]
        if active:
            lines.append(f"{FAMILY_LABELS.get(family, family)}: " + "; ".join(active))
    return lines


def _as_of_advancement_blocking(features: pd.DataFrame, as_of_dt: pd.Timestamp, max_dates: int = 15) -> dict[str, Any]:
    """Explain which family/families are keeping `as_of` from advancing.

    `_resolve_as_of` only accepts a date once every family has at least one
    non-null column on it (`_has_family_data`). This reports, for the next
    dates already present in `features.index` (i.e. 00631L.TW trading days)
    after `as_of`, which family is still missing data there -- so a stuck
    `as_of` can be attributed to a specific source instead of investigated
    from scratch each time.
    """
    candidates = features.index[features.index > as_of_dt][:max_dates]
    blocked = []
    for dt in candidates:
        missing = []
        for name, cols in FAMILY_COLUMNS.items():
            available_cols = [c for c in cols if c in features.columns]
            has_data = bool(available_cols) and bool(features.loc[dt, available_cols].notna().any())
            if not has_data:
                missing.append(name)
        if missing:
            blocked.append({"date": str(dt.date()), "missing_families": missing})
    return {
        "as_of": str(as_of_dt.date()),
        "latest_available_feature_date": str(features.index.max().date()) if len(features.index) else None,
        "blocked_dates": blocked,
    }


def _watch_level(score: int) -> str:
    if score >= 3:
        return "high"
    if score == 2:
        return "medium"
    if score == 1:
        return "watch"
    return "none"


def build_crash_risk_alert(
    *,
    db_path: Path,
    feature_start: str,
    as_of: str,
    history_dir: Path | None = DEFAULT_HISTORY_DIR,
) -> dict[str, Any]:
    ohlc = _load_ohlc(db_path, "00631L.TW", feature_start, "2100-01-01")
    if ohlc.empty:
        raise ValueError("No 00631L.TW OHLC rows available")
    features = build_multisource_features(db_path, ohlc.index)
    as_of_dt = _resolve_as_of(features, as_of)
    row = features.loc[as_of_dt]
    flags, details = _category_flags(row)
    score = int(sum(1 for active in flags.values() if active))
    previous = _load_previous_snapshot(history_dir, as_of_dt)
    previous_score = int(previous.get("category_score", 0) or 0) if isinstance(previous, dict) else 0
    previous_as_of = str(previous.get("as_of") or "") if isinstance(previous, dict) else None
    persistent_2of3 = score >= 2 and previous_score >= 2
    immediate_high = score >= 3
    alert_active = immediate_high or persistent_2of3
    watch_level = _watch_level(score)
    alert_level = "high" if immediate_high else "medium" if alert_active else None
    active_names = [name for name, active in flags.items() if active]
    reason_lines = _active_reason_lines(details)
    freshness = _family_freshness(features, as_of_dt, db_path)
    soxx_iv_health = _soxx_iv_health(db_path, as_of_dt)
    as_of_advancement = _as_of_advancement_blocking(features, as_of_dt)
    manual_review = {
        "recommended_action": (
            "manual_review_consider_pause_new_00631l_adds"
            if alert_active
            else "watch_only_no_action"
            if score == 1
            else "none"
        ),
        "do_not_auto_sell": True,
        "do_not_auto_deleverage": True,
        "no_buy_advisory": bool(alert_active),
        "rationale": reason_lines,
    }
    alert = None
    if alert_active:
        alert = {
            "type": "00631l_multisource_crash_risk",
            "level": alert_level,
            "title": "00631L multi-source crash-risk alert",
            "reason": (
                f"{score}/3 crash-risk source families are active"
                + (", including all families" if score >= 3 else f": {', '.join(active_names)}")
                + ". Advisory only; no automatic de-risk."
            ),
            "metadata": {
                "trade_policy": "advisory_no_auto_weight_change",
                "recommended_action": manual_review["recommended_action"],
                "auto_deleverage": False,
                "no_buy_advisory": True,
                "category_score": score,
                "category_flags": flags,
                "active_reasons": reason_lines,
                "as_of": str(as_of_dt.date()),
                "persistence": {
                    "previous_as_of": previous_as_of,
                    "previous_score": previous_score,
                    "persistent_2of3": persistent_2of3,
                    "immediate_high": immediate_high,
                },
            },
        }
    return {
        "schema_version": 1,
        "generated_at": _utc_now_iso(),
        "status": "available",
        "policy": "alert_only_no_auto_weight_change",
        "as_of": str(as_of_dt.date()),
        "requested_as_of": as_of,
        "watch_level": watch_level,
        "alert_level": alert_level,
        "alert_active": alert_active,
        "category_score": score,
        "category_flags": flags,
        "condition_details": details,
        "active_reason_lines": reason_lines,
        "manual_review": manual_review,
        "persistence": {
            "previous_as_of": previous_as_of,
            "previous_score": previous_score,
            "persistent_2of3": persistent_2of3,
            "immediate_high": immediate_high,
        },
        "latest_source_dates": {
            name: _latest_non_null_date(features, cols) for name, cols in FAMILY_COLUMNS.items()
        },
        "freshness": freshness,
        "soxx_iv_health": soxx_iv_health,
        "as_of_advancement": as_of_advancement,
        "feature_values": {col: _float_or_none(row.get(col)) for cols in FAMILY_COLUMNS.values() for col in cols},
        "signal_alert": alert,
        "research_context": {
            "source_script": "scripts/evaluate/evaluate_00631l_multisource_crash_risk.py",
            "promotion_status": "not_promoted_to_trading_rule",
            "reason": "2-of-3 ensemble had only local 2018 OOS value and failed broader trading validation.",
        },
    }


def write_crash_risk_alert(payload: dict[str, Any], *, output_path: Path, history_dir: Path = DEFAULT_HISTORY_DIR) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    as_of = payload.get("as_of")
    if isinstance(as_of, str) and as_of:
        history_dir.mkdir(parents=True, exist_ok=True)
        _history_path(history_dir, pd.Timestamp(as_of)).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--feature-start", default="2016-01-04")
    parser.add_argument("--as-of", default="latest")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    parser.add_argument("--no-history", action="store_true")
    args = parser.parse_args()

    payload = build_crash_risk_alert(
        db_path=args.db.resolve(),
        feature_start=args.feature_start,
        as_of=args.as_of,
        history_dir=None if args.no_history else args.history_dir,
    )
    if args.no_history:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        write_crash_risk_alert(payload, output_path=args.output, history_dir=args.history_dir)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
