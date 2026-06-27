# GroupA+ 交接文件 — 2026-06-21

## 摘要

- 正式策略維持 `a213_cash30_recovery_ramp`。
- A21.4、A21.5、A21.6 均不是正式策略。
- A21.5 已設為不可執行的影子策略。
- 已修正 A21.3／A21.4 runner 身分漂移；各策略目前使用獨立 runner 與固定參數。
- 2026-06-19 為臺灣證券市場休市日，已從資料新鮮度的交易日計算中排除。
- 執行計畫已支援券商手續費折扣、偏離帶、最小交易金額及股數單位控制。
- 本次沒有送出任何券商委託。

## 正式策略狀態

正式 manifest：

- 路徑：`report/group_a_plus/latest/strategy.json`
- 策略：`a213_cash30_recovery_ramp`
- Runner：`group_a_plus.runners.a213`
- 狀態：`active`

A21.3 固定規格：

- MA 期間：75 日
- 一般防守配置：0050 60%、00631L 10%、現金 30%
- 正常 `golden1` 配置：0050 60%、00631L 20%、現金 20%
- 進場 MA gap：-1.75%
- 進場回撤：-11%
- 必要總風險分數：6
- 最短持有：5 個交易日
- 正式退出 MA gap：+2%
- 復甦條件：MA gap 大於等於 0，且五日動能為正
- 每次防守期間只觸發一次復甦階段

重要執行檔：

- `group_a_plus/runners/a213.py`
- `group_a_plus/runners/latest.py`
- `group_a_plus/governance/latest.py`
- `group_a_plus/operations/daily_signal.py`
- `group_a_plus/operations/execution_plan.py`

## 2026-06-22 正式訊號

輸出：

- `results/group_a_plus_live_signal_20260622_a213.json`

訊號狀態：

- 實際資料日期：2026-06-18
- 資料落後：1 個交易日（已排除 2026-06-19 休市日）
- 資料防護允許執行：是
- 基礎 regime：`golden1`
- 執行 regime：`golden1`
- 目標配置：0050 60%、00631L 20%、現金 20%
- 總風險分數：2
- MA75 gap：+20.55%
- 五日動能：+7.46%

這是使用最新本地資料產生的盤前目標，不包含 2026-06-22 盤中行情。

## Runner 身分修正

先前 `group_a_plus.runners.a213` 的策略身分與預設參數曾被改成 A21.4，造成
manifest 宣告 A21.3、實際卻執行 A21.4 的風險。目前已完成修正與隔離。

| 策略 | Runner | MA | 防守籃子 | 狀態 |
| --- | --- | ---: | --- | --- |
| A21.3 | `group_a_plus.runners.a213` | 75 | cash30 | 正式 |
| A21.4 | `group_a_plus.runners.a214` | 60 | bond30_cash30 | 研究 |
| A21.5 | `group_a_plus.runners.a215` | 80 | cash40 | 影子 |
| A21.6 | `group_a_plus.runners.a216` | 75 | cash30／cash40 分級防守 | 研究 |

相容入口：

- `group_a_plus_a213_runner.py`
- `group_a_plus_a214_runner.py`
- `group_a_plus_a215_runner.py`
- `group_a_plus_a216_runner.py`

## A21.4 決策

A21.4 使用 MA60，防守配置為0050 40%、00679B 30%、現金30%。

歸因結果：

- `results/group_a_plus_a214_attribution_20260621.json`
- `results/group_a_plus_a214_attribution_20260621.csv`
- `results/group_a_plus_a214_attribution_20260621_effects.csv`

穩健性結果：

- `results/group_a_plus_a214_robustness_20260621.json`
- `results/group_a_plus_a214_robustness_20260621_walk_forward.csv`
- `results/group_a_plus_a214_robustness_20260621_latency.csv`
- `results/group_a_plus_a214_robustness_20260621_cost.csv`

結論：

- A21.4 可改善近期 Sharpe 與回撤。
- 延遲及較高交易成本下，未通過嚴格配對升級門檻。
- 交易成本提高至兩倍、三倍時，validation 期末值低於 A21.3。
- 維持研究用途，不得升級為正式策略。

## A21.5 影子策略

A21.5 僅使用2020–2024資料，從下列固定範圍選出：

- MA：60至90，每次增加5日
- 防守籃子：cash30、cash40、bond20
- 訓練門檻：期末值、Sharpe、MDD及ETL均不得低於A21.3

凍結後的候選：

- 策略：`a215_cash40_mw80`
- MA：80日
- 防守配置：0050 50%、00631L 10%、現金40%

相對 A21.3 的配對結果：

| 區間 | 期末值差異 | Sharpe差異 | MDD差異 |
| --- | ---: | ---: | ---: |
| 2020–2024 | +7,785 | +0.0097 | +0.04pp |
| 2025–2026 | -223 | +0.0591 | +2.07pp |
| 2020–2026 | +18,922 | +0.0174 | +0.04pp |

結論：

- Validation 期末值少 TWD 222.64，未通過「期末值不得落後」的嚴格門檻。
- A21.5 維持影子／觀察候選，不得執行委託。
- 影子訊號會明確輸出 `execution_allowed=false` 與不可執行原因。

