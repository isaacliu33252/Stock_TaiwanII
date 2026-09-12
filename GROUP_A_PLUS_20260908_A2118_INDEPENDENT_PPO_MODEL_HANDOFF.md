# GroupA+ Handoff: a2118-Independent PPO Model Experiment — 2026-09-08

## Status

**Research complete for this session. No production change made. No clean win found.**

This thread started from a much narrower question ("no-trade band 能做更詳細的分析?" — see
the "Direction 6 deeper analysis" section of `GROUP_A_PLUS_20260908_FABLE_10_DIRECTIONS_HANDOFF.md`)
and escalated, through several user-directed steps, into training six new PPO models to give
a2118 (最新策略, the live production runner) a golden1 signal source independent of
golden1_0531. **All six models are saved to disk. None has been wired into production.**
`report/group_a_plus/latest/strategy.json` and `DEFAULT_GOLDEN_SIGNAL` are unchanged — a2118
still consumes golden1_0531's output exactly as before this session.

## Why this thread exists (chain of reasoning, in order)

1. Deep-dived direction 6's no-trade-band claim and found production's own golden1 generation
   (`train_dual_group_2024_2026.py`) already gates PVA-driven weight changes at
   `pva_drift_threshold=0.05` (5% L1) — a no-trade band already exists. See the handoff section
   referenced above for the full writeup and the corrected proxy re-test.
2. User asked whether 6-8% would be better than the current 5%. A sweep showed 6% specifically
   improves all 4 test windows with no downside; 8% is mixed (great in covid_2020, worse in the
   two recent windows).
3. User asked to change it — but `pva_drift_threshold` is part of golden1_0531's frozen PVA
   formula, and golden1_0531 is explicitly immutable
   (`feedback_golden1_0531_immutable_naming` memory: "golden1_0531 是不能動的").
4. User asked to change it on "最新策略" (a2118) instead. Investigation found a2118 has **no
   PVA mechanism of its own** — it consumes golden1_0531's already-generated output file
   (`DEFAULT_GOLDEN_SIGNAL` in `backtest_group_a_plus_policy_signal.py` literally points to a
   `signal_group_a_golden1_0531_predict_*.json` file), confirmed directly from
   `report/group_a_plus/latest/strategy.json`'s active `runner_params` (no override present).
5. User stated the underlying architectural expectation: golden1_0531, golden2_0830, and
   "最新策略" (a2118) should not reference each other. Checked golden2_0830 — it is genuinely
   independent (never wired into a2118 or strategy.json, per the 2026-08-31 promotion review that
   rejected it). **a2118 is the one violating this — it depends entirely on golden1_0531.**
6. User chose to fix this by training a brand-new, independently-trained PPO model for a2118,
   rather than switching to golden2_0830 (already known-weaker) or a rule-based replacement.

## What was built

### Training setup (all 6 models)

- Script: `train_dual_group_2024_2026.py` (the existing Group A/B PPO training pipeline —
  reused, not newly written; this is the same tool that originally produced golden1_0531).
- Tickers: `0050.TW, 00631L.TW, 00679B.TWO, 00632R.TW` (Group A default).
- **Training window: 2017-01-11 – 2019-12-31** (requested 2016-01-01, but 00679B.TWO's data
  starts 2017-01-11). Chosen specifically to leave `covid_2020` and `inflation_2022` — the two
  crisis windows used throughout today's session — genuinely out-of-sample.
- **PVA/SJM continuous risk scaling: enabled**, with `pva_drift_threshold=0.06` (vs golden1_0531's
  0.05 — the one deliberate design change carried over from the no-trade-band finding above).
  All other PVA params matched golden1_0531's documented release config
  (`pva_weight=0.32, pva_j_state_weight=0.19, pva_m_state_weight=1.00, pva_target_vol=0.012,
  pva_min_leverage_scale=0.40, pva_inverse_hedge_budget=0.30`).
- **Disclosed feature gaps vs golden1_0531** (not a choice, a data-availability constraint):
  - No institutional features: `institutional_data` table only starts 2020-01-02, which
    postdates the entire 2017-2019 training window.
  - No LLM sentiment features: no historical sentiment table exists in the DB at all.
