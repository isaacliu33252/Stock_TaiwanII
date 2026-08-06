# GroupA+ Handoff - 2026-06-06

## Definition

`GroupA+` means:

```text
Latest Group A LLM meta shadow strategy + 00679B defensive sleeve
```

Config:

- `group_a_plus_config.json`

Base Group A signal:

- Strategy: `GroupA_meta_ensemble_real_v1`
- Selected profile: `adaptive_momcash_price_severe12_vote_bearfilter_recovery_defense22`
- Signal: `results/group_a_meta_ensemble_shadow_live_latest.json`
- Sweep: `results/group_a_meta_real_vote_tune_sweep_20250101_20260606_llmfilled.json`

00679B overlay:

- Ticker: `00679B.TWO`
- Reference shares: `10,000`
- Latest local price date: `2026-06-05`
- Latest local price: `26.55`

## Latest Data State

Market data refresh:

- Target date requested: `2026-06-06`
- Actual latest trading date: `2026-06-05`
- Reason: `2026-06-06` is Saturday.

LLM sentiment:

- File: `FinRL/data/sentiment/llm_market_sentiment_daily.csv`
- Date range: `2020-02-01` to `2026-06-06`
- Latest build uses LTN rule-based sentiment bundle.
- GDELT refresh was attempted but blocked by API rate limits / invalid responses.

## Group A LLM Meta Update

Updated artifacts:

- `results/group_a_meta_ensemble_real_backtest_20250101_20260606_llmfilled.json`
- `results/group_a_meta_real_vote_tune_sweep_20250101_20260606_llmfilled.json`
- `results/group_a_meta_ensemble_shadow_live_latest.json`

Latest Group A signal for `2026-06-08`:

- Actual data date: `2026-06-05`
- Regime/source event: `risk_off`
- Target weights:
  - `0050.TW`: `60.75%`
  - `00631L.TW`: `8.00%`
  - `00632R.TW`: `0.00%`
  - cash: `31.25%`

## GroupA+ Improvements Completed

### 1. Dynamic 00679B Overlay

Implemented in:

- `group_a_00679b_continuous_shadow.py`

Config:

- `overlay.dynamic_weight_bands`

Rules:

| Regime | 00679B target |
|---|---:|
| risk_on | 0% |
| caution | 2% |
| risk_off | 4% |
| severe | 8% |

Current `2026-06-08` result:

- Regime: `risk_off`
- 00679B target: `4%`
- Current 00679B: `10,000` shares
- Executable action: hold `10,000` shares

### 2. 00631L Leverage Cap

Config:

- `leverage_control.max_weight_by_regime`

Rules:

| Regime | 00631L max |
|---|---:|
| risk_on | 8% |
| caution | 8% |
| risk_off | 6% |
| severe | 3% |

Current `2026-06-08` result:

- Raw `00631L` after 80% Group A sleeve: `6.4%`
- Risk-off cap: `6.0%`
- Released to cash: `0.4%`

### 3. Risk-Off Staged Buy Execution

Config:

- `execution_control.buy_fraction_by_regime`

Rules:

| Regime | Buy fraction |
|---|---:|
| risk_on | 100% |
| caution | 100% |
| risk_off | 70% |
| severe | 50% |

Sell fraction remains `100%` in all regimes.

Defensive sleeve reduction fraction:

| Regime | 00679B sell fraction |
|---|---:|
| risk_on | 100% |
| caution | 100% |
| risk_off | 75% |
| severe | 50% |

Reason:

- Risk-off should not delay risk reduction sells.
- Risk-off should avoid buying full size into a possible continuation selloff.
- Selling 00679B to fund stock buys is risk-increasing, so defensive sleeve reductions are staged separately.

Single-trade turnover cap:

| Regime | Max turnover |
|---|---:|
| risk_on | 100% |
| caution | 60% |
| risk_off | 25% |
| severe | 25% |

Reason:

- Even after staged buys and staged 00679B sells, risk-off rotation can still be too large.
- The cap scales the already-staged trade deltas so one recommendation does not exceed the configured turnover budget.

### 4. Second-Stage Execution Trigger

Implemented in:

- `group_a_plus_second_stage_execution.py`

Config:

- `second_stage_control`

Rules:

| Trigger | Action |
|---|---:|
| 0050 breaks 6/5 low | pause deferred buys |
| 0050 opens down 1.5% or more | pause deferred buys unless close confirms recovery |
| 0050 closes above 6/5 close | release 50% of deferred buys |
| 0050 / TAIEX recovers intraday | release 25% of deferred buys |

The script reads the first-stage `GroupA+` JSON and outputs the next executable target using the first-stage target as the assumed current post-execution position.

## Latest GroupA+ 6/8 Output

Generated files:

- `results/group_a_plus_dynamic_20260608.json`
- `results/group_a_plus_dynamic_20260608.csv`
- `results/group_a_plus_dynamic_20260608.md`
- `results/group_a_plus_minimal_20260608.json`
- `results/group_a_plus_minimal_20260608.csv`
- `results/group_a_plus_minimal_20260608.md`
- `results/group_a_plus_minimal_staged_bond_20260608.json`
- `results/group_a_plus_minimal_staged_bond_20260608.csv`
- `results/group_a_plus_minimal_staged_bond_20260608.md`
- `results/group_a_plus_minimal_turnover35_20260608.json`
- `results/group_a_plus_minimal_turnover35_20260608.csv`
- `results/group_a_plus_minimal_turnover35_20260608.md`
- `results/group_a_plus_grid_sweep_20250102_20260605.json`
- `results/group_a_plus_grid_sweep_20250102_20260605.csv`
- `results/group_a_plus_grid_sweep_20250102_20260605_curve.csv`
- `results/group_a_plus_grid_best_20260608.json`
- `results/group_a_plus_grid_best_20260608.csv`
- `results/group_a_plus_grid_best_20260608.md`

