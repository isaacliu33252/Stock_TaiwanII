# Group A TDCC Improvement Sweep 2026-06-05

資料區間：2024-01-02 至 2026-06-04。  
方法：不重訓 PPO，使用既有 `group_a_tdcc_latest_backtest_20240101_20260605.json` 的 base rebalance events，重放 TDCC overlay。

## Decision

建議採用候選：**risk-off 釋放槓桿資金改買 0050**。

不建議採用：

- 00631L 新增買入節流
- 更嚴格 TDCC 門檻
- caution cap 降到 5%

## Best Candidate

| Variant | Final | Delta Final | Annual | Sharpe | Delta Sharpe | MDD | Rebalances | Fees |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| latest default | 3,104,211 | 0 | 59.68% | 2.1641 | 0.0000 | -26.43% | 80 | 36,231 |
| destination primary | 3,168,631 | +64,420 | 61.05% | 2.1789 | +0.0148 | -26.43% | 70 | 35,838 |

解讀：

- 釋放 00631L 後留 cash 太保守，2024-2026 這段會拖累報酬。
- 改成買 0050 後，仍保留「去槓桿」效果，但不完全離開市場。
- MDD 沒改善，但 final、Sharpe、交易次數、費用都改善。

## Other Useful Variants

| Variant | Final | Delta Final | Sharpe | MDD |
|---|---:|---:|---:|---:|
| caution cap 15% | 3,157,719 | +53,508 | 2.1701 | -26.43% |
| split 75% to 0050 / 25% cash | 3,151,063 | +46,852 | 2.1752 | -26.43% |
| split 25% to 0050 / 75% cash | 3,119,799 | +15,588 | 2.1679 | -26.43% |
| lenient thresholds + risk cap 3% | 3,108,881 | +4,670 | 2.1696 | -26.43% |

這些都不如 `destination_primary` 乾淨。

## Rejected: 00631L Buy Throttle

| Variant | Final | Delta Final | Sharpe | MDD |
|---|---:|---:|---:|---:|
| throttle caution cash | 2,906,952 | -197,259 | 2.0783 | -26.43% |
| strict throttle caution cash | 2,944,318 | -159,893 | 2.0855 | -26.43% |
| throttle caution primary | 3,069,036 | -35,175 | 2.1461 | -26.43% |

結論：不要在 caution 狀態阻止 00631L 新增買入。這會錯過後續反彈，且沒有降低最大回撤。

## Recommendation

Group A 下一版候選：

- Base：Golden1_0531 PPO
- Overlay：TDCC latest
- Change：`released_leverage_budget_destination = "primary"`
- Candidate config：`group_a_tdcc_improved_config_destination_primary.json`

這是目前 Group A 本體最乾淨的改善：不改 PPO、不增加外部 ETF、不增加複雜 selector，只改 risk-off 釋放槓桿資金的去向。

## Outputs

- Script: `backtest_group_a_tdcc_improvement_sweep.py`
- Candidate config: `group_a_tdcc_improved_config_destination_primary.json`
- JSON: `results/group_a_tdcc_improvement_sweep_20240102_20260604.json`
- CSV: `results/group_a_tdcc_improvement_sweep_20240102_20260604.csv`
- Curves: `results/group_a_tdcc_improvement_sweep_20240102_20260604_curve.csv`
