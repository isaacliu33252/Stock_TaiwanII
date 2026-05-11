# FinRL 改善建議 v3.0
==========================================

## 改善時間
2026-05-02

## 已修復的問題

### 1. total_steps=0 Bug ✅
**檔案：** `portfolio_train_v2.py`

**問題：** `_collect_stats()` 方法中，`timesteps` 變數不在 scope 內，永遠是 0。

**修復：**
- `__init__` 加入 `self.timesteps = 0`
- `train()` 方法中加入 `self.timesteps = timesteps`
- `_collect_stats()` 中改用 `self.timesteps`

```python
# 修復後
self.timesteps = 0  # __init__

self.timesteps = timesteps  # train() 內

'total_steps': self.timesteps,  # _collect_stats() 內
```

---

### 2. 交易激勵改善 ✅
**檔案：** `environments/reward_function.py`

**問題：** 模型學到「不交易」比交易好，導致 0 交易。

**改善：**
1. `trade_penalty`: `0.001` → `0.0003`（降低交易懲罰，鼓勵主動交易）
2. 加入 `inactivity_penalty`（連續空倉不作為懲罰）
3. 加入 `profitable_hold_scale`（盈利持倉複合成長權重）

**新增複合成長獎勵：**
```python
# 原本
rewards['holding'] = unrealized_pnl * self.holding_bonus

# 改為（線性 + 平方項）
rewards['holding'] = (
    unrealized_pnl * self.holding_bonus +
    (unrealized_pnl ** 2) * self.profitable_hold_scale
)
```

**空倉不作為懲罰：**
```python
if position == 0 and action == 0:
    rewards['inactivity'] = -self.inactivity_penalty
```

---

### 3. 訓練數據時間區間更新 ✅
**檔案：** `portfolio_config.py`

**問題：** 訓練數據是 2015-2019 年，與 2026 年市場結構脫節。

**修復：** 新增
```python
TRAIN_START = "2021-01-01"
TRAIN_END = "2025-12-31"
```

---

### 4. 環境驗證腳本 ✅
**檔案：** `test_env.py`（新建）

**功能：**
- 使用人工遞增價格資料
- 固定動作序列 `[1,0,0,2,1,0,0,3,1,0,0,4]` 測試
- 斷言交易歷史 > 0
- 斷言至少 1 筆 BUY + 1 筆 SELL
- T+2 結算機制驗證
- 隨機動作 50 步壓力測試

**測試結果：**
```
✅ 交易歷史: 6 筆
✅ BUY 交易: 3 筆
✅ SELL 交易: 3 筆
✅ Reward 在合理範圍內
✅ 餘額正常
🎉 所有測試通過！
```

---

## 改善後的 Reward Function 結構

| 獎勵項目 | 預設值 | 說明 |
|---------|-------|------|
| capital | ±動態 | 資本報酬（核心獎勵） |
| holding | ±動態 | 盈利持倉複合成長 |
| trade | -0.0003 | 交易懲罰（已降低） |
| inactivity | -0.002 | 空倉不作為懲罰 |
| stop_loss | -0.05 | 停損懲罰 |
| win_rate | ±動態 | 勝率獎勵 |
| drawdown | -動態 | 最大回撒懲罰 |
| limit_up_down | ±0.02 | 涨跌停 bonus |

---

## 已修改的檔案清單

| 檔案 | 修改內容 |
|------|---------|
| `portfolio_train_v2.py` | Bug fix: total_steps, self.timesteps |
| `environments/reward_function.py` | trade_penalty 降, 複合成長獎勵, 空倉懲罰 |
| `portfolio_config.py` | 新增 TRAIN_START/TRAIN_END |
| `test_env.py` | 新建環境驗證腳本 |

---

## 下一步建議

### 短期（可立即做）
1. **重新訓練模型** — 用 2021-2025 數據，跑 `portfolio_train_v2.py`
2. **觀察交易頻率** — 確認模型不再是 0 交易
3. **Walk-forward 回測** — 用 `walk_forward_v2.py` 驗證策略穩定性

### 中期（需要更多時間）
1. **狀態特徵擴展** — 加入期貨未平倉、合約價格、選擇權波動率
2. **多 AI Agent 策略** — 不同 Agent 用不同策略（PPO/A2C/SAC）
3. **真實持倉整合** — 對接實際帳戶，動態調整倉位
4. **事件驅動策略** — 針對財報公布、重大消息的反應

### 長期
1. **Backtesting 強化** — 加入交易成本、滑價、流動性約束
2. **Risk Manager v2 整合** — Early Stopping + Kelly 倉位
3. **蒙特卡羅模擬** — 評估策略在各種市場情境下的表現

---

## 風險說明

1. **Reward Function 調整可能有副作用** — 交易頻率提高可能導致過度交易，需要觀察實際表現
2. **T+2 規則實作細節** — `STOP_LOSS` 和 `CLOSE` 的 shares 計算需要再驗證
3. **2021-2025 數據涵蓋疫情+升息週期** — 可能與未來市場結構不同，Walk-forward 驗證更重要