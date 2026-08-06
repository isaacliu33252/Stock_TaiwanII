#!/usr/bin/env python3
"""Read-only research: retroactively apply the significance-testing tools
added 2026-08-01 (group_a_plus/governance/significance.py) to the ONE
candidate in this repo's history that was actually promoted to production
off a multi-window backtest comparison -- the 2020-V-shaped-crash switch
rule fix (see GROUP_A_PLUS_2020_COVID_SWITCH_RULE_FIX_HANDOFF_20260706.md,
already live in group_a_plus/runners/a2118.py since 2026-07-06).

Reuses the EXACT same code path as the original 2026-07-06 decision
(scripts/misc/evaluate_momentum_fast_exit_final_candidate_20260706.py's
_baseline_curve/_run_curve, and backtest_group_a_plus_latest_vs_golden1_0531_
five_crises_20260706.py's FOLDS/_load_fold_data) so the daily return series
tested here are apples-to-apples with the original headline numbers
(2020: final value +0.18%, Sharpe 1.253->1.512, MDD -30.97%->-24.05%).

Does not modify a2118.py, the switch policy, or any production/report file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_defensive_basket import DEFENSIVE_BASKETS  # noqa: E402
from backtest_group_a_plus_policy_signal import (  # noqa: E402
    DEFAULT_DECISION_POINTER,
    _load,
    _load_policy_signal,
    _normalize,
    _resolve,
    _weights_from_group_a,
    _weights_from_group_a_plus,
)
from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from group_a_plus.governance.significance import (  # noqa: E402
    bootstrap_final_value_ci,
    jobson_korkie_memmel_test,
)
from group_a_plus.runners.a2111 import _build_switch_rule, _resolve_golden_signal_path  # noqa: E402
from scripts.misc.backtest_group_a_plus_latest_vs_golden1_0531_five_crises_20260706 import (  # noqa: E402
    FOLDS,
    _load_fold_data,
)
from scripts.misc.evaluate_momentum_fast_exit_final_candidate_20260706 import (  # noqa: E402
    _baseline_curve,
    _run_curve,
)


def main() -> None:
    db_path = _resolve(str(DB_PATH))
    # 2026-08-01 fix: _resolve_golden_signal_path()/DEFAULT_DECISION_POINTER read
    # TODAY's live signal files, not what golden1/current_defensive were on
    # 2026-07-06 -- today golden1_0531's PVA overlay happens to be in a
    # defensive M-state (0050 35.9%/00631L 7%/00632R 27.1%/cash 30%), which
    # got silently applied to every "golden1"-regime day across the ENTIRE
    # 2015-2020 backtest, producing final values wildly different from the
    # original 07-06 run (confirmed by comparing to the 2008_gfc window, which
    # should be baseline==candidate-only and DID match structurally but not in
    # absolute level). Pin the static golden1 50/20/30 structure instead, and
    # current_defensive to the same bond30_cash30-style basket structure the
    # original decision used, so this is a fair like-for-like replay.
    current_defensive = _normalize({"0050.TW": 0.70, "00679B.TWO": 0.30})
    basket = _normalize(DEFENSIVE_BASKETS["bond30_cash30"])
    latest_golden_weights = _normalize({"0050.TW": 0.50, "00631L.TW": 0.20, "cash": 0.30})
    rule = _build_switch_rule()

    results: dict[str, Any] = {}
    for name, spec in FOLDS.items():
        prices, chip_features = _load_fold_data(name, spec, db_path)
        baseline_curve, _, _ = _baseline_curve(prices, chip_features, rule, latest_golden_weights, basket, current_defensive)
        candidate_curve, _, _ = _run_curve(prices, chip_features, rule, latest_golden_weights, basket, current_defensive)

        report_start, report_end = spec["report_start"], spec["report_end"]
        b = baseline_curve.loc[report_start:] if report_end is None else baseline_curve.loc[report_start:report_end]
        c = candidate_curve.loc[report_start:] if report_end is None else candidate_curve.loc[report_start:report_end]

        b_returns = b.pct_change().dropna()
        c_returns = c.pct_change().dropna()

        jk = jobson_korkie_memmel_test(c_returns, b_returns)
        boot = bootstrap_final_value_ci(c_returns, b_returns, n_boot=2000, block_size=10)

        results[name] = {
            "label": spec["label"],
            "n_days": len(b_returns),
            "baseline_final_value": float(b.iloc[-1]),
            "candidate_final_value": float(c.iloc[-1]),
            "jobson_korkie_memmel": jk,
            "bootstrap_final_value_ci": boot,
        }

    out_path = PROJECT_ROOT / "results" / "significance_check_2020_switch_rule_fix_20260801.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Saved: {out_path}\n")
    for name, r in results.items():
        jk = r["jobson_korkie_memmel"]
        boot = r["bootstrap_final_value_ci"]
        print(f"=== {name} ({r['label']}, n={r['n_days']}) ===")
        print(f"  final_value: baseline={r['baseline_final_value']:,.0f} candidate={r['candidate_final_value']:,.0f}")
        if jk.get("status") == "ok":
            print(f"  JK Sharpe test: sharpe_candidate={jk['sharpe_a']:.4f} sharpe_baseline={jk['sharpe_b']:.4f} "
                  f"p={jk['p_value']:.4f} significant_5pct={jk['significant_at_5pct']}")
        else:
            print(f"  JK Sharpe test: {jk.get('status')} ({jk.get('reason')})")
        if boot.get("status") == "ok":
            print(f"  Bootstrap final_value ratio CI: point={boot['point_final_value_ratio_a_over_b']:.4f} "
                  f"CI=[{boot['ci_lower']:.4f},{boot['ci_upper']:.4f}] "
                  f"candidate_sig_better={boot['a_significantly_better']} candidate_sig_worse={boot['a_significantly_worse']}")
        else:
            print(f"  Bootstrap CI: {boot.get('status')} ({boot.get('reason')})")
        print()


if __name__ == "__main__":
    main()
