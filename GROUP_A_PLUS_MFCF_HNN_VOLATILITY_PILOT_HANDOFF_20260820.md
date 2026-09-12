# GroupA+ MFCF/HNN Volatility Pilot Handoff - 2026-08-20

## 背景

同一天 session 內第二篇論文。使用者提供 `C:\Users\isaac\Downloads\2608.14323.pdf`
（arXiv:2608.14323, "Dependence-Informed Sparse Neural Architecture for Stock
Return Prediction", Lin/Chen/Wang/Briola/Aste, UCL），問是否有優點可導入
GroupA+ / a2118。

第一篇（arXiv:2608.12251 RG-ResMoE，見
`GROUP_A_PLUS_RG_RESMOE_VOLATILITY_GATE_PILOT_HANDOFF_20260820.md`）分析完後，
我對這篇一開始只做了輕量可行性檢查（算相關矩陣/PCA）就停下來問使用者要不要
繼續，理由是「碰 a2118 的 PPO 架構風險比較高」+「今天已經連續三個
regime-mixture 嘗試都失敗」。**使用者糾正：「每一個論文都是獨立的, 都要詳細
驗証」**——已存成 memory
`feedback_verify_every_paper_independently.md`。本輪是照這個指示重做的完整
實作驗證。

### 論文摘要

問題：神經網路的深度/寬度該怎麼決定，而不是regime資訊該放哪裡（跟前一篇不同）。

方法：用 **Maximally Filtered Clique Forest (MFCF)** 對輸入特徵的絕對相關矩陣
做過濾，把高度相關的特徵組織成重疊的 cliques（上限大小 K 是唯一結構參數），
再把 clique 結構映射成 **Homological Neural Network (HNN)**：每個 clique 子集
是一個 neural unit，layer k 的 unit 只跟其 (k-1)-subset 的 layer 連接（集合
包含關係決定連接），每一層都有直接讀出到最終預測（不像傳統 MLP 只從最後一層
讀出）。

GKX 美股橫斷面月報酬預測（1987-2016，94 個公司特徵，30 個 walk-forward 年）：
HNN 跟手調的 3 層 MLP(NN3) 準確度打平，排序能力(Pearson IC)顯著更好（Holm
校正後仍顯著），參數量只要等寬 dense 網路的 **1/80**。Ablation 證實：(1) 打亂
特徵對應的 clique node 會讓 IC 顯著下降（不只是稀疏性有用，具體 clique 結構
本身帶訊息）；(2) 換成 fully-connected 的等寬 dense 控制組（80 倍參數）反而
排序更差。

## 適用性評估

GroupA+ 不是 cross-sectional 選股系統，沒有 94 個公司特徵這種東西。但
`FinRL/v2/data/technical_indicators.py` 為 a2118 Last PPO 的 RL state vector
算出 **55 個技術指標**（MA×7、MACD×6、KDJ×3、動量×4 等），全部攤平串成一個
flat MLP 輸入——這跟論文的「大量相關特徵、架構純手調」情境結構相同（前一篇
RG-ResMoE pilot 就已標記這個位置，但兩篇都沒有直接動 PPO）。

可行性檢查（真實 0050.TW 資料）：55 個指標兩兩 |correlation| 中位數 0.17，但
**7% 的 pair 相關係數 > 0.8**（MA3/5/10 互相高度重疊、KDJ K/D/J、MACD 三分量
等），PCA 只需要 **14 個主成分就能解釋 90% 變異**（20 個解釋 95%）——確認
55 維裡真正獨立的訊息量遠小於 55，論文要解決的問題在這裡真實存在。

## Pilot 設計

不直接碰 production 的 PPO（風險與工程成本太高，且 RL 訓練動態跟論文的監督式
regression 情境不同）。改在一個 research-only、可完全獨立驗證核心架構主張的
supervised task 上測試：**用 55 個技術指標預測 0050.TW 未來已實現
(Garman-Klass) 變異數**，重用既有 `volatility_forecast.py` 的 target 定義
(`_future_avg_variance`) 與 `risk_sensitive_loss.qlike_loss` 評估基礎設施，跟
production 的 frozen HAR-RV forecast 做比較。

新增（皆 research-only，未接 `target_weights`）：

- `group_a_plus/integrations/mfcf_hnn_volatility_shadow.py`
  - `build_mfcf_forest()`：簡化版 MFCF 貪婪演算法（見下方「MFCF 實作驗證」）。
  - `build_layer_structure()`：把 clique forest 轉成 H(k) 集合（論文 eq 5）。
  - `HNN`（`nn.Module`）：clique-structured 稀疏層 + all-layer linear readout
    (論文 eq 6-8)，`dense=True` 時退化成論文的 MLP-HNN 寬度匹配 dense 控制組。
  - `build_hnn_from_correlation()`：從相關矩陣直接建出 HNN，`shuffle_seed`
    支援論文的 input-shuffled ablation（拓撲/參數量不變，只打亂特徵-node 對應）。
  - `train_hnn()`：Adam + early stopping + target 標準化（見下方 bug #1）。
