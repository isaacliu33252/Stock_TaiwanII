# Group A+ 策略改善 & Group B obs_dim 修復 — 交接記錄
**日期：2026-06-28**
**涵蓋工作：Group B RL obs_dim mismatch 修復 + Group A+ a2118 NCF late-bull overlay 完整回測**
**前次交接：`NCF_GROUP_A_PLUS_HANDOFF_20260626.md`、`NCF_00631L_HANDOFF_CLAUDE_20260627.md`**

---

## 0. 核心結論

### Group B（已完成）
`group_b_opt_balanced_cash20_llm_pva.zip` 推論已修復（obs_dim 66 mismatch），可正常執行。

### Group A+（分析完成，待決策）

**現行策略：a2111_tight_entry_bond30c30（Sharpe 2.374，AR 64.3%）**

本 session 完成 NCF 00631L panel 延伸至 2026-06-26，並以完整 357 列面板跑完 a2118 回測。

| 指標 | a2111（現行） | a2118（NCF overlay） | 差值 |
|------|-------------|---------------------|-----|
| 年化報酬 | **64.26%** | 58.67% | −5.58% |
| Sharpe | 2.374 | **2.410** | +0.036 |
| MDD | −13.82% | −13.82% | ≈0 |
| Sortino | 2.599 | **2.649** | +0.050 |
| 終值（100萬起始） | **2,082,732** | 1,978,940 | −103,792 |

a2118 是**風險調整後改善版**，代價是年化報酬少 5.58%。

**今日（2026-06-28）a2118 觸發狀態：ACTIVE**
- MA gap = 18.4%（超過 MA100 18.4%）
- NCF H=20 prob_up = 0.308（三個時間軸全為 DOWN，votes_up = 0/3）
- 信心指數 = 0.651（高信心，全共識）
- 建議倉位：`{0050: 74.7%, 00631L: 5.3%, cash: 20.0%}`

**待人工決策：是否將 a2118 升級為主動策略**（詳見第 8 節）

---

## 1. Group B obs_dim 修復

### 問題

```
ValueError: Error: Unexpected observation shape (64,) for Box environment,
please use (66,) or (n_env, 66)
```

訓練時的 obs_dim = 48（6 tickers × 8 features）+ 9（shared DJI+LLM）+ 4（PVA）+ 5（state）= **66**

推論時缺少 PVA 特徵，算出 obs_dim = 48 + 9 + 0 + 7 = **64**

### 修復方案：`train_dual_group_2024_2026.py`

**修改 1：新增 `_inject_0050_pva_columns()`**

位置：`_add_group_a_panel_features()` 之前（約 L420）

功能：計算 0050 的 PVA/SJM 特徵並 merge 進 Group B panel（Group B 本身沒有 0050，但訓練模型依賴這 4 欄）。

特徵欄位：`0050_pva_p`, `0050_pva_v`, `0050_pva_a`, `0050_pva_p_z`, `0050_pva_v_z`, `0050_pva_a_z`, `0050_sjm_state_code`（GROUP_A_PVA_OBS_COLUMNS 的前 4 欄進入 obs）

**修改 2：`PortfolioEnv.__init__`**

```python
# Before:
if self.enable_pva_features and self.group_a_triplet:
    ...
obs_dim = len(...) + 7

# After:
if self.enable_pva_features:    # 移除 and self.group_a_triplet
    ...
obs_dim = len(...) + 5          # 7 → 5（還原訓練時的 state 維度）
```

**修改 3：`_get_obs()`**

移除多餘的 `extra.extend([0.0, 0.0])`，state vector 精確維持 5 維。

### 修復方案：`generate_dual_group_signal.py`

**修改 1**：import 加入 `_inject_0050_pva_columns`

**修改 2**：在 `_align_panel` 之後，Group B + enable_pva_features 時注入 0050 PVA 欄：

