# GroupA+ 2026-08-23 Handoff: Fable 10-Direction Review Round 2

## Status

All 10 round-2 directions complete. No return-improving strategy change was
found or promoted. Three directions (1, 3, 4) turned out to duplicate work
already completed in earlier, unindexed sessions (2026-07-02, 2026-07-23,
2026-07-28). Three directions (2, 6, 10) closed negative or found their
target unreachable/nonexistent. Four directions (5, 7, 8, 9) produced
genuinely new findings not previously recorded anywhere in this codebase --
none promotable, but two (5, 9) revise how existing governance/experiment
methodology should be interpreted, and one (8) is new reusable diagnostic
infrastructure.

## User Request

2026-08-22 (continuing the same day round 1 completed): "使用fable 針對目前
project , groupA+　的最新策略　分析, 因00631L預測不準事項， 再提出１０個可以改善收益
的方向，" -- invoke Fable a second time, explicitly instructed to read the
full round-1 handoff (`GROUP_A_PLUS_20260822_FABLE_00631L_10_DIRECTIONS_
HANDOFF.md`) and the entire `research_semantic_registry.json` (26 entries at
the time) before proposing anything, so the new list would not duplicate
round 1's 10 directions.

2026-08-22/23: "一步一步來." -- work through 1-10 in order, one at a time.

Full original round-2 list is in memory `project_fable_10_directions_
round2_20260822` and is reproduced per-item below.

## Fable's Opening Findings (round 2)

