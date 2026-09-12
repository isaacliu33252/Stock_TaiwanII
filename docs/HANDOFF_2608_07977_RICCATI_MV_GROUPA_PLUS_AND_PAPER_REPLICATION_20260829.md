# 2608.07977 Riccati/MV Review And Replication Status

Date: 2026-08-29

Paper: arXiv:2608.07977, "A Computable Stochastic Riccati Equations Framework for Mean-Variance Portfolio Selection with Multifactor Stochastic Volatility Model"

## GroupA+ Decision

The paper has useful ideas for GroupA+, but only as a shadow risk-budget
diagnostic. It should not be promoted into live target weights or automatic
orders.

Implemented production-safe shadow pieces:

- `group_a_plus/integrations/riccati_mv_shadow.py`
- `scripts/run/build_group_a_plus_riccati_mv_shadow.py`
- daily pipeline step `riccati_mv_shadow` in `scripts/run/run_ncf_daily_pipeline.py`
- cap-only fields that can reduce 00631L/00632R to a shadow budget but never add
  either leveraged or inverse ETF beyond the live strategy weight.

Policy remains:

- `research_only_no_weight_change`
- `shadow_only_needs_backtest_before_any_guard_or_strategy_change`
- no target shares
- no execution regime changes

## GroupA+ Backtests Completed

Completed multi-window GroupA+ shadow tests:

- 00631L+00632R cap-to-cash
- 00631L-only cap
- 00632R-only cap
- transaction costs at 5, 10, and 20 bps
- confirmation modes: always, tail_only, total_risk, tail_or_drawdown, tail_drawdown_vol

Result: every tested variant had `promotion_allowed=false`.

Key reason: some variants improved final value or Sharpe in several windows, but
none improved drawdown consistently. The always-on setting improved final value
and Sharpe in all six windows, but improved max drawdown in only one of six
windows, which fails the risk-control purpose of this paper import.

## Current 2026-08-31 Shadow Snapshot

For the 2026-08-31 GroupA+ latest-strategy prediction using 1,000,000 TWD:

- latest strategy annualized volatility: 14.51%
- cap-only annualized volatility: 12.41%
- cap-only recommendation: cap 00631L from 10.04% to 5.00%
- 00632R is not increased even though the raw mean-variance optimizer prefers a
  higher 00632R weight.

This is exactly why the cap-only layer exists: the raw optimizer can treat the
inverse ETF as a hedge and ignore structural inverse-ETF decay.

## Paper-Level Replication Completed

Located and downloaded the authors' Zenodo software bundle:

- concept DOI: `10.5281/zenodo.21838225`
- resolved record: `10.5281/zenodo.21838226`
- title: `huangzhecheng1996/Deep_BSDE_for_4-ETFs: v1.0.0 Submission to JEDC`
- repository: `https://github.com/huangzhecheng1996/Deep_BSDE_for_4-ETFs`
- downloaded archive: `/tmp/Deep_BSDE_for_4-ETFs-v1.0.0.zip`
- md5 verified: `51a531528011160e64f0369816af2cc5`

The bundle contains:

- DeepBSDE source
- DBDP2 source
- `Trading_test/SP500_ETFs_data.csv`
- pre-trained DeepBSDE model `sre_deepbsde_model_step5.pt`
- pre-trained DBDP2 model `value_net_final_complete_set2.pt`

Downloaded missing US sector ETF data into `external_market_ohlcv`:

- SPY
- XLK
- XLF
- XLE
- XLV

Coverage: 2015-01-02 through 2026-08-28.

Added benchmark approximation script:

- `scripts/evaluate/evaluate_2608_07977_us_sector_benchmarks.py`

Output:

- `results/2608_07977_us_sector_benchmarks_20260829.json`
- `results/2608_07977_us_sector_benchmarks_20260829.csv`

This reproduces only the price-data benchmarks that are auditable from local
data:

- EW
- IV
- GMV

It does not reproduce:

- MV Deep-BSDE
- MV DBDP
- Black-Scholes baseline
- Heston/CIR calibration
- stochastic Riccati equation solver

Approximate benchmark results:

| Window | Strategy | Return | Vol | Sharpe | MDD |
| --- | --- | ---: | ---: | ---: | ---: |
| 2020 | EW | 6.03% | 38.40% | 0.16 | -38.95% |
| 2020 | IV | 8.35% | 37.27% | 0.22 | -37.71% |
| 2020 | GMV | 17.24% | 33.39% | 0.52 | -33.72% |
| 2025 | EW | 16.60% | 17.97% | 0.94 | -17.06% |
| 2025 | IV | 16.95% | 17.40% | 0.99 | -16.44% |
| 2025 | GMV | 17.76% | 18.31% | 0.98 | -17.55% |

Added author trading-test reproduction wrapper:

- `scripts/evaluate/reproduce_2608_07977_author_trading_test.py`

This executes the authors' notebook logic from `Trading_test_DeepBSDE_2020.ipynb`
and `Trading_test_DBDP2_2020.ipynb` as a script, using pre-trained weights
instead of retraining.

Outputs:

- `results/2608_07977_author_trading_test_2020_20260829.json`
- `results/2608_07977_author_trading_test_2020_20260829.csv`
- `results/2608_07977_author_trading_test_2025_20260829.json`
- `results/2608_07977_author_trading_test_2025_20260829.csv`

Author-data trading-test results:

| Window | Method | Strategy | Return | Vol | Sharpe | MDD | MES 5% |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2020 | DeepBSDE | Affine 6% | 5.49% | 18.51% | 0.30 | -16.59% | -1.06% |
| 2020 | DBDP2 | Affine 6% | 5.56% | 18.84% | 0.30 | -17.16% | -1.21% |
| 2020 | benchmark | EW | 3.69% | 58.57% | 0.06 | -52.56% | -9.55% |
| 2020 | benchmark | IV | 5.85% | 44.45% | 0.13 | -43.68% | -7.18% |
| 2020 | benchmark | GMV | 21.88% | 17.09% | 1.28 | -8.35% | -1.20% |
| 2025 | DeepBSDE | Affine 6% | 5.16% | 7.41% | 0.70 | -7.54% | -0.58% |
| 2025 | DBDP2 | Affine 6% | 5.23% | 7.01% | 0.75 | -7.16% | -0.53% |
| 2025 | benchmark | EW | 16.22% | 18.14% | 0.89 | -16.80% | -2.72% |
| 2025 | benchmark | IV | 14.21% | 16.70% | 0.85 | -15.47% | -2.43% |
| 2025 | benchmark | GMV | 3.51% | 12.57% | 0.28 | -16.16% | -1.60% |

The 2025 benchmark rows match the paper table closely, confirming that the
authors' `SP500_ETFs_data.csv` and engine are the relevant reproduction path.
The Affine/DeepBSDE/DBDP2 rows from the released notebook/weights are directionally
consistent with the paper's claim of lower volatility and better drawdown control
than EW/IV, but the exact numbers do not fully match the paper tables.

Additional parameter reconciliation attempts were run because the released
notebook hardcodes `RF=0.02` while the authors' CSV header says `r: 0.04`.

| Variant | Method | Return | Vol | Sharpe | MDD |
| --- | --- | ---: | ---: | ---: | ---: |
| 2020 RF 2%, target 6% | DeepBSDE | 5.49% | 18.51% | 0.30 | -16.59% |
| 2020 RF 2%, target 6% | DBDP2 | 5.56% | 18.84% | 0.30 | -17.16% |
| 2020 RF 4%, target 6% | DeepBSDE | 6.30% | 10.03% | 0.63 | -6.59% |
| 2020 RF 4%, target 6% | DBDP2 | 6.35% | 9.67% | 0.66 | -5.17% |
| 2020 RF 2%, target 8% | DeepBSDE | 1.27% | 22.21% | 0.06 | -22.67% |
| 2020 RF 2%, target 8% | DBDP2 | 0.98% | 22.61% | 0.04 | -23.40% |
| 2020 RF 2%, target 6%, 60d window | DeepBSDE | 1.51% | 21.73% | 0.07 | -25.58% |
| 2020 RF 2%, target 6%, 60d window | DBDP2 | 2.51% | 22.17% | 0.11 | -23.11% |
| 2025 RF 2%, target 6% | DeepBSDE | 5.16% | 7.41% | 0.70 | -7.54% |
| 2025 RF 2%, target 6% | DBDP2 | 5.23% | 7.01% | 0.75 | -7.16% |
| 2025 RF 4%, target 6% | DeepBSDE | 5.84% | 4.04% | 1.45 | -4.05% |
| 2025 RF 4%, target 6% | DBDP2 | 5.73% | 3.79% | 1.51 | -3.77% |
| 2025 RF 2%, target 8% | DeepBSDE | 4.10% | 9.87% | 0.42 | -10.09% |
| 2025 RF 2%, target 8% | DBDP2 | 3.57% | 9.66% | 0.37 | -9.79% |
| 2025 RF 2%, target 10% | DeepBSDE | 5.67% | 10.34% | 0.55 | -9.78% |
| 2025 RF 2%, target 10% | DBDP2 | 4.72% | 10.23% | 0.46 | -9.67% |

