# GroupA+ 2026-08-24 Handoff: arXiv:2607.00475 (End-to-End Parametric Portfolio Policies) — Three-Angle Review

## Status

`closed_negative` on the paper's main framework, `closed_negative` on the
temporal-memory sub-mechanism, `shadow_advisory` on the seed-averaging
sub-mechanism. No production code changed. `train_dual_group_2024_2026.py`
and `models/portfolio/last_ppo_group_a_100k.zip` were never touched.

**Important context**: a portion of this work (the temporal-memory /
RecurrentPPO angle) was already in progress from an EARLIER, UNCOMMITTED
same-day session before this session started — its scripts and one
completed result file existed in the working tree but were not indexed in
`group_a_plus/research_semantic_registry.json` or in `~/.claude/.../memory/`
at the time this session began. This session found it by grepping the
working tree, not by memory/registry search. **Lesson**: "not found in
registry/memory" is not proof "nobody has tried this" — always also check
uncommitted working-tree state (`git status --short`, `find -newer`) before
concluding a paper is unexplored, especially the same day.

---

## Paper Summary

Pollok & Robik, "End-to-End Parametric Portfolio Policies for Cross-Asset
Futures Timing: When Do AI Models Beat Simple Rules?" (arXiv:2607.00475,
2026-07-01). Trains a Transformer and an LSTM to map market state directly
to portfolio weights via a differentiable Sharpe-ratio loss, on the 16 most
liquid CME futures across 6 asset classes, benchmarked against equal
weight, risk parity, and TSMOM. Findings (paper's own, honestly qualified):

- Learned policies rank above simple rules on the pooled cross-asset
  portfolio and in several sleeves, but **not uniformly** — equal weighting
  is hard to beat in long-biased trending markets (equity index, energy).
- Edge is strongest where there is **breadth across near-orthogonal
  contracts** to exploit (within-asset-class daily-return correlation 0.67,
  cross-class 0.05). Single-asset-class sleeves (2-4 contracts) show the
  smallest gains.
- The only Bonferroni-corrected-significant result (equity index) is, on
  α/β decomposition, mostly market exposure (β) not residual alpha.
- Section V-D: **seed averaging is the only enhancement that reliably
  helped** in their tests. Mixture-of-experts, larger feature sets,
  per-class tuning, and cross-model (Transformer+LSTM) ensembling did not.
- The Transformer trades far less than the LSTM (turnover ~0.02/day vs
  0.07-0.17/day) and is much less eroded by realistic transaction costs.

---

## Angle 1: Main Framework — Desk Review, `closed_negative`

Group A+'s core mechanism is a 0050/00631L regime switch: structurally a
**single-asset-class sleeve** (smaller than the paper's smallest, 2-4
contracts). The paper's own evidence is that its technique's edge comes
almost entirely from breadth across a wide, near-orthogonal cross-section —
which does not exist here. This is consistent with, and further explained
by, [[project_2607_19497_trend_following_acf_sharpe_20260823]] and the
CHMM regime-detector finding from 2026-08-23: 0050/00631L's Sharpe is
almost entirely attributable to their own strong drift, not exploitable
serial/cross-sectional structure — the exact failure mode the paper itself
attributes to markets that "drift upward over the sample" (Section V-E).

No backtest was run for this angle — the universe-size mismatch is
sufficient to close it on inspection, matching prior desk-review closures
this month (e.g. 2607.24410, 2608.20020) for the same class of reason
(technique requires cross-sectional breadth Group A+'s asset pool doesn't
have).

---

## Angle 2: Temporal-Memory Mechanism (RecurrentPPO) — Hands-On, `closed_negative`

### What the earlier, uncommitted session had already done

Two scripts existed in the working tree before this session started:

- `scripts/misc/train_a2118_ppo_recurrent_lstm_experiment_2607_00475.py`
  (single-env RecurrentPPO, mtime 2026-08-23 23:47) — **completed**, result
  saved at
  `results/a2118_ppo_recurrent_lstm_experiment_2607_00475_1787511431.json`.
  Trains `sb3_contrib.RecurrentPPO` with `MlpLstmPolicy` in place of SB3's
  `PPO`+`MlpPolicy` (the architecture every prior a2118 PPO experiment this
  month used), same env/tickers/windows/hyperparameters, three seeds
  (42, 43, 44), 100k timesteps, custom backtest loop that correctly threads
  `lstm_states`/`episode_start` through `model.predict()` (the shared
  `_backtest_group` helper would silently reset the LSTM state every step
  and defeat the whole point).

  **Result**: all three seeds produced byte-identical backtest metrics
  (Sharpe 1.8400453545522812 to 16 significant figures, MDD -36.150...%,
  94 trades, std=0.0 across seeds) — despite genuinely different,
  independently-timed training runs (4148s / 4093s / 2991s). The script's
  own follow-up docstring records that this was diagnosed (not assumed) as
  **recurrent state collapse**: direct inspection of the policy's action
  distribution showed it saturates to a near-fixed point within the first
  few steps of a rollout and stops responding to the market-state input —
  independent of seed and of training budget (300 vs 100k steps gave the
  same fixed point). This is a documented sb3-contrib failure mode for
  RecurrentPPO trained on a single long, highly autocorrelated environment
  sequence (the standard fix, per sb3-contrib's own docs: train on multiple
  decorrelated parallel environments instead).

- `scripts/misc/train_a2118_ppo_recurrent_lstm_multienv_experiment_2607_00475.py`
  (8-env `DummyVecEnv` decorrelated training, mtime 2026-08-24 08:17) — the
  fix attempt, per sb3-contrib's own recommendation. `n_steps` reduced from
  1024 to 128 so total rollout buffer size (`n_steps * n_envs = 1024`)
  matches the single-env attempt exactly, isolating "many short decorrelated
  sequences vs one long sequence" as the only structural change. **Left
  incomplete**: only `models/portfolio/experiment_recurrentlstm_multienv_baseline_seed42.zip`
  existed (seed 42 trained; seeds 43/44 never run, no results JSON).

### What this session did

Rather than blindly re-running the (expensive, ~70-100 min/seed) multi-env
training script from scratch, this session first loaded the **already-
trained** seed42 multi-env checkpoint (no retraining) and re-ran the same
policy-distribution probe used to diagnose the original collapse, on the
real 2024-01-01..2026-05-08 backtest panel, threading real `lstm_states`.

**Result**: the multi-env fix did **not** resolve the problem. It produced
a *different* but equally broken failure mode: the action-probability
distribution reaches a static fixed point by step ~5 and never moves again
through step 29, but this time the fixed point is **near-uniform**
(`[0.204, 0.201, 0.206, 0.196, 0.194]` — barely above 1/5 chance for a
5-action space) rather than confidently concentrated on one action. Same
qualitative failure (an LSTM hidden state that becomes an input-insensitive
attractor), different flavor (uninformative-static instead of
confident-static).

**Decision**: training seeds 43/44 for the multi-env variant was
**deliberately skipped**. Both prior training designs (single long
sequence; 8 parallel decorrelated sequences) already independently produced
the same qualitative failure across their available seeds, at a training
cost of ~70-100 minutes per additional seed for very low expected
information gain. Documented as a diagnostic closure, not a full 5-seed
sweep:
`results/a2118_ppo_recurrent_lstm_multienv_experiment_2607_00475_diagnostic_closure.json`.

### Conclusion

`closed_negative`. This closes the paper's temporal-memory claim (that
giving a policy real memory reduces turnover and improves cost-
survivability) as untestable on a2118 Last PPO with the current setup:
RecurrentPPO never learns to use temporal memory at all here, under either
training design tried.

