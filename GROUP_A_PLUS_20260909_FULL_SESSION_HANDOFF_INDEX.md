# GroupA+ Full Session Handoff Index — 2026-09-08/09

This index ties together an unusually large arc of work spanning 2026-09-08 (research) and
2026-09-09 (production changes). Read this first; it links to the detailed documents for each
piece. **The single most important fact for anyone picking this up: a2118's golden-signal source
was switched away from golden1_0531 to an independently-trained, statistically-unproven model on
2026-09-09, at the user's explicit, fully-informed direction, against this project's own
significance-testing evidence.** See section 8 below before touching anything related to a2118's
signal generation.

## 1. a2118 independent PPO model research line (2026-09-08, read-only)

Full arc: baseline timestep sweep -> 3-seed noise check -> single-variable isolation (action
schema, leverage cap) -> cap20 3-seed reverification -> day-by-day root-cause diagnostic ->
institutional-features hypothesis test (not supported) -> 2608.15841 QUESTrader paper desk review
-> QUESTrader-lite auxiliary-task test (no effect).

**Conclusion at end of 09-08**: cap20 (triplet_v2, 00631L cap 20%, seed42, 2017-2019 training
window) is the cleanest shadow candidate — final value/Sharpe point estimates beat production on
the one fair OOS window (active_2025_2026), MDD point estimate ~1.6-3pp worse, residual gap
unexplained by either institutional features or auxiliary tasks. **Explicitly not a promotion
case** at this point.

Memory: `project_a2118_independent_ppo_model_experiment_20260908.md`,
`project_2608_15841_questrader_gvf_auxiliary_desk_review_20260908.md`.

## 2. Data freshness verification (2026-09-09 morning)

Ran `run_ncf_daily_pipeline.py --only-refresh`; verified via direct DB query (not just the
manifest) that OHLCV/institutional/taifex data landed correctly through 2026-09-08 (0050/00631L/
00632R capped at 09-07 due to normal TWSE T+1 publication lag — not a pipeline fault).

## 3. group_a_plus_policy_signal staleness fix

Found `results/group_a_plus_policy_signal_20260627_210621.json` (feeds the `group_a_plus_recovery`
regime only — narrow blast radius, never used since golden1 hasn't exited via a crash-recovery
transition since June) was 73 days stale, a known/accepted detection-only gap from 2026-07-12.
Regenerated via `scripts/misc/group_a_plus_decision_policy.py`; now fresh. No behavior change
(regime never entered).

## 4. 2026-09-09 three-strategy NT$1,500,000 prediction (golden1_0531 / golden2_0830 / latest strategy)

Read-only what-if predictions, no production pointer touched at the time. Note: golden1_0531's run
used `--extra-cash` on top of a real existing "即時庫存" holding (~NT$265,981: 89 shares 0050 +
10,000 shares 00679B), so its total basis (NT$1,765,981) is not directly comparable to
golden2_0830/latest strategy's clean NT$1,500,000 basis — flagged but not reconciled at the time.

## 5. "檢討最新策略" — NCF late-bull-hedge root cause + TabNet restored (2026-09-09)

Traced why a2118's core NCF late-bull-hedge mechanism's promotion evidence (3 historical triggers)
doesn't reproduce with current panels. Root cause: `run_ncf_daily_pipeline.py` hardcoded
`--no-tabnet` for 00631L/0050/00713 since day one, while the 2026-06-28 promotion panel was
generated **with** TabNet — model-set mismatch, already caught by existing governance
(`ncf_panel_drift_tabnet_vs_no_tabnet_20260630.json`, `panel_drift_triage.md` status=`blocked`).

**Fixed**: removed `--no-tabnet` from 4 command lists in `run_ncf_daily_pipeline.py` (00631L, 0050,
00713, and the external-feature-sensitivity shadow variant). Regenerated today's 00631L panel with
TabNet restored.

