"""Research-only MINGLE-lite diversification diagnostics.

This is a bounded adaptation of arXiv:2608.06618 for GroupA+.  It does not
implement the paper's full ADMM optimiser.  Instead, it uses rolling PCA factor
exposures to build an exposure-similarity graph and reports whether a target
portfolio is concentrated in central, similar-exposure assets.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MingleLiteFrame:
    exposures: pd.DataFrame
    graph: pd.DataFrame
    peripheral_score: pd.Series
    sample_condition_number: float
    factor_condition_number: float
    factor_count: int
    observations: int


def _condition_number(matrix: np.ndarray) -> float:
    eig = np.linalg.eigvalsh(np.asarray(matrix, dtype=float))
    eig = eig[np.isfinite(eig)]
    positive = eig[eig > 1e-12]
    if len(positive) == 0:
        return float("inf")
    return float(positive.max() / positive.min())


def _weighted_centered_returns(prices: pd.DataFrame, *, decay: float) -> pd.DataFrame:
    returns = np.log(prices.astype(float)).diff().replace([np.inf, -np.inf], np.nan).dropna(how="any")
    if returns.empty:
        return returns
    weights = np.asarray([float(decay) ** i for i in range(len(returns) - 1, -1, -1)], dtype=float)
    weights = weights / weights.sum()
    mean = pd.Series(np.average(returns.to_numpy(), axis=0, weights=weights), index=returns.columns)
    return returns.sub(mean, axis=1).mul(np.sqrt(weights), axis=0)


def build_mingle_lite_frame(
    prices: pd.DataFrame,
    *,
    factor_count: int = 3,
    decay: float = 0.997,
    ridge: float = 1e-6,
) -> MingleLiteFrame:
    """Build a PCA exposure graph and denoised covariance diagnostics."""

    clean = prices.sort_index().ffill().dropna(axis=1, thresh=20).dropna(how="any")
    if clean.shape[1] < 3:
        raise ValueError("MINGLE-lite requires at least 3 assets")
    weighted = _weighted_centered_returns(clean, decay=decay)
    if len(weighted) < 20:
        raise ValueError("MINGLE-lite requires at least 20 return observations")

    x = weighted.T.to_numpy(dtype=float)
    u, s, vt = np.linalg.svd(x, full_matrices=False)
    k = max(1, min(int(factor_count), clean.shape[1] - 1, len(s)))
    b = u[:, :k]
    factors = np.diag(s[:k]) @ vt[:k, :]
    reconstructed = b @ factors
    residual = x - reconstructed
    factor_cov = b @ np.cov(factors) @ b.T + np.diag(np.var(residual, axis=1) + float(ridge))
    sample_cov = np.cov(x)

    exposures = pd.DataFrame(b, index=clean.columns, columns=[f"factor_{i + 1}" for i in range(k)])
    distances = np.sum((b[:, None, :] - b[None, :, :]) ** 2, axis=2)
    scale = float(np.median(distances[distances > 0])) if np.any(distances > 0) else 1.0
    graph_values = np.exp(-distances / max(2.0 * scale, 1e-12))
    np.fill_diagonal(graph_values, 0.0)
    graph = pd.DataFrame(graph_values, index=clean.columns, columns=clean.columns)
    degree = graph.sum(axis=1)
    peripheral = 1.0 / (degree + float(ridge))
    peripheral = peripheral / peripheral.sum()
    peripheral.name = "mingle_lite_peripheral_score"

    return MingleLiteFrame(
        exposures=exposures,
        graph=graph,
        peripheral_score=peripheral,
        sample_condition_number=_condition_number(sample_cov),
        factor_condition_number=_condition_number(factor_cov),
        factor_count=k,
        observations=int(len(weighted)),
    )


def summarize_target_diversification(frame: MingleLiteFrame, target_weights: dict[str, float]) -> dict[str, Any]:
    risky = {ticker: max(float(target_weights.get(ticker, 0.0) or 0.0), 0.0) for ticker in frame.exposures.index}
    total = sum(risky.values())
    normalized = {ticker: value / total for ticker, value in risky.items()} if total > 0.0 else {ticker: 0.0 for ticker in risky}
    weights = pd.Series(normalized, index=frame.exposures.index).astype(float)
    graph = frame.graph.reindex(index=weights.index, columns=weights.index).fillna(0.0)
    exposure_similarity_concentration = float(weights.to_numpy() @ graph.to_numpy(dtype=float) @ weights.to_numpy())
    peripheral_alignment = float(weights.reindex(frame.peripheral_score.index).fillna(0.0).dot(frame.peripheral_score))
    degree = graph.sum(axis=1)
    weighted_degree = float(weights.dot(degree))
    top_central = degree.sort_values(ascending=False).head(3)
    top_peripheral = frame.peripheral_score.sort_values(ascending=False).head(3)
    return {
        "risky_weight_sum": float(total),
        "normalized_risky_weights": {ticker: float(value) for ticker, value in normalized.items() if value > 0.0},
        "exposure_similarity_concentration": exposure_similarity_concentration if isfinite(exposure_similarity_concentration) else None,
        "weighted_graph_degree": weighted_degree if isfinite(weighted_degree) else None,
        "peripheral_alignment": peripheral_alignment if isfinite(peripheral_alignment) else None,
        "top_central_assets": {str(k): float(v) for k, v in top_central.items()},
        "top_peripheral_assets": {str(k): float(v) for k, v in top_peripheral.items()},
    }
