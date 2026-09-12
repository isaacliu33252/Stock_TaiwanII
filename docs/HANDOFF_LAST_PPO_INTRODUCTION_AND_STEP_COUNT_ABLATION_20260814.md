# Last PPO 命名導入 + 訓練步數ablation + Model Provenance發現 — 交接記錄

**日期**：2026-08-14 ~ 2026-08-15
**起點**：審查論文2307.07694（DRL演算法評測：off-policy在雜訊報酬下失敗、PPO+clip最穩健、樣本複雜度極高需200萬步才接近最優）
**結論**：導入「Last PPO」命名與獨立sandbox，發現既有model provenance不可逆缺口，完成100k/500k/1M訓練步數ablation，**production維持100k不變**。

## 1. 論文審查結論（2307.07694）

不是找alpha訊號的論文，是DRL演算法工程評測。核心發現：
- Off-policy(DDPG/TD3/SAC)在雜訊報酬下學不到正確Q-function；on-policy(PPO/A2C)+GAE能處理雜訊
- PPO的clipping機制是收斂後不飄移的關鍵
- 樣本複雜度極高：即使是最簡單的3資產合成環境，都要200萬步才接近最優解

對照Group A+：golden1_0531用的正是PPO（驗證既有選擇正確）；SAC已有獨立負面證據（[[project_2606_10448_quantum_sac_layernorm_pilot_20260811]]過度交易虧80%）；但golden1_0531的PPO訓練只用了100,000步，遠低於論文的200萬步門檻——這是論文對本專案唯一有落地意義的發現。

## 2. 「Last PPO」命名與獨立複製

因為golden1_0531是[[feedback_golden1_0531_immutable_naming]]規定絕不能碰的凍結策略，使用者要求建立一個獨立sandbox：

- **golden1_0531**＝凍結artifact，`models/portfolio/group_a_production_2020_2025_100k.zip`，絕不能改。
- **Last PPO**＝a2118（最新策略）目前依賴輸入的PPO訊號來源，角色名非artifact名。實作為golden1_0531的**獨立複製檔**：
  - `models/portfolio/last_ppo_group_a_100k.zip`（複製自`group_a_production_2020_2025_100k.zip`）
  - `results/last_ppo_group_a_backtest_20250101_20260531_20260609_214023.json`（複製自對應payload，`model_name`欄位改指向上面那份複製檔）
- **a2118 production wiring已改動**：`scripts/run/run_group_a_combined_signal.py`的`DEFAULT_RESULT_JSON`從指向golden1_0531原始payload，改為指向Last PPO複製的payload。`tests/test_run_ncf_daily_pipeline.py`（21項）全數通過。golden1_0531原始檔案完全未被觸碰。

## 3. 意外發現：既有Model Provenance缺口（不可逆）

準備替Last PPO重訓練時，發現兩個既有(非本次引入)的provenance問題：

### 3a. 兩個不同的"golden1_0531"模型檔案
`models/MODEL_REGISTRY.json`顯示：
- `group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526.zip` — 標記`frozen_release`，「Golden1_0531 source-of-truth release checkpoint」，訓練細節完整已知
- `group_a_production_2020_2025_100k.zip`（本次複製為Last PPO的來源）— 標記`legacy_runtime_reference`，訓練features/action_schema原本是**"unknown"**

`GROUP_A_GOLDEN1_0531_STALENESS_AND_PREDICTION_HANDOFF_20260723.md`（07-23既有記錄，非本次發現）已經記載這個不一致，並懷疑payload在06-09被某次pipeline重跑靜默覆蓋。本次進一步確認：release manifest指向的payload(`...20260525_20260526_193252.json`)內部`model_name`欄位其實也是`group_a_production_2020_2025_100k`，不是`group_a_oos_2020_2024...`——代表這個「unknown」機型從05-31發布後就一直是實際運行的版本，不是本次才發現的新分歧。

### 3b. "unknown"訓練特徵其實可從payload頂層欄位還原
`results/group_a_backtest_20250101_20260531_20260609_214023.json`頂層記錄了完整訓練config：`group_a_action_schema=triplet_v4`, `group_a_ppo_config={learning_rate:0.0003, n_steps:1024, gamma:0.99, gae_lambda:0.95, ent_coef:0.08}`, `group_a_use_dji_features=False`, `group_a_use_llm_sentiment=False`, `group_a_pva_sigmoid_config`(overlay_enabled=True, features_enabled=False), `timesteps=100000`, `seed=42`, `train_start=2020-01-01`, train_end隱含2024-12-31。**registry的"unknown"標記本身是文件沒補而已，不是真的補不回來**——建議之後找機會把這些欄位回填進`models/MODEL_REGISTRY.json`。

### 3c. 但觀察空間維度仍然對不上（真正不可逆的缺口）
用還原出的config重建訓練環境，跑出觀察空間**41維**，但原始100k checkpoint要求**43維**，`PPO.load()`直接報`ValueError: Observation spaces do not match`。

追查`git log -p train_dual_group_2024_2026.py`：`obs_dim`公式的常數項歷史為 `+5`(05-20) → `+7`(06-27) → `+5`(07-03，=現在HEAD)，但`_get_obs()`實際組裝的`extra`清單（cash比例/回撤/rebalance天數/兩個benchmark相對表現，共5項）**橫跨三次快照從未被修改過**——代表06-27那次快照很可能存在「宣告43維但實際只塞41維內容」的暫時性bug，07-03的改動是修正它，不是移除了真實特徵。

