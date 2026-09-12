# A21.18 PPO Seed Averaging Shadow

- Source: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/results/a2118_ppo_seed_averaging_robustness_2607_00475_1787554541.json`
- Shadow gate: `pass`
- Shadow queue: `candidate_for_forward_shadow_monitoring`
- Production: `do_not_promote`
- Preferred ensemble: `42+43+44`
- Full Sharpe / MDD: `1.9644` / `-0.2883`

## Checks

- `ensemble_sharpe_above_individual_mean`: `True`
- `ensemble_mdd_better_than_individual_mean`: `True`
- `ensemble_not_far_below_best_sharpe`: `True`
- `ensemble_avoids_bad_seed_mdd_tail`: `True`
- `subperiods_positive_sharpe`: `True`

## Note

This artifact is shadow-only. It summarizes existing backtests and does not generate live actions.
