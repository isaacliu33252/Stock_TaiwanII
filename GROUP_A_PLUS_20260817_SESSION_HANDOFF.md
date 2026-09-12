# Group A+ 2026-08-17 Session 交接記錄

**日期**：2026-08-17（週一）
**涵蓋範圍**：每日OHLCV資料下載、新聞來源三源現況確認、golden1_0531 vs a2118（最新策略）8/18預測（先後跑了「全新$1M零持股」跟「真實持股+$1M現金」兩種情境）、過程中發現並修復a2118 execution guard的籌碼資料過期阻擋、兩篇論文審查（2605.17446穩健VIX指數構造法乾淨關閉；2601.21447股債相關性動態，判定無production可接處但實測驗證了00679B/0050相關性確實regime-dependent且近期偏高）。

## 一句話摘要

先下載今天(08-17)OHLCV後確認新聞三來源(LTN/SETN/Yahoo)也已是今天資料。接著兩輪預測8/18的golden1_0531跟a2118目標：第一輪用全新$1M零持股情境，過程中發現a2118的execution guard被過期的`institutional_data`/`day_trading_data`(停在08-14)硬擋，補抓到08-17後解除；第二輪使用者提供真實持股workbook(`taiwan_stock_20260817.xlsx`)+確認沿用$1M現金餘額重算。兩輪全程未動到production(`execution_plan.json`/`live_signal.json` mtime全程維持08-14)。接著審查論文2605.17446(穩健VIX指數構造法)，判定不適用(Group A+無選擇權部位、且只是VIX的外部消費者不是生產者)乾淨關閉。最後審查論文2601.21447(股債相關性動態受貿易政策不確定性驅動)，這篇跟前面幾篇不同——00679B.TWO(元大美債20年)是Group A+四檔核心標的之一，資產類別直接重疊，因此用自己的0050.TW/00679B.TWO真實歷史資料做了實測驗證。

## 1. 每日資料維運

### 1.1 OHLCV下載
執行`refresh_group_data.py --group both`，Group A+ 9檔標的(0050/00631L/00632R/0056/00646/00679B/00713/00751B/00878)全部更新到`max_date=2026-08-17`，`status=refreshed`。

### 1.2 新聞來源確認
確認[[project_news_sources_setn_yahoo_ltn_backfill_20260817]]今天新排進pipeline的三個來源都已有今天資料（LTN 126篇、SETN、Yahoo皆含2026-08-17，均在今天中午12:25由某次背景執行的daily pipeline non-fatal步驟寫入，非本session執行）：
- `news/ltn_mainstream_rolling.jsonl`
- `news/setn_news_rss_rolling.jsonl`
- `news/yahoo_news_rss_rolling.jsonl`

**踩坑提醒**：`news/ltn_mainstream_2026-06-30_to_2026-08-16.jsonl`這類手動/回補用的範圍檔跟真正production消費的`news/ltn_mainstream_rolling.jsonl`是兩個不同檔案，只查前者會誤判「LTN還沒更新到今天」——要查`_rolling.jsonl`才是實際餵給`watchlist_news.py`的來源。

## 2. golden1_0531 vs a2118 8/18預測 — 第一輪：全新$1,000,000零持股

沿用[[project_golden1_0531_a2118_20260803_predict_divergence_20260801]]同一套固定流程，資料截至2026-08-17收盤（stale 1天）。

**golden1_0531**（`generate_dual_group_signal.py --group group_a --result-json results/group_a_backtest_20250101_20260525_20260526_193252.json --live-start --extra-cash 1000000 --override-holdings-json '{}' --as-of-date 2026-08-18`）：
判定`rebalance_to_0050_50_00631L_20_cash_30`（PVA疊加層未觸發，`pva_allowed=false`，純模型base action）：
- 0050.TW 50% → 4,697股 @ $106.45 ≈ $500,097
- 00631L.TW 20% → 5,563股 @ $35.95 ≈ $200,040
- cash 30% ≈ $299,863

輸出：`results/whatif_signal_group_a_20260817_215044.json`（非production pointer）。

