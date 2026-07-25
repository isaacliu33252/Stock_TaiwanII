# GroupA+ PDF Research Decision Matrix（2026-07-17）

## Scope

This matrix consolidates the latest GroupA+ research decisions from twenty-three PDFs:

- `C:\Users\isaac\Downloads\2512.02166.pdf`
- `C:\Users\isaac\Downloads\2606.03184.pdf`
- `C:\Users\isaac\Downloads\2603.29086.pdf`
- `C:\Users\isaac\Downloads\2607.15195.pdf`
- `C:\Users\isaac\Downloads\2603.16035.pdf`
- `C:\Users\isaac\Downloads\2512.12420.pdf`
- `C:\Users\isaac\Downloads\2510.18990.pdf`
- `C:\Users\isaac\Downloads\2605.12653.pdf`
- `C:\Users\isaac\Downloads\2606.30037.pdf`
- `C:\Users\isaac\Downloads\2606.30997.pdf`
- `C:\Users\isaac\Downloads\2603.21330.pdf`
- `C:\Users\isaac\Downloads\1212.2833.pdf`
- `C:\Users\isaac\Downloads\2603.10202.pdf`
- `C:\Users\isaac\Downloads\2606.26625.pdf`
- `C:\Users\isaac\Downloads\2604.14498.pdf`
- `C:\Users\isaac\Downloads\2605.12462.pdf`
- `C:\Users\isaac\Downloads\1610.09404.pdf`
- `C:\Users\isaac\Downloads\2004.01917.pdf`
- `C:\Users\isaac\Downloads\1510.08162.pdf`
- `C:\Users\isaac\Downloads\2511.12476.pdf`
- `C:\Users\isaac\Downloads\2107.09048.pdf`
- `C:\Users\isaac\Downloads\2512.10913.pdf`
- `C:\Users\isaac\Downloads\2606.08450.pdf`

Active strategy under review:

- `a2118_a2111_ncf_late_bull_deleverage`
- Runner: `group_a_plus.runners.a2118`
- Current 7/20 reference target:
  - `0050.TW = 50%`
  - `00631L.TW = 20%`
  - `00632R.TW = 0%`
  - `00679B.TWO = 0%`
  - cash = `30%`

## Executive Decision

Do not change live target weights.

Do not auto-rebalance for `2026-07-20`.

Do not auto-add `00631L`.

Use all PDF imports as research / shadow / manual review only.

## Decision Matrix

| PDF | Main idea | Imported benefit | Artifact | Live impact |
| --- | --- | --- | --- | --- |
| `2512.02166` | Three-dimensional volatility memory decomposition | Level / shape / tempo volatility-memory shadow | `trigate_vol_memory_shadow.json` | No TG-Vol import / no weight change |
| `2606.03184` | FinStressTS mechanism-aware synthetic financial forecasting benchmark | Mechanism-specific model validation readiness governance | `finstressts_readiness_review_20260720.json` | No synthetic alpha / no weight change |
| `2603.29086` | Realistic market impact in RL trading environments | Market-impact / POV / turnover readiness governance | `market_impact_readiness_review_20260720.json` | No RL env / no rebalance |
| `2607.15195` | SciPhyRL/PINN offline portfolio optimization | Target-holding / explicit-cost readiness governance | `sciphyrl_readiness_review_20260720.json` | No optimizer / no weight change |
| `2603.16035` | Sparse heterogeneous Markov-switching heteroskedasticity | Source-level heterogeneous volatility review | `heterogeneous_vol_regime_advisory.json` | No weight change |
| `2512.12420` | Deep hedging with RL under costs / position limits | Cost-aware overlay governance and option-state coverage gate | `deep_hedging_overlay_review_20260720.json` | No RL import / no weight change |
| `2510.18990` | Adversarial examples against financial forecasting models | Adversarial market-integrity governance / no single-model auto-execution | `adversarial_market_integrity_review_20260720.json` | No weight change |
| `2605.12653` | FinPILOT inference-time planning before trade | FinPILOT-lite planning preview and forecast freshness gate | `finpilot_lite_planning_review_20260720.json` | No auto apply |
| `2606.30037` | Heads, not backbones for fat-tailed returns | Density-head tail calibration review | `density_head_tail_risk_advisory.json` | No guard / no weight change |
| `2606.30997` | Tax-aware personalized portfolio foundation model | Active cash buffer, rebalance preview, objective labels | `rebalance_review_20260720.json` | No auto rebalance |
| `2603.21330` | FinRL-X deployment-consistent weight-centric trading architecture | Deployment consistency / target-weight interface / execution guard monitoring review | `docs/2603_21330_FINRLX_GROUPA_PLUS_REVIEW_20260718.md` | No engine import / no weight change |
| `1212.2833` | Perpetual money machine / financialization / bubbles / ETF coupling | Time-at-risk governance, ETF-coupling fragility checklist, reflexivity proxy, scenario discipline | `docs/1212_2833_PERPETUAL_MONEY_MACHINE_GROUPA_PLUS_REVIEW_20260718.md` | No macro timing import / no weight change |
| `2603.10202` | Hybrid HMM with jump-duration synthetic financial scenarios | Synthetic scenario quality gate, multi-day jump-duration stress episodes, interpretable quantile-state transitions, Student-t copula dependence concept | `docs/2603_10202_HMM_WJ_SYNTHETIC_SCENARIO_GROUPA_PLUS_REVIEW_20260718.md` | No synthetic alpha / no weight change |
| `2606.26625` | Commodity ETF optimization under heavy-tailed returns | Dynamic CVaR/tail/cost readiness governance, CVaR/EVT tail diagnostics, turnover and transaction-cost robustness checklist, warning against return-seeking tangent optimizers | `docs/2606_26625_COMMODITY_ETF_CVAR_TAIL_RISK_GROUPA_PLUS_REVIEW_20260718.md`; `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json` | Research-only / blocked / no commodity allocation / no weight change |
| `2604.14498` | Synthetic augmentation validation for financial ML | Size-matched null augmentation gate, block permutation test, task-type restriction for synthetic data, rare-regime metric alignment | `docs/2604_14498_SYNTHETIC_AUGMENTATION_VALIDATION_GROUPA_PLUS_REVIEW_20260718.md` | Validation governance only / no synthetic alpha / no weight change |
| `2605.12462` | Gymnasium environment for risk-aware demand-response RL | Modular environment design, multi-objective CVaR reward, intervention fatigue, risk-budget pacing | `docs/2605_12462_DR_GYM_RISK_AWARE_ENV_GROUPA_PLUS_REVIEW_20260718.md`; `report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json` | Research-only / blocked / no RL policy / no weight change |
| `1610.09404` | Tracking errors of commodity leveraged ETFs | LETF holding-horizon risk, realized-variance decay, realized effective fee proxy, inverse ETF hedge-neutrality warning | `docs/1610_09404_LETF_TRACKING_ERROR_GROUPA_PLUS_REVIEW_20260718.md` | Research-only / no LETF pair strategy / no weight change |
| `2004.01917` | Illiquidity network of stocks in China's market crash | Liquidity-contagion data-readiness gate, high-frequency bid/ask requirement, five-day systemic-failure warning candidate | `docs/2004_01917_ILLIQUIDITY_NETWORK_GROUPA_PLUS_REVIEW_20260719.md`; `report/group_a_plus/latest/illiquidity_network_readiness_review.json` | Research-only / blocked / no crash guard / no weight change |
| `1510.08162` | Speculative Influence Network during financial bubbles | HMM bubble-state and transfer-entropy speculative influence readiness gate; NSII max-loss validation design; SIN-lite and systemic overlap audits retained as manual-review evidence only | `docs/1510_08162_SPECULATIVE_INFLUENCE_NETWORK_GROUPA_PLUS_REVIEW_20260719.md`; `report/group_a_plus/latest/speculative_influence_network_readiness_review.json`; `report/group_a_plus/latest/sin_lite_srr_overlap.json`; `report/group_a_plus/latest/systemic_bubble_param_sweep.json` | Research-only / blocked / no SIN gate / no systemic gate / no weight change |
| `2511.12476` | Performance and Risk Analytics of Asian Exchange-Traded Funds | Equal-weight ETF benchmark discipline, CVaR/STARR/Rachev/Hill tail analytics governance, long-short cost blocker | `docs/2511_12476_ASIAN_ETF_TAIL_ANALYTICS_GROUPA_PLUS_REVIEW_20260719.md`; `report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json` | Research-only / blocked / no optimizer / no long-short leverage / no weight change |
| `2107.09048` | Reduced-rank correlation market states as long-term crisis precursors | Largest-eigenvalue market-mode subtraction, reduced-rank correlation averaged-distance monitor, k-means crisis-state snapshot concept | `docs/2107_09048_REDUCED_RANK_CORRELATION_CRISIS_PRECURSOR_GROUPA_PLUS_REVIEW_20260719.md`; `docs/HANDOFF_2107_09048_REDUCED_RANK_CORRELATION_GROUPA_PLUS_20260719.md`; `docs/DETAILED_HANDOFF_2107_09048_REDUCED_RANK_CORRELATION_GROUPA_PLUS_20260720.md`; `report/group_a_plus/latest/reduced_rank_correlation_readiness_review.json`; `report/group_a_plus/latest/reduced_rank_correlation_proxy.json`; `report/group_a_plus/latest/reduced_rank_correlation_proxy_param_sweep.json`; `report/group_a_plus/latest/reduced_rank_correlation_crash_window_backtest.json`; `report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest.json` | Research-only / readiness blocked / confirmation gate lowers false positives / no crash predictor / no live gate / no weight change |
| `2512.10913` | Systematic review of RL in financial decision making | RL/ML promotion governance: explainability, robustness, deployment feasibility, benchmark discipline, implementation quality over algorithm complexity | `docs/2512_10913_RL_FINANCIAL_DECISION_SYSTEMATIC_REVIEW_GROUPA_PLUS_REVIEW_20260720.md`; `docs/HANDOFF_2512_10913_RL_FINANCIAL_DECISION_SYSTEMATIC_REVIEW_GROUPA_PLUS_20260720.md`; `docs/DETAILED_HANDOFF_2512_10913_RL_GOVERNANCE_GROUPA_PLUS_20260720.md`; `report/group_a_plus/latest/rl_governance_readiness_review.json` | Research-only governance / RL governance blocked / no RL allocator / no live gate / no weight change |
| `2606.08450` | GIFT LLM-guided state-reward interface for financial RL | Constrained LLM feature/reward proposal governance, risk-rule reward audit, diagnostic-guided refinement, frozen interface before OOS, multi-ticker feature-stability and windowed stress audit, manual hedge eligibility checklist, 00632R tail-gate split review, effective-fee proxy validation, live hedge policy boundary | `docs/2606_08450_GIFT_LLM_STATE_REWARD_INTERFACE_GROUPA_PLUS_REVIEW_20260720.md`; `docs/HANDOFF_2606_08450_GIFT_LLM_STATE_REWARD_INTERFACE_GROUPA_PLUS_20260720.md`; `report/group_a_plus/latest/llm_state_reward_interface_readiness_review.json`; `report/group_a_plus/latest/llm_state_reward_interface_catalog.json`; `report/group_a_plus/latest/llm_state_reward_interface_proposal_validation_review.json`; `report/group_a_plus/latest/llm_state_reward_interface_offline_smoke_review.json`; `report/group_a_plus/latest/llm_state_reward_interface_multi_ticker_smoke_review.json`; `report/group_a_plus/latest/llm_state_reward_interface_feature_stability_review.json`; `report/group_a_plus/latest/llm_state_reward_interface_windowed_stability_review.json`; `report/group_a_plus/latest/llm_state_reward_interface_manual_hedge_eligibility_review.json`; `report/group_a_plus/latest/00632r_tail_tracking_error_gate_review.json`; `report/group_a_plus/latest/00632r_effective_fee_proxy_validation_review.json`; `report/group_a_plus/latest/live_hedge_policy_review.json` | Research-only governance / readiness blocked / hedge evidence present / policy boundary defined but not live validated / manual hedge eligibility blocked / no weight change |

