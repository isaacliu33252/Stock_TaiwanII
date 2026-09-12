# HANDOFF - 2603.01157v2 BAWS Paper-Style Replication

Date: 2026-08-14  
Paper: `Adaptive Window Selection for Financial Risk Forecasting`,
arXiv `2603.01157v2`  
Scope: user follow-up asking whether the paper experiments were completed.

## Status

Completed a local paper-style replication harness and ran the practical
replication jobs that fit the local data/runtime constraints.

This is not a bit-for-bit full paper reproduction. The blockers are explicit:

- the paper uses large Monte Carlo settings (`1000` replications and large
  bootstrap counts) that are too slow for an interactive local run;
- the local S&P 500 cache starts on `2019-10-07`, while the paper's empirical
  section starts on `2005-01-04`;
- the GARCH setting is approximated with standardized Student-t innovations,
  not the paper's exact Fernandez-Steel skewed Student-t distribution with
  skewness parameter `r=0.95`;
- SAWS is implemented as a deterministic stability-threshold comparator, not a
  full reproduction of the cited SAWS method.

No live GroupA+ strategy file or production pointer was changed.

## Added

New research-only evaluator:

- `scripts/evaluate/evaluate_2603_01157_baws_paper_replication.py`

Outputs:

- `results/2603_01157_baws_paper_replication_coverage_r1_b20_stride20.json`
- `report/group_a_plus/latest/2603_01157_baws_paper_replication_coverage_r1_b20_stride20.md`
- `results/2603_01157_baws_paper_replication_normal_r10_b50_stride20.json`
- `report/group_a_plus/latest/2603_01157_baws_paper_replication_normal_r10_b50_stride20.md`

Related GroupA+ import experiments:

- `scripts/evaluate/evaluate_group_a_plus_baws_extended_experiments.py`
- `docs/HANDOFF_2603_01157_BAWS_EXTENDED_EXPERIMENTS_GROUPA_PLUS_20260814.md`

## Paper Settings Implemented

The harness implements the paper-style scenarios that were extractable from
the PDF:

- A1: structural mean break from `1` to `2`, variance `0.25`;
- A2: piecewise mean `1 -> 0 -> 2`, variance `0.25`;
- A3: A2 mean path with variance `0.25 -> 1 -> 0.49`;
- B1: sinusoidal mean, variance `0.25`;
- B2: random-walk mean increments, variance `0.25`;
- B3: geometric Brownian-style mean path;
- GARCH: approximate time-varying GARCH volatility setting;
- empirical S&P 500 subset using local `^GSPC` cache.

Core parameters supported by the script:

- `T=2000`;
- `t0=501`;
- `alpha=0.95`;
- `beta=0.90`;
- fixed windows `{250, 500, 750}`;
- BAWS maximum window `1000`;
- moving-block bootstrap threshold;
- `--forecast-stride` to make long replications feasible.

## Commands Run

Syntax check:

```bash
.venv/bin/python -m py_compile \
  scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py \
  scripts/evaluate/evaluate_group_a_plus_baws_extended_experiments.py \
  scripts/evaluate/evaluate_2603_01157_baws_paper_replication.py
```

Existing BAWS-lite tests:

```bash
.venv/bin/python -m pytest \
  tests/test_evaluate_group_a_plus_baws_lite_var_es_shadow.py -q
```

Coverage run across all implemented scenarios:

```bash
.venv/bin/python scripts/evaluate/evaluate_2603_01157_baws_paper_replication.py \
  --replications 1 \
  --bootstrap-samples 20 \
  --forecast-stride 20 \
  --empirical-bootstrap-samples 100 \
  --settings A1,A2,A3,B1,B2,B3,GARCH \
  --output-json results/2603_01157_baws_paper_replication_coverage_r1_b20_stride20.json \
  --output-md report/group_a_plus/latest/2603_01157_baws_paper_replication_coverage_r1_b20_stride20.md
```

Scaled normal simulation run:

```bash
.venv/bin/python scripts/evaluate/evaluate_2603_01157_baws_paper_replication.py \
  --replications 10 \
  --bootstrap-samples 50 \
  --forecast-stride 20 \
  --empirical-bootstrap-samples 100 \
  --settings A1,A2,A3,B1,B2,B3 \
  --output-json results/2603_01157_baws_paper_replication_normal_r10_b50_stride20.json \
  --output-md report/group_a_plus/latest/2603_01157_baws_paper_replication_normal_r10_b50_stride20.md
```