---

## Angle 3: Seed-Output Averaging (Section V-D) — Hands-On, `shadow_advisory`

### Method

New script: `scripts/misc/eval_a2118_ppo_seed_averaging_ensemble_2607_00475.py`
(inference-only, no retraining, ~2s to run). Loads the three ALREADY-
TRAINED baseline checkpoints from the 2026-08-22 finegrained-action
experiment (`experiment_finegrained_baseline_seed{42,43,44}.zip` — plain
SB3 `PPO`+`MlpPolicy`, default action schema, 100k timesteps, no hidden
state to collapse, so unaffected by Angle 2's failure). At each backtest
day, queries all loaded models' categorical action-probability
distributions on the same observation
(`model.policy.get_distribution(obs).distribution.probs`), averages them
elementwise, takes the ensemble's argmax as the day's action, and steps a
single shared, **unmodified** `PortfolioEnv` — this reuses the env's
existing turnover-gate/risk-gate/PVA/inverse-hedge logic exactly as every
prior PPO experiment did, rather than reimplementing it for a
continuous-weight blend (which the paper's own technique would literally
be, but Group A+'s policy is discrete-action, not continuous-weight).

### First-pass result (single 2024-01-01..2026-05-08 window)

| | Sharpe | MDD | Trades |
|---|---|---|---|
| seed42 | 1.916 | -29.42% | 80 |
| seed43 | 1.966 | -29.47% | 71 |
| seed44 | 1.952 | -30.23% | 85 |
| **3-seed ensemble** | **1.964** | **-28.83%** | 71 |

Ensemble MDD beat all 3 individual seeds; Sharpe nearly matched the best
individual (seed43). 56% of backtest days (316/564) showed the three seeds
disagreeing on argmax action, confirming the ensemble is resolving real
per-step disagreement, not just reproducing one dominant seed.

Result file:
`results/a2118_ppo_seed_averaging_ensemble_2607_00475_1787545811.json`.

### Robustness check 1: sub-period split (2024 vs 2025-2026)

New script: `scripts/misc/eval_a2118_ppo_seed_averaging_robustness_2607_00475.py`.
Splits the same backtest window's equity curve by calendar date and
recomputes metrics per sub-period (own baseline `initial_value` per
segment, not carried over from the full-window start).

| | 2024 Sharpe | 2024 MDD | 2025-26 Sharpe | 2025-26 MDD |
|---|---|---|---|---|
| seed42 | 1.459 | -25.75% | 2.259 | -28.61% |
| seed43 | 1.491 | -26.31% | 2.326 | -27.49% |
| seed44 | 1.486 | -26.31% | 2.302 | -28.62% |
| **3-seed ensemble** | **1.518** | -26.31% | 2.303 | -27.49% |

**The full-window "ensemble MDD beats every individual seed" claim does
NOT hold uniformly once split by sub-period**: in 2024, ensemble MDD ties
seed43/44 but loses to seed42 (-25.75%, the best of the four in that
sub-period). The full-window MDD advantage looks like an artifact of how
the two sub-periods' drawdown paths combine, not an independently-true
property of each sub-period. The claim that DOES hold: ensemble Sharpe is
best-of-four in 2024 and second-best (barely behind seed43) in 2025-26 —
**it never lands in "worst of the group" territory in either sub-period**,
which is the actual property worth having (protection from drawing a bad
seed), not "dominates every metric everywhere."

Result file:
`results/a2118_ppo_seed_averaging_robustness_2607_00475_1787548594.json`.

### Robustness check 2: does adding more seeds help (paper's own claim: no)

New script: `scripts/misc/train_a2118_ppo_baseline_extra_seeds_2607_00475.py`
trained two more baseline checkpoints with the **identical** recipe
(`experiment_finegrained_baseline_seed{45,46}.zip`, ~254s each):

- seed45: Sharpe 1.818, MDD **-36.05%** — a genuine bad seed, well outside
  the original 42/43/44 range.
- seed46: Sharpe 1.895, MDD -30.81%.

Re-ran the robustness script with all 5 seeds:

| Ensemble | Full Sharpe | Full MDD | Trades | 2024 Sharpe | 2025-26 Sharpe |
|---|---|---|---|---|---|
| {42,43,44} | 1.964 | -28.83% | 71 | 1.518 | 2.303 |
| {42,43,44,45} | 1.974 | -28.83% | 75 | 1.518 | 2.319 |
| {42,43,44,45,46} | 1.966 | -29.43% | 73 | 1.472 | **2.341** |

Even with a genuine bad seed (45, solo MDD -36.05%) mixed in, the 5-seed
ensemble's MDD only degrades to -29.43% — far short of seed45's own
-36.05%, and better than 3 of the 5 individual seeds (44, 45, and
matching/beating seed46's -30.81%). Full-window Sharpe stays in a narrow
1.964-1.974 band across 3/4/5-seed ensembles, consistent with the paper's
own Section V-D finding that adding seeds beyond 3 "did not materially
change the results." Sub-period detail is more mixed: the 5-seed
ensemble's 2024 Sharpe (1.472) is no longer best-of-group (diluted by
45/46, though still within the individual seeds' 1.459-1.491 band, not
outside it), while its 2025-26 Sharpe (2.341) becomes the single best
result of any individual seed or ensemble in that sub-period.

Result file:
`results/a2118_ppo_seed_averaging_robustness_2607_00475_1787554541.json`.

### Verified conclusion

The claim that survives robustness checking is **narrower but real**: seed
averaging protects against the tail risk of landing on a bad seed (the
seed45 case demonstrates this directly — solo MDD -36.05%, diluted to
~-29% inside any ensemble containing it) without giving up much upside
(ensemble Sharpe stays close to the pack's better end across all tested
compositions). It does **not** reliably dominate every individual seed on
every metric in every sub-period — that stronger claim, which the
first-pass single-window result suggested, did not survive the sub-period
split.

This directly targets a real, repeatedly observed problem this month:
multiple prior PPO architecture/feature experiments (HNN extractor,
volatility features, finegrained action space, the 500k-timestep budget
characterization) all showed 6-7.4x inflated cross-seed MDD variance
without a corresponding mean improvement. Seed averaging is a candidate
low-cost mitigation that requires **no architecture change** — only
inference-time averaging of checkpoints that already exist or are cheap to
train (~4-7 min per baseline seed).

**Status: `shadow_advisory`, not promotion-ready.** Before any shadow-track
consideration:
1. Test on a genuinely out-of-sample window, not a sub-split of the single
   window every PPO experiment this month has shared.
2. Check whether the ensembling mechanism transfers to the other PPO
   variants tried this month (finegrained action space, HNN extractor,
   volatility features) — this was only tested on the plain default-schema
   baseline.
3. Consider whether ensembling should apply to whatever variant eventually
   becomes the production Last PPO candidate, not the current baseline in
   isolation.

---

## Files Touched This Session

New (all uncommitted, all in `experiment_`/`scripts/misc/*_2607_00475*`
namespaces, none touch production paths):

- `scripts/misc/eval_a2118_ppo_seed_averaging_ensemble_2607_00475.py`
- `scripts/misc/eval_a2118_ppo_seed_averaging_robustness_2607_00475.py`
- `scripts/misc/train_a2118_ppo_baseline_extra_seeds_2607_00475.py`
- `results/a2118_ppo_recurrent_lstm_multienv_experiment_2607_00475_diagnostic_closure.json`
- `results/a2118_ppo_seed_averaging_ensemble_2607_00475_1787545811.json`
- `results/a2118_ppo_seed_averaging_robustness_2607_00475_1787548594.json`
- `results/a2118_ppo_seed_averaging_robustness_2607_00475_1787554541.json`
- `models/portfolio/experiment_finegrained_baseline_seed45.zip`
- `models/portfolio/experiment_finegrained_baseline_seed46.zip`

Pre-existing, from the earlier uncommitted same-day session (Angle 2):

- `scripts/misc/train_a2118_ppo_recurrent_lstm_experiment_2607_00475.py`
- `scripts/misc/train_a2118_ppo_recurrent_lstm_multienv_experiment_2607_00475.py`
- `results/a2118_ppo_recurrent_lstm_experiment_2607_00475_1787511431.json`
- `models/portfolio/experiment_recurrentlstm_baseline_seed{42,43,44}.zip`
- `models/portfolio/experiment_recurrentlstm_multienv_baseline_seed42.zip`

Registry: two new entries added to
`group_a_plus/research_semantic_registry.json`
(`2607_00475_end_to_end_policy_framework_and_recurrent_memory`,
`2607_00475_ppo_seed_output_averaging_ensemble`).

Memory:
`project_2607_00475_end_to_end_policy_and_seed_averaging_20260824.md`
(and `MEMORY.md` index updated).

## Next Steps If This Line Is Pursued Further

- Seed averaging is the only piece of this paper worth carrying forward,
  and only as a `shadow_advisory` candidate pending the out-of-sample and
  cross-variant checks listed above.
- The recurrent-memory angle should not be revisited without a different
  underlying hypothesis for why it might work this time — two independent
  training designs already failed identically, and Group A+'s task
  (single-asset, small discrete action space) is a plausible structural
  reason RecurrentPPO has nothing useful to remember (the whole state that
  matters each day is close to fully captured in a single day's flat
  feature vector already, unlike the paper's 16-instrument cross-sectional
  setting).
