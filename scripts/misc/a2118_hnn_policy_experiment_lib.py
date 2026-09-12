"""MFCF/HNN sparse feature extractor for a2118's PPO policy -- EXPERIMENT ONLY.

Adapts the same MFCF-derived clique-structured sparse architecture validated
in group_a_plus/integrations/mfcf_hnn_volatility_shadow.py (arXiv:2608.14323
pilot, 2026-08-20) to stable-baselines3's PPO, as a drop-in replacement for
the default MlpPolicy's flat fully-connected feature extractor.

This is the ONE place flagged (but not touched) in both the RG-ResMoE and
MFCF/HNN volatility pilots this session: a2118's "Last PPO" observation
vector concatenates ~30-40 correlated per-ticker technical features + a few
portfolio-state scalars into one flat MLP input -- structurally the same
"many correlated features, hand-tuned architecture" situation the paper
studies, but for an RL policy/value network instead of supervised
regression. Unlike the volatility pilot, there is no existing evidence this
transfers to PPO's very different (reward-driven, on-policy, small-batch)
optimization regime -- that is exactly what this experiment tests.

Deviation from the volatility pilot's HNN: that one reads out a single
scalar per layer (built for regression). Here we need a FEATURE VECTOR for
SB3's actor/critic heads, so HNNFeatureBody concatenates every non-input
layer's activations (h(2), h(3), ..., h(K*)) instead of collapsing them to
one number -- keeping the paper's "every clique order contributes directly"
design principle, just feeding it into policy/value linear heads instead of
a regression readout.

SAFETY: this module and its companion training script never import from or
write to any production path. Model checkpoints must be saved under
models/portfolio/experiment_* -- never overwrite last_ppo_group_a_100k.zip
or group_a_production_2020_2025_100k.zip.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from torch import nn

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from group_a_plus.integrations.mfcf_hnn_volatility_shadow import (
    build_layer_structure,
    build_mfcf_forest,
)

DEFAULT_MAX_CLIQUE_SIZE = 4


class HNNFeatureBody(nn.Module):
    """Clique-structured sparse layers, concatenated-activation output (no
    regression readout -- see module docstring for why this differs from
    mfcf_hnn_volatility_shadow.HNN).
    """

    def __init__(self, layers: dict[int, list[frozenset]]):
        super().__init__()
        self.k_star = max(layers.keys())
        self.n1 = len(layers[1])
        index1 = {u: i for i, u in enumerate(layers[1])}

        self.masks: dict[int, torch.Tensor] = {}
        self.linears = nn.ModuleDict()
        prev_index = index1
        n_prev = self.n1
        out_dim = 0
        for k in range(2, self.k_star + 1):
            units_k = layers[k]
            n_k = len(units_k)
            index_k = {u: i for i, u in enumerate(units_k)}
            mask = torch.zeros(n_k, n_prev)
            for u, i in index_k.items():
                for tau in _order_minus_one_subsets(u):
                    j = prev_index.get(tau)
                    if j is not None:
                        mask[i, j] = 1.0
            self.masks[k] = mask
            self.linears[str(k)] = nn.Linear(n_prev, n_k)
            self.linears[f"ln{k}"] = nn.LayerNorm(n_k)
            prev_index = index_k
            n_prev = n_k
            out_dim += n_k
        self.output_dim = out_dim

    def _masked_weight(self, k: int) -> torch.Tensor:
        lin = self.linears[str(k)]
        mask = self.masks[k].to(lin.weight.device)
        return lin.weight * mask

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = x
        parts = []
        for k in range(2, self.k_star + 1):
            lin = self.linears[str(k)]
            w = self._masked_weight(k)
            z = torch.nn.functional.linear(h, w, lin.bias)
            z = self.linears[f"ln{k}"](z)
            h = torch.relu(z)
            parts.append(h)
        return torch.cat(parts, dim=-1)


def _order_minus_one_subsets(u: frozenset) -> list[frozenset]:
    from itertools import combinations

    return [frozenset(c) for c in combinations(sorted(u), len(u) - 1)]


def build_hnn_layers_from_samples(
    samples: np.ndarray, *, max_clique_size: int = DEFAULT_MAX_CLIQUE_SIZE
) -> tuple[dict[int, list[frozenset]], np.ndarray]:
    """Build the MFCF clique-forest layer structure from sampled raw
    observations (rows = timesteps, cols = obs dims), returning the layer
    structure and the column permutation that maps obs index -> H(1) node
    order (feed observations through this permutation before the body).
    """
    mean = samples.mean(axis=0)
    std = samples.std(axis=0)
    std[std < 1e-8] = 1.0
    std_samples = (samples - mean) / std
    corr = np.abs(np.corrcoef(std_samples.T))
    corr = np.nan_to_num(corr, nan=0.0, posinf=1.0, neginf=0.0)
    forest = build_mfcf_forest(corr, max_clique_size)
    layers = build_layer_structure(forest, max_clique_size)
    col_perm = np.array([next(iter(u)) for u in layers[1]], dtype=int)
    return layers, col_perm


class HNNFeaturesExtractor(BaseFeaturesExtractor):
    """SB3-compatible wrapper: reorders raw obs into MFCF node order, runs
    HNNFeatureBody, exposes the concatenated activations as `features_dim`.
    """

    def __init__(self, observation_space, layers: dict[int, list[frozenset]], col_perm: np.ndarray):
        body = HNNFeatureBody(layers)
        super().__init__(observation_space, features_dim=body.output_dim)
        self.body = body
        self.register_buffer("col_perm", torch.tensor(col_perm, dtype=torch.long))

    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        x = observations.index_select(1, self.col_perm)
        return self.body(x)
