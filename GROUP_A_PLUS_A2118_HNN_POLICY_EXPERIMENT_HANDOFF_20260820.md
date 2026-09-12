# GroupA+ a2118 HNN Policy Experiment Handoff - 2026-08-20

## 背景

延續同一天的 `GROUP_A_PLUS_MFCF_HNN_VOLATILITY_PILOT_HANDOFF_20260820.md`（
arXiv:2608.14323 MFCF/HNN dependence-informed sparse architecture）。那次 pilot
在一個 research-only 的波動度預測任務上驗證了論文的架構主張，並明確標記
（但沒有動）a2118 Last PPO 的 flat state vector 是唯一真正對應論文情境的
production 位置。使用者問「不能用?」，我解釋了原因後補充「真正能用到這個
架構優點的地方是 a2118 PPO 的 policy 網路...但那是直接改 production 決策
引擎的架構，需要你明確要不要做這個實驗」。**使用者回覆「實驗做做看」**，
本文件記錄這個實驗。

## 動手前先做研究

沒有直接開始改程式碼，先用一個 Explore agent 完整釐清 a2118 實際的訓練/
推論鏈路（避免對一個沒完全搞懂的系統動手）。關鍵發現：

1. **`a2118.py` 本身不做 RL 推論**——它只讀取已經算好的 golden signal
   JSON（`results/group_a_combined_live_latest.json`），純粹是 post-hoc
   weight-overlay 邏輯。
2. **真正訓練 PPO 的是 `train_dual_group_2024_2026.py`**（不是
   `portfolio_train_v2.py`，那個只提供 `calculate_backtest_metrics()`
   helper）。用 `stable_baselines3.PPO("MlpPolicy", ...)`，**沒有任何
   `policy_kwargs`/`net_arch` override**——即 SB3 預設架構：policy net
   `pi=[64,64]`、value net `vf=[64,64]`，Tanh 啟動函數。這就是本實驗要
   替換的目標。
3. **環境是該檔案內建的 `PortfolioEnv(gym.Env)`**（不是
   `FinRL/v2/environments/taiwan_stock_env.py`，那個是給其他/較舊 pipeline
   用的）。Obs = 每檔 ticker 8 個技術指標（`FEATURE_COLUMNS`）× tickers +
   `shared_feature_cols`（預設關閉）+ 5 個 portfolio 狀態 scalar（現金比例、
   drawdown、距上次 rebalance 天數、相對兩個 benchmark 的表現）。
4. **Production Last PPO checkpoint**：`models/portfolio/last_ppo_group_a_100k.zip`，
   100k timesteps，CPU 訓練約 4-5 分鐘。**已知的 provenance gap**：用今天的
   程式碼重建訓練得到 41 維 obs，跟原始 production checkpoint 的 43 維對不
   上，無法完美重現——這代表任何架構比較實驗都應該用「今天的程式碼」訓練
   一個新鮮 baseline 再比，而不是硬要重現舊 checkpoint（否則會混淆「架構
   差異」跟「obs 組成差異」兩件事）。
5. 訓練依賴：`stable_baselines3==2.8.0`、`gymnasium==1.2.3`、
   `torch`（CPU-only，無 GPU）。

## 實驗設計：全程隔離 production

原則：**不碰任何 production 檔案或 checkpoint**。

新增（皆在明確標示為 experiment 的命名空間下）：

- `scripts/misc/a2118_hnn_policy_experiment_lib.py`
  - `HNNFeatureBody`：跟 volatility pilot 同一套 MFCF clique 稀疏層邏輯
    （import `build_mfcf_forest`/`build_layer_structure`，不重複實作），但
    輸出改成**串接所有層的 activation 當 feature vector**（本例 93 維：
    layer 2/3/4 分別 53+32+8），而不是 volatility pilot 那種單一 scalar
    regression readout——因為 SB3 的 actor/critic head 需要的是一個
    feature vector，不是一個數字。這是這次實驗對論文架構的必要調整，
    在程式碼註解裡有明確記錄。
  - `HNNFeaturesExtractor(BaseFeaturesExtractor)`：SB3 相容包裝，把原始
    obs 依 MFCF 找出的 node 順序重排後餵給 `HNNFeatureBody`。
  - `build_hnn_layers_from_samples()`：從真實取樣的 observation 資料建出
    clique 結構跟欄位排列。
