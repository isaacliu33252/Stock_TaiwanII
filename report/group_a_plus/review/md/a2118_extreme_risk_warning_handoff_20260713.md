# A21.18 Extreme Risk Warning Handoff

Date: 2026-07-13
Status: research-only advisory integrated into live signal output

## Policy

This warning does not change target weights and does not affect execution guards.

When active, it means:

- pause new 0050 risk adds
- pause new 00631L risk adds
- do not auto-sell existing 0050 or 00631L

## Trigger

The warning is active only when all conditions hold:

- A21.18 NCF live signal is current
- current regime is `golden1`
- `h20_prob_up <= 0.22`
- `prob_fwd_mdd_gt5_h20 >= 0.85`

## Live Signal Fields

Daily signal writes:

- `ncf_live_overlay.a2118_extreme_risk_warning`
- `signal_alerts[].type == "a2118_extreme_risk_warning"` when active

Alert metadata includes:

- `policy: warning_only_no_weight_change`
- `recommended_action: pause_new_risk_adds`
- `allow_new_0050_add`
- `allow_new_00631l_add`
- threshold and input diagnostics

## Execution Guard

Execution planning reads the alert through `apply_risk_add_pre_trade_guard`.

When active, it:

- blocks target shares above current holdings for `0050.TW`
- blocks target shares above current holdings for `00631L.TW`
- allows holds and reductions
- leaves other tickers untouched

The legacy volatility gate remains separate and still only blocks new `00631L.TW` exposure.

## Validation

Shadow warning-only report:

- `results/a2118_mpc_path_shadow_warning_only_cashbuffer_h22_m85_20260713.json`

Active 2025-2026 warning days:

- count: 9
- 1-day hedge-help rate: 77.8%
- 5-day hedge-help rate: 66.7%
- 20-day hedge-help rate: 88.9%
- mean 20-day `00631L - 0050`: -2.58%

The same signal failed as an automatic trading overlay because turnover and transaction costs erased the benefit. Keep it advisory-only unless a separate future sweep proves an executable rule.

## Verification

- `pytest -q tests/test_group_a_plus_daily_signal_v2.py`: 45 passed
- `pytest -q tests/test_group_a_plus_execution_guard.py tests/test_group_a_plus_execution_plan_v2.py`: 16 passed
- `pytest -q tests/test_evaluate_a2118_mpc_path_shadow.py`: 15 passed
- `python3 -m py_compile group_a_plus/operations/daily_signal.py group_a_plus/runners/a2118.py`

The execution-plan smoke test confirms that an active warning removes 0050/00631L buy trades from the final plan while preserving unrelated buys.
