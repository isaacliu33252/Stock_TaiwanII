# Group A+ handoff: paper 2507.18560 HARLF

## Scope

- Paper: `HARLF: Hierarchical Reinforcement Learning and Lightweight LLM-Driven Sentiment Integration for Financial Portfolio Optimization`
- Source file: `C:/Users/isaac/Downloads/2507.18560.pdf`
- arXiv: `2507.18560v1`
- PDF date: 2025-07-24
- Group A+ policy: research-only; no live weight change; keep `golden1_0531`
  unchanged.

## Paper Ideas Checked

Useful concepts:

- separate market-metric branch and sentiment branch;
- evaluate market-only, sentiment-only, and combined branches separately;
- hierarchical/meta aggregation only after branch evidence exists;
- use lightweight financial sentiment before any large LLM trading loop;
- require transaction-cost and stress testing before promotion.

Not suitable for direct import:

- live HARLF super-agent allocator;
- Stable-Baselines3 agent as production allocator;
- paper ROI/Sharpe as Group A+ evidence;
- Google News scraping as live dependency;
- monthly rebalance override.

Reason: the paper uses a different asset universe and omits important live
frictions such as transaction costs and asynchronous data handling.

## Implemented Artifacts

Readiness review:

- `scripts/evaluate/build_group_a_plus_harlf_readiness_review.py`
- `tests/test_build_group_a_plus_harlf_readiness_review.py`
- `report/group_a_plus/latest/harlf_readiness_review.json`
- `report/group_a_plus/harlf_readiness/history/harlf_readiness_20260808.json`

Monthly asset sentiment panel:

- `scripts/evaluate/build_group_a_plus_monthly_asset_sentiment_panel.py`
- `tests/test_build_group_a_plus_monthly_asset_sentiment_panel.py`
- `FinRL/data/sentiment/monthly_asset_sentiment_panel.csv`
- `report/group_a_plus/latest/monthly_asset_sentiment_panel_coverage.json`
- `report/group_a_plus/monthly_asset_sentiment_panel_coverage/history/`

HARLF branch ablation shadow:

- `scripts/evaluate/evaluate_group_a_plus_harlf_branch_ablation_shadow.py`
- `tests/test_evaluate_group_a_plus_harlf_branch_ablation_shadow.py`
- `report/group_a_plus/latest/harlf_branch_ablation_shadow.json`
- `report/group_a_plus/harlf_branch_ablation_shadow/history/`

HARLF meta-agent shadow:

- `scripts/evaluate/evaluate_group_a_plus_harlf_meta_agent_shadow.py`
- `tests/test_evaluate_group_a_plus_harlf_meta_agent_shadow.py`
- `report/group_a_plus/latest/harlf_meta_agent_shadow.json`
- `report/group_a_plus/harlf_meta_agent_shadow/history/`

Trade-level OOS validation:

- `scripts/evaluate/validate_group_a_plus_harlf_latest_blend_trade_oos.py`
- `tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py`
- `report/group_a_plus/latest/harlf_latest_blend_trade_oos_validation.json`
- `report/group_a_plus/harlf_latest_blend_trade_oos_validation/history/`

ETF-only HARLF mapping:

- `scripts/evaluate/evaluate_group_a_plus_harlf_etf_mapped_shadow.py`
- `tests/test_evaluate_group_a_plus_harlf_etf_mapped_shadow.py`
- `report/group_a_plus/latest/harlf_etf_mapped_shadow.json`
- `report/group_a_plus/latest/harlf_latest_blend_trade_oos_validation_etf_mapped.json`
- `report/group_a_plus/harlf_etf_mapped_shadow/history/`
- `report/group_a_plus/harlf_latest_blend_trade_oos_validation_etf_mapped/history/`

Latest strategy historical target weights:

- `scripts/evaluate/export_group_a_plus_latest_strategy_target_weights.py`
- `tests/test_export_group_a_plus_latest_strategy_target_weights.py`
- `report/group_a_plus/latest/latest_strategy_historical_target_weights.json`
- `report/group_a_plus/latest/latest_strategy_historical_target_weights.csv`
- `report/group_a_plus/latest_strategy_historical_target_weights/history/`

Trade-level replay:

