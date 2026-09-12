#!/usr/bin/env python3
"""Build a daily live-inference snapshot for A21.18 PPO seed averaging.

This is inference-only. It loads existing PPO checkpoints, computes each
seed's categorical action probabilities on the latest available observation,
and writes the averaged ensemble action for forward shadow monitoring.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch as th
from stable_baselines3 import PPO

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from train_dual_group_2024_2026 import (  # noqa: E402
    DEFAULT_GROUP_A_TICKERS,
    GROUP_A_PROFILE_PRESETS,
    PortfolioEnv,
    _action_label_for_context,
    _align_panel,
    _weights_to_dict,
    load_stock_data_db_first,
)

DEFAULT_LIVE_SIGNAL = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal.json"
DEFAULT_HOLDINGS_SNAPSHOT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "holdings_authoritative_snapshot.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_live_inference_snapshot.json"
DEFAULT_MODEL_DIR = PROJECT_ROOT / "models" / "portfolio"
DEFAULT_MODEL_PREFIX = "experiment_finegrained_baseline_seed"
DEFAULT_SEEDS = (42, 43, 44)


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(_resolve(path).read_text(encoding="utf-8"))


def _live_actual_date(live_signal: dict[str, Any]) -> str:
    data = live_signal.get("data") if isinstance(live_signal.get("data"), dict) else live_signal
    actual = data.get("actual_data_date") or data.get("requested_as_of_date")
    if not actual:
        raise ValueError("live signal missing actual_data_date/requested_as_of_date")
    return str(actual)


def _holdings_state(
    holdings_snapshot: dict[str, Any] | None,
    *,
    as_of: str,
    tickers: list[str],
    prices: np.ndarray,
) -> tuple[str, dict[str, Any] | None]:
    if not holdings_snapshot:
        return "reset_position_state_for_raw_policy_observation", None
    if str(holdings_snapshot.get("as_of") or "") != str(as_of):
        return "reset_position_state_holdings_snapshot_date_mismatch", {
            "holdings_snapshot_as_of": holdings_snapshot.get("as_of"),
            "required_as_of": as_of,
        }
    holdings = holdings_snapshot.get("holdings") if isinstance(holdings_snapshot.get("holdings"), dict) else {}
    cash = float(holdings_snapshot.get("cash_balance") or 0.0)
    shares = np.asarray([float(holdings.get(ticker) or 0.0) for ticker in tickers], dtype=float)
    market_value = float(np.dot(shares, prices))
    total_assets = float(cash + market_value)
    if total_assets <= 0.0:
        return "reset_position_state_invalid_authoritative_holdings", {
            "cash_balance": cash,
            "market_value": market_value,
            "total_assets": total_assets,
        }
    return "authoritative_holdings_snapshot_state", {
        "holdings_snapshot_as_of": holdings_snapshot.get("as_of"),
        "cash_balance": cash,
        "shares": {ticker: float(value) for ticker, value in zip(tickers, shares)},
        "latest_prices": {ticker: float(value) for ticker, value in zip(tickers, prices)},
        "market_value": market_value,
        "total_assets": total_assets,
        "weights": {ticker: float(shares[idx] * prices[idx] / total_assets) for idx, ticker in enumerate(tickers)},
        "cash_weight": float(cash / total_assets),
    }


def average_probabilities(seed_probabilities: dict[int, list[float]]) -> tuple[int, list[float], dict[int, int]]:
    if not seed_probabilities:
        raise ValueError("missing seed probabilities")
    lengths = {len(values) for values in seed_probabilities.values()}
    if len(lengths) != 1:
        raise ValueError(f"inconsistent probability vector lengths: {sorted(lengths)}")
    matrix = np.asarray([seed_probabilities[seed] for seed in sorted(seed_probabilities)], dtype=float)
    avg = matrix.mean(axis=0)
    argmaxes = {seed: int(np.asarray(values, dtype=float).argmax()) for seed, values in seed_probabilities.items()}
    return int(avg.argmax()), [float(value) for value in avg], argmaxes


def _model_probabilities(model: PPO, obs: np.ndarray) -> list[float]:
    obs_t = th.as_tensor(obs).float().unsqueeze(0)
    with th.no_grad():
        dist = model.policy.get_distribution(obs_t)
    return [float(value) for value in dist.distribution.probs.detach().cpu().numpy()[0]]


def _load_models(*, model_dir: Path, model_prefix: str, seeds: list[int]) -> dict[int, PPO]:
    models: dict[int, PPO] = {}
    for seed in seeds:
        path = model_dir / f"{model_prefix}{seed}.zip"
        if not path.exists():
            raise FileNotFoundError(f"missing checkpoint: {path}")
        models[seed] = PPO.load(str(path))
    return models


def build_snapshot_from_probabilities(
    *,
    as_of: str,
    tickers: list[str],
    profile_name: str,
    action_schema: str | None,
    seed_probabilities: dict[int, list[float]],
    model_prefix: str,
    model_paths: dict[int, str],
    panel_rows: int,
    observation_date: str,
    state_basis: str = "reset_position_state_for_raw_policy_observation",
    portfolio_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    action, avg_probs, argmaxes = average_probabilities(seed_probabilities)
    action_label = _action_label_for_context(action, profile_name, True, action_schema)
    env_for_weights = None
    try:
        env_for_weights = PortfolioEnv(
            panel=_dummy_panel_for_weights(observation_date, tickers),
            tickers=tickers,
            profile_name=profile_name,
            group_a_action_schema=action_schema,
        )
        target_weights = _weights_to_dict(tickers, env_for_weights._target_weights(action))
    except Exception:
        target_weights = None
    return {
        "schema_version": 1,
        "report_type": "a2118_ppo_seed_averaging_live_inference_snapshot",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of,
        "observation_date": observation_date,
        "policy": "shadow_only_no_live_weight_change",
        "live_execution_effect": "none",
        "state_basis": state_basis,
        "portfolio_state": portfolio_state,
        "preferred_ensemble": "+".join(str(seed) for seed in sorted(seed_probabilities)),
        "model_prefix": model_prefix,
        "model_paths": model_paths,
        "panel_rows": panel_rows,
        "tickers": tickers,
        "profile_name": profile_name,
        "action_schema": action_schema,
        "action": action_label,
        "action_index": action,
        "target_weights_for_action": target_weights,
        "average_probabilities": avg_probs,
        "seed_argmaxes": {str(seed): argmax for seed, argmax in sorted(argmaxes.items())},
        "seed_probabilities": {str(seed): values for seed, values in sorted(seed_probabilities.items())},
        "note": "Raw PPO policy snapshot for forward shadow monitoring only; not an execution instruction.",
    }


def _dummy_panel_for_weights(observation_date: str, tickers: list[str]) -> Any:
    import pandas as pd

    row: dict[str, Any] = {"date": observation_date}
    for ticker in tickers:
        row[f"{ticker}_open"] = 1.0
        row[f"{ticker}_close"] = 1.0
        row[f"{ticker}_dividends"] = 0.0
        for feature in ("close_ma120_ratio", "close_ma240_ratio", "ma60_ma240_ratio", "momentum_21", "momentum_63", "momentum_126", "momentum_252", "rolling_mdd_63"):
            row[f"{ticker}_{feature}"] = 0.0
    return pd.DataFrame([row])


def build_live_snapshot(
    *,
    live_signal: dict[str, Any],
    seeds: list[int],
    model_dir: Path,
    model_prefix: str,
    data_start: str,
    holdings_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    as_of = _live_actual_date(live_signal)
    tickers = list(DEFAULT_GROUP_A_TICKERS)
    profile_name = "default"
    action_schema = None
    profile = GROUP_A_PROFILE_PRESETS[profile_name]
    env_kwargs = dict(profile["env"])
    env_kwargs["group_a_action_schema"] = action_schema

    stock_data = load_stock_data_db_first(tickers, data_start, as_of)
    panel = _align_panel(stock_data, tickers, data_start, as_of, shared_feature_cols=None)
    if len(panel) < 2:
        raise RuntimeError(f"panel too short for inference: {len(panel)}")

    env = PortfolioEnv(panel, tickers, shared_feature_cols=None, initial_cash=1_000_000.0, **env_kwargs)
    env.step_idx = len(panel) - 1
    latest_prices = env.close_price_array[env.step_idx]
    state_basis, portfolio_state = _holdings_state(
        holdings_snapshot,
        as_of=as_of,
        tickers=tickers,
        prices=latest_prices,
    )
    if portfolio_state and state_basis == "authoritative_holdings_snapshot_state":
        env.cash = float(portfolio_state["cash_balance"])
        env.shares = np.asarray([float(portfolio_state["shares"][ticker]) for ticker in tickers], dtype=float)
        env.peak_value = max(float(portfolio_state["total_assets"]), 1.0)
    obs = env._get_obs()
    observation_date = str(panel.iloc[env.step_idx]["date"])[:10]

    models = _load_models(model_dir=model_dir, model_prefix=model_prefix, seeds=seeds)
    seed_probabilities = {seed: _model_probabilities(model, obs) for seed, model in models.items()}
    model_paths = {seed: str(model_dir / f"{model_prefix}{seed}.zip") for seed in seeds}
    return build_snapshot_from_probabilities(
        as_of=as_of,
        tickers=tickers,
        profile_name=profile_name,
        action_schema=action_schema,
        seed_probabilities=seed_probabilities,
        model_prefix=model_prefix,
        model_paths=model_paths,
        panel_rows=len(panel),
        observation_date=observation_date,
        state_basis=state_basis,
        portfolio_state=portfolio_state,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-signal", default=str(DEFAULT_LIVE_SIGNAL))
    parser.add_argument("--holdings-snapshot", default=str(DEFAULT_HOLDINGS_SNAPSHOT))
    parser.add_argument("--no-holdings-snapshot", action="store_true")
    parser.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    parser.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    parser.add_argument("--model-prefix", default=DEFAULT_MODEL_PREFIX)
    parser.add_argument("--data-start", default="2020-01-01")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    payload = build_live_snapshot(
        live_signal=_load_json(args.live_signal),
        seeds=list(args.seeds),
        model_dir=_resolve(args.model_dir),
        model_prefix=args.model_prefix,
        data_start=args.data_start,
        holdings_snapshot=None if args.no_holdings_snapshot else _load_json(args.holdings_snapshot),
    )
    output = _resolve(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "as_of": payload["as_of"], "action": payload["action"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
