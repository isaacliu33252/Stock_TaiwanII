# Group A+ review: 2507.18560 HARLF

## Source

- File: `C:/Users/isaac/Downloads/2507.18560.pdf`
- Title: `HARLF: Hierarchical Reinforcement Learning and Lightweight LLM-Driven Sentiment Integration for Financial Portfolio Optimization`
- arXiv: `2507.18560v1`
- Date in PDF: 2025-07-24
- Authors: Benjamin Coriat, Eric Benhamou

## Paper Takeaway

The paper proposes a three-tier architecture:

- base RL agents process either market metrics or FinBERT-style sentiment;
- meta-agents aggregate base-agent decisions by modality;
- a super-agent combines market and sentiment meta-agents into final portfolio
  weights.

Reported result: 2018-2024 test period, super-agent annualized ROI 26% and
Sharpe 1.2, outperforming equal-weight and S&P 500 in the paper's global
multi-asset universe.

Important limitations explicitly noted by the paper:

- transaction costs are excluded;
- real-world asynchronous data is not handled;
- stress/adversarial testing is missing;
- sentiment source noise can bias decisions.

## Fit With Group A+

Group A+ already has several related building blocks:

- `market_aligned_sentiment_shadow`;
- FinBERT/LLM sentiment CSV files under `FinRL/data/sentiment`;
- LLM state/reward governance artifacts;
- specialist/router style shadow modules.

The paper's useful idea is therefore not a new live allocator. The useful import
is a readiness checklist for cross-modal hierarchy:

- market-only branch;
- sentiment-only branch;
- hierarchical aggregation;
- super-agent ablation versus equal-weight and latest strategy;
- transaction-cost and stress testing before promotion.

## Imported

Implemented a research-only HARLF readiness review:

- `scripts/evaluate/build_group_a_plus_harlf_readiness_review.py`
- `tests/test_build_group_a_plus_harlf_readiness_review.py`
- `report/group_a_plus/latest/harlf_readiness_review.json`
- `report/group_a_plus/harlf_readiness/history/harlf_readiness_20260808.json`

Current report status: `blocked`.

Initial blocking reasons:

- `llm_state_reward_interface_blocked`;
- `missing_monthly_asset_level_sentiment_panel`;
- `missing_market_only_base_agent_oos_backtest`;
- `missing_sentiment_only_base_agent_oos_backtest`;
- `missing_hierarchical_meta_agent_oos_backtest`;
- `missing_super_agent_ablation_against_equal_weight_and_latest_strategy`;
- `missing_transaction_cost_and_stress_test_for_harlf`.

## 2026-08-08 Continuation

Added the first missing input artifact:

- `scripts/evaluate/build_group_a_plus_monthly_asset_sentiment_panel.py`
- `tests/test_build_group_a_plus_monthly_asset_sentiment_panel.py`
- `FinRL/data/sentiment/monthly_asset_sentiment_panel.csv`
- `report/group_a_plus/latest/monthly_asset_sentiment_panel_coverage.json`
- `report/group_a_plus/monthly_asset_sentiment_panel_coverage/history/`

The panel uses existing FinMind JSONL news and the deterministic FinBERT proxy
already used by `market_aligned_sentiment_shadow`. It does not query any LLM at
test time and has no trading effect.

Coverage:

- rows: 57 monthly ticker rows;
- raw records: 15,993;
- deduped records: 14,467;
- months: 2025-01 through 2026-08;
- tickers covered: `0050`, `00631L`, `00632R`, `00679B`, `2330`.

After regenerating `harlf_readiness_review.json`,
`missing_monthly_asset_level_sentiment_panel` is no longer a blocker.

Remaining blockers:

- `llm_state_reward_interface_blocked`;
- `missing_market_only_base_agent_oos_backtest`;
- `missing_sentiment_only_base_agent_oos_backtest`;
- `missing_hierarchical_meta_agent_oos_backtest`;
- `missing_super_agent_ablation_against_equal_weight_and_latest_strategy`;
- `missing_transaction_cost_and_stress_test_for_harlf`.

## 2026-08-08 Branch Ablation

Added the HARLF-style branch ablation shadow test:

- `scripts/evaluate/evaluate_group_a_plus_harlf_branch_ablation_shadow.py`
- `tests/test_evaluate_group_a_plus_harlf_branch_ablation_shadow.py`
- `report/group_a_plus/latest/harlf_branch_ablation_shadow.json`
- `report/group_a_plus/harlf_branch_ablation_shadow/history/`

This is not a live RL super-agent. It is a lightweight monthly OOS shadow check
using existing Group A+ data:

- market-only branch: trailing monthly return and volatility cross-section;
- sentiment-only branch: monthly asset sentiment score adjusted by news
  intensity;
- combined branch: 50/50 market and sentiment score;
- benchmark branch: equal weight;
- transaction cost approximation included in net returns.

Window and universe:

- evaluation window: 2025-01 through 2026-07;
- tickers: `0050`, `00631L`, `00632R`, `00679B`, `2330`;
- evaluated months: 19.

Net ranking from the shadow report:

| Rank | Branch | Net total return | Net Sharpe | Max drawdown | Beat equal weight |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | `sentiment_only` | 100.99% | 1.67 | -8.50% | yes |
| 2 | `combined` | 88.50% | 1.57 | -11.04% | yes |
| 3 | `market_only` | 69.72% | 1.40 | -13.07% | yes |
| 4 | `equal_weight` | 52.28% | 1.50 | -9.69% | no |

After regenerating `harlf_readiness_review.json`, these are no longer blockers:

- `missing_market_only_base_agent_oos_backtest`;
- `missing_sentiment_only_base_agent_oos_backtest`;
- `missing_super_agent_ablation_against_equal_weight_and_latest_strategy`.

Remaining blockers:

- `llm_state_reward_interface_blocked`;
- `missing_hierarchical_meta_agent_oos_backtest`;
- `missing_transaction_cost_and_stress_test_for_harlf`.

Interpretation:

- HARLF's market/sentiment branch separation is useful and now measurable in
  Group A+ shadow reports.
- The strongest branch in this short sample is `sentiment_only`, but 19 monthly
  observations are not enough to promote live allocation changes.
- `combined` beating equal weight supports keeping the cross-modal idea in the
  research queue.
- No `golden1_0531` or latest strategy live weights should change from this
  paper yet.

## 2026-08-08 Meta-Agent Shadow

Added the HARLF-style hierarchical meta-agent shadow router:

- `scripts/evaluate/evaluate_group_a_plus_harlf_meta_agent_shadow.py`
- `tests/test_evaluate_group_a_plus_harlf_meta_agent_shadow.py`
- `report/group_a_plus/latest/harlf_meta_agent_shadow.json`
- `report/group_a_plus/harlf_meta_agent_shadow/history/`

Method:

- uses only the completed branch ablation monthly net returns;
- warmup: 6 months;
- lookback: 6 months;
- each month selects one of `market_only`, `sentiment_only`, or `combined`;
- score uses trailing Sharpe adjusted by drawdown;
- no order creation and no `golden01_0531` changes.

Result:

- evaluated routed months: 13;
- net total return: 105.85%;
- annualized Sharpe: 2.21;
- max drawdown: -8.50%;
- beats equal-weight total return: yes;
- beats static combined total return: yes;
- candidate ready for stress test: yes;
- promotion ready: no.

After regenerating `harlf_readiness_review.json`,
`missing_hierarchical_meta_agent_oos_backtest` is no longer a blocker.

Remaining blockers after meta-agent:

- `llm_state_reward_interface_blocked`;
- `missing_transaction_cost_and_stress_test_for_harlf`.

Because the user confirmed `golden01_0531` is fixed, this router can only be
considered for the editable latest-strategy candidate after stress validation.

## 2026-08-08 Stress And Guard Sweep

Added HARLF stress testing:

- `scripts/evaluate/evaluate_group_a_plus_harlf_stress_shadow.py`
- `tests/test_evaluate_group_a_plus_harlf_stress_shadow.py`
- `report/group_a_plus/latest/harlf_stress_shadow.json`
- `report/group_a_plus/harlf_stress_shadow/history/`

Original meta-agent stress result:

- 3x transaction-cost stress still beats equal weight;
- sentiment dropout to `combined` stays positive;
- weak equal-weight months fail: meta-agent loses more than equal weight;
- latest-strategy comparison ready: no.

Added defensive equal-weight fallback support and parameter sweep:

