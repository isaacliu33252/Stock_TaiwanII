# Group A 00632R / DCA Sweep 2026-06-05

資料區間：2024-01-02 至 2026-06-04。  
基準：`Golden1_0531 + TDCC destination_primary`。  
方法：不重訓 PPO，只改 00632R target event 與 DCA history 後 replay。

## Decision

00632R 在這段回測中主要拖累報酬。  
若只看 Group A 本體，下一個最佳候選是：

**禁用 00632R，釋放權重改買 0050。**

| Variant | Final | Sharpe | MDD | DCA | Contribution Return |
|---|---:|---:|---:|---:|---:|
| baseline destination_primary | 3,168,631 | 2.1789 | -26.43% | 145,000 | 176.74% |
| disable 00632R -> 0050 | 3,566,548 | 2.2622 | -28.30% | 145,000 | 211.49% |

這個版本 final +397,917、Sharpe +0.0833、contribution return +34.75 pct，但 MDD 變差 1.87 pct。它是最高品質的「同投入本金」改善，但風險較高。

## Best By Objective

| Objective | Variant | Final | Sharpe | MDD | Note |
|---|---|---:|---:|---:|---|
| Highest final | disable 00632R -> 0050 + DCA double on DD10 | 3,638,689 | 2.2942 | -28.06% | 投入本金增加到 175,000 |
| Best same-DCA return | disable 00632R -> 0050 | 3,566,548 | 2.2622 | -28.30% | DCA 維持 145,000 |
| Risk-balanced | hold limit 00632R 10d -> 0050 | 3,323,211 | 2.2416 | -26.43% | MDD 不變，報酬提升 |
| Lowest MDD | conditional 00632R below MA60 + DCA double below MA60 | 3,210,941 | 2.1965 | -26.05% | MDD 改善，但多投入 15,000 |

## 00632R Ablation / Cap

| Variant | Final | Sharpe | MDD | Contribution Return |
|---|---:|---:|---:|---:|
| disable 00632R -> 0050 | 3,566,548 | 2.2622 | -28.30% | 211.49% |
| cap 00632R 5% -> 0050 | 3,492,929 | 2.2566 | -28.08% | 205.06% |
| cap 00632R 10% -> 0050 | 3,426,038 | 2.2481 | -27.74% | 199.22% |
| cap 00632R 15% -> 0050 | 3,360,727 | 2.2362 | -27.41% | 193.51% |
| disable 00632R -> cash | 3,366,769 | 2.2369 | -27.43% | 194.04% |

結論：00632R 權重越低，報酬越好；釋放到 0050 比 cash 好，但 MDD 也較高。

## Conditional / Holding Limit

| Variant | Final | Sharpe | MDD |
|---|---:|---:|---:|
| conditional below MA60 -> 0050 | 3,175,683 | 2.1789 | -26.31% |
| conditional below MA60 cap10 -> 0050 | 3,433,689 | 2.2481 | -27.63% |
| hold limit 10d -> 0050 | 3,323,211 | 2.2416 | -26.43% |
| hold limit 20d -> 0050 | 3,224,801 | 2.2037 | -26.43% |

結論：若不想承受 disable 00632R 的 MDD 惡化，`hold_limit_00632r_10d_to_0050` 是比較穩的折衷版。

## DCA

目前 DCA 原本就只買 0050。測試結果：

| Variant | Final | Sharpe | MDD | DCA |
|---|---:|---:|---:|---:|
| baseline | 3,168,631 | 2.1789 | -26.43% | 145,000 |
| double group DD10 | 3,238,011 | 2.2149 | -26.17% | 175,000 |
| double below MA60 | 3,203,872 | 2.1966 | -26.17% | 160,000 |
| pause negative mom21 | 3,060,834 | 2.1184 | -27.66% | 95,000 |

結論：DCA 暫停不好；逢回撤加碼 0050 可以降低 MDD 並提高 final，但投入本金不同，應視為資金管理規則，不是 alpha 改善。

## Recommendation

Group A 下一版可以分兩條：

1. **Aggressive candidate**：`destination_primary + disable 00632R -> 0050`
   - final 與 Sharpe 最強
   - MDD 變差到 -28.30%

2. **Balanced candidate**：`destination_primary + hold_limit_00632R_10d -> 0050`
   - final 3,323,211
   - Sharpe 2.2416
   - MDD 維持 -26.43%

若要正式替換目前 Group A，我建議先採用 balanced candidate 進一步做壓力測試，再決定是否上 aggressive candidate。

## Outputs

- Script: `backtest_group_a_00632r_dca_sweep.py`
- JSON: `results/group_a_00632r_dca_sweep_20240102_20260604.json`
- CSV: `results/group_a_00632r_dca_sweep_20240102_20260604.csv`
- Curves: `results/group_a_00632r_dca_sweep_20240102_20260604_curve.csv`