**a2118（最新策略）**：第一次跑`group_a_plus.operations.execution_plan`（`--holdings-json`全零、`--cash-balance 1000000`、`--as-of 2026-08-18`、`--output`/`--latest-pointer`明確導向scratch）時**`execution_allowed=False`**：
```
required strategy sources are stale or missing: ['day_trading_0050', 'institutional_0050']
```
`institutional_data`/`day_trading_data`(ticker=0050.TW)最後更新是2026-08-14，落後3天，超過`max_business_stale_days=0`的硬gate。

**修復**：手動補抓這兩張表到08-17：
```bash
python3 FinRL/data/stock_db.py --add-institutional 0050.TW --start 2026-07-28 --end 2026-08-17
python3 scripts/fetch/fetch_finmind_chip_data.py --datasets day_trading --tickers 0050.TW --start 2026-07-28 --end 2026-08-17
python3 scripts/fetch/fetch_finmind_chip_data.py --datasets securities_lending --tickers 0050.TW --start 2026-08-01 --end 2026-08-17
```
補抓後重跑，`execution_allowed=True`，`planning_status=ready`：
- 理論(未分批)目標：0050 53% / 00631L 7.43% / cash 39.57%（7,396→改為零持股情境下的4,978股／2,066股）
- 因全新$1M零持股，首日大額分批(`max_initial_buy_fraction=0.4`)只放行部分：買進0050 1,991股($211,942)＋00631L 826股($29,695)，換手率24.2%
- 殘留警告(不擋單)：`securities_lending_0050`仍略滯後(soft)；NCF live overlay因00631L/00632R訊號停在08-13(4天前)被跳過，53/7.43%權重是**沒有NCF調整過的原始快取值**

**分歧說明**：golden1_0531現算(50/20/30) vs a2118讀的golden signal快取(53/7.43/39.57，`golden_signal_modified_at: 2026-08-14`)——這是已知的H3快取落差(golden signal沒有每天重新生成)，不是這次資料造成的新分歧，兩邊方向仍一致(都偏多、都要加碼0050)。

## 3. golden1_0531 vs a2118 8/18預測 — 第二輪：真實持股 + $1,000,000現金

使用者提供`taiwan_stock_20260817.xlsx`當作真實現持股，並在被問到「現金餘額要用多少」時選擇**沿用$1,000,000**（見AskUserQuestion紀錄）。

**真實持股**(workbook「即時庫存」列，僅列Group A+相關4檔，其餘0056/00646/00713/00751B/00878不在Group A+範圍會被忽略)：
- 0050.TW: 4,234股
- 00631L.TW: 900股
- 00632R.TW: 0股
- 00679B.TWO: 100股

**⚠️ 踩坑：這份workbook是「單一組別扁平格式」，跟兩個腳本原生的workbook解析器都不相容**：
- `generate_dual_group_signal.py`的`_group_column_bounds()`要找「Group A / Group B」欄位headers → 報錯`Workbook does not expose both Group A / Group B headers`
- `group_a_plus.operations.execution_plan`的`_parse_group_a_plus_holdings()`要找「Group A++」或「Group A+」字樣的儲存格 → 報錯`Workbook has no Group A++ section`

兩者都改用手動讀出持股數字後，透過`--override-holdings-json`(generate_dual_group_signal.py)／`--holdings-json`(execution_plan.py)明確傳入JSON繞過，而非直接傳`--workbook`／`--xlsx`。**下次遇到這類扁平格式workbook直接採用這個繞過法，不用再猜測欄位格式。**

**golden1_0531**（`--override-holdings-json '{"0050.TW":4234,"00631L.TW":900,"00632R.TW":0,"00679B.TWO":100}' --extra-cash 1000000 --live-start`）：
總資產 = 持股市值$485,671 + 現金$1,000,000 = **$1,485,671**。判定同樣是`rebalance_to_0050_50_00631L_20_cash_30`：

| | 現在 | 目標 | 動作 |
|---|---|---|---|
| 0050.TW | 4,234股 | 6,978股 | 買進2,744股(≈$292,131) |
| 00631L.TW | 900股 | 8,265股 | 買進7,365股(≈$264,832) |
| 00679B.TWO | 100股 | 0股 | 賣出100股(≈$2,607) |
| cash | — | 30% | ≈$445,701 |

輸出：`results/whatif_signal_group_a_20260817_220146.json`。

