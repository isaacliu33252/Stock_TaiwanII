# 2607.24131 (MAPLE) — Diversity-Regularized Multi-Alpha Shadow — Handoff (2026-08-12)

**Status: shadow evaluation complete, clean negative result, no promotion,
confirmed to hold (and get slightly worse, not better) on a 3x larger
universe, on fully-verified data. Work was executed prior to this session
(script/results dated 2026-08-11/12, found untracked/uncommitted); this
document formalizes the record and verdict since none existed yet, then
extends it with a same-session top15-vs-full50 follow-up (§8) prompted by
a user question about whether a larger stock pool would fix the diversity
mechanism's failure, a root-caused bug fix (§9) found along the way, and
the final corrected comparison (§10).**

## 1. Paper

arXiv:2607.24131, "MAPLE: Efficient and Diverse Multi-Alpha Generation for
Portfolio Construction" (SinoPac Holdings + NCCU). Proposes an end-to-end
architecture that predicts `N_alpha` distinct return-ranking signals per
stock from one shared temporal encoder, trains them jointly with:

1. A unified prediction head summing an intra-stock MLP path and an
   inter-stock multi-head-attention path (one head per alpha), directly in
   prediction space (paper Sec 3.1, Eq. 1-5).
2. An extreme-rank-weighted listwise Spearman ranking loss, so gradient
   concentrates on stocks that would actually land in a top-k portfolio
   (Sec 3.2, Eq. 7, Algorithm 1).
3. A diversity regularizer explicitly penalizing pairwise `|correlation|`
   across the `N_alpha` predicted rankings (Sec 3.3, Eq. 8-9), the paper's
   central claim being that this produces genuinely diverse alphas whose
   ensemble beats any single one (their Table 3/4: reported diversification
   gains across 5 backbones, largest with a GRU encoder: +23% SR, +43% CR
   vs single-alpha).

## 2. Why a shadow test, not a full reproduction

This follows directly from the 2026-07-02 StockMixer+ATFNet shadow
(`scripts/evaluate/evaluate_stockmixer_atfnet_shadow.py`,
`project_stockmixer_atfnet_0050_20260702`), whose verdict was "noisy/
inconclusive IC, do not invest more compute without proper walk-forward
validation first." MAPLE was evaluated as an intentionally scoped-down
replication (`MapleLite` in
`scripts/evaluate/evaluate_maple_lite_0050top15_shadow.py`):

- GRU temporal encoder only (the backbone with MAPLE's own largest reported
  gain), not their default 2-layer causal Transformer.
- Fixed (not learnable) extreme-rank sharpness (`ξ=4.0`) / margin
  (`γ=0.3`) parameters, to cut down moving pieces for a first pass.
- The three core, portable ideas (unified head, extreme-rank Spearman loss,
  diversity regularizer) are implemented faithfully — this is a scope cut
  on architecture size/tuning, not a simplification of the mechanism being
  tested.

## 3. Setup

- Universe: 0050 top-15 by weight, reusing the cached parquet from the
  StockMixer+ATFNet shadow (`results/stockmixer_atfnet_0050top15_ohlcv_cache.parquet`,
  2019-01-02..2026-07-01).
- Features: 9 per stock/day (1/5/10/20d returns, 5/20/60d MA gap, 20d
  vol, 20d volume z-score), 16-day lookback window fed to the GRU.
- Label: 5-day forward return; execution/eval uses next-day return with a
  rolling top-5 basket.
- Validation: `group_a_plus.validation.purged_walk_forward.PurgedWalkForwardSplit`,
  5 folds, 5-day purge (matches the label horizon, no leakage).
- Transaction cost: 0.50% per name replaced in the top-5 basket per day
  (~0.1425% commission/side + 0.3% TW sell tax), applied to the net-Sharpe
  column only.
- Compared configs: `N_alpha=1` (single-alpha baseline, diversity loss term
  off) vs `N_alpha=8` (MAPLE's diversity-regularized ensemble,
  `diversity_lambda=0.1`), each run across 3 seeds (0, 1000, 2000) for a
  fair mean±std comparison.
