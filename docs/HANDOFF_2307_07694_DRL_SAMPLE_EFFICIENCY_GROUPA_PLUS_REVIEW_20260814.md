# HANDOFF - 2307.07694 DRL Sample Efficiency for GroupA+

Date: 2026-08-14  
PDF: `C:\Users\isaac\Downloads\2307.07694.pdf`  
Paper: `Evaluation of Deep Reinforcement Learning Algorithms for Portfolio Optimisation`  
arXiv: `2307.07694v3`  
Paper date shown in PDF: 2025-08-07  

## Status

Reviewed and converted into a research-only readiness review.

No live strategy change was made.

- `golden1_0531`: unchanged
- GroupA+ latest strategy: unchanged
- A21.18/a2118 decision rule: unchanged
- live signal: unchanged
- execution plan: unchanged
- orders: unchanged

Decision: do not import a DRL allocator into GroupA+ latest strategy. Borrow
only governance and execution-risk concepts.

## Paper Summary

The paper evaluates common deep reinforcement learning algorithms for portfolio
optimisation in a simulated market.

Setup:

- simulated correlated GBM price process;
- Bertsimas-Lo market impact model;
- optional regime switching through a continuous-time Markov chain;
- 3 risky assets plus cash;
- continuous portfolio weights;
- Kelly/log utility objective;
- Stable Baselines 3 implementations of A2C, PPO, DDPG, TD3, and SAC.

Main findings:

- off-policy algorithms (`DDPG`, `TD3`, `SAC`) struggled under noisy rewards
  because the critic/Q-function did not learn the right value surface;
- on-policy methods (`PPO`, `A2C`) were more stable;
- `PPO` with GAE and clipping was the strongest tested method;
- `PPO` still required roughly `2m` simulator steps in the simplest low-impact
  setting, which the paper translates to nearly `8,000` years of daily data;
- under high market impact, learned policies moved toward fractional Kelly-like
  exposure reduction;
- in regime switching, adding HMM regime context helped PPO learn distinct
  regime policies, but high-impact runs remained mixed and noisy.

## GroupA+ Applicability

High-risk parts not imported:

- no `PPO` allocator;
- no `A2C`, `DDPG`, `TD3`, or `SAC` allocator;
- no GBM/Bertsimas-Lo simulator used for live training;
- no HMM context network for live target weights;
- no shorting or levered Kelly weight import;
- no automatic target weight change;
- no automatic rebalance.

Useful concepts for GroupA+:

- live DRL should remain blocked unless sample-efficiency and noisy-reward
  diagnostics are satisfied;
- off-policy RL should be low priority for GroupA+ allocation because the paper
  shows noisy reward Q-function failure;
- market impact and transaction cost must be part of any RL promotion gate;
- fractional/staged adjustment is a valid execution primitive when market
  impact is material;
- regime context can be useful, but only as validated shadow context before it
  changes weights.

## Local Fit Check

Current GroupA+ already has several mechanisms aligned with the paper:

- staged buy execution through `_apply_buy_staging`;
- `max_initial_buy_fraction` control;
- transaction cost logging in execution planning;
- market-impact readiness review;
- RL governance readiness review;
- live exploration forbidden through governance.

Current blockers:

- market-impact readiness is currently `blocked`;
- RL governance readiness is currently `blocked`;
- real Taiwan ETF history cannot satisfy the paper's simulator-scale sample
  requirement;
- no validated resettable Taiwan ETF market simulator exists for live RL
  training;
- no local noisy-reward Q-function diagnostic exists for off-policy RL.

## What Was Added

Research-only readiness builder:

- `scripts/evaluate/build_group_a_plus_drl_sample_efficiency_readiness_review.py`

Test:

- `tests/test_build_group_a_plus_drl_sample_efficiency_readiness_review.py`

Outputs:

- `report/group_a_plus/latest/drl_sample_efficiency_readiness_review.json`
- `report/group_a_plus/latest/drl_sample_efficiency_readiness_review.md`
- `report/group_a_plus/drl_sample_efficiency_readiness/history/drl_sample_efficiency_readiness_20260814.json`

## Commands Run

Extracted PDF text with local `pypdf`:

```bash
.venv/bin/python -c "from pypdf import PdfReader; p='/mnt/c/Users/isaac/Downloads/2307.07694.pdf'; r=PdfReader(p); print('pages', len(r.pages)); open('/tmp/2307_07694.txt','w',encoding='utf-8').write('\n\n'.join((page.extract_text() or '') for page in r.pages))"
```

Syntax check:

```bash
.venv/bin/python -m py_compile \
  scripts/evaluate/build_group_a_plus_drl_sample_efficiency_readiness_review.py
```

Readiness review:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_drl_sample_efficiency_readiness_review.py \
  --as-of 2026-08-14
```

Unit test:

```bash
.venv/bin/python -m pytest \
  tests/test_build_group_a_plus_drl_sample_efficiency_readiness_review.py -q
```

Production pointer check:

```bash
git diff -- \
  report/group_a_plus/latest/strategy.json \
  report/group_a_plus/latest/live_signal.json \
  report/group_a_plus/latest/execution_plan.json