- Execution timing: signal from day t, executed at t+1 open, performance marked at t+1 close
  (no same-day lookahead) — this is the training script's own standard convention, unchanged.
- No GPU available (4-core CPU only). Actual training speed ~243-290 fps, so even 400K steps
  completed in ~27 minutes — far faster than initially estimated.

### The six models (`models/portfolio/`)

| Model name | Profile | Timesteps | Notes |
|---|---|---|---|
| `a2118_independent_ppo_v1` | default | 150,000 | first run; **note the inconsistent name — this is the 150K model, not tagged `_150k`** |
| `a2118_independent_ppo_v1_400k` | default | 400,000 | script's own default step count |
| `a2118_independent_ppo_v1_100k` | default | 100,000 | matches golden1_0531's original step count |
| `a2118_independent_ppo_v1_80k` | default | 80,000 | best of the default-profile sweep |
| `a2118_independent_ppo_v1_50k` | default | 50,000 | |
| `a2118_independent_ppo_v1_80k_conservative` | **conservative** | 80,000 | targeted retune for the MDD weakness found below |

### Raw standalone backtest (2024-01-02 – 2026-09-04, PPO model only — no switch rule, no defensive-basket overlay)

| Steps (default profile) | Final value | Return | Annualized | Sharpe | MDD | Trades | PVA triggers |
|---|---|---|---|---|---|---|---|
| 50K | 3,544,525 | 254.45% | 63.58% | 1.666 | -35.45% | 113 | 60 |
| **80K** | **3,595,510** | **259.55%** | **64.49%** | **1.681** | -35.45% | 113 | 59 |
| 100K | 3,594,106 | 259.41% | 64.46% | 1.675 | -35.66% | 113 | 59 |
| 150K | 3,557,014 | 255.70% | 63.80% | 1.670 | -35.63% | 113 | 60 |
| 400K | 3,252,786 | 225.28% | 58.20% | 1.613 | -34.80% (best MDD) | 112 | 46 |
| 80K conservative | 3,338,669 | 233.87% | 59.81% | **1.900** | **-20.76%** (much better) | 41 | 5 |

**Finding 1 — timesteps form a plateau + cliff, not a monotonic curve.** 80K-150K cluster
tightly (final value 3.54-3.60M, Sharpe 1.67-1.68); 400K is a clear, non-noisy step down on
every metric except MDD. This is consistent with PPO overfitting/entropy-collapse past a
training-window-specific optimum, not per-run noise — the curve is smooth. **80K was adopted as
the primary candidate** (user: "先以80K為主繼續").

## Real a2118 integration test (not the H3-limited kind)

Unlike the earlier direction-6 "a2118-faithful" attempt (which hit the H3 static-golden1-snapshot
wall because it tried to reconstruct golden1 weights externally), this integration is NOT
H3-limited: each model's own backtest run (one per window: 2020, 2022, 2024-2026) already produced
a genuine daily target-weight trajectory
(`group_a.result.daily_target_weight_history[].final_target_weights`, keyed by `execution_date`).
Script: `scripts/misc/test_a2118_independent_ppo_v1_80k_integration_20260908.py` (parametrized via
`--result-files <f1> <f2> <f3> <label>`).

Method: run `a2111._build_switch_rule()` (the real production switch rule, unchanged) over real
price/chip data to get the golden1 ↔ group_a_plus_defensive regime series per day. On
`golden1` days, use the new model's real weight for that `execution_date` (falling back to "hold
current weight" for the small number of days outside the model's exact backtest range — see
coverage caveat below). On `group_a_plus_defensive` days, use the real current production basket
(`bond0_cash60`). Compare against a real `run_a2118()` call (golden1_0531, current production
defaults) over the identical windows.

### Integration results