Before proposing directions, Fable read `group_a_plus/runners/a2118.py`
(1440 lines) in full, `scripts/misc/ncf_00631l.py` (3343 lines -- the actual
H1/H5/H20 prediction model), all 26 registry entries, and existing governance
artifacts (`panel_drift_triage.md`, `external_sensitivity_observation_log.md`,
`ncf_panel_refresh_recommendation.md`, `promotion_blocked_diagnostic.md`).
Two findings shaped the list: (1) the NCF H20 classifier's feature/model
space is already close to exhausted -- retrain candidates land at ~50.9%
favorable-vs-baseline (coin flip); (2) a live, currently-blocking governance
artifact (`external_sensitivity_observation_log.md`, 0/11 stability
observations) had a documented but unexecuted next-step. Fable explicitly
ruled out re-proposing 00632R as a cross-ticker signal (a2115.py's own
docstring already found its AUC is 0.44-0.46, worse than chance) and the
`multi_window`/`deployment_consistency` gate failures in `promotion_blocked_
diagnostic.md` (belong to the already-shelved GARCH/2008 line, or are the
same by-design staleness gap round 1's direction 1 already accepted).

## Direction 1: Root-cause the 0/11-stable external-sensitivity blocker

**Original framing**: `external_sensitivity_observation_log.md` shows 0/11
stability observations passing; `panel_drift_triage.md` independently flags
`h20_prob_up` exceeding its drift limit with two unexecuted documented next
steps ("compare baseline/candidate model sets", "isolate external-feature
sensitivity").

**Investigation**: confirmed via 12 daily history snapshots (2026-07-22 to
2026-08-21) that this is a chronic status (not new), with `max_abs_delta_
date` pinned to 2026-02-10 in 10 of 12 snapshots. Traced the root cause to a
model-set mismatch: the production-pinned baseline panel was built WITH
TabNet; daily candidate panels pass `--no-tabnet` for speed (`ncf_00631l.py`).

**Critical finding**: this exact root cause was already isolated by prior
(2026-07-28-referenced) work: `results/ncf_panel_drift_model_set_isolation_
report_{stamp}.json` (status=`model_set_mismatch_isolated`, already computed
daily) and `results/ncf_panel_same_method_baseline_manifest_{stamp}.json`
(status=`valid_shadow_baseline`, with an explicit prior decision:
`use_for_promotion_gate_baseline: false` -- deliberately keeping the gate
strict despite the explanation).

**Outcome**: drafted a code change to `build_ncf_panel_drift_diagnosis.py`
surfacing this cross-reference, then reverted it via `git checkout` on
finding it duplicated the already-existing, more thorough isolation
machinery. **closed_negative** as a "new direction." Incidentally cleaned up
a stale (8+ day old) `.git/index.lock` blocking `git checkout` (confirmed no
running git process via `ps aux` before removing).

## Direction 2: Add a leverage-decay/tracking-drag feature to the NCF classifier

**Original framing**: `ncf_00631l.py`'s `FEATURES`/`EXT_FEATURES` contain no
feature directly capturing the realized (00631L return) vs (2x realized 0050
return) tracking gap, despite that being 00631L's defining character.

**Method**: new script `scripts/misc/ncf_00631l_leverage_drag_feature_
experiment_20260822.py`. Reused (did not reimplement) `group_a_plus/
integrations/leveraged_etf_timing_anomaly.py`'s `rolling_timing_anomaly()`
to add 4 new EXT_FEATURES columns (trailing 20-day window, matching NCF's
own h20 horizon): `letf_effective_leverage_20d`, `letf_effective_leverage_
std_20d`, `letf_covariance_ratio_20d`, `letf_volatility_drag_20d`.
`ncf_00631l.py` never edited on disk -- `EXT_FEATURES`/`load_external_df`
monkey-patched in-process, matching the file's own existing extension
pattern (line 2430). Ran baseline vs candidate once each, `--no-tabnet`,
default val-start=2025-01-02. Verified identical train/val row counts (no
confound).

**Result**: h1 val_auc improved (0.5810->0.6000, +0.019). h5 val_auc
worsened (0.6189->0.5936, -0.025). **h20 val_auc worsened** (0.6741->0.6549,
-0.019) -- the trigger-critical horizon that matters most. None of the 4 new
features appear in the candidate's top-15 feature-importance list.
**closed_negative.**

## Direction 3: Audit the late-bull trigger threshold's sample representativeness

**Original framing**: `a2118.py`'s late-bull thresholds (`NCF_LB_MA_GAP_
MIN=0.10`, module-default `NCF_LB_H20_MAX=0.45`, `NCF_LB_CONF_MIN=0.55`)
were "confirmed from panel analysis 2025-01~2026-05" (336 days, 4 events)
per the module docstring -- has anyone checked earlier late-bull episodes?

**Pre-check**: production's actual live `h20_max` override is **0.33**
(`report/group_a_plus/latest/strategy.json`'s `runner_params`), stricter
than the docstring's 0.45 default -- Fable's framing used the wrong number.

**Method**: concatenated 7 already-existing NCF backfill panels spanning
2017-2026 (2271 days, no new ML training), computed `ma_gap` from DB OHLCV
(0050 close / 100-day MA - 1, matching a2111/a2118's own `ma_window=100`),
applied the production trigger condition at both h20_max=0.33 and 0.45.
Cross-checked by calling `run_a2118()` directly, which independently
reported `late_bull_trigger_days=0`.

**Result**: 442/2271 days have `ma_gap>0.10` (a real sample), but **zero
days** satisfy all 3 conditions across the entire 2017-2026 combined
history at either threshold.

**Critical finding**: this exact investigation was already done on
2026-07-23/24 (`project_a2118_ncf_hedge_dormancy_root_cause_20260723`,
itself a follow-up to an even earlier, pre-round-1 "Fable 10 directions"
audit -- `GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md`),
which found zero triggers across 4 independent years (2017-2019, 2020,
2022, 2025-2026) and root-caused why (2020's real 79-day extended rally
never dropped h20 below 0.579 or raised confidence above 0.523 -- the model
stayed genuinely bullish through a fundamentals-backed rally, not a bug).
This session's check adds 2021/2023/2024, extending "4 years zero triggers"
to "7 years zero triggers" -- reinforcing, not new. **closed_negative** as a
"new direction."

## Direction 4: Attribute overlay redundancy with golden1's PPO policy

**Original framing**: does the late-bull overlay's backtest edge double-count
golden1's own PPO de-risking on the same trigger days?

**Method**: since direction 3 established zero triggers under the current
production panel, used the historical panel snapshot
(`ncf_00631l_panel_latest_20260725.csv`) that DOES produce trigger events
(3 triggers: 2025-09-30, 2026-01-29, 2026-02-23, reproduced exactly via
`run_a2118()`). Read `group_a_plus/runners/a2111.py`'s `_resolve_golden_
signal_path()`/`_golden_signal_metadata()` to find golden1's actual weight
source.

**Critical finding**: `a2111.py:90-113`'s docstring cites "H3 (2026-07-02
Fable 5 audit)" explicitly: `_resolve_golden_signal_path()` picks whichever
`signal_group_a_*.json` file has the newest mtime **at backtest run time**,
so a backtest replays the ENTIRE historical "golden1" regime under TODAY's
static golden1 weights -- not the weights actually in force on each
historical date. Already wired into every backtest's `golden_signal_
coverage` output with an explicit `caveat` field, since 2026-07-02.

**Outcome**: Fable's framing (double-counting a time-varying PPO decision)
does not apply, because there is no time-varying PPO weight sequence being
modeled in this backtest architecture at all -- only one frozen snapshot.
This is a more fundamental, already-documented limitation than the one
Fable proposed. **closed_negative** as a "new direction," no code changed.

## Direction 5: Why does the panel-refresh recommendation land at ~50.9% (coin flip)?

**Investigation**: read `report/group_a_plus/latest/ncf_panel_refresh_
recommendation.json` directly -- found the full picture is worse than
Fable's framing: of 3 review columns, `h20_prob_up` is 50.9% (candidate
marginally ahead) but `prob_fwd_mdd_gt5_h20` is 45.9% and `prob_fwd_gain_
gt5_h20` is 46.7% -- candidate is actually BEHIND baseline on 2 of 3
metrics.

**Root-cause test**: computed direct correlation between baseline
(2026-07-16 pin) and candidate (2026-08-21 retrain) `h20_prob_up` over 371
overlapping days -- **Pearson r=0.96**, 91.4% directional agreement, median
absolute difference 0.078. Connects directly to direction 1's finding
(baseline/candidate differ only by TabNet inclusion, 7 of 8 model families
identical, ~85% overlapping training window).

**Conclusion**: the ~50% "coin flip" rate is primarily a **methodological
artifact**, not strong evidence of an absolute ceiling. When two models
agree on direction 91.4% of the time, a day-by-day pairwise "who's closer"
race is structurally close to 50/50 almost regardless of whether the
candidate is genuinely slightly better or worse -- the `min_candidate_
favorable_rate=0.55` gate has structurally low power to ever recognize a
genuinely beneficial incremental retrain. **User explicitly asked "放
gate?" (loosen the gate?) -- answered no**: (a) this specific 08-21
candidate doesn't even clear 50% on 2 of 3 metrics, so lowering the
threshold wouldn't help it pass anyway; (b) the real fix is redesigning the
statistic (e.g. paired test on error differences) not lowering an arbitrary
number -- a governance-design decision requiring explicit sign-off, not
made here. **closed_negative**, no gate code changed.

## Direction 6: Wire GJR-GARCH into a2118's soft_hedge_intensity dial

**Pre-check before implementing anything**: traced `NCF_LB_SOFT_REGIME`'s
reachability -- `hedge_regime_for_day()` (a2118.py:590-599) only returns it
as a sub-branch INSIDE the main late-bull trigger loop, which direction 3
already established fires zero times across all available 2017-2026 history.

**Outcome**: `soft_hedge_intensity` is currently completely unreachable --
not merely rarely used, but provably never invoked. Wiring GJR-GARCH into it
now would have zero measurable effect on anything. **Not implemented, no
GJR-GARCH code written.** Not a rejection of the underlying idea (sizing a
continuous dial is more defensible than GJR-GARCH's two prior failures as a
binary trigger/covariate) -- simply not currently testable.

## Direction 7: Does PPO policy entropy add information beyond NCF confidence?

**Method**: new script `scripts/misc/ppo_entropy_vs_ncf_confidence_
20260823.py`. Loaded the REAL production PPO checkpoint (`models/portfolio/
last_ppo_group_a_100k.zip`) read-only for inference (no training, no
checkpoint write), replayed day-by-day over 2025-01-02 to 2026-07-16
(matching the pinned NCF panel), reusing `PortfolioEnv`/`_align_panel`/
`GROUP_A_PROFILE_PRESETS` and `generate_dual_group_signal.py`'s `_adapt_
obs_for_model` (the real legacy 37-to-43-dim observation-padding shim
production inference actually uses) to exactly match production's inference
path. Extracted the categorical action distribution's Shannon entropy via
`model.policy.get_distribution(obs).distribution.entropy()` (SB3's standard
API, never used in this codebase before) at each step. 370 joined rows.

**Single-window result**: `corr(ppo_entropy, ncf_confidence)=0.31` (moderate
independence); `corr(ppo_entropy, ncf_h20_error)=-0.22` (useful direction on
its own); **partial correlation after controlling for confidence = -0.09**
(small, most of the raw correlation is redundant with confidence).

**User follow-up ("1.5年窗口上太弱 如何改善?")**: extended the same replay to
2020-2026 (n=1541, 7 years) reusing the direction-3 backfill panels, no new
training (~few minutes). Per-year partial correlations: 2020 +0.063, 2021
-0.157, 2022 -0.454, 2023 -0.317, 2024 -0.096, 2025 +0.064, 2026 -0.111;
pooled -0.069. **5/7 years share the pooled sign but 2020 and 2025 flip
positive**, and magnitude ranges from -0.454 to +0.064 -- effect
concentrated in 2021-2023 (COVID-recovery/rate-hike volatility), weak or
flipped in 2020/2024/2025/2026. `corr(entropy,confidence)` is also
structurally different in 2024/2026 (~0.00) vs 2020-2023 (~0.29-0.31).

**Conclusion**: extending the sample did NOT turn "too weak" into
"promotable" -- it revealed the effect is **regime-dependent and
non-robust**, which is a more cautionary finding than the original
underpowered single-window result. **closed_negative**, more thoroughly
evidenced (7 independent years) than typical for this kind of exploratory
check.

## Direction 8: Build a dedicated shadow log for the late-bull trigger

**Reframed after direction 3**: a binary trigger-fired log would record
"no" every day forever under current thresholds -- zero information.

**Method**: new script `scripts/evaluate/build_a2118_late_bull_trigger_
margin_shadow_log.py`. Instead of binary, computes a **continuous signed
margin** for each of the 3 trigger conditions daily (imports the real
threshold constants from `a2118.py`, not hardcoded) plus the **binding
constraint** (which condition actually prevents the trigger that day).
Reused the same 7-panel 2017-2026 dataset, 2271 days.

**Result**: 0 trigger days (consistent with direction 3). **Confidence is
the binding constraint on 58.4% of days** (h20: 38.7%, ma_gap: 2.9%) --
confidence>0.55 is by far the dominant bottleneck, not h20 bearishness or
ma_gap extension. Median binding margin -0.406 (a typical day misses by 40
percentage points -- structurally rare, not near-miss). Only ONE near-miss
ever: 2019-11-01, binding_margin=-0.0159 (missed by 1.6pp); only 2 days ever
within 0.02.

**Output**: `results/a2118_late_bull_trigger_margin_shadow_log.csv` (full
daily history, reusable for any future threshold recalibration) and a
summary JSON. **Not wired into the daily pipeline** (kept research-only,
matching this session's caution about a2118-adjacent production paths).
Classified `effect_type: infrastructure`, genuinely new and reusable.

## Direction 9: Does a 500k-timestep PPO budget shrink cross-seed MDD variance?

**Motivation**: three PPO modifications this session (2026-08-20 HNN
architecture, round-1 direction 5 volatility features, round-1 direction 6
finegrained action space) all showed MDD cross-seed variance inflated
6-7.4x at 100k timesteps versus baseline. Round-1's own Final Recommendation
named testing a higher budget as the prerequisite before a 4th modification,
never run until now.

**Method**: new script `scripts/misc/train_a2118_ppo_500k_timestep_budget_
characterization_20260823.py`. Trained ONLY the unmodified baseline
PortfolioEnv at 500k timesteps x 3 seeds (42/43/44), isolating the
training-budget variable alone. ~110 minutes total (~36 min/seed),
background-run with progress monitoring. Compared directly against the
already-recorded 100k baseline (2026-08-22 finegrained experiment's own
baseline run, identical env/seeds/everything else).

**Result**:

| Metric | 100k mean / std | 500k mean / std | std ratio |
|---|---|---|---|
| final_value | $3,511,776 / $61,932 | $3,529,082 / $4,314 | **0.07x** |
| Sharpe | 1.945 / 0.021 | 1.848 / 0.0101 | 0.48x |
| MDD | -0.2971 / 0.0037 | -0.3583 / 0.00476 | **1.29x** |

final_value cross-seed variance collapsed to 7% of the 100k baseline's;
Sharpe variance roughly halved. But **MDD variance did NOT converge** (still
slightly higher than at 100k) -- the specific metric inflated in all three
prior PPO experiments. Critically, the **mean also shifted unfavorably**:
Sharpe dropped 1.945->1.848, MDD deepened -0.2971->-0.3583 (6+ points
worse), even though final_value stayed similar.

**Conclusion**: round-1's training-budget hypothesis needs revision. Longer
training does not simply produce "a more stable version of the same
policy" -- it converges to a different, worse-risk-adjusted policy. Simply
increasing the timestep budget is **not a validated fix** for the MDD-
variance-inflation pattern seen in the three prior experiments, and using
500k as a "more reliable" comparison baseline would itself introduce a
different confound. **closed_negative** as a promotion candidate, but
genuinely (and more usefully) answers round-1's open question. Never
touched `models/portfolio/last_ppo_group_a_100k.zip` or any production
checkpoint.

## Direction 10: TAIFEX mini options instead of standard TXO

**Original framing**: solve the already-validated put overlay's (arXiv:
2607.00883) 65%-zero-contract-sizing problem using TAIFEX mini options
(TMO/MXO) instead of standard TXO.

**Verification (live check, not backtest)**: queried TAIFEX's official
OpenAPI (`https://openapi.taifex.com.tw/v1/DailyMarketReportOpt`, the same
source `taifex_options_data.py` already uses) and enumerated every distinct
`Contract` code in today's full options daily report (12,641 rows). Only
`TXO` appears as a TAIEX-index options product (6038 rows); no MXO/TMO or
any reduced-notional TAIEX-index options contract appears anywhere.
**Methodology sanity check**: cross-verified against `/v1/
DailyMarketReportFut` -- `MTX` (the known mini TAIEX FUTURES product)
correctly appears there, confirming the scan would have caught a mini
options product had one existed with any activity.

**Conclusion**: TAIFEX offers a mini FUTURES contract (MTX) but **not** a
mini OPTIONS contract -- direction 10's premise is factually incorrect. TXO
remains the only TAIEX-index options product. No backtest needed or run.
**closed_negative**, premise refuted at the data-availability stage
(matching round-1 direction 7's pattern).

## Files Changed/Added This Round

New research/shadow scripts (no production effect):
- `scripts/misc/ncf_00631l_leverage_drag_feature_experiment_20260822.py` (direction 2)
- `scripts/evaluate/backtest_group_a_plus_leveraged_etf_timing_guard_partial_cap.py` (round-1 direction 9, referenced)
- `scripts/misc/ppo_entropy_vs_ncf_confidence_20260823.py` (direction 7)
- `scripts/misc/ppo_entropy_vs_ncf_confidence_multiyear_20260823.py` (direction 7 follow-up)
- `scripts/evaluate/build_a2118_late_bull_trigger_margin_shadow_log.py` (direction 8)
- `scripts/misc/train_a2118_ppo_500k_timestep_budget_characterization_20260823.py` (direction 9)

Drafted and reverted (no net change): `scripts/evaluate/build_ncf_panel_
drift_diagnosis.py`'s `--tabnet-isolation-diagnosis` addition (direction 1) --
`git checkout`-reverted after finding it duplicated existing infrastructure.

No production code was touched this round (unlike round 1's directions 2
and 8, which made real pipeline changes). Every direction this round was
either a duplicate-work verification, a closed-negative experiment, a
provably-unreachable-target finding, a premise-refuted data check, or new
research-only diagnostic infrastructure not wired into any daily process.

## Production Impact

None. Nothing in round 2 touched `run_ncf_daily_pipeline.py`, `a2118.py`,
`golden1_0531`, live target weights, `execution_regime`, or any order-
generation path. `models/portfolio/last_ppo_group_a_100k.zip` and
`group_a_production_*` were never touched by either the direction-7 entropy
extraction (read-only inference) or the direction-9 timestep-budget
training (writes only to `experiment_500ktest_*`).

## Tests

No new pytest test files were added this round (all deliverables were
one-off research/diagnostic scripts, matching this codebase's convention of
not adding test coverage for one-shot research scripts -- see round-1
handoff's own note on this same convention). `tests/test_build_ncf_panel_
drift_diagnosis.py` (4 tests) was re-run after direction 1's revert to
confirm the file returned to its exact pre-session state; all passed.

## Final Recommendation

- Do not promote any of the tested candidates from directions 2, 5, 6, 7, 9,
  10 on this evidence.
- Direction 5's finding (the panel-refresh gate has structurally low power
  for incremental retrains) is worth revisiting if/when there is appetite
  to redesign that gate's statistical methodology -- not attempted here,
  requires explicit sign-off since it is governance-adjacent.
- Direction 8's margin shadow log (`results/a2118_late_bull_trigger_margin_
  shadow_log.csv`) is a reusable asset for any future late-bull threshold
  recalibration -- it already identifies `confidence` as the specific
  bottleneck rather than `ma_gap` or `h20`.
- Direction 9's finding argues against blindly using a higher timestep
  budget as a "more reliable" baseline for future PPO experiments; if the
  MDD-variance-inflation question is revisited, it needs a more careful
  design (e.g. sweep both timesteps and the architectural change together
  with proper interaction analysis) rather than assuming budget alone
  explains it.
- This round's meta-lesson: 3 of 10 directions (1, 3, 4) duplicated
  substantial prior work from sessions dated 2026-07-02, 2026-07-23, and
  2026-07-28 -- none of which were referenced in `research_semantic_
  registry.json` before this round. The registry, even after round 1 added
  entries, remains materially incomplete relative to the full history of
  memory files and root-level handoff docs. Any future "propose N new
  directions" request should have the reviewing agent (Fable or otherwise)
  read a broader slice of memory/handoff history, not just the registry and
  the immediately preceding round's handoff.

## Memory/Registry Index

Registry (`group_a_plus/research_semantic_registry.json`) entries added this
round, in order: `round2_direction1_external_sensitivity_tabnet_mismatch_
already_diagnosed`, `round2_direction2_ncf_leverage_drag_feature`,
`round2_direction3_late_bull_trigger_dormancy_already_diagnosed`,
`round2_direction4_golden1_ppo_overlay_redundancy_not_applicable`,
`round2_direction5_ncf_panel_refresh_coinflip_methodology_artifact`,
`round2_direction6_gjr_garch_soft_hedge_intensity_unreachable_target`,
`round2_direction7_ppo_entropy_vs_ncf_confidence`, `round2_direction8_
late_bull_trigger_margin_shadow_log`, `round2_direction9_ppo_500k_
timestep_budget_characterization`, `round2_direction10_taifex_mini_
options_do_not_exist`. Total registry size: 36 entries as of this handoff.

Memory files (chronological): `project_fable_10_directions_round2_
20260822` (original list), `project_fable_round2_direction_1_20260822`
through `project_fable_round2_direction_10_20260823` (one per direction;
direction 7's file was updated in place after the multi-year follow-up).
`MEMORY.md` was compacted mid-round (19.6KB -> 8.8KB) per a size-limit
hook, consolidating verbose per-entry hooks into shorter one-liners with
detail left in the topic files.

No commit was made -- per standing instruction, commits are not suggested
or created unless the user explicitly asks.
