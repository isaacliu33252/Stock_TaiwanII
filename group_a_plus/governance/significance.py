"""Statistical significance testing for GroupA+ candidate-vs-baseline comparisons.

2026-08-01: arXiv:2607.16450v1's own stated Limitation #1 is that its portfolio
rankings (Sharpe/Rachev/STARR boxplots) rely on the distribution of rolling-window
performance measures rather than a formal significance test -- it names
"Jobson-Korkie or Memmel-type tests, or bootstrap confidence intervals" as what
would be needed. group_a_plus/governance/compare.py's promotion gate has the
exact same gap: final_value_floor_pass / max_drawdown_non_worse_pass /
sharpe_non_worse_pass are simple point-estimate threshold checks with no
accounting for sampling uncertainty. This module adds that missing test as a
standalone, reusable utility -- it is diagnostic-only and is not wired into
compare_candidates()'s pass/fail gate, since doing that would need its own
validation pass (does requiring significance change any real historical
promotion decision, and would that have been the right call in hindsight) --
same "observe before wire" posture as promotion_utility in compare.py.

2026-09-04: arXiv:2608.08405 (a strategy-capacity experimental-design paper,
otherwise not applicable to GroupA+ -- see project memory
project_2608_08405_capacity_experiment_design_desk_review_20260904) proves in
passing (Prop 3.12/Table 8) that a bracket built from the best-looking member
of an adaptively searched grid covers the truth far below its nominal rate --
its simulation shows under 20% against a nominal 90%, since the candidate was
selected for looking good. That is the same shape of risk as GroupA+'s own
threshold/parameter grid searches (switch-policy cutoffs, defensive-basket
weights, NCF ensemble cutoffs): reporting a single winning candidate's own
p-value overstates confidence. bonferroni_grid_significance() adds the fix --
a Bonferroni correction over the size of the search grid fixed in advance --
as another standalone diagnostic, not wired into any gate.

2026-09-11: arXiv:2606.01650 (Pav, "Post-Selection Estimation of Sharpe
Ratios") and arXiv:2602.00080 (Sheppert, "The GT-Score") were desk-reviewed
against a real GroupA+ grid search -- the direction-5 momentum_fast_exit_min
19-point threshold sweep (results/reentry_momentum_threshold_sweep_20260908.json)
-- and both came back verified positive (see project memory
project_2606_01650_james_stein_governance_diagnostic_20260911 and
project_2602_00080_gtscore_overfitting_complement_20260911). Bonferroni above
answers "is the best candidate significantly better than baseline"; these two
answer a different, complementary question:

james_stein_shrink_best_sharpe() asks "how much of the best candidate's
apparent edge over its peers is just this grid's own selection bias" (Pav eq.
in Sec 2: shrinkage factor s = [1 - (k-2)/n / sum((zeta_hat_i - zeta_bar)^2)]+,
shrunk estimate = zeta_bar + s*(zeta_hat_best - zeta_bar)). On the real sweep,
3 of 4 historical windows had s=0 (the entire threshold curve was
indistinguishable from noise); only inflation_2022 had s=0.75, and that window
independently matches the "sharp cliff at 0.05/0.055" already flagged in the
sweep script's own docstring.

gt_score() (Sheppert eq. 1 + Algorithm 1) is a per-candidate composite score
that can replace "pick the window with the best raw Sharpe" as the selection
rule itself -- on the same sweep, raw-Sharpe selection walked straight into
that 0.05 cliff on a held-out inflation_2022 fold (MDD -17.97% -> -27.81%),
while GT-Score selection avoided it. It is a guard against a specific known
failure mode, not a source of new alpha: on the 3 noise windows it performed
within normal variance of raw-Sharpe selection, neither better nor worse.

Both are diagnostic-only, same posture as everything else in this module: not
wired into compare_candidates()'s pass/fail gate. Recommended order of use on
a future grid search: run james_stein_shrink_best_sharpe() first -- if s is
near 0, the grid has no real signal and gt_score() has nothing to protect
against; only bother re-selecting with gt_score() when s is meaningfully above
0.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


def jobson_korkie_memmel_test(
    returns_a: pd.Series, returns_b: pd.Series
) -> dict[str, Any]:
    """Test H0: Sharpe(returns_a) == Sharpe(returns_b) on paired return series.

    Implements the Jobson & Korkie (1981) test with Memmel's (2003) correction
    to the asymptotic variance formula (the version most references call
    "Jobson-Korkie/Memmel"). Both series must be non-annualized per-period
    (e.g. daily) returns aligned on the same dates -- the test assumes paired
    observations from a joint distribution, not independent samples.
    """
    paired = pd.concat([returns_a.rename("a"), returns_b.rename("b")], axis=1).dropna()
    n = len(paired)
    if n < 30:
        return {
            "n": n,
            "status": "insufficient_data",
            "reason": "need at least 30 paired observations for the asymptotic test",
        }

    mu_a = float(paired["a"].mean())
    mu_b = float(paired["b"].mean())
    sigma_a = float(paired["a"].std(ddof=1))
    sigma_b = float(paired["b"].std(ddof=1))
    sigma_ab = float(paired["a"].cov(paired["b"]))

    if sigma_a <= 0 or sigma_b <= 0:
        return {"n": n, "status": "degenerate_variance", "reason": "one series has zero variance"}

    sharpe_a = mu_a / sigma_a
    sharpe_b = mu_b / sigma_b

    theta = (1.0 / n) * (
        2.0 * sigma_a**2 * sigma_b**2
        - 2.0 * sigma_a * sigma_b * sigma_ab
        + 0.5 * mu_a**2 * sigma_b**2
        + 0.5 * mu_b**2 * sigma_a**2
        - (mu_a * mu_b / (sigma_a * sigma_b)) * sigma_ab**2
    )
    if theta <= 0:
        return {"n": n, "status": "degenerate_variance", "reason": "non-positive asymptotic variance estimate"}

    z_stat = (sigma_b * mu_a - sigma_a * mu_b) / math.sqrt(theta)
    p_value = float(2.0 * stats.norm.sf(abs(z_stat)))

    return {
        "n": n,
        "status": "ok",
        "sharpe_a": sharpe_a,
        "sharpe_b": sharpe_b,
        "sharpe_diff": sharpe_a - sharpe_b,
        "z_statistic": float(z_stat),
        "p_value": p_value,
        "significant_at_5pct": p_value < 0.05,
        "significant_at_1pct": p_value < 0.01,
    }


def bonferroni_grid_significance(
    results: dict[str, dict[str, Any]],
    *,
    candidate_grid_size: int,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Simultaneous-coverage significance check across a pre-specified grid of
    candidate configs (arXiv:2608.08405 Prop 3.12/Table 8: on a grid searched
    adaptively or reported only for its best-looking member, a bracket built
    from that member's own p-value/CI covers the truth well under nominal
    coverage -- the paper's simulation puts a naive adaptive bracket's coverage
    under 20% against a nominal 90%, because the candidate was selected FOR
    looking good. The fix is a Bonferroni correction over the size of the
    search grid fixed BEFORE looking at results, not over however many
    candidates happen to survive to be reported).

    `results` maps candidate_id -> the output of jobson_korkie_memmel_test for
    that candidate vs the same baseline. `candidate_grid_size` is the number
    of candidates in the pre-registered search grid; it must be supplied by
    the caller and be >= len(results) -- inferring it from len(results) after
    a search has already narrowed down to survivors defeats the correction,
    which is exactly the failure mode this function exists to prevent.

    Diagnostic-only, like the rest of this module: not wired into
    compare_candidates()'s pass/fail gate.
    """
    if candidate_grid_size < len(results):
        raise ValueError(
            "candidate_grid_size must be >= number of candidates evaluated; "
            "it is the size of the pre-registered search grid, not the "
            "number of survivors being reported"
        )

    corrected_alpha = alpha / candidate_grid_size
    candidates: dict[str, dict[str, Any]] = {}
    for candidate_id, result in results.items():
        if result.get("status") != "ok":
            candidates[candidate_id] = {
                "status": result.get("status", "unknown"),
                "significant": False,
                "significant_improvement": False,
            }
            continue
        p_value = result["p_value"]
        sharpe_diff = result.get("sharpe_diff")
        significant = p_value < corrected_alpha
        candidates[candidate_id] = {
            "status": "ok",
            "p_value": p_value,
            "sharpe_diff": sharpe_diff,
            # jobson_korkie_memmel_test is two-sided: `significant` alone only
            # means "distinguishable from baseline", not "better than
            # baseline" -- a candidate that is significantly WORSE also sets
            # it True. `significant_improvement` is the field a promotion
            # decision should actually read.
            "significant": significant,
            "significant_improvement": bool(significant and sharpe_diff is not None and sharpe_diff > 0),
        }

    return {
        "candidate_grid_size": candidate_grid_size,
        "alpha": alpha,
        "corrected_alpha": corrected_alpha,
        "candidates": candidates,
        "any_significant": any(c.get("significant") for c in candidates.values()),
        "any_significant_improvement": any(c.get("significant_improvement") for c in candidates.values()),
    }