- `scripts/misc/train_a2118_hnn_policy_experiment_20260820.py`
  - **直接 import** `train_dual_group_2024_2026.py` 的 `PortfolioEnv`、
    `GROUP_A_PROFILE_PRESETS`、`load_stock_data_db_first`、`_align_panel`、
    `_backtest_group`——**完全沒有修改那個檔案任何一行**。
  - 自己寫一個支援 `policy_kwargs` 的訓練函式（`_train_group` 本身不支援，
    這是唯一需要重寫而非直接 import 的部分）。
  - **Checkpoint 命名空間強制檢查**：`assert model_name.startswith("experiment_")`
    ——程式碼層級擋死，不可能不小心存到 `last_ppo_*` 或
    `group_a_production_*` 這些 production 名字。
  - MFCF 結構：用 800 個真實 observation（訓練環境 random-action rollout
    採樣）算相關矩陣建出來，`obs_dim=37, K*=4, layer widths=[37,53,32,8]`。

## 執行

3 seeds（42/43/44）× 2 變體（`baseline_mlp` = SB3 預設 MlpPolicy，跟
production Last PPO 實際使用的架構一致；`hnn` = MFCF-derived sparse
extractor）× 100k timesteps，同一套 env/reward/action schema/PPO 超參數
（`lr=3e-4, n_steps=1024, gamma=0.99, gae_lambda=0.95, ent_coef=0.08`，
Group A "default" profile），2020-2023 訓練 / 2024-01-02~2026-05-08 回測——
跟 production Last PPO 的訓練預算(100k)一致，但兩個變體都是**全新訓練**
（不是重用/微調任何既有 checkpoint），確保架構比較是 apples-to-apples。

### 背景執行踩到的一個真實疏漏

用 `python3 ... | tee log.txt` 背景執行整個 6-run 實驗（預估 30 分鐘，實際
跑了 47 分鐘）。Python 預設對非 terminal 輸出是 **full buffering**（不是
line buffering），導致中途 stdout 完全看不到任何進度。使用者問「跑多少
了」我答不出來，只能用 `models/portfolio/experiment_hnn_policy_*.zip` 的
檔案 mtime 反推目前跑到第幾組。使用者接著問「之前不是要建, %?」，
點出這正是既有 memory `feedback_long_running_command_progress`（長時間
背景指令要能看進度，不要用 tail 當 pipeline 最後一段）講的情況——這次沒
有事先做到。**下次背景長跑 RL 訓練這類任務，要用 `python3 -u`（unbuffered）
或在關鍵節點顯式 `sys.stdout.flush()`，讓中途進度真的可見，不能只靠事後
補救（檔案 mtime）。**

## 結果

6 組跑完，`results/a2118_hnn_policy_experiment_1787212641.json`：

| Variant | final_value (mean ± std) | Sharpe (mean ± std) | MDD (mean ± std) | 交易次數範圍 |
|---|---:|---:|---:|---:|
| baseline_mlp | $3,511,776 ± $61,932 | 1.945 ± 0.021 | -0.2971 ± 0.0037 | 71–85 |
| **hnn** | $3,511,692 ± **$16,264** | **1.845** ± 0.005 | **-0.3568** ± 0.0041 | 94（3個seed完全一樣）|

Paired t-test（n=3 each，統計檢定力先天不足，但方向一致、range 完全無
重疊）：

| 指標 | t | p | 解讀 |
|---|---:|---:|---|
| final_value | 0.002 | 0.999 | **完全打平** |
| Sharpe | 6.49 | 0.0029 | **hnn 三個 seed 全部比 baseline 三個 seed 低**（1.840–1.852 vs 1.916–1.966，無重疊） |
| max_drawdown | 15.37 | 0.0001 | **hnn 三個 seed 全部比 baseline 三個 seed差**（-0.352~-0.362 vs -0.294~-0.302，無重疊） |