| Window | production (golden1_0531) | new model 80K default (integrated) | new model 80K conservative (integrated) |
|---|---|---|---|
| covid_2020 | final 1,285,414 / Sharpe 1.815 / **MDD -14.64%** | 1,356,388 / 1.675 / -19.76% | 1,184,157 / 1.168 / -19.45% |
| inflation_2022 | 899,711 / -0.931 / **MDD -16.45%** | 852,558 / -1.058 / -21.38% | 864,089 / -1.165 / -19.95% |
| live_2024_2026 | 2,870,686 / 1.848 / **MDD -20.47%** | 3,206,393 / 1.774 / -24.16% | 2,338,928 / 1.649 / **-27.69% (worst of all three)** |
| active_2025_2026 | 2,123,517 / 2.053 / -16.44% | 2,402,703 / 2.064 / -19.38% | 1,955,432 / 2.050 / **-15.88% (only case beating production's MDD)** |

**Finding 2 — the default-profile 80K model beats production on final value in 3/4 windows
(+5.5% to +13.2%) but loses on MDD in all 4 windows (2.9-5.1pp worse), and loses on both return
AND risk in `inflation_2022`, the one genuine bear-market window.** Not a clean win by this
project's own established standard (MDD/crisis-window performance prioritized over raw return —
see `feedback_strategy_promotion_caution`).

**Finding 3 — the conservative-profile retune, motivated specifically to fix Finding 2's MDD
weakness, made things worse once integrated, despite dramatically improving the RAW standalone
MDD** (-35.45% → -20.76% raw covid_2020: -35.60% → -10.65%). Once wrapped in the real switch
rule, the MDD improvement almost entirely evaporates (covid_2020: only 0.31pp better than the
default-profile integration) and in `live_2024_2026` it's actively worse (-27.69% vs the
default profile's -24.16%) — likely because the switch rule itself already provides most of the
crisis de-risking via regime transitions, so the conservative model's own extra caution during
golden1-regime days shows up mostly as forgone upside rather than additional protection, and in
at least one window (live_2024_2026) may have made timing worse. This is the same
"proxy/standalone result doesn't survive faithful integration" pattern this project has now hit
independently in directions 5, 6, and 8 this week — see
`project_fable_direction5_and_8_audit_confirmation_20260908.md` and
`project_direction6_no_trade_band_production_gate_correction_20260908.md`.

### Known coverage caveat (not yet resolved)

In `covid_2020` and `inflation_2022`, roughly half the `golden1`-regime days in the simulated
range don't have a corresponding model weight (168/305 and 66/168 respectively) — these fall back
to "hold the currently-held weight" in the integration script. This is very likely concentrated in
the 200-calendar-day warmup period *before* each window's official start (each model's own
backtest was run for the exact window only, e.g. `2020-01-02..2020-12-31`, so anything before that
date has no model weight by construction) — meaning it should not bias the reported `[start:end]`
metrics, since those only cover dates the model backtest genuinely spans. **This has not been
independently verified**, only reasoned through; a full audit would check the actual date-by-date
overlap.

## Correction (same day, later pass): the 4-window comparison was not apples-to-apples

`GROUP_A_GOLDEN1_0531_RELEASE.md` section 3, checked only after the integration results above
were already written up: **golden1_0531 was trained on `2020-01-01` to `2024-12-31`**, with its
own documented OOS window being `2025-01-02` to `2026-05-25`. This was not checked before framing
today's 4-window comparison as an OOS test for both sides.

This means, of the 4 windows used throughout this thread:
- `covid_2020` (2020) — **in-sample for golden1_0531**, genuinely OOS for the new models.
- `inflation_2022` (2022) — **in-sample for golden1_0531**, genuinely OOS for the new models.
- `live_2024_2026` (starts 2024-01-02) — **partially in-sample for golden1_0531** (its training
  runs through 2024-12-31), genuinely OOS for the new models.
- `active_2025_2026` (starts 2025-01-02) — **the only window that is genuinely OOS for both**
  golden1_0531 (matches its own documented OOS start date) and the new models.

So golden1_0531's MDD advantage in 3 of the 4 windows reported above is confounded with it having
literally seen those crashes during training — not a clean skill comparison. **Re-reading only the
one fair window (`active_2025_2026`):**

| | production (golden1_0531) | new model 80K default | new model 80K conservative |
|---|---|---|---|
| Final value | 2,123,517 | **2,402,703 (+13.2%)** | 1,955,432 |
| Sharpe | 2.053 | **2.064 (marginal win)** | 2.050 |
| MDD | -16.44% | -19.38% (2.94pp worse) | **-15.88% (beats production)** |

