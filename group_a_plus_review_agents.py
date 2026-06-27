#!/usr/bin/env python3
"""Deterministic review agents for GroupA+ operational decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VOTES = ("approve", "caution", "block", "shadow_only")
SEVERITY_RANK = {"approve": 0, "shadow_only": 1, "caution": 2, "block": 3}


@dataclass(frozen=True)
class AgentReview:
    agent: str
    vote: str
    severity: str
    findings: list[str]
    evidence: dict[str, Any]


class BaseReviewAgent:
    name = "base_review_agent"
    description = ""

    def review(self, context: dict[str, Any]) -> AgentReview:
        raise NotImplementedError

    def _result(self, vote: str, findings: list[str], evidence: dict[str, Any] | None = None) -> AgentReview:
        if vote not in VOTES:
            raise ValueError(f"Invalid vote: {vote}")
        return AgentReview(
            agent=self.name,
            vote=vote,
            severity=vote,
            findings=findings,
            evidence=evidence or {},
        )


class DataFreshnessAgent(BaseReviewAgent):
    name = "data_freshness_agent"
    description = "Checks missing files and stale market data."

    def review(self, context: dict[str, Any]) -> AgentReview:
        daily = context["daily_status"]
        checks = {item["name"]: item for item in daily.get("checks", [])}
        required = checks.get("required_files", {})
        freshness = checks.get("data_freshness", {})
        signal = daily.get("signal", {})
        if required.get("status") == "block":
            return self._result("block", [str(required.get("detail"))], {"checks": checks})
        business_stale = int(signal.get("business_stale_days", 0) or 0)
        calendar_stale = int(signal.get("calendar_stale_days", 0) or 0)
        if business_stale > 3:
            return self._result(
                "block",
                [f"business stale days too high: {business_stale}"],
                {"business_stale_days": business_stale, "calendar_stale_days": calendar_stale},
            )
        if freshness.get("status") == "warn" or calendar_stale > business_stale:
            return self._result(
                "caution",
                [str(freshness.get("detail", "data freshness warning"))],
                {"business_stale_days": business_stale, "calendar_stale_days": calendar_stale},
            )
        return self._result("approve", ["required files present and data freshness acceptable"], {"checks": checks})


class RiskAgent(BaseReviewAgent):
    name = "risk_agent"
    description = "Checks signal guard, overlay regime, and risk posture."

    def review(self, context: dict[str, Any]) -> AgentReview:
        daily = context["daily_status"]
        checks = {item["name"]: item for item in daily.get("checks", [])}
        signal_guard = checks.get("signal_guard", {})
        overlay = checks.get("overlay_regime", {})
        group_a_plus = daily.get("group_a_plus", {})
        if signal_guard.get("status") == "block":
            return self._result("block", [str(signal_guard.get("detail"))], {"signal_guard": signal_guard})
        regime = str(group_a_plus.get("overlay_regime", ""))
        if regime in {"risk_off", "severe"}:
            return self._result(
                "caution",
                [f"overlay regime is {regime}; require execution review"],
                {"overlay_regime": regime, "overlay_check": overlay},
            )
        return self._result(
            "approve",
            [f"overlay regime is {regime}", f"signal guard: {signal_guard.get('detail')}"],
            {"overlay_regime": regime, "signal_guard": signal_guard},
        )


class CostAgent(BaseReviewAgent):
    name = "cost_agent"
    description = "Checks cash constraint and execution cost symptoms."

    def review(self, context: dict[str, Any]) -> AgentReview:
        daily = context["daily_status"]
        checks = {item["name"]: item for item in daily.get("checks", [])}
        cash_check = checks.get("group_a_plus_cash_constraint", {})
        cash_after_cost = float(daily.get("group_a_plus", {}).get("cash_after_cost", 0.0) or 0.0)
        if cash_check.get("status") == "block" or cash_after_cost < 0:
            return self._result(
                "block",
                [f"cash_after_cost is negative: {cash_after_cost:,.0f}"],
                {"cash_after_cost": cash_after_cost, "cash_check": cash_check},
            )
        if cash_after_cost < 100:
            return self._result(
                "caution",
                [f"cash_after_cost is thin: {cash_after_cost:,.0f}"],
                {"cash_after_cost": cash_after_cost, "cash_check": cash_check},
            )
        return self._result(
            "approve",
            [f"cash_after_cost remains positive: {cash_after_cost:,.0f}"],
            {"cash_after_cost": cash_after_cost, "cash_check": cash_check},
        )


class BenchmarkAgent(BaseReviewAgent):
    name = "benchmark_agent"
    description = "Compares latest GroupA+ target against Golden1_0531 benchmark."

    def review(self, context: dict[str, Any]) -> AgentReview:
        compare = context.get("strategy_compare", {})
        latest = compare.get("latest_group_a_plus", {})
        golden = compare.get("golden1_0531", {})
        latest_weights = dict(latest.get("target_weights", {}) or {})
        golden_weights = dict(golden.get("target_weights", {}) or {})
        lev_delta = float(latest_weights.get("00631L.TW", 0.0) or 0.0) - float(golden_weights.get("00631L.TW", 0.0) or 0.0)
        bond_delta = float(latest_weights.get("00679B.TWO", 0.0) or 0.0) - float(golden_weights.get("00679B.TWO", 0.0) or 0.0)
        cash_delta = float(latest_weights.get("cash", 0.0) or 0.0) - float(golden_weights.get("cash", 0.0) or 0.0)
        findings = [
            f"00631L weight delta vs Golden1: {lev_delta:+.2%}",
            f"00679B weight delta vs Golden1: {bond_delta:+.2%}",
            f"cash weight delta vs Golden1: {cash_delta:+.2%}",
        ]
        if lev_delta < -0.10:
            vote = "caution"
            findings.append("latest GroupA+ is materially less leveraged than Golden1; confirm intentional defensive posture")
        else:
            vote = "approve"
            findings.append("benchmark comparison does not create a block condition")
        return self._result(
            vote,
            findings,
            {
                "latest_weights": latest_weights,
                "golden_weights": golden_weights,
                "weight_delta": {
                    "00631L.TW": lev_delta,
                    "00679B.TWO": bond_delta,
                    "cash": cash_delta,
                },
            },
        )


def default_review_agents() -> list[BaseReviewAgent]:
    return [
        DataFreshnessAgent(),
        RiskAgent(),
        CostAgent(),
        BenchmarkAgent(),
    ]


def final_vote(agent_reviews: list[AgentReview]) -> dict[str, Any]:
    counts = {vote: 0 for vote in VOTES}
    for review in agent_reviews:
        counts[review.vote] += 1
    if counts["block"]:
        decision = "block"
        action = "Do not execute. Produce report and require manual review."
    elif counts["caution"]:
        decision = "caution"
        action = "Allow hold or reduced-risk execution only; require manual confirmation for new orders."
    elif counts["shadow_only"]:
        decision = "shadow_only"
        action = "Record as research only."
    else:
        decision = "approve"
        action = "Strategy may proceed under existing execution gates."
    return {
        "decision": decision,
        "action": action,
        "vote_counts": counts,
    }
