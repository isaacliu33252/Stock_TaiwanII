# Golden1_0531 Factor Attribution (research diagnostic)

- Source paper: `arXiv:2607.18001 AlphaZeroBeta (methodology adapted, not replicated)`
- Curve: `results/group_a_plus_switch_policy_compare_golden1_20250102_20260703.json_curve.csv` column `golden1_0531_1m`
- Sample: 360 trading days, 2025-01-03 to 2026-07-02
- Caveat: Single ~1.5-year, broadly bullish window; descriptive attribution, not an OOS predictive test.

## Strategy Stats (full sample)
- Annualized return: `77.80%`
- Annualized volatility: `28.44%`
- Simple correlation vs 0050 (MKT): `0.991`
- Simple correlation vs 00631L excess-of-2x (LETF_XS): `-0.053`

## Beta-Only Model: strategy_return ~ const + MKT + LETF_XS
- n = 360, R² = `0.989`
- alpha (annualized): `1.26%`
- MKT: 1.0516*** (t=32.51, p=0.000)
- LETF_XS: 0.1974*** (t=6.32, p=0.000)

## Full Model: + TSMOM + REV1
- n = 360, R² = `0.993`
- alpha (annualized): `-0.93%`
- MKT: 1.0457*** (t=55.08, p=0.000)
- LETF_XS: 0.2176*** (t=12.89, p=0.000)
- TSMOM: 0.0706*** (t=4.06, p=0.000)
- REV1: 0.0026 (t=0.57, p=0.570)

## Interpretation
- Beta-only model explains `99.6%` of the variance captured by the full model; the remainder (momentum + reversal + noise) adds `0.004` incremental R².
- The full-model alpha (annualized -0.93%) is statistically indistinguishable from zero (p=0.594): once MKT and LETF_XS exposure are controlled for, there is no reliable evidence of residual timing alpha in this sample -- the strategy's headline return is explained almost entirely by beta exposure, not by genuine market-neutral skill.
*** p<0.01, ** p<0.05, * p<0.10. HAC (Newey-West) standard errors, maxlags=5, matching the precedent in `scripts/evaluate/letf_close_auction_overshoot_reversal_test.py`.

