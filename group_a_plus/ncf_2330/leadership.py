"""TSMC leadership features for the 2330.TW NCF workflow."""

from __future__ import annotations

import numpy as np
import pandas as pd

from group_a_plus.utils.tsmc_0050_weight import TSMC_0050_WEIGHT_ASSUMPTION


def _rolling_zscore(series: pd.Series, window: int = 120) -> pd.Series:
    mean = series.rolling(window, min_periods=20).mean()
    std = series.rolling(window, min_periods=20).std()
    return ((series - mean) / std.replace(0.0, np.nan)).clip(-3.0, 3.0)


def _align_to_index(series: pd.Series | None, idx: pd.DatetimeIndex, *, shift_n: int = 0) -> pd.Series:
    if series is None or series.empty:
        return pd.Series(np.nan, index=idx)
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    out = s.sort_index().reindex(idx, method="ffill")
    if shift_n:
        out = out.shift(shift_n)
    return out.astype(float)


def _add_tsmc_leadership_features(
    ext: pd.DataFrame,
    idx: pd.DatetimeIndex,
    *,
    tsmc_close: pd.Series,
    etf_0050_close: pd.Series | None,
    adr_fx_ret: pd.Series | None,
    soxx_ret: pd.Series | None,
    peer_semis_ret: pd.Series | None,
    usdtwd_change: pd.Series | None,
    inst_foreign_net: pd.Series | None = None,
    feature_mode: str = "after_close",
    tsmc_weight_in_0050: float = TSMC_0050_WEIGHT_ASSUMPTION,
) -> None:
    """Add TSMC leadership features with explicit timing control.

    `pre_open` uses only T-1 Taiwan close-derived data plus US overnight data.
    `after_close` may use the current Taiwan close-derived data. US series are
    already overnight inputs from the latest available US session and are not
    additionally shifted here.
    """
    if feature_mode not in {"pre_open", "after_close"}:
        raise ValueError(f"Unsupported feature_mode: {feature_mode}")
    tw_shift = 1 if feature_mode == "pre_open" else 0
    weight = float(np.clip(tsmc_weight_in_0050, 0.0, 0.95))
    ex_weight = max(1.0 - weight, 1e-6)

    tsmc = _align_to_index(tsmc_close, idx)
    tsmc_ret_1d = tsmc.pct_change()
    tsmc_ret_5d = tsmc.pct_change(5)
    tsmc_ret_20d = tsmc.pct_change(20)

    et50 = _align_to_index(etf_0050_close, idx) if etf_0050_close is not None else pd.Series(np.nan, index=idx)
    et50_ret_1d = et50.pct_change()
    ex_tsmc_ret = (et50_ret_1d - weight * tsmc_ret_1d) / ex_weight
    vs_ex_tsmc = tsmc_ret_1d - ex_tsmc_ret
    contribution = weight * tsmc_ret_1d

    ext["tsmc_leadership_ret_5d"] = tsmc_ret_5d.shift(tw_shift).values
    ext["tsmc_leadership_ret_20d"] = tsmc_ret_20d.shift(tw_shift).values
    ext["tsmc_leadership_vs_0050_ex_tsmc"] = vs_ex_tsmc.shift(tw_shift).values
    ext["tsmc_leadership_0050_contribution"] = contribution.shift(tw_shift).values
    ext["tsmc_leadership_foreign_net"] = _align_to_index(inst_foreign_net, idx, shift_n=tw_shift).values

    ext["tsmc_leadership_adr_overnight"] = _align_to_index(adr_fx_ret, idx).values
    ext["tsmc_leadership_soxx_ret"] = _align_to_index(soxx_ret, idx).values
    ext["tsmc_leadership_peer_semis_ret"] = _align_to_index(peer_semis_ret, idx).values
    ext["tsmc_leadership_usdtwd_change"] = _align_to_index(usdtwd_change, idx).values

    score_inputs = [
        "tsmc_leadership_ret_5d",
        "tsmc_leadership_ret_20d",
        "tsmc_leadership_adr_overnight",
        "tsmc_leadership_soxx_ret",
        "tsmc_leadership_peer_semis_ret",
        "tsmc_leadership_vs_0050_ex_tsmc",
        "tsmc_leadership_0050_contribution",
        "tsmc_leadership_foreign_net",
        "tsmc_leadership_usdtwd_change",
    ]
    z = pd.DataFrame({col: _rolling_zscore(ext[col]) for col in score_inputs}, index=idx)
    weights = pd.Series(
        {
            "tsmc_leadership_ret_5d": 1.0,
            "tsmc_leadership_ret_20d": 1.0,
            "tsmc_leadership_adr_overnight": 1.2,
            "tsmc_leadership_soxx_ret": 0.8,
            "tsmc_leadership_peer_semis_ret": 0.8,
            "tsmc_leadership_vs_0050_ex_tsmc": 1.2,
            "tsmc_leadership_0050_contribution": 0.7,
            "tsmc_leadership_foreign_net": 0.9,
            "tsmc_leadership_usdtwd_change": 0.5,
        }
    )
    weighted = z.mul(weights, axis=1)
    denom = weighted.notna().mul(weights, axis=1).sum(axis=1).replace(0.0, np.nan)
    ext["TSMC_Leadership_Score"] = (weighted.sum(axis=1) / denom).fillna(0.0).clip(-3.0, 3.0).values
