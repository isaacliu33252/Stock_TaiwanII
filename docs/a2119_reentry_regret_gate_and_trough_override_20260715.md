# A21.19 Reentry Regret Gate and Trough Override Handoff - 2026-07-15

## Status

A21.19_REENTRY_REGRET_GATE is not promoted as a production execution overlay.

The safer research direction is a narrow guard-release shadow:

```text
A21.18 base strategy
  -> H20 crash diagnostic
  -> Trough / rebound nowcast
  -> Volatility gate blocked 00631L add
  -> Optional small override for reentry only
```

This remains research-only.  It must not sell existing 00631L, must not create
a new CAP0/CAP10 de-risk action, and must not buy beyond the A21.18 target.

## A21.19 Regret Gate Result

Evaluator:

```text
scripts/evaluate/evaluate_a2119_reentry_regret_gate.py
```

Key reports:

```text
results/a2119_reentry_regret_gate_shadow_20260715.json
results/a2119_reentry_regret_gate_shadow_live2024_edge00005_20260715.json
results/a2119_reentry_regret_gate_shadow_2017_2019_edge00005_20260715.json
results/a2119_reentry_regret_gate_shadow_live2024_event_20260715.json
results/a2119_reentry_regret_gate_shadow_2017_2019_event_20260715.json
```

Finding:

```text
2025-2026 daily shadow: KEEP only, no non-KEEP actions.
2024-2026 low-edge shadow: KEEP only, no non-KEEP actions.
2017-2019 low-edge shadow: KEEP only, no non-KEEP actions.
```

Event study showed A21.18 was already conservative on 00631L add events:

```text
2024-2026:
event_count = 3
00631L increase events = 2
NO_ADD helped = 0
NO_ADD hurt = 2
mean NO_ADD realized regret = -0.006245

2017-2019:
event_count = 2
00631L increase events = 2
NO_ADD helped = 0
NO_ADD hurt = 2
mean NO_ADD realized regret = -0.002840
```

Interpretation:

```text
Do not veto A21.18 recovery/golden1 reentry.
The opportunity is not automatic de-risking.
The opportunity is fast reentry when another guard blocks a valid rebound.
```

## Buy Attempt Alignment

Evaluator:

```text
scripts/evaluate/evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py
```

Report:

```text
results/group_a_plus_trough_nowcast_buy_attempt_alignment_20260715.json
results/group_a_plus_trough_nowcast_buy_attempt_alignment_active_to_20260715.json
```

Default windows:

```text
active_2025_2026: 2025-01-02..2026-07-09
covid_2020: 2020-01-02..2020-12-31
inflation_2022: 2022-01-03..2022-12-30
2018_correction: 2018-01-02..2018-12-31
```

Totals:

```text
buy_attempt_days = 348
partial_reentry_days = 39
partial_reentry_buy_attempt_days = 7
allowed_fast_reentry_days = 4
blocked_fast_reentry_days = 3
blocked_by_volatility_gate = 3
blocked_by_extreme_risk = 0
missed_rebound_blocked_by_guard = 2
```

The two relevant missed rebound events were:

```text
2026-03-25:
trough_state = PARTIAL_REENTRY
volatility_gate = high_vol_defensive
attempted 00631L add = 1.0545%
00631L forward return 5d = +4.2536%
00631L forward return 10d = +17.6577%

2026-06-29:
trough_state = PARTIAL_REENTRY
volatility_gate = high_vol_defensive
attempted 00631L add = 0.5417%
00631L forward return 3d = +7.1665%
00631L forward return 5d = +6.8082%
```

Active window extended to 2026-07-15:

```text
window = 2025-01-02..2026-07-15
buy_attempt_days = 115
partial_reentry_days = 10
partial_reentry_buy_attempt_days = 3
blocked_fast_reentry_days = 3
blocked_by_volatility_gate = 3
missed_rebound_blocked_by_guard = 2
```

## Volatility Gate Override Shadow

Evaluator:

```text
scripts/evaluate/evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py
```

Report:

```text
results/group_a_plus_trough_nowcast_vol_gate_override_shadow_20260715.json
results/group_a_plus_trough_nowcast_vol_gate_override_shadow_active_to_20260715.json
```

Override eligibility:

```text
trough_state == PARTIAL_REENTRY
volatility_gate == high_vol_defensive
attempted 00631L buy > 0.25%
extreme risk guard is false
confirmation mode passes
```

Policies tested:

```text
no_override
micro_override_25pct
small_override_50pct
```

Confirmation modes tested:

```text
none
second_partial
no_lower_low_3d
second_or_no_lower_low_3d
```

Default-window totals:

```text
micro_override_25pct:
eligible days = 2
delta final value = +634.66
delta sharpe sum = +0.000365
delta max drawdown sum = 0.0

small_override_50pct:
eligible days = 2
delta final value = +1205.17
delta sharpe sum = +0.000610
delta max drawdown sum = 0.0
```

`no_lower_low_3d` and `second_or_no_lower_low_3d` produced the same result as
no confirmation because both eligible events had no fresh 0050 lower low.
`second_partial` produced zero events.

Window split:

```text
active_2025_2026:
micro_override_25pct delta final value = +634.66
small_override_50pct delta final value = +1205.17
eligible days = 2

covid_2020:
eligible days = 0
delta = 0

inflation_2022:
eligible days = 0
delta = 0

2018_correction:
eligible days = 0
delta = 0
```

Active window extended to 2026-07-15:

```text
micro_override_25pct:
eligible days = 2
delta final value = +636.93
delta sharpe sum = +0.000362
delta max drawdown sum = 0.0

small_override_50pct:
eligible days = 2
delta final value = +1209.47
delta sharpe sum = +0.000605
delta max drawdown sum = 0.0
```

## Decision

Do not promote A21.19_REENTRY_REGRET_GATE as KEEP/NO_ADD/REENTER automation.

Keep this candidate as a research-only reentry guard-release module:

```text
Name: A21.19_REENTRY_GUARD_RELEASE_SHADOW
Preferred policy: small_override_50pct__no_lower_low_3d
Production effect today: none
Allowed action in future: partial release of high-vol 00631L add block only
Forbidden action: sell/reduce existing 00631L
Forbidden action: add above A21.18 target
```

Promotion requirements before any live use:

```text
1. More eligible events across added crisis/rebound windows.
2. Explicit transaction-cost/slippage stress.
3. Verify with latest 2026-07-15 data after all stale chip/TAIFEX sources refresh.
4. Add a daily advisory field first; do not wire into execution sizing.
```

## Regeneration Commands

```bash
.venv/bin/python scripts/evaluate/evaluate_a2119_reentry_regret_gate.py \
  --start 2024-01-02 \
  --end 2026-07-15 \
  --edge-threshold 0.0005 \
  --output results/a2119_reentry_regret_gate_shadow_live2024_edge00005_20260715.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py \
  --output results/group_a_plus_trough_nowcast_buy_attempt_alignment_20260715.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py \
  --output results/group_a_plus_trough_nowcast_vol_gate_override_shadow_20260715.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_trough_nowcast_buy_attempt_alignment.py \
  --windows active_2025_2026_to_20260715,2025-01-02,2026-07-15,results/ncf_00631l_panel_latest_20260707.csv,tuning_window \
  --output results/group_a_plus_trough_nowcast_buy_attempt_alignment_active_to_20260715.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py \
  --windows active_2025_2026_to_20260715,2025-01-02,2026-07-15,results/ncf_00631l_panel_latest_20260707.csv,tuning_window \
  --output results/group_a_plus_trough_nowcast_vol_gate_override_shadow_active_to_20260715.json
```

## Verification

Tests run on 2026-07-15:

```text
.venv/bin/python -m pytest -q \
  tests/test_evaluate_group_a_plus_trough_nowcast_vol_gate_override_shadow.py \
  tests/test_evaluate_a2119_reentry_regret_gate.py

Result: 6 passed
```
