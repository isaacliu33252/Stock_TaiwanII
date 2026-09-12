# HANDOFF - GroupA+ defensive basket sweep after 2022 failure attribution

Date: 2026-08-14  
Owner note: Codex 2026-08-14

## Scope

Follow-up to the 2022 failure attribution. The prior result showed that 2022 losses were mostly defensive-mode losses, not simply late 00631L adds. This sweep tests whether replacing the defensive basket with lower-beta / higher-cash-bond baskets would improve the weak 2022 window without damaging 2020 or recent windows.

No production strategy, live signal, golden1 pointer, execution plan, or order file was changed.

## Tool

Used existing research script:

- `backtest_group_a_plus_defensive_basket.py`

The script uses:

- A20.7/A21 defensive-switch regime frame
- local DuckDB OHLCV/chip features
- dividend-adjusted ETF returns
- transaction costs
- candidate defensive baskets from `DEFENSIVE_BASKETS`

Golden signal pinned to:

- `results/group_a_combined_live_latest.json`

## Windows run

Base mode:

```bash
.venv/bin/python backtest_group_a_plus_defensive_basket.py --start 2020-01-02 --end 2020-12-31 --initial-value 1000000 --golden-signal results/group_a_combined_live_latest.json --output-prefix results/group_a_plus_defensive_basket_sweep_2020_covid_after_20260813_refresh

.venv/bin/python backtest_group_a_plus_defensive_basket.py --start 2022-01-03 --end 2022-12-30 --initial-value 1000000 --golden-signal results/group_a_combined_live_latest.json --output-prefix results/group_a_plus_defensive_basket_sweep_2022_rate_hike_after_20260813_refresh

.venv/bin/python backtest_group_a_plus_defensive_basket.py --start 2024-01-02 --end 2026-08-13 --initial-value 1000000 --golden-signal results/group_a_combined_live_latest.json --output-prefix results/group_a_plus_defensive_basket_sweep_2024_2026_after_20260813_refresh

.venv/bin/python backtest_group_a_plus_defensive_basket.py --start 2025-01-02 --end 2026-08-13 --initial-value 1000000 --golden-signal results/group_a_combined_live_latest.json --output-prefix results/group_a_plus_defensive_basket_sweep_2025_2026_after_20260813_refresh
```

Recovery-ramp mode:

```bash
.venv/bin/python backtest_group_a_plus_defensive_basket.py --start 2020-01-02 --end 2020-12-31 --initial-value 1000000 --golden-signal results/group_a_combined_live_latest.json --recovery-ramp --output-prefix results/group_a_plus_defensive_basket_sweep_2020_covid_recovery_ramp_after_20260813_refresh

.venv/bin/python backtest_group_a_plus_defensive_basket.py --start 2022-01-03 --end 2022-12-30 --initial-value 1000000 --golden-signal results/group_a_combined_live_latest.json --recovery-ramp --output-prefix results/group_a_plus_defensive_basket_sweep_2022_rate_hike_recovery_ramp_after_20260813_refresh

.venv/bin/python backtest_group_a_plus_defensive_basket.py --start 2024-01-02 --end 2026-08-13 --initial-value 1000000 --golden-signal results/group_a_combined_live_latest.json --recovery-ramp --output-prefix results/group_a_plus_defensive_basket_sweep_2024_2026_recovery_ramp_after_20260813_refresh

.venv/bin/python backtest_group_a_plus_defensive_basket.py --start 2025-01-02 --end 2026-08-13 --initial-value 1000000 --golden-signal results/group_a_combined_live_latest.json --recovery-ramp --output-prefix results/group_a_plus_defensive_basket_sweep_2025_2026_recovery_ramp_after_20260813_refresh
```

## Base-mode result summary

Delta values are versus `current_a207` defensive basket in the same script/scenario.

| Window | Best basket | Formal pass count | Most useful finding |
|---|---|---:|---|
| 2020 COVID | bond30_cash30 | 6 | bond/cash baskets materially improve return, Sharpe, and drawdown |
| 2022 rate hike | cash30 | 0 | cash40 improves final value and MDD, but Sharpe worsens |
| 2024-2026 | cash40 | 0 | cash/cash40 improve Sharpe/MDD but reduce final value |
| 2025-2026 | cash40 | 0 | cash/cash40 improve Sharpe/MDD but reduce final value |

Selected base-mode deltas:

| Window | Basket | Final delta | Sharpe delta | MDD delta | Formal pass |
|---|---|---:|---:|---:|---:|
| 2022 | cash30 | +16,818.45 | -0.0332 | +0.0293 | false |
| 2022 | cash40 | +32,809.04 | -0.0695 | +0.0579 | false |
| 2022 | bond30_cash30 | +18,461.55 | -0.6837 | +0.0704 | false |
| 2025-2026 | cash30 | -3,484.85 | +0.0704 | +0.0221 | false |
| 2025-2026 | cash40 | -8,839.88 | +0.1338 | +0.0434 | false |
| 2025-2026 | bond30_cash30 | -92,914.41 | +0.1210 | +0.0918 | false |

## Recovery-ramp result summary

Recovery-ramp reduces some 2022 Sharpe damage for cash baskets, but does not produce a robust promotion candidate.

| Window | Basket | Final delta | Sharpe delta | MDD delta | Stress pass | Formal pass |
|---|---|---:|---:|---:|---:|---:|
| 2022 | cash30 | +9,623.84 | +0.0111 | +0.0043 | 3/4 | false |
| 2022 | cash40 | +20,621.98 | +0.0215 | +0.0139 | 3/4 | false |
| 2024-2026 | cash30 | -6,988.56 | +0.0433 | +0.0219 | 1/4 | false |
| 2024-2026 | cash40 | -16,039.76 | +0.0802 | +0.0427 | 1/4 | false |
| 2025-2026 | cash30 | -5,381.65 | +0.0629 | +0.0221 | 1/4 | false |
| 2025-2026 | cash40 | -11,717.52 | +0.1196 | +0.0434 | 1/4 | false |

## Decision

Do not replace the active defensive basket now.

Reasons:

1. No candidate passed formal multi-scenario gates outside 2020.
2. `cash40` helps 2022 final value and drawdown, but gives up recent final value.
3. `bond30_cash30` and `bond40` are excellent in 2020 COVID but do not solve 2022 well enough and hurt recent returns materially.
4. The best 2022 fix candidate is conditional, not static: use higher cash only during persistent downtrend/rate-hike-like regimes, then release quickly.

## Recommended next step

Build a conditional defensive cash-floor shadow:

- Trigger only when defensive mode is active and downtrend persists.
- Candidate trigger examples:
  - `ma_gap < 0`
  - `drawdown < -8%`
  - `exit_momentum <= 0`
  - optional `realized_vol_ratio_20_60 >= 1.1`
- Candidate basket during trigger:
  - `cash40` or `cash30`
- Release condition:
  - `ma_gap >= 0` and `exit_momentum > 0`

This is more promising than a static basket replacement because static higher-cash baskets improve 2022 but consistently sacrifice 2024-2026 and 2025-2026 final value.

