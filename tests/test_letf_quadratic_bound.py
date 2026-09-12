from __future__ import annotations

import math

import pytest

from group_a_plus.integrations.letf_quadratic_bound import (
    quadratic_lower_bound_log_return,
    remark2_lower_bound_coeffs,
)


def test_remark2_coeffs_match_paper_worked_example() -> None:
    # L=2, y0=log(0.8) (-20% daily floor): paper's own headline S&P 500
    # example (Section 4.3.1). b0 must equal L and c0 must equal 0 exactly
    # (Remark 2), and a0 must be negative (a0 < 0 holds for L > 1).
    coeffs = remark2_lower_bound_coeffs(leverage=2.0, y0=math.log(0.8))
    assert coeffs.b == 2.0
    assert coeffs.c == pytest.approx(0.0, abs=1e-9)
    assert coeffs.a < 0.0
    assert coeffs.a == pytest.approx(-1.29614, abs=1e-4)


def test_remark2_coeffs_reject_y0_outside_domain() -> None:
    with pytest.raises(ValueError):
        # y0 must be < 0 for this simplification.
        remark2_lower_bound_coeffs(leverage=2.0, y0=0.01)
    with pytest.raises(ValueError):
        # For L=2, log(1 - 1/2) = log(0.5); y0 must exceed that floor.
        remark2_lower_bound_coeffs(leverage=2.0, y0=math.log(0.4))
    with pytest.raises(ValueError):
        remark2_lower_bound_coeffs(leverage=1.0, y0=-0.1)


def test_quadratic_lower_bound_zero_return_gives_zero() -> None:
    coeffs = remark2_lower_bound_coeffs(leverage=2.0, y0=math.log(0.8))
    assert quadratic_lower_bound_log_return(m1=0.0, m2=0.0, n=20, coeffs=coeffs) == 0.0


def test_quadratic_lower_bound_scales_linearly_in_n() -> None:
    coeffs = remark2_lower_bound_coeffs(leverage=2.0, y0=math.log(0.8))
    one_day = quadratic_lower_bound_log_return(m1=0.001, m2=0.0002, n=1, coeffs=coeffs)
    ten_days = quadratic_lower_bound_log_return(m1=0.001, m2=0.0002, n=10, coeffs=coeffs)
    assert ten_days == pytest.approx(10.0 * one_day)
