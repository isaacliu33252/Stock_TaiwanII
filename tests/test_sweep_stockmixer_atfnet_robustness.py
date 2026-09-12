from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.evaluate.sweep_stockmixer_atfnet_robustness import build_sweep


def _cache(path: Path, tickers: list[str], rows: int = 180) -> Path:
    rng = np.random.default_rng(17)
    dates = pd.bdate_range("2024-01-02", periods=rows)
    parts = {}
    for i, ticker in enumerate(tickers):
        ret = rng.normal(0.0005 + i * 0.00001, 0.01, rows)
        close = 100.0 * np.exp(np.cumsum(ret))
        parts[ticker] = pd.DataFrame({"Adj Close": close, "Close": close}, index=dates)
    pd.concat(parts, axis=1).to_parquet(path)
    return path


def test_stockmixer_atfnet_robustness_stays_shadow_only(tmp_path: Path) -> None:
    tickers = [
        "2330.TW",
        "2454.TW",
        "2308.TW",
        "2317.TW",
        "3711.TW",
        "2303.TW",
        "2327.TW",
        "2383.TW",
        "3037.TW",
        "2345.TW",
        "2891.TW",
        "2881.TW",
    ]
    payload = build_sweep(
        as_of="2026-08-21",
        universe="top15",
        cache_path=_cache(tmp_path / "cache.parquet", tickers),
        seeds=[1],
        n_windows=1,
        train_rows=80,
        val_rows=30,
        test_rows=30,
        epochs=2,
        min_history_days=0,
        lookback=8,
        alpha=0.5,
        top_n=3,
    )

    assert payload["decision"]["research_complete"] is True
    assert payload["decision"]["promote_to_live"] is False
    assert payload["decision"]["target_weight_change_allowed"] is False
    assert payload["decision"]["allow_00631l_add"] is False
    assert payload["decision"]["allow_00632r_open"] is False
    assert "stockmixer_atfnet" in payload["aggregate"]
