# Group A+ 2026-08-11 交接記錄：arXiv:2607.18001論文審查 + golden1_0531 factor attribution/崩盤保護診斷 + backtest方法論bug發現

Status：單一session完整內容，本文件是最終版本，所有小節都已更新到跟現況一致。第12節原列的5項未完成事項，其中3項（bug修復、switch_ma*近期表現變差成因、00631L追蹤誤差假說）已在第13節收尾解決；1項（測試覆蓋）已補齊；1項（chip/risk/deriv系列納入長樣本）確認資料不存在，非能力問題，維持不做。

## 目錄

1. 論文審查：arXiv:2607.18001《AlphaZeroBeta: Deep Reinforcement Learning for Market-Neutral Portfolios》
2. 為什麼RL架構不採用，但方法論值得借用
3. 實作一：factor attribution迴歸腳本 + 短樣本結果
4. 實作二：family批次模式——18個switch policy變體全部無顯著alpha
5. 資料涵蓋率check + 拉長樣本到9.6年複驗
6. 實作三：崩盤期保護價值檢查（手選3窗口 → 客觀auto-detect 12 episode）
7. 落地：`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`新增第9項
8. 根因發現：`golden1_0531_1m`從未rebalance，00631L權重從20%飄移到62%
9. 最終確認：純屬backtest方法論bug，不是live風險
10. 本次session的檔案異動清單
11. 對應memory索引
12. 未完成/刻意不做的事項（第一輪判定）
13. 收尾（20260811第二輪）：修復bug、驗證item2/3假設、補測試覆蓋
14. 最終未完成/刻意不做事項（收尾後）

---

## 1. 論文審查：arXiv:2607.18001《AlphaZeroBeta: Deep Reinforcement Learning for Market-Neutral Portfolios》

使用者提供PDF：`C:\Users\isaac\Downloads\2607.18001.pdf`（Boris Belyakov, HSE University, 2026, 59頁，q-fin.PM）。

**核心方法**：Recurrent PPO + CNN-GRU策略，建構500+檔股票規模的多空市場中性組合，橫跨7個股指（S&P500、NASDAQ100、DJIA、FTSE、DAX、恒生、上證）。複合reward明確把「市場中性」寫進優化目標：

```
R_t = (r_p - r_m)/σ_p - λ1·Corr(r_p, r_m) - λ2·Σ|Δw_i|
```

每次rebalance的action先去均值再投影到ℓ1球（`Σw=0`且`Σ|w|≤1`），強制dollar-neutral。22折walk-forward（36月訓練/6月驗證/6月測試，逐折重訓）。Ablation（拿掉correlation penalty的RL版本）Sharpe更低、相關性衝到0.4-0.6、回撤更深——證明優勢來自reward設計，不是RL本身。Fama-French+動量+反轉+quality歸因確認策略beta≈0、alpha主要來自動量因子。

## 2. 為什麼RL架構不採用，但方法論值得借用

**問題設定根本不匹配**：這篇論文解決的是「500+檔股票多空市場中性選股」，需要跨股票同時建倉/放空的基建。Group A+目前的架構（`environments/taiwan_stock_env.py`、`portfolio_train_v2.py`）是單一標的（00631L/0050）的regime timing，不是跨股票多空系統，不是能力問題，是問題設定本身不同。

另外，RL portfolio路線在此專案已連續多次驗證失敗（見memory `project_alpha_reward_2607.16028_rl_env_upgrade_20260806`、DeepPocket/低風險DQN、PVM 1706.10059、FinSMART reward alignment），照搬整套RL架構風險高、報酬存疑。

**但factor attribution方法論本身跟RL無關，可以直接套用在既有production訊號上**：用迴歸量化「目前的高Sharpe有多少是真alpha、多少是disguised beta」，這是這次session的主線工作。

## 3. 實作一：factor attribution迴歸腳本 + 短樣本結果

新增`scripts/evaluate/build_group_a_plus_golden1_factor_attribution_review.py`（研究用，read-only查`results/*_curve.csv` + DuckDB `ohlcv`表，不動production pointer）。

