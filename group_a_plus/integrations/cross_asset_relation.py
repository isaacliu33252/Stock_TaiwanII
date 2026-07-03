"""NoGraphMixer-lite cross-asset relation features.

This is a feature-only approximation of the paper's implicit cross-asset
relationship idea. It does not fit a neural adjacency matrix; instead it emits
rolling interaction statistics that can be consumed by LightGBM/NCF shadow
evaluations without changing live allocation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


DEFAULT_WINDOWS = (5, 20, 60)


def build_cross_asset_relation_features(
    prices: pd.DataFrame,
    *,
    base: str = "0050.TW",
    leveraged: str = "00631L.TW",
    inverse: str = "00632R.TW",
    bond: str = "00679B.TWO",
    windows: tuple[int, ...] = DEFAULT_WINDOWS,
    prefix: str = "rel",
) -> pd.DataFrame:
    """Build rolling cross-asset relation features from close prices."""

    required = [base, leveraged, inverse, bond]
    missing = [ticker for ticker in required if ticker not in prices.columns]
    if missing:
        raise ValueError(f"missing price columns: {missing}")

    close = prices[required].astype(float).replace(0.0, np.nan).ffill()
    returns = np.log(close).diff()
    out = pd.DataFrame(index=prices.index)

    for window in windows:
        w = int(window)
        if w <= 1:
            raise ValueError("relation windows must be > 1")
        base_ret = returns[base]
        lev_ret = returns[leveraged]
        inv_ret = returns[inverse]
        bond_ret = returns[bond]

        out[f"{prefix}_{w}d_lev_base_corr"] = lev_ret.rolling(w, min_periods=max(3, w // 2)).corr(base_ret)
        out[f"{prefix}_{w}d_inv_base_corr"] = inv_ret.rolling(w, min_periods=max(3, w // 2)).corr(base_ret)
        out[f"{prefix}_{w}d_bond_base_corr"] = bond_ret.rolling(w, min_periods=max(3, w // 2)).corr(base_ret)
        base_var = base_ret.rolling(w, min_periods=max(3, w // 2)).var().replace(0.0, np.nan)
        out[f"{prefix}_{w}d_lev_beta_to_base"] = lev_ret.rolling(w, min_periods=max(3, w // 2)).cov(base_ret) / base_var
        out[f"{prefix}_{w}d_inv_beta_to_base"] = inv_ret.rolling(w, min_periods=max(3, w // 2)).cov(base_ret) / base_var
        out[f"{prefix}_{w}d_inverse_conflict"] = (
            out[f"{prefix}_{w}d_lev_base_corr"].fillna(0.0)
            + out[f"{prefix}_{w}d_inv_base_corr"].fillna(0.0)
        )
        out[f"{prefix}_{w}d_leverage_efficiency"] = (
            lev_ret.rolling(w, min_periods=max(3, w // 2)).sum()
            - 2.0 * base_ret.rolling(w, min_periods=max(3, w // 2)).sum()
        )
        out[f"{prefix}_{w}d_bond_cushion"] = (
            bond_ret.rolling(w, min_periods=max(3, w // 2)).sum()
            - base_ret.rolling(w, min_periods=max(3, w // 2)).sum()
        )

    return out.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def cross_asset_relation_feature_columns(
    *,
    windows: tuple[int, ...] = DEFAULT_WINDOWS,
    prefix: str = "rel",
) -> list[str]:
    suffixes = (
        "lev_base_corr",
        "inv_base_corr",
        "bond_base_corr",
        "lev_beta_to_base",
        "inv_beta_to_base",
        "inverse_conflict",
        "leverage_efficiency",
        "bond_cushion",
    )
    return [f"{prefix}_{window}d_{suffix}" for window in windows for suffix in suffixes]
