# GroupA+ Paper Review - arXiv 2605.01954 Moira - 2026-08-07

## Source

- File: `C:\Users\isaac\Downloads\2605.01954.pdf`
- Title: `Moira: Language-driven Hierarchical Reinforcement Learning for Pair Trading`
- arXiv: `2605.01954`

## Paper Summary

Moira treats pair trading as a hierarchical decision problem:

- High-level `Selector`: chooses a pair using long-horizon price and semantic
  information such as news.
- Low-level `Trader`: trades the selected pair using short-horizon spread,
  price, position, and news context.
- Feedback is delayed and ambiguous, so the paper separates errors into:
  - bad abstraction / selection,
  - bad execution,
  - interaction or market noise.
- Both policies are LLM prompts with frozen model weights.
- Improvement happens through textual critique and prompt updates, not gradient
  fine-tuning.

The paper reports strong results on a small U.S. stock universe, but the setting
is narrow: ten liquid U.S. equities, short 2025 test period, pair trading only,
and no Taiwan ETF execution constraints.

## Useful Ideas For GroupA+

### 1. Hierarchical Credit Assignment

Useful and safe to adapt.

GroupA+ already has multiple levels:

- high-level regime / strategy selection,
- signal and risk diagnostics,
- target-weight planning,
- execution guard and broker readiness.

Moira's strongest transferable idea is to separate failure attribution:

- Was the forecast/regime wrong?
- Was the strategy choice reasonable but execution timing bad?
- Was the risk guard correct but too late or too early?
- Was the result just market noise?

Recommended GroupA+ adaptation:

- Build a shadow `hierarchical_credit_review` report after each forecast-vs-actual
  comparison.
- Classify yesterday's miss into `selection_error`, `execution_error`,
  `risk_guard_error`, `data_freshness_error`, or `market_noise`.
- Do not feed target weights directly.

### 2. Textual Critic With Immutable / Mutable Policy Blocks

Useful and safe if governance-limited.

Moira's prompt-update design has a good control pattern:

- immutable contract: schema, allowed fields, forbidden actions,
- mutable policy: only small decision rules can change,
- critic proposes changes only using available inputs.

Recommended GroupA+ adaptation:

- Apply this to research-only rule proposals, not live strategy code.
- Use it to review daily forecast misses and propose candidate rule edits.
- Keep the output as `review_only_no_target_weight_change`.
- Require signed approval before any proposed rule becomes guarded candidate.

### 3. Event-Aware Entry And Anti-Overtrading Rules

Useful as execution-governance heuristics.

The trader prompt evolution introduces practical rules:

- avoid entering after a sharp move without fresh catalyst,
- wait for pullback or consolidation if already extended,
- avoid entering before major scheduled events if price already moved,
- avoid immediate re-entry in same direction without new catalyst,
- protect profits earlier after fast gains,
- reassess thesis after 3-5 days.

Recommended GroupA+ adaptation:

- Convert into a shadow execution-quality checklist.
- Especially relevant to `00631L` re-entry, `00632R` hedge opens, and defensive
  exits.
- Do not use as a direct order generator.

### 4. Semantic Relationship Selection And LETF Relative Exposure

Useful, but should not be copied as traditional market-neutral pair trading.

The paper's LLM selector found economically meaningful pairs beyond raw
correlation. For GroupA+, the closest analogue is not single-stock pair trading.
It is the relationship among:

- `0050.TW`: unlevered Taiwan 50 beta,
- `00631L.TW`: leveraged long Taiwan 50 beta,
- `00632R.TW`: inverse Taiwan 50 hedge,
- `00679B.TWO` / cash: defensive buffers.

Important distinction:

- `0050/00631L` is not a normal pair-trading spread. It is the same underlying
  exposure at different leverage and path-dependency.
- The useful concept is `relative exposure control`, not market-neutral
  statistical arbitrage.
- `00632R` is closer to a hedge leg, but long holding has decay/path risk and
  must remain event-driven and review-gated.

Recommended adaptation:

- Build a `relative_exposure_thesis_shadow` report.
- Evaluate whether current `0050/00631L/00632R/cash` posture is coherent with:
  - market trend,
  - realized volatility,
  - drawdown and rebound state,
  - tail-risk score,
  - signal alignment,
  - news / semantic catalysts,
  - execution guard freshness.
- Suggested output classes:
  - `leverage_expansion_thesis_supported`
  - `maintain_unlevered_beta_preferred`
  - `delever_to_cash_or_0050`
  - `short_term_inverse_hedge_review_only`
  - `thesis_conflicted_no_new_risk`
- Output thesis quality only, not orders.

Potential future guarded candidates, after validation:

- reduce `00631L` into `0050` or cash when leveraged exposure is extended and
  semantic/risk support is weak;
- allow limited `00631L` re-entry only when trend, volatility, and semantic
  thesis agree;
- allow `00632R` only as short-term hedge review, never as automatic long-hold
  allocation.

This is the place where Moira's selector idea is useful: it can help explain
whether the current relationship among ETF legs is economically coherent, not
select a new pair to trade.

### 5. Relationship Thesis For Existing Allocation

Useful as a broader diagnostic.

The current GroupA+ allocation already encodes a thesis. Moira suggests making
that thesis explicit:

- deciding whether `0050`, `00631L`, `00632R`, `00679B`, and cash buffers
  currently form a coherent allocation,
- detecting when a hedge/recovery/defensive thesis is semantically supported by
  news and market state.

Recommended adaptation:

- Build a `relationship_thesis_shadow` report.
- Inputs: current live signal, market state, news summaries, risk mechanism,
  signal alignment.
- Output: thesis quality only, not weights.

### 6. Context Compression

Useful operationally.

The paper notes that most LLM cost comes from contextual market information,
not prompt templates. GroupA+ already has many diagnostics and news artifacts,
so a compact daily context layer would help.

Recommended adaptation:

- Add a compact `daily_semantic_context_summary` artifact that other LLM-style
  reviewers can consume.
- Keep it deterministic where possible and source-linked.

## What Should Not Be Directly Imported

- Do not import Moira as traditional live pair trading.
- Do not let an LLM choose GroupA+ target weights.
- Do not use prompt updates to mutate production rules automatically.
- Do not introduce long/short single-stock pair positions into GroupA+.
- Do not treat `0050/00631L` as a normal cointegration spread.
- Do not cite the reported Moira performance as evidence for Taiwan ETF live
  allocation.

Reasons:

- The experiment universe is small and U.S.-stock-specific.
- The test period is short.
- Pair trading action space does not match GroupA+ ETF/cash allocation.
- `0050/00631L` is a leverage/path-dependency relation, not an independent
  market-neutral pair.
- LLM prompt policies can be brittle without strict governance.

## Recommended Integration Priority

1. `hierarchical_credit_review_shadow`
   - Highest value.
   - Explains why forecast-vs-actual misses happen.
   - No target-weight impact.

2. `relative_exposure_thesis_shadow`
   - Applies Moira's pair-selection insight to the existing
     `0050/00631L/00632R/cash` relationship.
   - Focuses on leverage expansion, deleveraging, and hedge thesis quality.
   - No target-weight impact until separately validated and signed.

3. `moira_style_policy_critic_shadow`
   - Takes recent review failures and proposes rule edits in a mutable-policy
     block.
   - Review-only.
   - Requires signed approval before any rule becomes a guarded candidate.

4. `event_aware_execution_quality_shadow`
   - Converts Moira's trader-rule evolution into a checklist for 00631L/00632R
     entries, exits, and re-entries.

5. `relationship_thesis_shadow`
   - Tests whether the current GroupA+ allocation thesis is semantically
     coherent.

## Implemented Shadow Prototype - 2026-08-07

Implemented `hierarchical_credit_review_shadow`,
`relative_exposure_thesis_shadow`, and
`event_aware_execution_quality_shadow`, plus
`moira_style_policy_critic_shadow` and
`moira_policy_critic_validation_shadow`,
`moira_execution_guard_hard_stop_backtest_shadow`, and
`daily_semantic_context_summary`, as review-only/context-only prototypes.

Added files:

- `group_a_plus/integrations/daily_semantic_context.py`
- `group_a_plus/integrations/event_aware_execution_quality.py`
- `group_a_plus/integrations/hierarchical_credit_review.py`
- `group_a_plus/integrations/moira_execution_guard_backtest.py`
- `group_a_plus/integrations/moira_policy_critic.py`
- `group_a_plus/integrations/moira_policy_critic_validation.py`
- `group_a_plus/integrations/relative_exposure_thesis.py`
- `scripts/evaluate/build_group_a_plus_daily_semantic_context_summary.py`
- `scripts/evaluate/build_group_a_plus_event_aware_execution_quality_shadow.py`
- `scripts/evaluate/build_group_a_plus_hierarchical_credit_review_shadow.py`
- `scripts/evaluate/build_group_a_plus_moira_policy_critic_shadow.py`
- `scripts/evaluate/build_group_a_plus_relative_exposure_thesis_shadow.py`
- `scripts/evaluate/backtest_group_a_plus_moira_execution_guard_hard_stop_shadow.py`
- `scripts/evaluate/validate_group_a_plus_moira_policy_critic_shadow.py`
- `tests/test_group_a_plus_daily_semantic_context.py`
- `tests/test_build_group_a_plus_daily_semantic_context_summary.py`
- `tests/test_group_a_plus_event_aware_execution_quality.py`
- `tests/test_build_group_a_plus_event_aware_execution_quality_shadow.py`
- `tests/test_group_a_plus_hierarchical_credit_review.py`
- `tests/test_build_group_a_plus_hierarchical_credit_review_shadow.py`
- `tests/test_group_a_plus_moira_policy_critic.py`
- `tests/test_build_group_a_plus_moira_policy_critic_shadow.py`
- `tests/test_group_a_plus_moira_execution_guard_backtest.py`
- `tests/test_backtest_group_a_plus_moira_execution_guard_hard_stop_shadow.py`
- `tests/test_group_a_plus_moira_policy_critic_validation.py`
- `tests/test_validate_group_a_plus_moira_policy_critic_shadow.py`
- `tests/test_group_a_plus_relative_exposure_thesis.py`
- `tests/test_build_group_a_plus_relative_exposure_thesis_shadow.py`

Updated pipeline wiring:

- `scripts/run/run_ncf_daily_pipeline.py`
- `tests/test_run_ncf_daily_pipeline.py`

Generated artifacts:

- `report/group_a_plus/latest/daily_semantic_context_summary.json`
- `report/group_a_plus/daily_semantic_context_summary/history/daily_semantic_context_summary_20260807.json`
- `results/daily_semantic_context_summary_log.jsonl`
- `report/group_a_plus/latest/event_aware_execution_quality_shadow.json`
- `report/group_a_plus/event_aware_execution_quality_shadow/history/event_aware_execution_quality_shadow_20260807.json`
- `results/event_aware_execution_quality_shadow_log.jsonl`
- `report/group_a_plus/latest/hierarchical_credit_review_shadow.json`
- `report/group_a_plus/hierarchical_credit_review_shadow/history/hierarchical_credit_review_shadow_20260807.json`
- `results/hierarchical_credit_review_shadow_log.jsonl`
- `report/group_a_plus/latest/moira_policy_critic_shadow.json`
- `report/group_a_plus/moira_policy_critic_shadow/history/moira_policy_critic_shadow_20260807.json`
- `results/moira_policy_critic_shadow_log.jsonl`
- `report/group_a_plus/latest/moira_policy_critic_validation_shadow.json`
- `report/group_a_plus/moira_policy_critic_validation_shadow/history/moira_policy_critic_validation_shadow_20260807.json`
- `results/moira_policy_critic_validation_shadow_log.jsonl`
- `report/group_a_plus/latest/moira_execution_guard_hard_stop_backtest_shadow.json`
- `report/group_a_plus/moira_execution_guard_hard_stop_backtest_shadow/history/moira_execution_guard_hard_stop_backtest_shadow_20260807.json`
- `report/group_a_plus/latest/relative_exposure_thesis_shadow.json`
- `report/group_a_plus/relative_exposure_thesis_shadow/history/relative_exposure_thesis_shadow_20260807.json`
- `results/relative_exposure_thesis_shadow_log.jsonl`