**方法**：對golden1_0531的日報酬序列迴歸：
- `MKT` = 0050日報酬（市場beta）
- `LETF_XS` = 00631L日報酬 − 2×MKT（超出2倍槓桿追蹤的殘差部分）
- `TSMOM` = 20日動量方向 × 當日MKT報酬（time-series momentum）
- `REV1` = −1 × 前一日MKT報酬（1日反轉）

用`statsmodels.api.OLS`配Newey-West HAC標準誤（maxlags=5），跟既有`scripts/evaluate/letf_close_auction_overshoot_reversal_test.py`裡的HAC迴歸慣例一致。

**短樣本結果**（curve來源`results/group_a_plus_switch_policy_compare_golden1_20250102_20260703.json_curve.csv`，n=360，2025-01-03~2026-07-02）：

| 模型 | R² | 年化alpha | alpha p值 |
|---|---|---|---|
| beta-only (MKT+LETF_XS) | 0.989 | +1.26% | 不顯著 |
| 全模型(+TSMOM+REV1) | 0.993 | −0.93% | **0.594，完全不顯著** |

- MKT係數≈1.05（t=55, p<0.001）、LETF_XS係數≈0.22（t=12.9, p<0.001，顯著但小）、TSMOM係數0.071（t=4.06, p<0.001，顯著但小）、REV1不顯著
- 策略跟0050簡單相關高達0.991
- beta-only模型解釋了全模型99.6%的變異，動量/反轉只多解釋0.44%

輸出：`results/golden1_factor_attribution.json`、`report/group_a_plus/latest/golden1_factor_attribution.md`

## 4. 實作二：family批次模式——18個switch policy變體全部無顯著alpha

同一支腳本加`--family`模式：對curve csv裡所有欄位（不指定`--columns`時自動抓全部非`dt`欄位）跑同一套迴歸，輸出依alpha p值排序的比較表。

```
python3 scripts/evaluate/build_group_a_plus_golden1_factor_attribution_review.py --family
```

**結果**：curve csv裡全部18個變體（golden1_0531、group_a_plus_defensive、6個switch_ma*、3個switch_chip_*、2個switch_deriv_*、5個switch_risk_*）**alpha p值全部>0.5**（最小0.526），沒有一個有統計顯著的殘差alpha；全模型R²全部落在0.987~0.996之間，跟MKT相關性0.985~0.995。**不是golden1_0531特有的問題，是整個switch-policy研究路線在這段2025-01~2026-07多頭樣本裡共同的beta-explained現象。**

輸出：`results/golden1_factor_attribution_family.json`、`report/group_a_plus/latest/golden1_factor_attribution_family.md`

## 5. 資料涵蓋率check + 拉長樣本到9.6年複驗

短樣本（360天）幾乎整段都是多頭，可能只是「沒機會展現alpha」。派agent追查golden1_0531背後switch規則實際依賴哪些資料表，確認往前拉長歷史是否安全。

**發現真實的資料涵蓋率陷阱**：`foreign_shareholding_data`、`short_sale_balance_data`、`day_trading_data`、`dealer_futures_data`、`dealer_options_data`全部**2025-01-02才有資料**；`shareholding_distribution`在2022-05~2025-06有1120天缺口；`margin_data`在2022-08~2023-10有406天缺口。代表`switch_chip_*`/`switch_risk_*`/`switch_deriv_*`這幾個依賴籌碼資料的規則，往2025年以前延伸會**靜默失真**（缺資料被當成「沒有籌碼壓力」，恰好可能在2022熊市期間誤判），同`GROUP_A_PLUS_A2118_CHIP_DATA_CORE_CLOCK_AUDIT_HANDOFF_20260712.md`記載的worst-case clock問題同一類。純價格/MA/drawdown規則（`switch_ma*`）跟golden1本身不受影響。

**釐清golden1_0531本質**：它不是一個「訊號」，是PPO模型凍結後輸出的靜態目標權重快照（`results/signal_group_a_golden1_0531_predict_20260615_from_all_20260613_total1000000.json`：`{0050.TW:0.6, 00631L.TW:0.2, 00632R.TW:0.0, 00679B.TWO:0.0, cash:0.2}`），backtest裡用常數regime "golden1"跑`_simulate_regime_curve`（見第8節，這裡埋了後來發現的根因bug）。