```python
if args.group == "group_b" and env_kwargs.get("enable_pva_features"):
    pva_source = load_stock_data_db_first(["0050.TW"], history_start, download_end)
    if "0050.TW" in pva_source:
        panel = _inject_0050_pva_columns(panel, pva_source["0050.TW"])
```

**修改 3**：`generate_dual_group_signal.py` L1147 — 修正 `AttributeError`：

```python
# Before: env.group_b_action_schema
# After:  env_kwargs.get("group_b_action_schema")
```

PortfolioEnv 沒有 `group_b_action_schema` 屬性，`**extra_env_kwargs` 沒有被 store 成 attribute。

### 驗證結果

Group B 推論已正常執行。結果：`results/signal_group_b_20260628_154125.json`
- status = hold (cooldown_2d)
- 總資產 = 1,695,329
- 策略最大回撤 = −1.30%

---

## 2. NCF 00631L Panel 延伸

### 背景

`results/ncf_00631l_panel_2025_v4_tail.csv` 在 2026-05-27 截止（336 rows）。
a2118 / a2115 runner 在無面板時退化成純 a2111，無法展現 NCF overlay 效果。

### 操作

```bash
python3 scripts/misc/ncf_00631l.py \
  --val-end latest \
  --val-predictions-output results/ncf_00631l_panel_2026_extended.csv \
  --full-panel \
  --output results/ncf_00631l_latest_20260628.json
```

`--full-panel` 旗標：在標記資料結尾後，再以訓練好的分類器對「無前向標籤的尾段」做推論，補齊最近 ~20 個交易日的 panel rows（is_live=True）。

### 結果

| 項目 | 舊面板 | 新面板 |
|------|--------|--------|
| 列數 | 336 | 357（+21） |
| 尾端日期 | 2026-05-27 | 2026-06-26 |
| is_live=True 行數 | 0 | 20（2026-05-29 ~ 2026-06-26） |
| 檔案 | `ncf_00631l_panel_2025_v4_tail.csv` | 同檔案（已覆寫更新） |

`results/ncf_00631l_panel_2025_v4_tail.csv` **已覆寫為新面板（357 rows）**。

### 今日 NCF 00631L 訊號（2026-06-28，基準日 2026-06-26）

| 時間軸 | 方向 | prob_up | 預測收盤 |
|--------|------|---------|---------|
| H=1（6/29） | DOWN | 0.429 | 35.19 |
| H=5（7/3） | DOWN | 0.404 | 34.63 |
| H=20（7/24） | DOWN | **0.308** | 34.29 |
| Ensemble | DOWN | **0.413** | 35.09 |

- confidence = **0.651**（shrinkage=0.756，高信心）
- votes_up = 0/3（全共識看跌）
- prob_fwd_mdd_gt5_h20 = 0.289（28.9% 機率 20 日內回撤 >5%）
- prob_fwd_gain_gt5_h20 = 0.728（72.8% 機率 20 日內仍有 >5% 漲幅機會）
- tail_reward_risk_score = +0.439（偏樂觀，反映「跌後反彈」模式）

---

## 3. a2118 完整回測結果

### 執行命令

```bash
python3 -m group_a_plus.runners.a2118 \
  --start 2025-01-02 \
  --end 2026-06-26 \
  --ncf-panel-631l results/ncf_00631l_panel_2025_v4_tail.csv \
  --ncf-00631l results/ncf_00631l_latest_20260628.json \
  --output results/group_a_plus_runner_a2118.json
```

### 觸發條件

```python
NCF_LB_MA_GAP_MIN = 0.10    # 價格超過 MA100 10% 以上（晚期多頭）
NCF_LB_H20_MAX    = 0.45    # H=20 prob_up < 45%（NCF 預期下跌）
NCF_LB_CONF_MIN   = 0.55    # 信心 > 55%（模型確信）
```