Hierarchical credit review command used:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_hierarchical_credit_review_shadow.py \
  --forecast report/group_a_plus/latest/live_signal_20260807_1m_latest_strategy_preview.json \
  --actual report/group_a_plus/latest/live_signal_20260810_1m_latest_strategy_preview.json \
  --as-of 2026-08-07 \
  --output report/group_a_plus/latest/hierarchical_credit_review_shadow.json \
  --history-dir report/group_a_plus/hierarchical_credit_review_shadow/history \
  --log results/hierarchical_credit_review_shadow_log.jsonl
```

Hierarchical credit review test command:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_hierarchical_credit_review.py \
  tests/test_build_group_a_plus_hierarchical_credit_review_shadow.py
```

Result:

- `6 passed`

Current hierarchical credit review result:

- `primary_attribution`: `data_freshness_error`
- `secondary_attributions`: `market_noise`, `execution_error`
- `confidence`: `0.90`
- evidence:
  - `stale_data_forecast=2_actual=2`
  - `execution_guard_not_satisfied`
  - `0050_move_small`
  - `target_return_small`
- realized proxy:
  - `0050.TW`: `-0.4817%`
  - forecast target return proxy: `-0.0656%`

Interpretation:

- This comparison does not show a strong strategy-selection failure.
- The miss/uncertainty is mainly attributed to stale input data and execution
  guard failure.
- The realized price movement was small enough that market noise remains a
  secondary attribution.
- The module is review-only and cannot change target weights.

Event-aware execution quality command used:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_event_aware_execution_quality_shadow.py \
  --live-signal report/group_a_plus/latest/live_signal_20260810_1m_latest_strategy_preview.json \
  --execution-plan report/group_a_plus/latest/execution_plan_20260807_1m_workbook_20260806_latest_strategy_preview.json \
  --relative-thesis report/group_a_plus/latest/relative_exposure_thesis_shadow.json \
  --as-of 2026-08-07 \
  --output report/group_a_plus/latest/event_aware_execution_quality_shadow.json \
  --history-dir report/group_a_plus/event_aware_execution_quality_shadow/history \
  --log results/event_aware_execution_quality_shadow_log.jsonl
```

Event-aware execution quality test command:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_event_aware_execution_quality.py \
  tests/test_build_group_a_plus_event_aware_execution_quality_shadow.py
```

Result:

- `6 passed`

Current event-aware execution quality result:

- `status`: `blocked_review_only`
- `quality_score`: `0.48`
- blockers:
  - `execution_guard_satisfied`
  - `source_fresh_enough`
- warnings:
  - `no_large_00632r_chase_without_staging`
  - `0050_reduction_not_aggressive_in_low_risk_bullish_state`

Interpretation:

- The module does not object to 00631L because no 00631L add is requested.
- The 00632R add is at least thesis-gated by
  `short_term_inverse_hedge_review_only`, but still flagged because the target
  hedge increase is large and not staged in the selected execution-plan
  artifact.
- Because execution guard is false and source freshness fails, the execution
  quality conclusion is blocked review-only.
- No live allocation, rebalance, `00631L` add, or new `00632R` open is allowed
  by this module.

Moira-style policy critic command used:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_moira_policy_critic_shadow.py \
  --credit report/group_a_plus/latest/hierarchical_credit_review_shadow.json \
  --execution report/group_a_plus/latest/event_aware_execution_quality_shadow.json \
  --thesis report/group_a_plus/latest/relative_exposure_thesis_shadow.json \
  --as-of 2026-08-07 \
  --output report/group_a_plus/latest/moira_policy_critic_shadow.json \
  --history-dir report/group_a_plus/moira_policy_critic_shadow/history \
  --log results/moira_policy_critic_shadow_log.jsonl
```

Moira-style policy critic test command:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_moira_policy_critic.py \
  tests/test_build_group_a_plus_moira_policy_critic_shadow.py
```

Result:

- `5 passed`

Current Moira-style policy critic result:

- `status`: `blocked_review_only`
- `proposal_count`: `5`
- blocker:
  - `execution_quality_below_0_50`
