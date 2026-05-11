# FinRL 台股強化學習交易系統

## 2026-05-09 0056 資料起始日期檢查

新增資料範圍檢查工具：

```bash
python inspect_data_range.py 0056
```

本機快取檢查結果：

- `data/portfolio_cache/0056_TW.parquet`：最早為 `2014-01-02` 台北時間附近，最晚到 `2026-04-30` 附近，共 3,005 筆。
- `data/portfolio_cache/0056_TW_20160101_20260509_1d.parquet`：最早為 `2016-01-04` 台北時間附近，最晚到 `2026-05-08` 附近，共 2,516 筆。
- `data/portfolio_cache/0056_TW_20200101_20260509_1d.parquet`：最早為 `2020-01-02` 台北時間附近，最晚到 `2026-05-08` 附近，共 1,538 筆。

結論：目前專案內可用的 0056 本機資料最早約從 `2014-01-02` 開始；若使用目前下載器重新抓 `2016` 起區間，則會從 `2016-01-04` 開始。

## 2026-05-09 0050：訓練 2009-2023，回測 2024-2026

依照可取得的 0050 資料，明確使用 2009-2023 訓練、2024-2026 回測：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 0050.TW --agent ppo --timesteps 100000 --seed 42 --train-start 2009-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08
```

實際資料區間：

- Train: `2009-01-02` 到 `2023-12-29`，共 3,678 筆
- Backtest: `2024-01-02` 到 `2026-05-08`，共 565 筆

模型：

`models/portfolio/0050_TW_20090101_20231231_ppo_enhanced`

輸出：

- `results/training_0050_TW_20090101_20231231_ppo_backtest_20240101_20260508_20260509_152804.json`
- `results/training_0050_TW_20090101_20231231_backtest_20240101_20260508_20260509_152804.png`
- `results/training_0050_TW_20090101_20231231_backtest_20240101_20260508_20260509_152804_drawdown.png`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0050 PPO | 1,483,556 | 48.36% | 19.27% | 1.730 | -10.99% | 8 | 1,926 | -157.94% |
| 0050 B&H | 3,062,966 | 206.30% | 64.90% | 1.994 | -27.48% | 0 | 0 | 基準 |

結論：這版 PPO 明顯偏保守，MDD 從 B&H 的 -27.48% 降到 -10.99%，但代價是大幅少賺，總報酬落後 B&H 約 157.94 個百分點。若目標是資產成長，這版不如 0050 B&H；若目標是低回撤，才有參考價值。

## 2026-05-09 0050 原始資料來源檢查

已檢查本機 0050 相關快取與外部資料來源：

- 本機 `FinRL/data/portfolio_cache/0050_TW_20030101_20260509_1d.parquet` 檔名雖然包含 20030101，但 parquet metadata 顯示實際資料範圍是 `2009-01-02` 到 `2026-05-08`，共 4,243 筆。
- 本機 `FinRL/data/portfolio_cache/0050_TW_20030101_20110101_1d.parquet` 同樣不是完整 2003 起資料。
- TWSE「個股日成交資訊」官方頁面註明資料自民國 99 年 1 月 4 日，也就是 `2010-01-04` 起提供，因此不能用它取得 2003-2009 的完整 OHLCV。
- TWSE「個股日收盤價及月平均價」自民國 88 年 1 月 5 日起提供，但欄位是日收盤價與月平均價，不是完整 OHLCV，不能直接取代目前 RL 訓練資料。
- 元大投信與 ETF 資訊頁可確認 0050 成立日 `2003-06-25`、掛牌日 `2003-06-30`，但不等於可直接取得 2003 起完整 OHLCV CSV。

結論：目前本機與 TWSE 免費官方 OHLCV 來源都不足以取得完整 `2003-2023` 的 0050 原始 OHLCV。若要真正訓練 2003-2023，需新增第三方歷史價格來源，或改用 `2010-2023` 作為官方 OHLCV 可驗證訓練區間。

## 2026-05-09 0050：訓練 2003-2023，回測 2024-2026

依照要求重新訓練 0050 單標的 PPO：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 0050.TW --agent ppo --timesteps 100000 --seed 42 --train-start 2003-01-01 --train-end 2023-12-31 --backtest-start 2024-01-01 --backtest-end 2026-05-08
```

注意：要求訓練區間為 2003-2023，但目前資料源實際取得的 0050 訓練資料從 `2009-01-02` 開始，因此實際訓練區間是 `2009-01-02` 到 `2023-12-29`，共 3,678 筆。回測實際區間為 `2024-01-02` 到 `2026-05-07`，共 564 筆。

模型：

`models/portfolio/0050_TW_20030101_20231231_ppo_enhanced`

輸出：

- `results/training_0050_TW_20030101_20231231_ppo_backtest_20240101_20260508_20260509_130503.json`
- `results/training_0050_TW_20030101_20231231_backtest_20240101_20260508_20260509_130503.png`
- `results/training_0050_TW_20030101_20231231_backtest_20240101_20260508_20260509_130503_drawdown.png`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0050 PPO | 3,113,744 | 211.37% | 66.26% | 2.018 | -26.92% | 3 | 2,783 | +2.87% |
| 0050 B&H | 3,085,070 | 208.51% | 65.58% | 2.009 | -27.48% | 0 | 0 | 基準 |

