#!/usr/bin/env python3
"""A17/A18/A19 stress-only run."""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from compare_group_a_plus_2008_golden_latest import (
    GROUP_A_PLUS_CONFIG, LATEST_MODEL, LATEST_PAYLOAD,
    _capture_model_events, _load_json, _run_group_a_plus,
)
import twii_proxy_utils

A15_STRESS_REF = PROJECT_ROOT / "results" / "group_a_plus_a15_turnover_fine_stress_20260614.json"

VARIANTS = {
    "A17_band_expand": {
        "overlay.dynamic_weight_bands": {
            "risk_on": 0.00, "caution": 0.01,
            "risk_off": 0.03, "severe": 0.06,
        },
    },
    "A18_caution_raise": {
        "overlay.dynamic_weight_bands": {
            "risk_on": 0.00, "caution": 0.03,
            "risk_off": 0.02, "severe": 0.04,
        },
    },
    "A19_band_contract": {
        "overlay.dynamic_weight_bands": {
            "risk_on": 0.02, "caution": 0.03,
            "risk_off": 0.02, "severe": 0.04,
        },
    },
}

def set_nested(d, key, value):
    parts = key.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value

def build_variant_config(base_config, overrides):
    config = copy.deepcopy(base_config)
    for dotpath, value in overrides.items():
        set_nested(config, dotpath, copy.deepcopy(value))
    return config

TWII_CACHES = {
    2007: PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_20030101_20110101_1d_market_v2.parquet",
    2015: PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_DJI_20150101_20161231_1d_market_v3.parquet",
    2016: PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_20160101_20260509_1d_market_v2.parquet",
    2020: PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_DJI_20200101_20260608_1d_market_v3.parquet",
    2022: PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_DJI_20200101_20260608_1d_market_v3.parquet",
}

STRESS_WINDOWS = [
    ("gfc_2008",          2007, "2007-07-01", "2010-12-31"),
    ("china_fx_2015",     2015, "2015-01-01", "2016-12-31"),
    ("china_fx_2016",     2016, "2016-01-01", "2016-12-31"),
    ("covid_2020",        2020, "2020-01-01", "2020-12-31"),
    ("inflation_2022",     2022, "2022-01-01", "2022-12-31"),
]

def run_stress(base_config, variant_name, overrides):
    variant_cfg = build_variant_config(base_config, overrides)
    results = {}

    for label, year, start, end in STRESS_WINDOWS:
        cache = TWII_CACHES.get(year)
        if cache is None or not cache.exists():
            print(f"    [SKIP {label}] no cache year={year}")
            continue
        twii_proxy_utils.DEFAULT_TWII_MARKET_CACHE = cache
        try:
            captured = _capture_model_events(
                name=f"group_a_{variant_name}_{label}",
                payload_path=LATEST_PAYLOAD,
                model_path=LATEST_MODEL,
                start=start, end=end,
            )
        except Exception as exc:
            print(f"    [SKIP {label}] capture error: {exc}")
            continue

        plus = _run_group_a_plus(captured, variant_cfg)
        base_m = captured["base_metrics"]
        plus_m = plus["metrics"]
        results[label] = {
            "base_final":   base_m["final_value"],
            "plus_final":    plus_m["final_value"],
            "delta_final":  plus_m["final_value"] - base_m["final_value"],
            "base_sharpe":  base_m["sharpe_ratio"],
            "plus_sharpe":  plus_m["sharpe_ratio"],
            "delta_sharpe": plus_m["sharpe_ratio"] - base_m["sharpe_ratio"],
            "base_mdd":     base_m["max_drawdown"],
            "plus_mdd":     plus_m["max_drawdown"],
            "delta_mdd":    plus_m["max_drawdown"] - base_m["max_drawdown"],
        }
        print(f"    {label}: dF={results[label]['delta_final']:+,.0f}  "
              f"dSh={results[label]['delta_sharpe']:+.4f}  "
              f"dMDD={results[label]['delta_mdd']:+.4f}")
    return results

def main():
    print("=" * 70)
    print("Group A+ A17/A18/A19 Stress Experiment")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    base_config = _load_json(GROUP_A_PLUS_CONFIG)
    a15_stress = _load_json(A15_STRESS_REF) if A15_STRESS_REF.exists() else {}

    output = {
        "experiment": "group_a_plus_a17_a18_a19_stress",
        "generated_at": datetime.now().isoformat(),
        "a15_stress_ref": A15_STRESS_REF.name,
        "variants": {},
    }

    for variant_name, overrides in VARIANTS.items():
        print(f"\n{'='*60}")
        print(f"  {variant_name}")
        print(f"{'='*60}")
        stress_results = run_stress(base_config, variant_name, overrides)
        output["variants"][variant_name] = {
            "overrides": overrides,
            "stress": stress_results,
        }

    out_path = PROJECT_ROOT / "results" / "group_a_plus_a17_a18_a19_stress_20260615.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {out_path}")

    # Comparison table
    print("\n" + "=" * 100)
    print("STRESS DELTA (plus - base)")
    print("=" * 100)
    windows = ["gfc_2008", "china_fx_2015", "china_fx_2016", "covid_2020", "inflation_2022"]
    hdr = f"{'Variant':<22}" + "".join(f" {w[:10]:>13}" for w in windows)
    print(hdr)
    print("-" * 100)

    # A15 ref row
    a15_strats = a15_stress.get("strategies", {})
    vals = []
    for w in windows:
        wd = a15_strats.get(w, {}).get("profiles", {}).get("focused_tdcc_0124_stab5_turn14_fast_cd3", {})
        bm = a15_strats.get(w, {}).get("base_metrics", {})
        if wd and bm:
            vals.append(f"{wd.get('metrics',{}).get('final_value',0) - bm.get('final_value',0):+13,.0f}")
        else:
            vals.append(f"{'N/A':>13}")
    print(f"{'A15 reference':<22}" + "".join(f" {v}" for v in vals))

    for variant_name in VARIANTS:
        stress = output["variants"].get(variant_name, {}).get("stress") or {}
        vals = []
        for w in windows:
            d = stress.get(w, {}).get("delta_final", 0)
            vals.append(f"{d:+13,.0f}" if d else f"{'N/A':>13}")
        print(f"{variant_name:<22}" + "".join(f" {v}" for v in vals))

if __name__ == "__main__":
    main()
