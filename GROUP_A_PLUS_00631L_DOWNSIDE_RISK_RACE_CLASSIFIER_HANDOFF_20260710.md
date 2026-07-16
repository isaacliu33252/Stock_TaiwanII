# GroupA+ 00631L 下檔風險 Race Classifier 研究 Handoff - 2026-07-10

## 一句話

針對 00631L.TW 建了一整條「不對稱下檔風險」研究線：oracle 天花板全面正向，但現實 walk-forward 分類器在四輪迭代（自適應門檻／更深模型／改標籤／漸進式減碼）後仍無法穩定轉成正的 final value，**這條 ML 分類器線暫停，不 promote，不動任何 live signal / target weight**。過程中意外修復了 ohlcv 主表 2017-2019 三年的資料缺口（永久性修復，獨立於本研究是否成功）。

同日追加的 **A22_bad_vol_overlay**（規則式、trend-gated vol cap，見文末附錄）在 covid_2020/inflation_2022/live_2024_2026/active_2025_2026 這 4 個固定窗口上跑了 6 輪 coordinate descent，數字持續改善，一度看起來是全案最佳候選。**但用回補出來的 2017-2019 真實 NCF panel 做真正 out-of-sample 驗證後（2017/2018/2019 三個完整年度，完全沒被用來調參），champion 配置的表現打平到明顯變差（三年加總 Δfinal_value=-17,691、ΔSharpe=-0.058），完全沒有重現在那 4 個窗口上的正向結果——證實這 6 輪「進步」絕大部分是 overfitting，不是真正的 forward-looking edge。A22_bad_vol_overlay 現在也是暫停狀態，不可 promote。**這是本次 session 最重要的方法論教訓：同一組固定窗口上超過 2-3 輪參數搜尋後，必須做 out-of-sample 驗證才能宣稱進步，見文末附錄與 `feedback_overfitting_fixed_window_tuning` 記憶。

過程中還意外抓到並修復了 `scripts/misc/ncf_00631l.py`（production 每日 pipeline 用的模型）一個真 bug：熊市 regime fallback 在訓練樣本稀疏但驗證集熊市天數充足時會誤用牛市模型的錯誤長度陣列，`--full-panel` 模式下直接 crash。已修復，2020-2026 production 路徑沒受影響。

## 背景與動機

過去 ncf_2330（台積電個股模型）反覆發現「方向預測被推翻、尾部風險預測是唯一穩健訊號」（見 `NCF_2330_TSMC_STOCK_MODEL_HANDOFF_20260703.md` 系列）。這次把同樣的思路搬到 00631L：不追「所有高波動」，只追「往下的高波動」。

## 研究時間軸

### 第一階段：對稱波動率預測（已否決）

- 建了 `group_a_plus/integrations/volatility_forecast.py`：Corsi (2009) HAR-RV 模型，Garman-Klass 日變異數估計，h=5/10/20 三個 horizon 直接多步預測。
- 獨立驗證腳本 `scripts/evaluate/evaluate_group_a_plus_volatility_forecast_quality.py`（QLIKE loss，跟論文同一套）。修過兩個 bug：expanding→504天滾動視窗（`DEFAULT_ROLLING_WINDOW=504`）；ratio 欄位分母 scale 錯誤。
- h10 預測有真實預測力，但接進三段式規則（`scripts/evaluate/evaluate_group_a_plus_00631l_tiered_vol_control.py`）後四個標準窗口 final value 全部虧損。**結論：問題不在訊號準不準，在「對稱波動率」這個框架本身**——高波動不等於下檔風險。

### 第二階段：下檔專屬(不對稱)標籤 — oracle 天花板全面正向

- `scripts/evaluate/evaluate_group_a_plus_00631l_downside_oracle_ceiling.py`：用真實未來價格（不能實盤，只確認理論上限）測三種標籤。**四個窗口、三種標籤，Sharpe 全部正向**（+0.03~+0.26）——整個 GroupA+ 波動率/regime 路由研究史上第一次出現全面正向結果。
- 表現最好的是標籤 B（race down-first）：未來 10 日 00631L 先碰 -8% 還是先碰 +12%。

### 第三階段：真實 walk-forward 分類器 baseline + 意外資料缺口

- `scripts/evaluate/evaluate_group_a_plus_00631l_downside_race_classifier.py`：針對標籤 B 訓練 GradientBoostingClassifier，504 天滾動視窗、每 21 天重訓、horizon=10 嚴格無 look-ahead。
- **意外發現**：`ohlcv` 表裡 0050.TW/00631L.TW/00632R.TW/00679B.TWO 四檔核心標的，**2017-01-01 到 2019-12-31 完全零筆資料**（原始攝取檔案本身就跳過這段）。過去沒人發現是因為所有長窗口回測都同時要求 00679B（它自己 2020 年才有資料），從沒人單獨 query 過 2017-2019 的 0050/00631L。
- 修復：用 yfinance `auto_adjust=False` 重抓（第一次用 `auto_adjust=True` 預設值插入後在邊界發現價格不連續，跌 26%/漲 23% 的假跳空，刪除重抓）。修復後 `tests/test_check_ohlcv_freshness.py`（6測試）全過，兩處邊界平滑銜接。**此修復永久有效，跟本研究是否成功無關。**
- 修復後 baseline（純價格特徵，決策門檻 0.5）：

