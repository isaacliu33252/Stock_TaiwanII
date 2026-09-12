# 2609.02014 Spectral 00679B Hedge Review

- Status: `research_only`
- Policy: `shadow_only_no_live_weight_change`
- Decision: promote_to_latest_strategy=`False`
- Spectral loss: `0.50*ES95 + 0.30*ES97.5 + 0.20*ES99 of daily losses`

## Interpretation

The paper's useful import is the objective, not the full deep-hedging machinery. GroupA++ does not trade a high-dimensional option book, so this review treats 00679B.TWO as a cash-funded hedge sleeve and scores it with a dynamic rolling spectral-loss proxy.

## Window Results

| window | best spectral | promote? | base final | best final | delta final | base MDD | best MDD | base spectral | best spectral loss |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020_covid | `static_00679b_05pct` | `True` | 961214.73 | 969616.37 | 8401.63 | -0.1751 | -0.1719 | 0.0333 | 0.0332 |
| 2022_rate_hike | `static_00679b_15pct` | `False` | 850711.80 | 817383.67 | -33328.13 | -0.1808 | -0.2124 | 0.0177 | 0.0173 |
| 2024_2026_live | `static_00679b_20pct` | `False` | 2971082.54 | 2884912.91 | -86169.63 | -0.2094 | -0.1980 | 0.0450 | 0.0440 |
| 2025_2026_live | `static_00679b_20pct` | `False` | 2173784.50 | 2135618.51 | -38165.99 | -0.1630 | -0.1656 | 0.0435 | 0.0430 |

## Conditional-Correlation Check

This check tries to avoid the known 2022 stock-bond hedge failure by opening 00679B only when lagged 63-day correlation versus the base strategy is negative and 00679B's own 63-day return is not worse than -2%.

| window | variant | active days | avg sleeve | delta final | delta MDD | delta spectral |
|---|---|---:|---:|---:|---:|---:|
| 2020_covid | `conditional_corr_00679b_05pct` | 50 | 0.0217 | 4796.46 | -0.0010 | 0.0007 |
| 2020_covid | `conditional_corr_00679b_10pct` | 50 | 0.0435 | 9551.58 | -0.0021 | 0.0017 |
| 2022_rate_hike | `conditional_corr_00679b_05pct` | 42 | 0.0104 | -4526.53 | -0.0044 | 0.0000 |
| 2022_rate_hike | `conditional_corr_00679b_10pct` | 42 | 0.0208 | -9039.26 | -0.0087 | 0.0000 |
| 2024_2026_live | `conditional_corr_00679b_05pct` | 219 | 0.0174 | -25558.64 | 0.0000 | -0.0001 |
| 2024_2026_live | `conditional_corr_00679b_10pct` | 219 | 0.0348 | -51009.47 | -0.0000 | -0.0001 |
| 2025_2026_live | `conditional_corr_00679b_05pct` | 148 | 0.0186 | -7246.24 | -0.0000 | -0.0001 |
| 2025_2026_live | `conditional_corr_00679b_10pct` | 148 | 0.0373 | -14532.18 | -0.0000 | -0.0001 |

## Spectral Profile Sensitivity

| window | profile | best variant | promote? | delta final | delta MDD | delta spectral loss |
|---|---|---|---:|---:|---:|---:|
| 2020_covid | `moderate_tail_sensitive` | `static_00679b_05pct` | `True` | 8401.63 | 0.0031 | -0.0001 |
| 2020_covid | `deep_tail_sensitive` | `static_00679b_05pct` | `True` | 8401.63 | 0.0031 | -0.0000 |
| 2020_covid | `extreme_tail_saturating` | `static_00679b_05pct` | `True` | 8401.63 | 0.0031 | -0.0002 |
| 2022_rate_hike | `moderate_tail_sensitive` | `static_00679b_15pct` | `False` | -33328.13 | -0.0316 | -0.0004 |
| 2022_rate_hike | `deep_tail_sensitive` | `static_00679b_15pct` | `False` | -33328.13 | -0.0316 | -0.0003 |
| 2022_rate_hike | `extreme_tail_saturating` | `static_00679b_15pct` | `False` | -33328.13 | -0.0316 | -0.0004 |
| 2024_2026_live | `moderate_tail_sensitive` | `static_00679b_20pct` | `False` | -86169.63 | 0.0114 | -0.0010 |
| 2024_2026_live | `deep_tail_sensitive` | `static_00679b_20pct` | `False` | -86169.63 | 0.0114 | -0.0014 |
| 2024_2026_live | `extreme_tail_saturating` | `static_00679b_20pct` | `False` | -86169.63 | 0.0114 | -0.0007 |
| 2025_2026_live | `moderate_tail_sensitive` | `static_00679b_20pct` | `False` | -38165.99 | -0.0027 | -0.0005 |
| 2025_2026_live | `deep_tail_sensitive` | `static_00679b_20pct` | `False` | -38165.99 | -0.0027 | -0.0007 |
| 2025_2026_live | `extreme_tail_saturating` | `static_00679b_20pct` | `False` | -38165.99 | -0.0027 | -0.0003 |

