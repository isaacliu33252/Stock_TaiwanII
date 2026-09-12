# HANDOFF - 2601.05428v1 DMFT / Bounded Multi-Factor Tilts for GroupA+

Date: 2026-08-14  
PDF: `C:\Users\isaac\Downloads\2601.05428v1.pdf`  
Paper: `Dynamic Inclusion and Bounded Multi-Factor Tilts for Robust Portfolio Construction`  
Author: Roberto Garrone  
arXiv: `2601.05428v1`  

## Status

Reviewed and shadow-tested for GroupA+ latest strategy relevance.

No live strategy change was made.

- `golden1_0531`: unchanged
- GroupA+ latest strategy: unchanged
- live signal: unchanged
- execution plan: unchanged
- orders: unchanged

Decision: do not import into GroupA+ latest strategy. Keep only as
research/governance inspiration.

## Paper Summary

The paper proposes a robust portfolio-construction framework, not a directional
forecasting model.

Core mechanism:

- define an eligible universe from lagged observable data;
- start from equal weight over eligible assets;
- compute cross-sectional factor ranks or z-scores;
- apply bounded multiplicative tilts around equal weight;
- rebalance on a deterministic low-frequency schedule;
- avoid expected-return estimation, covariance optimization, regime switching,
  and volatility targeting.

The paper's useful design principles:

- robustness over optimization;
- cross-sectional rankings instead of fragile level forecasts;
- explicit weight and eligibility constraints;
- operational realism: turnover, liquidity, costs, and rebalance frequency are
  part of the design.

Important limitation for GroupA+:

- the method is built for larger cross-sectional universes;
- GroupA+ latest tradable core has only four assets:
  `0050.TW`, `00631L.TW`, `00632R.TW`, `00679B.TWO`;
- the paper itself notes that very small universes make cross-sectional
  normalization unstable;
- the method is long-horizon/semiannual by design, while GroupA+ latest is a
  daily tactical regime and execution workflow.

## What Was Implemented

New research-only evaluator:

- `scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py`

This is a local DMFT-lite adaptation:

- universe: GroupA+ four ETF core;
- eligibility:
  - minimum price history;
  - average dollar volume threshold support;
- factors:
  - 126-day momentum skipping the most recent 21 days;
  - inverse 63-day realized volatility;
  - 126-day drawdown resilience;
- factor combination:
  - equal factor mixture;
  - cross-sectional z-score;
  - bounded multiplier;
- bounds:
  - default multiplier range `0.70` to `1.30`;
- rebalance frequencies:
  - monthly;
  - quarterly;
  - semiannual;
- transaction cost:
  - default `10 bps` per turnover value;
- benchmark:
  - same-universe equal weight at the same rebalance frequency.

The evaluator includes warmup support so signals can be computed from
pre-window history while performance is measured only in the requested window.

## Commands Run

Syntax check:

```bash
.venv/bin/python -m py_compile \
  scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py
```

Main and stress windows:

```bash
.venv/bin/python scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py \
  --start 2020-01-02 --end 2026-08-13 --warmup-start 2020-01-02 \
  --output-json results/2601_05428_dmft_lite_groupa_plus_shadow_2020_2026.json \
  --output-md report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2020_2026.md

.venv/bin/python scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py \
  --start 2021-01-04 --end 2026-08-13 --warmup-start 2020-01-02 \
  --output-json results/2601_05428_dmft_lite_groupa_plus_shadow_2021_2026.json \
  --output-md report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2021_2026.md

.venv/bin/python scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py \
  --start 2020-01-02 --end 2020-12-31 --warmup-start 2020-01-02 \
  --output-json results/2601_05428_dmft_lite_groupa_plus_shadow_2020_covid.json \
  --output-md report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2020_covid.md

.venv/bin/python scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py \
  --start 2022-01-03 --end 2022-12-30 --warmup-start 2020-01-02 \
  --output-json results/2601_05428_dmft_lite_groupa_plus_shadow_2022_rate_hike.json \
  --output-md report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2022_rate_hike.md

.venv/bin/python scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py \
  --start 2024-01-02 --end 2026-08-13 --warmup-start 2020-01-02 \
  --output-json results/2601_05428_dmft_lite_groupa_plus_shadow_2024_2026.json \
  --output-md report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2024_2026.md

.venv/bin/python scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py \
  --start 2025-01-02 --end 2026-08-13 --warmup-start 2020-01-02 \
  --output-json results/2601_05428_dmft_lite_groupa_plus_shadow_2025_2026.json \
  --output-md report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2025_2026.md
```