Findings from reconciliation:

- `RF=0.04` makes the 2020 risk profile closer to the paper's lower-volatility
  table, but it does not reconcile the 2025 table.
- Increasing the target return to 8% or 10% does not recover the paper's higher
  2025 return; it mostly worsens realized return while increasing risk.
- Extending the strategy window to 60 days worsens 2020.
- Therefore the released notebook/weights are reproducible, but the exact paper
  table remains not fully reproducible from the released notebook settings alone.
  The likely missing piece is the exact table-generation configuration or a
  different trained checkpoint.

## DeepBSDE/DBDP2 Continuation Retrain Check

CPU-only continuation retrains were run from the released DeepBSDE and DBDP2
checkpoints to confirm that both training paths are executable locally. These
are short continuation tests, not full paper retrains.

Implementation:

- `scripts/evaluate/continue_train_2608_07977_deepbsde.py`
- `scripts/evaluate/continue_train_2608_07977_dbdp2.py`
- `scripts/evaluate/reproduce_2608_07977_author_trading_test.py` now supports
  `--deepbsde-model-path` and `--dbdp2-model-path`.

Artifacts:

- `results/2608_07977_deepbsde_continuation_5epoch_20260829.pt`
- `results/2608_07977_deepbsde_continuation_5epoch_20260829_history.csv`
- `results/2608_07977_deepbsde_continuation_5epoch_20260829_report.json`
- `results/2608_07977_deepbsde_continuation_50epoch_20260829.pt`
- `results/2608_07977_deepbsde_continuation_50epoch_20260829_history.csv`
- `results/2608_07977_deepbsde_continuation_50epoch_20260829_report.json`
- `results/2608_07977_deepbsde_continuation_300epoch_20260829.pt`
- `results/2608_07977_deepbsde_continuation_300epoch_20260829_history.csv`
- `results/2608_07977_deepbsde_continuation_300epoch_20260829_report.json`
- `results/2608_07977_author_trading_test_2020_deepbsde_cont5_20260829.csv`
- `results/2608_07977_author_trading_test_2025_deepbsde_cont5_20260829.csv`
- `results/2608_07977_author_trading_test_2020_deepbsde_cont50_20260829.csv`
- `results/2608_07977_author_trading_test_2025_deepbsde_cont50_20260829.csv`
- `results/2608_07977_author_trading_test_2020_deepbsde_cont300_20260829.csv`
- `results/2608_07977_author_trading_test_2025_deepbsde_cont300_20260829.csv`
- `results/2608_07977_dbdp2_continuation_1epochstep_20260829.pt`
- `results/2608_07977_dbdp2_continuation_1epochstep_20260829_report.json`
- `results/2608_07977_author_trading_test_2020_dbdp2_cont1step_20260829.csv`
- `results/2608_07977_author_trading_test_2025_dbdp2_cont1step_20260829.csv`

Training runtime:

| Run | Epochs | Batch | Device | Runtime |
| --- | ---: | ---: | --- | ---: |
| DeepBSDE formal continuation | 5 | 128 | CPU | 5.29s |
| DeepBSDE formal continuation | 50 | 128 | CPU | 36.44s |
| DeepBSDE formal continuation | 300 | 128 | CPU | 240.68s |
| DBDP2 tiny full-step sweep | 1 per time step | 256 | CPU | 9.82s |

DeepBSDE Affine 6% comparison:

| Run | Return | Vol | Sharpe | MDD | MES 5% |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2020 original checkpoint | 5.49% | 18.51% | 0.30 | -16.59% | -1.06% |
| 2020 formal 5-epoch continuation | 5.48% | 18.49% | 0.30 | -16.64% | -1.06% |
| 2020 formal 50-epoch continuation | 5.47% | 18.51% | 0.30 | -16.65% | -1.06% |
| 2020 formal 300-epoch continuation | 5.45% | 18.58% | 0.29 | -16.62% | -1.07% |
| 2025 original checkpoint | 5.16% | 7.41% | 0.70 | -7.54% | -0.58% |
| 2025 formal 5-epoch continuation | 5.16% | 7.41% | 0.70 | -7.53% | -0.58% |
| 2025 formal 50-epoch continuation | 5.14% | 7.40% | 0.69 | -7.57% | -0.58% |
| 2025 formal 300-epoch continuation | 5.14% | 7.43% | 0.69 | -7.58% | -0.58% |

DBDP2 Affine 6% comparison:

| Run | Return | Vol | Sharpe | MDD | MES 5% |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2020 original checkpoint | 5.56% | 18.84% | 0.30 | -17.16% | -1.21% |
| 2020 1-epoch-per-step continuation | 5.56% | 18.85% | 0.29 | -17.18% | -1.21% |
| 2025 original checkpoint | 5.23% | 7.01% | 0.75 | -7.16% | -0.53% |
| 2025 1-epoch-per-step continuation | 5.23% | 7.03% | 0.74 | -7.18% | -0.53% |

Finding: formal continuation training is stable for both solvers but does not
materially improve the released checkpoints. DeepBSDE remains essentially
unchanged after 5, 50, and 300 additional CPU epochs. This suggests the gap
between the released notebook/weights and the paper tables is not explained by
adding a few hundred continuation epochs at the released checkpoint.

Note: an earlier ad-hoc `/tmp/2608_07977_deepbsde_smoke_retrain_5epoch.pt`
checkpoint produced unrealistically low-risk trading-test output because the
inline save path did not preserve the full loaded environment parameters. Treat
that `/tmp` artifact and its derived `smoke5` trading-test outputs as invalid.

## SRE Out-of-Sample Verification

The authors' out-of-sample SRE verification notebooks were converted into a
headless script so terminal-condition diagnostics can be reproduced without
plotting notebook images.

Implementation:

- `scripts/evaluate/evaluate_2608_07977_sre_oos.py`

Artifacts:

- `results/2608_07977_sre_oos_original_10k_20260829.json`
- `results/2608_07977_sre_oos_original_50k_20260829.json`
- `results/2608_07977_sre_oos_deepbsde_cont300_10k_20260829.json`

Original checkpoint, 50,000 scenarios:

| Method | Log mean | Log std | Log MSE vs 0 | Physical mean | Physical std | Physical MSE vs 1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DeepBSDE | 0.000104 | 0.009886 | 9.77e-05 | 0.996418 | 0.010329 | 1.20e-04 |
| DBDP2 | 0.000907 | 0.033271 | 1.11e-03 | 0.997387 | 0.033771 | 1.15e-03 |

DeepBSDE 300-epoch continuation, 10,000 scenarios:

| Checkpoint | Log mean | Log std | Log MSE vs 0 | Physical mean | Physical std | Physical MSE vs 1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| original | 0.000257 | 0.010059 | 1.01e-04 | 0.996424 | 0.010230 | 1.17e-04 |
| +300 epochs | 0.000214 | 0.010641 | 1.13e-04 | 0.996330 | 0.010773 | 1.30e-04 |

Finding: the released checkpoints satisfy the SRE terminal-condition diagnostics
reasonably well, especially DeepBSDE. The 300-epoch continuation does not
improve the SRE terminal MSE, matching the trading-test finding that additional
short continuation is not the missing paper-table ingredient.

## Trading-Test Parameter Sweep

A reusable parameter-sweep script was added to test whether the paper-table
gap is explained by trading-test settings rather than checkpoint training.

Implementation:

- `scripts/evaluate/evaluate_2608_07977_trading_param_sweep.py`

Artifacts:

- `results/2608_07977_trading_param_sweep_core_20260829.json`
- `results/2608_07977_trading_param_sweep_core_20260829.csv`
- `results/2608_07977_trading_param_sweep_leverage_20260829.json`
- `results/2608_07977_trading_param_sweep_leverage_20260829.csv`

Grid:

- windows: 2020, 2025
- methods: DeepBSDE, DBDP2
- risk-free rate: 2%, 4%
- target return: 6%, 8%
- strategy window: 20, 60 trading days
- leverage: off/on

