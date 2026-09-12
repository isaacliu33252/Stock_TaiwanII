# Leveraged ETF Timing Anomaly Review

- Generated: `2026-08-21T14:58:59`
- Source: `arXiv:2604.27287v1 A Levered ETF Anomaly Explained`
- Policy: `research_only_no_weight_change`
- Decision: `do_not_promote_keep_shadow`
- Latest strategy changed: `False`

## Findings

### 00631L.TW

- Average effective leverage: `1.671` vs target `2.0`
- Ratio-return covariance: `9.16%` annualized
- Arithmetic gap vs ideal constant leverage: `4.11%`
- Volatility drag estimate: `-10.48%`
- Full-sample warnings: `average_effective_leverage_away_from_target, large_volatility_drag`
- Latest rolling warnings: `negative_ratio_return_covariance, large_volatility_drag`
- Decision: `shadow_warning_for_manual_00631l_or_00632r_review`

### 00632R.TW

- Average effective leverage: `-0.736` vs target `-1.0`
- Ratio-return covariance: `-8.47%` annualized
- Arithmetic gap vs ideal constant leverage: `49.43%`
- Volatility drag estimate: `-103.46%`
- Full-sample warnings: `negative_ratio_return_covariance, average_effective_leverage_away_from_target, large_volatility_drag`
- Latest rolling warnings: `none`
- Decision: `shadow_warning_for_manual_00631l_or_00632r_review`

## GroupA+ Import Decision

The useful import is a shadow diagnostic only: track realized effective leverage, volatility drag, and the covariance between effective leverage and 0050 returns before considering 00631L/00632R exposure changes.

Do not wire this directly into latest strategy, golden1_0531, daily signals, execution plans, or orders without a separate multi-window promotion backtest.
