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
        "dfl_active_date_audit",
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
        # Fable independent review (2026-07-17) of 2607.03082v1: the CVaR/
        # Hill/POT-GPD tail-risk diagnostic evaluator only ever ran as a
        # manual one-off with a hardcoded --end date, so
        # report/group_a_plus/latest/ never had a current snapshot for
        # periodic human review. Pure diagnostic refresh -- research_only,
        # never changes target weights; a failure here must never block
        # anything downstream.
        "cvar_tail_risk_diagnostic",
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
        # Commodity ETF heavy-tail optimization review (2026-07-18):
        # dynamic CVaR / tail / transaction-cost readiness check inspired by
        # 2606.26625. Research-only; no optimizer and no weight changes.
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
        "intervention_fatigue_risk_budget_readiness_review",
        # LETF tracking-error / effective-fee review (2026-07-18): holding-
        # horizon and inverse-hedge neutrality governance inspired by
        # 1610.09404. Research-only; no LETF pair strategy and no weight change.
        "letf_tracking_error_effective_fee_readiness_review",
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
        "research_shadow_decision_snapshot",
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


def _normalize_project_path(raw: str | Path) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _assert_no_protected_golden1_output_targets(commands: dict[str, list[str]]) -> None:
    protected = {_normalize_project_path(path) for path in PROTECTED_GOLDEN1_RELEASE_ARTIFACTS}
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
            "daily pipeline attempted to write protected Golden1_0531 release artifact(s): "
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
        "--no-tabnet",
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
        commands["ncf_2330"].append("--no-external-features")

    commands["ncf_panel_manifest"] = [
        sys.executable,
        "scripts/evaluate/build_ncf_panel_manifest.py",
        "--panels",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        str(_result_path(f"ncf_00632r_panel_latest_{stamp}.csv")),
        str(_result_path(f"ncf_2330_panel_latest_{stamp}.csv")),
        "--output",
        str(_result_path(f"ncf_panel_manifest_{stamp}.json")),
    ]
    commands["ncf_panel_drift"] = [
        sys.executable,
        "scripts/evaluate/evaluate_ncf_panel_drift.py",
        "--baseline-panel",
        getattr(args, "active_ncf_00631l_panel", DEFAULT_ACTIVE_NCF_00631L_PANEL),
        "--candidate-panel",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--output",
        str(_result_path(f"ncf_panel_drift_active_vs_{stamp}.json")),
        "--csv-output",
        str(_result_path(f"ncf_panel_drift_active_vs_{stamp}.csv")),
    ]
    commands["ncf_panel_drift_diagnosis"] = [
        sys.executable,
        "scripts/evaluate/build_ncf_panel_drift_diagnosis.py",
        "--drift-audit",
        str(_result_path(f"ncf_panel_drift_active_vs_{stamp}.json")),
        "--baseline-panel",
        getattr(args, "active_ncf_00631l_panel", DEFAULT_ACTIVE_NCF_00631L_PANEL),
        "--candidate-panel",
        str(_result_path(f"ncf_00631l_panel_latest_{stamp}.csv")),
        "--baseline-signal",
        str(_result_path("ncf_00631l_latest_20260630.json")),
        "--candidate-signal",
        str(_result_path(f"ncf_00631l_latest_{stamp}.json")),
        "--output",
        str(_result_path(f"ncf_panel_drift_diagnosis_{stamp}.json")),
    ]
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
    commands["daily_signal"] = [
        sys.executable,
        "group_a_plus/operations/daily_signal.py",
        "--as-of",
        as_of,
        "--output",
        str(_result_path(f"group_a_plus_live_signal_v2_{stamp}.json")),
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
    commands["cvar_tail_risk_diagnostic"] = [
        sys.executable,
        "scripts/run/build_group_a_plus_cvar_tail_risk_diagnostic_snapshot.py",
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
    commands["dynamic_cvar_tail_cost_readiness_review"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_dynamic_cvar_tail_cost_readiness_review.py",
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
    commands["research_shadow_decision_snapshot"] = [
        sys.executable,
        "scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py",
        "--systemic-bubble",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "systemic_bubble_time_at_risk_review.json"),
        "--illiquidity-network",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "illiquidity_network_readiness_review.json"),
        "--speculative-influence",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "speculative_influence_network_readiness_review.json"
        ),
        "--sin-lite-proxy",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "sin_lite_proxy.json"),
        "--hmm-wj",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "hmm_wj_synthetic_scenario_readiness_review.json"),
        "--dynamic-cvar",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "dynamic_cvar_tail_cost_readiness_review.json"),
        "--synthetic-augmentation",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "synthetic_augmentation_validation_readiness_review.json"
        ),
        "--intervention-fatigue",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "intervention_fatigue_risk_budget_readiness_review.json"
        ),
        "--letf-tracking",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "letf_tracking_error_effective_fee_readiness_review.json"
        ),
        "--asian-etf-tail-analytics",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "asian_etf_tail_analytics_readiness_review.json"
        ),
        "--llm-state-reward-signed-approval-validation",
        str(
            PROJECT_ROOT
            / "report"
            / "group_a_plus"
            / "latest"
            / "llm_state_reward_human_exception_signed_approval_validation.json"
        ),
        "--output",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "research_shadow_decision_snapshot.json"),
    ]
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
    DFL_WINDOWS_7WIN_PIT = (
        "covid_2020:2020-01-02:2020-12-31:results/ncf_00631l_panel_backfill_2020_20260716.csv:out_of_sample,"
        "inflation_2022:2022-01-03:2022-12-30:results/ncf_00631l_panel_latest_20260707.csv:out_of_sample,"
        "live_2024_2026:2024-01-02:2026-07-15:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,"
        "active_2025_2026:2025-01-02:2026-07-15:results/ncf_00631l_panel_latest_20260707.csv:tuning_window,"
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
        "--dynamic-cvar-tail-cost-readiness-review",
        str(PROJECT_ROOT / "report" / "group_a_plus" / "latest" / "dynamic_cvar_tail_cost_readiness_review.json"),
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
    _assert_no_protected_golden1_output_targets(commands)
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
    parser.add_argument("--train-start-2330", default="2015-01-01")
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
                "panel_00631l": str(_result_path(f"ncf_00631l_panel_latest_{args.date_stamp}.csv")),
                "panel_00632r": str(_result_path(f"ncf_00632r_panel_latest_{args.date_stamp}.csv")),
                "panel_2330": str(_result_path(f"ncf_2330_panel_latest_{args.date_stamp}.csv")),
                "ncf_panel_manifest": str(_result_path(f"ncf_panel_manifest_{args.date_stamp}.json")),
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
                "live_signal": live_signal_output,
                "compounding_regime": str(_result_path(f"00631l_leveraged_compounding_regime_{args.date_stamp}.json")),
                "compounding_regime_csv": str(_result_path(f"00631l_leveraged_compounding_regime_{args.date_stamp}.csv")),
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
        DEFAULT_OUTPUT_PATH.write_text(json.dumps(env_health, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            "  "
            f"status={env_health.get('status')} "
            f"missing_files={len(env_health.get('missing_files', []))} "
            f"warnings={len(env_health.get('warnings', []))}"
        )
        print("  Saved → report/group_a_plus/latest/strategy_env_health.json")
    except Exception as exc:  # noqa: BLE001
        print(f"  [WARNING] Environment health check failed (non-fatal): {exc}")

    print("\n[ops-health]")
    try:
        from group_a_plus.operations.ops_health import DEFAULT_OUTPUT_PATH, build_ops_health

        ops_health = build_ops_health()
        DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_OUTPUT_PATH.write_text(json.dumps(ops_health, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            "  "
            f"status={ops_health.get('status')} "
            f"errors={len(ops_health.get('errors', []))} "
            f"warnings={len(ops_health.get('warnings', []))}"
        )
        print("  Saved → report/group_a_plus/latest/ops_health.json")
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
            # LTN's keyword-matched local scrape (news/ltn_mainstream_*.jsonl) is a
            # manually-curated feed and can go stale for days at a time (2026-07-07
            # Fable audit: found 8 days stale, article_count=0). FinMind's
            # already ticker-tagged news dataset is fetched automatically above,
            # so fall back to it rather than shipping an empty watchlist_news.json
            # to lm_dictionary_sentiment/signal_alignment/llm_commentary.
            from scripts.run.build_finmind_watchlist_news import build_finmind_watchlist_news_summary

            finmind_summary = build_finmind_watchlist_news_summary(
                signal_date=signal_date_str,
                news_glob="news/finmind_stock_news_rolling.jsonl",
            )
            if finmind_summary.get("article_count", 0) > 0:
                _WATCHLIST_NEWS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
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
