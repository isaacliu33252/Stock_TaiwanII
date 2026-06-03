# Group A 實驗記錄 — 交接文件
Date: 2026-06-03
Status: 實驗記錄完成，生產標準維持 Golden1_0531

## 1. 生產標準（不變）

**Golden1_0531** — 仍是 production entrypoint

- Final Value: 2,058,976
- Sharpe: 2.30
- MDD: -25%
- 特點：triplet_v4 + institutional + local regime gate + PVA + DCA

證據：`GROUP_A_GOLDEN1_0531_RELEASE.md`

---

## 2. 2026-06-03 全機能訓練

訓練命令：
```bash
python3 train_dual_group_2024_2026.py \
  --group-filter group_a --timesteps 300000 --seed 42 \
  --group-a-action-schema triplet_v4 \
  --group-a-enable-dca --group-a-dca-day 20 --group-a-dca-0050 5000 \
  --group-a-enable-pva-features --group-a-enable-pva-sigmoid \
  --group-a-enable-llm-sentiment \
  --group-a-enable-institutional \
  --group-a-enable-local-regime-gate \
  --group-a-00631l-max-weight 0.20 \
  --group-a-pva-weight 0.32 --group-a-pva-s-state-max-weight 0.35 \
  --group-a-pva-j-state-weight 0.19 --group-a-pva-m-state-weight 1.0 \
  --group-a-pva-drift-threshold 0.05 --group-a-pva-target-vol 0.012 \
  --group-a-pva-min-leverage-scale 0.40 --group-a-pva-inverse-hedge-budget 0.30 \
  --group-a-pva-buy-dip-strength 0.95 \
  --group-a-local-regime-risk-off-score-threshold 2 \
  --group-a-local-regime-severe-score-threshold 3 \
  --group-a-local-regime-risk-off-clear-days 3 \
  --group-a-local-regime-severe-clear-days 4 \
  --group-a-local-regime-risk-off-template 0050_only \
  --group-a-local-regime-severe-template 0050_70_00632R_30
```

結果：

| 指標 | 全機能版 | Golden1_0531 | 基本版(triplet_v2) |
| --- | ---: | ---: | ---: |
| Final Value | 2,686,446 | 2,058,976 | 3,572,755 |
| 年化報酬 | 55.51% | — | — |
| Sharpe | **1.860** | **2.30** | 1.857 |
| MDD | **-29.42%** | **-25%** | -36.15% |
| Trades | 109 | 63 | — |
| PVA次數 | 44 | — | — |
| DCA次數 | 28 | — | — |
| 總投入 | 1,140,000 | — | — |
| 淨利 | 1,546,446 | — | — |

觀察：
- Final value 高（2.69M > 2.06M），但 Sharpe 1.86 < 2.30，MDD -29% > -25%
- 高報酬但風險調整後表現較差，可能有過擬合或過度槓桿
- 基本版（無 overlay）最終值最高但 MDD 最差
- 全機能疊加並未提升風險調整表現

結論：Golden1_0531 維持生產標準。全機能方案需進一步調參。

證據：`results/group_a_backtest_20240101_20260508_20260603_150406.json`

---

## 3. 歷史實驗摘要（2026-05-31）

來自 `GROUP_A_GOLDEN1_0531_IMPROVEMENT_EXPERIMENT.md`：

- PVA 微調最佳候選：`pva_weight=0.36, j_state_weight=0.15`，Sharpe +0.004（不明顯）
- 當時判定：2026-08-31 前不改生產策略
- Local regime 測試：`risk_off_clear_days=7` 改善 MDD，但降低 final value
- `severe_template=0050_only` 減少交易但 MDD 惡化至 -54%

---

## 4. 待處理/未整合的實驗

以下實驗結果有潜力但尚未整合到正式訓練流程：

1. **Meta Ensemble** (`backtest_group_a_meta_ensemble_real.py`)
   - Sharpe 4.21, MDD -9%（回測看起來很好）
   - 但尚未进入正式 signal 生成流程

2. **A2C/SAC Shadow** (`train_group_a_a2c_sac_shadow.py`)
   - 100k timesteps 實驗
   - 模型已訓練但未整合到雙群組架構

3. **TDCC Shadow** (`run_group_a_tdcc_improved_signal.py`)
   - 已產生 signal但仍在 shadow 階段
   - 配置文件：`group_a_tdcc_improved_config.json`

---

## 5. 繼續方向建議

1. 近期（2026-06）：
   - 維持 Golden1_0531 生產標準
   - Meta Ensemble 整合進正式流程
   - 將 A2C/SAC Shadow 模型接入 dual-group 信號架構

2. 中期（2026-07 ~ 2026-08）：
   - 觀察 Meta Ensemble 實際表現
   - 2026-08-31 檢視是否要提升 shadow candidate `pva036_j015`

3. 風險控制：
   - 基本版 MDD 可達 -36%，需注意槓桿設定
   - PVA buy_dip=0.95 偏強，可考慮測試 0.90