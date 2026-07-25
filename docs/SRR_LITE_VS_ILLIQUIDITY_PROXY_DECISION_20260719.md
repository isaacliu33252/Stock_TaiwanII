# SRR-lite vs Daily Illiquidity Proxy Decision（2026-07-19）

## Question

SRR-lite 有用嗎？是否應該用 `2004.01917` 的 daily OHLCV
illiquidity proxy 改 SRR 或升級 GroupA+ live 策略？

Detailed final handoff:

- `docs/DETAILED_HANDOFF_2004_01917_SRR_ILLIQUIDITY_GROUPA_PLUS_20260719.md`

## Short Answer

SRR-lite 有用，但只能保留為 shadow / manual-review no-add 診斷。

不要用 daily illiquidity proxy 改 SRR-lite，也不要把 SRR-lite 升級成
自動減碼、自動 rebalance、或 live target-weight gate。

## Evidence

Latest overlap artifact:

- `report/group_a_plus/latest/illiquidity_daily_proxy_overlap.json`
- overlap window: `2025-01-02` to `2026-07-16`
- rows: `371`

Comparison:

| Signal | Active days | H10 precision | H10 recall | H10 FPR |
|---|---:|---:|---:|---:|
| SRR no-add | `8` | `0.5` | `0.03125` | `0.01646090534979424` |
| Illiquidity elevated-or-worse | `18` | `0.3888888888888889` | `0.0546875` | `0.04526748971193416` |
| Union: SRR no-add OR illiquidity elevated | `25` | `0.4` | `0.078125` | `0.06172839506172839` |
| Intersection: SRR no-add AND illiquidity elevated | `1` | `1.0` | `0.0078125` | `0.0` |

Overlap:

- illiquidity elevated-or-worse active days: `18`
- SRR no-add active days: `8`
- both active days: `1`
- Jaccard: `0.04`

Interpretation:

- Daily illiquidity proxy is not merely duplicating SRR-lite.
- But its added dates are lower quality than SRR no-add.
- Union improves recall slightly but raises false positives too much.
- Intersection is high precision but only one day, too sparse to use.

## Decision

Keep:

- SRR no-add as conservative shadow no-add diagnostic.
- SRR crash-watch as low-level manual crash watch.
- Daily illiquidity proxy as research-only context.

Do not promote:

- no live target-weight change;
- no auto rebalance;
- no automatic `00631L` reduction;
- no `00631L` add unlock;
- no `00632R` open;
- no SRR threshold change from this proxy.

## Operational Use

SRR-lite should answer:

- should a human be more careful before adding `00631L`?
- is there a low-frequency systemic fragility warning worth reviewing?

SRR-lite should not answer:

- should the system automatically sell?
- should GroupA+ rebalance now?
- should the strategy open `00632R`?
- should daily illiquidity proxy override existing SRR output?

## Current Live Policy

Keep existing SRR no-add rule unchanged:

```text
systemic_fragility_score >= 0.65
graph_density >= 0.65
graph_velocity >= 0.18
```

Keep existing SRR crash-watch rule as manual review only:

```text
systemic_fragility_score >= 0.75
graph_density >= 0.65
```

## Final Conclusion

SRR-lite remains more useful than the daily OHLCV illiquidity proxy.

The correct action is to retain SRR-lite as a conservative shadow diagnostic,
not to modify live strategy behavior.
