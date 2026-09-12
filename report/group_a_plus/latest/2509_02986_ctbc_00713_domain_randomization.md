# 2509.02986 CTBC 00713 Domain Randomization

- Policy: `research_only_no_weight_change`
- Decision: `robustness_test_complete_do_not_promote`
- Scenario count: `7`
- Best variant: `debounce_3of3`
- Strict robustness passed: `False`

## Aggregate

| variant | scenarios | positive avg dFV | positive avg dSharpe | nonnegative worst dFV | mean avg dFV | worst avg dFV | best avg dFV |
|---|---:|---:|---:|---:|---:|---:|---:|
| `raw_gate` | 7 | 0 | 0 | 0 | -3882.70 | -5656.14 | -1784.07 |
| `debounce_2of3` | 7 | 0 | 0 | 0 | -1951.16 | -2779.24 | -848.41 |
| `debounce_3of3` | 7 | 0 | 0 | 0 | -1519.65 | -2375.70 | -626.49 |

## Scenarios

- `base_1m_delay1` best=`raw_gate` avg_dFV=`-3747.40` avg_dSharpe=`-0.0066`
- `capital_500k_delay1` best=`raw_gate` avg_dFV=`-1873.70` avg_dSharpe=`-0.0066`
- `capital_1500k_delay1` best=`raw_gate` avg_dFV=`-5621.11` avg_dSharpe=`-0.0066`
- `delay0_1m` best=`raw_gate` avg_dFV=`-1784.07` avg_dSharpe=`-0.0046`
- `delay2_1m` best=`raw_gate` avg_dFV=`-3859.38` avg_dSharpe=`-0.0067`
- `high_slippage_1m` best=`raw_gate` avg_dFV=`-4637.11` avg_dSharpe=`-0.0076`
- `high_cost_1m` best=`raw_gate` avg_dFV=`-5656.14` avg_dSharpe=`-0.0088`

## Conclusion

Domain randomization validation is now implemented for the CTBC-inspired 00713 sleeve experiment. It does not support promotion.
