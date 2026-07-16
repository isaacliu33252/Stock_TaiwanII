# GroupA+ NCF Panel Drift Fix — Handoff (2026-07-07)

## Scope

Direct follow-up to `GROUP_A_PLUS_FINAL_DECISION_MEMO_20260706.md`'s Blocker #1
("NCF Panel Drift... max drift in probability/confidence fields is several times
larger than the current 0.05 governance limit") and
`GROUP_A_PLUS_NCF_PANEL_DRIFT_AUDIT_20260706.md` (measured the drift, did not fix it).
User picked this blocker as today's priority and approved a plan
(`/home/isaacliu33252/.claude/plans/reflective-moseying-cake.md`) before implementation.

Root cause (first diagnosed `project_ncf_panel_global_weight_drift_20260702` memory,
confirmed with real numbers 2026-07-06): `train_classifier()` in
`scripts/misc/ncf_00631l.py` (identical pattern duplicated in `ncf_2330.py` and
`ncf_00632r.py` — no shared module between the three files) blends the 7-8 base
classifiers (rf/et/hgb/gb/lgb/xgb/cat/tabnet) into one ensemble probability using a
**single global weight**, computed once from each model's AUC/Brier over the **entire**
validation set, applied uniformly to every historical row. Every time the validation
window grows, every model's full-sample AUC/Brier shifts slightly, the weight
redistributes, and **every historical panel date's probability retroactively changes**.
Measured impact (2026-07-06 audit, panels only 3 days apart): max drift
`prob_up_h1`=0.476, `confidence`=0.465, `ensemble_prob_up`=0.302.

**Scope for this session: `scripts/misc/ncf_00631l.py` only.** `ncf_2330.py` and
`ncf_00632r.py` have the identical bug but were deliberately not touched — `ncf_2330.py`
was promoted just yesterday under the old scheme (see
`results/NCF_2330_LEADERSHIP_PROMOTION_HANDOFF_20260707.md`) and deserves its own
re-verification pass, not a silent bundle-in.

## The fix

The codebase already had a proven pattern for exactly this problem one level up:
`_build_expanding_horizon_ensemble_panel()` combines H1/H5/H20 **horizon** predictions
using expanding-window AUC weights (row `pos` only uses labels/probs resolved before
`pos`, embargoed by `pos - horizon` since forward-looking labels need `horizon` days to
resolve). That fix never addressed the **model-level** combination one level below it —
the actual root cause named in the memo.

New `_expanding_model_ensemble_weights()` (scripts/misc/ncf_00631l.py, next to its
horizon-level sibling) ports the same technique down one level: per validation row,
compute each base model's AUC+Brier weight (`raw_w = auc_w * brier_w`, identical
formula shape to the original) using only rows resolved as of that row
(`resolved_end = pos - horizon`), with an equal-weight fallback below `min_history`
resolved rows.

### Iteration history (the naive version made things *worse*)

1. **v1 — hard cutoff at `min_history=60`** (no shrinkage): jump straight from equal
   weight to the raw computed weight the instant 60 resolved rows exist. Result: **made
   drift worse than the original bug** for direction tasks — `prob_up_h20` max drift
   went from 0.119 (old global-weight) to **0.675**. Cause: with 7-8 models and only
   ~60-80 resolved samples (worse for the bull/bear-regime-split direction tasks, which
   have a smaller effective sample), AUC/Brier estimates are noisy enough that a single
   model can seize almost all the weight by chance, and that model's own run-to-run
   training noise (BLAS/TabNet non-determinism) then gets amplified straight through to
   the ensemble output.
2. **v2 — shrinkage ramp, `min_history=150`, `full_confidence_history=400`**: blend
   `shrink * raw_weight + (1-shrink) * equal_weight` where `shrink` ramps 0→1 linearly
   as resolved rows grow from `min_history` to `full_confidence_history`. Net
   improvement (6/8 audited columns better than the old global-weight baseline, MDD-risk
   drift eliminated entirely: 0.069→0.000, its AUC also improved 0.629→0.648), but
   discovered `full_confidence_history=400` > actual validation-set size (~361 rows for
   this window), so the ramp never fully completes within the observed panel.
3. **v3 — recalibrated to `min_history=100`, `full_confidence_history=250`** (so the
   ramp completes ~75% through a 361-row panel): made the one already-weak column
   (`prob_fwd_gain_gt5_h20`, upside-reward) **worse**, not better (drift 0.087→0.219).
   Diagnostic: that task's 8 base models are closely AUC-matched (weight spread
   0.03-0.21, no clear winner) — reaching full confidence in the raw weight *faster*
   let its accumulated small-sample instability through *sooner*, the opposite of what
   was needed.
