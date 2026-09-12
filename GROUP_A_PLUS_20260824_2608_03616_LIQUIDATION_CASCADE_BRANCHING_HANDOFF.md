# GroupA+ 2026-08-24 Handoff: arXiv:2608.03616 (Liquidation Cascade Branching Ratio)

## Status

`closed_negative`, decided at desk review — no backtest or reimplementation
attempted. No production code changed.

---

## Paper

Garcia Seuma, "Measuring the engine of a liquidation cascade: subcritical
branching inside a first-order transition" (arXiv:2608.03616, 2026-08-04).
Part II of a series (Part I: arXiv:2607.27070) studying seven major
crypto-perpetual liquidation cascades (2022-2025: LUNA/UST, FTX, yen
carry-trade unwind, December 2024 leverage flush, two 2025 tariff shocks,
and the record October 2025 cascade).

**Core findings**:
1. Cross-asset correlation structure (order parameter c̄, susceptibility
   proxy χ = N·Var(c_ij)) jumps discontinuously at crash onset in 6/7
   events, with χ *collapsing* rather than diverging — the signature of a
   **first-order transition**, not a critical point. This is invariant
   under panel subsampling (N=8-28), ruling out small-panel artifacts.
2. The in-cascade signature lives in the **liquidity sector**: price
   impact spikes (×1.2-3.5 regressed on Binance, ×3.2-9.1 quoted directly
   on Hyperliquid) and open interest clears 25-70%, on two venues and two
   independent impact measurements.
3. A Galton-Watson branching-cascade model (λ = k·ρ̃, impact-per-dollar ×
   forced-notional-per-relative-move) is **eliminated** as a description
   of the pre-cascade state: both of its falsifiable predictions (a timing
   prediction and a severity/amplification prediction) fail at simulated
   power ≥ 0.96, on both proxied and directly measured regressors.
4. Using Hyperliquid's fully public on-chain fill log, the branching ratio
   of the record October 2025 cascade is measured **in flight**, with both
   factors observed and no free constants: λ̂ ≈ 0.1-0.2 throughout —
   deeply subcritical. 87.8% of post-onset forced selling landed within 30
   minutes, and 62.6% of it was absorbed off-book by the venue's automated
   backstop vault, which mechanically suppresses the branching ratio
   precisely at the climax.
5. Conclusion: severity is set by shock × map-in-path × liquidity
   withdrawal, not by a diverging multiplier — which is why no scalar
   pre-state measure (leverage stock, book fragility, or their product)
   grades crash severity. "Leverage is the fuel, not the fire alarm."

This is a rigorous, honestly-caveated physics-of-markets paper (own
limitations section, pre-registered power calculations, block-bootstrap
significance testing, an appendix documenting and fixing a timestamp-
misalignment artifact in a cross-venue causality test). The quality of the
paper is not in question; the applicability to Group A+ is.

---

## Applicability Assessment (desk review only — no backtest run)

Domain mismatch here is more complete than any prior paper closed this
month on structural grounds (e.g. `2607_24410_cd_dfm_characteristic_driven_covariance`,
`2608_20020_reconfiguration_premium_correlation_rotation`), for three
independent, each-sufficient reasons:

1. **The measured mechanism has no analogue in Group A+'s instruments.**
   The paper's central object, the branching ratio λ, is defined and
   measured from a specific, published exchange mechanism: user-level
   margin liquidation, triggered by a liquidation-threshold density near
   price, with forced sells hitting an order book and a portion absorbed
   by an automated backstop vault. Group A+ trades Taiwan-listed ETFs
   (0050, the 2x-leveraged 00631L, the inverse 00632R, plus a small
   defensive basket) — 00631L achieves its leverage via the *fund's own*
   daily rebalancing against futures/swaps at the fund-manager level, not
   via user-level margin positions that can be individually liquidated in
   a public cascade. There is no analogue of Hyperliquid's per-user
   liquidation engine, no analogue of a backstop vault, and critically,
   **no equivalent of a "liquidation-threshold density" for GroupA+'s
   retail-held ETF units** — an ETF holder does not get force-sold by an
   exchange the way an over-leveraged perpetual-futures position does.

2. **None of the paper's required data sources exist for Group A+'s
   universe.** The three inputs are Hyperliquid's on-chain fill log
   (`s3://hl-mainnet-node-data`, attributing every forced fill to a
   liquidated user), Hyperliquid's per-minute asset-context archive
   (quoted impact-spread prices), and a Kyle-style impact regression on
   Binance perpetuals order flow. None of these exist for 0050/00631L —
   there is no public fill log of forced liquidations, no venue-quoted
   impact-spread series, and Taiwan equity/ETF microstructure data at this
   granularity is not part of Group A+'s current data pipeline.

3. **The paper's actionable finding (single-variable EWS are unreliable;
   crashes are collective and abrupt, not gradual and critical) does not
   transfer as NEW evidence for Group A+ specifically — it is independently
   already established here.** This session has twice tested, hands-on, on
   0050/00631L directly, whether price/return-statistical structure alone
   (autocorrelation, HMM volatility regimes) carries exploitable predictive
   signal, and found it does not:
   [[project_2607_19497_trend_following_acf_sharpe_20260823]] (closed-form
   ACF-to-Sharpe framework: near-zero autocorrelation, Sharpe entirely
   drift-driven) and the 2026-08-23 CHMM regime-detector test (same
   conclusion via a volatility-regime framework). This crypto-liquidation
   paper reaches a *directionally* consistent conclusion (single-series
   EWS fail; the transition is collective/abrupt) via a completely
   different asset class and mechanism (perpetual-futures margin cascades,
   not ETF price dynamics) — interesting as a cross-domain echo, but it is
   confirmatory, not new evidence, and does not suggest a new mechanism
   Group A+ could test that the two direct Taiwan-data tests haven't
   already covered.

### What, if anything, is conceptually adjacent

The paper's liquidity-sector finding (impact spikes and open-interest
clearing are the universal in-cascade signature, more informative than any
pre-state predictor) is a genuinely interesting general market-
microstructure idea — "watch liquidity withdrawal, not price memory."
But operationalizing it for Group A+ would require order-book depth or
impact-spread data for 0050/00631L that does not currently exist in the
pipeline, and even if it did, this would be measuring the *in-cascade*
signature (i.e., confirming a crash is happening while it happens), not a
pre-crash warning signal — which is not obviously more useful than Group
A+'s existing drawdown-based reactive risk mechanisms (execution guard,
alert state) that already respond to realized price/drawdown moves.

---

## Conclusion

`closed_negative`, decided at desk review. Three independent,
each-sufficient reasons: (1) the paper's central measured mechanism
(user-level margin liquidation with a public backstop vault) has no
structural analogue in Group A+'s ETF-wrapper universe; (2) none of its
three required data sources (on-chain fill log, venue impact-spread
archive, perpetual order-flow regression) exist for 0050/00631L; (3) its
one genuinely actionable conclusion (single-variable EWS are unreliable;
crashes are abrupt and collective) is already independently established on
Taiwan ETF data this session via two unrelated hands-on tests, so this
paper adds cross-domain corroboration rather than new, testable evidence
or a new mechanism for Group A+.

## Files

- No new script (desk review only).
- Registry: `2608_03616_liquidation_cascade_branching_ratio`
- Memory: `project_2608_03616_liquidation_cascade_branching_20260824.md`