結論：這次 0050 PPO 在 2024-2026 小幅打贏 0050 B&H，總報酬多約 2.87 個百分點，MDD 也略低。不過差距很小，主要結論是「接近買進持有」，不是明顯優勢。

## 2026-05-09 0050 單標的：2003-2010 回測

新增 0050 單標的回測腳本，載入既有模型 `models/portfolio/0050_TW_2016_2023_ppo_enhanced`，不重新訓練：

```bash
python backtest_0050_2003_2010.py --start 2003-01-01 --end 2010-12-31
```

注意：雖然要求區間是 2003-2010，但目前資料下載源實際只回傳 `2009-01-02` 到 `2010-12-31` 的 0050 資料，共 499 筆交易日。因此下列結果是 2009-2010 的可用資料回測，不是完整 2003-2010。

輸出：

- `results/backtest_0050_20030101_20101231_20260509_123205.json`
- `results/backtest_0050_20030101_20101231_20260509_123205.png`
- `results/backtest_0050_20030101_20101231_20260509_123205_drawdown.png`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0050 PPO | 1,543,388 | 54.34% | 24.56% | 0.990 | -12.24% | 8 | 2,191 |
| 0050 B&H | 1,867,966 | 86.80% | 37.19% | 0.984 | -18.01% | 0 | 0 |

結論：0050 PPO 在這段資料的 MDD 較低，但總報酬落後 B&H 約 32.46 個百分點。此結果也屬於跨時期回測，因為模型是用 2016-2023 訓練，再拿去測 2009-2010，市場結構差異較大。

## 2026-05-09 2000-2010 回測可行性檢查

嘗試使用目前的全持股自由配置模型回測 2000-2010：

```bash
python backtest_all_holdings_unrestricted_2024_2026.py --start 2000-01-01 --end 2010-12-31
```

結果：目前這個「所有持股、不限制持股」模型不能直接回測 2000-2010。原因是模型資產池包含 `0050.TW`, `0056.TW`, `00646.TW`, `00679B.TWO`, `00713.TW`, `00751B.TWO`, `00878.TW`, `2884.TW`，其中多數 ETF 在 2010 年前尚未上市，無法形成共同交易資料區間。程式因此停止在 `Not enough backtest rows`。

若要做 2000-2010 類型的長期回測，建議改成「早期存在的標的」獨立模型，例如：

- 0050 單標的：可從 2003 年後開始測。
- 2884 單股票：可測更早期，但與 ETF 資產配置模型不同。
- 0050 + 2884 雙標的：可作為早期資料版本，但不能與目前全持股 ETF 模型直接比較。

## 2026-05-09 不限制持股模型：訓練期 2020-2023 回測

使用同一個全持股自由配置模型 `models/portfolio/portfolio_all_holdings_2020_2023_ppo`，將回測區間改為 2020-2023。因為這段是模型訓練期，所以此結果屬於 in-sample replay，不可視為泛化能力。

執行：

```bash
python backtest_all_holdings_unrestricted_2024_2026.py --start 2020-01-01 --end 2023-12-31
```

實際共同資料區間為 2020-07-10 到 2023-12-29，共 850 筆交易日。

結果：

`results/backtest_all_holdings_unrestricted_20200101_20231231_20260509_115036.json`

圖檔：

- `results/all_holdings_unrestricted_backtest_20200101_20231231_20260509_115036.png`
- `results/all_holdings_unrestricted_drawdown_20200101_20231231_20260509_115036.png`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 全持股 PPO 不限制 | 1,649,076 | 64.91% | 16.01% | 0.924 | -28.66% | 43 | 58,338 | +5.56% |
| 全持股等權 B&H | 1,424,571 | 42.46% | 11.08% | 0.886 | -19.56% | 0 | 0 | -16.89% |
| 目前持股比例 B&H | 1,066,441 | 6.64% | 1.93% | 0.036 | -23.48% | 0 | 0 | -52.70% |
| 100% 0050 B&H | 1,593,429 | 59.34% | 14.83% | 0.738 | -33.83% | 0 | 0 | 基準 |

最後配置仍約為 70.00% 0050，其餘 7 檔各約 4.29%。

結論：在訓練期內，全持股 PPO 不限制模型小幅打贏 0050 B&H，且 MDD 較低。但交易成本高、交易次數 43 次，且這是 in-sample，因此不能直接代表 2024-2026 的未來泛化能力。

## 2026-05-09 不限制持股回測與圖形化比較

依照「不應限制持股」要求，新增專用回測腳本，載入原本全持股自由配置模型，不使用 core-satellite 限制版 action space，重新回測 2024-2026 並輸出圖形化比較。

新增腳本：

```bash
python backtest_all_holdings_unrestricted_2024_2026.py
```

載入模型：

`models/portfolio/portfolio_all_holdings_2020_2023_ppo`

回測結果：

`results/backtest_all_holdings_unrestricted_2024_2026_20260509_114612.json`

圖檔：

- `results/all_holdings_unrestricted_backtest_2024_2026_20260509_114612.png`
- `results/all_holdings_unrestricted_drawdown_2024_2026_20260509_114612.png`