兩個變體的平均最終資產都輸給 `buy_and_hold_50_50_blend`（$3,820,029）——
這不是本次比較的重點，只是背景資訊。

### 解讀：跟同天前一個 pilot 一樣，論文的訓練穩定性主張複製成功，但這次是負面的風險/報酬trade-off

`hnn` 拿到跟 `baseline_mlp` 幾乎一模一樣的平均最終資產（差 $84，統計上
完全無法區分），但**用更深的 drawdown、更差的 risk-adjusted 報酬換來的**
——約 6 個百分點更深的最大回撤，且三個 seed 全部一致，不是單一 outlier
造成的雜訊。對於一個整個研究史都在強調尾端風險控制的專案（
[[feedback_strategy_promotion_caution]]、`tail_conformal.py`/
`adaptive_quantile_risk_gate.py` 那整條研究線），這是真實的扣分項。

但 `hnn` 展現出**遠高於 baseline 的跨 seed 穩定性**：final_value 標準差
只有 baseline 的 **1/3.8**，交易次數在三個 seed 上完全鎖定在 94 次（
baseline 則在 71–85 次間變動）。這正好複製了論文自己的訓練穩定性主張
（原論文：HNN 在監督式波動度預測上 0/30 collapse，標準 MoE/dense 常常
collapse）——這是本 session 唯一一次在 **RL**（而非監督式迴歸）架構實驗
上看到這個效應真的成立，比同天稍早的 volatility pilot 更進一步驗證了
論文的第二個主張（不只是準確度/參數效率，訓練穩定性本身也跨任務類型
成立）。

## 追加：300k timesteps 方向性檢查（使用者問「建議加長時間?」）

3-seed 結果出來後，使用者問要不要拉長訓練時間看看 hnn 的 Sharpe/MDD 劣勢
是不是訓練不足造成的。考量到 hnn 每 100k timesteps 比 baseline 慢（
稀疏 mask 運算開銷），3 seeds 全部拉到 500k/1M 會是數小時等級的運算成本
——而且 production 自己過去測過 500k/1M 比 100k 在 backtest 上數字更好，
但 2026Q3 那個下跌季度排名整個反過來，最後保守選了 100k 沒有升級（見
`docs/HANDOFF_LAST_PPO_INTRODUCTION_AND_STEP_COUNT_ABLATION_20260814.md`）
——「訓練更久 backtest 看起來更好」這個訊號在這個專案已經被驗證過不可
盡信。因此先跑一個便宜的方向性檢查：**只用 seed=42，兩個變體都拉到
300k timesteps**（不是完整 3-seed 重跑），並吸取前面的教訓改用
`python3 -u`（unbuffered）避免中途看不到進度。

```bash
python3 -u scripts/misc/train_a2118_hnn_policy_experiment_20260820.py \
  --seeds 42 --timesteps 300000 --obs-samples 800 \
  --output results/a2118_hnn_policy_experiment_300k_directional_check.json
```

耗時：baseline 764s，hnn 940s（約 12.7 分 / 15.7 分），比 100k 慢約 1.4-1.7
倍（非線性，可能跟 SB3 內部 buffer/scheduler 開銷有關，不是本次重點）。

### 結果：差距縮小了，但原因跟預期相反

| Seed 42 | 100k | 300k |
|---|---:|---:|
| baseline Sharpe | 1.916 | **1.852**（變差） |
| baseline MDD | -0.2942 | **-0.3516**（變差） |
| hnn Sharpe | 1.840 | 1.843（幾乎沒動） |
| hnn MDD | -0.3615 | -0.3569（幾乎沒動） |
| hnn 交易次數 | 94 | 94（完全一樣） |

差距明顯縮小，但**不是因為 hnn 變好**——是 `baseline_mlp` 自己在 300k
時退化了（Sharpe 跌、回撤變深，往 hnn 的水準靠攏），而 `hnn` 在 100k 到
300k 之間幾乎原地不動（連交易次數都完全相同）。

