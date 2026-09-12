# NCF Daily Pipeline: TabNet Restored — Production Change, 2026-09-09

**This changed production wiring.** Second production change today, after the a2118 golden
signal pipeline split (`GROUP_A_PLUS_20260909_A2118_GOLDEN_SIGNAL_PIPELINE_SPLIT_HANDOFF.md`).

## Background

While reviewing "the latest strategy" per the user's request, investigation traced why a2118's
core NCF late-bull-hedge mechanism's historical trigger evidence doesn't reproduce with current
panels (full root-cause chain in
`project_ncf_late_bull_hedge_confidence_instability_root_cause_20260909.md`). Found: the
2026-06-28 promotion-time panel (`ncf_00631l_panel_2025_v4_tail.csv`) was generated **with**
TabNet in the model ensemble, but `scripts/run/run_ncf_daily_pipeline.py` has hardcoded
`--no-tabnet` for the 00631L/0050/00713 NCF signal-generation steps since day one — meaning
daily production never ran the same model ensemble that generated the promotion evidence.

This was not a newly-introduced bug: it was already caught and quantified by existing governance
tooling —
- `results/ncf_panel_drift_tabnet_vs_no_tabnet_20260630.json` (dated 2026-06-30) already measured
  the confidence-column impact: mean abs delta 0.093, max abs delta 0.49 — against a 0.55 hard
  threshold, large enough to flip trigger decisions.
- `report/group_a_plus/latest/panel_drift_triage.md` currently shows `status: blocked`, flagging
  `h20_prob_up` exceeding its trigger-critical tolerance, with `model_set_changed` as the first
  listed hypothesis — exactly this issue. Its Decision Boundary already confirms no orders, no
  target-weight changes, and golden1_0531 unaffected while blocked — the drift never reached live
  trading.

User asked what restoring TabNet would cost. Measured directly: one ticker (00631L) with TabNet
took 944s (~15.7 min) vs. ~3-4 min without — roughly 3-4x slower per signal, under some CPU
contention from a concurrent background job (so likely a slight overestimate of the isolated
cost). Three signals (00631L, 0050, 00713) carry `--no-tabnet`; 00632R and 2330 never did (proof
the machine can already handle TabNet's cost for two of five signals). Net estimate: **+30-45
minutes to the daily pipeline's total runtime**. User confirmed: proceed.

## What changed

`scripts/run/run_ncf_daily_pipeline.py`: removed `"--no-tabnet"` from four command lists:
1. `commands["ncf_00631l"]`
2. `commands["ncf_0050"]`
3. `commands["ncf_00713"]`
4. `commands["ncf_00631l_no_external_shadow"]` (the external-feature-sensitivity shadow variant —
   removed here too so it stays a clean single-variable comparison against the main 00631L panel,
   which now also includes TabNet)

`commands["ncf_00632r"]` and `commands["ncf_2330"]` never had the flag; untouched.

Verified `python3 -m py_compile` passes. The background 165-step `--skip-refresh` pipeline
launched earlier today (11:12, before this edit) is unaffected by this source change since Python
had already loaded the old module — it continued running with the old no-tabnet behavior for its
own pass. Triggered a fresh, standalone re-run of `ncf_00631l.py` (without `--no-tabnet`, matching
the new command) to overwrite today's panel/signal files
(`results/ncf_00631l_panel_latest_20260909.csv`, `results/ncf_00631l_latest_20260909.json`) with
a TabNet-included version — this is the version that should be treated as "today's real panel"
going forward, not the earlier no-tabnet one the still-running background job produced.

**Known overlap risk**: the background 165-step pipeline's later steps (e.g.
`evaluate_a2118_decision_focused_action_shadow.py`) read
`results/ncf_00631l_panel_latest_20260909.csv` by path while this regeneration was concurrently
overwriting it — not a corruption risk (single-writer, atomic-enough file write), but downstream
analysis in that same background run may have read either the stale no-tabnet version or the new
TabNet version depending on timing. If anyone reviews that background run's output artifacts from
today, treat them as using an indeterminate panel vintage; re-run if it matters.

## What this does NOT do

Does not touch golden1_0531, its files, or `run_group_a_combined_signal.py`. Does not change any
threshold (`h20_max`, `conf_min`, `ma_gap_min`) in `group_a_plus/runners/a2118.py` — only the
model *ensemble composition* feeding the panel changed. Does not retroactively fix or explain the
residual drift that exists even among no-tabnet-only panel generations over time (mean abs delta
~0.059 confidence, 2026-06-30 baseline vs 2026-09-07) — that's a separate, still-open question
noted in the root-cause memory file.

## Post-change verification: TabNet is not a fix — it's another source of instability

Immediately after the change, regenerated today's (2026-09-09) 00631L panel with TabNet included
and re-ran the trigger check against the same three historical dates:

| Date | confidence, no-TabNet (this morning) | confidence, with-TabNet (after this change) |
|---|---:|---:|
| 2025-10-30 | 0.4646 | **0.3826** (lower) |
| 2025-10-31 | 0.5243 | **0.4756** (lower) |
| 2026-02-23 | 0.5907 (would trigger) | **0.5284** (drops below threshold) |

Running the full trigger check against today's TabNet-included panel: **0 triggers** — not a
restoration of the original 3, fewer than even this morning's no-tabnet run had.

This overturns the simplified "TabNet exclusion explains the gap" framing from the root-cause
memory. The 06-28 (TabNet-included) vs. 07-16/07-22/09-09 (no-TabNet) comparison that suggested
TabNet inclusion raises confidence was a snapshot of one specific TabNet training run, not a
general rule — today's fresh TabNet retrain pulled these same dates' confidence *down* instead.
TabNet itself does not reproduce its own predictions run to run (consistent with PyTorch's
known imperfect determinism even with a fixed seed, especially under early-stopping with
epoch-count sensitive to tiny floating-point differences). Restoring it re-aligns the *model
composition* with what was promoted (a legitimate, still-worthwhile architectural correction) but
does **not** fix the underlying reproducibility problem — if anything, TabNet may be one of the
more unstable individual ensemble members, not a stabilizing one.

## Follow-up not done this pass (flagged for whoever picks this up)

1. **`panel_drift_no_tabnet_baseline_vs_today`** (the daily drift-vs-06-30-baseline check) will
   show one large, expected jump starting today, since its comparison baseline is a no-tabnet
   panel and today's panel is the first with TabNet restored. This is a deliberate, known
   consequence of this change, not a new anomaly — but the baseline itself hasn't been reset, so
   anyone reading only that report's raw numbers without this context could misread it as a fresh
   problem.
2. **`panel_drift_triage.md`'s `blocked` status** hasn't been re-evaluated after this fix. Its
   `model_set_changed` hypothesis is now addressed; worth re-running the triage to see if it
   clears, or if the other two hypotheses (`candidate_external_source_stale`,
   `external_feature_sensitivity_visible`) still hold given the residual no-tabnet-lineage drift.
3. **Late-bull-hedge trigger dates will shift again** now that TabNet is back — this is not a
   claim that the mechanism has "recovered" or "gotten worse." It only removes the one-time,
   already-quantified TabNet-related gap; the mechanism's remaining reproducibility (or lack
   thereof) needs to be watched over the next several panel regenerations before drawing any new
   conclusion about it.

Memory: `project_ncf_tabnet_restored_daily_pipeline_20260909.md`,
`project_ncf_late_bull_hedge_confidence_instability_root_cause_20260909.md`.
