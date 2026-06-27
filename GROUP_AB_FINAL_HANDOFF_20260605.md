# Group A+B Final Handoff 2026-06-05

Date: 2026-06-05
Status: handoff / operational record

## Current Recommendation

The current best risk-adjusted production candidate for combined Group A + Group B is:

`dynamic_lb126_band012_base060_hold10_no2884_optimized`

Stack:

- Group A: `Golden1_0531_tdcc_destination_primary + 00632R max-hold-10 overlay`
- Group B: latest no-2884 version
- A/B governance:
  - dynamic lookback: `126`
  - dynamic band: `0.12`
  - base Group A weight: `0.60`
  - Group A weight range: `0.55` to `0.70`
  - min transfer notional: `50,000`
  - cooldown: `20`
  - stress gate: disabled for production candidate

## Main Backtest Result

Window: 2024-01-02 to 2026-06-04

Formal governed backtest result:

- Final value: `5,880,921.34`
- Annual return: `56.1490%`
- Sharpe: `2.5956`
- Sortino: `3.3078`
- Calmar: `2.9659`
- Max drawdown: `-18.9317%`
- Events: `7`
- Estimated cost: `2,069.06`

Main outputs:

- `results/group_ab_meta_governed_hold10_no2884_20240102_20260604.json`
- `results/group_ab_meta_governed_hold10_no2884_20240102_20260604.csv`
- `results/group_ab_meta_governed_hold10_no2884_20240102_20260604_curve.csv`
- `results/group_ab_meta_governed_hold10_no2884_20240102_20260604_trade_log.csv`
- `results/group_ab_meta_governed_hold10_no2884_20240102_20260604_diagnostic.csv`
- `results/group_ab_meta_governed_hold10_no2884_20240102_20260604.html`

## Comparison With Previous Best

Previous practical best:

`dynamic_lb126_band008_hold10_no2884_no_stress`

Previous metrics:

- Final value: `5,885,721.88`
- Sharpe: `2.5780`
- Max drawdown: `-19.0103%`
- Events: `7`
- Estimated cost: `1,865.83`

Interpretation:

- Previous version has slightly higher final value by about `4,801`.
- Optimized version has better Sharpe and lower drawdown.
- Use optimized version as the best risk-adjusted candidate.
- Keep previous version as a secondary benchmark because its absolute final value is slightly higher.

## Highest Return Variant

Best final-value variant from parameter optimization:

`opt_aggr_lb126_b0.080_base0.700_lo0.60_hi0.85_min50000_cd20_nostress`

Metrics:

- Final value: `6,192,321.28`
- Sharpe: `2.5148`
- Sortino: `3.2662`
- Max drawdown: `-19.5512%`

Interpretation:

- This is an aggressive profile, not the main recommendation.
- It is close to the `-20%` drawdown floor and has lower Sharpe.
- Keep as an optional aggressive profile only.

## Group A Standalone

Current practical Group A candidate:

`Golden1_0531_tdcc_destination_primary + 00632R max-hold-10 overlay`

Files:

- Config: `group_a_tdcc_improved_config_destination_primary.json`
- Overlay config: `group_a_00632r_hold10_overlay_config.json`
- Live runner: `run_group_a_tdcc_improved_signal.py`

Backtest 2024-01-02 to 2026-06-04:

- Final value: `3,323,211`
- Sharpe: `2.2416`
- Max drawdown: `-26.43%`

Important decision:

- Do not disable `00632R` as the main recommendation.
- `disable_00632R -> 0050` had higher 2024-2026 return, but worsened 2008 proxy stress.
- Keep `00632R` with max-hold-10 overlay as the practical candidate.

Latest live signal smoke output:

- `results/group_a_tdcc_improved_signal_20260605_174434.json`
- `results/group_a_tdcc_improved_signal_20260605_174434.csv`
- `results/group_a_tdcc_improved_signal_20260605_174434_trade_log.csv`

## Group B Standalone

Current Group B candidate:

`latest no-2884`

Backtest output:

- `results/group_b_latest_no2884_backtest_20240101_20260605.json`
- `results/group_b_latest_no2884_backtest_20240101_20260605.csv`
- `results/group_b_latest_no2884_backtest_20240101_20260605_curve.csv`

Metrics:

- Final value: `2,198,686.74`
- Sharpe: `2.4840`
- Max drawdown: `-13.6945%`

## FinRL-Meta Imports

Imported into this project:

- Last target weight / turnover-aware governance
- Trade cost log
- Cooldown and min transfer threshold
- Sortino, Calmar, rolling Sharpe
- Validation selector scaffold
- Epoch OOS scaffold
- Dataclass parameter configs
- HTML report generator
- Taiwan turbulence shadow gate
- Benchmark-relative shadow gate
- Square-root impact reporting
- Promotion gate checks

Main files:

- `finrl_meta_strategy_governance.py`
- `backtest_group_ab_meta_governed.py`
- `backtest_group_ab_shadow_risk_tools.py`
- `generate_strategy_html_report.py`
- `optimize_group_ab_governance.py`

Not imported:

- Full FinRL-Meta DataProcessor stack
- Yahoo/NYSE-oriented cleaner
- Alpaca/crypto/futures paths
- Full DRL wrapper

Reason: this project already has Taiwan ETF data refresh, local caches, DuckDB, and existing strategy runners.

## Shadow Risk Tools

Shadow risk outputs:

- `results/group_ab_shadow_risk_tools_20240102_20260604.json`
- `results/group_ab_shadow_risk_tools_20240102_20260604.csv`
- `results/group_ab_shadow_risk_tools_20240102_20260604_curve.csv`
- `results/group_ab_shadow_risk_tools_20240102_20260604_risk_diagnostic.csv`
- `results/group_ab_shadow_risk_tools_20240102_20260604_impact_log.csv`

Best defensive shadow:

`turbulence_cap55_shadow`

Metrics:

- Final value: `5,806,863.30`
- Sharpe: `2.6047`
- Max drawdown: `-18.8664%`
- Events: `16`
- Cost: `14,239`

Interpretation:

- Better Sharpe and slightly lower MDD than the old base.
- Lower final value and much higher costs.
- Keep as monitored shadow, not production default.

## Parameter Optimization

Optimization script:

`optimize_group_ab_governance.py`

Optimization outputs:

- `results/group_ab_governance_optimization_20240102_20260604.json`
- `results/group_ab_governance_optimization_20240102_20260604.csv`
- `results/group_ab_governance_optimization_20240102_20260604_curve.csv`

Research note:

- `GROUP_AB_PARAMETER_OPTIMIZATION_20260605.md`

Candidate count:

- `768`

Best balanced candidate:

`opt_lb126_b0.120_base0.600_lo0.55_hi0.70_min50000_cd10_nostress`

This was adopted into the formal governed backtest as:

`dynamic_lb126_band012_base060_hold10_no2884_optimized`

## Commands To Reproduce

Compile check:

```bash
python3 -m py_compile finrl_meta_strategy_governance.py backtest_group_ab_meta_governed.py backtest_group_ab_shadow_risk_tools.py generate_strategy_html_report.py optimize_group_ab_governance.py run_group_a_tdcc_improved_signal.py
```

Run parameter optimization:

```bash
python3 optimize_group_ab_governance.py
```

Run formal Group A+B governed backtest:

```bash
python3 backtest_group_ab_meta_governed.py
```

Generate HTML report:

```bash
python3 generate_strategy_html_report.py --summary-json results/group_ab_meta_governed_hold10_no2884_20240102_20260604.json
```

Run shadow risk tools:

```bash
python3 backtest_group_ab_shadow_risk_tools.py
```

Run Group A live signal smoke:

```bash
python3 run_group_a_tdcc_improved_signal.py \
  --config group_a_tdcc_improved_config_destination_primary.json \
  --base-signal-json results/signal_group_a_20260604_184447.json \
  --as-of-date 2026-06-05
```

## Promotion Rules

Use the optimized version as current best only if:

- Sharpe stays above the previous practical best or remains close with lower MDD.
- Max drawdown remains better than `-20%` in 2024-2026.
- Group A 2008 proxy stress does not worsen from removing the `00632R` hedge.
- Trade count and cost remain acceptable.
- Shadow gates are reviewed before being promoted to production.

## Next Work

Recommended next checks:

1. Run the same A/B governance optimization on earlier stress/proxy windows if curves are available.
2. Add a compact production config file for `dynamic_lb126_band012_base060_hold10_no2884_optimized`.
3. Keep `turbulence_cap55_shadow` in daily diagnostics only.
4. Re-run after each data refresh and compare against both:
   - `dynamic_lb126_band012_base060_hold10_no2884_optimized`
   - `dynamic_lb126_band008_hold10_no2884_no_stress`

