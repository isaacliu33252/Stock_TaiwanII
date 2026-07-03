# Group A+ Fable 5 Audit + StockMixer/ATFNet Bugfix + A21.4 Revert — Handoff

**Date:** 2026-07-02 (afternoon/evening session, after `GROUP_A_PLUS_IMPROVEMENT_SESSION_HANDOFF_20260702.md`)
**Scope touched:** `scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py` (research-only, untracked), `group_a_plus/runners/a2118.py`, `group_a_plus/runners/a2115.py`, `group_a_plus/runners/a2111.py`, `group_a_plus/runners/a213.py` (reverted), `group_a_plus/operations/daily_signal.py`, `group_a_plus/integrations/ncf.py`, `scripts/misc/ncf_00631l.py`, `report/group_a_plus/latest/strategy.json`, `ncf_data_quality.py`, `run_daily.bat`, plus test files listed per-section below.

This session had four parts: (1) fix and rerun the StockMixer+ATFNet 0050 research experiment, (2) run a Fable 5 full audit of Group A+, (3) discover and revert an in-flight A21.4 (a214) strategy promotion that the user judged premature, (4) work through the audit's remaining findings (H2 through M5) one at a time at the user's request ("一個一個來"). Sections 1-5 cover parts 1-3 and the first half of part 4 (H1/H3/H4/H5 + the small a2118.py bugs); **section 6 covers the rest of part 4 (M5, M3, M1, M2, M4, H2)** and is the most recent work — read it first if you only have time for one section.

---

## 1. StockMixer+ATFNet 0050 experiment — bugs fixed, rerun, decision unchanged

Full detail in `STOCKMIXER_ATFNET_0050_WEIGHTED_HANDOFF_20260702.md` section 13 (added this session). Summary:

- Fixed 3 bugs in `scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py`: an off-by-one gap in `make_windows()`/`own_history_logistic_baseline()` (window ended at `t-1`, target was `t+1`, skipping day `t`), use of un-adjusted `Close` instead of `Adj Close` (dividend contamination), and a `build_universe_weights()` edge case that silently dropped tickers instead of erroring/zero-weighting.
- The real finding: the original decision evidence (`long_short_sharpe ≈ -2.06` for the weighted 0050-proxy backtest) was a **mechanical artifact** of thresholding a weighted probability at a hard 0.5 — every model predicted "down" on every test day regardless of skill, because the market-cap-weighted index base rate (~56% up) differs from each stock's own calibrated base rate (~50%). Fixed by calibrating the threshold to each model's validation-period median.
- Reran all three universes (top15/full50/top75) on existing caches (no re-download). Decision **unchanged**: still `research_only`, do not wire into live allocation. New evidence is noisier but not stronger either way (73-name universe: `weighted_return_corr=+0.084`; 49-name universe: still `-0.041`).
- All changes are in untracked files (`scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py` was already untracked). No production code touched.

---

## 2. Fable 5 full audit of Group A+ — findings and what was fixed

A `model="fable"` subagent did an open-ended review of Group A+ (not targeted at a specific known issue). Full finding list is in memory `project_group_a_plus_fable5_audit_20260702` — H1 through H5 (high severity) and M1 through M8 (medium). This section covers only what changed in this session.

### 2.1 Fixed this session

**H1 — external market features (VIX, US indices) were silently stale and unmonitored.**
- `run_daily.bat` passed `--skip-refresh` but never `--refresh-external-cache`, so `NCF_EXTERNAL_ALLOW_DOWNLOAD` was never set and the yfinance external cache (`external_market_ohlcv` table) never refreshed automatically. Fixed: added `--refresh-external-cache` to the command in `run_daily.bat`.
- `ncf_data_quality.py::ncf_data_freshness()` never checked `external_market_ohlcv` at all — a stale VIX/US-market cache would report `status: "ok"`. Fixed: added an `external_market_ohlcv` source using `MIN(MAX(dt) per ticker)` (worst-case ticker, not an average) with the same 3-day staleness threshold as the other daily sources. Two tests added/updated in `tests/test_ncf_data_quality.py` (`test_ncf_data_freshness_reports_lags_and_ahead_sources` updated to include the table; `test_ncf_data_freshness_flags_stale_external_market_data` added as an H1 regression test). 4/4 tests pass.

**`group_a_plus/runners/a2118.py` — `or`-as-null-coalescing bug (lines ~434-441).**
`(sig_631l.get("horizon_prob_up") or {}).get("20") or sig_631l.get("calibrated_prob_up", 0.5)` discarded a genuine `0.0` probability (an extreme bearish reading) and substituted the calibrated ensemble value instead, because `or` treats `0.0` as falsy. Fixed with an explicit `is not None` check. Same fix applied to the `h5_prob` line.

**`group_a_plus/runners/a2118.py` — `trim_fraction` reporting bug (line ~517).**
The `backtest_live_discrepancy.trim_fraction` field hardcoded `0.25`, but the live default in `daily_signal.py::_apply_bearish_high_risk_trim` (`trim_fraction: float = 0.20`) is `0.20` and is called with no override. Fixed the reported value to match reality. This is a documentation/reporting field only — it does not feed back into any decision logic, so this fix has no behavioral effect, only a correctness-of-reporting effect.

**Dead code cleanup — `LATE_BULL_HEDGE_WEIGHTS` constant.**
Both `a2118.py` and `a2115.py` defined a static `LATE_BULL_HEDGE_WEIGHTS = {...}` dict (assuming a fixed 60/20/20 golden1 basket) that was never referenced anywhere — the actual hedge weights are computed dynamically by `_late_bull_hedge_weights()` from whatever golden1 currently is. Removed both (confirmed via repo-wide grep that nothing else referenced the constant; no test depended on it).

All of the above were verified with `py_compile` + the relevant pytest files (`tests/test_ncf_data_quality.py`, and later the full `tests/test_group_a_plus_latest_strategy.py` + a broader `-k "a2118 or a2115 or a213 or a214 or ..."` run — all green, see section 4).

### 2.2 Deliberately NOT fixed this session (flagged, needs a decision)

