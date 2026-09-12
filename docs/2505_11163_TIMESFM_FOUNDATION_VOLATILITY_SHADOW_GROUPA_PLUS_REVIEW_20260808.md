# 2505.11163 / TimesFM Foundation Volatility Shadow - Unfinished Scaffold Status

**Status: incomplete scaffold, research-only, no production impact.**

Written 2026-08-08 during a full-repo paper-audit action-items follow-up.
`group_a_plus/integrations/foundation_volatility_shadow.py` existed since
the 2026-07-16 upload with no doc, and no arXiv-ID / "TimesFM" reference
anywhere in the repo's docs. This records what it actually is today.

## What the module claims to be

Its own docstring: "the first integration step for foundation time-series
volatility models such as TimesFM. It deliberately starts with HAR-RV
context variants so the GroupA+ pipeline can validate schema, evaluation,
and downstream policy hooks before any heavyweight model dependency is
introduced."

## What it actually is

A pure HAR-RV (Garman-Klass realized variance + walk-forward HAR-RV
forecast, both already existing in
`group_a_plus/integrations/volatility_forecast.py`) proxy, dressed in
column names that mimic what a real foundation-model integration would
look like (`har_rv_ctx{context}_h{horizon}_variance` instead of, say,
`timesfm_ctx{context}_h{horizon}_variance`). There is:

- no TimesFM model, checkpoint, or inference call anywhere in the file or
  its dependencies,
- no `timesfm` (or any foundation-model) package in the project's
  dependencies,
- `latest_foundation_vol_snapshot()`'s output hardcodes
  `"model_family": "har_rv_context_shadow"` -- it does not even claim to be
  a foundation-model output at the data-contract level.

In other words: the schema/plumbing step described in the docstring was
built, but the actual model swap-in ("replacing only the producer," per the
`build_foundation_vol_shadow_frame` docstring) never happened. This is a
scaffold with nothing behind it yet, not a partially-validated model.

## Wiring / usage

- Not referenced in `scripts/run/run_ncf_daily_pipeline.py` -- not part of
  the daily pipeline.
- Its only consumer is
  `scripts/evaluate/evaluate_group_a_plus_reentry_accelerator_clean.py`
  (imports `build_foundation_vol_shadow_frame`), which is itself a
  standalone research-evaluation script, also not in the daily pipeline.
  That script's own conclusion is `"research_only": True`,
  `"decision": "do_not_promote_keep_shadow"`.
- `tests/test_group_a_plus_foundation_volatility_shadow.py` -- 3 tests,
  all passing, but they test the HAR-RV proxy math/schema only, not any
  foundation-model behavior (there is none to test).

## Production Decision

No production or shadow-pipeline change. The module is inert scaffolding:
it computes real HAR-RV numbers correctly, but the paper's actual
contribution (a pretrained foundation time-series model doing the
forecasting) was never implemented. Treat any reference to "foundation
volatility shadow" elsewhere in this project as describing this HAR-RV
proxy, not a TimesFM-backed forecast, until/unless a real model integration
is added here.

Not resumed in this pass -- recording current state only, per this punch
list item's scope ("記錄...未完成狀態").