Full stride-1 attempts with larger settings were started but interrupted
because they were too slow for the interactive run:

- `replications=10`, `bootstrap_samples=50`, `forecast_stride=1`;
- `replications=3`, `bootstrap_samples=50`, `forecast_stride=1`;
- `replications=1`, `bootstrap_samples=20`, `forecast_stride=1`.

## Replication Results

Coverage run, `replications=1`, `B=20`, `forecast_stride=20`:

| Setting | MAB winner | Var winner | MSE winner | CR winner | CL winner |
|---|---|---|---|---|---|
| A1 | saws_lite | baws | saws_lite | saws_lite | fixed_250 |
| A2 | fixed_250 | baws | fixed_250 | fixed_250 | fixed_250 |
| A3 | fixed_250 | baws | fixed_250 | fixed_250 | saws_lite |
| B1 | fixed_250 | baws | fixed_250 | fixed_250 | saws_lite |
| B2 | fixed_250 | baws | fixed_250 | fixed_250 | fixed_250 |
| B3 | full | baws | full | fixed_500 | fixed_500 |
| GARCH | saws_lite | baws | saws_lite | None | fixed_500 |

Scaled normal simulations, `replications=10`, `B=50`,
`forecast_stride=20`:

| Setting | MAB winner | Var winner | MSE winner | CR winner | CL winner |
|---|---|---|---|---|---|
| A1 | saws_lite | full | saws_lite | fixed_250 | fixed_250 |
| A2 | fixed_250 | full | fixed_250 | fixed_250 | fixed_250 |
| A3 | fixed_250 | full | fixed_250 | saws_lite | saws_lite |
| B1 | fixed_250 | full | fixed_250 | fixed_250 | fixed_250 |
| B2 | fixed_250 | full | fixed_250 | fixed_250 | saws_lite |
| B3 | saws_lite | full | fixed_250 | fixed_250 | fixed_250 |

Empirical S&P 500 local subset before backfill:

- local cache: `2019-10-07` to `2026-08-13`, `1722` rows;
- evaluated subset after warmup and stride: `2023-09-28` to `2026-08-13`,
  `37` rows;
- best average quantile score: `fixed_250`;
- BAWS did not beat the best fixed window in this local empirical subset.

This section is superseded by the S&P 500 backfill update below. It is retained
only to preserve the audit trail of the pre-backfill run.

## GroupA+ Import Decision

The GroupA+-specific experiments are more relevant than generic synthetic
paper replication for live strategy promotion.

Completed GroupA+ windows:

| Window | BAWS quantile wins | BAWS FZ-style wins | SAWS-like wins | Portfolio final delta | Promotion |
|---|---:|---:|---:|---:|---|
| 2020 COVID | 0/4 | 0/4 | 0/4 | -20,102 | false |
| 2022 rate hike | 0/4 | 0/4 | 1/4 | +2,160 | false |
| 2024-2026 | 0/4 | 0/4 | 1/4 | -199,776 | false |
| 2025-2026 latest | 0/4 | 0/4 | 0/4 | -125,421 | false |

Decision:

- do not import BAWS into GroupA+ latest strategy;
- do not change `golden1_0531`;
- do not add BAWS to live signal, target weights, execution guard, or orders;
- keep BAWS as research-only diagnostics unless future full-data replication
  and GroupA+ OOS tests both improve materially.

## Production Pointer Check

The live production pointers were checked after the research runs:

```bash
git diff -- \
  report/group_a_plus/latest/strategy.json \
  report/group_a_plus/latest/live_signal.json \
  report/group_a_plus/latest/execution_plan.json
```

No diff was produced.

## S&P 500 Backfill Update

Follow-up completed after the user asked whether S&P 500 index data can be
backfilled further.

Command:

```bash
.venv/bin/python scripts/fetch/fetch_cross_market_ohlcv.py \
  --tickers '^GSPC' \
  --start 2005-01-04 \
  --end 2026-08-14 \
  --output results/cross_market_ohlcv_gspc_backfill_20050104_20260814.json
```

Result:

- `external_market_ohlcv` now has `^GSPC` prices from `2005-01-04` to
  `2026-08-13`;
