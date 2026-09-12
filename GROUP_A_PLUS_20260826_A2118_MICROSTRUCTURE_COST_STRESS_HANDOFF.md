# Handoff: A21.18 Microstructure Cost Stress (not A21.19 SciPhyRL)

Date: 2026-08-26
Project root: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main`
Scope: user-directed follow-up to the 2607.15195 (SciPhyRL) review's own
conclusion -- do not open an RL main-line on SciPhyRL/PINN/HJB; instead build
a more realistic market-impact / liquidity cost model per ticker
(0050.TW / 00631L.TW / 00632R.TW / 00679B.TWO) and re-check whether previous
"small positive" candidates survive it.

## Files Added

- `scripts/evaluate/build_group_a_plus_a2118_microstructure_cost_stress.py`
- `tests/test_build_group_a_plus_a2118_microstructure_cost_stress.py` (8 passed)
- `report/group_a_plus/latest/a2118_microstructure_cost_stress.json`

## What Was Built

Three cost models, applied to the SAME live A21.18 regime/weight schedule
(decision logic unchanged -- this only changes cost accounting):

1. `flat` -- current production model (commission 0.1425% + slippage 0.05% +
   equity/LETF sell tax 0.1%, bond ETF exempt), independent of trade size.
2. `linear_liquidity` -- adds `notional * impact_bps/1e4 * participation`,
   where `participation = trade_notional / ADV_notional_20d` (per ticker).
3. `quadratic_impact` -- same but `participation^2`, matching the paper-side
   convention already governance-approved in
   `2607_15195_cost_aware_target_holding_shadow.json`
   (`linear_cost_bps=5.0`, `quadratic_impact_bps=25.0`).

Three stress levels per model:

- `1x_current_cost`: flat only (matches production today).
- `realistic_impact` / `2x_realistic_impact`: base coefficients, then doubled.
- `stress_liquidity`: base coefficients, ADV divided by 5 (simulated
  liquidity crunch / crash-day turnover collapse).

Re-priced against two targets:

1. Full live A21.18 regime-switch history, 2020-01-02 to 2026-08-24, at NAV
   scales `1,486,457` (current real AUM), `10M`, `50M`, `200M`.
2. The still-open raw A21.18 seed-ensemble target (`0050 70% / 00631L 30%`)
   vs the guarded live target (`0050 30% / cash 70%`), at the ACTUAL current
   portfolio state (~NT$1.99M total assets as of 2026-08-25).

## Key Results

ADV (mean daily notional, 2020-2026):

| Ticker | Mean ADV (NTD) | Median ADV (NTD) |
|---|---|---|
| 0050.TW | 2.67B | 1.51B |
| 00631L.TW | 1.22B | 0.51B |
| 00632R.TW | 1.00B | 0.85B |
| 00679B.TWO | 0.74B | 0.62B |

At current real AUM (NT$1.49M), worst case (`stress_liquidity_quadratic`)
over the full 6.5-year history:

- extra impact cost = **0.011 bps of NAV**, Sharpe delta = 0.0
- avg participation of ADV per trade: 0050 0.14%, 00631L 0.20%, 00632R 0.35%,
  00679B 0.015%
- 00632R has the highest participation (as its ADV is smallest relative to
  its role in the switch schedule) but is still 3-4 orders of magnitude below
  where impact would matter

At a hypothetical 200M NAV (~134x current AUM), same worst case:

- extra impact cost = 195.7 bps over 6.5 years (~30 bps/yr), Sharpe delta
  -0.0045 (still negligible vs baseline Sharpe 0.92)
- **but** max single-day participation for 00632R reaches 2.2x that day's
  ADV -- i.e. at that scale a same-day rebalance would not be physically
  executable, a structural constraint the smooth cost formula alone
  understates.

Raw vs guarded target, at actual current AUM (NT$1.99M total assets,
2026-08-25 snapshot): raw target costs 14.50 bps of assets, guarded costs
10.50 bps, under the flat model. Adding linear/quadratic impact at any
stress level changes these numbers only in the 3rd decimal place
(14.503 -> 14.504 bps). The guard-down decision is fully explained by the
flat commission/tax model alone; market impact contributes nothing to it.

## Conclusion

At GroupA+'s real capital scale, liquidity-aware and quadratic ADV-impact
costs are **not** the threat to any currently shadow "small positive"
candidate -- the flat commission/slippage/tax model already in production
completely dominates. This closes the specific question of whether a bigger
market-impact model would unmask a cost-driven false positive among existing
candidates: it does not, at this AUM. The already-documented real
constraints (TXO put integer-lot granularity, 0050 options bid/ask spread,
etc. -- see memory `project_txo_put_overlay_affordable_subset_20260823` and
`project_0050_options_liquidity_20260823`) remain the binding ones, not
market impact.

TXO put overlay and the PPO seed-averaging ensemble were NOT re-priced by
this script: the former trades TAIFEX options (no equity ADV), the latter's
only tradeable output is the raw/guarded target already covered above. BAWS
is a VaR/ES forecaster with no turnover of its own -- out of scope.

## What Would Change This

- GroupA+ AUM growing into the tens of millions of NTD (not currently the
  case) -- at that point, re-run this script and check the
  `nav_scale_results` table again, paying attention to
  `max_participation_of_adv_by_ticker` (execution feasibility), not just the
  smooth cost-bps number.
- A genuinely different ADV regime (e.g. 00631L/00632R volume collapsing
  structurally, not just a stress multiplier) -- re-run with a shorter
  recent window instead of the full 2020-2026 average.

## Reproduction

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_a2118_microstructure_cost_stress.py \
  --start 2020-01-02 --end 2026-08-24
.venv/bin/python -m pytest tests/test_build_group_a_plus_a2118_microstructure_cost_stress.py -q
```

Result: `8 passed`.
