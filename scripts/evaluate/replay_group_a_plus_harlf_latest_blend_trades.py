#!/usr/bin/env python3
"""Trade-level replay for ETF-mapped HARLF/latest blend.

This is a shadow replay only. It blends ETF-only HARLF monthly target weights
with latest-strategy historical target weights, rebalances on the first trading
day of each outcome month, rounds shares down to lot size, applies costs, and
tracks realized equity. It creates no orders and changes no strategy.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_DB = PROJECT_ROOT / "FinRL/data/stock_data.db"
DEFAULT_MAPPED_SHADOW = PROJECT_ROOT / "report/group_a_plus/latest/harlf_etf_mapped_shadow.json"
DEFAULT_BLEND = PROJECT_ROOT / "report/group_a_plus/latest/harlf_latest_blend_sweep.json"
DEFAULT_LATEST_TARGET_WEIGHTS_CSV = PROJECT_ROOT / "report/group_a_plus/latest/latest_strategy_historical_target_weights.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/harlf_latest_blend_trade_replay.json"
DEFAULT_HISTORY_DIR = PROJECT_ROOT / "report/group_a_plus/harlf_latest_blend_trade_replay/history"
ASSET_TABLES = {
    "0050": ("ohlcv", "0050.TW"),
    "00631L": ("ohlcv", "00631L.TW"),
    "00632R": ("ohlcv", "00632R.TW"),
    "00679B": ("ohlcv", "00679B.TWO"),
}
TRADABLE_ASSETS = tuple(ASSET_TABLES)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _daily_metrics(returns: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return {"n": 0}
    equity = (1.0 + clean).cumprod()
    peak = equity.cummax()
    std = float(clean.std(ddof=0))
    return {
        "n": int(len(clean)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "mean_daily_return": float(clean.mean()),
        "daily_volatility": std,
        "annualized_sharpe": float(clean.mean() / std * math.sqrt(252)) if std > 1e-12 else float(clean.mean() * 252),
        "max_drawdown": float((equity / peak - 1.0).min()),
        "positive_day_rate": float((clean > 0.0).mean()),
        "worst_day": float(clean.min()),
        "best_day": float(clean.max()),
    }


def _load_close(db_path: Path, start: str, end: str) -> pd.DataFrame:
    panels: list[pd.DataFrame] = []
    with duckdb.connect(str(db_path), read_only=True) as conn:
        for asset, (table, ticker) in ASSET_TABLES.items():
            df = conn.execute(
                f"SELECT dt, close FROM {table} WHERE ticker = ? AND dt >= ? AND dt <= ? ORDER BY dt",
                [ticker, start, end],
            ).fetchdf()
            if df.empty:
                continue
            df["dt"] = pd.to_datetime(df["dt"]).dt.normalize()
            panels.append(df.set_index("dt")["close"].astype(float).rename(asset).to_frame())
    return pd.concat(panels, axis=1).sort_index() if panels else pd.DataFrame()


def _load_latest_weights(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, encoding="utf-8-sig")
    if "date" not in frame.columns:
        return pd.DataFrame()
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame.set_index("date").sort_index()


def _harlf_monthly_weights(mapped_shadow: dict[str, Any], mode: str) -> dict[str, dict[str, float]]:
    rows = ((mapped_shadow.get("variants") or {}).get(mode) or {}).get("meta_agent_monthly_returns") or []
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        weights = {asset: float((row.get("weights") or {}).get(asset, 0.0) or 0.0) for asset in TRADABLE_ASSETS}
        total = sum(weights.values())
        if total > 1e-12:
            out[str(row.get("month"))] = {asset: value / total for asset, value in weights.items()}
    return out


def _latest_weights_on(frame: pd.DataFrame, dt: pd.Timestamp) -> dict[str, float]:
    if frame.empty:
        return {}
    if dt not in frame.index:
        prior = frame.loc[frame.index <= dt]
        if prior.empty:
            return {}
        row = prior.iloc[-1]
    else:
        row = frame.loc[dt]
    weights = {
        asset: float(row.get(f"target_weight_{asset}", 0.0) or 0.0)
        for asset in (*TRADABLE_ASSETS, "cash")
    }
    total = sum(max(value, 0.0) for value in weights.values())
    return weights if total <= 1e-12 else {asset: max(value, 0.0) / total for asset, value in weights.items()}


def _blend_weights(latest: dict[str, float], harlf: dict[str, float], harlf_weight: float) -> dict[str, float]:
    latest_weight = 1.0 - harlf_weight
    out = {
        asset: latest_weight * float(latest.get(asset, 0.0)) + harlf_weight * float(harlf.get(asset, 0.0))
        for asset in (*TRADABLE_ASSETS, "cash")
    }
    total = sum(out.values())
    return out if total <= 1e-12 else {asset: value / total for asset, value in out.items()}


def _cost(asset: str, side: str, value: float, commission: float, slippage: float, sell_tax: float) -> float:
    tax = 0.0 if asset == "00679B" or side == "buy" else sell_tax
    return value * (commission + slippage + tax)


def _portfolio_value(shares: dict[str, int], cash: float, prices: pd.Series) -> float:
    return float(cash + sum(shares.get(asset, 0) * float(prices[asset]) for asset in TRADABLE_ASSETS))


def _rebalance(
    *,
    shares: dict[str, int],
    cash: float,
    prices: pd.Series,
    target_weights: dict[str, float],
    lot_size: int,
    max_turnover_ratio: float,
    commission: float,
    slippage: float,
    sell_tax: float,
) -> tuple[dict[str, int], float, dict[str, Any]]:
    value_before = _portfolio_value(shares, cash, prices)
    current_values = {asset: shares.get(asset, 0) * float(prices[asset]) for asset in TRADABLE_ASSETS}
    desired_values = {asset: value_before * float(target_weights.get(asset, 0.0)) for asset in TRADABLE_ASSETS}
    raw_deltas = {asset: desired_values[asset] - current_values.get(asset, 0.0) for asset in TRADABLE_ASSETS}
    raw_turnover = sum(abs(delta) for delta in raw_deltas.values()) / value_before if value_before > 0 else 0.0
    scale = 1.0 if raw_turnover <= max_turnover_ratio or raw_turnover <= 1e-12 else max_turnover_ratio / raw_turnover
    new_shares = dict(shares)
    total_cost = 0.0
    traded_value = 0.0
    trades: list[dict[str, Any]] = []

    for side in ("sell", "buy"):
        for asset, delta in raw_deltas.items():
            scaled_delta = delta * scale
            if (side == "sell" and scaled_delta >= 0) or (side == "buy" and scaled_delta <= 0):
                continue
            price = float(prices[asset])
            qty = int(math.floor(abs(scaled_delta) / price / lot_size) * lot_size)
            if qty <= 0:
                continue
            if side == "sell":
                qty = min(qty, int(new_shares.get(asset, 0)))
                if qty <= 0:
                    continue
                value = qty * price
                fee = _cost(asset, side, value, commission, slippage, sell_tax)
                new_shares[asset] = int(new_shares.get(asset, 0) - qty)
                cash += value - fee
            else:
                value = qty * price
                fee = _cost(asset, side, value, commission, slippage, sell_tax)
                affordable_qty = int(math.floor(cash / ((price * (1.0 + commission + slippage)) * lot_size)) * lot_size)
                qty = min(qty, max(affordable_qty, 0))
                if qty <= 0:
                    continue
                value = qty * price
                fee = _cost(asset, side, value, commission, slippage, sell_tax)
                new_shares[asset] = int(new_shares.get(asset, 0) + qty)
                cash -= value + fee
            traded_value += value
            total_cost += fee
            trades.append({"asset": asset, "side": side, "shares": qty, "price": price, "value": value, "cost": fee})

    value_after = _portfolio_value(new_shares, cash, prices)
    return new_shares, cash, {
        "value_before": value_before,
        "value_after": value_after,
        "traded_value": traded_value,
        "turnover_ratio": traded_value / value_before if value_before > 0 else 0.0,
        "raw_turnover_ratio": raw_turnover,
        "turnover_scale": scale,
        "cost": total_cost,
        "trades": trades,
    }


def build_trade_replay(
    *,
    close: pd.DataFrame,
    latest_weights: pd.DataFrame,
    mapped_shadow: dict[str, Any],
    blend_report: dict[str, Any],
    mapping_mode: str = "drop_2330_renormalize",
    initial_value: float = 1_000_000.0,
    lot_size: int = 1,
    max_turnover_ratio: float = 0.50,
    commission_rate: float = 0.001425,
    slippage_rate: float = 0.0005,
    equity_etf_sell_tax: float = 0.001,
) -> dict[str, Any]:
    blockers: list[str] = []
    if close.empty:
        blockers.append("missing_close_prices")
    if latest_weights.empty:
        blockers.append("missing_latest_target_weights")
    best = blend_report.get("best_viable_blend") or {}
    harlf_weight = best.get("harlf_weight")
    if harlf_weight is None:
        blockers.append("missing_harlf_blend_weight")
        harlf_weight = 0.0
    harlf_by_signal_month = _harlf_monthly_weights(mapped_shadow, mapping_mode)
    if not harlf_by_signal_month:
        blockers.append("missing_harlf_mapped_monthly_weights")
    if blockers:
        return {
            "schema_version": 1,
            "report_type": "group_a_plus_harlf_latest_blend_trade_replay",
            "status": "blocked",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "blocking_reasons": sorted(set(blockers)),
            "decision": {
                "creates_orders": False,
                "changes_golden01_0531": False,
                "changes_latest_strategy": False,
                "trade_level_execution_cost_replay_available": False,
                "promotion_ready": False,
            },
        }

    close = close.dropna(subset=list(TRADABLE_ASSETS)).sort_index()
    months = sorted(harlf_by_signal_month)
    outcome_months = [(pd.Period(month, freq="M") + 1).strftime("%Y-%m") for month in months]
    start_month, end_month = min(outcome_months), max(outcome_months)
    replay_prices = close[(close.index.to_period("M").astype(str) >= start_month) & (close.index.to_period("M").astype(str) <= end_month)]
    cash = float(initial_value)
    shares = {asset: 0 for asset in TRADABLE_ASSETS}
    daily_rows: list[dict[str, Any]] = []
    rebalance_rows: list[dict[str, Any]] = []
    current_target = {asset: 0.0 for asset in (*TRADABLE_ASSETS, "cash")}
    rebalanced_months: set[str] = set()

    for dt, prices in replay_prices.iterrows():
        outcome_month = dt.to_period("M").strftime("%Y-%m")
        signal_month = (dt.to_period("M") - 1).strftime("%Y-%m")
        if signal_month in harlf_by_signal_month and outcome_month not in rebalanced_months:
            latest = _latest_weights_on(latest_weights, dt)
            current_target = _blend_weights(latest, harlf_by_signal_month[signal_month], float(harlf_weight))
            shares, cash, rebalance = _rebalance(
                shares=shares,
                cash=cash,
                prices=prices,
                target_weights=current_target,
                lot_size=lot_size,
                max_turnover_ratio=max_turnover_ratio,
                commission=commission_rate,
                slippage=slippage_rate,
                sell_tax=equity_etf_sell_tax,
            )
            rebalance_rows.append(
                {
                    "date": dt.strftime("%Y-%m-%d"),
                    "signal_month": signal_month,
                    "outcome_month": outcome_month,
                    "target_weights": current_target,
                    **rebalance,
                }
            )
            rebalanced_months.add(outcome_month)
        value = _portfolio_value(shares, cash, prices)
        daily_rows.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "portfolio_value": value,
                "cash": cash,
                **{f"shares_{asset}": shares[asset] for asset in TRADABLE_ASSETS},
                **{f"target_weight_{asset}": current_target.get(asset, 0.0) for asset in (*TRADABLE_ASSETS, "cash")},
            }
        )

    daily = pd.DataFrame(daily_rows)
    returns = pd.to_numeric(daily["portfolio_value"], errors="coerce").pct_change(fill_method=None).dropna()
    metrics = _daily_metrics(returns)
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_harlf_latest_blend_trade_replay",
        "status": "available",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "research_only_trade_replay_no_order_creation",
        "parameters": {
            "mapping_mode": mapping_mode,
            "harlf_weight": float(harlf_weight),
            "latest_weight": 1.0 - float(harlf_weight),
            "initial_value": initial_value,
            "lot_size": lot_size,
            "max_turnover_ratio": max_turnover_ratio,
            "commission_rate": commission_rate,
            "slippage_rate": slippage_rate,
            "equity_etf_sell_tax": equity_etf_sell_tax,
        },
        "window": (
            {}
            if daily.empty
            else {
                "start": str(daily["date"].iloc[0]),
                "end": str(daily["date"].iloc[-1]),
                "daily_rows": int(len(daily)),
                "rebalance_count": int(len(rebalance_rows)),
            }
        ),
        "metrics": metrics,
        "cost_summary": {
            "total_cost": float(sum(row["cost"] for row in rebalance_rows)),
            "total_traded_value": float(sum(row["traded_value"] for row in rebalance_rows)),
            "max_turnover_ratio_observed": float(max((row["turnover_ratio"] for row in rebalance_rows), default=0.0)),
            "turnover_cap_binding_count": int(sum(row["turnover_scale"] < 0.999999 for row in rebalance_rows)),
        },
        "rebalance_events": rebalance_rows,
        "daily_equity_preview": daily_rows[:20],
        "daily_equity_tail": daily_rows[-20:],
        "blocking_reasons": [],
        "decision": {
            "creates_orders": False,
            "changes_golden01_0531": False,
            "changes_latest_strategy": False,
            "trade_level_execution_cost_replay_available": True,
            "promotion_ready": False,
        },
    }


def _write(report: dict[str, Any], output: Path, history_dir: Path | None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if history_dir is not None:
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        (history_dir / f"harlf_latest_blend_trade_replay_{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--mapped-shadow", default=str(DEFAULT_MAPPED_SHADOW))
    parser.add_argument("--blend", default=str(DEFAULT_BLEND))
    parser.add_argument("--latest-target-weights-csv", default=str(DEFAULT_LATEST_TARGET_WEIGHTS_CSV))
    parser.add_argument("--mapping-mode", default="drop_2330_renormalize")
    parser.add_argument("--initial-value", type=float, default=1_000_000.0)
    parser.add_argument("--lot-size", type=int, default=1)
    parser.add_argument("--max-turnover-ratio", type=float, default=0.50)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--equity-etf-sell-tax", type=float, default=0.001)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR))
    parser.add_argument("--no-history", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    latest_weights = _load_latest_weights(_resolve(args.latest_target_weights_csv))
    start = latest_weights.index.min().strftime("%Y-%m-%d") if not latest_weights.empty else "2025-07-01"
    end = latest_weights.index.max().strftime("%Y-%m-%d") if not latest_weights.empty else "2026-08-07"
    report = build_trade_replay(
        close=_load_close(_resolve(args.db), start, end),
        latest_weights=latest_weights,
        mapped_shadow=_load_json(_resolve(args.mapped_shadow)),
        blend_report=_load_json(_resolve(args.blend)),
        mapping_mode=args.mapping_mode,
        initial_value=args.initial_value,
        lot_size=args.lot_size,
        max_turnover_ratio=args.max_turnover_ratio,
        commission_rate=args.commission_rate,
        slippage_rate=args.slippage_rate,
        equity_etf_sell_tax=args.equity_etf_sell_tax,
    )
    report["inputs"] = {
        "db": str(_resolve(args.db)),
        "mapped_shadow": str(_resolve(args.mapped_shadow)),
        "blend": str(_resolve(args.blend)),
        "latest_target_weights_csv": str(_resolve(args.latest_target_weights_csv)),
    }
    _write(report, _resolve(args.output), None if args.no_history else _resolve(args.history_dir))
    print(
        json.dumps(
            {
                "status": report["status"],
                "window": report.get("window"),
                "metrics": report.get("metrics"),
                "cost_summary": report.get("cost_summary"),
                "decision": report.get("decision"),
                "output": str(_resolve(args.output)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
