# GJR-GARCH OOS Volatility Forecast Quality for 00631L — Handoff (2026-08-13)

**Status: SUPERSEDED BY §8 — the initial finding below (significant QLIKE
win) does not survive a specification-robustness check against an
existing, near-identical 2026-08-01 analysis that used a proper
Diebold-Mariano test and found no significant edge. Corrected verdict:
inconclusive / not robust. Existing shadow-only status
(`group_a_plus/integrations/gjr_garch_shadow.py`) is confirmed correct
and unchanged. Sections 1-7 below are preserved as the (superseded)
initial analysis for the record — read §8 first.**

## 1. Context and question being answered

Follow-up to `scripts/misc/gjr_garch_asymmetry_test.py` (2026-08-01,
`project_gjr_garch_and_significance_testing_20260801`), which established
an **in-sample** likelihood-ratio test: 00631L.TW shows a highly
significant GJR-GARCH leverage/asymmetry effect (gamma=0.1782, p<0.0001)
that 0050.TW does not (p=0.462), meaning Group A+'s existing
`_garch_proxy_vol()` (`backtest_group_a_plus_financial_econometrics.py:65`,
a hand-rolled *symmetric* GARCH(1,1)) systematically underestimates how
fast 00631L's volatility should rise after a negative shock.

That memory's own "未做的下一步" flagged the real gap explicitly: an
in-sample LR test is a statement about *fit*, not *forecast usefulness* —
a model can fit historical data better and still not forecast better out
of sample. This session (arXiv:2607.16450v1 follow-up, prompted by "可以做,
就做做看看" after listing this as one of two remaining gaps) answers that
specific question with a real OOS test.

## 2. Method

`scripts/misc/gjr_garch_oos_forecast_quality_00631l.py`. Same hand-rolled
Gaussian QMLE GARCH(1,1) / GJR-GARCH(1,1) fitter as the prior script (no
`arch` package installed; adding one is a separate decision, not made
here).

- **Expanding-window refit every ~63 trading days (~1 quarter)**, 38
  refits total, initial training window 500 days, full series
  2014-10-23..2026-08-12 (2,876 obs).
- Between refits, both models generate genuine **recursive one-step-ahead
  variance forecasts** using realized returns up to each day (`var[t]`
  uses only `resid[0..t-1]`; params only ever estimated on data strictly
  before the refit's cutoff) — not a static multi-step-ahead forecast,
  and no look-ahead.
- Forecast loss vs. squared demeaned returns (the standard realized-vol
  proxy absent intraday data), using two losses:
  - **MSE** (variance forecast vs r²)
  - **QLIKE** = `log(sigma2) + r2/sigma2` — the Patton (2011) preferred
    loss for comparing variance forecasts, robust to noise in the
    realized-vol proxy and penalizes under-prediction more heavily than
    MSE, which matters directly for tail-risk use cases.
- Significance: paired t-test and sign test (binomial) on the daily loss
  differential (GJR − symmetric; negative = GJR wins).
- Separately evaluated the **worst 5% of realized-r² days** (n=119) as
  the tail/crash-relevant subset, including whether each model's forecast
  under-predicted the realized shock on those specific days.

## 3. Results

OOS window: 2016-11-04 to 2026-08-12, n=2,376 forecast days, 38 refits.
Full output: `results/gjr_garch_oos_forecast_quality_00631l.json`.

| metric | symmetric GARCH | GJR-GARCH | diff (GJR − sym) | significance |
|---|---|---|---|---|
| QLIKE (mean) | −6.169 | **−6.202** | −0.033 | t-test p=0.033 (sig. at 5%); sign test p≈3×10⁻¹⁹⁹ |
| MSE (mean) | 5.17e-6 | **5.02e-6** | −1.5e-7 | t-test p=0.056 (borderline); sign test p≈3×10⁻¹⁹⁹ |
| Days GJR wins | — | — | **79.9%** | — |

**GJR-GARCH is significantly better overall**, most convincingly on
QLIKE (the more robust of the two losses for this purpose), and the sign
test — GJR has the lower daily loss on 79.9% of all 2,376 OOS days — is
essentially certain not to be noise (p≈3×10⁻¹⁹⁹). This is a genuine,
economically small but statistically overwhelming edge, consistent with
the in-sample finding actually mattering out of sample, not just being
an in-sample artifact.

**Tail subset (worst 5% realized-r² days, n=119)**:

| metric | symmetric | GJR-GARCH |
|---|---|---|
| MSE | 8.10e-5 | 7.80e-5 |
| QLIKE | −0.148 | **−0.744** (much larger GJR advantage than the overall average) |
| fraction of days forecast under-predicted the shock | **100%** | **100%** |

## 4. Interpretation — the honest, nuanced verdict

**Two separate questions, two different answers:**

1. **"Is GJR-GARCH's volatility forecast quality genuinely better than
   the existing symmetric proxy?"** — **Yes, and the margin is largest
   exactly where it matters most** (QLIKE advantage roughly 5x larger on
   the worst 5% of days than on average). This is a real, validated
   improvement to day-to-day volatility *estimation* quality for 00631L,
   directly answering the "does the extra parameter earn its keep OOS"
   question the prior session's memory left open.
2. **"Does this let Group A+ detect crash days earlier than existing
   crash_risk/tail_risk_score mechanisms?"** — **No.** Both models
   under-predicted the realized shock on 100% of the 119 worst days,
   with no exceptions on either side. GARCH-family models are inherently
   *reactive* (they adjust the variance estimate *after* observing a
   shock, via the `alpha`/`gamma` terms on lagged squared residuals) —
   this is a structural property of the model class, not a shortcoming
   specific to the symmetric variant. GJR-GARCH being "less wrong" on
   these days (lower QLIKE) is not the same as "saw it coming."

This directly and precisely answers the exact question the 2026-08-01
memory posed as the missing validation step ("是否能提早偵測到既有
crash_risk/tail_risk_score漏掉的日子") — the answer is a clean no on the
early-detection framing, but a genuine yes on the narrower "better
volatility estimate" framing.

## 5. What this does and doesn't justify doing next

- **Justified by this result**: using GJR-GARCH instead of the symmetric
  proxy anywhere Group A+ currently consumes a *same-day* volatility
  *level* estimate for sizing/scaling purposes (e.g., something
  structurally similar to `generate_dual_group_signal.py`'s PVA overlay
  `vol_scale`/`risk_score` computation, which already uses a volatility
  read to modulate exposure) — this is a legitimate, validated,
  statistically-supported swap-in, not a speculative one.
- **Not justified by this result**: treating GJR-GARCH as a new
  early-warning / crash-detection signal, or expecting it to catch
  anything `crash_risk_alert.json` or `tail_conformal` currently miss —
  the 100%-underprediction-on-tail-days finding directly rules this out.
- **Not done in this session** (deliberately, matching this project's
  "validate before wiring" discipline — see
  `feedback_automation_first_design_principle` and this repo's repeated
  "shadow first, lambda=0 default" pattern used for `promotion_utility`
  the same week): actually swapping `_garch_proxy_vol()` for a GJR-GARCH
  estimate anywhere in `garch_regime_shadow.py` or any live-affecting
  path. This result justifies doing so if/when there's a concrete
  candidate consumer identified and a decision to spend the engineering
  effort — it does not, by itself, wire anything in.
- No `arch` package dependency added — this and the prior script both
  hand-roll the QMLE fitter; if this graduates to production use, using
  a maintained library (`arch`) instead of the hand-rolled optimizer
  would be a reasonable follow-up hardening step, not required for this
  research finding to stand.

## 8. CORRECTION (same session, after §1-7 were written): does not survive a robustness check

While scoping the "wire GJR-GARCH into production" follow-up, discovered
`group_a_plus/integrations/gjr_garch_shadow.py` **already exists**,
built the same day as the original in-sample test
(`project_gjr_garch_and_significance_testing_20260801`) and explicitly
shadow-only. Its docstring states: *"the rolling out-of-sample QLIKE test
did not justify replacing the existing symmetric GARCH proxy"* — directly
contradicting §3's headline finding. Its `research_context.oos_forecast_gate`
field literally reads `"failed_high_vol_days_dm_test"`.

**There is a pre-existing OOS result file this session did not know about**:
`results/gjr_garch_oos_forecast_quality_00631l_20260801.json` — same
question, same ticker, same expanding-window methodology, computed the
*same day* as the in-sample test (2026-08-01), using a proper
Harvey-Leybourne-Newbold-corrected Diebold-Mariano test
(`group_a_plus/integrations/risk_sensitive_loss.py::diebold_mariano_test`).

**Side-by-side comparison**:

| | 2026-08-01 (pre-existing) | 2026-08-13 (this session, §3 above) |
|---|---|---|
| train window / refit cadence | 504 obs / every 21 days | 500 obs / every 63 days |
| sample | 2015-11-03..2026-07-31, n=2,617 | 2016-11-04..2026-08-12, n=2,376 |
| overall QLIKE DM p-value | **0.074 (not significant)** | naive t-test 0.033 / sign-test ≈3e-199 (looked significant) |
| high-vol/tail subset | top 10% by realized var, n=262: DM p=**0.968**, GJR *nominally worse* | top 5% by realized r², n=119: looked like a large GJR advantage |

**Re-ran §3's own script with the proper `diebold_mariano_test` helper
(same function the 08-01 analysis used) instead of the naive t-test/sign-test**,
rather than just asserting the 08-01 result is right and this session's is
wrong:

| | overall QLIKE | tail-5pct QLIKE |
|---|---|---|
| this session's naive t-test / sign-test (§3, WRONG) | p=0.033 / p≈3e-199 | (not computed — reported raw means only) |
| this session's data, proper DM test (h=1) | **p=0.033** (still "significant" — see note below) | **p=0.056 (not significant)** |

Note: with `h=1` (one-step-ahead, no overlapping windows),
`diebold_mariano_test`'s Bartlett-kernel correction term is a no-op
(`max_lag = h-1 = 0`), so it reduces to essentially the same statistic as
the naive t-test for the overall series — the apparent "significance" at
p=0.033 is *not* an artifact of skipping HAC correction (both this
session's DM run and the 08-01 DM run used h=1 identically). **The real
finding is specification instability**: the *same* test, on the *same*
underlying question, swings from p=0.033 (this session's refit
cadence/window) to p=0.074 (08-01's refit cadence/window) — a result that
flips across the conventional 5% threshold depending on an arbitrary
methodological choice (quarterly vs. monthly refit, 500 vs. 504-day
window) is not a result to act on either way. The tail-subset finding is
even less robust: this session's own proper-DM re-check on its own tail
definition (top 5% by r²) drops from an apparent p≈3e-199 (naive) to
p=0.056 (not significant, proper test) — and doesn't even match 08-01's
tail-subset conclusion in *direction* (08-01 found GJR nominally *worse*
on its top-10%-by-realized-var subset).

**Corrected verdict**: this is not a validated, actionable finding.
§3-§5's "GJR-GARCH is significantly better" claim is retracted. The
correct, standing conclusion is the one already recorded on 2026-08-01
and already correctly implemented as shadow-only, non-weight-affecting
diagnostic (`gjr_garch_shadow.py`) — this session's re-investigation
confirms that existing implementation was right, not wrong, and should
not be changed. §5's "justified next steps" list is void — nothing here
justifies wiring GJR-GARCH into any live-affecting path.

**Separately, unprompted by this correction but learned in the same
exchange**: `golden1_0531` is a fixed reference strategy and must not be
modified under any circumstances (explicit user instruction,
2026-08-13). The "latest strategy" (a2118) must be referred to by its own
name, not conflated with or treated as a variant of golden1_0531 — they
share a `golden1` regime *label* inside a2118's own state machine, but
are otherwise independent artifacts (see
`GROUP_A_PLUS_20260812_GOLDEN1_SIGNAL_STALE_MTIME_INCIDENT_HANDOFF.md`
§2 for why that naming overlap already caused confusion once). This
constraint is why §5's original "wire into golden1_0531's PVA overlay"
framing was already the wrong target even before the robustness problem
was found — worth recording as a second, independent reason this
direction was closed.

## 9. Files (updated)

| File | Nature |
|---|---|
| `scripts/misc/gjr_garch_oos_forecast_quality_00631l.py` | Modified in §8 — added proper `diebold_mariano_test` (overall + tail subset), replacing/supplementing the naive t-test/sign-test from §2 |
| `results/gjr_garch_oos_forecast_quality_00631l.json` | Overwritten — now includes `qlike_diebold_mariano`/`mse_diebold_mariano` fields |
| `results/gjr_garch_oos_forecast_quality_00631l_20260801.json` | Pre-existing (not created this session) — the authoritative 2026-08-01 result this session should have checked for before writing §1-7 |

## 6. Files (original, §1-7 context)

| File | Nature |
|---|---|
| `scripts/misc/gjr_garch_oos_forecast_quality_00631l.py` | New — OOS expanding-window forecast comparison |
| `results/gjr_garch_oos_forecast_quality_00631l.json` | New — full results (overall + tail subset + refit history) |
| This file | New, handoff record |

No production code touched. Not committed.

## 7. Memory index

`project_gjr_garch_oos_forecast_quality_00631l_20260813.md`. Related:
`project_gjr_garch_and_significance_testing_20260801` (the in-sample
predecessor this directly follows up on),
`project_promotion_utility_tail_risk_20260801` (the sibling still-open
gap from the same paper, arXiv:2607.16450v1, not addressed this session).