實際回測區間為 2024-01-02 到 2026-05-07，共 563 筆共同交易日。

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 目前持股 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 全持股 PPO 不限制 | 2,298,782 | 129.88% | 45.24% | 1.816 | -22.84% | 29 | 22,045 | +98.30% | -78.63% |
| 全持股等權 B&H | 1,556,120 | 55.61% | 21.93% | 1.401 | -16.23% | 0 | 0 | +24.04% | -152.89% |
| 目前持股比例 B&H | 1,315,755 | 31.58% | 13.09% | 0.955 | -15.73% | 0 | 0 | 基準 | -176.93% |
| 100% 0050 B&H | 3,085,070 | 208.51% | 65.72% | 2.010 | -27.48% | 0 | 0 | +176.93% | 基準 |

最後配置：

- 70.01% 0050
- 4.29% 0056
- 4.29% 00646
- 4.29% 00679B
- 4.29% 00713
- 4.29% 00751B
- 4.29% 00878
- 4.27% 2884

結論：不限制持股的自由配置模型仍然明顯打贏目前持股比例 B&H 和全持股等權 B&H，但輸給 100% 0050 B&H。模型自己仍收斂到 70% 0050 + 其他持股平均分散，代表它沒有把非核心持股完全排除，但核心仍然是 0050。

## 2026-05-09 全持股 Core-Satellite v2

依照改善建議，把全持股投組模型從「自由配置」改成「0050 核心 + 衛星」配置。這版不再允許模型任意押注非核心標的，而是在少數可執行配置中切換。

修改檔案：`train_all_holdings_portfolio_2020_2023_backtest_2024_2026.py`

Action space：

- hold current weights
- 100% 0050
- 90% 0050 / 10% 00878
- 80% 0050 / 20% 00878
- 80% 0050 / 10% 00713 / 10% 00878
- 70% 0050 / 10% 0056 / 10% 00713 / 10% 00878
- 70% 0050 / 15% 00646 / 7.5% 00679B / 7.5% 00751B
- 80% 0050 / 10% 00679B / 10% 00751B

Reward：

```text
daily return
+ 1.5 * excess vs equal-weight B&H
+ 1.0 * excess vs actual-holdings B&H
- 0.8 * underperformance vs 0050 B&H
- 0.5 * current drawdown
- turnover/cost penalty
```

執行：

```bash
python train_all_holdings_portfolio_2020_2023_backtest_2024_2026.py --timesteps 100000 --seed 42
```

結果：`results/training_portfolio_all_holdings_2020_2023_ppo_backtest_2024_2026_20260509_085625.json`

模型：`models/portfolio/portfolio_all_holdings_2020_2023_core_satellite_v2_ppo`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 目前持股 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 全持股 Core-Satellite v2 | 2,999,386 | 199.94% | 63.64% | 2.073 | -27.48% | 11 | 8,615 | +168.36% | -8.57% |
| 全持股 PPO v1 | 2,298,782 | 129.88% | 45.24% | 1.816 | -22.84% | 29 | 22,045 | +98.30% | -78.63% |
| 目前持股比例 B&H | 1,315,755 | 31.58% | 13.09% | 0.955 | -15.73% | 0 | 0 | 基準 | -176.93% |
| 100% 0050 B&H | 3,085,070 | 208.51% | 65.72% | 2.010 | -27.48% | 0 | 0 | +176.93% | 基準 |

最後配置：

- 80.06% 0050
- 10.01% 00679B
- 9.93% 00751B
- 其他 0%

結論：core-satellite v2 是目前最好的 RL 投組版本。它幾乎追上 0050 B&H，只落後 8.57%，Sharpe 2.073 甚至略高於 0050 B&H 的 2.010，交易次數與成本也比全持股 PPO v1 低很多。缺點是 MDD 沒有比 0050 低，代表債券 ETF 衛星沒有在 2024-2026 有效降低最大回撤。

下一步應先對 core-satellite v2 做多 seed 與 walk-forward，不建議再擴大 action space。

## 2026-05-09 全持股投組訓練：2020-2023 / 2024-2026

依照目前 `PORTFOLIO_HOLDINGS` / `ALL_TICKERS`，把所有持股一起納入單一 PPO 投組模型訓練。這不是逐檔各自訓練，而是一個模型在不同投組配置 action 間切換。

持股標的：

- 0050.TW
- 0056.TW
- 00646.TW
- 00679B.TWO
- 00713.TW
- 00751B.TWO
- 00878.TW
- 2884.TW

新增腳本：

```bash
python train_all_holdings_portfolio_2020_2023_backtest_2024_2026.py --timesteps 100000 --seed 42
```

設定為 2020-2023 訓練、2024-2026 回測。因為 00878.TW 較晚有資料，實際共同訓練區間為 2020-07-10 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-07。

結果：`results/training_portfolio_all_holdings_2020_2023_ppo_backtest_2024_2026_20260509_005241.json`

模型：`models/portfolio/portfolio_all_holdings_2020_2023_ppo`

Observation 維度：70

Action space：

