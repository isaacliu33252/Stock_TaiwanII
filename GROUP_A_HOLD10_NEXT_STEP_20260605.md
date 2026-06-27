# Group A Hold10 Next Step 2026-06-05

資料區間：2024-01-02 至 2026-06-04。

## Key Finding

`00632R 最多持有 10 天` 要用 **post-target overlay** 實作，不是單純把環境參數 `inverse_max_holding_days` 從 5 改成 10。

完整 PPO replay 驗證：

| Variant | Final | Sharpe | MDD | Rebalances / Trades | Fees |
|---|---:|---:|---:|---:|---:|
| TDCC destination_primary | 3,168,631 | 2.1789 | -26.43% | 70 | 35,838 |
| env inverse max hold = 10 | 3,168,631 | 2.1789 | -26.43% | 70 | 35,838 |
| post-target 00632R hold10 overlay | 3,323,211 | 2.2416 | -26.43% | 9 inverse events | replay estimate |

結論：`env inverse_max_holding_days=10` 沒有改變這段結果；真正有效的是在 target event 產生後，若 00632R 連續持有超過 10 個 calendar days，就把後續 00632R 權重轉到 0050。

## Current Best Group A Candidates

| Candidate | Final | Sharpe | MDD | Role |
|---|---:|---:|---:|---|
| destination_primary | 3,168,631 | 2.1789 | -26.43% | current stable baseline |
| destination_primary + 00632R hold10 overlay | 3,323,211 | 2.2416 | -26.43% | balanced candidate |
| destination_primary + disable 00632R -> 0050 | 3,566,548 | 2.2622 | -28.30% | aggressive candidate |

## 2008 Constraint

2008 TWII proxy stress test does not support fully disabling 00632R:

| 2008 Variant | Final | Sharpe | MDD |
|---|---:|---:|---:|
| baseline keeps 00632R | 1,525,036 | 0.5395 | -50.44% |
| disable 00632R -> 0050 | 1,452,024 | 0.4787 | -51.96% |

因此正式方向應該是 **限制 00632R 持有時間**，不是永久禁用。

## Implementation Candidate

新增設定檔：

- `group_a_00632r_hold10_overlay_config.json`

語意：

- base strategy: `Golden1_0531_tdcc_v1_destination_primary`
- overlay ticker: `00632R.TW`
- max holding calendar days: 10
- released weight goes to `0050.TW`

這個 post-target overlay 已接到 `run_group_a_tdcc_improved_signal.py`。live / shadow signal 產生時會：

1. 先產生 base Group A signal。
2. 套用 TDCC overlay。
3. 再套用 00632R hold10 post-target overlay。
4. 將 overlay 狀態寫入 `tdcc_overlay.inverse_hold_overlay` 與 manifest。

預設 state file：

- `results/group_a_00632r_hold10_overlay_state.json`

可用 `--inverse-hold-overlay-config ""` 關閉此 overlay。

## Outputs

- Full env max-hold=10 replay: `results/group_a_tdcc_destination_primary_hold10_full_20240101_20260605.json`
- Overlay config: `group_a_00632r_hold10_overlay_config.json`
- Live signal integration: `run_group_a_tdcc_improved_signal.py`
- Smoke output: `results/group_a_tdcc_improved_signal_20260605_131043.json`
- Prior focused sweep: `results/group_a_00632r_dca_sweep_20240102_20260604.json`
