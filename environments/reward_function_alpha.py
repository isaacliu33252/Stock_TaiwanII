"""AlphaRewardFunction -- clean benchmark-relative log-return reward.

Implements the "alpha reward" from arXiv:2607.16028 ("Sentiment-Augmented
Deep RL for Active Trading", Neagu et al., CLEF 2026 FinMMEval Task 3):

    r_t = log(V_t / V_{t-1}) - log(c_t / c_{t-1})

i.e. portfolio log-return minus the traded asset's own buy-and-hold
log-return. Under a price-taker assumption this shares the same optimal
policy as the raw portfolio log-return (the benchmark term is a
policy-independent additive constant in expectation), but has substantially
lower variance -- it acts as a control variate that cancels the market's own
noise out of the training signal. Summed over an episode it telescopes
exactly to log(alpha_T), the terminal outperformance ratio over
buy-and-hold.

This is deliberately minimal -- unlike DynamicRewardShaper (reward_function_v3.py),
it has no Sortino/Calmar/MA-trend/holding-bonus/etc. terms. The paper's
argument is that the variance reduction is the point; stacking many other
shaped terms back in would reintroduce the noise this reward removes.
Provided as an alternative to v3 for side-by-side comparison, not a
replacement -- the entire RL training track this feeds
(portfolio_train_v2.py) is research-only and not part of live Group A+
signal generation.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple


class AlphaRewardFunction:
    """Minimal benchmark-relative log-return reward (arXiv:2607.16028)."""

    def __init__(self, clip: float = 0.20) -> None:
        self.clip = clip

    def calculate(
        self,
        portfolio_value: float,
        previous_portfolio_value: float,
        position: int,
        close_price: float,
        avg_cost: float,
        action: int,
        max_drawdown: float,
        trade_history: List[Dict],
        previous_close: Optional[float] = None,
        **_: object,
    ) -> Tuple[float, Dict]:
        portfolio_log_return = 0.0
        if previous_portfolio_value > 0 and portfolio_value > 0:
            portfolio_log_return = math.log(portfolio_value / previous_portfolio_value)

        benchmark_log_return = 0.0
        if previous_close is not None and previous_close > 0 and close_price > 0:
            benchmark_log_return = math.log(close_price / previous_close)

        reward = portfolio_log_return - benchmark_log_return
        reward = max(-self.clip, min(self.clip, reward))

        breakdown = {
            "portfolio_log_return": portfolio_log_return,
            "benchmark_log_return": benchmark_log_return,
            "alpha_reward": reward,
        }
        return reward, breakdown
