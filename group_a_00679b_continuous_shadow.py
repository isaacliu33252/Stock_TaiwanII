#!/usr/bin/env python3
"""FinRL-Meta-style continuous overlay shadow for Group A + 00679B.

This script is intentionally outside the Golden1 production path.  It reads an
existing Group A signal JSON, adds a portfolio-level 00679B sleeve, applies a
simple last-action turnover control, and exports execution-cost/batch estimates.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

from backtest_group_a_plus_overlay import (
    _apply_group_a_plus_risk_overlays,
    _fast_risk_off_overlay,
    _leverage_stop_cooldown_overlay,
)

try:
    import yfinance as yf

    _HAS_YFINANCE = True
except Exception:
    _HAS_YFINANCE = False


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SIGNAL_JSON = PROJECT_ROOT / "results" / "group_a_meta_ensemble_shadow_live_latest.json"
DEFAULT_GROUP_A_PLUS_CONFIG = PROJECT_ROOT / "group_a_plus_config.json"
DEFAULT_00679B_CACHE = (
    PROJECT_ROOT
    / "FinRL"
    / "data"
    / "portfolio_cache"
    / "00679B_TWO_20200101_20260604_1d_raw_v1.parquet"
)
DEFAULT_CACHE_DIR = PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache"
RISK_OVERLAY_CACHE_STEMS = {
    "0050.TW": "0050_TW",
    "00631L.TW": "00631L_TW",
    "00632R.TW": "00632R_TW",
    "00679B.TWO": "00679B_TWO",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a Group A + 00679B continuous overlay shadow recommendation."
    )
    parser.add_argument("--signal-json", default=str(DEFAULT_SIGNAL_JSON))
    parser.add_argument("--group-a-plus-config", default=str(DEFAULT_GROUP_A_PLUS_CONFIG))
    parser.add_argument("--00679b-cache", dest="cache_00679b", default=str(DEFAULT_00679B_CACHE))
    parser.add_argument("--total-assets", type=float, required=True)
    parser.add_argument("--current-00679b-shares", type=int, required=True)
    parser.add_argument("--overlay-00679b-weight", type=float, default=None)
    parser.add_argument(
        "--dynamic-overlay",
        action="store_true",
        help="Choose the 00679B sleeve from group_a_plus_config dynamic weight bands.",
    )
    parser.add_argument(
        "--turnover-penalty",
        type=float,
        default=None,
        help=(
            "Shrink proposed weight changes toward last/current weights. "
            "0 keeps the raw target; 0.25 applies 75%% of each weight change. "
            "When omitted, execution_control.default_turnover_penalty_by_regime is used."
        ),
    )
    parser.add_argument(
        "--min-trade-value",
        type=float,
        default=0.0,
        help="Suppress trades whose estimated notional is below this value.",
    )
    parser.add_argument(
        "--disable-cash-constraint",
        action="store_true",
        help=(
            "Do not shrink buy orders when target shares plus estimated execution "
            "cost would leave negative cash."
        ),
    )
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--etf-sell-tax-rate", type=float, default=0.001)
    parser.add_argument(
        "--slippage-rate",
        type=float,
        default=0.0005,
        help="Simple one-way slippage estimate on traded notional.",
    )
    parser.add_argument(
        "--batch-count",
        type=int,
        default=3,
        help="Number of execution batches for non-trivial trades.",
    )
    parser.add_argument(
        "--batch-threshold",
        type=float,
        default=100000.0,
        help="Trades at or above this notional are split into batches.",
    )
    parser.add_argument("--output-prefix", default=None)
    return parser.parse_args()


def _load_json(path: str | Path) -> dict:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = (PROJECT_ROOT / candidate).resolve()
    return json.loads(candidate.read_text(encoding="utf-8"))


def _fetch_vix(actual_date: str) -> float | None:
    """Fetch the most recent VIX close price before or on actual_date."""
    if not _HAS_YFINANCE:
        return None
    try:
        end = (pd.Timestamp(actual_date) + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        df = yf.download("^VIX", start="2020-01-01", end=end, auto_adjust=True, progress=False)
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index).normalize()
        dates = df.index.strftime("%Y-%m-%d")
        mask = dates <= actual_date
        if not mask.any():
            return None
        return float(df.loc[mask, "Close"].iloc[-1])
    except Exception:
        return None


def _fetch_turbulence(prices_df: pd.DataFrame, current_date: str) -> float:
    """Calculate turbulence index from price DataFrame up to current_date."""
    pivot = prices_df.loc[:current_date].copy()
    if len(pivot) < 60:
        return 0.0
    returns = pivot.pct_change().dropna()
    if returns.empty or returns.shape[1] < 2:
        return 0.0
    window = returns.iloc[-min(len(returns), 252):]
    if len(window) < 20:
        return 0.0
    try:
        cov = window.cov()
        current_ret = returns.iloc[-1].values
        inv_cov = pd.DataFrame(np.linalg.pinv(cov.values), cov.columns, cov.index)
        turbulence_val = float(current_ret @ inv_cov @ current_ret.T)
        return max(float(turbulence_val), 0.0)
    except Exception:
        return 0.0


def _infer_group_a_plus_regime(signal: dict, config: dict | None = None) -> tuple[str, dict]:
    source_event = dict(signal.get("source_event", {}) or {})
    overlay = dict(source_event.get("overlay", {}) or {})
    regime = str(source_event.get("regime") or overlay.get("tdcc_state") or "").lower()
    tdcc_state = str(overlay.get("tdcc_state") or "").lower()
    reason = str(signal.get("signal_reason") or "").lower()
    if bool(overlay.get("severe_inverse_allowed")):
        return "severe", {"upgrade_reason": "severe_inverse_allowed", "vix_override": None, "turbulence_override": None}
    if regime in {"severe", "risk_off", "caution", "risk_on"}:
        base_regime = regime
    elif tdcc_state in {"severe", "risk_off", "caution", "risk_on"}:
        base_regime = tdcc_state
    elif "risk_off" in reason:
        base_regime = "risk_off"
    elif "caution" in reason:
        base_regime = "caution"
    else:
        base_regime = "risk_on"

    upgrade_reason = None
    vix_override = None
    turbulence_override = None

    if config is not None:
        vix_cfg = dict(config.get("vix_regime_control", {}) or {})
        turb_cfg = dict(config.get("turbulence_control", {}) or {})

        vix = _fetch_vix(str(signal.get("actual_data_date") or "")) if vix_cfg.get("enabled", False) else None
        if vix is not None:
            vix_threshold_risk_off = float(vix_cfg.get("threshold_risk_off", 25.0))
            vix_threshold_severe = float(vix_cfg.get("threshold_severe", 35.0))
            if vix >= vix_threshold_severe:
                if base_regime in {"risk_on", "caution"}:
                    base_regime = "severe"
                    upgrade_reason = f"vix={vix:.1f}>=severe_threshold={vix_threshold_severe}"
                    vix_override = "severe"
            elif vix >= vix_threshold_risk_off:
                if base_regime == "risk_on":
                    base_regime = "risk_off"
                    upgrade_reason = f"vix={vix:.1f}>=risk_off_threshold={vix_threshold_risk_off}"
                    vix_override = "risk_off"
                elif base_regime == "caution":
                    base_regime = "risk_off"
                    upgrade_reason = f"vix={vix:.1f}>=risk_off_threshold={vix_threshold_risk_off}"
                    vix_override = "risk_off"

        prices_df = signal.get("_prices_df")
        if prices_df is not None and turb_cfg.get("enabled", False) and turb_cfg.get("override_regime"):
            turb_val = _fetch_turbulence(prices_df, str(signal.get("actual_data_date") or ""))
            turb_thresh_risk_off = float(turb_cfg.get("threshold_risk_off", 50.0))
            turb_thresh_severe = float(turb_cfg.get("threshold_severe", 100.0))
            if turb_val >= turb_thresh_severe:
                if base_regime in {"risk_on", "caution", "risk_off"}:
                    base_regime = "severe"
                    upgrade_reason = f"turbulence={turb_val:.2f}>=severe_threshold={turb_thresh_severe}"
                    turbulence_override = "severe"
            elif turb_val >= turb_thresh_risk_off:
                if base_regime == "risk_on":
                    base_regime = "risk_off"
                    upgrade_reason = f"turbulence={turb_val:.2f}>=risk_off_threshold={turb_thresh_risk_off}"
                    turbulence_override = "risk_off"

    return base_regime, {
        "upgrade_reason": upgrade_reason,
        "vix_override": vix_override,
        "turbulence_override": turbulence_override,
    }


def _resolve_ticker_cache(cache_dir: Path, ticker: str, actual_date: str) -> Path | None:
    stem = RISK_OVERLAY_CACHE_STEMS.get(ticker)
    if stem is None:
        return None
    actual_stamp = pd.Timestamp(actual_date).strftime("%Y%m%d")
    exact = cache_dir / f"{stem}_20200101_{actual_stamp}_1d_raw_v1.parquet"
    if exact.exists():
        return exact
    matches = sorted(cache_dir.glob(f"{stem}_20200101_*_1d_raw_v1.parquet"))
    actual = pd.Timestamp(actual_date).strftime("%Y-%m-%d")
    for candidate in reversed(matches):
        try:
            df = pd.read_parquet(candidate, columns=["date"])
        except Exception:
            continue
        dates = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        if bool((dates == actual).any()):
            return candidate
    return matches[-1] if matches else None


def _load_risk_overlay_prices(actual_date: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for ticker in ("0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"):
        cache_path = _resolve_ticker_cache(cache_dir, ticker, actual_date)
        if cache_path is None or not cache_path.exists():
            continue
        df = pd.read_parquet(cache_path)
        if "date" not in df.columns or "close" not in df.columns:
            continue
        dates = pd.to_datetime(df["date"]).dt.normalize()
        close = pd.to_numeric(df["close"], errors="coerce")
        s = pd.Series(close.values, index=dates, name=ticker).dropna()
        s = s[s.index <= pd.Timestamp(actual_date).normalize()]
        if not s.empty:
            series[ticker] = s
    if not series:
        return pd.DataFrame()
    return pd.concat(series.values(), axis=1).sort_index().ffill()


def _resolve_00679b_overlay_weight(
    *,
    signal: dict,
    config: dict,
    requested_weight: float | None,
    dynamic_overlay: bool,
) -> tuple[float, dict]:
    if requested_weight is not None and not dynamic_overlay:
        return float(requested_weight), {
            "mode": "manual",
            "regime": None,
            "source": "cli_overlay_00679b_weight",
        }

    regime, regime_info = _infer_group_a_plus_regime(signal, config)
    bands = dict(dict(config.get("overlay", {}) or {}).get("dynamic_weight_bands", {}) or {})
    if not bands:
        ref = dict(dict(config.get("overlay", {}) or {}).get("reference_static_mix", {}) or {})
        weight = float(ref.get("00679b_weight", 0.20))
        return weight, {
            "mode": "config_static_fallback",
            "regime": regime,
            "source": "reference_static_mix.00679b_weight",
        }
    weight = float(bands.get(regime, bands.get("risk_off", bands.get("caution", 0.20))))
    return weight, {
        "mode": "dynamic",
        "regime": regime,
        "source": f"dynamic_weight_bands.{regime}",
        "bands": bands,
    }


def _latest_00679b_price(cache_path: Path, actual_date: str) -> float:
    if not cache_path.exists():
        raise FileNotFoundError(f"00679B cache not found: {cache_path}")
    df = pd.read_parquet(cache_path)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    matched = df[df["date"] == actual_date]
    if matched.empty:
        raise RuntimeError(f"00679B price for {actual_date} not found in {cache_path}")
    return float(matched.iloc[-1]["close"])


def _resolve_00679b_cache(cache_path: Path, actual_date: str) -> Path:
    """Prefer the cache whose filename matches the signal's actual date."""
    if cache_path.exists():
        df = pd.read_parquet(cache_path, columns=["date"])
        actual = pd.Timestamp(actual_date).strftime("%Y-%m-%d")
        dates = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        if bool((dates == actual).any()):
            return cache_path

    cache_dir = cache_path.parent
    actual_stamp = pd.Timestamp(actual_date).strftime("%Y%m%d")
    exact = cache_dir / f"00679B_TWO_20200101_{actual_stamp}_1d_raw_v1.parquet"
    if exact.exists():
        return exact

    matches = sorted(cache_dir.glob("00679B_TWO_20200101_*_1d_raw_v1.parquet"))
    for candidate in reversed(matches):
        df = pd.read_parquet(candidate, columns=["date"])
        dates = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        if bool((dates == actual).any()):
            return candidate
    return cache_path