- **Reproducibility fix already applied before this write-up (in-code
  comment dated 2026-08-11)**: `torch.manual_seed` alone did not control
  `np.random.shuffle` used for epoch-level day shuffling — fixed by giving
  each fold its own `np.random.default_rng(seed)` instead of touching
  global numpy state. Also fixed: the very first version of this script
  ran `N_alpha=1` with only 1 seed while `N_alpha=8` got 3, an unfair
  comparison — the version evaluated here runs both configs across the
  same 3 seeds.

## 4. Results (top15)

`results/maple_lite_0050top15_shadow.json`, `report/group_a_plus/latest/maple_lite_0050top15_shadow.md`.

| config | mean rank IC | ensemble Sharpe (gross) | ensemble Sharpe (net) | mean turnover | diversification gain | mean alpha correlation |
|---|---|---|---|---|---|---|
| N_alpha=1 (3-seed mean±std) | 0.0353±0.0051 | 1.912±0.054 | 0.910±0.015 | 0.24±0.01 | n/a | n/a |
| N_alpha=8 (3-seed mean±std) | 0.0115±0.0095 | 1.747±0.101 | 0.647±0.118 | 0.26±0.01 | 0.046±0.055 | 0.821±0.020 |

Independent-samples t-test (`N_alpha=8` vs `N_alpha=1`, 3 seeds each,
`scipy.stats.ttest_ind`): IC diff p=0.035, net-Sharpe diff p=0.035 — both
significant at 5%, but in the **opposite** direction from MAPLE's claim.

Context only (not a fair comparison — different model/eval protocol, same
universe): 2026-07-02 StockMixer+ATFNet shadow got IC=0.0143, a plain
single-stock logistic baseline got IC=0.0244.

## 5. Interpretation (top15)

**The paper's central mechanism does not replicate on this universe.**
`N_alpha=8` with diversity regularization underperforms the single-alpha
baseline on every metric that matters (IC roughly a third of baseline,
gross Sharpe lower, net Sharpe roughly 30% lower after the same
transaction-cost model, higher variance across seeds on top of that), and
the "diversification gain" (ensemble Sharpe minus mean individual-alpha
Sharpe) is a small positive 0.046 — i.e. averaging the 8 alphas together
recovers only a small fraction of what a single well-trained alpha already
gets alone, not the reported +23-43% relative uplift.

**The diversity regularizer appears to fail at its own stated job.** Mean
pairwise `|correlation|` across the 8 predicted rankings is 0.821 — the
alphas are *not* diverse, they've converged to near-duplicates of each
other despite the explicit correlation penalty (`diversity_lambda=0.1`) in
the training loss. Two plausible readings, not distinguished at this
point:
  (a) `diversity_lambda=0.1` is too weak relative to the ranking-loss terms
      it's competing against at this scale/universe (15 stocks is a much
      smaller cross-section than MAPLE's paper universe, giving the
      attention-based inter-stock path much less room to specialize per
      head), or
  (b) with only 15 stocks and a shared GRU encoder producing all 8 heads'
      inputs, there simply isn't enough independent signal in the
      cross-section to support 8 genuinely different, individually-useful
      rankings — forcing diversity via the penalty term degrades the
      individually-useful signal instead of adding new orthogonal signal.

