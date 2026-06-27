# Group A Improvement Pack

Date: 2026-06-05
Status: Shadow improvement study complete

## Scope

Run the Group A-only improvement branches discussed:

1. `00679B` sleeve: `95/5` through `85/15`
2. TDCC overlay variants
3. PVA buy-dip reduction
4. `00631L` cap reduction
5. local regime clear-day tuning
6. live execution shadow for `95/5`

No PPO retraining was performed.

## Baseline

Full Group A exact replay:

| Strategy | Final value | Sharpe | MDD | Trades |
| --- | ---: | ---: | ---: | ---: |
| `Group A base exact` | `3,151,915` | `2.0733` | `-28.15%` | `106` |
| `Group A latest TDCC` | `3,104,211` | `2.1641` | `-26.42%` | `80` |

Interpretation:

- Latest TDCC is still useful as a risk-adjusted shadow/live overlay.
- It gives up about `47.7k` final value but improves Sharpe and MDD.

## 00679B Sleeve

Quarterly-or-drift, drift threshold `5%`, fee/tax included.

| Sleeve | Final value | Sharpe | MDD | Rebalances | Cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| `100% Group A` | `3,151,915` | `2.1551` | `-28.15%` | `0` | `0` |
| `95A / 5 00679B` | `2,979,390` | `2.1533` | `-26.90%` | `10` | `298` |
| `92.5A / 7.5 00679B` | `2,895,858` | `2.1514` | `-26.35%` | `10` | `431` |
| `90A / 10 00679B` | `2,814,116` | `2.1486` | `-25.81%` | `10` | `554` |
| `87.5A / 12.5 00679B` | `2,734,139` | `2.1450` | `-25.26%` | `10` | `668` |
| `85A / 15 00679B` | `2,655,905` | `2.1404` | `-24.72%` | `10` | `771` |

Interpretation:

- `95/5` is the best light-touch defensive overlay.
- `90/10` is better when drawdown reduction matters more than final value.
- Heavier bond sleeves reduce MDD but give up too much return for Group A-only use.

## TDCC Variants

The standalone TDCC variant sweep did not find a better replacement than the current latest TDCC full replay.

PVA-event replay top variants:

| Variant | Final value | Sharpe | MDD |
| --- | ---: | ---: | ---: |
| `baseline_golden1` | `2,118,184` | `1.7979` | `-25.92%` |
| `riskoff_cap_0.00_cash` | `2,058,756` | `1.8211` | `-25.92%` |
| `riskoff_cap_0.05_cash` | `2,066,307` | `1.8181` | `-25.92%` |
| `riskoff_cap_0_primary` | `2,097,246` | `1.8140` | `-25.92%` |

Interpretation:

- Some variants improve Sharpe slightly in the simplified replay, but do not improve MDD.
- Current full TDCC replay remains the better evidence source.

## Full PPO Replay Overrides

Same trained model, same backtest window, only payload parameters changed.

| Variant | Final value | Sharpe | MDD | Trades |
| --- | ---: | ---: | ---: | ---: |
| `baseline` | `3,151,915` | `2.0733` | `-28.15%` | `106` |
| `buydip090` | `3,152,365` | `2.0731` | `-28.16%` | `106` |
| `buydip085` | `3,152,868` | `2.0730` | `-28.16%` | `106` |
| `cap18` | `3,088,310` | `2.0541` | `-28.09%` | `106` |
| `cap15` | `3,010,007` | `2.0366` | `-28.01%` | `106` |
| `clear5_6` | `3,063,352` | `2.0293` | `-28.14%` | `106` |
| `clear7_8` | `3,100,819` | `2.0455` | `-28.04%` | `97` |

Interpretation:

- Lowering buy-dip strength does not improve drawdown or Sharpe.
- Lowering `00631L` cap reduces final value materially while improving MDD only marginally.
- Slower local-regime clearing reduces trades, but not enough to justify lower final value and Sharpe.

## Live Shadow Outputs

Generated a `95/5` continuous shadow recommendation:

- `results/group_a_00679b_continuous_shadow_20260605_1250k_95_5_turnover25.json`
- `results/group_a_00679b_continuous_shadow_20260605_1250k_95_5_turnover25.csv`
- `results/group_a_00679b_continuous_shadow_20260605_1250k_95_5_turnover25.md`

For `1,250,000` total assets and current `10,000` shares of `00679B`:

- Buy notional: `584,174`
- Sell notional: `151,814`
- Execution cost estimate: `1,569`
- Cash after cost: `498,970`

## Recommendation

Adopt only shadow-level changes:

1. Keep current Group A model and latest TDCC as-is.
2. Use `95A / 5 00679B` as the light defensive shadow candidate.
3. Keep `90A / 10 00679B` as the stronger defensive candidate.
4. Do not change PVA buy-dip, `00631L` cap, or local regime clear-days based on this sweep.

Primary Group A-only candidate:

- `95% Group A / 5% 00679B`
- quarterly rebalance
- drift threshold `5%`
- keep TDCC latest under observation

## Outputs

- `results/group_a_00679b_overlay_quarterly_sweep_latest_20240102_20260604.json`
- `results/group_a_tdcc_overlay_variant_sweep_20240102_20260604.json`
- `results/group_a_full_replay_override_sweep_20240102_20260604.json`
- `results/group_a_00679b_continuous_shadow_20260605_1250k_95_5_turnover25.json`