def _normalize_group_weights(signal: dict, group_a_sleeve_weight: float) -> dict[str, float]:
    target_weights = dict(signal["target_weights"])
    target_cash = float(signal["target_cash_weight"])
    out = {
        ticker: float(weight) * group_a_sleeve_weight
        for ticker, weight in target_weights.items()
    }
    out["cash"] = target_cash * group_a_sleeve_weight
    return out


def _apply_group_a_plus_leverage_control(
    weights: dict[str, float],
    *,
    config: dict,
    regime: str,
) -> tuple[dict[str, float], dict]:
    control = dict(config.get("leverage_control", {}) or {})
    ticker = str(control.get("ticker") or "00631L.TW")
    caps = dict(control.get("max_weight_by_regime", {}) or {})
    if not caps or ticker not in weights:
        return dict(weights), {
            "applied": False,
            "reason": "no_config_or_ticker_missing",
            "regime": regime,
            "ticker": ticker,
        }
    cap = float(caps.get(regime, caps.get("risk_off", weights.get(ticker, 0.0))))
    before = float(weights.get(ticker, 0.0))
    if before <= cap:
        return dict(weights), {
            "applied": False,
            "reason": "below_cap",
            "regime": regime,
            "ticker": ticker,
            "cap": cap,
            "before_weight": before,
            "after_weight": before,
            "released_weight": 0.0,
        }

    adjusted = dict(weights)
    released = before - cap
    adjusted[ticker] = cap
    release_to = str(control.get("release_to") or "cash")
    adjusted[release_to] = float(adjusted.get(release_to, 0.0)) + released
    return adjusted, {
        "applied": True,
        "reason": "capped_leverage_weight",
        "regime": regime,
        "ticker": ticker,
        "cap": cap,
        "before_weight": before,
        "after_weight": cap,
        "released_weight": released,
        "release_to": release_to,
    }