用`--no-chip-features`重跑`backtest_group_a_plus_switch_policy.py --start 2015-04-01 --end 2026-08-10`（只讀不動production pointer，`--latest-pointer`重導向到`results/scratch_switch_backtest_longhist_latest.json`而非預設的`report/group_a_plus/latest/switch_backtest.json`）：

```
python3 backtest_group_a_plus_switch_policy.py \
  --start 2015-04-01 --end 2026-08-10 --no-chip-features \
  --output-prefix results/group_a_plus_switch_policy_backtest_longhist_golden1_20150401_20260810 \
  --latest-pointer results/scratch_switch_backtest_longhist_latest.json
```

實際涵蓋2017-01-12~2026-08-10（受00679B.TWO 2017-01-11上市限制），2325天，包含2018修正/2020 COVID崩盤/2022熊市。對golden1_0531+group_a_plus_defensive+6個switch_ma*規則重跑family迴歸：**結論不變甚至更穩固**——全部alpha p值仍>0.18（golden1_0531本身p=0.188最低，其餘0.2~0.85）。附帶發現golden1_0531的實際MKT beta在長樣本裡是**1.337**（短樣本只有1.046）——這個異常beta後來在第8節被查出根因。

輸出：`results/golden1_factor_attribution_family_longhist.json`、`report/group_a_plus/latest/golden1_factor_attribution_family_longhist.md`

## 6. 實作三：崩盤期保護價值檢查（手選3窗口 → 客觀auto-detect 12 episode）

全樣本迴歸測的是「平均超額報酬有沒有alpha」，答案是沒有；但switch策略設計的初衷是「崩盤時少賠」而非「平均跑贏大盤」，這是條件式(conditional on crash state)的價值，線性迴歸的average alpha框架本來就測不出來。

新增`scripts/evaluate/build_group_a_plus_golden1_crash_window_protection_review.py`（同樣research-only）。

**第一輪：手選3個知名崩盤窗口**（2018Q4修正、2020 COVID崩盤、2022全年熊市）：

| strategy | 平均超額報酬 vs MKT | 命中率 |
|---|---|---|
| switch_ma60_dd8_hold10 | +2.43% | 3/3 |
| （其餘5個switch_ma*） | +2.0%~+2.4% | 3/3全部 |
| group_a_plus_defensive | +0.14% | 2/3 |
| golden1_0531 | **−2.33%** | **0/3** |

6個規則×3次崩盤=18次全部同向為正——**但這個18/18其實是手選「知名」崩盤窗口造成的灌水**。

**第二輪：改用客觀演算法自動偵測drawdown episode**（`--auto-detect`，用trailing 252日rolling peak偵測跌破-8%的episode，而非全歷史cummax，避免2018-2019這種多年橫盤被誤判成同一個peak延續出多個假episode；merge相近episode用`--min-gap-days 60`）：

```
python3 scripts/evaluate/build_group_a_plus_golden1_crash_window_protection_review.py \
  --auto-detect --min-gap-days 60 \
  --curve results/group_a_plus_switch_policy_backtest_longhist_golden1_20150401_20260810_curve.csv \
  --output results/golden1_crash_window_protection_auto.json \
  --output-md report/group_a_plus/latest/golden1_crash_window_protection_auto.md
```

從2017-2026客觀找出12個獨立崩盤episode（2018/2019/2020/2021×2/2022/2023/2024/2025×2/2026×2）：

| strategy | 平均超額報酬 vs MKT | 命中率 |
|---|---|---|
| switch_ma20_dd5_hold5 | +1.79% | 10/12 |
| switch_ma60_dd8_hold10 | +1.36% | 9/12 |
| switch_ma20_dd7_hold5 | +1.48% | 9/12 |
| switch_ma60_dd10_hold10 | +1.10% | 9/12 |
| switch_ma90_dd12_hold5_eg020_xg010 | +1.10% | 9/12 |
| switch_ma120_dd12_hold15 | +1.03% | 8/12 |
| group_a_plus_defensive | −1.13% | 5/12 |
| golden1_0531 | **−2.88%** | **4/12** |

**方向不變但幅度更誠實**：switch_ma*規則的崩盤保護是真的，命中率67~83%，不是100%；平均效果也比手選窗口版本的+2.0~2.4%更保守，是+1.0~1.8%。

