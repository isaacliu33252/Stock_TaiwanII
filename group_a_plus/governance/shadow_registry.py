"""Registry of permanent research/shadow modules under group_a_plus.integrations.

Fable audit (2026-07-28, #6): group_a_plus/integrations/ had accumulated 9
`*_shadow*.py` modules, each individually well-justified (research_only,
production_effect=none) at the time it was built, but with no mechanism
forcing anyone to come back and decide "is this still worth carrying, or has
enough live/OOS evidence now accumulated to promote or retire it". This
module is a plain data registry, not a gate: it does not run anything, alert
on anything, or change any target weight. Its only job is to make the
"should someone look at this again" question answerable without re-deriving
each module's history from scratch, and (via
test_group_a_plus_governance_shadow_registry.py) to fail loudly if a new
`*_shadow*.py` file is added under integrations/ without a matching entry
here.

`review_trigger` is a short paraphrase of the condition already stated in
each module's own docstring/audit history -- it is not a new judgement call
introduced by this registry.
"""

from __future__ import annotations

from typing import Any


SHADOW_MODULE_REGISTRY: dict[str, dict[str, Any]] = {
    "cross_market_graph_shadow": {
        "module": "group_a_plus.integrations.cross_market_graph_shadow",
        "review_trigger": (
            "Re-review once evaluate_cross_market_directed_graph_shadow.py's "
            "walk-forward variants show a consistent OOS edge; currently "
            "read-only consumption of a research snapshot with no promotion "
            "criterion defined yet."
        ),
    },
    "foundation_volatility_shadow": {
        "module": "group_a_plus.integrations.foundation_volatility_shadow",
        "review_trigger": (
            "Re-review once a heavyweight foundation model (e.g. TimesFM) is "
            "actually wired in and compared against the current HAR-RV "
            "context variants -- this module is explicitly a placeholder "
            "schema step ahead of that."
        ),
    },
    "garch_regime_shadow": {
        "module": "group_a_plus.integrations.garch_regime_shadow",
        "review_trigger": (
            "Re-review once a second independent crisis window (beyond the "
            "single 2008 TWII-proxy sample, n=1) is available to confirm or "
            "refute the 24/24 threshold-robust edge found there."
        ),
    },
    "network_volatility_forecast_shadow": {
        "module": "group_a_plus.integrations.network_volatility_forecast_shadow",
        "review_trigger": (
            "Closed by evaluate_group_a_plus_network_volatility_forecast_quality.py: "
            "all 6 horizon/order combinations were non-significant "
            "(Diebold-Mariano p>=0.29). Kept only as a scored reference "
            "implementation; re-review only if the GNHAR panel is extended "
            "to substantially more tickers or years."
        ),
    },
    "network_volatility_spillover_shadow": {
        "module": "group_a_plus.integrations.network_volatility_spillover_shadow",
        "review_trigger": (
            "Re-review once the daily snapshot (see #3 fix, now wired into "
            "run_ncf_daily_pipeline.py's BEST_EFFORT_STEP_NAMES) has "
            "accumulated enough live recovery_boost_gate trigger days to "
            "evaluate the spillover-gated recovery boost out-of-sample."
        ),
    },
    "recovery_boost_spillover_gate_shadow": {
        "module": "group_a_plus.integrations.recovery_boost_spillover_gate_shadow",
        "review_trigger": (
            "Re-review once enough live recovery-regime + spillover-stress "
            "coincidences accumulate to join against realized forward "
            "returns (recovery regime is rare: 32 days across 7 backtest "
            "windows spanning 2017-2026, and none coincided with a "
            "spillover spike in-sample)."
        ),
    },
    "signal_alignment_shadow_variant": {
        "module": "group_a_plus.integrations.signal_alignment_shadow_variant",
        "review_trigger": (
            "Re-review once signal_alignment_shadow_variant_log.jsonl has "
            "enough forward-OOS samples to judge whether adding "
            "trough_nowcast/compounding_regime/crash_risk_alert as extra "
            "alignment votes actually improves anything versus the "
            "production 9-source alignment."
        ),
    },
    "srr_lite_shadow": {
        "module": "group_a_plus.integrations.srr_lite_shadow",
        "review_trigger": (
            "Thresholds were tuned from this project's own local crash-window "
            "backtest only (the source paper's own prototype scored worse "
            "than its logistic-regression baseline); re-review if those "
            "thresholds are ever re-tuned, and do not cite the source paper "
            "as supporting evidence for any future change."
        ),
    },
    "trough_override_eligibility_shadow": {
        "module": "group_a_plus.integrations.trough_override_eligibility_shadow",
        "review_trigger": (
            "Re-review once trough_override_eligibility_shadow_log has grown "
            "meaningfully past 3 OOS events (the 2018_correction window is "
            "the only true OOS sample so far; override_fraction=0.50, "
            "confirmation_mode=\"none\" is not yet promotable at that sample size)."
        ),
    },
}