## Imported Concepts

### 2606.08450

Imported:

- constrained LLM feature proposal from approved financial primitives;
- risk-rule-guided reward shaping as an objective audit framework;
- diagnostic-guided refinement using rollout / validation metrics;
- frozen state-reward interface before OOS evaluation;
- no LLM query, prompt update, or interface modification at test time.

Produced:

- `docs/2606_08450_GIFT_LLM_STATE_REWARD_INTERFACE_GROUPA_PLUS_REVIEW_20260720.md`
- `docs/HANDOFF_2606_08450_GIFT_LLM_STATE_REWARD_INTERFACE_GROUPA_PLUS_20260720.md`
- `scripts/evaluate/build_group_a_plus_llm_state_reward_interface_readiness_review.py`
- `tests/test_build_group_a_plus_llm_state_reward_interface_readiness_review.py`
- `scripts/evaluate/build_group_a_plus_llm_state_reward_interface_catalog.py`
- `tests/test_build_group_a_plus_llm_state_reward_interface_catalog.py`
- `scripts/evaluate/validate_group_a_plus_llm_state_reward_interface_proposals.py`
- `tests/test_validate_group_a_plus_llm_state_reward_interface_proposals.py`
- `scripts/evaluate/evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py`
- `tests/test_evaluate_group_a_plus_llm_state_reward_interface_offline_smoke.py`
- `scripts/evaluate/evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke.py`
- `tests/test_evaluate_group_a_plus_llm_state_reward_interface_multi_ticker_smoke.py`
- `scripts/evaluate/evaluate_group_a_plus_llm_state_reward_interface_feature_stability.py`
- `tests/test_evaluate_group_a_plus_llm_state_reward_interface_feature_stability.py`
- `scripts/evaluate/evaluate_group_a_plus_llm_state_reward_interface_windowed_stability.py`
- `tests/test_evaluate_group_a_plus_llm_state_reward_interface_windowed_stability.py`
- `scripts/evaluate/build_group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review.py`
- `tests/test_build_group_a_plus_llm_state_reward_interface_manual_hedge_eligibility_review.py`
- `scripts/evaluate/build_group_a_plus_00632r_tail_tracking_error_gate_review.py`
- `tests/test_build_group_a_plus_00632r_tail_tracking_error_gate_review.py`
- `scripts/evaluate/build_group_a_plus_00632r_effective_fee_proxy_validation_review.py`
- `tests/test_build_group_a_plus_00632r_effective_fee_proxy_validation_review.py`
- `scripts/evaluate/build_group_a_plus_live_hedge_policy_review.py`
- `tests/test_build_group_a_plus_live_hedge_policy_review.py`
- `report/group_a_plus/latest/llm_state_reward_interface_readiness_review.json`
- `report/group_a_plus/llm_state_reward_interface/history/llm_state_reward_interface_readiness_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_catalog.json`
- `report/group_a_plus/llm_state_reward_interface_catalog/history/llm_state_reward_interface_catalog_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_sample_proposals.json`
- `report/group_a_plus/latest/llm_state_reward_interface_proposal_validation_review.json`
- `report/group_a_plus/llm_state_reward_interface_proposal_validation/history/llm_state_reward_interface_proposal_validation_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_offline_smoke_review.json`
- `report/group_a_plus/llm_state_reward_interface_offline_smoke/history/llm_state_reward_interface_offline_smoke_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_multi_ticker_smoke_review.json`
- `report/group_a_plus/llm_state_reward_interface_multi_ticker_smoke/history/llm_state_reward_interface_multi_ticker_smoke_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_feature_stability_review.json`
- `report/group_a_plus/llm_state_reward_interface_feature_stability/history/llm_state_reward_interface_feature_stability_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_windowed_stability_review.json`
- `report/group_a_plus/llm_state_reward_interface_windowed_stability/history/llm_state_reward_interface_windowed_stability_20260720.json`
- `report/group_a_plus/latest/llm_state_reward_interface_manual_hedge_eligibility_review.json`
- `report/group_a_plus/llm_state_reward_interface_manual_hedge_eligibility/history/llm_state_reward_interface_manual_hedge_eligibility_20260720.json`
- `report/group_a_plus/latest/00632r_tail_tracking_error_gate_review.json`
- `report/group_a_plus/00632r_tail_tracking_error_gate/history/00632r_tail_tracking_error_gate_20260720.json`
- `report/group_a_plus/latest/00632r_effective_fee_proxy_validation_review.json`
- `report/group_a_plus/00632r_effective_fee_proxy_validation/history/00632r_effective_fee_proxy_validation_20260720.json`
- `report/group_a_plus/latest/live_hedge_policy_review.json`
- `report/group_a_plus/live_hedge_policy/history/live_hedge_policy_20260720.json`

