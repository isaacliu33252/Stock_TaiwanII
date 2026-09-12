# GroupA+ 2608.08405 桌面審查 → Governance Tooling 交接記錄 - 2026-09-05

## Status

**已完結的研究線**。這是 2026-09-04/09-05 兩次對話對同一篇論文
（arXiv:2608.08405, "Robustness or Crowding: Experimental Design for
Trading Strategy Capacity"）的完整審查、實作、驗證、governance收斂記錄，
外加對「另一個 session 對同一篇論文做了不同處理」的衝突排查+逐行程式碼
審查。經過兩輪自我覆核（各抓到一個真問題並修復）+一輪對第三方程式碼的
深度審查（乾淨，無新發現），這條線的可信度已經反覆驗證過，沒有未解決
的阻塞項；有一項可選的後續（見「未做的事」）。

## 一、論文與主結論（2026-09-04）

論文是純方法論/實驗設計論文（非新alpha訊號、非新portfolio construction
技術）。解決「機構如何透過switchback實驗（多個平行sleeve、隨機分配不同
資金部署規模、固定期間持有、同日比較）量化策略資金容量(capacity)——即
部署多少資金會讓edge被crowding/market impact侵蝕」。

**判定：closed_negative，主框架不建議導入GroupA+。**

理由：
1. **前提不成立**：GroupA+目前AUM規模下market impact可忽略
   （見`project_a2118_microstructure_cost_stress_20260826`記憶），
   capacity/crowding問題本身尚不存在。
2. **機制不可複製**：實驗需要同一策略的100+個平行sleeves（機構多book/
   多執行通道結構），GroupA+是單一portfolio、單一決策路徑。
3. **性質不同**：這是「要不要/如何加碼策略」的因果實驗框架，不是alpha
   訊號/regime detection/optimizer方法。

完整記憶：`project_2608_08405_capacity_experiment_design_desk_review_20260904.md`。

## 二、跳脫主框架找可用構件（Fable model複查）

主框架不適用不代表全篇無可借鏡處。用 `model: fable` 的獨立agent複查，
逐項覆核後：

- **可用1（已實作+已驗證，見下）**：Bonferroni同時信賴帶取代自適應
  bracket（論文Prop 3.12/Table 8）——證明依序/自適應選網格後用兩點估計
  夾區間覆蓋率<50%（序貫細分後<20%），唯一有效法是對**事前固定**的整個
  候選網格做同時校正。
- **可用2（已寫入checklist）**：turnover-return迴歸內生性警告——「用
  realised return對realised turnover迴歸估到的是capacity slope與經理人
  自己加碼規則的混合物」。
- **弱可用（未實作）**：commonality criterion驅動因子篩選法——概念可
  借鏡，但統計力來自對13個異質策略算入選頻率，GroupA+子訊號數遠少於
  13，硬套樣本不足。
- **確認不可用**：erosion kernel/最小變異數attenuation回收權重/impact
  model單邊bound——全建立在「多sleeve累積部位產生持續性market impact」
  前提，與GroupA+規模結論直接衝突。

## 三、候選1的實作：`bonferroni_grid_significance()`

新增於 `group_a_plus/governance/significance.py`（diagnostic-only，
未接進 `compare_candidates()` 的 pass/fail gate，沿用該檔案既有的
"observe before wire" 原則，跟既有的 `jobson_korkie_memmel_test`/
`bootstrap_final_value_ci` 同一posture）：

```python
def bonferroni_grid_significance(
    results: dict[str, dict[str, Any]],
    *,
    candidate_grid_size: int,
    alpha: float = 0.05,
) -> dict[str, Any]: ...
```

- 對一組候選（每個都有JK-Memmel test結果）做Bonferroni校正。
- `candidate_grid_size` 必須由呼叫者明確傳入（搜索網格大小，非結果
  字典長度）——避免「搜完才回填網格大小」讓校正失效，這正是論文
  Prop 3.12 警告的失敗模式。
- 對非`ok`狀態的candidate直通、`candidate_grid_size < len(results)`
  時raise ValueError。

測試：`tests/test_group_a_plus_governance_significance.py` 新增4個
test（涵蓋大效應通過校正、邊際效應在大網格下被拒絕、非ok狀態直通、
網格大小檢查），連同既有7個test，**11 passed**。

## 四、候選1的回顧驗證：套用在真實歷史overfitting案例上