def _apply_group_a_plus_execution_control(
    current_shares: dict[str, int],
    target_shares: dict[str, int],
    *,
    config: dict,
    regime: str,
) -> tuple[dict[str, int], dict]:
    control = dict(config.get("execution_control", {}) or {})
    buy_fractions = dict(control.get("buy_fraction_by_regime", {}) or {})
    sell_fractions = dict(control.get("sell_fraction_by_regime", {}) or {})
    defensive_sell_fractions = dict(control.get("defensive_sleeve_sell_fraction_by_regime", {}) or {})
    defensive_ticker = str(dict(config.get("overlay", {}) or {}).get("ticker") or "00679B.TWO")
    if not buy_fractions and not sell_fractions:
        return dict(target_shares), {
            "applied": False,
            "reason": "no_execution_control_config",
            "regime": regime,
            "buy_fraction": 1.0,
            "sell_fraction": 1.0,
            "defensive_sleeve_sell_fraction": 1.0,
            "defensive_sleeve_ticker": defensive_ticker,
        }

    buy_fraction = min(max(float(buy_fractions.get(regime, buy_fractions.get("risk_off", 1.0))), 0.0), 1.0)
    sell_fraction = min(max(float(sell_fractions.get(regime, sell_fractions.get("risk_off", 1.0))), 0.0), 1.0)
    defensive_sell_fraction = min(
        max(float(defensive_sell_fractions.get(regime, defensive_sell_fractions.get("risk_off", sell_fraction))), 0.0),
        1.0,
    )
    adjusted: dict[str, int] = {}
    changed = False
    for ticker, target in target_shares.items():
        cur = int(current_shares.get(ticker, 0))
        target = int(target)
        delta = target - cur
        if delta > 0 and buy_fraction < 1.0:
            adjusted_target = cur + int(math.floor(delta * buy_fraction))
            changed = changed or adjusted_target != target
            adjusted[ticker] = adjusted_target
        elif delta < 0:
            active_sell_fraction = defensive_sell_fraction if ticker == defensive_ticker else sell_fraction
            adjusted_target = cur - int(math.floor(abs(delta) * active_sell_fraction))
            changed = changed or adjusted_target != target
            adjusted[ticker] = adjusted_target
        else:
            adjusted[ticker] = target

    return adjusted, {
        "applied": changed,
        "reason": "scaled_trade_deltas_by_regime" if changed else "fractions_keep_full_execution",
        "regime": regime,
        "buy_fraction": buy_fraction,
        "sell_fraction": sell_fraction,
        "defensive_sleeve_sell_fraction": defensive_sell_fraction,
        "defensive_sleeve_ticker": defensive_ticker,
        "target_shares_before_execution_control": dict(target_shares),
        "target_shares_after_execution_control": dict(adjusted),
    }


