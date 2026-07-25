# Handoff: 2603.10202 HMM-WJ Synthetic Scenario For GroupA+（2026-07-18）

## Objective

Analyze `C:\Users\isaac\Downloads\2603.10202.pdf` and decide whether its useful
ideas can be introduced into the latest GroupA+ strategy and Golden1_0531.

PDF:

- Title: `Hybrid Hidden Markov Model for Modeling Equity Excess Growth Rate Dynamics: A Discrete-State Approach with Jump-Diffusion`
- Authors: Abdulrahman Alswaidan and Jeffrey Varner
- arXiv: `2603.10202v2`
- Paper date in PDF: 2026-04-02
- Local file: `C:\Users\isaac\Downloads\2603.10202.pdf`

## Final Decision

Do not change live target weights.

Do not auto-rebalance for `2026-07-20`.

Do not auto-add `00631L`.

Keep `Golden1_0531` unchanged.

The paper contributes useful synthetic-scenario governance ideas, not a live
alpha model. It is imported as research-only readiness:

- synthetic scenario quality gate;
- jump-duration tail-state dwell-time concept;
- direct-counting quantile-state transitions;
- Student-t copula dependence concept.

## What Was Not Imported

Not imported into live strategy:

- HMM-WJ generator as a live trading signal;
- synthetic paths as alpha;
- SPY / S&P 500 hyperparameters for Taiwan ETFs;
- paper settings such as `N = 100`, `nu = 5`, or jump-grid values as fixed
  GroupA+ parameters;
- Student-t copula optimizer;
- automatic target-weight change;
- automatic `00631L` add or `00632R` hedge.

Reason:

- The paper validates mainly US equities / SPY-like data.
- The reported out-of-sample window is only one 249-trading-day 2025 period.
- The paper itself flags stationarity, structural-break, and jump-free ensemble
  limitations.
- Taiwan ETF scenario generation needs separate walk-forward validation before
  it can affect even manual advisory decisions.

## Implemented Artifact

New research-only readiness builder:

- `scripts/evaluate/build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review.py`

Main outputs:

- `report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json`
- `report/group_a_plus/hmm_wj_synthetic_scenario_readiness/history/20260717.json`

Policy:

- `research_only_hmm_wj_readiness_no_synthetic_alpha_no_weight_change`

Hard rule:

- The readiness review does not generate synthetic paths.
- It does not unlock execution.
- It does not change target weights.

## Data Readiness

Local DB:

- `FinRL/data/stock_data.db`

Required tickers:

- `0050.TW`
- `00631L.TW`
- `00632R.TW`
- `2330.TW`

Data source behavior:

- ETF rows are read from `ohlcv`.
- `2330.TW` is available from `external_market_ohlcv` through existing
  yfinance cache conventions used elsewhere in GroupA+.

Readiness thresholds:

- minimum return rows per ticker: `1000`
- minimum low-tail observations per ticker: `50`
- minimum high-tail observations per ticker: `50`
- tail definition: empirical 5th / 95th percentile returns per ticker

Latest result:

- `all_required_tickers_ready = true`

Ticker summary:

| Ticker | Return rows | Low-tail obs | High-tail obs | Tail transitions | Ann vol | Excess kurtosis | Data ready |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `0050.TW` | `2805` | `141` | `141` | `64` | `0.19588842219036645` | `7.1326365909438945` | `true` |
| `00631L.TW` | `2809` | `141` | `141` | `60` | `0.3874499137471748` | `21.021555654460244` | `true` |
| `00632R.TW` | `2809` | `141` | `141` | `62` | `1.7697096400166417` | `2710.1760640292405` | `true` |
| `2330.TW` | `2804` | `141` | `142` | `56` | `0.2722830454317871` | `3.3709105064547393` | `true` |

## Validation Readiness

Current validation state:

- `generator_implemented = false`
- `synthetic_paths_generated = false`
- `ks_ad_wasserstein_hellinger_acf_mae_available = false`
- `taiwan_etf_walkforward_validated = false`
- `student_t_copula_validated = false`

Interpretation:

- Local history is enough to begin research.
- HMM-WJ cannot be used for decisions yet because no Taiwan ETF generator or
  validation harness exists.

## Latest Readiness Result

Latest diagnostic file:

- `report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json`

As of:

- `2026-07-17`

Current result:

- `status = blocked`
- `all_required_tickers_ready = true`
- `can_generate_scenarios_for_decision = false`
- `promote_to_live = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add = false`
- `keep_golden1_0531_unchanged = true`

Blocking reasons:

- `finstressts_snapshot_blocked`
- `trigate_vol_memory_blocks_leverage_add`
- `systemic_bubble_time_at_risk_blocks_leverage_add`
- `hmm_wj_generator_not_implemented`
- `taiwan_etf_walkforward_validation_missing`

Warning reasons:

- `readiness_only_no_synthetic_paths_generated`

## Research Snapshot Integration

Updated:

- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`

Latest output:

- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

Current snapshot:

- `status = blocked`
- `hmm_wj_status = blocked`
- `hmm_wj_data_ready = true`
- `hmm_wj_can_generate_scenarios_for_decision = false`
- `hmm_wj_allow_00631l_add = false`

Research snapshot blocking reasons now include:

- `hmm_wj_synthetic_scenario_readiness_blocked`

## Daily Pipeline Integration

Updated:

- `scripts/run/run_ncf_daily_pipeline.py`

New best-effort step:

- `hmm_wj_synthetic_scenario_readiness_review`

Command output:

- `report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json`

Placement:

- after `systemic_bubble_time_at_risk_review`
- before `research_shadow_decision_snapshot`

Reason:

- research snapshot should see HMM-WJ readiness before it builds its consolidated
  blocker list.

## Daily Status Integration

Updated:

- `scripts/misc/check_group_a_plus_daily_status.py`

New CLI argument:

- `--hmm-wj-synthetic-scenario-readiness-review`

New JSON path:

- `group_a_plus.hmm_wj_synthetic_scenario_readiness_review`

New Markdown section:

- `## HMM-WJ Synthetic Scenario Readiness`