- `scripts/evaluate/sweep_group_a_plus_harlf_defensive_meta_agent_params.py`
- `tests/test_sweep_group_a_plus_harlf_defensive_meta_agent_params.py`
- `report/group_a_plus/latest/harlf_defensive_meta_agent_shadow.json`
- `report/group_a_plus/latest/harlf_defensive_meta_agent_param_sweep.json`
- `report/group_a_plus/harlf_defensive_meta_agent_param_sweep/history/`

Sweep thresholds: `2.0`, `2.5`, `3.0`, `3.5`, `4.0`, `4.5`, `5.0`.

Conclusion from sweep:

- threshold `2.0` protects weak months but no longer beats static `combined`;
- thresholds `2.5` and above beat static `combined` but fail weak-market stress;
- no threshold is ready for latest-strategy comparison.

After regenerating `harlf_readiness_review.json`, the stress blocker is now:

- `harlf_stress_test_not_ready_for_latest_strategy_comparison`.

The old missing-evidence blocker is resolved:

- `missing_transaction_cost_and_stress_test_for_harlf`.

## 2026-08-08 Compound Weak-Market Gate

Added a stronger HARLF defensive candidate using only information available at
the routing month:

- overheat fallback: if selected branch is `sentiment_only` and sentiment score
  is at least `4.0`, route to `equal_weight`;
- soft weak-market fallback: if selected branch is `sentiment_only`, sentiment
  score is at least `2.0`, and prior-month equal-weight return is at most
  `2.0%`, route to `equal_weight`.

Generated:

- `report/group_a_plus/latest/harlf_compound_defensive_meta_agent_shadow.json`
- `report/group_a_plus/latest/harlf_compound_defensive_stress_shadow.json`
- `report/group_a_plus/harlf_compound_defensive_meta_agent_shadow/history/`
- `report/group_a_plus/harlf_compound_defensive_stress_shadow/history/`

Compound defensive meta-agent result:

- evaluated months: 13;
- net total return: 118.76%;
- annualized Sharpe: 2.51;
- max drawdown: -6.64%;
- selected branch counts: `market_only` 4, `sentiment_only` 5,
  `equal_weight` 4;
- beats equal weight: yes;
- beats static combined: yes.

Compound defensive stress result:

- 3x transaction-cost stress beats equal weight: yes;
- sentiment dropout to `combined` positive: yes;
- weak-market months not worse than equal weight: yes;
- latest-strategy comparison ready: yes;
- promotion ready: no.

Interpretation:

- HARLF now has a research-only candidate that is strong enough for comparison
  against the editable latest strategy.
- This still does not change `golden01_0531`.
- This still does not directly modify latest strategy; comparison is the next
  required gate.

## 2026-08-08 Latest Strategy Comparison

Added comparison against the editable latest strategy and fixed
`golden01_0531` benchmark:

- `scripts/evaluate/compare_group_a_plus_harlf_compound_vs_latest_strategy.py`
- `tests/test_compare_group_a_plus_harlf_compound_vs_latest_strategy.py`
- `report/group_a_plus/latest/harlf_compound_vs_latest_strategy_comparison.json`
- `report/group_a_plus/harlf_compound_vs_latest_strategy_comparison/history/`

Alignment method:

- HARLF row `month=YYYY-MM` is treated as a signal at that month end;
- latest/golden daily backtests are converted to next-month outcomes from
  month-end to following month-end;
- this is a research comparison only.

Comparison over 13 aligned monthly outcomes:

| Strategy | Total return | Sharpe | Max drawdown |
| --- | ---: | ---: | ---: |
| HARLF compound defensive | 118.76% | 2.51 | -6.64% |
| latest strategy | 18.23% | 1.52 | -3.70% |
| `golden01_0531` fixed benchmark | 18.23% | 1.52 | -3.70% |

Decision:

- beats latest total return: yes;
- beats `golden01_0531` total return: yes;
- not worse than latest max drawdown: no;
- candidate ready for latest strategy review: no;
- promotion ready: no.

Interpretation:

- HARLF compound is return-dominant but still takes too much drawdown relative
  to the latest/golden benchmark.
- Do not import it into latest strategy yet.
- Next required work is a drawdown cap or blend that keeps the return edge
  without exceeding latest/golden max drawdown.

## 2026-08-08 HARLF/Latest Blend Sweep

