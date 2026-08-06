# GroupA+ Formal Report - 2026-06-13

## Active Baseline

- Baseline pointer: `GROUP_A_PLUS_CURRENT_BASELINE.json`
- Baseline snapshot: `results/group_a_plus_formal_baseline_20260613.json`
- GroupA+ config: `group_a_plus_config.json`
- Active profile: `focused_tdcc_0124_stab5_turn14_fast_cd3`
- Clean payload: `results/group_a_payload_clean_cashdiv_dca8000_20260612.json`
- Latest Group A signal: `results/signal_group_a_20260612_233305.json`
- Latest GroupA+ final signal: `results/group_a_plus_final_signal_20260613.json`

## Policy

- DCA: `0050.TW` monthly `8000`, day `20`
- Dividend mode: `cash`
- Dynamic DCA: disabled
- Dividend reinvestment: disabled
- GroupA+ risk-on 00679B sleeve: `0%`
- GroupA+ caution/risk_off/severe 00679B sleeve: `1% / 2% / 4%`
- Risk-off/severe turnover cap: `15%`
- Fast risk-off cooldown: `3` business days

## Clean Payload Replay

| Metric | Value |
| --- | ---: |
| Final value | `2,404,745.87` |
| Sharpe | `2.5930` |
| Max drawdown | `-24.26%` |
| DCA contributions | `136,000` |
| Dividend credited | `29,608.21` |
| Dividend reinvestment fees | `0` |

## Latest Signal

- Signal status: `hold`
- Signal reason: `cooldown_5d`
- Requested as-of date: `2026-06-12`
- Actual data date: `2026-06-11`
- Candidate target: `0050 79.6% / 00631L 10.4% / cash 10%`
- Executable Group A target: `hold_current`

## GroupA+ Final Signal

Assumption: current 00679B shares use the configured default `10000`.

| Ticker | Current | Target | Delta | Side | Notional |
| --- | ---: | ---: | ---: | --- | ---: |
| 0050.TW | `89` | `1,459` | `+1,370` | buy | `136,794` |
| 00631L.TW | `0` | `0` | `0` | hold | `0` |
| 00632R.TW | `0` | `0` | `0` | hold | `0` |
| 00679B.TWO | `10,000` | `4,830` | `-5,170` | sell | `137,315` |

- Overlay regime: `risk_on`
- 00679B target sleeve: `0%`
- Estimated execution cost: `665`
- Cash after cost: `56`

## Daily Check

- Output: `results/group_a_plus_daily_check_20260613.json`
- Overall: `warn`
- Reason: data is `1` business day stale and `2` calendar days stale; this is expected on weekend.
- Guard: `ok`, signal is held by `cooldown_5d`, not blocked by stale/MDD/underperformance guard.
- Cash constraint: `ok`, cash after cost remains positive.

## Stress Tests

| Window | Base Final | GroupA+ Final | Base MDD | GroupA+ MDD | Sharpe Delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2008 GFC proxy | `1,293,255` | `1,483,596` | `-50.05%` | `-39.32%` | `+0.3309` |
| 2015 China/FX | `1,105,198` | `1,155,030` | `-21.40%` | `-14.05%` | `+0.4163` |
| 2016 partial | `1,157,897` | `1,133,252` | `-8.12%` | `-7.87%` | `+0.0122` |
| 2020 COVID | `1,275,519` | `1,291,406` | `-25.06%` | `-20.76%` | `+0.3013` |
| 2022 inflation | `820,577` | `835,753` | `-26.52%` | `-23.03%` | `+0.0124` |

GroupA+ improves drawdown in every tested window. It gives up final value in 2016 partial, but that window is less severe and the drawdown/volatility profile still improves.

## Strict Cost Test

Source: `results/group_a_plus_strict_cost_dca8000_20260612.csv`

| Strategy | Final | Sharpe | MDD | Cost |
| --- | ---: | ---: | ---: | ---: |
| Base approx | `2,257,762` | `2.8302` | `-16.69%` | `44,920` |
| GroupA+ | `2,332,649` | `2.9829` | `-15.30%` | `41,196` |

