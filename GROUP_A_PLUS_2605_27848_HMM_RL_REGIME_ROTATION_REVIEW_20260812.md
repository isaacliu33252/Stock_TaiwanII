# 2605.27848 (Verma, Putri, Lesupi) — HMM + RL Regime-Based Portfolio Allocation — Group A+ Review

**Status: clean close, no promotion. Paper review + a real shadow test on
Group A+'s own universe, both negative.**

## 1. Paper

"Regime-Based Portfolio Allocation Using Hidden Markov Models and
Reinforcement Learning," Ajay Kumar Verma, Nunik Srikandi Putri, Neo Paul
Lesupi — three independent researchers, one affiliated with a small
consultancy ("Aenimatica Tech Research and Development"). Dated November
2025, **not peer-reviewed, no conference/journal venue**.

Method: daily SPY (equity) / TLT (bond) / GLD (gold) ETF data, 2004-2025.
A discrete first-order Markov chain on quantile-binned ΔVIX motivates the
approach; the actual model used is a **3-state Gaussian HMM** (selected
over a 2-state alternative via AIC/BIC) fit on a single return series via
EM (Hamilton forward filter, RTS backward smoother). States are
interpreted as low-vol/transitional/high-vol regimes with strong
persistence (diagonal transition probabilities 0.94/0.91/0.87). Two
rule-based rotation strategies (Top-1: 100% into the regime's
highest-mean asset; 60/40: split between top-2) are compared against a
**tabular RL policy** that treats the HMM regime as the MDP state, solves
the Bellman optimality equation via policy iteration over 7 discrete
portfolio-weight actions. Evaluated on a single chronological 70%
train / 30% out-of-sample test split, 1-day execution lag, **no
transaction costs**.

## 2. Why the paper's own evidence doesn't clear this project's bar

**Headline claim not supported by the paper's own results table.** The
abstract states the RL policy "achieves the highest risk-adjusted
performance, delivering the strongest Sharpe ratio." The paper's own
Table 7 (OOS test window): RL π* Sharpe = **0.83**, Equal-Weight (Monthly)
baseline Sharpe = **0.83** — an exact tie, with RL winning only on max
drawdown by a small margin (−23.5% vs −24.0%). This is the same failure
pattern already catalogued in
`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md` (headline claims
not matching the authors' own tables) — closest precedent this project has
reviewed is `2606.29347` (Adaptive Financial Transformer), where the
authors' own paired t-tests showed p=0.90/0.95. This paper is worse in one
respect: it reports **no significance test at all** — a single 70/30
split, no walk-forward, no multi-seed variance estimate, so even the
0.83-vs-0.83 tie can't be interpreted with any confidence interval.

**The "RL" component adds little beyond the rule-based Top-1 baseline it's
compared against.** Table 5's learned policy: state 0 → 100% SPY, state 1
→ 100% SPY, state 2 → 100% GLD — TLT receives zero allocation in any
state. This is structurally the same all-or-nothing single-asset
rotation as the paper's own "Top-1" rule-based baseline (Table 4), just
computed via a Bellman/policy-iteration framing on a fully-enumerated
3-state MDP rather than directly from state-conditional sample means.
With only 3 states, 7 discrete actions and one-step rewards, tabular
policy iteration on this problem is close to an expensive way to compute
the same argmax the Top-1 rule already computes directly.

**No transaction costs, acknowledged by the authors as a limitation.**
Section 9(4) states this explicitly. A regime-switching strategy that
reallocates around every regime transition (visible in Fig. 10-11's
choppy rotation lines) is exactly the kind of strategy whose apparent
edge is most sensitive to costs — this project's own experience (see
`GROUP_A_PLUS_20260811_ALPHAZEROBETA...` and the weight-drift/rebalance
work) repeatedly shows execution-realistic assumptions changing
conclusions materially.

## 3. Shadow test: does the mechanism itself hold up on Group A+'s universe?

