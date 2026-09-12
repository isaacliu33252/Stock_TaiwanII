# GroupA+ 2026-08-23 Handoff: arXiv:2009.09713 LETF Options Review + 0050 Options Liquidity Investigation

## Status

Paper decision: `do_not_promote`. Follow-up investigation into whether 0050's
own options market could fix the already-validated TXO put overlay's known
granularity problem: also `do_not_promote` (trades one problem for a worse
one). No production code was touched; no data was written to the shared
production database in this thread.

## User Request

User provided: `C:\Users\isaac\Downloads\2009.09713.pdf`

Question: Analyze whether the paper has useful advantages that can be
imported into GroupA+ and the latest strategy.

Follow-ups: "台灣有沒有針對00631L/00632R本身的選擇權市場?" (pushback asking
for more rigorous product-availability verification), then "0050 的選擇權,
可以提高獲利?" (a new, independent question once 0050's own options market
was confirmed to exist), then "OK" (proceed with a full historical liquidity
check rather than stopping at a single day's snapshot).

## Part 1: Paper Summary and Initial Verification

Paper: `arXiv:2009.09713` (Nasekin & Hardle, *Quantitative Finance* 2019,
"Model-driven statistical arbitrage on LETF option markets").

Core mechanism: the paper studies "moneyness scaling" (Leung & Sircar 2015),
a coordinate transformation that maps the implied-volatility smile of a
**leveraged ETF's own options market** (e.g. SSO/UPRO/SDS/SPXU options on
the S&P500) onto the moneyness coordinate of the **unleveraged underlying
ETF's own options market** (e.g. SPY options). Using bootstrap uniform
confidence bands, the paper finds the two markets' IV surfaces remain
statistically distinct even after the transformation, and builds a
model-driven statistical-arbitrage strategy on top: a dynamic
semiparametric factor model (DSFM) forecasts a one-step-ahead theoretical
LETF implied-volatility surface *from* the unleveraged ETF's own observed
options market, then trades the discrepancy against the LETF's own
*actually observed* options market.

**This mechanism structurally requires two separate, simultaneously-existing
options markets on a leveraged/unleveraged ETF pair.**

### Initial verification (later found incomplete, see Part 2)

Queried TAIFEX's official OpenAPI (`https://openapi.taifex.com.tw/v1/
DailyMarketReportOpt`, the same source `taifex_options_data.py` already uses
for TXO) and enumerated every distinct `Contract` code present in a single
day's full options report. Found `TXO` (options on the TAIEX index itself,
not on any ETF), `TEO`/`TFO`/`TGO` (sub-index options), and a number of
2-3-letter codes assumed to be individual-equity options. Initially
concluded **neither leg exists in Taiwan** -- no 00631L/00632R options, and
no dedicated 0050 options either (TXO's underlying is the index, not the
ETF). Recommended `do_not_promote` on this basis without running a
backtest.

## Part 2: User Pushback and Correction

User asked directly: "台灣有沒有針對00631L/00632R本身的選擇權市場?" This
prompted a more rigorous re-check using TAIFEX's **official ETF-options
underlying product list** (`https://www.taifex.com.tw/cht/2/stockLists`)
rather than a single day's trading-activity CSV.

**Correction found**: 0050.TW *does* have its own options market on TAIFEX
-- **contract code NY** (traded contract code `NYO`), confirmed in the
official underlying list alongside 006205 (富邦上証), 006206 (元大上證50),
00636 (國泰中國A50), 00639 (富邦深100), 00643 (群益深証中小), 0056 (元大高
股息), 00878 (國泰永續高股息), 00885 (富邦越南), 00923 (群益台ESG低碳50).
**00631L and 00632R remain confirmed absent** from this official list.

The `NYO` contract code had actually been present in the original raw
`DailyMarketReportOpt` scan (visible in the earlier distinct-contract-code
list) but was not identified as 0050 at the time -- a single day's raw
trading-activity CSV, scanned for unfamiliar codes, is not equivalent to
checking the exchange's official product/underlying list.

**Revised, precise conclusion**: Taiwan has the unleveraged-ETF-options leg
(0050/NY) the paper needs, but *not* the leveraged-ETF-options leg
(00631L/00632R options do not exist at all, on either a trading-activity or
an official-product-list basis). The paper's mechanism still cannot run,
because the leg it actually *trades against* -- the LETF's own observed
options market, whose discrepancy vs. the model-implied surface is the
arbitrage signal -- is the one that is missing. Having only the
unleveraged leg is not sufficient. **`do_not_promote` conclusion unchanged;
the reasoning is now precise about which specific leg is missing.**

Both the registry entry and memory file for this paper review were updated
in place with this correction (not silently overwritten), including an
explicit methodology lesson: a single daily-activity CSV scan is not
equivalent to checking the exchange's official product/underlying list.

## Part 3: 0050 Options Liquidity Investigation (User's Follow-Up Question)