- `scripts/evaluate/replay_group_a_plus_harlf_latest_blend_trades.py`
- `tests/test_replay_group_a_plus_harlf_latest_blend_trades.py`
- `report/group_a_plus/latest/harlf_latest_blend_trade_replay.json`
- `report/group_a_plus/harlf_latest_blend_trade_replay/history/`

Temporal OOS validation:

- `scripts/evaluate/validate_group_a_plus_harlf_blend_temporal_oos.py`
- `tests/test_validate_group_a_plus_harlf_blend_temporal_oos.py`
- `report/group_a_plus/latest/harlf_blend_temporal_oos_validation.json`
- `report/group_a_plus/harlf_blend_temporal_oos_validation/history/`

OOS failure diagnosis:

- `scripts/evaluate/diagnose_group_a_plus_harlf_oos_failure.py`
- `tests/test_diagnose_group_a_plus_harlf_oos_failure.py`
- `report/group_a_plus/latest/harlf_oos_failure_diagnosis.json`
- `report/group_a_plus/harlf_oos_failure_diagnosis/history/`

Conditional HARLF sleeve shadow:

- `scripts/evaluate/evaluate_group_a_plus_harlf_conditional_sleeve_shadow.py`
- `tests/test_evaluate_group_a_plus_harlf_conditional_sleeve_shadow.py`
- `report/group_a_plus/latest/harlf_conditional_sleeve_shadow.json`
- `report/group_a_plus/harlf_conditional_sleeve_shadow/history/`

Main review document:

- `GROUP_A_PLUS_2507_18560_HARLF_READINESS_REVIEW_20260808.md`

## Current Results

Monthly sentiment panel coverage:

- rows: 57 monthly ticker rows;
- raw news records: 15,993;
- deduped news records: 14,467;
- months: 2025-01 through 2026-08;
- tickers: `0050`, `00631L`, `00632R`, `00679B`, `2330`.

Branch ablation window:

- 2025-01 through 2026-07;
- 19 evaluated months;
- transaction-cost approximation included in net returns.

Net branch ranking:

| Rank | Branch | Net total return | Net Sharpe | Max drawdown |
| --- | --- | ---: | ---: | ---: |
| 1 | `sentiment_only` | 100.99% | 1.67 | -8.50% |
| 2 | `combined` | 88.50% | 1.57 | -11.04% |
| 3 | `market_only` | 69.72% | 1.40 | -13.07% |
| 4 | `equal_weight` | 52.28% | 1.50 | -9.69% |

Interpretation:

- sentiment branch has useful signal in this short sample;
- combined branch also beats equal weight, supporting further research;
- sample is still too short for live promotion;
- results do not authorize adding or reducing `00631L` live exposure.

Meta-agent shadow result:

- routed months: 13;
- net total return: 105.85%;
- annualized Sharpe: 2.21;
- max drawdown: -8.50%;
- beats equal weight: yes;
- beats static combined branch: yes;
- candidate ready for stress test: yes;
- promotion ready: no.

Stress and defensive sweep result:

- original meta-agent passes 3x cost stress;
- original meta-agent remains positive if sentiment branch drops to `combined`;
- original meta-agent fails weak-market months versus equal weight;
- defensive threshold `2.0` protects weak months but loses to static `combined`;
- defensive thresholds `2.5+` beat static `combined` but fail weak-market stress;
- no defensive threshold is ready for latest-strategy comparison.

Compound weak-market gate result:

- route to `equal_weight` if `sentiment_only` is selected and sentiment branch
  score is at least `4.0`;
- also route to `equal_weight` if `sentiment_only` score is at least `2.0` and
  prior-month equal-weight return is at most `2.0%`;
- net total return: 118.76%;
- annualized Sharpe: 2.51;
- max drawdown: -6.64%;
- 3x transaction-cost stress: pass;
- sentiment dropout to `combined`: pass;
- weak-market months not worse than equal weight: pass;
- latest-strategy comparison ready: yes;
- promotion ready: no.

Latest strategy comparison:

- comparison report:
  `report/group_a_plus/latest/harlf_compound_vs_latest_strategy_comparison.json`;
- HARLF compound total return: 118.76%;
- HARLF compound Sharpe: 2.51;
- HARLF compound max drawdown: -6.64%;
- latest strategy total return: 18.23%;
- latest strategy Sharpe: 1.52;
- latest strategy max drawdown: -3.70%;
- `golden01_0531` total return: 18.23%;
- `golden01_0531` Sharpe: 1.52;
- `golden01_0531` max drawdown: -3.70%;
- beats latest/golden return: yes;
- not worse than latest/golden drawdown: no;
- ready for latest strategy review: no.