Decision:

- Do not import a live LLM trading agent.
- Do not import PPO as a live allocator.
- Do not use generated feature/reward code without review.
- Do not allow test-time LLM updates.
- Keep `Golden1_0531` unchanged.
- Keep `00631L` add blocked.
- Keep `00632R` open blocked.
- `llm_state_reward_interface_readiness_review.json` is implemented and blocked.
- `llm_state_reward_interface_catalog.json` is implemented and live-blocked.
- `llm_state_reward_interface_proposal_validation_review.json` is implemented:
  one research-only proposal accepted for offline review, one live target-weight
  proposal rejected.
- `llm_state_reward_interface_offline_smoke_review.json` is implemented:
  accepted proposal passed finite/bounded smoke on `2560` rows of `0050.TW`
  DuckDB daily data through `2026-07-17`, with no live action and no model
  training.
- `llm_state_reward_interface_multi_ticker_smoke_review.json` is implemented:
  the same smoke passes on `8` ETF tickers, all through `2026-07-17`, with no
  blocked tickers and no live action.
- `llm_state_reward_interface_feature_stability_review.json`,
  `llm_state_reward_interface_windowed_stability_review.json`, and
  `llm_state_reward_interface_manual_hedge_eligibility_review.json` are
  implemented: `00632R.TW` hedge-like evidence is present in recent/windowed
  review, but manual hedge eligibility is blocked by tail tracking-error,
  effective-fee, live hedge policy, market-impact, and research-shadow gates.
- `00632r_tail_tracking_error_gate_review.json` is implemented: the full-sample
  30d p05 gate remains an auto-trading blocker, while recent-tail behavior
  supports a monitoring-only manual tier; no hedge permission is granted.
- `00632r_effective_fee_proxy_validation_review.json` is implemented:
  effective drag is highly correlated with tracking error but fails 20d/30d
  left-tail overlap, so the effective-fee proxy blocker remains active.
- `live_hedge_policy_review.json` is implemented: policy boundary is defined
  and explicitly forbids LLM/PPO/script-generated orders, target weights, and
  auto rebalance, but live hedge policy remains unvalidated for action.
- Useful only for research governance and future feature/reward proposal review.

### 2512.10913

Imported:

- RL promotion governance discipline;
- explainability and auditability requirement;
- robustness / non-stationarity testing requirement;
- standardized benchmark requirement;
- implementation-quality and domain-knowledge priority;
- transaction-cost, turnover, market-impact, and risk-management-first
  checklist.

Produced:

- `docs/2512_10913_RL_FINANCIAL_DECISION_SYSTEMATIC_REVIEW_GROUPA_PLUS_REVIEW_20260720.md`
- `docs/HANDOFF_2512_10913_RL_FINANCIAL_DECISION_SYSTEMATIC_REVIEW_GROUPA_PLUS_20260720.md`
- `docs/DETAILED_HANDOFF_2512_10913_RL_GOVERNANCE_GROUPA_PLUS_20260720.md`
- `scripts/evaluate/build_group_a_plus_rl_governance_readiness_review.py`
- `tests/test_build_group_a_plus_rl_governance_readiness_review.py`
- `report/group_a_plus/latest/rl_governance_readiness_review.json`
- `report/group_a_plus/rl_governance_readiness/history/rl_governance_readiness_20260720.json`

Decision:

- Do not import a live RL allocator.
- Do not import market-making or cryptocurrency RL results.
- Do not use as an execution gate.
- Do not change `Golden1_0531`.
- Keep `00631L` add blocked.
- Keep `00632R` open blocked.
- `rl_governance_readiness_review.json` is implemented and blocked.
- No RL/ML component is promotable.

### 2107.09048

Imported:

- reduced-rank correlation matrix concept;
- subtract largest-eigenvalue market component to separate broad market motion
  from sector / endogenous structure;
- averaged-distance transition monitor as a systemic-fragility candidate;
- k-means market-state snapshots as research-only diagnostics.

Produced:

- `docs/2107_09048_REDUCED_RANK_CORRELATION_CRISIS_PRECURSOR_GROUPA_PLUS_REVIEW_20260719.md`
- `docs/HANDOFF_2107_09048_REDUCED_RANK_CORRELATION_GROUPA_PLUS_20260719.md`
- `docs/DETAILED_HANDOFF_2107_09048_REDUCED_RANK_CORRELATION_GROUPA_PLUS_20260720.md`
- `scripts/evaluate/build_group_a_plus_reduced_rank_correlation_readiness_review.py`
- `tests/test_build_group_a_plus_reduced_rank_correlation_readiness_review.py`
- `report/group_a_plus/latest/reduced_rank_correlation_readiness_review.json`
- `report/group_a_plus/reduced_rank_correlation_readiness/history/reduced_rank_correlation_readiness_20260720.json`
- `scripts/evaluate/build_group_a_plus_reduced_rank_correlation_proxy.py`
- `tests/test_build_group_a_plus_reduced_rank_correlation_proxy.py`
- `report/group_a_plus/latest/reduced_rank_correlation_proxy.json`
- `report/group_a_plus/reduced_rank_correlation_proxy/history/reduced_rank_correlation_proxy_20260720.json`
- `scripts/evaluate/sweep_group_a_plus_reduced_rank_correlation_proxy_params.py`
- `tests/test_sweep_group_a_plus_reduced_rank_correlation_proxy_params.py`
- `report/group_a_plus/latest/reduced_rank_correlation_proxy_param_sweep.json`
- `report/group_a_plus/reduced_rank_correlation_proxy_param_sweep/history/reduced_rank_correlation_proxy_param_sweep_20260720.json`
- `scripts/evaluate/evaluate_group_a_plus_reduced_rank_correlation_crash_window_backtest.py`
- `tests/test_group_a_plus_reduced_rank_correlation_crash_window_backtest.py`
- `report/group_a_plus/latest/reduced_rank_correlation_crash_window_backtest.json`
- `report/group_a_plus/reduced_rank_correlation_crash_window_backtest/history/reduced_rank_correlation_crash_window_backtest_20260720.json`
- `scripts/evaluate/evaluate_group_a_plus_reduced_rank_confirmation_overlap_backtest.py`
- `tests/test_group_a_plus_reduced_rank_confirmation_overlap_backtest.py`
- `report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest.json`
- `report/group_a_plus/reduced_rank_confirmation_overlap_backtest/history/reduced_rank_confirmation_overlap_backtest_20260720.json`

Decision:

- Do not import as a crash predictor.
- Do not use as an execution gate.
- Current GroupA+ tradable universe is too small for the paper's full
  `250`-stock sector-state method.