**新發現：golden1_0531的崩盤期表現逐年惡化**——2018-2019 episode大致打平甚至小贏（+0.99%/+1.00%），但2024-2026的episode全部大輸（−7.34%/−9.69%/−5.85%/−9.71%）。這個時間趨勢後來在第8節查出根因。

## 7. 落地：`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`新增第9項

把「mean-alpha迴歸 ≠ 崩盤保護，要分開驗證」+「手選崩盤窗口會灌水一致性，要用客觀演算法」寫成清單第9項（純文件性質，不改任何production/gate邏輯，跟既有第1-8項同一慣例）。適用範圍：任何claim有switching/timing/defensive-tilt價值的候選訊號，除了項目1-4的mean-return walk-forward檢查，還要跑崩盤期條件式比較。同時更新「How to apply going forward」段落加入第9項的適用條件說明。

## 8. 根因發現：`golden1_0531_1m`從未rebalance，00631L權重從20%飄移到62%

追查為什麼golden1_0531長樣本beta是1.337（遠高於名目60/20/20算出的~1.0）、且崩盤表現逐年惡化，查到`_simulate_regime_curve`（`backtest_group_a_plus_switch_policy.py:603-620`）：

```python
def _simulate_regime_curve(prices, regimes, weights_by_regime, initial_value):
    ...
    shares, cash = _rebalance(initial_value, prices.iloc[0], weights_by_regime[current_regime])
    for dt, price_row in prices.iterrows():
        value = _mark_to_market(price_row, shares, cash)
        next_regime = str(regimes.loc[dt])
        if next_regime != current_regime:          # <-- 只有regime改變才rebalance
            current_regime = next_regime
            shares, cash = _rebalance(value, price_row, weights_by_regime[current_regime])
            ...
```

golden1_0531用**常數regime series**（永遠`"golden1"`，見`backtest_group_a_plus_switch_policy.py:1279-1284`）——代表這條曲線從2017-01-12起只在t=0做過**一次**rebalance到0050:0.6/00631L:0.2/現金:0.2，之後9.6年**完全沒有再平衡**。

實際算出00631L權重漂移（用DuckDB `ohlcv`的0050.TW/00631L.TW收盤價重建）：

| 日期 | 00631L實際權重 | 0050實際權重 |
|---|---|---|
| 2017-01-12（起始） | 20.1% | 60.0% |
| 2020-01-01 | 29.7% | 56.3% |
| 2022-01-01 | 44.9% | 47.3% |
| 2024-01-01 | 47.2% | 44.8% |
| **2026-08-08** | **62.1%** | **35.8%** |

因為00631L是2倍槓桿ETF，在9.6年多頭為主的走勢裡複利遠超過0050和現金，從未被rebalance拉回，權重一路飄移。**這一個機制同時解釋了第5、6節的兩個異常**：(a)長樣本實際beta 1.337遠高於名目~1.0——到後期它早就不是60/20/20了；(b)崩盤期表現逐年惡化——到2024-2026時portfolio已經是接近62%槓桿ETF的高風險配置，同樣跌幅打下去自然比2018年那個真正的20%槓桿配置痛得多。

`golden1_0531_1m`這個標籤名不符實：「靜態60/20/20」的描述只在t=0成立，之後它是一個會自己越滾越槓桿的配置。

## 9. 最終確認：純屬backtest方法論bug，不是live風險

派agent追查`daily_signal.py`/`execution_plan.py`，確認這個「從不rebalance」的問題**只存在於`_simulate_regime_curve`這支backtest比較曲線裡，不影響任何真實資金部位**：