**But then disproved my own simplification**: re-tested the 3 historical trigger dates with
TabNet restored — confidence went *down*, not up (0 triggers today, not a restoration of 3).
Ran a same-input reproducibility test (identical command, twice) and got **bit-identical output**
across 408 rows — TabNet/the full ensemble is fully deterministic under a fixed seed. The real
drift source is that the pipeline's code and external data genuinely evolve over 2+ months — not
a bug, an inherent property of a living pipeline, not fixable short of golden1_0531-style freezing.

Re-ran the drift/diagnosis/triage chain: `panel_drift_triage.md` (production file, updated)
narrowed from 3 hypotheses to 1 (`candidate_external_source_stale`) — confirms the TabNet fix
genuinely closed the `model_set_changed` hypothesis.

Investigated whether to also update `strategy.json`'s `ncf_panel_631l_path` (still pinned to a
stale 2026-07-16 panel) to today's fresh one — found a directly-relevant 2026-07-27 precedent that
already ran the same experiment (0716->0725) and found the "improvement" was noise via
outcome-aware verification (accuracy ~49-50%, a coin flip). Re-ran the same outcome-aware check for
0716 vs today: same result (49.6-50.4% across 3 columns). **Decision: left `ncf_panel_631l_path`
unchanged.**

Also fixed `results/group_a_plus_policy_signal`-adjacent staleness (see section 3) and
`strategy.json`'s `ncf_00713_path` (was pointing to a 2026-09-07 file; updated to the fresh
2026-09-09 one — this actually changed the recommended GroupA++ 00713 sleeve allocation from 12%
to 0%, since the fresh NCF signal shows `calibrated_prob_up` just below the buy threshold).

Memory: `project_ncf_late_bull_hedge_confidence_instability_root_cause_20260909.md`,
`project_ncf_tabnet_restored_daily_pipeline_20260909.md`.
Handoff: `GROUP_A_PLUS_20260909_NCF_TABNET_RESTORED_HANDOFF.md`.

## 6. a2118 golden-signal pipeline split (architectural, 2026-09-09)

