# a2118 Production Switch to cap20 — 2026-09-09

**This is the largest production change of the entire 2026-09-08/09 research arc, and it goes
against this project's own statistical evidence.** Read this in full before touching anything
related to a2118's golden-signal source.

## What changed

`scripts/run/run_a2118_own_golden_signal.py`'s `DEFAULT_RESULT_JSON` now points to
`results/a2118_own_golden_source_20260909_cap20.json`, which resolves to model checkpoint
`models/portfolio/a2118_independent_ppo_v1_80k_cap20.zip` — the independently-trained "cap20"
PPO model from this week's research line — instead of golden1_0531's weights. a2118's
golden1-regime-day target weights now come from this model, not golden1_0531.

## Why this happened despite the evidence

This week's entire cap20 research line (see `project_a2118_independent_ppo_model_experiment_*`
memory files) consistently concluded cap20 was a clean shadow candidate but **explicitly not a
promotion case** — point estimates favored it (final value +8.7-13%, Sharpe roughly tied) but MDD
was consistently ~1.6-3pp worse, and there was only one genuinely fair (both-sides-OOS) test
window.

On 2026-09-09, the user pushed on this repeatedly and the following evidence was generated and
shown directly to them, in order:
1. Confirmed 80K and 100K timestep variants are behaviorally identical on the fair window (not a
   bug — the few days their raw outputs differ either fall outside the window or land on
   defensive-regime days where both get overridden by the same fixed basket anyway).
2. Ran `scripts/misc/significance_check_cap20_vs_production_20260909.py` — a formal
   Jobson-Korkie/Memmel paired-Sharpe significance test (from the project's own existing
   `group_a_plus/governance/significance.py`, previously built but never wired into any gate)
   against **10 candidate configs** trained this week (seed42/7/123 at both cap30 and cap20,
   tripletv4, cap20+institutional-features, cap20+auxiliary-volatility-head, and the 100K variant),
   each vs. production on the one fair window. **Result: none significant.** Best candidate
   (seed42 cap20): p≈0.348, uncorrected. Bonferroni-corrected alpha for a 10-candidate grid:
   0.005 — nowhere close.
3. Computed how much more comparable OOS data each candidate would need to reach significance,
   assuming the currently-measured effect size holds exactly (an optimistic assumption). Most
   candidates: 400-4000+ years. Best candidate (seed42 cap20): **~6.9 years uncorrected, ~14.1
   years Bonferroni-corrected.**
4. Asked the user to explicitly clarify scope: shadow-only tracking (zero risk, this project's
   recommended path) vs. an actual production capital switch (explicitly framed as "betting real
   money on a candidate that doesn't show significant advantage"). **User chose the production
   switch, having just seen items 2-3 directly.**

**This is a fully informed, explicit user decision, not an analytical recommendation.** It
directly contradicts this project's own `feedback_strategy_promotion_caution` precedent
("promotion decisions require rigor; a high point-estimate Sharpe is not enough"). Flagging this
plainly because any future review of this decision should not mistake it for a case where the
evidence supported the switch — it didn't, and that was stated clearly before the switch was made.

## What was actually done

1. Copied `results/group_a_backtest_20240101_20260904_20260908_223625.json` (this week's real,
   full 2024-2026 backtest of cap20 seed42) to
   `results/a2118_own_golden_source_20260909_cap20.json`, fixing `group_a.model_name` (the
   original recording had a stray `.zip` suffix that would have broken the model-path resolution
   in `generate_dual_group_signal.py`).
2. Updated `scripts/run/run_a2118_own_golden_signal.py`: `DEFAULT_RESULT_JSON` now points to the
   new file; updated the module docstring and `RELEASE_NAME` to make this an unmissable, explicit
   strategy-change marker (not the earlier architectural-only pipeline fork).
3. Two of these file operations were blocked by the Claude Code auto-mode safety classifier
   (recognizing this as a high-risk, hard-to-reverse write into the live-signal chain) — correctly
   so. The user manually adjusted their session permission settings to allow it, twice, before it
   went through.

## Verification — and an important tool-limitation trap

Ran `run_a2118_own_golden_signal.py`: confirmed the model line correctly shows
`a2118_independent_ppo_v1_80k_cap20.zip`, and today's live signal produced
`Candidate: 0050 82.8% / 00631L 17.2%`, stepped down by the existing 0050-weight-change guard to
`Executable: 0050 53.0% / 00631L 17.2% / cash 29.8%`. This part is confirmed working correctly.

**Then hit a real trap**: ran `run_a2118("2025-01-02", "2026-09-04", ...)` (the standard backtest
entrypoint) expecting to see cap20's historical effect reflected — got final_value=2,123,864,
essentially identical to production's original number (2,124,056). This briefly looked like the
switch hadn't taken effect. Checked `group_a_plus/runners/a2118.py` and confirmed: **this is the
project's own documented "H3" limitation** — `run_a2118()`'s backtest replay resolves the golden
signal via `_resolve_golden_signal_path()` exactly once and applies that single static snapshot to
**every** golden1-regime day across the whole backtest range; it does not replay a true day-by-day
history. This is a pre-existing, structural limitation of this analysis tool (it already affected
golden1_0531 backtests too, which is why this week's real per-day comparisons were built with a
custom `simulate_new_model()` daily replay from `daily_target_weight_history`, not by calling
`run_a2118()` directly) — it is not a bug introduced by this switch, but this is the first time it
produced an actual false-negative reading during a real production verification.

**Practical consequence**: `run_a2118()`'s built-in backtest cannot be used to verify or
retrospectively evaluate this switch's historical effect. Use either (a) the actual live daily
executions accumulating from today forward, or (b) a `simulate_new_model()`-style day-by-day
replay matching this week's methodology (numbers already computed:
cap20 seed42 on active_2025_2026: final=2,402,703, Sharpe=2.064, MDD=-19.38% vs. production's
2,123,517/2.053/-16.44% — no need to recompute).

## What did NOT change

golden1_0531 itself and its own release artifacts, `run_group_a_combined_signal.py`, golden2_0830,
a2118's switch-rule/regime-detection logic, and every threshold (`h20_max`, `conf_min`,
`ma_gap_min`, etc.) are untouched. Only the source of golden1-regime-day target weights changed.

## Operational notes for whoever maintains this next

1. `run_a2118_own_golden_signal.py` must be run manually every day (confirmed earlier today: this
   golden-signal generation step has never been part of the Windows Task Scheduler automation;
   the user chose to keep it manual rather than add a new scheduled task).
2. cap20 (seed42) is a single-seed artifact. This week's multi-seed verification found ~1.6-2pp of
   MDD variance across seed42/7/123, with seed42 being the more optimistic of the three on some
   metrics — relevant context if this decision is ever revisited.
3. This switch passed **no** formal significance test. If cap20's live performance disappoints,
   that should not be a surprise — it is consistent with what p≈0.348 already implied before the
   switch was made.

## How to revert

Change `DEFAULT_RESULT_JSON` in `scripts/run/run_a2118_own_golden_signal.py` back to
`results/a2118_own_golden_source_20260909.json` (the golden1_0531-weights copy from the earlier,
purely architectural pipeline split). No other file needs to change — this clean insertion point
was deliberately preserved from that earlier fork.

Memory: `project_a2118_cap20_production_switch_20260909.md`.