## Results

Promotion gate definition:

- DMFT-lite final value must beat equal weight;
- Sharpe must beat equal weight;
- max drawdown must be no worse;
- minimum eligible asset count must be at least `3`;
- all are evaluated inside the requested window.

Summary:

| Window | Promotion ready | Passing variants | Best final-value variant | Final delta | Sharpe delta | MDD delta | Notes |
|---|---:|---:|---|---:|---:|---:|---|
| 2020-2026 | false | 0 | monthly, tilt 0.10 | -887,663 | -0.0330 | +0.0114 | early history/warmup constraints bind |
| 2021-2026 | false | 0 | monthly, tilt 0.10 | -170,075 | +0.0110 | +0.0114 | mature-period broad test still fails final value |
| 2020 COVID | false | 0 | monthly, tilt 0.10 | -167,418 | -1.5564 | +0.1214 | too little history; falls back toward cash |
| 2022 rate hike | false | 0 | monthly, tilt 0.35 | +2,292 | -0.4157 | +0.0278 | small final gain but Sharpe worse |
| 2024-2026 | false | 0 | monthly, tilt 0.10 | -108,066 | +0.0243 | +0.0165 | lower drawdown/Sharpe but loses return |
| 2025-2026 | true locally | 3 | monthly, tilt 0.35 | +52,710 | +0.0633 | +0.0309 | recent-window-only positive |

Interpretation:

- The only passing window is `2025-2026`, which is too narrow and too
  recent to justify live promotion.
- 2022 shows the expected defensive behavior: slightly better terminal value
  and drawdown, but materially worse Sharpe.
- 2024-2026 improves drawdown/Sharpe modestly but gives up too much return.
- Full-period and mature-period tests do not support replacing or overlaying
  GroupA+ latest with DMFT-lite.
- The method's low-frequency equal-weight core is not comparable to
  golden1/a2118's tactical daily regime logic.

## Continued Broad ETF Pool Test

After the initial GroupA+ four-ETF test, an additional fairer cross-sectional
test was run because the paper's method is intended for broader universes.

Broad ETF pool:

- `0050.TW`
- `0056.TW`
- `00631L.TW`
- `00632R.TW`
- `00646.TW`
- `00679B.TWO`
- `00713.TW`
- `00751B.TWO`
- `00878.TW`

Coverage check:

- all nine tickers have usable common data from `2020-07-10` onward;
- mature-history tests used `warmup-start=2020-07-10`.

Additional commands:

```bash
.venv/bin/python scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py \
  --tickers 0050.TW,0056.TW,00631L.TW,00632R.TW,00646.TW,00679B.TWO,00713.TW,00751B.TWO,00878.TW \
  --start 2022-01-03 --end 2026-08-13 --warmup-start 2020-07-10 \
  --output-json results/2601_05428_dmft_lite_broad_etf_shadow_2022_2026.json \
  --output-md report/group_a_plus/latest/2601_05428_dmft_lite_broad_etf_shadow_2022_2026.md

.venv/bin/python scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py \
  --tickers 0050.TW,0056.TW,00631L.TW,00632R.TW,00646.TW,00679B.TWO,00713.TW,00751B.TWO,00878.TW \
  --start 2022-01-03 --end 2022-12-30 --warmup-start 2020-07-10 \
  --output-json results/2601_05428_dmft_lite_broad_etf_shadow_2022_rate_hike.json \
  --output-md report/group_a_plus/latest/2601_05428_dmft_lite_broad_etf_shadow_2022_rate_hike.md

.venv/bin/python scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py \
  --tickers 0050.TW,0056.TW,00631L.TW,00632R.TW,00646.TW,00679B.TWO,00713.TW,00751B.TWO,00878.TW \
  --start 2024-01-02 --end 2026-08-13 --warmup-start 2020-07-10 \
  --output-json results/2601_05428_dmft_lite_broad_etf_shadow_2024_2026.json \
  --output-md report/group_a_plus/latest/2601_05428_dmft_lite_broad_etf_shadow_2024_2026.md

.venv/bin/python scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py \
  --tickers 0050.TW,0056.TW,00631L.TW,00632R.TW,00646.TW,00679B.TWO,00713.TW,00751B.TWO,00878.TW \
  --start 2025-01-02 --end 2026-08-13 --warmup-start 2020-07-10 \
  --output-json results/2601_05428_dmft_lite_broad_etf_shadow_2025_2026.json \
  --output-md report/group_a_plus/latest/2601_05428_dmft_lite_broad_etf_shadow_2025_2026.md
```

Broad-pool summary:

| Window | Promotion ready | Passing variants | Best final-value variant | Final delta | Sharpe delta | MDD delta | Min eligible |
|---|---:|---:|---|---:|---:|---:|---:|
| broad 2022-2026 | false | 0 | monthly, tilt 0.10 | -108,710 | +0.0313 | +0.0051 | 9 |
| broad 2022 rate hike | false | 0 | monthly, tilt 0.10 | -2,335 | -0.1143 | +0.0051 | 9 |
| broad 2024-2026 | false | 0 | monthly, tilt 0.10 | -100,002 | +0.0488 | +0.0091 | 9 |
| broad 2025-2026 | true locally | 3 | monthly, tilt 0.20 | +11,740 | +0.0546 | +0.0170 | 9 |

Additional control:

| Window | Universe | Promotion ready | Passing variants | Best final-value variant | Final delta | Sharpe delta | MDD delta | Min eligible |
|---|---|---:|---:|---|---:|---:|---:|---:|
| 2022-2026 | GroupA+ core 4 ETF | false | 0 | monthly, tilt 0.10 | -127,061 | +0.0137 | +0.0114 | 4 |

Broad-pool interpretation:

- More assets improve cross-sectional stability but do not solve the promotion
  problem.
- 2022-2026 and 2024-2026 still lose final value despite slightly better
  Sharpe/drawdown.
- The only positive broad-pool window is again `2025-2026`, matching the
  recent-window-only pattern from the 4-ETF core.
- This supports using bounded tilts as a research/governance pattern for
  future broader ETF baskets, but not as a current GroupA+ latest overlay.

## Import Decision

Do not import DMFT-lite into GroupA+ latest strategy.

Reasons:

- GroupA+ universe is too small for stable cross-sectional z-scoring;
- the paper is a robust construction framework, not a daily signal model;
- empirical support is not robust across stress windows;
- 2025-2026 positive result is recent-window-only and may reflect the same
  low-volatility/rising-market condition that the paper lists as a failure
  mode for dynamic eligibility comparisons;
- no evidence that this improves the existing golden1/a2118 live path after
  costs and guardrails.

## What Can Be Borrowed

Useful concepts to keep as governance or future shadow checks:

- explicit eligibility constraints for any future asset additions;
- bounded multiplier caps when adding factor/rank tilts;
- low-frequency rebalancing discipline for satellite baskets, not for
  golden1 core;
- requirement that any cross-sectional tilt first prove it works on a
  sufficiently broad ETF universe;
- hard promotion gate requiring final value, Sharpe, drawdown, and turnover to
  improve together.