Best Sharpe / drawdown settings:

| Window | Method | RF | Target | Strategy Window | Leverage | Return | Vol | Sharpe | MDD |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 2020 | DeepBSDE | 4% | 6% | 20 | off | 6.30% | 10.03% | 0.63 | -6.59% |
| 2020 | DBDP2 | 4% | 6% | 20 | off | 6.35% | 9.67% | 0.66 | -5.17% |
| 2025 | DeepBSDE | 4% | 6% | 60 | off | 6.65% | 2.36% | 2.81 | -2.43% |
| 2025 | DBDP2 | 4% | 6% | 60 | off | 6.64% | 2.09% | 3.17 | -2.06% |

Highest-return settings in this grid:

| Window | Method | RF | Target | Strategy Window | Leverage | Return | Vol | Sharpe | MDD |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 2020 | DeepBSDE | 2% | 8% | 20 | on | 9.08% | 32.54% | 0.28 | -20.06% |
| 2020 | DBDP2 | 2% | 8% | 20 | on | 9.25% | 31.38% | 0.29 | -17.61% |
| 2025 | DeepBSDE | 2% | 8% | 60 | on | 10.05% | 7.23% | 1.39 | -8.22% |
| 2025 | DBDP2 | 2% | 8% | 60 | on | 10.03% | 6.36% | 1.58 | -7.07% |

Findings:

- `RF=0.04` is the strongest setting difference found so far. It substantially
  lowers volatility and drawdown, especially for 2020.
- `allow_leverage=True` is not a stable explanation. It sometimes raises return,
  but often raises volatility and drawdown enough to reduce risk-adjusted quality.
- A 60-day strategy window helps 2025 but hurts 2020 under several settings.
- The sweep still does not fully reconcile the released checkpoint outputs with
  the paper tables. The most likely missing piece remains a different table
  generation config or a different checkpoint.

## Black-Scholes Baseline Approximation

The Zenodo bundle does not include the paper's `BS Baseline` implementation,
even though Table 5 and Table 6 report it. A transparent approximation script
was added to test two plausible interpretations:

- `scaled_target`: rolling constant drift/covariance tangency direction scaled
  to the annual target return.
- `feedback`: rolling constant drift/covariance Black-Scholes mean-variance
  feedback-control approximation.

Implementation:

- `scripts/evaluate/evaluate_2608_07977_bs_baseline_approx.py`

Artifacts:

- `results/2608_07977_bs_baseline_approx_nolev_20260829.json`
- `results/2608_07977_bs_baseline_approx_nolev_20260829.csv`
- `results/2608_07977_bs_baseline_approx_lev_20260829.json`
- `results/2608_07977_bs_baseline_approx_lev_20260829.csv`
- `results/2608_07977_bs_baseline_approx_feedback_nolev_20260829.json`
- `results/2608_07977_bs_baseline_approx_feedback_nolev_20260829.csv`
- `results/2608_07977_bs_baseline_approx_feedback_lev_20260829.json`
- `results/2608_07977_bs_baseline_approx_feedback_lev_20260829.csv`
- `results/2608_07977_bs_baseline_approx_feedback_v2_nolev_20260829.json`
- `results/2608_07977_bs_baseline_approx_feedback_v2_nolev_20260829.csv`
- `results/2608_07977_bs_baseline_approx_feedback_v2_lev_20260829.json`
- `results/2608_07977_bs_baseline_approx_feedback_v2_lev_20260829.csv`
- `results/2608_07977_bs_baseline_approx_feedback_v3_target6_lev_20260829.json`
- `results/2608_07977_bs_baseline_approx_feedback_v3_target6_lev_20260829.csv`
- `results/2608_07977_bs_baseline_approx_feedback_v3_target8_lev_20260829.json`
- `results/2608_07977_bs_baseline_approx_feedback_v3_target8_lev_20260829.csv`
- `results/2608_07977_bs_baseline_approx_feedback_v3_target12_lev_20260829.json`
- `results/2608_07977_bs_baseline_approx_feedback_v3_target12_lev_20260829.csv`

Paper BS Baseline targets:

| Window | Return | Vol | Sharpe | MDD | MES |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2020 | 6.87% | 32.19% | 0.21 | -28.34% | -4.48% |
| 2025 | 7.07% | 10.16% | 0.70 | -6.71% | -0.97% |

