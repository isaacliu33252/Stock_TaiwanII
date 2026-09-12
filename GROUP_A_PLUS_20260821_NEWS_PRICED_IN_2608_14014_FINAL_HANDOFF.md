# GroupA+ 2608.14014 Final Handoff - 2026-08-21

## Scope

Paper reviewed:

- `C:\Users\isaac\Downloads\2608.14014.pdf`
- Working title from extracted text: `Buy the Rumor, Sell the News: When Is News Priced In?`

Objective:

- Assess whether the paper has ideas worth adding to GroupA+ latest strategy.
- If useful, implement only low-risk research/shadow components first.
- Avoid turning public news sentiment into a direct trading signal unless local validation proves it adds value.

## Final Decision

Do not promote this paper into GroupA+ target-weight logic yet.

Current accepted state:

- Keep as `shadow_only_no_target_weight_change`.
- Keep as advisory/research metadata.
- Do not wire it into `daily_signal.py`.
- Do not allow it to change target weights, rebalance decisions, or execution guards.
- Do not trade positive/negative public-news direction directly.

Reason:

- The paper's central warning is directly relevant: much public news direction is already priced before or on publication.
- Local GroupA+ validation did not find any event bucket that materially beats a coverage-only baseline at both H5 and H20.
- The best current use is to measure event type, coverage intensity, and volatility-width context, not to infer a direct long/short signal from news direction.

## Paper Takeaways For GroupA+

Useful ideas:

- Separate event presence/coverage from news direction.
- Treat public post-news drift as suspicious unless compared with placebo or coverage-only baselines.
- Hard quantified/fundamental news can be monitored for continuation, but still needs local evidence.
- Soft narrative, promotional, or price-commentary news should be treated as attention/risk context, not directional alpha.
- News taxonomy should preserve event attributes instead of compressing everything into a single sentiment score.

Non-useful or risky ideas:

- Using positive/negative news sentiment as a direct trade trigger.
- Adding exposure after news publication without checking whether the move was already priced.
- Treating media coverage itself as bullish.

## Implemented Files

### 1. Research review

`docs/HANDOFF_2608_14014_NEWS_PRICED_IN_GROUPA_PLUS_REVIEW_20260821.md`

Contains:

- Paper summary.
- GroupA+ integration recommendation.
- Implementation addenda.
- Coverage-baseline validation addendum.
- Taxonomy-refinement addendum.
- Final no-promotion decision.

### 2. Shadow integration

`group_a_plus/integrations/news_event_prior_shadow.py`

Purpose:

- Classify watchlist news into event buckets.
- Produce advisory metadata only.
- Explicitly block target-weight and auto-rebalance use.

Important output policy fields:

- `policy`: `shadow_only_no_target_weight_change`
- `target_weight_change_allowed`: `False`
- `auto_rebalance_allowed`: `False`
- `direction_trade_allowed`: `False`

Current event buckets:

- `hard_quantified`
- `soft_story`
- `macro_through_stock`
- `legal_regulatory`
- `fund_flow_positioning`
- `etf_structure`
- `investor_education`
- `price_commentary`
- `promotional`
- fallback `unknown`

Important fix already made:

- The first draft treated almost any headline with a number as `quantified_like`.
- This was narrowed so quantified-like only applies to true `hard_quantified` items or numeric text with financial/fundamental context.

### 3. Daily/latest builder

`scripts/evaluate/build_group_a_plus_news_event_prior_shadow.py`

Purpose:

- Reads latest GroupA+ watchlist news.
- Builds latest shadow JSON.
- Writes dated history.
- Appends JSONL log.

Default inputs/outputs:

- Input: `report/group_a_plus/latest/watchlist_news.json`
- Latest output: `report/group_a_plus/latest/news_event_prior_shadow.json`
- History: `report/group_a_plus/news_event_prior_shadow/history/news_event_prior_shadow_YYYYMMDD.json`
- Log: `results/news_event_prior_shadow_log.jsonl`