def bootstrap_final_value_ci(
    returns_a: pd.Series,
    returns_b: pd.Series,
    *,
    n_boot: int = 2000,
    block_size: int = 20,
    confidence: float = 0.95,
    seed: int = 20260801,
) -> dict[str, Any]:
    """Block-bootstrap CI for the final-value ratio of two paired daily-return
    series (candidate vs baseline), preserving each series' own autocorrelation
    via moving-block resampling of paired (a, b) rows (same block indices
    applied to both legs, so the a-vs-b comparison for each resample stays a
    real paired comparison, not an independently-shuffled one).
    """
    paired = pd.concat([returns_a.rename("a"), returns_b.rename("b")], axis=1).dropna()
    n = len(paired)
    if n < block_size * 3:
        return {
            "n": n,
            "status": "insufficient_data",
            "reason": f"need at least {block_size * 3} paired observations for block bootstrap",
        }

    rng = np.random.default_rng(seed)
    a = paired["a"].to_numpy()
    b = paired["b"].to_numpy()
    n_blocks = math.ceil(n / block_size)
    max_start = n - block_size

    ratios = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, max_start + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block_size) for s in starts])[:n]
        final_a = float(np.prod(1.0 + a[idx]))
        final_b = float(np.prod(1.0 + b[idx]))
        ratios[i] = final_a / final_b if final_b != 0 else np.nan

    ratios = ratios[np.isfinite(ratios)]
    alpha = 1.0 - confidence
    lower = float(np.quantile(ratios, alpha / 2.0))
    upper = float(np.quantile(ratios, 1.0 - alpha / 2.0))
    point_ratio = float(np.prod(1.0 + a)) / float(np.prod(1.0 + b))

    return {
        "n": n,
        "status": "ok",
        "n_boot": int(len(ratios)),
        "block_size": block_size,
        "point_final_value_ratio_a_over_b": point_ratio,
        "ci_lower": lower,
        "ci_upper": upper,
        "confidence": confidence,
        "a_significantly_better": lower > 1.0,
        "a_significantly_worse": upper < 1.0,
    }


