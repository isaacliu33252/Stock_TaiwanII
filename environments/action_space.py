"""
ActionSpace - 離散動作空間定義
================================================================================
定義台股交易的離散動作空間。

動作設計考量:
1. 簡單性: 台股交易動作相對簡單（買/賣/持有），離散空間更穩定
2. 約束: 每筆交易最小單位 1000 股，最大持有 4000 股
3. 風險控制: 加入停損和清倉動作

5 個離散動作:
    0: HOLD           - 觀望，不執行任何操作
    1: BUY_1000       - 買入 1000 股 (若有空倉)
    2: SELL_1000      - 賣出 1000 股 (若有持倉)
    3: CLOSE_POSITION - 清倉 (賣出全部持股)
    4: STOP_LOSS      - 停損 (強制賣出，觸發時使用)

作者: FinRL量化交易專家
"""

from enum import Enum
from typing import Dict, List


class DiscreteActions(Enum):
    """
    台股離散動作枚舉
    
    每個動作對應特定的交易操作：
    
    - HOLD: 不動作，用於等待更好的進場時機
    - BUY_1000: 買入 1000 股，每次加碼一個單位
    - SELL_1000: 賣出 1000 股，逐步獲利了結
    - CLOSE_POSITION: 全部賣出，快速離場
    - STOP_LOSS: 強制停損，限制虧損
    """
    
    HOLD = 0           # 觀望，不動作
    BUY_1000 = 1       # 買入 1000 股
    SELL_1000 = 2      # 賣出 1000 股
    CLOSE_POSITION = 3 # 清倉 (全部賣出)
    STOP_LOSS = 4      # 停損賣出
    
    @property
    def name(self) -> str:
        """取得動作名稱"""
        return self.name
    
    @property
    def value(self) -> int:
        """取得動作數值"""
        return self.value
    
    @classmethod
    def from_value(cls, value: int) -> 'DiscreteActions':
        """
        從數值取得動作枚舉
        
        Args:
            value: 動作數值 (0-4)
        
        Returns:
            對應的 DiscreteActions 枚舉
        """
        if value < 0 or value >= len(cls):
            raise ValueError(f"Invalid action value: {value}")
        return cls(value)
    
    @classmethod
    def get_action_names(cls) -> List[str]:
        """
        取得所有動作名稱列表
        
        Returns:
            ['HOLD', 'BUY_1000', 'SELL_1000', 'CLOSE_POSITION', 'STOP_LOSS']
        """
        return [action.name for action in cls]
    
    @classmethod
    def get_action_dict(cls) -> Dict[int, str]:
        """
        取得動作數值到名稱的映射
        
        Returns:
            {0: 'HOLD', 1: 'BUY_1000', 2: 'SELL_1000', 3: 'CLOSE_POSITION', 4: 'STOP_LOSS'}
        """
        return {action.value: action.name for action in cls}


# =============================================================================
# 動作翻譯 (用於日誌和輸出)
# =============================================================================

ACTION_TRANSLATIONS: Dict[int, str] = {
    0: "觀望 (Hold)",
    1: "買入1000股 (Buy 1000)",
    2: "賣出1000股 (Sell 1000)",
    3: "清倉 (Close Position)",
    4: "停損 (Stop Loss)",
}


def translate_action(action: int) -> str:
    """
    翻譯動作數值為中文描述
    
    Args:
        action: 動作數值 (0-4)
    
    Returns:
        中文動作描述
    
    Example:
        >>> translate_action(1)
        '買入1000股 (Buy 1000)'
    """
    return ACTION_TRANSLATIONS.get(action, "未知動作")


# =============================================================================
# 動作有效性檢查
# =============================================================================

def is_valid_buy_action(
    current_position: int,
    max_position: int,
    action: int
) -> bool:
    """
    檢查買入動作是否有效
    
    Args:
        current_position: 目前持股數量
        max_position: 最大持股數量 (預設 4000)
        action: 動作數值
    
    Returns:
        True 如果買入動作有效
    """
    if action != DiscreteActions.BUY_1000.value:
        return True  # 非買入動作，視為有效
    return (current_position + 1000) <= max_position


def is_valid_sell_action(
    current_position: int,
    action: int
) -> bool:
    """
    檢查賣出動作是否有效
    
    Args:
        current_position: 目前持股數量
        action: 動作數值
    
    Returns:
        True 如果賣出動作有效
    """
    if action == DiscreteActions.SELL_1000.value:
        return current_position >= 1000
    elif action == DiscreteActions.CLOSE_POSITION.value:
        return current_position > 0
    elif action == DiscreteActions.STOP_LOSS.value:
        return current_position > 0
    return True  # HOLD 動作，視為有效