- Current readiness review has `15` local tickers and `22` external market
  tickers: weak cross-market proxy is possible for research, but not
  paper-equivalent.
- Weak proxy generated on `35` fresh usable tickers; latest state is `normal`,
  with no manual review required by proxy itself.
- Parameter sweep across `24` candidates produced `16` normal and `8` watch
  states, with no elevated-fragility majority.
- Crash-window backtest is unfavorable: stress watch-or-worse `0.246711` vs
  non-window watch-or-worse `0.424373`, so false positives exceed stress-window
  recall.
- Confirmation-gated overlap with SIN-lite/systemic-bubble improves noise:
  confirmed stress watch `0.192982` vs non-window watch `0.084929`.
- Reduced-rank matrix, averaged-distance monitor, k-means snapshots, and Taiwan
  crash-window walk-forward validation are not paper-equivalent yet.
- Keep `00631L` add blocked.
- Keep `00632R` open blocked.
- Keep `Golden1_0531` unchanged.
- No live strategy change.

### 2511.12476

Imported:

- equal-weight ETF benchmark as a research comparator;
- CVaR `95%` / `99%` frontier as future validation benchmark;
- Sharpe / Rachev / STARR reward-risk ratios as reporting candidates;
- Hill tail index as an extreme-loss diagnostic candidate;
- explicit transaction, borrow, financing, and shorting-cost blocker before any
  long-short strategy.
- Rachev 95/95 reporting was added to the existing CVaR tail diagnostic for
  current GroupA+ exposures.
- Tail reward/risk tier was added to the Asian ETF readiness review and daily
  status; latest tier is `defensive_preference`.

Produced:

- `docs/2511_12476_ASIAN_ETF_TAIL_ANALYTICS_GROUPA_PLUS_REVIEW_20260719.md`
- `docs/HANDOFF_2511_12476_ASIAN_ETF_TAIL_ANALYTICS_GROUPA_PLUS_20260719.md`
- `scripts/evaluate/build_group_a_plus_asian_etf_tail_analytics_readiness_review.py`
- `scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py`
- `tests/test_build_group_a_plus_asian_etf_tail_analytics_readiness_review.py`
- `tests/test_evaluate_cvar_tail_risk_diagnostic_shadow.py`
- `report/group_a_plus/latest/asian_etf_tail_analytics_readiness_review.json`
- `report/group_a_plus/asian_etf_tail_analytics_readiness/history/asian_etf_tail_analytics_readiness_20260720.json`

Decision:

- Do not import the paper's 29 US-listed Asian ETF allocation.
- Do not import Markowitz or CVaR optimized live weights.
- Do not import long-short `10%`, `20%`, or `30%` leverage.
- Current local coverage has only `1` of the paper's `29` ETFs available:
  `EWT`.
- Keep the paper as ETF tail-risk analytics governance only.
- Rachev/STARR/Hill reporting is useful, but optimizer and full 29-ETF
  validation remain blocked.
- Current Rachev comparison supports the existing defensive stance:
  `Golden1_0531` `1.034594033280388` vs `00631L` `0.9502107385766837`.
- Keep `00631L` add blocked.
- Keep `00632R` open blocked.
- Keep `Golden1_0531` unchanged.
- No live strategy change.

### 1510.08162

Imported:

- speculative bubble influence should be tested as a sector/firm network;
- HMM bubble-state probabilities can serve as a speculative-regime diagnostic;
- transfer entropy and NSII can rank directional speculative influence;
- maximum-loss validation is the correct promotion target before live use;
- sector / financial vs non-financial asymmetry should be inspected only after
  metadata and full-universe coverage exist.

Produced:

- `docs/1510_08162_SPECULATIVE_INFLUENCE_NETWORK_GROUPA_PLUS_REVIEW_20260719.md`
- `docs/HANDOFF_1510_08162_SPECULATIVE_INFLUENCE_NETWORK_GROUPA_PLUS_20260719.md`
- `scripts/evaluate/build_group_a_plus_speculative_influence_network_readiness_review.py`
- `scripts/fetch/backfill_group_a_plus_ticker_metadata.py`
- `scripts/evaluate/build_group_a_plus_sin_lite_proxy.py`
- `scripts/evaluate/evaluate_group_a_plus_sin_lite_crash_window_backtest.py`
- `scripts/evaluate/sweep_group_a_plus_sin_lite_params.py`
- `scripts/evaluate/evaluate_group_a_plus_sin_lite_srr_overlap.py`
- `scripts/evaluate/evaluate_group_a_plus_systemic_bubble_srr_overlap.py`
- `scripts/evaluate/sweep_group_a_plus_systemic_bubble_srr_params.py`
- `tests/test_build_group_a_plus_speculative_influence_network_readiness_review.py`
- `tests/test_backfill_group_a_plus_ticker_metadata.py`
- `tests/test_build_group_a_plus_sin_lite_proxy.py`
- `tests/test_group_a_plus_sin_lite_crash_window_backtest.py`
- `tests/test_sweep_group_a_plus_sin_lite_params.py`
- `tests/test_group_a_plus_sin_lite_srr_overlap.py`
- `tests/test_group_a_plus_systemic_bubble_srr_overlap.py`
- `tests/test_sweep_group_a_plus_systemic_bubble_srr_params.py`
- `report/group_a_plus/latest/ticker_metadata_backfill_report.json`
- `report/group_a_plus/latest/speculative_influence_network_readiness_review.json`
- `report/group_a_plus/latest/sin_lite_proxy.json`
- `report/group_a_plus/latest/sin_lite_crash_window_backtest.json`
- `report/group_a_plus/latest/sin_lite_param_sweep.json`
- `report/group_a_plus/latest/sin_lite_srr_overlap.json`
- `report/group_a_plus/latest/systemic_bubble_srr_overlap.json`
- `report/group_a_plus/latest/systemic_bubble_param_sweep.json`
- `report/group_a_plus/speculative_influence_network_readiness/history/speculative_influence_network_readiness_20260720.json`

Decision:

- Do not import China 2006-2008 bubble parameters.
- Do not implement SIN as a live crash guard.
- Do not replace or widen SRR-lite with SIN-lite.
- Do not replace or widen SRR-lite with systemic bubble time-at-risk.
- Use the paper as governance evidence through
  `speculative_influence_network_readiness_review`.
- SIN-lite tuned watch improves recall but has excessive H10 false positives;
  `SRR OR SIN tuned watch` has H10 FPR `0.5313653136531366`.
- Systemic watch+ is too broad; H10 FPR `0.757201646090535`.
- Strict systemic confirmation can improve precision only by making the signal
  too sparse:
  - `srr_confirmed_by_systemic_blocked`: active `2`, H10 precision `1.0`;
  - best sample-ready systemic candidate: active `33`, H10 precision
    `0.36363636363636365`, below SRR.
- Current status is `blocked` because broad sector/firm universe, sector
  metadata, HMM bubble-state probabilities, transfer entropy / NSII network, and
  max-loss validation labels are missing.
- Keep `00631L` add blocked.
- Keep `00632R` open blocked.
- Keep `Golden1_0531` unchanged.
- No live strategy change.

### 2004.01917

Imported:

- illiquidity contagion should be monitored as a market-network effect;
- crash days may show denser and more homogeneous liquidity-stress dependency;
- finance / core-market instruments deserve liquidity-stress inspection;
- five-day systemic liquidity-failure count is a candidate early-warning idea;
- high-frequency bid/ask and full-market failure-event data are mandatory before
  the idea can be tested.

Produced:

