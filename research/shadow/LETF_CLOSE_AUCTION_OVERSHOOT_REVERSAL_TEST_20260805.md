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
2026    80.8

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
2026    722.0

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
2026    0.112

## Full-sample regressions (HAC/Newey-West, 5 lags)

                      channel                                                label    n      beta         t            p
                 same-day (t)                               2330 (TSMC) | t | SOXX 3075  0.365671 15.123862 1.127326e-51
next-day (t+1, reversal test)                             2330 (TSMC) | t+1 | SOXX 3074 -0.011124 -0.656917 5.112344e-01
                 same-day (t)    0050 (Taiwan50, LETF's own underlying) | t | SOXX 3074  0.277639 14.415738 4.120141e-47
next-day (t+1, reversal test)  0050 (Taiwan50, LETF's own underlying) | t+1 | SOXX 3073  0.003772  0.274575 7.836426e-01
                 same-day (t)             Hon Hai (low Taiwan50 weight) | t | SOXX 3064  0.242830 10.344820 4.417477e-25
next-day (t+1, reversal test)           Hon Hai (low Taiwan50 weight) | t+1 | SOXX 3063  0.054265  2.483691 1.300286e-02
                 same-day (t)            MediaTek (low Taiwan50 weight) | t | SOXX 3064  0.359693 11.720743 9.979287e-32
next-day (t+1, reversal test)          MediaTek (low Taiwan50 weight) | t+1 | SOXX 3063  0.087106  3.212643 1.315198e-03
                 same-day (t)       Chunghwa Telecom (low-beta control) | t | SOXX 3064  0.018903  2.381721 1.723195e-02
next-day (t+1, reversal test)     Chunghwa Telecom (low-beta control) | t+1 | SOXX 3063 -0.000906 -0.121016 9.036783e-01
                 same-day (t)                                2330 (TSMC) | t | QQQ 3075  0.504572 12.032966 2.384394e-33
next-day (t+1, reversal test)                              2330 (TSMC) | t+1 | QQQ 3074 -0.036065 -1.410430 1.584128e-01
                 same-day (t)     0050 (Taiwan50, LETF's own underlying) | t | QQQ 3074  0.382630 11.515133 1.106885e-30
next-day (t+1, reversal test)   0050 (Taiwan50, LETF's own underlying) | t+1 | QQQ 3073 -0.010097 -0.519087 6.036997e-01
                 same-day (t)              Hon Hai (low Taiwan50 weight) | t | QQQ 3064  0.337566  8.591475 8.586006e-18
next-day (t+1, reversal test)            Hon Hai (low Taiwan50 weight) | t+1 | QQQ 3063  0.084658  2.664290 7.715112e-03
                 same-day (t)             MediaTek (low Taiwan50 weight) | t | QQQ 3064  0.476254  8.779762 1.638213e-18
next-day (t+1, reversal test)           MediaTek (low Taiwan50 weight) | t+1 | QQQ 3063  0.079144  2.065639 3.886254e-02
                 same-day (t)        Chunghwa Telecom (low-beta control) | t | QQQ 3064  0.042158  3.434626 5.933731e-04
next-day (t+1, reversal test)      Chunghwa Telecom (low-beta control) | t+1 | QQQ 3063  0.001339  0.102864 9.180711e-01
                 same-day (t)                              2330 (TSMC) | t | ^IXIC 3075  0.520384 11.740733 7.880014e-32
next-day (t+1, reversal test)                            2330 (TSMC) | t+1 | ^IXIC 3074 -0.034454 -1.251490 2.107558e-01
                 same-day (t)   0050 (Taiwan50, LETF's own underlying) | t | ^IXIC 3074  0.398618 11.485603 1.558434e-30
next-day (t+1, reversal test) 0050 (Taiwan50, LETF's own underlying) | t+1 | ^IXIC 3073 -0.008558 -0.399282 6.896857e-01
                 same-day (t)            Hon Hai (low Taiwan50 weight) | t | ^IXIC 3064  0.350407  8.524599 1.533405e-17
next-day (t+1, reversal test)          Hon Hai (low Taiwan50 weight) | t+1 | ^IXIC 3063  0.089387  2.692005 7.102386e-03
                 same-day (t)           MediaTek (low Taiwan50 weight) | t | ^IXIC 3064  0.488426  8.776735 1.682886e-18
next-day (t+1, reversal test)         MediaTek (low Taiwan50 weight) | t+1 | ^IXIC 3063  0.085205  2.199169 2.786591e-02
                 same-day (t)      Chunghwa Telecom (low-beta control) | t | ^IXIC 3064  0.041090  3.343579 8.270516e-04
next-day (t+1, reversal test)    Chunghwa Telecom (low-beta control) | t+1 | ^IXIC 3063  0.002606  0.196010 8.446026e-01

## Dose-split and period-split regressions (2330, next-day reversal, SOXX instrument)

                                                              label    n      beta         t        p                                          regime
 2330 (TSMC) | t+1 | low-dose (00631L+00632R turnover below median) 1525 -0.011441 -0.416672 0.676918  low-dose (00631L+00632R turnover below median)
2330 (TSMC) | t+1 | high-dose (00631L+00632R turnover above median) 1522 -0.014368 -0.662405 0.507712 high-dose (00631L+00632R turnover above median)
                   2330 (TSMC) | t+1 | pre-2020-01 (smaller 00631L) 1465 -0.034725 -1.345306 0.178527                    pre-2020-01 (smaller 00631L)
                 2330 (TSMC) | t+1 | 2020-01 onward (larger 00631L) 1609 -0.004195 -0.201984 0.839929                  2020-01 onward (larger 00631L)