- hold current weights
- equal weight all holdings
- actual current holding weights
- 100% 0050
- 70% 0050, rest equal
- 80% 0050 / 20% 00878
- 50% 0050 / 25% 00679B / 25% 00751B
- 0056/00713/00878 equal high-dividend basket
- 100% best 6M momentum
- top-2 6M momentum equal
- top-3 6M momentum equal

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 等權 B&H | vs 目前持股 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 全持股 PPO | 2,298,782 | 129.88% | 45.24% | 1.816 | -22.84% | 29 | 22,045 | +74.27% | +98.30% | -78.63% |
| 全持股等權 B&H | 1,556,120 | 55.61% | 21.93% | 1.401 | -16.23% | 0 | 0 | 基準 | +24.04% | -152.89% |
| 目前持股比例 B&H | 1,315,755 | 31.58% | 13.09% | 0.955 | -15.73% | 0 | 0 | -24.04% | 基準 | -176.93% |
| 100% 0050 B&H | 3,085,070 | 208.51% | 65.72% | 2.010 | -27.48% | 0 | 0 | +152.89% | +176.93% | 基準 |

最後配置約為：

- 70.01% 0050
- 其餘 7 檔各約 4.29%

結論：把所有持股加入後，PPO 明顯打贏「全持股等權 B&H」與「目前持股比例 B&H」，代表它有學到應該提高 0050 權重。但它仍大幅輸給 100% 0050 B&H。這再次確認目前最有效的訊號不是增加更多標的，而是：0050 應該是核心，其他持股只能作為衛星或風險分散。

## 2026-05-09 特徵改善實驗：四 ETF 投組 v3

針對「52 個特徵是否不夠」的問題，本次沒有再堆疊更多單檔技術指標，而是在四 ETF 投組腳本加入投組專用特徵。

修改檔案：`train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py`

新增特徵類型：

- 0050 市場狀態：MA120/MA240 趨勢、MA60 vs MA240、63 日回撤風險、63 日波動率、252 日波動分位。
- 高股息 ETF 相對強弱：0056/00713/00878 平均動能 vs 0050。
- ETF 相對動能：00878 vs 0050、00713 vs 0050、0056 vs 0050、00878 vs 0056。
- 動能排名：0050 在 63/126/252 日動能排名、00878 在 126 日排名、最佳與最弱動能差距。
- 投組狀態：目前各 ETF 權重、現金權重、目前 MDD、距離上次換倉天數、相對等權 B&H/0050 B&H 的領先落後、高股息總權重。

Observation 維度從 v2 的 37 維提高到 60 維。

執行指令：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --timesteps 100000 --seed 42
```

結果：`results/training_portfolio_0050_0056_00713_00878_2016_2023_ppo_backtest_2024_2026_20260509_003317.json`

模型：`models/portfolio/portfolio_0050_0056_00713_00878_2016_2023_ppo_features_v3`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 等權 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 四 ETF PPO v3 features | 1,875,722 | 87.57% | 32.52% | 1.341 | -31.45% | 24 | 66,363 | +0.29% | -120.93% |
| 四 ETF PPO v2 benchmark | 2,326,863 | 132.69% | 45.94% | 1.944 | -22.47% | 28 | 17,464 | +45.40% | -75.82% |
| 四 ETF 等權 B&H | 1,872,848 | 87.28% | 32.43% | 1.537 | -22.73% | 0 | 0 | 基準 | -121.22% |
| 100% 0050 B&H | 3,085,070 | 208.51% | 65.58% | 2.009 | -27.48% | 0 | 0 | +121.22% | 基準 |

結論：特徵增加後沒有改善，反而讓 PPO 學得更差。v3 只小贏等權 B&H，且 MDD 擴大到 -31.45%，成本也升到 66,363。這表示問題不是「特徵數量太少」，而是特徵太多後樣本數只有 850 筆，PPO 更容易學到不穩定配置。現階段最佳版本仍是 v2 benchmark reward，而不是 v3 features。

下一步建議：保留少數高價值特徵，不要一次加入 30 多個狀態。優先保留 `0050_trend_score`、`high_dividend_vs_0050_momentum_126`、`0050_momentum_rank_126`、`relative_value_vs_equal_weight_bh`、`relative_value_vs_0050_bh`，其餘先移除或用 feature ablation 逐批測試。

### 四 ETF 投組 v4：精簡特徵

v4 依照 v3 結論，把投組衍生特徵縮小，只保留：

- `0050_trend_score`
- `0050_volatility_rank_252`
- `high_dividend_vs_0050_momentum_126`
- `00878_vs_0050_momentum_63`
- `0050_momentum_rank_126`

投組狀態仍保留目前權重、現金、MDD、距上次換倉天數、相對等權 B&H/0050 B&H 的領先落後。Observation 維度降為 43。

結果：`results/training_portfolio_0050_0056_00713_00878_2016_2023_ppo_backtest_2024_2026_20260509_003758.json`

模型：`models/portfolio/portfolio_0050_0056_00713_00878_2016_2023_ppo_features_v4_reduced`

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 等權 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 四 ETF PPO v4 reduced features | 1,953,868 | 95.39% | 34.96% | 1.499 | -25.13% | 29 | 9,640 | +8.10% | -113.12% |
| 四 ETF PPO v3 features | 1,875,722 | 87.57% | 32.52% | 1.341 | -31.45% | 24 | 66,363 | +0.29% | -120.93% |
| 四 ETF PPO v2 benchmark | 2,326,863 | 132.69% | 45.94% | 1.944 | -22.47% | 28 | 17,464 | +45.40% | -75.82% |

結論：v4 比 v3 改善，但仍明顯輸 v2。特徵精簡是正確方向，但目前加入投組狀態與相對特徵後，模型仍沒有學出更好的配置。現階段應保留 v2 作為最佳版本，v4 只作為特徵實驗紀錄。

## 2026-05-09 改善實驗：00878 多 seed 與四 ETF 投組 v2

### 00878 PPO 多 seed

執行 00878.TW、PPO、100k timesteps，seed 使用 1、7、42、99、123。實際訓練區間仍為 2020-07-10 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-08。

| Seed | Final Value | 總報酬 | Sharpe | MDD | 交易次數 | vs B&H |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1,393,381 | 39.34% | 0.749 | -5.16% | 2 | -16.49% |
| 7 | 1,629,973 | 63.00% | 1.044 | -13.93% | 39 | +7.17% |
| 42 | 1,635,155 | 63.52% | 1.025 | -13.79% | 3 | +7.68% |
| 99 | 1,652,890 | 65.29% | 1.075 | -13.58% | 2 | +9.07% |
| 123 | 1,607,563 | 60.76% | 1.078 | -11.28% | 10 | +4.53% |

摘要：平均總報酬 58.38%，平均 Sharpe 0.994，平均 vs B&H +2.39%，最差 seed vs B&H -16.49%。00878 PPO 仍值得追蹤，但 seed 1 明顯落後，代表單檔 00878 RL 還不能只靠一次訓練定案。

### 四 ETF 投組 PPO v2

更新內容：

- Reward 改為 `daily_return + 2.0 * excess_return_vs_max(equal_weight_BH, 0050_BH)`。
- Action space 從 8 個擴充為 10 個。
- 新增 `70% 0050 / 10% 0056 / 10% 00713 / 10% 00878`。
- 新增 `80% 0050 / 20% 00878`。

執行指令：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --timesteps 100000 --seed 42
```

