# 2605.01176 v1 vs v4 Diff - SPO Companion Paper

**Status: diff only, no change to prior closure verdict.**

Written 2026-08-08 during a full-repo paper-audit action-items follow-up.
The 2026-07-26 review (`GROUP_A_PLUS_2601_04062_SPO_PAPER_REVIEW_HANDOFF_20260726.md`,
memory `project_spo_companion_paper_2605_01176_closed_20260726`) explicitly
reviewed v4 and closed it with "no applicable mechanism at all." This
checks whether v1 -- also present in Downloads -- differs in any way that
would change that verdict. Read both PDFs directly and compared section by
section.

## What changed between v1 (2026-05-02) and v4 (2026-07-13)

1. **Turnover results upgraded from single-run to 5-seed mean+/-std**
   (Section 2.4 / Table 1). v1 reported one turnover number per
   dataset/lambda (e.g. DOW lambda=0.1: 88.30%). v4 reruns with 5 random
   seeds and reports mean+/-std (e.g. DOW lambda=0.1: 94.93%+/-1.61%). This
   is a robustness upgrade, not a reversal -- v4's numbers are if anything
   *higher* and now explicitly shown to be seed-stable, reinforcing the
   original "turnover stays unrealistically high regardless of risk
   aversion" claim rather than weakening it.
2. **Table 2 gains an explicit `Fee rate kappa = 0.005` row.** Pure
   reproducibility disclosure; the value was previously implicit.
3. **Table 3, lambda=50.0 row only: small numeric revision.** DOW
   Standard/Rescale turnover and a few other cells shifted slightly (e.g.
   Standard TO 0.9913 -> 0.9513; Rescale TO 0.9782 -> 0.9382). No bolded
   best-metric winner changes; the qualitative ranking (Clip+Adj most
   conservative, Rescale+Adj best Sharpe/return) is identical in both
   versions.
4. **Section 2.2 DFL-regret formalization rewritten** to explicitly name
   the MVO objective `U_t` and define `w*(r) = argmax U_t(w;r)`. Cosmetic
   formalization, same regret definition and same downstream math.
5. **Section 6 (Future Work) reframed**, and this is the only change worth
   flagging as substantive: v1's future work was additive ("design better
   ranking-based losses," "add more financially-motivated correction
   mechanisms," "broader empirical evaluation"). v4 replaces this with two
   more skeptical open questions: (a) whether the observed turnover/
   inflation is an artifact of *this specific* penalty formulation and
   linear predictor choice, or intrinsic to SPO-based learning generally;
   (b) whether stabilization mechanisms belong post-hoc or embedded in
   training. v4 is explicitly less confident that its own findings
   generalize across model/penalty choices than v1 was.

## Relevance to the prior Group A+ closure verdict

None of the above changes the mechanism the paper diagnoses (SPO+-trained
predictors self-inflating to force decisive rankings under transaction-cost
-adjusted marginal-score optimization) or the three stabilizers it proposes
(clipping, min-max rescaling, partial portfolio adjustment). The prior
verdict's reasoning -- Group A+'s NCF models train on bounded
AUC/Brier-style classification objectives, and `target_weights` come from a
hand-tuned regime table with bounded discrete trim fractions, so there is
no continuous unbounded "predicted return vector" for SPO's pathology to
apply to -- depends only on that unchanged mechanism, not on the turnover
percentages or Future Work framing that moved between versions.

If anything, v4's added skepticism about generalizability (item 5 above)
is a point in favor of the closure being appropriately conservative rather
than under-cautious: the paper's own authors are now less sure the effect
transfers outside their exact SPO+/linear-predictor/MVO setup, which is a
setup Group A+ doesn't use in the first place.

**Conclusion: no re-open. The 2026-07-26 v4 review remains the accurate
and current closure.**
