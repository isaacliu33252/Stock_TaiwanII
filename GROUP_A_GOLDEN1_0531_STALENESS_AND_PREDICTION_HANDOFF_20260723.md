# Group A "Golden1_0531" Naming/Staleness Investigation + 7/24 Prediction Handoff - 2026-07-23

## Status

**Investigation + informational forecast only. No production files changed,
no strategy/config modified.** This continues the same 2026-07-23 session
as `GROUP_A_PLUS_FABLE_10_DIRECTIONS_AUDIT_HANDOFF_20260723.md` but is a
separate, unrelated task: the user asked for a $1,000,000 7/24 forecast
under both `golden1_0531` and the "latest strategy" (a2118). What started
as a simple prediction turned into a real governance-drift discovery about
Group A (not Group A+) that's worth a standalone record.

## What was actually done today (chronological)

1. Ran the daily **data download** (`run_fetch.bat`'s equivalent:
   `run_ncf_daily_pipeline.py --only-refresh --force-refresh --strict-refresh
   --fail-on-ohlcv-warning`). 18/18 steps completed, exit 0. One transient,
   non-fatal failure: `refresh_taifex` (TAIFEX futures, not options) failed
   once inside the pipeline; re-ran `taifex_futures_data.py --refresh-latest`
   standalone immediately after and it succeeded cleanly (wrote 2026-07-22
   TX futures data, which is the correct latest available -- 07-23's
   futures haven't settled/published yet). Not a real data-source outage,
   just a one-off hiccup; no further action needed.
2. Regenerated `results/00631l_leveraged_compounding_regime_20260723.json/
   .csv` (was stale at 07-22, causing a spurious `execution_guard_reasons`
   date-mismatch block when generating a fresh a2118 execution plan for
   07-24 -- see Finding A below).
3. Attempted a $1,000,000 "predict 7/24" forecast for two strategies:
   `golden1_0531` and a2118 ("latest strategy"). Initial attempt for
   `golden1_0531` incorrectly reused a stale static snapshot
   (`results/signal_group_a_golden1_0531_predict_20260615_from_all_20260613_
   total1000000.json`, 0050=60%/00631L=20%/cash=20%) as if it were "the
   golden1_0531 answer for today" -- **this was wrong**, corrected below
   (Finding B/C).

## Finding A (FIXED 2026-07-24): `_latest_prices()` in execution_plan.py crashes on fully-empty holdings

While building a "fresh $1,000,000, zero existing holdings" scenario for
a2118 via `group_a_plus.operations.execution_plan`'s `--holdings-json`, a
holdings dict with every ticker at `0` shares triggers
`_latest_prices(db_path, [], requested_as_of)` -- an empty `WHERE ticker IN
()` SQL clause, which DuckDB rejects with `ParserException: syntax error at
or near ")"`. Workaround used: set one ticker (0050.TW) to `1` share
(negligible, ~$104 on a $1M base) instead of `0`. **Not fixed in code** --
this is a minor, easily-reproduced edge case (`held_tickers = sorted(ticker
for ticker, shares in holdings.items() if shares != 0)` at
`group_a_plus/operations/execution_plan.py` around line 598, feeding into
`_latest_prices` at line 600) worth a one-line guard (skip the query / return
`{}` when `held_tickers` is empty) if anyone touches this function again.
**Fixed 2026-07-24**: added a one-line guard (`if not tickers: return {}`)
at the top of `_latest_prices()`. New regression test
`test_latest_prices_returns_empty_dict_for_empty_ticker_list` in
`tests/test_group_a_plus_execution_plan_v2.py`. Verified the original
all-zero-holdings scenario now succeeds end-to-end via
`build_execution_plan` (no workaround needed anymore); 24/24 tests in
that file pass, 33/33 across the execution-plan + execution-guard test
files.

## Finding B: "golden1_0531" is a release name, not a frozen date snapshot -- but the user's instinct that something was off was directionally right

The user reasonably read "0531" as "this strategy is fixed/frozen as of
2026-05-31." That is **half right**: `GROUP_A_GOLDEN1_0531_RELEASE.md`
(2026-05-31) confirms `Golden1_0531` is the **release name** of Group A's
then-current production strategy (PPO model `group_a_production_2020_2025_
100k`, `triplet_v4` discrete action schema, institutional+LLM-sentiment
features, PVA/SJM continuous risk-scaling overlay, local TWII/0050 regime
defensive overlay, exposure caps 00631L=20%/00632R=30%, `pva_weight=0.32`).
The doc explicitly states a **three-month trial freeze**: "production
release remains frozen during the three-month trial" (2026-06-01 to
2026-08-31) -- i.e. the *config* was supposed to stay fixed, while still
producing **fresh live predictions every day** from new market data (not a
one-time static answer). `GROUP_A_GOLDEN1_0531_IMPROVEMENT_EXPERIMENT.md`
(same day) confirms a shadow-only PVA micro-sweep candidate
(`pva036_j015`) was evaluated and explicitly *not* promoted, "does not
justify changing the production strategy during the three-month trial."

