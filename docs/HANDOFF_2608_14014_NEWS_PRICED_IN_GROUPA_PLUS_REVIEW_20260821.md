# arXiv 2608.14014 News Priced-In Review for GroupA+ - 2026-08-21

## Paper

Local file: `C:\Users\isaac\Downloads\2608.14014.pdf`

Title: "Buy the Rumor, Sell the News: When Is News Priced In?"

Core question: when public equity news is incorporated into prices, which kinds
of news continue versus reverse, and whether news sentiment direction itself is
tradable after publication.

## Paper Summary

The paper studies 4.57 million financial-news articles for roughly 3,000 US
stocks from 2023 to 2026. A GPT teacher plus distilled classifier labels each
article with 17 event tags and five attributes: scheduled, forward-looking,
primary source, quantified, and rumor. Articles are clustered into stories so
first reports can be separated from follow-up coverage. Returns are measured
around 1.68 million stock-day events, with 364,405 neutral-sentiment events used
as a placebo for general coverage/background drift.

Main findings:

- Most news-direction price movement happens before or on publication day.
- Rumor-confirmation events literally match "buy the rumor, sell the news":
  the rumor captures the move; confirmation adds little or nothing.
- Raw post-news drift is misleading unless neutral-news / comparable-stock
  background drift is subtracted.
- After the placebo adjustment, quantified fundamental news tends to continue:
  capital returns, earnings, guidance, analyst actions.
- Soft narrative news tends to reverse: macro-through-stock, product launches,
  leadership/governance, competition.
- News has a second-moment effect: coverage raises uncertainty before
  publication and volatility compresses after publication because uncertainty
  is resolved.
- For forecasting systems, durable information is event kind, first/follow-up
  status, rumor flag, quantified/scheduled attributes, source type, and coverage
  intensity. Sentiment direction is mostly spent by publication close.

## Relevance to GroupA+

GroupA+ already has several news/sentiment components:

- `group_a_plus/integrations/finbert.py`
- `group_a_plus/integrations/lm_dictionary_sentiment.py`
- `group_a_plus/integrations/watchlist_news.py`
- `group_a_plus/integrations/daily_semantic_context.py`
- `scripts/evaluate/build_market_aligned_sentiment_shadow.py`
- daily fetch steps for LTN, Yahoo RSS, SETN RSS, and FinMind stock news.

Current GroupA+ news handling is mostly sentiment-score or headline-alignment
based. This paper argues that this is the wrong primary representation for
post-publication prediction: event type and coverage structure matter more than
sentiment direction.

## Direct Trading Readiness

Do not directly promote.

Reasons:

- The paper is US single-stock public-news event study; GroupA+ trades a small
  Taiwan ETF basket.
- GroupA+ does not currently have the paper's required event classifier:
  17 event tags, five event attributes, story clustering, NEW/follow-up flag,
  source groups, and neutral-news placebo baseline.
- The paper explicitly shows that naive sentiment-fading strategies can be
  indistinguishable from a coverage/background drift baseline.
- Existing GroupA+ news sources are mostly headlines/snippets, not full article
  bodies, and Chinese local news requires a separate Taiwan-specific taxonomy.
- Directional signal is mostly priced by publication day, so it should not be
  used to automatically add 00631L after the news is already public.

Decision: no target-weight wiring, no execution guard wiring, no live trade
rule.

## Useful Transferable Ideas

### 1. Stop treating news sentiment as a direct forecast

The strongest immediate design lesson is negative: do not promote a simple
"positive news -> add risk" or "negative news -> cut risk" rule from public
headlines. In GroupA+, FinBERT/LM/news signals should remain weak alignment or
context diagnostics unless they pass a placebo-controlled event study.

Recommended policy:

- Keep FinBERT and LM dictionary as low-weight context.
- Keep `next_day_prediction` null in market-aligned sentiment shadow unless a
  new diagnostic proves otherwise.
- Do not use public-news direction alone to add 00631L.

### 2. Add event-type priors as shadow-only metadata

