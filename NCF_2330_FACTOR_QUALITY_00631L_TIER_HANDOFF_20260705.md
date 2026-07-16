# NCF 2330 / 00631L Tier Handoff - 2026-07-05

## Scope

This handoff records the current state of the `ncf_2330` improvement work, the
TSMC daily/weekly checklist, the factor-quality overlay, the 00631L tier shadow
tests, and the 2008 proxy stress-test findings.

All production-weight changes remain blocked unless explicitly promoted later.
The new factor-quality logic is advisory/shadow only.

## Important Constraints

- A true 2008 `ncf_2330 + 00631L` backtest is not possible with current local data.
- Local `00631L.TW` OHLCV starts on `2015-01-05`.
- Local external `2330.TW` / `^TWII` cache starts around `2014-01-02`.
- 2008 tests must use TWII-derived proxy paths:
  - `0050.TW` proxy from TWII returns.
  - `00631L.TW` proxy as 2x TWII daily returns.
  - `00632R.TW` proxy as inverse TWII exposure.
- The factor-quality overlay should not be treated as a 2008 signal because its
  inputs depend on modern checklist sources and NCF panels.

## Files Added Or Modified In This Workstream

Primary new files:

- `scripts/report/build_ncf_2330_checklist.py`
- `scripts/fetch/fetch_ncf_2330_checklist_external_cache.py`
- `scripts/evaluate/evaluate_ncf_2330_checklist_factor_quality.py`
- `scripts/misc/shadow_ncf_2330_factor_quality_tier_overlay.py`
- `tests/test_ncf_2330_checklist.py`
- `tests/test_ncf_2330_checklist_factor_quality.py`
- `tests/test_ncf_2330_factor_quality_tier_overlay_shadow.py`

Important modified files:

- `ncf_2330.py`
- `group_a_plus/integrations/ncf.py`
- `group_a_plus/integrations/signal_alignment.py`
- `group_a_plus/operations/daily_signal.py`
- `scripts/run/run_ncf_daily_pipeline.py`
- `tests/test_group_a_plus_ncf_integration.py`
- `tests/test_group_a_plus_signal_alignment.py`
- `tests/test_group_a_plus_daily_signal_v2.py`
- `tests/test_run_ncf_daily_pipeline.py`

The repo already has many unrelated dirty/untracked files. Do not reset or
revert them without explicit user instruction.

## ncf_2330 Model Changes

`ncf_2330.py` was improved with:

- Tail-risk feature policy that excludes sparse TXO features from drawdown-risk
  models.
- Severe drawdown model:
  - `forward_severe_drawdown_risk`
  - `P(fwd 20d MDD > 8%)`
  - panel fields such as `prob_fwd_mdd_gt8_h20`
- TSMC 5-state classifier:
  1. `強勢領漲`
  2. `高檔震盪`
  3. `假突破`
  4. `拉回整理`
  5. `趨勢轉弱`
- Latest smoke result classified TSMC as `2 高檔震盪`.

Known smoke result from this workstream:

- 5% / 20d drawdown risk AUC: `0.6859`
- 8% / 20d severe drawdown risk AUC: `0.8271`
- feature policy: `tail_risk_exclude_txo_features`

## TSMC Checklist

`scripts/report/build_ncf_2330_checklist.py` builds a diagnostic-only daily or
weekly checklist with these layers:

- Fundamental:
  - monthly revenue YoY
  - 3-month QoQ proxy
  - YoY acceleration
  - gross margin / EPS still missing
- Valuation:
  - PE
  - PB
  - dividend yield
  - forward PE still missing
- Technical:
  - close vs 20MA / 60MA / 120MA
  - prior 60-day high
- ADR:
  - TSM ADR
  - USD/TWD
  - ADR premium/discount
- Global semiconductor:
  - SOXX
  - NVDA
  - AMD
  - ASML
- FX:
  - USD/TWD
  - DXY aliases
- Chip:
  - foreign net buy/sell
  - investment trust net buy/sell
  - dealer net buy/sell
  - foreign holding ratio
- 0050 relationship:
  - 2330 vs 0050
  - 0050 ex-TSMC proxy
- Latest `ncf_2330` snapshot

Checklist is diagnostic only:

```text
policy = diagnostic_only_no_weight_change
```

Run:

```bash
.venv/bin/python scripts/report/build_ncf_2330_checklist.py --output results/ncf_2330_checklist_$(date +%Y%m%d).json
```

## External Cache And Data Refresh

External checklist cache script:

```bash
.venv/bin/python scripts/fetch/fetch_ncf_2330_checklist_external_cache.py
```

Known successful cache run downloaded:

- `NVDA`: rows `751`, last `2026-07-02`
- `AMD`: rows `751`, last `2026-07-02`
- `ASML`: rows `751`, last `2026-07-02`
- `DX-Y.NYB`: rows `753`, last `2026-07-02`

FinMind PER refresh was run:

```bash
.venv/bin/python scripts/fetch/fetch_finmind_chip_data.py --datasets per --tickers 2330 --start 2023-01-01 --end 2026-07-06
```

Known result:

```text
[FinMind] per 2330: 845 rows
rows_written={'per': 845}
```

The NCF daily pipeline now includes:

- `refresh_2330_per`
- `ncf_2330_checklist`

## Factor-Quality Overlay

The checklist now includes:

```json
"factor_quality_overlay": {
  "status": "research_only",
  "signal": "...",
  "label": "...",
  "risk_score": ...,
  "opportunity_score": ...,
  "net_score": ...,
  "components": {...}
}
```

Components:

- `technical_extension`
- `valuation_heat`
- `fx_tail_pressure`
- `chip_crowding`
- `fundamental_growth`

Latest real-data smoke result:

```text
factor_quality_signal = bearish
label = risk_off
risk_score = 6.0
opportunity_score = 1.0
net_score = -5.0
```

Interpretation of latest snapshot:

- Not a fundamental deterioration signal.
- Risk came from:
  - price extended above 60MA and 120MA
  - PB elevated
  - USD/TWD pressure
  - foreign 5d net selling
  - investment trust 5d net buying, treated as possible crowding
- Fundamental monthly revenue remained a positive offset.

## Factor-Quality Evaluator

`scripts/evaluate/evaluate_ncf_2330_checklist_factor_quality.py` rebuilds the
checklist point-in-time and evaluates factor IC against:

- 2330 forward 5d return
- 2330 forward 20d return
- 20d forward MDD
- 20d tail event

Important lookahead protection:

- `ncf_2330.*` latest JSON snapshot is excluded by default.
- It can only be included with `--include-latest-ncf-snapshot`.

Example:

```bash
.venv/bin/python scripts/evaluate/evaluate_ncf_2330_checklist_factor_quality.py --start 2026-01-02 --end 2026-07-02
```

Short-window result:

- `2026-01-02 ~ 2026-06-03`
- rows: `98`
- factors: `81`

Strong factors in that short window:

- 20d return:
  - `technical.close_vs_ma120`
  - `technical.close_vs_ma60`
  - `fx.usdtwd`
  - `valuation.pb`
  - `valuation.pe`
- MDD:
  - `technical.close_vs_ma120`
  - `adr.tsmc_close_twd`
  - `technical.close`
  - `technical.close_vs_ma60`
- Tail event:
  - `fx.dxy_5d_change`
  - `technical.close_vs_ma60`
  - `technical.close_vs_ma120`
  - `chip.investment_trust_net_5d_shares`

## GroupA+ Integration

`group_a_plus/integrations/ncf.py` now has:

```python
load_ncf_2330_checklist(path)
```

This loads the checklist separately from the NCF model JSON. Do not mix the two
payload types.

`group_a_plus/integrations/signal_alignment.py` now surfaces an advisory-only
candidate:

```json
"shadow_momentum_candidate": true/false,
"shadow_momentum_note": "...",
"inputs": {
  "ncf_2330_factor_quality_signal": "...",
  "ncf_2330_factor_quality_risk_score": ...,
  "ncf_2330_factor_quality_net_score": ...
}
```

This does not alter the official tier. It only flags a possible shadow
`tier2 -> tier3` momentum confirmation.

Expected live signal location if wired later:

```text
ncf_live_overlay.ncf_2330_checklist.factor_quality_overlay
```

## 00631L Tier Shadow Tests

Script:

```bash
.venv/bin/python scripts/misc/shadow_ncf_2330_factor_quality_tier_overlay.py
```

Modes tested:

- `downgrade`
  - tier 3 -> 2
  - tier 2 -> 1
- `no_add`
  - tier 3 -> 2
  - tier 2 unchanged
- `momentum_confirm`
  - tier 2 -> 3
  - tier 0/1/3 unchanged

Default is weekly sampling:

```bash
.venv/bin/python scripts/misc/shadow_ncf_2330_factor_quality_tier_overlay.py --sample-step 5
```

Full daily:

```bash
.venv/bin/python scripts/misc/shadow_ncf_2330_factor_quality_tier_overlay.py --sample-step 1
```

The script supports subwindows:

```bash
.venv/bin/python scripts/misc/shadow_ncf_2330_factor_quality_tier_overlay.py \
  --sample-step 5 \
  --start 2026-01-02 \
  --end 2026-07-02
```

### Shadow Results

Weekly full window:

```text
Best spec: risk4_net2_scoreonly_momentum
Changed days: 5
Affected mean 20d excess vs 0050: +9.8265%
Win rate vs 0050: 100%
bad MDD > 5%: 0%
```

Daily full window:

```text
Best spec: risk4_net2_scoreonly_momentum
Changed days: 6
Affected mean 20d excess vs 0050: +7.8112%
Win rate vs 0050: 100%
bad MDD > 5%: 0%
```

Subwindow results:

| Window | Sampling | Best/Observation | Changed Days | 20d Excess vs 0050 | Conclusion |
|---|---:|---|---:|---:|---|
| 2025-2026 | weekly | `momentum_confirm` | 5 | `+9.83%` | positive, small sample |
| 2025 only | weekly | no valid rule | 2 | `+5.32%` | insufficient sample |
| 2026 only | weekly | downgrade score negative | 6 | downgraded days were `+11.35%` | do not downgrade |
| 2025-2026 | daily | `momentum_confirm` | 6 | `+7.81%` | same direction, small sample |

Current decision:

- Do not use `factor_quality_overlay` to downgrade 00631L.
- Do not use it to block adding.
- It can remain an advisory-only `tier2 -> tier3 momentum candidate`.
- It is not eligible for production-weight changes because sample size is only
  about 5-6 changed days.

## 2008 Proxy Findings

True 2008 `ncf_2330 + 00631L` is unavailable with current data. Existing repo
proxy results were reviewed instead.

Data availability:

```text
ohlcv:
  0050.TW   2009-01-02 to 2026-07-03
  00631L.TW 2015-01-05 to 2026-07-03

external_market_ohlcv:
  2330.TW 2014-01-02 to 2026-07-02
  ^TWII   2014-01-02 to 2026-07-01
```

Existing 2008 proxy result files:

- `results/group_a_twii_proxy_2008_20070701_20101231_20260526_193325.json`
- `results/group_a_twii_proxy_2008_inverse_sweep_20070701_20101231.json`
- `results/group_a_twii_proxy_2008_conditional_inverse_20070701_20101231.json`
- `results/group_a_meta_adv_conditional_inverse_twii_proxy_2008_20070701_20101231_20260603_163629.json`

Read summary:

| Test | Total Return | Sharpe | Max DD | Trades |
|---|---:|---:|---:|---:|
| inverse sweep baseline | `+52.50%` | `0.540` | `-50.44%` | 147 |
| conditional inverse baseline | `+53.16%` | `0.642` | `-48.62%` | 94 |
| conditional inverse best | `+53.50%` | `0.645` | `-48.61%` | 93 |
| meta adv canonical proxy | `+49.44%` | `0.572` | `-38.02%` | 310 |

Interpretation:

- 2008 TWII proxy stress test survives, but drawdown remains severe.
- Conditional inverse improves Sharpe and modestly improves max drawdown versus
  inverse sweep baseline.
- Meta adv canonical proxy has much lower max drawdown, but with higher trading
  count and lower total return than conditional inverse.
- The 2008 proxy is suitable for testing price/volatility controls, not
  checklist factor quality.

Attempted rerun notes:

- `scripts/backtest/backtest_group_a_twii_proxy_2008.py` failed because default
  payload path points to a non-existing `scripts/backtest/results/...` path.
- Running with `PYTHONPATH=.` fixed module import but not missing payload.
- Repo currently lacks `results/group_a_runtime_payload_primary_20260524.json`.
- Existing 2008 proxy JSONs are usable for review.

## Commands Verified

Compile/test commands run successfully:

```bash
.venv/bin/python -m py_compile scripts/misc/shadow_ncf_2330_factor_quality_tier_overlay.py
.venv/bin/python -m pytest -q tests/test_ncf_2330_factor_quality_tier_overlay_shadow.py
.venv/bin/python -m pytest -q tests/test_group_a_plus_signal_alignment.py tests/test_ncf_2330_factor_quality_tier_overlay_shadow.py
.venv/bin/python -m pytest -q tests/test_group_a_plus_signal_alignment.py tests/test_group_a_plus_ncf_integration.py tests/test_ncf_2330_checklist.py tests/test_ncf_2330_factor_quality_tier_overlay_shadow.py tests/test_run_ncf_daily_pipeline.py
```

Known successful test totals:

- `4 passed` for tier overlay shadow tests.
- `22 passed` for signal alignment + tier overlay tests.
- `97 passed` for broader NCF/checklist/signal/pipeline group.

## Recommended Next Steps

1. Keep `factor_quality_overlay` as research/advisory only.
2. Do not promote any 00631L weight change from this overlay yet.
3. Continue collecting daily `shadow_momentum_candidate` observations.
4. Promote only if changed-day sample grows materially and holds up across:
   - 2025/2026 split
   - daily and weekly sampling
   - rising and falling markets
   - 20d excess return and MDD criteria
5. For 2008, test price/volatility proxy rules instead of NCF/checklist:
   - MA breakdown
   - realized volatility percentile
   - rolling MDD
   - TWII 20d/60d momentum
   - conditional inverse/cash caps

## Current Decision Record

Production status:

```text
ncf_2330 model enhancements: usable
TSMC checklist: usable diagnostic
factor_quality_overlay: research-only
00631L tier downgrade: rejected
00631L no-add: rejected
00631L tier2->tier3 momentum candidate: advisory-only shadow candidate
2008 direct ncf_2330/00631L backtest: unavailable
2008 TWII proxy stress test: available and reviewed
```

