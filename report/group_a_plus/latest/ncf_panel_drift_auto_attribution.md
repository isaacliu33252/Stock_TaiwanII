# NCF Panel Drift Auto Attribution

- Status: `blocked`
- Primary attribution: `data_or_artifact_freshness`
- Policy: `diagnostic_only_no_model_change_no_weight_change`

## Attributions

- `panel_value_drift` severity `blocked`
  - diagnosis_status=blocked
  - exceeded_columns=['h20_prob_up']
  - trigger_critical_exceeded=['h20_prob_up']
  - overlap_rows=371
  - max_column_delta=0.2704866995193387
  - next: inspect the columns and dates with largest deltas before changing promotion gates
- `data_or_artifact_freshness` severity `blocked`
  - data_freshness_status=blocked
  - blockers=['latest_strategy_explain_target_weight_window_lags_live_signal']
  - warnings=['latest_strategy_explain_snapshot_has_warnings', 'ohlcv_freshness_target_date_mismatch']
  - live_signal_actual_data_date=2026-09-07
  - live_signal_business_stale_days=1
  - ohlcv_target_date=2026-09-04
  - latest_strategy_target_weight_window_end=2026-08-07
  - next: refresh upstream data and rebuild live signal, panel manifest, drift audit, and latest strategy explain snapshot
- `candidate_source_staleness` severity `blocked`
  - action=refresh_stale_candidate_sources
  - stale_sources=['external_market_ohlcv']
  - candidate NCF run used degraded or stale sources
  - next: refresh stale candidate sources, then rebuild same-day NCF panels and drift diagnosis
- `external_feature_sensitivity` severity `blocked`
  - action=quantify_external_feature_sensitivity
  - max_trigger_critical_sensitivity=0.6372621107070484
  - governance_status=blocked_observation_required
  - external-feature sensitivity exceeds trigger-critical drift tolerance
  - next: keep external/no-external paired audit running until same-method observations are stable
- `external_feature_governance_block` severity `blocked`
  - governance_status=blocked_observation_required
  - reason=external-feature sensitivity exceeds trigger-critical limits
  - resolution_allowed=False
  - next: do not reduce the external-feature blocker until the governance report allows resolution
- `panel_date_window_mismatch` severity `warning`
  - panel_date_ends=['2026-09-07', '2026-09-09']
  - next: rebuild lagging NCF panels so all instruments share the same latest panel date
- `model_set_or_retrain_change` severity `warning`
  - h1: removed=['tabnet'] added=[] val_auc 0.5975->0.5699
  - h5: removed=['tabnet'] added=[] val_auc 0.6812->0.6218
  - h20: removed=['tabnet'] added=[] val_auc 0.6879->0.6837
  - next: confirm whether the model roster change was an intentional retrain/promotion or an unpinned dependency drift

## Decision Boundary

- Creates orders: `False`
- Promotion allowed: `False`
- Training allowed: `False`
- Target weight change allowed: `False`
- Golden1_0531 unchanged: `True`
- Golden2_0830 unchanged: `True`
