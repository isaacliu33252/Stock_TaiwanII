"""
ActionSpace - 離散/連續動作空間工具
================================================================================
保留既有離散動作支援，並新增連續控制模式，讓同一套環境可同時支援
PPO（離散）與 SAC/TD3（連續）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

import numpy as np
from gymnasium import spaces


class ActionMode(str, Enum):
    """環境動作模式。"""

    DISCRETE = "discrete"
    CONTINUOUS = "continuous"

    @classmethod
    def from_value(cls, value: str | "ActionMode") -> "ActionMode":
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().lower()
        for item in cls:
            if item.value == normalized:
                return item
        raise ValueError(f"Unsupported action mode: {value}")


class DiscreteActions(Enum):
    """
    舊版單股票離散動作定義。

    這個 enum 保留向後相容；新環境若使用 9 類動作，會直接由
    `TaiwanStockTradingEnv.ACTION_NAMES` 管理。
    """

    HOLD = 0
    BUY_1000 = 1
    SELL_1000 = 2
    CLOSE_POSITION = 3
    STOP_LOSS = 4

    @classmethod
    def from_value(cls, value: int) -> "DiscreteActions":
        if value < 0 or value >= len(cls):
            raise ValueError(f"Invalid action value: {value}")
        return cls(value)

    @classmethod
    def get_action_names(cls) -> List[str]:
        return [action.name for action in cls]

    @classmethod
    def get_action_dict(cls) -> Dict[int, str]:
        return {action.value: action.name for action in cls}


@dataclass(frozen=True)
class ContinuousActionSpec:
    """
    連續動作設定。

    預設使用 `[-1, 1]`，並在 long-only 模式映射為 `[0, 1]` 的目標持倉比重。
    """

    low: float = -1.0
    high: float = 1.0
    shape: tuple[int, ...] = (1,)
    long_only: bool = True

    def build(self) -> spaces.Box:
        return spaces.Box(
            low=np.full(self.shape, self.low, dtype=np.float32),
            high=np.full(self.shape, self.high, dtype=np.float32),
            dtype=np.float32,
        )


ACTION_TRANSLATIONS: Dict[int, str] = {
    0: "觀望 (Hold)",
    1: "買入1000股 (Buy 1000)",
    2: "賣出1000股 (Sell 1000)",
    3: "清倉 (Close Position)",
    4: "停損 (Stop Loss)",
}


def build_action_space(
    mode: str | ActionMode,
    discrete_size: int,
    continuous_spec: ContinuousActionSpec | None = None,
) -> spaces.Space:
    """依模式建立 Gymnasium action space。"""
    resolved = ActionMode.from_value(mode)
    if resolved == ActionMode.DISCRETE:
        return spaces.Discrete(int(discrete_size))
    spec = continuous_spec or ContinuousActionSpec()
    return spec.build()


def clip_continuous_action(
    action: float | np.ndarray,
    spec: ContinuousActionSpec | None = None,
) -> np.ndarray:
    """將連續 action clip 到合法區間。"""
    action_spec = spec or ContinuousActionSpec()
    arr = np.asarray(action, dtype=np.float32).reshape(action_spec.shape)
    return np.clip(arr, action_spec.low, action_spec.high)


def continuous_action_to_target_ratio(
    action: float | np.ndarray,
    spec: ContinuousActionSpec | None = None,
) -> float:
    """
    將連續 action 轉成目標持倉比重。

    long-only:
        [-1, 1] -> [0, 1]
    allow-short:
        直接回傳 clip 後數值
    """
    action_spec = spec or ContinuousActionSpec()
    arr = clip_continuous_action(action, action_spec)
    value = float(arr.reshape(-1)[0])
    if not action_spec.long_only:
        return value
    if action_spec.high <= action_spec.low:
        raise ValueError("continuous action spec must satisfy high > low")
    scaled = (value - action_spec.low) / (action_spec.high - action_spec.low)
    return float(np.clip(scaled, 0.0, 1.0))


def format_continuous_action(
    action: float | np.ndarray,
    spec: ContinuousActionSpec | None = None,
) -> str:
    """格式化連續控制 action 方便記錄。"""
    target_ratio = continuous_action_to_target_ratio(action, spec)
    return f"目標持倉 {target_ratio * 100:.1f}%"


def translate_action(action: int | float | np.ndarray) -> str:
    """翻譯離散或連續 action。"""
    if isinstance(action, np.ndarray) or isinstance(action, float):
        return format_continuous_action(action)
    return ACTION_TRANSLATIONS.get(int(action), "未知動作")


def is_valid_buy_action(
    current_position: int,
    max_position: int,
    action: int,
) -> bool:
    """檢查舊版買入動作是否有效。"""
    if action != DiscreteActions.BUY_1000.value:
        return True
    return (current_position + 1000) <= max_position


def is_valid_sell_action(
    current_position: int,
    action: int,
) -> bool:
    """檢查舊版賣出動作是否有效。"""
    if action == DiscreteActions.SELL_1000.value:
        return current_position >= 1000
    if action == DiscreteActions.CLOSE_POSITION.value:
        return current_position > 0
    if action == DiscreteActions.STOP_LOSS.value:
        return current_position > 0
    return True
