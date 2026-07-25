# GroupA+ Panel Drift Triage

- Status: `blocked`
- Exceeded columns: `['ensemble_prob_up', 'h20_prob_up', 'confidence']`
- Trigger-critical exceeded: `['h20_prob_up', 'confidence']`
- Source hypotheses: `['model_set_changed', 'panel_method_schema_changed', 'external_feature_sensitivity_visible', 'horizon_ensemble_or_confidence_blend_check_needed']`

## Columns

- `ensemble_prob_up` tier `diagnostic` delta `0.24570435280144232` limit `0.15` date `2025-05-09` direction `positive`
- `h20_prob_up` tier `trigger_critical` delta `0.26368676066031893` limit `0.15` date `2025-09-18` direction `negative`
- `confidence` tier `trigger_critical` delta `0.49140870560288463` limit `0.28` date `2025-05-09` direction `positive`

## Next Checks

- compare baseline/candidate horizon model sets and best-model selections
- rerun or isolate external-feature and no-external panel sensitivity
- inspect horizon ensemble weights/confidence blend around max-drift dates

## Decision Boundary

- Creates orders: `False`
- Target weight change allowed: `False`
- Auto rebalance allowed: `False`
- Golden1_0531 unchanged: `True`