| 窗口 | AUC | 觸發天數 | Δfinal_value | ΔSharpe |
|---|---:|---:|---:|---:|
| covid_2020 | 0.639 | 9/185 | -21,790 | -0.086 |
| inflation_2022 | 0.538 | 76/246 | -29,899 | -0.162 |
| live_2024_2026 | 0.558 | 62/538 | -245,139 | +0.010 |
| active_2025_2026 | 0.508 | 47/296 | -156,171 | +0.013 |

covid_2020 AUC 明顯優於隨機，證明純價格特徵有訊號，但接進交易規則後 final value/Sharpe 仍是負的。

### 第四、五階段：門檻掃描 + 籌碼特徵

- 門檻掃描（純價格版）：**th=0.7 是甜蜜點**，live/active 兩窗口 Sharpe 轉正（+0.061/+0.075），inflation 大幅改善但未轉正（-0.044），covid_2020 在任何門檻下都卡在同一組 9 天觸發不變。**所有配置 final value 仍全部為負。**
- 加入 19 個真實籌碼/法人/衍生性商品特徵（`--use-chip-features`）：AUC 在 live/active 兩窗口明確改善（0.558→0.586、0.508→0.553），但重新掃過門檻(0.5/0.6/0.7/0.8)後沒有整體贏過純價格版 th=0.7。
- **細粒度補測**（0.65/0.75）發現 inflation_2022 對門檻單調遞增：th=0.8 時 ΔSharpe=-0.024、final_value=-13,580，是目前記錄過所有配置裡最好的 inflation 結果。但代價是 live/active 在高門檻反而變差，covid 在 th=0.65 後完全平坦。**四個窗口沒有共同的最優門檻**——covid 喜歡 0.65、inflation 喜歡 0.8、live/active 喜歡 0.65~0.7，regime-dependent tradeoff，不是還沒調到位。

### 第六階段：三個未耗盡方向逐一驗證

腳本擴充 CLI：`--threshold-mode {fixed,rolling_quantile}`、`--horizon`、`--race-down-threshold`、`--race-up-threshold`、`--n-estimators`、`--max-depth`、`--learning-rate`（全部可調，預設值不變）。

- **(a) rolling quantile 自適應門檻**：用 trailing 252 天預測機率分佈的 top-K%（測 0.85/0.90/0.95）取代固定 cutoff。**沒有任何 level 贏過已知最佳固定門檻**，多數更差。問題不在「固定門檻不會跟 regime 調整」，是模型在不同 regime 的可分性本來就不同，重新排名生不出額外訊號。
- **(b) 更有表達力的模型**：100 trees/depth=2 → 100 trees/depth=4。AUC 全面提升，**第一次撬動 covid_2020**（配合 th=0.85：Sharpe -0.086→-0.057、fv -21,790→-15,636，是全案 covid 最佳）。但 inflation/live/active 三窗口全部比 baseline 差，整體沒贏。
- **(c) 改標籤定義**：horizon=15 天全面變差；down 門檻收緊到 -6% 全面變差（inflation AUC 甚至跌破 0.5）；down 門檻放寬到 -10% 讓 covid Sharpe 創全案最佳(-0.030)，但只觸發 2 天、AUC=0.55 近隨機，樣本太少不可信；**horizon 縮短到 7 天讓 live/active AUC 跳到 0.68/0.67**（baseline 只有 0.56/0.51），但轉成交易規則後 Sharpe 反而更差——AUC 進步沒轉成錢。

三個方向的共同模式：**AUC/判別力持續在進步，但都轉不成 final value 的改善**。由此提出新假說：瓶頸可能不在分類器，而在下游「訊號一觸發就把 00631L 全部換成 0050」這個全有全無規則本身。

### 第七階段：漸進式減碼規則 — 假說被推翻

- 新增 `--derisk-mode {binary,graduated}`、`--graduated-low-threshold/--graduated-high-threshold/--graduated-buckets`：graduated 模式下換倉比例依預測機率在 [low,high] 區間線性內插、bucket 化後才觸發（避免每天因機率微幅變動換倉）。
- 重構：`_simulate_flagged_curve`+`_weights_de_risked` 統一成通用的 `_simulate_scaled_curve`+`_weights_scaled`（fraction=1.0 數學上等價於原本全額 de-risk，binary 模式=graduated 的 buckets=1 特例）。**重跑 baseline th=0.7 驗證數字跟重構前逐位元組相同，無 regression。**
- 測了 4 組 (low, high, buckets)：(0.4,0.8,4)、(0.6,0.8,4)、(0.5,0.9,4)、(0.65,0.75,2)近乎二元的窄帶版本。**四組全部在 inflation/live/active 三窗口比 binary th=0.7 baseline 差**，只有 covid_2020 偶爾略好一點點。
- 原因分析：graduated 模式的 low threshold 通常低於原本二元門檻，讓更多天出現非零 de-risk fraction，但這些新增觸發天數裡假陽性比例沒有下降——**多付了機會成本（部分減碼期間損失 00631L 槓桿溢價）卻沒有等比例換到保護力**。分批進出的交易成本結構在這裡反而比一次到位更差。
- **結論：假說被推翻。真正瓶頸看來還是分類器本身的假陽性率，不是規則的顆粒度。**