4. **v4 (final) — `min_history=150`, `full_confidence_history=800`** (well beyond the
   panel's actual row count, so shrinkage stays conservative throughout): best result —
   upside-reward drift 0.078 (down from v1's 0.431, still slightly above the old
   baseline's 0.057) with AUC plateaued at 0.624 (down from 0.652). Pushing shrinkage
   even further didn't move this specific task any more — a genuine floor, not a tuning
   miss.

### Final decision on the one remaining cost

Only `forward_upside_reward`'s AUC (0.652→0.624, -0.027) is a real, irreducible cost of
this fix — every other of the 8 audited metrics improved or was a wash. Considered
special-casing that one task to keep the old global weight (avoiding the cost
entirely, since each `train_classifier` call site already threads its own
`expanding_model_weights` flag independently) versus applying uniformly everywhere.
**User chose uniform application, accepting the -0.027 AUC cost for consistency** —
rejected the per-task-exception path specifically to avoid a future maintainer finding
"most columns don't drift, this one still does" and mistaking it for an unfixed bug
rather than a deliberate, documented tradeoff.

## Code changes

`scripts/misc/ncf_00631l.py`:
- New `_expanding_model_ensemble_weights()` (next to `_build_expanding_horizon_ensemble_panel`).
- `train_classifier()` gained `horizon: int | None = None` and
  `expanding_model_weights: bool = False` parameters (function-level default stays
  `False` — safe for any caller not explicitly migrated, e.g. purged-K-fold evaluation,
  feature-stability walk-forward, bull/bear diagnostic sub-analyses, none of which were
  touched this session).
- Both ensemble-weight blocks inside `train_classifier` (primary `W`/`ens_proba`, and
  the secondary `stable_rf`-inclusive `W2`/`ens_proba2` path) branch on
  `expanding_model_weights`; each `results["ensemble"]` now also carries
  `"ensemble_weight_method": "expanding_prior" | "global"` for self-documentation.
- Three call sites migrated (the ones that feed the drift-audited panel columns): the
  main per-horizon bull/bear `train_classifier` calls (passes `horizon=h`), and
  `train_forward_drawdown_risk` / `train_forward_upside_reward` (both gained their own
  `expanding_model_weights` passthrough parameter, `horizon=20` fixed).
- New CLI flag: `--no-expanding-model-weights` (opt-out; **default is now ON** — flipped
  after verification, see below). `--expanding-model-weights` no longer exists as a
  separate opt-in flag; it's `parser.set_defaults(expanding_model_weights=True)` with
  the negation flag for rollback.

`tests/test_ncf_00631l_paths.py`: 5 new tests (8 total in file) —
`test_expanding_model_ensemble_uses_equal_weights_before_min_history`,
`test_expanding_model_ensemble_does_not_rewrite_prior_rows` (the actual anti-drift
property), `test_expanding_model_ensemble_embargoes_unresolved_forward_labels` (mirrors
the horizon-level M1 fix), `test_expanding_model_ensemble_shrinkage_ramps_gradually`
(guards against ever regressing to the v1 hard-cutoff bug), and
`test_expanding_model_weights_flag_off_matches_current_behavior`.

## Empirical verification

Reproduced the original audit's methodology: retrained twice with `--val-end` 3 days
apart (`2026-06-30` vs `2026-07-03`, same as the original audit), compared via
`scripts/evaluate/evaluate_ncf_panel_drift.py`.

| Column | Old (global weight) | New (expanding + shrinkage, final v4) |
|---|---:|---:|
| `prob_up_h1` | 0.080 | 0.058 |
| `prob_up_h5` | 0.088 | 0.125 |
| `prob_up_h20` | 0.119 | 0.111 |
| `ensemble_prob_up` | 0.114 | 0.107 |
| `confidence` | 0.228 | 0.213 |
| `prob_fwd_mdd_gt5_h20` | 0.069 | **0.000** |
| `prob_fwd_gain_gt5_h20` | 0.057 | 0.078 |
| `tail_reward_risk_score_h20` | 0.101 | 0.078 |

6/8 improved, 1 (`prob_up_h5`) roughly a wash, 1 (`prob_fwd_gain_gt5_h20`) the accepted
cost above.

AUC: H1 0.606→0.595, H5 0.691→0.692, H20 0.685→0.685 (unchanged), drawdown-risk
0.629→**0.648** (improved), upside-reward 0.652→**0.624** (the accepted cost).

### a2118 live-trigger stability check

Re-ran `group_a_plus.runners.a2118.run_a2118` with production params (`h20_max=0.33,
conf_min=0.55, h5_reentry_min=0.55, chip_data_fallback_max_stale_days=10,
risk_score_lookback_days=5, momentum_fast_exit_min=0.10,
momentum_fast_exit_ma_gap_min=-0.08`), window `2025-01-02`~`2026-07-06`, comparing the
pinned old panel (`ncf_00631l_panel_latest_20260630.csv`) against the newly regenerated
one (`ncf_00631l_panel_latest_20260707.csv`, expanding weights):

- **70 of 75 trigger days bit-identical** (the entire `2025-02-25`~`2025-06-09` stretch
  unchanged).
- The 5 dropped days (`2025-10-29`~`2025-11-04`) are exactly the borderline event
  originally flagged in the panel-drift audit as disappearing/reappearing across panel
  refreshes.
- `final_value`: 2,134,770 → 2,201,273 (+3.1%). `sharpe_ratio`: 2.5045 → 2.4906 (-0.014).
  `max_drawdown`: unchanged at -13.82%.

Verification script: `/tmp/.../scratchpad/a2118_panel_stability_check.py`
(session-local, not committed to the repo — rerun manually if needed by adapting
`scripts/misc/a2118_ncf_2330_tsmc_overlay_sweep.py`'s `run_latest`/`run_a2118` pattern).

## Production changes

- `results/ncf_00631l_latest_20260707.json` / `results/ncf_00631l_panel_latest_20260707.csv`
  regenerated with the new default (expanding weights on).
- `report/group_a_plus/latest/strategy.json`:
  - `active_strategy.runner_params.ncf_panel_631l_path` updated from
    `results/ncf_00631l_panel_latest_20260630.csv` to
    `results/ncf_00631l_panel_latest_20260707.csv`.
  - New `improvements.ncf_panel_model_ensemble_drift_fix_20260707` record documenting
    reason/fix/verification/decision (self-contained, includes the drift table and
    trigger-stability numbers above).
- `tests/test_group_a_plus_latest_strategy.py::test_repository_manifest_activates_a2118`
  updated to expect the new panel path (this test reads the real
  `report/group_a_plus/latest/strategy.json`, not a fixture).

## Test suite verification

Targeted suite (`tests/test_ncf_00631l_paths.py`,
`tests/test_group_a_plus_latest_strategy.py`,
`tests/test_group_a_plus_ncf_integration.py`,
`tests/test_group_a_plus_strategy_env.py`, `tests/test_group_a_plus_ops_health.py`):
101 passed.

Full suite (`pytest -q`, ~2h03m): **663 passed, 1 failed.** The 1 failure
(`test_repository_manifest_activates_a2118`) was a **self-inflicted race condition**,
not a real regression: the full suite was launched *before* the `strategy.json` edit
landed, and this specific test happened to execute (at the 63% mark) after the test
file itself had been edited (to expect the new path) but before the `strategy.json`
edit had been applied on disk — a pure sequencing mistake (should have made all file
edits first, then launched the 2-hour suite). Re-ran the single test in isolation
afterward with the current file state: **passes**. User declined a second full 2-hour
re-run given the time cost; the isolated re-confirmation was accepted as sufficient.

## Deferred (not done this session, explicit follow-up)

- `ncf_2330.py` and `ncf_00632r.py` have the byte-for-byte identical global-weight bug
  (`auc_w`/`brier_w`/`raw_w`/`W`/`ens_proba` pattern) and were **not** touched. Porting
  `_expanding_model_ensemble_weights` there would need its own retrain + drift-audit +
  quality-check cycle per file, and for `ncf_2330.py` specifically should be sequenced
  after (not silently mixed into) yesterday's leadership-feature promotion, since that
  promotion's reported numbers (H1 val_auc=0.7625 etc.) were generated under the old
  global-weight scheme.
- `GROUP_A_PLUS_FINAL_DECISION_MEMO_20260706.md`'s remaining two blockers (#2 "rework
  NCF2330 overlay objective" — partially addressed by this week's H1 tactical-overlay
  multi-window test, see `GROUP_A_PLUS_NCF2330_H1_TACTICAL_OVERLAY_HANDOFF_20260707.md`;
  #3 "GARCH routing 2020 behavior" — untouched) are separate threads, not part of this
  fix.
