# GroupA+ Smart Leverage Paper Review Final Handoff - arXiv 2412.05431v2

Date: 2026-08-21  
Paper: `C:\Users\isaac\Downloads\2412.05431v2.pdf`  
Title: `Smart leverage? Rethinking the role of Leveraged Exchange Traded Funds in constructing portfolios to beat a benchmark`  
Scope: analyze whether the paper has useful ideas for GroupA+ / latest strategy.

## Decision

Do not promote into latest strategy or `golden1_0531` today.

The paper has a useful idea for GroupA+: LETF exposure should be managed as a dynamic, benchmark-relative, contrarian sleeve, not as naive buy-and-hold leverage. The actionable GroupA+ interpretation is:

- keep LETF use inside broad-market / golden1-style risk-on regimes only;
- after a strong 00631L run, systematically harvest part of the 00631L sleeve into lower-beta exposure such as 0050;
- do not use portfolio-level leverage to mimic 00631L;
- evaluate against benchmark-relative outcomes, not just absolute return;
- treat extreme left-tail risk as a hard blocker.

However, current GroupA+ `golden1` replay has no effective 00631L trim exposure in the active profit-harvest shadow. The trigger can fire, but there is no 00631L weight to trim, so the current result is a no-op. No live strategy, target weight, rebalance file, or order file was changed.

## Paper Findings

The paper compares portfolios using a vanilla ETF versus a leveraged ETF on a broad equity market index, optimized to beat a benchmark using Information Ratio. The authors use both stylized closed-form results and a neural-network optimizer trained on stationary block bootstrap data from 1926-2023.

Key points relevant to GroupA+:

- LETFs can provide convenient embedded leverage without direct portfolio borrowing.
- The benefit depends on dynamic rebalancing, not long-horizon naive holding.
- The strategy is contrarian: after good LETF performance, reduce LETF allocation and lock gains into safer/lower-beta assets.
- Quarterly-style rebalancing and costs are central to the claim.
- Left-tail outcomes remain worse than unlevered ETF/benchmark in extreme cases.

Non-portable parts:

- The paper is trained on long US market history, not Taiwan 00631L history.
- It assumes a broad market LETF and a 70/30 benchmark; GroupA+ has Taiwan-specific ETF, chip concentration, NCF overlays, tail gates, and 00631L/00632R incident history.
- The NN/IR optimizer is not directly production-ready for GroupA+ without a separate Taiwan walk-forward and governance layer.

## What Was Tested / Updated

Existing GroupA+ coverage already contained the closest practical mechanism:

- `scripts/evaluate/evaluate_2506_19200_letf_profit_harvest_shadow.py`
- `results/2506_19200_letf_profit_harvest_shadow.json`
- `report/group_a_plus/latest/2506_19200_letf_profit_harvest_shadow.md`

This shadow tests a profit-triggered 00631L harvest:

- trailing 00631L gain threshold;
- positive leveraged-compounding contribution versus 2x 0050;
- relative momentum rollover;
- trim part of 00631L into 0050;
- research-only, no live changes.

During the 2026-08-21 rerun, the old promotion gate initially reported `promotion_ready=true`, but inspection showed all candidate-vs-baseline deltas were zero despite trigger days. Root cause: the current golden1 baseline has no effective 00631L exposure to trim. I patched the shadow gate to count `effective_trim_weight`; no-op trigger days can no longer pass promotion review.

Updated result after patch:

- `promotion_ready=false`
- reason: `Profit-harvest trigger fired, but current golden1 has no effective 00631L trim exposure.`
- all windows: `3/9` pass, total final delta `0.00`, effective harvest days `0`
- holdout: `1/3` pass, effective harvest days `0`

## IR-lite Taiwan Replication Added

After the initial review, I added a direct Taiwan IR-lite shadow to test the
paper's benchmark-relative mechanism instead of only relying on the existing
profit-harvest proxy.

Files:

- `scripts/evaluate/evaluate_2412_05431_smart_leverage_ir_lite_shadow.py`
- `tests/test_evaluate_2412_05431_smart_leverage_ir_lite_shadow.py`
- `results/2412_05431_smart_leverage_ir_lite_shadow.json`
- `report/group_a_plus/latest/2412_05431_smart_leverage_ir_lite_shadow.md`
- `results/2412_05431_smart_leverage_ir_lite_shadow_monthly_coarse.json`
- `report/group_a_plus/latest/2412_05431_smart_leverage_ir_lite_shadow_monthly_coarse.md`