def _apply_group_a_plus_turnover_cap(
    current_shares: dict[str, int],
    target_shares: dict[str, int],
    prices: dict[str, float],
    *,
    config: dict,
    regime: str,
    total_assets: float,
) -> tuple[dict[str, int], dict]:
    control = dict(config.get("execution_control", {}) or {})
    caps = dict(control.get("max_turnover_ratio_by_regime", {}) or {})
    cap = caps.get(regime, caps.get("risk_off"))
    if cap is None:
        return dict(target_shares), {
            "applied": False,
            "reason": "no_turnover_cap_config",
            "regime": regime,
            "cap": None,
            "initial_turnover_ratio": None,
            "final_turnover_ratio": None,
            "turnover_scale": 1.0,
        }
    cap = max(float(cap), 0.0)
    turnover = sum(
        abs(int(target_shares.get(ticker, 0)) - int(current_shares.get(ticker, 0))) * float(price)
        for ticker, price in prices.items()
    )
    ratio = turnover / max(float(total_assets), 1.0)
    if ratio <= cap:
        return dict(target_shares), {
            "applied": False,
            "reason": "turnover_within_cap",
            "regime": regime,
            "cap": cap,
            "initial_turnover_ratio": ratio,
            "final_turnover_ratio": ratio,
            "turnover_scale": 1.0,
        }

    scale = cap / ratio if ratio > 0 else 1.0
    adjusted: dict[str, int] = {}
    for ticker in target_shares:
        cur = int(current_shares.get(ticker, 0))
        delta = int(target_shares.get(ticker, 0)) - cur
        if delta >= 0:
            adjusted[ticker] = cur + int(math.floor(delta * scale))
        else:
            adjusted[ticker] = cur - int(math.floor(abs(delta) * scale))
    final_turnover = sum(
        abs(int(adjusted.get(ticker, 0)) - int(current_shares.get(ticker, 0))) * float(price)
        for ticker, price in prices.items()
    )
    return adjusted, {
        "applied": True,
        "reason": "scaled_trade_deltas_to_turnover_cap",
        "regime": regime,
        "cap": cap,
        "initial_turnover_ratio": ratio,
        "final_turnover_ratio": final_turnover / max(float(total_assets), 1.0),
        "turnover_scale": scale,
    }