Not recommended:

- replacing golden1 weights with equal-weight baseline;
- applying cross-sectional z-scores directly to the 4-ETF GroupA+ core;
- using DMFT-lite as an automatic `00631L` add/reduce rule;
- wiring it into live signal, execution guard, or order generation.

## Current State

Files produced:

- `scripts/evaluate/evaluate_2601_05428_dmft_lite_groupa_plus_shadow.py`
- `results/2601_05428_dmft_lite_groupa_plus_shadow_2020_2026.json`
- `results/2601_05428_dmft_lite_groupa_plus_shadow_2021_2026.json`
- `results/2601_05428_dmft_lite_groupa_plus_shadow_2020_covid.json`
- `results/2601_05428_dmft_lite_groupa_plus_shadow_2022_rate_hike.json`
- `results/2601_05428_dmft_lite_groupa_plus_shadow_2024_2026.json`
- `results/2601_05428_dmft_lite_groupa_plus_shadow_2025_2026.json`
- `results/2601_05428_dmft_lite_groupa_plus_shadow_2022_2026.json`
- `results/2601_05428_dmft_lite_broad_etf_shadow_2022_2026.json`
- `results/2601_05428_dmft_lite_broad_etf_shadow_2022_rate_hike.json`
- `results/2601_05428_dmft_lite_broad_etf_shadow_2024_2026.json`
- `results/2601_05428_dmft_lite_broad_etf_shadow_2025_2026.json`
- `report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2020_2026.md`
- `report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2021_2026.md`
- `report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2020_covid.md`
- `report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2022_rate_hike.md`
- `report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2024_2026.md`
- `report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2025_2026.md`
- `report/group_a_plus/latest/2601_05428_dmft_lite_groupa_plus_shadow_2022_2026.md`
- `report/group_a_plus/latest/2601_05428_dmft_lite_broad_etf_shadow_2022_2026.md`
- `report/group_a_plus/latest/2601_05428_dmft_lite_broad_etf_shadow_2022_rate_hike.md`
- `report/group_a_plus/latest/2601_05428_dmft_lite_broad_etf_shadow_2024_2026.md`
- `report/group_a_plus/latest/2601_05428_dmft_lite_broad_etf_shadow_2025_2026.md`

Production pointer check:

```bash
git diff -- \
  report/group_a_plus/latest/strategy.json \
  report/group_a_plus/latest/live_signal.json \
  report/group_a_plus/latest/execution_plan.json
```

Expected result: no diff.

## Final Closeout

User asked whether this paper has been fully analyzed. Current answer: yes,
for GroupA+ latest-strategy import purposes.

Completed scope:

- PDF content reviewed;
- paper method classified correctly as robust portfolio construction, not a
  forecasting or daily-timing model;
- GroupA+ core 4-ETF DMFT-lite shadow completed;
- mature-window GroupA+ core control completed;
- broader 9-ETF universe shadow completed;
- stress windows completed;
- local promotion gates applied consistently;
- production pointer diff checked.

Closed decision:

- do not import into latest strategy;
- do not alter `golden1_0531`;
- do not wire to live signal;
- do not wire to execution guard;
- do not create orders;
- do not cite the `2025-2026` local positive result as sufficient evidence
  for production promotion.

Allowed future use:

- cite this paper as support for explicit eligibility gates;
- cite this paper as support for bounded factor/rank tilts;
- use the evaluator for future broader ETF-basket research;
- require multi-window promotion evidence before any live integration.

Blocked future use unless new evidence is produced:

- replacing GroupA+ latest weights;
- changing `00631L` exposure rules;
- adding a live cross-sectional z-score overlay to the 4-ETF core;
- promoting broad ETF DMFT-lite based only on the recent `2025-2026` window.

Final production status:

- latest strategy remains unchanged;
- `golden1_0531` remains unchanged;
- latest live signal remains unchanged;
- latest execution plan remains unchanged.
