# NCF_2330 — Rounds 2 & 3 Handoff (Chip Features, Revenue Falsification, Tail-Risk Deepening) - 2026-07-04

## Executive Summary

Follow-up to `NCF_2330_TSMC_STOCK_MODEL_HANDOFF_20260703.md` (baseline `ncf_2330.py` build).
Two further improvement rounds were run same-day/overnight (2026-07-03 evening → 2026-07-04
early morning). Net result: **direction prediction (H1/H5/H20) did not improve enough to
consider integration**; the most useful outcome is a corrected, honest tail-risk (drawdown)
AUC and two falsified/downgraded assumptions from the baseline report.

**Still standalone / shadow-only. Nothing in this work touches `a2118`, `daily_signal.py`,
`group_a_plus_config.json`, or `market_state.py`.**

## Round 2: Chip/Institutional Features, Revenue Signal Falsification, Real Earnings Dates

### What was done

1. Added per-stock chip/institutional features via FinMind (previously the local DB had zero
   per-stock chip data for 2330.TW — see baseline handoff):
   - `TaiwanStockInstitutionalInvestorsBuySell` (foreign/investment-trust/dealer net buy-sell,
     2012-05 ~ present) → cached at `results/finmind_2330_institutional_buysell_cache.csv`
   - `TaiwanStockMarginPurchaseShortSale` (margin/short balances, 2010-01 ~ present) → cached at
     `results/finmind_2330_margin_short_cache.csv`
   - `TaiwanStockShareholding` (foreign shareholding ratio, 2010-01 ~ present) → cached at
     `results/finmind_2330_shareholding_cache.csv`
   - T-1 point-in-time alignment (same convention as `ncf_00631l.py`), verified 840/841 trading
     days had non-null `inst_foreign_net`.
2. **Independently validated the monthly-revenue signal — result: falsified.** The baseline
   report found `revenue_ytd_yoy` as the #1 feature (of 141) for H20. A dedicated
   trailing-median-split + t-test analysis on 177 historical revenue-release events, with an
   out-of-sample holdout (last 54 events, 2021-12 ~ 2026-05), found **no significant relationship**
   to forward 20-day returns (p = 0.75–0.90). Extreme-quartile comparison was also
   non-significant and pointed the wrong way (top quartile forward return +1.27% < bottom
   quartile +2.30%, p = 0.45). Working hypothesis: tree ensembles may be using the slow-moving
   cumulative revenue-growth series as a proxy for "how far into this bull run are we" rather
   than a genuine forward-looking signal.
3. Replaced the coarse `earnings_window_flag` (quarter-end + N-day calendar proxy, previously
   ranked 129-131/141 — useless) with real TSMC investor-conference dates sourced from SEC EDGAR
   6-K filings for the TSM ADR (40/46 quarters directly confirmed, 2 quarters estimated from
   same-quarter pattern and flagged as such).
4. **Bug found and fixed**: ensemble probability summation in `train_classifier` (inherited from
   the `ncf_00631l.py`/`ncf_00632r.py` templates) occasionally produced values marginally above
   1.0 (e.g. 1.0000000045) due to floating-point error, which made `brier_score_loss`'s strict
   validation raise. This wasn't hit by the baseline run but was hit once chip features shifted
   the ensemble weighting. Fixed with `np.clip(..., 0.0, 1.0)` at both probability-summation
   sites in `train_classifier`.

### Round 2 results: baseline vs improved (purged 5-fold CV)

| Horizon | Baseline AUC | Round-2 AUC | Δ |
|---|---:|---:|---:|
| H1 | 0.5408 | 0.5449 | +0.0041 |
| H5 | 0.5242 | 0.5375 | **+0.0133** |
| H20 | 0.5612 | 0.5502 | **-0.0110** |

Feature-stability grades unchanged (H1=C, H5=C, H20=A). Walk-forward average accuracy flat
(within ±0.002) across all horizons.

Mixed/marginal: chip features gave a real H5 gain but a real H20 regression (likely added
overfitting risk on the long horizon). H1 stayed near-noise regardless.

Auxiliary models (H20, 5% threshold, single-split methodology at the time):
`forward_drawdown_risk` AUC 0.626 → 0.698, `forward_upside_reward` AUC 0.603 → 0.614.
**Important: these Round-2 numbers used the single-split methodology, not purged-CV — see the
Round-3 correction below.**

Output: `results/ncf_2330_improved_20260703.json`,
`results/ncf_2330_improved_panel_latest_20260703.csv`.

## Round 3: Tail-Risk Deepening + Correction of the Round-2 Drawdown Number

### What was done

Built `scripts/misc/ncf_2330_tail_risk_sweep.py` (new file) to properly investigate the one
clearly promising thread from Round 2 — tail-risk / drawdown prediction — with rigorous
per-combo purged-CV, rather than relying on the single main-ensemble run.

1. Added 6 new tail-risk-specific features to `ncf_2330.py`: `inst_foreign_accel`,
   `inst_foreign_sell_streak`, `margin_balance_5d_chg`, `vol5_vol20_spike`,
   `soxx_down_x_vix_spike`, `foreign_streak_x_vol20`, plus two continuous earnings-distance
   features (`trading_days_since_earnings`, `trading_days_until_earnings`).
2. Swept (threshold, horizon) combinations: (3%,10d), (5%,20d — the Round-2 baseline combo),
   (8%,20d), (5%,40d). Each combo got its own 5-fold purged-CV.
3. Validated the continuous earnings-distance features against the old binary flag.
4. Tried pruning the bottom-30%-importance features for H20 to see if it recovers the Round-2
   regression.
