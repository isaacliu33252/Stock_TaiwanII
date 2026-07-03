# Group A+ Model Weight Health 交接紀錄 - 2026-07-01

## 背景

使用者要求分析：

```text
C:\Users\isaac\Downloads\WeightWatcher-master\WeightWatcher-master
```

並針對 Group A+ 做改善。

WeightWatcher 是 DNN 權重譜診斷工具，不是投組權重工具。可吸收的重點是模型治理：用權重矩陣 SVD / eigenvalue spectrum 檢查模型是否有 over-trained / under-trained 等風險。

本次導入採取 read-only shadow/governance 方式：

```text
active_allocation_impact = none
not_in_daily_pipeline = true
model_mutation = none
```

## 新增檔案

### 1. `group_a_plus/operations/model_weight_health.py`

用途：

- 建立 Group A+ 模型權重健康 shadow report。
- 不依賴 WeightWatcher 套件本體。
- 使用輕量 SVD / eigenvalue spectrum 指標。
- 支援：
  - PyTorch state_dict：`.pt` / `.pth`
  - Stable-Baselines3 `.zip`：嘗試用 PPO / A2C / SAC 載入，取 `.policy.state_dict()`
- 固定輸出：

```text
active_allocation_impact = none
```

核心函式：

- `analyze_weight_matrix(name, weight)`
- `analyze_state_dict(state_dict)`
- `load_model_state_dict(path, model_type="auto")`
- `build_model_weight_health(model_path, model_type="auto")`

主要指標：

- `log_norm`
- `log_spectral_norm`
- `stable_rank`
- `alpha`
- `alpha_weighted`

Warning 規則：

```text
alpha < 2.0  -> over-trained
alpha > 6.0  -> under-trained
```

注意：這是受 WeightWatcher 啟發的輕量近似治理指標，不是完整 WeightWatcher 分析。

### 2. `scripts/run/check_model_weight_health.py`

用途：

- CLI wrapper。
- 產生 JSON output。

範例：

```bash
PYTHONPATH=. MPLCONFIGDIR=/tmp/matplotlib-model-health \
  .venv/bin/python scripts/run/check_model_weight_health.py \
  --model models/portfolio/group_a_plus_4tickers_2020_2025.zip \
  --model-type sb3 \
  --output results/model_weight_health_shadow_latest_20260701.json
```

參數：

- `--model`
- `--model-type auto|torch|sb3`
- `--output`

### 3. `tests/test_group_a_plus_model_weight_health.py`

覆蓋：

- 權重矩陣核心指標輸出。
- state_dict 分析會跳過 bias。
- 缺檔時輸出 `status: unavailable`，且仍保留 `active_allocation_impact: none`。

### 4. `WEIGHTWATCHER_IMPORT_REVIEW_20260701.md`

用途：

- 原始 WeightWatcher 專案分析紀錄。
- 記錄可取概念、不建議導入項目、Group A+ 試導入結果。

## 實測環境

工作目錄：

```text
/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main
```

檢查結果：

```text
torch ok 2.11.0+cu130
stable_baselines3 ok
```

執行時使用：

```bash
MPLCONFIGDIR=/tmp/matplotlib-model-health
```

原因：避免 matplotlib 嘗試寫入 `/home/isaacliu33252/.config/matplotlib` 時產生 cache warning。

## 實測模型

模型：

```text
models/portfolio/group_a_plus_4tickers_2020_2025.zip
```

大小：

```text
195K
```

載入方式：

```text
Stable-Baselines3 PPO.load(..., device="cpu")
framework = sb3_ppo_policy
```

輸出：

```text
results/model_weight_health_shadow_latest_20260701.json
```

## 實測摘要

```text
status                    warning
framework                 sb3_ppo_policy
layer_count               5
skipped_count             1
warning_count             2
summary.alpha             2.931536
summary.alpha_weighted    2.255281
summary.stable_rank       12.492131
warning_counts            {"over-trained": 2}
active_allocation_impact  none
```