## 附錄：A22_bad_vol_overlay — 換規則骨架，不是 ML 分類器（同日追加，最終也暫停，見本節末尾的 out-of-sample 驗證）

上面七個階段全部在同一個 ML 分類器骨架下調（門檻/模型/標籤/規則顆粒度），使用者接著提了一個完全不同的規則式設計：

```
IF trend_good:    忽略 vol forecast
IF trend_neutral: vol high → 00631L cap 10%
IF trend_bad:     vol high → 00631L cap 0%
```

回應前先發現兩件事：

1. `group_a_plus/runners/a2126.py`（`golden1_dynamic_leverage_cap_shadow`）已經存在，是先前 session 留下、從未被任何評估腳本引用過的 uncommitted 草稿。它只在 golden1（趨勢好）內、且 `tail_risk_score>=1` AND `realized_vol_ratio_20_60>=1.25` AND `drawdown<=-8%` 同時成立時才把 00631L 砍到固定 15% 上限——邏輯方向跟這次提案相反（a2126 選趨勢好時觸發，提案選趨勢好時忽略）。
2. golden1 基礎 00631L 權重只有 **~10.92%**（四窗口皆相同、非逐日變動）。這代表 `neutral cap 10%` 幾乎是 no-op（只砍 ~0.9pp），真正有意義的槓桿是 `bad cap 0%`（等同全額 de-risk）。也連帶發現 a2126 的 15% 上限預設值同樣是 no-op——這解釋了為什麼從沒人發現這個參數選錯了：它從沒被跑過。

新腳本 `scripts/evaluate/evaluate_group_a_plus_a22_bad_vol_overlay.py`：

- trend 三分類：沿用 a2118 既有的 `frame["ma_gap"]`/`frame["drawdown"]`（跟 a2126 同一組 proxy），門檻可調（`--good-ma-gap-min=0.02`/`--good-drawdown-min=-0.05`/`--bad-ma-gap-max=-0.02`/`--bad-drawdown-max=-0.08`，drawdown 沿用 a2126 已驗證過的 -8%）
- vol_high：**沿用正式 production 的凍結定義**（`group_a_plus/integrations/garch_regime_shadow.py` 的 `ratio>=1.05 OR percentile>=0.70 AND return_5d<0`），跟目前 live 的 pre-trade guard 同一套判斷，不是重新發明的門檻

結果（四個標準窗口，vs a2118 baseline）：

| 窗口 | trend 分佈 (good/neutral_capped/neutral_uncapped/bad_capped/bad_uncapped) | ΔSharpe | Δfinal_value |
|---|---|---:|---:|
| covid_2020 | 144/6/10/15/10 | **-0.071**（全案第二好，僅次於 depth4+th0.85 的 -0.057） | -18,987（全案第二好） |
| inflation_2022 | 23/17/18/89/99 | -0.154（比 binary th=0.7 的 -0.044 差很多） | -24,774 |
| live_2024_2026 | 406/30/47/32/23 | **+0.068（全案新紀錄，超越 binary th=0.7 的 +0.061 和所有籌碼特徵版本）** | -168,337 |
| active_2025_2026 | 242/22/25/7/0 | -0.006（接近打平，遠不如 binary th=0.7 的 +0.075） | -132,202 |

判斷：混合結果，但模式跟 ML 分類器線完全不同（ML 線是「AUC 漲、賺錢能力跟不上」；這個規則式版本是「部分窗口創新高、部分窗口明顯變差」）。covid_2020 和 live_2024_2026 創下（或逼近）全案最佳 Sharpe，證明「trend 先決、vol 次要」這個骨架本身有東西。inflation_2022 變差的原因很清楚：該年 246 個 golden1 天裡有 188 天被自建 trend 門檻分類成「bad」，其中 99 天 vol 沒有 high 所以沒 cap（照規則字面設計，bad+vol 不 high 時維持 golden1 原倉位）——2022 年多數時間曝險沒被真正控制住，卡在「判斷出趨勢不好但 vol 訊號沒同時確認」的縫隙裡。這跟 GARCH/specialist routing 反覆出現的模式一致：同一套 regime 規則在不同危機年份反應不一致。