- Live production目前實際運行的是`a2118_a2111_ncf_late_bull_deleverage`策略（`group_a_plus/runners/latest.py:33-52`的`run_latest`分派邏輯，讀`report/group_a_plus/latest/strategy.json`決定活躍策略），**根本不是golden1_0531靜態權重**
- `daily_signal.py:1526-1534`每天重新計算`execution_regime`，`_resolve_weights`（`daily_signal.py:146-159`，`"golden1"→"golden1_0531_1m"`的別名對應）解析出base weights後，立刻疊加NCF-driven調整（`_apply_ncf_live_overlay`，`daily_signal.py:196-315`）+ a2118 late-bull de-leverage override——**即使regime停在"golden1"，實際target weights每天都在變**
- `execution_plan.py:198-244`的`_build_trades`每天拿**真實券商庫存**（`load_group_a_plus_holdings`解析即時庫存，`execution_plan.py:70-108`）跟目標權重比對；`_apply_execution_controls`（`execution_plan.py:247-293`）有真正的0.5% drift band（`min_weight_deviation=0.005`）觸發rebalance——下單仍是人工執行（`execution_plan.py:719`註解：目前沒有自動下單），但**目標權重每日重算並跟真實持倉比對，不是凍結不動**
- **直接證據**：`report/group_a_plus/latest/execution_plan.json`（生成於2026-08-08，`actual_data_date`2026-08-07）顯示真實持倉`{0050.TW:3994, 00632R.TW:2000, 00679B.TWO:3000}`——**00631L.TW實際持有量是0**，目標權重是`{0050:0.3, 00631L:0.0, 00632R:0.27, cash:0.43}`，跟golden1_0531名目60/20/20完全不是一回事，完全沒有漂移到62%槓桿的跡象
- `final_governance_snapshot.md`裡的`Golden1_0531 unchanged: True`（來自`scripts/evaluate/build_group_a_plus_final_governance_snapshot.py:176,222`的Decision Boundary boilerplate）只是指這份研究產出沒有重新定義golden1_0531的權重數字，不是指有真實部位凍結不動

**最終結論：golden1_0531_1m崩盤期表現逐年惡化只存在於`_simulate_regime_curve`這支backtest比較曲線裡（買一次後9.6年沒再平衡的方法論bug），不影響任何真實資金部位。沒有修改任何production程式碼、沒有動`_simulate_regime_curve`（多支腳本共用的核心模擬函式，這次未動它，只記錄為已知限制）。**

## 10. 本次session的檔案異動清單

| 檔案 | 性質 |
|---|---|
| `scripts/evaluate/build_group_a_plus_golden1_factor_attribution_review.py` | 新增，factor attribution迴歸（單一策略模式+`--family`批次模式），read-only查`results/*.csv`+DuckDB |
| `results/golden1_factor_attribution.json` | 新增，短樣本單一策略結果 |
| `report/group_a_plus/latest/golden1_factor_attribution.md` | 新增 |
| `results/golden1_factor_attribution_family.json` | 新增，短樣本18變體結果 |
| `report/group_a_plus/latest/golden1_factor_attribution_family.md` | 新增 |
| `results/group_a_plus_switch_policy_backtest_longhist_golden1_20150401_20260810.json/.csv/_curve.csv/_recommended_regime.csv` | 新增，`backtest_group_a_plus_switch_policy.py`重跑產物（2017-2026），只讀不寫production |
| `results/scratch_switch_backtest_longhist_latest.json` | 新增，`--latest-pointer`重導向目標（避免覆蓋`report/group_a_plus/latest/switch_backtest.json`） |
| `results/golden1_factor_attribution_family_longhist.json` | 新增，長樣本8變體結果 |
| `report/group_a_plus/latest/golden1_factor_attribution_family_longhist.md` | 新增 |
| `scripts/evaluate/build_group_a_plus_golden1_crash_window_protection_review.py` | 新增，崩盤期保護價值診斷（手選窗口+`--auto-detect`客觀偵測模式），read-only |
| `results/golden1_crash_window_protection.json` | 新增，手選3窗口結果 |
| `report/group_a_plus/latest/golden1_crash_window_protection.md` | 新增 |
| `results/golden1_crash_window_protection_auto.json` | 新增，auto-detect 12 episode結果 |
| `report/group_a_plus/latest/golden1_crash_window_protection_auto.md` | 新增 |
| `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md` | 修改，新增第9項+更新適用範圍段落 |
| 本檔案 | 新增，交接記錄 |
| `backtest_group_a_plus_switch_policy.py` | **修改（第13節）**：`_simulate_regime_curve`新增opt-in`rebalance_every_days`參數+docstring，`main()`新增`--rebalance-every-days` CLI參數並接上三個呼叫點。預設值`None`完全保留原行為，已用測試證明逐位元組相同。 |
| `tests/test_backtest_group_a_plus_switch_policy_rebalance_drift.py` | 新增，4個測試，驗證bug存在+修復有效+預設行為不變+regime-change trigger仍正常 |
| `tests/test_build_group_a_plus_golden1_factor_attribution_review.py` | 新增，4個測試 |
| `tests/test_build_group_a_plus_golden1_crash_window_protection_review.py` | 新增，5個測試 |
| `results/group_a_plus_switch_policy_backtest_longhist_rebalmonthly_20150401_20260810.json/.csv/_curve.csv/_recommended_regime.csv` | 新增，月度rebalance版長樣本backtest產物 |
| `results/scratch_switch_backtest_longhist_rebalmonthly_latest.json` | 新增，`--latest-pointer`重導向目標 |
| `results/golden1_factor_attribution_family_longhist_rebalmonthly.json` + `report/group_a_plus/latest/golden1_factor_attribution_family_longhist_rebalmonthly.md` | 新增 |
| `results/golden1_crash_window_protection_auto_rebalmonthly.json` + `report/group_a_plus/latest/golden1_crash_window_protection_auto_rebalmonthly.md` | 新增 |

