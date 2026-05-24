"""
Group A FinRL-X strategy adapter.

Wrap the existing Group A payload + PPO replay path and expose a
FinRL-X-compatible StrategyResult.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .base_strategy import BaseStrategy, StrategyConfig, StrategyResult

logger = logging.getLogger(__name__)


try:
    import numpy.core.numeric as _numpy_core_numeric

    sys.modules.setdefault("numpy._core.numeric", _numpy_core_numeric)
except ImportError:
    pass


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_project_root_on_path() -> Path:
    root = _project_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def _resolve_local_path(raw: str | Path) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return (_project_root() / candidate).resolve()


def _coerce_ohlcv_frame(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    local = df.copy()
    if "date" not in local.columns:
        local = local.reset_index()
        if "date" not in local.columns:
            local = local.rename(columns={local.columns[0]: "date"})
    local["date"] = pd.to_datetime(local["date"]).dt.tz_localize(None)
    local = local.sort_values("date").reset_index(drop=True)
    if "tic" not in local.columns:
        local["tic"] = ticker
    return local


def _resolve_group_a_model_path(project_root: Path, payload: dict[str, Any], override: str | None) -> Path:
    if override:
        raw = _resolve_local_path(override)
        if raw.exists():
            return raw
        if raw.suffix != ".zip" and raw.with_suffix(".zip").exists():
            return raw.with_suffix(".zip")
        raise FileNotFoundError(f"Unable to locate Group A model override: {override}")

    group_a = payload.get("group_a", {}) or {}
    model_name = group_a.get("model_name")
    if model_name:
        candidate = project_root / "models" / "portfolio" / str(model_name)
        if candidate.exists():
            return candidate
        if candidate.suffix != ".zip" and candidate.with_suffix(".zip").exists():
            return candidate.with_suffix(".zip")

    resume_model = payload.get("group_a_resume_model") or group_a.get("resume_model")
    if resume_model:
        candidate = _resolve_local_path(str(resume_model))
        if candidate.exists():
            return candidate

    raise FileNotFoundError("Unable to resolve Group A model path from payload")


def _weight_history_frame(
    panel: pd.DataFrame,
    tickers: list[str],
    weight_history: list[np.ndarray],
) -> pd.DataFrame:
    if not weight_history:
        return pd.DataFrame(columns=tickers)
    dates = pd.to_datetime(panel["date"]).reset_index(drop=True)
    usable = min(len(dates), len(weight_history))
    return pd.DataFrame(
        np.asarray(weight_history[:usable], dtype=float),
        index=pd.DatetimeIndex(dates.iloc[:usable]),
        columns=tickers,
    ).sort_index()


def _rebalance_weight_frame(full_weights: pd.DataFrame) -> pd.DataFrame:
    if full_weights.empty:
        return full_weights.copy()
    rebalance_mask = full_weights.diff().abs().sum(axis=1).fillna(1.0) > 1e-10
    rebalance_mask.iloc[0] = True
    return full_weights.loc[rebalance_mask].copy()


def _cash_weight_series(full_weights: pd.DataFrame) -> pd.Series:
    if full_weights.empty:
        return pd.Series(dtype=float)
    values = np.clip(1.0 - full_weights.sum(axis=1).to_numpy(dtype=float), 0.0, 1.0)
    return pd.Series(values, index=full_weights.index, name="cash_weight")


def _price_frame(panel: pd.DataFrame, tickers: list[str], field: str) -> pd.DataFrame:
    dates = pd.to_datetime(panel["date"]).reset_index(drop=True)
    data = {
        ticker: panel[f"{ticker}_{field}"].to_numpy(dtype=float)
        for ticker in tickers
        if f"{ticker}_{field}" in panel.columns
    }
    return pd.DataFrame(data, index=pd.DatetimeIndex(dates)).sort_index()


@dataclass
class GroupAFinRLXConfig(StrategyConfig):
    name: str = "GroupAFinRLX"
    result_json: str = ""
    model_path: Optional[str] = None
    download_end: Optional[str] = None
    backtest_start: Optional[str] = None
    initial_cash: Optional[float] = None
    deterministic: bool = True


class GroupAFinRLXStrategy(BaseStrategy):
    """Replay a canonical Group A payload and emit a FinRL-X StrategyResult."""

    def __init__(self, config: GroupAFinRLXConfig):
        super().__init__(config)
        self.cfg: GroupAFinRLXConfig = config

    def generate_weights(
        self,
        data: Dict[str, pd.DataFrame],
        target_date: Optional[str] = None,
    ) -> StrategyResult:
        project_root = _ensure_project_root_on_path()

        from stable_baselines3 import PPO

        from generate_dual_group_signal import _env_kwargs_from_payload, _llm_sentiment_path_from_payload
        from train_dual_group_2024_2026 import (
            DEFAULT_INITIAL_CASH,
            PortfolioEnv,
            _align_panel,
            attach_market_features_db_first,
            load_stock_data_db_first,
        )

        if not self.cfg.result_json:
            raise ValueError("GroupAFinRLXConfig.result_json is required")

        result_json = _resolve_local_path(self.cfg.result_json)
        payload = json.loads(result_json.read_text(encoding="utf-8"))
        group_payload = payload.get("group_a", {}) or {}
        tickers = list(group_payload.get("tickers", ["0050.TW", "00631L.TW", "00632R.TW"]))
        if not tickers:
            raise ValueError(f"{result_json} does not contain Group A tickers")

        train_start = str(payload.get("train_start") or group_payload.get("train_start") or "2024-01-01")
        backtest_start = str(
            self.cfg.backtest_start
            or payload.get("backtest_start")
            or group_payload.get("backtest_start")
            or train_start
        )
        requested_end = pd.Timestamp(
            target_date or payload.get("backtest_end") or payload.get("download_end") or backtest_start
        ).tz_localize(None)
        payload_download_end = pd.Timestamp(
            self.cfg.download_end or payload.get("download_end") or requested_end
        ).tz_localize(None)
        download_end = str(max(payload_download_end, requested_end).date())
        backtest_end = str(requested_end.date())

        env_kwargs, shared_feature_cols = _env_kwargs_from_payload(payload, "group_a")
        llm_enabled = bool(payload.get("group_a_use_llm_sentiment", False))
        llm_path = _llm_sentiment_path_from_payload(payload, "group_a") if llm_enabled else None
        initial_cash = float(self.cfg.initial_cash or payload.get("initial_cash_per_group", DEFAULT_INITIAL_CASH))

        if data:
            missing = [ticker for ticker in tickers if ticker not in data]
            if missing:
                raise KeyError(f"Missing Group A tickers in supplied data: {missing}")
            stock_data = {ticker: _coerce_ohlcv_frame(data[ticker], ticker) for ticker in tickers}
        else:
            stock_data = load_stock_data_db_first(tickers, train_start, download_end)

        if shared_feature_cols:
            stock_data = attach_market_features_db_first(
                stock_data,
                tickers,
                train_start,
                download_end,
                include_llm_sentiment=llm_enabled,
                llm_sentiment_path=llm_path,
            )

        panel = _align_panel(
            stock_data,
            tickers,
            backtest_start,
            backtest_end,
            shared_feature_cols=shared_feature_cols,
        )
        if len(panel) < 2:
            raise ValueError(
                f"Group A adapter requires at least 2 aligned rows; got {len(panel)} for "
                f"{backtest_start} ~ {backtest_end}"
            )

        model_path = _resolve_group_a_model_path(project_root, payload, self.cfg.model_path)
        env = PortfolioEnv(
            panel,
            tickers,
            shared_feature_cols=shared_feature_cols,
            initial_cash=initial_cash,
            **env_kwargs,
        )
        model = PPO.load(
            str(model_path),
            env=env,
            custom_objects={
                "action_space": env.action_space,
                "observation_space": env.observation_space,
                "_last_obs": None,
                "_last_original_obs": None,
                "_last_episode_starts": None,
            },
        )

        obs, _ = env.reset()
        decisions: list[dict[str, Any]] = []
        weight_history: list[np.ndarray] = [np.asarray(env.weights, dtype=float).copy()]
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=bool(self.cfg.deterministic))
            decisions.append(env.plan_action(int(action)))
            obs, _, terminated, truncated, info = env.step(action)
            weight_history.append(np.asarray(info["weights"], dtype=float).copy())
            done = terminated or truncated

        full_weights = _weight_history_frame(panel, tickers, weight_history)
        rebalance_weights = _rebalance_weight_frame(full_weights)
        close_prices = _price_frame(panel, tickers, "close")
        open_prices = _price_frame(panel, tickers, "open")
        cash_weights = _cash_weight_series(full_weights)

        metadata = {
            "payload_path": str(result_json),
            "model_path": str(model_path),
            "target_date": backtest_end,
            "initial_cash": initial_cash,
            "window": {
                "train_start": train_start,
                "download_end": download_end,
                "backtest_start": backtest_start,
                "backtest_end": backtest_end,
            },
            "tickers": tickers,
            "shared_feature_cols": shared_feature_cols,
            "env_kwargs": env_kwargs,
            "prices": close_prices,
            "price_frame": close_prices,
            "open_prices": open_prices,
            "weights_full": full_weights,
            "weights_daily": full_weights,
            "weights_rebalance": rebalance_weights,
            "cash_weight_daily": cash_weights,
            "decision_history": decisions,
            "equity_curve": [float(value) for value in env.equity_curve],
            "final_portfolio_value": float(env.equity_curve[-1]),
            "fees_paid_estimate": float(env.fees_paid),
            "trade_count": int(env.trade_count),
            "pva_sigmoid_count": int(env.pva_sigmoid_count),
            "pva_sigmoid_history": env.pva_sigmoid_history,
            "dca_purchase_count": int(env.dca_purchase_count),
            "dca_purchase_history": env.dca_purchase_history,
            "dca_total_contributions": float(env.total_contributions),
            "inverse_forced_exit_count": int(env.inverse_forced_exit_count),
            "inverse_forced_exit_history": env.inverse_forced_exit_history,
            "sjm_state_history": env.sjm_state_history,
            "dividend_credited_history": env.dividend_credited_history,
            "total_dividend_credited": float(env.total_dividend_credited),
            "dividend_reinvestment_history": env.dividend_reinvestment_history,
            "group_a_runtime_config": {
                "leverage_cap": float(env.leverage_cap),
                "inverse_cap": float(env.inverse_cap),
                "pva_weight": float(env.pva_weight),
                "pva_j_state_weight": float(env.pva_j_state_weight),
                "pva_m_state_weight": float(env.pva_m_state_weight),
                "pva_drift_threshold": float(env.pva_drift_threshold),
                "pva_target_vol": float(env.pva_target_vol),
                "pva_min_leverage_scale": float(env.pva_min_leverage_scale),
                "pva_inverse_hedge_budget": float(env.pva_inverse_hedge_budget),
                "pva_s_state_drift_boost": float(env.pva_s_state_drift_boost),
                "pva_s_state_max_weight": float(env.pva_s_state_max_weight),
                "pva_buy_dip_strength": float(env.pva_buy_dip_strength),
                "dca_day": int(env.dca_day),
                "inverse_m_state_only": bool(env.inverse_m_state_only),
                "inverse_max_holding_days": int(env.inverse_max_holding_days),
                "dividend_mode": str(env.dividend_mode),
            },
        }

        return StrategyResult(
            strategy_name=self.cfg.name,
            weights=full_weights,
            metadata=metadata,
        )
