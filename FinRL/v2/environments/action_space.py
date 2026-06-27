"""
================================================================================
ActionSpace - 動作空間定義模組 (v2新版)
================================================================================
定義台股交易環境的動作空間，支援離散和連續兩種模式。

離散動作空間（9類動作）:
    0: HOLD - 觀望，不做任何操作
    1: BUY_1000 - 買入1000股
    2: SELL_1000 - 賣出1000股
    3: CLOSE_POSITION - 清倉（賣出全部持股）
    4: STOP_LOSS - 停損（下跌超過門檻時強制賣出）
    5: BUY_3000 - 買入3000股
    6: SELL_3000 - 賣出3000股
    7: BUY_5000 - 買入5000股
    8: SELL_5000 - 賣出5000股

連續動作空間:
    動作值域: [-1, 1]，映射為目標持倉比重 [0, 1]
    -1 = 空倉 (0%)
    0 = 當前持有不變
    1 = 滿倉 (100%)

台股特殊規則：
    - 最小交易單位: 1000 股（1張）
    - 最大持有: 40000 股（40張）
    - 涨跌停限制: ±10%

作者: FinRL量化交易專家
日期: 2026-05-23
================================================================================
"""

from enum import Enum
from typing import Dict, List, Tuple, Any, Union
import numpy as np


# =============================================================================
# 動作枚舉
# =============================================================================

class ActionMode(Enum):
    """
    動作模式枚舉
    
    用於區分離散和連續動作空間。
    """
    DISCRETE = "discrete"    # 離散動作空間
    CONTINUOUS = "continuous"  # 連續動作空間


class DiscreteActions(Enum):
    """
    離散動作枚舉
    
    定義9類離散交易動作。
    每個動作都有明確的數量含義，方便 RL 模型學習有意義的策略。
    """
    HOLD = 0              # 觀望，不做任何操作
    BUY_1000 = 1          # 買入1000股
    SELL_1000 = 2         # 賣出1000股
    CLOSE_POSITION = 3    # 清倉（賣出全部持股）
    STOP_LOSS = 4         # 停損（下跌超過門檻時強制賣出）
    BUY_3000 = 5          # 買入3000股
    SELL_3000 = 6         # 賣出3000股
    BUY_5000 = 7          # 買入5000股
    SELL_5000 = 8         # 賣出5000股
    
    @property
    def shares(self) -> int:
        """
        獲取動作對應的股數
        
        返回:
            正值=買入, 負值=賣出, 0=持有
        """
        shares_map = {
            0: 0,    # HOLD
            1: 1000,  # BUY_1000
            2: -1000,  # SELL_1000
            3: 0,    # CLOSE_POSITION (特殊處理)
            4: 0,    # STOP_LOSS (特殊處理)
            5: 3000,  # BUY_3000
            6: -3000,  # SELL_3000
            7: 5000,  # BUY_5000
            8: -5000,  # SELL_5000
        }
        return shares_map.get(self.value, 0)
    
    @property
    def is_buy(self) -> bool:
        """是否為買入動作"""
        return self.value in [1, 5, 7]
    
    @property
    def is_sell(self) -> bool:
        """是否為賣出動作"""
        return self.value in [2, 3, 4, 6, 8]
    
    @property
    def is_hold(self) -> bool:
        """是否為持有動作"""
        return self.value == 0
    
    @property
    def description(self) -> str:
        """動作描述"""
        descriptions = {
            0: "觀望",
            1: "買入1000股",
            2: "賣出1000股",
            3: "清倉",
            4: "停損",
            5: "買入3000股",
            6: "賣出3000股",
            7: "買入5000股",
            8: "賣出5000股",
        }
        return descriptions.get(self.value, "未知動作")


# =============================================================================
# 連續動作空間
# =============================================================================