Rather than close on paper-quality critique alone, the core *mechanism*
(3-state Gaussian HMM regime detection → regime-conditioned Top-1
rotation) was tested directly on Group A+'s own tradable assets, with a
materially more rigorous protocol than the paper's own single 70/30
split.

**Adaptation**: Group A+ has no gold ETF in its tradable universe
(`config/group_a_plus_watchlist.json`: 0050/00631L/00632R/00679B/2330).
Substituted 0050 (equity, SPY-role) / 00679B (20y US treasury, TW-listed,
TLT-role) / 00632R (inverse, GLD-role substitute — plays the "gains when
equities fall" defensive role, though mechanically different from gold).

**Implementation**: `scripts/evaluate/evaluate_hmm_regime_rotation_shadow.py`.
`hmmlearn` is not installed in this environment (would require
`pip --break-system-packages`, a system-level change not worth making for
a one-off research script); a compact univariate 3-state Gaussian HMM
(Baum-Welch EM with 5 random restarts, causal forward-filter for state
inference — no smoothing, no look-ahead) is implemented directly in the
script instead. Regime signal: 0050 daily log returns (×100, matching the
paper's own Table 2 value scale, which is consistent with percentage-unit
daily returns rather than raw VIX levels).

**Validation**: `group_a_plus.validation.purged_walk_forward.PurgedWalkForwardSplit`,
5 folds, 1-day purge (matches the paper's 1-day execution lag), HMM
refit from scratch on each fold's train-only data (no leakage — the
paper's own single-split design doesn't even test this). On each fold:
fit HMM on train, determine each state's historical Top-1 asset from
train-only conditional means, then causally filter states through
train+test and rotate into that fold's frozen state→asset mapping on
test days, with the same 1-day execution lag as the paper.

## 4. Results

`results/hmm_regime_rotation_shadow.json`,
`report/group_a_plus/latest/hmm_regime_rotation_shadow.md`.

| strategy | annual return | Sharpe | max drawdown | n test days |
|---|---|---|---|---|
| HMM regime Top-1 | −1.4% | **−0.068** | 69.1% | 2065 |
| Equal-weight (0050/00679B/00632R) | +4.2% | 0.182 | 36.7% | 2065 |
| Buy & hold 0050 | +19.5% | **0.903** | 45.2% | 2065 |

All three rows evaluated on the identical pooled OOS test days (2018-01
through 2026-08, 5 walk-forward folds) for a fair comparison.

Per-fold detail:

| fold | test window | state→asset map | annual return | Sharpe |
|---|---|---|---|---|
| 1 | 2018-01..2019-10 | {0: bond, 1: equity, 2: equity} | +7.8% | 0.692 |
| 2 | 2019-10..2021-07 | {0: equity, 1: bond, 2: equity} | −13.3% | −0.697 |
| 3 | 2021-07..2023-03 | {0: inverse, 1: equity, 2: equity} | −11.7% | −0.602 |
| 4 | 2023-03..2024-11 | {0: inverse, 1: equity, 2: equity} | +18.9% | 0.920 |
| 5 | 2024-11..2026-08 | {0: inverse, 1: equity, 2: equity} | −8.5% | −0.301 |

## 5. Interpretation

**The mechanism does not merely fail to add value — it actively hurts.**
HMM regime Top-1 rotation has a *negative* Sharpe, underperforming both
naive equal-weight and plain buy-and-hold 0050 by a wide margin, with the
worst max drawdown of the three (69.1% vs 45.2% for buy-and-hold — a
regime-switching strategy somehow drew down *more* than the pure-equity
benchmark it was supposed to protect against).

**Regime identity is unstable across refits, contradicting the paper's
"strong persistence" framing.** State 2 (highest-mean regime) maps to
`equity` in all 5 folds — the one part of the mapping that's stable. But
state 0 (lowest-mean regime) maps to `bond` (fold 1), `equity` (fold 2),
then `inverse` (folds 3-5) — three different assets across five refits.
A regime whose *economic identity* flips depending on which training
window it was estimated on is not the "clear and stable segmentation of
market conditions" the paper's conclusion claims for its own (US,
15-year-train) setting. Some of this instability is plausibly a
small-sample artifact in fold 1 (only 253 training days, well under the
paper's own 15-year training window) — a known limitation of an
expanding walk-forward's earliest folds, not a code bug — but folds 3-5
(1000+ training days each) still show state 0 mapping to `inverse` while
folds 1-2 mapped it elsewhere, so this isn't purely a small-sample
problem.

**Only 3/5 folds are individually positive, and none are close to the
paper's own reported OOS Sharpe (0.83, itself tied with a naive
baseline).** This is a directionally clean, not merely inconclusive,
negative result — consistent with (and sharper than) the paper's own
weak internal evidence.