**本次對話對production的實質異動：一處，且是backward-compatible的opt-in擴充。** `backtest_group_a_plus_switch_policy.py`的`_simulate_regime_curve`與`main()`有實質程式碼修改（第13.1節），但新參數預設值完全保留原行為，已用`pd.testing.assert_series_equal`跟既有12個測試+新增4個測試共16個測試證明沒有任何既有呼叫者/既有比較結果會受影響。除此之外，其餘所有新增檔案都是research-only診斷腳本、其輸出、測試、跟一份文件性質的驗證清單更新，沒有覆蓋任何`report/group_a_plus/latest/`下原本存在的正式檔案（`switch_backtest.json`已明確重導向避開）。

## 11. 對應memory索引

- `project_2607_18001_alphazerobeta_golden1_factor_attribution_20260810.md`（涵蓋第1-9節全部內容，含所有輪次的驗證結果與根因發現）
- 已連結既有：`project_alpha_reward_2607.16028_rl_env_upgrade_20260806`、`project_compounding_regime_guard_reverted_to_advisory_20260809`、`project_a2118_chip_core_clock_worst_case_reverted_20260712`、`project_a2118_original_promotion_evidence_reconstructed_20260725`

## 12. 未完成/刻意不做的事項

- **沒有修復`_simulate_regime_curve`的buy-once bug**——這是多支腳本共用的核心模擬函式（`backtest_group_a_plus_switch_policy.py:603-620`），改變它的行為（例如加入週期性/年度rebalance）會影響所有依賴這條曲線的既有比較結果，屬於需要獨立session評估影響範圍的改動，這次只記錄為已知限制，沒有動它。如果之後要修，最小改法是幫`golden1_0531`/`group_a_plus_defensive`這兩條「常數regime」曲線加一個獨立的週期性rebalance選項（例如每年或每季），不動`switch_*`規則本身的既有rebalance-on-regime-change邏輯。
- **沒有追查為什麼2024-2026的崩盤期`switch_ma*`規則也開始表現變差**（第6節auto-detect結果裡，2025-10/2026-02/2026-06三個episode，switch_ma*規則的excess return大多轉負，不像2018-2022那樣穩定為正）——這次只確認了golden1_0531的惡化根因（權重漂移），沒有進一步查switch_ma*規則本身近期表現轉弱的原因，值得之後單獨追查（可能是市場微結構改變、規則本身在新的波動度regime下失效，或純粹是小樣本雜訊）。
- **沒有查00631L近期（2024-2026）追蹤誤差/槓桿衰減是否本身惡化**——golden1_0531的崩盤期表現惡化理論上有兩個獨立成因：(a)本次確認的權重漂移(第8節)，(b)00631L本身的每日重置追蹤誤差是否在近期高波動環境下也變差。這次只驗證了(a)，(b)沒有單獨拆解驗證，兩者可能疊加。
- **`switch_chip_*`/`switch_risk_*`/`switch_deriv_*`系列規則沒有納入長樣本複驗**——因為其依賴的籌碼資料在2025年前有嚴重缺口（見第5節），刻意排除，只在原本的2025-2026短樣本family迴歸裡驗證過（結果同樣無顯著alpha，見第4節）。
- **兩支新診斷腳本沒有pytest測試**——刻意維持一次性研究診斷腳本定位，跟`GROUP_A_PLUS_20260810_2301_03186_QUADRATIC_BOUND_REGIME_CROSSCHECK_HANDOFF.md`同一節的慣例一致。
- **沒有commit**——使用者沒有要求commit，依既有慣例不主動提。

