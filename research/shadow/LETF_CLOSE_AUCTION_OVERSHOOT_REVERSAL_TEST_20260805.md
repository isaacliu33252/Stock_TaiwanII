# LETF Close-Auction Overshoot/Reversal Test — 2330 vs 00631L/00632R

**Status: research/shadow only. Not wired to any production signal or gate.**

Motivated by arXiv:2608.03703 ("Preying on Leveraged ETFs", Zhao 2026-08-04).
Tests whether TSMC's close over-weights overnight U.S. tech/semiconductor news
and reverses the next session -- the paper's headline signature for Korean
single-stock LETFs -- given that TSMC dominates the Taiwan 50 index weight that
00631L/00632R rebalance against. No LETF AUM or closing-auction-specific volume
data exists in this project's DB, so K and the saturation ratio from the paper
cannot be replicated directly; this is a reduced-form proxy test only.

## Dose proxy: 00631L+00632R combined daily traded value (億元 TWD, yearly mean)

2014     0.4
2015     4.2
2016    13.6
2017     6.6
2018     9.0
2019     6.6
2020    18.0
2021    12.7
2022    16.8
2023    10.2
2024    16.5
2025    24.4
2026    80.7

## Context: TSMC's own daily traded value (億元 TWD, yearly mean)

2014     31.2
2015     39.5
2016     39.2
2017     42.6
2018     65.4
2019     69.8
2020    156.2
2021    187.9
2022    169.6
2023    129.7
2024    344.9
2025    373.2
2026    744.3

## Ratio: (00631L+00632R turnover) / (TSMC's own full-day turnover)

Ceiling on any same-day loop gain from this channel -- 00631L/00632R's
*entire* day's flow, not just the closing-auction slice of it, relative to
TSMC's own full-day liquidity. Korea's SK Hynix analogue (order vs. auction
alone, not full-day volume) reached a median of 1.02.

2014    0.014
2015    0.106
2016    0.346
2017    0.156
2018    0.138
2019    0.095
2020    0.115
2021    0.068
2022    0.099
2023    0.079
2024    0.048
2025    0.065
2026    0.108

## Full-sample regressions (HAC/Newey-West, 5 lags)

                      channel                                                label    n      beta         t            p
                 same-day (t)                               2330 (TSMC) | t | SOXX 3061  0.380785 16.121764 1.794140e-58
next-day (t+1, reversal test)                             2330 (TSMC) | t+1 | SOXX 3060 -0.008746 -0.507773 6.116125e-01
                 same-day (t)    0050 (Taiwan50, LETF's own underlying) | t | SOXX 3061  0.287238 15.095591 1.731301e-51
next-day (t+1, reversal test)  0050 (Taiwan50, LETF's own underlying) | t+1 | SOXX 3060  0.004786  0.340496 7.334834e-01
                 same-day (t)             Hon Hai (low Taiwan50 weight) | t | SOXX 3061  0.241960 10.323646 5.509048e-25
next-day (t+1, reversal test)           Hon Hai (low Taiwan50 weight) | t+1 | SOXX 3060  0.053818  2.445787 1.445362e-02
                 same-day (t)            MediaTek (low Taiwan50 weight) | t | SOXX 3061  0.359259 11.676760 1.675617e-31
next-day (t+1, reversal test)          MediaTek (low Taiwan50 weight) | t+1 | SOXX 3060  0.080827  2.978572 2.895953e-03
                 same-day (t)       Chunghwa Telecom (low-beta control) | t | SOXX 3061  0.018843  2.365269 1.801699e-02
next-day (t+1, reversal test)     Chunghwa Telecom (low-beta control) | t+1 | SOXX 3060 -0.000680 -0.090265 9.280767e-01
                 same-day (t)                                2330 (TSMC) | t | QQQ 3061  0.517291 12.051398 1.906881e-33
next-day (t+1, reversal test)                              2330 (TSMC) | t+1 | QQQ 3060 -0.034813 -1.341609 1.797227e-01
                 same-day (t)     0050 (Taiwan50, LETF's own underlying) | t | QQQ 3061  0.390320 11.506332 1.225816e-30
next-day (t+1, reversal test)   0050 (Taiwan50, LETF's own underlying) | t+1 | QQQ 3060 -0.010174 -0.515252 6.063773e-01
                 same-day (t)              Hon Hai (low Taiwan50 weight) | t | QQQ 3061  0.336694  8.567398 1.058493e-17
next-day (t+1, reversal test)            Hon Hai (low Taiwan50 weight) | t+1 | QQQ 3060  0.083419  2.615255 8.916097e-03
                 same-day (t)             MediaTek (low Taiwan50 weight) | t | QQQ 3061  0.474791  8.756405 2.015770e-18
next-day (t+1, reversal test)           MediaTek (low Taiwan50 weight) | t+1 | QQQ 3060  0.072631  1.897906 5.770840e-02
                 same-day (t)        Chunghwa Telecom (low-beta control) | t | QQQ 3061  0.042646  3.470527 5.194388e-04
next-day (t+1, reversal test)      Chunghwa Telecom (low-beta control) | t+1 | QQQ 3060  0.001643  0.125922 8.997938e-01
                 same-day (t)                              2330 (TSMC) | t | ^IXIC 3061  0.529175 11.684221 1.534796e-31
next-day (t+1, reversal test)                            2330 (TSMC) | t+1 | ^IXIC 3060 -0.033501 -1.205419 2.280418e-01
                 same-day (t)   0050 (Taiwan50, LETF's own underlying) | t | ^IXIC 3061  0.403797 11.431797 2.900443e-30
next-day (t+1, reversal test) 0050 (Taiwan50, LETF's own underlying) | t+1 | ^IXIC 3060 -0.008841 -0.408251 6.830896e-01
                 same-day (t)            Hon Hai (low Taiwan50 weight) | t | ^IXIC 3061  0.349886  8.503078 1.846289e-17
next-day (t+1, reversal test)          Hon Hai (low Taiwan50 weight) | t+1 | ^IXIC 3060  0.088027  2.642195 8.237052e-03
                 same-day (t)           MediaTek (low Taiwan50 weight) | t | ^IXIC 3061  0.486617  8.758300 1.982165e-18
next-day (t+1, reversal test)         MediaTek (low Taiwan50 weight) | t+1 | ^IXIC 3060  0.079231  2.047330 4.062567e-02
                 same-day (t)      Chunghwa Telecom (low-beta control) | t | ^IXIC 3061  0.041783  3.399713 6.745664e-04
next-day (t+1, reversal test)    Chunghwa Telecom (low-beta control) | t+1 | ^IXIC 3060  0.002986  0.224232 8.225765e-01

## Dose-split and period-split regressions (2330, next-day reversal, SOXX instrument)

                                                              label    n      beta         t        p                                          regime
 2330 (TSMC) | t+1 | low-dose (00631L+00632R turnover below median) 1517 -0.011062 -0.402121 0.687595  low-dose (00631L+00632R turnover below median)
2330 (TSMC) | t+1 | high-dose (00631L+00632R turnover above median) 1516 -0.010620 -0.479088 0.631876 high-dose (00631L+00632R turnover above median)
                   2330 (TSMC) | t+1 | pre-2020-01 (smaller 00631L) 1465 -0.034725 -1.345330 0.178519                    pre-2020-01 (smaller 00631L)
                 2330 (TSMC) | t+1 | 2020-01 onward (larger 00631L) 1595 -0.000457 -0.021494 0.982852                  2020-01 onward (larger 00631L)
