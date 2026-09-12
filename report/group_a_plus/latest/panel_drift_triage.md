# GroupA+ Panel Drift Triage

- Status: `blocked`
- Exceeded columns: `['h20_prob_up']`
- Trigger-critical exceeded: `['h20_prob_up']`
- Source hypotheses: `['candidate_external_source_stale']`

## Columns

- `h20_prob_up` tier `trigger_critical` delta `0.22270426444278837` limit `0.15` date `2026-03-11` direction `negative`

## Next Checks

- rerun or isolate external-feature and no-external panel sensitivity

## Decision Boundary

- Creates orders: `False`
- Target weight change allowed: `False`
- Auto rebalance allowed: `False`
- Golden1_0531 unchanged: `True`
