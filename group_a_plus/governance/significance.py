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