Design:

- benchmark: `70% 0050 / 30% 00679B`
- candidate assets: `0050`, `00631L`, `00679B`, `cash`
- no `00632R`, no portfolio-level leverage
- grid optimizer chooses weights using only trailing 252 trading days
- objective: benchmark-relative Information Ratio
- constraints: max 00631L weight, max effective equity beta, drawdown/worst-20d tail filter
- replay includes transaction cost, slippage, and ETF sell tax using existing GroupA+ target simulator
- comparison lines: benchmark and current A21.18/latest replay

Quarterly full-grid result:

- decision: `do_not_promote_keep_shadow`
- promotion ready: `false`
- all windows: `0/7` pass
- holdout: `0/3` pass
- total final delta vs benchmark: `-2,816`
- total final delta vs latest A21.18: `+1,911,039`
- average 00631L weight: `6.87%`
- note: after adding direct drawdown/worst-20d penalties, the full-grid quarterly
  optimizer lowered 00631L exposure materially, but still failed every window.

Monthly coarse-grid sensitivity:

- decision: `do_not_promote_keep_shadow`
- promotion ready: `false`
- all windows: `0/7` pass
- holdout: `0/3` pass
- total final delta vs benchmark: `+367,865`
- total final delta vs latest A21.18: `+2,281,720`
- average 00631L weight: `13.57%`

Monthly risk-penalty + turnover-cap sensitivity:

- file: `report/group_a_plus/latest/2412_05431_smart_leverage_ir_lite_shadow_monthly_risk_penalty_turnover_cap.md`
- decision: `do_not_promote_keep_shadow`
- promotion ready: `false`
- all windows: `0/7` pass
- holdout: `0/3` pass
- total final delta vs benchmark: `+199,419`
- total final delta vs latest A21.18: `+2,113,275`
- average 00631L weight: `9.57%`
- parameters: monthly, grid step `0.10`, drawdown penalty `12`, worst-20d penalty `8`,
  max rebalance turnover `0.30`, no-trade band `0.05`

Monthly low-beta sensitivity:

- file: `report/group_a_plus/latest/2412_05431_smart_leverage_ir_lite_shadow_monthly_low_beta.md`
- decision: `do_not_promote_keep_shadow`
- promotion ready: `false`
- all windows: `0/7` pass
- holdout: `0/3` pass
- total final delta vs benchmark: `-5,471`
- total final delta vs latest A21.18: `+1,908,385`
- average 00631L weight: `5.56%`
- parameters: monthly, grid step `0.10`, max 00631L `10%`, max effective beta `0.80`,
  drawdown penalty `20`, worst-20d penalty `12`, max rebalance turnover `0.20`,
  no-trade band `0.05`

## Completion Experiments

After the third round, I added the missing completion experiment bundle:

- `scripts/evaluate/sweep_2412_05431_smart_leverage_completion.py`
- `tests/test_sweep_2412_05431_smart_leverage_completion.py`
- `results/2412_05431_smart_leverage_completion_experiments.json`
- `report/group_a_plus/latest/2412_05431_smart_leverage_completion_experiments.md`

Coverage:

- standard recent/holdout/stress windows: 7 windows
- incident replay windows: 4 windows
  - 2020 Covid crash slice
  - 2022 rate-hike slice
  - 2024 August unwind slice
  - 2026 Q2 drawdown slice
- parameter families:
  - quarterly default risk-penalty
  - monthly default risk-penalty
  - monthly risk penalty + turnover cap
  - monthly low beta
  - monthly no-00631L control
  - monthly risk penalty + turnover cap + `lot_size=1000` stress

Completion result:

- decision: `do_not_promote_keep_shadow`
- promotion ready: `false`
- best by pass/final ranking: `monthly_default_risk_penalty`
- every variant: `0/11` pass
- standard holdout: every variant `0/3` pass
- incident replay: every variant `0/4` pass
- dominant blocker: `latest_a2118_drawdown` in `11/11` windows for every variant
- `lot_size=1000` stress: total final-value delta vs fractional IR-lite `-159,070`