## 13. 收尾（20260811第二輪）：修復bug、驗證item2/3假設、補測試覆蓋

使用者要求把第12節的未完成事項做完才結案。

### 13.1 修復`_simulate_regime_curve`的buy-once bug（opt-in，不改預設行為）

在`backtest_group_a_plus_switch_policy.py:603-631`（`_simulate_regime_curve`）新增`rebalance_every_days: int | None = None`參數：預設`None`完全保留原本行為（regime改變才rebalance），只有明確傳入正整數時才會**額外**在regime不變的情況下每N個交易日也觸發一次rebalance。同步新增CLI參數`--rebalance-every-days`（`main()`），並把三個`_simulate_regime_curve(...)`呼叫點（golden1_0531_1m、group_a_plus_defensive_1m、每個`switch_*`變體）都接上這個參數。

**為什麼選擇opt-in而非改預設值**：`_simulate_regime_curve`被至少10支其他腳本引用（`backtest_group_a_plus_coverage_normalized.py`、`backtest_group_a_plus_copula_tail.py`、`backtest_group_a_plus_news_anomaly.py`、`backtest_group_a_plus_dynamic_exposure.py`、`scripts/backtest/backtest_group_a_plus_bayesian_selector.py`等，見`grep -rl "_simulate_regime_curve"`），改變預設行為會讓所有既有比較結果的基準線悄悄改變，屬於需要獨立session評估影響範圍的改動。opt-in設計讓這次的修復可以立即驗證假說，同時不影響任何既有production/研究產物。

新增測試`tests/test_backtest_group_a_plus_switch_policy_rebalance_drift.py`（4個測試，全過）：
1. 驗證預設(不傳參數)時常數regime確實從不rebalance，00631L權重會漂移超過50%
2. 驗證`rebalance_every_days=21`確實把週期性漂移的00631L拉回，最終值低於未rebalance版本（符合「讓贏家奔跑 vs 定期再平衡」的預期trade-off，不是bug）
3. 驗證`rebalance_every_days=None`跟完全不傳這個參數，結果**逐位元組相同**（`pd.testing.assert_series_equal`）——確保沒有任何既有呼叫者會看到行為差異
4. 驗證regime真的改變時（切到100%現金），即使設了`rebalance_every_days`，regime-change trigger依然正常運作

既有測試`tests/test_backtest_group_a_plus_switch_policy_2020_fix.py`、`tests/test_backtest_group_a_plus_switch_policy_chip_fallback.py`（12個測試）全部重跑仍通過，確認沒有破壞既有行為。

### 13.2 驗證假說：用`--rebalance-every-days 21`重跑長樣本，一次性驗證item 2跟item 3

第12節列的item 2（`switch_ma*`近期崩盤表現變差的原因未查）、item 3（00631L追蹤誤差是否本身惡化未拆分驗證），這次用同一個修復工具一次驗證完：

```
python3 backtest_group_a_plus_switch_policy.py \
  --start 2015-04-01 --end 2026-08-10 --no-chip-features --rebalance-every-days 21 \
  --output-prefix results/group_a_plus_switch_policy_backtest_longhist_rebalmonthly_20150401_20260810 \
  --latest-pointer results/scratch_switch_backtest_longhist_rebalmonthly_latest.json
```

**Factor attribution重跑結果**（月度rebalance vs 原本never-rebalance）：

| strategy | MKT beta（never-rebal） | MKT beta（月度rebal） |
|---|---|---|
| golden1_0531_1m | 1.337 | **0.993**（幾乎精準貼合名目60/20/20算出的~1.0） |

**Crash-window保護價值重跑結果**（同樣12個auto-detect episode）：

| strategy | 平均超額報酬（never-rebal） | 命中率（never-rebal） | 平均超額報酬（月度rebal） | 命中率（月度rebal） |
|---|---|---|---|---|
| golden1_0531_1m | −2.88% | 4/12 | **+1.38%** | **10/12** |
| group_a_plus_defensive_1m | −1.13% | 5/12 | **+2.30%** | **12/12** |
| switch_ma20_dd5_hold5 | +1.79% | 10/12 | +1.95% | 11/12 |
| switch_ma60_dd8_hold10 | +1.36% | 9/12 | +1.69% | 10/12 |
| （其餘switch_ma*規則） | +1.0%~+1.5% | 8-9/12 | +1.65%~+1.79% | 10-11/12 |

