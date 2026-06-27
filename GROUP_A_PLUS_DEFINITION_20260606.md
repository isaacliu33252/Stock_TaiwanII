# GroupA+ Definition

`GroupA+` means:

```text
Latest Group A LLM meta shadow strategy + 00679B defensive sleeve
```

Current base strategy:

- `GroupA_meta_ensemble_real_v1`
- Selected profile: `adaptive_momcash_price_severe12_vote_bearfilter_recovery_defense22`
- Latest sweep: `results/group_a_meta_real_vote_tune_sweep_20250101_20260606_llmfilled.json`
- Latest signal: `results/group_a_meta_ensemble_shadow_live_latest.json`

Overlay:

- Ticker: `00679B.TWO`
- Name: `元大美債20年`
- Reference holding: `10,000` shares
- Reference static mix: `80% Group A / 20% 00679B`

Dynamic sleeve target:

| Regime | 00679B target |
|---|---:|
| risk_on | 0% |
| caution | 0% |
| risk_off | 0% |
| severe | 0% |

Latest reference as of `2026-06-11`:

- Actual data date: `2026-06-05`
- 00679B price: `26.55`
- 10,000 shares value: about `265,500`
- Weight with latest Group A signal: about `20.83%`
- Latest preferred overlay profile: `cap_guard_optimized`
- Named replay profile: `cap_guard_optimized`
- Latest live turnover penalty: `0.00`
- 00631L cap by regime: `risk_on=20%`, `caution=18%`, `risk_off=0%`, `severe=0%`
- Latest replay result vs base approximation: final `+5,058`, Sharpe `+0.0113`, MDD unchanged, volatility `-0.03pp`
- The continuous overlay script now reads `execution_control.live_turnover_penalty_by_regime` first, then the legacy `latest_reference.recommended_live_turnover_penalty`, before falling back to regime defaults.
- The 00679B cache is resolved to the file containing the signal's actual data date, so refreshed data no longer requires manually changing the default cache path.
- `backtest_group_a_plus_overlay.py` includes `cap_guard_optimized` first in the default `--plus-variants`, so the latest cap-sweep winner is replayed without a manual variant argument.

This is a shadow portfolio definition, not a retrained production model.

Second-stage execution control:

Current default: disabled. It remains documented as a fallback execution-control tool, not the active `cap_guard_optimized` profile.

| Trigger | Action |
|---|---:|
| 0050 breaks prior reference low | pause deferred buys |
| 0050 opens down 1.5% or more | pause deferred buys unless close confirms recovery |
| 0050 closes above prior reference close | release 50% of deferred buys |
| 0050 / TAIEX recovers intraday | release 25% of deferred buys |

Implementation:

- `group_a_plus_second_stage_execution.py`

Defensive sleeve reduction:

Current default: no 00679B sleeve, so these fractions are inactive.

| Regime | 00679B sell fraction |
|---|---:|
| risk_on | 100% |
| caution | 100% |
| risk_off | 75% |
| severe | 50% |

This treats 00679B sells as risk-increasing when proceeds are used to buy stocks, so reductions are staged separately from ordinary risk-reduction sells.

Single-trade turnover cap:

Current default: 100% in every regime, so the cap does not bind.

| Regime | Max turnover |
|---|---:|
| risk_on | 100% |
| caution | 60% |
| risk_off | 25% |
| severe | 25% |

The cap is applied after staged buys and staged 00679B sells.
