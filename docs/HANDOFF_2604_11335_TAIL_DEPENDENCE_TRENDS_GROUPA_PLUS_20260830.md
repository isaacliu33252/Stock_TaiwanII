# 2604.11335 Tail Dependence Trends Review for GroupA+

Date: 2026-08-30  
Paper: `C:\Users\isaac\Downloads\2604.11335.pdf`  
Title: `Trends in tail dependence of heteroscedastic extremes`  
arXiv: `2604.11335v1`, paper date `2026-04-14`  
Authors: John H. J. Einmahl, Chen Zhou

## Decision

Do not import the paper's full nonparametric tail-copula test into GroupA+
latest strategy or live gating.

Adopt only a shadow diagnostic interpretation:

- monitor whether tail dependence among GroupA+ ETF legs is stable or changing;
- treat high `0050.TW`/`00631L.TW` lower-tail co-exceedance as a caution against
  adding leverage;
- do not use this paper to open or increase `00632R.TW`;
- do not change target weights;
- keep `Golden1_0531` unchanged.

## Paper Summary

The paper is an extreme-value statistics paper, not a trading or ETF allocation
paper. It studies multivariate extremes when observations are independent but
not identically distributed, tail copulas can vary smoothly over time, and
marginal distributions can be heteroscedastic.

The useful idea is conceptual: tail dependence can trend over time, and changing
marginal volatility should not automatically be confused with changing tail
dependence. This is relevant to GroupA+ because `0050.TW`, `00631L.TW`,
`00632R.TW`, and `00679B.TWO` can change their crisis co-movement behavior over
time.

## GroupA+ Applicability

Direct live import is blocked:

- the paper is asymptotic statistical theory, not a portfolio policy;
- exact tail-copula testing needs careful `k` / bandwidth calibration and larger
  samples than the small GroupA+ ETF universe provides;
- it does not define position sizing, hedge ratios, transaction costs, or ETF
  execution rules;
- it does not solve `00632R.TW` realized-loss governance or inverse-ETF
  eligibility.

The practical import is a shadow monitor:

- reuse the existing `2607_16450_tail_dependence_monitor` style;
- estimate rolling lower-tail co-exceedance proxies;
- add trend/stability summaries inspired by `2604.11335`;
- keep the result advisory only.

## Implemented Artifact

Implemented:

- `scripts/evaluate/build_group_a_plus_2604_11335_tail_dependence_trend_review.py`
- `tests/test_build_group_a_plus_2604_11335_tail_dependence_trend_review.py`
- `report/group_a_plus/latest/2604_11335_tail_dependence_trend_review.json`
- `report/group_a_plus/latest/2604_11335_tail_dependence_trend_review.md`
- `report/group_a_plus/2604_11335_tail_dependence_trend_review/history/2604_11335_tail_dependence_trend_review_20260828.json`