Given 0050's own options market (NY/NYO) does exist, the user asked directly
whether it could improve returns. The natural, concrete angle: GroupA+'s
already-validated TXO put overlay (`2607_00883_txo_put_overlay_pilot_
positive_20260819`, arXiv:2607.00883 -- the cleanest positive result in the
entire research registry) is blocked by a known granularity problem: 65% of
historical rolls theoretically size to zero contracts, because standard
TXO's NT$50/point multiplier against a 43,000+-point TAIEX index doesn't fit
GroupA+'s ~$1.5M NAV. 0050 trades at a much lower nominal price (options
priced per-share in NT$, not index points), so `NYO` options should in
principle offer much finer premium granularity.

### Single-day snapshot (initial check)

`NYO` put premiums observed in the NT$0.5-6/unit range on 2026-08-19 --
i.e. NT$5,000-60,000 per 10,000-unit contract, confirming the granularity
theory (an order of magnitude smaller than typical TXO contract premiums).
However, the same snapshot showed near-total zero trading volume across
almost every strike/expiry combination, with only 1-3 contracts trading on
a handful of near-the-money strikes.

### Full-year verification (per user's "OK" to not stop at one day)

To confirm this wasn't a one-day fluke, fetched a **full year of NYO
history (2025, 238 trading days, 18,504 rows)** by reusing
`taifex_options_data.py`'s existing `refresh_history_years()` function
(pointed at `contract='NYO'` instead of the script's default `'TXO'`),
written to a scratch DB only (not the shared production database, since
this was exploratory and no promotion decision had been reached).

Note: attempting to fetch **2026**'s (current, in-progress year) bulk
history failed both via a raw `urllib` replication of the request and via
the production script's own `refresh_history_years()` function itself
("not a zip file") -- this appears to be a genuine limitation of TAIFEX's
bulk yearly-archive endpoint (it likely only serves fully-completed prior
years), not a bug introduced by this investigation. 2025 (the most recent
complete year) was used instead.

### Results (238 trading days, full year 2025)

- Median daily total volume across the **entire strike/expiry chain**
  (not just puts -- every listed contract): **12**.
- Mean: 20.9.
- **25 of 238 days (10.5%) had ZERO volume across the whole chain.**
- Median number of *different strikes* with any trade at all on a given
  day: **3** (out of dozens listed).
- Maximum single-day total volume across the whole chain: 222.
- Open interest similarly thin: roughly 150-400 contracts total near
  2025 year-end.

### Conclusion

0050 options solve the TXO put overlay's granularity problem in theory
(premium sizes an order of magnitude smaller, comfortably fitting the
~$1.5M NAV budget) but trade it for a different, likely worse problem: the
market is too illiquid to reliably execute a systematic strategy requiring
regular rolls. A strategy needing to trade a specific ~10%-OTM put/expiry
combination on a specific roll date would very plausibly find zero recent
volume and a missing or extremely wide bid-ask at exactly that strike,
given the median across the *entire* chain is only 12 contracts/day.
Execution risk (slippage, inability to fill at a fair price) would likely
erase the granularity benefit in practice.

**`do_not_promote`** -- do not pursue building a 0050-options version of
the put overlay on this evidence.

## Files Changed/Added

No new permanent scripts were added to the repository in this thread (the
investigation was done via ad-hoc Python in the scratchpad and by reusing
`taifex_options_data.py`'s existing functions in-process).

Scratch-only artifact (not committed, not in the shared production DB):
- `/tmp/.../scratchpad/nyo_scratch.db` -- 2025 NYO options history, for
  this investigation only.

Registry (`group_a_plus/research_semantic_registry.json`) entries added
this thread:
- `2009_09713_letf_options_moneyness_scaling_arbitrage` (later corrected
  in place, see Part 2)
- `0050_etf_options_liquidity_check_for_put_overlay_granularity`

## Production Impact

None. No GroupA+ strategy files were touched. No data was written to the
shared `FinRL/data/stock_data.db` -- the 2025 NYO history fetched during
this investigation lives only in a scratch database, since no promotion
decision was reached that would justify making it a permanent part of the
production data pipeline.

## Tests

Not applicable -- this thread was research/data-verification only, no code
changes to test.

## Final Recommendation

- Do not build a 0050-options-based version of the put overlay on this
  evidence -- the granularity problem is solved but the liquidity problem
  that replaces it is, on a full year of real data, worse in a way that
  likely makes systematic execution infeasible.
- The TXO put overlay's original granularity limitation
  (`2607_00883_txo_put_overlay_pilot_positive_20260819`) remains unresolved.
  Any future fix would need either a different mechanism entirely, or
  acceptance of the current NAV-scale limitation as structural.
- If 0050 options liquidity is ever revisited (e.g. GroupA+'s NAV grows
  substantially, or TAIFEX's ETF-options market deepens over time), a fresh
  liquidity check against more recent data would be needed -- this
  conclusion is a snapshot of 2025 conditions, not a permanent structural
  fact about the product.
- Methodology lesson (recorded in memory for future paper reviews): when
  checking whether a Taiwan-market derivative product exists, check the
  exchange's **official product/underlying list** first, not just a single
  day's trading-activity data -- a thinly-traded or unfamiliar contract
  code can be present in the data but not correctly identified, exactly as
  happened here with `NYO`.

No commit was made -- per standing instruction, commits are not suggested
or created unless the user explicitly asks.
