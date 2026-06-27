"""Shared filesystem paths for GroupA+ pipeline modules."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NEWS_DIR = PROJECT_ROOT / "news"