## Short-Horizon Dynamic Risk Check

This follows the paper's finding that dynamic risk objectives can be more useful at shorter horizons. Negative delta means the 00679B variant reduced rolling-horizon spectral loss versus base GroupA++.

| window | best spectral variant | delta 5d spectral | delta 20d spectral |
|---|---|---:|---:|
| 2020_covid | `static_00679b_05pct` | 0.0035 | -0.0029 |
| 2022_rate_hike | `static_00679b_15pct` | -0.0021 | 0.0012 |
| 2024_2026_live | `static_00679b_20pct` | -0.0006 | -0.0019 |
| 2025_2026_live | `static_00679b_20pct` | 0.0003 | 0.0033 |

## Block Bootstrap Stability

Paired 20-day block bootstrap on the best-spectral variant in each window. Higher `p spectral improve` means spectral-loss reduction is more stable under resampling; higher `p final improve` means final-value improvement is more stable.

| window | variant | p spectral improve | spectral delta p05 | spectral delta p95 | p final improve | final delta p05 | final delta p95 | p MDD improve |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2020_covid | `static_00679b_05pct` | 0.6080 | -0.0020 | 0.0017 | 0.9140 | -1888.39 | 17711.84 | 0.7460 |
| 2022_rate_hike | `static_00679b_15pct` | 0.6720 | -0.0014 | 0.0011 | 0.0120 | -53732.38 | -11102.05 | 0.0200 |
| 2024_2026_live | `static_00679b_20pct` | 0.9620 | -0.0018 | -0.0001 | 0.2000 | -319596.04 | 74722.87 | 0.5800 |
| 2025_2026_live | `static_00679b_20pct` | 0.7640 | -0.0012 | 0.0005 | 0.2560 | -149001.07 | 51974.28 | 0.2240 |

## 00679B Hedge Readiness State

Daily diagnostic state adapted from the paper's state-design idea. This is lagged one day and does not trade. `high_days` counts days whose readiness score is at least 0.70.

| window | latest level | latest score | corr63 | corr126 | bond 63d return | bond DD126 | base DD126 | base vol20 | cash capacity | high days |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020_covid | `medium` | 0.5409 | -0.5925 | -0.2374 | -0.0173 | -0.0872 | -0.0457 | 0.1393 | 0.1800 | 0 |
| 2022_rate_hike | `low` | 0.1947 | 0.1093 | -0.1471 | -0.1211 | -0.1442 | -0.1018 | 0.1187 | 0.4800 | 1 |
| 2024_2026_live | `low` | 0.2080 | -0.0408 | 0.0664 | -0.0290 | -0.0817 | -0.0894 | 0.1577 | 0.1800 | 59 |
| 2025_2026_live | `low` | 0.2080 | -0.0408 | 0.0664 | -0.0290 | -0.0817 | -0.0894 | 0.1577 | 0.1800 | 13 |

## Stress Path Perturbation

Deterministic stress scenarios adapted from the paper's perturbed-path validation. Each row applies the window's best-spectral 00679B sleeve to a modified 00679B return path while keeping the base GroupA++ path fixed.

