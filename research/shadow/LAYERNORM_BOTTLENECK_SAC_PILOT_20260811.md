# LayerNorm Bottleneck SAC Pilot (small spike, 2606.10448 follow-up)

- Ticker: `0050.TW`, train 2015-01-01..2022-12-31, test 2023-01-01..2026-08-10
- 20000 SAC timesteps, 3 seeds per config -- small pilot, not a rigorous multi-seed study

| config | critic-loss var | test total return | test Sharpe | test max drawdown |
|---|---|---|---|---|
| baseline | 1.271e+19±5.93e+18 | 0.00%±0.00% | 0.000±0.000 | 0.00%±0.00% |
| layernorm | 0.009126±0.0003845 | 14.94%±0.00% | 0.654±0.000 | -20.28%±0.00% |