HARLF/latest blend sweep:

- sweep report: `report/group_a_plus/latest/harlf_latest_blend_sweep.json`;
- best viable blend: 8% HARLF compound, 92% latest strategy;
- blend total return: 24.54%;
- blend Sharpe: 1.75;
- blend max drawdown: -3.70%;
- beats latest total return: yes;
- not worse than latest/golden drawdown: yes;
- ready for latest-strategy review: yes;
- promotion ready: no.

Trade-level OOS validation:

- validation report:
  `report/group_a_plus/latest/harlf_latest_blend_trade_oos_validation.json`;
- status: `blocked`;
- candidate: 8% HARLF compound, 92% latest strategy;
- Group A+ tradable universe: `0050`, `00631L`, `00632R`, `00679B`, `cash`;
- HARLF used assets: `0050`, `00631L`, `00632R`, `00679B`, `2330`;
- non-tradable under current Group A+ ETF implementation: `2330`;
- selected HARLF branch weight months: 13;
- mean HARLF branch turnover: 37.82%;
- max HARLF branch turnover: 87.00%;
- creates orders: no;
- changes `golden01_0531`: no;
- changes latest strategy: no;
- trade-level OOS validation passed: no.

ETF-only mapping result:

- mapping report: `report/group_a_plus/latest/harlf_etf_mapped_shadow.json`;
- compared `drop_2330_renormalize` and `map_2330_to_0050`;
- best mapping for next shadow: `drop_2330_renormalize`;
- `drop_2330_renormalize` total return: 118.09%;
- `drop_2330_renormalize` Sharpe: 2.56;
- `drop_2330_renormalize` max drawdown: -5.42%;
- `map_2330_to_0050` total return: 118.07%;
- `map_2330_to_0050` Sharpe: 2.48;
- `map_2330_to_0050` max drawdown: -6.51%;
- both mappings remove non-ETF assets from meta-agent weights;
- creates orders: no;
- changes `golden01_0531`: no;
- changes latest strategy: no.

ETF-mapped trade-level validation:

- validation report:
  `report/group_a_plus/latest/harlf_latest_blend_trade_oos_validation_etf_mapped.json`;
- status: `blocked`;
- removed blocker:
  `harlf_uses_assets_outside_group_a_plus_tradable_universe`;
- remaining blockers:
  `missing_trade_level_execution_cost_replay_for_blend`,
  `missing_oos_window_beyond_blend_selection_window`.

Latest target weight export:

- target-weight report:
  `report/group_a_plus/latest/latest_strategy_historical_target_weights.json`;
- target-weight CSV:
  `report/group_a_plus/latest/latest_strategy_historical_target_weights.csv`;
- status: `available`;
- rows: 266;
- window: 2025-07-01 through 2026-08-07;
- assets: `0050`, `00631L`, `00632R`, `00679B`, `cash`;
- historical target weight series available: yes;
- creates orders: no;
- changes `golden01_0531`: no;
- changes latest strategy: no.

After re-running ETF-mapped trade-level validation with latest target weights:

- removed blocker:
  `missing_latest_strategy_historical_target_weight_series`;
- remaining blockers:
  `missing_trade_level_execution_cost_replay_for_blend`,
  `missing_oos_window_beyond_blend_selection_window`.

Trade-level replay:

- replay report:
  `report/group_a_plus/latest/harlf_latest_blend_trade_replay.json`;
- status: `available`;
- mapping mode: `drop_2330_renormalize`;
- HARLF sleeve: 8%;
- latest sleeve: 92%;
- window: 2025-08-01 through 2026-08-07;
- daily rows: 248;
- rebalance count: 13;
- total return: 11.40%;
- annualized Sharpe: 3.13;
- max drawdown: -1.23%;
- total transaction cost: 3,400.39;
- total traded value: 1,541,894.62;
- max observed turnover ratio: 49.99%;
- turnover cap binding count: 1;
- creates orders: no;
- changes `golden01_0531`: no;
- changes latest strategy: no.

After re-running ETF-mapped trade-level validation with replay:

- removed blocker:
  `missing_trade_level_execution_cost_replay_for_blend`;
- remaining blocker:
  `missing_oos_window_beyond_blend_selection_window`.

Temporal OOS validation:

- temporal OOS report:
  `report/group_a_plus/latest/harlf_blend_temporal_oos_validation.json`;
- status: `blocked`;
- holdout months: `2026-05`, `2026-06`, `2026-07`;
- OOS window available: yes;
- train best viable blend: none;
- blocking reason:
  `no_train_viable_harlf_blend_under_drawdown_constraint`;
- temporal OOS passed: no;
- creates orders: no;
- changes `golden01_0531`: no;
- changes latest strategy: no.

After re-running ETF-mapped trade-level validation with temporal OOS:

- removed blocker:
  `missing_oos_window_beyond_blend_selection_window`;
- new blocker:
  `harlf_temporal_oos_validation_not_passed`.

OOS failure diagnosis:

- diagnosis report:
  `report/group_a_plus/latest/harlf_oos_failure_diagnosis.json`;
- status: `available`;
- primary failure:
  `positive_harlf_sleeve_improves_return_but_immediately_worsens_drawdown_gate`;
- drawdown-gate blocker months: `2025-10`, `2026-02`;
- minimum positive HARLF sleeve tested: 1%;
- minimum positive HARLF sleeve passing drawdown gate: none;
- 1% HARLF sleeve improves train total return but worsens max drawdown from
  -3.4238% to -3.4559%;
- 8% HARLF sleeve improves train total return but worsens max drawdown to
  -3.6809%;
- fixed HARLF sleeve recommended: no;
- conditional HARLF sleeve research allowed: yes, latest-strategy-only;
- current 8% HARLF sleeve rejected: yes;
- creates orders: no;
- changes `golden01_0531`: no;
- changes latest strategy: no.

Conditional HARLF sleeve shadow:

- conditional sleeve report:
  `report/group_a_plus/latest/harlf_conditional_sleeve_shadow.json`;
- status: `available`;
- method: train-only drawdown gate controls whether HARLF sleeve can turn on;
- nonzero HARLF months: 0;
- conditional sleeve total return: 18.23%;
- latest strategy total return: 18.23%;
- conditional sleeve max drawdown: -3.70%;
- latest strategy max drawdown: -3.70%;
- candidate ready for latest-strategy review: no;
- creates orders: no;
- changes `golden01_0531`: no;
- changes latest strategy: no.

## Current Blockers

Latest `harlf_readiness_review.json` status: `blocked`.

Remaining blockers:

- `llm_state_reward_interface_blocked`;
- `harlf_trade_level_oos_validation_not_passed`.

Trade-level sub-blockers:

- `harlf_temporal_oos_validation_not_passed`.

Resolved in ETF-mapped shadow:

- `harlf_uses_assets_outside_group_a_plus_tradable_universe`.
- `missing_latest_strategy_historical_target_weight_series`.
- `missing_trade_level_execution_cost_replay_for_blend`.
- `missing_oos_window_beyond_blend_selection_window`.

Resolved blockers:

- `missing_monthly_asset_level_sentiment_panel`;
- `missing_market_only_base_agent_oos_backtest`;
- `missing_sentiment_only_base_agent_oos_backtest`;
- `missing_super_agent_ablation_against_equal_weight_and_latest_strategy`.
- `missing_hierarchical_meta_agent_oos_backtest`.
- `missing_transaction_cost_and_stress_test_for_harlf`.

## Verification

Passed:

- `.venv/bin/python -m py_compile scripts/evaluate/build_group_a_plus_harlf_readiness_review.py scripts/evaluate/build_group_a_plus_monthly_asset_sentiment_panel.py scripts/evaluate/evaluate_group_a_plus_harlf_branch_ablation_shadow.py`
- `.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_harlf_meta_agent_shadow.py`
- `.venv/bin/python -m py_compile scripts/evaluate/evaluate_group_a_plus_harlf_stress_shadow.py scripts/evaluate/sweep_group_a_plus_harlf_defensive_meta_agent_params.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_harlf_readiness_review.py tests/test_build_group_a_plus_monthly_asset_sentiment_panel.py tests/test_evaluate_group_a_plus_harlf_branch_ablation_shadow.py tests/test_evaluate_group_a_plus_harlf_meta_agent_shadow.py tests/test_evaluate_group_a_plus_harlf_stress_shadow.py tests/test_sweep_group_a_plus_harlf_defensive_meta_agent_params.py tests/test_build_market_aligned_sentiment_shadow.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_harlf_readiness_review.py tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_harlf_readiness_review.py tests/test_build_group_a_plus_monthly_asset_sentiment_panel.py tests/test_evaluate_group_a_plus_harlf_branch_ablation_shadow.py tests/test_evaluate_group_a_plus_harlf_meta_agent_shadow.py tests/test_evaluate_group_a_plus_harlf_stress_shadow.py tests/test_sweep_group_a_plus_harlf_defensive_meta_agent_params.py tests/test_compare_group_a_plus_harlf_compound_vs_latest_strategy.py tests/test_sweep_group_a_plus_harlf_latest_blend.py tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py tests/test_build_market_aligned_sentiment_shadow.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_harlf_readiness_review.py tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py tests/test_evaluate_group_a_plus_harlf_etf_mapped_shadow.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_harlf_readiness_review.py tests/test_build_group_a_plus_monthly_asset_sentiment_panel.py tests/test_evaluate_group_a_plus_harlf_branch_ablation_shadow.py tests/test_evaluate_group_a_plus_harlf_meta_agent_shadow.py tests/test_evaluate_group_a_plus_harlf_stress_shadow.py tests/test_sweep_group_a_plus_harlf_defensive_meta_agent_params.py tests/test_compare_group_a_plus_harlf_compound_vs_latest_strategy.py tests/test_sweep_group_a_plus_harlf_latest_blend.py tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py tests/test_evaluate_group_a_plus_harlf_etf_mapped_shadow.py tests/test_build_market_aligned_sentiment_shadow.py`
- `.venv/bin/python -m pytest tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py tests/test_export_group_a_plus_latest_strategy_target_weights.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_harlf_readiness_review.py tests/test_build_group_a_plus_monthly_asset_sentiment_panel.py tests/test_evaluate_group_a_plus_harlf_branch_ablation_shadow.py tests/test_evaluate_group_a_plus_harlf_meta_agent_shadow.py tests/test_evaluate_group_a_plus_harlf_stress_shadow.py tests/test_sweep_group_a_plus_harlf_defensive_meta_agent_params.py tests/test_compare_group_a_plus_harlf_compound_vs_latest_strategy.py tests/test_sweep_group_a_plus_harlf_latest_blend.py tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py tests/test_evaluate_group_a_plus_harlf_etf_mapped_shadow.py tests/test_export_group_a_plus_latest_strategy_target_weights.py tests/test_build_market_aligned_sentiment_shadow.py`
- `.venv/bin/python -m pytest tests/test_replay_group_a_plus_harlf_latest_blend_trades.py tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_harlf_readiness_review.py tests/test_build_group_a_plus_monthly_asset_sentiment_panel.py tests/test_evaluate_group_a_plus_harlf_branch_ablation_shadow.py tests/test_evaluate_group_a_plus_harlf_meta_agent_shadow.py tests/test_evaluate_group_a_plus_harlf_stress_shadow.py tests/test_sweep_group_a_plus_harlf_defensive_meta_agent_params.py tests/test_compare_group_a_plus_harlf_compound_vs_latest_strategy.py tests/test_sweep_group_a_plus_harlf_latest_blend.py tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py tests/test_evaluate_group_a_plus_harlf_etf_mapped_shadow.py tests/test_export_group_a_plus_latest_strategy_target_weights.py tests/test_replay_group_a_plus_harlf_latest_blend_trades.py tests/test_build_market_aligned_sentiment_shadow.py`
- `.venv/bin/python -m pytest tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py tests/test_validate_group_a_plus_harlf_blend_temporal_oos.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_harlf_readiness_review.py tests/test_build_group_a_plus_monthly_asset_sentiment_panel.py tests/test_evaluate_group_a_plus_harlf_branch_ablation_shadow.py tests/test_evaluate_group_a_plus_harlf_meta_agent_shadow.py tests/test_evaluate_group_a_plus_harlf_stress_shadow.py tests/test_sweep_group_a_plus_harlf_defensive_meta_agent_params.py tests/test_compare_group_a_plus_harlf_compound_vs_latest_strategy.py tests/test_sweep_group_a_plus_harlf_latest_blend.py tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py tests/test_evaluate_group_a_plus_harlf_etf_mapped_shadow.py tests/test_export_group_a_plus_latest_strategy_target_weights.py tests/test_replay_group_a_plus_harlf_latest_blend_trades.py tests/test_validate_group_a_plus_harlf_blend_temporal_oos.py tests/test_build_market_aligned_sentiment_shadow.py`
- `.venv/bin/python -m pytest tests/test_diagnose_group_a_plus_harlf_oos_failure.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_harlf_readiness_review.py tests/test_build_group_a_plus_monthly_asset_sentiment_panel.py tests/test_evaluate_group_a_plus_harlf_branch_ablation_shadow.py tests/test_evaluate_group_a_plus_harlf_meta_agent_shadow.py tests/test_evaluate_group_a_plus_harlf_stress_shadow.py tests/test_sweep_group_a_plus_harlf_defensive_meta_agent_params.py tests/test_compare_group_a_plus_harlf_compound_vs_latest_strategy.py tests/test_sweep_group_a_plus_harlf_latest_blend.py tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py tests/test_evaluate_group_a_plus_harlf_etf_mapped_shadow.py tests/test_export_group_a_plus_latest_strategy_target_weights.py tests/test_replay_group_a_plus_harlf_latest_blend_trades.py tests/test_validate_group_a_plus_harlf_blend_temporal_oos.py tests/test_diagnose_group_a_plus_harlf_oos_failure.py tests/test_build_market_aligned_sentiment_shadow.py`
- `.venv/bin/python -m pytest tests/test_evaluate_group_a_plus_harlf_conditional_sleeve_shadow.py`
- `.venv/bin/python -m pytest tests/test_build_group_a_plus_harlf_readiness_review.py tests/test_build_group_a_plus_monthly_asset_sentiment_panel.py tests/test_evaluate_group_a_plus_harlf_branch_ablation_shadow.py tests/test_evaluate_group_a_plus_harlf_meta_agent_shadow.py tests/test_evaluate_group_a_plus_harlf_stress_shadow.py tests/test_sweep_group_a_plus_harlf_defensive_meta_agent_params.py tests/test_compare_group_a_plus_harlf_compound_vs_latest_strategy.py tests/test_sweep_group_a_plus_harlf_latest_blend.py tests/test_validate_group_a_plus_harlf_latest_blend_trade_oos.py tests/test_evaluate_group_a_plus_harlf_etf_mapped_shadow.py tests/test_export_group_a_plus_latest_strategy_target_weights.py tests/test_replay_group_a_plus_harlf_latest_blend_trades.py tests/test_validate_group_a_plus_harlf_blend_temporal_oos.py tests/test_diagnose_group_a_plus_harlf_oos_failure.py tests/test_evaluate_group_a_plus_harlf_conditional_sleeve_shadow.py tests/test_build_market_aligned_sentiment_shadow.py`

