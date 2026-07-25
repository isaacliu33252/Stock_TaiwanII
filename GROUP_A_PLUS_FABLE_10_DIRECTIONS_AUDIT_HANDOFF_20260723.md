# GroupA+ Fable 10-Direction Profit-Improvement Audit Handoff - 2026-07-23

## Status

**Continuation note (2026-07-24)**: this session continued past this
document's original scope into several follow-up threads, each written up
in its own file rather than appended here: (1) a golden1_0531 naming/
staleness/governance investigation --
`GROUP_A_GOLDEN1_0531_STALENESS_AND_PREDICTION_HANDOFF_20260723.md`
(includes a small `_latest_prices()` empty-holdings crash fix, 2026-07-24);
(2) the FinRL-X citation rule's first real application plus a four-window
(2017-2019/2020/2022/2025-2026) deep-dive into whether a2118's
`h20_max`/`conf_min` thresholds can be tuned (answer: no clean signal in
any window, but the reason turned out to be a missed `ma_gap` condition in
the trigger logic, not the thresholds themselves -- see
`project_a2118_ncf_hedge_dormancy_root_cause_20260723` memory) and whether
the NCF continuous overlay's real cost holds up out-of-sample (a panel-
path bug was found and fixed; the 2017-2019 OOS cost turned out to be
-1.14pp, not -9.3pp -- see `project_a2118_ncf_live_overlay_backtest_gap_20260723`
memory); (3) a user-proposed A21.19 continuous-defensive-tilt shadow
candidate and a full investigation of its 2020 COVID failure, which found
a structural design flaw (it never reads `execution_regime` at all) --
`GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`.

**Two production changes implemented and tested (original 2026-07-23
scope).** Fable was asked to
propose 10 directions to improve Group A+'s current active strategy
(a2118_a2111_ncf_late_bull_deleverage) returns. Each direction was
independently verified (not taken on Fable's word) before any action. Net
result: two real production corrections shipped, one major mis-attributed
promotion claim corrected, seven directions closed with no action needed.
Full test suite: **1390 passed, 9 skipped, 0 failed** after all changes
(`python3 -m pytest tests/ -q`, ~45 min).

### What changed in production

1. **`group_a_plus/operations/execution_plan.py`** — the volatility-gate and
   compounding-regime pre-trade guards no longer auto-zero the 00631L target
   share count. New keyword arg `enforce_advisory_pre_trade_guards`
   (function default `True`, preserving old behavior for every existing
   caller/test; **CLI default is `False`**, so the real daily-plan entry
   point now defaults to the new behavior). New flag:
   `--enforce-advisory-pre-trade-guards` restores the old hard-block
   behavior if ever needed. New test:
   `test_execution_plan_advisory_guards_do_not_block_when_not_enforced`
   (`tests/test_group_a_plus_execution_plan_v2.py`).
2. **`report/group_a_plus/latest/strategy.json`** — `active_strategy.
   improvements.sharpe_delta` (0.029, the number that originally justified
   promoting a2111->a2118) now has a sibling `sharpe_delta_status` field
   marking it stale, plus a new dated block
   `ncf_late_bull_hedge_dormancy_audit_20260723` documenting why and what
   actually drives a2118's edge today (see Finding 3 below).

Today's `report/group_a_plus/latest/execution_plan.json` was regenerated
with the new behavior (cash balance 1,000,000, confirmed by the user as
their real, no-discount account) — see Finding 1.

New reusable script: `scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py`
(research-only, no production effect by itself — see Finding 2).

---

## Why this session happened

User asked Fable (model override `fable`, via the Agent tool) to read the
current Group A+ codebase and propose 10 concrete directions to improve
returns, having been warned Fable must not just repeat directions already
closed in project memory (extensive list was given in the prompt — GARCH
routing, GNHAR, downside-vol timing, 2008 stress candidates, ncf_2330
5-way-rejected attempts, etc.). Fable's response is reproduced in full
in the conversation transcript; each of the 10 directions was then
independently re-verified by reading code and running real backtests
before any conclusion was accepted or any change was made — several of
Fable's specific claims turned out to be wrong or overstated (see Finding
2's TSMC-trim correction, and the general pattern of "confirmed but less
severe/different mechanism than claimed").

**IMPORTANT process rule established mid-session** (see
`feedback_automation_first_design_principle` in Claude's persistent
memory): *all decisions should be evaluated as if the logic will
eventually run unattended/automated, even though execution is currently
100% manual.* Guard/threshold correctness should not be relaxed just
because "a human will catch it" — that human-review step is temporary.

---

## Finding 1 (Fable direction 2, highest priority): pre-trade guards were silently auto-blocking real trades, contradicting their own stated intent

`group_a_plus/operations/execution_guard.py`'s
`apply_volatility_gate_pre_trade_guard` and
`apply_compounding_regime_pre_trade_guard` read alerts/regime data from
`garch_regime_shadow.py` (self-declared `"policy": "shadow_only_no_weight_
change"`) and `leveraged_compounding_regime.py` (self-declared
"diagnostic-only... must never feed target_weights"), and from an alert
in `daily_signal.py` whose own title/reason text says **"manual review" /
"advisory-only review"** — yet the guard functions were **automatically**
zeroing the 00631L buy target with no human ever seeing the full
recommendation. Confirmed live: as of 2026-07-22 data, both guards had
been continuously active since 2026-07-09 (one 2-day gap 07-15/16),
silently suppressing a NT$101,198 (~8% of the ~NT$1.27M account) 00631L
cold-start buy for 2+ weeks. The only historical shadow validation of
these guards (`results/00631l_compounding_regime_no_add_shadow_strict_
20260715.json`, 82 blocked events) only ever saw 0.02%-0.5% weight
blocks on an *already-invested* position — never a full cold-start build
like the live one. User confirmed all orders are placed manually and
automation is not currently allowed, so the correct fix is to restore the
guards' own stated design (surface a prominent warning, let the human
decide) rather than removing the guards or leaving them auto-blocking.
Implemented as described in "What changed in production" above. Verified
end-to-end: regenerated `execution_plan.json` now shows the full 2,908-
share / NT$101,198 00631L buy recommendation with
`pre_trade_guard.status = "flagged_advisory_only"`,
`enforced: false`, and the original blocked-trade detail preserved under
a new `advisory_trades` field for visibility. `guard_impact_summary.
blocked_guard_names` is now `[]` since nothing is actually blocked.
The third guard (`a2118_extreme_risk_no_new_adds`) was left untouched —
its own docstring never claimed "no weight change", so there was no
contradiction to fix there.

