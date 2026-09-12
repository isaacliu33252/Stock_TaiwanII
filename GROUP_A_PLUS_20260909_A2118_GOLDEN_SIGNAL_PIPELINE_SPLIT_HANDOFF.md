# a2118 Golden Signal Pipeline Split — Production Change, 2026-09-09

**This changed production wiring.** Unlike the entire 2026-09-08/09 a2118-independent-PPO-model
research line (cap20, multi-seed verification, QUESTrader-lite), which was read-only research,
this is a real, live change to how a2118 sources its golden1-regime-day weights day to day.

## What prompted this

After this week's a2118-independent-PPO-model research line concluded (cap20 is a shadow
candidate, not ready to promote), the user asked directly: "has the latest strategy (a2118)
actually been changed — is it independent of golden1_0531 and golden2_0830?" Verified: no. a2118
still fully depends on golden1_0531's trained weights (via the "Last PPO" copy introduced
2026-08-14, `models/portfolio/last_ppo_group_a_100k.zip`). golden2_0830 was reviewed for
promotion on 2026-09-01 and rejected (failed 2 of 4 window gates), never wired to production.

The user then asked how to decouple it. Two different questions were distinguished:
1. **Give a2118 genuinely different intelligence** (a new, better-trained independent model) —
   this is what this week's cap20 research targeted, and it isn't ready (residual ~1.6-2pp MDD
   gap versus production, unexplained after two separate tests this week, and only one
   genuinely fair OOS test window).
2. **Stop a2118 from sharing a live pipeline with golden1_0531** — a pure architectural
   decoupling, no change in trading behavior today, much lower risk. This is what the user meant
   and confirmed ("現在，馬上切割" — do it now).

This document covers only #2.

## The coupling that existed

`group_a_plus/runners/a2111.py`'s `_resolve_golden_signal_path()` (imported and used by
`group_a_plus/runners/a2118.py`, which backs the live daily decision computed in
`group_a_plus/operations/daily_signal.py`) read `LATEST_GROUP_A_SIGNAL =
results/group_a_combined_live_latest.json` — golden1_0531's own live pipeline output, written
daily by `scripts/run/run_group_a_combined_signal.py`. Any future change to that script or its
`DEFAULT_RESULT_JSON` pointer (this already happened once, 2026-08-14's "Last PPO" introduction)
would silently propagate into a2118's live trading decisions with no a2118-specific review. That
was the architectural risk the user's stated principle ("golden1_0531/golden2_0830/最新策略不該互相參考")
was originally about.

## What changed

1. **Frozen copies of golden1_0531's current weights**, made by a2118, for a2118:
   - `models/portfolio/a2118_own_golden_ppo_20260909.zip` — byte-identical copy (verified via
     sha256) of `models/portfolio/last_ppo_group_a_100k.zip`.
   - `results/a2118_own_golden_source_20260909.json` — copy of
     `results/last_ppo_group_a_backtest_20250101_20260531_20260609_214023.json`, with
     `group_a.model_name` repointed from `last_ppo_group_a_100k` to `a2118_own_golden_ppo_20260909`
     (the only field changed).
2. **New script `scripts/run/run_a2118_own_golden_signal.py`** — a line-for-line fork of
   `run_group_a_combined_signal.py`. Only the 4 module-level path constants changed
   (`DEFAULT_RESULT_JSON`, `DEFAULT_LATEST_JSON`, `DEFAULT_LATEST_CSV`, `DEFAULT_MANIFEST`), now
   pointing at a2118's own frozen source and its own output files
   (`results/a2118_own_golden_live_latest.{json,csv}`,
   `results/a2118_own_golden_bundle_latest.json`) instead of overwriting golden1_0531's.
3. **`group_a_plus/runners/a2111.py`**: `LATEST_GROUP_A_SIGNAL` repointed from
   `results/group_a_combined_live_latest.json` to `results/a2118_own_golden_live_latest.json`.
   This is the one line that actually takes effect — `_resolve_golden_signal_path()`'s own logic
   is untouched.

## Verification performed (not just "the files exist")

- Ran the new `run_a2118_own_golden_signal.py` for today (2026-09-09, data through 2026-09-07) —
  succeeded, model resolved correctly to the new frozen zip, wrote to the new output paths.
- Also re-ran the original `run_group_a_combined_signal.py` (golden1_0531's normal daily refresh
  — a legitimate, expected operation regardless of this change) same day, same frozen weights.
- **Field-by-field diff of both output JSONs**: `target_weights`, `target_shares`,
  `signal_status` are identical. Only `model_path` (different filename, same content) and
  `output_csv` (different path) differ — both expected.
- Called `_resolve_golden_signal_path()` directly: confirms it now resolves to
  `results/a2118_own_golden_live_latest.json`.
- Re-ran `run_a2118("2025-01-02", "2026-09-04", ...)` end-to-end after the change: still works,
  final_value/Sharpe/MDD consistent with the pre-change baseline (the small final-value delta is
  two additional days of market data, not the wiring change).
- Checked other files still referencing `group_a_combined_live_latest.json`
  (`run_ncf_daily_pipeline.py`'s `PROTECTED_GOLDEN1_RELEASE_ARTIFACTS`, `ensemble_group_a_vote.py`,
  `evaluate_golden1_weight_drift.py`, one test file) — these are audit/protection/ensemble tools
  that are *supposed* to keep observing golden1_0531's own file; left unchanged, correctly.

## What this is NOT

The model weights are identical to golden1_0531's as of today. This is a pipeline/architecture
decoupling, not a strategy or intelligence change — today's trading decision is byte-for-byte the
same as it would have been without this change (verified above). It does not touch golden1_0531
itself, `run_group_a_combined_signal.py` itself, or golden2_0830 in any way.

## Open gap for whoever maintains this next

`run_a2118_own_golden_signal.py` must now be run **every day** going forward (same cadence as
`run_group_a_combined_signal.py`) to keep a2118's signal fresh — freezing the model checkpoint
does not freeze the daily inference step, which still needs each new day's market data.
`daily_signal.py` carries a 2026-08-12-incident comment noting that `run_group_a_combined_signal.py`'s
generation "isn't part of the automated daily pipeline" (implying manual/external triggering) —
if true, that means **two** scripts now need to be run daily instead of one, and this pass did
not verify or update whatever currently triggers the first one. Worth confirming and wiring the
new script into the same trigger before this becomes a staleness incident like the 2026-08-12 one.

## Path forward for an eventual real model swap

If an independent model (e.g. a future promoted successor to cap20) ever clears this project's
promotion bar, the insertion point is now clean: swap `group_a.model_name` in
`a2118_own_golden_source_20260909.json` (or a newer dated copy) to the new checkpoint. Neither
`run_a2118_own_golden_signal.py` nor `a2111.py`'s `_resolve_golden_signal_path()` need to change
again — this pass already separated "which weights" from "which file a2118 reads."

Memory: `project_a2118_own_golden_signal_pipeline_split_20260909.md`.