def james_stein_shrink_best_sharpe(
    candidate_sharpes: dict[str, float],
    *,
    n_obs: int,
) -> dict[str, Any]:
    """How much of the best candidate's apparent edge is grid selection bias.

    Pav 2026 (arXiv:2606.01650), Sec 2. `candidate_sharpes` maps candidate_id
    to its own (non-annualized, per-period, e.g. daily) in-sample Sharpe
    ratio, all computed over the SAME `n_obs` periods -- this is the
    compound-symmetric setup the paper analyzes (candidates sharing one price
    path, e.g. a threshold/parameter grid), not independent assets. Let
    zeta_hat be the k-vector of candidate Sharpes, zeta_bar its grand mean.
    The shrinkage factor is

        s = max(0, 1 - (k-2)/n_obs / sum((zeta_hat_i - zeta_bar)**2))

    and the shrunk estimate of the best candidate's true Sharpe is
    zeta_bar + s*(zeta_hat_best - zeta_bar). s in [0, 1]: s=0 means the
    entire grid is statistically indistinguishable from noise around the
    grand mean (do not trust ANY candidate's apparent ranking); s=1 means no
    shrinkage was needed (spread across candidates dwarfs sampling noise).

    Needs k >= 3 candidates (k-2 must be positive) and a genuinely
    pre-specified grid, same caveat as bonferroni_grid_significance: do not
    call this after already narrowing down to a subset of "interesting"
    candidates.

    Diagnostic-only: not wired into compare_candidates()'s pass/fail gate.
    """
    if n_obs <= 0:
        raise ValueError("n_obs must be positive")
    k = len(candidate_sharpes)
    if k < 3:
        return {
            "k": k,
            "n_obs": n_obs,
            "status": "insufficient_candidates",
            "reason": "need at least 3 candidates for James-Stein (k-2 must be positive)",
        }

    ids = list(candidate_sharpes.keys())
    zeta_hat = np.array([candidate_sharpes[i] for i in ids], dtype=float)
    zeta_bar = float(zeta_hat.mean())
    sum_sq_dev = float(np.sum((zeta_hat - zeta_bar) ** 2))

    best_idx = int(np.argmax(zeta_hat))
    best_id = ids[best_idx]
    biased_estimate = float(zeta_hat[best_idx])  # Pav's "Biased" estimator: the raw ζ̂_k, unshrunk.

    if sum_sq_dev <= 0:
        # All candidates tied -- no spread to shrink from; grand mean is already the answer.
        shrinkage_factor = 0.0
        shrunk_estimate = zeta_bar
    else:
        shrinkage_factor = max(0.0, 1.0 - ((k - 2) / n_obs) / sum_sq_dev)
        shrunk_estimate = zeta_bar + shrinkage_factor * (biased_estimate - zeta_bar)

    return {
        "k": k,
        "n_obs": n_obs,
        "status": "ok",
        "best_candidate_id": best_id,
        "grand_mean_sharpe": zeta_bar,
        "biased_estimate": biased_estimate,
        "shrinkage_factor": shrinkage_factor,
        "shrunk_estimate": shrunk_estimate,
        "selection_bias": biased_estimate - shrunk_estimate,
        # Heuristic read, not from the paper: near 0 says "this grid's spread is
        # noise, do not trust the ranking"; near 1 says "shrinkage barely mattered".
        "grid_has_real_signal": shrinkage_factor > 0.1,
    }


