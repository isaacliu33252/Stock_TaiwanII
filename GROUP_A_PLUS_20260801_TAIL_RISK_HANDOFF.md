# GroupA+ 2026-08-01 Session Handoff: Tail-Risk Paper Review, risk_mechanism_classifier, Significance Testing

**Scope note**: this document covers only what this session did (2026-08-01, continuing into 2026-08-02).
The working tree also has a large amount of unrelated uncommitted content (fubon dashboard,
model registry, rebalance CLI, `docs/`, `handoff/`, `research/`, `experiments/`, `archive/`,
`outputs/`, etc.) from other work that this session did not touch and does not describe.
Everything below is **uncommitted** (explicit user instruction this session: "不用commit").

## What triggered this session

User provided `C:\Users\isaac\Downloads\2607.16450v1.pdf` ("Portfolio Optimization under Heavy
Tails and Asymmetric Volatility: Evidence from Taiwan-Exposed ETFs", Lee/Shirvani/Rachev/Fabozzi,
2026-07-21) and asked whether its findings had advantages worth importing into GroupA+. This
branched into several sub-threads, listed in the order they were worked.

## Part 1 — Implemented and kept (all diagnostic-only, none gate/change target_weights)

### 1a. `group_a_plus/integrations/risk_mechanism_classifier.py` (new)
Splits GroupA+'s risk diagnosis into `NORMAL` / `FAST_CRASH` / `PERSISTENT_DRAWDOWN` / `RECOVERY`,
motivated by the user's own proposal (fast-crash vs. persistent-drawdown need different responses;
a single `total_risk_score` conflates them — see `project_spo_paper_robustness_checklist_item7_20260726`
for the prior evidence that `total_risk_score`'s >=9 threshold is fragile).