## Finding C: the freeze was NOT honored -- documented supersession only 12 days into the trial

`GROUP_A_LATEST_HANDOFF_20260612.md` (2026-06-12, i.e. day 12 of the
supposed 3-month freeze) records that Group A's **production release name
changed** to `latest_group_a_improved_0050_step0300bp_stepgate105_ma60_
brake30_631l0_tdcc18`, adding three new overlays on top of the same
underlying PPO model output: a 0050 target-weight step limiter (+/-3pp per
signal, released when 0050 > MA60*1.05), an MA60 trend brake (caps 0050 at
30% and 00631L at 0% when 0050 <= MA60), and a TDCC shareholding-crowding
overlay (00631L caution cap 18%, risk-off cap 0%). This matches the
hardcoded `RELEASE_NAME` constant currently sitting at the top of
`scripts/run/run_group_a_combined_signal.py` -- **this is a real,
documented governance change, not silent code drift**, but it directly
contradicts the golden1_0531 release doc's explicit "frozen until
2026-08-31" commitment. No further Group-A-specific (non-Group-A+) handoff
doc exists after 2026-06-12, so it is unknown whether the config changed
again since then, or whether it's still on this 06-12 "improved" version
today (07-23).

**Separately discovered documentation inconsistency** (not chased further):
the release manifest `results/group_a_release_Golden1_0531.json` lists
`model_checkpoint: models/portfolio/group_a_oos_2020_2024_cap20_llm_pva_
tripletv4_inst_localregime_20260526.zip`, but the `strategy_payload` JSON
it also references (`results/group_a_backtest_20250101_20260525_
20260526_193252.json`) internally records `model_name:
group_a_production_2020_2025_100k` -- a *different* model file. Both
`.zip` files do exist on disk. Not resolved; flagged for whoever next
touches Group A model provenance.

**2026-07-25 addendum: chased further, and it's worse than a labeling
inconsistency -- the payload file itself was silently overwritten after
the release, most likely with a different model's output.** Full
timeline reconstructed from file mtimes (`ls -la --time-style=full-iso`):

| Artifact | Timestamp |
|---|---|
| `group_a_oos_..._tripletv4_inst_localregime_20260526.zip` (the `model_checkpoint` the manifest names) | 2026-05-26 19:32:50 |
| Payload filename's own embedded suffix (`..._20260526_193252.json`) | matches the checkpoint's mtime to the second |
| `group_a_release_Golden1_0531.json` (the release manifest itself) | 2026-05-31 14:49:16, `release_date` field also 2026-05-31 |
| `group_a_production_2020_2025_100k.zip` (the model the payload's *internal* `model_name` field names) | 2026-06-09 21:40:22 |
| **The payload JSON file's actual mtime on disk today** | **2026-06-09 21:49:06 -- 9 minutes after that second model checkpoint** |

The payload's filename and the referenced checkpoint's mtime agree with
each other almost to the second (both `2026-05-26 19:32:5x`), and the
release manifest was written five days later (05-31) evidently against
that same, consistent pair -- everything is self-consistent as of
release time. But the payload **file currently on disk was last
modified 2026-06-09 21:49:06, nine minutes after `group_a_production_
2020_2025_100k.zip` was created** -- strong circumstantial evidence that
some later pipeline run reused the exact same output filename (its name
is deterministic from its date-range/timestamp arguments, so a rerun
with matching arguments would silently overwrite it) and regenerated it
using the *newer* model, without renaming the file or updating the
release manifest that still points to it by name. The payload's own
internal `model_name: group_a_production_2020_2025_100k` field is
consistent with this -- it's not a stale label, it's honestly reporting
which model actually produced the content **currently** in that file,
which is not the same content (or necessarily the same model) the
release manifest was written against on 05-31.

**Practical implication**: the original 05-31 golden1_0531 release-time
backtest evidence, as referenced by `results/group_a_release_
Golden1_0531.json`, was very likely silently overwritten in place at
some point on or after 2026-06-09 and is presumably not recoverable from
this file -- there is no versioned/dated backup found. This compounds
Finding C's main point above (the freeze itself wasn't honored,
superseded 12 days in by a documented config change) with a second,
independent problem: even the frozen release's own supporting evidence
file didn't stay frozen either, and nothing detected or flagged the
silent overwrite at the time. No code fix applied -- this is a
provenance/process finding (deterministic output filenames without
versioning is the root mechanism), not a single bug with an obvious
one-line fix; flagged for whoever next works on Group A's release/backtest
output conventions. Group A (as opposed to Group A+) release-output
paths generally would benefit from either content-hashing the model
checkpoint into the output filename, or refusing to overwrite an existing
release-referenced artifact -- not implemented today, out of scope for a
single-session fix.

## Finding D: Group A's own "latest signal" tracking is itself stale and inconsistent across pointers

Two different "latest" files disagree on freshness as of today (07-23):
- `results/group_a_combined_live_latest.json` (the wrapper script's stable
  output pointer) -- last generated 2026-07-08 (actual data 07-06), **15
  days stale**.
