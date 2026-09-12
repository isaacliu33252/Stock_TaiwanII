# 2511.00390 Dynamic vs Fixed Lag Diagnostic

- Status: `diagnostic_available`

| pair | windows | share lag=1 best | mean|corr| best-lag | mean|corr| fixed lag=1 | gap |
|---|---:|---:|---:|---:|---:|
| QQQ_vs_0050.TW | 1978 | 0.9277 | 0.4616 | 0.4569 | 0.0048 |
| QQQ_vs_2330.TW | 1977 | 0.9697 | 0.4373 | 0.4365 | 0.0008 |
| SOXX_vs_0050.TW | 1978 | 0.9565 | 0.4842 | 0.4827 | 0.0015 |
| SOXX_vs_2330.TW | 1977 | 0.9929 | 0.4748 | 0.4745 | 0.0003 |
| TSM_vs_0050.TW | 1978 | 0.6577 | 0.4816 | 0.4519 | 0.0298 |
| TSM_vs_2330.TW | 1977 | 0.7714 | 0.5105 | 0.4946 | 0.0159 |

## Boundary

- Diagnostic only: rolling cross-correlation, not a trained model.
- Does not modify ncf_0050.py or any production feature.
