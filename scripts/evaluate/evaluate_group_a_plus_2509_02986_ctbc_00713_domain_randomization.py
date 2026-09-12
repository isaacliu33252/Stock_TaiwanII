#!/usr/bin/env python3
"""Run CTBC-inspired domain-randomization stress for 00713 debounce.

Research-only. It perturbs capital size, execution delay, slippage, and
commission assumptions around the 00713 NCF sleeve/debounce experiment. This
implements the validation discipline transferred from arXiv:2509.02986 without
changing live weights, golden artifacts, NCF gates, or orders.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backtest_group_a_plus_switch_policy import DB_PATH  # noqa: E402
from scripts.evaluate import evaluate_group_a_plus_2509_02986_ctbc_00713_debounce_shadow as debounce_00713  # noqa: E402


DEFAULT_PANEL = PROJECT_ROOT / "results/ncf_00713_panel_latest_20260907.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_00713_domain_randomization.json"
DEFAULT_MARKDOWN = PROJECT_ROOT / "report/group_a_plus/latest/2509_02986_ctbc_00713_domain_randomization.md"


@dataclass(frozen=True)
class Scenario:
    name: str
    initial_value: float
    signal_delay_days: int
    commission_rate: float
    slippage_rate: float
    equity_etf_sell_tax: float


SCENARIOS = (
    Scenario("base_1m_delay1", 1_000_000.0, 1, 0.001425, 0.0005, 0.0010),
    Scenario("capital_500k_delay1", 500_000.0, 1, 0.001425, 0.0005, 0.0010),
    Scenario("capital_1500k_delay1", 1_500_000.0, 1, 0.001425, 0.0005, 0.0010),
    Scenario("delay0_1m", 1_000_000.0, 0, 0.001425, 0.0005, 0.0010),
    Scenario("delay2_1m", 1_000_000.0, 2, 0.001425, 0.0005, 0.0010),
    Scenario("high_slippage_1m", 1_000_000.0, 1, 0.001425, 0.0010, 0.0010),
    Scenario("high_cost_1m", 1_000_000.0, 1, 0.002000, 0.0010, 0.0010),
)


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _namespace(args: argparse.Namespace, scenario: Scenario) -> argparse.Namespace:
    return argparse.Namespace(
        db=args.db,
        panel_00713=args.panel_00713,
        windows=args.windows,
        initial_value=scenario.initial_value,
        signal_delay_days=scenario.signal_delay_days,
        commission_rate=scenario.commission_rate,
        slippage_rate=scenario.slippage_rate,
        equity_etf_sell_tax=scenario.equity_etf_sell_tax,
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    scenario_reports = []
    for scenario in SCENARIOS:
        report, _curves = debounce_00713.build_report(_namespace(args, scenario))
        scenario_reports.append(
            {
                "scenario": scenario.name,
                "settings": {
                    "initial_value": scenario.initial_value,
                    "signal_delay_days": scenario.signal_delay_days,
                    "commission_rate": scenario.commission_rate,
                    "slippage_rate": scenario.slippage_rate,
                    "equity_etf_sell_tax": scenario.equity_etf_sell_tax,
                },
                "decision": report.get("decision"),
                "summary": report.get("summary"),
            }
        )

    variants = ("raw_gate", "debounce_2of3", "debounce_3of3")
    aggregate: dict[str, dict[str, Any]] = {}
    for variant in variants:
        rows = [item["summary"][variant] for item in scenario_reports if variant in item.get("summary", {})]
        aggregate[variant] = {
            "scenario_count": len(rows),
            "positive_avg_delta_final_value_scenarios": int(sum(row["average_delta_final_value"] > 0 for row in rows)),
            "positive_avg_delta_sharpe_scenarios": int(sum(row["average_delta_sharpe"] > 0 for row in rows)),
            "nonnegative_worst_delta_final_value_scenarios": int(sum(row["worst_delta_final_value"] >= 0 for row in rows)),
            "mean_average_delta_final_value": float(sum(row["average_delta_final_value"] for row in rows) / len(rows)),
            "worst_average_delta_final_value": float(min(row["average_delta_final_value"] for row in rows)),
            "best_average_delta_final_value": float(max(row["average_delta_final_value"] for row in rows)),
        }

    best = max(
        aggregate,
        key=lambda name: (
            aggregate[name]["positive_avg_delta_final_value_scenarios"],
            aggregate[name]["mean_average_delta_final_value"],
        ),
    )
    strict_pass = bool(
        aggregate[best]["positive_avg_delta_final_value_scenarios"] == len(scenario_reports)
        and aggregate[best]["positive_avg_delta_sharpe_scenarios"] == len(scenario_reports)
        and aggregate[best]["nonnegative_worst_delta_final_value_scenarios"] == len(scenario_reports)
    )
    return {
        "schema_version": 1,
        "report_type": "group_a_plus_2509_02986_ctbc_00713_domain_randomization",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_paper": {
            "id": "2509.02986",
            "transferred_idea": "domain_randomization_for_strategy_robustness",
        },
        "policy": "research_only_no_weight_change",
        "changes_latest_strategy": False,
        "changes_golden1_0531": False,
        "changes_golden2_0830": False,
        "changes_ncf_live_gate": False,
        "scenario_count": len(scenario_reports),
        "aggregate": aggregate,
        "scenario_reports": scenario_reports,
        "decision": {
            "domain_randomization_completed": True,
            "promotion_allowed": False,
            "decision": "robustness_test_complete_do_not_promote",
            "best_variant": best,
            "strict_robustness_passed": strict_pass,
            "reason": "No 00713 debounce variant beats fixed 10% across all perturbation scenarios.",
        },
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# 2509.02986 CTBC 00713 Domain Randomization",
        "",
        f"- Policy: `{report['policy']}`",
        f"- Decision: `{report['decision']['decision']}`",
        f"- Scenario count: `{report['scenario_count']}`",
        f"- Best variant: `{report['decision']['best_variant']}`",
        f"- Strict robustness passed: `{report['decision']['strict_robustness_passed']}`",
        "",
        "## Aggregate",
        "",
        "| variant | scenarios | positive avg dFV | positive avg dSharpe | nonnegative worst dFV | mean avg dFV | worst avg dFV | best avg dFV |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, item in report["aggregate"].items():
        lines.append(
            f"| `{name}` | {item['scenario_count']} | {item['positive_avg_delta_final_value_scenarios']} | "
            f"{item['positive_avg_delta_sharpe_scenarios']} | {item['nonnegative_worst_delta_final_value_scenarios']} | "
            f"{item['mean_average_delta_final_value']:.2f} | {item['worst_average_delta_final_value']:.2f} | "
            f"{item['best_average_delta_final_value']:.2f} |"
        )
    lines.extend(["", "## Scenarios", ""])
    for row in report["scenario_reports"]:
        best = row["decision"]["best_variant"]
        best_summary = row["summary"][best]
        lines.append(
            f"- `{row['scenario']}` best=`{best}` avg_dFV=`{best_summary['average_delta_final_value']:.2f}` "
            f"avg_dSharpe=`{best_summary['average_delta_sharpe']:.4f}`"
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "Domain randomization validation is now implemented for the CTBC-inspired 00713 sleeve experiment. It does not support promotion.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--panel-00713", default=str(DEFAULT_PANEL))
    parser.add_argument("--windows", default=None)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--markdown", default=str(DEFAULT_MARKDOWN))
    args = parser.parse_args()

    report = build_report(args)
    output = _resolve(args.output)
    markdown = _resolve(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    write_markdown(report, markdown)
    print(f"decision={report['decision']['decision']}")
    print(f"best_variant={report['decision']['best_variant']}")
    print(f"strict_robustness_passed={report['decision']['strict_robustness_passed']}")
    print(f"Output: {output}")
    print(f"Markdown: {markdown}")


if __name__ == "__main__":
    main()