- proposal IDs:
  - `freshness_first_review_gate`
  - `execution_guard_hard_stop_for_new_risk`
  - `large_inverse_hedge_staging_review`
  - `low_risk_bullish_beta_reduction_cooldown`
  - `hedge_thesis_blocker_echo`

Interpretation:

- The critic converted the three shadow diagnostics into candidate rule text.
- Every proposal is `research_proposal_only` and `allowed_to_apply=false`.
- The immutable contract forbids code modification, target weight changes,
  order creation, or guarded-candidate promotion.
- Any future candidate requires backtest and signed approval.

Moira policy critic validation command used:

```bash
.venv/bin/python scripts/evaluate/validate_group_a_plus_moira_policy_critic_shadow.py \
  --signal-glob 'results/group_a_plus_live_signal_v2_2026*.json' \
  --plan-glob 'results/group_a_plus_execution_plan_v2_2026*.json' \
  --as-of 2026-08-07 \
  --min-trigger-count 5 \
  --output report/group_a_plus/latest/moira_policy_critic_validation_shadow.json \
  --history-dir report/group_a_plus/moira_policy_critic_validation_shadow/history \
  --log results/moira_policy_critic_validation_shadow_log.jsonl
```

Moira policy critic validation test command:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_moira_policy_critic_validation.py \
  tests/test_validate_group_a_plus_moira_policy_critic_shadow.py
```

Result:

- `5 passed`

Current Moira policy critic validation result:

- input coverage:
  - signal records: `20`
  - execution-plan records: `9`
  - date range: `2026-06-18` to `2026-08-05`
  - next-return pairs: `19`
- ready for shadow backtest:
  - `execution_guard_hard_stop_for_new_risk`
- needs more history:
  - `freshness_first_review_gate`
  - `large_inverse_hedge_staging_review`
  - `low_risk_bullish_beta_reduction_cooldown`
  - `hedge_thesis_blocker_echo`
- trigger ledger rows:
  - `freshness_first_review_gate`: `0`
  - `execution_guard_hard_stop_for_new_risk`: `7`
  - `large_inverse_hedge_staging_review`: `0`
  - `low_risk_bullish_beta_reduction_cooldown`: `0`
  - `hedge_thesis_blocker_echo`: `1`

Interpretation:

- Only the execution-guard proposal has enough artifact replay triggers
  (`7`) to justify a more formal shadow backtest.
- The other four proposals are still sample-starved in currently available
  artifacts; three currently have zero strict ledger rows and the hedge-blocker
  echo has only one.
- The validation artifact now includes `trigger_ledger`, preserving the
  per-trigger date, reason, next `0050.TW` reference return, guard state,
  freshness, and relevant target/current weights for future replay.
- This validation remains replay-only and cannot change code, target weights,
  orders, or guarded-candidate status.

Moira execution-guard hard-stop formal shadow backtest command used:

```bash
.venv/bin/python scripts/evaluate/backtest_group_a_plus_moira_execution_guard_hard_stop_shadow.py \
  --signal-glob 'results/group_a_plus_live_signal_v2_2026*.json' \
  --as-of 2026-08-07 \
  --min-trigger-count 5 \
  --output report/group_a_plus/latest/moira_execution_guard_hard_stop_backtest_shadow.json \
  --history-dir report/group_a_plus/moira_execution_guard_hard_stop_backtest_shadow/history
```

Moira execution-guard hard-stop backtest test command:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_moira_execution_guard_backtest.py \
  tests/test_backtest_group_a_plus_moira_execution_guard_hard_stop_shadow.py \
  tests/test_run_ncf_daily_pipeline.py
```

Result:

- `26 passed`

Current Moira execution-guard hard-stop backtest result:

- schema version: `2`
- input coverage:
  - signal records: `20`
  - return rows: `19`
  - general trigger count: `6`
  - strict trigger count: `4`
  - date range: `2026-06-18` to `2026-08-05`
  - minimum trigger count: `5`
- trigger taxonomy:
  - general trigger: `execution_allowed is false`
  - strict actionable trigger:
    `execution_allowed is false and target adds 00631L.TW or 00632R.TW above previous target`
