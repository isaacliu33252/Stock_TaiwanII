# 2608.15841 QUESTrader (Self-Supervised Auxiliary Task Discovery for Stable RL in Stock Trading) — Desk Review

Date: 2026-09-08. Paper: Orra, Choudhary, Thakur (IIT Mandi), arXiv:2608.15841v1.
Downloaded 2026-09-02, sat unreviewed until picked up in this session as the next research
item after the a2118 independent-PPO-model line closed out.

## What the paper does

QUESTrader: a two-network PPO framework that **automatically discovers** auxiliary tasks for
an RL trading agent instead of hand-designing them. Auxiliary tasks are formulated as General
Value Functions (GVFs) — predictions of arbitrary cumulants discounted by a learned,
state-dependent discount factor, not just future reward. A "question network" emits the
cumulant/discount pair defining each GVF; a "main/answer network" learns the trading policy
(PPO) plus the answers to those GVFs, with the GVF prediction loss added to the PPO loss as an
auxiliary term. The question network's parameters are treated as meta-parameters and updated via
a non-myopic meta-gradient (bi-level optimization: K inner PPO updates on the main network per 1
outer update on the question network), so questions are shaped by their delayed causal effect on
trading performance, not just immediate loss.

Evaluated on 4 indices (DJI, FTSE, Sensex, TAIEX; 30 stocks each, or top-30 for FTSE/TAIEX),
train 2010-01-01..2023-12-31, test 2024-01-01..2025-03-31 (single OOS window, ~15 months).
Beats every baseline (Buy-Hold, MVO, Random, plain PPO, VS-DRL, SRRS, FinRL-DDPG/SAC, Adaptive
ensemble, DREB, and three hand-crafted-auxiliary-task baselines PA-AXT/PPO-AXT/DeepScalper) on
annual return, cumulative return, Sharpe, Calmar, and Sortino on all 4 indices, with competitive
(not always best) max drawdown.

## Why this one is different from most papers reviewed this session