5. **Bug found and fixed** (independent of the Round-2 ensemble-probability bug): the new sweep
   script's own code did `mask = y_dir != -1` producing an index-carrying boolean pandas Series,
   then passed it to `.iloc[mask]`, which pandas rejects (`ValueError: iLocation based boolean
   indexing cannot use an indexable as a mask`). Fixed by converting to `.to_numpy()` and using
   `.iloc[]` consistently with positional masks. Confirmed reproducible/fixed by rerunning (first
   combo's AUC matched exactly across the crashed and rerun executions).

### Correction: the Round-2 drawdown-risk number was optimistic (single-split, not purged-CV)

| Combo | single-split AUC | **purged-CV AUC (honest)** | Brier (purged-CV) |
|---|---:|---:|---:|
| 3% / 10d | 0.6047 | 0.5808 | 0.2207 |
| 5% / 20d (Round-2's combo) | 0.7197 | **0.5850** | 0.2184 |
| **8% / 20d (best)** | 0.8642 | **0.6560** | 0.1094 |
| 5% / 40d | 0.6353 | 0.5643 | 0.2725 |

All four combos show a large single-split-vs-purged-CV gap (0.10-0.21 AUC points). The Round-2
report's "drawdown-risk AUC 0.626 → 0.698" used the single-split figure, not purged-CV — this
number should not be trusted as-is. Re-run on the same (5%, 20d) combo with purged-CV gives
0.5850. **The best honestly-validated result across this whole 2330 project is the (8%, 20d)
tail-risk combo at purged-CV AUC = 0.656**, still the strongest number produced across all three
rounds, but meaningfully lower than what Round 2 implied.

### Other Round-3 findings

- New chip-outflow features are mostly weak: `inst_foreign_sell_streak` ranks 154/160 (near
  useless), best of the batch is `vol5_vol20_spike` at 62/160. The "chip outflow acceleration
  predicts crashes" hypothesis is not strongly supported.
- **`revenue_ytd_yoy` / `revenue_yoy` are still the #1 and #2 features (of 160) for the best
  tail-risk combo**, despite being independently falsified as a forward-return predictor in
  Round 2. This reinforces the Round-2 concern that these features are acting as a bull-market
  time-progress proxy rather than genuine signal — the same suspicious pattern shows up in a
  second, differently-labeled task.
- Continuous earnings-distance features clearly beat the binary flag:
  `trading_days_since_earnings` rank 30/160, `trading_days_until_earnings` rank 26/160, vs old
  `earnings_window_flag` rank 160/160 (dead last). Confirms the earlier flag's weakness was a
  feature-design problem, not a date-precision problem.
- H20 LOW-stability pruning (removed 48 of 160 features) made results **worse**, not better:
  purged-CV AUC 0.5562 → 0.5473 (-0.0089). Not adopted.

Output: `results/ncf_2330_tail_risk_sweep_20260704.json`.

## Consolidated Status After 3 Rounds

| Model | Best honest (purged-CV) metric | Verdict |
|---|---|---|
| H1 direction | AUC ~0.54 | Near noise across all 3 rounds. Likely a real ceiling for 1-day-ahead prediction on a large, relatively low-idiosyncratic-vol stock. |
| H5 direction | AUC ~0.54 | Weak, small real gain from chip features (+0.013), still not tradeable-grade. |
| H20 direction | AUC ~0.55 | Chip features hurt this horizon; pruning also hurt. No further easy win found. |
| H20 tail-risk (8%/20d) | AUC 0.656, Brier 0.109 | **Best result in the project.** Still not strong enough to gate real decisions, but the only thread worth continuing. |
| Revenue signal | Falsified (Round 2), reinforced-suspicious (Round 3) | Downgrade confidence in any future claim that revenue growth predicts 2330 forward returns. |
| Continuous earnings-distance features | Confirmed better than binary flag | Keep this change; low-risk, clean win. |

## Recommendation

- Do not integrate `ncf_2330.py` (any horizon, any sub-model) into `a2118` or any production
  decision path.
- Keep the tail-risk (drawdown) sub-model as an independent, periodically-rerun shadow concept —
  it is the one genuinely promising thread, but 0.656 AUC is a research-stage result, not a
  production-grade risk gate.
- If this line of work continues, prioritize investigating *why* the revenue features dominate
  importance despite failing independent validation (possible leakage-adjacent time-trend
  confound) before trusting them in any other context, including other tickers' NCF models that
  might reuse similar revenue features.
- No further rounds are queued. This closes out the ncf_2330 exploration for now pending a
  decision to pursue the tail-risk angle specifically.

## Files Produced (Rounds 2 & 3, cumulative with baseline)

- `ncf_2330.py` (modified in place across both rounds; not rebuilt from scratch)
- `scripts/misc/ncf_2330_tail_risk_sweep.py` (new)
- `results/ncf_2330_improved_20260703.json`, `results/ncf_2330_improved_panel_latest_20260703.csv`
- `results/ncf_2330_tail_risk_sweep_20260704.json`
- `results/finmind_2330_institutional_buysell_cache.csv`,
  `results/finmind_2330_margin_short_cache.csv`, `results/finmind_2330_shareholding_cache.csv`

## No Production Changes

`group_a_plus/governance/latest.py`, `group_a_plus/runners/a2118.py`,
`group_a_plus/operations/daily_signal.py`, `group_a_plus/operations/market_state.py`,
`group_a_plus_config.json`, and `report/group_a_plus/latest/*` were not modified across any of
the three rounds. No git commits were created.