Targeted test result after trade-level OOS gate: 11 passed.
Full HARLF-related test result after trade-level OOS gate: 44 passed.
Targeted test result after ETF-only mapping: 15 passed.
Full HARLF-related test result after ETF-only mapping: 48 passed.
Targeted test result after latest target-weight export: 6 passed.
Full HARLF-related test result after latest target-weight export: 51 passed.
Targeted test result after trade-level replay: 7 passed.
Full HARLF-related test result after trade-level replay: 54 passed.
Targeted test result after temporal OOS: 8 passed.
Full HARLF-related test result after temporal OOS: 57 passed.
Targeted test result after OOS failure diagnosis: 2 passed.
Full HARLF-related test result after OOS failure diagnosis: 59 passed.
Targeted test result after conditional sleeve shadow: 3 passed.
Full HARLF-related test result after conditional sleeve shadow: 62 passed.

## Next Step

Do not import HARLF into latest strategy yet.

Required before reconsidering:

- keep `golden01_0531` fixed as benchmark only;
- do not promote the current 8% HARLF sleeve because temporal OOS failed;
- do not promote the conditional HARLF sleeve because it turns HARLF off for all
  evaluated months and adds no edge;
- close HARLF weight import from this paper as rejected;
- keep the HARLF-derived validation infrastructure for future papers/signals;
- require explicit approval before any latest-strategy promotion.
