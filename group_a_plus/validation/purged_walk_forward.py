"""Purged walk-forward split utilities.

The splitter is intentionally small and index-position based. It supports the
common financial-validation pattern where each fold trains only on observations
strictly before the test window, with a purge gap between train and test to
avoid label-horizon leakage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import numpy as np


@dataclass(frozen=True)
class PurgedWalkForwardSplit:
    """Expanding or rolling walk-forward splitter with a pre-test purge gap.

    Parameters
    ----------
    n_splits:
        Number of test windows.
    test_size:
        Number of rows per test window. If omitted, uses
        ``n_samples // (n_splits + 1)``.
    train_size:
        Optional maximum train rows. Omit for expanding-window training.
    purge:
        Number of rows removed immediately before each test window.
    min_train_size:
        Minimum rows required for a fold to be emitted.
    """

    n_splits: int = 4
    test_size: int | None = None
    train_size: int | None = None
    purge: int = 0
    min_train_size: int = 20

    def __post_init__(self) -> None:
        if self.n_splits < 1:
            raise ValueError("n_splits must be >= 1")
        if self.test_size is not None and self.test_size < 1:
            raise ValueError("test_size must be >= 1")
        if self.train_size is not None and self.train_size < 1:
            raise ValueError("train_size must be >= 1")
        if self.purge < 0:
            raise ValueError("purge must be >= 0")
        if self.min_train_size < 1:
            raise ValueError("min_train_size must be >= 1")

    def split(self, x) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        n_samples = len(x)
        if self.test_size is None:
            available_for_tests = n_samples - self.min_train_size - self.purge
            test_size = max(1, available_for_tests // self.n_splits)
        else:
            test_size = self.test_size
        required = self.n_splits * test_size + self.purge + self.min_train_size
        if n_samples < required:
            raise ValueError(
                "Not enough samples for purged walk-forward split: "
                f"n_samples={n_samples}, required>={required}"
            )

        first_test_start = n_samples - self.n_splits * test_size
        for fold in range(self.n_splits):
            test_start = first_test_start + fold * test_size
            test_end = test_start + test_size
            train_end = test_start - self.purge
            if train_end < self.min_train_size:
                continue
            train_start = 0 if self.train_size is None else max(0, train_end - self.train_size)
            train_idx = np.arange(train_start, train_end, dtype=int)
            test_idx = np.arange(test_start, min(test_end, n_samples), dtype=int)
            if len(train_idx) >= self.min_train_size and len(test_idx) > 0:
                yield train_idx, test_idx


def purged_walk_forward_splits(
    n_samples: int,
    *,
    n_splits: int = 4,
    test_size: int | None = None,
    train_size: int | None = None,
    purge: int = 0,
    min_train_size: int = 20,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Return purged walk-forward splits for simple callers/tests."""

    splitter = PurgedWalkForwardSplit(
        n_splits=n_splits,
        test_size=test_size,
        train_size=train_size,
        purge=purge,
        min_train_size=min_train_size,
    )
    return list(splitter.split(range(n_samples)))
