# 1909.03278 Low-risk DQN Trading Agent - Group A+ Review

**Status: closed, no import. Research-only assessment, no code written.**

Source: `C:\Users\isaac\Downloads\1909.03278.pdf`

Paper: Shin, Bu, Cho (Yonsei University), "Automatic Financial Trading
Agent for Low-risk Portfolio Management using Deep Reinforcement Learning"
(2019). Not previously reviewed in this repo (checked, no hits).

## Paper Summary

A DQN-based crypto portfolio allocator (8 high-volume coins, 2017-2018
Binance data) whose stated contribution is a **risk-aware target policy**:
instead of the standard Q-learning TD target (which greedily bootstraps
off the single best next-state action), it uses an Expected-SARSA-style
target that averages over all next-state actions weighted by a
temperature-scaled softmax of their Q-values:

```
Target = r + sum_a' softmax_tau(Q(s',a')) * Q(s',a')
tau = mean(|Q(s',a_i)|) * hyper_temperature
```

Lower `hyper_temperature` -> closer to pure greedy; higher -> the target
incorporates more of the non-optimal (safer) actions' values, biasing
training toward less risky policies. Actions are per-coin buy/sell/hold
with a continuous trade ratio from a softmax over Q-values; reward is
clipped portfolio-return, amplified by a constant. Backtested vs UBAH,
UCRP, EG, PAMR, and a plain-greedy DQN baseline on a 2017/11-2017/12 crypto
window (claims highest profit + lowest MDD) and a January 2018 crash
window (claims 13% MDD vs 49-64% for hold/random baselines).

## Fit to Group A+

**No import recommended.** This is architecturally the same family of
paper as two others already closed this session
(`docs/1706_10059_DEEP_PORTFOLIO_MANAGEMENT_GROUPA_PLUS_REVIEW_20260808.md`,
`docs/2105_08664_DEEPPOCKET_GROUPA_PLUS_REVIEW_20260809.md`): a from-scratch
neural network trained end-to-end to directly output discrete-asset trade
actions/ratios. Group A+ does not have, and per this session's repeated
review conclusions is not building, a live neural allocator that Q-learning
training mechanics would attach to -- the live mechanism is a hand-tuned
regime table with bounded discrete trim fractions, not a trained value
function over portfolio actions.

The one genuinely distinct idea versus the other two papers is the
temperature-scaled softmax target itself (the other two papers propose
architecture changes -- PVM state, GCN correlations -- not a change to
*how the training target is computed*). Considered whether this has a
non-RL analogue for Group A+: the abstract principle is "when picking among
discrete options by estimated value, soften the choice with a
temperature-weighted average instead of taking the argmax, to avoid
overconfidence in noisy value estimates." Group A+ does have discrete
choice points that superficially resemble this (regime arbitration in
`market_state.py`, specialist routing) -- but the paper's technique is not
actually a generic "soften an argmax" trick applicable at decision time;
it specifically changes what a Q-network's *training label* is during
gradient descent, which only has meaning if there is a Q-network being
trained. There's no such training loop in Group A+'s regime-arbitration
logic to attach it to, so this doesn't transfer as anything more concrete
than a vague inspiration -- not enough to justify opening a shadow line.

## Not Recommended

- Do not build a DQN/RL trading agent for Group A+ -- same conclusion as
  the two prior RL-allocator paper reviews this session, now reached a
  third time via a different paper's specific technique.
- Do not import the crypto-market crash-period performance claims (Jan
  2018) as evidence -- different asset class, different volatility regime,
  and per this project's citation discipline
  ([[project_finrlx_citation_rule_adopted_20260724]]) a paper's own
  headline numbers on a foreign universe aren't evidence for this one.
- The temperature-softened-target idea is conceptually interesting but has
  no host mechanism in this codebase to attach to; not worth a speculative
  shadow diagnostic on its own.

## Decision

Closed, no code written, no shadow candidate opened. Third RL-direct-
allocator paper reviewed and closed this session
(1706.10059, 2105.08664, 1909.03278) -- all three reach the same
architectural-fit verdict for the same underlying reason (Group A+ has no
trained-allocator mechanism for any of their techniques to attach to), so
each successive review closes faster than the last.
