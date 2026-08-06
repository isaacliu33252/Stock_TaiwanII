# NCF Panel Refresh Recommendation

- Recommendation: `keep_current_pin`
- Reason: `candidate_not_more_accurate_on_resolved_outcomes`
- Baseline panel: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/results/ncf_00631l_panel_latest_20260716.csv`
- Candidate panel: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/results/ncf_00631l_panel_latest_20260806.csv`

## Outcome-Aware Columns

- `h20_prob_up`: verdict `candidate_not_more_accurate`, candidate_favorable `189/365` rate `0.5178`, risk_delta `0.19439771629200908`
- `prob_fwd_mdd_gt5_h20`: verdict `candidate_not_more_accurate`, candidate_favorable `174/351` rate `0.4957`, risk_delta `0.171089209157912`
- `prob_fwd_gain_gt5_h20`: verdict `candidate_not_more_accurate`, candidate_favorable `170/351` rate `0.4843`, risk_delta `0.08291365214662683`

## Decision Boundary

- Auto pin update allowed: `False`
- Target weight change allowed: `False`
- Creates orders: `False`
