# Group A Golden1_0531 Improvement Experiment

Date: 2026-05-31
Status: Research complete, no production promotion
Scope: Group A only

## 1. Baseline

Production release remains:

- [`Golden1_0531`](GROUP_A_GOLDEN1_0531_RELEASE.md)

The production entrypoint, payload, and live signal were not changed.

## 2. PVA Runtime Micro-Sweep

Evidence:

- [`results/group_a_Golden1_0531_pva_micro_sweep_20260531.json`](results/group_a_Golden1_0531_pva_micro_sweep_20260531.json)
- [`results/group_a_Golden1_0531_dual_objective_20260531.json`](results/group_a_Golden1_0531_dual_objective_20260531.json)

The first sweep tested `243` runtime combinations without PPO retraining.

The best dual-objective shadow candidate is:

- [`results/group_a_candidate_Golden1_0531_pva036_j015_20260531.json`](results/group_a_candidate_Golden1_0531_pva036_j015_20260531.json)

Changes versus `Golden1_0531`:

- `pva_weight: 0.32 -> 0.36`
- `pva_j_state_weight: 0.19 -> 0.15`
- Keep `pva_min_leverage_scale = 0.40`
- Keep `pva_buy_dip_strength = 0.95`
- Keep all local-regime settings unchanged

The sweep produced the same observed metrics for `pva_min_leverage_scale = 0.35`, `0.40`, and `0.45` in this candidate neighborhood. The shadow manifest keeps the production value `0.40` to minimize unnecessary changes.

Recent OOS comparison on `2025-01-02` to `2026-05-25`:

| Metric | Golden1_0531 | Shadow candidate | Delta |
| --- | ---: | ---: | ---: |
| Final value | `2,058,975.61` | `2,061,509.36` | `+2,533.75` |
| Annual return | `72.7260%` | `72.8868%` | `+0.1608 pp` |
| Sharpe | `2.303933` | `2.307882` | `+0.003948` |
| Max drawdown | `-24.9939%` | `-24.9909%` | `+0.0031 pp` |
| Trades | `63` | `63` | `0` |
| Fees | `21,338.36` | `21,286.15` | `-52.21` |

TWII 2008 proxy comparison:

| Metric | Golden1_0531 | Shadow candidate | Delta |
| --- | ---: | ---: | ---: |
| Final value | `1,494,398.92` | `1,494,175.46` | `-223.46` |
| Sharpe | `0.572420` | `0.572326` | `-0.000094` |
| Max drawdown | `-38.0202%` | `-38.0194%` | `+0.0008 pp` |
| Trades | `310` | `310` | `0` |

Interpretation:

- The OOS improvement is real but small.
- Crash behavior is effectively unchanged.
- This does not justify changing the production strategy during the three-month trial.
- Retain the candidate for shadow comparison through `2026-08-31`.

## 3. Local-Regime Hysteresis Sweep

Evidence:

- [`results/group_a_Golden1_0531_local_regime_sweep_20260531.json`](results/group_a_Golden1_0531_local_regime_sweep_20260531.json)

Tested:

- `risk_off_clear_days = 3, 5, 7`
- `severe_clear_days = 4, 6, 8`
- `severe_template = 0050_70_00632R_30, 0050_only`

Result:

- Keep the existing Golden1_0531 local-regime configuration.
- Increasing `risk_off_clear_days` to `7` improved crash proxy drawdown from `-38.02%` to `-36.19%`, but reduced recent OOS final value by about `61,162`.
- Replacing the severe inverse template with `0050_only` reduced crash trades materially, but worsened crash proxy drawdown to roughly `-54%` to `-55%`.
- Changing `severe_clear_days` did not materially change results in this tested matrix.

## 4. Decision

- Keep production release: `Golden1_0531`
- Do not modify live execution rules during the trial period.
- Track shadow candidate: `Golden1_0531_shadow_pva036_j015`
- Revisit promotion only after the `2026-08-31` review with actual execution data.

## 5. Full-Feature Training Run — 2026-06-03

Training command:
```
python3 train_dual_group_2024_2026.py \
  --group-filter group_a --timesteps 300000 --seed 42 \
  --group-a-action-schema triplet_v4 \
  --group-a-enable-dca --group-a-dca-day 20 --group-a-dca-0050 5000 \
  --group-a-enable-pva-features --group-a-enable-pva-sigmoid \
  --group-a-enable-llm-sentiment \
  --group-a-enable-institutional \
  --group-a-enable-local-regime-gate \
  --group-a-00631l-max-weight 0.20 \
  --group-a-pva-weight 0.32 --group-a-pva-s-state-max-weight 0.35 \
  --group-a-pva-j-state-weight 0.19 --group-a-pva-m-state-weight 1.0 \
  --group-a-pva-drift-threshold 0.05 --group-a-pva-target-vol 0.012 \
  --group-a-pva-min-leverage-scale 0.40 --group-a-pva-inverse-hedge-budget 0.30 \
  --group-a-pva-buy-dip-strength 0.95 \
  --group-a-local-regime-risk-off-score-threshold 2 \
  --group-a-local-regime-severe-score-threshold 3 \
  --group-a-local-regime-risk-off-clear-days 3 \
  --group-a-local-regime-severe-clear-days 4 \
  --group-a-local-regime-risk-off-template 0050_only \
  --group-a-local-regime-severe-template 0050_70_00632R_30
```

Results:

| Metric | Full-Feature Run | Golden1_0531 | Basic (triplet_v2) |
| --- | ---: | ---: | ---: |
| Final Value | 2,686,446 | 2,058,976 | 3,572,755 |
| Annual Return | 55.51% | — | — |
| Sharpe | **1.860** | **2.30** | 1.857 |
| MDD | **-29.42%** | **-25%** | -36.15% |
| Trades | 109 | 63 | — |
| PVA triggers | 44 | — | — |
| DCA triggers | 28 | — | — |
| Total invested | 1,140,000 | — | — |
| Net profit | 1,546,446 | — | — |

Observation:
- Final value is higher than Golden1_0531 (2.69M vs 2.06M) but Sharpe 1.86 < 2.30 and MDD -29.42% > -25%.
- Higher return but worse risk-adjusted metrics suggests excessive volatility / overfitting.
- Basic triplet_v2 with no overlays achieved highest final value (3.57M) but worst MDD (-36.15%).
- Adding full feature set (PVA + sentiment + institutional + regime gate) did NOT improve risk-adjusted performance over Golden1_0531.

Conclusion: Golden1_0531 remains the production standard. Full-feature approach needs further tuning before promotion.
Evidence: `results/group_a_backtest_20240101_20260508_20260603_150406.json`
