# WeightWatcher 導入評估紀錄 - 2026-07-01

## 來源

- 來源路徑：`C:\Users\isaac\Downloads\WeightWatcher-master\WeightWatcher-master`
- 目標：評估是否有可導入 Group A+ 最新策略的優點。

## 專案摘要

WeightWatcher 是 DNN 權重譜診斷工具，不是投資組合權重工具。

核心概念：

- 不需要訓練資料或測試資料，只分析模型權重矩陣。
- 對 Dense / Conv / Embedding / Norm 等 layer 做 SVD / eigenvalue spectrum 分析。
- 用 Random Matrix Theory 與 heavy-tailed self-regularization 指標判斷模型權重品質。
- 支援 PyTorch、Keras、ONNX、PyTorch state_dict、safetensors。
- 輸出 layer-level details 與 summary metrics。

常見 summary 指標：

- `alpha`
- `alpha_weighted`
- `log_norm`
- `log_alpha_norm`
- `log_spectral_norm`
- `stable_rank`
- `mp_softrank`

原專案也有 correlation trap 分析/移除功能，但文件明確提醒該功能尚未充分測試，因此不適合導入 production 流程。

## 可取概念

可導入 Group A+ 的不是交易訊號，而是模型治理：

1. 模型權重健康報告
   - 對 NCF、TabNet、LSTM shadow、FinRL policy 等神經網路模型做 read-only 診斷。
   - 可輸出 `alpha`、`alpha_weighted`、`stable_rank` 等摘要。

2. over-trained / under-trained warning
   - WeightWatcher 以 `alpha < 2` 標記 over-trained、`alpha > 6` 標記 under-trained。
   - 可作為 retrain/sweep 結果的健康附註。

3. promotion gate 補充條件
   - Shadow 模型若想升級，不只看 AUC/Brier/Sharpe。
   - 也可要求權重健康無明顯異常，例如 layer 分析沒有大量 failed/under-trained/over-trained 標記。

4. 模型版本比較
   - 對同架構不同 seed/checkpoint 比較權重譜指標。
   - 可輔助判斷某個 seed 是否 seed collapse 或過度擬合。

5. 只讀模型審計
   - 不需資料集，適合離線掃描模型 artefact。
   - 對目前大量 `models/portfolio/*.zip` 有治理價值，但需要先載入 Stable-Baselines3 policy 才能分析。

## 不建議直接導入的原因

- 它不能直接分析 Stable-Baselines3 `.zip` 檔；必須先用 PPO/A2C/SAC 載入，再傳入 PyTorch policy/module。
- 依賴較重，包含 `powerlaw`、`safetensors`、科學運算套件；若放進 daily pipeline 會增加失敗面。
- 部分新功能如 trap removal 文件說明尚未充分測試，不適合自動修改模型。
- WeightWatcher 指標不是交易績效指標，不能替代 OOS AUC、Brier、Sharpe、drawdown、turnover。
- 目前 Group A+ active allocation 主要由策略規則與 NCF/output artifacts 管控，不應因權重譜單獨調倉。

## 與目前 Group A+ 的關係

目前已有：

- `group_a_plus/operations/ops_health.py`
  - 檢查資料/輸出/環境健康。
- `scripts/evaluate/evaluate_direction_magnitude_shadow.py`
  - 檢查方向/幅度 shadow 模型表現。
- 多個 NCF / relative-window / event attribution shadow report。

缺口：

- 尚未有模型 artefact 的 read-only 權重健康報告。
- 尚未把模型健康納入 promotion gate。
- 尚未對大量 Stable-Baselines3 `.zip` policy 做 seed/checkpoint 健康比較。

## 建議導入方式

建議做，但只做離線 shadow/governance，不進 active allocation。

優先順序：

1. 新增 `model_weight_health_shadow`
   - 可選輸入：Stable-Baselines3 `.zip` 或 PyTorch `.pt/.pth`。
   - 對 SB3 模型先嘗試 `PPO.load` / `A2C.load` / `SAC.load`，取 `.policy` 分析。
   - 若缺少相依套件或載入失敗，輸出 `status: unavailable`，不得讓 daily pipeline fail。
   - 輸出：
     - model path
     - framework
     - layer count
     - summary metrics
     - failed layer count
     - warning counts
     - `active_allocation_impact: none`

2. 接到 research health，而不是 daily execution
   - 可以放在 `results/model_weight_health_shadow_*.json`。
   - 不建議放進 `run_ncf_daily_pipeline.py`。

3. promotion gate 使用
   - 若某 shadow model 權重健康異常，只能降低 promotion confidence。
   - 不得直接改倉位。

## 結論

建議吸收 WeightWatcher 的「模型權重健康檢查」概念。

不建議導入 trap removal、自動修模型、或任何會改變 live allocation 的流程。

```text
decision = import_governance_concept_only
recommended_next_step = model_weight_health_shadow
active_allocation_impact = none
```

目前不需要改 Group A+ 實際配置。

## 針對 Group A+ 試導入結果

已完成 read-only shadow/governance 導入：

- 新增 `group_a_plus/operations/model_weight_health.py`
  - 不依賴 WeightWatcher 套件本體。
  - 使用輕量 SVD / eigenvalue spectrum 指標。
  - 支援 PyTorch state_dict。
  - 支援嘗試載入 Stable-Baselines3 `.zip`，分析 `.policy.state_dict()`。
  - 輸出 `alpha`、`alpha_weighted`、`log_norm`、`log_spectral_norm`、`stable_rank`。
  - 以 WeightWatcher 類似門檻標記：
    - `alpha < 2`: `over-trained`
    - `alpha > 6`: `under-trained`
  - 固定 `active_allocation_impact: none`。
- 新增 `scripts/run/check_model_weight_health.py`
- 新增 `tests/test_group_a_plus_model_weight_health.py`

測試：

```bash
.venv/bin/python -m pytest -q tests/test_group_a_plus_model_weight_health.py
```

結果：

```text
3 passed
```

實測掃描：

```bash
PYTHONPATH=. MPLCONFIGDIR=/tmp/matplotlib-model-health \
  .venv/bin/python scripts/run/check_model_weight_health.py \
  --model models/portfolio/group_a_plus_4tickers_2020_2025.zip \
  --model-type sb3 \
  --output results/model_weight_health_shadow_latest_20260701.json
```

實測摘要：

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

判讀：

- `group_a_plus_4tickers_2020_2025.zip` 可成功載入並分析 PPO policy。
- 2 個 layer 被標記為 `over-trained`，目前只代表治理 warning。
- 不應因此調整 Group A+ 權重；若未來該模型要升級為 active/advisory，應搭配 OOS AUC、Brier、Sharpe、drawdown、turnover 一起審核。
- 此工具不放入 daily pipeline，建議作為離線 research health check。