Under doubled commission/sell tax, GroupA+ still improves final value, Sharpe, drawdown, and estimated cost.

## 2026-06-13 Improvement

- Restored turnover cap to balanced `turn12`.
- Reason: `turn12` has the best balanced score across `turn08 / turn10 / turn12`; it improves 2025-2026 strict-cost final, Sharpe, MDD, and volatility versus `turn08`.
- Tradeoff: `turn08` remains better for worst-window final drag (`-12,073` vs `turn12 -24,645`) and lower stress-window cost, so it is retained as the tail-risk fallback.

## 2026-06-13 A8 Improvement

- Promoted profile: `focused_tdcc_0258_stab5_turn15`.
- Change: TDCC stability `3 -> 5` days, risk_off/severe turnover cap `12% -> 15%`.
- Recent replay vs previous `stab3_turn12`: final nearly flat (`2,369,851` vs `2,370,192`), Sharpe improves (`3.0481` vs `3.0400`), MDD improves (`-14.89%` vs `-15.02%`), volatility improves (`21.65%` vs `21.71%`).
- Multi-window stress: worst final drag improves to `-20,356` from `-24,645`; min Sharpe delta remains positive (`+0.0115`).
- Hybrid severe-only caps were tested but had no effect, showing the prior guardrail failure came from risk_off turnover, not severe turnover.

## 2026-06-13 A9 Improvement

- Promoted profile: `focused_tdcc_0235_stab5_turn15`.
- Change: TDCC bands `0/2/5/8 -> 0/2/3/5`; stability stays `5` days and risk_off/severe turnover cap stays `15%`.
- Recent replay vs A8: final improves (`2,370,171` vs `2,369,851`), with small tradeoffs in Sharpe (`3.0410` vs `3.0481`), MDD (`-14.95%` vs `-14.89%`), and volatility (`21.71%` vs `21.65%`).
- Multi-window stress: average final delta improves to `52,773` from `50,188`; min Sharpe delta improves to `+0.0324` from `+0.0115`; worst final drag is slightly worse (`-20,619` vs `-20,356`).
- A8 `focused_tdcc_0258_stab5_turn15` is retained as the fallback if near-term drawdown/volatility is prioritized over stress-average return and min Sharpe.

## 2026-06-14 A10 Improvement

- Promoted profile: `focused_tdcc_0124_stab5_turn15`.
- Change: TDCC bands `0/2/3/5 -> 0/1/2/4`; stability stays `5` days and risk_off/severe turnover cap stays `15%`.
- Recent replay vs A9: final improves slightly (`2,370,196` vs `2,370,171`) and cost falls (`21,411` vs `21,760`), with small tradeoffs in Sharpe (`3.0372` vs `3.0410`), MDD (`-14.98%` vs `-14.95%`), and volatility (`21.73%` vs `21.71%`).
- Multi-window stress: average final delta improves to `54,456` from `52,773`; min Sharpe delta improves to `+0.0348` from `+0.0324`; worst final drag is slightly worse (`-20,757` vs `-20,619`).
- A9 `focused_tdcc_0235_stab5_turn15` is retained as the fallback if balanced near-term Sharpe/MDD is prioritized.

## 2026-06-14 A11 Check

- Decision: no promotion; keep `focused_tdcc_0124_stab5_turn15`.
- `focused_tdcc_0124_stab2_turn12` improves recent final (`2,381,470`) and Sharpe (`3.0536`), but stress worst final drag worsens to `-27,574` and min Sharpe delta falls to `+0.0073`.
- `focused_tdcc_0258_stab2_turn08` improves stress robustness, but recent final falls to `2,358,623` and Sharpe falls to `2.9673`.
- Conclusion: A10 remains the best balanced formal baseline; A11 candidates are research-only.

## 2026-06-14 A12 Check

- Decision: no promotion; keep current 00631L stop/cooldown.
- `stop_disabled`, `stop_loose`, and `stop_base` match the current formal result exactly.
- `stop_fast` lowers recent final to `2,359,391` and Sharpe to `3.0276`.
- Conclusion: leverage stop/cooldown is not a useful improvement lever for the current A10 profile.

