# Alphalens Factor Lens GroupA+ Handoff - 2026-06-29

## Scope

Integrated a lightweight Alphalens-inspired diagnostics layer for the GroupA+
NCF advisory panel.  This is a research gate and validation tool, not a direct
position-sizing rule yet.

## Added Files

- `group_a_plus/integrations/factor_lens.py`
  - Forward returns
  - Factor quantiles
  - Spearman/Pearson IC
  - Rolling IC
  - Mean forward returns by quantile
  - Upper-minus-lower quantile spread
  - Rank autocorrelation
  - Event-study forward return summaries

- `scripts/evaluate/evaluate_group_a_plus_factor_lens.py`
  - Loads the latest `ncf_advisory_panel_latest_*.csv`
  - Evaluates NCF-derived market factors against `0050.TW`
  - Writes a JSON report under `results/`

- `tests/test_factor_lens.py`
- `tests/test_evaluate_group_a_plus_factor_lens.py`

## Current Report

Generated:

- `results/group_a_plus_factor_lens_20260629.json`

Input panel:

- `results/ncf_advisory_panel_latest_20260629.csv`

Window:

- 2025-01-02 to 2026-05-28
- 337 rows

## Initial Findings

Best IC by horizon:

- 1d: `ncf_00631l_prob_up`, IC `0.1068`
- 5d: `ncf_00631l_prob_up`, IC `0.1413`
- 20d: `ncf_cross_ticker_market_up`, IC `0.1585`

Notable quantile spreads:

- `ncf_00631l_prob_up`: 1d `0.6768%`, 5d `2.0336%`, 20d `5.2159%`
- `ncf_cross_ticker_market_up`: 1d `0.3585%`, 5d `1.3848%`, 20d `5.1710%`
- `ncf_00632r_inverse_market_up`: weak at 1d/5d, better at 20d

Event study:

- High-agreement bullish events: 148
  - 5d mean return `1.5088%`, hit rate `66.22%`
- High-agreement bearish events: 92
  - 5d mean return `1.2315%`, hit rate `62.50%`

Interpretation:

- The NCF advisory factors show positive ranking information versus `0050.TW`.
- The bullish/bearish event study does not yet prove bearish calls should reduce
  exposure by itself, because high-agreement bearish periods still had positive
  average 5d returns in this sample.
- The best immediate use is a research dashboard/gate for strategy changes:
  require stable positive IC and positive high-minus-low spread before enabling
  a new NCF-based trading rule.

## Commands

Run tests:

```bash
.venv/bin/python -m pytest tests/test_tbrain_features.py tests/test_ncf_multiyear_wf.py tests/test_factor_lens.py tests/test_evaluate_group_a_plus_factor_lens.py
```

Run report:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_factor_lens.py
```

Optional explicit panel:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_factor_lens.py \
  --advisory-panel results/ncf_advisory_panel_latest_20260629.csv
```

## Verification

Latest targeted test run:

- 16 passed

## Next Suggested Step

Use Factor Lens output as a threshold gate in daily reporting before connecting
it to live position sizing.  A conservative rule would be:

- enable only factors with positive 1d/5d/20d IC,
- positive top-minus-bottom quantile spread,
- and non-deteriorating rolling IC.

Based on the current report, `ncf_00631l_prob_up` and
`ncf_cross_ticker_market_up` are the first candidates for deeper backtest.