a2118 (via `group_a_plus/runners/a2111.py`'s `_resolve_golden_signal_path()`) used to read
golden1_0531's own live pipeline output (`results/group_a_combined_live_latest.json`) directly.
Forked a new script `scripts/run/run_a2118_own_golden_signal.py` (copy of
`run_group_a_combined_signal.py` with independent output paths) and repointed
`LATEST_GROUP_A_SIGNAL` to it. **Pure architectural decoupling at the time** — same weights
(golden1_0531's, via a frozen copy), verified byte-identical trading decisions on the fork date.

While investigating whether to schedule the new script, discovered via direct Windows Task
Scheduler inspection (`schtasks.exe`/PowerShell, not just the repo's `task_scheduler_setup.xml`
which turned out to be stale) that golden-signal generation was **never** part of the automated
daily pipeline (only OHLCV refresh and NCF-signal generation are scheduled, both at 23:00) — this
was already true before today, not a gap introduced by the split. Also found and fixed the repo's
stale `task_scheduler_setup.xml` (said 1-hour execution limit; the real live task has always had
72 hours — no actual runtime risk from the TabNet change). **User decided to keep golden-signal
generation manual** (no new scheduled task).

Memory: `project_a2118_own_golden_signal_pipeline_split_20260909.md`.
Handoff: `GROUP_A_PLUS_20260909_A2118_GOLDEN_SIGNAL_PIPELINE_SPLIT_HANDOFF.md`.

## 7. Formal significance testing of the entire cap20 lineage (2026-09-09)

Built `scripts/misc/significance_check_cap20_vs_production_20260909.py` using this project's own
previously-unwired `group_a_plus/governance/significance.py` (Jobson-Korkie/Memmel paired-Sharpe
test + Bonferroni grid correction). Tested **10 candidates** (seed42/7/123 at cap30 and cap20,
tripletv4, cap20+institutional-features, cap20+auxvol, and a 100K-timestep variant) vs. production
on the one fair window (active_2025_2026). **Result: none significant** — best candidate (seed42
cap20) p=0.343 uncorrected; Bonferroni-corrected alpha for this grid is 0.005.

Computed the additional comparable OOS data each candidate would need to reach significance
(assuming the current effect size holds exactly, an optimistic assumption): most candidates need
400-4000+ years; the best one needs an estimated ~6.9 years uncorrected / ~14.1 years
Bonferroni-corrected. Confirmed the 80K/100K variants are behaviorally identical on this window
(verified this isn't a bug — their few differing days fall outside the window or on
defensive-regime days where both get overridden anyway).

Result file: `results/significance_check_cap20_vs_production_20260909.json`.

## 8. **a2118 production switch to cap20 (2026-09-09) — the big one**

After seeing the section-7 evidence directly (not significant, 6.9-14.1 years needed), the user
was asked to clarify scope (shadow-only tracking vs. an actual production capital switch, framed
explicitly as "betting real money on a candidate without significant evidence of an advantage")
and **explicitly chose the production switch**.

`scripts/run/run_a2118_own_golden_signal.py`'s `DEFAULT_RESULT_JSON` now points to
`results/a2118_own_golden_source_20260909_cap20.json`, resolving to model checkpoint
`a2118_independent_ppo_v1_80k_cap20.zip`. a2118's golden1-regime-day weights now come from this
independently-trained model, not golden1_0531. **This is a real strategy change made against this
project's own statistical evidence, at explicit, informed user direction — not an analytical
recommendation.**

Verification hit a genuine trap: `run_a2118()`'s backtest tool has a pre-existing, documented
limitation ("H3") where it applies a single static golden-signal snapshot to every golden1-regime
day in a backtest range rather than replaying true daily history — so a naive post-switch backtest
looked nearly identical to the pre-switch production numbers, which briefly looked like the switch
had failed. It hadn't; this tool simply cannot verify any golden-signal-source change
retrospectively (true for golden1_0531 too, historically — this is why this week's real
comparisons were built with a custom day-by-day replay, not `run_a2118()` directly).

Full decision record, evidence chain, and revert instructions:
`GROUP_A_PLUS_20260909_A2118_CAP20_PRODUCTION_SWITCH_HANDOFF.md`.
Memory: `project_a2118_cap20_production_switch_20260909.md`.

**To revert**: change `DEFAULT_RESULT_JSON` back to `results/a2118_own_golden_source_20260909.json`
in `scripts/run/run_a2118_own_golden_signal.py`. Nothing else needs to change.

## What did NOT change, across this entire two-day arc

golden1_0531 itself and its release artifacts, `run_group_a_combined_signal.py`, golden2_0830, and
every a2118 threshold (`h20_max`, `conf_min`, `ma_gap_min`, `momentum_fast_exit_min`, etc.) are
untouched. The only things that changed in production are: (a) which file a2118 reads its golden
signal from (pipeline split, section 6), (b) the NCF daily pipeline's model ensemble composition
(TabNet restored, section 5), (c) two stale-pointer fixes (`ncf_00713_path`,
`group_a_plus_policy_signal`), and (d) — the significant one — which model actually generates
a2118's golden1-regime-day weights (section 8).

## Open items for whoever picks this up next

1. `run_a2118_own_golden_signal.py` must be run manually every day; not on any automated schedule
   (deliberate user choice).
2. `panel_drift_triage.md`'s one remaining hypothesis (`candidate_external_source_stale`) was not
   fully resolved — a missing historical no-external-features baseline panel (2026-07-16) made the
   full automated attribution impossible, and given the 07-27 precedent's outcome-aware finding
   (panel refreshes are typically noise, not signal), further chasing this specific hypothesis was
   judged low-value.
3. cap20 (seed42) is a single-seed production model as of this switch. This week's own multi-seed
   testing found ~1.6-2pp of MDD variance across seed42/7/123 — relevant if this decision is ever
   revisited.
4. The golden1_0531/golden2_0830/latest-strategy 09-09 prediction comparison (section 4) used an
   inconsistent capital basis for golden1_0531 (real existing holdings + extra cash) vs. the other
   two (clean assumed total) — never reconciled; low priority, flagged for completeness.
