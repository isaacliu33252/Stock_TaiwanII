# NCF_2330 — Round 4 Handoff (TXO Options Features, Revenue-Trend Diagnostic) - 2026-07-04

## Executive Summary

Follow-up to `NCF_2330_TSMC_STOCK_MODEL_ROUNDS_2_3_HANDOFF_20260704.md` (Rounds 2 & 3). This
round investigated two specific open questions flagged in that document: whether TXO
(Taiwan index options) features help the tail-risk model, and whether the monthly-revenue
features are a spurious bull-market-timeline proxy.

**Result: the honest best number for the project improves from AUC 0.656 to 0.673** (removing
TXO features from the tail-risk combo). **The revenue-signal-is-spurious hypothesis from Rounds
2/3 is not supported by this round's diagnostic** — it needs to be narrowed, not dropped.

Still standalone/shadow-only. No production files touched, no commits.

## Task 1: TXO Options Features — Net Negative, Recommend Removal

`ncf_2330.py` already had 7 TXO-derived features (`txo_foreign_put_oi`, `txo_foreign_call_oi`,
`txo_foreign_pc_spread`, `txo_foreign_pc_spread_ma5`, `txo_total_pcr`, `txo_pcr_x_ma_gap`,
`txo_foreign_pc_x_vix`), sourced from `derivative_institutional_data` (`product_id='TXO'`).

**Coverage check**: this table only covers 378 of the model's 2,555 total rows (**14.8%**,
2025-01-02 ~ 2026-07-01). Outside that window, all `txo_*` features are silently `fillna(0.0)`
in `build_dataset`/`build_feature_matrix` — not dropped, not flagged as missing. 85% of the
training window trains on a fake constant for these features.

**With vs. without TXO, (8%, 20d) tail-risk combo, purged 5-fold CV:**

| Window | With TXO | Without TXO | Δ |
|---|---:|---:|---:|
| Full window (2,555 rows) | AUC 0.6560 / Brier 0.1094 | **AUC 0.6732 / Brier 0.1048** | **+0.0172 AUC** |
| Recent window only, real TXO data (359 rows, 3/5 folds usable) | AUC 0.4672 / Brier 0.2551 | AUC 0.4685 / Brier 0.2621 | +0.0013 (both ~random) |

TXO features are a net drag on the full-window result (likely the zero-fill noise), and show no
real predictive power even in the window where the data genuinely exists (both with/without are
near-random, ~0.47 AUC). **The "options-market panic sentiment leads spot" hypothesis is not
supported.**

**Recommendation: drop the 7 TXO features from the tail-risk feature set.** Not yet applied to
`ncf_2330.py` itself — this round only ran the comparison in a separate script
(`scripts/misc/ncf_2330_round4_txo_trend.py`); the features are still present in
`ncf_2330.py`'s general feature set as of this writing. If this recommendation is acted on, the
**new headline honest number for the whole ncf_2330 project becomes AUC 0.673** for the (8%,
20d) tail-risk combo (up from 0.656 in the Round-3 handoff).

## Task 2: Revenue-Trend Diagnostic — More Nuanced Than Expected, Does Not Confirm the Spurious-Proxy Hypothesis

Rounds 2/3 raised a concern: `revenue_ytd_yoy`/`revenue_yoy` dominate feature importance in
multiple tasks, but Round 2's independent out-of-sample test found no significant relationship
between revenue growth and forward 20-day *returns* — raising a suspicion that these features
are really just proxying "how far into this bull run are we" rather than encoding genuine
signal.

This round tested that suspicion directly, on the *tail-risk* task specifically (not the
direction-prediction task Round 2 falsified):

1. **Correlation with a trading-day trend index**: `revenue_ytd_yoy` = 0.577, `revenue_yoy` =
   0.420 — moderate, not the near-1.0 correlation that would indicate a pure trend proxy.
   `revenue_yoy_accel` (-0.012) and `revenue_mom` (0.049) are essentially uncorrelated with
   trend.
2. **Explicit trend-control feature added, model refit**: the new `trend_idx_control` feature
   itself ranks 7th of 161 features (has real explanatory power, as expected in a sustained
   bull market). But `revenue_ytd_yoy` and `revenue_yoy`'s rank and importance **barely moved**
   (rank 1→1, importance 0.0470→0.0456; rank 2→2, importance 0.0384→0.0375). If these features
   were mainly encoding trend, adding an explicit, better trend variable should have caused the
   tree ensemble to shift weight onto it and away from the revenue features. That did not
   happen.

**Conclusion: this diagnostic does not support the "revenue features are purely a spurious
trend proxy" hypothesis for the tail-risk task.** This is an important scope correction: Round
2 falsified revenue growth as a predictor of *forward returns*; this round finds no evidence
that it's spurious as a predictor of *tail risk*. These are different tasks and the earlier
falsification should not be assumed to carry over. The revenue-in-tail-risk-model result should
be treated as still-plausibly-genuine pending further validation, not as debunked.

## Updated Consolidated Status

| Item | Previous (Round 3) | Updated (Round 4) |
|---|---|---|
| Best honest tail-risk AUC | 0.656 (8%/20d, with TXO) | **0.673 (8%/20d, without TXO — pending removal from code)** |
| TXO options features | Present, untested | Tested: net negative, recommend removal |
| Revenue signal in tail-risk model | Assumed suspect (carried over from Round 2's return-prediction falsification) | Diagnostic does not confirm suspicion for this specific task — treat as an open question, not resolved either way |
| Revenue signal in direction (H1/H5/H20) prediction | Falsified (Round 2, out-of-sample, p=0.75-0.90) | Unchanged — still falsified for this task specifically |

## Recommendation

- Apply the TXO removal to `ncf_2330.py`'s tail-risk feature set if this line of work continues
  further — it's a clean, evidence-backed simplification (fewer features, better AUC).
- Do not re-apply Round 2's revenue falsification to the tail-risk task without further
  task-specific validation. If pursued further, a dedicated out-of-sample test analogous to
  Round 2's (but targeting drawdown events instead of forward returns) would be the right next
  step, not just re-citing the direction-prediction result.
- No further rounds are currently queued for `ncf_2330`. This is Round 4 of 4; the project
  should be considered stable at this state pending any future decision to revisit it.

## Files Produced

- `scripts/misc/ncf_2330_round4_txo_trend.py` (new, standalone diagnostic script)
- `results/ncf_2330_round4_20260704.json` (raw results)

## No Production Changes

Consistent with all prior rounds: `group_a_plus/governance/latest.py`,
`group_a_plus/runners/a2118.py`, `group_a_plus/operations/daily_signal.py`,
`group_a_plus/operations/market_state.py`, `group_a_plus_config.json`, and
`report/group_a_plus/latest/*` were not modified. No git commits were created.
