# GIFT Signed Approval Manual Completion Guide

- Status: `ready_for_human_completion`
- As of: `2026-07-23`
- Template: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/report/group_a_plus/latest/llm_state_reward_human_exception_signed_approval_record_TEMPLATE.json`
- Formal signed record target: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/report/group_a_plus/latest/llm_state_reward_human_exception_signed_approval_record.json`
- Validator output: `/mnt/c/Users/isaac/Downloads/Stock_taiwan2-main/Stock_taiwan2-main/report/group_a_plus/latest/llm_state_reward_human_exception_signed_approval_validation.json`

## Current State

- Manual completion ready: `True`
- Signed record exists: `False`
- Signed record valid: `False`
- Human exception approved: `False`
- Broker actionable latest strategy: `True`
- Deployment status: `manual_review_required`

## Fields A Human May Fill

- `reviewer`
- `reviewer_role`
- `approved_at`
- `expires_at`
- `approved_actions.allow_non_ppo_offline_shadow_training_queue_review` may be set to `true` only for non-PPO offline shadow queue review.

## Acknowledgements Required True

- `00631l_and_00632r_remain_excluded`
- `golden1_0531_unchanged`
- `no_live_action_no_target_weight_no_auto_rebalance`
- `non_ppo_offline_shadow_review_only`
- `research_shadow_remains_blocked_for_live_allocation`
- `training_runner_must_preserve_no_action_outputs`

## Must Remain False

- `approved_actions.allow_00631l_add`
- `approved_actions.allow_00632r_open`
- `approved_actions.allow_auto_rebalance`
- `approved_actions.allow_live_signal_output`
- `approved_actions.allow_live_strategy_change`
- `approved_actions.allow_model_training_command`
- `approved_actions.allow_ppo_training`
- `approved_actions.allow_target_weight_output`

## Hard Safety Notes

- This guide does not create or approve the formal signed record.
- `golden1_0531` must remain unchanged.
- `00631L.TW` and `00632R.TW` remain excluded from the GIFT approval scope.
- Training, PPO, live signal output, target weight output, auto rebalance, and live strategy change remain disallowed.
