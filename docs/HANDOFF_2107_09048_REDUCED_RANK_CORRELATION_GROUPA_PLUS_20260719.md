# Handoff: 2107.09048 Reduced-Rank Correlation Precursors for GroupA+（2026-07-19）

## Decision

`2107.09048.pdf` is research-useful but not live-ready.

Import only as governance / shadow research:

- reduced-rank correlation matrix concept;
- largest-eigenvalue market-mode subtraction;
- averaged-distance transition monitor;
- k-means market-state snapshot idea;
- systemic-fragility manual-review warning candidate.

Do not import as:

- crash predictor;
- execution gate;
- optimizer;
- rebalance trigger;
- `00631L` add permission;
- `00632R` open permission.

## Why Blocked

- Paper uses `250` stocks with full sector coverage.
- GroupA+ live tradable universe is too small for equivalent sector-state
  clustering.
- Taiwan/cross-market proxy would be weaker and needs walk-forward validation.
- Dot-com evidence is weaker than Lehman evidence; transition can be concurrent
  or after the event.
- Existing GroupA+ guards already block leverage add and inverse ETF open.

## Current Strategy

Latest 2026-07-20 estimate remains:

- strategy: `a2118_a2111_ncf_late_bull_deleverage`;
- regime: `golden1`;
- `0050.TW`: `50%`;
- `00631L.TW`: about `19.954%`;
- `00632R.TW`: `0%`;
- `00679B.TWO`: `0%`;
- cash: about `30.046%`.

Manual holdings stance remains:

- `00631L = 500`, do not add;
- `00632R = 0`, do not open;
- 0050 action depends on actual cash and final `00679B` shares.

## Artifacts

- `docs/2107_09048_REDUCED_RANK_CORRELATION_CRISIS_PRECURSOR_GROUPA_PLUS_REVIEW_20260719.md`
- `docs/HANDOFF_2107_09048_REDUCED_RANK_CORRELATION_GROUPA_PLUS_20260719.md`
- `docs/DETAILED_HANDOFF_2107_09048_REDUCED_RANK_CORRELATION_GROUPA_PLUS_20260720.md`
- `docs/GROUPA_PLUS_PDF_RESEARCH_DECISION_MATRIX_20260717.md`
- `scripts/evaluate/build_group_a_plus_reduced_rank_correlation_readiness_review.py`
- `tests/test_build_group_a_plus_reduced_rank_correlation_readiness_review.py`
- `report/group_a_plus/latest/reduced_rank_correlation_readiness_review.json`
- `report/group_a_plus/reduced_rank_correlation_readiness/history/reduced_rank_correlation_readiness_20260720.json`
- `scripts/evaluate/build_group_a_plus_reduced_rank_correlation_proxy.py`
- `tests/test_build_group_a_plus_reduced_rank_correlation_proxy.py`
- `report/group_a_plus/latest/reduced_rank_correlation_proxy.json`
- `report/group_a_plus/reduced_rank_correlation_proxy/history/reduced_rank_correlation_proxy_20260720.json`
- `scripts/evaluate/sweep_group_a_plus_reduced_rank_correlation_proxy_params.py`
- `tests/test_sweep_group_a_plus_reduced_rank_correlation_proxy_params.py`
- `report/group_a_plus/latest/reduced_rank_correlation_proxy_param_sweep.json`
- `report/group_a_plus/reduced_rank_correlation_proxy_param_sweep/history/reduced_rank_correlation_proxy_param_sweep_20260720.json`
- `scripts/evaluate/evaluate_group_a_plus_reduced_rank_correlation_crash_window_backtest.py`
- `tests/test_group_a_plus_reduced_rank_correlation_crash_window_backtest.py`
- `report/group_a_plus/latest/reduced_rank_correlation_crash_window_backtest.json`
- `report/group_a_plus/reduced_rank_correlation_crash_window_backtest/history/reduced_rank_correlation_crash_window_backtest_20260720.json`
- `scripts/evaluate/evaluate_group_a_plus_reduced_rank_confirmation_overlap_backtest.py`
- `tests/test_group_a_plus_reduced_rank_confirmation_overlap_backtest.py`
- `report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest.json`
- `report/group_a_plus/latest/reduced_rank_confirmation_overlap_backtest_frame.csv`
- `report/group_a_plus/reduced_rank_confirmation_overlap_backtest/history/reduced_rank_confirmation_overlap_backtest_20260720.json`
- `report/group_a_plus/latest/research_shadow_decision_snapshot.json`