結果：`results/training_portfolio_0050_0056_00713_00878_2016_2023_ppo_backtest_2024_2026_20260509_001901.json`

模型：`models/portfolio/portfolio_0050_0056_00713_00878_2016_2023_ppo_benchmark_v2`

實際訓練區間為 2020-07-10 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-07。

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 等權 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 四 ETF PPO v2 | 2,326,863 | 132.69% | 45.94% | 1.944 | -22.47% | 28 | 17,464 | +45.40% | -75.82% |
| 四 ETF 等權 B&H | 1,872,848 | 87.28% | 32.43% | 1.537 | -22.73% | 0 | 0 | 基準 | -121.22% |
| 100% 0050 B&H | 3,085,070 | 208.51% | 65.58% | 2.009 | -27.48% | 0 | 0 | +121.22% | 基準 |

結論：v2 已成功從「輸等權 B&H」改善為「贏等權 B&H +45.40%」，最後配置約為 70% 0050 / 10% 0056 / 10% 00713 / 10% 00878，方向正確。但仍輸 0050 B&H -75.82%，代表這版比較像「比等權更積極的核心衛星策略」，還不是能取代 0050 B&H 的主策略。

## 0050+0056+00713+00878 投組 PPO 實驗紀錄

執行指令：

```bash
python train_portfolio_0050_0056_00713_00878_2016_2023_backtest_2024_2026.py --timesteps 100000 --seed 42
```

這支腳本是單一 PPO 投組配置模型，不是逐檔各自訓練。Action space 會在等權、100% 0050、0050 偏重、高股息偏重、防守型高股息、6M 動能第一名、6M 動能前兩名等配置間切換。

設定為 2016-2023 訓練、2024-2026 回測，但四檔 ETF 需要共同可用資料；因 00878.TW 較晚上市，本次實際訓練區間為 2020-07-10 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-08。

| 策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs 等權 B&H | vs 0050 B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 四 ETF PPO 投組 | 1,797,774 | 79.78% | 29.96% | 1.445 | -21.79% | 22 | 7,644 | -7.24% | -126.52% |
| 四 ETF 等權 B&H | 1,870,153 | 87.02% | 32.27% | 1.532 | -22.73% | 0 | 0 | 基準 | -119.28% |
| 100% 0050 B&H | 3,062,966 | 206.30% | 64.90% | 1.994 | -27.48% | 0 | 0 | +119.28% | 基準 |

模型：`models/portfolio/portfolio_0050_0056_00713_00878_2016_2023_ppo`

結果：`results/training_portfolio_0050_0056_00713_00878_2016_2023_ppo_backtest_2024_2026_20260508_234521.json`

結論：這版多 ETF PPO 投組沒有打贏四 ETF 等權 B&H，也大幅輸給 0050 B&H。模型最後偏向 0% 0050、約 40% 0056、30% 00713、30% 00878，代表它太保守並錯過 0050 在 2024-2026 的強勢主升段。後續若要繼續做投組 RL，reward 應明確加入「等權 B&H / 0050 B&H 超額報酬」作為門檻，否則模型容易學成低波動但低報酬配置。

## 00878 PPO 實驗紀錄

