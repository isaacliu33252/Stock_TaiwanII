# GroupA+ 2008 Shadow Candidate — 2025-2026 Verification Handoff - 2026-07-03

## Executive Summary

Follow-up to `GROUP_A_PLUS_2008_STRESS_TUNING_HANDOFF_20260703.md`, Recommended Next Steps #1:
validate the 2008-proxy shadow candidate config patch on real 2025-2026 GroupA+ overlay data.

Decision: **reject the shadow candidate.** Do not promote. Do not keep tracking it as a shadow
candidate — 2025-2026 real data already gives a clean negative result, so further observation
adds no information.

## What Was Tested

The 2008-proxy micro sweep (see the prior handoff) proposed this patch to
`group_a_plus_config.json`:

```json
{
  "overlay": {
    "dynamic_weight_bands": {"risk_on": 0.0, "caution": 0.01, "risk_off": 0.0, "severe": 0.0}
  },
  "execution_control": {
    "max_turnover_ratio_by_regime": {"risk_on": 1.0, "caution": 1.0, "risk_off": 0.10, "severe": 0.10}
  },
  "fast_risk_off_control": {"cash_floor": 0.35}
}
```

i.e. drop the synthetic 00679B bond sleeve in risk-off/severe regimes, cut the risk-off/severe
turnover cap from 12% to 10%, and raise the fast risk-off cash floor to 35%.

## Method

- Reused existing functions from `backtest_group_a_plus_overlay.py`
  (`_simulate_base_events_approx`, `_simulate_plus`, `_promotion_gate`) — did not reimplement
  the replay/environment logic.
- Data source: `results/group_a_meta_real_vote_tune_sweep_20250101_20260606_llmfilled.json`
  (real 2025-01-02 ~ 2026-06-05 market data, 343 rows — **not** the 2008 TWII proxy).
- Ran the same meta-signal replay twice: once against the unmodified
  `group_a_plus_config.json` (`current_active`), once against an in-memory deep-copy patched
  with the shadow config (`shadow_2008_candidate`). `group_a_plus_config.json` itself was never
  written to.
- Script: `scripts/misc/verify_2008_shadow_candidate_2025_2026.py` (read-only; writes only to
  `results/group_a_plus_2008_shadow_candidate_vs_active_2025_2026_verify.json`, a new filename —
  no existing results file was overwritten).

Repro:

```bash
.venv/bin/python scripts/misc/verify_2008_shadow_candidate_2025_2026.py
```

## Results (2025-01-02 ~ 2026-06-05, real data)

| Mode | final_value | annual_return | Sharpe | MDD | Vol | rebalances |
|---|---:|---:|---:|---:|---:|---:|
| current_active | 2,291,456.39 | 79.24% | 2.9231 | -15.86% | 21.73% | 75 |
| shadow_2008_candidate | 2,284,239.77 | 78.84% | 2.8899 | -15.87% | 21.91% | 73 |

Delta (shadow vs current_active):

| Metric | Delta |
|---|---:|
| final_value | -7,216.62 (-0.32%) |
| Sharpe | **-0.0332** |
| MDD | -0.0058pp (slightly worse) |
| volatility | +0.18pp (slightly worse) |
| rebalances | -2 |

## Acceptance Check (thresholds from the prior handoff)

| Criterion | Threshold | Result | Pass? |
|---|---|---|---|
| final value | no material drop | -0.32% | borderline |
| Sharpe | not below current by more than 0.02 | -0.033 | **fail** |
| MDD | not worse | +0.0058pp worse | **fail** |
| turnover | not materially higher | -2 rebalances (slightly lower) | pass |

Overall: **fails acceptance** (Sharpe and MDD both fail).

## Interpretation

The 2008 TWII proxy stress test showed this patch as a small improvement, because in a 2008-style
crash, cash outperforms the synthetic 00679B bond proxy. On real 2025-2026 data — which is mostly
bull / late-bull, not crash — removing the risk-off/severe bond sleeve and raising the cash floor
does the opposite: it gives up return and Sharpe without buying any real drawdown or volatility
improvement. This is a case of a crash-only tuned parameter set not generalizing to normal-regime
conditions, consistent with the "do not promote on single-window results" caution already in
[[feedback_strategy_promotion_caution]].

## Important Clarification: Two Separate GroupA+ Mechanisms

This overlay path (`group_a_plus_config.json` + `backtest_group_a_plus_overlay._simulate_plus`,
applied on top of the Group A RL/meta-ensemble signal) is **not** the same mechanism as the live
production strategy.

- Live production: `report/group_a_plus/latest/strategy.json` → `active_strategy.id =
  a2118_a2111_ncf_late_bull_deleverage`, runner `group_a_plus.runners.a2118` (MA100 tight-entry
  switch + `bond30_cash30` defensive basket + narrow NCF late-bull de-leverage overlay). This
  code path never reads `group_a_plus_config.json`.
- This verification (and the 2008 stress test it follows up on): a separate, parallel research
  track (`base_strategy: GroupA_meta_ensemble_real_v1`) that overlays `group_a_plus_config.json`
  bands on top of Group A RL model / meta-ensemble outputs.

**This rejection does not touch, and has no effect on, the live a2118 signal generation
currently used by `daily_signal.py`.**

## Files Produced

- `scripts/misc/verify_2008_shadow_candidate_2025_2026.py` (reusable verification script)
- `results/group_a_plus_2008_shadow_candidate_vs_active_2025_2026_verify.json` (raw output)

## Status of Prior Handoff's Recommended Next Steps

1. ~~Validate 2008 shadow candidate on 2025-2026~~ — **done, rejected** (this document).
2. Multi-window stress (2008 / 2015 / 2016 / 2020 / 2022 / 2025-2026) — still open.
3. Keep A21.18 NCF trigger tuning as shadow only — unchanged, still open/no action taken.

## No Production Changes

`group_a_plus_config.json`, `report/group_a_plus/latest/*`, and all runner code
(`group_a_plus/runners/*`) were not modified by this verification.