## Implemented Status

The readiness review is implemented and connected to the research shadow
snapshot.

Latest generated result:

- `as_of`: `2026-07-20`;
- actual data end: `2026-07-17`;
- status: `blocked`;
- local ticker count: `15`;
- external market ticker count: `22`;
- weak proxy ready for research: `true`;
- paper-equivalent readiness: `false`;
- `00631L` add allowed: `false`;
- `00632R` open allowed: `false`.

Parameter sweep:

- candidate count: `24`;
- available candidate count: `24`;
- states: `normal = 16`, `watch = 8`, `elevated_fragility = 0`;
- best candidate: `window=42`, `min_history=63`, `analysis_lookback=504`,
  `min_tickers=12`, `max_stale_days=10`;
- best candidate state: `normal`;
- best candidate manual review required: `false`.

Crash-window backtest:

- total scored days: `4621`;
- stress-window watch-or-worse rate: `0.246711`;
- non-window watch-or-worse rate: `0.424373`;
- stress-window elevated-or-worse rate: `0.016447`;
- non-window elevated-or-worse rate: `0.197358`;
- blocker: false-positive rate exceeds stress-window recall.

Confirmation-gated overlap:

- confirmation sources: `SIN-lite`, `systemic_bubble`;
- base non-window watch rate: `0.424373`;
- confirmed non-window watch rate: `0.084929`;
- base stress watch rate: `0.246711`;
- confirmed stress watch rate: `0.192982`;
- confirmed stress/non ratio: `2.272292`;
- strict both-confirmation sample is too sparse.

Conclusion on improvement:

- Improves shadow research quality and parameter stability tracking.
- Confirmation-gated version improves false-positive control enough to keep as
  manual-review dashboard context.
- Does not improve live decision confidence enough to change GroupA+ weights.
- Keep `00631L` add blocked and `00632R` open blocked.

Weak proxy latest:

- status: `available_for_manual_review`;
- actual data end: `2026-07-17`;
- usable ticker count after stale filtering: `35`;
- latest state: `normal`;
- manual review required by proxy itself: `false`;
- `00631L` add allowed: `false`;
- `00632R` open allowed: `false`.

The paper's idea is now tracked as
`reduced_rank_correlation_readiness_blocked` in the consolidated research
shadow snapshot, while proxy context is visible as
`reduced_rank_proxy_status = available_for_manual_review` and
`reduced_rank_proxy_state = normal`.

Focused tests passed:

- `.venv/bin/python -m pytest tests/test_group_a_plus_reduced_rank_confirmation_overlap_backtest.py tests/test_group_a_plus_reduced_rank_correlation_crash_window_backtest.py tests/test_sweep_group_a_plus_reduced_rank_correlation_proxy_params.py tests/test_build_group_a_plus_reduced_rank_correlation_proxy.py tests/test_build_group_a_plus_reduced_rank_correlation_readiness_review.py tests/test_build_group_a_plus_research_shadow_decision_snapshot.py`
- result: `12 passed`

## Next Candidate Work

Build only if needed:

- broad Taiwan stock universe and sector metadata backfill;
- paper-equivalent 42-day reduced-rank correlation matrix and averaged-distance
  monitor on broad stock universe;
- k-means snapshot view for manual research review.

Promotion blockers:

- broad universe coverage;
- sector or asset-class labels;
- crash-window walk-forward validation;
- false-positive analysis;
- no execution use until validated.