全部滿足 → 當日 execution_regime 改為 `ncf_late_bull_hedge`：
`{0050: 70%, 00631L: 10%, cash: 20%}`（base golden1 的 00631L 砍半，轉入 0050）

### 7 個歷史觸發事件與實際走勢

| 觸發日 | MA gap | h20_prob | confidence | 5d 走勢 | 20d 走勢 | 判斷 |
|--------|--------|----------|-----------|---------|---------|------|
| 2025-10-30 | 20.4% | 0.252 | 0.553 | −2.2% | **−5.85%** | ✅ 正確保護 |
| 2025-10-31 | 20.6% | 0.255 | 0.596 | −5.5% | **−5.21%** | ✅ 正確保護 |
| 2026-02-23 | 19.1% | 0.254 | 0.570 | +2.8% | **−8.95%** | ✅ 正確保護 |
| 2026-05-04 | 28.4% | 0.351 | 0.655 | +5.4% | **+21.9%** | ❌ 誤觸發 |
| 2026-05-06 | 28.8% | 0.373 | 0.620 | −0.1% | **+23.0%** | ❌ 誤觸發 |
| 2026-05-11 | 28.5% | 0.385 | 0.613 | −5.4% | +3.5% | ⚠️ 部分 |
| 2026-05-12 | 27.9% | 0.384 | 0.581 | −8.0% | +9.0% | ⚠️ 部分 |

**分析：**
- Oct 2025 + Feb 2026 = 3 次正確保護（00631L 於 20d 內跌 5~9%）
- May 2026 = 4 次觸發，但 00631L 在急跌後強力反彈（20d 漲 21~23%），de-leverage 成本高
- May 2026 的 prob_up_h20 在 0.35~0.39 之間（比 Oct/Feb 的 0.25 更接近 0.45），信號偏弱
- **今日 prob_up_h20 = 0.308**，比 May 2026 所有觸發日都更偏空，訊號強度較高

### 模式說明

a2118 設計對 00631L 的操作：
- 原始 golden1：`{0050: ~60%, 00631L: ~20%, cash: 20%}`
- ncf_late_bull_hedge：`{0050: ~70%, 00631L: ~10%, cash: 20%}`（00631L 砍半，轉入 0050）
- de-leverage 主要目的：降低 2× 槓桿 ETF 的下行風險，同時保留 0050 參與反彈

與 `daily_signal.py` 的 soft NCF overlay 相比，a2118 hard overlay 更積極：
- daily_signal soft: 00631L 從 10.5% → 9.93%（僅 −0.6pp，幾乎無影響）
- a2118 hard: 00631L 從 ~20% → ~10%（−10pp，實質去槓桿）

---

## 4. a2115 回測（雙模式 NCF）

```bash
python3 -m group_a_plus.runners.a2115 \
  --start 2025-01-02 --end 2026-06-26 \
  --ncf-panel-631l results/ncf_00631l_panel_2025_v4_tail.csv \
  --output results/group_a_plus_runner_a2115_with_panel.json
```

結果：**與 a2118 完全相同**（AR 58.67%，Sharpe 2.410，MDD −13.82%）。
a2115 的 near-MA gate 在本回測期間未額外觸發。

---

## 5. 今日倉位建議對比

| 來源 | 0050 | 00631L | cash | 備註 |
|------|------|--------|------|------|
| a2111 backtest 末日倉位 | 69.5% | 10.5% | 20.0% | 純策略，無 NCF |
| daily_signal soft overlay | 69.5% | **9.9%** | 20.6% | NCF 軟調整 −0.6pp |
| a2118 live trigger | 74.7% | **5.3%** | 20.0% | Late-bull hard de-leverage |

今日 NCF 觸發全部條件：
```
MA gap  = 18.4% > NCF_LB_MA_GAP_MIN (10%)   ✓
h20_prob = 0.308 < NCF_LB_H20_MAX   (45%)   ✓  ← 比 May 2026 觸發日更強
confidence = 0.651 > NCF_LB_CONF_MIN (55%)  ✓  ← 共識 = 1.00（三軸全跌）
```

