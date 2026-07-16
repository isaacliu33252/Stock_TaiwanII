# GroupA+ A21.28/A21.29 Recovery Boost Shadow Handoff

Date: 2026-07-11

Workspace: `C:\Users\isaac\Downloads\Stock_taiwan2-main\Stock_taiwan2-main`

## Executive Decision

Production GroupA+ remains unchanged.

- production strategy: `a2118_a2111_ncf_late_bull_deleverage`
- production runner: `group_a_plus.runners.a2118`
- production manifest: `report/group_a_plus/latest/strategy.json`
- production decision: `do_not_promote`

Shadow observation is enabled through a shadow-only manifest:

- preferred shadow: `a2129_recovery_00631l_boost_age_guard_aggressive_shadow`
- conservative shadow: `a2128_recovery_00631l_boost_age_guard_shadow`
- shadow manifest: `report/group_a_plus/shadow/a2129_recovery_boost_age_guard_strategy.json`
- shadow scorecard: `report/group_a_plus/shadow/recovery_boost_age_guard_scorecard_20260711.json`

The central finding is:

```text
Recovery boost is only viable with an age guard.
Enable boost only during the first 20 trading days of a recovery episode.
Do not use unbounded recovery boost.
Do not relax the age guard to 30 days.
```

## Strategy Summary

All candidates leave defensive entry, formal exit, NCF late-bull de-leverage,
and production allocation logic unchanged. They only change the existing
`group_a_plus_recovery` allocation while the system is already in recovery.

| Strategy | Role | Recovery boost | Max recovery age | Status |
| --- | --- | ---: | ---: | --- |
| A21.27 | deprecated shadow candidate | 10% 0050 -> 00631L | none | not preferred |
| A21.28 | conservative shadow | 10% 0050 -> 00631L | 20 trading days | keep shadow |
| A21.29 | preferred shadow | 15% 0050 -> 00631L | 20 trading days | keep shadow |

The age guard means each recovery episode is counted independently. Once a
single recovery episode exceeds 20 trading days, boosted recovery weights are
disabled and the system falls back to normal recovery weights.

## Why A21.27 Was Rejected

A21.27 originally looked attractive on the clean recent/OOS replay:

| Variant | Clean tuning final delta | Clean OOS final delta | Clean changed days |
| --- | ---: | ---: | ---: |
| `recovery_boost_010` | +2655.042 | +3116.456 | 32 |

However, five-crisis stress testing showed that unbounded recovery boost fails
on 2011-style long, weak recovery regimes.

| Variant | Five-crisis rebased final delta | Positive folds | Rebased Sharpe delta | Boosted days |
| --- | ---: | ---: | ---: | ---: |
| `recovery_boost_010` | -2071.194 | 2/5 | -0.008155 | 236 |

Primary failure mode:

- 2008 recovery episodes were short; boost helped.
- 2011 recovery episodes were long and weak; boost stayed active too long and
  became harmful.
- Therefore, unbounded boost is not robust enough for preferred shadow status.

## Age Guard Evidence

The key feature comparison was recovery episode age:

| Fold | Report recovery days | Recovery age profile | Interpretation |
| --- | ---: | --- | --- |
| 2008 GFC proxy | 37 | max age 10 | short recovery bursts; boost acceptable |
| 2011 Euro debt proxy | 199 | median age 41, max age 140 | long weak recovery; unbounded boost harmful |

This motivated an age guard sweep.

Five-crisis stress results:

| Variant | Rebased final delta | Positive folds | Rebased Sharpe delta | Boosted days | Decision |
| --- | ---: | ---: | ---: | ---: | --- |
| `recovery_boost_010` | -2071.194 | 2/5 | -0.008155 | 236 | reject |
| `recovery_boost_010_age20` | +9072.220 | 3/5 | +0.015100 | 114 | keep conservative shadow |
| `recovery_boost_010_age30` | +490.100 | 2/5 | -0.003000 | 126 | reject |
| `recovery_boost_015_age20` | +13843.174 | 3/5 | +0.023000 | 114 | keep preferred shadow |
| `recovery_boost_015_age30` | +1851.900 | 2/5 | -0.002300 | 126 | reject |

The 20-day guard is the useful cutoff. Relaxing to 30 days lets 2011-style
risk leak back in.

## Clean Replay Evidence

Clean replay windows:

- `covid_2020`
- `inflation_2022`
- `live_2024_2026`
- `active_2025_2026`
- `2017_bull`
- `2018_correction`
- `2019_recovery`

Key clean replay results:

| Variant | Tuning final delta | OOS final delta | Tuning Sharpe delta | OOS Sharpe delta | Changed days |
| --- | ---: | ---: | ---: | ---: | ---: |
| `recovery_boost_010` | +2655.042 | +3116.456 | +0.002000 | +0.023830 | 32 |
| `recovery_boost_100_age20` | +2655.042 | +1733.196 | +0.002000 | +0.014054 | 22 |
| `recovery_boost_150_age20` | +3827.114 | +2669.600 | +0.002879 | +0.021294 | 22 |

Interpretation:

- Age guard reduces some 2017 bull upside because it cuts off the last 10 days
  of a 30-day recovery episode.
- That upside reduction is acceptable because the same guard materially
  improves five-crisis robustness.