In the one apples-to-apples comparison, the default-profile 80K model wins on final value and
Sharpe and only loses narrowly on MDD; the conservative-profile model's MDD actually **beats**
production here. **This meaningfully weakens (not reverses) the "no clean win" conclusion below** —
it was based on a comparison that gave golden1_0531 a 3-out-of-4-window structural advantage.

Other real training-config differences beyond the date range, also uncontrolled for: golden1_0531
has institutional features, LLM sentiment features, and a "local TWII/0050 regime defensive
overlay" enabled (none of which the new models have, for the data-availability reasons already
disclosed above), uses `triplet_v4` action schema (new models: `triplet_v2`), and caps 00631L at
20% (new models: 30%). Any of these could also be contributing to the remaining gap in
`active_2025_2026` — not just "more/less training" or "profile choice." **None of this has been
isolated or controlled for.**

## Bottom line

- Neither the default-profile nor the conservative-profile new model is ready to replace
  golden1_0531 as a2118's input — but the evidence against them is weaker than first written up.
  On the only fair (both-sides-OOS) window, `active_2025_2026`, the default 80K model wins on
  final value and Sharpe and is only narrowly behind on MDD; the conservative variant's MDD there
  actually beats production. The "loses on MDD everywhere" framing from before the correction
  above was measuring golden1_0531's in-sample advantage in 3 of 4 windows as much as it was
  measuring genuine skill.
- This is 1 seed, 1 training window (2017-2019), 6 model variants total, and only 1 truly fair
  test window (n=1) — a small, single-pass, low-power exploration, not a rigorous architecture
  search. No claim of having found "the best" independent model, and no claim that the default
  80K model's `active_2025_2026` win generalizes.
- a2118's dependency on golden1_0531 is still fully intact in production. This was, and remains,
  a read-only research exercise.

## Multi-seed follow-up (same day, later pass): 3 seeds agree — not single-seed noise

Trained two more seeds of the 80K default profile (`a2118_independent_ppo_v1_80k_seed7`,
`_seed123`) — identical config to the original seed42 80K default, only the PPO seed changes.

**Methodology bug caught and fixed mid-pass**: the seed7/seed123 integration comparisons already
sitting in `results/` from earlier in the day (`a2118_independent_ppo_v1_80k_integration_new_model_80k_seed{7,123}_20260908.json`,
no `_v2` suffix) were invalid — they were built by passing `--result-files` a single backtest
file covering only `active_2025_2026` (2025-01-02..2026-09-04), so `covid_2020` and
`inflation_2022` had **zero** model-weight coverage (100% fallback to "hold last position") and
`live_2024_2026` had only 332/710 days covered (all of 2024 fell back too). Do not cite those
files. Fixed by re-running `train_dual_group_2024_2026.py --group-a-backtest-only-model
a2118_independent_ppo_v1_80k_seed{7,123}` (no retraining, ~1 min each) for `covid_2020`,
`inflation_2022`, and a full `2024-01-01..2026-09-04` window per seed, then re-running the
integration script with the correct 3-file `--result-files`. Outputs (coverage now matches the
seed42 baseline, e.g. 468/468 in `active_2025_2026`):
- `results/a2118_independent_ppo_v1_80k_integration_new_model_80k_seed7_v2_20260908.json`
- `results/a2118_independent_ppo_v1_80k_integration_new_model_80k_seed123_v2_20260908.json`

**On the one genuinely fair window (`active_2025_2026`), 3 seeds now agree closely:**

| | production | seed42 (original) | seed7 | seed123 |
|---|---|---|---|---|
| Final value | 2,123,517 | 2,402,703 (+13.2%) | 2,368,771 (+11.5%) | 2,408,331 (+13.4%) |
| Sharpe | 2.053 | 2.064 | 2.046 | 2.068 |
| MDD | -16.44% | -19.38% (-2.94pp) | -19.38% (-2.94pp) | -19.62% (-3.18pp) |