Approximation findings:

- `scaled_target` is far too conservative: 2020 volatility only ranges from
  about 0.58% to 3.04%, and 2025 volatility only ranges from about 0.52% to
  2.76%.
- The initial `feedback` approximation was too cash-like because it re-scaled
  `c_star` from current equity. It was corrected to mirror the authors'
  DeepBSDE strategy interface: `c_star` uses initial capital and `q_t` uses
  remaining time.
- Corrected `feedback` with target 6% still does not match: 2020 volatility
  stays at about 0.01% to 0.20%, and 2025 at about 0.43% to 1.87%.
- Increasing feedback target return to 8% and 12% still does not reconcile the
  paper baseline. At target 12%, 2020 volatility remains only about 0.04% to
  0.52%; 2025 reaches about 2.25% to 4.78%, still below the paper's 10.16%.
- Weight diagnostics confirm the low-risk output is driven by low or unstable
  exposure, not a metrics bug. At target 12%, 2020 mean gross exposure is only
  about 0.1% to 2.3%. For 2025, mean gross exposure is higher at about 11.6% to
  37.6%, with max gross exposure up to 2.68x in the 20-day window, but the
  realized return/volatility still does not match Table 6.

Finding: these two plausible local approximations do not match the paper's BS
Baseline. The exact Table 5/6 BS Baseline likely depends on an unreleased
benchmark implementation, different objective scaling, or different table
generation settings.

## Paper-Level Replication Gaps

The paper's central experiment is not fully replicated. To fully reproduce Table
5 and Table 6, the remaining work requires either the authors' Zenodo bundle or
a fresh implementation of the paper's solver stack:

- exact paper-table version of the released weights/notebook settings
- exact benchmark definitions for the Black-Scholes baseline
- multifactor Heston-type stochastic volatility calibration
- CIR factor simulation
- stochastic Riccati equation iteration
- logarithmic transformed BSDE
- full Deep-BSDE and DBDP neural re-training runs
- five-trading-day dynamic rebalancing under the paper's terminal wealth target,
  aligned exactly to the paper's table-generation code
- GPU availability. The local environment did not expose `nvidia-smi`; full
  training is expected to be slow or impractical here.

## Final Decision: Stop Here for GroupA+

Decision date: 2026-08-29.

Status: stop further promotion work for this paper in GroupA+. Keep only the
implemented Riccati/MV shadow diagnostics.

Reasons:

- The GroupA+ targeted tests failed the live promotion gate.
- The released Zenodo checkpoints run successfully, but the reported paper
  tables cannot be fully reconciled from the released notebooks/checkpoints.
- Short continuation retraining does not improve either trading-test metrics or
  SRE terminal diagnostics.
- Parameter sweeps identify useful sensitivity patterns, especially `RF=0.04`,
  but they do not produce a stable deployable GroupA+ improvement.
- The paper's `BS Baseline` is not included in the released implementation; two
  transparent approximations were tested and rejected as table explanations.
- Full paper replication would require a separate research project with exact
  benchmark definitions, solver implementation details, and likely GPU compute.

Do not re-run by default:

- DeepBSDE 5/50/300 epoch continuation from the released checkpoint.
- DBDP2 one-step tiny continuation.
- RF/target/window/leverage sweep already recorded in the 20260829 artifacts.
- `scaled_target` and corrected `feedback` BS baseline approximations.

Re-open conditions:

- The authors release exact Table 5/6 code, benchmark definitions, or new
  checkpoints.
- A dedicated research task is approved to reimplement the full paper stack.
- GroupA+ receives a separate mandate to use Riccati/MV only as a constrained
  risk overlay and not as an alpha/trade generator.

## Recommendation

For GroupA+, stop promotion work here and keep the Riccati/MV logic as daily
shadow diagnostics. Full paper replication is a separate research project; it is
not necessary for the current GroupA+ decision because the GroupA+ targeted
tests already failed the live promotion gate.

Operational rule:

- `riccati_mv_shadow` can reduce or flag exposure in leveraged/inverse ETF legs.
- `riccati_mv_shadow` must not directly add leveraged/inverse exposure.
- Raw optimizer weights remain research output only.
- Daily NCF/latest-strategy decisions remain the primary production signal path.