| window | variant | scenario | delta final | delta MDD | delta spectral | delta 20d spectral |
|---|---|---|---:|---:|---:|---:|
| 2020_covid | `static_00679b_05pct` | `historical` | 8401.63 | 0.0031 | -0.0001 | -0.0029 |
| 2020_covid | `static_00679b_05pct` | `negative_corr_hedge` | 13498.33 | 0.0059 | -0.0006 | -0.0048 |
| 2020_covid | `static_00679b_05pct` | `stock_bond_down` | 2314.87 | -0.0008 | 0.0007 | -0.0000 |
| 2020_covid | `static_00679b_05pct` | `carry_drag` | 7565.43 | 0.0029 | -0.0001 | -0.0027 |
| 2022_rate_hike | `static_00679b_15pct` | `historical` | -33328.13 | -0.0316 | -0.0004 | 0.0012 |
| 2022_rate_hike | `static_00679b_15pct` | `negative_corr_hedge` | -14548.46 | -0.0142 | -0.0010 | -0.0022 |
| 2022_rate_hike | `static_00679b_15pct` | `stock_bond_down` | -50123.24 | -0.0478 | 0.0009 | 0.0042 |
| 2022_rate_hike | `static_00679b_15pct` | `carry_drag` | -37038.53 | -0.0349 | -0.0004 | 0.0016 |
| 2024_2026_live | `static_00679b_20pct` | `historical` | -86169.63 | 0.0114 | -0.0010 | -0.0019 |
| 2024_2026_live | `static_00679b_20pct` | `negative_corr_hedge` | 316176.57 | 0.0224 | -0.0030 | -0.0127 |
| 2024_2026_live | `static_00679b_20pct` | `stock_bond_down` | -514537.10 | -0.0093 | 0.0031 | 0.0182 |
| 2024_2026_live | `static_00679b_20pct` | `carry_drag` | -135203.89 | 0.0111 | -0.0009 | -0.0014 |
| 2025_2026_live | `static_00679b_20pct` | `historical` | -38165.99 | -0.0027 | -0.0005 | 0.0033 |
| 2025_2026_live | `static_00679b_20pct` | `negative_corr_hedge` | 148124.00 | 0.0100 | -0.0024 | -0.0065 |
| 2025_2026_live | `static_00679b_20pct` | `stock_bond_down` | -243212.92 | -0.0257 | 0.0035 | 0.0206 |
| 2025_2026_live | `static_00679b_20pct` | `carry_drag` | -61288.72 | -0.0033 | -0.0004 | 0.0038 |

## Transaction Cost Sensitivity

Cost sensitivity on each window's best-spectral 00679B sleeve. This follows the paper's explicit inclusion of proportional transaction costs. The base GroupA++ path is unchanged; only the cash-funded 00679B sleeve cost changes.

| window | variant | cost bps | delta final | delta MDD | delta spectral |
|---|---|---:|---:|---:|---:|
| 2020_covid | `static_00679b_05pct` | 0.0 | 8498.63 | 0.0031 | -0.0001 |
| 2020_covid | `static_00679b_05pct` | 10.0 | 8450.13 | 0.0031 | -0.0001 |
| 2020_covid | `static_00679b_05pct` | 20.0 | 8401.63 | 0.0031 | -0.0001 |
| 2020_covid | `static_00679b_05pct` | 50.0 | 8256.13 | 0.0031 | -0.0001 |
| 2022_rate_hike | `static_00679b_15pct` | 0.0 | -33083.16 | -0.0316 | -0.0004 |
| 2022_rate_hike | `static_00679b_15pct` | 10.0 | -33205.64 | -0.0316 | -0.0004 |
| 2022_rate_hike | `static_00679b_15pct` | 20.0 | -33328.13 | -0.0316 | -0.0004 |
| 2022_rate_hike | `static_00679b_15pct` | 50.0 | -33695.60 | -0.0316 | -0.0004 |
| 2024_2026_live | `static_00679b_20pct` | 0.0 | -82376.79 | 0.0114 | -0.0010 |
| 2024_2026_live | `static_00679b_20pct` | 10.0 | -84273.72 | 0.0114 | -0.0010 |
| 2024_2026_live | `static_00679b_20pct` | 20.0 | -86169.63 | 0.0114 | -0.0010 |
| 2024_2026_live | `static_00679b_20pct` | 50.0 | -91851.31 | 0.0114 | -0.0010 |
| 2025_2026_live | `static_00679b_20pct` | 0.0 | -35358.25 | -0.0026 | -0.0005 |
| 2025_2026_live | `static_00679b_20pct` | 10.0 | -36762.50 | -0.0026 | -0.0005 |
| 2025_2026_live | `static_00679b_20pct` | 20.0 | -38165.99 | -0.0027 | -0.0005 |
| 2025_2026_live | `static_00679b_20pct` | 50.0 | -42371.99 | -0.0027 | -0.0005 |

## Imported Advantages

- Use spectral risk instead of only Sharpe/MDD when judging a hedge sleeve.
- Evaluate short-horizon hedge behavior separately from terminal wealth.
- Keep dynamic decisions time-consistent by using rolling past data only.
- Treat 00679B capacity as state-dependent and funded only from cash.

## Not Imported

- No actor-critic live allocator.
- No option-pricing surrogate.
- No DCC-GARCH simulator in production.
- No automatic 00679B target-weight change.