- A21.29 improves both clean replay and five-crisis score versus A21.28, but
  remains more aggressive and therefore stays shadow-only.

## Scorecard Decision

Scorecard file:

- `report/group_a_plus/shadow/recovery_boost_age_guard_scorecard_20260711.json`

Scorecard ranking:

| Strategy | Clean total final delta | Five-crisis rebased final delta | Composite score | Shadow decision |
| --- | ---: | ---: | ---: | --- |
| A21.29 | +6496.714 | +13843.174 | 23247.515 | preferred shadow |
| A21.28 | +4388.238 | +9072.220 | 15372.254 | conservative shadow |
| A21.27 | +5771.497 | -2071.194 | 3530.600 | not preferred |

Production blockers for all candidates:

- research-only shadow evidence
- limited event count
- not yet observed through enough live/paper forward days

Additional blocker for A21.27:

- no recovery age guard
- five-crisis rebased gate failed

## Implemented Files

Core runner changes:

- `group_a_plus/runners/a2118.py`
  - added `RECOVERY_00631L_BOOST_REGIME`
  - added `_apply_recovery_boost_age_guard`
  - added `recovery_00631l_boost_max_age_days`
  - added CLI flag `--recovery-00631l-boost-max-age-days`

Shadow runners:

- `group_a_plus/runners/a2128.py`
  - 10% recovery 00631L boost
  - max recovery age 20 trading days
- `group_a_plus/runners/a2129.py`
  - 15% recovery 00631L boost
  - max recovery age 20 trading days

Governance:

- `group_a_plus/governance/latest.py`
  - registered A21.28 and A21.29 as supported shadow strategy ids

Evaluation scripts:

- `scripts/evaluate/evaluate_group_a_plus_reentry_accelerator_clean.py`
  - added age guard variants for 5%, 10%, 15% and age 10/20/30
- `scripts/evaluate/evaluate_group_a_plus_recovery_boost_five_crises.py`
  - added five-crisis stress test for fixed and guarded recovery boost variants
- `scripts/evaluate/build_group_a_plus_recovery_boost_shadow_scorecard.py`
  - consolidates clean replay and five-crisis reports into one shadow scorecard

Shadow artifacts:

- `report/group_a_plus/shadow/a2129_recovery_boost_age_guard_strategy.json`
- `report/group_a_plus/shadow/recovery_boost_age_guard_scorecard_20260711.json`

Tests:

- `tests/test_group_a_plus_a2128.py`
- `tests/test_group_a_plus_a2129.py`
- `tests/test_group_a_plus_recovery_boost_shadow_scorecard.py`

## Verification Commands

Executed checks:

```bash
.venv/bin/python -m pytest tests/test_group_a_plus_recovery_boost_shadow_scorecard.py tests/test_group_a_plus_a2128.py tests/test_group_a_plus_a2129.py tests/test_group_a_plus_latest_strategy.py::LatestStrategyTests::test_unknown_strategy_is_rejected
```

Result:

```text
7 passed
```

Additional checks:

```bash
.venv/bin/python -m py_compile group_a_plus/runners/a2118.py group_a_plus/runners/a2128.py group_a_plus/runners/a2129.py group_a_plus/governance/latest.py scripts/evaluate/evaluate_group_a_plus_reentry_accelerator_clean.py scripts/evaluate/evaluate_group_a_plus_recovery_boost_five_crises.py scripts/evaluate/build_group_a_plus_recovery_boost_shadow_scorecard.py
```

A21.29 smoke:

```bash
.venv/bin/python -m group_a_plus.runners.a2129 \
  --start 2025-06-01 \
  --end 2025-06-20 \
  --ncf-panel-631l results/ncf_00631l_panel_latest_20260707.csv \
  --output results/group_a_plus_runner_a2129_smoke_20260711.json \
  --frame-output results/group_a_plus_runner_a2129_smoke_20260711_frame.csv
```

Smoke output confirmed:

```text
strategy = a2129_recovery_00631l_boost_age_guard_aggressive_shadow
boost_fraction = 0.15
max_age = 20
boost_days = 1
recovery_days = 1
```

Known warning:

- Existing pandas `FutureWarning` from `backtest_group_a_plus_switch_policy.py:530`
- This is not caused by the recovery boost change and did not fail execution.

## Operational Guidance

Use A21.29 and A21.28 only as shadow/paper comparisons.

Do:

- keep production manifest unchanged
- monitor A21.29 as preferred shadow
- monitor A21.28 as conservative shadow
- compare live/paper daily output against A21.18
- require more forward shadow evidence before promotion review

Do not:

- route live orders from the shadow manifest
- promote A21.29 solely from current backtests
- use A21.27 as preferred shadow
- remove the age20 guard
- relax age20 to age30 without re-opening crisis validation

## Next Promotion Gate

A future promotion review should require all of the following:

1. A21.29 and A21.28 both replay cleanly through the latest data refresh.
2. A21.29 remains better than A21.28 on combined clean/crisis score.
3. A21.29 does not worsen max drawdown in newly added stress folds.
4. At least several live/paper recovery events are observed without abnormal
   turnover or execution drift.
5. The age20 guard remains part of the candidate.

Until those conditions are met, production stays on A21.18.