```

Expected output: no diff.

## Readiness Result

Latest output:

- status: `blocked`
- `drl_allocator_promotable`: `false`
- `target_weight_change_allowed`: `false`
- `auto_rebalance_allowed`: `false`
- `keep_golden1_0531_unchanged`: `true`

Local checks:

- market impact status: `blocked`;
- RL governance status: `blocked`;
- staged buys present: `true`;
- buy fraction control present: `true`;
- transaction cost logging present: `true`.

Blocking reasons:

- `market_impact_readiness_blocked`;
- `rl_governance_readiness_blocked`;
- `paper_sample_efficiency_requirement_not_satisfied_by_real_market_history`;
- `no_local_resettable_market_simulator_validated_for_training_live_rl`;
- `no_noisy_reward_q_function_diagnostic_for_off_policy_rl`.

## Import Decision

Do not import this paper into GroupA+ latest strategy as a trading model.

Reasons:

- the paper itself argues that DRL sample complexity is too high for real
  financial data without a resettable simulator;
- off-policy methods failed in the noisy reward setting;
- on-policy PPO/A2C did better but still needed unrealistic simulator data;
- GroupA+ already has more transparent staged execution and regime/risk guards;
- current market-impact and RL-governance reviews are blocked.

Safe to borrow:

- use this as an explicit blocker for live DRL allocator promotion;
- keep fractional/staged execution controls;
- require market-impact-aware training and evaluation before any RL import;
- require a noisy-reward Q-function diagnostic for off-policy methods;
- require regime-context validation before using HMM/RL context in live weights.

Not safe to borrow:

- live PPO/A2C/DDPG/TD3/SAC allocator;
- simulator-trained weights as live target weights;
- shorting or levered Kelly weights;
- any automatic rebalance triggered by this paper.

## Verification

- `py_compile` passed.
- Unit test passed: `1 passed`.
- Production pointer diff had no output.

Final decision: research/governance only; no latest strategy import.

## GBM Stress-Test Follow-Up

Follow-up question: does GBM have any direct practical value?

Answer: yes, but only as a repeatable execution stress-test environment. It is
not an alpha source and should not generate GroupA+ target weights.

Added a GBM + market-impact staging shadow:

- `scripts/evaluate/evaluate_2307_07694_gbm_market_impact_staging_shadow.py`
- `tests/test_evaluate_2307_07694_gbm_market_impact_staging_shadow.py`

The script reads the current latest execution plan and compares:

- `full_day0`: move immediately to `theoretical_target_shares`;
- `staged_then_full`: move first to `staged_target_shares_before_guards`, then
  finish the deferred buy after `5` days.

It uses GBM paths only as synthetic stress paths. Cost model:

- commission;
- slippage;
- sell tax for equity ETFs;
- Bertsimas-Lo-inspired convex impact term where large one-shot notional costs
  more than split execution.

Commands:

```bash
.venv/bin/python -m py_compile \
  scripts/evaluate/evaluate_2307_07694_gbm_market_impact_staging_shadow.py
```

```bash
.venv/bin/python -m pytest \
  tests/test_evaluate_2307_07694_gbm_market_impact_staging_shadow.py -q
```

Default impact stress:

```bash
.venv/bin/python scripts/evaluate/evaluate_2307_07694_gbm_market_impact_staging_shadow.py
```

Low-impact sensitivity:

```bash
.venv/bin/python scripts/evaluate/evaluate_2307_07694_gbm_market_impact_staging_shadow.py \
  --impact-scale 0.3 \
  --output-json results/2307_07694_gbm_market_impact_staging_shadow_impact03.json \
  --output-md report/group_a_plus/latest/2307_07694_gbm_market_impact_staging_shadow_impact03.md
```

Default stress result, `impact_scale=3.0`, `2000` paths:

| Scenario | Mean final delta, staged-full | P05 final delta | Mean cost delta | Staged final win rate |
|---|---:|---:|---:|---:|
| neutral | +38,763 | +25,459 | -39,509 | 1.000 |
| bull | +38,707 | +25,108 | -39,509 | 1.000 |
| bear | +40,790 | +25,210 | -39,688 | 1.000 |
| high-vol flat | +38,857 | +12,443 | -39,496 | 0.988 |

Low-impact sensitivity, `impact_scale=0.3`, `2000` paths:

| Scenario | Mean final delta, staged-full | P05 final delta | Mean cost delta | Staged final win rate |
|---|---:|---:|---:|---:|
| neutral | +3,208 | -9,111 | -3,955 | 0.672 |
| bull | +3,152 | -9,516 | -3,955 | 0.666 |
| bear | +5,078 | -9,382 | -3,976 | 0.719 |
| high-vol flat | +3,315 | -21,241 | -3,954 | 0.597 |

Interpretation:

- GBM confirms the value of staged execution under convex market impact;
- lower impact assumptions reveal the real tradeoff: staging saves cost but can
  lose to full execution on some paths due opportunity cost;
- this supports keeping `staged_buys` and `max_initial_buy_fraction` as
  execution controls;
- it does not support GBM-driven return forecasts or target weights.

Additional outputs:

- `results/2307_07694_gbm_market_impact_staging_shadow.json`
- `report/group_a_plus/latest/2307_07694_gbm_market_impact_staging_shadow.md`
- `results/2307_07694_gbm_market_impact_staging_shadow_impact03.json`
- `report/group_a_plus/latest/2307_07694_gbm_market_impact_staging_shadow_impact03.md`

Updated final decision:

- import GBM only as an execution stress-test framework;
- do not import GBM as alpha, forecast, or allocation source;
- no latest strategy, live signal, execution plan, or order file was changed.
