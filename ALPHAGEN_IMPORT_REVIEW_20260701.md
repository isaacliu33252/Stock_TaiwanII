# alphagen-master Import Review / Group A+ Shadow Test

**Date:** 2026-07-01
**Source reviewed:** `C:\Users\isaac\Downloads\alphagen-master\alphagen-master`
**Target system:** Group A+ / A2118 / NCF 00631L

---

## 1. Source Summary

`alphagen-master` is the official implementation of *Generating Synergistic Formulaic
Alpha Collections via Reinforcement Learning* (KDD 2023), plus GP/DSO/LLM-based
baselines. It searches an expression-tree space (WorldQuant-style operators:
`Ref/Delta/Mean/Std/Skew/Kurt/WMA/EMA/Rank/CSRank/Corr/Cov`) using PPO to find
formulaic alphas that maximize IC/RankIC against a target, then combines the found
alphas into a diversified linear pool (`LinearAlphaPool`) using a greedy
add-and-refit procedure with a mutual-IC diversity constraint.

Unlike the two prior external reviews (stock-rnn, Stock-Prediction-Models), this
repo's objective (IC/RankIC on a formulaic feature) matches Group A+'s existing
`factor_lens_gate` methodology directly, rather than a mismatched MSE/price
objective. It was judged worth a scoped shadow test rather than a documentation-only
pass.

Limitations for direct import:

- Designed for **cross-sectional** stock-picking across large stock universes;
  `CSRank`/`Rank` need many instruments to carry signal. Group A+ trades 4 highly
  correlated Taiwan ETFs (0050 + 2x leveraged/inverse derivatives of the same index
  + 1 bond ETF) — cross-sectional ranking is close to meaningless at this scale.
- Full pipeline needs Qlib + baostock data plumbing and a PyTorch/stable-baselines3
  PPO training loop — heavy dependencies not currently in this project's stack.

---

## 2. What Was Imported (v1 Shadow Test)

Implemented:

```text
scripts/evaluate/evaluate_alphagen_lite_shadow.py
tests/test_evaluate_alphagen_lite_shadow.py
```

Latest output:

```text
results/alphagen_lite_shadow_latest_20260701.json
```

Command used:

```bash
PYTHONPATH=. .venv/bin/python scripts/evaluate/evaluate_alphagen_lite_shadow.py \
  --panel results/ncf_00631l_panel_latest_20260630.csv \
  --start 2025-01-02 --end 2026-06-30 \
  --n-splits 4 --gap 5 \
  --output results/alphagen_lite_shadow_latest_20260701.json
```

Imported, deliberately scoped down from the full paper:

- Time-series-only operator algebra: `Delta` (pct-change), `Div(x, Mean(x,d))-1`
  (mean-bias), normalized rolling `Std`, `WMA`/`EMA` bias terms, plus rolling
  `Corr` between `0050.TW` returns and `00631L.TW`/`00632R.TW` returns (pairwise,
  not cross-sectional — meaningful even with only 2 series).
- `LinearAlphaPool`-style greedy selection: candidates ranked by absolute
  single-alpha IC on the train fold, added to a capacity-5 pool subject to a
  mutual-IC diversity check (reject if `|corr| >= 0.7` with any pool member),
  combined via least-squares weights (no RL search — candidate space is small
  enough to score exhaustively).
- Continuous IC/RankIC target (`forward_gain_h20`), not a binarized AUC target —
  this matches AlphaGen's actual objective and Group A+'s existing factor_lens IC
  checks, unlike the binarized AUC framing used in the stock-rnn review.

Explicitly excluded: `CSRank`/`Rank` (cross-sectional, meaningless at N=4),
`Skew`/`Kurt` (kept the candidate count bounded for v1), full RL/PPO search,
Qlib/baostock data layer.

Leaves used: 6 panel columns (`prob_up_h20`, `h20_prob_up`, `confidence`,
`prob_fwd_mdd_gt5_h20`, `prob_fwd_gain_gt5_h20`, `tail_reward_risk_score_h20`) +
4-ticker close/volume from the project's own OHLCV DB. Operator windows: 5/10/20
days. Total candidate count: 228.

---

## 3. Result

TimeSeriesSplit(n_splits=4, gap=5) over 2025-01-02..2026-06-30 (291 aligned rows):

| Metric | Baseline (`prob_up_h20`) | AlphaGen-lite pool |
|---|---:|---:|
| Mean IC | 0.2181 | 0.0008 |
| Mean RankIC | 0.1546 | -0.0131 |
| IC delta vs baseline | 0.0000 | **-0.2173** |

Per-fold detail (this is the important part):

| Fold | Test window | Baseline IC | Pool IC |
|---|---|---:|---:|
| 1 | 2025-05-08..2025-08-20 | 0.047 | 0.497 |
| 2 | 2025-08-21..2025-11-14 | 0.371 | -0.060 |
| 3 | 2025-11-17..2026-02-06 | -0.239 | -0.671 |
| 4 | 2026-02-09..2026-06-01 | 0.693 | 0.237 |

The pool's per-fold IC swings from +0.497 to -0.671 while selecting a
different subset of the 228 candidates almost every fold (only mild overlap
in `most_selected_alphas`). This is the signature of **pure in-sample
overfitting**, not a real edge: with ~150-250 training rows per fold and 228
candidates scored purely by train-fold |IC|, the greedy pool reliably finds
alphas that correlated with the target by chance in that specific train
window, and that correlation does not survive to the held-out fold.

The existing `prob_up_h20` baseline (TabNet ensemble trained with proper
train/test discipline across far more underlying features) is not beaten by
this naive formulaic-mining approach at this sample size.

Decision:

```text
status = research_only
active_allocation_impact = none
promotion_decision = research_only
```

---

## 4. Interpretation

- AlphaGen's methodology is philosophically well-matched to Group A+ (both
  optimize IC-style objectives), unlike stock-rnn/Stock-Prediction-Models which
  optimized the wrong objective outright.
- The failure mode here is sample size, not methodology: 228 candidates against
  ~300 rows is a severe multiple-comparisons problem. The original AlphaGen paper
  operates on thousands of stocks over many years (far larger IC estimation
  sample per candidate).
- The most directly reusable piece — `LinearAlphaPool`'s greedy add + mutual-IC
  diversity constraint — is implemented and tested (`greedy_pool_select` in the
  new script) and could be repointed at a much smaller, pre-vetted candidate set
  (e.g., the existing hand-crafted NCF features) if the goal shifts from
  "mine new alphas" to "prune redundant existing features" — this reuses the
  same mutual-IC logic that the "7 個共識 D 特徵待剪除" pruning task already needs,
  without the doomed wide-candidate mining step.

---

## 5. Current Strategy Impact

No active strategy change was made. Active strategy remains:

```text
a2118_a2111_ncf_late_bull_deleverage
```

Active allocation impact: `none`.

---

## 6. Next Step Candidates

Only proceed if requested:

1. Repoint `greedy_pool_select` at the existing small set of hand-crafted NCF
   features (not the wide 228-candidate mined set) to test it as a principled
   replacement for the manual "7 個共識 D 特徵" pruning step.
2. If more history becomes available (multi-year panel), retry the wide mining
   version — the overfitting problem is a sample-size problem, not a
   methodology problem, and may resolve with a longer panel.
3. Do not pursue the full RL/PPO search or Qlib integration; not justified at
   this universe size (4 tickers).