**這翻轉了原本對「hnn 在 100k 是不是訓練不足」這個問題的解讀**：hnn
不是訓練不足——它在 100k 就已經收斂穩定了，拉長訓練也不改變它的行為。
反而是 `baseline_mlp` 在 100k 的優勢看起來更像是訓練時長的一個 snapshot，
不是穩定的架構特性，跟 production 自己過去「更多訓練步數不保證更好，
取決於 OOS 落在哪個時期」的教訓完全一致。

**這進一步強化（而非推翻）了前面 3-seed 結果裡「hnn 訓練穩定性遠高於
baseline」的發現**——hnn 這次同時對 seed（3-seed 實驗）跟對 training
budget（這次的 100k vs 300k）都表現出高度不變性，是整個子實驗裡最一致
的訊號，直接呼應論文自己的訓練穩定性主張。

**但原本 100k 的結論不變，沒有被推翻**：在 production 實際使用的 100k
訓練預算下，hnn 的 Sharpe/MDD 確實比 baseline 差，不建議 promote。**不能
把這次的發現解讀成「訓練更久 hnn 就會贏」**——縮小差距的是 baseline
變差，不是 hnn 變好，這是兩件不同的事。

n=1（單一 seed、單一額外 timestep 設定）只能當方向性訊號，沒有繼續跑更
多 seed 在 300k+（邊際資訊量遞減 + 這個 session 已經花了不少運算成本）。
如果之後真要繼續深入，比較有意義的下一步不是繼續加碼 hnn 的訓練時長，
而是先把 `baseline_mlp` 自己拉一個完整的 step-count sweep（量化它在
100k 的優勢有多少比例是訓練時長脆弱的），釐清 baseline 本身的行為之後，
再回頭談跟 hnn 的比較才有意義。

## 決定

**不 promote，不 wire 進任何 production 路徑**（全部 checkpoint 都在
`experiment_` 命名空間、結果 JSON 是獨立檔案，`train_dual_group_2024_2026.py`
/ `a2118.py` / `a2111.py` / `generate_dual_group_signal.py` 一行都沒改）。

但穩定性這個發現值得獨立記住，不要跟「這次不 promote」的結論一起被忘掉：
如果之後 PPO 訓練不穩定/對 seed 敏感真的變成一個實際痛點——
`docs/HANDOFF_LAST_PPO_INTRODUCTION_AND_STEP_COUNT_ABLATION_20260814.md`
記錄的 2026Q3 步數 ablation 排名反轉問題，本質上就是這類 seed/樣本敏感性
——sparse HNN feature extractor 是一個**有實證支持、值得重新考慮**的具體
方向。但要先解決這次觀察到的 Sharpe/MDD 系統性退化才值得再花一次訓練
成本，例如：

- 把原始 features 跟 HNN 的 clique-summary 一起串接（而非完全取代原始
  features），讓 policy 仍能存取細粒度資訊。
- 在 extractor 輸出上補一層小 `net_arch`（而非這次用的 `net_arch=[]`），
  給 actor/critic head 多一點非線性能力。
- 增加 seed 數（論文用 10，這次只有 3）跟做多年獨立 OOS backtest（這次
  只有單一 2024-2026-05 訓練後回測窗口），而不是單一 train/backtest split。

n=3 seeds 遠低於論文自己的 n=10，也沒有做多年獨立 OOS 窗口驗證——這個
負面結果是「方向一致、效應量大、但統計力不足」，不是鐵板釘釘的定論，
未來若重新檢視需要先補足這些樣本量。

## 已改檔案 / 產出

全部在 experiment 命名空間，皆未接 production：

- 新增 `scripts/misc/a2118_hnn_policy_experiment_lib.py`
- 新增 `scripts/misc/train_a2118_hnn_policy_experiment_20260820.py`
- 更新 `group_a_plus/research_semantic_registry.json`（新增
  `research_id: mfcf_hnn_a2118_ppo_policy_architecture_experiment`，
  `status: closed_negative`）