class ContinuousActionSpec:
    """
    連續動作空間規格
    
    用於定義連續動作空間的範圍和映射方式。
    
    Attributes:
        low: 動作下限（通常為 -1）
        high: 動作上限（通常為 1）
        target_position_ratio: 目標持倉比重 [0, 1]
        max_position: 最大持股數
    """
    
    def __init__(
        self,
        low: float = -1.0,
        high: float = 1.0,
        max_position: int = 40000
    ):
        """
        初始化連續動作空間規格
        
        參數:
            low: 動作下限
            high: 動作上限
            max_position: 最大持股數
        """
        self.low = low
        self.high = high
        self.max_position = max_position
    
    def normalize(self, action: float) -> float:
        """
        將動作值正規化到 [0, 1] 範圍
        
        參數:
            action: 原始動作值 [low, high]
            
        返回:
            正規化後的值 [0, 1]
        """
        return (action - self.low) / (self.high - self.low)
    
    def map_to_position(self, action: float) -> int:
        """
        將動作值映射為目標持股數
        
        參數:
            action: 動作值 [-1, 1]
            
        返回:
            目標持股數
        """
        normalized = self.normalize(action)
        return int(normalized * self.max_position)
    
    def map_to_ratio(self, action: float) -> float:
        """
        將動作值映射為目標持倉比重
        
        參數:
            action: 動作值 [-1, 1]
            
        返回:
            目標持倉比重 [0, 1]
        """
        return self.normalize(action)
    
    def describe_action(self, action: float) -> str:
        """
        描述動作的含義
        
        參數:
            action: 動作值 [-1, 1]
            
        返回:
            動作描述
        """
        ratio = self.map_to_ratio(action)
        position = self.map_to_position(action)
        
        if ratio < 0.1:
            return f"空倉 (0%)"
        elif ratio < 0.3:
            return f"輕倉 ({ratio*100:.0f}%, 約{position}股)"
        elif ratio < 0.6:
            return f"半倉 ({ratio*100:.0f}%, 約{position}股)"
        elif ratio < 0.9:
            return f"重倉 ({ratio*100:.0f}%, 約{position}股)"
        else:
            return f"滿倉 ({ratio*100:.0f}%, 約{position}股)"


# =============================================================================
# 動作解析和翻譯
# =============================================================================

def build_action_space(
    mode: str = 'discrete',
    max_position: int = 40000
) -> "gymnasium.spaces.Discrete":
    """
    構建動作空間
    
    根據模式返回相應的動作空間對象。
    
    參數:
        mode: 動作模式 ('discrete' 或 'continuous')
        max_position: 最大持股數
        
    返回:
        動作空間對象
    """
    if mode == 'discrete':
        from gymnasium import spaces
        return spaces.Discrete(9)
    else:
        return ContinuousActionSpec(max_position=max_position)


def translate_action(
    action: Union[int, float, np.ndarray],
    mode: str = 'discrete',
    current_position: int = 0,
    max_position: int = 40000
) -> Tuple[str, int, int]:
    """
    翻譯動作為人類可讀的描述
    
    將 RL 模型輸出的動作轉換為具體的交易描述。
    
    參數:
        action: 動作值
            - 離散模式: int (0-8)
            - 連續模式: float (-1 to 1)
        mode: 動作模式
        current_position: 當前持股數
        max_position: 最大持股數
        
    返回:
        (description, shares_to_buy, shares_to_sell)
        - description: 動作描述
        - shares_to_buy: 買入股數（正值）
        - shares_to_sell: 賣出股數（正值）
    """
    if mode == 'discrete':
        action = int(action)
        
        if action == 0:  # HOLD
            return "觀望", 0, 0
        
        elif action == 1:  # BUY_1000
            return "買入1000股", 1000, 0
        
        elif action == 2:  # SELL_1000
            return "賣出1000股", 0, min(1000, current_position)
        
        elif action == 3:  # CLOSE_POSITION
            return "清倉", 0, current_position
        
        elif action == 4:  # STOP_LOSS
            return "停損（強制賣出）", 0, current_position
        
        elif action == 5:  # BUY_3000
            return "買入3000股", 3000, 0
        
        elif action == 6:  # SELL_3000
            return "賣出3000股", 0, min(3000, current_position)
        
        elif action == 7:  # BUY_5000
            return "買入5000股", 5000, 0
        
        elif action == 8:  # SELL_5000
            return "賣出5000股", 0, min(5000, current_position)
        
        else:
            return "未知動作", 0, 0
    
    else:  # continuous
        # 連續動作：action 是目標持倉比重
        if isinstance(action, np.ndarray):
            action = float(action[0])
        
        # 計算目標持股數
        target_ratio = (action + 1) / 2  # [-1, 1] -> [0, 1]
        target_position = int(target_ratio * max_position)
        
        # 計算買入/賣出數量
        if target_position > current_position:
            return f"買入{target_position - current_position}股", target_position - current_position, 0
        elif target_position < current_position:
            return f"賣出{current_position - target_position}股", 0, current_position - target_position
        else:
            return "持倉不變", 0, 0