def gt_score(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    downside_mar: float = 0.0,
) -> dict[str, Any]:
    """Composite selection score guarding against a specific overfitting failure mode.

    Sheppert 2026 (arXiv:2602.00080), Eq. 1 + Algorithm 1. Meant to REPLACE
    "pick the candidate with the highest raw Sharpe/return" as the selection
    rule on a grid of candidates evaluated over the same `returns` index, not
    to be read as a standalone quality score in isolation.

    mu = mean(returns), sigma = std(returns, ddof=1), N = len(returns),
    z = (mu - mean(benchmark_returns)) / (sigma / sqrt(N)), r2 = R-squared of
    a linear fit of the log cumulative-return curve against a time index
    (consistency of the equity curve, penalizes lumpy/outlier-driven
    performance), sigma_d = downside deviation of returns below `downside_mar`
    (Sortino & van der Meer). Piecewise (paper's Algorithm 1, sign-flipped
    here from the paper's loss-to-minimize convention to a score-to-maximize
    convention -- higher `gt_score` is always better in this function's
    output, matching every other score in this module):

        z <= 0:      score = -(100 + 100*(1 - exp(-abs(z - 1))))   # underperforms benchmark
        0 < z <= 1:  score = -(100*(1 - exp(-abs(z - 1))))          # marginal, smooth transition
        z > 1:       score = mu * ln(z) * r2 / (sigma_d + 1e-6)     # standard GT-Score

    Diagnostic-only: not wired into compare_candidates()'s pass/fail gate. Use
    it to re-rank an existing grid of candidates, not to gate promotion on its
    own -- the desk review (project memory
    project_2602_00080_gtscore_overfitting_complement_20260911) found it only
    earns its keep on grid folds that james_stein_shrink_best_sharpe() flags
    as having real signal; on pure-noise folds it performs within normal
    variance of plain Sharpe selection.
    """
    paired = returns.dropna()
    n = len(paired)
    if n < 2:
        return {"n": n, "status": "insufficient_data", "reason": "need at least 2 return observations"}

    mu = float(paired.mean())
    sigma = float(paired.std(ddof=1))
    if sigma <= 1e-12:
        # Floating-point summation of a near-constant return series rarely
        # lands on an exact 0.0 std -- treat anything at that noise floor as
        # degenerate rather than letting it through and dividing by it below.
        return {"n": n, "status": "degenerate_variance", "reason": "zero-variance return series"}

    mu_m = float(benchmark_returns.dropna().mean())
    z = (mu - mu_m) / (sigma / math.sqrt(n))

    log_curve = np.log1p(paired).cumsum().to_numpy()
    time_index = np.arange(n, dtype=float)
    if np.allclose(log_curve, log_curve[0]):
        r_squared = 0.0
    else:
        slope_result = stats.linregress(time_index, log_curve)
        r_squared = float(slope_result.rvalue**2)

    downside = np.minimum(0.0, paired.to_numpy() - downside_mar)
    sigma_d = float(np.sqrt(np.mean(downside**2)))

    if z <= 0:
        score = -(100.0 + 100.0 * (1.0 - math.exp(-abs(z - 1.0))))
        regime = "underperforms_benchmark"
    elif z <= 1:
        score = -(100.0 * (1.0 - math.exp(-abs(z - 1.0))))
        regime = "marginal_smooth_transition"
    else:
        score = mu * math.log(z) * r_squared / (sigma_d + 1e-6)
        regime = "standard_gt_score"

    return {
        "n": n,
        "status": "ok",
        "mu": mu,
        "mu_benchmark": mu_m,
        "sigma": sigma,
        "z": z,
        "r_squared": r_squared,
        "sigma_d": sigma_d,
        "regime": regime,
        "gt_score": score,
    }
