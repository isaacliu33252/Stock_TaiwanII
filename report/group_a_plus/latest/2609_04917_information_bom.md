# 2609.04917 Information Bill of Materials

- status: warning
- artifact_count: 13
- missing_artifacts: none

| artifact | status | warnings |
| --- | --- | --- |
| live_signal | available | none |
| execution_plan | available | none |
| ops_health | available | none |
| signal_alignment | warning | event_or_data_date_missing |
| watchlist_news | warning | model_or_policy_version_missing |
| market_aligned_sentiment | warning | availability_or_generation_time_missing, model_or_policy_version_missing |
| profit_deployment_readiness | available | none |
| ncf_0050_signal | available | none |
| ncf_00631l_signal | available | none |
| ncf_00632r_signal | available | none |
| ncf_0050_panel | warning | availability_time_column_missing, model_version_column_missing |
| ncf_00631l_panel | warning | availability_time_column_missing, model_version_column_missing |
| ncf_00632r_panel | warning | availability_time_column_missing, model_version_column_missing |

## Recommended Next Actions

- add availability_time or available_at to NCF and sentiment panels
- record model_path or model_version for every predictive artifact
- treat generated_at as artifact creation time, not as data availability time
- link each promoted candidate to this BOM before human promotion review