Almost every paper closed_negative this quarter for one of two reasons: (a) needs a large,
heterogeneous cross-sectional asset pool that GroupA+'s ~4-ticker sleeve doesn't have (RMT,
cross-sectional ranking, graph/attention over many stocks), or (b) targets an asset class
GroupA+ doesn't trade (options, FX, crypto, HFT). **QUESTrader has neither problem**: the GVF/
meta-gradient machinery operates per-asset on a single learner's temporal credit assignment, not
on cross-sectional structure — nothing in the method requires N to be large. It also uses PPO,
the exact same underlying algorithm `train_dual_group_2024_2026.py` already uses for a2118's
independent PPO models (this week's whole research line). This is a genuine methodological
match, not a topical near-miss.

**It is also unusually well-timed**: today's day-by-day diagnostic on the cap20 independent PPO
model (`project_a2118_independent_ppo_model_experiment_20260908.md`) found that the residual
~2pp MDD gap versus golden1_0531 traces to the new model sitting pinned near its leverage cap
throughout `golden1`-regime days, with no internal risk modulation — and hypothesized (without
being able to test) that golden1_0531's institutional/LLM-sentiment features let it do that
modulation and the new model can't because those features don't exist for the 2017-2019 training
window. **QUESTrader offers a different, data-free path to the same goal**: instead of needing
new input features, auxiliary GVF tasks (e.g. predicting future volatility/drawdown-related
cumulants) could push the *same* network to develop the risk-representation the paper's action
timelines show (Figure 7: QUESTrader "issues fewer and more coherent switches," "keeps the short
stance intact for most of the descent" versus plain PPO's whipsaws) — using only price/volume
data already available in every training window, no institutional or sentiment data required.

## Reasons for caution — this is not a quick shadow test

1. **Engineering lift is real.** GroupA+'s entire PPO training pipeline is built on
   `stable-baselines3`'s black-box `PPO` class (`model.learn(total_timesteps=...)`). QUESTrader's
   meta-gradient step requires differentiating the *inner-loop-unrolled* main-network parameters
   with respect to the question network's parameters (Algorithm 1, bi-level optimization) — this
   is not something you can bolt onto `stable_baselines3.PPO` via a training callback or a kwarg.
   It needs a custom PPO loop with a second optimizer and a differentiable inner unroll, which is
   a genuinely different (and more complex) codebase than everything else in this project's RL
   stack. Not a 20-line change.
2. **The paper's own ablation methodology has the same fixed-window-tuning issue this project's
   checklist already flags** ([[feedback_overfitting_fixed_window_tuning]]): "For each
   configuration, we retrain the full pipeline and evaluate it using the fixed test window" —
   `dq` and `K` were swept and picked by looking directly at performance on the same test window
   reported as the headline result. The paper doesn't hold out a separate validation window for
   hyperparameter selection. This doesn't necessarily invalidate the core idea, but the specific
   `dq∈[16,64]`, `K≈10-20` "sweet spot" numbers should not be trusted as universal — they'd need
   re-tuning (ideally on a walk-forward split) for any GroupA+ adaptation.
3. **Single OOS window (~15 months, 2024-01 to 2025-03), no walk-forward, no significance
   testing** against baselines despite reporting 5-run means±std — same generic gap flagged for
   most RL papers this project has reviewed (checklist items 10/11 on Bonferroni-style multi-
   window significance). "5 independent runs" is a real practice, better than most papers
   reviewed this session, but still n=1 window.
4. **Asset universe mismatch remains, just not fatal.** The paper's per-market universe (30
   large-cap constituents) is far larger than GroupA+'s core sleeve, and the reward/action space
   is per-share position sizing, not the same triplet/discrete-weight action schema GroupA+ uses.
   Porting the idea means re-deriving the auxiliary-task machinery for GroupA+'s actual action
   schema, not a drop-in swap.

## Recommendation

**Not closed_negative** — unlike most papers this session, this one clears the applicability bar
cleanly (same algorithm family, no cross-sectional requirement, timely fit to today's own
diagnosed gap) and is worth carrying forward. But it is **not a same-day shadow-test candidate**
like most of this session's reviews — it requires writing a custom bi-level-optimization PPO
trainer, which is a multi-session engineering project, not a script.

**Two ways to use this, cheapest first:**
1. **Cheap partial version (no meta-gradient)**: bolt one or two *fixed* (hand-picked, not
   discovered) auxiliary prediction heads onto the existing PPO training — e.g., predict N-day
   forward realized volatility or forward drawdown, added as an extra MSE loss term alongside the
   PPO loss (this is exactly what the paper's own weaker baselines PA-AXT/DeepScalper do, and they
   still beat plain PPO in every one of the paper's tables, just by less than the full
   meta-gradient version). This only requires a custom policy network with an extra head plus a
   custom loss function passed to SB3's `PPO` via a modified `train()` override or a custom
   `ActorCriticPolicy` — meaningfully smaller lift than full QUESTrader, and directly testable on
   the cap20 recipe already established today as the best independent-model baseline.
2. **Full QUESTrader (discovered GVFs + non-myopic meta-gradient)**: the complete method, only
   worth the larger engineering investment if step 1 shows the general "auxiliary task helps
   internal risk modulation" idea has legs on GroupA+'s data at all.

**Not scheduled.** This is a desk-review conclusion, not a commitment to build — flagging as the
most promising *unexplored* lead against today's diagnosed residual-MDD-gap root cause, for
whoever picks up this research line next.

## "Cheap version" test (2026-09-09, next day): no measurable effect

Implemented and ran the cheap version described above:
`scripts/misc/train_questrader_lite_aux_head_20260909.py`. No meta-gradient — a single fixed
auxiliary head (predict standardized 5-day forward realized volatility of 0050.TW) bolted onto
the cap20 recipe (2017-2019 window, triplet_v2, 00631L cap 20%, seed=42), added as an extra MSE
term (`aux_coef=0.1`) alongside the normal PPO loss. Required a custom `RolloutBuffer` (carries
the aux target outside the observation, avoiding label leakage into the actor), a custom
`ActorCriticPolicy` (extra linear head off the value latent), and a custom `PPO` subclass
overriding `collect_rollouts`/`train()` to wire it together — validated with a 2048-step smoke
test before committing to the full 80K-step run.

**On `active_2025_2026`:**

| | production | cap20 seed42 | cap20 seed7 | cap20 seed123 | cap20+auxvol (seed42) |
|---|---|---|---|---|---|
| Final value | 2,123,517 | 2,317,731 (+9.1%) | 2,307,775 (+8.7%) | 2,317,750 (+9.1%) | 2,312,182 (+8.9%) |
| Sharpe | 2.053 | 2.218 | 2.086 | 2.091 | 2.087 |
| MDD | -16.44% | -16.34% (-0.10pp) | -18.31% (-1.87pp) | -18.42% (-1.98pp) | -18.42% (-1.98pp) |

**No measurable effect.** The auxvol run's MDD (-18.42%) is essentially identical to seed7/123's
plain-cap20 numbers, not closer to production and not distinguishable from ordinary seed-to-seed
variance. This single fixed auxiliary task, at this coefficient, did not produce a detectable
change in behavior. This does **not** refute the full QUESTrader idea — the paper's own core
claim is that *meta-gradient-discovered* questions beat any single hand-picked one (its own
PA-AXT/DeepScalper baselines, which use fixed auxiliary tasks like this one, do beat plain PPO in
every table but by much less than the full method) — but the specific cheap shortcut tested here
is a dead end as implemented. Untested variations (different `aux_coef`, different cumulant
target such as forward drawdown, multiple heads) would just be hyperparameter fishing
([[feedback_overfitting_fixed_window_tuning]]) rather than a principled next step; the paper's
actual mechanism (automatic discovery via meta-gradient) is the only version of this idea that
has real evidence behind it, and remains a large, unstarted engineering investment.

**This closes out the entire a2118-independent-PPO-model research line** (from the original
no-trade-band analysis through 3-seed verification, single-variable isolation, day-by-day
diagnosis, the institutional-features hypothesis test, and now this auxiliary-task test): cap20
stands as the line's one clean shadow candidate, and both routes toward explaining/fixing its
residual MDD gap (institutional/LLM features, and now a QUESTrader-lite auxiliary task) have been
tested and neither showed an effect.

Memory: `project_2608_15841_questrader_gvf_auxiliary_desk_review_20260908.md` (cheap-version test
section appended).