相關檔案：

- `results/group_a_plus_a215_evaluation_20260621.json`
- `results/group_a_plus_a215_evaluation_20260621_search.csv`
- `results/group_a_plus_a215_evaluation_20260621_windows.csv`
- `report/group_a_plus/shadow/a215_strategy.json`
- `report/group_a_plus/shadow/a215_live_signal.json`
- `results/group_a_plus_shadow_a215_signal_20260622.json`

A21.5 在 2026-06-22 的影子 regime 也是 `golden1`，因此目標與 A21.3 相同：
0050 60%、00631L 20%、現金20%。

## A21.6 分級防守

A21.6 保留 A21.3 的所有進場、退出、MA75及復甦規則。進入防守期間後，只要
符合任一固定條件，就從 cash30 升級為 cash40：

- 總風險分數大於等於8；或
- 回撤小於等於-15%；或
- 尾端風險分數大於等於2。

一旦升級，在復甦或正式退出前會持續使用cash40，避免每日來回切換。

相對A21.3的配對結果：

| 區間 | 期末值差異 | Sharpe差異 | MDD差異 |
| --- | ---: | ---: | ---: |
| 2020–2024 | -5,531 | +0.0018 | 0.00pp |
| 2025–2026 | +3,711 | +0.0585 | +1.96pp |
| 2020–2026 | -3,558 | +0.0108 | 0.00pp |

結論：

- 近期 validation 的主要指標全部改善。
- Train及long期末值較低。
- A21.6未通過嚴格升級門檻，維持研究用途。

證據：

- `results/group_a_plus_a216_evaluation_20260621.json`
- `results/group_a_plus_a216_evaluation_20260621_windows.csv`

## 執行控制

輸出：

- `results/group_a_plus_execution_plan_controls_20260622.json`

`group_a_plus.operations.execution_plan` 新增下列控制：

- `--commission-discount`：公告手續費率的折扣乘數，範圍0至1；取得實際券商
  折扣前預設為1。
- `--min-trade-notional`：最小交易金額，預設TWD 5,000。
- `--min-weight-deviation`：最小權重偏離，預設總資產的0.5%。
- `--share-lot-size`：股數單位，預設1股；若只允許整張交易，可設為1000。
- 完整清倉會略過最小交易額與偏離帶限制。
- 輸出同時保留理論目標與控制後目標。
- 被抑制的交易會列出明確原因。

目前使用工作簿並假設現金為0的結果：

- 預估執行成本：TWD 859.98
- 預估交易後現金：TWD 80,875.11
- 換手率：109.43%
- 自動執行上限：50%
- 規劃狀態：`manual_review_required`
- 未送出任何委託

目前高換手率來自實際持倉與目標配置的差異，不是小額交易造成，因此新增的偏離帶
不會抑制這些主要交易。

## 驗證

最終相關測試命令：

```bash
python3 -m unittest \
  test_group_a_plus_a216.py \
  test_group_a_plus_a215.py \
  test_group_a_plus_a214_robustness.py \
  test_group_a_plus_a214_attribution.py \
  test_group_a_plus_latest_strategy.py \
  test_group_a_plus_defensive_basket.py \
  test_group_a_plus_daily_signal_v2.py \
  test_group_a_plus_execution_plan_v2.py
```

結果：25項測試通過。

## 操作命令

產生正式 A21.3 訊號：

```bash
python3 -m group_a_plus.operations.daily_signal \
  --as-of 2026-06-22 \
  --portfolio-value 1000000 \
  --output results/group_a_plus_live_signal_20260622_a213.json
```

產生 A21.5 影子訊號：

```bash
python3 -m group_a_plus.operations.daily_signal \
  --as-of 2026-06-22 \
  --portfolio-value 1000000 \
  --manifest report/group_a_plus/shadow/a215_strategy.json \
  --output results/group_a_plus_shadow_a215_signal_20260622.json \
  --latest-pointer report/group_a_plus/shadow/a215_live_signal.json
```

產生持倉感知的執行控制計畫：

```bash
python3 -m group_a_plus.operations.execution_plan \
  --workbook taiwan_stock_20260619.xlsx \
  --as-of 2026-06-22 \
  --cash-balance 0 \
  --commission-discount 1.0 \
  --min-trade-notional 5000 \
  --min-weight-deviation 0.005 \
  --share-lot-size 1 \
  --output results/group_a_plus_execution_plan_controls_20260622.json
```

## 後續工作與限制

1. 取得實際券商手續費折扣後，再修改預設折扣參數。
2. 產生執行計畫時，必須提供帳戶真實現金餘額。
3. A21.5必須維持影子運行，直到取得真正新的獨立期間。
4. 不得再使用現有2025–2026資料調整A21.5或A21.6參數。
5. 不得只依近期Sharpe改善就升級A21.4或A21.6。
6. 目前休市日集合只補入本次必要的2026-06-19；處理其他日期前，應擴充完整的
   臺灣證券市場休市日曆。
7. 除非候選通過預先定義的升級門檻，否則
   `report/group_a_plus/latest/strategy.json` 必須維持A21.3。
