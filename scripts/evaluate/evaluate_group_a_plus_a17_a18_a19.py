#!/usr/bin/env python3
"""A17/A18/A19 experiments for Group A+.

A17: TDCC band expansion — risk_off 2%→3%, severe 4%→6%
A18: caution band raise — caution 1%→3%
A19: TDCC band contraction — risk_on 0%→2%, caution 1%→3%
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_overlay import (
    _variant_config,
    _load_prices,
    DEFAULT_SOURCE,
    DEFAULT_DCA_SOURCE,
)
from compare_group_a_plus_2008_golden_latest import (
    GROUP_A_PLUS_CONFIG,
    LATEST_MODEL,
    LATEST_PAYLOAD,
    _capture_model_events,
    _load_json,
    _run_group_a_plus,
)
import twii_proxy_utils

# ── A15 reference ────────────────────────────────────────────────────────────
A15_REPLAY_REF = PROJECT_ROOT / "results" / "group_a_plus_a15_turnover_fine_replay_20260614.json"
A15_STRESS_REF = PROJECT_ROOT / "results" / "group_a_plus_a15_turnover_fine_stress_20260614.json"

# ── Variant definitions ──────────────────────────────────────────────────────
VARIANTS: dict[str, dict[str, Any]] = {
    "A17_band_expand": {
        "overlay.dynamic_weight_bands": {
            "risk_on": 0.00,
            "caution": 0.01,
            "risk_off": 0.03,  # A15: 0.02 → 0.03
            "severe": 0.06,    # A15: 0.04 → 0.06
        },
    },
    "A18_caution_raise": {
        "overlay.dynamic_weight_bands": {
            "risk_on": 0.00,
            "caution": 0.03,  # A15: 0.01 → 0.03
            "risk_off": 0.02,
            "severe": 0.04,
        },
    },
    "A19_band_contract": {
        "overlay.dynamic_weight_bands": {
            "risk_on": 0.02,   # A15: 0.00 → 0.02
            "caution": 0.03,   # A15: 0.01 → 0.03
            "risk_off": 0.02,
            "severe": 0.04,
        },
    },
}

# ── Helpers ──────────────────────────────────────────────────────────────────

def set_nested(d: dict, key: str, value: Any) -> None:
    parts = key.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def build_variant_config(base_config: dict, overrides: dict) -> dict:
    config = copy.deepcopy(base_config)
    for dotpath, value in overrides.items():
        set_nested(config, dotpath, copy.deepcopy(value))
    return config


TWII_CACHES = {
    2007: PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_20030101_20110101_1d_market_v2.parquet",
    2015: PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_DJI_20150101_20161231_1d_market_v3.parquet",
    2016: PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_20160101_20260509_1d_market_v2.parquet",
    2020: PROJECT_ROOT / "FinRL" / "data" / "portfolio_cache" / "TWII_DJI_20200101_20260608_1d_market_v3.parquet",
}

STRESS_WINDOWS = [
    ("gfc_2008",           2007, "2007-07-01", "2010-12-31"),
    ("china_fx_2015",      2015, "2015-01-01", "2016-12-31"),
    ("china_fx_2016",      2016, "2016-01-01", "2016-12-31"),
    ("covid_2020",         2020, "2020-01-01", "2020-12-31"),
    ("inflation_2022",      2022, "2022-01-01", "2022-12-31"),
]


def run_replay(base_config: dict, variant_name: str, overrides: dict) -> dict | None:
    """Run overlay replay for 2025-01 ~ 2026-06."""
    variant_cfg = build_variant_config(base_config, overrides)
    source = _load_json(DEFAULT_SOURCE)
    dca_backtest = _load_json(DEFAULT_DCA_SOURCE)
    prices = _load_prices("2025-01-02", "2026-06-05")

    # Use backtest_group_a_plus_overlay main logic via subprocess (single variant)
    # We call the script directly with the patched config
    import subprocess, tempfile, os

    # Write temp config
    tmp_config = PROJECT_ROOT / "results" / f"_tmp_config_{variant_name}.json"
    with open(tmp_config, "w", encoding="utf-8") as f:
        json.dump(variant_cfg, f, ensure_ascii=False)

    output_path = PROJECT_ROOT / "results" / f"group_a_plus_{variant_name}_replay_20260615.json"
    cmd = [
        sys.executable, str(PROJECT_ROOT / "backtest_group_a_plus_overlay.py"),
        "--config", str(tmp_config),
        "--plus-variants", "focused_tdcc_0124_stab5_turn14_fast_cd3",
        "--output", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    tmp_config.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"    REPLAY FAILED:\n{result.stderr[-800:]}")
        return None
    try:
        return _load_json(output_path)
    except Exception as e:
        print(f"    Could not load result: {e}")
        return None


def run_stress(base_config: dict, variant_name: str, overrides: dict) -> dict | None:
    """Run stress windows."""
    variant_cfg = build_variant_config(base_config, overrides)
    results: dict[str, Any] = {}

    for label, year, start, end in STRESS_WINDOWS:
        cache = TWII_CACHES.get(year)
        if cache is None or not cache.exists():
            print(f"    [SKIP {label}] no cache")
            continue
        twii_proxy_utils.DEFAULT_TWII_MARKET_CACHE = cache
        try:
            captured = _capture_model_events(
                name=f"group_a_{variant_name}_{label}",
                payload_path=LATEST_PAYLOAD,
                model_path=LATEST_MODEL,
                start=start,
                end=end,
            )
        except Exception as exc:
            print(f"    [SKIP {label}] capture error: {exc}")
            continue

        plus = _run_group_a_plus(captured, variant_cfg)
        base_m = captured["base_metrics"]
        plus_m = plus["metrics"]
        results[label] = {
            "base_final": base_m["final_value"],
            "plus_final": plus_m["final_value"],
            "delta_final": plus_m["final_value"] - base_m["final_value"],
            "base_sharpe": base_m["sharpe_ratio"],
            "plus_sharpe": plus_m["sharpe_ratio"],
            "delta_sharpe": plus_m["sharpe_ratio"] - base_m["sharpe_ratio"],
            "base_mdd": base_m["max_drawdown"],
            "plus_mdd": plus_m["max_drawdown"],
            "delta_mdd": plus_m["max_drawdown"] - base_m["max_drawdown"],
        }
        print(f"    {label}: delta_final={results[label]['delta_final']:+,.0f}  "
              f"delta_sharpe={results[label]['delta_sharpe']:+.4f}")
    return results


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("Group A+ A17 / A18 / A19 Experiment")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    base_config = _load_json(GROUP_A_PLUS_CONFIG)
    a15_replay = _load_json(A15_REPLAY_REF) if A15_REPLAY_REF.exists() else None
    a15_stress = _load_json(A15_STRESS_REF) if A15_STRESS_REF.exists() else None

    output: dict[str, Any] = {
        "experiment": "group_a_plus_a17_a18_a19",
        "generated_at": datetime.now().isoformat(),
        "a15_replay_ref": A15_REPLAY_REF.name,
        "a15_stress_ref": A15_STRESS_REF.name,
        "variants": {},
    }

    # A15 baseline for comparison
    a15_base_fv = None
    a15_plus_fv = None
    a15_plus_sh = None
    a15_plus_mdd = None
    if a15_replay:
        s = a15_replay.get("summary", {})
        a15_base_fv = s.get("base_events_approx", {}).get("final_value")
        a15_plus_fv = s.get("GroupA+_focused_tdcc_0124_stab5_turn14_fast_cd3", {}).get("final_value")
        a15_plus_sh = s.get("GroupA+_focused_tdcc_0124_stab5_turn14_fast_cd3", {}).get("sharpe_ratio")
        a15_plus_mdd = s.get("GroupA+_focused_tdcc_0124_stab5_turn14_fast_cd3", {}).get("max_drawdown")

    for variant_name, overrides in VARIANTS.items():
        print(f"\n{'='*60}")
        print(f"  {variant_name}")
        print(f"{'='*60}")

        # ── Replay ──────────────────────────────────────────────────────────
        print(f"\n  [1/2] Replay 2025-01 ~ 2026-06 …")
        replay_result = run_replay(base_config, variant_name, overrides)

        # ── Stress ──────────────────────────────────────────────────────────
        print(f"\n  [2/2] Stress windows …")
        stress_results = run_stress(base_config, variant_name, overrides)

        output["variants"][variant_name] = {
            "overrides": overrides,
            "replay": replay_result,
            "stress": stress_results,
        }

        # Print live summary
        if replay_result:
            s = replay_result.get("summary", {})
            base_fv = s.get("base_events_approx", {}).get("final_value", 0) or 0
            plus_key = "GroupA+_focused_tdcc_0124_stab5_turn14_fast_cd3"
            plus_fv = s.get(plus_key, {}).get("final_value", 0) or 0
            plus_sh = s.get(plus_key, {}).get("sharpe_ratio", 0) or 0
            plus_mdd = s.get(plus_key, {}).get("max_drawdown", 0) or 0
            drag = (plus_fv - base_fv) / base_fv * 100 if base_fv else 0
            print(f"\n  Replay result:")
            print(f"    base final : {base_fv:>12,.0f}")
            print(f"    plus final : {plus_fv:>12,.0f}  ({drag:+.3f}% vs base)")
            print(f"    Sharpe     : {plus_sh:.4f}")
            print(f"    MDD        : {plus_mdd:.4f}")

    # ── Save ─────────────────────────────────────────────────────────────────
    out_path = PROJECT_ROOT / "results" / "group_a_plus_a17_a18_a19_20260615.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {out_path}")

    # ── Comparison table ─────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SUMMARY COMPARISON")
    print("=" * 80)

    # A15 row
    if a15_plus_fv and a15_base_fv:
        a15_drag = (a15_plus_fv - a15_base_fv) / a15_base_fv * 100
        print(f"{'A15 (reference)':<22} base={a15_base_fv:>11,.0f}  "
              f"plus={a15_plus_fv:>11,.0f}  ({a15_drag:+.3f}%)  "
              f"Sharpe={a15_plus_sh:.4f}  MDD={a15_plus_mdd:.4f}")

    print(f"\n{'Variant':<20} {'base_final':>12} {'plus_final':>12} {'drag%':>8} "
          f"{'Sharpe':>7} {'MDD':>8}  {'GFC_dF':>10} {'COVID_dF':>10}")
    print("-" * 100)

    for variant_name, overrides in VARIANTS.items():
        v = output["variants"].get(variant_name, {})
        replay = v.get("replay")
        stress = v.get("stress") or {}

        if replay:
            s = replay.get("summary", {})
            base_fv = s.get("base_events_approx", {}).get("final_value", 0) or 0
            plus_key = "GroupA+_focused_tdcc_0124_stab5_turn14_fast_cd3"
            plus_fv = s.get(plus_key, {}).get("final_value", 0) or 0
            plus_sh = s.get(plus_key, {}).get("sharpe_ratio", 0) or 0
            plus_mdd = s.get(plus_key, {}).get("max_drawdown", 0) or 0
            drag = (plus_fv - base_fv) / base_fv * 100 if base_fv else 0
            gfc_d = stress.get("gfc_2008", {}).get("delta_final", 0) or 0
            covid_d = stress.get("covid_2020", {}).get("delta_final", 0) or 0
            print(f"{variant_name:<20} {base_fv:>12,.0f} {plus_fv:>12,.0f} "
                  f"{drag:>+7.3f}% {plus_sh:>7.4f} {plus_mdd:>8.4f}  "
                  f"{gfc_d:>+10,.0f} {covid_d:>+10,.0f}")
        else:
            print(f"{variant_name:<20}  REPLAY FAILED")

    print("\nAll stress deltas:")
    for variant_name, overrides in VARIANTS.items():
        stress = output["variants"].get(variant_name, {}).get("stress") or {}
        vals = [f"{k}={stress.get(k,{}).get('delta_final',0):+,.0f}" for k in ["gfc_2008","china_fx_2015","china_fx_2016","covid_2020","inflation_2022"]]
        print(f"  {variant_name}: {', '.join(vals)}")


if __name__ == "__main__":
    main()