**這是本文件唯一一個在任一窗口創下全案最佳/次佳紀錄的非 ML 方案，是獨立候選、尚未暫停**——跟上面七階段 race classifier 線的「暫停」結論是分開的判斷。

### 補 inflation_2022 縫隙 — 全案第一次出現正的 final value

新增 `--bad-no-vol-cap`（trend_bad 但 vol 沒同時 high 時也套用一個 cap，預設 None = 維持原行為不動）。測了 0.10/0.05/0.0：

| bad_no_vol_cap | covid ΔSharpe / Δfv | inflation ΔSharpe / Δfv | live ΔSharpe / Δfv |
|---:|---:|---:|---:|
| None（原始） | -0.071 / -18,987 | -0.154 / -24,774 | +0.068 / -168,337 |
| 0.10 | -0.070 / -18,973 | -0.146 / -22,574 | +0.068 / -169,298 |
| 0.05 | -0.062 / -17,786 | -0.077 / -8,560 | +0.061 / -182,787 |
| **0.0** | **-0.053 / -16,566** | **-0.048 / +4,903** | +0.052 / -199,633 |

（active_2025_2026 不受影響，維持 -0.006 / -132,202，因為該窗口 `bad_uncapped` 天數本來就是 0）

**`bad_no_vol_cap=0.0`（trend_bad 就直接全額 de-risk 00631L，不等 vol 二次確認）是本文件全部階段裡最好的單一調整**：
- **inflation_2022 final value delta 轉正（+4,903）——這是整個 00631L 下檔風險研究線第一次出現正的 final value**，不只是風險調整後指標變好，是真的多賺錢。
- covid_2020 的 Sharpe(-0.053) 追平甚至微幅超越先前記錄的最佳值（depth4+th0.85 的 -0.057），用的是完全不同機制（規則式 trend 判斷，不是深模型）。
- 代價：live_2024_2026 惡化到本文件記錄過的最差 fv(-199,633)，因為多頭格局裡任何被判「trend bad」的正常回檔（沒有 vol 確認）現在都會全額 de-risk，容易在良性拉回時被甩轎。四窗口加總 final value 大致打平，不是消除虧損，是把虧損從 inflation/covid 搬去 live。

**判斷：不是暫停，是目前全部研究線裡最有希望的分支**。

### 加 trend_bad 連續天數過濾 — 全案目前最佳整體配置

新增 `_require_bad_persistence()` + `--bad-persistence-days`：trend='bad' 要連續撐滿 N 天才算 confirmed，未滿 N 天的 bad 日先降級成 'neutral' 處理（cap 規則改用 neutral tier：vol_high 才 cap 10%、不 high 不動）。**第一版有 off-by-one bug**（groupby cumcount 算法把 streak 多算 1，導致 `--bad-persistence-days 2` 實際上等效於 N=1，完全沒有過濾效果）——寫了獨立單元測試抓出來並修好。

在 `bad_no_vol_cap=0.0` 基礎上掃 N=1/2/3/4/5/7/10：