- `docs/2004_01917_ILLIQUIDITY_NETWORK_GROUPA_PLUS_REVIEW_20260719.md`
- `docs/HANDOFF_2004_01917_ILLIQUIDITY_NETWORK_GROUPA_PLUS_20260719.md`
- `scripts/evaluate/build_group_a_plus_illiquidity_network_readiness_review.py`
- `tests/test_build_group_a_plus_illiquidity_network_readiness_review.py`
- `report/group_a_plus/latest/illiquidity_network_readiness_review.json`
- `report/group_a_plus/illiquidity_network_readiness/history/illiquidity_network_readiness_20260720.json`

Decision:

- Do not import China 2015 crash-warning parameters.
- Do not import the five-day signal as a live crash guard.
- Use the paper as governance evidence through
  `illiquidity_network_readiness_review`.
- Current status is `blocked` because high-frequency bid/ask, intraday
  liquidity, market-wide failure events, and sector/style mapping are missing.
- Keep `00631L` add blocked.
- Keep `00632R` open blocked.
- Keep `Golden1_0531` unchanged.
- No live strategy change.

### 1610.09404

Imported:

- leveraged ETF tracking error should be checked across multiple horizons:
  - 1 day;
  - 5 days;
  - 10 days;
  - 20 days;
  - 30 days;
- realized variance creates a decay term for LETFs;
- realized effective fee / effective drag can quantify underperformance beyond
  stated expense fees;
- inverse ETFs can have asymmetric tracking and horizon penalties;
- long/inverse LETF pair or hedge positions are not reliably neutral over large
  reference moves;
- double-short LETF strategies have large tail risk and should not be promoted
  into GroupA+.

Produced:

- `docs/1610_09404_LETF_TRACKING_ERROR_GROUPA_PLUS_REVIEW_20260718.md`
- `docs/HANDOFF_1610_09404_LETF_TRACKING_ERROR_GROUPA_PLUS_20260718.md`
- `scripts/evaluate/build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py`
- `tests/test_build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py`
- `report/group_a_plus/latest/letf_tracking_error_effective_fee_readiness_review.json`
- `report/group_a_plus/letf_tracking_error_effective_fee_readiness/history/letf_tracking_error_effective_fee_readiness_20260720.json`

Decision:

- Do not import commodity ETF parameters.
- Do not import double-short LETF strategy.
- Use the paper as governance evidence through the implemented
  `letf_tracking_error_effective_fee_readiness_review`.
- Keep `00631L` add blocked.
- Keep `00632R` open blocked.
- Keep `Golden1_0531` unchanged.
- No live strategy change.

2026-07-20 result:

- `status = blocked`, actual data end `2026-07-17`.
- Research shadow now includes
  `letf_tracking_error_effective_fee_readiness_blocked`.

### 2605.12462

Imported:

- modular environment/testbed design for future strategy simulation;
- multi-objective reward framing:
  - expected return / revenue analogue;
  - investor cost / drawdown analogue;
  - stress-state penalty;
  - CVaR or tail-risk penalty;
- intervention fatigue:
  - repeated position changes consume future flexibility;
  - clustered leverage additions should be penalized;
- risk-budget pacing:
  - do not spend all leverage/hedge budget on the first signal;
  - preserve optionality for crash or recovery windows;
- baseline comparison discipline:
  - compare learned or adaptive policy against simple rules before promotion.

Produced:

- `docs/2605_12462_DR_GYM_RISK_AWARE_ENV_GROUPA_PLUS_REVIEW_20260718.md`
- `docs/HANDOFF_2605_12462_DR_GYM_RISK_AWARE_ENV_GROUPA_PLUS_20260718.md`
- `scripts/evaluate/build_group_a_plus_intervention_history_from_daily_status.py`
- `scripts/evaluate/build_group_a_plus_broker_holdings_time_series_sample.py`
- `scripts/evaluate/build_group_a_plus_intervention_fatigue_risk_budget_readiness_review.py`
- `tests/test_build_group_a_plus_intervention_history_from_daily_status.py`
- `tests/test_build_group_a_plus_broker_holdings_time_series_sample.py`
- `tests/test_build_group_a_plus_intervention_fatigue_risk_budget_readiness_review.py`
- `report/group_a_plus/latest/intervention_history.json`
- `report/group_a_plus/intervention_history/history/20260720.json`
- `report/group_a_plus/latest/broker_holdings_time_series_sample.json`
- `report/group_a_plus/broker_holdings_time_series_sample/history/20260717.json`
- `report/group_a_plus/latest/intervention_fatigue_risk_budget_readiness_review.json`
- `report/group_a_plus/intervention_fatigue_risk_budget_readiness/history/20260720.json`

Current output:

- `status = blocked`
- `intervention_fatigue_ready = false`
- `risk_budget_pacing_ready = false`
- `allow_00631l_add = false`
- `allow_00632r_open = false`
- `auto_rebalance_allowed = false`
- `target_weight_change_allowed = false`
- `turnover = 0.5006477801878955`
- normalized intervention history is available:
  - `entry_count = 40`
  - `blocked_entry_count = 21`
  - `leverage_intervention_count = 31`
  - `hedge_intervention_count = 0`
- broker holdings sample is available, but not authoritative:
  - `transaction_count = 146`
  - `snapshot_count = 116`
  - `negative_position_count = 4`

Decision:

- Do not import electricity market data or PPO policy.
- Use the paper only as governance for the implemented research-only
  `intervention_fatigue_risk_budget_readiness_review`.
- No live strategy change.
- Keep `Golden1_0531` unchanged.
- Do not auto rebalance, add `00631L`, or open `00632R`.

### 2604.14498

Imported:

- size-matched null augmentation as a required control before accepting
  synthetic data;
- block permutation testing for temporally dependent out-of-sample loss
  differences;
- task-type restriction:
  - directional synthetic alpha defaults to blocked;
  - volatility / tail-risk / rare-regime synthetic augmentation can be
    research-only if validated;
- rare-regime metrics must match the economic objective:
  - AP;
  - F1;
  - recall under false-positive constraints;
  - expected shortfall / drawdown style metrics.

Produced:

- `docs/2604_14498_SYNTHETIC_AUGMENTATION_VALIDATION_GROUPA_PLUS_REVIEW_20260718.md`
- `docs/HANDOFF_2604_14498_SYNTHETIC_AUGMENTATION_VALIDATION_GROUPA_PLUS_20260718.md`

Decision:

- Do not use synthetic augmentation as direct `00631L` / `00632R` alpha.
- Use the paper as validation governance for FinStressTS, HMM-WJ, dynamic CVaR,
  density-head, and any future synthetic scenario generator.
- Keep all synthetic scenario outputs research-only until they beat a
  size-matched null augmentation under walk-forward block-permutation testing.
- Keep `Golden1_0531` unchanged.

### 2512.02166

Imported:

- volatility-memory level gate
- volatility-memory shape / long-memory proxy
- volatility-memory tempo / business-time proxy
- separation of persistent volatility from transient bursts
- equity volatility memory can be regime- and tempo-dominated

Produced:

- `scripts/evaluate/evaluate_group_a_plus_trigate_vol_memory_shadow.py`
- `results/group_a_plus_trigate_vol_memory_shadow_20260717.json`
- `report/group_a_plus/latest/trigate_vol_memory_shadow.json`
- `docs/2512_02166_TRIGATE_VOL_MEMORY_GROUPA_PLUS_REVIEW_20260717.md`

Current output:

- `state = blocked_for_leverage_add`
- `stress_gate_count = 3`
- level gate active:
  - 00631L 20-day annualized volatility: `0.7395`
  - 252-day percentile: `0.9325`
- shape gate active:
  - memory shape score: `0.8211`
  - 252-day percentile: `0.9762`
- tempo gate active:
  - tempo score: `7.4887`
  - 252-day percentile: `1.0000`
- `allow_00631l_add = false`

Decision:

- Do not import the full TG-Vol / QMLE estimator.
- Do not import SPY / EURUSD parameters.
- Keep as a research-only volatility-memory shadow diagnostic.
- Do not change live allocation.
- Keep `Golden1_0531` unchanged.