- 產出 `models/portfolio/experiment_hnn_policy_{baseline_mlp,hnn}_seed{42,43,44}.zip`
  （6 個檔案，共約 900KB，**不是** production checkpoint）
- 產出 `results/a2118_hnn_policy_experiment_1787212641.json`（3-seed×100k主結果）
- 追加產出 `results/a2118_hnn_policy_experiment_300k_directional_check.json`
  （300k方向性檢查）與對應 checkpoint
  `models/portfolio/experiment_hnn_policy_{baseline_mlp,hnn}_seed42.zip`
  （被 300k 版本覆蓋，100k 版本的原始數字已記錄在本文件與 registry，
  checkpoint 本身不影響任何結論的可驗證性）

## 測試

**沒有新增測試檔案**——理由同前兩篇：確定 closed_negative、不會 promote、
不會 wire 進任何 production 路徑。驗證止於：

- 一次小規模 smoke test（2000 timesteps, 1 seed）先確認整條 pipeline
  （資料載入 → MFCF 建構 → SB3 PPO 訓練 → `_backtest_group` 回測）能跑通、
  不會拋例外，才進行完整的 100k×6 run。
- 完整跑完後對 Sharpe/MDD/final_value 做了 t-test，數字經得起檢驗（三個
  seed 的 range 完全不重疊，不是單一 lucky/unlucky run 造成的假象）。

若之後真的要沿著「解決 Sharpe/MDD 退化」的方向繼續，建議先補
`tests/test_a2118_hnn_policy_experiment_lib.py`，至少覆蓋
`HNNFeaturesExtractor` 的 forward pass 輸出 shape 正確、`col_perm` 重排
邏輯正確（避免重蹈 volatility pilot 那次 `self.index1` 型別不匹配的
覆轍）。

## Git 狀態

```text
?? scripts/misc/a2118_hnn_policy_experiment_lib.py
?? scripts/misc/train_a2118_hnn_policy_experiment_20260820.py
```

`models/portfolio/experiment_hnn_policy_*.zip` 跟
`results/a2118_hnn_policy_experiment_*.json` 是否被 git 追蹤請自行確認
（`models/`、`results/` 目錄過去有被加進 `.gitignore` 的紀錄，這批實驗
產出的檔案本來就不該進版控）。`group_a_plus/research_semantic_registry.json`
同前兩篇，只是新增一筆 entry。

## Memory

已寫入 `project_2608_14323_a2118_hnn_ppo_experiment_20260820.md`，並更新
`MEMORY.md` 索引。

## 一句話交接

同天分析 arXiv:2608.14323 的第三步：使用者要求把前面驗證過的 MFCF/HNN
架構真的套到 a2118 Last PPO 的 policy 網路上實測。全程用 `experiment_`
命名空間隔離、未改動任何 production 檔案；3 seeds 完整重訓比較 SB3 預設
MlpPolicy vs MFCF-derived sparse HNN feature extractor，結果：final_value
完全打平，但 hnn 在三個 seed 上一致地 Sharpe 更低、drawdown 更深（t-test
p<0.003，range 無重疊）——同時展現出遠高於 baseline 的跨 seed 穩定性
（final_value 變異數只有 baseline 的 1/3.8，交易次數完全鎖定）。複製了
論文的訓練穩定性主張，但風險/報酬 trade-off 是負面的，不足以 promote。
過程中因為背景執行 stdout 被 buffer 卡住看不到進度，被使用者提醒要對照
既有的「長時間指令要能看進度」原則，下次背景長跑會用 unbuffered 輸出。

使用者接著問「建議加長時間?」，追加跑了一個便宜的方向性檢查（seed=42，
兩變體都拉到 300k timesteps）：差距明顯縮小，但是 baseline 自己退化造成
的，不是 hnn 進步——hnn 在 100k/300k 兩個訓練預算下行為幾乎完全一樣
（連交易次數都相同），進一步證實它的訓練穩定性；baseline 反而顯得對
訓練時長敏感，跟 production 過去「訓練更久不保證更好」的教訓一致。
100k 這個 production 實際使用的比較點上，不 promote 的結論沒有改變。