- price rows: `5436`;
- first close: `2005-01-04`, `1188.050048828125`;
- latest close: `2026-08-13`, `7798.990234375`.

The paper-replication script was updated so the empirical section no longer
hard-codes the old 2019-only caveat.

New empirical-only BAWS report after backfill:

- `results/2603_01157_baws_sp500_empirical_backfilled_2005_b1000_stride20.json`
- `report/group_a_plus/latest/2603_01157_baws_sp500_empirical_backfilled_2005_b1000_stride20.md`

Backfilled S&P 500 empirical run:

- status: `available_full_local_cache`;
- loss window: `2005-01-05` to `2026-08-13`, `5435` rows;
- evaluated dates with `forecast_stride=20`: `2008-12-26` to `2026-07-27`,
  `222` rows;
- best quantile-score method: `baws`;
- average quantile scores:
  - `baws`: `0.0015734577482571035`;
  - `fixed_250`: `0.001620065506831623`;
  - `fixed_500`: `0.0016015012817371583`;
  - `fixed_750`: `0.0015734577482571035`;
  - `full`: `0.001659961730980468`;
  - `saws_lite`: `0.0016521804271897873`.

Interpretation:

- the generic S&P 500 empirical subset now supports BAWS under this local
  stride-20 run;
- this does not override the GroupA+ decision, because GroupA+ ETF/portfolio
  tests remain negative and production pointers still have no diff.

## Current Handoff State

As of this handoff, the practical state is:

- S&P 500 index data gap is closed for the paper's requested start date;
- paper-style synthetic replication harness exists and is reproducible;
- backfilled S&P 500 empirical run now favors BAWS on local stride-20
  quantile score;
- GroupA+ ETF-specific BAWS tests remain negative;
- latest strategy, live signal, execution plan, and order outputs are unchanged.

Important files:

- `scripts/evaluate/evaluate_2603_01157_baws_paper_replication.py`
  - paper-style synthetic and empirical replication harness;
  - empirical caveat now checks actual cache coverage instead of hard-coding
    the old 2019 cache limitation.
- `scripts/evaluate/evaluate_group_a_plus_baws_extended_experiments.py`
  - GroupA+-specific BAWS/FZ/SAWS-lite/portfolio replay evaluator.
- `scripts/evaluate/evaluate_group_a_plus_baws_lite_var_es_shadow.py`
  - existing BAWS-lite evaluator;
  - moving-block bootstrap threshold calculation was vectorized for speed;
  - method logic unchanged.
- `results/cross_market_ohlcv_gspc_backfill_20050104_20260814.json`
  - S&P 500 backfill report.
- `results/2603_01157_baws_sp500_empirical_backfilled_2005_b1000_stride20.json`
  - current backfilled empirical S&P 500 BAWS result.
- `report/group_a_plus/latest/2603_01157_baws_sp500_empirical_backfilled_2005_b1000_stride20.md`
  - readable summary of the backfilled empirical S&P 500 run.
- `results/group_a_plus_baws_extended_experiments_*_b1000.json`
  - GroupA+ window-level import experiments.
- `report/group_a_plus/latest/baws_extended_experiments_*_b1000.md`
  - readable summaries for GroupA+ windows.

Verification already run:

- `py_compile` passed for the BAWS paper replication script;
- `py_compile` previously passed for both GroupA+ BAWS evaluators;
- `pytest tests/test_evaluate_group_a_plus_baws_lite_var_es_shadow.py -q`
  passed with `3 passed`;
- `git diff -- report/group_a_plus/latest/strategy.json report/group_a_plus/latest/live_signal.json report/group_a_plus/latest/execution_plan.json`
  produced no output.

Recommended next steps if a future run needs closer paper replication:

1. Run the empirical S&P 500 section with `forecast_stride=1`.
2. Increase empirical bootstrap samples only if runtime is acceptable.
3. Run synthetic A1-A3/B1-B3/GARCH with higher replications toward the paper's
   `1000` replication target.
4. Replace `saws_lite` and the approximate GARCH innovations only if exact
   SAWS and Fernandez-Steel skewed Student-t replication is required.
5. Keep all of the above research-only until GroupA+ ETF and portfolio
   promotion gates are positive.

Do not promote BAWS into GroupA+ solely because the backfilled S&P 500
empirical run improved. The production decision must be based on GroupA+'s
Taiwan ETF universe and costed portfolio replay, where the evidence remains
negative.