**a2118**（`--holdings-json`指向真實持股JSON、`--cash-balance 1000000`、workbook用`taiwan_stock_20260815.xlsx`——注意這裡的`--workbook`參數對execution_plan.py而言只在沒給`--holdings-json`時才會被用來解析持股，給了`--holdings-json`後workbook本身的持股解析會被跳過但仍是必要參數）：
理論目標(未分批)：0050 53% / 00631L 7.43% / cash 39.57%（7,396股／3,069股）。因為要一次跳大權重(0050現在僅佔~28.5%)，大額分批限制(40%)生效：

| | 現在 | 這次實際執行 | 動作 |
|---|---|---|---|
| 00679B.TWO | 100股 | 0股 | 賣出100股(≈$2,607) |
| 0050.TW | 4,234股 | 5,498股 | 買進1,264股(≈$134,553) |
| 00631L.TW | 900股 | 1,767股 | 買進867股(≈$31,169) |

換手率11.3%，`execution_allowed=True`，`planning_status=ready`。剩餘0050 1,898股／00631L 1,302股遞延到後續交易日分批補足。警告同第一輪(securities_lending soft-stale、NCF overlay跳過)。

輸出：`results/point_in_time_artifacts/execution_plan/2026/08/17/execution_plan_20260817T220247_525a6596de5f.json` + scratch copy（非production pointer）。

**Production驗證**：兩輪四次跑法（含最初一次guard擋單的失敗嘗試）全程用`stat`確認`report/group_a_plus/latest/execution_plan.json`／`live_signal.json`的mtime維持`2026-08-14`不變，未被誤寫。

## 4. 論文審查：2605.17446（乾淨關閉）

**Robust Volatility Index Calculation with OTM Option-implied Probability**（大阪大學，2026-05-17掛出，22頁）。核心貢獻：不靠優化、純幾何構造的方法，從OTM選擇權bid/ask報價直接建構滿足無套利條件的價格曲線，用來穩健計算VIX式波動率指數——尤其在ATM附近連續zero-bid（如2020-03-13 COVID崩盤日）時，傳統VIX Riemann sum演算法直接算不出來，本方法仍可計算。用SPX選擇權2018-2021對比CBOE VIX驗證。

**判定：不適用，乾淨關閉**，理由三層：
1. Group A+全部標的(0050/00631L/00632R/00679B等)都是現貨ETF，無選擇權部位。
2. Group A+目前用的VIX(`global_features.py`/`regime_switching_volatility_shadow.py`)是直接抓CBOE公開算好的數字，我們是消費者不是生產者——論文解決的是「CBOE自己怎麼算得更穩健」，不是我們的問題。
3. 就算想套用，也沒有原始資料：現有最接近的`scripts/fetch/fetch_soxx_options_iv.py`只存壓縮後單日快照(ATM IV+2個固定moneyness點+PCR比)，沒有逐履約價bid/ask鏈，要套用得重建整條選擇權chain擷取pipeline，成本不划算。且「VIX/SOXX IV在崩盤當天剛好抓不到值」這個論文要解決的痛點，目前沒有證據顯示我們的資料源真的發生過，屬於為假設性缺口預先投資、不划算。

跟先前3篇選擇權曲面論文(2607.19030柴油、2608.12493曲面transport、2607.29220 IVS diffusion)判斷邏輯一致。未留獨立memory檔（沿用既有選擇權排除的固定判斷模式，见下方memory索引）。

## 5. 論文審查：2601.21447（不接production，但實測驗證了真實regime-dependence）

**Trade uncertainty impact on stock-bond correlations: Insights from conditional correlation models**（Lacava & Otranto，義大利Messina/羅馬大學，2026-01-29掛出，24頁）。用GJR-GARCH兩步驟法(CCC/STCC/DCC)分析美股四大指數(S&P500/道瓊/那斯達克/羅素2000) vs 10年期美債的動態相關性，把Trade Policy Uncertainty(TPU)指數跟總統黨籍虛擬變數當驅動因子。核心發現：股債相關性不是常數，轉折點常跟TPU飆升同步；共和黨執政期股債相關性明顯較高(平均0.71)，民主黨執政期較低甚至轉負(平均0.37)——高不確定性/關稅密集時期，債券避險功能會失效；DCC+TPU+政黨效應模型樣本內外預測都最準。

