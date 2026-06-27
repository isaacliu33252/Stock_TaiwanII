#!/usr/bin/env python3
"""Compare GroupA+ turnover profiles across recent strict-cost and stress windows."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
STRICT_COST = PROJECT_ROOT / "results" / "group_a_plus_strict_cost_dca8000_turnover_compare_20260613.json"
STRESS = PROJECT_ROOT / "results" / "group_a_plus_multi_window_turnover_cap_sweep_20260613.json"
OUTPUT = PROJECT_ROOT / "results" / "group_a_plus_turnover_profile_score_20260613"
CAPS = {
    "turn08": 0.08,
    "turn10": 0.10,
    "turn12": 0.12,
    "turn15": 0.15,
    "turn18": 0.18,
    "turn20": 0.20,
    "turn25": 0.25,
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rank_score(values: dict[str, float], *, higher_is_better: bool = True) -> dict[str, float]:
    ordered = sorted(values.items(), key=lambda item: item[1], reverse=higher_is_better)
    n = max(len(ordered) - 1, 1)
    return {name: 1.0 - (rank / n) for rank, (name, _value) in enumerate(ordered)}


def main() -> None:
    strict = _load(STRICT_COST)
    stress = _load(STRESS)
    strict_summary = dict(strict["summary"])
    stress_aggregate = {float(row["turnover_cap"]): row for row in stress["aggregate"]}

    rows: list[dict[str, Any]] = []
    for label, cap in CAPS.items():
        strict_key = f"GroupA+_focused_tdcc_0258_stab3_{label}"
        strict_row = strict_summary[strict_key]
        stress_row = stress_aggregate[cap]
        rows.append(
            {
                "profile": label,
                "turnover_cap": cap,
                "strict_final_value": float(strict_row["final_value"]),
                "strict_sharpe": float(strict_row["sharpe_ratio"]),
                "strict_mdd": float(strict_row["max_drawdown"]),
                "strict_cost": float(strict_row["total_cost"]),
                "stress_avg_delta_final": float(stress_row["avg_delta_final_value"]),
                "stress_min_delta_final": float(stress_row["min_delta_final_value"]),
                "stress_avg_delta_sharpe": float(stress_row["avg_delta_sharpe_ratio"]),
                "stress_min_delta_sharpe": float(stress_row["min_delta_sharpe_ratio"]),
                "stress_avg_mdd_improvement": float(stress_row["avg_mdd_improvement"]),
                "stress_min_mdd_improvement": float(stress_row["min_mdd_improvement"]),
                "stress_avg_vol_reduction": float(stress_row["avg_volatility_reduction"]),
                "stress_windows_positive_final": int(stress_row["windows_positive_final"]),
                "stress_windows_total": int(stress_row["windows_total"]),
            }
        )

    metrics = {
        "strict_final_score": _rank_score({r["profile"]: r["strict_final_value"] for r in rows}),
        "strict_sharpe_score": _rank_score({r["profile"]: r["strict_sharpe"] for r in rows}),
        "strict_mdd_score": _rank_score({r["profile"]: r["strict_mdd"] for r in rows}),
        "strict_cost_score": _rank_score({r["profile"]: r["strict_cost"] for r in rows}, higher_is_better=False),
        "stress_avg_final_score": _rank_score({r["profile"]: r["stress_avg_delta_final"] for r in rows}),
        "stress_worst_final_score": _rank_score({r["profile"]: r["stress_min_delta_final"] for r in rows}),
        "stress_min_sharpe_score": _rank_score({r["profile"]: r["stress_min_delta_sharpe"] for r in rows}),
        "stress_avg_mdd_score": _rank_score({r["profile"]: r["stress_avg_mdd_improvement"] for r in rows}),
        "stress_avg_vol_score": _rank_score({r["profile"]: r["stress_avg_vol_reduction"] for r in rows}),
    }
    # Weighted for current production choice: 60% stress robustness, 40% recent strict-cost.
    weights = {
        "strict_final_score": 0.16,
        "strict_sharpe_score": 0.10,
        "strict_mdd_score": 0.08,
        "strict_cost_score": 0.06,
        "stress_avg_final_score": 0.10,
        "stress_worst_final_score": 0.20,
        "stress_min_sharpe_score": 0.12,
        "stress_avg_mdd_score": 0.10,
        "stress_avg_vol_score": 0.08,
    }
    for row in rows:
        profile = row["profile"]
        for name, score_by_profile in metrics.items():
            row[name] = float(score_by_profile[profile])
        row["balanced_score"] = float(sum(row[name] * weight for name, weight in weights.items()))
        row["passes_guardrail"] = bool(
            row["stress_min_delta_sharpe"] >= 0.0
            and row["stress_windows_positive_final"] >= 4
            and row["stress_min_delta_final"] >= -25_000.0
        )

    rows = sorted(rows, key=lambda row: row["balanced_score"], reverse=True)
    eligible_rows = [row for row in rows if row["passes_guardrail"]]
    recommendation = eligible_rows[0]["profile"] if eligible_rows else rows[0]["profile"]
    report = {
        "experiment": "group_a_plus_turnover_profile_score",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "strict_cost_source": str(STRICT_COST),
        "stress_source": str(STRESS),
        "profiles": list(CAPS),
        "score_weights": weights,
        "guardrails": {
            "stress_min_delta_sharpe": ">= 0.0",
            "stress_windows_positive_final": ">= 4 of 5",
            "stress_min_delta_final": ">= -25000",
        },
        "recommendation": recommendation,
        "decision_note": (
            "The recommendation is the highest balanced-score profile that passes the stress guardrails. "
            "Use turn08 if prioritizing worst-case stress robustness only; use higher caps only as "
            "return-seeking research profiles because their stress guardrails can fail."
        ),
        "rows": rows,
    }

    json_path = OUTPUT.with_suffix(".json")
    csv_path = OUTPUT.with_suffix(".csv")
    md_path = OUTPUT.with_suffix(".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    lines = [
        "# GroupA+ Turnover Profile Score",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Recommendation: `{recommendation}`",
        "",
        "| Profile | Guardrail | Score | Strict Final | Strict Sharpe | Strict MDD | Stress Avg Final Delta | Stress Worst Final Delta | Stress Min Sharpe Delta |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {profile} | {guardrail} | {balanced_score:.3f} | {strict_final_value:,.0f} | {strict_sharpe:.4f} | {strict_mdd:.2%} | {stress_avg_delta_final:,.0f} | {stress_min_delta_final:,.0f} | {stress_min_delta_sharpe:.4f} |".format(
                guardrail="PASS" if row["passes_guardrail"] else "FAIL",
                **row,
            )
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            report["decision_note"],
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    print(f"MD:   {md_path}")
    print(f"Recommendation: {recommendation}")
    for row in rows:
        print(
            f"{row['profile']}: guardrail={'PASS' if row['passes_guardrail'] else 'FAIL'}, "
            f"score={row['balanced_score']:.3f}, "
            f"strict_final={row['strict_final_value']:.0f}, "
            f"stress_worst={row['stress_min_delta_final']:.0f}"
        )


if __name__ == "__main__":
    main()