### 2606.03184

Imported:

- mechanism-specific stress-test checklist before model promotion
- controlled counterfactual financial time-series idea
- probabilistic calibration review under known data-generating mechanisms
- data-efficiency / learning-curve requirement
- simple baseline before Transformer or density-head promotion
- failure attribution by financial mechanism

Produced:

- `scripts/evaluate/build_group_a_plus_finstressts_readiness_review.py`
- `scripts/evaluate/evaluate_group_a_plus_finstressts_counterfactual_shadow.py`
- `scripts/evaluate/evaluate_group_a_plus_finstressts_baseline_compare_shadow.py`
- `report/group_a_plus/latest/finstressts_readiness_review_20260720.json`
- `report/group_a_plus/latest/finstressts_readiness_review.json`
- `report/group_a_plus/finstressts_readiness/history/20260720.json`
- `results/group_a_plus_finstressts_counterfactual_shadow_20260717.json`
- `report/group_a_plus/latest/finstressts_counterfactual_shadow.json`
- `results/group_a_plus_finstressts_baseline_compare_shadow_20260717.json`
- `report/group_a_plus/latest/finstressts_baseline_compare_shadow.json`
- `report/group_a_plus/latest/finstressts_decision_snapshot.json`
- `scripts/run/run_ncf_daily_pipeline.py` now runs
  `finstressts_readiness_review` as a best-effort daily diagnostic.
- `scripts/run/run_ncf_daily_pipeline.py` now runs
  `finstressts_counterfactual_shadow` and
  `finstressts_baseline_compare_shadow` as best-effort daily diagnostics.
- `docs/2606_03184_FINSTRESSTS_GROUPA_PLUS_REVIEW_20260717.md`
- `docs/FINSTRESSTS_COUNTERFACTUAL_SHADOW_20260717.md`
- `docs/FINSTRESSTS_BASELINE_COMPARE_SHADOW_20260717.md`
- `docs/FINSTRESSTS_DECISION_SNAPSHOT_20260717.md`

Current output:

- `status = blocked`
- blocked mechanisms:
  - `heavy_tailed_shocks`
  - `self_exciting_jumps`
  - `zero_inflated_sparse_jumps`
  - `execution_under_stress`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- counterfactual shadow:
  - reference loses to no-`00631L`: `5 / 5` scenarios
  - reference tail failures: `4 / 5` scenarios
- baseline compare shadow:
  - best shadow candidate: `combined_vol_trend_gate`
  - wins versus no-`00631L`: `0 / 5`
  - tail failures improve from `4 / 5` to `1 / 5`, but still not promotable
- consolidated snapshot:
  - `status = blocked`
  - `allow_00631l_add = false`
- blocking reasons:
  - `live_signal_execution_not_allowed`
  - `rebalance_review_disallows_target_weight_change`
  - `option_state_gate_not_passed`
  - `adversarial_market_integrity_not_passed`
  - `market_impact_readiness_not_passed`
  - `optimizer_readiness_not_passed`
  - `mechanism_stress_coverage_blocked`

Decision:

- Do not import synthetic returns as live alpha.
- Do not use KDD benchmark rankings as Taiwan ETF evidence.
- Do not replace the current GroupA+ model stack.
- Keep as research-only model-validation readiness governance.
- Keep the first fixed-weight counterfactual stress harness as additional
  evidence against `00631L` add.
- Keep `combined_vol_trend_gate` as research-only follow-up candidate, not live.
- Keep `Golden1_0531` unchanged.

### 2603.29086

Imported:

- flat transaction costs can misrank strategies
- Almgren-Chriss / square-root impact readiness concept
- participation-of-volume monitoring
- turnover pathology detection
- trade-level logging requirement

Produced:

- `scripts/evaluate/build_group_a_plus_market_impact_readiness_review.py`
- `report/group_a_plus/latest/market_impact_readiness_review_20260720.json`
- `report/group_a_plus/latest/market_impact_readiness_review.json`
- `report/group_a_plus/market_impact_readiness/history/20260720.json`
- `scripts/run/run_ncf_daily_pipeline.py` now runs
  `market_impact_readiness_review` as a best-effort daily diagnostic.
- `docs/2603_29086_MARKET_IMPACT_GROUPA_PLUS_REVIEW_20260717.md`

Current output:

- `status = blocked`
- turnover: `0.5915811038461518`
- max participation of volume: `0.00022187708009762592`
- `target_weight_change_allowed = false`
- `allow_00631l_add = false`
- blocking reasons:
  - `live_signal_execution_not_allowed`
  - `execution_plan_stale_vs_live_signal`
  - `rebalance_review_disallows_auto_rebalance`
  - `turnover_exceeds_limit`

Decision:

- Do not import the Gymnasium/FinRL DRL environment.
- Do not use NASDAQ 100 RL results as Taiwan ETF evidence.
- Keep as pre-trade market-impact readiness governance.
- Keep `Golden1_0531` unchanged.

### 2607.15195

Imported:

- target-holding control as review abstraction
- explicit cumulative cost state
- turnover / capacity / price-impact checklist
- signal-quality requirement before optimizer claims
- offline single-sweep shadow governance idea

Produced:

- `scripts/evaluate/build_group_a_plus_sciphyrl_readiness_review.py`
- `report/group_a_plus/latest/sciphyrl_readiness_review_20260720.json`
- `report/group_a_plus/latest/sciphyrl_readiness_review.json`
- `report/group_a_plus/sciphyrl_readiness/history/20260720.json`
- `scripts/run/run_ncf_daily_pipeline.py` now runs
  `sciphyrl_readiness_review` as a best-effort daily diagnostic.
- `docs/2607_15195_SCIPHYRL_GROUPA_PLUS_REVIEW_20260717.md`

Current output:

- `status = blocked`
- `target_weight_change_allowed = false`
- `allow_00631l_add = false`
- blocking reasons:
  - `live_signal_execution_not_allowed`
  - `rebalance_review_disallows_target_weight_change`
  - `option_state_gate_not_passed`
  - `adversarial_market_integrity_not_passed`
  - `leverage_suitability_disallows_00631l_add`

Decision:

- Do not import the PINN/HJB optimizer.
- Do not use the engineered-oracle Sharpe results as GroupA+ evidence.
- Keep as research-only target-holding / explicit-cost readiness governance.
- Keep `Golden1_0531` unchanged.

### 2603.16035

Imported:

- heterogeneous volatility by source
- sparse regime thresholding
- heteroskedasticity verification
- manual review threshold tuning

Current best research threshold:

- `vol_window = 20`
- `percentile_window = 252`
- `crisis_source_min_count = 3`

Result:

- H10 precision improves from `57.8%` to `59.0%`.
- H10 FPR improves from `11.5%` to `10.6%`.
- Stress-window validation is mixed.

Decision:

- Keep as advisory.
- Do not promote to execution guard.
- Do not auto-reduce or auto-add `00631L`.

### 2512.12420

Imported:

- cost-aware overlay review
- position / notional limits
- rebalance cadence review
- option surface and macro state coverage gate
- deterministic replay / monitoring requirement

Produced:

- `scripts/evaluate/build_group_a_plus_deep_hedging_overlay_review.py`
- `report/group_a_plus/latest/deep_hedging_overlay_review_20260720.json`
- `scripts/evaluate/evaluate_deep_hedging_lite_overlay_shadow.py`
- `results/deep_hedging_lite_overlay_shadow_20260717.json`
- `scripts/evaluate/build_group_a_plus_option_state_coverage_review.py`
- `report/group_a_plus/latest/option_state_coverage_review.json`
- `report/group_a_plus/option_state_coverage/history/20260717.json`
- `report/group_a_plus/option_state_coverage/params/strict_20_10_20260717.json`
- `report/group_a_plus/option_state_coverage/params/warmup_10_5_20260717.json`
- `report/group_a_plus/option_state_coverage/params/floor_4_2_20260717.json`
- `scripts/run/run_ncf_daily_pipeline.py` now runs
  `option_state_coverage_review` as a best-effort daily diagnostic.
