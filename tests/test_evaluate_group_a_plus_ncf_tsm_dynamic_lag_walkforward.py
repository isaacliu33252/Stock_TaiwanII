from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.evaluate import evaluate_group_a_plus_ncf_tsm_dynamic_lag_walkforward as mod


def test_build_dynamic_lag_column_recovers_true_lag_causally(monkeypatch) -> None:
    rng = np.random.default_rng(0)
    n = 600
    idx = pd.date_range("2020-01-01", periods=n, freq="D")

    tsm_ret = pd.Series(rng.normal(0, 0.01, n), index=idx)
    tsm_close = (1 + tsm_ret).cumprod()
    # Target (0050) is driven by TSM's return from 2 days earlier, not 1 (the
    # fixed production lag), so a correctly-causal adaptive-lag feature
    # should diverge from the fixed lag=1 baseline after the warmup window.
    target_ret = tsm_ret.shift(2).fillna(0.0) * 0.9 + pd.Series(rng.normal(0, 0.001, n), index=idx)
    target_close = (1 + target_ret).cumprod()
    main_df = pd.DataFrame({"close": target_close}, index=idx)

    monkeypatch.setattr(mod, "fetch_yf_close_cached", lambda *a, **k: tsm_close)
    monkeypatch.setattr(mod, "ROLLING_WINDOW_DAYS", 60)

    out = mod.build_dynamic_lag_column(main_df, db_path="unused")

    fixed_lag1 = tsm_ret.shift(1).reindex(idx)
    # After enough warmup, the adaptive column should differ from the fixed
    # lag=1 baseline often enough that it isn't just silently falling back.
    tail = out.iloc[200:]
    fixed_tail = fixed_lag1.iloc[200:]
    disagreement = (tail.round(10) != fixed_tail.round(10)).mean()
    assert disagreement > 0.3


def test_build_dynamic_lag_column_falls_back_to_fixed_lag_during_warmup(monkeypatch) -> None:
    n = 50
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    tsm_ret = pd.Series(np.linspace(-0.01, 0.01, n), index=idx)
    tsm_close = (1 + tsm_ret).cumprod()
    main_df = pd.DataFrame({"close": (1 + tsm_ret.shift(1).fillna(0.0)).cumprod()}, index=idx)

    monkeypatch.setattr(mod, "fetch_yf_close_cached", lambda *a, **k: tsm_close)
    monkeypatch.setattr(mod, "ROLLING_WINDOW_DAYS", 126)

    out = mod.build_dynamic_lag_column(main_df, db_path="unused")

    # Build the expected series the same way the function does internally
    # (pct_change of the reconstructed close series loses the first point).
    recovered_tsm_ret = tsm_close.pct_change().reindex(idx, method="ffill")
    fixed_lag1 = recovered_tsm_ret.shift(1)
    pd.testing.assert_series_equal(out, fixed_lag1, check_names=False)