## Finding 2 (Fable direction 1+9): the live-only NCF continuous downside overlay costs ~10.75pp/year in the only testable window, with no measurable risk benefit; one of Fable's three claimed "live overlay" layers turned out not to be live at all

`daily_signal.py::_apply_ncf_live_overlay` (calls `ncf.py::
ncf_overlay_summary`/`adjust_golden1_weights`) runs every golden1 day in
production but was never modeled in `a2118.py`'s own backtest — confirmed
by grep (`a2118.py` imports `ncf_overlay_summary` but never calls it).
Built `scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py` to
reconstruct it historically by calling the real production functions
(not a reimplementation) against the 00631L/00632R NCF panels (only
available from 2025-01 onward — cannot speak to crash regimes like 2020).

**Correction to Fable's framing**: Fable's other claimed "live-only" layer,
`_apply_tsmc_weakness_trim`, is fully implemented and unit-tested but is
**never called from `build_daily_signal`** (grep confirms zero call
sites outside its own `def`) — it is not live. It is very likely the
"weight trim" candidate already rejected in the 2026-07-05 ncf_2330
five-way-rejection session (see `scripts/misc/
ncf_00631l_total_risk_score_overlay_sweep.py`'s docstring, which calls it
"already-rejected"). The evaluate script's `--include-tsmc-trim` flag
defaults off to reflect this.

Results (`results/a2118_live_overlay_backtest_gap_ncf_only.json`,
2025-01-02..2026-07-16, no-deadband): baseline (current a2118 backtest,
no overlay) annual_return=66.12% Sharpe=2.341 Sortino=2.548 MDD=-13.56%;
with the real live overlay added: annual_return=55.37% (**-10.75pp**)
Sharpe=2.399 (+0.057) Sortino=2.602 (+0.054) MDD=-13.44% (+0.12pp,
noise-level). 157/291 golden1 days triggered a small adjustment (median
-0.35pp, max -1.88pp, never >2pp in one day) — the annual-return cost is
NOT primarily transaction-cost noise: re-ran with `--no-trade-band 0.005`
(mirrors execution_plan.py's real `min_weight_deviation`) and rebalance
count dropped 214->26, transaction cost dropped $8,565->$6,092, but
annual_return delta barely moved (-10.75pp -> -10.53pp). The cost is a
genuine, persistent average-exposure reduction compounding over a bull
window with essentially no measured downside protection to show for it
(consistent with the project's repeated 2025-2026-is-a-single-bull-regime
finding elsewhere in memory).

**Decision**: user chose to keep the live overlay running as-is for now
("維持現狀，先記錄下來"), consistent with prior stated preference to
keep risk-control overlays even at a return cost
(`feedback_strategy_promotion_caution` memory). No code change made for
this finding. If the NCF panels ever extend to cover a real drawdown
period, re-run the same script to re-evaluate the cost/protection
trade-off.

## Finding 3 (Fable direction 6, escalated into the session's biggest discovery): a2118's late-bull-hedge trigger has fired ZERO times on any current panel, and a2118's entire current edge over plain a2111 is 100% attributable to the independent 2020 COVID switch-rule fix

Started as Fable's threshold-recalibration question (are `h20_max=0.33`/
`conf_min=0.55` still well-calibrated after the 2026-07-07 panel
ensemble-weight fix?). Direct check: `run_a2118` with production params
on the current panel (`results/ncf_00631l_panel_latest_20260722.csv`)
over 2025-01-02..2026-07-22 gives `late_bull_trigger_days = 0`.

