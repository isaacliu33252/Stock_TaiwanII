# Group A Selector Overlay Backtest 2026-06-05

資料區間：2024-01-02 至 2026-06-04。

來源策略：`results/group_a_tdcc_latest_backtest_20240101_20260605.json` 的 `latest_tdcc_overlay_replay`。  
方法：不重訓 PPO，用前一日 Group A drawdown 與 21 日動能判斷 00679B 防守部位，避免使用當日未來資訊。

## 結論

不建議把動態 selector overlay 納入目前 Group A 正式策略。

目前最好的 selector 版本是 mild + conservative：

- normal：0% 00679B
- caution：5% 00679B
- risk-off：7.5% 00679B
- severe：10% 00679B
- 門檻：drawdown -10% / -18% / -25%，21 日動能 -6% / -12% / -20%
- 季再平衡，5% drift trigger，交易成本 0.1425%，00679B 賣出稅 0.1%

它只把 MDD 從 -26.43% 改到 -26.39%，但 final value 從 3,104,211 降到 3,009,779，少約 94,431。風險改善太小，不值得犧牲報酬與增加 39 次再平衡。

## Fair Compare

| Variant | Final Value | Annual | Sharpe | MDD | Rebalances | Cost |
|---|---:|---:|---:|---:|---:|---:|
| TDCC latest, no bond | 3,104,211 | 59.68% | 2.1641 | -26.43% | 10 | 0 |
| fixed 5% 00679B | 2,934,984 | 56.03% | 2.1619 | -25.25% | 10 | 287 |
| fixed 10% 00679B | 2,772,964 | 52.41% | 2.1568 | -24.06% | 10 | 533 |
| selector 0/5/10/15 | 2,928,610 | 55.89% | 2.1262 | -26.36% | 70 | 15,503 |
| selector mild + conservative | 3,009,779 | 57.66% | 2.1333 | -26.39% | 39 | 5,302 |

## Recommendation

Group A 目前應維持：

1. 正式策略：`latest_tdcc_overlay_replay`，不加動態 00679B selector。
2. 實盤風控：只在帳戶層級使用固定 95/5 或 90/10 作為人工風險偏好，不把它寫進 Group A alpha 策略。
3. Group A + Group B 組合：沿用前次較好的 62.5% Group A / 37.5% Group B，季再平衡、5% drift。

## Output Files

- Script: `backtest_group_a_selector_overlay.py`
- Best selector result: `results/group_a_selector_overlay_mild_conservative_20240102_20260604.json`
- Default selector result: `results/group_a_selector_overlay_0_5_10_15_20240102_20260604.json`
- Fixed baseline result: `results/group_a_selector_overlay_fixed0_20240102_20260604.json`