Inputs:

- Total assets: `1,274,769`
- Current 00679B: `10,000` shares
- Turnover penalty: `0.10` from `execution_control.live_turnover_penalty_by_regime`
- Min trade value: `10,000`
- Source signal: `results/group_a_meta_ensemble_shadow_live_latest.json`
- 00679B cache resolved to: `FinRL/data/portfolio_cache/00679B_TWO_20200101_20260605_1d_raw_v1.parquet`

Generated live-config files:

- `results/group_a_plus_dynamic_20260608_live_config.json`
- `results/group_a_plus_dynamic_20260608_live_config.csv`
- `results/group_a_plus_dynamic_20260608_live_config.md`

Note:

- The final executable target is unchanged from the 25% turnover-cap output because the `risk_off` single-trade turnover cap still binds after staged execution.

Executable targets:

| Ticker | Current | Target | Delta | Action |
|---|---:|---:|---:|---|
| `0050.TW` | 89 | 2,248 | +2,159 | buy |
| `00631L.TW` | 0 | 638 | +638 | buy |
| `00632R.TW` | 0 | 0 | 0 | hold |
| `00679B.TWO` | 10,000 | 7,348 | -2,652 | sell |

Execution estimate:

- Buy notional: `248,255`
- Sell notional: `70,411`
- Estimated total execution cost: `684`
- Estimated cash after cost: `821,471`
- Turnover ratio: `25.00%`

## Pytest Fix

Root issue:

- Root `__init__.py` was collected by pytest as a standalone module.
- It eagerly ran relative imports like `from . import data`.
- That failed with `ImportError: attempted relative import with no known parent package`.

Fix:

- Root `__init__.py` now only eager-imports subpackages when `__package__` is set.

Validation:

- `.venv/bin/python -m pytest test_group_a_00679b_continuous_shadow.py -q`
  - `11 passed`
- `.venv/bin/python -m pytest test_group_a_tdcc_improved_signal.py -q`
  - `13 passed`

## Important Files Changed

- `__init__.py`
- `group_a_plus_config.json`
- `group_a_00679b_continuous_shadow.py`
- `test_group_a_00679b_continuous_shadow.py`
- `test_group_a_tdcc_improved_signal.py`
- `GROUP_A_PLUS_DEFINITION_20260606.md`
- `results/group_a_plus_dynamic_20260608.json`
- `results/group_a_plus_dynamic_20260608.csv`
- `results/group_a_plus_dynamic_20260608.md`

## Current Recommendation

For `2026-06-08`, prefer the latest `GroupA+ grid_best` staged execution output rather than the older 20% 00679B defensive version:

- Buy `0050.TW` toward `2,248` shares.
- Buy `00631L.TW` toward `638` shares.
- Reduce `00679B.TWO` toward `7,348` shares, not the full 3,940 raw target.
- Keep a cash reserve until market confirms no continuation selloff.

## GroupA+ Overlay Backtest

Implemented in:

- `backtest_group_a_plus_overlay.py`

Generated files:

- `results/group_a_plus_overlay_backtest_20250102_20260605.json`
- `results/group_a_plus_overlay_backtest_20250102_20260605.csv`
- `results/group_a_plus_overlay_backtest_20250102_20260605_curve.csv`

Method:

- Research approximation, not a full RL rerun.
- Replays selected Group A meta rebalance events.
- Applies GroupA+ dynamic 00679B sleeve, 00631L caps, and staged buy execution at close prices.
- Uses exact DCA purchase history from `base_exact_backtest.dca_purchase_history`, so the base approximation is now within about `10,179` of the source selected meta replay.

Result:

| Variant | Final | Sharpe | MDD | Vol |
|---|---:|---:|---:|---:|
| source selected meta | `2,218,146` | `2.7835` | `-16.7260%` | `21.9757%` |
| base events approx | `2,207,967` | `2.7675` | `-16.8630%` | `21.9810%` |
| GroupA+ grid best final | `1,987,234` | `2.6767` | `-16.8427%` | `19.6407%` |
| GroupA+ best Sharpe | `1,964,693` | `2.6841` | `-16.8427%` | `19.2443%` |

Conclusion:

- The old 20% risk-off 00679B sleeve was too defensive for 2025-2026.
- Grid sweep selected `grid_b04_buy70_bsell75_turn25` by final value.
- Highest Sharpe was `grid_b10_buy70_bsell75_turn25`, but with lower final value.
- GroupA+ still trails base events on final value and Sharpe, so it remains a risk-control execution overlay rather than a return-maximizing strategy.
- Promotion gate added to `backtest_group_a_plus_overlay.py`:
  - Decision: `shadow_risk_control_only`
  - Best return variant: `GroupA+_grid_b04_buy70_bsell75_turn25`
  - Best risk variant: `GroupA+_grid_b10_buy70_bsell75_turn25`
  - Best return variant vs base approx: final drag `-9.9971%`, Sharpe delta `-0.0908`, MDD improvement `+0.0203%`, volatility reduction `+2.3403%`
  - Gate result: do not promote and do not retrain from this evidence alone.

## Next Improvements

1. Full RL environment replay with GroupA+ controls embedded, if we need a stricter answer than the current event replay approximation.
2. Retrain only if the embedded replay shows the base allocator needs to learn the 00679B sleeve directly.