This is a tight, consistent pattern across 3 independent seeds, not single-seed luck: final value
beats production by 11.5-13.4% every time, Sharpe is a wash (within ±0.02 of production in both
directions), and MDD loses to production by a stable 2.9-3.2pp every time. The earlier caveat
("results might just be seed42 noise") no longer applies — the default-80K-profile "recipe" (2017-
2019 training window, standard action schema/exposure caps) has a real, reproducible final-
value/MDD trade-off versus golden1_0531 on this window, not something that would flip with a
different random seed.

**Still not a promotion case, for reasons multi-seeding cannot fix**: there is still only 1
genuinely fair (both-sides-OOS) test window — more seeds add confidence within that one window,
not more windows. The other uncontrolled training differences (institutional features, LLM
sentiment, local TWII regime overlay, action schema `triplet_v2` vs `v4`, 00631L cap 30% vs 20%)
are still untouched. No multi-window significance testing has been run. Nothing in production
changed.

Memory: `project_a2118_independent_ppo_model_experiment_20260908.md` (multi-seed section appended).

## Isolation follow-up (same day, later pass): 00631L cap 30%->20% nearly closes the MDD gap alone

Continuing item 2 from "what would meaningfully continue this line": isolate the uncontrolled
training differences one at a time instead of changing all of them plus the training window at
once. Institutional features and LLM sentiment are hard data-availability gaps for the 2017-2019
training window (already disclosed above, not a choice). The local regime gate has no CLI flag in
`train_dual_group_2024_2026.py` (`local_regime_gate_enabled` is only wired programmatically via
`generate_dual_group_signal.py`) — testing it would require a code change, not attempted here. Two
remaining differences are controllable via existing CLI flags, changed one at a time from the
seed42 80K default baseline (2017-2019 window, PVA config unchanged):
- **tripletv4 variant**: action schema `triplet_v2` -> `triplet_v4` (9 discrete actions incl.
  partial-cash-holding options), 00631L cap stays 30%. Model:
  `a2118_independent_ppo_v1_80k_tripletv4`.