## 6. Verdict

**Clean close. Not promoted, no shadow line opened.** Two independent
lines of evidence point the same way: (a) the paper's own numbers don't
support its headline claim (RL tied with naive baseline, no significance
testing), and (b) a more rigorous walk-forward test of the core mechanism
on Group A+'s actual Taiwan universe produces a strategy that's *worse*
than doing nothing (buy-and-hold). Group A+'s existing regime-detection
machinery (`market_state` classifiers, chip-flow indicators, `switch_ma*`
family, tail-risk sub-indicators — all Taiwan-market-specific,
domain-engineered features) is not something this paper's generic
price-only Gaussian HMM offers any evidence of improving on.

## 7. What was and wasn't done

- Read the full paper (9 pages + references) directly, not summarized
  secondhand.
- Implemented and ran a real shadow test (not just a paper critique) —
  compact Gaussian HMM from scratch (no `hmmlearn` dependency added),
  proper purged walk-forward (stricter than the paper's own single-split
  protocol), fair same-day comparison against equal-weight and
  buy-and-hold references.
- **Not implemented**: the RL/tabular-policy-iteration layer itself —
  skipped because (a) the paper's own results show it barely
  distinguishing itself from a simple Top-1 rule, and (b) the HMM regime
  signal it would operate on already failed decisively at the more basic
  Top-1 level; layering RL on top of a regime signal that's already
  actively harmful wouldn't be an informative next experiment. Consistent
  with this project's standing skepticism toward RL approaches (10+ prior
  closed RL lines, see e.g. `project_2606_10448_quantum_sac_layernorm_pilot_20260811`).
- **Not implemented**: 2-state HMM alternative, non-Gaussian emissions, or
  a gold-proxy asset (no TW-listed gold ETF in the current watchlist;
  00632R was used as a structurally-different substitute for GLD's
  "rises when equities fall" role, not a faithful replication of gold's
  actual return profile — this is a real scope limitation, not a bug,
  and is disclosed rather than presented as a full reproduction).
- No production code touched. No shadow line opened in the daily
  pipeline — one-off research script + static report, same treatment as
  every other closed-paper shadow this project has run.
- No pytest coverage — one-time research diagnostic script, consistent
  with this project's convention (see e.g.
  `GROUP_A_PLUS_20260811_ALPHAZEROBETA...` §14).
- Not committed — user has not asked for a commit for this batch of work.

## 8. Files

| File | Nature |
|---|---|
| `scripts/evaluate/evaluate_hmm_regime_rotation_shadow.py` | New — compact Gaussian HMM (Baum-Welch EM) + purged walk-forward regime-rotation shadow harness |
| `results/hmm_regime_rotation_shadow.json` | New — full per-fold results, state→asset maps, daily returns for all 3 compared strategies |
| `report/group_a_plus/latest/hmm_regime_rotation_shadow.md` | New — summary tables |
| This file | New, handoff record |

## 9. Memory index

`project_2605_27848_hmm_rl_regime_rotation_closed_20260812.md`. Related:
`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md` (headline-vs-own-data
mismatch pattern), `project_2606_10448_quantum_sac_layernorm_pilot_20260811`
(most recent of this project's many closed RL lines).
