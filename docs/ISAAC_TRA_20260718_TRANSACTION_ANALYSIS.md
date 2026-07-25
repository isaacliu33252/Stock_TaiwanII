# isaac_tra_20260718 Transaction Analysis

## Source

- File: `C:\Users\isaac\Downloads\Stock_taiwan2-main\Stock_taiwan2-main\isaac_tra_20260718.xlsx`
- Sheet: `工作表1`
- Rows read: `278`
- Valid transaction rows after removing blank / malformed rows: `276`
- Transaction date range after data cleaning: `2022-09-14` to `2026-07-17`

## Data Quality Notes

This file should be treated as a transaction-history sample, not a complete
broker-position ledger.

Issues found:

- One obvious date typo:
  - raw date: `2925-06-13`
  - interpreted for analysis as `2025-06-13`
- Some symbols have sells greater than buys inside this file:
  - `元大台灣50`
  - `富邦台50`
  - `玉山金`
  - `普萊德`
- Therefore, the file is missing initial holdings, transfers, corporate-action
  adjustments, or older trade records.

Practical implication:

- Do not use this file alone to generate broker-actionable orders.
- A current broker holdings export plus real cash balance is required.

## Estimated Current Positions

Positive positions with local 2026-07-17 prices:

| Name | Ticker | Estimated shares | Cost basis | 2026-07-17 price | Estimated market value | Unrealized P/L | Return |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `元大高股息` | `0056.TW` | `14233` | `463,997` | `50.75` | `722,325` | `258,328` | `55.67%` |
| `國泰永續高股息` | `00878.TW` | `13775` | `304,347` | `31.81` | `438,183` | `133,836` | `43.97%` |
| `元大台灣高息低波` | `00713.TW` | `4952` | `250,307` | `60.25` | `298,358` | `48,051` | `19.20%` |
| `元大AAA至A公司債` | `00751B.TWO` | `4000` | `126,608` | `31.44` | `125,760` | `-848` | `-0.67%` |
| `元大美債20年` | `00679B.TWO` | `3000` | `82,914` | `26.95` | `80,850` | `-2,064` | `-2.49%` |
| `元大S&P500` | `00646.TW` | `1032` | `75,916` | `76.05` | `78,484` | `2,567` | `3.38%` |
| `元大台灣50正2` | `00631L.TW` | `500` | `18,646` | `32.17` | `16,085` | `-2,561` | `-13.73%` |

Estimated total for positive priced positions:

- cost basis: `1,322,736`
- market value: `1,760,044`
- unrealized P/L: `437,309`
- unrealized return: `33.06%`

Estimated market-value weights, excluding incomplete / missing-price positions:

| Name | Weight |
| --- | ---: |
| `元大高股息` | `41.04%` |
| `國泰永續高股息` | `24.90%` |
| `元大台灣高息低波` | `16.95%` |
| `元大AAA至A公司債` | `7.15%` |
| `元大美債20年` | `4.59%` |
| `元大S&P500` | `4.46%` |
| `元大台灣50正2` | `0.91%` |

## July 2026 Activity

Transactions from `2026-07-01` through `2026-07-17`:

| Name | Type | Trades | Shares | Net cashflow |
| --- | --- | ---: | ---: | ---: |
| `元大台灣50` | buy | `10` | `880` | `-93,565` |
| `元大台灣50正2` | buy | `9` | `470` | `-17,514` |
| `元大美債20年` | sell | `1` | `2000` | `53,424` |

July net cashflow:

- `-57,655`

Interpretation:

- July trading sold part of `00679B` bond ETF and added `0050` plus `00631L`.
- This increases Taiwan equity exposure and adds leveraged exposure during a
  period when GroupA+ governance still blocks new leverage adds.

## Fit With GroupA+ 2026-07-20 Final Decision

Latest full-pipeline decision record:

- `docs/GROUPA_PLUS_20260720_FULL_PIPELINE_FINAL_DECISION_RECORD.md`

Relevant GroupA+ state:

- `00631L` NCF direction: `DOWN`
- `00631L probability_up = 0.4912`
- `00631L confidence = 0.3332`
- dynamic CVaR tail/cost readiness: `blocked`
- research shadow snapshot: `blocked`
- deployment consistency: `manual_review_required`
- promotion gate: `blocked_multi_window`

Therefore:

- The July `00631L` adds are not aligned with current GroupA+ governance.
- `00631L` should not be averaged down while the dynamic CVaR / tail / cost
  readiness remains blocked.
- A direct `00632R` hedge is also not recommended automatically; the signal is
  mixed and governance does not authorize a hedge trade.

## Recommendations

### 1. Stop New `00631L` Buys For Now

The transaction file shows `470` new `00631L` shares bought in July 2026.

Recommendation:

- pause further `00631L` accumulation;
- do not average down the current `00631L` position;
- only reconsider after dynamic CVaR readiness, research shadow, deployment
  consistency, and promotion gates improve.

### 2. Keep Bonds / Cash As Buffer

The file shows `00679B` was reduced sharply:

- total bought in file: `46,000`
- total sold in file: `43,000`
- estimated remaining: `3,000`

Recommendation:

- avoid selling remaining bond/cash buffer to fund leverage buys;
- keep liquidity available until the governance layer no longer blocks
  rebalance / leverage adds.

### 3. Simplify Overlapping High-Dividend ETF Exposure

Estimated priced portfolio is heavily concentrated in high-dividend Taiwan ETFs:

- `0056`
- `00878`
- `00713`

These three alone are roughly `82.9%` of the priced positive-position estimate.

Recommendation:

- keep these as long-term income exposure only if this is intentional;
- avoid adding all three mechanically without a target allocation;
- for GroupA+ alignment, define a simple policy such as:
  - core: `0050`
  - income sleeve: one or two dividend ETFs
  - defensive sleeve: cash / bonds
  - tactical sleeve: `00631L` only when gates permit

### 4. Do Not Use This File Alone For Rebalance Orders

Because several positions are incomplete or negative in the transaction-only
ledger, this file cannot determine true current holdings.

Required before broker-actionable planning:

- current broker holdings export;
- actual cash balance;
- confirmation whether the `2925-06-13` row should be corrected to
  `2025-06-13`;
- clarification of any transfers, stock distributions, or pre-2022 positions.

### 5. Practical 2026-07-20 Action

For 2026-07-20:

- do not auto-rebalance;
- do not add `00631L`;
- do not open `00632R` hedge automatically;
- do not change Golden1_0531;
- continue using the refreshed full-pipeline result as reference only.

## Next Data Step

To produce a reliable execution plan, use this transaction file only as context
and provide a current holdings/cash file. Then rerun:

- execution plan from real holdings and cash;
- daily status with the new execution plan;
- deployment consistency review.