執行指令：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 00878.TW --agent ppo --timesteps 100000 --seed 42
```

設定為 2016-2023 訓練、2024-2026 回測，但 00878.TW 的可用資料實際從 2020-07-10 開始。因此本次實際訓練區間為 2020-07-10 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-08。

| 標的/策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 00878 PPO 100k | 1,635,155 | 63.52% | 24.57% | 1.025 | -13.79% | 3 | 680 | +7.68% |
| 00878 B&H | 約 1,558,314 | 55.83% | 21.92% | 1.132 | -22.29% | 0 | 0 | 基準 |

模型：`models/portfolio/00878_TW_2016_2023_ppo_enhanced`

結果：`results/training_00878_TW_2016_2023_ppo_backtest_2024_2026_20260508_233220.json`

結論：00878 PPO 在 2024-2026 回測贏過 B&H 約 7.68%，且 MDD 較低、交易次數只有 3 次，成本控制明顯優於 0056 PPO。訓練期仍輸給 B&H 約 31.79%，所以此結果應視為值得追蹤的候選，不應只用單一 seed 定案。

## 00713 PPO 實驗紀錄

執行指令：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --ticker 00713.TW --agent ppo --timesteps 100000 --seed 42
```

設定為 2016-2023 訓練、2024-2026 回測，但 00713.TW 的可用資料實際從 2017-09-19 開始。因此本次實際訓練區間為 2017-09-19 到 2023-12-29，回測區間為 2024-01-02 到 2026-05-08。

| 標的/策略 | Final Value | 總報酬 | 年化報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs B&H |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 00713 PPO 100k | 1,337,168 | 33.72% | 13.86% | 0.490 | -7.37% | 19 | 15,466 | +2.98% |
| 00713 B&H | 約 1,307,373 | 30.74% | 12.72% | 0.789 | -15.40% | 0 | 0 | 基準 |

模型：`models/portfolio/00713_TW_2016_2023_ppo_enhanced`

結果：`results/training_00713_TW_2016_2023_ppo_backtest_2024_2026_20260508_232301.json`

結論：00713 PPO 在 2024-2026 回測小幅贏過 B&H，且 MDD 較低；但訓練期 `train_excess_return_vs_bh=-90.63%`，表示模型在訓練期仍明顯輸給買進持有。這組結果可以保留，但不能只用單一 seed 當作正式結論，後續應補多 seed 與 walk-forward。

本資料夾是針對台灣 ETF/股票的強化學習交易實驗環境，主要使用 Stable-Baselines3 的 PPO/A2C/DQN，搭配台股交易限制、T+2 交割、交易成本、風控、增強 reward 與 walk-forward/backtest 流程。

## 目前重點改善

本版已把先前發現的高影響問題納入程式與文件：

- 回測輸出加入 `RL vs Buy & Hold` 基準比較。
- 回測輸出加入 `total_return`、`annual_return`、`sharpe`、`max_drawdown`、`volatility`、`excess_return_vs_bh`。
- 回測輸出加入 `fees_paid_estimate`、`turnover_trades`、`equity_curve`。
- 訓練加入 `--seed`，並寫入實驗 metadata。
- metadata 包含 `seed`、`git_commit`、`python`、`platform`、`model_path`、reward/env config。
- 修正 `reward_function_v3.py` 中最大回撤判斷順序，避免 `max_drawdown > 0.30` 永遠不會觸發。
- `.gitignore` 已排除 `results/`、`models/`、cache、圖表、JSON/CSV 等實驗輸出。
- README 已同步實作中的 9-action action space。
- 新增 DQN baseline，可用 `--agent dqn` 與 PPO/A2C/B&H 比較。
- 訓練摘要改為訓練後回放 train-set 統計，不再只顯示未更新的 `best_sharpe=-999`。
- Reward  now 加重 B&H 超額報酬、低週轉與最短持有約束，降低頻繁交易。
- 資料載入流程新增長週期趨勢/風險特徵，包含 3M/6M/12M momentum、MA120/MA240 比例、52 週位置與 63 日 rolling MDD。

## 主要檔案

```text
FinRL/
  portfolio_train_v2.py                         # 主要訓練入口，含 seed、metadata、benchmark 回測輸出
  backtest_0050_2016_2023_model_2024_2026.py    # 0050 固定模型回測，輸出 RL vs B&H
  portfolio_data_loader.py                      # Yahoo Finance 下載、快取與技術指標資料整理
  environments/taiwan_stock_env.py              # 9-action 台股交易環境
  environments/reward_function_v3.py            # Dynamic reward shaping
  risk_manager_v2.py                            # 風控、early stopping、Kelly 建議
  safe_ppo.py                                   # PPO logits/gradient 保護
  walk_forward_v2.py                            # Walk-forward 分段訓練與測試
  results/                                      # 訓練與回測輸出
  models/                                       # 模型輸出
  data/cache/                                   # 單標的資料快取
  data/portfolio_cache/                         # 投組資料快取
```

## 狀態空間

`TaiwanStockTradingEnv` 使用 52 維狀態：

| 類別 | 維度 | 內容 |
|---|---:|---|
| 價格/量 | 6 | close、open、high、low、volume、turnover |
| 技術指標 | 20 | MA、MACD、RSI、KDJ、BB、ATR、ADX、MFI 等 |
| 型態/動能 | 8 | 突破、跌破、量增、momentum、volatility、連漲連跌、gap |
| 基本/籌碼 | 8 | 外資、投信、自營商、殖利率、PER、PBR |
| 持倉狀態 | 6 | position、現金比例、未實現損益、MDD、距上次交易日數 |
| 市場情緒 | 4 | 加權指數報酬、量變化、相關性、市場波動 |

## Action Space

目前實作為 9 個離散動作：

