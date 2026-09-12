# 2608.06618 MINGLE-lite GroupA+ Review - 2026-08-22

## Paper

- File: `C:/Users/isaac/Downloads/2608.06618.pdf`
- Title: `Beyond Co-Movement: Locality by Exposures Enables a Joint Factor-Graph Framework for Portfolio Diversification`
- Core idea: build portfolio diversification on factor-exposure similarity graphs instead of raw correlation/co-movement graphs.

## What Was Imported

Research-only MINGLE-lite diagnostic:

- Rolling PCA factor exposures as a lightweight proxy for MINGLE exposure profiles.
- RBF exposure-similarity graph over GroupA+ ETF legs plus cross-market reference assets.
- Factor-induced covariance conditioning diagnostic.
- Current target concentration and peripheral-alignment review.

This does not implement the paper's full non-convex ADMM joint factor-graph training, Adaptive CutV allocation, or Contagion Cut live allocation.

## Implementation Notes

The full paper method is deliberately not implemented in production form:

- The original MINGLE objective is non-convex and uses ADMM over factor and graph blocks.
- The paper's tested universe is large global equity constituents; GroupA+ live tradable universe is a small ETF set with leveraged and inverse products.
- Direct graph allocation on this universe can accidentally reward mechanically peripheral assets such as `00632R.TW` or over-shift away from the core 0050/00631L compounding engine.

The local adaptation therefore uses only a safe diagnostic approximation:

- Price panel is aligned with forward fill before return construction, because Taiwan, US, VIX, FX, rates, and gold have asynchronous trading calendars.
- PCA is fitted to exponentially downweighted log returns.
- Exposure similarity graph uses an RBF kernel on PCA exposure rows.
- Peripheral score is inverse graph degree, normalized to sum to 1.
- Factor covariance condition number is compared against sample covariance condition number as a denoising diagnostic.
- All generated reports set `production_effect: none` and `promotion_allowed: false`.

## Local Artifacts

- `group_a_plus/integrations/mingle_lite_diversification.py`
- `scripts/evaluate/build_group_a_plus_mingle_lite_readiness_review.py`
- `tests/test_group_a_plus_mingle_lite_diversification.py`
- `report/group_a_plus/latest/mingle_lite_readiness_review.json`
- `report/group_a_plus/latest/mingle_lite_readiness_review.md`
- `report/group_a_plus/mingle_lite_readiness_review/history/mingle_lite_readiness_review_20260822.json`

Peripheral-tilt shadow artifacts:

- `scripts/evaluate/evaluate_group_a_plus_mingle_lite_peripheral_tilt_shadow.py`
- `tests/test_evaluate_group_a_plus_mingle_lite_peripheral_tilt_shadow.py`
- `report/group_a_plus/latest/mingle_lite_peripheral_tilt_shadow.json`
- `report/group_a_plus/latest/mingle_lite_peripheral_tilt_shadow.md`
- `report/group_a_plus/mingle_lite_peripheral_tilt_shadow/history/mingle_lite_peripheral_tilt_shadow_20260822.json`

## Latest Result

As of `2026-08-21`, with 730 calendar days of lookback and 16 available assets:

- observations: `519`
- sample condition number: `887.62`
- factor condition number: `15.18`
- condition improvement ratio: `58.47`
- target risky weight sum: `0.6145`
- normalized risky target:
  - `0050.TW`: `0.8625`
  - `00631L.TW`: `0.1375`
- exposure similarity concentration: `0.150479`
- weighted graph degree: `8.873065`
- peripheral alignment: `0.003734`

The denoising/conditioning concept is useful as a diagnostic. The current live target is still mostly 0050 plus small 00631L, so this does not produce a new safe allocation by itself.

Readiness-review graph universe:

- `0050.TW`
- `00631L.TW`
- `00632R.TW`
- `00679B.TWO`
- `^TWII`
- `2330.TW`
- `2317.TW`
- `2454.TW`
- `SOXX`
- `QQQ`
- `NVDA`
- `TSM`
- `^VIX`
- `TWD=X`
- `^TNX`
- `GC=F`

Top peripheral assets in the latest readiness run:

- `00632R.TW`: `0.583991`
- `^VIX`: `0.363686`
- `00631L.TW`: `0.006290`

This is why direct graph allocation must stay constrained: the mathematically peripheral nodes are not necessarily live-eligible long allocation targets for GroupA+.

## Decision

Do not promote.

Reasons:

- `research_only_no_live_weight_change`
- `full_mingle_admm_not_implemented`
- No multi-window portfolio shadow has shown that exposure-graph peripheral tilts improve GroupA+ after turnover/costs.
- GroupA+ live ETF universe is small; graph-allocation methods can overfit or mechanically favor inverse/leveraged legs unless constrained.

Final policy:

- Keep MINGLE-lite as diagnostic-only.
- Do not change Golden1_0531.
- Do not change latest strategy target weights.
- Do not auto-rebalance from MINGLE-lite output.
- Do not open `00632R.TW` from any MINGLE-lite graph/peripheral score.
- Do not spend more time reproducing full ADMM unless there is a separate research goal unrelated to live GroupA+ deployment.

## Recommended Next Step

