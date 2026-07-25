# GroupA+ NCF / GMM Backfill Record（2026-07-17）

## Question

Can adding more NCF panel data improve the GMM density-head result from
`2606.30037`?

## Data Coverage Check

Local DuckDB source:

- `FinRL/data/stock_data.db`

Key findings:

- `2022_rate_hike` can be backfilled at comparable NCF panel quality.
  - `00631L.TW`, `0050.TW`, `00632R.TW`, `00679B.TWO` OHLCV all cover
    `2022-01-03 ~ 2022-10-31`.
  - institutional / margin data cover 2020 onward.
  - TAIFEX options and futures tables cover 2020 onward.
- `2015_china` can be price-backfilled only, but it is not comparable to the
  current NCF panel quality.
  - ETF OHLCV exists.
  - institutional / margin / TAIFEX options features are missing before 2020.

Decision:

- Backfill `2022_rate_hike` first.
- Do not use 2015 as a same-quality GMM promotion window without a separate
  lower-feature methodology label.

## Backfilled Panel

Generated:

- `results/ncf_00631l_backfill_2022_rate_hike_20260717.json`
- `results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv`

Command:

```bash
MPLCONFIGDIR=/tmp/matplotlib-ncf .venv/bin/python scripts/misc/ncf_00631l.py \
  --train-start 2017-01-01 \
  --val-start 2022-01-03 \
  --val-end 2022-10-31 \
  --output results/ncf_00631l_backfill_2022_rate_hike_20260717.json \
  --val-predictions-output results/ncf_00631l_panel_backfill_2022_rate_hike_20260717.csv \
  --full-panel
```

Panel sanity check:

- rows: `202`
- columns: `22`
- date range: `2022-01-03 ~ 2022-10-31`
- final 20 rows are full-panel unlabeled/live tail rows, as expected.

## Density-Head Result

Generated:

- `results/density_head_tail_risk_shadow_00631l_2022_rate_hike_backfill_20260717.json`
- `results/density_head_tail_risk_shadow_00631l_2022_rate_hike_backfill_20260717_predictions.csv`
- `results/density_head_tail_risk_param_sweep_00631l_2022_rate_hike_backfill_20260717.json`
- `results/density_head_tail_risk_param_sweep_00631l_2022_rate_hike_backfill_20260717_rows.csv`

Single-run result:

| head | CRPS | q05 pinball | VaR 5% breach | central 90% coverage | tail alert precision | tail alert FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| point | 0.2731 | 0.2542 | 85.9% | 0.0% | 92.6% | 6.7% |
| Gaussian | 0.2226 | 0.1179 | 59.3% | 40.7% | 88.9% | 10.0% |
| GMM | 0.1712 | 0.0985 | 51.1% | 28.9% | 85.2% | 13.3% |

Parameter sweep:

- rows: `30`
- `gmm_wins_crps = 30 / 30`
- `gmm_wins_pinball_q05 = 24 / 30`
- `gaussian_wins_crps = 0 / 30`
- `gaussian_wins_pinball_q05 = 6 / 30`

Best GMM candidate:

- `gmm_components = 2`
- `alert_quantile = 0.10`
- `seed = 42`
- GMM CRPS: `0.1564`
- Gaussian CRPS: `0.2226`
- GMM q05 pinball: `0.0695`
- Gaussian q05 pinball: `0.1179`
- GMM tail alert precision: `85.7%`
- GMM tail alert FPR: `6.7%`

## Conclusion

Adding the 2022 rate-hike NCF panel improves the evidence for GMM materially.
On this newly backfilled window, GMM wins CRPS consistently and usually wins
q05 tail loss.

However, this is not enough for live promotion:

- 2018 correction still favors Gaussian.
- 2020 COVID still favors Gaussian.
- 2026 recent favors GMM, and 2022 now favors GMM, but the evidence is
  regime-dependent.
- GMM improves distributional fit, not trade alpha.

Current strategy decision remains unchanged:

- keep GroupA+ latest strategy unchanged;
- keep `Golden1_0531` unchanged;
- do not auto-rebalance;
- do not auto-add `00631L`;
- keep GMM as research-only pending a combined multi-window promotion test.

## Multi-Window Promotion Review

Generated:

- `scripts/evaluate/build_density_head_tail_risk_promotion_review.py`
- `report/group_a_plus/latest/density_head_tail_risk_promotion_review.json`

Result:

- required windows available: `5 / 5`
- aggregate sweep rows: `150`
- aggregate GMM CRPS win rate: `40.0%`
- aggregate GMM q05 win rate: `20.0%`
- stable GMM windows: `2022_rate_hike_backfill`
- required crash failures: `2018_correction`, `2020_covid`
- promotion decision: `promote_to_live = false`
- recommended research baseline: `gaussian_residual_head`

Blockers:

- `gmm_failed_required_crash_windows`
- `aggregate_gmm_crps_win_rate_below_70pct`
- `aggregate_gmm_q05_win_rate_below_60pct`

## Next Research Step

The next useful research step is not live promotion. It is either:

- keep Gaussian as the current residual density-head baseline; or
- test a hybrid rule where GMM is allowed only in detected 2022-like / recent
  high-rate regimes, while Gaussian remains the crash-window default.

Any hybrid rule must still be research-only until it passes the same
multi-window promotion review without failing 2018 / 2020 crash windows.