The paper's most usable positive idea is a compact event prior table. GroupA+
could classify watchlist news into a small Taiwan-adapted taxonomy:

- hard/quantified: earnings, dividends/capital return, guidance/outlook,
  analyst/broker action, financing/dilution, regulatory/legal.
- soft/story: product launch, partnership/customer, leadership/governance,
  macro-through-stock, promotional/price commentary.
- structural attributes: scheduled, quantified, rumor, primary source,
  NEW/follow-up, article_count.

Initial use should be shadow-only:

- `event_prior_direction`: continuation / reversal / neutral.
- `event_width_prior`: widen_before / compress_after / neutral.
- `event_quality`: hard_quantified / soft_story / promotional / unknown.
- `target_weight_change_allowed`: false.

### 3. Add coverage-baseline diagnostics

Before any news alpha is trusted, compare it to a coverage-presence baseline:
what happens on days a ticker simply appears in news, regardless of sentiment.

For GroupA+, a Taiwan-specific version could use:

- ticker/date news presence from FinMind tagged stock news.
- article count / source count as coverage intensity.
- same-day and +1..+5 / +6..+20 ETF or stock abnormal returns.
- neutral or zero-score headlines as weak placebo, if enough observations exist.
- quiet days with no same-ticker news as a fallback baseline.

This should be a research report first, not a trade rule.

### 4. Use news as a volatility-width signal

This is more plausible for GroupA+ than direction:

- scheduled, quantified events may widen near event date.
- after the event is public, uncertainty may compress.
- high article-count days may imply wider realized move, even if direction is
  not predictable.

Candidate integration point:

- daily semantic context or volatility shadow metadata.
- never directly target weights.
- compare against existing GARCH / RG-ResMoE / tail-conformal diagnostics.

## Recommended Implementation Path

### Phase 1: Research-only review and registry

Record this paper as a caution against raw sentiment trading and as a design
prior for future news-conditioned diagnostics.

Status: recommended.

### Phase 2: Build a Taiwan news event-prior shadow

Proposed file:

- `group_a_plus/integrations/news_event_prior_shadow.py`

Inputs:

- `report/group_a_plus/latest/watchlist_news.json`
- `news/finmind_stock_news_rolling.jsonl`
- optional Yahoo/SETN/LTN rolling files.

Outputs:

- `report/group_a_plus/latest/news_event_prior_shadow.json`
- `results/news_event_prior_shadow_log.jsonl`

Suggested payload:

- date
- article_count
- per_ticker event buckets
- hard_quantified_count
- soft_story_count
- rumor_like_count
- followup_like_count
- coverage_intensity
- width_prior
- direction_prior
- target_weight_change_allowed=false

Important: first version can use deterministic keyword buckets, not an LLM. It
should be marked low-confidence and shadow-only until validated.

### Phase 3: Backtest coverage baseline

Before any promotion, run a Taiwan-specific event study:

- compare sentiment/event-prior returns versus coverage-only baseline.
- measure same-day, +1..+5, +6..+20 windows.
- split 0050, 00631L, 00632R, 00679B, 2330 if data allows.
- include costs and trading feasibility if any long/short overlay is proposed.

Promotion bar:

- event-prior edge must beat coverage-only baseline.
- effect must survive recent 2025-2026 slice.
- no added 00631L exposure from public-news direction without separate review.

## Current Decision

This paper has useful ideas, but not an immediately promotable GroupA+ trading
rule.

Adopt now:

- conceptual rule: sentiment direction is mostly spent by publication close.
- review rule: any news alpha must beat a coverage-presence baseline.
- design rule: represent news as event tags/attributes/coverage intensity, not
  only sentiment scalar.

Do not adopt now:

- public-news sentiment direction as a target-weight driver.
- buy/sell after rumor confirmation.
- fade positive soft news without Taiwan-specific coverage baseline.
- any direct 00631L add/cut rule.

Best next step:

- Build a shadow-only `news_event_prior_shadow` and validate it against current
  news logs before considering any strategy impact.

## 2026-08-21 Implementation Addendum

Completed the first shadow-only implementation.

New files:

- `group_a_plus/integrations/news_event_prior_shadow.py`
- `scripts/evaluate/build_group_a_plus_news_event_prior_shadow.py`

Outputs generated:

- `report/group_a_plus/latest/news_event_prior_shadow.json`
- `report/group_a_plus/news_event_prior_shadow/history/news_event_prior_shadow_20260820.json`
- `results/news_event_prior_shadow_log.jsonl`

Design:

- deterministic keyword taxonomy only; no LLM call.
- coarse event buckets:
  - `hard_quantified`
  - `soft_story`
  - `macro_through_stock`
  - `legal_regulatory`
  - `price_commentary`
  - `promotional`
  - `unknown`
- article attributes:
  - `rumor_like`
  - `scheduled_like`
  - `quantified_like`
  - `primary_source_like`
  - `followup_like`
- output policy:
  - `shadow_only_no_target_weight_change`
  - `target_weight_change_allowed=false`
  - `direction_trade_allowed=false`
  - `auto_rebalance_allowed=false`

Validation run:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_news_event_prior_shadow.py --as-of 2026-08-20
```

Result for current `watchlist_news.json`:

- status: `available`
- article_count: `8`
- event_bucket_counts:
  - `soft_story`: 3
  - `price_commentary`: 3
  - `macro_through_stock`: 1
  - `unknown`: 1
- hard_quantified_count: `0`
- rumor_like_count: `0`
- scheduled_like_count: `0`
- quantified_like_count: `0`
- coverage_width_watch: `true`

Per-symbol dominant buckets:

- `0050.TW`: `soft_story`, medium coverage intensity.
- `00631L.TW`: `price_commentary`, medium coverage intensity.
- `00632R.TW`: `unknown`, medium coverage intensity.
- `00679B.TWO`: `macro_through_stock`, low coverage intensity.
- `2330.TW`: `price_commentary`, low coverage intensity.

Important implementation note:

- The first draft marked any numeric headline as `quantified_like`; this was
  too broad and inconsistent with the paper's meaning of quantified
  fundamental disclosure. It was narrowed to financial/fundamental numeric
  contexts such as earnings, dividend, guidance, rating, target price, rate,
  yield, and inflation.

Current decision after implementation:

- keep as a daily shadow/context artifact.
- do not add to `daily_signal.py` target-weight logic.
- do not use direction priors as trade rules.
- next validation, if requested, should be a Taiwan-specific coverage-baseline
  event study using current news logs and OHLCV.

## 2026-08-21 Coverage-Baseline Event Study Addendum

Completed the first Taiwan coverage-baseline review.

New file:

- `scripts/evaluate/evaluate_group_a_plus_news_event_prior_coverage_baseline.py`

Outputs:

- `report/group_a_plus/latest/news_event_prior_coverage_baseline_review.json`
- `report/group_a_plus/latest/news_event_prior_coverage_baseline_review.md`
- `report/group_a_plus/news_event_prior_coverage_baseline_review/history/news_event_prior_coverage_baseline_review_20260818.json`

Command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_news_event_prior_coverage_baseline.py
```

Coverage:

- raw FinMind news rows: `14512`
- ticker-day event rows: `1065`
- event days with forward returns: `725`
- date range: `2025-01-02` to `2026-08-18`
- quiet days with forward returns: `14581`

Quiet baseline:

| Horizon | Mean return | Mean absolute return |
|---|---:|---:|
| H1 | 0.075% | 1.052% |
| H5 | 0.363% | 2.550% |
| H20 | 1.447% | 5.875% |

Coverage-only baseline:

| Horizon | Mean return | Excess vs quiet | Mean absolute return | Excess abs vs quiet |
|---|---:|---:|---:|---:|
| H1 | 0.299% | 0.223% | 1.607% | 0.554% |
| H5 | 1.385% | 1.021% | 3.837% | 1.287% |
| H20 | 5.347% | 3.900% | 9.040% | 3.165% |