**Root-cause chase (this took several wrong turns, documented for
future reference so nobody re-treads them)**:
- First hypothesis (07-07 expanding-model-weights fix diluted confidence)
  was **disproved**: re-checked the pre-fix "OFF" (global-weight)
  verification panel for the same window
  (`results/ncf_00631l_panel_verify_off_20260703.csv`) — also 0/0
  trigger-eligible days. The dormancy predates that fix.
- Second hypothesis (shrinkage-ramp still "warming up" since the live
  panel's validation window is young) was also **not clean** — checked
  monthly confidence trend within the live panel, it's noisy/
  non-monotonic, not a smooth ramp.
- Confirmed instead: this is a genuine property of the 2025-2026
  panel/regime. A 2017-2019 backfill panel
  (`results/ncf_00631l_panel_backfill_2017_2019_20260710.csv`, built
  2026-07-10 with the same current pipeline, `--train-start 2015-06-01
  --val-start 2017-01-01 --val-end 2019-12-31 --full-panel`) shows much
  higher confidence (mean 0.40 vs 0.23-0.29, max 0.92 vs 0.72-0.84) and
  26 trigger-eligible days vs 0. `confidence` is computed directly from
  `prob_magnitude` (distance from 0.5), not from the ensemble-weight
  shrinkage ramp — so this is a market/model-behavior fact about
  2025-2026, not a pipeline bug.
- Checked robustness: 0/0 trigger-eligible days is consistent across
  every panel snapshot regenerated since 07-07 (07-07, 07-08, 07-16,
  07-20, 07-21, 07-22 — 6/6).

**Decisive confirmation** — ran three backtests over 2024-01-02..
2026-07-22 with the current real panel:
  - Pure a2111 (`group_a_plus/runners/a2111.py`, no 2020 fix, no NCF):
    final_value=2,854,319 Sharpe=1.8690 Sortino=1.8527 MDD=-21.03%
  - Full current a2118 production config: final_value=2,854,319
    Sharpe=1.9035 Sortino=1.8800 MDD=-21.03% (late_bull_trigger_days=0)
  - `run_a2118` with `ncf_panel_631l_path=None` (i.e. a2111 base + only
    the 2020 COVID fix params, zero NCF involvement):
    final_value=2,854,319 Sharpe=1.9035 Sortino=1.8800 MDD=-21.03%

The last two are **numerically identical to every reported decimal**.
a2118's entire current Sharpe improvement over plain a2111 (1.8690 ->
1.9035) comes 100% from `switch_rule_2020_covid_fix_20260706`
(independently validated via a 5-crisis backtest, gate-passed, unrelated
to NCF). The NCF late-bull-hedge mechanism contributes exactly zero to
today's numbers. The original promotion evidence
(`sharpe_delta: 0.029`, `trigger_count_short: 3` in strategy.json,
dated before the 2026-06-29 v5 panel upgrade) was earned on a since-
superseded panel snapshot and does not reproduce under any panel-
generation method checked so far.

User asked "so should we revert to a2111?" — answer given and accepted:
**no**, because a2118's *current* behavior is already byte-identical to
"a2111 + 2020 fix" (the NCF mechanism is dormant, not harmful), so
reverting would only lose the independently-validated 2020 fix for
nothing in return. Instead, corrected `strategy.json`'s attribution (see
"What changed in production" above) so the stale claim can't mislead a
future promotion/decision record. NCF late-bull-hedge is downgraded from
"demonstrated production edge" to "unproven/dormant, do not re-cite
without fresh out-of-sample validation."

**Open follow-up, not done**: never located/reconstructed the exact
pre-2026-06-29 panel snapshot that produced the original 3 trigger days,
so it's unknown whether that original evidence was ever robust or was
itself a fragile/borderline artifact from the start. Worth doing if
anyone wants to fully close this loop.