Variant summary:

| Variant | Pass | Holdout | Incident | dFinal vs Benchmark | Avg 00631L | Main blocker |
|---|---:|---:|---:|---:|---:|---|
| quarterly_default_risk_penalty | 0/11 | 0/3 | 0/4 | +236,829 | 10.25% | latest A21.18 drawdown |
| monthly_default_risk_penalty | 0/11 | 0/3 | 0/4 | +305,060 | 10.34% | latest A21.18 drawdown |
| monthly_risk_turnover_cap | 0/11 | 0/3 | 0/4 | +260,230 | 9.78% | latest A21.18 drawdown |
| monthly_low_beta | 0/11 | 0/3 | 0/4 | +36,565 | 5.27% | latest A21.18 drawdown |
| monthly_no_00631l_control | 0/11 | 0/3 | 0/4 | -7,170 | 0.00% | latest A21.18 drawdown / benchmark instability |
| monthly_risk_turnover_cap_lot1000 | 0/11 | 0/3 | 0/4 | +260,230 | 9.78% | latest A21.18 drawdown + lot rounding |

Interpretation:

The IR-lite optimizer can improve final value in several windows, especially
with monthly rebalancing, but it repeatedly pays for that with worse
benchmark-relative Sharpe or worse drawdown. Adding explicit drawdown penalties,
no-trade bands, turnover caps, and low-beta constraints reduces 00631L exposure,
but does not produce a promotable policy. Against latest A21.18 it still often
accepts deeper drawdowns. This confirms the paper's caveat: LETF smart leverage
can raise upside, but the tail-risk trade-off is not acceptable for live GroupA+
promotion under the current guard standard.

## Files Changed

- `scripts/evaluate/evaluate_2506_19200_letf_profit_harvest_shadow.py`
  - Added `effective_trim_weight`.
  - Promotion now requires effective 00631L trim exposure, not just trigger days.
  - Markdown report now shows effective harvest days and effective trim weight.

- `tests/test_evaluate_2506_19200_letf_profit_harvest_shadow.py`
  - Added tests that no-op profit-harvest triggers are not pass/promotion-ready.

- `report/group_a_plus/latest/2506_19200_letf_profit_harvest_shadow.md`
  - Regenerated with 2026-08-21 data and corrected gate.

- `results/2506_19200_letf_profit_harvest_shadow.json`
  - Regenerated with corrected no-op detection.

- `scripts/evaluate/evaluate_2412_05431_smart_leverage_ir_lite_shadow.py`
  - Added Taiwan IR-lite optimizer, drawdown/worst-20d objective penalties,
    turnover cap, no-trade band, and optional lot-rounded execution stress.

- `tests/test_evaluate_2412_05431_smart_leverage_ir_lite_shadow.py`
  - Added tests for candidate constraints, IR selection, drawdown penalty,
    turnover cap, no-trade band, and lot-rounded simulation.

- `scripts/evaluate/sweep_2412_05431_smart_leverage_completion.py`
  - Added completion sweep for parameter robustness, incident replay,
    no-00631L control, and lot-size stress.

- `tests/test_sweep_2412_05431_smart_leverage_completion.py`
  - Added completion promotion/blocker logic test.

## Verification

Commands run:

```bash
.venv/bin/python -m pytest tests/test_evaluate_2506_19200_letf_profit_harvest_shadow.py
.venv/bin/python scripts/evaluate/evaluate_2506_19200_letf_profit_harvest_shadow.py
.venv/bin/python -m pytest tests/test_evaluate_2412_05431_smart_leverage_ir_lite_shadow.py
.venv/bin/python scripts/evaluate/evaluate_2412_05431_smart_leverage_ir_lite_shadow.py
.venv/bin/python scripts/evaluate/evaluate_2412_05431_smart_leverage_ir_lite_shadow.py --rebalance-frequency monthly --grid-step 0.10 --output-json results/2412_05431_smart_leverage_ir_lite_shadow_monthly_coarse.json --output-md report/group_a_plus/latest/2412_05431_smart_leverage_ir_lite_shadow_monthly_coarse.md
.venv/bin/python scripts/evaluate/evaluate_2412_05431_smart_leverage_ir_lite_shadow.py --rebalance-frequency monthly --grid-step 0.10 --drawdown-penalty 12 --worst-20d-penalty 8 --max-rebalance-turnover 0.30 --no-trade-band 0.05 --output-json results/2412_05431_smart_leverage_ir_lite_shadow_monthly_risk_penalty_turnover_cap.json --output-md report/group_a_plus/latest/2412_05431_smart_leverage_ir_lite_shadow_monthly_risk_penalty_turnover_cap.md
.venv/bin/python scripts/evaluate/evaluate_2412_05431_smart_leverage_ir_lite_shadow.py --rebalance-frequency monthly --grid-step 0.10 --max-00631l-weight 0.10 --max-effective-beta 0.80 --drawdown-penalty 20 --worst-20d-penalty 12 --max-rebalance-turnover 0.20 --no-trade-band 0.05 --output-json results/2412_05431_smart_leverage_ir_lite_shadow_monthly_low_beta.json --output-md report/group_a_plus/latest/2412_05431_smart_leverage_ir_lite_shadow_monthly_low_beta.md
.venv/bin/python -m pytest tests/test_evaluate_2506_19200_letf_profit_harvest_shadow.py tests/test_evaluate_2412_05431_smart_leverage_ir_lite_shadow.py tests/test_sweep_2412_05431_smart_leverage_completion.py
.venv/bin/python scripts/evaluate/sweep_2412_05431_smart_leverage_completion.py
```

Test result:

- profit-harvest gate: `2 passed`
- IR-lite shadow: `7 passed`
- completion bundle combined tests: `11 passed`

Final verification pass:

```bash
.venv/bin/python -m pytest tests/test_evaluate_2506_19200_letf_profit_harvest_shadow.py tests/test_evaluate_2412_05431_smart_leverage_ir_lite_shadow.py tests/test_sweep_2412_05431_smart_leverage_completion.py
```

Result:

- `11 passed`

Completion JSON consistency check:

- file exists: `results/2412_05431_smart_leverage_completion_experiments.json`
- file exists: `report/group_a_plus/latest/2412_05431_smart_leverage_completion_experiments.md`
- file exists: `GROUP_A_PLUS_20260821_SMART_LEVERAGE_2412_05431_FINAL_HANDOFF.md`
- `promotion_ready=false`
- `decision=do_not_promote_keep_shadow`
- variant count: `6`
- windows per variant: `11`
- standard holdout per variant: `0/3`
- incident replay per variant: `0/4`
- pass count per variant: `0`
- best by pass/final ranking: `monthly_default_risk_penalty`
- lot-size 1000 stress total final-value delta vs fractional IR-lite: `-159,070.2790879173`
- scope:
  - `changes_latest_strategy=false`
  - `changes_golden1_0531=false`
  - `changes_target_weights=false`
  - `creates_orders=false`

Process check:

- no lingering `sweep_2412_05431`, `evaluate_2412_05431`, or `pytest` process was left running.

Dirty-worktree boundary:

- `group_a_plus/runners/a2118.py`, `scripts/run/run_group_a_combined_signal.py`, and
  `scripts/run/run_ncf_daily_pipeline.py` were already shown as modified in the broader
  worktree; this paper-review/completion pass did not intentionally edit them.
- This line intentionally changed/created only research/report/test artifacts for the
  2412.05431 review and the related 2506.19200 no-op promotion-gate fix.

Shadow rerun result:

- `promotion_ready=false`
- report: `report/group_a_plus/latest/2506_19200_letf_profit_harvest_shadow.md`
- json: `results/2506_19200_letf_profit_harvest_shadow.json`

## Next Steps

1. Keep this research-only; do not promote into latest strategy or `golden1_0531`.
2. Treat the smart-leverage import as closed for now under current GroupA+
   promotion standards: holdout, incident, control, and lot-rounding experiments
   all failed.
3. Only revisit if the live strategy's risk budget changes or if a future
   00631L allocation request explicitly accepts materially deeper drawdown than
   A21.18.
4. Engineering-only cleanup if this line is revisited: cache A21.18 baseline
   replay to make repeated completion sweeps faster.