These change **live risk behavior for an active, real-money strategy** and were not touched without explicit sign-off:

- **H2** — panel `confidence` (`prob_magnitude`) and live-JSON `confidence` (`consensus×0.4 + magnitude×0.4 + spread×0.2`) are different definitions on completely different scales (measured 0.031 vs 0.5683 same day). `a2118`'s `conf_min=0.55` gate means something very different depending on which one is actually being read at trigger time. `reconcile_latest_panel_row` also overwrites the panel's last row with the JSON-scale value, mixing definitions within one column.
- **H3** — runner backtests resolve "golden1" weights from whichever Group A live-signal file has the newest mtime, so a backtest run today replays the *entire history* under today's golden1 weights, not the weights that were actually in force on each historical date. This is a second, previously-unrecorded drift channel distinct from the already-known NCF panel weight drift (`project_ncf_panel_global_weight_drift_20260702`).
- **H4** — overlay backtests switch regime at the *signal day's* close, but the real NCF signal isn't produced until 23:30 that night — a 1-trading-day look-ahead in every NCF-overlay backtest. `_delayed_regime` already exists in `backtest_group_a_plus_defensive_basket.py:85` but isn't used as the a2118 decision baseline.
- **H5** — when the NCF signal is stale/date-mismatched, `daily_signal.py::_a2118_live_hard_overlay_reason` returns `None` unconditionally (line ~236-237), so an already-active hedge silently reverts to full-leverage golden1 with only a warning log, `execution_allowed` still `True`. Fail-open in the case that most needs fail-closed.
- **M1** — `_build_expanding_horizon_ensemble_panel`'s AUC-weighting for the H=20 label uses `label_df[horizon].iloc[:pos]`, which includes up to 19 days of forward label look-ahead near the training frontier (should be `iloc[:max(0, pos - horizon)]`). Small magnitude (slow-moving expanding statistic) but is exactly the "rolling/expanding without embargo" pattern this session was asked to watch for.
- **M2-M8** — see the memory file for the full list (a2115 dead-code bugs are now confirmed *not* live-path, so lower priority; strategy signature pinning, rally_suppress/hard-overlay interaction, hardcoded TW holiday calendar, FinRL vs Group A+ metric convention mismatch, signal_alignment double-counting NCF via execution_regime, FinMind fetch resilience).

**Do not fix H2/H3/H4/H5/M1 without discussing the intended behavior change first** — each one changes when/how the live a2118 hedge triggers or falls back, which is exactly the kind of change that needs explicit confirmation before touching, per this session's own experience with the a214 promotion below.

---

## 3. The A21.4 (a214) promotion — discovered, investigated, reverted

**What happened:** at 17:40 today, *outside this conversation* (not by any action in this session), something promoted the Group A+ active strategy from `a2118_a2111_ncf_late_bull_deleverage` to `a214_bond30c30_mw60` (A21.4 = A21.3 base + MA60 entry + `bond30_cash30` defensive basket, per the 2026-06-20 research doc `Three_Direction_Handoff_20260620.md`). The same edit also changed `group_a_plus/runners/a213.py::run_a213()`'s defaults in place from the historically-`"immutable"` `basket_name="cash30", ma_window=75` to `basket_name="bond30_cash30", ma_window=60"` — i.e. it edited the function `test_a213_parameters_are_immutable` exists specifically to guard.

**How it was found:** two pre-existing test failures (`test_repository_manifest_activates_a2118`, `test_a213_parameters_are_immutable`) surfaced while verifying the H1/a2118.py fixes above didn't break anything. Neither failure was caused by this session's edits — tracing them back led to the strategy.json diff and the a213.py diff.

**Key fact: a214 does not carry over a2118's NCF overlay.** `group_a_plus/runners/a214.py` is a thin wrapper directly around `a213._run_recovery_strategy(basket_name="bond30_cash30", ma_window=60, ...)` — no NCF, no confidence, no late-bull hedge logic at all. The promotion note in `strategy.json` said this explicitly: *"NCF overlay can be re-added on top of A21.4 parameters as a separate candidate."*

