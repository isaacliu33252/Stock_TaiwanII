from __future__ import annotations

import unittest

from group_a_plus.validation.purged_walk_forward import PurgedWalkForwardSplit


class PurgedWalkForwardSplitTests(unittest.TestCase):
    def test_split_leaves_purge_gap_before_each_test_window(self) -> None:
        splitter = PurgedWalkForwardSplit(
            n_splits=3,
            test_size=10,
            purge=5,
            min_train_size=20,
        )

        splits = list(splitter.split(range(80)))

        self.assertEqual(3, len(splits))
        for train_idx, test_idx in splits:
            self.assertEqual(10, len(test_idx))
            self.assertLess(train_idx[-1], test_idx[0] - 4)
            self.assertEqual(5, test_idx[0] - train_idx[-1] - 1)

    def test_rolling_train_size_caps_training_window(self) -> None:
        splitter = PurgedWalkForwardSplit(
            n_splits=2,
            test_size=8,
            train_size=15,
            purge=3,
            min_train_size=10,
        )

        splits = list(splitter.split(range(60)))

        self.assertEqual(2, len(splits))
        self.assertTrue(all(len(train_idx) == 15 for train_idx, _ in splits))

    def test_auto_test_size_accounts_for_purge_and_min_train(self) -> None:
        splitter = PurgedWalkForwardSplit(n_splits=4, purge=20, min_train_size=80)

        splits = list(splitter.split(range(339)))

        self.assertEqual(4, len(splits))
        for train_idx, test_idx in splits:
            self.assertGreaterEqual(len(train_idx), 80)
            self.assertEqual(20, test_idx[0] - train_idx[-1] - 1)

    def test_rejects_too_few_samples(self) -> None:
        splitter = PurgedWalkForwardSplit(n_splits=4, test_size=10, purge=5, min_train_size=20)

        with self.assertRaisesRegex(ValueError, "Not enough samples"):
            list(splitter.split(range(30)))


if __name__ == "__main__":
    unittest.main()
