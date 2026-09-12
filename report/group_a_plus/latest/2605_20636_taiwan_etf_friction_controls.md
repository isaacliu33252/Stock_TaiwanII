# 2605.20636 Taiwan ETF Friction Controls

Generated: `2026-08-30T08:39:57`
Status: `blocked_for_live_promotion`
Endpoint: `0050_00631l_cash`

## Decision

- Friction controls repair signal: `False`
- Promote to live: `False`
- Production effect: `none`

## Combo Summary

| Combo | Triple-pass windows | Avg final value delta | Avg Sharpe delta | Min MaxDD delta | Avg turnover delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| band0.005_freq1 | 0/4 | -115341.54 | -0.347761 | -0.055629 | 10.632059 |
| band0.005_freq5 | 0/4 | -14796.95 | -0.266774 | -0.035816 | 3.178408 |
| band0.005_freq10 | 0/4 | -86363.71 | -0.276140 | -0.038855 | 1.069493 |
| band0.02_freq1 | 0/4 | -116437.02 | -0.334431 | -0.054129 | 8.356855 |
| band0.02_freq5 | 0/4 | 8839.83 | -0.255383 | -0.035696 | 2.876094 |
| band0.02_freq10 | 0/4 | -60563.22 | -0.266570 | -0.038899 | 1.044592 |
| band0.05_freq1 | 0/4 | -136840.40 | -0.302276 | -0.046781 | 6.037060 |
| band0.05_freq5 | 0/4 | -2130.89 | -0.264170 | -0.028652 | 1.892100 |
| band0.05_freq10 | 0/4 | -47120.24 | -0.248607 | -0.033016 | 0.400549 |
| band0.1_freq1 | 0/4 | -75696.09 | -0.274008 | -0.047841 | 6.084604 |
| band0.1_freq5 | 0/4 | 81633.59 | -0.206229 | -0.044307 | 1.352798 |
| band0.1_freq10 | 0/4 | 42595.67 | -0.217052 | -0.033007 | 0.035784 |

Best combo: `band0.1_freq5`

## Best Combo Window Rows

| Window | Final value delta | Annual return delta | Sharpe delta | MaxDD delta | Turnover delta | Triple pass |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| full_available | -53740.93 | -0.001343 | -0.405702 | -0.044307 | 0.444908 | `False` |
| covid_2020 | -22456.32 | -0.022546 | -0.005760 | 0.013733 | 0.151103 | `False` |
| rate_hike_2022 | -14757.71 | -0.014912 | -0.154759 | -0.006605 | 0.730367 | `False` |
| recent_2024_2026 | 417489.32 | 0.071183 | -0.258695 | 0.034425 | 4.084816 | `False` |

## Failure Diagnosis

- Positive final-value windows: `['recent_2024_2026']`
- Negative final-value windows: `['full_available', 'covid_2020', 'rate_hike_2022']`
- Negative Sharpe windows: `['full_available', 'covid_2020', 'rate_hike_2022', 'recent_2024_2026']`
- Worse drawdown windows: `['full_available', 'rate_hike_2022']`
- Primary reason: Best combo's average final-value gain is concentrated in the recent 2024-2026 window; full-history/COVID/2022 final-value deltas remain negative and Sharpe deltas are negative in every best-combo window.

