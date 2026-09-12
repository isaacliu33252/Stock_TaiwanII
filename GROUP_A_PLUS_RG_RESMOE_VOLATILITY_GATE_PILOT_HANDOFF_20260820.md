# GroupA+ RG-ResMoE Volatility Gate Pilot Handoff - 2026-08-20

## 2026-08-21 Addendum - supersedes the 2026-08-20 closed-negative wording

The 2026-08-20 conclusion below was written before the later multi-ticker,
high-vol-only, residual-VaR, and deep-MoE follow-up experiments. The final
state as of 2026-08-21 is more nuanced:

- Full RG-ResMoE promotion remains blocked.
- Deep MoE is explicitly rejected for GroupA+ daily signal.
- Residual-calibrated VaR is useful as a shadow diagnostic.
- H5 high-vol-only RG-ResMoE-lite is allowed as a shadow advisory only.
- No RG-ResMoE path may change target weights without a separate signed
  promotion review.

Current production-adjacent status:

- `group_a_plus/integrations/rg_resmoe_volatility_gate_shadow.py` now supports
  multi-ticker 0050/00631L daily snapshots, readiness-review loading, H5
  high-vol-only advisory payloads, and idempotent shadow logs.
- `group_a_plus/operations/daily_signal.py` now emits
  `rg_resmoe_volatility_gate_shadow` and
  `rg_resmoe_h5_high_vol_shadow_advisory`.
- The H5 advisory has `outputs_target_weights=false` and
  `allow_target_weight_change=false`.
- Latest 2026-08-21 run for actual data date 2026-08-20 kept weights unchanged:
  0050.TW 30%, cash 70%, 00631L/00632R/00679B 0%.

Final experimental summary:

- Multi-ticker lite soft gate:
  - Full promotion blocked because DM significance is not stable across
    0050.TW / 00631L.TW and H5/H10/H20.
  - H5 high-vol-only shadow is partial-ready:
    - 0050.TW H5 high-vol-only QLIKE +0.77%, DM p=0.0340.
    - 00631L.TW H5 high-vol-only QLIKE +1.04%, DM p=0.1629.
  - Residual-calibrated VaR with 756-day calibration window and 1pct tail
    buffer 1.35 passes the readiness layer.
- Deep RG-ResMoE:
  - Tested tiny neural residual MoE with frozen HAR-RV base, 3 experts, soft
    gate, dropout/weight decay/early stopping, and residual shrinkage.
  - Best conservative setting still failed promotion:
    - 0050.TW H5 deep -0.92%, H10 deep -2.97%, H20 deep +1.99% but not
      significant and recent slices remain negative.
    - 00631L.TW H5 deep +0.82%, but H10/H20 are negative.
  - Decision: do not wire deep MoE into daily signal.

Primary current artifacts:

- `report/group_a_plus/latest/rg_resmoe_volatility_gate_readiness_review.md`
- `report/group_a_plus/latest/deep_rg_resmoe_volatility_pilot_review.md`
- `results/group_a_plus_live_signal_v2_20260821_rg_resmoe_h5_advisory.json`
- `results/rg_resmoe_h5_high_vol_shadow_advisory_log.jsonl`
- `scripts/evaluate/evaluate_group_a_plus_deep_rg_resmoe_volatility_pilot.py`

Operational decision: keep RG-ResMoE-lite H5 high-vol shadow logging; do not
add deep MoE, do not alter alerts beyond existing advisory-only metadata, and
do not change target weights.

## 背景

使用者提供論文 `C:\Users\isaac\Downloads\2608.12251.pdf`（arXiv:2608.12251,
"Regime-Gated Residual Mixture-of-Experts for Cross-Sectional Volatility
Forecasting", Ye & Borde, Montclair State University），問是否有優點可以導入
GroupA+ / 最新策略（a2118）。

### 論文摘要

1,027 檔美股（另有 1,552 檔日股 TSE Prime 做複製）橫斷面五日已實現波動率預測，
30 個 walk-forward 窗口（2018-04 ~ 2025-10）。核心問題：regime 資訊（市場波動度
+ idiosyncratic 波動度）應該放在神經網路的哪裡。

- 把 regime 變數**直接串接進預測輸入**（如 `MLP-L(+z)`）：IC 下降，訓練嚴重不
  穩定（30 個 random seed 全部 collapse；標準 MoE 24/30 collapse）。