`feedback_overfitting_fixed_window_tuning` 記憶引用的歷史事件：
A22_bad_vol_overlay在4個固定窗口
（covid_2020/inflation_2022/live_2024_2026/active_2025_2026）上跑了
6輪以上coordinate descent，champion配置sum Sharpe從+0.001推進到
+0.045，看似持續改善；但2026-07-10對2017/2018/2019真實OOS資料驗證後
證實overfit（三年加總ΔSharpe=-0.058）。

**問題**：`bonferroni_grid_significance()` 若在OOS驗證之前就用，能不能
提早發現這是overfitting？

**做法**：`scripts/misc/significance_check_a22_bad_vol_overlay_grid_20260905.py`
（read-only research，不動production）：
- 重建champion vs baseline在4個原始調參窗口的每日報酬序列（用
  `evaluate_group_a_plus_a22_bad_vol_overlay.py`的`_simulate_a22_curve`，
  baseline用`vol_high`強制全False來重現「無A22 overlay」的golden1
  純權重曲線）。
- 對每個窗口跑`jobson_korkie_memmel_test`。
- `candidate_grid_size=33`（32個實際candidate結果檔`results/
  group_a_plus_a22_bad_vol_overlay_*.json` + 1輪round-0預設值，
  排除`latest`指標檔跟`a22_champion_*`事後確認檔）。

**結果**（`results/significance_check_a22_bad_vol_overlay_grid_20260905.json`）：
未校正前champion在4窗口中**沒有任何一個顯著贏過baseline**
（inflation_2022 p=0.031顯著但方向相反，champion比baseline差；
live_2024_2026 p=0.053臨界不顯著；covid_2020/active_2025_2026都
p>0.2）。校正後全部not significant。**baseline重建與原始腳本report
完全對上**（4窗口final value逐分逐角一致，回溯重建無誤）。

**結論**：這個工具不需要OOS資料，就能提早複製後來OOS驗證才發現的
「champion其實沒有真實優勢」的結論。

## 五、正式收斂進governance checklist

候選1、2都已寫入 `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`
的 **item 10**（simultaneous-coverage significance check for
multi-round search）跟 **item 11**（manager-scaling-endogeneity
caution），格式沿用該文件既有的「N. 標題, added日期 from
arXiv:XXXX...Applies to...」慣例，並更新了文件最後的「How to apply
going forward」段落。

## 六、自我覆核抓到並修復一個真漏洞（使用者追問「這邊分析有問題,有漏?」後）

重新檢查`bonferroni_grid_significance()`：`jobson_korkie_memmel_test()`
是**雙尾檢定**，`significant_at_5pct`只代表「兩個Sharpe有顯著差異」，
不代表「candidate顯著更好」。原本的`bonferroni_grid_significance()`
直接用`p_value`判斷`significant`，**沒有檢查`sharpe_diff`方向**。

這在第四節的A22回顧驗證裡已經真實出現：inflation_2022窗口p=0.031
（未校正下"顯著"），但champion Sharpe(-0.0639)其實比baseline(-0.0587)
**更差**，不是更好。若這個工具被直接接進未來的gate，會把「顯著更差」
跟「顯著更好」都標成`significant: True`，可能導致promotion決策誤判
（把確認變差當成確認有效果）。

**修復**：`bonferroni_grid_significance()`新增`significant_improvement`
欄位（`significant AND sharpe_diff>0`）跟`any_significant_improvement`
彙總欄位，明確跟原本雙尾的`significant`欄位分開。新增
`test_bonferroni_grid_significance_flags_significant_worsening_separately`
確認顯著變差不會被誤標。**12 tests全過**。同步更新checklist item 10
文字，明確要求未來使用者讀`significant_improvement`而非`significant`。
A22驗證腳本重跑，結論不變（`any_significant`跟
`any_significant_improvement`都是False，champion在4窗口都沒有顯著
優於baseline）。

## 七、再次自我覆核：抓到更根本的方法論落差（使用者要求「証明你有用,再重分析一次」後）

發現原本逐窗口分別套用`bonferroni_grid_significance()`（4個窗口各自用
`candidate_grid_size=33`校正）**不忠實重現實際選擇過程**：A22歷史上
champion是用「4窗口加總Sharpe」這個單一指標選出來的，不是4個獨立檢定。

改用Stouffer's method把4個窗口的z-statistic合併成一個檢定（更貼近實際
選擇邏輯，假設4個窗口彼此獨立——它們是不同、大致不重疊的曆史期間，這個
假設合理）：

```
covid_2020:       z=-0.86
inflation_2022:   z=-2.16
live_2024_2026:   z=+1.93
active_2025_2026: z=+1.24

combined z = sum(z)/sqrt(4) = 0.076
combined p = 0.939（跟uncorrected 0.05比、跟grid校正後的0.0015比都差很遠）
```

