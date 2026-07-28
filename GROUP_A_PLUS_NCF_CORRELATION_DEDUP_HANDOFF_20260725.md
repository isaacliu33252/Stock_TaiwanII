# NCF Feature-Selection Correlation De-Duplication -- 2026-07-25

## Origin

User pushed back on `docs/2607_06117_RGRR_QQQ_DIA_GROUPA_PLUS_REVIEW_20260725.md`'s
"no direct import" framing with three specific mechanisms from
arXiv:2607.06117v1 that might transfer even though the paper's own
strategy doesn't. This document covers the third: RGRR's screening step
de-duplicates candidate signals whose pairwise correlation exceeds 0.95
before admission, to avoid interaction terms built from near-duplicate
signals looking spuriously informative. User asked whether Group A+'s
own feature pipeline has an equivalent layer.

**Confirmed via grep, 2026-07-25**: it does not. `_feature_selection`/
`apply_feature_selection` in `scripts/misc/ncf_00631l.py` filter
candidates by RandomForest-importance median threshold only.
`identify_stable_features` filters by top-K-across-TimeSeriesSplit-folds
membership only. Neither considers pairwise redundancy among the
survivors -- two near-duplicate technical indicators can both clear
either bar and both get kept, silently double-weighting the same
underlying information.

(Separately clarified for the user: Group A+'s actual production model is
NCF, gradient-boosted-tree ensembles trained on engineered technical/chip/
external features -- not FinRL/RL. FinRL is a distinct research directory;
Group A, not Group A+, has the project's only real RL model.)

## Where this actually matters in production

`_feature_selection`/`apply_feature_selection` are gated behind
`do_feature_selection`, which defaults `False` and is **not** enabled by
`scripts/run/run_ncf_daily_pipeline.py`'s actual invocation of
`ncf_00631l.py` (confirmed by reading the pipeline's command-line args) --
so a fix there would not touch the live daily panel at all.

`identify_stable_features`, by contrast, **runs unconditionally for the
H=20 horizon** (`scripts/misc/ncf_00631l.py` around line 2545, no flag
gating) and its output feeds an extra `stable_rf` sub-model into the
AUC-weighted ensemble. This is the layer that actually matters for
today's production panel, so it's where the fix was made.

## What was implemented

Two new pieces in `scripts/misc/ncf_00631l.py`:

1. **`_deduplicate_correlated_features(X, features, corr_threshold=0.95,
   priority=None)`** -- a standalone, independently testable helper.
   Walks `features` in `priority` order (or `features`' own order if no
   priority given) and greedily drops any feature whose absolute pairwise
   correlation with an already-kept, higher-priority feature exceeds
   `corr_threshold`. Returns survivors in `features`' original relative
   order (not priority order), so callers depending on that ordering
   elsewhere are unaffected.

2. **`identify_stable_features(..., dedupe_correlated: bool = False,
   corr_threshold: float = 0.95)`** -- new optional parameters, **default
   `False`/`0.95`, off by default, exactly preserving existing behavior**
   (matches this project's established pattern for every prior opt-in
   pipeline change, e.g. `expanding_model_weights`). When enabled, orders
   the already-stability-selected features by their mean RF importance
   across the same folds already being computed (no extra model fits),
   then applies the de-dup helper with that priority so the *more
   important* of two highly-correlated survivors is the one kept.

## Empirical check on real data (not synthetic)

Loaded real 00631L OHLCV (`load_data`, 2020-01-01 through latest,
1591 rows) and built the real H=20 feature matrix via `build_dataset`
(`ext_df=None` to skip external-data fetches and keep this a fast, local-
only check -- the technical/interaction feature set alone, `FEATURES +
INTERACTION_FEATURES`, 56 columns, is where correlation redundancy is
most likely to concentrate anyway). Ran `identify_stable_features` with
and without `dedupe_correlated`:

- **Without dedup**: 15 stable features, including both
  `close_ma200_ratio` and `close_ma200_dist`.
- **With dedup** (`corr_threshold=0.95`): 13 features -- drops
  `close_ma200_ratio` and `close_ma200_dist`.
- **Why**: `close_ma200_ratio` vs `close_ma200_dist` correlation = **1.000**
  (essentially the same underlying quantity through two transformations).
  `close_ma200_ratio` also correlates 0.953 with `close_ma120_ratio`
  (the higher-importance, kept survivor). This is exactly the redundancy
  class the paper's own de-duplication step targets, found on this
  project's real feature set, not a synthetic example.

Raw check not saved to a result file (ad hoc `python3 -c`, reproducible
from this document's own commands -- `load_data` + `build_dataset(...,
horizon=20, ext_df=None, direction_threshold=0.005, labeling='simple')`
+ `identify_stable_features(..., dedupe_correlated=True)`).

## What was NOT done

**Full ensemble AUC impact not measured.** Confirming the de-dup pair is
genuinely redundant (correlation up to 1.000) is strong circumstantial
evidence it's a safe removal, but the actual effect on `stable_rf`
sub-model AUC (and therefore the blended ensemble) was not measured --
that requires running `train_classifier`'s full multi-model fit, which is
the expensive part of this pipeline (8 base models, `TimeSeriesSplit`
validation, per horizon) and was out of scope for today's check. The
lightweight `identify_stable_features`-only check (3 folds of a single
200-tree RF) is cheap and was run directly; the full training loop was
not.

**Default not flipped.** `dedupe_correlated` stays `False` -- this is a
new, validated-on-real-data-for-feature-selection-behavior-only opt-in,
not yet validated for AUC/ensemble impact. Flipping the default (the way
`expanding_model_weights` eventually was, after its own dedicated 07-07
verification session) would need that AUC check first, plus explicit user
sign-off before touching the daily production pipeline.

## Verification

- `python3 -m ast` syntax check clean.
- Module imports cleanly (`from scripts.misc.ncf_00631l import
  identify_stable_features, _deduplicate_correlated_features`).
- `tests/test_ncf_00631l_paths.py`: **13/13 pass** (8 pre-existing + 5 new
  -- `test_deduplicate_correlated_features_drops_near_duplicate`,
  `test_deduplicate_correlated_features_priority_order_picks_winner`,
  `test_deduplicate_correlated_features_below_threshold_keeps_both`,
  `test_identify_stable_features_dedupe_correlated_flag_off_matches_
  current_behavior` (the off-by-default regression guard, same pattern
  as `test_expanding_model_weights_flag_off_matches_current_behavior`),
  `test_identify_stable_features_dedupe_correlated_drops_redundant_pair`).

## Files

Modified:
- `scripts/misc/ncf_00631l.py` (`_deduplicate_correlated_features` new
  function; `identify_stable_features` gains `dedupe_correlated`/
  `corr_threshold` params, default off)
- `tests/test_ncf_00631l_paths.py` (5 new tests, listed above)

No production pipeline files modified -- `run_ncf_daily_pipeline.py`'s
invocation is unchanged, so today's daily panel generation is unaffected
until/unless someone explicitly flips `dedupe_correlated=True` somewhere
in the call chain.

## Recommended next step if this is pursued further

Run the full `train_classifier` path (or the existing `--feature-
stability` CLI flag's flow) with `dedupe_correlated=True` vs `False` on
a real historical window and compare H=20 val AUC directly -- the
missing piece flagged above. Given the specific redundant pair found
(`close_ma200_ratio` / `close_ma200_dist`, corr=1.000) is unlikely to be
carrying independent information, a neutral-to-positive AUC effect would
be the expected outcome, but should be confirmed empirically before
considering a default flip, per this project's standing discipline.
