# 2105.08664 DeepPocket - Group A+ Review

**Status: closed, no import. Research-only assessment, no code written.**

Source: `C:\Users\isaac\Downloads\2105.08664.pdf`

Paper: Soleymani & Paquet (NRC Canada), "Deep Graph Convolutional
Reinforcement Learning for Financial Portfolio Management - DeepPocket"
(2021), a sequel to the same authors' 2020 "DeepBreath" paper (neither
previously reviewed in this repo -- checked, no hits).

## Paper Summary

An end-to-end RL portfolio allocator with three stages: (1) a restricted
stacked autoencoder (RSAE) compresses 11 raw price/technical-indicator
features per asset into a low-dimensional latent representation; (2) a
graph convolutional network (GCN) models time-varying pairwise correlations
between assets, with edge weight `w_ij = 1 - corr(asset_i, asset_j)` over a
short rolling window; (3) an actor-critic RL agent (two CNNs) consumes the
GCN output and directly outputs portfolio weights via softmax, trained
offline on historical data then updated daily with a rolling 11-day buffer
("passive concept drift"). Tested on 28 US large-cap stocks across 5
periods including the COVID-19 crash (Feb-Mar 2020), where it claims a
+4.46% return versus DJI's -29.36% over the same window.

## Fit to Group A+

**No import recommended.** Every one of the paper's three core mechanisms
either doesn't apply to this project's universe or duplicates ground
already covered and closed:

1. **GCN over asset correlations -- doesn't apply to a 4-ticker universe.**
   The GCN's entire value proposition is exploiting complex, non-trivial
   correlation structure across many (28 in the paper) heterogeneous
   instruments. Group A+ has 4 risky tickers: 0050, 00631L, 00632R,
   00679B. Three of those six pairs are mechanically determined, not
   learnable relationships -- 00631L and 00632R are a 2x-leveraged and
   -1x-inverse derivative of the *same* underlying (0050/TAIEX-50), so
   their correlation with 0050 and each other is near-deterministic by
   construction, not something a graph convolution needs to discover.
   00679B (US 20yr treasury) is the one genuinely distinct driver, but
   one real edge in a graph isn't a case for graph convolution machinery.
   This is functionally the same verdict already reached for network/graph
   volatility modeling on this project's universe -- see the closed
   GNHAR line (`project_gnhar_network_volatility_forecast_20260711`, all
   p>=0.29, not significant): a graph-structure model needs more genuinely
   independent nodes than this universe has.
2. **Direct neural-network weight output (actor-critic RL) -- already
   extensively shadow-tested this same day via the unrelated
   arXiv:1706.10059 (Jiang/Xu/Liang PVM) review
   (`docs/1706_10059_DEEP_PORTFOLIO_MANAGEMENT_GROUPA_PLUS_REVIEW_20260808.md`).**
   That paper makes the identical fundamental architectural claim (an RL
   agent should directly output continuous portfolio weights instead of a
   hand-tuned regime table), and after full validation (8 OOS windows
   2017-2026, parameter sensitivity, workbook-aware holdings check) the
   verdict was shadow-only-at-best, not promoted, with Group A+'s
   hand-tuned regime table + bounded discrete trim fractions remaining the
   live mechanism. There's no reason DeepPocket's version of the same core
   idea (direct RL weight output) would fare differently on the same
   4-ticker universe; re-running that validation for a second paper making
   the same architectural claim would be pure duplication.
3. **RSAE feature compression -- solves a problem Group A+ doesn't have.**
   The autoencoder's purpose is reducing computational cost/dimensionality
   before training a large neural allocator daily. Group A+'s NCF models
   are gradient-boosted/ensemble classifiers trained on engineered features
   directly (AUC/Brier-optimized, per
   [[project_a2118_ncf_hedge_dormancy_root_cause_20260723]] and the wider
   NCF integration work) -- there's no daily-retrain-a-large-net cost
   problem here to solve, so importing a feature-compression stage aimed
   at that problem has no target to attach to.
4. **Passive concept-drift / rolling online retraining -- already present
   in spirit.** The paper's "retrain daily on a rolling buffer of recent
   days" discipline is conceptually the same as this project's existing
   rolling/expanding-window NCF panel training (see the
   `project_ncf_panel_global_weight_drift_20260702` fix and related NCF
   panel work) -- already implemented via a different mechanism (periodic
   panel-window retraining rather than literal daily neural-weight
   gradient updates). Marginal, not a new capability.

## Not Recommended

- Do not build a GCN over Group A+'s 4-ticker universe -- there isn't
  enough genuinely independent correlation structure to learn, and the
  question has already been asked and answered negatively via GNHAR.
- Do not re-run a second full shadow-validation cycle for a direct-RL-
  weight-output allocator -- 1706.10059's review already did this
  exhaustively for the same architectural family the same day; the
  verdict transfers.
- Do not import the COVID-19 headline performance claim as evidence for
  anything -- different universe (US large-cap equities, not Taiwan
  leveraged/inverse ETFs), different training regime, and per this
  project's own citation discipline
  ([[project_finrlx_citation_rule_adopted_20260724]]) a paper's raw
  headline numbers on a foreign universe are not evidence for this one.

## Decision

Closed, no code written, no shadow candidate opened. Cleaner close than
most papers reviewed this session -- every mechanism either has an
existing, already-negative answer on this universe, or targets a problem
this project doesn't have.