**4個窗口的效果方向兩正兩負、量級相近，幾乎完全互相抵消**——這是
overfitting的教科書特徵：每個窗口在fit各自的雜訊，沒有共同真訊號。這比
逐窗口分開檢定的結果更有力、也更貼近實際的「加總後選出champion」過程。

**已永久補進**`scripts/misc/significance_check_a22_bad_vol_overlay_grid_20260905.py`
（新增`combined_cross_window_check`欄位，module docstring追加說明），
並更新checklist item 10文字：套用在「用加總/pooled多窗口指標選出的
candidate」時，優先用combined-z重建法而非4個邊際per-window檢定。

## 八、發現並排查：另一個session對同一篇論文的獨立處理

2026-09-05對話中發現，repo裡已存在一份未commit的檔案
`GROUP_A_PLUS_20260904_2608_08405_CAPACITY_CROWDING_REVIEW.md`，記錄
了另一個（更早的、非本次對話衍生的）session對同一篇論文的處理：建立
一個「research-only capacity/crowding readiness gate」，**實際修改了
`scripts/run/run_ncf_daily_pipeline.py`**（git status顯示為modified，
非untracked），接入3個新pipeline步驟：

- `capacity_crowding_readiness_2608_08405`
  （`scripts/evaluate/build_group_a_plus_2608_08405_capacity_crowding_readiness.py`）
- `assigned_realized_deployment_shadow_2608_08405`
  （`scripts/evaluate/build_group_a_plus_2608_08405_assigned_realized_deployment_shadow.py`）
- `capacity_grid_shadow_2608_08405`
  （`scripts/evaluate/build_group_a_plus_2608_08405_capacity_grid_shadow.py`）

**排查結果（本次對話執行）**：
1. 三個腳本單獨執行都正常完成，輸出跟已存在的report檔案一致。
2. 對應測試 `tests/test_build_group_a_plus_2608_08405_*.py`（3個檔案，
   7 tests）全過；`tests/test_run_ncf_daily_pipeline.py`（23 tests，
   驗證整條pipeline wiring含manifest輸出）全過。
3. 三個report的`checks`/`blocking_reasons`欄位是**硬編碼常數**（例如
   `randomized_parallel_sleeves_available: False`永遠為False）而非
   動態運算——但這是**誠實反映一個不會變的結構限制**（GroupA+永久沒有
   平行sleeve），不是bug。
4. **沒有任何其他程式碼讀取這3個report的JSON去真正攔阻任何動作**
   （`promotion_allowed: false`等欄位沒有被消費）——這是純粹的
   pipeline常態性診斷/audit trail紀錄，跟`daily_signal.py`、
   `execution_guard.py`、真正的promotion gate完全沒有耦合。
5. 這個「每篇論文審查完就在pipeline裡加一個永久readiness_review診斷
   步驟」是這個專案**已經大量存在的既有慣例**（同一段pipeline清單裡
   還有`market_impact_readiness_review`、`sciphyrl_readiness_review`、
   `adversarial_market_integrity_review`、`finstressts_*`等一長串
   同類型步驟）。

**判定：兩條線的核心結論一致**（capacity實驗不可行、不能拿impact
model當capacity證據、不能改變即時權重），只是形式不同——一個是永久性
pipeline診斷文件記錄（沿用這個專案的主流慣例），一個是可重用統計
工具+checklist規則（沿用`significance.py`的observe-before-wire小眾
慣例）。**兩者不衝突，不需要回退任一邊，建議都保留。**

## 九、深度逐行審查另兩個腳本 + 公式數值驗證（結論：乾淨，未發現新bug）

第八節的排查只跑過腳本+測試，沒有逐行讀程式碼。這次把
`build_group_a_plus_2608_08405_assigned_realized_deployment_shadow.py`
跟`build_group_a_plus_2608_08405_capacity_grid_shadow.py`也逐行讀完，
並交叉比對實際production JSON檔案的真實欄位結構：

- 確認`live_signal.json`（有`data`包裝，`success`/`data`/`metadata`/
  `error`結構）、`execution_plan.json`（同樣有`data`包裝）、
  `market_impact_readiness_review.json`（**沒有**`data`包裝，欄位在
  top level）、`2608_08405_assigned_realized_deployment_shadow.json`
  （同樣沒有`data`包裝）——三個腳本對這些檔案呼叫`_unwrap()`與否的
  取捨都跟實際檔案結構一致：`_unwrap()`本身對「沒有data key」的
  payload是no-op（`payload.get("data")`回`None`時直接fallback回
  `payload`本身），所以即使某處沒呼叫`_unwrap()`也不影響正確性。