- **cap20 variant**: 00631L cap 30% -> 20% (matches golden1_0531's actual cap), action schema
  stays `triplet_v2`. Model: `a2118_independent_ppo_v1_80k_cap20`.

Same procedure as the multi-seed pass: train 80K steps + backtest 2024-2026, then
`--group-a-backtest-only-model` for covid_2020 and inflation_2022, then the integration script.

**On `active_2025_2026` (the one fair window):**

| | production | original 80K (30% cap, v2) | tripletv4 (30% cap) | cap20 (20% cap, v2) |
|---|---|---|---|---|
| Final value | 2,123,517 | 2,402,703 (+13.2%) | 1,964,460 (-7.5%) | **2,317,731 (+9.1%)** |
| Sharpe | 2.053 | 2.064 | 2.030 (loses) | **2.218 (clear win)** |
| MDD | -16.44% | -19.38% (-2.94pp) | **-15.89% (beats prod by 0.55pp)** | **-16.34% (basically tied, -0.10pp)** |

**Finding A (tripletv4)**: the action schema is a real contributor to the MDD gap — swapping it
alone drops MDD from -19.38% to -15.89%, beating production. But it costs almost all the upside:
final value flips from +13.2% to -7.5%, Sharpe also loses. The finer-grained cash-holding options
do reduce risk, but this checkpoint apparently didn't learn to use them selectively — same
"defensive fix trades away upside" pattern seen elsewhere this week (direction 5/8 audit).

**Finding B (cap20) — the most important result of this pass**: capping 00631L at 20% instead of
30% (everything else unchanged, still triplet_v2) very nearly closes the MDD gap entirely
(-16.34% vs production's -16.44%, only 0.10pp off) **while still keeping a 9.1% final-value edge
and actually improving Sharpe to a clear win (2.218 vs 2.053)**. This means a meaningful share of
the "new model loses on MDD everywhere" pattern that 3 seeds already confirmed wasn't noise may
simply be the 30%-vs-20% leverage cap difference, not something inherent to independent training.
`cap20` is the first candidate in this whole line that ties or beats production on all three
metrics simultaneously on the one fair window.

**Caveat — same warning that applied to the original 80K result before multi-seeding**: cap20 has
only been tested at seed=42 so far. Institutional features, LLM sentiment, and the local regime
gate are still unisolated. Still only one genuinely fair window. Before treating "cap20 ties
production" as more than seed42 luck, it needs the same seed7/seed123 verification the baseline
80K model already went through.

Memory: `project_a2118_independent_ppo_model_experiment_20260908.md` (isolation section appended).

## cap20 multi-seed verification (same day, later pass): seed42 was optimistic — gap shrinks, doesn't close

Trained `a2118_independent_ppo_v1_80k_cap20_seed7` and `_seed123` (same cap20 config, different
seeds), same covid_2020/inflation_2022/2024-2026 backtest-only + integration procedure.

**On `active_2025_2026`, 3 seeds:**

| | production | cap20 seed42 | cap20 seed7 | cap20 seed123 |
|---|---|---|---|---|
| Final value | 2,123,517 | 2,317,731 (+9.1%) | 2,307,775 (+8.7%) | 2,317,750 (+9.1%) |
| Sharpe | 2.053 | 2.218 | 2.086 | 2.091 |
| MDD | -16.44% | -16.34% (-0.10pp) | -18.31% (-1.87pp) | -18.42% (-1.98pp) |

**Correction to the single-seed finding above**: seed42's near-perfect MDD tie did **not**
reproduce — seed7 and seed123 both lose to production by ~1.9-2.0pp on MDD, and seed42 is clearly
the most optimistic of the three, not representative. But even using the more conservative
seed7/seed123 numbers, the MDD gap (-1.87 to -1.98pp) is only about **2/3 the size** of the
original cap30 model's gap (-2.94 to -3.18pp) — a real, consistent (all 3 seeds agree on the
direction) improvement, just not a full close. Final value (+8.7-9.1%) and Sharpe (2.09-2.22, all
3 seeds beat production's 2.053) hold up cleanly across all 3 seeds, no worse than the original
cap30 profile.

**Correct framing**: 00631L cap 30%->20% is a robust, reproducible, directionally-correct
improvement — it shrinks the MDD gap by roughly a third while fully preserving the final-
value/Sharpe edge — but it is not a free lunch that ties production; it is a smaller, real
trade-off. Still not a promotion case (still n=1 fair window), but the cleanest, most consistent
positive signal this whole research line has produced. Reasonable to carry forward as a shadow
candidate for further tracking.

Memory: `project_a2118_independent_ppo_model_experiment_20260908.md` (cap20 multi-seed section
appended).

## Day-by-day diagnostic (same day, later pass): residual MDD gap traces to golden1-state risk scaling, not action schema or leverage cap

Following the memory file's own earlier "How to apply" note (don't keep sweeping parameters —
understand why MDD still loses once wired to the real switch rule). Wrote
`scripts/misc/diagnose_cap20_seed7_mdd_gap_20260908.py`, which compares cap20_seed7's
(integrated) daily drawdown series against production's, day by day, on `active_2025_2026` — both
use the identical `_build_switch_rule()` regime timeline, so any difference comes from what
happens *inside* `golden1`-regime days, not from disagreeing about when to switch.

**Findings:**
1. Both hit their max drawdown on the **same date** (2026-07-30): model -18.31% vs production
   -16.44%. Same underlying selloff, the model just falls further into it — not a different crisis.
2. During `golden1` days, the model sits **almost continuously pinned at its 00631L 20% cap**
   (weight mostly 0.1773-0.2000, rarely lower) — it isn't doing much internal risk modulation
   inside the golden1 state. Production's realized drawdown is consistently shallower on the same
   calendar days.
3. The single worst daily drawdown-gap (-4.51pp) is on 2025-06-23. Tracing backward: even during
   days both strategies are already in `group_a_plus_defensive` (identical bond0_cash60 basket for
   both), the model's drawdown (measured from its own running peak) is already deeper than
   production's — because the extra loss was accumulated *during the preceding golden1 window*,
   before the regime ever flipped to defensive. The defensive-regime handling itself is not at
   fault; the gap is an old wound carried over from the golden1 phase.

**Working hypothesis (evidence-supported, not independently confirmed)**: golden1_0531's
institutional-flow and LLM-sentiment features most likely let it do finer-grained risk scaling
*within* the golden1 state itself (partial de-risking ahead of a regime-level switch), while the
new model — lacking those features by construction (2017-2019 training window predates the
institutional data table and there is no historical sentiment table at all) — tends toward holding
near-max leverage until the coarser regime switch fires. This reframes where the residual ~2pp gap
likely comes from: **not** the two factors already isolated and largely ruled out this round
(action schema was a net negative trade-off when tested alone; leverage cap only explains about
1/3 of the original gap) but the institutional/LLM-sentiment feature gap that's been flagged as
untestable all session for data-availability reasons.

**Cannot be directly verified**: institutional data doesn't exist before 2020, so testing this
would require retraining on a window that includes 2020+ — which reintroduces the in-sample
overlap with golden1_0531's own 2020-2024 training window (the exact confound "item 1" in this
document has always flagged and never attempted, for that reason).