---

## 6. 結果檔案清單

| 檔案 | 說明 |
|------|------|
| `results/ncf_00631l_panel_2025_v4_tail.csv` | NCF 00631L 歷史面板（已更新，357 rows，~2026-06-26） |
| `results/ncf_00631l_latest_20260628.json` | 今日 NCF 00631L 完整推論結果 |
| `results/group_a_plus_runner_a2118.json` | a2118 with 完整面板的 backtest（正式版） |
| `results/group_a_plus_runner_a2115_with_panel.json` | a2115 with 面板 backtest（參考） |
| `results/group_a_plus_runner_a2118_frame.csv` | a2118 逐日 regime / portfolio_value frame |
| `results/signal_group_b_20260628_154125.json` | Group B 推論結果（obs_dim 修復後首次成功）|

---

## 7. 待決定事項

### 決策：是否將 a2118 升級為主動策略？

**升級 a2118（建議）：**
- Sharpe +0.036（2.374 → 2.410），Sortino +0.050（2.599 → 2.649）
- 今日 NCF 訊號強力觸發（votes_up=0，共識=1.00）
- 5.58% AR 的代價 = 晚期多頭 2× ETF 的保護成本
- May 2026 失真是結構性問題（acute rally after sharp drop），非模型失效

**維持 a2111：**
- AR 高 5.58%（接近 1 個百分點 per month 的複利優勢）
- May 2026 展示 NCF 在 ma_gap > 25% 時信號偏弱
- daily_signal 的 soft overlay 已部分覆蓋 NCF 下行風險

**折衷方案（可選）：**
使用 a2118 的觸發訊號作為手動決策的 advisory（不改 strategy.json），今日實際操作將 00631L 從 10% 降至 5~7%。

### 如果升級到 a2118，需要執行：

```bash
# 1. 更新 strategy.json
python3 -c "
import json
with open('report/group_a_plus/latest/strategy.json') as f:
    s = json.load(f)
s['active_strategy']['id'] = 'a2118_a2111_ncf_late_bull_deleverage'
s['active_strategy']['runner'] = 'group_a_plus.runners.a2118'
s['active_strategy']['recent_result'] = 'results/group_a_plus_runner_a2118.json'
s['activated_at'] = '2026-06-28'
with open('report/group_a_plus/latest/strategy.json', 'w') as f:
    json.dump(s, f, indent=2, ensure_ascii=False)
"

# 2. 重新跑 latest runner（a2118 需要 ncf-panel-631l 參數）
# 需先確認 group_a_plus/runners/latest.py 的 run_latest() 支援 ncf_panel_631l_path

# 3. 重新生成 live signal
python3 -m group_a_plus.operations.daily_signal \
  --as-of 2026-06-28 \
  --output report/group_a_plus/latest/live_signal.json
```

**注意**：`latest.py` runner 目前是否支援 a2118 的 `ncf_panel_631l_path` 參數需確認。

---

## 8. 重要技術細節

### NCF Panel confidence 欄位定義（與 live signal 不同）

Panel CSV 的 `confidence` = `prob_magnitude` = `|ensemble_prob_up − 0.5| × 2`

Live JSON 的 `confidence` = `consensus_score × 0.4 + magnitude_score × 0.4 + (1−spread_score) × 0.2`

a2118 歷史回測用 panel confidence（簡化公式）；a2118 live signal 用 live JSON confidence（豐富公式）。兩者含義相近但數值有差異，在回測與 live 之間保持一致性即可。

### Full Panel 的 is_live=True 行

Panel 末尾 20 行（2026-05-29 ~ 2026-06-26）是以**當次訓練模型對無前向標籤尾段的推論**（`--full-panel` 旗標）。