前幾個 layer 範例：

```text
mlp_extractor.policy_net.0.weight
  shape       [64, 39]
  rank        39
  alpha       5.267735
  warning     none

mlp_extractor.policy_net.2.weight
  shape       [64, 64]
  rank        64
  alpha       5.098758
  warning     none

mlp_extractor.value_net.0.weight
  shape       [64, 39]
  rank        39
  alpha       0.690267
  warning     over-trained
```

## 判讀

目前結果是治理 warning，不是交易訊號。

2 個 layer 被標記 `over-trained`，表示該 PPO policy 的部分權重譜可能偏集中或重尾估計偏低，需要在模型升級審核時注意。

不得因此直接：

- 改 Group A+ 權重
- 調整 00631L / 0050 配置
- 覆蓋 NCF signal
- 自動 retrain
- 自動刪模型或修模型

建議用途：

- shadow model promotion gate 的輔助欄位
- seed/checkpoint 比較
- retrain 後健康檢查
- research health report

## 測試

執行：

```bash
.venv/bin/python -m pytest -q \
  tests/test_group_a_plus_model_weight_health.py \
  tests/test_group_a_plus_ops_health.py
```

結果：

```text
5 passed in 4.71s
```

單獨模型健康測試：

```bash
.venv/bin/python -m pytest -q tests/test_group_a_plus_model_weight_health.py
```

結果：

```text
3 passed in 4.61s
```

## 與既有 Group A+ 的關係

既有：

- `group_a_plus/operations/ops_health.py`
  - 檢查資料、輸出、系統資源。
- `scripts/evaluate/evaluate_direction_magnitude_shadow.py`
  - 檢查方向/幅度模型表現。
- `scripts/evaluate/evaluate_event_sentiment_attribution_shadow.py`
  - 檢查新聞情緒與 forward relative return。

本次新增：

- `model_weight_health.py`
  - 檢查模型 artefact 的權重健康。

分工：

```text
ops_health                 -> pipeline/output/environment health
model_weight_health_shadow -> model weight spectrum health
direction_magnitude_shadow -> predictive task metric
event_sentiment_attribution -> news sentiment attribution
```

## 不做的事

本次刻意不做：

- 不安裝 WeightWatcher 套件。
- 不導入 WeightWatcher trap removal。
- 不自動修改模型權重。
- 不把模型健康檢查接入 `run_ncf_daily_pipeline.py`。
- 不讓 warning 影響 live allocation。
- 不用權重健康指標取代 OOS performance。

## 後續建議

1. 掃描更多 Group A+ 候選模型

可比較：

```text
models/portfolio/group_a_plus_4tickers_2020_2024.zip
models/portfolio/group_a_plus_4tickers_2020_2025.zip
models/portfolio/group_a_plus_tripletv4_2020_2024.zip
models/portfolio/group_a_plus_retrain_2020_2024_tripletv4_inst_llm_pva_local_20260607.zip
```

2. 建立 multi-model summary

未來可新增：

```text
scripts/evaluate/evaluate_model_weight_health_sweep.py
```

輸出每個模型：

```text
model_path
status
framework
layer_count
warning_count
summary.alpha
summary.alpha_weighted
summary.stable_rank
```

3. 接到 research health summary

可建立：

```text
report/group_a_plus/latest/research_health.json
```

彙整：

- NCF health
- factor lens
- event sentiment attribution
- direction/magnitude shadow
- model weight health
- ops health

4. Promotion gate 建議

Shadow model 升級至少應同時檢查：

```text
OOS AUC > baseline
Brier not worse
Sharpe / drawdown not worse
turnover acceptable
sample size enough
model weight health no severe warning
```

## 目前狀態

```text
implementation_status = complete
tests = passing
latest_output = results/model_weight_health_shadow_latest_20260701.json
active_allocation_impact = none
recommended_usage = offline_governance_shadow
```
