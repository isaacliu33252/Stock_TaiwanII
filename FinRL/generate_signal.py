#!/usr/bin/env python3
"""Generate signal-only portfolio weights for the current 4-ETF PPO strategy."""

from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from stable_baselines3 import PPO


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from portfolio_config import PORTFOLIO_HOLDINGS
from portfolio_data_loader import download_all_stocks
from train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026 import (
    ACTION_LABELS,
    DOWNLOAD_END,
    TICKERS,
    _align_panel,
    _simulate_model,
    env_kwargs_from_result_payload,
)


def _resolve_result_json(path: str | None) -> Path:
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        if not candidate.exists():
            raise FileNotFoundError(f"Result JSON not found: {candidate}")
        return candidate

    result_dir = PROJECT_ROOT / "results"
    candidates = sorted(
        result_dir.glob("training_portfolio_0050_0056_00713_00878_*.json"),
        key=lambda item: item.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError("No training result JSON found under FinRL/results")
    return candidates[-1]


def _normalize_ticker(value: str) -> str | None:
    text = str(value).strip().upper()
    if text in TICKERS:
        return text
    base = text.split(".")[0]
    mapping = {ticker.split(".")[0].upper(): ticker for ticker in TICKERS}
    return mapping.get(base)


def _normalize_weights(raw_weights: dict[str, float]) -> dict[str, float]:
    clean = {ticker: max(float(raw_weights.get(ticker, 0.0)), 0.0) for ticker in TICKERS}
    total = sum(clean.values())
    if total <= 0:
        return {ticker: 1.0 / len(TICKERS) for ticker in TICKERS}
    return {ticker: value / total for ticker, value in clean.items()}


def _load_holdings_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


def _weights_from_holdings_file(path: str, latest_prices: dict[str, float]) -> tuple[dict[str, float], str]:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = PROJECT_ROOT / file_path
    df = _load_holdings_table(file_path)
    cols = {col.lower(): col for col in df.columns}
    if "ticker" not in cols:
        raise ValueError("holdings file must contain a ticker column")

    ticker_col = cols["ticker"]
    weight_col = cols.get("weight")
    shares_col = cols.get("shares")
    price_col = cols.get("price") or cols.get("close")
    raw_weights = {}
    for _, row in df.iterrows():
        ticker = _normalize_ticker(row[ticker_col])
        if ticker is None:
            continue
        if weight_col is not None and pd.notna(row[weight_col]):
            raw_weights[ticker] = float(row[weight_col])
            continue
        if shares_col is not None and pd.notna(row[shares_col]):
            shares = float(row[shares_col])
            price = float(row[price_col]) if price_col is not None and pd.notna(row[price_col]) else latest_prices[ticker]
            raw_weights[ticker] = raw_weights.get(ticker, 0.0) + shares * price

    if not raw_weights:
        raise ValueError("No usable ticker/weight or ticker/shares rows found in holdings file")
    return _normalize_weights(raw_weights), f"file:{file_path}"


def _weights_from_cli(text: str) -> tuple[dict[str, float], str]:
    values = [float(item.strip()) for item in text.split(",") if item.strip()]
    if len(values) != len(TICKERS):
        raise ValueError(f"--current-weights expects {len(TICKERS)} values ordered as {', '.join(TICKERS)}")
    return _normalize_weights(dict(zip(TICKERS, values))), "cli"


def _weights_from_portfolio_config(latest_prices: dict[str, float]) -> tuple[dict[str, float], str]:
    raw_weights = {}
    for ticker in TICKERS:
        shares = float(PORTFOLIO_HOLDINGS.get(ticker, {}).get("shares", 0))
        raw_weights[ticker] = shares * latest_prices[ticker]
    return _normalize_weights(raw_weights), "portfolio_config"


def _action_hint(diff: float, threshold: float, signal_status: str) -> str:
    if signal_status != "rebalance":
        return "hold"
    if diff >= threshold:
        return "buy"
    if diff <= -threshold:
        return "sell"
    return "hold"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate signal-only target weights for the 4-ETF PPO model.")
    parser.add_argument("--result-json", default=None, help="training result JSON; defaults to the latest 4-ETF result")
    parser.add_argument("--simulation-start", default=None, help="override the live simulation start date")
    parser.add_argument("--history-start", default=None, help="override the feature history download start date")
    parser.add_argument("--download-end", default=None, help="data download end date; defaults to the cached project default")
    parser.add_argument("--as-of-date", default=None, help="signal date; defaults to download-end")
    parser.add_argument("--current-weights", default=None, help="comma-separated weights ordered as 0050,0056,00713,00878")
    parser.add_argument("--current-holdings-file", default=None, help="CSV/XLSX with ticker+weight or ticker+shares")
    parser.add_argument("--action-threshold", type=float, default=0.01, help="minimum executable weight diff for buy/sell hint")
    parser.add_argument("--max-stale-days", type=int, default=3, help="block signals when latest data is older than this")
    parser.add_argument("--max-strategy-drawdown", type=float, default=0.27, help="block signals when strategy drawdown exceeds this")
    parser.add_argument(
        "--max-underperformance-vs-0050",
        type=float,
        default=0.10,
        help="block signals when strategy trails 0050 B&H by more than this",
    )
    args = parser.parse_args()

    result_json = _resolve_result_json(args.result_json)
    with open(result_json, encoding="utf-8") as f:
        payload = json.load(f)

    model_path = Path(payload["model_path"])
    if not model_path.is_absolute():
        model_path = PROJECT_ROOT / model_path
    if not model_path.exists():
        raise FileNotFoundError(f"Model path not found: {model_path}")

    simulation_start = (
        args.simulation_start
        or payload.get("actual_backtest_start")
        or payload.get("backtest_start")
        or "2024-01-01"
    )
    history_start = args.history_start or payload.get("actual_train_start") or payload.get("train_start") or "2009-01-01"
    download_end = args.download_end or args.as_of_date or DOWNLOAD_END
    as_of_date = args.as_of_date or download_end

    print("=" * 72)
    print("Generate 4 ETF signal")
    print(f"Result JSON: {result_json}")
    print(f"Model:       {model_path}")
    print(f"History:     {history_start} ~ {download_end}")
    print(f"Simulation:  {simulation_start} ~ {as_of_date}")
    print("=" * 72)

    stock_data = download_all_stocks(TICKERS, history_start, download_end)
    missing = [ticker for ticker in TICKERS if ticker not in stock_data]
    if missing:
        raise RuntimeError(f"Unable to load data for {missing}")

    panel = _align_panel(stock_data, simulation_start, as_of_date)
    if len(panel) < 20:
        raise RuntimeError("Not enough aligned rows to generate a signal")

    env_kwargs = env_kwargs_from_result_payload(payload, include_dca=bool(payload.get("dca_enabled", False)))
    model = PPO.load(str(model_path))
    env, _ = _simulate_model(model, panel, env_kwargs)

    actual_date = pd.Timestamp(env.panel.iloc[env.step_idx]["date"])
    latest_prices = {ticker: float(price) for ticker, price in zip(TICKERS, env.price_array[env.step_idx])}
    if args.current_weights:
        current_weights, current_source = _weights_from_cli(args.current_weights)
    elif args.current_holdings_file:
        current_weights, current_source = _weights_from_holdings_file(args.current_holdings_file, latest_prices)
    else:
        current_weights, current_source = _weights_from_portfolio_config(latest_prices)

    obs = env._get_obs()
    action, _ = model.predict(obs, deterministic=True)
    decision = env.plan_action(int(action))

    strategy_value = float(env._portfolio_value(env.price_array[env.step_idx]))
    strategy_drawdown = float(strategy_value / max(env.peak_value, 1.0) - 1.0)
    relative_vs_0050 = float(strategy_value / max(float(env.bh_0050_curve[env.step_idx]), 1.0) - 1.0)
    stale_days = max((pd.Timestamp(as_of_date) - actual_date).days, 0)

    guard_reasons = []
    if stale_days > args.max_stale_days:
        guard_reasons.append(f"stale_data_{stale_days}d")
    if strategy_drawdown <= -abs(args.max_strategy_drawdown):
        guard_reasons.append(f"drawdown_{strategy_drawdown:.2%}")
    if relative_vs_0050 <= -abs(args.max_underperformance_vs_0050):
        guard_reasons.append(f"underperform_vs_0050_{relative_vs_0050:.2%}")

    if guard_reasons:
        signal_status = "guard_blocked"
        signal_reason = "; ".join(guard_reasons)
        executable_weights = current_weights.copy()
    elif decision["can_trade_now"]:
        signal_status = "rebalance"
        signal_reason = decision["reason"]
        executable_weights = dict(decision["effective_target_weights"])
    else:
        signal_status = "hold"
        signal_reason = decision["reason"]
        executable_weights = current_weights.copy()

    strategy_weights = dict(decision["current_weights"])
    planned_weights = dict(decision["candidate_target_weights"])
    strategy_cash_weight = float(decision.get("current_cash_weight", max(0.0, 1.0 - sum(strategy_weights.values()))))
    planned_cash_weight = float(
        decision.get("candidate_target_cash_weight", max(0.0, 1.0 - sum(planned_weights.values())))
    )
    target_cash_weight = float(max(0.0, 1.0 - sum(executable_weights.values())))

    rows = []
    for ticker in TICKERS:
        current_weight = float(current_weights[ticker])
        executable_target = float(executable_weights[ticker])
        planned_target = float(planned_weights[ticker])
        strategy_weight = float(strategy_weights[ticker])
        diff = executable_target - current_weight
        planned_diff = planned_target - current_weight
        rows.append(
            {
                "date": str(actual_date.date()),
                "ticker": ticker,
                "latest_price": float(latest_prices[ticker]),
                "current_weight": current_weight,
                "strategy_weight": strategy_weight,
                "planned_target_weight": planned_target,
                "target_weight": executable_target,
                "weight_diff": diff,
                "planned_diff": planned_diff,
                "action_hint": _action_hint(diff, args.action_threshold, signal_status),
                "signal_status": signal_status,
            }
        )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = PROJECT_ROOT / "results" / f"signal_4etf_{timestamp}.csv"
    json_path = PROJECT_ROOT / "results" / f"signal_4etf_{timestamp}.json"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")
    summary = {
        "result_json": str(result_json),
        "model_path": str(model_path),
        "current_weights_source": current_source,
        "requested_as_of_date": str(pd.Timestamp(as_of_date).date()),
        "actual_data_date": str(actual_date.date()),
        "stale_days": int(stale_days),
        "signal_status": signal_status,
        "signal_reason": signal_reason,
        "guard_reasons": guard_reasons,
        "latest_action": int(action),
        "latest_action_label": ACTION_LABELS[int(action)],
        "strategy_portfolio_value": strategy_value,
        "strategy_drawdown": strategy_drawdown,
        "relative_vs_0050_bh": relative_vs_0050,
        "decision": decision,
        "latest_prices": latest_prices,
        "current_weights": current_weights,
        "strategy_weights": strategy_weights,
        "strategy_cash_weight": strategy_cash_weight,
        "planned_target_weights": planned_weights,
        "planned_target_cash_weight": planned_cash_weight,
        "target_weights": executable_weights,
        "target_cash_weight": target_cash_weight,
        "output_csv": str(csv_path),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"Signal status: {signal_status}")
    print(f"Reason:        {signal_reason}")
    print(f"Data date:     {actual_date.date()} (stale {stale_days}d)")
    print(f"Action:        {ACTION_LABELS[int(action)]}")
    print(f"Target cash:   {target_cash_weight:.2%}")
    print(f"CSV:           {csv_path}")
    print(f"JSON:          {json_path}")


if __name__ == "__main__":
    main()