Command used:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_news_event_prior_shadow.py --as-of 2026-08-20
```

Latest known output summary:

- `as_of`: `2026-08-20`
- `status`: `available`
- `policy`: `shadow_only_no_target_weight_change`
- `article_count`: `8`
- `target_weight_change_allowed`: `False`
- `direction_trade_allowed`: `False`
- `coverage_width_watch`: `True`

Latest current event bucket counts:

- `soft_story`: `3`
- `price_commentary`: `2`
- `investor_education`: `1`
- `macro_through_stock`: `1`
- `fund_flow_positioning`: `1`

### 4. Coverage-baseline evaluator

`scripts/evaluate/evaluate_group_a_plus_news_event_prior_coverage_baseline.py`

Purpose:

- Tests whether event buckets add value beyond plain news coverage.
- Compares event days to quiet days and coverage baseline.
- Evaluates H1/H5/H20 forward returns.

Default tickers:

- `0050.TW`
- `00631L.TW`
- `00632R.TW`
- `00679B.TWO`
- `2330.TW`

Default outputs:

- `report/group_a_plus/latest/news_event_prior_coverage_baseline_review.json`
- `report/group_a_plus/latest/news_event_prior_coverage_baseline_review.md`
- `report/group_a_plus/news_event_prior_coverage_baseline_review/history/`

Command used:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_news_event_prior_coverage_baseline.py
```

Latest known result:

- `event_days`: `725`
- date range: `2025-01-02..2026-08-18`
- decision: `do_not_promote_keep_shadow`
- blocker count: `1`
- blocker: `no_event_bucket_materially_beats_coverage_baseline`

Coverage stats:

- raw news rows: `14512`
- total event days: `1065`
- event days with returns: `725`
- quiet days with returns: `14581`

Taxonomy quality after refinement:

- unknown event days: `289`
- unknown share of event days with returns: `39.86%`
- usable bucket count: `5`
- material bucket edges vs coverage: none

## Latest Validation Numbers

Coverage baseline quiet-day means:

| Horizon | Mean return | Mean abs return |
| --- | ---: | ---: |
| H1 | `0.0007530081` | `0.0105232073` |
| H5 | `0.0036335258` | `0.0255011361` |
| H20 | `0.0144716277` | `0.0587475793` |

Key bucket excess returns versus coverage baseline:

| Bucket | Event days | H1 excess | H5 excess | H20 excess | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| `fund_flow_positioning` | `140` | `+0.0020848` | `+0.0048125` | `+0.0032035` | Watch only |
| `etf_structure` | `217` | `-0.001911` | `-0.002923` | `-0.004290` | Do not promote |
| `hard_quantified` | `30` | `+0.002539` | `-0.007778` | `-0.014335` | Do not promote |
| `macro_through_stock` | `20` | `-0.002902` | insufficient | insufficient | Do not promote |
| `unknown` | `289` | `+0.000287` | `+0.001396` | `+0.002125` | Not actionable |

Interpretation:

- `fund_flow_positioning` is the closest candidate, but it still does not clear the strict H5/H20 materiality threshold versus coverage baseline.
- `hard_quantified` is too sparse and unstable in current local data.
- The high `unknown` share means taxonomy can still improve, but current evidence is not strong enough for target-weight promotion.

## Verification Already Run

Python compile checks passed:

```bash
.venv/bin/python -m py_compile \
  group_a_plus/integrations/news_event_prior_shadow.py \
  scripts/evaluate/build_group_a_plus_news_event_prior_shadow.py \
  scripts/evaluate/evaluate_group_a_plus_news_event_prior_coverage_baseline.py
```

Generated artifacts refreshed after taxonomy refinement:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_news_event_prior_shadow.py --as-of 2026-08-20
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_news_event_prior_coverage_baseline.py
```

## Do Not Do

Do not:

- Promote this module into `daily_signal.py` yet.
- Use news event bucket counts to directly change GroupA+ target weights.
- Add or reduce `00631L` based on public-news direction.
- Treat positive public news as bullish alpha.
- Treat negative public news as bearish alpha.
- Treat coverage spikes as buy signals.
- Use `fund_flow_positioning` as a live trade rule until strict out-of-sample and cost-aware tests pass.

## Allowed Follow-Up

Reasonable next steps:

- Keep running the daily shadow builder.
- Keep logging `news_event_prior_shadow.json` and `results/news_event_prior_shadow_log.jsonl`.
- Improve Taiwan-specific taxonomy to reduce `unknown`.
- Add explicit coverage-intensity and volatility-width diagnostics.
- Retest after more labeled data accumulates.
- Test `fund_flow_positioning` separately with strict out-of-sample, turnover, and transaction-cost assumptions.

Promotion criteria before this can affect GroupA+:

- Event bucket must beat coverage baseline, not only quiet baseline.
- Must show stable H5 and H20 advantage.
- Must survive ticker-level checks.
- Must survive realistic turnover/cost assumptions.
- Must not duplicate existing chip, margin, or regime signals.

## Current Handoff Status

Paper 2608.14014 first-pass GroupA+ experiment is complete.

Final state:

- Research note complete.
- Shadow module implemented.
- Daily builder implemented.
- Coverage-baseline evaluator implemented.
- Latest artifacts generated.
- No live strategy promotion.
- Keep as research/shadow only.