- 把同樣的 regime 變數**只拿來當 gate**（softmax 混合殘差修正 expert，base
  forecast 網路完全不吃 regime 變數）：IC 提升、VaR 校準改善、0/30 collapse。
- Soft routing 全面顯著優於 hard routing（learned top-1、波動度分位數切分、
  GICS 產業分類、market×idio split 全部輸給 soft gate，p < 10⁻⁴，見論文
  Table 5）。
- K=2~4 個 expert 即可，關鍵是「frozen base + zero-init 殘差」架構本身，不是
  expert 數量（K=2 只比 K=4 差 0.0004 IC；K=6 沒有更好還降低穩定性）。
- 效果集中在高波動期：COVID 期間 IC 優勢是全樣本的 6.7 倍，VaR calibration 在
  高波動 slice 改善最明顯。

## 適用性評估

GroupA+ 生產路徑幾乎全是 rule-based（chip risk score / momentum / ma_gap），
沒有一個「NN 把 regime 變數跟股票特徵串在一起當輸入」的既有元件，所以論文的
主結論（不要把 regime 串進輸入層）在目前 production 沒有直接對應的 bug 可修。

檢查過的候選落點：

1. **a2118 Last PPO 的 RL policy**（`FinRL/v2/environments/taiwan_stock_env.py`
   `_get_observation()`）：state vector 把價格(6)+技術指標(44)+型態(8)+法人
   買賣超(6，類 regime 資訊)+部位(4) 全部攤平成一個 flat MLP 輸入 —— 架構上
   正是論文說的 "bad" input pathway pattern。但 RL 是 reward-driven，論文情境
   是監督式 MSE regression，兩者訓練動態不同，論文結論不能直接套用；重構 PPO
   架構風險高、工程量大 —— **未動**。
2. **`group_a_plus/integrations/volatility_forecast.py`**（HAR-RV，目前只是
   diagnostic、未接 `target_weights`）：論文自己的 Table 3 裡 HAR 正是被
   RG-ResMoE 打敗的 baseline 之一，是唯一風險較低、可低成本驗證的落點 ——
   **本輪 pilot 的對象**。

### 重要既有負面先例（動手前先查過）

查了 `group_a_plus/research_semantic_registry.json`（11 條，沒有重複主題），
但發現兩個高度相關、概念上是同一類「regime-mixture/routing」的既有研究，
兩個都失敗：

- **`group_a_plus/integrations/specialist_router.py`**（arXiv:2604.10402v4
  "Risk-Sensitive Specialist Routing"，2026-07-10 已完整實作 + sweep 測試，
  見 memory `project_garch_specialist_routing_2008`）：`eligible_variants: []`，
  shelved。失敗原因整理：forecast metric 改善不等於 portfolio P&L 改善、
  a2118 baseline 已經很強、既有 diagnostics 高度相關(orthogonal 資訊少)、
  交易成本吃掉 marginal gain。
- **`group_a_plus/integrations/regime_switching_volatility_shadow.py`**
  （arXiv:2510.03236，soft mixture of regime-clustered HAR 係數集）：已測試，
  `results/group_a_plus_regime_switching_volatility_forecast_quality_latest.json`
  顯示 QLIKE 改善 **-150% ~ -207%**（h=5/10/20 vs plain HAR-RV），R² 由正轉負
  (-0.51)。這是同一個 0050.TW HAR-RV 預測目標上，用 changepoint 切割 + 係數
  clustering 的 regime mixture，慘敗。

這兩個先例是本輪 pilot 開始前就已知的重要背景 —— 決定了本輪要用「盡量保守、
可回退到 baseline」的架構（frozen base + 小幅殘差修正），而不是重新推導整組
係數，以降低重蹈覆轍的風險。

## Pilot 設計與實作

新增兩個 research-only 檔案，皆未接 `target_weights` 或任何 execution 路徑：

- `group_a_plus/integrations/rg_resmoe_volatility_gate_shadow.py`
- `scripts/evaluate/evaluate_group_a_plus_rg_resmoe_volatility_gate_pilot.py`

三條 walk-forward 路徑對照（呼應論文 Table 4）：

1. **base**：`har_rv_walkforward_forecast`（production 既有函式，原封不動
   reuse，不重新 fit）。