- `scripts/evaluate/evaluate_group_a_plus_mfcf_hnn_volatility_pilot.py`
  - h=5，`min_train_rows=250`、`refit_every=63`、`rolling_window=504`，
    2017-2026 共 37 次 walk-forward refit。
  - 每次 refit 訓練三個模型：`nn3_dense`（GKX 風格 3 層 32/16/8 dense MLP，
    論文的手調 baseline）、`hnn_marginal`（MFCF 導出的 sparse HNN）、
    `hnn_shuffled`（同架構同參數量，alignment ablation）。
  - 對比 production frozen HAR-RV，pooled + per-year QLIKE/R²/win-rate/
    參數量。

### MFCF 實作驗證

`build_mfcf_forest()` 是 Previde Massara & Aste (2019, arXiv:1905.02266) 演算法
的簡化近似（貪婪成長：優先把最高 gain 的 unplaced node 接到現有 under-full
clique 上，或從一個已滿 clique 的最相關 member 分支出新 clique，或當所有現有
方案 gain 都不夠好時，從剩餘 node 中挑最強的一對開一個全新 clique），不是
bit-identical 的原論文演算法，但用同一個 attachment score
`G(v,S) = sum_{u in S} D_vu^2` 跟同樣的 K-bounded-clique 輸出結構。

在真實 55 指標相關矩陣上跑（K=4），0.018 秒跑完，找出 20 個 cliques，語意上
完全合理：

```
['ma3', 'ma5', 'ma10', 'ma20']
['ma20', 'bb_upper', 'bb_lower', 'ma60']
['ma60', 'ma120', 'ma240', 'vwap']
['obv', 'obv_ma10', 'obv_slope']
['kdj_k', 'kdj_d', 'kdj_j', 'dmi_plus']
...
```

確認實作行為正常後才往下建 HNN。

## 抓到的兩個真 bug

### Bug #1：log-variance target 未標準化，dense 網路訓練卡死

第一次跑完整 37-refit walk-forward，`nn3_dense` 結果慘烈爆炸：QLIKE=3.96（vs
base 0.28），R²=-38.6，win_rate=2%。逐層檢查發現：target（log-variance，範圍
約 -9 到 -12）沒有標準化，網路初始化輸出接近 0，在給定的 epoch 預算（150
epochs, patience 15）內沒能把 bias 拉到正確量級，卡在一個離真實範圍兩個數量級
的常數輸出附近（train/test 預測值都幾乎不變，約 -5.16~-5.17）——不是真的
「dense 過擬合」，是我的訓練 harness 的優化問題。

修正：`train_hnn()` 內部把 target 用 train-window 的 mean/std 標準化再訓練，
訓練完用一個 `_AffineOutputWrapper` 把預測值還原尺度，對呼叫端透明。

### Bug #2（真正的架構 bug）：`self.index1` 型別不匹配，layer 2 mask 100% 全零

修正 bug #1 後，`hnn_marginal` 和 `hnn_shuffled`——這兩個本該因為 clique
alignment 不同而給出不同預測的模型——數值幾乎完全相同（QLIKE 到小數點後 4
位都一樣）。逐層印出 batch 內 activation variance 才抓到：

```
layer 2: z var across batch = 0.000000, mask nnz per row (min/max)=0.0/0.0
```

Layer 2 的 sparse mask **100% 是零**——完全沒有任何 connection。根因：
`HNN.__init__` 裡 `self.index1 = {next(iter(u)): i for i, u in
enumerate(layers[1])}` 把 key 存成**裸整數**（拆開 frozenset），但 layer 2
的 (k-1)-subset 查詢 `_order_minus_one_subsets(u)` 回傳的是 **frozenset**，
`prev_index.get(tau)` 型別不匹配永遠查不到，`if j is not None` 的 guard 悄悄
跳過所有 mask 賦值。Layer 3 以上不受影響，因為它們的 `prev_index` 是上一輪
迴圈自己建的 `index_k = {u: i for i, u in enumerate(units_k)}`，key 本來就是
frozenset。

結果：整個網路從 layer 2 開始對輸入完全無感（除了 readout scalar `beta_k` 以外
所有權重從 epoch 0 開始梯度就是精確的 0——用 Adam 訓練 300 epoch 也無法恢復，
因為梯度鏈斷在 `beta_k=0` 的初始值上，只有 `beta_k` 自己能收到訊號）。