Both readings point the same direction for this project: this isn't a
tuning bug to fix, it's evidence the mechanism's benefit (if real on
MAPLE's own larger US/CN universes) doesn't transfer to Group A+'s
0050-top15-scale problem. **§8-10 test reading (b) directly and refute
it** — reading (a) (regularizer weight too weak) remains untested and,
per §6, deliberately not pursued via parameter search.

## 6. What was and wasn't done (top15 phase)

- Implemented: unified intra/inter-stock prediction head, extreme-rank
  Spearman ranking loss, diversity regularizer — all three core MAPLE
  ideas, GRU backbone only.
- Not implemented: the other 4 backbones MAPLE validates against (their
  default is a 2-layer causal Transformer), learnable extreme-rank
  sharpness/margin parameters, any hyperparameter sweep over
  `diversity_lambda` or `N_alpha` other than the single 1-vs-8 comparison.
- **Not investigated further**: whether a smaller `N_alpha` (e.g. 2-3) or
  a larger `diversity_lambda` recovers a positive result — deliberately
  not pursued, per this project's standing caution against multi-round
  parameter tuning on a fixed backtest window turning into overfitting
  (`feedback_overfitting_fixed_window_tuning`). If this line is revisited,
  it should be with a reason to believe the mechanism is sound (e.g. a
  literature or first-principles argument for why 15 names should support
  8 alphas) rather than a parameter search for a config that happens to
  win on this window.
- No production code touched. No shadow line opened in the daily pipeline
  — this is a one-off research script + static report, same treatment as
  every other closed-paper shadow this project has run.
- No pytest coverage written for `evaluate_maple_lite_0050top15_shadow.py`
  — consistent with this project's convention for one-time research
  diagnostic scripts (see e.g. `GROUP_A_PLUS_20260811_ALPHAZEROBETA...`
  §14, "兩支新診斷腳本沒有pytest測試").
- Not committed — user has not asked for a commit for this batch of work.

## 7. Verdict (top15, pre-existing before this session started)

**Clean negative shadow result. Not promoted, no further tuning planned.**
Same category of outcome as the 2026-07-02 StockMixer+ATFNet shadow this
followed up on — a plausible-sounding cross-sectional deep-learning
mechanism from a paper validated on a large stock universe does not carry
its benefit down to Group A+'s much smaller (15-name) universe. Unlike
that predecessor shadow (verdict: "noisy/inconclusive, don't invest more
compute"), this one is a **clean, statistically significant negative**,
not an inconclusive one — the sign of the effect is backwards, not just
noisy.

---

**Everything below this line happened in this session** (2026-08-12),
prompted by the user asking whether the 2026-07-02 predecessor's full50
result (where a bigger pool *helped* a different model) meant the same
fix would apply here.

## 8. Follow-up: does a larger universe (top50) fix it?

**Bug found and fixed before rerunning**: `load_panel()` read raw `Close`
unconditionally. The top15 cache has no `Adj Close` column at all (so this
was a no-op for the §4 top15 run — confirmed by inspection, not rerun),
but the full50 cache
(`results/stockmixer_atfnet_full50_202606_ohlcv_cache.parquet`) does. Raw
Close on dividend-paying names (2317/2454/2881/2882/2891 all appear in
this pool) produces fake ex-dividend-day return crashes — the exact bug
already found and fixed in the StockMixer+ATFNet predecessor
(`project_stockmixer_atfnet_0050_20260702` bug #2) but not carried over
into MAPLE-lite. Fixed: `load_panel()` now prefers `Adj Close` when the
cache has it.

**First full50 run hit a data-integrity trap, caught before drawing
conclusions**: in every one of the 6 runs (3 seeds x 2 configs), fold 5
(test window 2025-02-17..2026-07-02, the most recent/last fold) produced
`mean_ic = None`, and all 6 runs' fold-5 `ensemble_daily_returns` produced
the exact same Sharpe value (2.205) regardless of `N_alpha` or seed —
too suspicious to be coincidence, root-caused in §9. A first-pass clean
comparison excluding fold 5 entirely (`results/maple_lite_full50_shadow.json`,
folds 0-3 only) gave:

| universe | config | mean rank IC | Sharpe (net) | mean alpha correlation | diversification gain |
|---|---|---|---|---|---|
| top15 | N_alpha=1 | 0.0353±0.0051 | 0.910±0.015 | n/a | n/a |
| top15 | N_alpha=8 | 0.0115±0.0095 | 0.647±0.118 | 0.821±0.020 | +0.046±0.055 |
| full50 (fold 5 excluded) | N_alpha=1 | 0.0104±0.0028 | 0.174±0.075 | n/a | n/a |
| full50 (fold 5 excluded) | N_alpha=8 | 0.0094±0.0062 | 0.073±0.047 | 0.830±0.031 | −0.090±0.014 |

This fold-5-excluded estimate already pointed the same direction as the
final answer (§10) — alpha correlation essentially unchanged,
diversification gain flips negative — but §9's fix and full rerun
replaced it with a materially better (and fully trustworthy) full50
result, because fold 5 turned out to be the *strongest* fold once fixed.
**Do not cite this table's full50 numbers — see §10 for the authoritative
version.** Kept here only as the methodology record of what was checked
before the root cause was found.

## 9. Root cause of the fold-5 corruption (diagnosed and fixed)

User pushed for the actual mechanism rather than leaving it as an
unexplained "training instability, out of scope." Root-caused via two
standalone repro scripts (an isolated fold-5 retrain with per-step
loss/grad-norm logging, then a step-by-step forward/backward isolation)
before touching the shared script:

1. **A single ticker, a real data gap.** `7769.TW`'s Adj Close is NaN for
   a stretch starting 2025-01-03 in the full50 cache. Every one of its 9
   engineered features (`ret_1d/5d/10d/20d`, `ma_gap_5/20/60`, `vol_20d`,
   `volume_z_20d`) inherits NaN downstream for any lookback window
   touching that gap — confirmed directly: the 16-day window ending
   2025-02-04 (the exact date that triggered the very first NaN, at
   training step 12 of epoch 0) has 135 NaN feature values, all on
   `7769.TW`, zero elsewhere.
2. **The validity filter was label-only.** `train_fold`'s (and
   `evaluate_fold`'s) `valid = ~np.isnan(y)` checked only the
   forward-return *label* for NaN, never the input *feature window*. A
   stock with a defined label but a NaN-contaminated lookback window still
   got fed into the GRU.
3. **MapleLite's inter-stock attention path spreads one stock's NaN to
   all of them.** The `inter` branch computes pairwise dot-product
   attention scores across every included stock in the cross-section
   (`einsum("snd,tnd->nst", q, k)` in `MapleLite.forward`). One NaN
   embedding poisons the softmax-normalized attention weights for *every*
   stock that day, not just `7769.TW` — confirmed directly: at the
   triggering step, `y_hat` for all 50 tickers was simultaneously NaN
   (verified via direct tensor inspection), while the *label* data (`y_t`)
   for that same day was completely unremarkable (range −0.02 to +0.24,
   no NaN, no outlier) — ruling out a bad label as the cause.
4. **No recovery mechanism.** Once `loss.backward()` produces NaN
   gradients and `opt.step()` applies them, every model parameter becomes
   NaN permanently — there's no gradient clipping (unlike, coincidentally,
   the same-day-reviewed `2607.23068` compact-GMV paper, which does clip)
   and no NaN-skip guard on the optimizer step. Every subsequent forward
   pass for the rest of that run's training and evaluation is NaN,
   explaining the full-fold wipeout (330/330 evaluable test days, all
   NaN IC) rather than an occasional bad day.
5. **Why fold 5 only, and why all 6 runs failed identically.** `7769.TW`'s
   gap date range (2025-01 onward) only exists within fold 5's training
   window (train up to 2025-02-07). Fold 3 trains only to 2023-09-14,
   fold 2 to 2022-05-04, and so on — none of folds 0-3 ever reach this
   date range, so they were never at risk. Within fold 5, the corrupting
   date is highly likely to be sampled at some point in any 30-epoch run
   regardless of shuffle seed (1401 training days per epoch, 30 epochs),
   which is why all 3 seeds x 2 configs failed identically — not a
   coincidence, a near-certainty given the setup.

**Fix applied**: both `train_fold` and `evaluate_fold` in
`scripts/evaluate/evaluate_maple_lite_0050top15_shadow.py` now compute
`window_valid = ~np.isnan(window).any(axis=(0, 2))` and require
`valid = ~np.isnan(y) & window_valid` — a stock is only included on a
given day if *both* its label and its full lookback feature window are
NaN-free. This is a general-purpose correctness fix (any future reuse of
this script benefits, not specific to this one paper or ticker).

**Re-verification**: fold 5 was retrained/re-evaluated for all 6 runs
with the fix (folds 0-3 carried over unchanged from
`results/maple_lite_full50_shadow.json`, which were never affected by
this bug — verified no NaN in their `ensemble_daily_returns`). Full
results: `results/maple_lite_full50_shadow_fold5fixed.json` /
`report/group_a_plus/latest/maple_lite_full50_shadow_fold5fixed.md`.
Fold 5 itself, now genuinely trained, turned out to be the *strongest*
fold for both configs (IC 0.075-0.10 for N_alpha=1 across the 3 seeds,
vs ~0.01-0.04 typical of folds 0-3) — consistent with 2025-2026 being a
trending/IC-friendly regime — so the corrected full50 aggregate (§10) is
meaningfully better than §8's fold-5-excluded estimate, though the
qualitative verdict is unchanged.

## 10. Final authoritative top15-vs-full50 comparison (all folds genuine)

Supersedes §8's fold-5-excluded numbers (kept there only as the
methodology record of what was checked before §9's root cause was found —
do not cite conclusions from §8's full50 row).

| universe | config | mean rank IC | Sharpe (net) | mean alpha correlation | diversification gain |
|---|---|---|---|---|---|
| top15 | N_alpha=1 | 0.0353±0.0051 | 0.910±0.015 | n/a | n/a |
| top15 | N_alpha=8 | 0.0115±0.0095 | 0.647±0.118 | 0.821±0.020 | +0.046±0.055 |
| full50 | N_alpha=1 | 0.0248±0.0020 | 0.647±0.085 | n/a | n/a |
| full50 | N_alpha=8 | 0.0139±0.0052 | 0.540±0.019 | **0.870±0.024** | **−0.015±0.018** |

t-test (`N_alpha=8` vs `N_alpha=1`, full50, all folds genuine): IC diff
p=0.052, net-Sharpe diff p=0.159 (both weaker significance than top15's
p=0.035, consistent with a noisier/harder cross-section, not with the
effect reversing).

**Final verdict, on fully-verified data: expanding to 50 stocks does not
fix the diversity mechanism — mean alpha correlation is *higher* on
full50 than top15 (0.870 vs 0.821), not lower**, and diversification gain
is still negative (though less severely than §8's fold-5-excluded
estimate suggested: −0.015 vs −0.090). Every reading from §5 holds with
the corrected data:

1. More stocks gave the 8 attention heads *no* additional room to
   specialize — if anything, alpha correlation went slightly the wrong
   way. This directly refutes reading (b) from §5 — insufficient
   cross-section was not the limiting factor. Reading (a) (regularizer
   weight too weak) remains untested and, per §6, deliberately not
   pursued via parameter search.
2. Diversification gain stays negative on the larger universe.
3. The single-alpha baseline is still weaker on full50 than top15
   (IC 0.0248 vs 0.0353), though less dramatically than §8's
   fold-5-excluded estimate implied (0.0104) — some of that earlier gap
   was itself an artifact of discarding fold 5's (genuinely strong) data
   entirely, not a real universe-size effect. Not a fair apples-to-apples
   comparison against the StockMixer+ATFNet predecessor's own full50
   result either way (different model, different baseline, and that
   predecessor's full50 finding was itself flagged as "single split,
   single seed, noisy, not evidence bigger-is-better" —
   `project_stockmixer_atfnet_0050_20260702`).
4. No further scale points (e.g. top75, full universe) planned — the
   consistent-and-slightly-worse-not-better result across a 3x universe
   change, now on verified data, is sufficient to close this question
   without spending more compute chasing it.

This closes the investigation the user's original question opened: the
scale hypothesis is refuted on verified, uncorrupted data, not on a
workaround estimate.

## 11. Final verification pass (before writing this record)

Run directly against `results/maple_lite_full50_shadow_fold5fixed.json`
before treating §10 as final:

- All 6/6 fold-5 `mean_ic` values are non-`None` (range 0.030-0.100,
  in line with other folds).
- Zero folds, across all 6 runs and all 5 folds each, contain any NaN in
  `ensemble_daily_returns`.
- The fix (`window_valid = ~np.isnan(window).any(axis=(0, 2))`) is
  present in both `train_fold` and `evaluate_fold` in the live script
  file (grep-confirmed, not just asserted from memory of having written
  it).

## 12. Files

| File | Nature |
|---|---|
| `scripts/evaluate/evaluate_maple_lite_0050top15_shadow.py` | Pre-existing (§2-7); modified this session (§8: Adj Close fix; §9: NaN feature-window validity fix) |
| `results/maple_lite_0050top15_shadow.json` | Pre-existing, full per-fold/per-seed results (top15) |
| `report/group_a_plus/latest/maple_lite_0050top15_shadow.md` | Pre-existing, summary table + significance test (top15) |
| `results/maple_lite_full50_shadow.json` | New (§8); folds 0-3 authoritative, fold 5 corrupted (§9) — superseded by the fold5fixed file for any conclusion |
| `report/group_a_plus/latest/maple_lite_full50_shadow.md` | New (§8); raw script aggregate, fold-5-contaminated — do not cite, see §10 |
| `results/maple_lite_full50_shadow_fold5fixed.json` | New (§9-10), authoritative full50 result, all 5 folds genuinely trained |
| `report/group_a_plus/latest/maple_lite_full50_shadow_fold5fixed.md` | New (§9-10), authoritative full50 summary table — **cite this one** |
| This file | New, handoff record |

## 13. Paper re-read directly (2026-08-12, after §1-12)

§1's paper summary was written from the shadow script's docstring, not a
direct reading. Read the full 14-page paper + appendix directly to close
that gap before finalizing this record. Two corrections/additions:

1. **The paper's own evidence for the diversity loss is not weak.**
   Table 4's ablation (at `N_alpha=8`, on the paper's actual 200-500+
   stock markets) shows `spr+ext+div` improving return-to-volatility
   ratio over `spr+ext` alone (0.104 → 0.112) — a real, if modest (~8%),
   positive contribution in the paper's own tested regime. This is
   *unlike* some other papers reviewed this week (e.g. `2606.29347`)
   where the authors' own statistics already refute the headline claim.
   §5's shadow finding should be read as "this mechanism doesn't
   transfer to a 5-50-stock Taiwan universe," not "the paper's evidence
   was already shaky" — those are different and this record previously
   didn't distinguish them clearly.
2. **Implementation gap found on re-read: alpha aggregation method
   differs from the paper.** Paper §3.3 / Algorithm 2: each alpha
   independently selects and softmax-weights its own top-k basket, and
   the *realized sub-portfolio returns* are averaged across alphas
   (portfolio-level aggregation) — explicitly motivated as "consistent
   with classical alpha mining practice... diversification benefit
   arises from signal diversity rather than explicit score fusion."
   `MapleLite`'s `evaluate_fold` instead averages the `N_alpha` raw
   *scores* first, then selects one top-k basket from that averaged
   score (score-level aggregation, `ensemble_score = y_hat.mean(axis=1)`).
   When alphas are highly correlated (0.82-0.87 as measured), score-level
   averaging is close to a no-op relative to any single alpha, which may
   understate whatever diversification benefit portfolio-level
   aggregation would have captured even from imperfectly-decorrelated
   alphas. **This does not overturn §10's verdict** — see point 3 — but
   is a genuine gap between `evaluate_maple_lite_0050top15_shadow.py`
   and the paper, not previously documented, and would need fixing
   before citing this shadow as a faithful test of the paper's full
   aggregation scheme specifically (as opposed to its diversity-loss
   training mechanism, which score-vs-portfolio aggregation doesn't
   affect — the alpha correlation numbers in §10 are unaffected by this
   gap since correlation is measured on the raw scores, not the
   aggregation method).
3. **More fundamental reason for non-adoption, independent of whether
   the diversity mechanism works: MAPLE assumes a large cross-sectional
   stock universe to rank and select top-k from.** Group A+'s actual
   tradable set is 5 symbols
   (`config/group_a_plus_watchlist.json`: 0050/00631L/00632R/00679B/2330)
   allocated via discrete regime-switching rules, not stock-picked from
   a universe of hundreds. This mismatch predates and is more decisive
   than the diversity-mechanism question §5-10 investigated — it would
   apply even if score-vs-portfolio aggregation were fixed and even if
   the diversity mechanism worked perfectly. Same category of
   architecture/universe mismatch as `2607_23068`
   (compact GMV neural network, reviewed the same week) and
   `2310_02084`/`2301_03186` (LETF papers assuming a decision variable
   this project doesn't have).

No code changes from this re-read — confirms and sharpens the existing
non-adoption verdict rather than changing it.

## 14. Memory index

`project_2607_24131_maple_diversity_alpha_shadow_closed_20260812.md`.
Related: `project_stockmixer_atfnet_0050_20260702` (predecessor shadow,
same universe/cache, source of the Adj Close bug pattern),
`feedback_overfitting_fixed_window_tuning` (why no diversity_lambda/N_alpha
sweep was attempted).