- `results/signal_group_a_20260716_175626.json` (the file `a2118.py`
  actually reads via `_resolve_golden_signal_path()`, already flagged
  stale in an earlier 2026-07-23 session segment -- see Fable direction 8
  in the sibling handoff doc) -- last generated 07-16, **7 days stale**.

Neither is being kept fresh by any daily-pipeline step observed today
(`run_ncf_daily_pipeline.py`/`run_daily.bat`/`run_fetch.bat` do not appear
to invoke `run_group_a_combined_signal.py`). This is consistent with, and
adds detail to, the "Group A's underlying RL model is stale/not actively
maintained" observation already recorded in Fable direction 8
(`project_a2118_remaining_fable_directions_5_8_10_20260723` memory).

## How the strict golden1_0531 reconstruction was actually done

`scripts/run/run_group_a_combined_signal.py` cannot be used for this --
its hardcoded defaults now reflect the post-06-12 "improved" release
(step limiter/MA60 brake/TDCC always applied; none of these are
individually toggleable except TDCC). Instead, called the underlying
`generate_dual_group_signal.py` **directly**, bypassing the wrapper, whose
newer-overlay flags all default to `None`/disabled when unset:

```bash
python3 generate_dual_group_signal.py \
  --group group_a \
  --result-json results/group_a_backtest_20250101_20260525_20260526_193252.json \
  --as-of-date 2026-07-24 \
  --live-start \
  --extra-cash 1000000 \
  --override-holdings-json '{"0050":0,"00631L":0,"00632R":0}' \
  --action-threshold 0.01 \
  --max-stale-days 60
```

This reads the model reference (`group_a_production_2020_2025_100k`) and
all PVA/exposure-cap/institutional/LLM-sentiment/local-regime config
directly from the golden1_0531 payload JSON, with fresh 07-23 market data,
and none of the later overlays. Output:
`results/signal_group_a_20260723_223610.json` /`.csv`.

## Result: 7/24 forecast, $1,000,000 fresh capital, both strategies

**golden1_0531 (strict original config, no later overlays), 07-23 close
data:**
- 0050.TW: 50% / 4,812 shares / $499,863
- 00631L.TW: 20% / 5,703 shares / $200,004
- cash: 30% / $300,133

**a2118 (current Group A+ production), same $1,000,000, same date:**
- Theoretical (unstaged) target: 0050=4,812 shares / 00631L=5,703 shares --
  **identical to golden1_0531's numbers above, to the share.**
- Actual staged recommendation: 0050=3,368 shares (buy, $349,831),
  00631L=3,992 shares (buy, $139,999) -- staging accelerated to 70%
  (not the usual 40%) because `trough_nowcast` currently reads
  `PARTIAL_REENTRY`.
- `pre_trade_guard` status `flagged_advisory_only` (high-volatility gate
  active but not auto-blocking, per today's earlier fix -- see sibling
  handoff doc's Finding 1).

**Interpretation given to the user**: golden1_0531 and a2118 share the
exact same underlying Group A model output (50/20/30) -- confirming
`a2118.py`'s `_weights_from_group_a()` really is pulling from this same
PPO model, not an independently-diverged judgment. The only difference
between "what golden1_0531 says" and "what a2118 actually recommends
today" is Group A+'s own execution-discipline layer on top (staged
buying, NCF overlay, guards) -- not a difference in market view.

## Open follow-ups

**2026-07-25 update**: items 2 and 3 below are resolved as of today (see
their respective Finding sections above for detail); items 1 and 4 remain
open.

1. Whether Group A's production config changed again after
   2026-06-12 -- no doc found either way; the two "latest" pointer files
   are too stale (07-08, 07-16) to tell us what's *actually* running now.
2. ~~The `model_checkpoint` vs. payload `model_name` mismatch inside
   `results/group_a_release_Golden1_0531.json` (Finding C).~~ **Resolved
   2026-07-25**: not a labeling inconsistency -- the payload file itself
   was silently overwritten on disk after the release (see Finding C's
   07-25 addendum above for the full mtime-based timeline).
3. ~~`_latest_prices()`'s empty-`held_tickers` crash (Finding A) -- trivial
   one-line fix, not applied.~~ **Already fixed 2026-07-24** (see Finding
   A's own heading above, which already says FIXED -- this list just
   wasn't updated to match at the time).
4. Nobody has reconciled whether the "frozen until 2026-08-31" trial
   review is still meaningful given the release was already superseded
   12 days in -- this is a Group A governance question, separate from
   today's Group A+ (Fable audit) work, and out of scope for this
   session.

## Files touched today (this sub-task only; see sibling handoff for the
Fable-audit file list)

- `results/00631l_leveraged_compounding_regime_20260723.json` / `.csv`
  (new, regenerated)
- `results/signal_group_a_20260723_223610.json` / `.csv` (new, the strict
  golden1_0531 reconstruction)
- Scratch/temp files under the session scratchpad (zero-holdings JSON,
  throwaway a2118 execution-plan outputs) -- not part of the repo, safe
  to ignore/expire.
- No production code or config files modified in this sub-task.