Added a blend sweep:

- `scripts/evaluate/sweep_group_a_plus_harlf_latest_blend.py`
- `tests/test_sweep_group_a_plus_harlf_latest_blend.py`
- `report/group_a_plus/latest/harlf_latest_blend_sweep.json`
- `report/group_a_plus/harlf_latest_blend_sweep/history/`

Method:

- blend monthly returns from `harlf_compound` and latest strategy;
- sweep HARLF sleeve from 0% to 100% in 1% steps;
- require total return above latest;
- require max drawdown not worse than latest/`golden01_0531`.

Best viable blend:

- HARLF sleeve: 8%;
- latest sleeve: 92%;
- total return: 24.54%;
- annualized Sharpe: 1.75;
- max drawdown: -3.70%;
- beats latest total return: yes;
- not worse than latest/golden drawdown: yes;
- promotion ready: no.

Interpretation:

- Standalone HARLF is too aggressive.
- A small HARLF sleeve is now ready for latest-strategy review.
- This still does not modify latest strategy and does not modify
  `golden01_0531`.

## 2026-08-08 Trade-Level OOS Validation

Added a trade-level readiness gate for the 8% HARLF / 92% latest blend:

- `scripts/evaluate/validate_group_a_plus_harlf_latest_blend_trade_oos.py`
- `tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py`
- `report/group_a_plus/latest/harlf_latest_blend_trade_oos_validation.json`
- `report/group_a_plus/harlf_latest_blend_trade_oos_validation/history/`

Validation result: `blocked`.

Blocking reasons:

- `harlf_uses_assets_outside_group_a_plus_tradable_universe`;
- `missing_latest_strategy_historical_target_weight_series`;
- `missing_trade_level_execution_cost_replay_for_blend`;
- `missing_oos_window_beyond_blend_selection_window`.

Tradability finding:

- Group A+ tradable universe: `0050`, `00631L`, `00632R`, `00679B`, `cash`;
- HARLF branch weights used: `0050`, `00631L`, `00632R`, `00679B`, `2330`;
- non-tradable for current Group A+ implementation: `2330`.

Turnover finding:

- selected HARLF branch weight months: 13;
- mean branch turnover: 37.82%;
- max branch turnover: 87.00%.

Interpretation:

- The 8% HARLF / 92% latest blend remains a research candidate only.
- It cannot be promoted until `2330` is mapped/removed, latest-strategy
  historical target weights are exported, and the blend is replayed with real
  execution costs, lot rounding, turnover caps, and an OOS window not used to
  choose the 8% weight.
- No `golden01_0531` or latest strategy weights were changed.

## 2026-08-08 ETF-Only Mapping

Added an ETF-only mapping shadow to compare two ways to remove `2330` from
HARLF branch weights:

- `scripts/evaluate/evaluate_group_a_plus_harlf_etf_mapped_shadow.py`
- `tests/test_evaluate_group_a_plus_harlf_etf_mapped_shadow.py`
- `report/group_a_plus/latest/harlf_etf_mapped_shadow.json`
- `report/group_a_plus/harlf_etf_mapped_shadow/history/`

Mapping modes:

- `drop_2330_renormalize`: remove `2330` and renormalize the remaining ETF
  weights;
- `map_2330_to_0050`: add `2330` weight into `0050`.

Result on the same 13 meta-agent routed months:

| Mapping | Total return | Sharpe | Max drawdown | Non-ETF assets |
| --- | ---: | ---: | ---: | --- |
| `drop_2330_renormalize` | 118.09% | 2.56 | -5.42% | none |
| `map_2330_to_0050` | 118.07% | 2.48 | -6.51% | none |

Decision:

- best mapping for next shadow step: `drop_2330_renormalize`;
- creates orders: no;
- changes `golden01_0531`: no;
- changes latest strategy: no;
- promotion ready: no.

Re-ran trade-level validation with `drop_2330_renormalize`:

- `report/group_a_plus/latest/harlf_latest_blend_trade_oos_validation_etf_mapped.json`
- status: `blocked`;
- removed blocker:
  `harlf_uses_assets_outside_group_a_plus_tradable_universe`;
- remaining blockers:
  `missing_latest_strategy_historical_target_weight_series`,
  `missing_trade_level_execution_cost_replay_for_blend`,
  `missing_oos_window_beyond_blend_selection_window`.