- `docs/2512_12420_DEEP_HEDGING_GROUPA_PLUS_REVIEW_20260717.md`

Current output:

- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `allow_00631l_add = false`
- blocking reasons:
  - `live_signal_execution_not_allowed`
  - `option_surface_state_incomplete`
  - `medium_high_or_high_risk_context`
  - `rebalance_review_disallows_00631l_add`
- deep-hedging-lite shadow:
  - beats golden1 proxy by STARR95: `1 / 4`
  - beats no-add by STARR95: `2 / 4`
  - `promote_to_live = false`
- option-state coverage review:
  - `status = blocked`
  - TXO option data is mostly available through `2026-07-16`
  - SOXX option snapshots are insufficient (`4` snapshots vs `20` required)
  - SOXX snapshot quality was improved by filtering near-zero placeholder IV
  - remaining blockers are SOXX history length / valid snapshot count

Decision:

- Do not import the SPX/SPY RL actor.
- Do not auto-execute a deep-hedging overlay.
- Keep only governance concepts for future research-only overlay review.
- Do not promote the simple Taiwan deep-hedging-lite rule.

### 2510.18990

Imported:

- forecast models treated as an attack surface
- sparse/small market-input perturbation sensitivity as a governance concern
- cross-check requirement before model-driven trading
- no single-model automatic execution
- future shadow tests for sparse perturbation and smoothing stability

Produced:

- `scripts/evaluate/build_group_a_plus_adversarial_market_integrity_review.py`
- `report/group_a_plus/latest/adversarial_market_integrity_review_20260720.json`
- `report/group_a_plus/latest/adversarial_market_integrity_review.json`
- `report/group_a_plus/adversarial_market_integrity/history/20260720.json`
- `scripts/run/run_ncf_daily_pipeline.py` now runs
  `adversarial_market_integrity_review` as a best-effort daily diagnostic.
- `docs/2510_18990_BLACK_TUESDAY_ATTACK_GROUPA_PLUS_REVIEW_20260717.md`

Current output:

- `status = blocked`
- `target_weight_change_allowed = false`
- `allow_00631l_add = false`
- blocking reasons:
  - `live_signal_execution_not_allowed`
  - `option_state_gate_not_passed`
  - `rebalance_review_disallows_target_weight_change`
  - `adversarial_robustness_state_incomplete`

Decision:

- Do not import attack construction or surrogate adversarial model.
- Do not change live allocation.
- Keep as pre-trade / research-only model-integrity governance.
- Keep `Golden1_0531` unchanged.

### 2605.12653

Imported:

- plan before trade
- preview before apply
- forecaster quality / freshness gate
- downside-risk penalty as review scoring
- candidate-plan comparison

Produced:

- `scripts/evaluate/build_group_a_plus_finpilot_lite_planning_review.py`
- `report/group_a_plus/latest/finpilot_lite_planning_review_20260720.json`

Current output:

- `forecast_quality_gate = failed`
- `downside_risk_gate = high`
- `recommended_plan_for_manual_review = no_00631l_add_or_wait_for_fresh_data`
- `auto_apply_allowed = false`

Decision:

- Do not import full FinPILOT.
- Do not run inference-time actor updates.
- Use only as planning preview.

### 2606.30037

Imported:

- output-head review before backbone replacement
- density forecast evaluation for fat-tailed returns
- CRPS / pinball / VaR breach / coverage diagnostics
- Gaussian residual head as current 00631L H20 tail-calibration baseline

Produced:

- `scripts/evaluate/evaluate_density_head_tail_risk_shadow.py`
- `scripts/evaluate/build_density_head_tail_risk_advisory.py`
- `scripts/evaluate/sweep_density_head_tail_risk_params.py`
- `report/group_a_plus/latest/density_head_tail_risk_advisory.json`

Current output:

- `best_by_crps = gaussian`
- `best_by_pinball_q05 = gaussian`
- `recommended_research_baseline = gaussian_residual_head`
- parameter sweep rows: `30`
- `gaussian_wins_crps = 30 / 30`
- `gaussian_wins_pinball_q05 = 30 / 30`
- `gmm_wins_crps = 0 / 30`
- crash-window sweep:
  - 2018 correction: Gaussian wins CRPS / q05 pinball `30 / 30`
  - 2020 COVID: Gaussian wins CRPS / q05 pinball `30 / 30`
  - 2026 recent: GMM wins CRPS `30 / 30`, q05 pinball `6 / 30`
- 2022 rate-hike backfill:
  - new NCF panel: `results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv`
  - GMM wins CRPS `30 / 30`
  - GMM wins q05 pinball `24 / 30`
  - best GMM candidate: `gmm_components=2`, `alert_quantile=0.10`, `seed=42`
- multi-window promotion review:
  - `promote_to_live = false`
  - aggregate GMM CRPS win rate: `40.0%`
  - aggregate GMM q05 win rate: `20.0%`
  - required crash failures: `2018_correction`, `2020_covid`
- `promote_to_live = false`

Decision:

- Do not import GMM as a live trigger.
- Do not replace NCF backbone.
- 2022 backfill improves GMM evidence, but 2018 / 2020 crash windows still
  block live promotion.
- Use density-head diagnostics only for research / promotion review.

### 2606.30997

Imported:

- cash is an active allocation / risk buffer
- allocation-driven rebalance threshold
- redeployment-aware turnover review
- objective-conditioned review labels
- trust-first preview before apply

Produced:

- `scripts/evaluate/build_group_a_plus_rebalance_review.py`
- `report/group_a_plus/latest/rebalance_review_20260720.json`
- `docs/GROUPA_PLUS_REBALANCE_REVIEW_20260720_DECISION_RECORD.md`

Current output:

- `auto_rebalance_allowed = false`
- `manual_review_required = true`
- `allow_00631l_add = false`
- `target_weight_change_allowed = false`

Decision:

- Do not import Chronos / DRL / MoE.
- Do not import tax-aware LoRA personalization.
- Use only execution-governance concepts.

## 7/20 Unified Decision

Latest full-pipeline final decision record:

- `docs/GROUPA_PLUS_20260720_FULL_PIPELINE_FINAL_DECISION_RECORD.md`

Inputs:

- `report/group_a_plus/latest/live_signal_20260720_estimate.json`
- `results/group_a_plus_live_signal_v2_20260720.json`
- `results/group_a_plus_daily_status_20260720.json`
- `report/group_a_plus/latest/rebalance_review_20260720.json`
- `report/group_a_plus/latest/finpilot_lite_planning_review_20260720.json`
- `report/group_a_plus/latest/heterogeneous_vol_regime_advisory.json`
- `report/group_a_plus/latest/density_head_tail_risk_advisory.json`
- `report/group_a_plus/latest/deep_hedging_overlay_review_20260720.json`
- `report/group_a_plus/latest/finstressts_readiness_review_20260720.json`
- `report/group_a_plus/latest/trigate_vol_memory_shadow.json`
- `report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json`
- `report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json`
- `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

Blocking reasons:

- After the full 2026-07-20 pipeline refresh, `execution_allowed = true` and
  `source_freshness = ok`; the earlier stale `institutional_0050` and NCF panel
  mismatch blockers were resolved.
- Daily status remains `warn` because the 2026-07-20 check date uses latest
  market data from `2026-07-17`.
- heterogeneous volatility advisory is high.
- FinPILOT-lite forecast quality / freshness gate failed.
- density-head tail-risk advisory is research-only and does not permit auto-add.
- deep-hedging overlay review blocks 00631L add because execution is not
  allowed, option-state features are incomplete, and risk context is
  medium-high.
- FinStressTS readiness review blocks model-promotion claims because heavy-tail,
  jump-cluster, sparse-jump, and execution-under-stress coverage is incomplete.
- Tri-gate volatility-memory shadow blocks leverage add because level, shape,
  and tempo gates are all active.
- Systemic bubble time-at-risk review blocks leverage add.
- HMM-WJ synthetic scenario readiness is blocked because the scenario generator
  and Taiwan ETF walk-forward validation are not decision-ready.
- Dynamic CVaR tail/cost readiness is blocked because 00631L tail diagnostics
  remain heavy-tailed, density GMM is research-only/unstable, market-impact and
  rebalance reviews disallow execution, and no validated dynamic optimizer
  exists.
- Deployment consistency remains `manual_review_required`.
- Promotion gate remains `blocked_multi_window`.

Unified output:

- `auto_rebalance_allowed = false`
- `manual_review_required = true`
- `allow_00631l_add = false`
- `target_weight_change_allowed = false`
- `active_allocation_impact = none`

## Files Created / Updated

Review docs:

- `docs/HETEROGENEOUS_VOL_REGIME_SHADOW_20260717.md`
- `docs/GROUPA_PLUS_HETEROGENEOUS_VOL_PARAM_TUNING_RECORD_20260717.md`
- `docs/2512_12420_DEEP_HEDGING_GROUPA_PLUS_REVIEW_20260717.md`
- `docs/HANDOFF_2512_12420_DEEP_HEDGING_GROUPA_PLUS_20260717.md`
- `docs/2605_12653_FINPILOT_GROUPA_PLUS_REVIEW_20260717.md`
- `docs/2606_30037_HEADS_NOT_BACKBONES_GROUPA_PLUS_REVIEW_20260717.md`
- `docs/GROUPA_PLUS_NCF_GMM_BACKFILL_20260717.md`
- `docs/2606_30997_TAX_AWARE_PORTFOLIO_FM_GROUPA_PLUS_REVIEW_20260717.md`
- `docs/GROUPA_PLUS_REBALANCE_REVIEW_20260720_DECISION_RECORD.md`
- `docs/2606_03184_FINSTRESSTS_GROUPA_PLUS_REVIEW_20260717.md`
- `docs/2512_02166_TRIGATE_VOL_MEMORY_GROUPA_PLUS_REVIEW_20260717.md`
- `docs/HANDOFF_2512_02166_TRIGATE_VOL_MEMORY_GROUPA_PLUS_20260717.md`
- `docs/1212_2833_PERPETUAL_MONEY_MACHINE_GROUPA_PLUS_REVIEW_20260718.md`
- `docs/HANDOFF_1212_2833_SYSTEMIC_BUBBLE_TIME_AT_RISK_GROUPA_PLUS_20260718.md`
- `docs/2603_10202_HMM_WJ_SYNTHETIC_SCENARIO_GROUPA_PLUS_REVIEW_20260718.md`
- `docs/HANDOFF_2603_10202_HMM_WJ_SYNTHETIC_SCENARIO_GROUPA_PLUS_20260718.md`
- `docs/2606_26625_COMMODITY_ETF_CVAR_TAIL_RISK_GROUPA_PLUS_REVIEW_20260718.md`
- `docs/HANDOFF_2606_26625_COMMODITY_ETF_CVAR_TAIL_COST_GROUPA_PLUS_20260718.md`
- `docs/2604_14498_SYNTHETIC_AUGMENTATION_VALIDATION_GROUPA_PLUS_REVIEW_20260718.md`
- `docs/HANDOFF_2604_14498_SYNTHETIC_AUGMENTATION_VALIDATION_GROUPA_PLUS_20260718.md`
- `docs/GROUPA_PLUS_20260720_FULL_PIPELINE_FINAL_DECISION_RECORD.md`

Scripts:

- `scripts/evaluate/evaluate_heterogeneous_vol_regime_shadow.py`
- `scripts/evaluate/sweep_heterogeneous_vol_regime_params.py`
- `scripts/evaluate/build_heterogeneous_vol_regime_advisory.py`
- `scripts/evaluate/build_group_a_plus_rebalance_review.py`
- `scripts/evaluate/build_group_a_plus_finpilot_lite_planning_review.py`
- `scripts/evaluate/build_group_a_plus_deep_hedging_overlay_review.py`
- `scripts/evaluate/evaluate_deep_hedging_lite_overlay_shadow.py`
- `scripts/evaluate/build_group_a_plus_option_state_coverage_review.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `scripts/evaluate/build_density_head_tail_risk_advisory.py`
- `scripts/evaluate/sweep_density_head_tail_risk_params.py`
- `scripts/evaluate/build_density_head_tail_risk_promotion_review.py`
- `scripts/evaluate/build_group_a_plus_finstressts_readiness_review.py`
- `scripts/evaluate/evaluate_group_a_plus_trigate_vol_memory_shadow.py`
- `scripts/evaluate/evaluate_group_a_plus_systemic_bubble_time_at_risk_review.py`
- `scripts/evaluate/build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review.py`
- `scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py`
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `scripts/misc/check_group_a_plus_daily_status.py`

Latest artifacts:

- `report/group_a_plus/latest/heterogeneous_vol_regime_advisory.json`
- `report/group_a_plus/latest/rebalance_review_20260720.json`
- `report/group_a_plus/latest/finpilot_lite_planning_review_20260720.json`
- `report/group_a_plus/latest/density_head_tail_risk_advisory.json`
- `report/group_a_plus/latest/density_head_tail_risk_promotion_review.json`
- `report/group_a_plus/latest/deep_hedging_overlay_review_20260720.json`
- `report/group_a_plus/latest/option_state_coverage_review.json`
- `report/group_a_plus/latest/finstressts_readiness_review_20260720.json`
- `report/group_a_plus/latest/finstressts_readiness_review.json`
- `report/group_a_plus/latest/trigate_vol_memory_shadow.json`
- `results/group_a_plus_trigate_vol_memory_shadow_20260717.json`
- `report/group_a_plus/latest/systemic_bubble_time_at_risk_review.json`
- `report/group_a_plus/systemic_bubble_time_at_risk/history/20260717.json`
- `report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json`
- `report/group_a_plus/hmm_wj_synthetic_scenario_readiness/history/20260717.json`
- `report/group_a_plus/latest/dynamic_cvar_tail_cost_readiness_review.json`
- `report/group_a_plus/dynamic_cvar_tail_cost_readiness/history/20260720.json`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`
- `results/group_a_plus_daily_status_20260720_dynamic_cvar.json`
- `results/group_a_plus_daily_status_20260720_dynamic_cvar.md`
- `results/ncf_daily_pipeline_20260720.json`
- `results/group_a_plus_live_signal_v2_20260720.json`
- `results/group_a_plus_daily_status_20260720.json`
- `results/group_a_plus_promotion_gate_20260720.json`
- `results/group_a_plus_daily_status_20260720_research_shadow_smoke.json`
- `results/group_a_plus_daily_status_20260720_research_shadow_smoke.md`
- `results/group_a_plus_daily_status_20260720_research_shadow_summary_smoke.json`
- `results/group_a_plus_daily_status_20260720_research_shadow_summary_smoke.md`

## Final Position

The PDF research improves review quality and execution governance, not live allocation.

Before any real 7/20 trade:

1. Refresh required source data.
2. Rebuild NCF panels and live signal.
3. Rebuild execution plan from fresh holdings/prices.
4. Re-run rebalance review and FinPILOT-lite planning review.
5. Execute only after manual confirmation.

Until then:

- keep GroupA+ latest strategy unchanged;
- keep `Golden1_0531` unchanged;
- do not auto-rebalance;
- do not auto-add `00631L`.