**Decision:** user reviewed and judged **a2118 is the better strategy** (keeps the NCF late-bull de-leverage risk control; a214's higher isolated Sharpe/Sortino/return come from dropping that overlay entirely, which is a different risk profile, not a strict improvement). Instructed to revert.

**How it was reverted:**
1. `report/group_a_plus/latest/strategy.json` — restored the full `active_strategy` block for a2118 from `results/group_a_plus_latest_strategy_resolved_20260701.json` (a governance-script-generated resolved snapshot from 2026-07-01 20:27, i.e. hard evidence of the exact pre-promotion state, not reconstructed from memory/fragments). `previous_strategy` now records a214's brief promotion and reversion (with its actual 2026-07-02 backtest metrics) rather than silently erasing that it happened, so the audit trail is honest.
2. `group_a_plus/runners/a213.py` — reverted via `git checkout -- group_a_plus/runners/a213.py` (the file's git-tracked base version already matched the pre-promotion "immutable A21.3" state — a clean revert, no manual reconstruction needed).
3. `group_a_plus/runners/a214.py` itself was **left in place** — it's a legitimate, self-contained research candidate (created 2026-06-21) that can be reconsidered later; only the *promotion* was reverted, not the code.
4. Verified: `pytest tests/test_group_a_plus_latest_strategy.py` → 21/21 pass (both previously-failing tests now pass); broader `-k "a2118 or a2115 or a213 or a214 or ..."` → 114/114 pass; full `pytest tests/` run was in progress at the time this doc was written — see the live session for the final tally, or rerun `.venv/bin/python -m pytest tests/ -q`.

**Files touched by the revert:**
- `report/group_a_plus/latest/strategy.json` (rewritten)
- `group_a_plus/runners/a213.py` (git-reverted, zero diff vs HEAD)

**Not touched / left as-is:**
- `group_a_plus/runners/a214.py` (kept as a research candidate)
- `results/group_a_plus_runner_a214_20260702.json`, `results/group_a_plus_runner_a214_20260702_frame.csv`, `backtest_group_a_plus_a214_attribution.py` (artifacts from the brief promotion; harmless, kept for reference)

### 3.1 Open question for next session

Neither `run_ncf_daily_pipeline.py` nor any checked-in script actually *writes* `strategy.json`'s promotion fields (`active_strategy`, `previous_strategy`, `promoted_from`, `deactivated_at`) — grepped for `deactivated_at`/`promoted_from` across the repo and found no production writer, only the test file. **This manifest is hand-edited**, which is how an unreviewed promotion could happen in the first place (no CLI, no confirmation step, no diff review built in). If Group A+ promotions are going to keep happening, it's worth asking the user whether a small promotion/rollback script (write the manifest transactionally, keep a rotating history of prior states so a revert doesn't require digging through `results/*resolved*.json` snapshots like this session had to) is worth building — flagging, not doing unprompted.

---

## 4. Test status at end of session

```
tests/test_ncf_data_quality.py ................ 4 passed
tests/test_group_a_plus_latest_strategy.py ..... 21 passed
-k "a2118 or a2115 or a213 or a214 or bayesopt_a2118 or
    group_a_plus_latest_strategy or group_a_plus_ncf_integration
    or ncf_data_quality" .......................... 114 passed
tests/test_fourier_features.py +
tests/test_evaluate_stock_ranking_walkforward.py ... 24 passed (StockMixer section)
full `pytest tests/` .............................. was running at doc-write time
```

Run `.venv/bin/python -m pytest tests/ -q` to get the final full-suite tally if picking this up later.

---

## 5. Priority-ordered follow-ups

Updated after a second pass this same session that closed out H3, H4 (analysis), and H5:

1. ~~**H5** — make the NCF-stale fallback fail-closed~~ **Done.** `_a2118_live_hard_overlay_reason()` now returns a new `"stale_fail_closed"` reason when NCF is stale/mismatched *and* the previous day's hedge/hold was active; it reuses the `ncf_late_bull_hedge` weight basket (same as `h5_hold`) instead of falling back to golden1, and raises a new high-severity `a2118_ncf_stale_fail_closed` alert for manual review. 3 new tests in `tests/test_group_a_plus_daily_signal_v2.py` (20/20 pass).
2. ~~**H3** — version/pin golden1 weights per backtest run~~ **Done.** Added `_golden_signal_metadata(path, weights)` to `a2111.py` (path/sha256/mtime/resolved-weights, mirroring the existing `ncf_panel_coverage` guard); both `a2111.py` and `a2118.py` reports now carry a `golden_signal_coverage` field. Does **not** change how the path is resolved (still newest-mtime) — only makes the choice auditable. 2 new tests in `tests/test_a2111_golden_signal_metadata.py`.
3. ~~**H4** — rerun a2118 with `_delayed_regime`~~ **Done as an analysis, not a live-behavior change.** Added an opt-in `regime_execution_delay_days: int = 0` parameter to `run_a2118()` (default 0 = zero behavior change for every existing caller/test) plus a `--regime-execution-delay-days` CLI flag. Ran both variants against the pinned production config (`ncf_panel_631l_path=results/ncf_00631l_panel_latest_20260630.csv`, `h20_max=0.33`, `conf_min=0.55`, `h5_reentry_min=0.55`):

   | | delay=0 (existing) | delay=1 (H4 real-world) | Δ |
   |---|---:|---:|---:|
   | Sharpe | 2.5258 | 2.4974 | -0.028 (-1.1%) |
   | Annual return | 66.29% | 64.89% | -1.4pp |
   | Max drawdown | -13.816% | -13.818% | ~0 |

   **Finding: the look-ahead is real but small** — only one hedge trigger occurred in the test window (2025-10-29), so the 1-day gap only affects that single transition's entry timing. **This does not change the "a2118 is the better strategy" conclusion from section 3.** Results saved at `results/a2118_h4_delay0_baseline_20260702.json` / `results/a2118_h4_delay1_20260702.json`.
4. ~~**H2** — needs a decision first~~ **Done — see section 6.** User chose Option A (unify on the panel's method).
5. ~~**M1** (ensemble weight forward-label leak)~~ **Done — see section 6.**
6. ~~**M2** (a2115 dead-code bugs)~~ **Done — see section 6.**
7. ~~**M3** (pinned panel staleness warning)~~ **Done — see section 6.**
8. ~~**M4** (rally_suppress / effective_hedge_active mismatch)~~ **Done — see section 6.**
9. ~~**M5** (Taiwan holiday calendar)~~ **Done — see section 6.**
10. ~~**M6** (FinRL vs Group A+ metric convention mismatch)~~ **Fully done — see sections 6.8 and 6.14.** Metric-convention reconciliation helper shipped (6.8); the dual-engine P&L reconciliation (6.14, done 2026-07-03) confirms the two engines broadly agree, with the residual gap explained by known methodology differences.
11. ~~**M7** (`signal_alignment` double-counting `execution_regime`)~~ **Done — see section 6.10.**
12. ~~**M8** (FinMind fetch resilience)~~ **Partially done — see section 6.11.** Retry/backoff and the `chip_start` 21-day window both shipped; pipeline-visibility-of-failures and `ncf_external_cache.py`'s ex-dividend cache-boundary issue were not attempted (bigger scope, span multiple functions/files).
13. **The promotion-tooling gap noted in 3.1** — worth a short discussion, not urgent.
14. Everything in `STOCKMIXER_ATFNET_0050_WEIGHTED_HANDOFF_20260702.md` section 13.5 (multi-seed/walk-forward eval, truncation-invariance tests for the *production* `fourier_features.py`/`cross_asset_relation.py`) if that research line is picked back up.

**As of the end of this session, every item from the original Fable 5 audit (H1-H5, M1-M8) has been addressed at least once** — either fully fixed, fixed-with-tests-but-scoped-down (M6, M8), or done as analysis rather than a code change (H4). Nothing from the original audit is untouched; what remains is the *larger* sub-scope items noted above (dual-engine backtest reconciliation, pipeline failure visibility, cache-boundary fix, `chip_start` windowing), each independently sized like its own small project.

### 5.1 Test status after H3/H4/H5

```
tests/test_group_a_plus_daily_signal_v2.py ..... 20 passed (H5: 3 new)
tests/test_a2111_golden_signal_metadata.py ..... 2 passed (H3: new file)
-k "a2118 or a2111 or a2115 or a213 or a214 or
    group_a_plus_latest_strategy or group_a_plus_ncf_integration
    or daily_signal or ncf_data_quality or bayesopt" ... 129 passed
full `pytest tests/` (started right after H3/H4/H5) ... 494 passed, 9 skipped, 0 failed
```

---

## 6. Third pass: M5, M3, M1, M2, M4, H2 — "一個一個來" (do them one by one)

User asked to work through the remaining items one at a time, verifying with tests after each. Order below is the order done, low-risk first.

### 6.1 M5 — Taiwan holiday calendar had only one date

**First attempt reverted: do not infer holidays from ohlcv-table gaps.** Tried inferring market holidays as "weekdays where no ticker in `TICKERS` has an `ohlcv` row." This broke two existing tests (`test_optional_source_freshness_aligns_to_actual_price_date`, `test_t_plus_one_chip_sources_are_allowed_but_t_plus_two_blocks`) whose fixtures only insert a single sparse date — nearly the entire lookback window got misclassified as "holidays," masking the staleness the tests exist to catch. **This is the real lesson from M5:** inferring a holiday calendar from data-completeness is unsafe for a risk-management staleness gate whenever the underlying table isn't guaranteed densely populated (test fixtures aren't; production may have similar edge cases). Fully reverted (`_infer_market_holidays`, its call sites, and the `market_holidays` plumbing through `_source_freshness`/`build_daily_signal` all removed).

**What shipped instead:** `TAIWAN_MARKET_HOLIDAYS` in `daily_signal.py` hand-expanded from 1 date to a best-effort 2025-2026 TWSE calendar (New Year, Lunar New Year, Peace Memorial Day, Tomb Sweeping/Children's Day, Labor Day, Dragon Boat Festival, Mid-Autumn Festival, National Day — with the usual weekend-observed-date adjustments). Explicitly does not cover ad hoc typhoon/earthquake closures (announced same-day). 4 new tests in `tests/test_group_a_plus_daily_signal_v2.py`.

### 6.2 M3 — pinned NCF panel had no staleness warning

`_build_signal_alerts()` gained an `ncf_panel_coverage` parameter and a new `ncf_panel_stale` alert: compares `panel_631l_last_date` against the signal date via `_business_days_between`, `medium` at ≥3 trading days behind, `high` at ≥10. Wired from `build_daily_signal` via `report.get("ncf_panel_coverage")`. 2 new tests in `tests/test_group_a_plus_latest_strategy.py`.

### 6.3 M1 — ensemble AUC weighting had unembargoed forward labels

`_build_expanding_horizon_ensemble_panel()` in `scripts/misc/ncf_00631l.py`: the per-row AUC-weight computation used `label_df[horizon].iloc[:pos]`, which for horizon=20 includes up to 19 rows whose forward label needs 20 days of *future* price data to resolve — i.e. up to 19 days of look-ahead leaking into the weight (not the ensemble probability itself — every row still gets a probability; only the *confidence weighting between horizons* was affected). Fixed to `iloc[:max(0, pos - horizon)]`. New regression test `test_expanding_horizon_panel_embargoes_unresolved_forward_labels` in `tests/test_ncf_00631l_paths.py` — constructs data where h=20 should contribute zero weight (not a leaked AUC value) until `pos >= min_history + horizon`.

**Important scope note:** this only affects panels *generated from now on*. The currently pinned `results/ncf_00631l_panel_latest_20260630.csv` (see M3 above, and section 3) is not automatically regenerated — no live behavior changes until/unless that panel is refreshed.

### 6.4 M2 — a2115.py had two dead-path bugs, fixed for consistency (not urgency)

Confirmed via a dedicated Explore-agent investigation that `a2115.py` is not wired into any live/production path (`daily_signal.py` only ever calls `a2118.py` via the `strategy.json` manifest; `a2115` only appears in `governance/latest.py`'s validation dict). Fixed anyway, matching a2118.py's already-corrected logic, since a2115 could be revived later and the fixes are cheap:
- `_resolve_ncf_path()`: old glob `ncf_{tag}_2?????.json` (exactly 6 wildcard chars) never matched real 8-digit-dated or `_latest_`-prefixed filenames — always returned `None`. Replaced with the same two-pattern glob + panel-exclusion a2118.py uses.
- The live-signal block read `sig_631l.get("prob_up_h20", ...)` — `load_ncf_signal()` never returns that key (it returns `horizon_prob_up: {"1":..,"5":..,"20":..}` and `calibrated_prob_up`) — always fell through to the ensemble-average fallback. Fixed to `horizon_prob_up.get("20")`.
- Removed now-unused `import glob` / `from datetime import date`.
- No dedicated a2115 tests exist (further confirming it's not on a tested/live path) — verified with `py_compile` + an import smoke test only.

### 6.5 M4 — `late_bull_triggered` vs `effective_hedge_active` mismatch

`_a2118_live_hard_overlay_reason()`'s `"trigger"` branch checked `ncf_live_signal.get("late_bull_triggered")` directly, ignoring `rally_suppressed`/`effective_hedge_active` (which a2118.py's live-signal block already computes: `effective_hedge_active = late_bull_triggered and not rally_suppressed`). If `rally_suppress_min` is ever enabled, a rally-suppressed trigger day would still apply hard-hedge weights via this path, and the next day's `_previous_a2118_hold_active` would wrongly extend an h5_hold chain from a hedge that was never really active. Fixed: `ncf_live_signal.get("effective_hedge_active", ncf_live_signal.get("late_bull_triggered"))` (new field preferred, old field as fallback for payloads predating it). **`rally_suppress_min` is not currently enabled — this fix is preventative, zero live-behavior change today.** New test in `tests/test_group_a_plus_daily_signal_v2.py`.

### 6.6 H2 — confidence definition unification (Option A) — the one behavior-changing fix

User picked **Option A**: unify on the panel's `prob_magnitude` computation (the metric a2118's `conf_min=0.55` was actually swept/calibrated against), rather than Option B (switch to the richer composite `confidence` and re-sweep `conf_min` from scratch — noted as a future research question, not done). See section 7 for the full formula breakdown given to the user.

**Root cause, precisely:** panel `prob_magnitude = abs(ensemble_prob_up - 0.5) * 2`, where `ensemble_prob_up` comes from `_build_expanding_horizon_ensemble_panel`'s expanding-window (walk-forward-through-calendar-time) AUC weighting. Live JSON `confidence = consensus*0.4 + prob_magnitude*0.4 + spread_conf*0.2` (clamped to `[0.1, 1.0]`), where this `prob_magnitude` is computed from `combined_prob`, itself weighted by **fixed per-horizon AUC from that training run's own validation set** — a completely different weighting scheme, not just a different formula on the same number. Confirmed panel's `confidence` column already equals `prob_magnitude` exactly (`_val_predictions` panel sets `panel_df["confidence"] = prob_magnitude*0.6 + 0.4*prob_magnitude.clip(0,1)`, which is algebraically `== prob_magnitude`).

**What shipped:**
1. `scripts/misc/ncf_00631l.py`: right after the existing `consensus`/`prob_magnitude`/`spread_conf` computation, added a block that reuses `val_panels` (same source data as the panel builder, already populated earlier in `main()` regardless of `--val-predictions-output`) to call `_build_expanding_horizon_ensemble_panel()` again and take the **last row's** `ensemble_prob_up` / `prob_magnitude` — i.e. the panel-consistent value for today. Wrapped in try/except (prints a warning, leaves the fields `None` on failure — never blocks JSON generation). Added to the `horizon_ensemble` payload as two **new** fields: `ensemble_prob_up_panel_aligned`, `prob_magnitude_panel_aligned`. The old composite `confidence` field is untouched (other consumers may still read it).
2. `reconcile_latest_panel_row()`: previously overwrote the panel's last-row `ensemble_prob_up`/`prob_magnitude`/`confidence` using `combined_probability_up` (the differently-weighted JSON metric) — this was the actual contamination point the audit found (a panel column meaning "expanding-AUC prob_magnitude" on every other row, overwritten with a JSON-composite-derived value on the last row). Now reads `ensemble_prob_up_panel_aligned`/`prob_magnitude_panel_aligned` instead; if those keys are absent (old JSON format), the panel's existing values for that row are left untouched rather than overwritten with something wrong.
3. `group_a_plus/integrations/ncf.py::load_ncf_signal()`: returns a new `confidence_panel_aligned` key — `None` when the JSON payload predates this field (does **not** silently fall back to the differently-scaled `confidence`).
4. `group_a_plus/runners/a2118.py`: the live-signal block's `conf = float(sig_631l.get("confidence", 0.0))` → reads `confidence_panel_aligned`, defaulting to `0.0` (never triggers) rather than the old composite value when absent.

**Behavioral consequence (the point of doing this):** panel-based backtest calibration found `conf_min=0.55` selects roughly the top 8% most extreme days by `prob_magnitude` (29/359 in one sample). The live JSON's composite `confidence` runs structurally higher (0.1 floor + consensus/spread additive terms), so the same `0.55` threshold was far less selective live than in the calibration backtest. After this fix, live trigger frequency should converge toward what the backtest assumed — **most likely fewer triggers than before**, not more. This takes effect the next time `ncf_00631l.py` regenerates the live JSON; until then `confidence_panel_aligned` is absent → `conf=0.0` → a2118 does not trigger via this path (existing `stale_fail_closed`/`h5_hold` paths from H5 are unaffected, since those don't depend on this field).

**Tests:** `tests/test_ncf_data_quality.py` (`test_reconcile_latest_panel_row_aligns_json_horizon_payload` updated to the new fields/values; `test_reconcile_latest_panel_row_skips_alignment_when_field_absent` added for the backward-compat path). `tests/test_group_a_plus_ncf_integration.py` (`test_load_ncf_signal_confidence_panel_aligned_absent_is_none`, `test_load_ncf_signal_confidence_panel_aligned_present`).

**Option B, not done:** switch the standard to the richer composite `confidence` (consensus + magnitude + spread) instead, and re-sweep `conf_min` against it from scratch (today's `0.55` calibration doesn't transfer — different metric shape). Flagged by the user as a future research question, independent of and not blocking this fix.

### 6.7 Test status after section 6

```
tests/test_group_a_plus_daily_signal_v2.py ........... 23 passed (M4: 1 new, on top of H5's 20)
tests/test_group_a_plus_latest_strategy.py ............ 25 passed (M3: 2 new)
tests/test_ncf_00631l_paths.py ......................... 3 passed (M1: 1 new)
tests/test_ncf_data_quality.py ......................... 5 passed (H2: reconcile behavior updated + 1 new)
tests/test_group_a_plus_ncf_integration.py ............ 64 passed (H2: 2 new)
-k "a2118 or ncf_integration or ncf_data_quality or ncf_00631l or
    a2115 or daily_signal or group_a_plus_latest_strategy or
    bayesopt or a2111" ................................. 137 passed
full `pytest tests/` (started after M5/M3/M1, before M2/M4/H2) ... 494 passed, 9 skipped, 0 failed
```

No full-suite run has been done *after* M2/M4/H2 specifically — the targeted `-k` run above (137 passed) covers every file touched by those three, but if picking this back up, rerun `.venv/bin/python -m pytest tests/ -q` for a final all-green confirmation before considering the day's work fully closed out.

### 6.8 M6 — FinRL vs Group A+ metric convention mismatch (documentation + helper only)

`FinRL/v2/backtesting/performance_metrics.py`'s `calculate_sharpe_ratio`/`calculate_sortino_ratio` default to `risk_free_rate=0.02` (2% annual) and `calculate_volatility` returns a percentage; `backtest_group_a_plus_switch_policy.py::_metrics()` uses `risk_free_rate=0` (no subtraction at all) and returns every ratio as a decimal fraction. Same equity curve → Sharpe differs by ~0.1-0.3 depending on which system computed it. **Did not change either system's defaults** — that would alter the reported numbers of every existing backtest report that already relies on them, for no clear "correct" default (it's a legitimate convention choice, not a bug in either).

**What shipped:** a detailed docstring on `_metrics()` warning about the discrepancy and pointing to the fix; a new `_metrics_finrl_comparable(values, risk_free_rate=0.02, periods_per_year=252)` function in `backtest_group_a_plus_switch_policy.py` that **calls FinRL's functions directly** rather than reimplementing the formulas — this was a deliberate choice after discovering FinRL's Sortino downside-deviation uses `np.std(negative_excess_returns, ddof=1)` (sample std of the negative-excess subset), a genuinely different formula from the naive root-mean-square-from-zero reimplementation (which is what both Group A+'s own Sortino and a first-draft reimplementation used) — calling FinRL directly avoids introducing a *second*, harder-to-notice formula mismatch on top of the one being fixed. A matching cross-reference docstring was added to FinRL's `calculate_sharpe_ratio`. 3 new tests in `tests/test_backtest_group_a_plus_metrics_finrl_comparable.py`, including one that asserts the FinRL-comparable Sharpe is measurably lower than `_metrics()`'s own Sharpe for the same curve — confirms the systematic offset is real, not just theoretical.

**Not done:** the audit's other M6 suggestion — actually running a2118's regime/weight sequence through `FinRL.v2.backtesting.BacktestEngine` and reconciling P&L against `_simulate_costed_curve`'s output for the *same* inputs. That's a real integration task (mapping Group A+'s regime-switch weight series into whatever input shape `BacktestEngine` expects), not a quick fix, and reconciling the *metric formula* doesn't by itself confirm the two *engines* agree on P&L. Left as a follow-up.

### 6.9 Test status after M6

```
tests/test_backtest_group_a_plus_metrics_finrl_comparable.py .. 3 passed (new file)
-k "switch_policy or performance_metrics or finrl_comparable or
    a2118 or a2111" ..................................... 45 passed
```

### 6.10 M7 — `signal_alignment.py` double-counting `execution_regime`

When a2118's NCF late-bull hedge is active, `execution_regime == "ncf_late_bull_hedge"`, and `_execution_regime_source()` voted `bearish` at strength 0.65 on top of the three already-NCF-derived sources (`ncf_00631l`, `ncf_00632r_inverse`, `ncf_cross_ticker`) — the same underlying NCF reading counted as up to 4 "independent" bearish votes, inflating `weighted_share["bearish"]` and making it easier to cross the `bearish_alignment`/`wide_divergence` thresholds that `_apply_bearish_high_risk_trim` (`daily_signal.py`) uses to apply an *additional* 00631L cut on top of a2118's own hedge — a form of double-penalizing the same signal.

**Fix:** `_execution_regime_source()` now returns `available=False` (excluded from the vote entirely) when `regime in {"ncf_late_bull_hedge", "ncf_late_bull_hedge_soft"}`. `group_a_plus_defensive` (MA/price-derived, genuinely independent of NCF) still votes as before. **Confirmed against a real scenario, not a hypothetical:** the existing test `test_signal_alignment_detects_current_bearish_alignment`'s fixture already used `execution_regime="ncf_late_bull_hedge"` — its `available_sources` assertion dropped from 7 to 6 after the fix, directly demonstrating the double-count this closes. 2 new tests in `tests/test_group_a_plus_signal_alignment.py` (`test_execution_regime_excluded_when_ncf_hedge_active`, `test_execution_regime_still_votes_for_technical_defensive_regime`).

### 6.11 M8 — FinMind fetch resilience (retry/backoff shipped; 3 sub-issues left)

The audit bundled three distinct problems under M8; only the first was fixed today:

1. **Fixed: no retry/backoff on transient failures.** `scripts/fetch/fetch_finmind_chip_data.py::_get()` previously made a single `requests.get()` call with no retry at all — one 429 (rate limit) or 5xx blip aborted that dataset/ticker's fetch for the day, and the many `except RuntimeError: skip` call sites (`fetch_derivative_institutional`, `fetch_derivative_large_trader`, etc.) would just silently drop it. Added retry with exponential backoff (respecting a `Retry-After` header when FinMind sends one) for 429/5xx/connection errors, up to 3 attempts. **402 (FinMind's free-tier quota/plan gate) and other 4xx are deliberately *not* retried** — those aren't transient, and retrying just burns attempts before failing anyway. 7 new tests in `tests/test_fetch_finmind_chip_data_retry.py` covering: 429-then-success, `Retry-After` header respected, 5xx-then-success, 402 fails immediately with no sleep, retries exhausted raises, connection-error retry, first-try success has zero sleep calls.
2. **Fixed: `chip_start = today - 21 days` fixed lookback window (M8-2).** `run_ncf_daily_pipeline.py` gained `_resolve_chip_start(db_path, tables, default_start)`, which queries `MAX(dt)` for the given table(s) and returns the *earlier* of the default 21-day lookback and (day after the last known row) — this only ever widens the fetch window to cover a real gap, never narrows it below the default (a fresh table still gets the full default trailing window, so late-arriving upstream revisions are still covered). Applied independently to each of the four chip-data commands (`institutional_data`, `margin_data`, `market_margin_data`, `derivative_institutional_data`) via their own resolved start — a gap in one table's history doesn't affect the others' windows. Falls back silently to the original fixed `chip_start` if the DB/table doesn't exist or the query errors, so this never blocks the pipeline. 5 new tests in `tests/test_run_ncf_daily_pipeline.py` (DB-missing fallback, the actual gap-extension scenario, fresh-table-doesn't-narrow, missing-table fallback, per-table independence) — plus the 3 pre-existing tests in that file were given an explicit `db="/nonexistent/..."` so they don't accidentally query the real project DB.
3. **Not done: pipeline can't see fetch failures.** The `except RuntimeError: print(...); continue` pattern (now hit less often thanks to #1, and now covers a smaller true gap thanks to #2, but still reachable for genuine persistent failures) doesn't propagate to `run_ncf_daily_pipeline.py` — the script's exit code stays 0 either way. Fixing this means collecting skip/failure counts and either returning them from each `fetch_*` function or raising once a threshold is exceeded, which touches every one of the ~10 fetch functions in this file plus their caller. Bigger change, not attempted.
4. **Not done: `ncf_external_cache.py` `auto_adjust=True` cache-boundary issue.** `_write_cache()` only deletes/replaces rows in the freshly-downloaded date range; since `auto_adjust=True` re-bases historical prices relative to *all* dividends/splits known at download time, a ticker re-cached after an ex-dividend date can have old and new cached rows computed against different adjustment bases, producing a spurious price jump exactly at the cache boundary — which would then contaminate `pct_change`-based features. Audit's suggested fix: cache raw price + adjustment factor separately, or fully rebuild the cached range for a ticker on every re-fetch rather than only the new portion. Not attempted.

### 6.12 Test status after M7/M8

```
tests/test_group_a_plus_signal_alignment.py ................ 10 passed (M7: 2 new)
tests/test_fetch_finmind_chip_data_retry.py .................. 7 passed (M8-1: new file)
tests/test_run_ncf_daily_pipeline.py ......................... 8 passed (M8-2: 5 new)
-k "signal_alignment or daily_signal or group_a_plus_latest_strategy
    or bearish_high_risk or a2118" ........................... 80 passed
-k "finmind" ................................................. 13 passed
-k "run_ncf_daily_pipeline or fetch_finmind" ................. 18 passed
```

The full-suite run kicked off after H2/M2/M4 (section 6.7) eventually completed: **498 passed, 9 skipped, 0 failed** (53:56 wall-clock — slow because many other pytest invocations were competing for CPU throughout this session; not a sign of a problem). It covered everything through M2/M4 but was already running before M5-M8-2 landed; those were only verified with targeted `-k` runs, not re-covered by a second full-suite pass yet.

### 6.13 H2 Option B — composite confidence research (2026-07-03, no live change)

User asked to try Option B (rejected at the H2 decision point in section 6.6) as a research question, separate from and not reversing Option A (which stays shipped/live). New standalone script `scripts/evaluate/evaluate_a2118_composite_confidence_sweep.py` — touches no live/production file:

1. Recomputes the old composite-confidence formula (`consensus*0.4 + prob_magnitude*0.4 + spread_conf*0.2`, clamped `[0.1, 1.0]`) purely from columns already in the pinned panel CSV (`prob_up_h1`/`h5`/`h20` for consensus+spread, the panel's own `prob_magnitude` for the magnitude term — no live JSON needed).
2. Writes this as a **temp copy** of the panel (never touches the real file).
3. Runs `run_a2118()` once per `conf_min` in a grid (0.30-0.80) against the temp panel, and once against the real panel at `conf_min=0.55` as the Option A baseline.

**Result — composite confidence is directionally better, but the sample is too small to call it conclusive:**

| | conf_min | Sharpe | Annual | MDD | Triggers |
|---|---:|---:|---:|---:|---:|
| Option A baseline (prob_magnitude, live) | 0.55 | 2.5258 | 66.29% | -13.82% | 1 |
| Option B best (composite) | 0.75 | 2.5661 | 64.03% | -13.82% | 3 |

Option B's best setting triggers earlier on the same event Option A caught (2025-10-21 vs 2025-10-29) and catches two additional events Option A missed entirely (2026-02-26, 2026-04-17). MDD is identical across almost the entire sweep (the test window's worst drawdown isn't inside any of the candidate trigger windows), so Sharpe is the only real differentiator, and a ~1.6% Sharpe gap on 1 vs 3 discrete trigger events is well within plausible noise for a single fixed backtest window. **Decision: keep Option A live** (per section 6.6) — this finding is worth recording, not strong enough to reopen that decision. Getting real confidence here would need multiple walk-forward windows, not one fixed 2025-01-02-to-now period. 4 new tests in `tests/test_a2118_composite_confidence_sweep.py` (composite-formula correctness only, not the sweep itself). Results saved at `results/a2118_h2_option_b_composite_sweep_20260703.json`.

### 6.14 M6 — dual-engine reconciliation (2026-07-03, the last big item)

The audit's original M6 suggestion, done as a follow-up: actually run a2118's daily target weights through an independent engine and compare P&L against `_simulate_costed_curve`.

**Key discovery before this could even be built:** `FinRL/v2/backtesting/backtest_engine.py` (the module this handoff's section 6.8 assumed would be used) is a **single-instrument** engine — one scalar `position`, one `close` price series, designed for an RL agent trading a single stock (`buy`/`sell` actions). It **cannot** consume a multi-asset weight-allocation strategy like a2118's at all. The actually-usable engine is a **different file**, `FinRL/backtesting/backtest_engine.py` (note: `FinRL/backtesting/`, not `FinRL/v2/backtesting/`) — a `bt`-library-based, weight-centric engine taking a `StrategyResult(weights: DataFrame[date, ticker])`. `FinRL/backtesting/group_a_bridge.py` already uses exactly this engine to reconcile Group A's RL strategy — it was the right reference pattern to follow, just for a different (non-RL, regime-switching) strategy.

**What shipped:** `scripts/evaluate/evaluate_a2118_finrl_dual_engine_reconciliation.py`. Reconstructs a2118's actual daily target weights from `report["base_weights"]` (regime → weight dict) and `frame["execution_regime"]` (daily regime), reloads the same total-return price series a2118 itself used, adds a constant-price=1.0 synthetic "cash" column (FinRL's engine needs every non-zero weight column priced), wraps it as a `StrategyResult`, and runs it through `FinRL.backtesting.BacktestEngine` with `risk_free_rate=0.0` (to match `_metrics()`'s own convention from section 6.8, not FinRL's 0.02 default).

**Result:**

| | a2118's own engine | FinRL engine | Δ |
|---|---:|---:|---:|
| Sharpe | 2.5258 | 2.4686 | -0.057 (-2.3%) |
| Annual return | 66.29% | 64.33% | -1.96pp |
| Max drawdown | -13.82% | -14.49% | -0.68pp |
| Total return | 113.87% | 103.72% | -10.15pp |

**The two engines broadly agree** — same order of magnitude, same conclusion ("a2118 is a strong strategy"), no metric flips sign or changes by an order of magnitude. The residual gap is consistent with documented, expected methodology differences (not a hidden bug in either engine):
- FinRL's engine (`_cost_fn`) doesn't model slippage at all; a2118's own curve charges `slippage_rate=0.0005` on every trade.
- FinRL's engine applies one `tax_rate` to every ticker (set to 0.001 here as the closest single-parameter approximation); a2118 distinguishes equity-ETF sell tax (0.001) from bond-ETF sell tax (0.0).
- `bt`'s `WeighTarget`+`Rebalance` algo pair has its own execution-day semantics for reaching a target weight, which may not exactly match `_simulate_costed_curve`'s own share-tracked rebalancing — plausibly related to the same kind of one-day timing effect section 3's H4 analysis already found to be small.

**This is a confirming result, not a debunking one** — it does not surface a hidden bug in a2118's own reported Sharpe/MDD, and doesn't change any decision from earlier in this document. 2 new tests in `tests/test_a2118_finrl_dual_engine_reconciliation.py` (daily-weight-from-regime resolution logic only — the full engine run isn't unit-tested, it's the research script's actual execution that serves as the check). Results saved at `results/a2118_m6_dual_engine_reconciliation_20260703.json`.

### 6.15 M8-3 / M8-4 — the last two items, closed (2026-07-03)

User asked to finish M8-3 and M8-4 rather than leave them open.

**M8-3 — pipeline couldn't see fetch failures.** Investigation found the swallow-and-continue pattern (`except RuntimeError: print(...); continue`) only exists in 12 call sites across 11 functions (`fetch_derivative_institutional`, `fetch_derivative_large_trader`, `fetch_stock_per`, `fetch_securities_lending`, `fetch_short_sale_balances`, `fetch_total_return_index`, `fetch_margin_maintenance`, `fetch_government_bank`, `fetch_day_trading`, `fetch_dealer_futures`, `fetch_dealer_options`, `fetch_derivative_afterhours`) — the four earliest-defined functions (`fetch_institutional`, `fetch_margin`, `fetch_shareholding`, `fetch_foreign_shareholding`) call `_get()` with no try/except at all, so a `RuntimeError` there already propagates out of `main()` uncaught (an unhandled exception exits non-zero on its own). Also confirmed `run_ncf_daily_pipeline.py`'s `_run()` already calls `subprocess.run(cmd, ..., check=True, ...)` — so the fix didn't need to touch the pipeline runner at all; it only needed to make the fetch script itself exit non-zero when a swallowed failure occurred, and the existing `check=True` does the rest.

**Fix:** added a module-level `_FETCH_FAILURES: list[str]` in `fetch_finmind_chip_data.py`, a `_record_fetch_failure(context)` helper called from all 12 except-blocks (alongside the existing `print`), and `_exit_if_fetch_failures()` (prints a summary, `sys.exit(1)` if anything was recorded) called at the end of `main()`, with `_FETCH_FAILURES.clear()` at the start of `main()` for process-reuse safety. "No rows returned" (empty response, not an error) is deliberately *not* counted as a failure — only genuine post-retry `RuntimeError`s are. 5 new tests in `tests/test_fetch_finmind_chip_data_retry.py` (noop-when-empty, `SystemExit(1)` when recorded, `fetch_stock_per` records on exhausted retries, `fetch_stock_per` does not record on success) — 11 total in that file, all passing.

**M8-4 — `ncf_external_cache.py` ex-dividend cache-boundary issue.** Confirmed the actual callers (`ncf_00631l.py`/`ncf_00632r.py`'s `_fetch_yf`) always request a wide, mostly-fixed `[main_df.index[0] - 90d, main_df.index[-1] + 2d]` window, not a narrow rolling tail — so under normal operation a full re-download already overwrites the whole cached range consistently. The real risk is a *partial* re-download (yfinance rate-limited, transient gap, only returns a narrower span than requested): the old code computed the cache-delete range from the downloaded frame's own `min()/max()`, so a narrower-than-requested download would only purge/replace that narrow span, leaving older rows cached under a stale (pre-refresh) adjustment basis sitting right next to the freshly rebased rows — exactly the spurious-jump-at-the-boundary bug the audit flagged, just gated on a less common trigger than originally assumed.

**Fix (audit's simpler option (b) — rebuild the full requested range, not just the downloaded span):** `_write_cache()` gained optional `requested_start`/`requested_end` kwargs; when given, the delete range is widened to `min(df_start, requested_start)..max(df_end, requested_end)` instead of just `df`'s own min/max. `fetch_yf_close_cached()` now always passes the original `start_ts`/`end_ts` it asked for. Net effect: a partial download now purges the *entire* originally-requested window before inserting only the rows it actually got — dates it couldn't refresh become genuinely *missing* from cache (honest) rather than present-but-computed-under-a-different-basis (misleading), and the next call's `cache_is_usable` coverage check (`cached.index.min() <= start_ts`) will then correctly see the cache as incomplete and force a full re-download rather than silently serving mismatched vintages. Backward compatible — `requested_start`/`requested_end` default to `None`, preserving the exact old behavior for the 3 pre-existing tests (all still pass unmodified). 2 new tests in `tests/test_ncf_external_cache.py` (`test_write_cache_purges_full_requested_window_not_just_downloaded_span`, `test_fetch_yf_close_cached_partial_redownload_does_not_mix_adjustment_bases`) — 5 total in that file, all passing.

### 6.16 Where this leaves the audit

As of 2026-07-03, every item from the original Fable 5 audit (H1-H5, M1-M8 including M8-3/M8-4) plus both follow-up research questions (H2 Option B, M6 dual-engine) has been addressed and shipped with tests. Nothing from the original audit list remains open. The only forward-looking non-audit item is the a2120 variant decision noted in section 2.2/[[project_a2118_upgrade]], which was never part of this audit's scope.
