#!/usr/bin/env python3
"""Run the daily NCF refresh, signal, and advisory-panel pipeline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from group_a_plus.governance.latest import resolve_ncf_00631l_panel_path  # noqa: E402
from group_a_plus.outputs import output_path, write_json_report  # noqa: E402
from tw_output_standard import backup_latest_pointer_before_overwrite  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "results"
DB_PATH = PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
DEFAULT_PROMOTION_BASELINE = "results/a2118_ncf_2330_tsmc_overlay_sweep_20260704.json"
DEFAULT_PROMOTION_CANDIDATES = (DEFAULT_PROMOTION_BASELINE,)
PROTECTED_GOLDEN1_RELEASE_ARTIFACTS = frozenset(
    {
        PROJECT_ROOT / "GROUP_A_GOLDEN1_0531_RELEASE.md",
        PROJECT_ROOT / "results" / "group_a_release_Golden1_0531.json",
        PROJECT_ROOT / "models" / "portfolio" / "group_a_oos_2020_2024_cap20_llm_pva_tripletv4_inst_localregime_20260526.zip",
        PROJECT_ROOT / "results" / "group_a_backtest_20250101_20260525_20260526_193252.json",
        PROJECT_ROOT / "results" / "group_a_combined_live_latest.json",
        PROJECT_ROOT / "results" / "group_a_combined_live_latest.csv",
        PROJECT_ROOT / "results" / "group_a_combined_bundle_latest.json",
        PROJECT_ROOT / "Group_A_history.xlsx",
    }
)
PROTECTED_GOLDEN2_RELEASE_ARTIFACTS = frozenset(
    {
        PROJECT_ROOT / "GROUP_A_PLUS_GOLDEN2_0830_RELEASE.md",
        PROJECT_ROOT / "results" / "group_a_plus_release_golden2_0830.json",
        PROJECT_ROOT / "releases" / "golden2_0830" / "group_a_plus_strategy_golden2_0830.json",
        PROJECT_ROOT / "releases" / "golden2_0830" / "group_a_plus_live_signal_golden2_0830_20260831.json",
        PROJECT_ROOT / "results" / "golden2_0830" / "group_a_combined_live_golden2_0830.json",
        PROJECT_ROOT / "results" / "golden2_0830" / "group_a_combined_live_golden2_0830.csv",
        PROJECT_ROOT / "results" / "golden2_0830" / "group_a_combined_bundle_golden2_0830.json",
        PROJECT_ROOT / "results" / "golden2_0830" / "signal_group_a_golden2_0830_20260831.json",
        PROJECT_ROOT / "results" / "golden2_0830" / "signal_group_a_golden2_0830_20260831.csv",
        PROJECT_ROOT
        / "results"
        / "golden2_0830"
        / "group_a_plus_live_signal_v2_golden2_0830_20260831_total_1m.json",
        PROJECT_ROOT / "models" / "portfolio" / "golden2_0830" / "last_ppo_group_a_100k_golden2_0830.zip",
        PROJECT_ROOT / "results" / "golden2_0830" / "last_ppo_group_a_backtest_golden2_0830.json",
        PROJECT_ROOT / "results" / "golden2_0830" / "ncf_0050_golden2_0830.json",
        PROJECT_ROOT / "results" / "golden2_0830" / "ncf_0050_panel_golden2_0830.csv",
        PROJECT_ROOT / "results" / "golden2_0830" / "ncf_00631l_golden2_0830.json",
        PROJECT_ROOT / "results" / "golden2_0830" / "ncf_00631l_panel_golden2_0830.csv",
        PROJECT_ROOT / "results" / "golden2_0830" / "ncf_00632r_golden2_0830.json",
        PROJECT_ROOT / "results" / "golden2_0830" / "ncf_00632r_panel_golden2_0830.csv",
        PROJECT_ROOT / "results" / "golden2_0830" / "ncf_2330_golden2_0830.json",
        PROJECT_ROOT / "results" / "golden2_0830" / "ncf_2330_panel_golden2_0830.csv",
        PROJECT_ROOT / "results" / "golden2_0830" / "ncf_advisory_panel_golden2_0830.csv",
        PROJECT_ROOT / "results" / "golden2_0830" / "ncf_panel_manifest_golden2_0830.json",
    }
)
PROTECTED_GOLDEN_RELEASE_ARTIFACTS = (
    PROTECTED_GOLDEN1_RELEASE_ARTIFACTS | PROTECTED_GOLDEN2_RELEASE_ARTIFACTS
)
OUTPUT_TARGET_FLAGS = frozenset(
    {
        "--output",
        "--output-json",
        "--output-md",
        "--output-prefix",
        "--latest",
        "--latest-pointer",
        "--csv",
        "--log",
        "--history-dir",
        "--manifest-output",
        "--val-predictions-output",
    }
)
# Fallback only -- Fable audit (2026-07-08, #4): this used to be the sole,
# hardcoded baseline for the daily drift audit, which meant the audit kept
# comparing against a week-stale snapshot after strategy.json moved on. The
# --active-ncf-00631l-panel CLI default now resolves the live value via
# resolve_ncf_00631l_panel_path(); this constant only applies when
# strategy.json is missing or doesn't have that field yet.
DEFAULT_ACTIVE_NCF_00631L_PANEL = "results/ncf_00631l_panel_latest_20260630.csv"
DEFAULT_PROMOTION_MULTI_WINDOW_GATE = "results/group_a_plus_multi_window_gate_20260706.json"
# Fable audit (2026-07-08, #2): main()'s command loop had no try/except, so
# a transient failure in any one step (most often these network-dependent
# refresh calls) propagated straight out of main() uncaught -- NCF models,
# daily_signal, alert_state, and the push notification never ran, and
# nothing about the failure was recorded (collect_pipeline_health only
# checked whether *a* manifest existed, not whether today's had been
# written). These steps are best-effort: log and continue past their
# failure, since the NCF/signal steps below can still run against
# already-fetched or cached data. Steps not in this set are critical --
# a failure there halts the run, writes a partial manifest, and pushes a
# direct notification (see main()).
BEST_EFFORT_STEP_NAMES = frozenset(
    {
        "refresh_group_data",
        "refresh_taifex",
        "refresh_taifex_options",
        "refresh_institutional",
        "refresh_margin",
        "refresh_market_margin",
        "refresh_derivative_institutional",
        "refresh_securities_lending",
        "securities_lending_0050_source_status",
        "refresh_dealer_positions",
        "refresh_foreign_shareholding",
        "refresh_short_sale_balances",
        "refresh_day_trading",
        "refresh_soxx_options_iv",
        "refresh_cross_market_ohlcv",
        "refresh_2330_per",
        "refresh_shareholding",
        "ohlcv_freshness",
        # Pure logging step for scripts/evaluate/evaluate_ncf_blend_live_auc_archive.py
        # (research-only; never changes a live decision). A failure here must
        # never block ncf_2330/daily_signal/alert_state below it.
        "ncf_signal_archive",
        # Diagnostic-only threshold sweep for the 0050 NCF panel. It can
        # recommend shadow gates such as block_new_0050_add, but never changes
        # live target weights.
        "ncf_0050_threshold_eval",
        # Shadow-only decision_confidence governance report. It records that
        # empirical probability calibration is closed_failed_oos and must
        # never block live signal generation.
        "ncf_decision_calibration_shadow",
        # QUESTrader-inspired auxiliary-task readiness review (2608.15841).
        # It audits existing NCF auxiliary heads and records missing
        # policy-impact validation; it never changes live weights.
        "auxiliary_policy_lift_shadow_2608_15841",
        "auxiliary_churn_shadow_2608_15841",
        "auxiliary_purged_walkforward_2608_15841",
        "auxiliary_regime_decay_audit_2608_15841",
        "auxiliary_lifecycle_audit_2608_15841",
        "delayed_credit_audit_2608_15841",
        "candidate_auxiliary_bank_blueprint_2608_15841",
        "auxiliary_task_discovery_readiness_2608_15841",
        # CTBC review (2509.02986, 2026-09-07): robotics/contact-triggered
        # RL ideas are imported only as research-governance validation checks
        # plus debounce/domain-randomization shadows. They never emit target
        # weights, golden changes, NCF live gates, or orders.
        "ctbc_debounce_shadow_2509_02986",
        "ctbc_00713_debounce_shadow_2509_02986",
        "ctbc_00713_domain_randomization_2509_02986",
        "ctbc_promotion_readiness_gate_2509_02986",
        "ctbc_groupa_plusplus_review_2509_02986",
        # TSI stress shadow (2608.10788, 2026-08-22): coincident
        # correlation-network stress monitor, OOS threshold sweep, and
        # 00631L no-add counterfactual. Research-only; it never emits target
        # weights, execution regimes, or live order permissions.
        "tsi_stress_shadow",
        "tsi_stress_oos",
        "tsi_no_add_shadow",
        # 00631L<->0050 relative re-entry opportunity shadow. Research-only
        # observation of whether a small 0050->00631L shift is favorable after
        # permission/reliability/slow-bear gates; never changes live weights.
        "relative_reentry_opportunity_shadow",
        # Daily gate/readiness wrapper for the relative re-entry opportunity
        # shadow. It only writes a human-review report with trust/risk/data
        # blockers and never changes live weights.
        "relative_reentry_advisory_shadow",
        # Candidate-review wrapper for historical relative re-entry rows.
        # It summarizes 5/10/20d realized edges and tail cases for manual
        # review only; it never changes live weights.
        "relative_reentry_candidate_review",
        # Promotion gate for the relative re-entry shadow. It converts the
        # advisory/candidate-review reports into explicit promote/block/warn
        # fields for manual review only; it never changes live weights.
        "relative_reentry_promotion_gate",
        # Governance-only artifact integrity report. It checks stale/missing
        # production-sensitive artifacts and PIT coverage, but it must never
        # change live weights or block daily status generation.
        "daily_artifact_integrity",
        # Riccati/MV risk-budget shadow for arXiv:2608.07977. It reads the
        # already-produced daily signal and only writes diagnostic/cap-only
        # review fields; it must never alter live weights or block the run.
        "riccati_mv_shadow",
        # 2608.17808 current-policy re-evaluation gate. It summarizes the
        # Riccati/MV shadow transfer checks and fixed tail-bank review into an
        # explicit research-only promote/block decision; it never changes live
        # weights, golden artifacts, or execution permissions.
        "current_policy_re_evaluation_gate",
        # External-feature sensitivity shadow artifacts are diagnostics only:
        # they preserve paired no-external/external panels so drift root-cause
        # reviews are reproducible. Missing output is recorded as a blocker by
        # ncf_panel_external_feature_sensitivity_governance; it must not halt
        # live signal generation.
        "ncf_00631l_no_external_shadow",
        "ncf_panel_drift_no_external_vs_external",
        "ncf_panel_refresh_recommendation",
        "dfl_active_date_audit",
        # A21.18 PPO seed averaging (2607.00475 follow-up, 2026-08-24):
        # backtest robustness passed, but live seed-level inference/parity and
        # enough forward rows are still missing. This step only accumulates
        # forward shadow evidence and must never change live weights.
        "a2118_seed_averaging_live_inference_snapshot",
        "a2118_seed_averaging_forward_shadow_monitor",
        "a2118_seed_averaging_promotion_gate",
        "a2118_risk_down_mapped_shadow",
        # 2606.09104 BAVAR/BLED-derived risk-aversion monitors:
        # transparent EXTREME-state and staged 00631L ladder review only.
        # These are shadow/governance artifacts and must never alter live
        # weights or block the daily signal.
        "paper_2606_09104_00631l_regime_split",
        "paper_2606_09104_00631l_staged_ladder_readiness",
        "paper_2606_09104_extreme_state_monitor",
        # Fable audit (2026-07-16, combination opportunities #2): this whole
        # sub-pipeline was previously never scheduled at all, so
        # report/group_a_plus/latest/a2120_letf_compounding_shadow.json and
        # the a2119+a2120 combined-policy shadow were frozen at whatever date
        # someone last ran the script by hand. It writes advisory-only
        # artifacts (research_only=True, production_effect="none"), so a
        # failure here must never block daily_status/promotion_gate below it.
        "a2120_shadow_pipeline",
        # Fable audit (2026-07-16, combination opportunities #4): the
        # spillover-gated recovery boost has never had its gate actually fire
        # in any historical backtest window (recovery regime is rare and
        # never coincided with a spillover spike in-sample), and the 2008/2011
        # crisis folds structurally cannot test it (close-only proxy data,
        # missing basket tickers). Pure logging step -- accumulates real daily
        # observations instead; a failure here must never block anything
        # downstream.
        "recovery_boost_spillover_gate_shadow_log",
        # Fable audit (2026-07-16, combination opportunities #1): the trough+
        # compounding override eligibility union grew historical OOS events
        # from 0 to 3, but 3 is still too few to promote. Pure logging step --
        # accumulates real daily eligibility samples at live speed instead of
        # waiting on more historical proxy data; a failure here must never
        # block anything downstream.
        "trough_override_eligibility_shadow_log",
        # User-proposed TSMC concentration-divergence guard (2026-08-09): the
        # 7/7-window backtest passed but only found 3 trigger events across
        # 6+ years, too sparse to validate. Pure logging step -- accumulates
        # real daily narrow_lead/would-trigger observations instead; a
        # failure here must never block anything downstream.
        "add_0050_instead_shadow_log",
        # User-proposed adaptive review interval (2026-08-09): the 7-window
        # backtest was a genuine mixed result (3 windows had zero suppressed
        # days, i.e. no differentiating evidence). Pure logging step --
        # accumulates real daily 1d/3d/5d classification frequency instead;
        # a failure here must never block anything downstream.
        "adaptive_review_interval_shadow_log",
        # GatedLinear-lite drawdown forecast shadow (2607.09537 follow-up,
        # 2026-08-16): the H=20 forecast showed a small but robust (3/3
        # sub-windows) edge over persistence on a single historical backtest
        # split. Pure logging step -- accumulates real daily forecasts
        # instead of relying on that one split; a failure here must never
        # block anything downstream.
        "gatedlinear_drawdown_forecast_shadow_log",
        # GJR-GARCH asymmetry shadow (2026-08-02): the 2607.16450v1 review
        # found in-sample leverage-effect significance for 00631L, but OOS
        # high-volatility forecast quality did not justify a live rule. Log
        # model-disagreement evidence only; never block daily signal.
        "gjr_garch_shadow",
        # Fable independent review (2026-07-17) of 2607.03082v1: the CVaR/
        # Hill/POT-GPD tail-risk diagnostic evaluator only ever ran as a
        # manual one-off with a hardcoded --end date, so
        # report/group_a_plus/latest/ never had a current snapshot for
        # periodic human review. Pure diagnostic refresh -- research_only,
        # never changes target weights; a failure here must never block
        # anything downstream.
        "cvar_tail_risk_diagnostic",
        # Taiwan-exposed ETF heavy-tail/CVaR review (2607.16450, 2026-08-25):
        # imports paper concepts only as governance/review-layer checks.
        # It never changes target weights or creates orders.
        "taiwan_etf_2607_16450_review",
        # Tail-sensitive scorecard derived from the 2607.16450 review and
        # latest CVaR diagnostic. This ranks review references only; it is
        # never a live allocation engine.
        "taiwan_etf_2607_16450_tail_scorecard",
        # Cost/turnover robustness sweep for the 2607.16450 CVaR optimizer
        # import. It checks whether the dynamic CVaR idea survives realistic
        # cost assumptions; it never changes live weights.
        "taiwan_etf_2607_16450_cost_robustness",
        # Candidate-level tail review for current profit-improvement shadows.
        # It applies the 2607.16450 scorecard/cost conclusions to staged
        # re-entry, A21.18, A21.20, and GJR without changing weights.
        "taiwan_etf_2607_16450_candidate_tail_review",
        # Regime-switching volatility was listed as future research in
        # 2607.16450. These steps keep a daily forecast-quality/gate record
        # only; they never change target weights or execution regimes.
        "taiwan_etf_2607_16450_regime_vol_forecast_quality",
        "taiwan_etf_2607_16450_regime_vol_gate",
        # Dynamic copula/tail dependence was listed as future research in
        # 2607.16450. This empirical co-exceedance proxy is monitoring-only
        # and never adds leverage or changes live weights.
        "taiwan_etf_2607_16450_tail_dependence_monitor",
        # Geopolitical risk conditioning was listed as future research in
        # 2607.16450. This local-news CVaR overlay is monitoring-only and can
        # only add risk caution; it never creates target weights or orders.
        "taiwan_etf_2607_16450_geopolitical_cvar_overlay",
        # The paper notes that ranking differences were not formally tested.
        # This bootstrap gate is statistical promotion governance only; it
        # never creates orders or target-weight changes.
        "taiwan_etf_2607_16450_bootstrap_promotion_gate",
        # Stock/bond/gold dynamic allocation review (2609.07946, 2026-09-10):
        # 00635U instrument readiness plus complementarity forward shadows.
        # These write research artifacts only and never change target weights
        # or orders.
        "paper_2609_07946_00635u_instrument_review",
        "paper_2609_07946_stock_bond_gold_forward_shadow",
        "paper_2609_07946_bond_only_forward_shadow",
        "paper_2609_07946_complementarity_promotion_gate",
        "paper_2609_07946_adoption_matrix",
        # Nyström attention review (2609.08106, 2026-09-10): import only
        # the complementarity insight as a forward-shadow/adoption matrix.
        # It never changes live target weights or creates orders.
        "paper_2609_08106_complementarity_forward_shadow",
        "paper_2609_08106_latest_target_weight_replay",
        "paper_2609_08106_latest_target_weight_param_sweep",
        "paper_2609_08106_adoption_matrix",
        # Order-flow regime review (2609.07989, 2026-09-12): execution
        # advisory only. It requires signed intraday order-flow data and
        # emits status=unavailable when that data is missing; it never uses
        # daily OHLCV proxies, changes live weights, or creates orders.
        "paper_2609_07989_order_flow_regime_shadow",
        # Deep-hedging overlay review (2026-07-17): option-state coverage is
        # a governance/data-readiness check for TXO/SOXX option features.
        # It only writes a latest JSON report and never changes live target
        # weights, so keep it best-effort.
        "option_state_coverage_review",
        # Black Tuesday Attack review (2026-07-17): adversarial market
        # integrity is a pre-trade governance check that treats model outputs
        # and sparse market perturbations as an attack surface. Diagnostic
        # only; never changes target weights.
        "adversarial_market_integrity_review",
        # SciPhyRL review (2026-07-17): target-holding / explicit-cost
        # optimizer readiness checks are governance-only. They depend on the
        # preceding source freshness, option-state, adversarial-integrity, and
        # rebalance gates, and never change target weights.
        "sciphyrl_readiness_review",
        # Market-impact review (2026-07-17): pre-trade turnover and POV
        # readiness check inspired by realistic-impact RL environments.
        # Diagnostic only; never changes target weights.
        "market_impact_readiness_review",
        # FinStressTS review (2026-07-17): mechanism-specific synthetic
        # stress-test readiness check for forecast/model promotion. Diagnostic
        # only; never changes target weights.
        "finstressts_readiness_review",
        # FinStressTS fixed-weight counterfactual shadow (2026-07-17):
        # compares 7/20 reference weights against no-00631L under
        # mechanism-specific stress scenarios. Diagnostic only.
        "finstressts_counterfactual_shadow",
        # FinStressTS baseline comparison shadow (2026-07-17): compares
        # transparent static/dynamic baselines under the same counterfactual
        # scenarios. Diagnostic only.
        "finstressts_baseline_compare_shadow",
        # FinStressTS consolidated daily snapshot (2026-07-17): summarizes the
        # readiness, counterfactual, and baseline-comparison diagnostics.
        # Diagnostic only; never unlocks execution.
        "finstressts_decision_snapshot",
        # Tri-gate volatility-memory shadow (2026-07-17): level/shape/tempo
        # volatility-memory diagnostic inspired by 2512.02166. Diagnostic only.
        "trigate_vol_memory_shadow",
        # Perpetual money machine review (2026-07-18): systemic bubble
        # time-at-risk / ETF-coupling / reflexivity-proxy diagnostic inspired
        # by 1212.2833. Diagnostic only; never changes target weights.
        "systemic_bubble_time_at_risk_review",
        # Illiquidity-network review (2026-07-19): data-readiness check
        # inspired by 2004.01917. Requires high-frequency bid/ask and
        # market-wide failure events before any liquidity-contagion signal can
        # be tested. Diagnostic only.
        "illiquidity_network_readiness_review",
        # Speculative-influence-network review (2026-07-19): data-readiness
        # check inspired by 1510.08162. Requires broad sector/firm universe,
        # HMM bubble-state probabilities, transfer entropy, and max-loss
        # validation before any SIN signal can be tested. Diagnostic only.
        "speculative_influence_network_readiness_review",
        # SIN-lite proxy (2026-07-19): daily-OHLCV weak proxy for correlation,
        # lagged influence, and downside co-movement. Shadow only.
        "sin_lite_proxy",
        # HMM-WJ synthetic scenario readiness (2026-07-18): data and
        # validation-readiness check inspired by 2603.10202. It does not
        # generate paths and never changes target weights.
        "hmm_wj_synthetic_scenario_readiness_review",
        # SCR readiness review (2602.24037, 2026-08-30): scenario-to-real
        # mismatch guard, robustness/window checks, and latest downside stress
        # score for future scenario-conditioned RL governance. Shadow only;
        # never trains SCR-PPO and never changes target weights.
        "scr_readiness_review_2602_24037",
        "scr_readiness_robustness_2602_24037",
        "scr_readiness_window_split_2602_24037",
        "scr_scenario_stress_score_2602_24037",
        # Commodity ETF heavy-tail optimization review (2026-07-18):
        # dynamic CVaR / tail / transaction-cost readiness check inspired by
        # 2606.26625. Research-only; no optimizer and no weight changes.
        "cvar_cost_window_split_2606_26625",
        "rolling_tail_no_add_gate_2606_26625",
        "dynamic_cvar_constraint_shadow_2608_20179",
        "dynamic_cvar_forward_validation_2608_20179",
        "dynamic_cvar_tail_cost_readiness_review",
        # Synthetic augmentation validation review (2026-07-18): validation
        # gate inspired by 2604.14498. It blocks synthetic directional alpha
        # unless size-matched null, walk-forward, and block permutation checks
        # are implemented and passed. Research-only; no weight changes.
        "synthetic_augmentation_validation_audit",
        "synthetic_augmentation_validation_readiness_review",
        # DR-Gym review (2026-07-18): intervention fatigue and finite
        # risk-budget pacing check inspired by 2605.12462. Research-only; no
        # target-weight changes.
        "intervention_history",
        "broker_holdings_time_series_sample",
        "broker_holdings_reconciliation_review",
        # 2608.08405 assigned-vs-realized deployment audit: checks whether
        # live targets, execution plans, and realized broker positions are
        # synchronized before any capacity claim. Research-only.
        "assigned_realized_deployment_shadow_2608_08405",
        # 2608.08405 finite-grid capacity interval shadow: specifies
        # deployment arms and reports why no interval is identified. Research-only.
        "capacity_grid_shadow_2608_08405",
        # 2608.08405 erosion-persistence proxy: estimates OHLCV proxy
        # persistence for Taiwan ETFs, but never treats it as causal capacity.
        "erosion_persistence_shadow_2608_08405",
        # 2608.08405 natural-experiment instrument readiness: checks lending
        # and index-event candidates for first-stage/exclusion conditions.
        "instrument_readiness_shadow_2608_08405",
        # 2608.08405 ramp path-dependence shadow: keeps ramp-up/ramp-down
        # questions separate from the capacity-level grid estimand.
        "ramp_path_dependence_shadow_2608_08405",
        # Capacity/crowding review (2608.08405): checks whether current
        # evidence can support scaling capital or interpreting impact models
        # as capacity proof. Research-only; never changes target weights.
        "capacity_crowding_readiness_2608_08405",
        "intervention_fatigue_risk_budget_readiness_review",
        # LETF tracking-error / effective-fee review (2026-07-18): holding-
        # horizon and inverse-hedge neutrality governance inspired by
        # 1610.09404. Research-only; no LETF pair strategy and no weight change.
        "letf_tracking_error_effective_fee_readiness_review",
        # 00632R discipline guard: latest-strategy hard rule that inverse ETF
        # exposure defaults to zero; no DCA, averaging down, or discretionary buy.
        "00632r_discipline_guard",
        # LETF/futures liquidity feedback watch (2603.05862, 2026-08-07):
        # shadow backtest for hidden liquidity and rebalancing feedback risk.
        # Diagnostic only; no target weights, orders, or guarded candidates.
        "letf_liquidity_feedback_watch_shadow_backtest",
        # Asian ETF tail analytics readiness (2026-07-19): CVaR/STARR/Rachev/
        # Hill tail-risk governance inspired by 2511.12476. Research-only; no
        # optimizer and no long-short leverage.
        "asian_etf_tail_analytics_readiness_review",
        # Consolidated research-shadow decision snapshot (2026-07-17):
        # summarizes research-only diagnostics such as FinStressTS and
        # tri-gate volatility memory. Diagnostic only.
        "gift_human_exception_record_draft",
        "gift_human_exception_approval_record_schema",
        "gift_signed_approval_record_template",
        "gift_signed_approval_validation",
        "gift_signed_approval_checklist_review",
        "gift_signed_approval_validator_smoke",
        "gift_manual_approval_readiness",
        "gift_pdf_advantage_coverage_review",
        "defensive_cash_floor_signed_approval_validation",
        "defensive_cash_floor_guarded_candidate",
        "defensive_cash_floor_guarded_monitor",
        # Moira paper review (2605.01954, 2026-08-07): these deterministic
        # shadow/context builders summarize forecast-vs-actual credit,
        # relative ETF exposure thesis, execution quality, policy-critic
        # proposals, and compact daily semantic context. They are diagnostics
        # only; no target weights, orders, code mutations, or guarded
        # candidates are produced.
        "moira_relative_exposure_thesis_shadow",
        "moira_hierarchical_credit_review_shadow",
        "moira_event_aware_execution_quality_shadow",
        "moira_policy_critic_shadow",
        "moira_policy_critic_validation_shadow",
        "moira_execution_guard_hard_stop_backtest_shadow",
        "daily_semantic_context_summary",
        "paper_convergence_review",
        "research_shadow_decision_snapshot",
        "research_governance_gate",
        "shadow_artifact_registry",
        "latest_strategy_target_weight_export",
        "latest_strategy_explain_snapshot",
        "data_freshness_gate",
        "ncf_panel_drift_auto_attribution",
        "golden_release_separation_audit",
        # FinRL-X review (2026-07-18): deployment-consistency review checks
        # target-weight / execution-plan / guard / health alignment. It is
        # diagnostic only and never changes target weights.
        "deployment_consistency_review",
        "deployment_summary",
        # DFL advisory stale-input fix (2026-07-26): regenerates the four
        # shadow artifacts (main + p50 + p70 + overlap) that
        # scripts/run/build_a2118_dfl_advisory.py and
        # evaluate_a2118_dfl_active_date_audit.py read, to STABLE
        # filenames, every pipeline run -- see
        # GROUP_A_PLUS_DFL_ADVISORY_STALE_INPUT_FIX_20260726.md. Each of
        # these three is a ~1-2 minute walk-forward backtest, not a data
        # refresh; a failure here must never block daily_status/
        # promotion_gate below it, and the advisory step already handles a
        # missing/stale input file gracefully (reports status=unavailable).
        "dfl_shadow_refresh_main",
        "dfl_shadow_refresh_p50",
        "dfl_shadow_refresh_p70",
        "dfl_shadow_refresh_overlap",
        "relative_reentry_opportunity_shadow",
        "relative_reentry_advisory_shadow",
        "relative_reentry_candidate_review",
        "relative_reentry_promotion_gate",
        "staged_reentry_event_study",
        "staged_reentry_promotion_review",
        "staged_reentry_confirmatory_tracker_2609_04917",
        "golden2_same_window_candidate_backtests",
        "golden2_multi_window_gate",
        "golden2_promotion_candidate_review",
        # 2026-07-28 fix: the whole TabNet/no-TabNet model-set-isolation /
        # same-method-baseline / external-feature-sensitivity governance
        # chain tracks a *different* candidate model's promotion-gate
        # status (see the manifest's own "promote_to_live": false /
        # "training_allowed": false permissions block) -- it never changes
        # a2118's live target weights. Discovered as a real, previously-
        # unwired dependency gap on 2026-07-27: a missing same-day file
        # here crashed the entire remaining pipeline (daily_signal/
        # execution_plan/alert_state included), which is exactly the
        # failure mode every other best-effort step in this set already
        # guards against. Best-effort here too, for the same reason.
        "ncf_panel_drift_no_tabnet_baseline_vs_today",
        "ncf_panel_drift_model_set_isolation_report",
        "ncf_panel_same_method_baseline_manifest",
        "ncf_panel_external_feature_sensitivity_governance",
        "ncf_panel_drift_remediation_plan",
        "panel_drift_resolution_progress",
        "ncf_panel_drift_auto_attribution",
    }
)

DEFAULT_TICKERS = (
    "0050.TW",
    "00631L.TW",
    "00632R.TW",
    "0056.TW",
    "00646.TW",
    "00679B.TWO",
    "00713.TW",
    "00751B.TWO",
    "00878.TW",
)


def _result_path(name: str) -> Path:
    return RESULTS_DIR / name


def _infer_no_external_panel_path(panel_path: str | Path) -> str:
    path = Path(panel_path)
    if path.suffix.lower() != ".csv":
        return str(path)
    if path.stem.endswith("_no_external"):
        return str(path)
    return str(path.with_name(f"{path.stem}_no_external{path.suffix}"))


def _normalize_project_path(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _assert_no_protected_golden_release_output_targets(commands: dict[str, list[str]]) -> None:
    protected = {_normalize_project_path(path) for path in PROTECTED_GOLDEN_RELEASE_ARTIFACTS}
    protected_prefixes = tuple(str(path) for path in protected)
    violations: list[str] = []
    for step, cmd in commands.items():
        for index, token in enumerate(cmd[:-1]):
            if token not in OUTPUT_TARGET_FLAGS:
                continue
            candidate = _normalize_project_path(cmd[index + 1])
            candidate_str = str(candidate)
            if candidate in protected or any(candidate_str.startswith(prefix + ".") for prefix in protected_prefixes):
                violations.append(f"{step}:{token}={candidate}")
    if violations:
        raise ValueError(
            "daily pipeline attempted to write protected frozen Golden release artifact(s): "
            + "; ".join(sorted(violations))
        )


def _json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_failed_manifest(
    date_stamp: str, *, failed_step: str, error: str, completed_steps: list[str]
) -> Path:
    """Record a critical step's failure so collect_pipeline_health() sees
    today's date_stamp with status="failed" instead of silently falling
    back to the last good manifest via glob."""
    manifest_path = _result_path(f"ncf_daily_pipeline_{date_stamp}.json")
    manifest_path.write_text(
        json.dumps(
            {
                "date_stamp": date_stamp,
                "status": "failed",
                "failed_step": failed_step,
                "error": error,
                "completed_steps": completed_steps,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _notify_pipeline_failure(date_stamp: str, failed_step: str, error: str) -> None:
    """daily_signal/alert_state never ran (the failure happened before
    them), so this is the only channel left to reach a human about today's
    run. Best-effort -- must never raise, or it would mask the original
    failure being re-raised by the caller."""
    try:
        from group_a_plus.operations.push_notifications import send_telegram_message

        send_telegram_message(
            f"<b>GroupA+ daily pipeline FAILED</b> ({date_stamp})\n"
            f"Step: {failed_step}\nError: {error}"
        )
    except Exception:
        pass


def _run(cmd: list[str], *, dry_run: bool, env_extra: dict[str, str] | None = None, log_fh=None) -> None:
    if log_fh:
        log_fh.write("$ " + " ".join(cmd) + "\n")
        log_fh.flush()
    if dry_run:
        print("$ " + " ".join(cmd))
        return
    env = os.environ.copy()
    env.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-ncf")
    if env_extra:
        env.update(env_extra)
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, env=env,
                   stdout=log_fh, stderr=log_fh)


def _signal_summary(path: Path) -> dict[str, Any]:
    payload = _json_load(path)
    ensemble = payload.get("horizon_ensemble", {})
    freshness = payload.get("data_freshness", {})
    return {
        "ticker": payload.get("ticker"),
        "last_close_date": payload.get("last_close_date"),
        "last_close": payload.get("last_close"),
        "current_regime": payload.get("current_regime"),
        "direction": ensemble.get("direction"),
        "probability_up": ensemble.get("combined_probability_up"),
        "calibrated_probability_up": ensemble.get("calibrated_probability_up"),
        "confidence": ensemble.get("confidence"),
        "weighted_return": ensemble.get("weighted_return"),
        "data_freshness_status": freshness.get("status"),
        "data_sources": freshness.get("sources"),
        "missing_sources": freshness.get("missing_sources"),
        "stale_sources": freshness.get("stale_sources"),
        "sources_ahead_of_ohlcv": freshness.get("sources_ahead_of_ohlcv"),
    }


def _resolve_chip_start(db_path: Path, tables: list[str], default_start: str) -> str:
    """M8 (2026-07-02 Fable 5 audit): extend the fetch window backward to
    cover any real gap since the last successful fetch, instead of always
    using a fixed lookback (`--chip-start` defaults to today-21d) that
    leaves a permanent hole whenever the pipeline was down longer than that
    -- this happened for real on 2026-07-02 (derivative_institutional_data
    gap, backfilled manually; see project_automation memory).

    Returns the earlier of `default_start` and (the day after the earliest
    MAX(dt) across `tables`) -- this only ever *widens* the window when
    there's a real gap; a table that's already fresher than the default
    lookback doesn't narrow it (still refetches the default trailing window,
    which is harmless and covers any late-arriving upstream revisions).
    Falls back to `default_start` unchanged if the DB or tables don't exist
    yet, or on any query error (never blocks the pipeline on this check).
    """
    if not db_path.exists() or not tables:
        return default_start
    try:
        import duckdb

        con = duckdb.connect(str(db_path), read_only=True)
        try:
            existing = {
                row[0] for row in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
            }
            max_dates: list[date] = []
            for table in tables:
                if table not in existing:
                    continue
                result = con.execute(f"SELECT MAX(dt) FROM {table}").fetchone()
                if result and result[0] is not None:
                    max_dates.append(result[0] if isinstance(result[0], date) else date.fromisoformat(str(result[0])))
        finally:
            con.close()
    except Exception:
        return default_start
    if not max_dates:
        return default_start
    earliest_gap_start = min(max_dates) + timedelta(days=1)
    default_start_date = date.fromisoformat(default_start)
    return min(default_start_date, earliest_gap_start).isoformat()


def _build_research_governance_commands(*, stamp: str, as_of: str, db_path: Path | None = None) -> dict[str, list[str]]:
    latest_dir = PROJECT_ROOT / "report" / "group_a_plus" / "latest"
    resolved_db = db_path or PROJECT_ROOT / "FinRL" / "data" / "stock_data.db"
    return {
        "research_shadow_decision_snapshot": [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py",
            "--systemic-bubble",
            str(latest_dir / "systemic_bubble_time_at_risk_review.json"),
            "--illiquidity-network",
            str(latest_dir / "illiquidity_network_readiness_review.json"),
            "--speculative-influence",
            str(latest_dir / "speculative_influence_network_readiness_review.json"),
            "--sin-lite-proxy",
            str(latest_dir / "sin_lite_proxy.json"),
            "--hmm-wj",
            str(latest_dir / "hmm_wj_synthetic_scenario_readiness_review.json"),
            "--scr-readiness",
            str(latest_dir / "2602_24037_scr_readiness_review.json"),
            "--scr-robustness",
            str(latest_dir / "2602_24037_scr_readiness_robustness.json"),
            "--scr-window-split",
            str(latest_dir / "2602_24037_scr_readiness_window_split.json"),
            "--scr-stress-score",
            str(latest_dir / "2602_24037_scr_scenario_stress_score.json"),
            "--dynamic-cvar",
            str(latest_dir / "dynamic_cvar_tail_cost_readiness_review.json"),
            "--cvar-cost-window-split-2606-26625",
            str(latest_dir / "2606_26625_cvar_cost_window_split.json"),
            "--rolling-tail-no-add-2606-26625",
            str(latest_dir / "2606_26625_rolling_tail_no_add_gate.json"),
            "--dynamic-cvar-constraint-2608-20179",
            str(latest_dir / "2608_20179_dynamic_cvar_constraint_shadow.json"),
            "--dynamic-cvar-forward-2608-20179",
            str(latest_dir / "2608_20179_dynamic_cvar_forward_validation.json"),
            "--synthetic-augmentation",
            str(latest_dir / "synthetic_augmentation_validation_readiness_review.json"),
            "--intervention-fatigue",
            str(latest_dir / "intervention_fatigue_risk_budget_readiness_review.json"),
            "--letf-tracking",
            str(latest_dir / "letf_tracking_error_effective_fee_readiness_review.json"),
            "--asian-etf-tail-analytics",
            str(latest_dir / "asian_etf_tail_analytics_readiness_review.json"),
            "--llm-state-reward-signed-approval-validation",
            str(latest_dir / "llm_state_reward_human_exception_signed_approval_validation.json"),
            "--ncf-decision-calibration",
            str(_result_path(f"ncf_decision_calibration_shadow_{stamp}.json")),
            "--output",
            str(latest_dir / "research_shadow_decision_snapshot.json"),
        ],
        "research_governance_gate": [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_research_governance_gate.py",
            "--reports-dir",
            str(latest_dir),
            "--as-of",
            as_of,
            "--output",
            str(latest_dir / "research_governance_gate.json"),
            "--output-md",
            str(latest_dir / "research_governance_gate.md"),
        ],
        "shadow_artifact_registry": [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_shadow_artifact_registry.py",
            "--reports-dir",
            str(latest_dir),
            "--as-of",
            as_of,
            "--output",
            str(latest_dir / "shadow_artifact_registry.json"),
            "--output-md",
            str(latest_dir / "shadow_artifact_registry.md"),
        ],
        "latest_strategy_target_weight_export": [
            sys.executable,
            "scripts/evaluate/export_group_a_plus_latest_strategy_target_weights.py",
            "--start",
            "2025-07-01",
            "--end",
            "latest",
            "--db",
            str(resolved_db),
            "--output-json",
            str(latest_dir / "latest_strategy_historical_target_weights.json"),
            "--output-csv",
            str(latest_dir / "latest_strategy_historical_target_weights.csv"),
            "--history-dir",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest_strategy_historical_target_weights" / "history"),
        ],
        "latest_strategy_explain_snapshot": [
            sys.executable,
            "scripts/evaluate/build_group_a_plusplus_latest_strategy_explain_snapshot.py",
            "--watchlist",
            str(PROJECT_ROOT / "config" / "group_a_plus_watchlist.json"),
            "--target-weights",
            str(latest_dir / "latest_strategy_historical_target_weights.json"),
            "--research-governance",
            str(latest_dir / "research_governance_gate.json"),
            "--shadow-registry",
            str(latest_dir / "shadow_artifact_registry.json"),
            "--as-of",
            as_of,
            "--output",
            str(latest_dir / "group_a_plusplus_latest_strategy_explain_snapshot.json"),
            "--output-md",
            str(latest_dir / "group_a_plusplus_latest_strategy_explain_snapshot.md"),
        ],
        "data_freshness_gate": [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_data_freshness_gate.py",
            "--live-signal",
            str(latest_dir / "live_signal.json"),
            "--latest-strategy-explain-snapshot",
            str(latest_dir / "group_a_plusplus_latest_strategy_explain_snapshot.json"),
            "--ohlcv-freshness",
            str(_result_path(f"ohlcv_freshness_{stamp}.json")),
            "--as-of",
            as_of,
            "--output",
            str(latest_dir / "data_freshness_gate.json"),
            "--output-md",
            str(latest_dir / "data_freshness_gate.md"),
        ],
        "ncf_panel_drift_auto_attribution": [
            sys.executable,
            "scripts/evaluate/build_ncf_panel_drift_auto_attribution.py",
            "--diagnosis",
            str(_result_path(f"ncf_panel_drift_diagnosis_{stamp}.json")),
            "--remediation-plan",
            str(_result_path(f"ncf_panel_drift_remediation_plan_{stamp}.json")),
            "--external-sensitivity-governance",
            str(_result_path(f"ncf_panel_external_feature_sensitivity_governance_{stamp}.json")),
            "--panel-manifest",
            str(_result_path(f"ncf_panel_manifest_{stamp}.json")),
            "--data-freshness-gate",
            str(latest_dir / "data_freshness_gate.json"),
            "--as-of",
            as_of,
            "--output",
            str(latest_dir / "ncf_panel_drift_auto_attribution.json"),
            "--output-md",
            str(latest_dir / "ncf_panel_drift_auto_attribution.md"),
        ],
        "golden_release_separation_audit": [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_golden_release_separation_audit.py",
            "--as-of",
            as_of,
            "--output",
            str(latest_dir / "golden_release_separation_audit.json"),
            "--output-md",
            str(latest_dir / "golden_release_separation_audit.md"),
        ],
    }


def _build_ctbc_2509_02986_commands(*, stamp: str, db_path: Path) -> dict[str, list[str]]:
    latest_dir = PROJECT_ROOT / "report" / "group_a_plus" / "latest"
    return {
        "ctbc_debounce_shadow_2509_02986": [
            sys.executable,
            "scripts/evaluate/evaluate_group_a_plus_2509_02986_ctbc_debounce_shadow.py",
            "--panel",
            str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
            "--db",
            str(db_path),
            "--output",
            str(latest_dir / "2509_02986_ctbc_debounce_shadow.json"),
            "--markdown",
            str(latest_dir / "2509_02986_ctbc_debounce_shadow.md"),
        ],
        "ctbc_00713_debounce_shadow_2509_02986": [
            sys.executable,
            "scripts/evaluate/evaluate_group_a_plus_2509_02986_ctbc_00713_debounce_shadow.py",
            "--db",
            str(db_path),
            "--panel-00713",
            str(_result_path(f"ncf_00713_panel_latest_{stamp}.csv")),
            "--output",
            str(latest_dir / "2509_02986_ctbc_00713_debounce_shadow.json"),
            "--markdown",
            str(latest_dir / "2509_02986_ctbc_00713_debounce_shadow.md"),
            "--curves-output",
            str(_result_path(f"2509_02986_ctbc_00713_debounce_shadow_curves_{stamp}.csv")),
        ],
        "ctbc_00713_domain_randomization_2509_02986": [
            sys.executable,
            "scripts/evaluate/evaluate_group_a_plus_2509_02986_ctbc_00713_domain_randomization.py",
            "--db",
            str(db_path),
            "--panel-00713",
            str(_result_path(f"ncf_00713_panel_latest_{stamp}.csv")),
            "--output",
            str(latest_dir / "2509_02986_ctbc_00713_domain_randomization.json"),
            "--markdown",
            str(latest_dir / "2509_02986_ctbc_00713_domain_randomization.md"),
        ],
        "ctbc_groupa_plusplus_review_2509_02986": [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_2509_02986_ctbc_review.py",
            "--output",
            str(latest_dir / "2509_02986_ctbc_groupa_plusplus_review.json"),
            "--markdown",
            str(latest_dir / "2509_02986_ctbc_groupa_plusplus_review.md"),
            "--debounce",
            str(latest_dir / "2509_02986_ctbc_debounce_shadow.json"),
            "--debounce-00713",
            str(latest_dir / "2509_02986_ctbc_00713_debounce_shadow.json"),
            "--domain-randomization",
            str(latest_dir / "2509_02986_ctbc_00713_domain_randomization.json"),
            "--promotion-readiness",
            str(latest_dir / "2509_02986_ctbc_promotion_readiness_gate.json"),
        ],
        "ctbc_promotion_readiness_gate_2509_02986": [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_2509_02986_ctbc_promotion_readiness_gate.py",
            "--review",
            str(latest_dir / "2509_02986_ctbc_groupa_plusplus_review.json"),
            "--debounce-00631l",
            str(latest_dir / "2509_02986_ctbc_debounce_shadow.json"),
            "--debounce-00713",
            str(latest_dir / "2509_02986_ctbc_00713_debounce_shadow.json"),
            "--domain-randomization",
            str(latest_dir / "2509_02986_ctbc_00713_domain_randomization.json"),
            "--output",
            str(latest_dir / "2509_02986_ctbc_promotion_readiness_gate.json"),
            "--markdown",
            str(latest_dir / "2509_02986_ctbc_promotion_readiness_gate.md"),
        ],
    }


def build_commands(args: argparse.Namespace) -> dict[str, list[str]]:
    stamp = args.date_stamp
    as_of = stamp[:4] + "-" + stamp[4:6] + "-" + stamp[6:]
    chip_start = args.chip_start
    chip_end = args.chip_end
    db_path = Path(getattr(args, "db", None) or DB_PATH)
    live_signal_path = getattr(args, "live_signal_override", None) or str(
        _result_path(f"group_a_plus_live_signal_v2_{stamp}.json")
    )
    institutional_start = _resolve_chip_start(db_path, ["institutional_data"], chip_start)
    margin_start = _resolve_chip_start(db_path, ["margin_data"], chip_start)
    market_margin_start = _resolve_chip_start(db_path, ["market_margin_data"], chip_start)
    derivative_start = _resolve_chip_start(db_path, ["derivative_institutional_data"], chip_start)
    securities_lending_start = _resolve_chip_start(db_path, ["securities_lending_data"], chip_start)
    dealer_start = _resolve_chip_start(db_path, ["dealer_futures_data", "dealer_options_data"], chip_start)
    foreign_shareholding_start = _resolve_chip_start(db_path, ["foreign_shareholding_data"], chip_start)
    short_sale_balance_start = _resolve_chip_start(db_path, ["short_sale_balance_data"], chip_start)
    day_trading_start = _resolve_chip_start(db_path, ["day_trading_data"], chip_start)
    tickers = ",".join(DEFAULT_TICKERS)
    refresh_target_date = getattr(args, "refresh_target_date", "auto")

    only_refresh = getattr(args, "only_refresh", False)
    commands: dict[str, list[str]] = {}
    if not args.skip_refresh:
        refresh_cmd = [
            sys.executable,
            "refresh_group_data.py",
            "--group",
            "both",
            "--summary-path",
            str(_result_path(f"data_refresh_{stamp}.json")),
        ]
        if refresh_target_date != "auto":
            refresh_cmd.extend(["--target-date", refresh_target_date])
        if args.force_refresh:
            refresh_cmd.append("--force")
        if getattr(args, "strict_refresh", False):
            refresh_cmd.append("--strict")
        commands["refresh_group_data"] = refresh_cmd
        commands["refresh_taifex"] = [sys.executable, "taifex_futures_data.py", "--refresh-latest"]
        commands["refresh_taifex_options"] = [sys.executable, "taifex_options_data.py", "--refresh-latest"]
        commands["refresh_institutional"] = [
            sys.executable,
            "FinRL/data/stock_db.py",
            "--add-institutional",
            tickers,
            "--start",
            institutional_start,
            "--end",
            chip_end,
        ]
        commands["refresh_margin"] = [
            sys.executable,
            "FinRL/data/stock_db.py",
            "--add-margin",
            tickers,
            "--start",
            margin_start,
            "--end",
            chip_end,
        ]
        commands["refresh_market_margin"] = [
            sys.executable,
            "FinRL/data/stock_db.py",
            "--add-market-margin",
            "--start",
            market_margin_start,
            "--end",
            chip_end,
        ]
        commands["refresh_derivative_institutional"] = [
            sys.executable,
            "scripts/fetch/fetch_finmind_chip_data.py",
            "--datasets",
            "derivative_institutional",
            "--futures-ids",
            "TX",
            "--option-ids",
            "TXO",
            "--start",
            derivative_start,
            "--end",
            chip_end,
        ]
        commands["refresh_securities_lending"] = [
            sys.executable,
            "scripts/fetch/fetch_finmind_chip_data.py",
            "--datasets",
            "securities_lending",
            "--tickers",
            "0050.TW",
            "--start",
            securities_lending_start,
            "--end",
            chip_end,
        ]
        commands["securities_lending_0050_source_status"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_securities_lending_source_status.py",
            "--db",
            str(db_path),
            "--query-start",
            securities_lending_start,
            "--query-end",
            chip_end,
            "--as-of",
            as_of,
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "securities_lending_0050_source_status.json"),
            "--output-md",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "securities_lending_0050_source_status.md"),
        ]
        commands["refresh_dealer_positions"] = [
            sys.executable,
            "scripts/fetch/fetch_finmind_chip_data.py",
            "--datasets",
            "dealer_futures,dealer_options",
            "--futures-ids",
            "TX",
            "--option-ids",
            "TXO",
            "--start",
            dealer_start,
            "--end",
            chip_end,
        ]
        commands["refresh_foreign_shareholding"] = [
            sys.executable,
            "scripts/fetch/fetch_finmind_chip_data.py",
            "--datasets",
            "foreign_shareholding",
            "--tickers",
            "0050.TW",
            "--start",
            foreign_shareholding_start,
            "--end",
            chip_end,
        ]
        commands["refresh_short_sale_balances"] = [
            sys.executable,
            "scripts/fetch/fetch_finmind_chip_data.py",
            "--datasets",
            "short_sale_balances",
            "--tickers",
            "0050.TW",
            "--start",
            short_sale_balance_start,
            "--end",
            chip_end,
        ]
        commands["refresh_day_trading"] = [
            sys.executable,
            "scripts/fetch/fetch_finmind_chip_data.py",
            "--datasets",
            "day_trading",
            "--tickers",
            "0050.TW",
            "--start",
            day_trading_start,
            "--end",
            chip_end,
        ]
        commands["refresh_soxx_options_iv"] = [
            sys.executable,
            "scripts/fetch/fetch_soxx_options_iv.py",
        ]
        commands["refresh_cross_market_ohlcv"] = [
            sys.executable,
            "scripts/fetch/fetch_cross_market_ohlcv.py",
        ]
        commands["refresh_2330_per"] = [
            sys.executable,
            "scripts/fetch/fetch_finmind_chip_data.py",
            "--datasets",
            "per",
            "--tickers",
            "2330",
            "--start",
            args.per_start,
            "--end",
            chip_end,
        ]
        if not args.skip_shareholding:
            commands["refresh_shareholding"] = [
                sys.executable,
                "FinRL/data/stock_db.py",
                "--add-shareholding",
            ]

    ohlcv_target_date = args.ohlcv_target_date
    if ohlcv_target_date == "auto" and refresh_target_date != "auto":
        ohlcv_target_date = refresh_target_date

    commands["ohlcv_freshness"] = [
        sys.executable,
        "scripts/misc/check_ohlcv_freshness.py",
        "--target-date",
        ohlcv_target_date,
        "--max-db-lag-days",
        str(args.max_ohlcv_lag_days),
        "--output",
        str(_result_path(f"ohlcv_freshness_{stamp}.json")),
    ]
    if args.fail_on_ohlcv_warning:
        commands["ohlcv_freshness"].append("--fail-on-warning")

    if only_refresh:
        return commands

    if not getattr(args, "skip_ncf_data_validation", False):
        validation_tickers = "00631L.TW,00632R.TW,2330.TW"
        commands["ncf_data_validation"] = [
            sys.executable,
            "ncf_data_quality.py",
            "--db",
            str(DB_PATH),
            "--tickers",
            validation_tickers,
            "--reference-date",
            "latest",
            "--max-ohlcv-gap-days",
            str(getattr(args, "ncf_max_ohlcv_gap_days", 14)),
            "--output",
            str(_result_path(f"ncf_data_validation_{stamp}.json")),
        ]

    if args.refresh_external_cache:
        commands["refresh_ncf_2330_checklist_external_cache"] = [
            sys.executable,
            "scripts/fetch/fetch_ncf_2330_checklist_external_cache.py",
            "--start",
            args.checklist_external_start,
            "--end",
            args.checklist_external_end,
            "--allow-download",
            "--output",
            str(_result_path(f"ncf_2330_checklist_external_cache_{stamp}.json")),
        ]

    commands["ncf_00631l"] = [
        sys.executable,
        "scripts/misc/ncf_00631l.py",
        "--train-start",
        args.train_start_00631l,
        "--val-start",
        args.val_start,
        "--val-end",
        args.val_end,
        "--output",
        str(_result_path(f"ncf_00631l_latest_{stamp}.json")),
        "--val-predictions-output",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--full-panel",
    ]
    commands["ncf_00632r"] = [
        sys.executable,
        "ncf_00632r.py",
        "--train-start",
        args.train_start_00632r,
        "--val-start",
        args.val_start,
        "--val-end",
        args.val_end,
        "--output",
        str(_result_path(f"ncf_00632r_latest_{stamp}.json")),
        "--val-predictions-output",
        str(_result_path(f"ncf_00632r_panel_latest_{stamp}.csv")),
        "--full-panel",
    ]
    commands["ncf_0050"] = [
        sys.executable,
        "scripts/misc/ncf_0050.py",
        "--train-start",
        getattr(args, "train_start_0050", "2015-01-01"),
        "--val-start",
        args.val_start,
        "--val-end",
        args.val_end,
        "--output",
        str(_result_path(f"ncf_0050_latest_{stamp}.json")),
        "--val-predictions-output",
        str(_result_path(f"ncf_0050_panel_latest_{stamp}.csv")),
        "--full-panel",
    ]
    commands["ncf_00713"] = [
        sys.executable,
        "scripts/misc/ncf_00713.py",
        "--train-start",
        getattr(args, "train_start_00713", "2017-09-19"),
        "--val-start",
        args.val_start,
        "--val-end",
        args.val_end,
        "--output",
        str(_result_path(f"ncf_00713_latest_{stamp}.json")),
        "--val-predictions-output",
        str(_result_path(f"ncf_00713_panel_latest_{stamp}.csv")),
        "--full-panel",
    ]
    commands["ncf_signal_archive"] = [
        sys.executable,
        "scripts/evaluate/append_ncf_signal_archive.py",
        "--date-stamp",
        stamp,
    ]
    commands["ncf_2330"] = [
        sys.executable,
        "ncf_2330.py",
        "--train-start",
        getattr(args, "train_start_2330", "2015-01-01"),
        "--val-start",
        args.val_start,
        "--val-end",
        args.val_end,
        "--output",
        str(_result_path(f"ncf_2330_latest_{stamp}.json")),
        "--val-predictions-output",
        str(_result_path(f"ncf_2330_panel_latest_{stamp}.csv")),
        "--full-panel",
        "--feature-mode",
        getattr(args, "ncf_2330_feature_mode", "after_close"),
    ]
    if args.no_external_features:
        commands["ncf_00631l"].append("--no-external-features")
        commands["ncf_00632r"].append("--no-external-features")
        commands["ncf_0050"].append("--no-external-features")
        commands["ncf_00713"].append("--no-external-features")
        commands["ncf_2330"].append("--no-external-features")
    else:
        commands["ncf_00631l_no_external_shadow"] = [
            sys.executable,
            "scripts/misc/ncf_00631l.py",
            "--train-start",
            args.train_start_00631l,
            "--val-start",
            args.val_start,
            "--val-end",
            args.val_end,
            "--output",
            str(_result_path(f"ncf_00631l_latest_{stamp}_no_external.json")),
            "--val-predictions-output",
            str(_result_path(f"ncf_00631l_panel_latest_{stamp}_no_external.csv")),
            "--full-panel",
            "--no-external-features",
        ]

    commands["ncf_panel_manifest"] = [
        sys.executable,
        "scripts/evaluate/build_ncf_panel_manifest.py",
        "--panels",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        str(_result_path(f"ncf_00632r_panel_latest_{stamp}.csv")),
        str(_result_path(f"ncf_0050_panel_latest_{stamp}.csv")),
        str(_result_path(f"ncf_00713_panel_latest_{stamp}.csv")),
        str(_result_path(f"ncf_2330_panel_latest_{stamp}.csv")),
        "--output",
        str(_result_path(f"ncf_panel_manifest_{stamp}.json")),
    ]
    commands["ncf_0050_threshold_eval"] = [
        sys.executable,
        "scripts/evaluate/evaluate_ncf_0050_panel_thresholds.py",
        "--panel",
        str(_result_path(f"ncf_0050_panel_latest_{stamp}.csv")),
        "--output",
        str(_result_path(f"ncf_0050_threshold_eval_{stamp}.json")),
        "--output-md",
        str(_result_path(f"ncf_0050_threshold_eval_{stamp}.md")),
        "--min-active-rows",
        "20",
    ]
    commands.update(_build_ctbc_2509_02986_commands(stamp=stamp, db_path=db_path))
    commands["auxiliary_policy_lift_shadow_2608_15841"] = [
        sys.executable,
        "scripts/evaluate/evaluate_ncf_downside_upside_net_derisk_score.py",
        "--db",
        str(db_path),
        "--panel-631l",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--panel-632r",
        str(_result_path(f"ncf_00632r_panel_latest_{stamp}.csv")),
        "--ncf-panel-631l",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--start",
        args.val_start,
        "--end",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_existing_aux_heads_policy_lift_shadow.json"),
    ]
    commands["auxiliary_churn_shadow_2608_15841"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_churn_shadow.py",
        "--policy-lift",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_existing_aux_heads_policy_lift_shadow.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_churn_shadow.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_churn_shadow.md"),
    ]
    commands["auxiliary_purged_walkforward_2608_15841"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_2608_15841_auxiliary_purged_walkforward.py",
        "--panel-631l",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--panel-632r",
        str(_result_path(f"ncf_00632r_panel_latest_{stamp}.csv")),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_purged_walkforward.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_purged_walkforward.md"),
    ]
    commands["auxiliary_regime_decay_audit_2608_15841"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_regime_decay_audit.py",
        "--panel",
        f"00631L.TW={_result_path(f'ncf_00631l_panel_latest_{stamp}.csv')}",
        "--panel",
        f"00632R.TW={_result_path(f'ncf_00632r_panel_latest_{stamp}.csv')}",
        "--panel",
        f"0050.TW={_result_path(f'ncf_0050_panel_latest_{stamp}.csv')}",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_regime_decay_audit.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_regime_decay_audit.md"),
    ]
    commands["auxiliary_lifecycle_audit_2608_15841"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_lifecycle_audit.py",
        "--panel",
        f"00631L.TW={_result_path(f'ncf_00631l_panel_latest_{stamp}.csv')}",
        "--panel",
        f"00632R.TW={_result_path(f'ncf_00632r_panel_latest_{stamp}.csv')}",
        "--panel",
        f"0050.TW={_result_path(f'ncf_0050_panel_latest_{stamp}.csv')}",
        "--regime-decay",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_regime_decay_audit.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_lifecycle_audit.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_lifecycle_audit.md"),
    ]
    commands["delayed_credit_audit_2608_15841"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_15841_delayed_credit_audit.py",
        "--panel",
        f"00631L.TW={_result_path(f'ncf_00631l_panel_latest_{stamp}.csv')}",
        "--panel",
        f"00632R.TW={_result_path(f'ncf_00632r_panel_latest_{stamp}.csv')}",
        "--panel",
        f"0050.TW={_result_path(f'ncf_0050_panel_latest_{stamp}.csv')}",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_delayed_credit_audit.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_delayed_credit_audit.md"),
    ]
    commands["candidate_auxiliary_bank_blueprint_2608_15841"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_15841_candidate_auxiliary_bank_blueprint.py",
        "--readiness",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_task_discovery_readiness.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_candidate_auxiliary_bank_blueprint.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_candidate_auxiliary_bank_blueprint.md"),
    ]
    commands["auxiliary_task_discovery_readiness_2608_15841"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_15841_auxiliary_task_discovery_readiness.py",
        "--panel",
        f"00631L.TW={_result_path(f'ncf_00631l_panel_latest_{stamp}.csv')}",
        "--panel",
        f"00632R.TW={_result_path(f'ncf_00632r_panel_latest_{stamp}.csv')}",
        "--panel",
        f"0050.TW={_result_path(f'ncf_0050_panel_latest_{stamp}.csv')}",
        "--signal",
        f"00631L.TW={_result_path(f'ncf_00631l_latest_{stamp}.json')}",
        "--signal",
        f"00632R.TW={_result_path(f'ncf_00632r_latest_{stamp}.json')}",
        "--signal",
        f"0050.TW={_result_path(f'ncf_0050_latest_{stamp}.json')}",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_task_discovery_readiness.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_task_discovery_readiness.md"),
        "--policy-lift",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_existing_aux_heads_policy_lift_shadow.json"),
        "--purged-wf",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_purged_walkforward.json"),
        "--churn-shadow",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_churn_shadow.json"),
        "--regime-decay",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_regime_decay_audit.json"),
        "--candidate-bank-blueprint",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_candidate_auxiliary_bank_blueprint.json"),
        "--lifecycle-audit",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_auxiliary_lifecycle_audit.json"),
        "--delayed-credit",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_15841_delayed_credit_audit.json"),
    ]
    active_ncf_00631l_panel = getattr(args, "active_ncf_00631l_panel", DEFAULT_ACTIVE_NCF_00631L_PANEL)
    commands["ncf_panel_drift"] = [
        sys.executable,
        "scripts/evaluate/evaluate_ncf_panel_drift.py",
        "--baseline-panel",
        active_ncf_00631l_panel,
        "--candidate-panel",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--outcome-aware",
        "--output",
        str(_result_path(f"ncf_panel_drift_active_vs_{stamp}.json")),
        "--csv-output",
        str(_result_path(f"ncf_panel_drift_active_vs_{stamp}.csv")),
    ]
    commands["ncf_panel_refresh_recommendation"] = [
        sys.executable,
        "scripts/evaluate/build_ncf_panel_refresh_recommendation.py",
        "--drift-audit",
        str(_result_path(f"ncf_panel_drift_active_vs_{stamp}.json")),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "ncf_panel_refresh_recommendation.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "ncf_panel_refresh_recommendation.md"),
        "--snapshot-output",
        str(_result_path(f"ncf_panel_refresh_recommendation_{stamp}.json")),
    ]
    if not args.no_external_features:
        commands["ncf_panel_drift_no_external_vs_external"] = [
            sys.executable,
            "scripts/evaluate/evaluate_ncf_panel_drift.py",
            "--baseline-panel",
            str(_result_path(f"ncf_00631l_panel_latest_{stamp}_no_external.csv")),
            "--candidate-panel",
            str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
            "--columns",
            "h20_prob_up",
            "confidence",
            "prob_fwd_mdd_gt5_h20",
            "prob_fwd_gain_gt5_h20",
            "--outcome-aware",
            "--output",
            str(_result_path(f"ncf_panel_drift_no_external_vs_external_{stamp}.json")),
        ]
    commands["ncf_panel_drift_diagnosis"] = [
        sys.executable,
        "scripts/evaluate/build_ncf_panel_drift_diagnosis.py",
        "--drift-audit",
        str(_result_path(f"ncf_panel_drift_active_vs_{stamp}.json")),
        "--baseline-panel",
        active_ncf_00631l_panel,
        "--candidate-panel",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--baseline-signal",
        str(_result_path("ncf_00631l_latest_20260630.json")),
        "--candidate-signal",
        str(_result_path(f"ncf_00631l_latest_{stamp}.json")),
        "--output",
        str(_result_path(f"ncf_panel_drift_diagnosis_{stamp}.json")),
    ]
    if not args.no_external_features:
        commands["ncf_panel_drift_diagnosis"].extend(
            [
                "--baseline-no-external-panel",
                _infer_no_external_panel_path(active_ncf_00631l_panel),
                "--candidate-no-external-panel",
                str(_result_path(f"ncf_00631l_panel_latest_{stamp}_no_external.csv")),
                "--sensitivity-audit",
                str(_result_path(f"ncf_panel_drift_no_external_vs_external_{stamp}.json")),
            ]
        )
    commands["panel_drift_triage"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_panel_drift_triage.py",
        "--diagnosis",
        str(_result_path(f"ncf_panel_drift_diagnosis_{stamp}.json")),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "panel_drift_triage.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "panel_drift_triage.md"),
    ]
    commands["ncf_panel_drift_remediation_plan_initial"] = [
        sys.executable,
        "scripts/evaluate/build_ncf_panel_drift_remediation_plan.py",
        "--diagnosis",
        str(_result_path(f"ncf_panel_drift_diagnosis_{stamp}.json")),
        "--output",
        str(_result_path(f"ncf_panel_drift_remediation_plan_initial_{stamp}.json")),
    ]
    # 2026-07-28 fix: the three commands below were never wired into the
    # automated pipeline at all, even though ncf_panel_external_feature_
    # sensitivity_governance / ncf_panel_drift_remediation_plan below
    # require same-day-dated versions of their outputs. Every prior day's
    # copy of these files (e.g. ncf_panel_same_method_baseline_manifest_
    # 20260722.json, ..._20260725.json) was produced by someone manually
    # re-running these commands by hand that same day (see
    # docs/HANDOFF_GROUPA_PLUS_EXTERNAL_SENSITIVITY_OBSERVATION_20260722.md).
    # On any day nobody does that, the automated run crashes with
    # FileNotFoundError at ncf_panel_external_feature_sensitivity_governance
    # and (pre-2026-07-28) that crash aborted the entire remaining pipeline,
    # including daily_signal/execution_plan/alert_state for that day --
    # discovered when this happened for real on 2026-07-27's manually
    # triggered run. All three compare the fixed 2026-06-30 TabNet/no-TabNet
    # baseline panels against today's real panel; none of it changes a2118's
    # live target weights (see the manifest's own
    # "promote_to_live": false / "training_allowed": false permissions
    # block) -- it exists to track a *different* candidate model's
    # promotion-gate status.
    commands["ncf_panel_drift_no_tabnet_baseline_vs_today"] = [
        sys.executable,
        "scripts/evaluate/evaluate_ncf_panel_drift.py",
        "--baseline-panel",
        str(_result_path("ncf_00631l_panel_latest_20260630_no_tabnet.csv")),
        "--candidate-panel",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--output",
        str(_result_path(f"ncf_panel_drift_no_tabnet_baseline_vs_{stamp}.json")),
    ]
    commands["ncf_panel_drift_model_set_isolation_report"] = [
        sys.executable,
        "scripts/evaluate/build_ncf_panel_drift_model_set_isolation_report.py",
        "--original-vs-today",
        str(_result_path(f"ncf_panel_drift_active_vs_{stamp}.json")),
        "--original-vs-no-tabnet",
        str(_result_path("ncf_panel_drift_tabnet_vs_no_tabnet_20260630.json")),
        "--no-tabnet-vs-today",
        str(_result_path(f"ncf_panel_drift_no_tabnet_baseline_vs_{stamp}.json")),
        "--output",
        str(_result_path(f"ncf_panel_drift_model_set_isolation_report_{stamp}.json")),
    ]
    commands["ncf_panel_same_method_baseline_manifest"] = [
        sys.executable,
        "scripts/evaluate/build_ncf_panel_same_method_baseline_manifest.py",
        "--original-baseline-panel",
        str(_result_path("ncf_00631l_panel_latest_20260630.csv")),
        "--same-method-baseline-panel",
        str(_result_path("ncf_00631l_panel_latest_20260630_no_tabnet.csv")),
        "--same-method-baseline-signal",
        str(_result_path("ncf_00631l_latest_20260630_no_tabnet.json")),
        "--validation-drift-audit",
        str(_result_path(f"ncf_panel_drift_no_tabnet_baseline_vs_{stamp}.json")),
        "--isolation-report",
        str(_result_path(f"ncf_panel_drift_model_set_isolation_report_{stamp}.json")),
        "--output",
        str(_result_path(f"ncf_panel_same_method_baseline_manifest_{stamp}.json")),
    ]
    commands["external_sensitivity_observation_log"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_external_sensitivity_observation_log.py",
        "--sensitivity-audit",
        str(_result_path(f"ncf_panel_drift_no_external_vs_external_{stamp}.json")),
        "--same-method-baseline-manifest",
        str(_result_path(f"ncf_panel_same_method_baseline_manifest_{stamp}.json")),
        "--observation-date",
        f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}",
        "--existing-log",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "external_sensitivity_observation_log.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "external_sensitivity_observation_log.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "external_sensitivity_observation_log.md"),
    ]
    commands["ncf_panel_external_feature_sensitivity_governance"] = [
        sys.executable,
        "scripts/evaluate/build_ncf_panel_external_feature_sensitivity_governance.py",
        "--sensitivity-audit",
        str(_result_path(f"ncf_panel_drift_no_external_vs_external_{stamp}.json")),
        "--same-method-baseline-manifest",
        str(_result_path(f"ncf_panel_same_method_baseline_manifest_{stamp}.json")),
        "--remediation-plan",
        str(_result_path(f"ncf_panel_drift_remediation_plan_initial_{stamp}.json")),
        "--observation-log",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "external_sensitivity_observation_log.json"),
        "--allow-missing-sensitivity-audit",
        "--output",
        str(_result_path(f"ncf_panel_external_feature_sensitivity_governance_{stamp}.json")),
    ]
    commands["ncf_panel_drift_remediation_plan"] = [
        sys.executable,
        "scripts/evaluate/build_ncf_panel_drift_remediation_plan.py",
        "--diagnosis",
        str(_result_path(f"ncf_panel_drift_diagnosis_{stamp}.json")),
        "--model-set-isolation-report",
        str(_result_path(f"ncf_panel_drift_model_set_isolation_report_{stamp}.json")),
        "--same-method-baseline-manifest",
        str(_result_path(f"ncf_panel_same_method_baseline_manifest_{stamp}.json")),
        "--external-sensitivity-governance",
        str(_result_path(f"ncf_panel_external_feature_sensitivity_governance_{stamp}.json")),
        "--output",
        str(_result_path(f"ncf_panel_drift_remediation_plan_{stamp}.json")),
    ]
    commands["panel_drift_resolution_progress"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_panel_drift_resolution_progress.py",
        "--remediation-plan",
        str(_result_path(f"ncf_panel_drift_remediation_plan_{stamp}.json")),
        "--external-sensitivity-governance",
        str(_result_path(f"ncf_panel_external_feature_sensitivity_governance_{stamp}.json")),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "panel_drift_resolution_progress.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "panel_drift_resolution_progress.md"),
    ]
    commands["ncf_panel_coverage"] = [
        sys.executable,
        "scripts/evaluate/evaluate_ncf_panel_coverage.py",
        "--panel-ticker",
        f"{_result_path(f'ncf_00631l_panel_latest_{stamp}.csv')}=00631L.TW",
        f"{_result_path(f'ncf_00632r_panel_latest_{stamp}.csv')}=00632R.TW",
        f"{_result_path(f'ncf_2330_panel_latest_{stamp}.csv')}=external_market_ohlcv:yfinance:2330.TW",
        "--output",
        str(_result_path(f"ncf_panel_coverage_{stamp}.json")),
    ]
    commands["advisory_panel"] = [
        sys.executable,
        "scripts/misc/build_ncf_advisory_panel.py",
        "--panel-00631l",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--panel-00632r",
        str(_result_path(f"ncf_00632r_panel_latest_{stamp}.csv")),
        "--output",
        str(_result_path(f"ncf_advisory_panel_latest_{stamp}.csv")),
    ]
    commands["factor_lens"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_factor_lens.py",
        "--output",
        str(_result_path(f"group_a_plus_factor_lens_{stamp}.json")),
    ]
    # Codex 2026-08-13: this is a production-critical freshness guard. The
    # 2026-08 stale-golden1 incident happened because daily_signal/execution
    # only consumed the latest Group A pointer; the daily pipeline never
    # regenerated it. Keep this before daily_signal and out of BEST_EFFORT so
    # a failed golden1 refresh stops trade-driving artifacts fail-closed.
    commands["golden1_combined_signal"] = [
        sys.executable,
        "scripts/run/run_group_a_combined_signal.py",
        "--as-of-date",
        as_of,
    ]
    commands["daily_signal"] = [
        sys.executable,
        "group_a_plus/operations/daily_signal.py",
        "--as-of",
        as_of,
        "--output",
        str(_result_path(f"group_a_plus_live_signal_v2_{stamp}.json")),
    ]
    commands["riccati_mv_shadow"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_riccati_mv_shadow.py",
        "--as-of",
        as_of,
        "--execution-plan",
        live_signal_path,
        "--output",
        str(_result_path(f"riccati_mv_shadow_{stamp}.json")),
        "--latest-output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "riccati_mv_shadow.json"),
    ]
    commands["current_policy_re_evaluation_gate"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_current_policy_re_evaluation_gate.py",
        "--shadow",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "riccati_mv_shadow.json"),
        "--tail-bank",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_17808_tail_bank_review.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "current_policy_re_evaluation_gate.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "current_policy_re_evaluation_gate.md"),
    ]
    commands["rebalance_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_rebalance_review.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "rebalance_review.json"),
    ]
    commands["compounding_regime"] = [
        sys.executable,
        "scripts/evaluate/evaluate_00631l_leveraged_compounding_regime.py",
        "--end",
        "latest",
        "--output",
        str(_result_path(f"00631l_leveraged_compounding_regime_{stamp}.json")),
        "--csv",
        str(_result_path(f"00631l_leveraged_compounding_regime_{stamp}.csv")),
    ]
    commands["gjr_garch_shadow"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_gjr_garch_shadow.py",
        "--as-of",
        "latest",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gjr_garch_shadow.json"),
        "--log",
        str(PROJECT_ROOT / "results" / "gjr_garch_shadow_log.jsonl"),
    ]
    commands["a2120_shadow_pipeline"] = [
        sys.executable,
        "scripts/run/run_a2120_daily_shadow_pipeline.py",
        "--date-stamp",
        stamp,
    ]
    commands["recovery_boost_spillover_gate_shadow_log"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_recovery_boost_spillover_gate_shadow_log.py",
        "--panel",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
    ]
    commands["trough_override_eligibility_shadow_log"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_trough_override_eligibility_shadow_log.py",
        "--panel",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
    ]
    commands["add_0050_instead_shadow_log"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_add_0050_instead_shadow_log.py",
        "--panel",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
    ]
    commands["adaptive_review_interval_shadow_log"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_adaptive_review_interval_shadow_log.py",
        "--panel",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
    ]
    commands["gatedlinear_drawdown_forecast_shadow_log"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_gatedlinear_drawdown_forecast_shadow_log.py",
    ]
    commands["cvar_tail_risk_diagnostic"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_cvar_tail_risk_diagnostic_snapshot.py",
    ]
    commands["taiwan_etf_2607_16450_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2607_16450_taiwan_etf_review.py",
    ]
    commands["taiwan_etf_2607_16450_tail_scorecard"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2607_16450_tail_sensitive_scorecard.py",
    ]
    commands["taiwan_etf_2607_16450_cost_robustness"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2607_16450_turnover_cost_robustness.py",
    ]
    commands["taiwan_etf_2607_16450_candidate_tail_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2607_16450_candidate_tail_review.py",
    ]
    commands["taiwan_etf_2607_16450_regime_vol_forecast_quality"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_regime_switching_volatility_forecast_quality.py",
        "--ticker",
        "0050.TW",
        "--start",
        "2018-01-02",
        "--end",
        as_of if args.val_end == "latest" else args.val_end,
        "--output",
        str(PROJECT_ROOT / "report/group_a_plus/latest/2607_16450_regime_switching_volatility_forecast_quality.json"),
        "--rolling-window",
        "504",
        "--n-regimes",
        "2",
        "--use-augmented-features",
    ]
    commands["taiwan_etf_2607_16450_regime_vol_gate"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2607_16450_regime_switching_volatility_gate.py",
    ]
    commands["taiwan_etf_2607_16450_tail_dependence_monitor"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2607_16450_tail_dependence_monitor.py",
        "--end",
        args.val_end,
    ]
    commands["taiwan_etf_2607_16450_geopolitical_cvar_overlay"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2607_16450_geopolitical_cvar_overlay.py",
        "--watchlist-news",
        str(PROJECT_ROOT / "report/group_a_plus/latest/watchlist_news.json"),
    ]
    commands["taiwan_etf_2607_16450_bootstrap_promotion_gate"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2607_16450_bootstrap_promotion_gate.py",
    ]
    commands["paper_2609_07946_00635u_instrument_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_00635u_instrument_review.py",
        "--db",
        str(db_path),
        "--required-latest-date",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "00635u_instrument_review.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "00635u_instrument_review.md"),
    ]
    commands["paper_2609_07946_stock_bond_gold_forward_shadow"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_2609_07946_stock_bond_gold_forward_shadow.py",
        "--db",
        str(db_path),
        "--as-of",
        as_of,
        "--universe",
        "bond_plus_00635u",
        "--threshold",
        "2.0",
        "--shift-weight",
        "0.03",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07946_stock_bond_gold_forward_shadow_latest.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07946_stock_bond_gold_forward_shadow_latest.md"),
        "--log",
        str(PROJECT_ROOT / "results" / "2609_07946_stock_bond_gold_forward_shadow_log.jsonl"),
    ]
    commands["paper_2609_07946_bond_only_forward_shadow"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_2609_07946_stock_bond_gold_forward_shadow.py",
        "--db",
        str(db_path),
        "--as-of",
        as_of,
        "--universe",
        "bond_only",
        "--threshold",
        "1.8",
        "--shift-weight",
        "0.03",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07946_bond_only_forward_shadow_latest.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07946_bond_only_forward_shadow_latest.md"),
        "--log",
        str(PROJECT_ROOT / "results" / "2609_07946_bond_only_forward_shadow_log.jsonl"),
    ]
    commands["paper_2609_07946_complementarity_promotion_gate"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2609_07946_complementarity_promotion_gate.py",
        "--stock-bond-gold-log",
        str(PROJECT_ROOT / "results" / "2609_07946_stock_bond_gold_forward_shadow_log.jsonl"),
        "--bond-only-log",
        str(PROJECT_ROOT / "results" / "2609_07946_bond_only_forward_shadow_log.jsonl"),
        "--instrument-review",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "00635u_instrument_review.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07946_complementarity_promotion_gate.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07946_complementarity_promotion_gate.md"),
    ]
    commands["paper_2609_07946_adoption_matrix"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2609_07946_adoption_matrix.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07946_adoption_matrix.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07946_adoption_matrix.md"),
    ]
    commands["paper_2609_08106_complementarity_forward_shadow"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_2609_08106_complementarity_forward_shadow.py",
        "--db",
        str(db_path),
        "--as-of",
        as_of,
        "--threshold",
        "2.0",
        "--shift-weight",
        "0.03",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_08106_complementarity_forward_shadow_latest.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_08106_complementarity_forward_shadow_latest.md"),
        "--log",
        str(PROJECT_ROOT / "results" / "2609_08106_complementarity_forward_shadow_log.jsonl"),
    ]
    commands["paper_2609_08106_latest_target_weight_replay"] = [
        sys.executable,
        "scripts/evaluate/replay_group_a_plus_2609_08106_latest_target_weights.py",
        "--db",
        str(db_path),
        "--target-weights",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "latest_strategy_historical_target_weights.csv"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_08106_latest_target_weight_replay.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_08106_latest_target_weight_replay.md"),
    ]
    commands["paper_2609_08106_latest_target_weight_param_sweep"] = [
        sys.executable,
        "scripts/evaluate/sweep_group_a_plus_2609_08106_latest_target_replay_params.py",
        "--db",
        str(db_path),
        "--target-weights",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "latest_strategy_historical_target_weights.csv"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_08106_latest_target_weight_replay_param_sweep.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_08106_latest_target_weight_replay_param_sweep.md"),
    ]
    commands["paper_2609_08106_adoption_matrix"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2609_08106_adoption_matrix.py",
        "--latest-target-replay",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_08106_latest_target_weight_replay.json"),
        "--latest-target-param-sweep",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_08106_latest_target_weight_replay_param_sweep.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_08106_adoption_matrix.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_08106_adoption_matrix.md"),
    ]
    commands["paper_2609_07989_order_flow_regime_shadow"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_2609_07989_order_flow_regime_shadow.py",
        "--input",
        str(PROJECT_ROOT / "results" / "intraday_signed_order_flow_latest.csv"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07989_order_flow_regime_shadow.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07989_order_flow_regime_shadow.md"),
        "--log",
        str(PROJECT_ROOT / "results" / "2609_07989_order_flow_regime_shadow_log.jsonl"),
    ]
    commands["option_state_coverage_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_option_state_coverage_review.py",
        "--as-of",
        as_of,
    ]
    commands["adversarial_market_integrity_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_adversarial_market_integrity_review.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "adversarial_market_integrity_review.json"),
    ]
    commands["sciphyrl_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_sciphyrl_readiness_review.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "sciphyrl_readiness_review.json"),
    ]
    commands["market_impact_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_market_impact_readiness_review.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "market_impact_readiness_review.json"),
    ]
    commands["finstressts_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_finstressts_readiness_review.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "finstressts_readiness_review.json"),
    ]
    commands["finstressts_counterfactual_shadow"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_finstressts_counterfactual_shadow.py",
        "--output",
        str(_result_path(f"group_a_plus_finstressts_counterfactual_shadow_{stamp}.json")),
        "--latest",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "finstressts_counterfactual_shadow.json"),
    ]
    commands["finstressts_baseline_compare_shadow"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_finstressts_baseline_compare_shadow.py",
        "--output",
        str(_result_path(f"group_a_plus_finstressts_baseline_compare_shadow_{stamp}.json")),
        "--latest",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "finstressts_baseline_compare_shadow.json"),
    ]
    commands["finstressts_decision_snapshot"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_finstressts_decision_snapshot.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "finstressts_decision_snapshot.json"),
    ]
    commands["trigate_vol_memory_shadow"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_trigate_vol_memory_shadow.py",
        "--output",
        str(_result_path(f"group_a_plus_trigate_vol_memory_shadow_{stamp}.json")),
        "--latest",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "trigate_vol_memory_shadow.json"),
    ]
    commands["systemic_bubble_time_at_risk_review"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_systemic_bubble_time_at_risk_review.py",
        "--output",
        str(_result_path(f"group_a_plus_systemic_bubble_time_at_risk_review_{stamp}.json")),
        "--latest",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "systemic_bubble_time_at_risk_review.json"),
    ]
    commands["illiquidity_network_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_illiquidity_network_readiness_review.py",
        "--as-of",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "illiquidity_network_readiness_review.json"),
    ]
    commands["speculative_influence_network_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_speculative_influence_network_readiness_review.py",
        "--as-of",
        as_of,
        "--output",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "speculative_influence_network_readiness_review.json"
        ),
    ]
    commands["sin_lite_proxy"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_sin_lite_proxy.py",
        "--db",
        str(db_path),
        "--as-of",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "sin_lite_proxy.json"),
    ]
    commands["hmm_wj_synthetic_scenario_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "hmm_wj_synthetic_scenario_readiness_review.json"),
    ]
    commands["scr_readiness_review_2602_24037"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2602_24037_scr_readiness_review.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2602_24037_scr_readiness_review.json"),
    ]
    commands["scr_readiness_robustness_2602_24037"] = [
        sys.executable,
        "scripts/evaluate/sweep_group_a_plus_2602_24037_scr_readiness_robustness.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2602_24037_scr_readiness_robustness.json"),
    ]
    commands["scr_readiness_window_split_2602_24037"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_2602_24037_scr_readiness_window_split.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2602_24037_scr_readiness_window_split.json"),
    ]
    commands["scr_scenario_stress_score_2602_24037"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2602_24037_scr_scenario_stress_score.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2602_24037_scr_scenario_stress_score.json"),
    ]
    commands["cvar_cost_window_split_2606_26625"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_2606_26625_cvar_cost_window_split.py",
        "--end",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_26625_cvar_cost_window_split.json"),
        "--md-output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_26625_cvar_cost_window_split.md"),
    ]
    commands["rolling_tail_no_add_gate_2606_26625"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2606_26625_rolling_tail_no_add_gate.py",
        "--end",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_26625_rolling_tail_no_add_gate.json"),
        "--md-output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_26625_rolling_tail_no_add_gate.md"),
    ]
    commands["dynamic_cvar_constraint_shadow_2608_20179"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_20179_dynamic_cvar_constraint_shadow.py",
        "--end",
        as_of,
        "--rolling-tail-gate",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_26625_rolling_tail_no_add_gate.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_20179_dynamic_cvar_constraint_shadow.json"),
        "--md-output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_20179_dynamic_cvar_constraint_shadow.md"),
    ]
    commands["dynamic_cvar_forward_validation_2608_20179"] = [
        sys.executable,
        "scripts/evaluate/validate_group_a_plus_2608_20179_dynamic_cvar_forward.py",
        "--end",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_20179_dynamic_cvar_forward_validation.json"),
        "--md-output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_20179_dynamic_cvar_forward_validation.md"),
    ]
    commands["dynamic_cvar_tail_cost_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py",
        "--cvar-cost-window-split",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_26625_cvar_cost_window_split.json"),
        "--rolling-tail-no-add",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_26625_rolling_tail_no_add_gate.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "dynamic_cvar_tail_cost_readiness_review.json"),
    ]
    commands["synthetic_augmentation_validation_audit"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_synthetic_augmentation_validation_audit.py",
        "--panel",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--as-of",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "synthetic_augmentation_validation_audit.json"),
    ]
    commands["synthetic_augmentation_validation_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_synthetic_augmentation_validation_readiness_review.py",
        "--validation-audit",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "synthetic_augmentation_validation_audit.json"),
        "--output",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "synthetic_augmentation_validation_readiness_review.json"
        ),
    ]
    commands["intervention_history"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_intervention_history_from_daily_status.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "intervention_history.json"),
    ]
    commands["broker_holdings_time_series_sample"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_broker_holdings_time_series_sample.py",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "broker_holdings_time_series_sample.json"),
    ]
    commands["broker_holdings_reconciliation_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_broker_holdings_reconciliation_review.py",
        "--sample",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "broker_holdings_time_series_sample.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "broker_holdings_reconciliation_review.json"),
    ]
    commands["assigned_realized_deployment_shadow_2608_08405"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_08405_assigned_realized_deployment_shadow.py",
        "--live-signal",
        live_signal_path,
        "--execution-plan",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"),
        "--broker-sample",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "broker_holdings_time_series_sample.json"),
        "--broker-reconciliation",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "broker_holdings_reconciliation_review.json"),
        "--output",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "2608_08405_assigned_realized_deployment_shadow.json"
        ),
        "--markdown",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "2608_08405_assigned_realized_deployment_shadow.md"
        ),
    ]
    commands["capacity_grid_shadow_2608_08405"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_08405_capacity_grid_shadow.py",
        "--live-signal",
        live_signal_path,
        "--market-impact",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "market_impact_readiness_review.json"),
        "--assigned-realized",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "2608_08405_assigned_realized_deployment_shadow.json"
        ),
        "--capital",
        "1000000",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_capacity_grid_shadow.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_capacity_grid_shadow.md"),
    ]
    commands["erosion_persistence_shadow_2608_08405"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_08405_erosion_persistence_shadow.py",
        "--db",
        str(db_path),
        "--as-of",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_erosion_persistence_shadow.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_erosion_persistence_shadow.md"),
    ]
    commands["instrument_readiness_shadow_2608_08405"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_08405_instrument_readiness_shadow.py",
        "--securities-lending-status",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "securities_lending_0050_source_status.json"),
        "--assigned-realized",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "2608_08405_assigned_realized_deployment_shadow.json"
        ),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_instrument_readiness_shadow.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_instrument_readiness_shadow.md"),
    ]
    commands["ramp_path_dependence_shadow_2608_08405"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_08405_ramp_path_dependence_shadow.py",
        "--intervention-history",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "intervention_history.json"),
        "--assigned-realized",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "2608_08405_assigned_realized_deployment_shadow.json"
        ),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_ramp_path_dependence_shadow.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_ramp_path_dependence_shadow.md"),
    ]
    commands["capacity_crowding_readiness_2608_08405"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2608_08405_capacity_crowding_readiness.py",
        "--live-signal",
        live_signal_path,
        "--execution-plan",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"),
        "--market-impact",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "market_impact_readiness_review.json"),
        "--liquidity-feedback",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "letf_liquidity_feedback_watch_shadow_backtest.json"),
        "--capacity-grid",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_capacity_grid_shadow.json"),
        "--erosion-persistence",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_erosion_persistence_shadow.json"),
        "--instrument-readiness",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_instrument_readiness_shadow.json"),
        "--ramp-path-dependence",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_ramp_path_dependence_shadow.json"),
        "--capital",
        "1000000",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_capacity_crowding_readiness.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_capacity_crowding_readiness.md"),
    ]
    commands["intervention_fatigue_risk_budget_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_intervention_fatigue_risk_budget_readiness_review.py",
        "--intervention-history",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "intervention_history.json"),
        "--broker-holdings-history",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "broker_holdings_time_series_sample.json"),
        "--broker-reconciliation",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "broker_holdings_reconciliation_review.json"),
        "--output",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "intervention_fatigue_risk_budget_readiness_review.json"
        ),
    ]
    commands["letf_tracking_error_effective_fee_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_letf_tracking_error_effective_fee_readiness_review.py",
        "--db",
        str(db_path),
        "--as-of",
        stamp[:4] + "-" + stamp[4:6] + "-" + stamp[6:],
        "--intervention-fatigue",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "intervention_fatigue_risk_budget_readiness_review.json"
        ),
        "--output",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "letf_tracking_error_effective_fee_readiness_review.json"
        ),
    ]
    commands["00632r_discipline_guard"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_00632r_discipline_guard.py",
        "--live-signal",
        live_signal_path,
        "--letf-readiness",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "letf_tracking_error_effective_fee_readiness_review.json"
        ),
        "--tail-gate",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "00632r_tail_tracking_error_gate_review.json"),
        "--trade-check",
        str(PROJECT_ROOT / "0501_0904_check.xlsx"),
        "--max-manual-weight",
        "0.05",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "00632r_discipline_guard.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "00632r_discipline_guard.md"),
    ]
    commands["letf_liquidity_feedback_watch_shadow_backtest"] = [
        sys.executable,
        "scripts/evaluate/backtest_group_a_plus_letf_liquidity_feedback_watch_shadow.py",
        "--db",
        str(db_path),
        "--as-of",
        stamp[:4] + "-" + stamp[4:6] + "-" + stamp[6:],
        "--start",
        "2015-01-01",
        "--range-threshold",
        "0.035",
        "--volume-z-min",
        "1.5",
        "--dislocation-z-min",
        "1.5",
        "--min-trigger-count",
        "20",
        "--output",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "letf_liquidity_feedback_watch_shadow_backtest.json"
        ),
        "--history-dir",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "letf_liquidity_feedback_watch_shadow"
            / "history"
        ),
    ]
    commands["asian_etf_tail_analytics_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_asian_etf_tail_analytics_readiness_review.py",
        "--db",
        str(db_path),
        "--output",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "asian_etf_tail_analytics_readiness_review.json"
        ),
    ]
    commands["gift_human_exception_record_draft"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_llm_state_reward_human_exception_record_draft.py",
        "--as-of",
        as_of,
    ]
    commands["gift_human_exception_approval_record_schema"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_llm_state_reward_human_exception_approval_record_schema.py",
        "--as-of",
        as_of,
    ]
    commands["gift_signed_approval_record_template"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_llm_state_reward_human_exception_signed_approval_record_template.py",
        "--as-of",
        as_of,
    ]
    commands["gift_signed_approval_validation"] = [
        sys.executable,
        "scripts/evaluate/validate_group_a_plus_llm_state_reward_human_exception_signed_approval_record.py",
        "--as-of",
        as_of,
    ]
    commands["gift_signed_approval_checklist_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_gift_signed_approval_checklist_review.py",
        "--as-of",
        as_of,
    ]
    commands["gift_signed_approval_validator_smoke"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_gift_signed_approval_validator_smoke.py",
        "--as-of",
        as_of,
    ]
    commands["gift_manual_approval_readiness"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_llm_state_reward_manual_approval_readiness_review.py",
        "--as-of",
        as_of,
    ]
    commands["gift_pdf_advantage_coverage_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_gift_pdf_advantage_coverage_review.py",
        "--as-of",
        as_of,
    ]
    commands["defensive_cash_floor_signed_approval_validation"] = [
        sys.executable,
        "scripts/evaluate/validate_group_a_plus_defensive_cash_floor_signed_approval_record.py",
        "--as-of",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "defensive_cash_floor_signed_approval_validation.json"),
        "--history-dir",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "defensive_cash_floor_signed_approval_validation" / "history"),
    ]
    commands["defensive_cash_floor_guarded_candidate"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_defensive_cash_floor_guarded_candidate.py",
        "--live-signal",
        live_signal_path,
        "--signed-review",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "defensive_cash_floor_signed_approval_validation.json"),
        "--as-of",
        as_of,
        "--enable",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "defensive_cash_floor_guarded_candidate.json"),
        "--history-dir",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "defensive_cash_floor_guarded_candidate" / "history"),
        "--log",
        str(PROJECT_ROOT / "results" / "defensive_cash_floor_guarded_candidate_log.jsonl"),
    ]
    commands["defensive_cash_floor_guarded_monitor"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_defensive_cash_floor_guarded_monitor.py",
        "--db",
        str(db_path),
        "--log",
        str(PROJECT_ROOT / "results" / "defensive_cash_floor_guarded_candidate_log.jsonl"),
        "--as-of",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "defensive_cash_floor_guarded_monitor.json"),
        "--history-dir",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "defensive_cash_floor_guarded_monitor" / "history"),
    ]
    commands.update(_build_research_governance_commands(stamp=stamp, as_of=as_of, db_path=db_path))
    # 2026-07-26: repointed from the pre-2026-07-16 files (which claimed
    # 7/7 "triple_pass" windows). That claim was disproven on 2026-07-16
    # (GROUP_A_PLUS_FABLE_COMBINATION_OPPORTUNITIES_HANDOFF_20260716.md
    # item #9): covid_2020 had been silently panel-blind (zero NCF rows,
    # defaulting to KEEP), not genuinely tested. After backfilling real
    # 2020 NCF data, the main config dropped to 6/7 with covid_2020 as the
    # worst window (4x wrong-signed CAP10 actions during the March/June/
    # October 2020 V-shaped rally). This default was left pointing at the
    # disproven file for 10 days -- see
    # GROUP_A_PLUS_DFL_ADVISORY_STALE_INPUT_FIX_20260726.md. The selective
    # p50/p70 variants had never been re-run against the real 2020 data at
    # all until today; both are now regenerated (p50: 6/7, covid_2020's
    # reliability filter correctly rejects all candidates there rather
    # than repeating the main config's misfire; p70: 5/7, same covid_2020
    # rejection).
    # 2026-07-26: dated snapshot files (e.g. "..._pit2020_20260716.json")
    # are exactly what caused the stale-input bug this comment block used
    # to describe -- a one-time rerun's output filename gets hardcoded as
    # a default and nobody repoints it when the data is next refreshed.
    # Replaced with a "dfl_shadow_refresh" step (below) that regenerates
    # these same four artifacts to STABLE, non-dated filenames every
    # pipeline run, so the defaults below never need to be touched again.
    # Also fixes a second issue found the same day: reusing an old dated
    # file for one variant while regenerating others produces internally
    # inconsistent results if `run_a2118()` itself has changed in the
    # meantime (see GROUP_A_PLUS_DFL_ADVISORY_STALE_INPUT_FIX_20260726.md)
    # -- all four are now always regenerated together in one run.
    dfl_live_panel_path = _result_path(f"ncf_00631l_panel_latest_{stamp}.csv")
    DFL_WINDOWS_7WIN_PIT = (
        "covid_2020:2020-01-02:2020-12-31:results/ncf_00631l_panel_backfill_2020_20260716.csv:out_of_sample,"
        "inflation_2022:2022-01-03:2022-12-30:results/ncf_00631l_panel_latest_20260707.csv:out_of_sample,"
        f"live_2024_2026:2024-01-02:latest:{dfl_live_panel_path}:tuning_window,"
        f"active_2025_2026:2025-01-02:latest:{dfl_live_panel_path}:tuning_window,"
        "2017_bull:2017-01-03:2017-12-29:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,"
        "2018_correction:2018-01-02:2018-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,"
        "2019_recovery:2019-01-02:2019-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample"
    )
    relative_reentry_windows = (
        "covid_2020:2020-01-02:2020-12-31:results/ncf_00631l_panel_backfill_2020_20260716.csv:out_of_sample,"
        "inflation_2022:2022-01-03:2022-12-30:results/ncf_00631l_panel_latest_20260707.csv:out_of_sample,"
        f"live_2024_2026:2024-01-02:latest:{_result_path(f'ncf_00631l_panel_latest_{stamp}.csv')}:tuning_window,"
        f"active_2025_2026:2025-01-02:latest:{_result_path(f'ncf_00631l_panel_latest_{stamp}.csv')}:tuning_window,"
        "2017_bull:2017-01-03:2017-12-29:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,"
        "2018_correction:2018-01-02:2018-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample,"
        "2019_recovery:2019-01-02:2019-12-31:results/ncf_00631l_panel_backfill_2017_2019_20260710.csv:out_of_sample"
    )
    DFL_COMMON_FLAGS = [
        "--stateful-actions",
        "--require-panel-signal",
        "--min-train-days",
        "60",
        "--edge-threshold",
        "0.0005",
        "--reenter-edge-threshold",
        "-0.0005",
        "--regret-clip",
        "0.02",
        "--adjustment-fraction",
        "0.75",
        "--turnover-cap",
        "0.05",
        "--windows",
        DFL_WINDOWS_7WIN_PIT,
    ]
    dfl_advisory_input = getattr(
        args,
        "dfl_advisory_input",
        "results/a2118_decision_focused_action_shadow_dfl_main_latest.json",
    )
    dfl_selective_p50_input = getattr(
        args,
        "dfl_selective_p50_input",
        "results/a2118_decision_focused_action_shadow_dfl_selective_p50_latest.json",
    )
    dfl_selective_p70_input = getattr(
        args,
        "dfl_selective_p70_input",
        "results/a2118_decision_focused_action_shadow_dfl_selective_p70_latest.json",
    )
    commands["dfl_shadow_refresh_main"] = [
        sys.executable,
        "scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py",
        *DFL_COMMON_FLAGS,
        "--output",
        dfl_advisory_input,
    ]
    commands["dfl_shadow_refresh_p50"] = [
        sys.executable,
        "scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py",
        *DFL_COMMON_FLAGS,
        "--selective-reliability",
        "--reliability-max-error-percentile",
        "0.5",
        "--reliability-min-train-days",
        "60",
        "--output",
        dfl_selective_p50_input,
    ]
    commands["dfl_shadow_refresh_p70"] = [
        sys.executable,
        "scripts/evaluate/evaluate_a2118_decision_focused_action_shadow.py",
        *DFL_COMMON_FLAGS,
        "--selective-reliability",
        "--reliability-max-error-percentile",
        "0.7",
        "--reliability-min-train-days",
        "60",
        "--output",
        dfl_selective_p70_input,
    ]
    commands["dfl_advisory"] = [
        sys.executable,
        "scripts/run/build_a2118_dfl_advisory.py",
        "--input",
        dfl_advisory_input,
        "--selective-inputs",
        f"p50={dfl_selective_p50_input},p70={dfl_selective_p70_input}",
        "--live-signal",
        live_signal_path,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_dfl_advisory.json"),
    ]
    # 2026-07-26: same stable-filename fix as dfl_advisory_input above --
    # these two feed evaluate_a2118_dfl_active_date_audit.py.
    dfl_shadow_result = getattr(args, "dfl_shadow_result", dfl_advisory_input)
    dfl_overlap_result = getattr(
        args,
        "dfl_overlap_result",
        "results/a2118_decision_focused_action_overlap_dfl_latest.json",
    )
    commands["dfl_shadow_refresh_overlap"] = [
        sys.executable,
        "scripts/evaluate/evaluate_a2118_decision_focused_overlap.py",
        "--input",
        dfl_advisory_input,
        "--output",
        dfl_overlap_result,
    ]
    commands["dfl_active_date_audit"] = [
        sys.executable,
        "scripts/evaluate/evaluate_a2118_dfl_active_date_audit.py",
        "--input",
        dfl_shadow_result,
        "--overlap",
        dfl_overlap_result,
        "--output",
        str(_result_path(f"a2118_dfl_active_date_audit_{stamp}.json")),
    ]
    commands["dfl_shadow_ensemble"] = [
        sys.executable,
        "scripts/run/build_a2118_dfl_shadow_ensemble_log.py",
        "--advisory",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_dfl_advisory.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_dfl_shadow_ensemble.json"),
        "--log",
        str(PROJECT_ROOT / "results" / "a2118_dfl_shadow_ensemble_log.jsonl"),
    ]
    commands["a2118_seed_averaging_live_inference_snapshot"] = [
        sys.executable,
        "scripts/evaluate/build_a2118_seed_averaging_live_inference_snapshot.py",
        "--live-signal",
        live_signal_path,
        "--holdings-snapshot",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "holdings_authoritative_snapshot.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_live_inference_snapshot.json"),
    ]
    commands["a2118_seed_averaging_forward_shadow_monitor"] = [
        sys.executable,
        "scripts/evaluate/build_a2118_seed_averaging_forward_shadow_monitor.py",
        "--shadow",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_shadow.json"),
        "--live-signal",
        live_signal_path,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_forward_shadow_monitor.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_forward_shadow_monitor.md"),
        "--log",
        str(PROJECT_ROOT / "results" / "a2118_seed_averaging_forward_shadow_monitor_log.jsonl"),
        "--optional-inference-snapshot",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_live_inference_snapshot.json"),
    ]
    commands["a2118_seed_averaging_promotion_gate"] = [
        sys.executable,
        "scripts/evaluate/build_a2118_seed_averaging_promotion_gate.py",
        "--monitor",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_forward_shadow_monitor.json"),
        "--log",
        str(PROJECT_ROOT / "results" / "a2118_seed_averaging_forward_shadow_monitor_log.jsonl"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_promotion_gate.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_promotion_gate.md"),
    ]
    commands["a2118_risk_down_mapped_shadow"] = [
        sys.executable,
        "scripts/evaluate/build_a2118_risk_down_mapped_shadow.py",
    ]
    commands["paper_2606_09104_00631l_regime_split"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2606_09104_00631l_4pct_regime_split.py",
    ]
    commands["paper_2606_09104_00631l_staged_ladder_readiness"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2606_09104_00631l_staged_ladder_readiness.py",
        "--live-snapshot",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_seed_averaging_live_inference_snapshot.json"),
        "--live-signal",
        live_signal_path,
        "--holdings-snapshot",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "holdings_authoritative_snapshot.json"),
        "--regime-split",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_09104_00631l_4pct_regime_split.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_09104_00631l_staged_ladder_readiness.json"),
        "--history-dir",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "2606_09104_00631l_staged_ladder_readiness" / "history"),
    ]
    commands["paper_2606_09104_extreme_state_monitor"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_2606_09104_extreme_state_monitor.py",
        "--end",
        as_of,
        "--ladder",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_09104_00631l_staged_ladder_readiness.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_09104_extreme_state_monitor.json"),
        "--history-dir",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "2606_09104_extreme_state_monitor" / "history"),
    ]
    commands["relative_reentry_opportunity_shadow"] = [
        sys.executable,
        "scripts/evaluate/evaluate_00631l_0050_relative_reentry_opportunity.py",
        "--windows",
        relative_reentry_windows,
        "--actions",
        "KEEP,SHIFT_00631L_2,SHIFT_00631L_5",
        "--min-train-days",
        "60",
        "--edge-threshold",
        "0.0005",
        "--regret-clip",
        "0.02",
        "--selective-reliability",
        "--reliability-max-error-percentile",
        "0.7",
        "--reliability-min-train-days",
        "60",
        "--slow-bear-gate",
        "--slow-bear-drawdown-0050-60d-max",
        "-0.08",
        "--slow-bear-ret-0050-20d-max",
        "0.0",
        "--slow-bear-spread-00631l-0050-20d-max",
        "0.0",
        "--slow-bear-momentum-ret-0050-20d-max",
        "-0.03",
        "--risk-up-permission-gate",
        "--risk-up-permission-min-probability",
        "0.50",
        "--risk-up-permission-action",
        "SHIFT_00631L_5",
        "--risk-up-permission-min-train-days",
        "60",
        "--output",
        "results/00631l_0050_relative_reentry_opportunity_latest.json",
        "--latest-output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_opportunity_shadow.json"),
    ]
    commands["relative_reentry_advisory_shadow"] = [
        sys.executable,
        "scripts/run/build_00631l_0050_relative_reentry_advisory_shadow.py",
        "--input",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_opportunity_shadow.json"),
        "--live-signal",
        live_signal_path,
        "--strategy-trust-log",
        str(PROJECT_ROOT / "results" / "strategy_trust_shadow_log.jsonl"),
        "--risk-mechanism-log",
        str(PROJECT_ROOT / "results" / "risk_mechanism_shadow_log.jsonl"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_advisory_shadow.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_advisory_shadow.md"),
    ]
    commands["relative_reentry_candidate_review"] = [
        sys.executable,
        "scripts/evaluate/build_00631l_0050_relative_reentry_candidate_review.py",
        "--input",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_opportunity_shadow.json"),
        "--advisory",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_advisory_shadow.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_candidate_review.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_candidate_review.md"),
    ]
    commands["relative_reentry_promotion_gate"] = [
        sys.executable,
        "scripts/evaluate/build_00631l_0050_relative_reentry_promotion_gate.py",
        "--advisory",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_advisory_shadow.json"),
        "--review",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_candidate_review.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_promotion_gate.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_reentry_promotion_gate.md"),
    ]
    commands["staged_reentry_event_study"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_staged_reentry_shadow.py",
        "--evaluate-history",
    ]
    commands["staged_reentry_promotion_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_staged_reentry_promotion_review.py",
    ]
    commands["staged_reentry_confirmatory_tracker_2609_04917"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plusplus_2609_04917_staged_reentry_confirmatory_tracker.py",
        "--spec",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_04917_staged_reentry_frozen_confirmatory_spec.json"),
        "--event-study",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "staged_reentry_shadow_event_study.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_04917_staged_reentry_confirmatory_tracker.json"),
        "--markdown",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_04917_staged_reentry_confirmatory_tracker.md"),
    ]
    commands["ncf_decision_calibration_shadow"] = [
        sys.executable,
        "scripts/evaluate/evaluate_ncf_decision_calibration.py",
        "--panel",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--advisory",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_dfl_advisory.json"),
        "--dfl-shadow",
        dfl_advisory_input,
        "--output",
        str(_result_path(f"ncf_decision_calibration_shadow_{stamp}.json")),
    ]
    commands["tsi_stress_shadow"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_tsi_stress_shadow.py",
        "--start",
        "2020-01-01",
        "--end",
        as_of,
        "--as-of",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "tsi_stress_shadow.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "tsi_stress_shadow.md"),
        "--history-dir",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "tsi_stress_shadow" / "history"),
    ]
    commands["tsi_stress_oos"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_tsi_stress_oos.py",
        "--start",
        "2020-01-01",
        "--end",
        as_of,
        "--as-of",
        as_of,
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "tsi_stress_oos.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "tsi_stress_oos.md"),
        "--history-dir",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "tsi_stress_oos" / "history"),
    ]
    commands["tsi_no_add_shadow"] = [
        sys.executable,
        "scripts/evaluate/evaluate_group_a_plus_tsi_no_add_shadow.py",
        "--windows",
        (
            "live_2024_2026,2024-01-02,latest,results/ncf_00631l_panel_latest_20260707.csv,tuning_window;"
            "active_2025_2026,2025-01-02,latest,results/ncf_00631l_panel_latest_20260707.csv,tuning_window;"
            "taiwan_2026_q1q2_stress,2026-02-02,2026-04-30,results/ncf_00631l_panel_latest_20260707.csv,stress_window;"
            "taiwan_2026_recent,2026-05-15,latest,results/ncf_00631l_panel_latest_20260707.csv,recent_window"
        ),
        "--threshold",
        "0.90",
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "tsi_no_add_shadow.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "tsi_no_add_shadow.md"),
        "--history-dir",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "tsi_no_add_shadow" / "history"),
    ]
    commands["daily_artifact_integrity"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_daily_artifact_integrity.py",
        "--check-date",
        stamp[:4] + "-" + stamp[4:6] + "-" + stamp[6:],
        "--live-signal",
        live_signal_path,
        "--execution-plan",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"),
        "--panel-refresh-recommendation",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "ncf_panel_refresh_recommendation.json"),
        "--ncf-decision-calibration",
        str(_result_path(f"ncf_decision_calibration_shadow_{stamp}.json")),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "daily_artifact_integrity.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "daily_artifact_integrity.md"),
    ]
    research_shadow_decision_snapshot = commands.pop("research_shadow_decision_snapshot")
    research_governance_gate = commands.pop("research_governance_gate")
    shadow_artifact_registry = commands.pop("shadow_artifact_registry")
    latest_strategy_target_weight_export = commands.pop("latest_strategy_target_weight_export")
    latest_strategy_explain_snapshot = commands.pop("latest_strategy_explain_snapshot")
    data_freshness_gate = commands.pop("data_freshness_gate")
    golden_release_separation_audit = commands.pop("golden_release_separation_audit")
    paper_convergence_review = commands.pop("paper_convergence_review", None)
    if paper_convergence_review is not None:
        commands["paper_convergence_review"] = paper_convergence_review
    commands["research_shadow_decision_snapshot"] = research_shadow_decision_snapshot
    commands["research_governance_gate"] = research_governance_gate
    commands["shadow_artifact_registry"] = shadow_artifact_registry
    commands["latest_strategy_target_weight_export"] = latest_strategy_target_weight_export
    commands["latest_strategy_explain_snapshot"] = latest_strategy_explain_snapshot
    commands["data_freshness_gate"] = data_freshness_gate
    commands["golden_release_separation_audit"] = golden_release_separation_audit
    commands["daily_status"] = [
        sys.executable,
        "scripts/misc/check_group_a_plus_daily_status.py",
        "--mode",
        "live",
        "--live-signal",
        live_signal_path,
        "--execution-plan",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"),
        "--compounding-regime",
        str(_result_path(f"00631l_leveraged_compounding_regime_{stamp}.json")),
        "--dfl-advisory",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_dfl_advisory.json"),
        "--dfl-shadow-ensemble",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "a2118_dfl_shadow_ensemble.json"),
        "--dfl-active-date-audit",
        str(_result_path(f"a2118_dfl_active_date_audit_{stamp}.json")),
        "--finstressts-decision-snapshot",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "finstressts_decision_snapshot.json"),
        "--trigate-vol-memory-shadow",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "trigate_vol_memory_shadow.json"),
        "--systemic-bubble-time-at-risk-review",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "systemic_bubble_time_at_risk_review.json"),
        "--illiquidity-network-readiness-review",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "illiquidity_network_readiness_review.json"),
        "--speculative-influence-network-readiness-review",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "speculative_influence_network_readiness_review.json"
        ),
        "--sin-lite-proxy",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "sin_lite_proxy.json"),
        "--hmm-wj-synthetic-scenario-readiness-review",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "hmm_wj_synthetic_scenario_readiness_review.json"),
        "--scr-readiness-review-2602-24037",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2602_24037_scr_readiness_review.json"),
        "--scr-readiness-robustness-2602-24037",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2602_24037_scr_readiness_robustness.json"),
        "--scr-readiness-window-split-2602-24037",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2602_24037_scr_readiness_window_split.json"),
        "--scr-scenario-stress-score-2602-24037",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2602_24037_scr_scenario_stress_score.json"),
        "--dynamic-cvar-tail-cost-readiness-review",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "dynamic_cvar_tail_cost_readiness_review.json"),
        "--cvar-cost-window-split-2606-26625",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_26625_cvar_cost_window_split.json"),
        "--rolling-tail-no-add-2606-26625",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_26625_rolling_tail_no_add_gate.json"),
        "--dynamic-cvar-constraint-2608-20179",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_20179_dynamic_cvar_constraint_shadow.json"),
        "--dynamic-cvar-forward-2608-20179",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_20179_dynamic_cvar_forward_validation.json"),
        "--synthetic-augmentation-validation-readiness-review",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "synthetic_augmentation_validation_readiness_review.json"
        ),
        "--intervention-fatigue-risk-budget-readiness-review",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "intervention_fatigue_risk_budget_readiness_review.json"
        ),
        "--letf-tracking-error-effective-fee-readiness-review",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "letf_tracking_error_effective_fee_readiness_review.json"
        ),
        "--asian-etf-tail-analytics-readiness-review",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "asian_etf_tail_analytics_readiness_review.json"
        ),
        "--research-shadow-decision-snapshot",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "research_shadow_decision_snapshot.json"),
        "--daily-artifact-integrity",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "daily_artifact_integrity.json"),
        "--gift-signed-approval-checklist-review",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gift_signed_approval_checklist_review.json"),
        "--gift-signed-approval-validator-smoke",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gift_signed_approval_validator_smoke.json"),
        "--check-date",
        stamp[:4] + "-" + stamp[4:6] + "-" + stamp[6:],
        "--status-stage",
        "pre_promotion",
        "--output-prefix",
        str(_result_path(f"group_a_plus_daily_status_{stamp}")),
    ]
    commands["deployment_consistency_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_deployment_consistency_review.py",
        "--live-signal",
        live_signal_path,
        "--daily-status",
        str(_result_path(f"group_a_plus_daily_status_{stamp}.json")),
        "--securities-lending-source-status",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "securities_lending_0050_source_status.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "deployment_consistency_review.json"),
    ]
    commands["deployment_summary"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_deployment_summary.py",
        "--live-signal",
        live_signal_path,
        "--execution-plan",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"),
        "--deployment",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "deployment_consistency_review.json"),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "deployment_summary.json"),
        "--output-md",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "deployment_summary.md"),
    ]
    if not getattr(args, "skip_promotion_gate", False):
        promotion_candidates = list(getattr(args, "promotion_candidates", DEFAULT_PROMOTION_CANDIDATES))
        promotion_drift_audit = getattr(args, "promotion_drift_audit", None) or str(
            _result_path(f"ncf_panel_drift_active_vs_{stamp}.json")
        )
        commands["promotion_gate"] = [
            sys.executable,
            "scripts/evaluate/evaluate_group_a_plus_promotion_gate.py",
            "--baseline",
            getattr(args, "promotion_baseline", DEFAULT_PROMOTION_BASELINE),
            "--candidates",
            *promotion_candidates,
            "--drift-audit",
            promotion_drift_audit,
            "--multi-window-gate",
            getattr(args, "promotion_multi_window_gate", DEFAULT_PROMOTION_MULTI_WINDOW_GATE),
            "--deployment-consistency",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "deployment_consistency_review.json"),
            "--deployment-summary",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "deployment_summary.json"),
            "--output",
            str(_result_path(f"group_a_plus_promotion_gate_{stamp}.json")),
        ]
        # 2026-09-01: two upstream steps so golden2_promotion_candidate_review
        # gets fresh, golden2-specific evidence every day instead of reading a
        # data-availability-gap placeholder. Before this, the review's own
        # three legacy candidate files never had extractable candidate rows
        # (see _BLOCKER_NEXT_STEPS in the review script), and its
        # --multi-window-gate default fell back to
        # DEFAULT_PROMOTION_MULTI_WINDOW_GATE (a generic, pre-golden2 gate
        # file unrelated to golden2's own evidence) -- so
        # "no_multi_window_candidate_available" could never mean anything
        # golden2-specific. These two steps close that gap.
        golden2_same_window_dir = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "golden2_same_window_candidate_backtests"
        golden2_multi_window_gate_path = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "golden2_multi_window_gate.json"
        commands["golden2_same_window_candidate_backtests"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_golden2_same_window_candidate_backtests.py",
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "golden2_same_window_candidate_backtests.json"),
            "--output-md",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "golden2_same_window_candidate_backtests.md"),
        ]
        commands["golden2_multi_window_gate"] = [
            sys.executable,
            "scripts/evaluate/evaluate_group_a_plus_multi_window_gate.py",
            "--results",
            str(golden2_same_window_dir / "2020_covid.json"),
            str(golden2_same_window_dir / "2022_rate_hike.json"),
            str(golden2_same_window_dir / "live_2024_2026.json"),
            str(golden2_same_window_dir / "active_2025_2026.json"),
            "--output",
            str(golden2_multi_window_gate_path),
        ]
        commands["golden2_promotion_candidate_review"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_golden2_promotion_candidate_review.py",
            "--baseline",
            getattr(args, "promotion_baseline", DEFAULT_PROMOTION_BASELINE),
            "--promotion-gate",
            str(_result_path(f"group_a_plus_promotion_gate_{stamp}.json")),
            "--multi-window-gate",
            str(golden2_multi_window_gate_path),
            "--golden2-same-window-dir",
            str(golden2_same_window_dir),
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "golden2_promotion_candidate_review.json"),
            "--output-md",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "golden2_promotion_candidate_review.md"),
        ]
        commands["multi_window_failure_attribution"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_multi_window_failure_attribution.py",
            "--multi-window-gate",
            getattr(args, "promotion_multi_window_gate", DEFAULT_PROMOTION_MULTI_WINDOW_GATE),
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "multi_window_failure_attribution.json"),
            "--output-md",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "multi_window_failure_attribution.md"),
        ]
        commands["promotion_blocked_diagnostic"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_promotion_blocked_diagnostic.py",
            "--promotion-gate",
            str(_result_path(f"group_a_plus_promotion_gate_{stamp}.json")),
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "promotion_blocked_diagnostic.json"),
            "--output-md",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "promotion_blocked_diagnostic.md"),
        ]
        commands["daily_status_final"] = list(commands["daily_status"])
        output_prefix_index = commands["daily_status_final"].index("--output-prefix") + 1
        commands["daily_status_final"][output_prefix_index] = str(_result_path(f"group_a_plus_daily_status_final_{stamp}"))
        commands["daily_status_final"].extend(
            [
                "--promotion-gate",
                str(_result_path(f"group_a_plus_promotion_gate_{stamp}.json")),
            ]
        )
        status_stage_index = commands["daily_status_final"].index("--status-stage") + 1
        commands["daily_status_final"][status_stage_index] = "final"
        commands["moira_relative_exposure_thesis_shadow"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_relative_exposure_thesis_shadow.py",
            "--live-signal",
            live_signal_path,
            "--as-of",
            as_of,
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_exposure_thesis_shadow.json"),
            "--history-dir",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "relative_exposure_thesis_shadow" / "history"),
            "--log",
            str(PROJECT_ROOT / "results" / "relative_exposure_thesis_shadow_log.jsonl"),
        ]
        commands["moira_hierarchical_credit_review_shadow"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_hierarchical_credit_review_shadow.py",
            "--forecast",
            live_signal_path,
            "--actual",
            live_signal_path,
            "--as-of",
            as_of,
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "hierarchical_credit_review_shadow.json"),
            "--history-dir",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "hierarchical_credit_review_shadow" / "history"),
            "--log",
            str(PROJECT_ROOT / "results" / "hierarchical_credit_review_shadow_log.jsonl"),
        ]
        commands["moira_event_aware_execution_quality_shadow"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_event_aware_execution_quality_shadow.py",
            "--live-signal",
            live_signal_path,
            "--execution-plan",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "execution_plan.json"),
            "--relative-thesis",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_exposure_thesis_shadow.json"),
            "--liquidity-feedback",
            str(
                PROJECT_ROOT
                / "report"
                / "group_a_plus"
                / "latest"
                / "letf_liquidity_feedback_watch_shadow_backtest.json"
            ),
            "--as-of",
            as_of,
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "event_aware_execution_quality_shadow.json"),
            "--history-dir",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "event_aware_execution_quality_shadow" / "history"),
            "--log",
            str(PROJECT_ROOT / "results" / "event_aware_execution_quality_shadow_log.jsonl"),
        ]
        commands["moira_policy_critic_shadow"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_moira_policy_critic_shadow.py",
            "--credit",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "hierarchical_credit_review_shadow.json"),
            "--execution",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "event_aware_execution_quality_shadow.json"),
            "--thesis",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_exposure_thesis_shadow.json"),
            "--as-of",
            as_of,
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "moira_policy_critic_shadow.json"),
            "--history-dir",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "moira_policy_critic_shadow" / "history"),
            "--log",
            str(PROJECT_ROOT / "results" / "moira_policy_critic_shadow_log.jsonl"),
        ]
        commands["moira_policy_critic_validation_shadow"] = [
            sys.executable,
            "scripts/evaluate/validate_group_a_plus_moira_policy_critic_shadow.py",
            "--signal-glob",
            "results/group_a_plus_live_signal_v2_2026*.json",
            "--plan-glob",
            "results/group_a_plus_execution_plan_v2_2026*.json",
            "--as-of",
            as_of,
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "moira_policy_critic_validation_shadow.json"),
            "--history-dir",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "moira_policy_critic_validation_shadow" / "history"),
            "--log",
            str(PROJECT_ROOT / "results" / "moira_policy_critic_validation_shadow_log.jsonl"),
        ]
        commands["moira_execution_guard_hard_stop_backtest_shadow"] = [
            sys.executable,
            "scripts/evaluate/backtest_group_a_plus_moira_execution_guard_hard_stop_shadow.py",
            "--signal-glob",
            "results/group_a_plus_live_signal_v2_2026*.json",
            "--as-of",
            as_of,
            "--output",
            str(
                PROJECT_ROOT
                / "report"
                / "group_a_plus"
                / "latest"
                / "moira_execution_guard_hard_stop_backtest_shadow.json"
            ),
            "--history-dir",
            str(
                PROJECT_ROOT
                / "report"
                / "group_a_plus"
                / "moira_execution_guard_hard_stop_backtest_shadow"
                / "history"
            ),
        ]
        commands["daily_semantic_context_summary"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_daily_semantic_context_summary.py",
            "--live-signal",
            live_signal_path,
            "--signal-alignment",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "signal_alignment.json"),
            "--risk-mechanism",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "risk_mechanism.json"),
            "--watchlist-news",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "watchlist_news.json"),
            "--credit",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "hierarchical_credit_review_shadow.json"),
            "--execution",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "event_aware_execution_quality_shadow.json"),
            "--thesis",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "relative_exposure_thesis_shadow.json"),
            "--critic",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "moira_policy_critic_shadow.json"),
            "--as-of",
            as_of,
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "daily_semantic_context_summary.json"),
            "--history-dir",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "daily_semantic_context_summary" / "history"),
            "--log",
            str(PROJECT_ROOT / "results" / "daily_semantic_context_summary_log.jsonl"),
        ]
        commands["paper_convergence_review"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_paper_convergence_review.py",
            "--as-of",
            as_of,
            "--cvar-cost-window-split",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2606_26625_cvar_cost_window_split.json"),
            "--re-evaluation-gate",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "current_policy_re_evaluation_gate.json"),
            "--auxiliary-task-readiness",
            str(
                PROJECT_ROOT
                / "report"
                / "group_a_plus"
                / "latest"
                / "2608_15841_auxiliary_task_discovery_readiness.json"
            ),
            "--adoption-2609-07946",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07946_adoption_matrix.json"),
            "--promotion-gate-2609-07946",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_07946_complementarity_promotion_gate.json"),
            "--instrument-review-00635u",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "00635u_instrument_review.json"),
            "--adoption-2609-08106",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2609_08106_adoption_matrix.json"),
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "paper_convergence_review.json"),
            "--history-dir",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "paper_convergence_review" / "history"),
        ]
        commands["final_governance_snapshot"] = [
            sys.executable,
            "scripts/evaluate/build_group_a_plus_final_governance_snapshot.py",
            "--daily-status",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "daily_status.json"),
            "--ops-health",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "ops_health.json"),
            "--promotion-gate",
            str(_result_path(f"group_a_plus_promotion_gate_{stamp}.json")),
            "--promotion-blocked-diagnostic",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "promotion_blocked_diagnostic.json"),
            "--multi-window-failure-attribution",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "multi_window_failure_attribution.json"),
            "--panel-drift-triage",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "panel_drift_triage.json"),
            "--panel-drift-resolution-progress",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "panel_drift_resolution_progress.json"),
            "--external-sensitivity-observation-log",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "external_sensitivity_observation_log.json"),
            "--deployment-summary",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "deployment_summary.json"),
            "--output",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "final_governance_snapshot.json"),
            "--output-md",
            str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "final_governance_snapshot.md"),
        ]
    commands["ncf_2330_checklist"] = [
        sys.executable,
        "scripts/report/build_ncf_2330_checklist.py",
        "--mode",
        "daily",
        "--as-of",
        stamp[:4] + "-" + stamp[4:6] + "-" + stamp[6:],
        "--output",
        str(_result_path(f"ncf_2330_checklist_{stamp}.json")),
    ]
    _assert_no_protected_golden_release_output_targets(commands)
    return commands


def parse_args() -> argparse.Namespace:
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date-stamp", default=today.strftime("%Y%m%d"))
    parser.add_argument("--skip-refresh", action="store_true", help="Only run NCF signals and advisory panel.")
    parser.add_argument("--force-refresh", action="store_true", help="Pass --force to refresh_group_data.py.")
    parser.add_argument(
        "--refresh-target-date",
        default="auto",
        help="Target trading date for refresh_group_data.py in YYYY-MM-DD, or auto.",
    )
    parser.add_argument(
        "--strict-refresh",
        action="store_true",
        help="Fail refresh_group_data.py if the provider does not return refresh-target-date.",
    )
    parser.add_argument("--skip-shareholding", action="store_true", help="Skip TDCC shareholding refresh.")
    parser.add_argument("--chip-start", default=(today - timedelta(days=21)).isoformat())
    parser.add_argument("--chip-end", default=today.isoformat())
    parser.add_argument("--per-start", default=(today - timedelta(days=365 * 3)).isoformat())
    parser.add_argument("--val-start", default="2025-01-02")
    parser.add_argument("--val-end", default="latest")
    parser.add_argument("--ohlcv-target-date", default="auto")
    parser.add_argument("--max-ohlcv-lag-days", type=int, default=3)
    parser.add_argument("--fail-on-ohlcv-warning", action="store_true")
    parser.add_argument("--train-start-00631l", default="2020-01-01")
    parser.add_argument("--train-start-00632r", default="2015-01-01")
    parser.add_argument("--train-start-0050", default="2015-01-01")
    parser.add_argument("--train-start-00713", default="2017-09-19")
    parser.add_argument("--train-start-2330", default="2015-01-01")
    parser.add_argument("--skip-ncf-data-validation", action="store_true")
    parser.add_argument("--ncf-max-ohlcv-gap-days", type=int, default=14)
    parser.add_argument(
        "--ncf-2330-feature-mode",
        choices=["pre_open", "after_close"],
        default="after_close",
        help=(
            "Timing mode passed to ncf_2330.py. pre_open uses T-1 Taiwan "
            "close-derived leadership inputs plus US overnight data; after_close "
            "may use same-day Taiwan close-derived inputs."
        ),
    )
    parser.add_argument("--no-external-features", action="store_true")
    parser.add_argument(
        "--refresh-external-cache",
        action="store_true",
        help="Allow NCF scripts to download missing yfinance external features; default is cache-only.",
    )
    parser.add_argument("--checklist-external-start", default=(today - timedelta(days=365 * 3)).isoformat())
    parser.add_argument("--checklist-external-end", default=(today + timedelta(days=1)).isoformat())
    parser.add_argument("--only-refresh", action="store_true", help="Only run data refresh steps, skip NCF models.")
    parser.add_argument(
        "--live-signal-override",
        default=None,
        help=(
            "Override the live signal consumed by downstream governance steps. "
            "Useful for next-session signals named with a _from_<data-date> suffix."
        ),
    )
    parser.add_argument("--skip-promotion-gate", action="store_true", help="Skip GroupA+ promotion governance gate.")
    parser.add_argument("--promotion-baseline", default=DEFAULT_PROMOTION_BASELINE)
    parser.add_argument("--promotion-candidates", nargs="+", default=list(DEFAULT_PROMOTION_CANDIDATES))
    parser.add_argument(
        "--active-ncf-00631l-panel",
        default=resolve_ncf_00631l_panel_path(PROJECT_ROOT, fallback=DEFAULT_ACTIVE_NCF_00631L_PANEL),
        help="Baseline 00631L NCF panel for daily drift audit against the newly generated panel.",
    )
    parser.add_argument(
        "--promotion-drift-audit",
        default=None,
        help="Override the drift audit consumed by promotion_gate; defaults to today's generated panel drift audit.",
    )
    parser.add_argument("--promotion-multi-window-gate", default=DEFAULT_PROMOTION_MULTI_WINDOW_GATE)
    parser.add_argument(
        "--dfl-shadow-result",
        default="results/a2118_decision_focused_action_shadow_dfl_main_latest.json",
        help="Fixed A21.18 DFL shadow result consumed by the active-date audit step.",
    )
    parser.add_argument(
        "--dfl-advisory-input",
        default="results/a2118_decision_focused_action_shadow_dfl_main_latest.json",
        help="Base A21.18 DFL result consumed by the advisory snapshot step.",
    )
    parser.add_argument(
        "--dfl-selective-p50-input",
        default="results/a2118_decision_focused_action_shadow_dfl_selective_p50_latest.json",
        help="Selective p50 A21.18 DFL result consumed by the advisory snapshot step.",
    )
    parser.add_argument(
        "--dfl-selective-p70-input",
        default="results/a2118_decision_focused_action_shadow_dfl_selective_p70_latest.json",
        help="Selective p70 A21.18 DFL result consumed by the advisory snapshot step.",
    )
    parser.add_argument(
        "--dfl-overlap-result",
        default="results/a2118_decision_focused_action_overlap_dfl_latest.json",
        help="Existing-guard overlap result consumed by the DFL active-date audit step.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    parser.add_argument("--skip-commentary", action="store_true", help="Skip LLM commentary generation.")
    parser.add_argument("--commentary-provider", default="auto",
                        choices=["auto", "minimax", "anthropic", "template"],
                        help="Commentary provider (default: auto → minimax → anthropic → template).")
    parser.add_argument("--commentary-api-key", default=None,
                        help="API key for commentary provider (overrides env vars).")
    return parser.parse_args()


def run_pipeline_commands(
    commands: dict[str, list[str]],
    *,
    date_stamp: str,
    dry_run: bool,
    refresh_external_cache: bool,
    log_path: Path,
) -> list[str]:
    """Execute the daily pipeline's step sequence in order.

    Returns the list of successfully completed step names. A best-effort
    step (BEST_EFFORT_STEP_NAMES) that fails is logged and skipped; a
    critical step that fails writes a partial "failed" manifest, sends a
    best-effort push notification (daily_signal/alert_state never ran to do
    it themselves), and re-raises subprocess.CalledProcessError.
    """
    log_path.parent.mkdir(exist_ok=True)
    total = len(commands)
    completed_steps: list[str] = []
    with open(log_path, "a", encoding="utf-8") as log_fh:
        for i, (name, cmd) in enumerate(commands.items(), 1):
            pct_start = int((i - 1) / total * 100)
            pct_done  = int(i / total * 100)
            msg_start = f"[{i}/{total}] {name}  ({pct_start}%)"
            msg_done  = f"  ✓ 完成 ({pct_done}%)"
            print(msg_start, flush=True)
            log_fh.write(msg_start + "\n"); log_fh.flush()
            env_extra = {"NCF_EXTERNAL_ALLOW_DOWNLOAD": "1"} if refresh_external_cache and name.startswith("ncf_") else None
            try:
                _run(cmd, dry_run=dry_run, env_extra=env_extra, log_fh=log_fh)
            except subprocess.CalledProcessError as exc:
                if dry_run:
                    raise
                if name in BEST_EFFORT_STEP_NAMES:
                    msg_fail = f"  [WARNING] {name} failed (non-fatal, best-effort refresh step): {exc}"
                    print(msg_fail, flush=True)
                    log_fh.write(msg_fail + "\n"); log_fh.flush()
                else:
                    msg_fail = f"  [CRITICAL] {name} failed: {exc}"
                    print(msg_fail, flush=True)
                    log_fh.write(msg_fail + "\n"); log_fh.flush()
                    manifest_path = _write_failed_manifest(
                        date_stamp, failed_step=name, error=str(exc), completed_steps=completed_steps
                    )
                    print(f"Partial manifest (failed): {manifest_path}")
                    _notify_pipeline_failure(date_stamp, name, str(exc))
                    raise
            else:
                print(msg_done, flush=True)
                log_fh.write(msg_done + "\n"); log_fh.flush()
                completed_steps.append(name)
    return completed_steps


def _pipeline_db_path(args: argparse.Namespace) -> Path:
    raw = getattr(args, "db", None)
    if raw:
        return Path(raw).resolve()
    from backtest_group_a_plus_switch_policy import DB_PATH

    return Path(DB_PATH).resolve()


def main() -> None:
    args = parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    commands = build_commands(args)

    log_path = PROJECT_ROOT / "logs" / "daily.log"
    run_pipeline_commands(
        commands,
        date_stamp=args.date_stamp,
        dry_run=args.dry_run,
        refresh_external_cache=args.refresh_external_cache,
        log_path=log_path,
    )

    manifest_path = _result_path(f"ncf_daily_pipeline_{args.date_stamp}.json")
    if args.dry_run:
        print(f"\nDry run only. Manifest would be written to: {manifest_path}")
        return

    outputs = {
        "ohlcv_freshness": str(_result_path(f"ohlcv_freshness_{args.date_stamp}.json")),
    }
    live_signal_output = getattr(args, "live_signal_override", None) or str(
        _result_path(f"group_a_plus_live_signal_v2_{args.date_stamp}.json")
    )
    if not args.skip_refresh:
        outputs["data_refresh"] = str(_result_path(f"data_refresh_{args.date_stamp}.json"))
    if not args.only_refresh:
        outputs.update(
            {
                "ncf_00631l": str(_result_path(f"ncf_00631l_latest_{args.date_stamp}.json")),
                "ncf_00632r": str(_result_path(f"ncf_00632r_latest_{args.date_stamp}.json")),
                "ncf_0050": str(_result_path(f"ncf_0050_latest_{args.date_stamp}.json")),
                "ncf_00713": str(_result_path(f"ncf_00713_latest_{args.date_stamp}.json")),
                "panel_00631l": str(_result_path(f"ncf_00631l_panel_latest_{args.date_stamp}.csv")),
                "panel_00632r": str(_result_path(f"ncf_00632r_panel_latest_{args.date_stamp}.csv")),
                "panel_0050": str(_result_path(f"ncf_0050_panel_latest_{args.date_stamp}.csv")),
                "panel_00713": str(_result_path(f"ncf_00713_panel_latest_{args.date_stamp}.csv")),
                "panel_2330": str(_result_path(f"ncf_2330_panel_latest_{args.date_stamp}.csv")),
                "ncf_panel_manifest": str(_result_path(f"ncf_panel_manifest_{args.date_stamp}.json")),
                "ncf_0050_threshold_eval": str(_result_path(f"ncf_0050_threshold_eval_{args.date_stamp}.json")),
                "ncf_0050_threshold_eval_md": str(_result_path(f"ncf_0050_threshold_eval_{args.date_stamp}.md")),
                "auxiliary_policy_lift_shadow_2608_15841": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_existing_aux_heads_policy_lift_shadow.json"
                ),
                "auxiliary_churn_shadow_2608_15841": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_auxiliary_churn_shadow.json"
                ),
                "auxiliary_churn_shadow_2608_15841_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_auxiliary_churn_shadow.md"
                ),
                "auxiliary_task_discovery_readiness_2608_15841": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_auxiliary_task_discovery_readiness.json"
                ),
                "auxiliary_task_discovery_readiness_2608_15841_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_auxiliary_task_discovery_readiness.md"
                ),
                "auxiliary_purged_walkforward_2608_15841": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_auxiliary_purged_walkforward.json"
                ),
                "auxiliary_purged_walkforward_2608_15841_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_auxiliary_purged_walkforward.md"
                ),
                "auxiliary_regime_decay_audit_2608_15841": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_auxiliary_regime_decay_audit.json"
                ),
                "auxiliary_regime_decay_audit_2608_15841_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_auxiliary_regime_decay_audit.md"
                ),
                "auxiliary_lifecycle_audit_2608_15841": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_auxiliary_lifecycle_audit.json"
                ),
                "auxiliary_lifecycle_audit_2608_15841_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_auxiliary_lifecycle_audit.md"
                ),
                "delayed_credit_audit_2608_15841": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_delayed_credit_audit.json"
                ),
                "delayed_credit_audit_2608_15841_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_delayed_credit_audit.md"
                ),
                "candidate_auxiliary_bank_blueprint_2608_15841": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_candidate_auxiliary_bank_blueprint.json"
                ),
                "candidate_auxiliary_bank_blueprint_2608_15841_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_15841_candidate_auxiliary_bank_blueprint.md"
                ),
                "capacity_crowding_readiness_2608_08405": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_08405_capacity_crowding_readiness.json"
                ),
                "capacity_crowding_readiness_2608_08405_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_08405_capacity_crowding_readiness.md"
                ),
                "capacity_grid_shadow_2608_08405": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_capacity_grid_shadow.json"
                ),
                "capacity_grid_shadow_2608_08405_md": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2608_08405_capacity_grid_shadow.md"
                ),
                "erosion_persistence_shadow_2608_08405": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_08405_erosion_persistence_shadow.json"
                ),
                "erosion_persistence_shadow_2608_08405_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_08405_erosion_persistence_shadow.md"
                ),
                "instrument_readiness_shadow_2608_08405": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_08405_instrument_readiness_shadow.json"
                ),
                "instrument_readiness_shadow_2608_08405_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_08405_instrument_readiness_shadow.md"
                ),
                "ramp_path_dependence_shadow_2608_08405": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_08405_ramp_path_dependence_shadow.json"
                ),
                "ramp_path_dependence_shadow_2608_08405_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_08405_ramp_path_dependence_shadow.md"
                ),
                "assigned_realized_deployment_shadow_2608_08405": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_08405_assigned_realized_deployment_shadow.json"
                ),
                "assigned_realized_deployment_shadow_2608_08405_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2608_08405_assigned_realized_deployment_shadow.md"
                ),
                "00632r_discipline_guard": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "00632r_discipline_guard.json"
                ),
                "00632r_discipline_guard_md": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "00632r_discipline_guard.md"
                ),
                "ncf_panel_drift": str(_result_path(f"ncf_panel_drift_active_vs_{args.date_stamp}.json")),
                "ncf_panel_drift_csv": str(_result_path(f"ncf_panel_drift_active_vs_{args.date_stamp}.csv")),
                "panel_drift_triage": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "panel_drift_triage.json"
                ),
                "external_sensitivity_observation_log": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "external_sensitivity_observation_log.json"
                ),
                "panel_drift_resolution_progress": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "panel_drift_resolution_progress.json"
                ),
                "ncf_panel_coverage": str(_result_path(f"ncf_panel_coverage_{args.date_stamp}.json")),
                "advisory_panel": str(_result_path(f"ncf_advisory_panel_latest_{args.date_stamp}.csv")),
                "factor_lens": str(_result_path(f"group_a_plus_factor_lens_{args.date_stamp}.json")),
                "research_governance_gate": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "research_governance_gate.json"
                ),
                "research_governance_gate_md": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "research_governance_gate.md"
                ),
                "shadow_artifact_registry": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "shadow_artifact_registry.json"
                ),
                "shadow_artifact_registry_md": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "shadow_artifact_registry.md"
                ),
                "latest_strategy_explain_snapshot": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "group_a_plusplus_latest_strategy_explain_snapshot.json"
                ),
                "latest_strategy_explain_snapshot_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "group_a_plusplus_latest_strategy_explain_snapshot.md"
                ),
                "data_freshness_gate": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "data_freshness_gate.json"
                ),
                "data_freshness_gate_md": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "data_freshness_gate.md"
                ),
                "ncf_panel_drift_auto_attribution": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "ncf_panel_drift_auto_attribution.json"
                ),
                "ncf_panel_drift_auto_attribution_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "ncf_panel_drift_auto_attribution.md"
                ),
                "golden_release_separation_audit": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "golden_release_separation_audit.json"
                ),
                "golden_release_separation_audit_md": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "golden_release_separation_audit.md"
                ),
                "live_signal": live_signal_output,
                "riccati_mv_shadow": str(_result_path(f"riccati_mv_shadow_{args.date_stamp}.json")),
                "riccati_mv_shadow_latest": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "riccati_mv_shadow.json"
                ),
                "current_policy_re_evaluation_gate": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "current_policy_re_evaluation_gate.json"
                ),
                "current_policy_re_evaluation_gate_md": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "current_policy_re_evaluation_gate.md"
                ),
                "ctbc_debounce_shadow_2509_02986": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2509_02986_ctbc_debounce_shadow.json"
                ),
                "ctbc_debounce_shadow_2509_02986_md": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "2509_02986_ctbc_debounce_shadow.md"
                ),
                "ctbc_00713_debounce_shadow_2509_02986": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2509_02986_ctbc_00713_debounce_shadow.json"
                ),
                "ctbc_00713_debounce_shadow_2509_02986_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2509_02986_ctbc_00713_debounce_shadow.md"
                ),
                "ctbc_00713_domain_randomization_2509_02986": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2509_02986_ctbc_00713_domain_randomization.json"
                ),
                "ctbc_00713_domain_randomization_2509_02986_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2509_02986_ctbc_00713_domain_randomization.md"
                ),
                "ctbc_promotion_readiness_gate_2509_02986": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2509_02986_ctbc_promotion_readiness_gate.json"
                ),
                "ctbc_promotion_readiness_gate_2509_02986_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2509_02986_ctbc_promotion_readiness_gate.md"
                ),
                "ctbc_groupa_plusplus_review_2509_02986": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2509_02986_ctbc_groupa_plusplus_review.json"
                ),
                "ctbc_groupa_plusplus_review_2509_02986_md": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "2509_02986_ctbc_groupa_plusplus_review.md"
                ),
                "compounding_regime": str(_result_path(f"00631l_leveraged_compounding_regime_{args.date_stamp}.json")),
                "compounding_regime_csv": str(_result_path(f"00631l_leveraged_compounding_regime_{args.date_stamp}.csv")),
                "gjr_garch_shadow": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gjr_garch_shadow.json"
                ),
                "daily_status": str(_result_path(f"group_a_plus_daily_status_{args.date_stamp}.json")),
                "daily_status_pointer": str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "daily_status.json"),
                "securities_lending_0050_source_status": str(
                    PROJECT_ROOT
                    / "report"
                    / "group_a_plus"
                    / "latest"
                    / "securities_lending_0050_source_status.json"
                ),
                "deployment_summary": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "deployment_summary.json"
                ),
                "gift_signed_approval_checklist_review": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gift_signed_approval_checklist_review.json"
                ),
                "gift_signed_approval_validator_smoke": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gift_signed_approval_validator_smoke.json"
                ),
                "gift_pdf_advantage_coverage_review": str(
                    PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "gift_pdf_advantage_coverage_review.json"
                ),
                "ncf_2330_checklist": str(_result_path(f"ncf_2330_checklist_{args.date_stamp}.json")),
            }
        )
        if not args.skip_promotion_gate:
            outputs["promotion_gate"] = str(_result_path(f"group_a_plus_promotion_gate_{args.date_stamp}.json"))
            outputs["golden2_same_window_candidate_backtests"] = str(
                PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "golden2_same_window_candidate_backtests.json"
            )
            outputs["golden2_multi_window_gate"] = str(
                PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "golden2_multi_window_gate.json"
            )
            outputs["golden2_promotion_candidate_review"] = str(
                PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "golden2_promotion_candidate_review.json"
            )
            outputs["multi_window_failure_attribution"] = str(
                PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "multi_window_failure_attribution.json"
            )
            outputs["promotion_blocked_diagnostic"] = str(
                PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "promotion_blocked_diagnostic.json"
            )
            outputs["daily_status_final"] = str(_result_path(f"group_a_plus_daily_status_final_{args.date_stamp}.json"))
            outputs["final_governance_snapshot"] = str(
                PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "final_governance_snapshot.json"
            )
        if args.refresh_external_cache:
            outputs["ncf_2330_checklist_external_cache"] = str(
                _result_path(f"ncf_2330_checklist_external_cache_{args.date_stamp}.json")
            )

    summary = {
        "date_stamp": args.date_stamp,
        "mode": "refresh_only" if args.only_refresh else "full",
        "outputs": outputs,
    }
    if not args.only_refresh:
        summary["signals"] = {
            "00631L": _signal_summary(_result_path(f"ncf_00631l_latest_{args.date_stamp}.json")),
            "00632R": _signal_summary(_result_path(f"ncf_00632r_latest_{args.date_stamp}.json")),
            "0050": _signal_summary(_result_path(f"ncf_0050_latest_{args.date_stamp}.json")),
            "00713": _signal_summary(_result_path(f"ncf_00713_latest_{args.date_stamp}.json")),
        }
    manifest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\nNCF daily pipeline complete")
    if args.only_refresh:
        print("  refresh-only mode: NCF signal generation skipped")
    else:
        for ticker, signal in summary["signals"].items():
            print(
                f"  {ticker}: {signal['direction']} "
                f"prob_up={signal['probability_up']} "
                f"freshness={signal['data_freshness_status']} "
                f"date={signal['last_close_date']}"
            )
    print(f"Manifest: {manifest_path}")

    print("\n[env-health]")
    try:
        from group_a_plus.operations.strategy_env import DEFAULT_OUTPUT_PATH, build_strategy_env_health

        env_health = build_strategy_env_health()
        DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        backup_latest_pointer_before_overwrite(DEFAULT_OUTPUT_PATH)
        DEFAULT_OUTPUT_PATH.write_text(json.dumps(env_health, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        canonical_env_path = write_json_report(
            output_path("strategy_env_health", kind="pipeline", run_mode="production", latest=True),
            artifact_name="strategy_env_health",
            kind="pipeline",
            run_mode="production",
            payload=env_health,
        )
        print(
            "  "
            f"status={env_health.get('status')} "
            f"missing_files={len(env_health.get('missing_files', []))} "
            f"warnings={len(env_health.get('warnings', []))}"
        )
        print("  Saved → report/group_a_plus/latest/strategy_env_health.json")
        print(f"  Canonical → {canonical_env_path.relative_to(PROJECT_ROOT)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Environment health check failed (non-fatal): {exc}")

    print("\n[ops-health]")
    try:
        from group_a_plus.operations.ops_health import DEFAULT_OUTPUT_PATH, build_ops_health

        ops_health = build_ops_health()
        DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        backup_latest_pointer_before_overwrite(DEFAULT_OUTPUT_PATH)
        DEFAULT_OUTPUT_PATH.write_text(json.dumps(ops_health, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        canonical_ops_path = write_json_report(
            output_path("ops_health", kind="pipeline", run_mode="production", latest=True),
            artifact_name="ops_health",
            kind="pipeline",
            run_mode="production",
            payload=ops_health,
        )
        print(
            "  "
            f"status={ops_health.get('status')} "
            f"errors={len(ops_health.get('errors', []))} "
            f"warnings={len(ops_health.get('warnings', []))}"
        )
        print("  Saved → report/group_a_plus/latest/ops_health.json")
        print(f"  Canonical → {canonical_ops_path.relative_to(PROJECT_ROOT)}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Ops health check failed (non-fatal): {exc}")

    if args.only_refresh:
        print("\nRefresh-only mode complete; skipped commentary, watchlist news, signal alignment, and alert state.")
        return

    # --- LLM commentary (optional) ---
    if not args.skip_commentary:
        print("\n[commentary]")
        try:
            from group_a_plus.integrations.llm_commentary import generate_commentary
            ncf_path = _result_path(f"ncf_00631l_latest_{args.date_stamp}.json")
            commentary = generate_commentary(
                ncf_signal_path=ncf_path,
                provider=args.commentary_provider,
                api_key=args.commentary_api_key,
                signal_date=args.date_stamp[:4] + "-" + args.date_stamp[4:6] + "-" + args.date_stamp[6:],
            )
            mode = commentary.get("mode", "?")
            print(f"  [{mode}] {commentary.get('headline', '')}")
            print(f"  去槓桿: {commentary.get('signal_interpretation', {}).get('deleverage_status', '?')}")
            if "_saved_to" in commentary:
                print(f"  Saved → {commentary['_saved_to']}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARNING] Commentary failed (non-fatal): {exc}")

    print("\n[watchlist-news]")
    signal_date_str = args.date_stamp[:4] + "-" + args.date_stamp[4:6] + "-" + args.date_stamp[6:]

    # 2026-08-17: LTN was the nominal DEFAULT_NEWS_GLOB source in
    # watchlist_news.py but was never actually re-scraped by any scheduled
    # step -- news/ltn_mainstream_*.jsonl only had whatever manual one-off
    # runs happened to produce, and went stale for weeks at a time (see the
    # FinMind fallback comment below, added 2026-07-07 for exactly this
    # reason). This closes that gap by scraping a rolling few-day window
    # every day, same non-fatal pattern as the FinMind step.
    try:
        from fetch_ltn_news_jsonl import fetch_search_results as _ltn_fetch_search_results, write_jsonl as _ltn_write_jsonl

        _ltn_end = date.fromisoformat(signal_date_str)
        _ltn_start = _ltn_end - timedelta(days=3)
        _ltn_keywords = ("台股", "股市", "0050", "00631L", "台積電")
        _ltn_rows: list[dict] = []
        _ltn_seen_urls: set[str] = set()
        for _ltn_keyword in _ltn_keywords:
            _kw_rows = _ltn_fetch_search_results(
                keyword=_ltn_keyword,
                start_date=_ltn_start.isoformat(),
                end_date=_ltn_end.isoformat(),
                news_type="all",
                max_pages=15,
                timeout=30,
                sleep_ms=200,
            )
            for _row in _kw_rows:
                _url = _row.get("url", "")
                if _url and _url in _ltn_seen_urls:
                    continue
                if _url:
                    _ltn_seen_urls.add(_url)
                _ltn_rows.append(_row)
        _ltn_rolling_path = PROJECT_ROOT / "news" / "ltn_mainstream_rolling.jsonl"
        _ltn_write_jsonl(_ltn_rows, _ltn_rolling_path)
        print(f"  [ltn-news] {len(_ltn_rows)} articles -> {_ltn_rolling_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] LTN news refresh failed (non-fatal): {exc}")

    # 2026-08-17: Yahoo's native RSS feeds carry real, non-empty article-lead
    # snippets (unlike FinMind, which is title-only), making them a genuinely
    # complementary source rather than a redundant one.
    try:
        from scripts.fetch.fetch_yahoo_news_rss import fetch_all as _yahoo_fetch_all, write_jsonl as _yahoo_write_jsonl

        _yahoo_rows, _yahoo_errors = _yahoo_fetch_all()
        _yahoo_rolling_path = PROJECT_ROOT / "news" / "yahoo_news_rss_rolling.jsonl"
        _yahoo_write_jsonl(_yahoo_rows, _yahoo_rolling_path)
        print(f"  [yahoo-news] {len(_yahoo_rows)} articles -> {_yahoo_rolling_path}")
        for _yahoo_err in _yahoo_errors:
            print(f"  [yahoo-news] WARNING: {_yahoo_err}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Yahoo news refresh failed (non-fatal): {exc}")

    # 2026-08-17: SETN's own search page is a client-side-rendered SPA (empty
    # static HTML), so this goes through Google News RSS's site: filter
    # instead -- see scripts/fetch/fetch_setn_news_rss.py module docstring.
    try:
        from scripts.fetch.fetch_setn_news_rss import fetch_all as _setn_fetch_all, write_jsonl as _setn_write_jsonl

        _setn_rows, _setn_errors = _setn_fetch_all(lookback_days=3)
        _setn_rolling_path = PROJECT_ROOT / "news" / "setn_news_rss_rolling.jsonl"
        _setn_write_jsonl(_setn_rows, _setn_rolling_path)
        print(f"  [setn-news] {len(_setn_rows)} articles -> {_setn_rolling_path}")
        for _setn_err in _setn_errors:
            print(f"  [setn-news] WARNING: {_setn_err}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] SETN news refresh failed (non-fatal): {exc}")

    try:
        from scripts.fetch.fetch_finmind_stock_news import (
            DEFAULT_OUT_DIR as _FINMIND_NEWS_DIR,
            fetch_range as _finmind_fetch_range,
            write_jsonl as _finmind_write_jsonl,
        )

        _finmind_end = date.fromisoformat(signal_date_str)
        _finmind_start = _finmind_end - timedelta(days=10)
        _finmind_tickers = [t for t in DEFAULT_TICKERS if t.endswith(".TW") or t.endswith(".TWO")]
        _finmind_rows, _finmind_stop = _finmind_fetch_range(
            _finmind_tickers,
            start=_finmind_start,
            end=_finmind_end,
            token=os.environ.get("FINMIND_API_TOKEN", ""),
        )
        _finmind_rolling_path = _FINMIND_NEWS_DIR / "finmind_stock_news_rolling.jsonl"
        _finmind_write_jsonl(_finmind_rows, _finmind_rolling_path)
        print(f"  [finmind-news] {len(_finmind_rows)} articles -> {_finmind_rolling_path}")
        if _finmind_stop:
            print(f"  [finmind-news] WARNING: {_finmind_stop}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] FinMind news refresh failed (non-fatal): {exc}")

    # 2026-08-22: build_finbert_sentiment_features.py was never wired into the
    # daily pipeline, so FinRL/data/sentiment/finbert_market_sentiment_daily.csv
    # went stale (frozen since 2026-06-29). finbert.py's freshness decay then
    # zeroed the feature's risk contribution AND flipped ops_health's
    # module_health sub-status to "warning" every day, which in turn made
    # strategy_trust_gate.classify_strategy_trust() ABSTAIN unconditionally
    # (see project_fable_00631l_direction_8_20260822 memory). Rebuild the whole
    # CSV from the news/ directory (proxy scoring mode, no model download,
    # ~15s for the full 2020-2026 archive) so this stays fresh going forward.
    try:
        from build_finbert_sentiment_features import (
            DEFAULT_OUTPUT as _FINBERT_OUTPUT,
            build_finbert_daily_features as _finbert_build_daily,
        )
        from build_llm_sentiment_features import read_input_source as _finbert_read_input

        _finbert_table = _finbert_read_input(PROJECT_ROOT / "news")
        _finbert_daily = _finbert_build_daily(_finbert_table, scoring_mode="proxy")
        _FINBERT_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        _finbert_daily.to_csv(_FINBERT_OUTPUT, index=False, encoding="utf-8")
        print(
            f"  [finbert-sentiment] {len(_finbert_daily)} daily rows -> {_FINBERT_OUTPUT} "
            f"(latest={_finbert_daily['date'].iloc[-1] if len(_finbert_daily) else 'n/a'})"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] FinBERT sentiment feature rebuild failed (non-fatal): {exc}")

    try:
        from group_a_plus.integrations.watchlist_news import (
            DEFAULT_OUTPUT_PATH as _WATCHLIST_NEWS_OUTPUT,
            write_watchlist_news_summary,
        )

        news_summary = write_watchlist_news_summary(signal_date=signal_date_str)
        print(
            "  "
            f"articles={news_summary.get('article_count', 0)} "
            f"fallback={news_summary.get('fallback_used', False)}"
        )
        print("  Saved → report/group_a_plus/latest/watchlist_news.json")

        if news_summary.get("article_count", 0) == 0:
            # DEFAULT_NEWS_GLOBS (LTN + Yahoo + SETN, all refreshed daily above
            # as of 2026-08-17) can still all miss the watchlist's keyword match
            # for a given day even when individually non-empty (2026-07-07 Fable
            # audit found LTN alone going 8 days stale before these three were
            # added). FinMind's already ticker-tagged news dataset is fetched
            # automatically above, so fall back to it rather than shipping an
            # empty watchlist_news.json to lm_dictionary_sentiment/signal_alignment/
            # llm_commentary.
            from scripts.run.build_finmind_watchlist_news import build_finmind_watchlist_news_summary

            finmind_summary = build_finmind_watchlist_news_summary(
                signal_date=signal_date_str,
                news_glob="news/finmind_stock_news_rolling.jsonl",
            )
            if finmind_summary.get("article_count", 0) > 0:
                _WATCHLIST_NEWS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
                backup_latest_pointer_before_overwrite(_WATCHLIST_NEWS_OUTPUT)
                _WATCHLIST_NEWS_OUTPUT.write_text(
                    json.dumps(finmind_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                )
                print(
                    "  [fallback→finmind] "
                    f"articles={finmind_summary.get('article_count', 0)} "
                    "(primary LTN source was empty)"
                )
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Watchlist news summary failed (non-fatal): {exc}")

    print("\n[signal-alignment]")
    try:
        from group_a_plus.integrations.signal_alignment import (
            DEFAULT_LIVE_SIGNAL_PATH,
            DEFAULT_OUTPUT_PATH,
            build_signal_alignment_from_file,
        )

        alignment = build_signal_alignment_from_file(DEFAULT_LIVE_SIGNAL_PATH, output_path=DEFAULT_OUTPUT_PATH)
        print(
            "  "
            f"alignment={alignment.get('alignment')} "
            f"dominant={alignment.get('dominant_direction')} "
            f"penalty={alignment.get('confidence_penalty')}"
        )
        print("  Saved → report/group_a_plus/latest/signal_alignment.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Signal alignment failed (non-fatal): {exc}")

    print("\n[crash-risk-alert]")
    try:
        from scripts.run.build_00631l_crash_risk_alert import DEFAULT_OUTPUT, build_crash_risk_alert, write_crash_risk_alert

        crash_alert = build_crash_risk_alert(db_path=_pipeline_db_path(args), feature_start="2016-01-04", as_of="latest")
        write_crash_risk_alert(crash_alert, output_path=DEFAULT_OUTPUT)
        print(
            "  "
            f"as_of={crash_alert.get('as_of')} "
            f"watch_level={crash_alert.get('watch_level')} "
            f"score={crash_alert.get('category_score')} "
            f"active={crash_alert.get('alert_active')}"
        )
        print("  Saved → report/group_a_plus/latest/crash_risk_alert.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Crash-risk alert build failed (non-fatal): {exc}")

    # 2026-08-06, arXiv:2607.28127-motivated ("FinSMART") shadow diagnostic --
    # see research/shadow/FINSMART_LITE_MARKET_ALIGNED_SENTIMENT_SHADOW_DESIGN_20260806.md.
    # research_only: true, production_effect: none -- never read by
    # daily_signal.py. Forces as_of to today's live_signal actual_data_date
    # (not "latest available news date") so a stale prior day's sentiment is
    # never silently reported as today's -- same anti-staleness-masking
    # convention as crash_alert below.
    print("\n[market-aligned-sentiment-shadow]")
    try:
        from scripts.evaluate.build_market_aligned_sentiment_shadow import run_and_write as _run_sentiment_shadow

        _live_signal_path = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal.json"
        _live_signal_envelope = json.loads(_live_signal_path.read_text(encoding="utf-8-sig"))
        _as_of_for_sentiment = str((_live_signal_envelope.get("data") or {}).get("actual_data_date") or "")

        sentiment_shadow_payload = _run_sentiment_shadow(as_of=_as_of_for_sentiment or None)
        print(
            "  "
            f"date={sentiment_shadow_payload.get('date')} "
            f"dropped_duplicates={sentiment_shadow_payload.get('dropped_duplicate_count')}/"
            f"{sentiment_shadow_payload.get('raw_headline_count')}"
        )
        print("  Saved → report/group_a_plus/latest/market_aligned_sentiment_shadow.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Market-aligned sentiment shadow build failed (non-fatal): {exc}")

    # 2026-08-01 user proposal: split "fast crash" from "persistent
    # drawdown" risk mechanisms instead of letting total_risk_score alone
    # (already flagged as fragile near its threshold, see the 2026-07-26 SPO
    # robustness checklist) stand in for both. Diagnostic/event-attribution
    # only -- see group_a_plus/integrations/risk_mechanism_classifier.py's
    # docstring for the arbitration policy (never feeds target_weights).
    # Reuses market_state (just written by the daily_signal step above) and
    # crash_risk_alert (just written above) rather than recomputing
    # overnight/skew/margin features.
    print("\n[risk-mechanism-classifier]")
    try:
        from group_a_plus.integrations.risk_mechanism_classifier import (
            append_risk_mechanism_shadow_log,
            classify_risk_mechanism,
            load_market_state_history_before,
        )

        live_signal_path = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "live_signal.json"
        live_signal_envelope = json.loads(live_signal_path.read_text(encoding="utf-8-sig"))
        # daily_signal.py writes through OutputStandardizer, so the actual
        # frame is nested under "data" (envelope: success/data/metadata/error).
        live_signal_payload = live_signal_envelope.get("data") or {}
        market_state_today = live_signal_payload.get("market_state") or {}
        as_of_date = str(live_signal_payload.get("actual_data_date") or "")

        crash_alert_path = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "crash_risk_alert.json"
        crash_alert_today = None
        if crash_alert_path.exists():
            crash_alert_payload = json.loads(crash_alert_path.read_text(encoding="utf-8-sig"))
            # Only trust this as today's evidence if its as_of matches
            # today's live_signal actual_data_date -- a stale (e.g.
            # yesterday's, if the crash-risk-alert step above failed) file
            # must not be read as if it were fresh. Same staleness-masking
            # bug class already fixed in ops_health/panel-drift elsewhere.
            if crash_alert_payload.get("as_of") == as_of_date:
                crash_alert_today = crash_alert_payload

        sentiment_shadow_path = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "market_aligned_sentiment_shadow.json"
        sentiment_shadow_today = None
        if sentiment_shadow_path.exists():
            sentiment_shadow_payload = json.loads(sentiment_shadow_path.read_text(encoding="utf-8-sig"))
            # Same staleness-masking guard as crash_alert above -- only trust
            # this as today's evidence if its date matches actual_data_date.
            if sentiment_shadow_payload.get("date") == as_of_date:
                sentiment_shadow_today = sentiment_shadow_payload

        market_state_log = RESULTS_DIR / "market_state_shadow_log.jsonl"
        history = load_market_state_history_before(market_state_log, as_of_date) if as_of_date else []

        risk_mechanism = classify_risk_mechanism(
            market_state_today, crash_alert_today, history, sentiment_shadow=sentiment_shadow_today
        )
        if as_of_date:
            append_risk_mechanism_shadow_log(
                RESULTS_DIR / "risk_mechanism_shadow_log.jsonl", risk_mechanism, date=as_of_date
            )
        risk_mechanism_output = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "risk_mechanism.json"
        risk_mechanism_output.parent.mkdir(parents=True, exist_ok=True)
        backup_latest_pointer_before_overwrite(risk_mechanism_output)
        risk_mechanism_output.write_text(
            json.dumps({"as_of": as_of_date, **risk_mechanism}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  as_of={as_of_date} mechanism={risk_mechanism['mechanism']}")
        print("  Saved → report/group_a_plus/latest/risk_mechanism.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Risk mechanism classifier failed (non-fatal): {exc}")

    # 2026-08-02 user proposal ("strategy trust gate"): diagnostic-only,
    # shadow-logging composition of risk_mechanism (above), signal_alignment,
    # and ops_health's data-quality sub-statuses into a coarse
    # TRUST/SHADOW_ONLY/ABSTAIN label. See
    # group_a_plus/integrations/strategy_trust_gate.py's docstring for why
    # this deliberately does NOT implement the user's full 7-input
    # calibration/RankIC/action-value score (each of those inputs has a
    # documented OOS-failure or noise history in this codebase). Same
    # arbitration policy as risk_mechanism_classifier.py: never feeds
    # target_weights/execution_regime until an out-of-sample evaluation via
    # scripts/evaluate/evaluate_model_trust_gate.py exists and passes.
    print("\n[strategy-trust-gate]")
    try:
        from group_a_plus.integrations.strategy_trust_gate import (
            append_strategy_trust_shadow_log,
            classify_strategy_trust,
        )

        signal_alignment_path = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "signal_alignment.json"
        signal_alignment_today: dict[str, Any] = {}
        if signal_alignment_path.exists():
            signal_alignment_payload = json.loads(signal_alignment_path.read_text(encoding="utf-8-sig"))
            # Same staleness-masking guard as crash_alert above: only trust
            # this as today's evidence if its signal_date matches today.
            if signal_alignment_payload.get("signal_date") == as_of_date:
                signal_alignment_today = signal_alignment_payload

        ops_health_path = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "ops_health.json"
        ops_health_today: dict[str, Any] | None = None
        if ops_health_path.exists():
            ops_health_today = json.loads(ops_health_path.read_text(encoding="utf-8-sig"))

        strategy_trust = classify_strategy_trust(risk_mechanism, signal_alignment_today, ops_health_today)
        if as_of_date:
            append_strategy_trust_shadow_log(
                RESULTS_DIR / "strategy_trust_shadow_log.jsonl", strategy_trust, date=as_of_date
            )
        strategy_trust_output = PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "strategy_trust.json"
        strategy_trust_output.parent.mkdir(parents=True, exist_ok=True)
        backup_latest_pointer_before_overwrite(strategy_trust_output)
        strategy_trust_output.write_text(
            json.dumps({"as_of": as_of_date, **strategy_trust}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  as_of={as_of_date} trust_level={strategy_trust['trust_level']}")
        print("  Saved → report/group_a_plus/latest/strategy_trust.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Strategy trust gate failed (non-fatal): {exc}")

    # Fable audit (2026-07-16, combination opportunities #8): signal_alignment's
    # production sources have never included trough_nowcast, compounding_regime,
    # or crash_risk_alert even though all three are already computed above --
    # this is a shadow-only comparison (see
    # group_a_plus/integrations/signal_alignment_shadow_variant.py), pure
    # logging, never touches the production alignment/target weights.
    print("\n[signal-alignment-shadow-variant]")
    try:
        from scripts.run.build_group_a_plus_signal_alignment_shadow_variant_log import main as run_shadow_variant

        run_shadow_variant()
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Signal alignment shadow variant failed (non-fatal): {exc}")

    print("\n[alert-state]")
    try:
        from group_a_plus.operations.alert_state import update_alert_state_from_files

        alert_state = update_alert_state_from_files()
        alert_summary = alert_state.get("summary", {})
        print(
            "  "
            f"emitted={alert_summary.get('emitted_count', 0)} "
            f"suppressed={alert_summary.get('suppressed_count', 0)} "
            f"resolved={alert_summary.get('resolved_count', 0)}"
        )
        print("  Saved → report/group_a_plus/latest/alert_state.json")

        from group_a_plus.operations.push_notifications import send_alert_notifications

        push_result = send_alert_notifications(alert_state)
        if push_result.get("alert_count", 0) > 0:
            print(
                "  "
                f"push_notification sent={push_result.get('sent')} "
                f"alert_count={push_result.get('alert_count')}"
            )
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Alert state update failed (non-fatal): {exc}")


if __name__ == "__main__":
    main()