Memory: `project_a2118_independent_ppo_model_experiment_20260908.md` (day-by-day diagnostic
section appended).

## Institutional-features hypothesis test (same day, later pass): not supported — this line stops here

Took path (a) from the diagnostic's own options: retrained
`a2118_independent_ppo_v1_80k_cap20_2020window_inst` — training window changed to match
golden1_0531 exactly (2020-01-01..2024-12-31), `--group-a-use-institutional-features` enabled,
everything else the cap20 recipe (triplet_v2, 00631L cap 20%, seed=42). **Hit another coverage bug
mid-pass**: the first backtest only covered the exact reporting window (2025-01-02..2026-09-04),
leaving the integration script's ~200-day warmup lookback with zero model-weight coverage
(332/468). Fixed with a `--group-a-backtest-only-model` rerun starting 2024-06-01, restoring full
468/468 coverage.

**On `active_2025_2026`:**

| | production | cap20 seed42 (2017-19, no inst) | cap20 seed7 | cap20 seed123 | cap20+inst (2020-24 window) |
|---|---|---|---|---|---|
| Final value | 2,123,517 | 2,317,731 (+9.1%) | 2,307,775 (+8.7%) | 2,317,750 (+9.1%) | 2,320,210 (+9.3%) |
| Sharpe | 2.053 | 2.218 | 2.086 | 2.091 | 2.103 |
| MDD | -16.44% | -16.34% (-0.10pp) | -18.31% (-1.87pp) | -18.42% (-1.98pp) | -18.05% (-1.61pp) |

**Not supported.** Adding institutional features *and* matching golden1_0531's exact training
window still lands MDD (-18.05%) squarely inside the existing 3-seed spread from the plain cap20
runs (-16.34% to -18.42%) — no systematic improvement, no closer tie to production than plain
cap20 already achieves. The day-by-day diagnostic's hypothesis (institutional/LLM features enable
finer within-golden1 risk scaling) is not confirmed by this test. More likely explanation: the
cap20 recipe already has ~1.6-2pp of natural seed-to-seed MDD variance (seed42 is the optimistic
outlier), and this institutional+matched-window run is just another sample inside that same
variance, not a systematic effect of the added feature. Caveat: single seed, and this test changed
two variables at once (training window + institutional features), so it isn't a fully clean
isolation of the feature alone — but given the result already falls inside existing noise, the
marginal value of further isolating it is low.

## Overall conclusion for this research line

13 models trained today across: baseline sweep (6 timestep/profile variants) -> 3-seed noise check
-> single-variable isolation (action schema, leverage cap) -> cap20 3-seed reverification ->
day-by-day root-cause diagnostic -> institutional-features hypothesis test (not supported).
**Final call**: cap20 (triplet_v2, 00631L cap 20%, 2017-2019 training window) remains the cleanest,
most consistent positive signal from this line — final value +8.7-9.3% and Sharpe wins across all
3 seeds, MDD gap shrunk by roughly a third from the original cap30 model but not eliminated
(~1.6-2pp residual, no single attributable/fixable factor found — not action schema, not leverage
cap, not institutional features). **Not recommending further training on this line.** Every
CLI-controllable difference (action schema, leverage cap, institutional features) has now been
tested individually. LLM sentiment has no historical data at all; the local regime gate has no
exposed CLI flag and (per a quick code read) `local_regime_gate_enabled` in
`train_dual_group_2024_2026.py` appears to be dead code (computed but never consumed) — its real
production effect likely lives elsewhere and would need its own separate investigation, out of
scope here. cap20 can be carried forward as a shadow candidate for tracking; actual promotion
still needs more genuinely fair OOS windows or full multi-window significance testing, neither of
which more model training can produce.