def _current_weights(
    signal: dict,
    current_00679b_shares: int,
    price_00679b: float,
    total_assets: float,
) -> dict[str, float]:
    prices = dict(signal["latest_prices"])
    shares = dict(signal["current_shares"])
    weights: dict[str, float] = {}
    invested = 0.0
    for ticker, qty in shares.items():
        value = float(qty) * float(prices[ticker])
        invested += value
        weights[ticker] = value / total_assets
    bond_value = float(current_00679b_shares) * price_00679b
    invested += bond_value
    weights["00679B.TWO"] = bond_value / total_assets
    weights["cash"] = max(total_assets - invested, 0.0) / total_assets
    return weights


def _apply_turnover_penalty(
    current: dict[str, float],
    raw_target: dict[str, float],
    penalty: float,
) -> dict[str, float]:
    penalty = min(max(float(penalty), 0.0), 1.0)
    if penalty <= 0:
        return dict(raw_target)
    keys = sorted(set(current) | set(raw_target))
    adjusted = {
        key: float(current.get(key, 0.0))
        + (1.0 - penalty) * (float(raw_target.get(key, 0.0)) - float(current.get(key, 0.0)))
        for key in keys
    }
    total = sum(v for v in adjusted.values() if v > 0)
    if total <= 0:
        return dict(raw_target)
    return {key: max(value, 0.0) / total for key, value in adjusted.items()}


def _resolve_turnover_penalty(config: dict, regime: str, requested_penalty: float | None) -> tuple[float, dict]:
    if requested_penalty is not None:
        penalty = float(requested_penalty)
        return penalty, {
            "source": "cli",
            "regime": regime,
            "requested_penalty": penalty,
        }

    control = dict(config.get("execution_control", {}) or {})
    live_by_regime = dict(control.get("live_turnover_penalty_by_regime", {}) or {})
    if regime in live_by_regime or "risk_off" in live_by_regime:
        penalty = float(live_by_regime.get(regime, live_by_regime.get("risk_off")))
        return penalty, {
            "source": "config_live",
            "regime": regime,
            "config_key": "execution_control.live_turnover_penalty_by_regime",
            "requested_penalty": None,
        }

    latest_reference = dict(config.get("latest_reference", {}) or {})
    if latest_reference.get("recommended_live_turnover_penalty") is not None:
        penalty = float(latest_reference["recommended_live_turnover_penalty"])
        return penalty, {
            "source": "config_latest_reference",
            "regime": regime,
            "config_key": "latest_reference.recommended_live_turnover_penalty",
            "requested_penalty": None,
        }

    by_regime = dict(control.get("default_turnover_penalty_by_regime", {}) or {})
    fallback = control.get("default_turnover_penalty", 0.0)
    penalty = float(by_regime.get(regime, by_regime.get("risk_off", fallback)))
    return penalty, {
        "source": "config",
        "regime": regime,
        "config_key": "execution_control.default_turnover_penalty_by_regime",
        "requested_penalty": None,
    }


def _target_shares(weights: dict[str, float], prices: dict[str, float], total_assets: float) -> dict[str, int]:
    shares = {}
    for ticker, price in prices.items():
        shares[ticker] = int(math.floor(total_assets * float(weights.get(ticker, 0.0)) / float(price)))
    return shares


def _apply_cash_constraint(
    current_shares: dict[str, int],
    target_shares: dict[str, int],
    prices: dict[str, float],
    *,
    total_assets: float,
    commission_rate: float,
    etf_sell_tax_rate: float,
    slippage_rate: float,
    min_trade_value: float,
) -> tuple[dict[str, int], dict]:
    """Scale buy orders down if estimated post-trade cash would be negative."""
    adjusted = dict(target_shares)
    rows, summary = _execution_rows(
        current_shares,
        adjusted,
        prices,
        {},
        total_assets,
        commission_rate=commission_rate,
        etf_sell_tax_rate=etf_sell_tax_rate,
        slippage_rate=slippage_rate,
        min_trade_value=min_trade_value,
        batch_count=1,
        batch_threshold=float("inf"),
    )
    if summary["cash_after_cost"] >= 0:
        return adjusted, {
            "applied": False,
            "reason": "cash_after_cost_nonnegative",
            "initial_cash_after_cost": summary["cash_after_cost"],
            "final_cash_after_cost": summary["cash_after_cost"],
            "buy_scale": 1.0,
        }

    buy_notional = summary["buy_notional"]
    if buy_notional <= 0:
        return adjusted, {
            "applied": False,
            "reason": "negative_cash_without_buy_orders",
            "initial_cash_after_cost": summary["cash_after_cost"],
            "final_cash_after_cost": summary["cash_after_cost"],
            "buy_scale": 1.0,
        }

    buy_cost_rate = commission_rate + slippage_rate
    required_reduction = -summary["cash_after_cost"] / (1.0 + buy_cost_rate)
    buy_scale = max(0.0, min(1.0, (buy_notional - required_reduction) / buy_notional))
    for ticker, price in prices.items():
        cur = int(current_shares.get(ticker, 0))
        tgt = int(adjusted.get(ticker, 0))
        delta = tgt - cur
        if delta > 0:
            adjusted[ticker] = cur + int(math.floor(delta * buy_scale))

    # Rounding to whole shares can still leave a small deficit. Remove one share
    # at a time from the largest remaining buy until the estimate is fundable.
    while True:
        _, final_summary = _execution_rows(
            current_shares,
            adjusted,
            prices,
            {},
            total_assets,
            commission_rate=commission_rate,
            etf_sell_tax_rate=etf_sell_tax_rate,
            slippage_rate=slippage_rate,
            min_trade_value=min_trade_value,
            batch_count=1,
            batch_threshold=float("inf"),
        )
        if final_summary["cash_after_cost"] >= 0:
            break
        buy_tickers = [
            ticker
            for ticker in prices
            if int(adjusted.get(ticker, 0)) > int(current_shares.get(ticker, 0))
        ]
        if not buy_tickers:
            break
        ticker_to_reduce = max(buy_tickers, key=lambda ticker: float(prices[ticker]))
        adjusted[ticker_to_reduce] -= 1

    return adjusted, {
        "applied": True,
        "reason": "scaled_buy_orders_to_keep_cash_after_cost_nonnegative",
        "initial_cash_after_cost": summary["cash_after_cost"],
        "final_cash_after_cost": final_summary["cash_after_cost"],
        "buy_scale": buy_scale,
    }