## 2026-06-14 A13 Improvement

- Promoted profile: `focused_tdcc_0124_stab5_turn15_fast_cd3`.
- Change: fast risk-off cooldown `5 -> 3` business days.
- Recent replay vs A10: final improves (`2,375,967` vs `2,370,196`) and Sharpe improves (`3.0401` vs `3.0372`), while MDD stays unchanged at `-14.98%`.
- Multi-window stress: average final delta improves to `57,089` from `54,456`; worst final drag and min Sharpe delta are unchanged (`-20,757`, `+0.0348`).
- `fast_disabled` improves stress average but fails recent replay; `fast_tight` hurts recent final. `fast_cd3` is the balanced upgrade.

## 2026-06-14 A14 Check

- Decision: no promotion; keep `focused_tdcc_0124_stab5_turn15_fast_cd3`.
- Tested low 00679B bands around A13: `0113`, `0114`, `0123`, and `0125`, all with `stab5_turn15_fast_cd3`; also retested `fast_cash20` and `fast_cash25`.
- Recent replay: current A13 remains best by final and Sharpe (`2,375,967`, Sharpe `3.0401`). `0113/0114` trail slightly (`2,375,372`, Sharpe `3.0359`); cash floor relaxations trail more.
- Multi-window stress: `0113/0114` improve average final delta (`59,036` vs `57,089`) but worsen worst final drag (`-20,906` vs `-20,757`) and min Sharpe delta (`+0.0341` vs `+0.0348`).
- Conclusion: the extra stress-average gain is too small to justify worse recent replay and slightly weaker guardrails. A14 variants remain research-only.

## 2026-06-14 A15 Improvement

- Promoted profile: `focused_tdcc_0124_stab5_turn14_fast_cd3`.
- Change: risk_off/severe turnover cap `15% -> 14%`; TDCC bands remain `0/1/2/4`, stability remains `5` days, and fast risk-off cooldown remains `3` business days.
- Recent replay vs A13: final improves (`2,378,609` vs `2,375,967`) and Sharpe improves (`3.0424` vs `3.0401`); MDD gives back slightly (`-15.03%` vs `-14.98%`) and volatility rises slightly (`21.79%` vs `21.78%`).
- Multi-window stress: worst final drag improves (`-20,127` vs `-20,757`) and min Sharpe delta improves (`+0.0382` vs `+0.0348`); average final delta falls modestly (`56,037` vs `57,089`).
- `turn13` has higher recent final but lower stress min Sharpe; `turn15` has higher stress average final but weaker recent replay, worse worst-window drag, and lower min Sharpe. `turn14` is the balanced upgrade.

## 2026-06-14 A16 Check

- Decision: no promotion; keep `focused_tdcc_0124_stab5_turn14_fast_cd3`.
- Tested fast risk-off variants on top of A15: `fast_loose`, `fast_tight`, `fast_cd2`, `fast_cash20`, and `fast_cash25`.
- Recent replay: A15 and `fast_loose` tie for best final/Sharpe (`2,378,609`, Sharpe `3.0424`). `fast_cash25` trails by about `7,296`; `fast_tight`, `fast_cd2`, and `fast_cash20` trail more.
- Multi-window stress: `fast_cash25` improves average final delta only slightly (`56,118` vs `56,037`) while leaving worst final drag and min Sharpe unchanged; this is too small to offset the recent replay drag.
- Conclusion: fast risk-off threshold/duration/cash-floor tuning is exhausted for the current A15 profile.

## Locked Decisions

- Keep DCA at `8000`
- Keep dividends as `cash`
- Do not use dynamic DCA
- Do not restore dividend reinvestment
- Keep `0124_stab5_turn14_fast_cd3`
- Keep TDCC bands `0/1/2/4`
- Keep VIX, turbulence, and second-stage controls disabled

## Operational Next Step

Use `GROUP_A_PLUS_CURRENT_BASELINE.json` as the formal pointer for daily runs. Regenerate the Group A signal first, then regenerate the GroupA+ final signal, then run `check_group_a_plus_daily_status.py`.