Latest generated daily status:

- `results/group_a_plus_daily_status_20260720_hmm_wj.json`
- `results/group_a_plus_daily_status_20260720_hmm_wj.md`
- `report/group_a_plus/latest/daily_status.json`

Latest managed reports:

- `report/group_a_plus/daily/html/daily_status_a2118_a2111_ncf_late_bull_deleverage_20260720_20260718_125215.html`
- `report/group_a_plus/daily/json/daily_status_a2118_a2111_ncf_late_bull_deleverage_20260720_20260718_125215.json`
- `report/group_a_plus/daily/md/daily_status_a2118_a2111_ncf_late_bull_deleverage_20260720_20260718_125215.md`
- `report/group_a_plus/daily/meta/daily_status_a2118_a2111_ncf_late_bull_deleverage_20260720_20260718_125215.meta.json`

Daily status now shows:

- `Status = blocked`
- `00631L add = blocked`
- `Data ready = True`
- `Can generate scenarios for decision = False`
- `Generator implemented = False`
- `Taiwan ETF walk-forward validated = False`
- blocking reasons include generator and walk-forward validation gaps

Daily status overall:

- `overall_status = warn`

Reason:

- `data_freshness = warn`
- `2026-07-20` check date vs `2026-07-17` actual data:
  - `1` business day stale
  - `3` calendar days stale

This warning does not unlock or change execution.

## Tests

Added / updated:

- `tests/test_build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review.py`
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- `tests/test_check_group_a_plus_daily_status.py`
- `tests/test_run_ncf_daily_pipeline.py`

Verified:

- HMM-WJ readiness / research snapshot / pipeline:
  - `19 passed`
- daily_status / pipeline / HMM-WJ readiness:
  - `31 passed`
- `py_compile` passed for:
  - `scripts/evaluate/build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review.py`
  - `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
  - `scripts/misc/check_group_a_plus_daily_status.py`
  - `scripts/run/run_ncf_daily_pipeline.py`

Recent commands:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py tests/test_run_ncf_daily_pipeline.py
```

Result:

- `19 passed`

```bash
.venv/bin/python -m pytest tests/test_check_group_a_plus_daily_status.py tests/test_run_ncf_daily_pipeline.py tests/test_build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review.py
```

Result:

- `31 passed`

## Current Strategy Implication For 2026-07-20

Strategy:

- `a2118_a2111_ncf_late_bull_deleverage`

Reference target:

- `0050.TW = 50%`
- `00631L.TW = 20%`
- `00632R.TW = 0%`
- `00679B.TWO = 0%`
- cash = `30%`

Execution conclusion:

- no auto-rebalance;
- no new `00631L` add;
- no direct `00632R` hedge;
- keep `Golden1_0531` unchanged;
- keep manual review requirement.

The HMM-WJ readiness result does not add a new live signal. It strengthens the
research record by making explicit that synthetic scenario generation is not yet
decision-ready.

## Files Changed In This Workstream

Core:

- `scripts/evaluate/build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review.py`
- `scripts/evaluate/build_group_a_plus_research_shadow_decision_snapshot.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `scripts/misc/check_group_a_plus_daily_status.py`

Tests:

- `tests/test_build_group_a_plus_hmm_wj_synthetic_scenario_readiness_review.py`
- `tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- `tests/test_check_group_a_plus_daily_status.py`
- `tests/test_run_ncf_daily_pipeline.py`

Docs:

- `docs/2603_10202_HMM_WJ_SYNTHETIC_SCENARIO_GROUPA_PLUS_REVIEW_20260718.md`
- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`
- `docs/HANDOFF_2603_10202_HMM_WJ_SYNTHETIC_SCENARIO_GROUPA_PLUS_20260718.md`

Generated reports:

- `report/group_a_plus/latest/hmm_wj_synthetic_scenario_readiness_review.json`
- `report/group_a_plus/hmm_wj_synthetic_scenario_readiness/history/20260717.json`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`
- `results/group_a_plus_daily_status_20260720_hmm_wj.json`
- `results/group_a_plus_daily_status_20260720_hmm_wj.md`
- `report/group_a_plus/latest/daily_status.json`

## Maintenance Notes

Do not implement or promote HMM-WJ as live allocation logic without a separate
validation phase.

Required before any future promotion:

- implement a minimal Taiwan ETF HMM-WJ generator;
- generate synthetic paths only as research artifacts;
- compute KS / AD / Wasserstein-1 / Hellinger / ACF-MAE on `0050`, `00631L`,
  `00632R`, and `2330`;
- compare against simple bootstrap, GARCH-style volatility proxy, and existing
  FinStressTS counterfactual shadows;
- run walk-forward validation over multiple Taiwan market windows;
- verify Student-t copula or simpler dependence proxy improves joint crash
  synchronization without creating false confidence;
- keep output incapable of unlocking execution until explicitly approved.

Current safe next step, if continuing:

- build a history scorecard for HMM-WJ readiness and compare its blocked periods
  with next 1/5/20-day `00631L` drawdowns.
