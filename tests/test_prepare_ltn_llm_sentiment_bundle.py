#!/usr/bin/env python3
"""Tests for Liberty Times sentiment bundle preparation helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from prepare_ltn_llm_sentiment_bundle import (
    deduplicate_records,
    iter_input_paths,
    read_jsonl_records,
)


class PrepareLtnLlmSentimentBundleTests(unittest.TestCase):
    def test_deduplicate_records_prefers_unique_url(self) -> None:
        records = [
            {"date": "2024-01-01", "source": "自由時報", "title": "A", "url": "https://example.com/a", "category": "財經", "snippet": "x"},
            {"date": "2024-01-01", "source": "自由時報", "title": "A2", "url": "https://example.com/a", "category": "財經", "snippet": "y"},
            {"date": "2024-01-02", "source": "自由時報", "title": "B", "url": "", "category": "財經", "snippet": "z"},
            {"date": "2024-01-02", "source": "自由時報", "title": "B", "url": "", "category": "財經", "snippet": "z"},
        ]
        deduped = deduplicate_records(records)
        self.assertEqual(len(deduped), 2)

    def test_iter_input_paths_excludes_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "ltn_mainstream_2020-02-01.jsonl").write_text("", encoding="utf-8")
            (root / "ltn_mainstream_2020-02.jsonl").write_text("", encoding="utf-8")
            (root / "ignore.jsonl").write_text("", encoding="utf-8")
            paths = iter_input_paths(
                root,
                include_glob="ltn_mainstream_*.jsonl",
                exclude_names={"ltn_mainstream_2020-02-01.jsonl"},
            )
            self.assertEqual([path.name for path in paths], ["ltn_mainstream_2020-02.jsonl"])

    def test_read_jsonl_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "ltn_mainstream_2020-02.jsonl"
            path.write_text(
                '{"date":"2020-02-01","source":"自由時報","title":"A","url":"https://example.com/a","category":"財經","snippet":"s"}\n',
                encoding="utf-8",
            )
            records, counts = read_jsonl_records([path])
            self.assertEqual(len(records), 1)
            self.assertEqual(counts[path.name], 1)
            self.assertEqual(records[0]["title"], "A")


if __name__ == "__main__":
    unittest.main()