**2026-07-25 addendum: closed.** User asked to switch direction away from
the day's A21.19/`credit_stress` investigation
(`GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`)
and try something new; this was the concrete candidate offered and picked.
The exact pre-06-29 panel turned out to still be on disk:
`results/ncf_00631l_panel_2025_v4_tail.csv` (the v4/pre-TabNet panel cited
by name in `GROUP_A_PLUS_A2118_HANDOFF_20260628.md`, the promotion's own
`decision_record`), together with that same handoff's original threshold
`NCF_LB_H20_MAX = 0.45` (later tightened to 0.35, then to today's 0.33,
specifically "to eliminate May-2026 false positives" per
`strategy.json`'s own note). Re-running `run_a2118()` with this exact
panel + threshold reproduces `late_bull_trigger_days = 3` **exactly**,
matching `strategy.json`'s recorded `trigger_count_short: 3` -- this is
almost certainly the original promotion configuration, not a
reconstruction guess.

**The three trigger events**: 2025-10-30, 2026-02-23, 2026-05-04.
**This directly contradicts `strategy.json`'s recorded `trigger_accuracy:
"3/3 (100%)"`**: the same source handoff document
(`GROUP_A_PLUS_A2118_HANDOFF_20260628.md`)'s own "7 個歷史觸發事件與實際走勢"
table, dated the same day as the promotion, already lists 2026-05-04 as
`❌ 誤觸發` (false trigger) -- 00631L rallied +21.9% over the following 20
trading days rather than falling, the exact outcome the hedge exists to
avoid. **The original promotion record's "100% accuracy" claim is
inconsistent with its own cited source document** -- 1 of the 3 counted
trigger events was already known, in the same document, to be a misfire
at the time the evidence was recorded. This is a genuine finding, not
just "unreproducible": it isn't that the evidence was fragile or
couldn't be pinned down -- the exact configuration reproduces cleanly --
it's that the accuracy figure itself doesn't match what the promotion's
own source material already showed.

The magnitude figures don't reproduce as cleanly: `sharpe_delta=+0.109`,
`sortino_delta=+0.135`, `annual_return_delta=-7.10pp` in this
reproduction, versus `0.029`/`0.033`/`-5.04pp` recorded in `strategy.json`
-- same direction and same rough shape (Sharpe/Sortino improve, annual
return costs), but 3-4x larger magnitude here. The trigger-count match
being exact while the metric deltas aren't suggests the comparison
baseline (what exactly a2118-with-panel was measured against) differed
in some detail not yet identified -- flagged as a smaller, secondary loose
end, not chased further today. This does not change the main finding
above (the panel/threshold identification itself, and the accuracy-claim
contradiction) and does not reopen Finding 3's already-settled
conclusion that the NCF late-bull-hedge mechanism is currently dormant
and should not be cited as a demonstrated live edge -- if anything it
mildly reinforces skepticism about how solid the original promotion
evidence was, consistent with Finding 3's broader conclusion. No code or
production files changed; this was pure historical reconstruction using
`run_a2118()` as-is against an archived panel file already on disk.

| # | Direction | Verdict |
|---|---|---|
| 3 | Multiple independent guards OR-combine, false-positive rate compounds | Premise changed by Finding 1's fix — 2 of 3 guards no longer auto-enforce, so there's no more "stacking." Noted, not pursued further. |
| 4 | 40%/day staged-buy pacing + 50% turnover cap too conservative for cold-start | Checked with today's real numbers: 00631L converges to ~92% filled by day 5 under the current 40%/day geometric taper; today's turnover (~34%) is well under the 50% cap, so the cap isn't even binding. `max_initial_buy_fraction=0.4` has never been grid-searched but no evidence a faster pace would help. No change. |
| 5 | Compounding-regime guard should also force-reduce existing positions, not just block adds | Existing shadow data (`00631l_compounding_regime_no_add_shadow_strict_20260715.json`, 82 events) shows the held-vs-target gap during MEAN_REVERTING days is already tiny (0.02%-0.5%) — little room for a force-reduce rule to matter. Matches Fable's own low-confidence rating. Closed, not worth building new backtest machinery for. |
| 6 | (see Finding 3 above — escalated, not a "no action" item) | |
| 7 | `commission_discount=1.0` (no discount) — does it match the user's real brokerage? | User confirmed: no discount, so the current default is already correct. Sensitivity check also run beforehand (1.0 down to 0.10 discount): final_value spread only $8,624 (0.3%), Sharpe spread only 0.0037 — a2118's low turnover (4 rebalances per 2.5yr window) means commission assumptions barely matter either way. |
| 8 | Where does golden1's 30% cash weight come from? | Traced to `results/signal_group_a_*.json` -> `models/portfolio/group_a_production_2020_2025_100k.zip`, a **reinforcement-learning (PPO-family) model** with a discrete `triplet_v4` action schema. The 30% is a discrete RL action choice, not a continuously-computed risk-parity/Kelly figure. This model is trained only through 2025 and the golden_signal feed is separately known to be 6+ days stale. Retraining/auditing this RL model is a large, separate undertaking — out of scope today, flagged for whoever picks up Group A (not Group A+) work. |
| 10 | Is `_apply_bearish_high_risk_trim`'s 20%/30% trim fraction validated? | a2118.py's own `backtest_live_discrepancy` field already documents this as not historically reconstructable (needs live `signal_alignment`). Its own diagnostic proxy: `high_chip_golden1_days=4` out of 291 golden1 days in 2025-2026 — sample too small (≤4 days) for any statistical validation. Inherited existing known limitation, nothing new to do. |

---

## Separately reviewed: six papers (arXiv:2606.08450, arXiv:2602.01388, arXiv:2605.01384, arXiv:2512.15739, arXiv:2605.20636v2, arXiv:2603.21330)

A sixth paper (FinRL-X, arXiv:2603.21330) was reviewed on 2026-07-24 --
see its own subsection at the very end of this section. Unlike the first
five, it is a **systems/architecture** paper, not a strategy paper, and
is the most directly relevant of the six: its core principle would have
structurally prevented the exact bug class found in this handoff's own
Finding 2 (a2118.py's backtest never calling the same overlay functions
daily_signal.py's live path calls). Flagged as a real (but larger, not
done today) refactoring direction, distinct from the "not applicable"
verdicts on the first five.

Five unrelated papers were brought in later in the same session, each in
a separate follow-up exchange. Four were reviewed and rejected outright;
the fifth had a genuinely different, partially-positive verdict (see its
own subsection at the end -- **process-methodology adoption suggested,
no strategy-logic import**). The first three were rejected for the same
underlying reason (architecture mismatch: all three improve a
PPO/DDPG/TD3/A2C/Actor-Critic-style RL agent's training interface,
network architecture, or loss function, and Group A+'s actual production
decision logic -- a2118, NCF gradient-boosted-tree ensembles, rule-based
switch/guard logic -- is not RL at all); the fourth (Bayesian risk
modeling) for a different reason -- task/scope mismatch plus the one
relevant piece already existing and not being clearly supported by the
paper's own evidence. Full detail below; see also the second paper's
section for a specific "what if the hypothesis were true anyway"
follow-up analysis, since the user pushed on that specific question.

### GIFT paper (arXiv:2606.08450)

User provided `C:\Users\isaac\Downloads\2606.08450.pdf` ("GIFT: LLM-Guided
State-Reward Interface for Financial Reinforcement Learning") and asked
whether it has anything importable into Group A+. Full read + verdict:
**not applicable**. GIFT's entire contribution (LLM-guided, diagnostic-
refined state/reward interface design) presupposes a PPO/RL agent being
trained — Group A+'s actual decision logic (a2118, NCF gradient-boosted-
tree ensembles, switch rules) is not RL at all, so there is no state/
reward/policy to attach this to. The only genuine RL surface anywhere in
this project is the separate, dormant Group A base-weight model
discovered in Finding/direction 8 above — GIFT's methodology could
theoretically inform a *future retrain* of that specific model, but that
is out of scope today. One candidate idea (GIFT's diagnostic-refinement
loop, i.e. use per-feature IC/importance to prune candidates before
committing to a full backtest) was initially proposed as importable, then
found to **already exist and be more rigorous** in this codebase:
`scripts/misc/ncf_00631l.py`'s `_feature_selection` /
`evaluate_feature_stability` (actively called at lines ~1514, ~1801,
~2483, ~2944) already do walk-forward TimeSeriesSplit feature-importance
stability analysis with A/B/C/D grading — GIFT only does single-shot IC
without the fold-stability check. Net verdict: nothing in this paper is
usable for this project, not because of laziness but because either the
architecture doesn't match or the idea is already implemented, and in
one case implemented better.

### PIKAN paper (arXiv:2602.01388) — "Physics-Informed Kolmogorov-Arnold
Networks... Applications of Newton's Laws in Financial DRL"

Replaces MLPs with spline-based Kolmogorov-Arnold Networks (KANs) in the
actor/critic of A2C/DDPG/PPO/TD3, and adds a "physics-informed" loss term
during actor updates: treats 1-day return as a velocity analogue, the
agent's action as a force, and penalizes (via MSE) the gap between
action-implied acceleration (`action/mass`) and observed return
acceleration (second difference of returns) — i.e. a smoothness/inertia
regularizer coupling the RL policy's action updates to observed return
dynamics, tested across CSI 300 / VN100 / S&P 100 10-stock portfolios.

**Verdict: not applicable, same root cause as GIFT** — both mechanisms
(KAN architecture, physics-loss regularization term) are specific to a
neural-network policy's gradient-based training loss. Group A+'s NCF
pipeline is gradient-boosted-tree ensembles trained with supervised
classification loss, not an RL actor with a policy loss to attach a
physics regularizer to. Unlike GIFT, this paper doesn't even offer an
abstractable non-RL methodology to borrow — its contribution is tightly
coupled to neural-net policy-gradient training specifically. The stated
goal (discourage abrupt, noise-driven reallocation) is already achieved
in Group A+ through entirely different, non-ML machinery: staged buying
(`_apply_buy_staging`, 40%/day), the `min_weight_deviation` no-trade band,
and `max_turnover_ratio`.

**Follow-up the user specifically pushed on**: "if Group A's underlying
RL model's actor/critic really is an MLP, would swapping in KAN + the
physics loss show a clear improvement?" Answer given: **no, not
expected**, for five compounding reasons (not investigated further,
this is reasoning from the paper's own reported evidence, not a new
experiment):
1. The paper's own results are algorithm-dependent, not uniformly
   positive — `PPO_PINN` remains deeply negative in all three markets
   (China -34.72%, Vietnam -39.73%, US -45.14%); only `A2C_PINN`
   performs strongly across the board. The technique's value depends
   heavily on which base RL algorithm is used, and we don't know Group
   A's algorithm.
2. Weaker validation design than this project's own current bar: single
   train(2015-2023)/test(2023-2025) split, no rolling-window
   cross-validation, no multi-seed robustness check (contrast with
   GIFT's Appendix I, which did both) — exactly the kind of single-
   window evidence this project's own
   `feedback_overfitting_fixed_window_tuning` memory warns against
   trusting.
3. Likely action-space mismatch: PIKAN is built for **continuous**
   portfolio-weight actions (how PPO/DDPG/TD3/A2C are normally used).
   Group A's model's `group_a_action_schema: "triplet_v4"` and its
   discrete `action_label` values (e.g.
   `"rebalance_to_0050_50_00631L_20_cash_30"`) look like a **discrete**
   action space (pick one of an enumerated set of weight combos) — a
   fundamentally different RL setup this paper never tests.
4. Asset-class mismatch: validated on ordinary equities, not daily-reset
   leveraged/inverse ETFs — the "return as velocity" physics analogy has
   never been checked against leverage decay dynamics.
5. Even a genuine improvement to Group A's raw output weights might not
   survive contact with Group A+'s downstream stack (switch rules, NCF
   overlays, guards) that already heavily modifies/dilutes the base
   signal before it reaches a real trade — the same dilution pattern
   found today in Finding 2/3 above.

No code changes, no further investigation needed unless someone commits
to the separate "retrain Group A's RL model" project first.

### SBCA paper (arXiv:2605.01384) -- "Cross-Modal BERT-driven Actor-Critic
for Multi-Asset Portfolio Optimization"

Actor-Critic RL framework with two novel components: (1) a cross-modal
gated fusion module that adaptively blends BERT-derived news-sentiment
features into price-time-series features (proven, via two included
theorems, to be strictly more expressive than naive linear feature
concatenation), and (2) a risk-sensitive reward function (log return minus
a squared downside-risk penalty minus a turnover penalty) with a proven
utility-consistency theorem (under log/CRRA(ρ=1) utility, higher
cumulative reward ⟺ higher terminal expected utility). Tested via
ablation (SB → SBA → SBC → SBCA, isolating Actor-Critic vs. cross-modal
fusion contributions) on 2/4/6-asset baskets of US large-caps
(NVDA/GS/CAT/KO/MRK/GILD), 2012-2022, plus a commission-rate (0.1%-1%)
sensitivity sweep.

**Verdict: not applicable, same root cause as the other two papers above**
-- both novel components (gated fusion, risk-sensitive reward) are
mechanisms for training a neural-net RL policy; Group A+'s NCF pipeline
has no policy/reward to attach either to. Unlike GIFT, this paper offers
no abstractable non-RL methodology either -- it's pure architecture/loss
engineering for actor-critic nets.

One useful, unprompted observation surfaced while reading it: the paper's
own Theorem 2 proves gated fusion beats **linear concatenation**
specifically -- that comparison is irrelevant to Group A+, because NCF's
gradient-boosted-tree ensembles (rf/et/hgb/gb/lgb/xgb/cat/tabnet) were
never doing linear concatenation in the first place; tree splits already
capture nonlinear feature interactions between price and sentiment
features natively. So the specific problem this paper's fusion module
solves doesn't exist in Group A+'s architecture to begin with. The stated
goals (fuse price + text sentiment; penalize downside risk; penalize
turnover) are all already achieved in Group A+ through unrelated,
non-neural-net machinery: sentiment already feeds NCF via
finbert_sentiment / llm_sentiment_features.py / watchlist_news.py;
downside-risk penalization is what NCF's tail_reward_risk_score /
prob_fwd_mdd_gt5_h20 labels are for; turnover penalization is
execution_plan.py's no-trade band and max_turnover_ratio. Same small-
basket-of-ordinary-equities validation-scope mismatch as the other two
papers (no leveraged/inverse ETFs tested). No code changes.

### Bayesian risk modeling paper (arXiv:2512.15739) -- "Bayesian Modeling
for Uncertainty Management in Financial Risk Forecasting and Compliance"

Not an RL paper -- three independent Bayesian pipelines: (1) a Dynamic
Linear Model (DLM, random-walk-on-log-volatility state-space model) for
S&P 500 volatility forecasting, validated via proper Kupiec (unconditional
coverage) and Christoffersen (independence / conditional coverage) VaR
backtests; (2) Bayesian logistic regression for credit-card fraud
detection (AUC 0.953); (3) a hierarchical Beta state-space model for
compliance-risk monitoring. Plus GPU-accelerated NUTS/ADVI inference and
a Kafka-based ERP-to-FinTech streaming architecture.

**Verdict: not applicable**, but for a different reason than the RL
papers above:
- Components (2) and (3) are irrelevant by task -- Group A+ is a
  portfolio allocation strategy, not a fraud-detection or regulatory-
  compliance system; those tasks don't exist in this project.
- The Kafka/GPU/ERP streaming infrastructure is over-engineered for this
  project's actual scale (single-user daily-batch DuckDB pipeline, not an
  institutional real-time system needing sub-2-second ingestion).
- Component (1), the only plausibly relevant piece, doesn't clear the
  bar on two counts: (a) the paper's **own** VaR backtest table (Table
  IV) shows the DLM is "slightly liberal" (6.0% exceedances vs. nominal
  5%) **and fails the Christoffersen independence test** (p=0.042,
  violations cluster) -- their own LSTM baseline actually passes both
  tests comfortably (p=0.510 / p=0.237 / p=0.400) and is the
  best-calibrated model in their own table, undercutting the paper's own
  headline claim for the one metric that matters most for a tail-risk
  overlay. (b) Kupiec-style VaR backtesting is not a new idea for this
  project -- `_metrics()` in `backtest_group_a_plus_switch_policy.py`
  already reports `kupiec_lr_5pct`/`kupiec_pvalue_5pct` as standard
  output on every backtest run (confirmed present in results read earlier
  this same session, e.g.
  `00631l_compounding_regime_no_add_shadow_strict_20260715.json`). A
  GARCH-based volatility-regime router
  (`group_a_plus/integrations/garch_regime_shadow.py`) was already built
  and tested to exhaustion earlier this project (no consistent
  out-of-sample edge across a 6-fold walk-forward, per
  `project_garch_specialist_routing_2008_20260705` memory) -- this
  paper's DLM targets the same underlying problem (model volatility to
  drive risk decisions) and its own evidence doesn't show it clearing the
  bar that approach already failed at. No code changes.

### Growth/Defensive smooth-score timing paper (arXiv:2605.20636v2) --
"Continuous Timing Signals for Growth-Defensive Style Allocation"

**Not an RL/neural-net paper** -- the first of the five that isn't. A
rule-based continuous-score framework for timing allocation between a
growth/tech ETF basket and a defensive income/value ETF basket: four
softplus-smoothed signals (rate relief, SPY drawdown depth, VIX stress
relief, growth-crowding penalty from 126-day trailing relative
outperformance) sum into a score, mapped through tanh into a continuous
target weight (replacing discrete regime labels/if-then rules), then
EWMA-smoothed. Validated properly: walk-forward expanding, walk-forward
rolling, fixed-parameter, and a dedicated post-2022 robustness check
added specifically to reduce dependence on the 2020 COVID crash (whose
defensive basket had an anomalously large drawdown in-sample), plus a
0/5/10/20bp transaction-cost sensitivity sweep. Honest about its own
limits: doesn't beat 100% growth in raw CAGR, ~400-470%/year turnover.

**Verdict: mixed -- no strategy-logic import, but one process/methodology
practice worth adopting.**

1. **Worth adopting: the three-tier OOS validation + explicit crisis-
   independence check + cost-sensitivity sweep, as a standard checklist**
   for evaluating future Group A+ signal/overlay candidates. This is
   more systematic than most existing `scripts/evaluate/*.py` scripts in
   this repo, which each pick their own ad hoc validation window. Low
   risk (pure process, no strategy change). **Adopted same-session**: see
   `GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md` for the
   standing checklist future evaluations should follow.
2. **Tested 2026-07-25, closed with a negative result: the paper's
   growth-crowding penalty** ("penalize when a trend has run far and VIX
   is complacently low") is philosophically the opposite of Group A+'s
   current NCF gating logic (`ma_gap_bull_threshold=0.40` in
   `group_a_plus/integrations/ncf.py::ncf_regime_gated_signal`
   *suppresses* the downside overlay during strong/extended trends, i.e.
   "don't fight a strong trend" -- the opposite of "penalize an extended
   trend as crowded"). Originally left as "worth a future debate, not
   something to silently import." The debate is now resolved by evidence:
   built as a new component (126-day trailing relative return, 0050 vs
   00679B, z-scored) in the A21.19 shadow candidate's
   `build_defensive_tilt()` and tested standalone (IC) and blended into a
   real backtest across three windows. IC is genuinely correctly-signed
   (unlike `rate_stress`/`tsmc_crowding`), but blending it into the tilt
   makes annual-return delta monotonically worse in every window tested,
   with only one narrow, non-generalizing Sharpe exception at low weight
   in the tuning window. See
   `GROUP_A_PLUS_A2119_CONTINUOUS_DEFENSIVE_TILT_SHADOW_HANDOFF_20260724.md`'s
   2026-07-25 addendum #7 for full detail. No code change to production;
   the new component's weight (`w5_crowding`) stays at its 0.0 default in
   the research script.
3. **Explicitly NOT recommended: importing the core "continuous smooth
   score replaces discrete regime state" idea itself.** It's the closest
   in spirit to something Group A+ already has (the NCF continuous
   downside overlay, `ncf.py::adjust_golden1_weights`) -- and this same
   2026-07-23 session already quantified that existing continuous
   overlay's cost at -10.75pp/year with no measurable risk benefit in
   the only testable window (see Finding 2 above,
   `project_a2118_ncf_live_overlay_backtest_gap_20260723` memory). The
   paper's positive result is in a different asset class (growth vs.
   value/income US equities) under a different validation regime; it
   does not override Group A+'s own contradicting evidence on the
   closest existing analog. No code changes.

### FinRL-X systems paper (arXiv:2603.21330) -- "An AI-Native Modular
Infrastructure for Quantitative Trading" (reviewed 2026-07-24)

Not a strategy paper -- a **systems architecture** paper from the
AI4Finance Foundation (same group that maintains the FinRL library this
project's `FinRL/` directory is built on). Core principle: structure the
trading pipeline as a chain of weight-vector transformations,
`w_t = RiskOverlay(TimeAdjust(Allocate(Select(X))))`, where every
stage's *sole* interface contract is a target-allocation weight vector --
and, critically, **backtesting and live/broker execution consume the
exact same weight-producing code path**, not two separately-maintained
implementations. The paper's own stated motivation is that backtest-to-
live divergence ("Sresearch != Splive") is usually an *engineering*
failure (parallel/inconsistent implementations), not a modeling failure.

**Verdict: the one paper of the six reviewed this session that is
directly relevant, though as an architecture lesson, not a code import.**
Its core principle is the structural fix for the exact bug class this
handoff's own Finding 2 identified: `a2118.py` (backtest) imports
`ncf_overlay_summary` but never calls it, while `daily_signal.py` (live)
does call it -- meaning the Sharpe/return numbers used to justify keeping
a2118 active were never actually produced by the same code that runs
live. Had Group A+'s NCF overlay / guards / staging been built from the
start as composable weight-vector stages shared by both a2118.py and
daily_signal.py (rather than daily_signal.py accumulating overlay logic
inline, separately from a2118.py's backtest), this specific divergence
could not have happened -- it would have been structurally impossible
for backtest to silently skip a stage that live applies.

**What's NOT applicable**: the broker-integration, paper-trading-as-
deployment-validation, and operational-resilience (crash recovery, API
fault tolerance) sections don't apply today -- the user confirmed all
orders are placed manually, so there is no broker API connection to
harden (this would become relevant if/when automation is ever built --
see `feedback_automation_first_design_principle` memory). The paper's own
empirical results (DRL+timing on NASDAQ-100 rolling selection, sector
rotation Sharpe numbers) are a different asset universe (broad US
equities/ETFs, dozens of names) from Group A+'s fixed 4-ticker leveraged-
ETF book and carry no evidentiary weight here -- not cited as support for
anything.

**Small-scope import implemented 2026-07-24** (user explicitly chose the
low-risk option over a full `run_a2118()` refactor): today's research
script (`scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py`)
was promoted to canonical, required tooling rather than a one-off. Added
as **checklist item 5** in
`GROUP_A_PLUS_SIGNAL_VALIDATION_CHECKLIST_20260723.md`: whenever a2118's
headline Sharpe/annual-return numbers are cited for a promotion, revert,
or "keep as-is" decision, this script's overlay-inclusive numbers must be
reported alongside. `report/group_a_plus/latest/strategy.json`'s
`active_strategy.improvements` block got a new `citation_rule_20260724`
field pointing to this rule (mirrors the `sharpe_delta_status` staleness
flag added earlier the same day). The script's own docstring was updated
to state its new canonical role. Verified: script still runs and produces
the same numbers as this morning's run (`golden1_days=291,
overlay_active_days=157`); 55 related tests (`test_group_a_plus_latest_
strategy.py` etc.) still pass after the strategy.json edit.

**NOT done, explicitly deferred**: a real refactor of Group A+'s weight-
generation logic (a207 regime -> NCF continuous overlay -> hard late-bull
overlay -> bearish-risk trim -> pre-trade guards -> staging) into a
formal Select/Allocate/Time/Risk pipeline with one shared implementation
consumed by both `a2118.py`'s backtest and `daily_signal.py`'s live path
-- the "real" architectural fix that would make this class of divergence
structurally impossible, not just flagged by a citation rule. This is a
larger, cross-cutting engineering task the user was offered as a mid-size
option and declined for today, given `run_a2118()` has too many existing
callers/tests to safely restructure its simulation engine in one sitting.
Worth a dedicated future session if this project wants to close the gap
properly rather than just paper over it with a process rule.

---

## Files touched this session

**Modified (production):**
- `group_a_plus/operations/execution_plan.py`
- `tests/test_group_a_plus_execution_plan_v2.py`
- `report/group_a_plus/latest/strategy.json`
- `report/group_a_plus/latest/execution_plan.json` (regenerated with new
  advisory-only guard behavior, cash_balance=1,000,000)

**New (research-only, no production wiring):**
- `scripts/evaluate/evaluate_a2118_live_overlay_backtest_gap.py`
- `results/a2118_live_overlay_backtest_gap_latest.json`
- `results/a2118_live_overlay_backtest_gap_ncf_only.json`
- `results/a2118_live_overlay_backtest_gap_ncf_only_banded.json`
- `results/group_a_plus_execution_plan_v2_20260723_advisory_review.json`

**This file:**
- `GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md`

**Claude persistent memory** (for cross-session continuity, not part of
the repo): `project_advisory_guard_auto_block_fix_20260723`,
`project_a2118_ncf_live_overlay_backtest_gap_20260723`,
`project_a2118_ncf_hedge_dormancy_root_cause_20260723`,
`project_a2118_remaining_fable_directions_5_8_10_20260723`,
`feedback_automation_first_design_principle`.

## Suggested next steps for whoever picks this up

1. Full test suite already re-verified green after all changes; no
   pending test debt.
2. If NCF panels ever extend backward or a real drawdown period enters
   the live 2025-2026 window, re-run
   `evaluate_a2118_live_overlay_backtest_gap.py` to re-check whether the
   live NCF overlay's cost/protection trade-off (Finding 2) still holds.
3. Group A's underlying RL base-weight model (direction 8) is stale
   (trained through 2025, golden_signal feed 6+ days behind) and was
   only diagnosed, not fixed — a legitimate separate project if anyone
   wants to pick it up.
4. The open follow-up in Finding 3 (reconstruct the original pre-06-29
   panel that produced 3 trigger days) is the only unclosed thread from
   the original 10 Fable directions.