**結論**：`group_a_production_2020_2025_100k`（=Last PPO來源）的訓練血緣在06-09~06-27之間的實際程式碼狀態完全沒有留下記錄（git只有大照快照，逐步修改遺失），這個模型**用現在的程式碼已經無法精確復現其訓練環境**，`MODEL_REGISTRY.json`的"unknown"狀態是真的補不回去，不只是文件缺口。

## 4. 訓練步數Ablation：100k / 500k / 1M

既然無法精確復現舊checkpoint，改用**今天的程式碼**（`train_dual_group_2024_2026.py`，obs_dim=+5版本）從頭訓練三個步數版本做乾淨對照，全部同一套config（action_schema=triplet_v4, ppo learning_rate/n_steps/gamma/gae_lambda/ent_coef照payload還原值，DCA/PVA sigmoid/exposure cap全部一致），seed=42，backtest window 2025-01-02~2026-08-14(392筆)：

| 步數 | 模型檔 | 訓練耗時 | 最終價值 | 總報酬 | 年化 | Sharpe | MDD | 交易次 |
|---|---|---|---|---|---|---|---|---|
| 100k | `last_ppo_group_a_100k_freshcode.zip` | ~5分 | 2,062,235 | 106.22% | 59.44% | 2.028 | -23.83% | 66 |
| 500k | `last_ppo_group_a_500k.zip` | ~22分 | 2,276,460 | 127.65% | 69.92% | 2.169 | -23.83% | 66 |
| 1M | `last_ppo_group_a_1000k.zip` | ~44分 | 2,372,667 | 137.27% | 74.52% | 2.257 | -23.83% | 66 |

單調遞增，1M未見平緩跡象，MDD跟交易次數三次完全相同（PVA/SJM regime判斷是同一套規則邏輯，差異純粹來自RL在允許範圍內的倉位微調）。方向跟論文「訓練步數不足會拖累表現」吻合。

**季度拆解**（免費，不需再訓練，用既有equity_curve切季度）：

| 季度 | 100k | 500k | 1M |
|---|---|---|---|
| 2025Q1 | -6.67% | -6.67% | -6.67%（完全相同）|
| 2025Q2 | 5.25% | 7.51% | 7.38% |
| 2025Q3 | 18.15% | 20.21% | 22.15% |
| 2025Q4 | 11.93% | 13.21% | 14.51% |
| 2026Q1 | 9.29% | 10.53% | 12.28% |
| 2026Q2 | 33.74% | 39.04% | 37.66% |
| 2026Q3 | **-0.87%** | -2.04% | -1.68% |

7季度中6個500k/1M都優於100k，方向一致非單一聚合數字假象。**但唯一負報酬的2026Q3反轉**：100k反而跌最少(-0.87%)，500k跌最多(-2.04%)——暗示訓練步數更多的模型在多頭段更積極曝險換取更高報酬，但面對近期轉弱時的抗性可能較弱，是報酬與下檔韌性的取捨，不是無腦的「訓練越久越好」。

## 5. 最終決策

**Last PPO正式運行版本維持100k不變**（`last_ppo_group_a_100k.zip`，內容=golden1_0531，production wiring未再更動）。500k/1M模型檔案保留在`models/portfolio/`作研究參考，**不接production**。理由：
1. 只測了單一多頭窗口（2025-01~2026-08），無法排除窗口特化
2. 唯一的下跌季度出現訓練步數與抗性的反向關係，證據不夠乾淨到能改變實際交易依據
3. 真正的多視窗OOS驗證需要真實的空頭/盤整資料，目前訓練窗口(2020-2024)之後的OOS期間(2025至今)幾乎全是多頭，無法人工製造——只能等未來累積到真正的下跌期再回頭驗證

## Do Not Do
- 不要把`last_ppo_group_a_500k.zip`或`last_ppo_group_a_1000k.zip`接上a2118 production——季度拆解的下檔韌性疑慮還沒解決。
- 不要再嘗試用現在的程式碼resume/續訓原始43維的`group_a_production_2020_2025_100k.zip`或`group_a_oos_2020_2024_...zip` checkpoint——observation space對不上，會直接報錯，血緣已不可逆。
- 不要假設`group_a_oos_2020_2024_..._20260526.zip`(registry標記的"真正"frozen_release)才是正確的golden1_0531——實際上從05-31發布當下開始，運行的payload內部就已經指向`group_a_production_2020_2025_100k`，這是既有事實不是bug。

## Next Step
1. 建議找機會把還原出的訓練config（見3b小節）回填進`models/MODEL_REGISTRY.json`的`group_a_production_2020_2025_100k`條目，把metadata_status從"partial"改成至少部分補完。
2. 若未來累積到2025-2026 OOS期間出現真正的下跌/盤整段，可以回頭用今天記錄的100k/500k/1M三個checkpoint重新做季度拆解，驗證2026Q3那個「訓練步數越多抗性越弱」的訊號是否穩定重現。
3. 若要繼續往2M推進步數ablation，先確認是否有新的下跌窗口可用，否則邊際資訊量已經不高。
