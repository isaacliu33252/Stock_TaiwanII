# GroupA+ NCF Panel Drift Audit - 2026-07-06

## Summary

Built a read-only audit tool for NCF panel drift:

- Script: `scripts/evaluate/evaluate_ncf_panel_drift.py`
- Test: `tests/test_evaluate_ncf_panel_drift.py`
- Audit output:
  - `results/ncf_00631l_panel_drift_20260630_vs_20260703.json`
  - `results/ncf_00631l_panel_drift_20260630_vs_20260703.csv`

No model training, live allocation, runner behavior, or strategy pointer was changed.

## What Was Measured

Compared:

- Baseline panel: `results/ncf_00631l_panel_latest_20260630.csv`
- Candidate panel: `results/ncf_00631l_panel_latest_20260703.csv`

Overlapping dates: 2025-01-02 through 2026-06-30, 359 rows.

Audited columns:

- `prob_up_h1`
- `prob_up_h5`
- `prob_up_h20`
- `ensemble_prob_up`
- `h20_prob_up`
- `confidence`
- `prob_fwd_mdd_gt5_h20`
- `prob_fwd_gain_gt5_h20`
- `tail_reward_risk_score_h20`

## Key Findings

The drift is material, not just a one-day issue.

Maximum absolute drift by column:

| Column | Max abs drift | Date |
| --- | ---: | --- |
| `prob_up_h1` | 0.476220 | 2025-03-10 |
| `prob_up_h5` | 0.412306 | 2025-06-03 |
| `prob_up_h20` / `h20_prob_up` | 0.298098 | 2025-05-26 |
| `ensemble_prob_up` | 0.302322 | 2025-04-15 |
| `confidence` | 0.464781 | 2025-04-11 |
| `prob_fwd_mdd_gt5_h20` | 0.341588 | 2025-08-18 |
| `prob_fwd_gain_gt5_h20` | 0.161184 | 2025-01-08 |
| `tail_reward_risk_score_h20` | 0.442679 | 2025-05-16 |

The original handoff's focus date, 2025-10-29, also drifted materially:

| Field | 2026-06-30 panel | 2026-07-03 panel | Delta |
| --- | ---: | ---: | ---: |
| `prob_up_h1` | 0.297217 | 0.476206 | +0.178989 |
| `prob_up_h5` | 0.194103 | 0.300653 | +0.106550 |
| `prob_up_h20` | 0.189917 | 0.159831 | -0.030086 |
| `ensemble_prob_up` | 0.219328 | 0.282459 | +0.063131 |
| `confidence` | 0.561343 | 0.435081 | -0.126262 |
| `tail_reward_risk_score_h20` | -0.684059 | -0.557739 | +0.126320 |

## Interpretation

This confirms the NCF panel drift problem is broad enough to affect trigger-based research:

- BayesOpt trigger thresholds can optimize against unstable historical probabilities.
- A21.18 trigger dates can appear or disappear after a panel refresh.
- Research that compares old and new NCF panels must report drift before treating trigger changes as real signal.

## Decision

Do not change production ensemble weights yet.

The safe next step is to add this drift audit to any NCF-trigger promotion workflow. A production change to rolling/expanding per-model weights should be handled as a separate architecture change, followed by re-running A21.18 parameter sweeps and promotion gates.

## Verification

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_ncf_panel_drift.py
.venv/bin/python -m pytest -q tests/test_evaluate_ncf_panel_drift.py
```

Result: 1 passed.

