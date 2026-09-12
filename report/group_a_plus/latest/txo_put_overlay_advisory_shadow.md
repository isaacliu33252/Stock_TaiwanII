# TXO Put Overlay Advisory Shadow

- as_of: `2026-08-18`
- status: `holding`
- **advisory only — no live position, no order placed, no live allocation impact**

## Roll schedule
- current roll date: `2026-08-03` (next roll: `2026-09-01`, in 11 trading days)
- is roll day today: `False`

## Contract
- TXO put, contract_month=`202609`, strike=`39000` (target 10% OTM was `39000`)
- TAIEX spot at roll: `43386.4`

## Pricing
- entry price at roll: `750.0`  current price: `106.0` (as of `2026-08-17`)
- unrealized P&L vs initial premium: `-85.9%`

## Sizing (theoretical, at recommended premium budget)
- NAV used: `$1,478,056` (source: `execution_plan.current_total_assets`)
- annual premium budget: `1.50%`, this roll's budget: `$1,848`
- recommended contracts: `0` (actual premium at that size: `$0`)
- **budget rounds to 0 contracts at current option pricing** — the premium budget this roll (`$1,848`) is smaller than one contract's premium (`$37,500`)

Validation reference: Five robustness layers (single-window, 7 independent calendar years, 0.5-3.0%/yr premium sensitivity, real bid-ask transaction costs, 0050-vs-TWII basis risk) all positive or directionally unchanged as of 2026-08-19. Not yet promoted -- Group A+ has no options-execution infrastructure.