| Action | ID | 說明 |
|---|---:|---|
| HOLD | 0 | 不交易 |
| BUY_1000 | 1 | 買入 1000 股 |
| BUY_5000 | 2 | 買入 5000 股 |
| BUY_10000 | 3 | 買入 10000 股 |
| SELL_1000 | 4 | 賣出 1000 股 |
| SELL_5000 | 5 | 賣出 5000 股 |
| SELL_10000 | 6 | 賣出 10000 股 |
| TARGET_50_PERCENT | 7 | 調整至約 50% 倉位 |
| TARGET_100_PERCENT | 8 | 調整至約 100% 倉位 |

## 台股交易設定

- 交易單位：1000 股。
- 最大持股：預設 40000 股。
- 漲跌停限制：10%。
- 買入成本：成交金額加券商手續費。
- 賣出成本：成交金額扣券商手續費與證交稅。
- T+2：新買入股數會被鎖定，解鎖前不可賣出。

## 訓練

安裝依賴：

```bash
cd FinRL
pip install -r requirements.txt
```

單一標的訓練：

```bash
python portfolio_train_v2.py --tickers 0050.TW --timesteps 100000 --seed 42
```

固定 0050 訓練/回測，支援選擇 agent：

```bash
python train_0050_2016_2023_backtest_2024_2026.py --agent ppo --timesteps 100000 --seed 42
python train_0050_2016_2023_backtest_2024_2026.py --agent dqn --timesteps 100000 --seed 42
```

指定 agent：

```bash
python portfolio_train_v2.py --tickers 0050.TW --agent ppo --timesteps 100000 --seed 42
python portfolio_train_v2.py --tickers 0050.TW --agent a2c --timesteps 100000 --seed 42
python portfolio_train_v2.py --tickers 0050.TW --agent dqn --timesteps 100000 --seed 42
```

停用風控或增強 reward：

```bash
python portfolio_train_v2.py --tickers 0050.TW --timesteps 100000 --no-risk
python portfolio_train_v2.py --tickers 0050.TW --timesteps 100000 --no-enhanced-reward
```

Walk-forward：

```bash
python portfolio_train_v2.py --tickers 0050.TW --walk-forward --timesteps 50000 --seed 42
```

## 固定 0050 回測

這支腳本會載入 `models/portfolio/0050_TW_2016_2023_enhanced`，用 2016-2023 作為訓練區間紀錄，回測 2024-2026。

```bash
python backtest_0050_2016_2023_model_2024_2026.py
```

輸出會寫入 `results/training_0050_2016_2023_backtest_2024_2026_fixed_*.json`，包含：

- `final_value`
- `total_reward`
- `num_trades`
- `final_position`
- `rl_metrics`
- `buy_and_hold_metrics`
- `excess_return_vs_bh`
- `fees_paid_estimate`
- `turnover_trades`
- `equity_curve`
- `metadata`

## 回測指標

每次 `EnhancedStockTrainer.backtest()` 會回傳：

```json
{
  "rl_metrics": {
    "total_return": 0.0,
    "annual_return": 0.0,
    "sharpe": 0.0,
    "max_drawdown": 0.0,
    "volatility": 0.0
  },
  "buy_and_hold_metrics": {
    "total_return": 0.0,
    "annual_return": 0.0,
    "sharpe": 0.0,
    "max_drawdown": 0.0,
    "volatility": 0.0,
    "initial_price": 0.0,
    "final_price": 0.0
  },
  "excess_return_vs_bh": 0.0,
  "fees_paid_estimate": 0.0,
  "turnover_trades": 0
}
```

`max_drawdown` 使用負值表示回撤，例如 `-0.18` 代表 -18%。

## Reward 與低週轉約束

目前 PPO/A2C/DQN 共用同一個 env 與 enhanced reward。重要設計：

- `benchmark_weight=2.0`：提高 RL 相對 B&H 的每日超額報酬權重。
- `underperform_penalty=1.0`：輸給 B&H 時加重懲罰。
- `trade_reward=0.0`、`trade_penalty=0.02`：不再鼓勵為交易而交易。
- env 額外加入 `turnover_penalty=0.01`。
- env 額外加入 `min_hold_days=20` 與 `short_hold_penalty=0.02`，短持有賣出會被扣 reward。
- 訓練摘要會在 `model.learn()` 後回放訓練區間，輸出 `train_total_return`、`train_max_drawdown`、`train_excess_return_vs_bh` 與實際 train-set Sharpe。

## 長週期特徵

`download_all_stocks()` 會在讀取 cache 或下載後補上：

- `close_ma120_ratio`
- `close_ma240_ratio`
- `ma60_ma240_ratio`
- `momentum_63`
- `momentum_126`
- `momentum_252`
- `high_252_position`
- `rolling_mdd_63`

這些特徵優先進入 `TaiwanStockTradingEnv` 的 20 個技術指標槽，目標是讓 ETF 策略更容易學會大週期趨勢與長抱。

## DQN Baseline

DQN 已接入 `portfolio_train_v2.py --agent dqn`。目前定位是比較基準，不是預設主力模型。

DQN 目前設定：

