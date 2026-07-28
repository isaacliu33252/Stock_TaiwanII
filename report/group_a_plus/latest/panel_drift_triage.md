# GroupA+ Panel Drift Triage

- Status: `blocked`
- Exceeded columns: `['h20_prob_up']`
- Trigger-critical exceeded: `['h20_prob_up']`
- Source hypotheses: `['model_set_changed', 'candidate_external_source_stale']`

## Columns

- `h20_prob_up` tier `trigger_critical` delta `0.15955034020305625` limit `0.15` date `2026-05-11` direction `negative`

## Next Checks

- compare baseline/candidate horizon model sets and best-model selections
- rerun or isolate external-feature and no-external panel sensitivity

## Decision Boundary

- Creates orders: `False`
- Target weight change allowed: `False`
- Auto rebalance allowed: `False`
- Golden1_0531 unchanged: `True`