2. **input_pathway**：regime scalar 直接當第 4 個 OLS regressor，跟其餘 3 個
   HAR 特徵一起 fit 一個 walk-forward OLS（論文說的「bad」路徑，用來確認方向
   是否複製）。
3. **gate_pathway**：frozen base + regime-gated 殘差修正（論文說的「好」路徑）。

regime scalar（`regime_scalar()`）：20 日 / 120 日已實現變異數的 log ratio，
因果計算（只用截至當日的資料），是論文「市場波動度 regime state」在單一標的
情境下的類比。

Gate weight：regime scalar 的 trailing 252 日 percentile rank（`rolling(252,
min_periods=60).rank(pct=True)`），因果、無 look-ahead。

Walk-forward 紀律與 production HAR-RV 完全一致：`min_train_rows=130`、
`refit_every=21`、`rolling_window=504`、`train_end = i - horizon`（避免用到
目標區間內的資料）。

### 第一次踩到的真 bug（OLS 正交性）

第一版把殘差修正器 fit 在跟 base OLS **完全相同**的 3 個 HAR 特徵上：

```python
base_coef = _fit_ols(x_base, y)
resid_train = y - (base_coef[0] + x_base @ base_coef[1:])
resid_coef = _fit_ridge(x_base, resid_train, lam=ridge_lambda)   # 全樣本
```

驗證發現 `gate_pathway` 跟 `base_pathway` 的相對差異只有 `1e-15` 量級 —— 不是
「殘差訊號真的接近零」，是數學上注定如此：OLS 的殘差對其自身 design matrix
在 normal equations 下必然正交，所以在**同一個全樣本**上把殘差再對同樣的
`x_base` 做一次迴歸，係數必然趨近 0，跟 ridge 正則化強度無關。

修正：把 train set 依 regime scalar 的 in-sample 中位數切成 calm / stress
兩組，各自 fit 獨立的 ridge expert（K=2，呼應論文的 K=2~4 ablation）。正交性
只在「同一個迴歸的同一個樣本」內成立，切成兩個子集後每個 expert 各自的殘差
不再保證對 `x_base` 正交，才學得到東西。修正後 correction 量級變得有意義
（relative correction 中位數 ~3%，尾部到 60~80%）。

## 結果（第一版：硬切 calm/stress）

`--start 2018-01-02 --end 2026-08-19 --rolling-window 504 --ridge-lambda 4.0`，
`0050.TW`，n≈1,800~1,840 rows/horizon：

| Pathway | h=5 QLIKE改善% | h=10 | h=20 |
|---|---:|---:|---:|
| input_pathway | -4.18% | -3.27% | -11.87% |
| gate_pathway（硬切） | **-11.78%** | **-9.11%** | -6.85% |

- `input_pathway` 全部輸給 base，方向跟論文一致（直接串 regime 確實傷害預測）。
- `gate_pathway` 也全部輸給 base，且 h=5、h=10 時比 `input_pathway` 還差 ——
  論文的核心主張「gate 贏 input」**在此未複製成功**。
- per-year（2019-2026）h=5 有 6/8 年是負的，只有 2023 (+0.98%) 和
  h=20/2021 (+3.18%) 有微幅正值，沒有任何一年穩定 win。

## 使用者問「有什麼可以微調的」—— 第二輪追加測試

檢視後發現：硬切 calm/stress（用 regime scalar 中位數把 train set 切兩半各自
fit）本身就是論文 Table 5 明確測試過、證明**顯著輸給 soft routing**的 hard
routing 變體之一（"volatility quantile assignment"）—— 這不是調參數，是修一個
做錯的架構選擇，值得測一次，不算重複調參。

改成 **soft-weighted ridge**（`_fit_ridge_weighted`）：每筆訓練資料依其
regime scalar 在 train set 內的 percentile rank 給連續權重（`weight_stress =
rank`, `weight_calm = 1 - rank`），兩個 expert 共享重疊樣本而非硬切互斥。
新增 `gate_pathway_soft_h{horizon}` 欄位，跟硬切版本並存比較。

### 結果（軟權重）

| Pathway | h=5 | h=10 | h=20 |
|---|---:|---:|---:|
| gate_pathway（硬切） | -11.78% | -9.11% | -6.85% |
| **gate_pathway_soft** | **-1.05%** | **+0.34%** | **+0.32%** |