## 2026-08-08 Latest Target Weight Export

Added a research-only latest-strategy target weight exporter:

- `scripts/evaluate/export_group_a_plus_latest_strategy_target_weights.py`
- `tests/test_export_group_a_plus_latest_strategy_target_weights.py`
- `report/group_a_plus/latest/latest_strategy_historical_target_weights.json`
- `report/group_a_plus/latest/latest_strategy_historical_target_weights.csv`
- `report/group_a_plus/latest_strategy_historical_target_weights/history/`

Method:

- run the active latest strategy runner;
- read daily `execution_regime` from the returned frame;
- read regime weight maps from the runner report;
- expand them into daily target weights for `0050`, `00631L`, `00632R`,
  `00679B`, and `cash`;
- no orders and no strategy changes.

Export result:

- status: `available`;
- rows: 266;
- window: 2025-07-01 through 2026-08-07;
- historical target weight series available: yes;
- changes `golden01_0531`: no;
- changes latest strategy: no.

Re-ran ETF-mapped trade-level validation with this latest target-weight series:

- removed blocker:
  `missing_latest_strategy_historical_target_weight_series`;
- remaining blockers:
  `missing_trade_level_execution_cost_replay_for_blend`,
  `missing_oos_window_beyond_blend_selection_window`.

## 2026-08-08 Trade-Level Replay

Added a trade-level replay for the 8% HARLF / 92% latest blend:

- `scripts/evaluate/replay_group_a_plus_harlf_latest_blend_trades.py`
- `tests/test_replay_group_a_plus_harlf_latest_blend_trades.py`
- `report/group_a_plus/latest/harlf_latest_blend_trade_replay.json`
- `report/group_a_plus/harlf_latest_blend_trade_replay/history/`

Replay method:

- mapping mode: `drop_2330_renormalize`;
- HARLF sleeve: 8%;
- latest sleeve: 92%;
- rebalance on the first trading day of each HARLF outcome month;
- use latest target weights from the exported daily series;
- round shares down by lot size;
- apply commission, slippage, and equity ETF sell tax;
- cap rebalance turnover at 50%;
- no orders and no strategy changes.

Replay result:

- status: `available`;
- window: 2025-08-01 through 2026-08-07;
- daily rows: 248;
- rebalance count: 13;
- total return: 11.40%;
- annualized Sharpe: 3.13;
- max drawdown: -1.23%;
- total transaction cost: 3,400.39;
- total traded value: 1,541,894.62;
- max observed turnover ratio: 49.99%;
- turnover cap binding count: 1.

Re-ran ETF-mapped trade-level validation with the replay report:

- removed blocker:
  `missing_trade_level_execution_cost_replay_for_blend`;
- remaining blocker:
  `missing_oos_window_beyond_blend_selection_window`.

## 2026-08-08 Temporal OOS Validation

Added temporal OOS validation for the HARLF/latest blend:

- `scripts/evaluate/validate_group_a_plus_harlf_blend_temporal_oos.py`
- `tests/test_validate_group_a_plus_harlf_blend_temporal_oos.py`
- `report/group_a_plus/latest/harlf_blend_temporal_oos_validation.json`
- `report/group_a_plus/harlf_blend_temporal_oos_validation/history/`

Method:

- split the 13 aligned monthly outcomes into training and holdout;
- default holdout: last 3 signal months, `2026-05`, `2026-06`, `2026-07`;
- rerun HARLF/latest sleeve selection only on the earlier training segment;
- require the selected sleeve to beat latest total return without worsening
  latest/golden max drawdown;
- then evaluate only on the holdout months.

Result:

- status: `blocked`;
- OOS window available: yes;
- train best viable blend: none;
- blocking reason:
  `no_train_viable_harlf_blend_under_drawdown_constraint`;
- temporal OOS passed: no;
- creates orders: no;
- changes `golden01_0531`: no;
- changes latest strategy: no.

Re-ran ETF-mapped trade-level validation with temporal OOS:

- removed blocker:
  `missing_oos_window_beyond_blend_selection_window`;
- new blocker:
  `harlf_temporal_oos_validation_not_passed`.

Interpretation:

- The 8% HARLF sleeve was not stable under temporal OOS selection.
- It should not be imported into the editable latest strategy.
- The useful imported value from HARLF remains the research infrastructure:
  asset sentiment panel, branch ablation, meta-agent/stress gates, ETF mapping,
  target-weight export, trade replay, and OOS rejection logic.

## 2026-08-08 OOS Failure Diagnosis

Added a diagnosis report for the failed temporal OOS gate:

- `scripts/evaluate/diagnose_group_a_plus_harlf_oos_failure.py`
- `tests/test_diagnose_group_a_plus_harlf_oos_failure.py`
- `report/group_a_plus/latest/harlf_oos_failure_diagnosis.json`
- `report/group_a_plus/harlf_oos_failure_diagnosis/history/`

Diagnosis:

- primary failure:
  `positive_harlf_sleeve_improves_return_but_immediately_worsens_drawdown_gate`;
- drawdown-gate blocker months: `2025-10`, `2026-02`;
- minimum positive HARLF sleeve tested: 1%;
- minimum positive HARLF sleeve passing drawdown gate: none;
- 1% HARLF sleeve improves train total return but worsens max drawdown from
  -3.4238% to -3.4559%;
- 8% HARLF sleeve improves train total return but worsens max drawdown to
  -3.6809%.

Branch metrics on the train window after ETF mapping:

| Branch | Total return | Sharpe | Max drawdown |
| --- | ---: | ---: | ---: |
| `sentiment_only` | 104.62% | 2.97 | -8.23% |
| `combined` | 88.12% | 2.60 | -10.97% |
| `market_only` | 55.33% | 1.76 | -16.87% |
| `equal_weight` | 46.89% | 2.86 | -5.42% |

Implication for latest strategy:

- fixed HARLF sleeve recommended: no;
- current 8% HARLF sleeve rejected: yes;
- `golden01_0531` remains fixed benchmark only;
- latest strategy should not import HARLF weights from this paper;
- if continued, only a future conditional HARLF sleeve candidate is worth
  researching, and it must pass train-only drawdown gating before any temporal
  OOS/trade replay promotion attempt.

## 2026-08-08 Conditional Sleeve Shadow

Added a latest-strategy-only conditional HARLF sleeve shadow:

- `scripts/evaluate/evaluate_group_a_plus_harlf_conditional_sleeve_shadow.py`
- `tests/test_evaluate_group_a_plus_harlf_conditional_sleeve_shadow.py`
- `report/group_a_plus/latest/harlf_conditional_sleeve_shadow.json`
- `report/group_a_plus/harlf_conditional_sleeve_shadow/history/`

Method:

- `golden01_0531` remains fixed benchmark only;
- latest strategy is not changed;
- after warmup, each month uses only prior months to search for a HARLF sleeve;
- positive HARLF sleeve is allowed only if it improves train total return
  without worsening latest/golden max drawdown;
- otherwise HARLF sleeve is set to 0%.

Result:

- status: `available`;
- nonzero HARLF months: 0;
- conditional sleeve total return: 18.23%;
- latest strategy total return: 18.23%;
- conditional sleeve max drawdown: -3.70%;
- latest strategy max drawdown: -3.70%;
- candidate ready for latest-strategy review: no.

Interpretation:

- The strict train-only drawdown gate disables HARLF for all evaluated months.
- That is the correct risk behavior, but it adds no edge over latest strategy.
- HARLF weights from this paper should be closed as not importable into latest
  strategy.

## Not Imported

Do not import:

- Stable-Baselines3 live allocator;
- HARLF super-agent live weights;
- Google News scraping as live dependency;
- paper ROI 26% as Group A+ evidence;
- monthly rebalance live override.

The paper uses global indices/commodities, monthly rebalancing, no transaction
costs, and a different benchmark universe. That is not enough evidence for
Taiwan ETF live allocation.

## Recommendation

Keep this as a readiness review only.

Next useful shadow step:

1. Use `drop_2330_renormalize` as the ETF-only HARLF mapping candidate.
2. Keep `golden01_0531` fixed as benchmark only.
3. Do not promote the current 8% HARLF sleeve because temporal OOS failed.
4. Conditional HARLF sleeve was tested and added no edge; close HARLF weight
   import as rejected unless a materially different signal is proposed later.

`golden1_0531` and latest strategy weights remain unchanged.
