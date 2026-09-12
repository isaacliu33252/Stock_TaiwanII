# 2605.20636 Taiwan ETF Sensitivity

Generated: `2026-08-30T00:38:41`
Status: `blocked_for_live_promotion`

## Decision

- Taiwan ETF backtest useful: `True`
- Promote to live: `False`
- Production effect: `none`
- Do not change latest strategy target weights.

## Endpoint Summary

| Endpoint | Triple-pass windows | Avg final value delta | Avg Sharpe delta | Min MaxDD delta | Avg turnover delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0050_cash | 0/4 | -139164.78 | -0.364008 | -0.056854 | 25.859151 |
| 0050_00679b_cash | 0/4 | -176700.52 | -0.398113 | -0.043145 | 55.516191 |
| 0050_00631l_cash | 0/4 | -115341.54 | -0.347761 | -0.055629 | 10.632059 |

## Window Rows

| Window | Endpoint | Final value delta | Annual return delta | Sharpe delta | MaxDD delta | Turnover delta | Triple pass |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| full_available | 0050_cash | -577926.65 | -0.015190 | -0.439076 | -0.056854 | 63.162711 | `False` |
| full_available | 0050_00679b_cash | -607760.51 | -0.016022 | -0.440977 | -0.043145 | 140.028402 | `False` |
| full_available | 0050_00631l_cash | -536162.59 | -0.014034 | -0.438269 | -0.055629 | 24.130456 | `False` |
| covid_2020 | 0050_cash | -73079.30 | -0.073365 | -0.476503 | -0.006763 | 2.613706 | `False` |
| covid_2020 | 0050_00679b_cash | -45611.18 | -0.045791 | -0.188881 | 0.009383 | 6.544928 | `False` |
| covid_2020 | 0050_00631l_cash | -50641.20 | -0.050841 | -0.311542 | -0.005313 | 1.148414 | `False` |
| rate_hike_2022 | 0050_cash | -7659.80 | -0.007740 | -0.228440 | 0.002625 | 3.066107 | `False` |
| rate_hike_2022 | 0050_00679b_cash | -24926.33 | -0.025186 | -0.626074 | -0.014210 | 6.266154 | `False` |
| rate_hike_2022 | 0050_00631l_cash | -18810.37 | -0.019007 | -0.334707 | -0.008149 | 2.520313 | `False` |
| recent_2024_2026 | 0050_cash | 102006.62 | 0.017879 | -0.312012 | 0.040850 | 34.594081 | `False` |
| recent_2024_2026 | 0050_00679b_cash | -28504.05 | -0.005056 | -0.336520 | 0.054618 | 69.225281 | `False` |
| recent_2024_2026 | 0050_00631l_cash | 144247.99 | 0.025186 | -0.306525 | 0.038699 | 14.729053 | `False` |