- Reuses existing infra, does not re-derive features: FAST_CRASH = `market_state.py`'s existing
  `crash_risk` state OR `scripts/run/build_00631l_crash_risk_alert.py`'s 2-of-3 cross-asset stress
  score (SOXX/skew/margin/USD-TWD — already covers the user's proposed crash-feature list).
- PERSISTENT_DRAWDOWN requires >=5 consecutive trading days in a drawdown-type `market_state`
  bucket (`bear_breakdown`/`choppy_range_high_risk`/`bull_pullback_deep`) before confirming, to
  avoid racing FAST_CRASH.
- `append_risk_mechanism_shadow_log()` — idempotent-per-date JSONL log at
  `results/risk_mechanism_shadow_log.jsonl`, same pattern as `market_state.py`'s shadow log.
- Wired into `scripts/run/run_ncf_daily_pipeline.py` (new best-effort step after crash-risk-alert),
  reading same-day `live_signal.json` (note: nested under `OutputStandardizer`'s `data` key — this
  tripped up the first implementation attempt) and same-day `crash_risk_alert.json`, with an
  explicit freshness guard (only trusts `crash_risk_alert.json` if its `as_of` matches today's
  `actual_data_date` — same staleness-masking bug class already fixed elsewhere in ops_health).
  Writes `report/group_a_plus/latest/risk_mechanism.json`.
- 11 new tests (`tests/test_group_a_plus_risk_mechanism_classifier.py`), full suite re-run
  afterward: 1573 passed / 9 skipped / 0 failed.
- Detail: `project_risk_mechanism_classifier_20260801.md`

### 1b. `promotion_utility` in `group_a_plus/governance/compare.py`
Adds a tail-risk-aware advisory score alongside (never replacing) the existing
final_value/Sharpe/MDD promotion gate (`compare_candidates()`).

- Formula (per user's original proposal): `final_value_delta + lambda_starr*starr_delta -
  lambda_es*max(0, expected_shortfall_delta) - transaction_cost_delta`.
- Reads optional fields from candidate `metrics` dicts: `starr_95`, `expected_shortfall_loss_95`,
  `rachev_95_95`, `worst_5d_return`, `worst_10d_return` (no current producer script — pure
  placeholder key), `max_drawdown_duration`, `recovery_duration`, `transaction_cost`. A repo-wide
  search (background agent) found ES/STARR/Rachev/worst_5d already computed by
  `scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py` and
  `evaluate_a2118_h20_tail_score_shadow.py`, but never fed into any candidate's `metrics` dict —
  so `promotion_utility` is forward-looking infrastructure, not something already influencing real
  candidates today.
- **`--tail-risk-lambda-starr`/`--tail-risk-lambda-es` default to `0.0`** — no-op until explicitly
  calibrated (same posture as `w6_credit`, `--use-calibration-model` elsewhere in this repo).
  Confirmed on real production data (`group_a_plus_runner_a207_datahygiene_recent_20260620.json` vs
  `group_a_plus_warmup_consistency_recent_20260620.json`): `promotion_utility == delta_final`,
  `formal_upgrade_pass_count` unchanged.
- 8 new tests (`tests/test_group_a_plus_governance_compare_promotion_utility.py`).
- Detail: `project_promotion_utility_tail_risk_20260801.md`

### 1c. `calculate_recovery_duration()` in `backtesting/performance_metrics.py`
The one metric from the user's list with zero prior implementation anywhere in the repo
(drawdown-trough → new-high day count; `None` if never recovered within the series). Wired into
`calculate_all_metrics()`'s output dict as `recovery_duration`. 4 new tests
(`tests/test_performance_metrics_recovery_duration.py`).

### 1d. `group_a_plus/governance/significance.py` (new)
`jobson_korkie_memmel_test()` (paired Sharpe-difference z-test) and `bootstrap_final_value_ci()`
(paired moving-block bootstrap CI on final-value ratio). Directly answers the paper's own stated
Limitation #1 ("Jobson-Korkie or Memmel-type tests, or bootstrap confidence intervals" would be
needed to make its rolling-window rankings rigorous) — `compare.py`'s gate has the identical gap
(simple point-estimate thresholds, no significance test). **Not wired into `compare_candidates()`'s
gate** — standalone utility, same "observe before wire" posture as `promotion_utility`.
7 new tests (`tests/test_group_a_plus_governance_significance.py`).
Detail: `project_gjr_garch_and_significance_testing_20260801.md`

## Part 2 — Research lines run to completion and rejected/closed

### 2a. Regime-conditional overlay (risk_mechanism_classifier → CVaR-tangency allocation switch)
Hypothesis: gate `evaluate_cvar_tail_risk_diagnostic_shadow.py`'s `dynamic_tangency_cvar` allocation
behind `risk_mechanism_classifier`'s FAST_CRASH/PERSISTENT_DRAWDOWN state, to get crisis protection
without the bull-market drag pure `tangency_cvar` showed in an initial 4-window OOS check.
**Rejected** — new script `scripts/misc/risk_mechanism_regime_overlay_backtest.py` (real 0050/00631L
prices, 2016-09~2026-07-27, no lookahead) shows the overlay does *worse* than plain golden1 in
2018 and 2022 (whipsaw: switching only on the handful of acute FAST_CRASH days catches neither
regime's benefit cleanly), and `PERSISTENT_DRAWDOWN` never fired in any of the 4 test windows
(structurally unreachable with `execution_regime` pinned to `golden1` and `total_risk_score`
pinned at 0 due to missing historical chip data — a backtest-environment limitation, not
necessarily true live). Detail: `project_risk_mechanism_regime_overlay_rejected_20260801.md`

### 2b. GJR-GARCH asymmetry — in-sample significant, OOS useless
`scripts/misc/gjr_garch_asymmetry_test.py` (hand-rolled Gaussian QMLE, no `arch` package installed;
multi-start-verified non-local-optimum) found 00631L.TW has a highly significant leverage effect
(gamma=0.178, LR test p<0.0001) while 0050.TW does not (p=0.462) — this **corrected an earlier
wrong claim in this same session** that `garch_regime_shadow.py` already covered asymmetric GARCH;
it's actually a hand-rolled *symmetric* GARCH(1,1) proxy.
Follow-up OOS validation (`scripts/misc/gjr_garch_oos_forecast_quality_00631l.py`, rolling
21-day-refit / 504-day-window QLIKE + Diebold-Mariano test, reusing this repo's existing
`group_a_plus/integrations/risk_sensitive_loss.py` — same methodology used for GNHAR per
arXiv:2606.03828): overall QLIKE improvement is borderline (p=0.074, not significant at 5%), and
on the top-10%-realized-variance days specifically (the ones that matter for crash detection),
there is **no difference at all** (p=0.968). **Not recommended to wire into
`garch_regime_shadow.py`.** Detail: `project_gjr_garch_oos_rejected_20260801.md`

### 2c. 2020 switch-rule-fix reproducibility check — root-caused, corrected once
Used `significance.py` to retroactively check the one candidate actually promoted to production
(`project_2020_switch_rule_fix_promotion_ready_20260706`, live in `group_a_plus/runners/a2118.py`
since 2026-07-06). First attempt found the reproduction didn't match the original numbers at all
(`momentum_fast_exit` fired 0 times vs. the original's headline mechanism) and initially concluded
this was DB data drift — **this was wrong** and was corrected in the same session: checking
`institutional_data`/`margin_data`/`market_margin_data`'s `updated_at` columns showed zero rows in
the 2015-2020 range were touched after 2026-07-06. The real cause: `git diff` between the 07-03 and
07-16 snapshot commits shows `backtest_group_a_plus_switch_policy.py`'s `_load_chip_features()` was
substantially rewritten (219 insertions/11 deletions) in that window — a code-evolution gap, not a
data-integrity gap. No point-in-time DB snapshot infrastructure is needed; what doesn't exist (and
isn't easily fixable given this repo's coarse "full project state" commit granularity) is a way to
pin the exact code state a past decision was made under.
Scripts: `scripts/misc/significance_check_2020_switch_rule_fix_20260801.py`.
Detail: `project_2020_switch_rule_reproducibility_root_cause_20260801.md` (supersedes the earlier,
now-corrected `project_2020_switch_rule_reproducibility_gap_20260801.md`).

## Part 3 — Self-corrections made mid-session (worth knowing about explicitly)

1. Claimed `garch_regime_shadow.py` already matched the paper's asymmetric-GARCH recommendation —
   **wrong**, corrected in 2b above.
2. Reported "`dynamic_tangency_cvar` cleanly beat golden1 in all 3 independent crisis windows
   (2018/2020/2022)" based on `compare.py`'s point-estimate gate — **applying
   `jobson_korkie_memmel_test`/`bootstrap_final_value_ci` to the same data showed only the 2022
   result is actually statistically significant; 2018 and 2020 were within noise.** The bull-market
   *loss* turned out to be the most statistically solid finding of the whole exercise. This is
   recorded in `project_gjr_garch_and_significance_testing_20260801.md`.
3. Speculated the 2020 reproducibility gap was DB data revision — corrected in 2c above.

## Part 4 — Independent thread: golden1_0531 vs a2118 8/3 prediction

Not related to the paper review. User asked for a $1M hypothetical prediction for 2026-08-03 using
both golden1_0531 and the latest production strategy (a2118). Done safely (production
`execution_plan.json` MD5 confirmed unchanged before/after). Result: a **genuine model
disagreement**, not a data-freshness artifact this time (all 13 a2118 data-source freshness checks
were "ok") — golden1_0531's PVA overlay is in a defensive M-state (0050 35.9%/00631L 7%/00632R
27.1%/cash 30%), while a2118 is in `group_a_plus_recovery` (bullish, 0050 ~70%). **Still an open
decision** — user has not said which to act on. Detail:
`project_golden1_0531_a2118_20260803_predict_divergence_20260801.md`. Saved artifacts:
`results/signal_group_a_20260801_203956.json` (golden1_0531),
`results/group_a_plus_a2118_predict_20260803_1m.json` (a2118, non-production copy).

## Files created/modified this session (only these — see scope note above)

New:
- `group_a_plus/integrations/risk_mechanism_classifier.py`
- `group_a_plus/governance/significance.py`
- `scripts/misc/risk_mechanism_regime_overlay_backtest.py`
- `scripts/misc/gjr_garch_asymmetry_test.py`
- `scripts/misc/gjr_garch_oos_forecast_quality_00631l.py`
- `scripts/misc/significance_check_2020_switch_rule_fix_20260801.py`
- `tests/test_group_a_plus_risk_mechanism_classifier.py`
- `tests/test_group_a_plus_governance_compare_promotion_utility.py`
- `tests/test_performance_metrics_recovery_duration.py`
- `tests/test_group_a_plus_governance_significance.py`
- This file.

Modified:
- `group_a_plus/governance/compare.py` (promotion_utility)
- `backtesting/performance_metrics.py` (calculate_recovery_duration)
- `scripts/run/run_ncf_daily_pipeline.py` (risk-mechanism-classifier pipeline step)

Result artifacts (not production-critical, all in `results/`):
`risk_mechanism_regime_overlay_backtest_20260801.json`, `gjr_garch_asymmetry_test_20260801.json`,
`gjr_garch_oos_forecast_quality_00631l_20260801.json`,
`significance_check_2020_switch_rule_fix_20260801.json`,
`group_a_plus_a2118_predict_20260803_1m.json`, `signal_group_a_20260801_203956.{json,csv}`.

Also (side effect of validating the pipeline wiring against real data):
`report/group_a_plus/latest/risk_mechanism.json` exists on disk (as_of 2026-07-27) — diagnostic
output only, not read by any weight-computing code path.

## Test status

38 tests directly added/touched this session, all passing. Full-suite re-run after the
risk_mechanism_classifier work: 1573 passed / 9 skipped / 0 failed (37m56s). Not re-run after the
later additions (significance.py, GJR-GARCH scripts) — those don't touch any code path the full
suite exercises beyond what the 38 targeted tests already cover directly.

## Open items / suggested next steps

1. **golden1_0531 vs a2118 8/3 decision** — still pending, see Part 4.
2. `promotion_utility`'s lambdas are inert until some evaluate/backtest script actually populates
   `starr_95`/`expected_shortfall_loss_95` into a candidate's `metrics` dict — no such producer
   exists yet.
3. `worst_10d_return` — key defined in `compare.py`'s optional schema, no producer anywhere.
4. If GroupA+ ever wants to re-audit a past promotion decision from git history, be aware this
   repo's coarse snapshot-commit granularity makes pinning "the exact code as of decision day" hard
   in general, not just for the 2020 case checked here.
5. Nothing here is committed. All additions are default-inert (lambdas at 0.0, new pipeline step is
   best-effort/non-fatal, no gate logic changed) — safe to leave as-is indefinitely if not picked
   back up.