**跟前幾篇選擇權論文不同**：00679B.TWO(元大美債20年)就在`GROUP_A_PLUS_TICKERS`四檔核心標的裡，是真正的美國長天期公債ETF，資產類別直接對應論文研究的標的。因此沒有直接排除，改用自己的資料實測。

**實測**：0050.TW vs 00679B.TWO日報酬相關性，2017-01-12~2026-08-17完整歷史(2,332筆)。

| 指標 | 數值 |
|---|---|
| 全樣本相關性 | -0.10（正常，輕度分散） |
| 60日滾動相關性範圍 | -0.73 ~ +0.51（std=0.26，波動極大） |
| 2018-2019年(第一次美中貿易戰) | -0.38 / -0.42（避險效果最強） |
| 2023年 | +0.19（轉正） |
| 2025年 | +0.02 |
| 2026年至今 | +0.05 |
| 最近90天滾動平均 | **+0.11**（vs 過去250天平均-0.09，明顯偏高） |

**結論**：論文核心機制(股債相關性regime-dependent、非穩定)在我們自己的資產對上成立，且目前(近90天)正處於相關性偏高、分散效果變差的階段。細節機制不同——論文的美國樣本顯示川普第一任(關稅戰)相關性上升，但00679B在2018-2019反而是負相關最強期(長天期公債主要反映Fed降息預期/避險買盤，跟論文用總統黨籍當代理變數的機制不完全一樣)。

**不接production的原因**：golden1_0531跟a2118現在**所有情境下00631L/00679B的target weight都是0%**(今天兩輪8/18預測都印證)——00679B目前是完全休眠的資產，模型從沒真的拿它當避險部位用，沒有現成的「債券避險機制」可以去調節TPU訊號，沒有地方接。引進TPU指數擷取pipeline的成本，對一個休眠資產不划算。

**留給未來參考**：如果哪天要重新評估00679B當防禦部位，這次實測是個提醒——不能假設債券永遠避險，現在的相關性其實偏高、避險效果不如歷史均值。

## Do Not Do

1. **不要只查`news/ltn_mainstream_*range*.jsonl`就判斷LTN是否更新到今天**——要查`news/ltn_mainstream_rolling.jsonl`才是production實際消費的檔案。
2. **不要假設`run_daily.bat`／`run_ncf_daily_pipeline.py --skip-refresh`模式會保持`institutional_data`/`day_trading_data`新鮮**——這個模式故意跳過`refresh_institutional`/`refresh_day_trading`步驟（只做NCF訊號+advisory panel），如果没有另外定期跑完整refresh或手動補這兩張表，a2118的execution guard會在3天後開始擋單。今天就是活生生的案例。
3. **不要直接對`taiwan_stock_20260817.xlsx`這類扁平格式workbook傳`--workbook`/`--xlsx`參數**——兩個腳本的原生解析器都認不得這個格式，會直接報錯。改用`--override-holdings-json`/`--holdings-json`手動傳入持股數字。
4. **不要假設「以1百萬」的cash假設可以自動沿用到「真實持股」情境**——第一輪是零持股+$1M的假設性起點，第二輪是真實持股，現金餘額必須另外向使用者確認（這次確認後選擇沿用$1M），不能默認搬過去。
5. **不要看到「Group A+標的」四個字就自動假設跟論文資產類別重疊**——00679B.TWO雖然在`GROUP_A_PLUS_TICKERS`裡，但target weight長期是0%，屬於休眠資產；判斷一篇論文是否值得實測要同時看「資產類別是否重疊」跟「該資產是否真的在決策路徑上」，兩者都成立才值得投入實測成本，只有前者成立(如2601.21447)可以實測驗證但不必期待能接production。

## Next Step

無強制後續行動。若要讓a2118的NCF overlay(00631L/00632R)不再被跳過，需要重新跑NCF訊號pipeline(目前停在08-13，4天未更新)；若要讓golden signal快取的H3落差消失，需要重新跑`run_group_a_combined_signal.py`更新`results/group_a_combined_live_latest.json`——這兩個都會動到production消費的檔案，需要使用者明確要求才執行。2601.21447的00679B/0050相關性regime-dependence發現純觀察記錄，不需要後續動作，除非未來重新評估00679B當防禦部位時要回頭參考。
