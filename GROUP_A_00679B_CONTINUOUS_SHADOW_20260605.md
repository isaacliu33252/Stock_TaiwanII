# Group A + 00679B Continuous Shadow

Date: 2026-06-05 signal, using market data through 2026-06-04
Status: Shadow research only

## Scope

This is a FinRL-Meta-style continuous overlay/reporting layer. It does not change `Golden1_0531` production.

Inputs:

- Group A signal: `results/signal_group_a_20260604_184447.json`
- Total assets: `1,250,000`
- Current 00679B: `10,000` shares
- Overlay target: `80% Group A / 20% 00679B`
- Slippage estimate: `0.05%`
- Commission: `0.1425%`
- ETF sell tax: `0.10%`

## Raw 80/20 Target

| Ticker | Current | Target | Delta | Side | Trade notional | Batches |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| `0050.TW` | `492` | `5,470` | `4,978` | buy | `528,166` | `3` |
| `00631L.TW` | `0` | `3,123` | `3,123` | buy | `119,611` | `3` |
| `00632R.TW` | `0` | `0` | `0` | hold | `0` | `1` |
| `00679B.TWO` | `10,000` | `9,437` | `-563` | sell | `14,914` | `1` |

Cost estimate:

- Buy notional: `647,777`
- Sell notional: `14,914`
- Total execution cost including slippage: `1,291`
- Cash after cost: `298,745`

Outputs:

- `results/group_a_00679b_continuous_shadow_20260605_1250k_raw.csv`
- `results/group_a_00679b_continuous_shadow_20260605_1250k_raw.json`
- `results/group_a_00679b_continuous_shadow_20260605_1250k_raw.md`

## Turnover-Controlled Target

This version uses current weights as `last_action` and applies `turnover_penalty = 0.25`, shrinking the move toward the raw target by 25%.

| Ticker | Current | Target | Delta | Side | Trade notional | Batches |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| `0050.TW` | `492` | `4,225` | `3,733` | buy | `396,071` | `3` |
| `00631L.TW` | `0` | `2,342` | `2,342` | buy | `89,699` | `1` |
| `00632R.TW` | `0` | `0` | `0` | hold | `0` | `1` |
| `00679B.TWO` | `10,000` | `9,578` | `-422` | sell | `11,179` | `1` |

Cost estimate:

- Buy notional: `485,770`
- Sell notional: `11,179`
- Total execution cost including slippage: `968`
- Cash after cost: `457,340`

Outputs:

- `results/group_a_00679b_continuous_shadow_20260605_1250k_turnover25.csv`
- `results/group_a_00679b_continuous_shadow_20260605_1250k_turnover25.json`
- `results/group_a_00679b_continuous_shadow_20260605_1250k_turnover25.md`

## Recommendation

Use the turnover-controlled target as the first practical shadow candidate. It preserves the same directional allocation as raw 80/20, but lowers first-day turnover and execution cost.

The raw 80/20 target is useful as the long-run target reference. The turnover-controlled version is better for staged real execution.
