# GroupA+ Defensive Cash Floor Signed Promotion Review

- status: `manual_signature_pending`
- as_of: `2026-08-06`
- candidate: `cash55_risk7_tail1`
- rule: Inside group_a_plus_defensive only, raise cash floor to 55% when total_risk_score >= 7 or tail_risk_score >= 1.
- signed_review_ready: `True`
- manual_signature_valid: `False`
- target_weight_change_allowed: `False`
- auto_rebalance_allowed: `False`

## Evidence

- sweep total_return_delta: `+5.2029%`
- sweep max_drawdown_delta: `+2.8792%`
- sweep worst_day_delta: `+0.9545%`
- changed_days: `27`
- window validation: `5/5` changed windows passed
- fold ablation: `4/4` changed folds passed
- same-family train reselection: `4/4`

## Limitations

- Only 27 changed days in the 607-row 2024-01-02 to 2026-08-05 frame.
- 2024 has zero trigger days, so it is evidence-neutral rather than validated.
- The rule was validated as a shadow replay, not as broker-executed live trading.
- This review does not validate tax, liquidity, broker fill, or intraday slippage effects.
- The rule changes defensive cash posture, so it can lag if high-risk defensive days rebound immediately.

## Decision

This package is ready for manual signature review, but it does not itself authorize live trading, target-weight changes, or auto rebalance.