| N | covid ΔSharpe/Δfv | inflation ΔSharpe/Δfv | live ΔSharpe/Δfv | active ΔSharpe/Δfv | 4窗sum Sharpe | 4窗sum fv |
|---:|---|---|---|---|---:|---:|
| 1 | -0.053/-16,566 | -0.048/+4,903 | +0.052/-199,633 | -0.006/-132,202 | -0.055 | -343,498 |
| 3 | -0.057/-16,973 | -0.046/+2,568 | +0.063/-178,210 | **+0.015/-115,772** | -0.025 | -308,387 |
| 5 | -0.065/-18,269 | -0.018/+7,007 | +0.060/-176,475 | +0.015/-115,772 | -0.008 | -303,509 |
| **7** | -0.060/-17,286 | -0.014/**+7,029** | **+0.060/-176,390** | +0.015/-115,772 | **-0.009** | **-302,419** |
| 10 | -0.063/-17,484 | -0.003/+8,370 | +0.022/-202,524（開始反轉變差） | +0.015/-115,772 | -0.030 | -327,410 |

（active 在 N>=3 後 `bad_capped` 降到 0，之後 N 繼續增加不再有影響）

**N=7 是目前找到的最佳整體點**（N=3~7 都很接近，N=10 開始反轉、live window 惡化回去）。跟 N=1 相比：

- inflation final value 維持正值且還小幅改善（+4,903 → +7,029）
- **active_2025_2026 Sharpe 從負轉正（-0.006 → +0.015），fv 從 -132,202 改善到 -115,772**——第二個轉正的 Sharpe 窗口
- live_2024_2026 的 Sharpe（+0.052 → +0.060）跟 fv（-199,633 → -176,390）同時改善
- 唯一代價是 covid_2020 Sharpe 從 -0.053 小幅退到 -0.060（fv 退幅很小）
- 四窗口加總 Sharpe 從 -0.055 大幅改善到 -0.009（幾乎打平），加總 final value 虧損從 -343,498 收斂到 -302,419

**這是全案（含所有 race classifier 配置）目前整體表現最好的單一配置**：`trend_good 忽略 vol` + `trend_neutral vol_high→cap10%` + `trend_bad 連續 7 天 confirmed→cap0%`（未滿 7 天先當 neutral 處理）。四個窗口三個改善、只有一個小幅退步，是這整條研究線第一次出現這種結果。所有門檻（`--good/bad-ma-gap/drawdown-*`、`--neutral-cap`、`--bad-cap`、`--bad-no-vol-cap`、`--bad-persistence-days`）都已是 CLI 參數。

### 想救回 covid_2020 的兩個 bypass 設計 — 都被推翻，N=7 維持冠軍

診斷發現 N=7 比 N=1 差的 9 天精確對應到 2020-01-31 跟 2020-02-24~27 兩波「崩盤前早期警訊」的短 streak（撐不滿 7 天被降級成 neutral），且這 9 天**全部 vol_high=True**。試了兩個 bypass：

1. `--bad-severe-ma-gap-max`/`--bad-severe-drawdown-max`（急跌夠深就跳過 persistence）：**完全沒效果**——covid 真正重挫(drawdown<=-15%)要到 2020-03-12 才達到，但 streak 本身 2020-03-04 就已經自然滿 7 天確認了，bypass 永遠來不及生效。診斷前提本身就錯：N=7 傷 covid 不是「太晚確認崩盤」，是「弄丟早期警訊」，深度門檻救不了時間點問題。
2. `--bad-vol-confirms-immediately`（trend=bad 且 vol_high 同時成立就跳過 persistence）：精準命中那 9 天，covid 完全恢復到 N=1 數字，但代價是 active 完全打回 N=1 原始數字（active 裡被 N=7 過濾掉的短 streak 也全部 vol_high=True，一併被放行）、live 也退步。加總後明顯比純 N=7 差，不採用。

### trend 門檻掃描 — 找到真正的槓桿，新冠軍配置

四個 trend 門檻（`good_ma_gap_min`/`good_drawdown_min`/`bad_ma_gap_max`/`bad_drawdown_max`）從設計以來從沒掃過。逐一測試（都在 N=7、`bad_no_vol_cap=0.0` 基礎上）：

- 放寬 `good_ma_gap_min`（0.02→0.0）：**完全沒效果**，跟 champion 逐位元組相同，目前是死參數。
- 放寬 `good_drawdown_min`（-0.05→-0.08，跟 `bad_drawdown_max` 對齊、消除中間的 neutral 灰色地帶）：**covid_2020 巨幅改善**（ΔSharpe -0.060→-0.027，**是整個 00631L 下檔風險研究線目前最好的 covid 結果，贏過 ML 分類器線的最佳紀錄 -0.057**），live 的 fv 也大幅改善。代價：active_2025_2026 Sharpe 由正轉負。
- 收緊 `bad_ma_gap_max`/`bad_drawdown_max`：整體變差，不採用。

局部再掃 `good_drawdown_min` 的 -0.06/-0.08/-0.10（-0.10 跟 -0.08 完全相同，是平原邊界）：

| good_drawdown_min | covid | inflation | live | active | 4窗sum Sharpe | 4窗sum fv |
|---|---|---|---|---|---:|---:|
| -0.05（N=7 原冠軍） | -0.060/-17,286 | -0.014/+7,029 | +0.060/-176,390 | +0.015/-115,772 | +0.001 | -302,419 |
| **-0.06** | -0.027/-8,776 | -0.014/+6,925 | +0.057/-166,417 | +0.013/-105,850 | **+0.029（全案最佳 Sharpe 加總）** | -274,118 |
| **-0.08** | -0.027/-8,776 | -0.015/+6,909 | +0.052/-138,995 | -0.013/-100,189 | -0.003 | **-241,051（全案最佳 dollar 加總）** |

**`good_drawdown_min` 才是這整個規則真正的槓桿，`good_ma_gap_min` 目前是死參數。** 兩個新候選都優於原 N=7 預設：`-0.06` 是風險調整後報酬最均衡的（四窗口 Sharpe 加總全案最佳，沒有窗口轉負），`-0.08` 是 dollar term 最好的（代價是 active 轉負）。**建議把 `good_drawdown_min=-0.06` 當新的預設基準**，`-0.08` 留作備選。

**結論：這條線持續在進步，還沒有遇到明確的天花板。** covid_2020 的 Sharpe 代價已經被 `good_drawdown_min` 這個槓桿大幅回收，不再是「persistence 機制無法迴避的 trade-off」——上一輪的判斷已被推翻。

### 掃 neutral_cap — 意外發現 vol_high 訊號已經失去作用

在 `good_drawdown_min=-0.06` 基礎上掃 `neutral_cap`（0.0/0.05/0.10/0.15/0.20）：

| neutral_cap | 4窗sum Sharpe | 4窗sum fv |
|---:|---:|---:|
| 0.0 | -0.176 | -452,590 |
| 0.05 | -0.070 | -363,999 |
| 0.10（原值） | +0.029 | -274,118 |
| **0.15/0.20**（golden1 基礎 00631L 權重 ~10.92% 以上 = no-op） | **+0.043（全案最佳）** | **-259,926（全案最佳）** |

**neutral_cap 越低（越激進）結果越差，越高（越接近 no-op）結果越好**——這代表「neutral tier 輕度 cap」這個動作本身是負貢獻，關掉它（設到 baseline 以上變成 no-op）比原設計的 10% cap 更好。

進一步發現：目前 champion 配置下 `bad_cap` 跟 `bad_no_vol_cap` 都是 0.0（同一個值），neutral tier 的 cap 也是 no-op——**代表 `vol_high` 這個輸入在目前最佳配置裡已經完全不影響結果**，只剩 bookkeeping 上的差異。用 `--bad-no-vol-cap 0.05`（讓 vol_high=True 的天全額 de-risk、vol_high=False 的只 cap 到 5%，試圖重新引入 vol 當差異化因子）驗證：inflation final value 從 +7,470 惡化到 -5,516（直接轉負），sum sharpe 從 +0.043 退到 +0.010——**重新引入 vol 差異化反而讓結果變差**。

**這是一個重要、有點意外的結論修正**：A22 原本的核心構想是「用 vol 訊號決定要不要保護」，但一路迭代優化下來，實際跑出最好結果的配置已經完全不看 vol 了——真正在起作用的是「trend 連續壞 7 天就全額 de-risk，其他情況完全不動」這個純 trend-persistence 規則。**"bad_vol_overlay" 這個名字現在名不符實**，本質上已經變成 "trend_persistence_overlay"。這不代表 `vol_high` 這個 production 訊號本身沒用（它在 pre-trade guard 等其他地方仍是獨立驗證過的），只代表在 00631L 這個特定的 cap/de-risk 規則裡，把 vol 疊加在 trend 之上並沒有帶來額外價值——trend 本身（連續 7 天 ma_gap/drawdown 確認）已經包含了 vol 訊號想抓的大部分資訊。

### coordinate descent 回頭重掃 persistence_days — N=8 微幅超車，訊號收斂

換了 drawdown 門檻跟 neutral_cap 之後，原本選 N=7 的依據已經過時，回頭在新基準（`good_drawdown_min=-0.06`、`neutral_cap=0.15` no-op）下重掃 N=3~10：

| N | 4窗sum Sharpe | 4窗sum fv |
|---:|---:|---:|
| 7（前一輪冠軍） | 0.043 | -259,926 |
| **8** | **0.045（微幅最佳）** | **-255,498（微幅最佳）** |
| 9 | 0.022 | -269,401 |
| 10 | 0.012 | -288,222（開始反轉） |

N=8 些微超越 N=7，但**這輪的進步幅度明顯比前幾輪小**（前幾輪都是 20-40% 的加總指標跳動，這輪只有 ~1.7% 的 fv 進步）——代表 drawdown_min→neutral_cap→persistence_days 這輪 coordinate descent 已經接近收斂，數字只剩小數點後幾位在動。

**目前 champion 完整規格**：`good_ma_gap_min=0.02`（死參數，不影響）、`good_drawdown_min=-0.06`、`bad_ma_gap_max=-0.02`、`bad_drawdown_max=-0.08`、`neutral_cap>=0.11`（no-op）、`bad_cap=0.0`、`bad_no_vol_cap=0.0`、`bad_persistence_days=8`。4 窗口 sum Sharpe=0.045、sum fv=-255,498，都是全案（含所有 race classifier 配置）目前最佳紀錄，但邊際進步已經很小。

### 最後一輪 coordinate check + out-of-sample 嘗試被資料擋住 — 建議在此停止數值調參

在新基準（N=8, `good_drawdown_min=-0.06`, `neutral_cap` no-op）下測 `bad_drawdown_max` 收緊(-0.06)跟放寬(-0.10)兩個方向，**兩者都比預設值 -0.08 差**（sum sharpe 分別 0.026/0.005，sum fv 分別 -310,670/-285,365，都輸給 champion 的 0.045/-255,498）。確認 -0.08 已經是這個維度的局部最優。

原本想做真正的 out-of-sample 驗證（用 2018 Q4 這種沒被用來調參的獨立危機窗口測試目前 champion，而不是繼續在同一組 4 個窗口上疊代）——00631L.TW 價格資料從 2015-01-05 就有，理論上可行，**但 `results/ncf_00631l_panel_latest_20260707.csv`（a2118 NCF late-bull deleverage overlay 的必要輸入）只覆蓋 2025-01-02 到 2026-07-06**，2018 年完全沒有 NCF panel 資料，`run_a2118` 在 2018 窗口跑不出有意義的結果。這條驗證路徑目前被資料擋住，需要先回補 NCF panel 到更早年份才能做。

**明確的 overfitting 提醒**：這個 A22 champion 配置已經在同樣的 4 個固定歷史窗口上跑過 6 輪以上的 coordinate descent（drawdown 門檻 → neutral_cap → persistence_days → bad_drawdown_max）。每輪都在同一組資料上優化，數字持續改善不代表真正的 forward-looking edge，比較可能是在 fit 這 4 段歷史的特定雜訊。邊際進步幅度已經從 20-40% 收斂到 1.7%，這次 `bad_drawdown_max` 兩個方向都不再改善，是同一個收斂訊號的延續。**建議在此停止純數值調參**，除非先解決 NCF panel 的歷史回補問題以取得真正的 out-of-sample 驗證，或改用 bootstrap/synthetic resampling 這類不同性質的穩健度驗證方法。

下次接手直接從這組配置繼續，不用回去碰已經暫停的 race classifier 線；也不建議再對同一 4 個窗口做更細的參數網格搜尋。

### 真正的 out-of-sample 驗證 — champion 配置失效，A22 這條線也暫停

上面「被資料擋住」的 out-of-sample 驗證後來做成了。過程：

1. 用 `scripts/misc/ncf_00631l.py --train-start 2015-06-01 --val-start 2017-01-01 --val-end 2019-12-31 --full-panel` 回補 NCF panel 到 2017-2019。**第一次跑直接 crash**：`ValueError: Length of values (605) does not match length of index (125)`。
2. 定位到 production 腳本裡一個真 bug：熊市 regime 的 fallback 邏輯 `if (~above_ma200_val).sum()==0 or (~above_ma200_train_clf).sum()<20: clf_bear = clf_bull`，這個 OR 條件在「熊市訓練樣本 <20 天」時也會觸發 fallback，即使驗證集熊市天數充足（這次 n_bull=605/n_bear=125，明顯不是文件註解說的「0 bear samples / all-bull years」情境）。後果：熊市預測陣列直接借用長度不對的牛市陣列，`--full-panel` 模式下崩潰；即使不崩潰，log 也顯示 Bull/Bear AUC 逐位元組相同（其實是同一個物件）。**已修復**：兩處消費 `clf_bear["ensemble"]["proba"]` 的地方（H=1 cascade 區塊 + panel export 區塊）偵測到 `clf_bear is clf_bull` 時改用長度正確的中性 0.5 機率陣列。相關既有測試全過，這個分支在 2020-2026 production 資料上從沒被觸發過，不影響現行 daily pipeline。
3. 修好後成功產出 `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`（2017-01-03~2019-12-31，731 天，之前完全不存在）。
4. 用這份全新、從未被用來調參的 panel，對 A22 champion 配置（`good_drawdown_min=-0.06`、`neutral_cap` no-op、`bad_cap=bad_no_vol_cap=0.0`、`bad_persistence_days=8`）分別測 2017(多頭)/2018(修正年，含 Q4 真實下跌)/2019(復甦年) 三個完整年度：

| 年份 | golden1 天數 | baseline fv/Sharpe | A22 fv/Sharpe | Δfv | ΔSharpe |
|---|---:|---|---|---:|---:|
| 2017（多頭） | 199/236 | 1,140,980 / 1.701 | 1,141,055 / 1.708 | +75（可忽略） | +0.007（可忽略） |
| 2018（修正年） | 245/245（全 golden1） | 948,319 / -0.273 | 948,417 / -0.285 | +98（可忽略） | -0.012（可忽略） |
| 2019（復甦年） | 241/241（全 golden1） | 1,330,253 / 2.728 | 1,312,389 / 2.676 | **-17,864（真實虧損）** | **-0.053（明顯變差）** |

三年加總：Δfv=-17,691、ΔSharpe=-0.058。

**結論：champion 配置在真正沒被用來調參的資料上，表現是打平到明顯變差，完全沒有重現 4 個 tuned windows 上的正向結果（那邊 sum Sharpe=+0.045）。證實了「被資料擋住」那節提出的 overfitting 疑慮是真的——6 輪 coordinate descent 在同一組 4 個固定窗口上疊代出來的「進步」，絕大部分是在 fit 那 4 段歷史的特定雜訊，不是真正的 forward-looking edge。**

**A22_bad_vol_overlay 現在也是暫停狀態，不應該被視為已驗證、可以 promote 的候選。** 這是本次 session 最重要的方法論教訓：同一組固定窗口上超過 2-3 輪參數搜尋後，進步的可信度要打折扣，必須先做 out-of-sample 驗證才能宣稱真的變好——已寫成獨立的 feedback 記憶 `feedback_overfitting_fixed_window_tuning`，適用於未來任何策略研究，不只是這條線。

## 目前已知最佳配置（皆未通過 out-of-sample 驗證，不可 promote）

純價格特徵 + HAR-RV h10 輔助特徵 + 決策門檻 0.7 + **binary（全有全無）de-risk 規則**：

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_00631l_downside_race_classifier.py \
  --decision-threshold 0.7
```

（不加 `--use-chip-features`、不用 `--threshold-mode rolling_quantile`、不用 `--derisk-mode graduated`，horizon/race 門檻用預設 10/-8%/+12%，模型用預設 100 trees/depth=2）

4 個窗口中 2 個 (live/active) Sharpe 明確轉正、1 個 (inflation) 大幅改善未轉正、covid_2020 用門檻救不回。**所有已測配置 final value 仍全部為負**——只有風險調整後報酬有改善，不是真的賺錢。

## 主要檔案

Core：

- `group_a_plus/integrations/volatility_forecast.py`
- `scripts/evaluate/evaluate_group_a_plus_volatility_forecast_quality.py`
- `scripts/evaluate/evaluate_group_a_plus_00631l_tiered_vol_control.py`
- `scripts/evaluate/evaluate_group_a_plus_00631l_downside_oracle_ceiling.py`
- `scripts/evaluate/evaluate_group_a_plus_00631l_downside_race_classifier.py`（本次會話大幅擴充：`--threshold-mode`/`--derisk-mode`/`--horizon`/`--race-down-threshold`/`--race-up-threshold`/`--n-estimators`/`--max-depth`/`--learning-rate`/`--graduated-*` 全部是 CLI 參數）
- `FinRL/data/stock_db.py`（ohlcv 缺口修復用的既有 CLI）
- `scripts/evaluate/evaluate_group_a_plus_a22_bad_vol_overlay.py`（A22 規則式 overlay，`--good/bad-ma-gap/drawdown-*`、`--neutral-cap`、`--bad-cap`、`--bad-no-vol-cap`、`--bad-persistence-days`、`--bad-severe-*`、`--bad-vol-confirms-immediately` 皆為 CLI 參數）
- `scripts/misc/ncf_00631l.py`（本次修復熊市 regime fallback 的長度不匹配 bug，production 每日 pipeline 仍在用這個腳本）
- `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`（新回補的 2017-2019 NCF panel，之前不存在，未來 out-of-sample 驗證可直接重用）

Tests：

- `tests/test_group_a_plus_volatility_forecast.py`（6測試）
- `tests/test_check_ohlcv_freshness.py`（6測試，含缺口修復驗證）

Results（`results/group_a_plus_00631l_downside_race_classifier_*.json`，共 20+ 組）：

- `latest.json`：純價格 th=0.5 baseline
- `chip_th0{6,65,7,75,8}.json`：籌碼特徵門檻掃描
- `rq_price_0{85,90,95}.json` / `rq_chip_0{90,95}.json`：rolling quantile 自適應門檻
- `model_300d2.json` / `model_100d4*.json`：更深模型
- `label_h{15,7}.json` / `label_down{06,10}.json`：改標籤定義
- `grad_l*h*b*.json`：漸進式減碼

## 目前風險與注意事項

- **兩條子研究線都不能宣稱可以 promote**，全程 research_only，未接任何 live signal / target weight。
- race classifier 線：四輪迭代（自適應門檻、更深模型、改標籤、漸進式減碼）都測過且都被推翻，邊際報酬已經非常低。
- A22_bad_vol_overlay 線：6 輪 coordinate descent 在固定 4 窗口上看似持續進步，但 out-of-sample 驗證（2017/2018/2019）後打平到明顯變差，**確認是 overfitting**，不可 promote。
- ohlcv 2017-2019 缺口修復、NCF panel 2017-2019 回補、`ncf_00631l.py` 熊市 fallback bug 修復，三者都與本研究成敗無關、獨立有價值，已永久生效，不需要重做。

## 下一步建議

1. **兩條子研究線（race classifier / A22_bad_vol_overlay）現在都是暫停狀態，不可 promote**。不建議在沒有新想法之前繼續投入。
2. **最有價值的既有資產是 `results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`**——真實、之前不存在的 2017-2019 NCF panel。任何後續研究都應該先用它做 out-of-sample check，而不是又在 2025-2026 那組窗口上疊代。如果要進一步延伸 out-of-sample 覆蓋範圍（例如 2015-2016），用同樣的 `scripts/misc/ncf_00631l.py --train-start/--val-start/--val-end --full-panel` 指令即可，熊市 fallback 的 bug 已經修好。
3. 如果之後真的要重啟策略研究，值得先想一個**全新的規則設計**，而且從一開始就規劃「調參用一組窗口、驗證用另一組完全獨立的窗口」，不要像這次一樣調完才想到要驗證。
4. depth=4(+較高門檻) 是 race classifier 線裡唯一撬動過 covid_2020 窗口的手段（但同樣沒做過 OOS 驗證），如果之後要專門為危機情境調參，從這裡接著試，且要記得先用新回補的 2017-2019 panel 驗證。
5. 所有調校維度都已是 CLI 參數，之後要重跑任何一組掃描不需要改程式碼。