- raw metrics:
  - total return proxy: `-5.643972%`
  - max drawdown proxy: `-7.454722%`
  - positive rate: `42.105263%`
- guarded metrics:
  - total return proxy: `-5.587054%`
  - max drawdown proxy: `-7.398590%`
  - positive rate: `42.105263%`
- trigger delta metrics:
  - trigger mean delta: `+0.014872%`
  - positive trigger delta rate: `50.000000%`
  - trigger total delta: `+0.059495%`
- promotion checklist:
  - manual review minimum strict triggers: `20`
  - guarded candidate minimum strict triggers: `40`
  - required positive trigger delta rate: `55%`
  - `mean_trigger_delta_positive`: `true`
  - `positive_trigger_delta_rate_ge_55pct`: `false`
  - `max_drawdown_not_worse`: `true`
  - `signed_approval_present`: `false`
  - `manual_review_allowed`: `false`
  - `guarded_candidate_allowed`: `false`
- recommendation: `needs_more_trigger_history`
- ready for manual review: `false`
- promotion checklist manual review allowed: `false`
- promotion checklist guarded candidate allowed: `false`
- promote to live: `false`
- target weight change allowed: `false`
- guarded candidate allowed: `false`

Interpretation:

- The validation stage counted `7` execution-guard-false days. The formal
  backtest can evaluate `6` of them with next-return data, and the stricter
  actionable definition only counts days where guard was false and the raw
  target actually increased new `00631L.TW` or `00632R.TW` risk versus the
  previous target. That leaves only `4` strict triggers.
- The current replay result is mildly positive for the hard-stop idea, but the
  sample is below the `5`-trigger minimum, far below the `20`-trigger manual
  review threshold, and the positive trigger rate is only `50%`.
- This is not enough for manual promotion, guarded-candidate review, code
  mutation, target-weight changes, or orders.
- Continue accumulating daily artifacts; re-run after at least one more strict
  trigger, preferably many more.

Daily semantic context summary command used:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_daily_semantic_context_summary.py \
  --live-signal report/group_a_plus/latest/live_signal_20260810_1m_latest_strategy_preview.json \
  --signal-alignment report/group_a_plus/latest/signal_alignment.json \
  --risk-mechanism report/group_a_plus/latest/risk_mechanism.json \
  --watchlist-news report/group_a_plus/latest/watchlist_news.json \
  --credit report/group_a_plus/latest/hierarchical_credit_review_shadow.json \
  --execution report/group_a_plus/latest/event_aware_execution_quality_shadow.json \
  --thesis report/group_a_plus/latest/relative_exposure_thesis_shadow.json \
  --critic report/group_a_plus/latest/moira_policy_critic_shadow.json \
  --as-of 2026-08-07 \
  --output report/group_a_plus/latest/daily_semantic_context_summary.json \
  --history-dir report/group_a_plus/daily_semantic_context_summary/history \
  --log results/daily_semantic_context_summary_log.jsonl
```

Daily semantic context summary test command:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_daily_semantic_context.py \
  tests/test_build_group_a_plus_daily_semantic_context_summary.py
```

Result:

- `4 passed`

Current daily semantic context result:

- `market_state`: `choppy_range_low_risk`
- `signal_alignment`: `bullish_alignment`
- `dominant_direction`: `bullish`
- `risk_mechanism`: `FAST_CRASH`
- `news_article_count`: `0`
- `policy_critic_proposal_count`: `5`
- hard blockers:
  - `execution_guard_false`
  - `source_stale_ge_2_business_days`
  - `execution_quality_below_0_50`
  - `execution_guard_satisfied`
  - `source_fresh_enough`

Interpretation:

- This artifact compresses the daily context for downstream reviewers.
- It confirms the same governance conclusion: resolve freshness and execution
  guard before any live execution discussion.
- It is context-only and cannot create orders, target weights, or promotion.

Daily pipeline integration:

- Added best-effort steps:
  - `moira_relative_exposure_thesis_shadow`
  - `moira_hierarchical_credit_review_shadow`
  - `moira_event_aware_execution_quality_shadow`
  - `moira_policy_critic_shadow`
  - `moira_policy_critic_validation_shadow`
  - `moira_execution_guard_hard_stop_backtest_shadow`
  - `daily_semantic_context_summary`