- 確認`live.get("reference_target_shares_before_cost")`、
  `plan.get("target_shares"/"theoretical_target_shares")`、
  `market.get("decision", {}).get("target_weight_change_allowed")`
  這些欄位名稱都真實存在於對應的production JSON裡，不是猜錯欄位名
  導致靜默失效。
- `assigned_realized_deployment_shadow.py`的三方比對（assigned vs
  execution_plan vs broker_sample shares）邏輯正確；broker sample裡
  `0050.TW: -2304`這種負股數是已知的「broker部位是transaction衍生、
  非官方對帳」資料品質問題（`negative_positions`欄位本身就有記錄），
  不是這個腳本造成的新問題，腳本正確地把它反映成
  `broker_positions_not_authoritative`/`broker_holdings_not_reconciled`
  blocker。
- `capacity_grid_shadow.py`的grid math（`deployed = capital * arm *
  risky_weight`、impact proxy線性隨arm縮放）是有標註"proxy"的簡化
  示意計算，符合其宣稱的illustrative定位，非精確聲稱。
- 額外用數值驗證了`capacity_crowding_readiness.py`裡`_finite_hold_
  fraction()`的公式（`F_L=1-a^L`、`G_L=1-a(1-a^L)/(L(1-a))`，抄自
  論文Section 3.2/Equation 3）：代入`persistence=0.9177, hold=24`
  （兩年期）算出`G_L=0.5945`，跟論文摘要說的「兩年持有回收約五分之三
  （59%）」完全對上，公式轉錄正確無誤。

**結論：這輪深度審查沒有找到新bug。** 跟第六、七節（我自己的
`bonferroni_grid_significance()`）不同——那两輪自我覆核都抓到真問題
（雙尾檢定沒判方向、逐窗口檢定不忠實重現加總選擇標準），這次審查別人
的程式碼是乾淨的。誠實記錄這個「沒找到問題」的結果，而非為了製造
「有用」的假象硬掰不存在的bug。

## 檔案清單

新增（本次對話，2026-09-04/09-05）：
- `group_a_plus/governance/significance.py`：新增`bonferroni_grid_significance()`函數
  + module docstring追加段落 + 事後修復方向性欄位`significant_improvement`
- `tests/test_group_a_plus_governance_significance.py`：新增6個test（含方向性bug的回歸測試）
- `scripts/misc/significance_check_a22_bad_vol_overlay_grid_20260905.py`：
  read-only回顧驗證腳本
- `results/significance_check_a22_bad_vol_overlay_grid_20260905.json`：
  驗證結果輸出
- `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`：新增item 10、
  11 + 更新「How to apply going forward」
- 本檔案

已存在但非本次對話所建（另一session，2026-09-04，排查確認無誤，
建議保留）：
- `GROUP_A_PLUS_20260904_2608_08405_CAPACITY_CROWDING_REVIEW.md`
- `scripts/evaluate/build_group_a_plus_2608_08405_capacity_crowding_readiness.py`
- `scripts/evaluate/build_group_a_plus_2608_08405_assigned_realized_deployment_shadow.py`
- `scripts/evaluate/build_group_a_plus_2608_08405_capacity_grid_shadow.py`
- `tests/test_build_group_a_plus_2608_08405_capacity_crowding_readiness.py`
- `tests/test_build_group_a_plus_2608_08405_assigned_realized_deployment_shadow.py`
- `tests/test_build_group_a_plus_2608_08405_capacity_grid_shadow.py`
- `scripts/run/run_ncf_daily_pipeline.py`（modified：3個新步驟wiring）
- `report/group_a_plus/latest/2608_08405_*.json`/`.md`（3組report輸出）

全部**未commit**（git status顯示untracked/modified）。本次對話沒有
commit任何東西——使用者尚未要求commit。

## 未做的事 / 可選後續

- 沒有把`bonferroni_grid_significance()`實際接進任何真正的promotion
  gate判定邏輯（跟`bootstrap_final_value_ci`一樣停在「先觀察」階段）。
  若之後要接線，需要先決定用在哪個gate、並比照`bootstrap_final_value_ci`
  的驗證期慣例。
- 「弱可用」的commonality criterion驅動因子篩選法沒有實作——GroupA+
  子訊號數量不足，等未來累積更多獨立子訊號後可重新評估。
- 這次沒有commit任何變更（含另一session留下的3個腳本+pipeline修改）。
  如果使用者想commit，建議兩條線分開兩個commit（governance
  tooling一個、capacity readiness gate一個），因為是不同session、
  不同動機做的獨立變更。