修正：`self.index1 = {u: i for i, u in enumerate(layers[1])}`，跟其他層一致
用 frozenset 當 key。修正後同一個 window 的訓練集 R² 從卡在 ~0 附近變成
0.38。

**這代表修 bug #1 之後、bug #2 之前跑出來的任何 HNN 結果都是無效的**（一個
完全 broken、等效於常數輸出的網路，只是恰好那個常數接近訓練窗口的平均變異
數水準，帶有類似 persistence forecast 的偶然技巧，才會看起來有正 R²）。已
重新用修正後的程式碼跑過完整 37-refit walk-forward，以下是修正後的真實結果。

## 結果（修正後，37 refits，2017-2026，h=5）

| Model | 有效參數量 | pooled QLIKE 改善% (vs base HAR-RV) | R² | win_rate |
|---|---:|---:|---:|---:|
| nn3_dense (GKX 風格 3 層) | 2,577 | -55.54% | 0.135 | 39.6% |
| **hnn_marginal (MFCF 導出)** | **920 (中位數)** | **-31.81%** | **0.173** | **41.5%** |
| hnn_shuffled (alignment 打亂) | 920 (中位數) | -40.53% | 0.149 | 39.1% |

Width-matched dense 控制組（同層寬全連接，非上表的 nn3_dense）在代表性窗口下
有效參數量是 sparse HNN 的 **9.8 倍**（論文在 94 特徵/K 到 7 的設定下是 80
倍——方向一致，量級較小，因為這裡只有 55 特徵/K=4）。

Per-year（h=5, improvement% vs base）：

| 年 | nn3_dense | hnn_marginal | hnn_shuffled |
|---|---:|---:|---:|
| 2017 | -40.4% | -40.3% | -35.0% |
| 2018 | -35.5% | -10.2% | -43.9% |
| 2019 | +21.6% | +12.5% | +23.6% |
| 2020 | -72.0% | -64.8% | -76.1% |
| 2021 | -20.7% | -4.8% | +10.0% |
| 2022 | -32.7% | -24.5% | -11.9% |
| 2023 | -6.9% | -31.3% | -36.8% |
| 2024 | -117.4% | -88.5% | -96.4% |
| 2025 | +23.5% | +6.8% | +6.8% |
| 2026 | -249.8% | -60.4% | -135.0% |

### 解讀：這是本 session 唯一一篇兩個核心主張都定性複製成功的論文

1. **Sparse HNN 用更少參數打贏 dense**：`hnn_marginal`（920 參數中位數）在
   QLIKE、R²、win_rate 三項指標**全部贏過** `nn3_dense`（2577 參數），參數量
   只要 1/2.8——跟論文「HNN 用遠少於 dense 的參數達到同等或更好準確度」的主張
   方向一致。
2. **Clique alignment 本身帶有訊息，不只是稀疏性有用**：`hnn_shuffled`（同
   拓撲、同參數量，只是特徵-node 對應打亂）在三項指標**全部輸給**
   `hnn_marginal`——跟論文的 ablation 結論方向一致。

跟同一天稍早的 arXiv:2608.12251（RG-ResMoE，soft routing vs hard routing的
子結論有複製成功，但主結論gate贏input沒複製成功）以及更早的
specialist_router/regime_switching_volatility_shadow（完全失敗）相比，這是
架構層面複製得最乾淨的一次。

### 但仍是 closed_negative——不能 promote

三個 NN 變體（dense/sparse/shuffled）**全部輸給現有 production 的 frozen
HAR-RV baseline**：pooled QLIKE 改善 -31.8% ~ -55.5%，win_rate 全部低於
50%（39-42%）。Per-year 只有 2019、2025 三個模型全部打贏 HAR-RV（很可能只是
那兩年剛好比較容易預測，不是模型真的學到技巧），2020/2024/2026 則明顯落後，
2024 更是三個模型都輸超過 -88%。

根本原因：即使架構效率再好，**單一標的 ~500 天訓練資料、每個 refit window
從頭初始化訓練一個 NN**，仍然打不過一個已經調好的 3 特徵封閉解 OLS
（production HAR-RV）。這是資料量/任務難度的限制，不是架構選擇的問題——換
句話說，論文驗證的是「NN 架構怎麼設計比較好」，但 GroupA+ 這裡真正的瓶頸是
「NN 這條路本身在單一標的小樣本上打不過簡單線性模型」，這一層瓶頸不是
換架構能解決的。

## 決定

**Closed negative。不 promote，不 wire 進任何 production 路徑。**

