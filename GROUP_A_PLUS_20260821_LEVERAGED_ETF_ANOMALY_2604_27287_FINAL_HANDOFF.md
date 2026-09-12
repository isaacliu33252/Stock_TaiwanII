# GroupA+ 2604.27287v1 Leveraged ETF Anomaly Final Handoff - 2026-08-21

## Status

Final decision: `do_not_promote_keep_shadow`.

The paper was analyzed, converted into GroupA+ shadow diagnostics, tested
against 00631L/00632R Taiwan ETF data, promoted to a multi-window guard
backtest, then refined with stricter trigger policies. The result is useful as
a manual warning / diagnostic only. It is not robust enough to change GroupA+
latest strategy, golden1_0531, daily signals, execution plans, or order files.

## User Request

User provided:

`C:\Users\isaac\Downloads\2604.27287v1.pdf`

Question:

Analyze whether the paper has useful advantages that can be imported into
GroupA+ and the latest strategy.

## Paper Summary

Paper: `arXiv:2604.27287v1 A Levered ETF Anomaly Explained`

Core idea:

Long-horizon levered ETF performance is not explained only by underlying return,
target leverage, and volatility drag. A major residual term can come from the
covariance between realized effective daily leverage and the underlying daily
return.

For GroupA+, the importable diagnostic is:

- realized effective leverage = ETF daily return / 0050 daily return;
- winsorized ratio handling when 0050 daily return is tiny;
- annualized covariance between effective leverage and 0050 return;
- gap between observed ETF return and ideal constant-leverage return;
- volatility drag via approximate geometric return.

This is not an alpha model. It does not forecast returns by itself. It can only
support manual risk review before changing 00631L/00632R exposure.

## Implemented Files

Core diagnostic:

- `group_a_plus/integrations/leveraged_etf_timing_anomaly.py`

Diagnostic evaluator:

- `scripts/evaluate/evaluate_group_a_plus_leveraged_etf_timing_anomaly.py`

Promotion backtest:

- `scripts/evaluate/backtest_group_a_plus_leveraged_etf_timing_guard.py`

Tests:

- `tests/test_leveraged_etf_timing_anomaly.py`
- `tests/test_leveraged_etf_timing_guard_backtest.py`

Detailed docs/report artifacts:

- `docs/HANDOFF_2604_27287_LEVERAGED_ETF_ANOMALY_GROUPA_PLUS_REVIEW_20260821.md`
- `report/group_a_plus/latest/leveraged_etf_timing_anomaly_2604_27287.md`
- `report/group_a_plus/latest/leveraged_etf_timing_guard_backtest_2604_27287.md`
- `report/group_a_plus/latest/leveraged_etf_timing_guard_backtest_2604_27287_negcov.md`
- `report/group_a_plus/latest/leveraged_etf_timing_guard_backtest_2604_27287_negcov_drag_p3.md`

Result artifacts:

- `results/group_a_plus_leveraged_etf_timing_anomaly_2604_27287.json`
- `results/group_a_plus_leveraged_etf_timing_anomaly_2604_27287.csv`
- `results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287.json`
- `results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287.csv`
- `results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287_negcov.json`
- `results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287_negcov.csv`
- `results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287_negcov_drag_p3.json`
- `results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287_negcov_drag_p3.csv`

## Diagnostic Run