def _execution_rows(
    current_shares: dict[str, int],
    target_shares: dict[str, int],
    prices: dict[str, float],
    weights: dict[str, float],
    total_assets: float,
    *,
    commission_rate: float,
    etf_sell_tax_rate: float,
    slippage_rate: float,
    min_trade_value: float,
    batch_count: int,
    batch_threshold: float,
) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    buy_notional = 0.0
    sell_notional = 0.0
    commission = 0.0
    sell_tax = 0.0
    slippage = 0.0
    target_invested = 0.0
    for ticker in prices:
        cur = int(current_shares.get(ticker, 0))
        tgt = int(target_shares.get(ticker, 0))
        price = float(prices[ticker])
        delta = int(tgt - cur)
        trade_notional = abs(delta) * price
        suppressed = False
        if trade_notional < float(min_trade_value):
            delta = 0
            tgt = cur
            trade_notional = 0.0
            suppressed = True
        side = "hold"
        if delta > 0:
            side = "buy"
            buy_notional += trade_notional
        elif delta < 0:
            side = "sell"
            sell_notional += trade_notional
            sell_tax += trade_notional * etf_sell_tax_rate
        commission += trade_notional * commission_rate
        slippage += trade_notional * slippage_rate
        batch_n = int(batch_count if trade_notional >= batch_threshold and delta != 0 else 1)
        batch_shares = int(math.ceil(abs(delta) / batch_n)) if batch_n > 0 else 0
        target_value = tgt * price
        target_invested += target_value
        rows.append(
            {
                "ticker": ticker,
                "latest_price": price,
                "current_shares": cur,
                "target_shares": tgt,
                "delta_shares": delta,
                "side": side,
                "trade_notional": trade_notional,
                "target_value": target_value,
                "target_weight": target_value / total_assets,
                "raw_target_weight": float(weights.get(ticker, 0.0)),
                "estimated_commission": trade_notional * commission_rate,
                "estimated_sell_tax": trade_notional * etf_sell_tax_rate if delta < 0 else 0.0,
                "estimated_slippage": trade_notional * slippage_rate,
                "batch_count": batch_n,
                "batch_shares": batch_shares,
                "suppressed_by_min_trade_value": suppressed,
            }
        )
    total_cost = commission + sell_tax + slippage
    summary = {
        "buy_notional": buy_notional,
        "sell_notional": sell_notional,
        "commission": commission,
        "sell_tax": sell_tax,
        "slippage": slippage,
        "total_execution_cost": total_cost,
        "target_invested": target_invested,
        "cash_before_cost": total_assets - target_invested,
        "cash_after_cost": total_assets - target_invested - total_cost,
        "turnover_notional": buy_notional + sell_notional,
        "turnover_ratio": (buy_notional + sell_notional) / total_assets,
    }
    return rows, summary