- MLP policy，網路寬度 `[256, 256]`。
- Replay buffer：`100000`。
- Learning starts：`5000`。
- Batch size：`128`。
- Target network update interval：`2000`。
- Epsilon exploration：從 `1.0` 線性降到 `0.05`，探索期佔 `25%`。
- Reward 與 env 與 PPO/A2C 共用，因此可以直接比較同一組 benchmark。

建議比較方式：

```bash
python portfolio_train_v2.py --tickers 0050.TW --agent ppo --timesteps 100000 --seed 42
python portfolio_train_v2.py --tickers 0050.TW --agent dqn --timesteps 100000 --seed 42
```

比較時不要只看 `final_value`，要同時看：

- `excess_return_vs_bh`
- `rl_metrics.sharpe`
- `rl_metrics.max_drawdown`
- `fees_paid_estimate`
- `turnover_trades`
- 多個 seed 的平均與最差結果

## 實驗追蹤

每筆訓練結果會加入 `metadata`：

```json
{
  "created_at": "2026-05-08T20:00:00",
  "ticker": "0050.TW",
  "agent_type": "ppo",
  "timesteps": 100000,
  "seed": 42,
  "train_rows": 1200,
  "test_rows": 600,
  "model_path": "...",
  "git_commit": "...",
  "python": "3.12.0",
  "platform": "...",
  "reward_config": {
    "enhanced_reward": true
  },
  "env_config": {
    "risk_manager": true,
    "action_space": 9
  }
}
```

建議後續將每次實驗輸出整理成：

```text
results/experiments/YYYYMMDD_HHMMSS_name/
  config.json
  metrics.json
  trades.csv
  equity.csv
  model.zip
```

目前程式已先把必要 metadata 寫入 JSON，後續可以再把輸出目錄改成上述結構。

## 目前風險與後續優先順序

1. 優先確認 RL 是否穩定贏過 Buy & Hold，而不是只看 final value。
2. 對 `taiwan_stock_env.py` 進一步清掉舊 5-action 註解與不可達舊碼，降低維護成本。
3. 把 `results/`、`models/`、`data/cache/` 明確排除版控或移到 experiment 目錄。
4. 對 reward 權重做 grid search 或 walk-forward，不要只用單一回測期間調參。
5. 每次報告都應同時列出交易成本、交易次數、超額報酬與最大回撤。

## 免責

此專案是研究與回測用途，不構成投資建議。實盤前需要獨立驗證資料品質、滑價、手續費、稅負、成交量限制與風險控管。

## 三段倉位規則策略 Baseline

`rule_based_trend_strategy.py` 是 0/50/100 三段倉位的低頻趨勢策略，不使用 RL，目標是建立 RL 必須先打贏的規則型 baseline。

主要邏輯：

- 強多頭：`close_ma120_ratio > 0`、`close_ma240_ratio > 0`、`ma60_ma240_ratio > 0`、6M/12M momentum 皆大於 0，持倉 100%。
- 風險轉弱：`close_ma240_ratio < -5%` 或 `rolling_mdd_63 < -15%`，持倉 0%。
- 其他中性狀態：持倉 50%。
- 預設每 60 個交易日最多調倉一次。

執行範例：

```bash
python rule_based_trend_strategy.py --ticker 0056.TW --min-rebalance-days 60 --defensive-position 0.5
python rule_based_trend_strategy.py --ticker 0050.TW --min-rebalance-days 20 --defensive-position 0.5
```

0056 在 2024-2026 的目前結果：

| 策略 | Final Value | 總報酬 | Sharpe | MDD | 交易次數 | 估計成本 | vs B&H |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0056 PPO 100k | 1,265,538 | 26.55% | -1.632 | -19.72% | 311 | 261,013 | -28.64% |
| 0056 三段倉位 | 1,418,244 | 41.82% | 1.143 | -18.78% | 7 | 7,846 | -13.37% |
| 0056 B&H | 約 1,551,960 | 55.20% | 1.069 | -26.89% | 0 | 0 | 基準 |

## 0050+0056 投組規則 Baseline

`portfolio_rule_baseline_0050_0056.py` 是第一版 0050/0056/現金配置規則，不使用 RL。邏輯是每 20 個交易日根據 0050 與 0056 的 3M/6M/12M 相對動能與風險狀態，在以下配置間切換：

- 70% 0050 / 30% 0056
- 30% 0050 / 70% 0056
- 50% 0050 / 50% 0056
- 風險轉弱時保留部分現金

執行：

```bash
python portfolio_rule_baseline_0050_0056.py
```

2024-2026 目前結果：

| 策略 | Final Value | 總報酬 | Sharpe | MDD | 交易次數 | 估計成本 |
|---|---:|---:|---:|---:|---:|---:|
| 0050+0056 規則投組 | 1,992,777 | 99.28% | 1.546 | -29.01% | 25 | 11,334 |
| 50/50 B&H | 約 2,307,463 | 130.75% | 1.740 | -26.68% | 0 | 0 |
| 100% 0050 B&H | 約 3,062,966 | 206.30% | 1.994 | -27.48% | 0 | 0 |
| 100% 0056 B&H | 約 1,551,960 | 55.20% | 1.069 | -26.89% | 0 | 0 |

結論：第一版投組規則 baseline 尚未打贏 50/50 B&H，主要問題是切換太保守且錯過 0050 大波段。後續 PortfolioEnv/RL 應以 50/50 B&H 和 100% 0050 B&H 作為主要門檻。