Command:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_leveraged_etf_timing_anomaly.py
```

Window:

- 2015-01-05 through 2026-08-20
- 2,828 aligned rows
- 252-day rolling window

00631L.TW:

- average effective leverage: 1.671 vs target 2.0;
- full-sample ratio-return covariance: +9.16% annualized;
- latest 252-day ratio-return covariance: -21.41% annualized;
- volatility drag estimate: -10.48%;
- latest rolling warnings: negative ratio-return covariance and large
  volatility drag;
- decision: `shadow_warning_for_manual_00631l_or_00632r_review`.

00632R.TW:

- average effective leverage: -0.736 vs target -1.0;
- full-sample ratio-return covariance: -8.47% annualized;
- latest 252-day ratio-return covariance: +10.05% annualized;
- volatility drag estimate: -103.46%;
- full-sample warnings: negative ratio-return covariance, average effective
  leverage away from target, and large volatility drag;
- decision: `shadow_warning_for_manual_00631l_or_00632r_review`.

Diagnostic conclusion:

The paper's signal is real enough to monitor, especially because 00631L's latest
rolling covariance is negative, but it is not enough to trade.

## Promotion Backtest Design

Script:

`scripts/evaluate/backtest_group_a_plus_leveraged_etf_timing_guard.py`

Method:

- use `group_a_plus.runners.latest.run_latest()` to replay latest strategy;
- use `_simulate_costed_curve()` with existing project cost assumptions;
- use previous-day warning only, so no same-day lookahead;
- compare baseline latest vs timing-guard variants;
- require every window to improve final value, Sharpe, Sortino, and not worsen
  max drawdown.

Backtest windows:

- `full_2016_2026`: 2016-01-04 to latest;
- `rate_hike_2022_2023`: 2022-01-03 to 2023-12-29;
- `live_2024_2026`: 2024-01-02 to latest;
- `active_2025_2026`: 2025-01-02 to latest.

Variants:

- `00631l_only`: move guarded 00631L weight to 0050;
- `00632r_only`: move guarded 00632R weight to cash;
- `combined`: apply both.

## Initial Backtest Result

Command:

```bash
.venv/bin/python scripts/evaluate/backtest_group_a_plus_leveraged_etf_timing_guard.py
```

Decision: `do_not_promote_keep_shadow`.

Variant summary:

- `00631l_only`: 1 of 4 windows promotion-ready; average final-value delta
  -16,479.54; average Sharpe delta +0.0028.
- `00632r_only`: 0 of 4 windows promotion-ready; average final-value delta
  -55,429.51; average Sharpe delta -0.0134.
- `combined`: 0 of 4 windows promotion-ready; average final-value delta
  -68,331.38; average Sharpe delta -0.0064.

Window details:

- `full_2016_2026`: all variants reduce final value.
- `rate_hike_2022_2023`: all variants reduce final value and Sharpe.
- `live_2024_2026`: `00631l_only` improves final value by +3,293.52 and passes
  that single window.
- `active_2025_2026`: `00631l_only` reduces final value by -39,755.34 even
  though Sharpe/Sortino rise.

## Refinement Sweep

Because the initial warning fired too often, the guard was parameterized:

- `--warning-policy any_warning`
- `--warning-policy negative_covariance`
- `--warning-policy negative_covariance_and_large_drag`
- `--persistence-days N`

### Negative Covariance Only

Command:

```bash
.venv/bin/python scripts/evaluate/backtest_group_a_plus_leveraged_etf_timing_guard.py \
  --warning-policy negative_covariance \
  --output results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287_negcov.json \
  --csv results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287_negcov.csv \
  --markdown report/group_a_plus/latest/leveraged_etf_timing_guard_backtest_2604_27287_negcov.md
```

Decision: `do_not_promote_keep_shadow`.

Key results:

- `00631l_only`: 1 of 4 windows promotion-ready; average final-value delta
  -34,552.27.
- `00632r_only`: 0 of 4 windows promotion-ready; average final-value delta
  -21,600.62.
- `combined`: 1 of 4 windows promotion-ready; average final-value delta
  -34,208.21.
- `00631l_only` still loses -39,755.34 in `active_2025_2026`.

### Negative Covariance And Large Drag, Persistence 3

Command:

```bash
.venv/bin/python scripts/evaluate/backtest_group_a_plus_leveraged_etf_timing_guard.py \
  --warning-policy negative_covariance_and_large_drag \
  --persistence-days 3 \
  --output results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287_negcov_drag_p3.json \
  --csv results/group_a_plus_leveraged_etf_timing_guard_backtest_2604_27287_negcov_drag_p3.csv \
  --markdown report/group_a_plus/latest/leveraged_etf_timing_guard_backtest_2604_27287_negcov_drag_p3.md
```

Decision: `do_not_promote_keep_shadow`.

Key results:

- `00631l_only`: 1 of 4 windows promotion-ready; average final-value delta
  -32,439.20.
- `00632r_only`: 0 of 4 windows promotion-ready; average final-value delta
  -5,632.43.
- `combined`: 1 of 4 windows promotion-ready; average final-value delta
  -31,904.21.
- 00632R warning count drops materially, but after-cost portfolio utility is
  still not enough.
- `00631l_only` improves `live_2024_2026` by +3,985.44, but loses -39,493.19 in
  `active_2025_2026` and -91,863.54 in `full_2016_2026`.

Refinement conclusion:

Stricter triggers reduce noise but do not fix cross-window fragility. Do not
continue live-promotion work for this exact guard design.

## Tests

Commands run:

```bash
.venv/bin/python -m pytest tests/test_leveraged_etf_timing_anomaly.py -q
```

Result:

- 4 passed.

```bash
.venv/bin/python -m pytest tests/test_leveraged_etf_timing_anomaly.py tests/test_leveraged_etf_timing_guard_backtest.py -q
```

Results:

- 6 passed before refinement.
- 7 passed after refinement.

## Production Impact

No production strategy files were intentionally changed.

Not changed:

- latest strategy manifest;
- `golden1_0531`;
- daily signal output;
- execution plan;
- target weights;
- order files.

All changes are research/shadow scripts, tests, result artifacts, and handoff
documents.

## Final Recommendation

Keep the diagnostic as a research/manual warning:

- useful when reviewing 00631L/00632R exposure;
- useful to explain why simple constant-leverage assumptions can be misleading;
- useful as context next to existing compounding, volatility, GARCH, BAWS, and
  crash-risk diagnostics.

Do not promote any timing guard from this paper into GroupA+ latest strategy.

Only reopen promotion work if a materially different action is proposed, such
as:

- partial cap instead of full 00631L-to-0050 shift;
- only blocking new 00631L additions rather than reducing existing exposure;
- using the timing anomaly as an advisory feature combined with an already
  validated risk gate;
- requiring a separate signed promotion review and multi-window after-cost
  dominance before live wiring.