軟權重顯著修正了硬切版本最壞的失敗（改善幅度全面收斂到雜訊範圍 ±1% 內），
**複製了論文「soft routing 贏 hard routing」的結論**——這是本輪唯一算是
「驗證論文其中一個子結論」的正面發現。

但 per-year 拆解（h=5）：

| 年 | gate_hard | gate_soft |
|---|---:|---:|
| 2019 | -3.53% | -0.95% |
| 2020 | -4.08% | +0.60% |
| 2021 | -1.13% | +0.13% |
| 2022 | -3.22% | -1.73% |
| 2023 | +0.98% | +1.39% |
| 2024 | -2.30% | +0.39% |
| 2025 | -41.01% | -8.28% |
| 2026 | -21.26% | +3.69% |

軟權重版本正負參半（2019、2022、2025 仍偏負，2025 h=5 仍達 -8.28%），沒有
任何一個 horizon/年份組合展現穩定、有意義的優勢 —— **本質上是打平 base
HAR-RV，不是真正贏過它**。

到此為止**沒有再繼續調** `ridge_lambda`（目前 4.0）、regime scalar 的窗口
長度（20/120 日）、gate percentile 窗口（252 日）等旋鈕 —— 再往下轉會踩到
`feedback_overfitting_fixed_window_tuning`（固定窗口多輪調參 = overfitting
風險）：這已經是同一個 2018-2026 窗口上的第二輪架構調整，繼續轉下去就是在
挑一組讓同一份歷史數據好看的參數，不是驗證真實訊號。

## Why（為何論文結果沒有轉換過來）

論文的優勢來自 1,027 檔股票的橫斷面 pooling：很多資產共享同一個 base
forecast，同時個別/市場 regime state 驅動路由，這是真正有 pooling 結構可以
exploit 的設定。GroupA+ 的 HAR-RV 只預測單一標的（0050.TW）的波動度，沒有
這種橫斷面 pooling 結構。把 ~500 天 rolling window 的 train set 依 regime
切開（不論硬切還是軟權重）給兩個 expert，等於讓每個 expert 的有效樣本數
打折，這帶來的估計雜訊足以抵銷任何真實的 regime 依賴訊號能帶來的好處。

這是 GroupA+ 第三個因為同樣理由失敗的 regime-mixture / routing 嘗試：

1. `specialist_router.py`（arXiv:2604.10402v4）—— shelved，`eligible_variants: []`。
2. `regime_switching_volatility_shadow.py`（arXiv:2510.03236）—— QLIKE
   -150%~-207%，慘敗（因為整組係數重新估計，而非只加小修正）。
3. 本輪 `rg_resmoe_volatility_gate_shadow.py`（arXiv:2608.12251）—— 硬切版
   -6.85%~-11.78%，軟權重版打平（±1%），皆非改善。

三次結果收斂到同一個結論：**單一標的 HAR-RV 預測沒有足夠獨立的
regime-conditioned 訊號，能支撐 mixture/routing 架構贏過 plain pooled-sample
擬合** —— 不論架構做得多保守（frozen base + 小修正）或多忠實（soft routing）。

## 決定

**Closed negative。不建議把這篇論文的任何機制導入 GroupA+ / a2118。**

- 不 promote、不 wire 進 `daily_signal.py` 或任何 target_weight 路徑。
- 不建議在這個單一標的波動度預測上再嘗試 regime-conditioned mixture/routing，
  除非有真正新的機制（例如跨 GroupA+ 自己小型 ETF 池的橫斷面 pooling，那
  需要獨立驗證，不能假設會成功——GroupA+ 的資產池本來就小且高度相關，
  pooling 能提供的獨立訊號可能一樣有限）。
- PPO policy 的 flat state vector（唯一真正有「regime 當輸入」問題的地方）
  維持原樣不動：論文情境（監督式 regression）跟 RL 訓練動態不同，沒有可靠的
  轉換路徑，且重構風險/成本遠高於本輪已知的預期收益。

## 已改檔案 / 產出

Research-only，皆未接 production：

