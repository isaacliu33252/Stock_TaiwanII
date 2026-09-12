"""Closed-form quadratic log-return bounds for daily-reset leveraged ETFs.

Implements Theorem 1 / Remark 2 of Brown (2023), "Long-Term Returns
Estimation of Leveraged Indexes and ETFs" (arXiv:2301.03186), evaluated at
the free variable y = 0. The paper's own numerical experiments (Section
4.3.1) find the true supremum over y is close to y = 0 in practice, so this
is a practical closed-form approximation of the bound, not the exact
supremum.

Research-only. Not wired into any production signal, guard or execution
path. See scripts/evaluate/evaluate_00631l_quadratic_bound_regime_crosscheck.py
for the diagnostic that consumes this module.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class QuadraticBoundCoeffs:
    a: float
    b: float
    c: float


def remark2_lower_bound_coeffs(leverage: float, y0: float) -> QuadraticBoundCoeffs:
    """Coefficients (a0, b0, c0) for Theorem 1's lower bound at free variable y=0.

    Valid for leverage > 1 and log(1 - 1/leverage) < y0 < 0 (Theorem 1
    domain restricted to Remark 2's y=0 simplification). y0 is meant to be a
    lower bound on daily log-returns (y0 <= Y_i for all i) for the bound to
    be a certified guarantee; see quadratic_lower_bound_log_return.
    """
    if leverage <= 1.0:
        raise ValueError("remark2_lower_bound_coeffs requires leverage > 1")
    floor = math.log(1.0 - 1.0 / leverage)
    if not (floor < y0 < 0.0):
        raise ValueError(f"y0={y0} must satisfy log(1-1/L)={floor} < y0 < 0")
    a = (1.0 / y0) * (math.log(1.0 + leverage * (math.exp(y0) - 1.0)) / y0 - leverage)
    return QuadraticBoundCoeffs(a=a, b=float(leverage), c=0.0)


def quadratic_lower_bound_log_return(m1: float, m2: float, n: int, coeffs: QuadraticBoundCoeffs) -> float:
    """n * (a*m2 + b*m1 + c): the Theorem-1 lower bound on cumulative log-return.

    m1, m2 are the mean and mean-square of daily log-returns over the n-day
    window. This is a certified lower bound only if every daily log-return
    in the window is >= the y0 anchor used to build `coeffs`. Used here as a
    continuous scoring function on realized (not worst-case-clipped)
    returns, not as a certified guarantee -- callers must check the y0
    condition separately if a certified bound is required.
    """
    return n * (coeffs.a * m2 + coeffs.b * m1 + coeffs.c)