- Placement:
  - after `daily_status_final`
  - before `final_governance_snapshot`
- Governance:
- all seven steps are in `BEST_EFFORT_STEP_NAMES`
  - failures do not block daily status, promotion gate, or final governance
  - no protected Golden1_0531 release artifacts are written
  - no target weights, orders, code mutations, or guarded candidates are
    produced

Pipeline validation commands:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_moira_execution_guard_backtest.py \
  tests/test_backtest_group_a_plus_moira_execution_guard_hard_stop_shadow.py \
  tests/test_run_ncf_daily_pipeline.py
```

Result:

- `25 passed`

Dry-run command:

```bash
.venv/bin/python scripts/run/run_ncf_daily_pipeline.py \
  --date-stamp 20260807 \
  --skip-refresh \
  --dry-run
```

Result:

- dry-run completed
- command count increased to `96`
- Moira steps appear as steps `88`-`94`

Note:

- The automated daily pipeline uses the same daily live signal for both
  `--forecast` and `--actual` in `moira_hierarchical_credit_review_shadow`,
  so it functions as a same-day governance/context check.
- For a true yesterday-forecast vs today-actual attribution, run
  `build_group_a_plus_hierarchical_credit_review_shadow.py` manually with
  explicit `--forecast` and `--actual` artifact paths.

Relative exposure thesis command used:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_relative_exposure_thesis_shadow.py \
  --live-signal report/group_a_plus/latest/live_signal_20260810_1m_latest_strategy_preview.json \
  --as-of 2026-08-07 \
  --output report/group_a_plus/latest/relative_exposure_thesis_shadow.json \
  --history-dir report/group_a_plus/relative_exposure_thesis_shadow/history \
  --log results/relative_exposure_thesis_shadow_log.jsonl
```

Relative exposure thesis test command:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_relative_exposure_thesis.py \
  tests/test_build_group_a_plus_relative_exposure_thesis_shadow.py
```

Result:

- `7 passed`

Current 2026-08-07 shadow result from the 2026-08-10 preview signal:

- `thesis_class`: `short_term_inverse_hedge_review_only`
- `thesis_quality_score`: `0.55`
- reason codes:
  - `current_00632r_weight_present`
  - `cash_buffer_material`
  - `market_state=choppy_range_low_risk`
- supporting evidence:
  - bullish signal alignment,
  - low total/tail risk,
  - positive 5-day momentum,
  - price above moving average.
- blocking evidence:
  - `execution_guard_not_satisfied`
  - `business_stale_days=2`

Interpretation:

- The current preview already contains a material `00632R.TW` inverse hedge
  allocation, so the prototype classifies it as a short-term hedge thesis.
- Because execution guard is not satisfied and the source signal uses
  `actual_data_date=2026-08-06` for `requested_as_of_date=2026-08-10`, the
  module keeps the conclusion review-only.
- No live allocation, rebalance, `00631L` add, or new `00632R` open is allowed
  by this module.

Governance status:

- `policy`: `shadow_only_no_target_weight_change`
- `target_weight_change_allowed`: `false`
- `auto_rebalance_allowed`: `false`
- `allow_00631l_add`: `false`
- `allow_00632r_open`: `false`
- `requires_backtest_before_guarded_candidate`: `true`

## Current Decision

- `promotion_decision`: `research_shadow_candidate`
- `target_weight_change_allowed`: `false`
- `auto_rebalance_allowed`: `false`
- `allow_00631l_add`: `false`
- `allow_00632r_open`: `false`

## Bottom Line

The paper has useful ideas, but the useful part is governance, diagnosis, and
relative exposure thesis review, not direct live pair-trading.

Remaining Moira-derived work:

- continue the formal shadow backtest for
  `execution_guard_hard_stop_for_new_risk`; first pass produced only `4`
  strict triggers against a `5`-trigger minimum, so it is not ready for
  manual/guarded-candidate review;
- continue accumulating daily artifact replay samples for the other four
  critic proposals;
- keep all outputs review-only until validated across enough history and signed
  approval exists for any guarded candidate.