- 新增 `group_a_plus/integrations/rg_resmoe_volatility_gate_shadow.py`
  - `regime_scalar()`：causal 20d/120d GK variance log ratio。
  - `_fit_ridge()` / `_fit_ridge_weighted()`：標準化空間 ridge 迴歸，intercept
    不受懲罰；weighted 版本支援 soft routing。
  - `rg_resmoe_pathways()`：單一 horizon 的 base / input_pathway /
    gate_pathway / gate_pathway_soft 四條 walk-forward 序列。
  - `build_rg_resmoe_shadow()` / `latest_rg_resmoe_snapshot()`：跟其他
    shadow 模組同款的 multi-horizon frame + snapshot 介面，目前沒有任何
    呼叫者接它（未 wire 進 `daily_signal.py`）。
- 新增 `scripts/evaluate/evaluate_group_a_plus_rg_resmoe_volatility_gate_pilot.py`
  - pooled + per-year QLIKE/R²/win-rate 評估，三條 pathway 對 base 的比較。
  - 輸出 `results/group_a_plus_rg_resmoe_volatility_gate_pilot_latest.json`
    （`results/` 目錄已加入 `.gitignore`，不會被 commit）。
- 更新 `group_a_plus/research_semantic_registry.json`
  - 新增 `research_id: rg_resmoe_regime_gate_residual_correction_volatility`，
    `status: closed_negative`，含硬切版本結果 + 軟權重追加測試的完整 notes。

## 測試

**沒有新增測試檔案。** 因為結論確定是 closed_negative、不會 promote、不會
wire 進任何 production 路徑（跟 `specialist_router.py` 當初被 wire 進
`daily_signal.py` shadow log、因此需要正式測試覆蓋的情況不同），所以沒有
比照 production 模組的規格補測試。跑過的驗證僅止於：

- 手動確認 correction 量級（修 bug 前 `1e-15`，修 bug 後中位數 ~3%）。
- 完整跑過 pooled + per-year 評估兩次（硬切、軟權重），結果皆已寫入本文件與
  registry。
- `python3 -c "import json; json.load(...)"` 確認 `research_semantic_registry.json`
  修改後仍是合法 JSON。

若之後有人想繼續深入這個方向（不建議，見上），建議先幫
`rg_resmoe_volatility_gate_shadow.py` 補 `tests/test_group_a_plus_rg_resmoe_volatility_gate_shadow.py`
再動，尤其要覆蓋「硬切 vs 軟權重殘差不應該對 base OLS 特徵正交」這個踩過的
坑，避免未來重新踩到同一個 bug。

## Git 狀態

```text
?? group_a_plus/integrations/rg_resmoe_volatility_gate_shadow.py
?? group_a_plus/research_semantic_registry.json
?? scripts/evaluate/evaluate_group_a_plus_rg_resmoe_volatility_gate_pilot.py
```

`group_a_plus/research_semantic_registry.json` 原本就是 tracked 檔案，這次
只是新增一筆 entry（append），不是新建檔案，但因為 repo 目前有大量既有
uncommitted 變更（見本 session 開頭的 git status），這裡列出的三個檔案是本輪
唯一實際新增/修改的內容，其餘 dirty 檔案與本輪無關，不要假設已 commit，也
不要因為本文件而動它們。

## Memory

已寫入
`project_2608_12251_rg_resmoe_volatility_gate_pilot_20260820.md`（含硬切版本
與軟權重追加測試兩輪結果），並更新 `MEMORY.md` 索引。內容跟本文件重疊但
memory 版本更精簡，本文件是完整記錄。

## 一句話交接

使用者提供 arXiv:2608.12251（regime 資訊該當 NN 輸入還是當 gate）問是否可用
在 GroupA+；GroupA+ 沒有對應的 NN，唯一貼合落點是單標的 0050.TW HAR-RV
diagnostic，pilot 測試（含修正一個 OLS 正交性 bug、以及依使用者要求把硬切
routing 改成論文自己建議的軟權重 routing）顯示：軟權重確實修正了硬切版本
明顯更差的結果，複製了論文「soft > hard routing」的子結論，但修正後最多只是
打平現有 production HAR-RV，不是真正改善 —— 跟另外兩個既有的 regime-mixture
研究（specialist_router / regime_switching_volatility_shadow）殊途同歸：
GroupA+ 單標的波動度預測沒有足夠獨立訊號支撐這類架構。Closed negative，未
promote，未 wire 進任何 production 路徑。
