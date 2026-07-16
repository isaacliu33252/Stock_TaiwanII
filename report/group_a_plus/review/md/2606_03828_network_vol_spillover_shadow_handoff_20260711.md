# 2606.03828 Network Volatility Spillover Shadow Handoff

Date: 2026-07-11

Paper: Network Time Series Models for Multivariate Volatility Forecasting

Source PDF: C:\Users\isaac\Downloads\2606.03828v1.pdf

## Paper Points Imported

- Use a network of cross-asset volatility spillovers instead of only single-asset volatility.
- Treat network connectedness as a systemic risk state that can rise before or during contagion.
- Prefer a parsimonious global/network coefficient style before attempting a full joint volatility model.
- Use the signal first as advisory risk context, not as a direct trading rule.

## GroupA+ Shadow Implementation

Added a pure shadow integration:

- `group_a_plus/integrations/network_volatility_spillover_shadow.py`
- `scripts/evaluate/build_group_a_plus_network_volatility_spillover_shadow.py`
- `scripts/evaluate/evaluate_group_a_plus_recovery_boost_spillover_gate.py`
- `tests/test_group_a_plus_network_volatility_spillover_shadow.py`

The implementation builds a rolling lagged realized-volatility spillover frame from existing OHLCV data:

- log realized variance proxy from daily returns
- rolling lagged correlation from source volatility at t-1 to destination volatility at t
- edge density
- mean absolute edge strength
- systemic spillover score
- 0050 in-spillover, out-spillover, and net pressure
- 252-day percentiles
- crisis regime flag
- recovery-boost advisory gate

Default network tickers:

- `0050.TW`
- `00631L.TW`
- `00632R.TW`
- `00679B.TWO`
- `00646.TW`
- `00713.TW`
- `00878.TW`

## Latest Snapshot

Generated artifact:

- `results/group_a_plus_network_vol_spillover_shadow_latest.json`
- `results/group_a_plus_network_vol_spillover_shadow_frame_latest.csv`

Latest available date: 2026-07-09

Snapshot:

- edge density: 0.2857142857142857
- mean absolute strength: 0.18548227173181875
- systemic score: 0.05299493478051964
- systemic percentile 252d: 1.0
- 0050 in-spillover percentile 252d: 0.996031746031746
- crisis regime: true
- recovery boost advisory: blocked

Interpretation:

- The current shadow network state is elevated.
- It is useful as a daily risk alert and review flag.
- It is not yet a proven trading gate because the clean replay did not find changed recovery-boost days.

## Recovery Boost Gate Test

Generated artifact:

- `results/group_a_plus_recovery_boost_spillover_gate_20260711.json`

Result:

- A21.28 spillover p80/p90/p95 matched age20 baseline.
- A21.29 spillover p80/p90/p95 matched age20 baseline.
- Blocked recovery days in the tested clean windows: 0.

Conclusion:

- Do not promote this as a trading weight rule yet.
- Keep as shadow risk alert.
- Production strategy remains unchanged.

## Alert Integration

Added daily alert/commentary plumbing:

- `group_a_plus/operations/alert_state.py`
- `scripts/run/update_group_a_plus_alert_state.py`
- `tests/test_group_a_plus_alert_state.py`

Behavior:

- If spillover is elevated, emit `network_spillover_high`.
- The alert is advisory-only and carries `trade_policy=advisory_no_auto_weight_change`.
- If the spillover snapshot date does not match the live signal date, emit `network_spillover_snapshot_stale` instead of using stale gate decisions.

Shadow alert output:

- `results/group_a_plus_alert_state_with_network_spillover_shadow_20260711.json`

Current output for signal date 2026-07-09:

- emitted `network_spillover_high`
- level: high
- allow recovery boost: false
- reason: `spillover_blocked`

## Verification

Commands run:

- `.venv/bin/python -m pytest tests/test_group_a_plus_network_volatility_spillover_shadow.py tests/test_group_a_plus_volatility_forecast.py`
- `.venv/bin/python -m pytest tests/test_group_a_plus_alert_state.py tests/test_group_a_plus_push_notifications.py tests/test_group_a_plus_network_volatility_spillover_shadow.py`
- `.venv/bin/python -m py_compile group_a_plus/operations/alert_state.py scripts/run/update_group_a_plus_alert_state.py group_a_plus/integrations/network_volatility_spillover_shadow.py scripts/evaluate/build_group_a_plus_network_volatility_spillover_shadow.py scripts/evaluate/evaluate_group_a_plus_recovery_boost_spillover_gate.py`

Results:

- 9 passed for spillover/volatility tests.
- 32 passed for alert/push/spillover tests.
- py_compile passed.

## Decision

Do not導入 production target weights yet.

導入 status:

- Yes: shadow signal.
- Yes: daily advisory alert.
- No: automatic 00631L weight change.
- No: production promotion.

## Next Candidate To Test

Next useful paper import:

- network-spillover trend / acceleration signal

Rationale:

- A static percentile did not change recovery-boost trading days in clean replay.
- The paper's useful edge may be not the level itself, but whether connectedness is rising quickly.
- Test as an advisory or recovery-boost block only when systemic spillover percentile is high and its 5-day/10-day slope is positive.