但跟前三個純負面結果不同——這篇論文的架構主張是真的有實證支持，值得記住。
如果之後真的要重新檢視這個方向，更有意義的下一步**不是**繼續在這個單一標的
volatility forecast sandbox 上調參數，而是把 MFCF/HNN 用在 **a2118 Last PPO
實際的 52-57 維 flat state vector** 上（本 session 兩篇論文分析都標記了這個
位置，但都沒有動）——這才是論文的「大量相關特徵、架構純手調」情境真正對應
的地方，也是唯一可能讓「用更少參數、更好泛化」這個優勢真正發揮作用的場景
（PPO 訓練資料同樣有限，過度參數化的風險同樣存在）。但這是直接碰觸
production 決策引擎架構的高風險/高成本實驗，需要使用者明確同意才進行，本
session 沒有做。

## 已改檔案 / 產出

Research-only，皆未接 production：

- 新增 `group_a_plus/integrations/mfcf_hnn_volatility_shadow.py`
- 新增 `scripts/evaluate/evaluate_group_a_plus_mfcf_hnn_volatility_pilot.py`
- 更新 `group_a_plus/research_semantic_registry.json`（新增
  `research_id: mfcf_hnn_dependence_informed_sparse_architecture_volatility`，
  `status: closed_negative`，含兩個 bug 的完整記錄）
- 產出 `results/group_a_plus_mfcf_hnn_volatility_pilot_latest.json`
  （`results/` 已在 `.gitignore`，不會被 commit）

## 測試

**沒有新增測試檔案**，理由同前一篇 RG-ResMoE pilot：結論確定是
closed_negative、不會 promote、不會 wire 進任何 production 路徑。驗證止於：

- MFCF 實作在真實資料上產出語意合理的 clique（人工檢查）。
- 兩個 bug 的診斷過程本身就是詳盡的手動驗證（逐層印出 activation
  variance、mask 稀疏度、gradient norm、beta 係數演化），已記錄在本文件與
  registry 供未來參考。
- 完整跑過 37-refit walk-forward兩次（bug 修正前後），確認修正前後結果
  存在有意義的差異，不是雜訊。

若之後有人想在 `mfcf_hnn_volatility_shadow.py` 基礎上繼續（例如真的要碰 PPO
state vector），強烈建議先補
`tests/test_group_a_plus_mfcf_hnn_volatility_shadow.py`，至少覆蓋：(1) mask
稀疏度非零檢查（避免重踩 bug #2 這類靜默失敗）、(2) 一個小型合成資料集上
sparse HNN 的訓練 loss 確實會下降（避免重踩 bug #1 這類收斂假象）。

## Git 狀態

```text
?? group_a_plus/integrations/mfcf_hnn_volatility_shadow.py
?? scripts/evaluate/evaluate_group_a_plus_mfcf_hnn_volatility_pilot.py
```

`group_a_plus/research_semantic_registry.json` 同前一篇，只是新增一筆 entry
（append），本來就是 tracked 檔案。其餘 repo 既有 dirty/untracked 檔案與本輪
無關，不要假設已 commit。

## Memory

已寫入 `project_2608_14323_mfcf_hnn_volatility_pilot_20260820.md`，並更新
`MEMORY.md` 索引。另外新增了行為準則 memory
`feedback_verify_every_paper_independently.md`（記錄本輪一開始被使用者糾正
「每篇論文都要獨立詳細驗證」這件事本身，避免未來再犯同樣的省略）。

## 一句話交接

使用者提供 arXiv:2608.14323（MFCF clique 結構 → 稀疏 Homological Neural
Network，用來決定神經網路架構而非手調深度寬度）問是否可用在 GroupA+；一開始
我只做輕量可行性檢查就想停下問要不要繼續，被使用者糾正「每篇論文都要獨立詳細
驗證」後，改在 0050.TW 波動度預測 task 上完整實作 MFCF+HNN 並跟 dense/shuffled
控制組比較，過程抓到兩個真 bug（target 未標準化導致 dense 網路收斂假象；
`self.index1` 型別不匹配導致 sparse HNN 的 layer 2 mask 100% 全零、整個網路
對輸入完全無感）修正後重跑，結果：**論文的兩個核心架構主張（sparse 贏
dense、alignment 本身帶訊息）都定性複製成功**——這是本 session 唯一一篇
架構層面驗證成功的論文，跟同天另外三個 regime-mixture/routing 嘗試全部失敗
形成對比，值得記住。但三個 NN 變體仍全部輸給現有 production 的簡單 HAR-RV
baseline，因為單一標的小樣本從頭訓練 NN 本質上打不過調好的線性模型——結論
仍是 closed negative，未 promote，未 wire 進任何 production 路徑。