def _write_markdown(path: Path, payload: dict, rows: list[dict]) -> None:
    s = payload["execution_summary"]
    lines = [
        "# Group A + 00679B Continuous Shadow",
        "",
        f"Date: {payload['generated_at']}",
        "Status: Shadow research only",
        "",
        "## Assumptions",
        "",
        f"- Total assets: `{payload['total_assets']:,.0f}`",
        f"- Group A sleeve: `{payload['group_a_sleeve_weight']:.2%}`",
        f"- 00679B sleeve: `{payload['overlay_00679b_weight']:.2%}`",
        f"- 00631L control: `{payload['leverage_control']['reason']}`",
        f"- Buy execution fraction: `{payload['execution_control']['buy_fraction']:.2%}`",
        f"- Turnover cap: `{payload['turnover_cap']['cap']:.2%}`" if payload["turnover_cap"]["cap"] is not None else "- Turnover cap: `n/a`",
        f"- Turnover penalty: `{payload['turnover_penalty']:.2f}`",
        f"- Cash constraint: `{payload['cash_constraint']['reason']}`",
        f"- Slippage rate: `{payload['slippage_rate']:.4%}`",
        "",
        "## Recommendation",
        "",
        "| Ticker | Current | Target | Delta | Side | Trade notional | Batches |",
        "| --- | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {ticker} | {current_shares:,} | {target_shares:,} | {delta_shares:,} | {side} | {trade_notional:,.0f} | {batch_count} |".format(
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
            f"- Commission: `{s['commission']:,.0f}`",
            f"- Sell tax: `{s['sell_tax']:,.0f}`",
            f"- Slippage estimate: `{s['slippage']:,.0f}`",
            f"- Total execution cost: `{s['total_execution_cost']:,.0f}`",
            f"- Cash after cost: `{s['cash_after_cost']:,.0f}`",
        ]
    )
    c = payload["cash_constraint"]
    if c["applied"]:
        lines.extend(
            [
                "",
                "## Cash Constraint",
                "",
                f"- Initial cash after cost: `{c['initial_cash_after_cost']:,.0f}`",
                f"- Final cash after cost: `{c['final_cash_after_cost']:,.0f}`",
                f"- Buy scale: `{c['buy_scale']:.4f}`",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = _parse_args()
    signal = _load_json(args.signal_json)
    plus_config = _load_json(args.group_a_plus_config)
    total_assets = float(args.total_assets)
    overlay_weight, overlay_policy = _resolve_00679b_overlay_weight(
        signal=signal,
        config=plus_config,
        requested_weight=args.overlay_00679b_weight,
        dynamic_overlay=bool(args.dynamic_overlay),
    )
    if not 0 <= overlay_weight <= 1:
        raise ValueError("--overlay-00679b-weight must be between 0 and 1")
    actual_date = str(signal["actual_data_date"])
    risk_prices = _load_risk_overlay_prices(actual_date)
    risk_date = pd.Timestamp(actual_date).normalize()
    fast_override, _fast_until, fast_report = _fast_risk_off_overlay(
        risk_prices,
        risk_date,
        plus_config,
    )
    if fast_override is not None:
        overlay_policy["base_regime_before_fast_risk_off"] = overlay_policy.get("regime")
        overlay_policy["regime"] = fast_override
        if bool(args.dynamic_overlay):
            bands = dict(dict(plus_config.get("overlay", {}) or {}).get("dynamic_weight_bands", {}) or {})
            overlay_weight = float(bands.get(fast_override, bands.get("risk_off", overlay_weight)))
    group_a_sleeve_weight = 1.0 - overlay_weight
    cache_00679b = Path(args.cache_00679b)
    if not cache_00679b.is_absolute():
        cache_00679b = (PROJECT_ROOT / cache_00679b).resolve()
    cache_00679b = _resolve_00679b_cache(cache_00679b, actual_date)
    price_00679b = _latest_00679b_price(cache_00679b, actual_date)

    prices = dict(signal["latest_prices"])
    prices["00679B.TWO"] = price_00679b
    current_shares = {ticker: int(qty) for ticker, qty in signal["current_shares"].items()}
    current_shares["00679B.TWO"] = int(args.current_00679b_shares)

    raw_target_weights_before_leverage_control = _normalize_group_weights(signal, group_a_sleeve_weight)
    raw_target_weights_before_leverage_control["00679B.TWO"] = overlay_weight
    regime = str(overlay_policy.get("regime") or "risk_on")
    _, regime_info = _infer_group_a_plus_regime(signal, plus_config)
    overlay_policy["upgrade_reason"] = regime_info.get("upgrade_reason")
    overlay_policy["vix_override"] = regime_info.get("vix_override")
    overlay_policy["turbulence_override"] = regime_info.get("turbulence_override")
    raw_target_weights, leverage_control = _apply_group_a_plus_leverage_control(
        raw_target_weights_before_leverage_control,
        config=plus_config,
        regime=regime,
    )
    _stop_until, stop_report = _leverage_stop_cooldown_overlay(
        risk_prices,
        risk_date,
        plus_config,
    )
    raw_target_weights, _risk_overlay_cash, risk_overlay_report = _apply_group_a_plus_risk_overlays(
        {ticker: float(raw_target_weights.get(ticker, 0.0)) for ticker in prices},
        float(raw_target_weights.get("cash", 0.0)),
        fast_report=fast_report,
        stop_report=stop_report,
    )
    raw_target_weights["cash"] = _risk_overlay_cash
    current_weights = _current_weights(signal, int(args.current_00679b_shares), price_00679b, total_assets)
    turnover_penalty, turnover_penalty_policy = _resolve_turnover_penalty(
        plus_config,
        regime,
        args.turnover_penalty,
    )
    target_weights = _apply_turnover_penalty(current_weights, raw_target_weights, turnover_penalty)

    target_shares_raw = _target_shares(target_weights, prices, total_assets)
    target_shares_after_execution_control, execution_control = _apply_group_a_plus_execution_control(
        current_shares,
        target_shares_raw,
        config=plus_config,
        regime=regime,
    )
    target_shares_after_turnover_cap, turnover_cap = _apply_group_a_plus_turnover_cap(
        current_shares,
        target_shares_after_execution_control,
        prices,
        config=plus_config,
        regime=regime,
        total_assets=total_assets,
    )
    if args.disable_cash_constraint:
        target_shares = dict(target_shares_after_turnover_cap)
        cash_constraint = {
            "applied": False,
            "reason": "disabled",
            "initial_cash_after_cost": None,
            "final_cash_after_cost": None,
            "buy_scale": 1.0,
        }
    else:
        target_shares, cash_constraint = _apply_cash_constraint(
            current_shares,
            target_shares_after_turnover_cap,
            prices,
            total_assets=total_assets,
            commission_rate=float(args.commission_rate),
            etf_sell_tax_rate=float(args.etf_sell_tax_rate),
            slippage_rate=float(args.slippage_rate),
            min_trade_value=float(args.min_trade_value),
        )
    rows, execution_summary = _execution_rows(
        current_shares,
        target_shares,
        prices,
        target_weights,
        total_assets,
        commission_rate=float(args.commission_rate),
        etf_sell_tax_rate=float(args.etf_sell_tax_rate),
        slippage_rate=float(args.slippage_rate),
        min_trade_value=float(args.min_trade_value),
        batch_count=max(int(args.batch_count), 1),
        batch_threshold=float(args.batch_threshold),
    )
    executable_target_shares = {
        str(row["ticker"]): int(row["target_shares"])
        for row in rows
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = Path(args.output_prefix) if args.output_prefix else PROJECT_ROOT / "results" / f"group_a_00679b_continuous_shadow_{timestamp}"
    if not prefix.is_absolute():
        prefix = (PROJECT_ROOT / prefix).resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    csv_path = prefix.with_suffix(".csv")
    json_path = prefix.with_suffix(".json")
    md_path = prefix.with_suffix(".md")

    payload = {
        "study": "Group A + 00679B continuous overlay shadow",
        "strategy_name": plus_config.get("name", "GroupA+"),
        "status": "shadow_research_only",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_signal_json": str(Path(args.signal_json).resolve() if Path(args.signal_json).is_absolute() else (PROJECT_ROOT / args.signal_json).resolve()),
        "source_00679b_cache": str(cache_00679b),
        "actual_data_date": actual_date,
        "requested_as_of_date": signal.get("requested_as_of_date"),
        "signal_status": signal.get("signal_status"),
        "signal_reason": signal.get("signal_reason"),
        "total_assets": total_assets,
        "group_a_sleeve_weight": group_a_sleeve_weight,
        "overlay_00679b_weight": overlay_weight,
        "overlay_policy": overlay_policy,
        "leverage_control": leverage_control,
        "finrl_trading_risk_overlays": risk_overlay_report,
        "turnover_penalty": float(turnover_penalty),
        "turnover_penalty_policy": turnover_penalty_policy,
        "min_trade_value": float(args.min_trade_value),
        "commission_rate": float(args.commission_rate),
        "etf_sell_tax_rate": float(args.etf_sell_tax_rate),
        "slippage_rate": float(args.slippage_rate),
        "batch_count": int(args.batch_count),
        "batch_threshold": float(args.batch_threshold),
        "latest_prices": prices,
        "current_shares": current_shares,
        "current_weights": current_weights,
        "raw_target_weights_before_leverage_control": raw_target_weights_before_leverage_control,
        "raw_target_weights": raw_target_weights,
        "target_weights_after_turnover_penalty": target_weights,
        "target_shares_before_execution_control": target_shares_raw,
        "execution_control": execution_control,
        "target_shares_before_turnover_cap": target_shares_after_execution_control,
        "turnover_cap": turnover_cap,
        "target_shares_before_cash_constraint": target_shares_after_turnover_cap,
        "cash_constraint": cash_constraint,
        "target_shares_before_min_trade_filter": target_shares,
        "target_shares": executable_target_shares,
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
    print(f"Buy notional: {execution_summary['buy_notional']:,.0f}")
    print(f"Sell notional: {execution_summary['sell_notional']:,.0f}")
    print(f"Execution cost: {execution_summary['total_execution_cost']:,.0f}")
    print(f"Cash after cost: {execution_summary['cash_after_cost']:,.0f}")


if __name__ == "__main__":
    main()
