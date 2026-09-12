#!/usr/bin/env python3
"""NCF_00713 wrapper using the standard ETF NCF pipeline."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.misc import ncf_0050 as base


base.TICKER = "00713.TW"
base.DEFAULT_OUTPUT = base.PROJECT_ROOT / "results" / f"ncf_00713_{datetime.now().strftime('%Y%m%d')}.json"


if __name__ == "__main__":
    base.main()