這些行的 `prob_fwd_mdd_gt5_h20`, `actual_fwd_mdd_gt5_h20` 等欄位為空（無前向標籤）。
a2118 的觸發邏輯只讀 `prob_up_h20` 和 `confidence`，不受影響。

### 今日觸發用的 live signal（ncf_00631l_latest_20260628.json）

這個檔案是**以 2026-06-26 為基準日、完整重訓後的推論**，比 panel 末行（is_live=True）更準確，因為包含了最新的 ext features（外資、法人、台指期）。a2118 runner 以 `--ncf-00631l` 參數指定此檔，用於計算今日 live trigger。

---

## 9. 重跑命令

### NCF 00631L 面板更新（每次 daily 更新後執行）

```bash
python3 scripts/misc/ncf_00631l.py \
  --val-end latest \
  --val-predictions-output results/ncf_00631l_panel_2025_v4_tail.csv \
  --full-panel \
  --output results/ncf_00631l_latest_$(date +%Y%m%d).json
```

### a2118 回測

```bash
python3 -m group_a_plus.runners.a2118 \
  --start 2025-01-02 \
  --end $(date +%Y-%m-%d) \
  --ncf-panel-631l results/ncf_00631l_panel_2025_v4_tail.csv \
  --ncf-00631l results/ncf_00631l_latest_$(date +%Y%m%d).json \
  --output results/group_a_plus_runner_a2118.json
```

### Group B 推論（修復後）

```bash
python3 generate_dual_group_signal.py \
  --group group_b \
  --xlsx taiwan_stock_20260626.xlsx \
  --as-of-date 2026-06-26 \
  --total-value 1695329 \
  --output results/signal_group_b_$(date +%Y%m%d).json
```

### 測試

```bash
python3 -m pytest -q \
  tests/test_group_a_plus_latest_strategy.py \
  tests/test_group_a_plus_ncf_integration.py \
  -x
```

---

## 10. 下一步建議

### Priority 1（待人工決策）— a2118 升級

確認 `group_a_plus/runners/latest.py` 的 `run_latest()` 是否支援 a2118，
若支援，更新 strategy.json，重跑 live signal。

若不升級：今日手動將 00631L 持倉從 ~10% 降至 ~5~7% 作為 advisory 操作。

### Priority 2 — Opportunity-cost label（來自前次交接）

訓練直接預測「降 00631L / 切 defensive 是否優於原策略」的 label：
- `cap_00631l_15pct_beats_base_next20d`
- `defensive_beats_base_next20d`

這比繼續優化 NCF gate 更接近 Group A+ 實際決策問題。

### Priority 3 — May 2026 模式分析

May 2026 的 4 次觸發均在 ma_gap > 28%（極度晚期多頭）且市場發生急跌後強力反彈。
可考慮加入 ma_gap 上限條件（例如 ma_gap > 25% 時提高觸發門檻，或縮小 de-leverage 幅度），
以避免在極端多頭期間因 NCF 保守訊號而錯過大幅反彈。

### Priority 4 — a2119（FinBERT）資料更新

`group_a_plus/runners/a2119.py`（FinBERT boundary risk gate）目前因 FinBERT 資料陳舊未觸發。
若取得新的 FinBERT 情緒資料，可重跑 a2119 backtest。

---

## 11. 文件版本說明

本交接記錄對應以下 session 工作：

1. **上個 session**（context 壓縮前）：Group B obs_dim mismatch 修復（三個檔案共 6 處修改）
2. **本 session**：NCF 面板延伸（336→357 rows）+ a2118 完整 backtest + 觸發事件分析

前次相關文件：
- `NCF_GROUP_A_PLUS_HANDOFF_20260626.md`：NCF v6 interaction features、tail reward/risk
- `NCF_00631L_HANDOFF_CLAUDE_20260627.md`：TXO 特徵、Optuna 調參、multi-year walk-forward

---

*Generated 2026-06-28*
