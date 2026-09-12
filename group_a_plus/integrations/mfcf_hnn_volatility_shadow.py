"""MFCF/HNN dependence-informed sparse architecture pilot for 0050.TW volatility.

Research-only pilot inspired by arXiv:2608.14323 ("Dependence-Informed Sparse
Neural Architecture for Stock Return Prediction", Lin/Chen/Wang/Briola/Aste,
UCL). The paper's core claim is architectural, not a trading rule: instead of
hand-choosing an MLP's depth and hidden-layer widths, estimate dependence
among input features with a Maximally Filtered Clique Forest (MFCF), then map
the resulting clique structure directly to a Homological Neural Network
(HNN) -- each retained k-way clique subset becomes a neural unit, and
connections follow set inclusion. On the GKX 94-characteristic US equity
panel this matched a hand-tuned 3-hidden-layer MLP on accuracy, ranked the
cross-section better, and used ~80x fewer parameters than a width-matched
dense network.

GroupA+ has no 94-characteristic cross-sectional panel; the closest genuine
analogue is the 55-indicator technical feature set already computed by
FinRL/v2/data/technical_indicators.py for the RL policy's state vector (see
GROUP_A_PLUS_RG_RESMOE_VOLATILITY_GATE_PILOT_HANDOFF_20260820.md for the same
observation re: a2118's flat PPO input). Rather than touching the live PPO
policy directly, this pilot tests the paper's core architectural claim on a
lower-risk, already-instrumented supervised task: forecasting 0050.TW future
realized (Garman-Klass) variance from those 55 technical indicators, reusing
the walk-forward/QLIKE evaluation machinery from volatility_forecast.py and
rg_resmoe_volatility_gate_shadow.py.

MFCF implementation note: this is a practical, documented approximation of
Previde Massara & Aste (2019, arXiv:1905.02266)'s clique-forest algorithm,
not a byte-for-byte port. It uses the same attachment score G(v,S) = sum_{u
in S} D_vu^2 and the same K-bounded-clique output structure, but a simplified
greedy search (grow the highest-gain existing under-full clique, branch a new
clique off the single best-correlated member of a full clique, or seed an
entirely new clique from the best remaining unplaced pair -- whichever has
the highest score at each step). Verified on real 0050.TW technical-indicator
correlations to recover semantically coherent groups (MA3/5/10/20 together,
KDJ K/D/J together, OBV/obv_ma10/obv_slope together, etc.) before being used
here.

This module only produces forecasts; it does not change any target weight.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import torch
from torch import nn

DEFAULT_MAX_CLIQUE_SIZE = 4
DEFAULT_HIDDEN_MULT = 1.0


def build_mfcf_forest(D: np.ndarray, max_clique_size: int) -> list[list[int]]:
    """Greedy K-bounded clique-forest construction from an |correlation| matrix.

    See module docstring for the documented deviation from the reference
    MFCF algorithm.
    """
    p = D.shape[0]
    remaining = set(range(p))
    forest: list[list[int]] = []

    def best_new_seed() -> tuple[float, int | None, int | None]:
        best = (-1.0, None, None)
        rem = list(remaining)
        for i in range(len(rem)):
            for j in range(i + 1, len(rem)):
                u, v = rem[i], rem[j]
                if D[u, v] > best[0]:
                    best = (float(D[u, v]), u, v)
        return best

    def best_attach() -> tuple[float, int | None, int | None, list[int] | None]:
        best: tuple[float, int | None, int | None, list[int] | None] = (-1.0, None, None, None)
        for v in remaining:
            for ci, C in enumerate(forest):
                if len(C) < max_clique_size:
                    S = C
                else:
                    S = [max(C, key=lambda u: D[v, u])]
                gain = float(sum(D[v, u] ** 2 for u in S))
                if gain > best[0]:
                    best = (gain, v, ci, S)
        return best

    while remaining:
        seed_gain, su, sv = best_new_seed() if len(remaining) >= 2 else (-1.0, None, None)
        attach_gain, av, aci, asep = best_attach() if forest else (-1.0, None, None, None)
        if forest and attach_gain >= seed_gain:
            C = forest[aci]
            if len(C) < max_clique_size:
                C.append(av)
            else:
                forest.append(list(asep) + [av])
            remaining.discard(av)
        else:
            forest.append([su, sv])
            remaining -= {su, sv}
    return forest


def build_layer_structure(forest: list[list[int]], max_clique_size: int) -> dict[int, list[frozenset]]:
    """H(k): distinct order-k subsets of any clique in the forest, for k=1..K*."""
    from itertools import combinations

    layers: dict[int, set[frozenset]] = {k: set() for k in range(1, max_clique_size + 1)}
    for C in forest:
        for k in range(1, min(len(C), max_clique_size) + 1):
            for combo in combinations(sorted(C), k):
                layers[k].add(frozenset(combo))
    k_star = max(k for k, units in layers.items() if units)
    return {k: sorted(layers[k], key=lambda s: sorted(s)) for k in range(1, k_star + 1)}


class HNN(nn.Module):
    """Homological Neural Network: clique-structured sparse layers + all-layer readout.

    `dense`=True turns this into the paper's MLP-HNN control: same induced
    layer widths, fully connected weights instead of the sparse clique mask,
    prediction from the last layer only instead of the summed all-layer
    readout (matching the paper's Section 3.3 description).
    """

    def __init__(self, layers: dict[int, list[frozenset]], *, dense: bool = False):
        super().__init__()
        self.k_star = max(layers.keys())
        self.layer_units = layers
        self.dense = dense
        self.n1 = len(layers[1])
        self.index1 = {u: i for i, u in enumerate(layers[1])}

        self.masks: dict[int, torch.Tensor] = {}
        self.linears = nn.ModuleDict()
        self.readout_a = nn.ParameterDict()
        self.readout_c = nn.ParameterDict()
        self.readout_beta = nn.ParameterDict()

        prev_index = self.index1
        n_prev = self.n1
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
            self.masks[k] = mask if not dense else torch.ones_like(mask)
            self.linears[str(k)] = nn.Linear(n_prev, n_k)
            self.linears[f"ln{k}"] = nn.LayerNorm(n_k)
            if not dense:
                self.readout_a[str(k)] = nn.Parameter(torch.randn(n_k) * 0.01)
                self.readout_c[str(k)] = nn.Parameter(torch.zeros(1))
                self.readout_beta[str(k)] = nn.Parameter(torch.zeros(1))
            prev_index = index_k
            n_prev = n_k
        if dense:
            self.head = nn.Linear(n_prev, 1)
        else:
            self.head_bias = nn.Parameter(torch.zeros(1))

    def _masked_weight(self, k: int) -> torch.Tensor:
        lin = self.linears[str(k)]
        mask = self.masks[k].to(lin.weight.device)
        return lin.weight * mask

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = x
        readout_sum = None
        for k in range(2, self.k_star + 1):
            lin = self.linears[str(k)]
            w = self._masked_weight(k)
            z = torch.nn.functional.linear(h, w, lin.bias)
            z = self.linears[f"ln{k}"](z)
            h = torch.relu(z)
            if not self.dense:
                r = h @ self.readout_a[str(k)] + self.readout_c[str(k)]
                contrib = self.readout_beta[str(k)] * r
                readout_sum = contrib if readout_sum is None else readout_sum + contrib
        if self.dense:
            return self.head(h).squeeze(-1)
        return readout_sum + self.head_bias

    def param_count(self) -> int:
        """Effective trainable parameter count.

        PyTorch's nn.Linear always allocates a dense weight tensor even when
        we mask most of it to zero for the forward pass (masked entries get
        zero gradient and never move from their random init, but naively
        summing `p.numel()` over `.parameters()` would still count them).
        For a fair "N times fewer parameters" comparison against the dense
        control (matching the paper's Table 2 Params. column), only count
        biases, readout parameters, and the nonzero mask entries.
        """
        total = 0
        for k in range(2, self.k_star + 1):
            lin = self.linears[str(k)]
            total += int(lin.bias.numel())
            if self.dense:
                total += int(lin.weight.numel())
            else:
                total += int(self.masks[k].sum().item())
            ln = self.linears[f"ln{k}"]
            total += int(sum(p.numel() for p in ln.parameters()))
        if self.dense:
            total += int(sum(p.numel() for p in self.head.parameters()))
        else:
            for k in range(2, self.k_star + 1):
                total += int(self.readout_a[str(k)].numel())
                total += int(self.readout_c[str(k)].numel())
                total += int(self.readout_beta[str(k)].numel())
            total += int(self.head_bias.numel())
        return total


def _order_minus_one_subsets(u: frozenset) -> list[frozenset]:
    from itertools import combinations

    return [frozenset(c) for c in combinations(sorted(u), len(u) - 1)]


def build_hnn_from_correlation(
    corr_abs: np.ndarray,
    feature_names: list[str],
    *,
    max_clique_size: int = DEFAULT_MAX_CLIQUE_SIZE,
    shuffle_seed: int | None = None,
    dense: bool = False,
) -> tuple[HNN, list[str]]:
    """Build an HNN (or its dense/shuffled control) from a feature correlation matrix.

    `shuffle_seed`, when set, permutes which feature occupies which graph
    node before the mask is built (paper's HNN (input-shuffled) ablation):
    topology and parameter count are identical, only feature-to-node
    alignment changes.
    """
    corr_abs = np.nan_to_num(corr_abs, nan=0.0, posinf=1.0, neginf=0.0)
    forest = build_mfcf_forest(corr_abs, max_clique_size)
    layers = build_layer_structure(forest, max_clique_size)
    ordered_names = [feature_names[next(iter(u))] for u in layers[1]]
    if shuffle_seed is not None:
        rng = np.random.default_rng(shuffle_seed)
        perm = rng.permutation(len(ordered_names))
        ordered_names = [ordered_names[i] for i in perm]
    model = HNN(layers, dense=dense)
    return model, ordered_names


class _AffineOutputWrapper(nn.Module):
    """Wraps a model trained on a standardized target so forward() returns
    the original scale transparently. Log-variance targets sit around -9 to
    -12 with near-zero variance across a single-instrument training window;
    without this, a freshly-initialized network's near-zero output has to be
    dragged across that whole range by gradient descent alone, and a modest
    epoch budget can leave it stuck at a roughly constant, badly-off-scale
    prediction (caught empirically: an early un-normalized run collapsed to
    a single value ~2 orders of magnitude off across the whole test set --
    an optimization artifact of the harness, not a real finding about dense
    vs. sparse architectures).
    """

    def __init__(self, base: nn.Module, y_mean: float, y_std: float):
        super().__init__()
        self.base = base
        self.register_buffer("y_mean", torch.tensor(float(y_mean)))
        self.register_buffer("y_std", torch.tensor(float(y_std)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.base(x) * self.y_std + self.y_mean

    def param_count(self) -> int:
        return self.base.param_count()


def train_hnn(
    model: nn.Module,
    x_train: np.ndarray,
    y_train: np.ndarray,
    *,
    epochs: int = 150,
    lr: float = 3e-3,
    val_frac: float = 0.15,
    patience: int = 15,
    seed: int = 0,
) -> nn.Module:
    torch.manual_seed(seed)
    n = len(x_train)
    n_val = max(20, int(n * val_frac))

    y_mean = float(y_train[:-n_val].mean())
    y_std = float(y_train[:-n_val].std())
    if y_std < 1e-8:
        y_std = 1.0
    y_standardized = (y_train - y_mean) / y_std

    x_t = torch.tensor(x_train, dtype=torch.float32)
    y_t = torch.tensor(y_standardized, dtype=torch.float32)
    x_tr, y_tr = x_t[:-n_val], y_t[:-n_val]
    x_val, y_val = x_t[-n_val:], y_t[-n_val:]

    opt = torch.optim.Adam(model.parameters(), lr=lr)
    best_val = float("inf")
    best_state = None
    bad_epochs = 0
    for _epoch in range(epochs):
        model.train()
        opt.zero_grad()
        pred = model(x_tr)
        loss = torch.nn.functional.mse_loss(pred, y_tr)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        model.eval()
        with torch.no_grad():
            val_loss = torch.nn.functional.mse_loss(model(x_val), y_val).item()
        if val_loss < best_val - 1e-6:
            best_val = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            bad_epochs = 0
        else:
            bad_epochs += 1
            if bad_epochs >= patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    return _AffineOutputWrapper(model, y_mean, y_std)