Memory: `project_a2118_independent_ppo_model_experiment_20260908.md` (final section appended).

## What would meaningfully continue this line (not scheduled)

1. **Fix the comparison, not just the model.** Either (a) find/construct more genuinely-OOS test
   windows for golden1_0531 (only post-2025 data qualifies), or (b) retrain a new model on
   golden1_0531's exact 2020-2024 window for a properly controlled comparison — recognizing that
   choice would make `covid_2020`/`inflation_2022` in-sample for the new model too, so it only
   answers "does the independent-model idea work," not "is this specific 2017-2019-trained
   checkpoint good."
2. Isolate the other uncontrolled differences from golden1_0531 (institutional features, LLM
   sentiment, local TWII/0050 regime overlay, action schema `triplet_v2` vs `v4`, 00631L cap
   30% vs 20%) one at a time, rather than changing all of them plus the training window at once.
3. Verify the coverage-caveat reasoning (roughly half of golden1-regime days in the crisis windows
   lack model weight coverage) by checking actual date overlap, not just reasoning about it.
4. Multiple training seeds would be needed before treating any single timestep/profile choice, or
   the `active_2025_2026` win, as more than this-run's noise — today's comparisons are all
   single-seed (seed=42) and n=1 on the one fair test window.
5. If a model is ever found that genuinely clears production's bar on a fair comparison, it would
   still need to go through this project's full promotion-gate process (multi-window significance
   testing, not just eyeballing a handful of numbers) before any production wiring — consistent
   with how every other candidate in this project's history has been evaluated.

## Files from this round (all read-only research; nothing in production changed)

Scripts:
- `scripts/misc/test_a2118_independent_ppo_v1_80k_integration_20260908.py`

Models (`models/portfolio/`):
- `a2118_independent_ppo_v1` (150K), `a2118_independent_ppo_v1_400k`, `_100k`, `_80k`, `_50k`,
  `_80k_conservative`, `_80k_seed7`, `_80k_seed123`, `_80k_tripletv4`, `_80k_cap20`,
  `_80k_cap20_seed7`, `_80k_cap20_seed123`

Result files (`results/`):
- `group_a_backtest_20240101_20260904_20260908_{162655,173145,175510,180917,181915,183750}.json`
  (raw standalone backtests, one per model, 2024-2026 window)
- `group_a_backtest_20200102_20201231_20260908_{182423,183827,222028,222216}.json`
  (default/conservative/seed7/seed123 80K, covid_2020)
- `group_a_backtest_20220103_20221230_20260908_{182450,183852,222047,222107}.json`
  (default/conservative/seed7/seed123 80K, inflation_2022)
- `group_a_backtest_20240101_20260904_20260908_{222057,222118}.json` (seed7/seed123 80K, full
  2024-2026 window)
- `a2118_independent_ppo_v1_80k_integration_20260908.json` (default 80K integration)
- `a2118_independent_ppo_v1_80k_integration_new_model_80k_conservative_20260908.json`
  (conservative 80K integration)
- `a2118_independent_ppo_v1_80k_integration_new_model_80k_seed{7,123}_20260908.json` —
  **invalid, do not cite** (methodology bug: single-file `--result-files`, near-zero model
  coverage on 3 of 4 windows; see multi-seed section above)
- `a2118_independent_ppo_v1_80k_integration_new_model_80k_seed{7,123}_v2_20260908.json` —
  corrected versions, full coverage, cite these instead

Memory: `project_a2118_independent_ppo_model_experiment_20260908.md`.