Interpretation:

- News coverage itself is associated with higher forward returns and wider
  realized moves than quiet days in the 2025-2026 sample.
- This supports the paper's warning that coverage/presence is a powerful
  baseline and must not be confused with event-direction alpha.
- It does not prove event bucket alpha.

Bucket results:

- `unknown` dominates: 664 of 725 event days with returns.
- `hard_quantified` has only 24 event days; H20 excess return is positive
  (+2.51% vs quiet), but sample is too small for promotion.
- `macro_through_stock` has 20 H1 observations only; H1 excess return is near
  zero while absolute-return excess is positive, consistent with width rather
  than direction.
- `price_commentary`, `soft_story`, and `legal_regulatory` are below the
  minimum sample threshold in this first taxonomy pass.

Blocker added:

- `event_taxonomy_unknown_share_above_50pct`

Decision after coverage study:

- Coverage/intensity shadow is useful.
- Current keyword event taxonomy is not mature enough to support event-bucket
  conclusions.
- No promotion, no target weight change, no directional news trade.
- The next useful improvement is better Taiwan-specific event labeling, not
  strategy wiring.

## 2026-08-21 Taxonomy Refinement Addendum

The first coverage-baseline run showed `unknown` dominated the taxonomy. A
manual sample of unknown FinMind headlines showed that many were Taiwan ETF
flow/positioning, ETF structure, or investor-education articles rather than
corporate events. Added three Taiwan-specific buckets:

- `fund_flow_positioning`
- `etf_structure`
- `investor_education`

Updated file:

- `group_a_plus/integrations/news_event_prior_shadow.py`

Full FinMind classification distribution after refinement:

- `unknown`: 6539
- `etf_structure`: 4895
- `fund_flow_positioning`: 4722
- `hard_quantified`: 2095
- `investor_education`: 1380
- `soft_story`: 1051
- `macro_through_stock`: 892
- `price_commentary`: 661
- `legal_regulatory`: 99
- `promotional`: 63

The daily `news_event_prior_shadow` for 2026-08-20 was also regenerated. The
8 current watchlist articles now classify as:

- `soft_story`: 3
- `price_commentary`: 2
- `investor_education`: 1
- `macro_through_stock`: 1
- `fund_flow_positioning`: 1

Coverage-baseline review was rerun after the taxonomy update:

- event days with returns: `725`
- unknown event days: `289`
- unknown share: `39.86%`
- usable bucket count: `5`
- blocker now: `no_event_bucket_materially_beats_coverage_baseline`

Key excess-vs-coverage results:

| Bucket | Event days | H1 excess vs coverage | H5 excess vs coverage | H20 excess vs coverage |
|---|---:|---:|---:|---:|
| fund_flow_positioning | 140 | +0.21% | +0.48% | +0.32% |
| etf_structure | 217 | -0.19% | -0.29% | -0.43% |
| hard_quantified | 30 | +0.25% | -0.78% | -1.43% |
| macro_through_stock | 20 | -0.29% | insufficient | insufficient |
| unknown | 289 | +0.03% | +0.14% | +0.21% |

Interpretation after refinement:

- Taxonomy quality improved enough for monitoring.
- Coverage itself remains the main signal; event buckets do not materially beat
  the coverage-only baseline.
- `fund_flow_positioning` is the only bucket with positive excess at all three
  horizons, but the effect is small and does not clear the material edge bar
  used in the review.
- `hard_quantified` does not replicate the paper's continuation edge in this
  Taiwan ETF/news setting; it is positive only at H1 and worse than coverage at
  H5/H20.

Final implementation decision:

- Keep `news_event_prior_shadow` and coverage-baseline review as research
  artifacts.
- Do not wire event buckets into `daily_signal.py`.
- Do not use `fund_flow_positioning` to trade until a stricter out-of-sample
  and cost-aware study proves it beats coverage-only days.