def validate_action(
    action: Union[int, float],
    mode: str = 'discrete',
    current_position: int = 0,
    cash: float = 0,
    price: float = 0,
    max_position: int = 40000
) -> Tuple[bool, str]:
    """
    驗證動作是否合法
    
    檢查動作是否符合台股交易規則：
    - 最小交易單位：1000股
    - 最大持有：40000股
    - 資金是否足夠買入
    - 是否有足够的股票可以賣出
    
    參數:
        action: 動作值
        mode: 動作模式
        current_position: 當前持股數
        cash: 可用現金
        price: 當前價格
        max_position: 最大持股數
        
    返回:
        (is_valid, error_message)
        - is_valid: 動作是否合法
        - error_message: 錯誤訊息（如果不正確）
    """
    if mode == 'discrete':
        action = int(action)
        
        # 檢查持股限制
        if action in [1, 5, 7]:  # 買入動作
            new_position = current_position + action * 1000
            if new_position > max_position:
                return False, f"買入後持股 ({new_position}) 將超過最大限制 ({max_position})"
        
        # 檢查賣出限制
        if action in [2, 6, 8]:  # 賣出動作
            if current_position < action * 1000:
                return False, f"持股不足 ({current_position} < {action * 1000})"
        
        if action == 3:  # 清倉
            if current_position == 0:
                return False, "無持股可賣"
        
        if action == 4:  # 停損
            if current_position == 0:
                return False, "無持股可停損"
    
    else:  # continuous
        # 連續動作驗證
        target_ratio = (action + 1) / 2
        target_position = int(target_ratio * max_position)
        
        if target_position > max_position:
            return False, f"目標持股 ({target_position}) 超過最大限制 ({max_position})"
        
        # 檢查資金
        if target_position > current_position:
            shares_to_buy = target_position - current_position
            cost = shares_to_buy * price * 1.0015  # 包含手續費
            if cost > cash:
                return False, f"資金不足 (需要 {cost:.2f}, 可用 {cash:.2f})"
    
    return True, ""


# =============================================================================
# 便捷函數
# =============================================================================

def get_action_description(action: Union[int, float]) -> str:
    """
    獲取動作的描述
    
    參數:
        action: 動作值
        
    返回:
        動作描述
    """
    if isinstance(action, (int, np.integer)):
        return DiscreteActions(action).description
    else:
        spec = ContinuousActionSpec()
        return spec.describe_action(float(action))


def get_available_actions(
    current_position: int = 0,
    cash: float = 0,
    price: float = 0,
    max_position: int = 40000,
    min_trade_unit: int = 1000
) -> List[int]:
    """
    獲取在當前狀態下可執行的動作列表
    
    參數:
        current_position: 當前持股數
        cash: 可用現金
        price: 當前價格
        max_position: 最大持股數
        min_trade_unit: 最小交易單位
        
    返回:
        可執行動作的列表
    """
    available = [0]  # HOLD 總是可執行
    
    # 計算最大買入量
    max_buy_shares = max_position - current_position
    max_buy_cost = max_buy_shares * price * 1.0015
    
    # 計算最大賣出量
    max_sell_shares = current_position
    
    # 評估每個買入動作
    buy_actions = {1: 1000, 5: 3000, 7: 5000}
    for action, shares in buy_actions.items():
        if shares <= max_buy_shares and shares * price * 1.0015 <= cash:
            available.append(action)
    
    # 評估每個賣出動作
    sell_actions = {2: 1000, 6: 3000, 8: 5000}
    for action, shares in sell_actions.items():
        if shares <= max_sell_shares:
            available.append(action)
    
    # 清倉和停損
    if current_position > 0:
        available.append(3)  # CLOSE_POSITION
        available.append(4)  # STOP_LOSS
    
    return sorted(available)


# =============================================================================
# 主程式測試
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("ActionSpace 測試")
    print("=" * 60)
    
    # 測試離散動作
    print("\n[離散動作測試]")
    for i in range(9):
        action = DiscreteActions(i)
        print(f"  {i}: {action.description}")
    
    # 測試動作翻譯
    print("\n[動作翻譯測試]")
    test_cases = [
        (0, 'discrete', 0),
        (1, 'discrete', 0),
        (2, 'discrete', 5000),
        (3, 'discrete', 3000),
        (0.5, 'continuous', 5000),
        (-0.5, 'continuous', 10000),
    ]
    
    for action, mode, pos in test_cases:
        desc, buy, sell = translate_action(action, mode, pos)
        print(f"  Action={action}, Mode={mode}, Position={pos}")
        print(f"    -> {desc}, Buy={buy}, Sell={sell}")
    
    # 測試可用動作
    print("\n[可用動作測試]")
    available = get_available_actions(
        current_position=5000,
        cash=500000,
        price=100,
        max_position=40000
    )
    print(f"  可用動作: {available}")
    
    print("\n" + "=" * 60)
    print("測試完成")
    print("=" * 60)