Command run:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2604_11335_tail_dependence_trend_review.py
```

Test run:

```bash
.venv/bin/python -m pytest tests/test_build_group_a_plus_2604_11335_tail_dependence_trend_review.py
```

Result: `3 passed`.

## Latest Result

As of `2026-08-28`, status is `available_for_shadow_monitoring`.

Latest lower-tail co-exceedance proxy versus `0050.TW`:

- `00631L.TW`: `0.923077`, co-exceedance days `24`, correlation `0.975193`
- `00632R.TW`: `0.000000`, co-exceedance days `0`, correlation `-0.978399`
- `00679B.TWO`: `0.076923`, co-exceedance days `2`, correlation `-0.027451`

Trend summary:

- `00631L.TW`: latest `0.923077`, long-run mean `0.843205`,
  recent-minus-prior `0.050657`, slope `-0.000003`
- `00632R.TW`: latest `0.000000`, long-run mean `0.000000`,
  recent-minus-prior `0.000000`, slope `0.000000`
- `00679B.TWO`: latest `0.076923`, long-run mean `0.116797`,
  recent-minus-prior `0.012896`, slope `0.000054`

Warnings:

- `00631l_lower_tail_dependence_high_vs_0050`
- `high_latest_lower_tail_dependence_present`

No recent tail-dependence-rising asset was flagged by the configured threshold.

## Interpretation

The paper is useful because it strengthens the reason to track changing tail
dependence separately from ordinary volatility. The current GroupA+ evidence
does not support a live allocation change.

`00631L.TW` still has very high lower-tail dependence with `0050.TW`, which is
expected for a 2x Taiwan equity ETF and is a caution against using this research
line to add leverage. `00632R.TW` has zero lower-lower co-exceedance against
`0050.TW`, but that does not prove it is a good live hedge; inverse-ETF use is
still governed by separate `00632R` manual review and realized-loss constraints.
`00679B.TWO` has low latest lower-tail co-exceedance, but the signal is not
strong enough to create a live bond allocation rule.

## Final Decision

- `best_import = shadow_tail_dependence_trend_diagnostic_only`
- `promote_tail_copula_test_to_live_gate = false`
- `target_weight_change_allowed = false`
- `auto_rebalance_allowed = false`
- `allow_00631l_add_from_tail_dependence = false`
- `allow_00632r_open_from_tail_dependence = false`
- `keep_golden1_0531_unchanged = true`

This paper is worth keeping as a diagnostic upgrade to tail-dependence
governance, but not as a live strategy module.

## Robustness Sweep Addendum

User asked to continue after the initial review. A parameter robustness sweep was
added to check whether the `00631L.TW` high lower-tail dependence finding was a
single-parameter artifact.

Implemented:

- `scripts/evaluate/sweep_group_a_plus_2604_11335_tail_dependence_trend_robustness.py`
- `report/group_a_plus/latest/2604_11335_tail_dependence_trend_robustness.json`
- `report/group_a_plus/latest/2604_11335_tail_dependence_trend_robustness.md`

Sweep grid:

- `alpha`: `0.05`, `0.10`, `0.15`
- rolling window: `126`, `252`, `504`
- total runs: `9`

Result:

- valid runs: `9`
- high `00631L.TW` lower-tail dependence runs: `9`
- recent-rising `00631L.TW` runs: `0`
- `00631l_high_tail_dependence_robust = true`
- `00631l_recent_rising_robust = false`

Latest `00631L.TW` lower-tail proxy range across the grid:

- minimum: `0.842105`
- maximum: `0.947368`

Interpretation:

The high `0050.TW`/`00631L.TW` lower-tail dependence finding is robust across
reasonable alpha/window settings. This strengthens the caution against adding
`00631L.TW` from this research line. However, the trend component does not show a
robust recent deterioration, so it does not justify a new live de-risking gate.

Decision unchanged:

- keep as shadow tail-dependence trend diagnostic only;
- do not change target weights;
- do not add `00631L.TW`;
- do not open `00632R.TW`;
- keep `Golden1_0531` unchanged.

## Stress Window Split Addendum

User asked to continue after the robustness sweep. A stress-window split was
added to check whether the tail-dependence diagnosis is stable across distinct
market environments rather than only in the latest rolling window.

Implemented:

- `scripts/evaluate/evaluate_group_a_plus_2604_11335_tail_dependence_window_split.py`
- `report/group_a_plus/latest/2604_11335_tail_dependence_window_split.json`
- `report/group_a_plus/latest/2604_11335_tail_dependence_window_split.md`

Windows:

- `full_available`
- `trade_war_2018`
- `covid_2020`
- `rate_hike_2022`
- `recent_2024_2026`

Result:

- valid windows: `5`
- high `00631L.TW` windows: `5/5`
- high `00679B.TWO` windows: `0/5`
- positive `00632R.TW` lower-lower co-exceedance windows: `0/5`

Window-level lower-tail proxy versus `0050.TW`:

- `full_available`: `00631L.TW = 0.843602`, `00632R.TW = 0.000000`,
  `00679B.TWO = 0.137441`
- `trade_war_2018`: `00631L.TW = 0.880000`, `00632R.TW = 0.000000`,
  `00679B.TWO = 0.120000`
- `covid_2020`: `00631L.TW = 0.720000`, `00632R.TW = 0.000000`,
  `00679B.TWO = 0.160000`
- `rate_hike_2022`: `00631L.TW = 0.800000`, `00632R.TW = 0.000000`,
  `00679B.TWO = 0.080000`
- `recent_2024_2026`: `00631L.TW = 0.861538`, `00632R.TW = 0.000000`,
  `00679B.TWO = 0.076923`

Interpretation:

The high `0050.TW`/`00631L.TW` lower-tail dependence warning is stable across all
stress windows tested. `00679B.TWO` is not a high lower-tail co-crash asset in
this metric, but its low co-exceedance alone is not enough to justify a live bond
allocation rule. `00632R.TW` has zero lower-lower co-exceedance by construction
of inverse behavior, but this does not override inverse-ETF governance or
realized-loss constraints.

Decision unchanged:

- keep as shadow diagnostic only;
- do not add `00631L.TW`;
- do not open `00632R.TW`;
- do not add `00679B.TWO` from this paper alone;
- no target-weight change.

## 00679B Tail-Break Alert Addendum

User asked whether the paper can do more than the main tail-dependence review.
The useful remaining extension is a shadow alert for whether `00679B.TWO` loses
its low lower-tail co-exceedance profile versus `0050.TW`.

Implemented:

- `scripts/evaluate/evaluate_group_a_plus_2604_11335_00679b_tail_break_alert.py`
- `report/group_a_plus/latest/2604_11335_00679b_tail_break_alert.json`
- `report/group_a_plus/latest/2604_11335_00679b_tail_break_alert.md`

Rule:

- compute rolling `P(00679B.TWO in lower tail | 0050.TW in lower tail)`;
- compare latest and recent mean against the older baseline mean;
- alert only when the proxy is both elevated and meaningfully above baseline.

Real-data result as of `2026-08-28`:

- observations: `1852`
- latest lower-tail proxy: `0.076923`
- baseline mean: `0.115920`
- recent mean: `0.128816`
- latest minus baseline: `-0.038997`
- recent minus baseline: `0.012896`
- historical max: `0.269231`
- break alert: `false`

Interpretation:

`00679B.TWO` has not shown a tail-dependence break versus `0050.TW` under this
diagnostic. This means the paper does not require downgrading bond-hedge
confidence today. It still does not justify adding `00679B.TWO` from this paper
alone, because low co-exceedance is a hedge-quality diagnostic rather than an
allocation rule.

Decision unchanged:

- keep as shadow diagnostic only;
- no `00679B.TWO` add from this paper alone;
- no `00631L.TW` add;
- no `00632R.TW` open;
- no target-weight change;
- keep `Golden1_0531` unchanged.

## Final Closeout

User confirmed the `2604.11335` paper work is complete and asked to leave a
detailed record.

Completed experiments:

- main `2604.11335` tail-dependence trend review;
- alpha/window robustness sweep;
- stress-window split;
- `00679B.TWO` tail-dependence break alert.

Validation completed:

- Python syntax check passed for all `2604.11335` evaluator scripts;
- pytest passed for
  `tests/test_build_group_a_plus_2604_11335_tail_dependence_trend_review.py`;
- final test count: `8 passed`.

Final implementation status:

- all outputs are research/shadow diagnostics;
- no live runner change;
- no execution-plan change;
- no target-weight change;
- no `00631L.TW` add;
- no `00632R.TW` open;
- no standalone `00679B.TWO` add rule;
- `Golden1_0531` remains unchanged.

Final decision:

`2604.11335` is useful for monitoring tail-dependence stability and detecting a
possible future `00679B.TWO` hedge-quality break. It is not strong enough to
become a live allocation, leverage, inverse, or rebalance rule by itself.

## 2026-08-31 Recheck After `golden2_0830`

User asked again whether `C:\Users\isaac\Downloads\2604.11335.pdf` has benefits
that can be imported into GroupA+ latest strategy.

Context changed since the original closeout:

- `golden2_0830` was created on `2026-08-30` as a frozen copy of the current
  GroupA+ latest strategy state.
- Latest available market data for this review remains `2026-08-28`.

Re-ran all four `2604.11335` evaluators:

```bash
.venv/bin/python scripts/evaluate/build_group_a_plus_2604_11335_tail_dependence_trend_review.py
.venv/bin/python scripts/evaluate/sweep_group_a_plus_2604_11335_tail_dependence_trend_robustness.py
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_2604_11335_tail_dependence_window_split.py
.venv/bin/python scripts/evaluate/evaluate_group_a_plus_2604_11335_00679b_tail_break_alert.py
.venv/bin/python -m pytest tests/test_build_group_a_plus_2604_11335_tail_dependence_trend_review.py
```

Validation:

- pytest result: `8 passed`.
- Main review status: `available_for_shadow_monitoring`.
- Robustness sweep: `9/9` valid runs show high `00631L.TW` lower-tail
  dependence; `0/9` show robust recent-rising `00631L.TW`.
- Window split: `5/5` valid windows show high `00631L.TW` lower-tail dependence;
  `0/5` windows show high `00679B.TWO`; `0/5` windows show positive
  `00632R.TW` lower-lower co-exceedance.
- `00679B.TWO` break alert: inactive; latest proxy `0.076923`, baseline mean
  `0.115920`, recent mean `0.128816`.

Decision remains unchanged:

- do not import the full nonparametric tail-copula test into production;
- keep the implemented tools as shadow diagnostics only;
- do not change GroupA+ latest target weights;
- do not alter `golden2_0830`;
- do not alter `golden1_0531`;
- do not add `00631L.TW` from this paper;
- do not open or increase `00632R.TW` from this paper;
- do not add `00679B.TWO` from this paper alone.

Practical use after `golden2_0830`: retain this paper only as a monitoring lens.
It can warn that a leveraged leg has persistent lower-tail co-crash exposure or
that a bond hedge has lost low-tail-diversification behavior. It is not a sizing
or trading rule.

## Final Archive Note

User asked: "該導入都導入了?" and then confirmed: "OK,留下詳細記錄."

Final answer:

- Yes, all importable pieces from `2604.11335` have been imported.
- The imported pieces are diagnostic-only, not production allocation rules.
- Nothing from this paper should be used to change `golden1_0531`,
  `golden2_0830`, or the current latest strategy weights.

Imported and kept:

- rolling lower-tail co-exceedance trend monitor;
- `0050.TW`/`00631L.TW` lower-tail co-crash warning;
- alpha/window robustness sweep;
- stress-window split across full sample, 2018, 2020, 2022, and recent
  2024-2026 windows;
- `00679B.TWO` hedge-quality tail-break alert.

Explicitly not imported:

- no full nonparametric tail-copula production gate;
- no target-weight change;
- no automatic rebalance trigger;
- no `00631L.TW` add or leverage unlock;
- no `00632R.TW` open/increase rule;
- no standalone `00679B.TWO` add rule;
- no change to `golden1_0531`;
- no change to frozen `golden2_0830`.

Latest confirmed results:

- market data date: `2026-08-28`;
- main review status: `available_for_shadow_monitoring`;
- `00631L.TW` latest lower-tail proxy versus `0050.TW`: `0.923077`;
- robustness: `9/9` valid parameter runs flagged high `00631L.TW` lower-tail
  dependence;
- recent-rising `00631L.TW`: `0/9`;
- stress-window split: `5/5` windows flagged high `00631L.TW` lower-tail
  dependence;
- high `00679B.TWO` windows: `0/5`;
- positive `00632R.TW` lower-lower co-exceedance windows: `0/5`;
- `00679B.TWO` tail-break alert: `false`;
- pytest: `8 passed`.

Archived decision:

`2604.11335` is closed for GroupA+ production import. Keep the diagnostics as
monitoring tools and do not rerun or reopen this paper by default unless new
Taiwan ETF evidence appears or the user explicitly asks for a new review.