**結論：一個機制解釋了item 2跟item 3兩個問題，不需要分開驗證00631L追蹤誤差是否惡化**——golden1_0531的崩盤表現從全面落後（4/12勝率）**完全翻轉**成穩定優於大盤（10/12），MKT beta從異常的1.337精準修回名目值0.993；`switch_ma*`規則本身的命中率也全面從67-83%提升到83-92%。因為`switch_*`規則也是靠regime-change觸發rebalance（見`backtest_group_a_plus_switch_policy.py:1313-1319`），在市場強勢趨勢、regime維持golden1很長一段時間不觸發切換時，同一個「只在regime改變時才rebalance」機制也會讓這些規則在單一regime內部緩慢累積槓桿漂移——這就是2024-2026近期表現變差的完整解釋，**不是00631L本身的追蹤誤差/衰減惡化**，純粹是同一個weight-drift機制在不同規則上的程度差異（switch規則因為會定期切換出golden1而部分自我修正，golden1_0531因為永不切換而漂移到最嚴重）。

（附帶一提：月度rebalance版本的golden1_0531_1m**總報酬反而更低**——`9,645,582` → `6,238,162`——這正常，是「讓槓桿贏家奔跑換取更高平均報酬」vs「定期再平衡換取更好風險調整後/崩盤保護表現」的真實trade-off，不是新bug，兩種都是合理的設計選擇，只是原本的backtest意外地隱性選了前者卻標成後者。）

輸出：`results/group_a_plus_switch_policy_backtest_longhist_rebalmonthly_20150401_20260810.json/.csv/_curve.csv/_recommended_regime.csv`、`results/scratch_switch_backtest_longhist_rebalmonthly_latest.json`、`results/golden1_factor_attribution_family_longhist_rebalmonthly.json`+`.md`、`results/golden1_crash_window_protection_auto_rebalmonthly.json`+`.md`

### 13.3 補測試覆蓋（原第12節最後一項）

新增`tests/test_build_group_a_plus_golden1_factor_attribution_review.py`（4個測試）跟`tests/test_build_group_a_plus_golden1_crash_window_protection_review.py`（5個測試），對兩支診斷腳本的純函式（`_hac_ols`、`build_factors`、`_regress_strategy`、`_sample_caveat`、`_window_stats`、`detect_drawdown_episodes`）用合成資料驗證，不需要DB/網路存取。全部9個測試通過。

全部相關測試（`switch_policy`+`golden1_factor_attribution`+`golden1_crash_window`關鍵字）合計**25個測試全過**。

## 14. 最終未完成/刻意不做事項（收尾後）

- **`switch_chip_*`/`switch_risk_*`/`switch_deriv_*`系列規則仍未納入長樣本複驗**——這不是能力或時間問題，是資料本身2025年前不存在（見第5節），維持刻意排除。
- **沒有把`rebalance_every_days`的預設值改成非None**——這次驗證完假說後，`_simulate_regime_curve`的預設行為（regime-change-only rebalance）本身沒有改變，只是新增了選用工具。如果之後要讓golden1_0531_1m/group_a_plus_defensive_1m這兩條「參考基準」曲線的預設輸出也採用週期性rebalance（例如把`main()`裡這兩條曲線的呼叫寫死用某個rebalance頻率，區別於`switch_*`規則），需要額外決定「多久rebalance一次」這個新的設計參數本身該怎麼定，這次沒有主動做這個決定，留給之後需要用這條曲線當正式比較基準時再定。
- **沒有回頭修正已經產出的舊報告**（例如第3-6節提到的原始short-sample/long-history分析結果，包括本文件第3-6節列出的數字）——那些數字忠實反映了`_simulate_regime_curve`修復前的實際行為，是這次調查過程的正確記錄，不需要也不應該回溯修改；第13節的新結果是附加的對照組，不是取代。
- **沒有commit**——使用者沒有要求commit，依既有慣例不主動提。