The proposed multi-window MINGLE-lite peripheral-tilt shadow was run after the
readiness review:

- Keep Golden1_0531 and latest strategy as the baseline.
- Capped tilt fractions: `0%`, `5%`, `10%`, `20%`.
- `00632R.TW` prohibited, so the shadow never opens inverse exposure.
- Monthly / 21-trading-day MINGLE-lite graph refresh.

Artifacts:

- `scripts/evaluate/evaluate_group_a_plus_mingle_lite_peripheral_tilt_shadow.py`
- `tests/test_evaluate_group_a_plus_mingle_lite_peripheral_tilt_shadow.py`
- `report/group_a_plus/latest/mingle_lite_peripheral_tilt_shadow.json`
- `report/group_a_plus/latest/mingle_lite_peripheral_tilt_shadow.md`
- `report/group_a_plus/mingle_lite_peripheral_tilt_shadow/history/mingle_lite_peripheral_tilt_shadow_20260822.json`

Result across 8 windows:

| tilt | delta final value sum | delta Sharpe sum | delta MDD sum | positive windows | non-worse MDD windows |
|---:|---:|---:|---:|---:|---:|
| `0%` | `0` | `0.0000` | `0.00%` | `0` | `8` |
| `5%` | `-147,617` | `+0.2265` | `+3.35%` | `2` | `6` |
| `10%` | `-149,741` | `+0.2079` | `+3.29%` | `2` | `6` |
| `20%` | `-153,965` | `+0.1689` | `+3.17%` | `2` | `6` |

Decision: closed negative for direct allocation tilt. The best final-value
choice is no tilt. MINGLE-lite remains useful only as a diversification
diagnostic; do not use it to alter live GroupA+ target weights.

## Reproduction Commands

Run readiness review:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_mingle_lite_readiness_review.py \
  --output report/group_a_plus/latest/mingle_lite_readiness_review.json \
  --output-md report/group_a_plus/latest/mingle_lite_readiness_review.md
```

Run peripheral-tilt shadow:

```bash
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_mingle_lite_peripheral_tilt_shadow.py \
  --output report/group_a_plus/latest/mingle_lite_peripheral_tilt_shadow.json \
  --output-md report/group_a_plus/latest/mingle_lite_peripheral_tilt_shadow.md
```

Run tests:

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_mingle_lite_diversification.py \
  tests/test_evaluate_group_a_plus_mingle_lite_peripheral_tilt_shadow.py \
  -q
```

Last verification:

- `tests/test_group_a_plus_mingle_lite_diversification.py`: included asynchronous-market missing value handling.
- `tests/test_evaluate_group_a_plus_mingle_lite_peripheral_tilt_shadow.py`: confirms `00632R.TW` is not opened by tilt.
- Combined result: `6 passed in 8.81s`.

## Shadow Window Set

The peripheral-tilt shadow used 8 windows:

- `covid_2020`: `2020-01-02` to `2020-12-31`, `results/ncf_00631l_panel_backfill_2020_20260716.csv`
- `recovery_2021`: `2021-01-04` to `2021-12-30`, `results/ncf_00631l_panel_backfill_2021_20260726.csv`
- `rate_hike_2022`: `2022-01-03` to `2022-10-31`, `results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv`
- `rebound_2023`: `2023-01-03` to `2023-12-29`, `results/ncf_00631l_panel_backfill_2023_20260726.csv`
- `full_2024`: `2024-01-02` to `2024-12-31`, `results/ncf_00631l_panel_backfill_2024_20260726.csv`
- `active_2025_2026`: `2025-01-02` to latest, `results/ncf_00631l_panel_latest_20260707.csv`
- `taiwan_2026_q1q2_stress`: `2026-02-02` to `2026-04-30`, `results/ncf_00631l_panel_latest_20260707.csv`
- `taiwan_2026_recent`: `2026-05-15` to latest, `results/ncf_00631l_panel_latest_20260707.csv`

Tilt configuration:

- `tilt_fractions`: `0`, `0.05`, `0.10`, `0.20`
- `prohibited_assets`: `00632R.TW`
- `lookback_days`: `730`
- `factor_count`: `3`
- `decay`: `0.997`
- `rebalance_every_days`: `21`
- `transaction_cost_bps`: `0.0`

## Important Gotchas

- `pdftotext` was not available in the environment; PDF extraction used `pypdf`.
- The first readiness run failed because asynchronous cross-market calendars caused too many `NaN` rows. Fixed by forward-filling prices before return construction in `build_mingle_lite_frame`.
- Peripheral score naturally ranked `00632R.TW` and `^VIX` highly. That is mathematically expected but operationally unsafe for live GroupA+ allocation.
- The tilt shadow improved some Sharpe/MDD aggregates but destroyed final value. Do not promote a risk metric improvement that comes from giving up the core compounding sleeve.
- Best final-value result is exactly no tilt, so this is not an ambiguous tuning problem.

## Final Status

`2608.06618` is complete for GroupA+ decision-making:

- Diagnostic import: accepted, research-only.
- Allocation import: rejected / closed negative.
- Live strategy impact: none.
- Follow-up priority: low. Revisit only if the goal is offline research on full ADMM, not production GroupA+ improvement.
