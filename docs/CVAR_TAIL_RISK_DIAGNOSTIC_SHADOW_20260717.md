# CVaR Tail-Risk Diagnostic Shadow 交接（2026-07-17）

## 來源

- PDF：`C:\Users\isaac\Downloads\2607.03082v1.pdf`
- 論文：`Portfolio Optimization and Tail-Risk Analytics of Actively Managed ETFs`
- arXiv：`2607.03082v1`

## 論文可參考重點

這篇論文的價值在 portfolio risk diagnostics，不是直接交易訊號：

- portfolio 應同時看 return、drawdown、VaR、Expected Shortfall、tail thickness。
- CVaR optimization 可改善 downside control，但常犧牲 upside。
- Tangency / reward-to-risk 類策略可提升報酬，但 tail risk 與 turnover 更敏感。
- 相同 Sharpe 的 portfolio，MDD、ES、Hill tail index、POT-GPD tail shape 可能差很多。
- Long-short 對成本與估計誤差敏感，不適合直接套到 GroupA+。

## 本專案導入方式

新增 research-only evaluator：

- `scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py`

本次只做台股 ETF / cash proxy：

- `0050.TW`
- `00631L.TW`
- `cash`

策略 / proxy：

- `0050_only`
- `00631l_only`
- `golden1_frozen_proxy_50_20_30`
- `defensive_0050_70_cash30`
- `dynamic_min_cvar`
- `dynamic_tangency_cvar`

約束：

- long-only
- cash allowed
- `00631L <= 20%`
- grid step `5%`
- rolling lookback `252`
- rebalance every `21` trading days
- transaction cost proxy `10 bps`

不做：

- 不接 `daily_signal.py`
- 不改 GroupA+ 最新策略權重
- 不改 `golden1_0531`
- 不做 optimizer promotion

## 評估指標

- annualized return
- annualized volatility
- Sharpe
- Sortino
- max drawdown
- Calmar
- VaR loss 95 / 99
- Expected Shortfall loss 95 / 99
- STARR 95
- Hill tail index
- POT-GPD shape / scale

## 主視窗結果

視窗：`2025-01-02 ~ 2026-07-16`

| strategy | ann return | MDD | ES95 | VaR99 | Sharpe | STARR95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `0050_only` | 69.5% | -28.5% | 3.49% | 4.07% | 2.59 | 19.88 |
| `golden1_frozen_proxy_50_20_30` | 56.6% | -25.9% | 3.26% | 3.85% | 2.36 | 17.34 |
| `00631l_only` | 129.8% | -50.2% | 7.64% | 9.43% | 2.43 | 16.99 |
| `dynamic_tangency_cvar_net_cost10bps` | 14.6% | -11.0% | 1.73% | 2.21% | 1.28 | 8.45 |
| `dynamic_min_cvar_net_cost10bps` | 0.0% | 0.0% | 0.0% | 0.0% | 無 | 無 |

解讀：

- `dynamic_tangency_cvar` 明顯降低 MDD / ES，但犧牲大量報酬。
- `dynamic_min_cvar` 退化為全現金，符合最小 CVaR 目標但沒有投資意義。
- `00631L_only` 報酬最高，但 MDD 與 ES 也最大。
- Golden1 frozen proxy 沒有被替代的證據；它仍是報酬與風險之間的中間選擇。

主視窗 tail diagnostics：

| strategy | Hill 95 | POT-GPD 95 shape |
| --- | ---: | ---: |
| `0050_only` | 0.3121 | 0.3471 |
| `golden1_frozen_proxy_50_20_30` | 0.2855 | 0.3456 |
| `00631l_only` | 0.3263 | 0.1595 |
| `dynamic_tangency_cvar_net_cost10bps` | 0.3511 | 0.1179 |

解讀：

- 主視窗有足夠資料估 tail shape，但仍只能視為 diagnostic。
- GPD shape 對樣本與 threshold 敏感，不應作單獨交易規則。

## Crash / Stress Windows

### 2018 Correction

| strategy | ann return | MDD | ES95 | VaR99 | STARR95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `dynamic_tangency_cvar_net_cost10bps` | -0.4% | -1.5% | 0.31% | 0.50% | -1.27 |
| `golden1_frozen_proxy_50_20_30` | -5.7% | -13.7% | 2.31% | 2.13% | -2.47 |
| `0050_only` | -8.3% | -16.7% | 2.60% | 2.39% | -3.20 |
| `00631l_only` | -10.7% | -27.3% | 5.21% | 4.99% | -2.05 |

### 2020 COVID

| strategy | ann return | MDD | ES95 | VaR99 | STARR95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `dynamic_tangency_cvar_net_cost10bps` | -0.2% | -3.4% | 0.61% | 0.68% | -0.36 |
| `golden1_frozen_proxy_50_20_30` | -8.0% | -27.7% | 4.13% | 4.97% | -1.94 |
| `0050_only` | -15.1% | -30.5% | 4.55% | 5.51% | -3.33 |
| `00631l_only` | -10.8% | -52.1% | 9.45% | 11.26% | -1.15 |

### 2022 Rate-Hike

| strategy | ann return | MDD | ES95 | VaR99 | STARR95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `dynamic_tangency_cvar_net_cost10bps` | -2.0% | -2.6% | 0.38% | 0.49% | -5.27 |
| `golden1_frozen_proxy_50_20_30` | -32.2% | -30.3% | 2.66% | 2.98% | -12.11 |
| `0050_only` | -38.1% | -36.4% | 3.07% | 3.67% | -12.40 |
| `00631l_only` | -55.0% | -51.3% | 5.74% | 6.09% | -9.59 |

### 2026 Recent

| strategy | ann return | MDD | ES95 | VaR99 | STARR95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `00631l_only` | 395.6% | -21.2% | 7.32% | 8.82% | 54.06 |
| `dynamic_tangency_cvar_net_cost10bps` | 43.2% | -3.2% | 0.82% | 0.88% | 52.65 |
| `0050_only` | 159.1% | -10.8% | 3.32% | 3.95% | 47.89 |
| `golden1_frozen_proxy_50_20_30` | 126.7% | -9.7% | 3.11% | 3.73% | 40.69 |

## 最終決策

不導入 live。

原因：

- `dynamic_min_cvar` 退化成全現金，不能作策略替代。
- `dynamic_tangency_cvar` 可顯著降風險，但報酬拖累太大，不適合直接替代最新策略。
- Crash windows 證明 CVaR 類配置有防守價值，但 2026 recent 也顯示它會錯過槓桿 ETF 上行。
- POT-GPD / Hill 對樣本量敏感，短視窗多數 exceedance 不足，不能作 live trigger。
- 論文標的是美國 active ETF universe，不是台股 GroupA+。

可保留的研究價值：

- 作為 GroupA+ strategy review 的 tail-risk table。
- 用 ES95 / ES99 / MDD / POT-GPD 輔助人工 review。
- 未來若要做 daily report scorecard，可加入這類 tail diagnostics，但不得自動改權重。

## 產物

- `scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py`
- `results/cvar_tail_risk_diagnostic_shadow_20250102_20260716.json`
- `results/cvar_tail_risk_diagnostic_shadow_20250102_20260716_returns.csv`
- `results/cvar_tail_risk_diagnostic_shadow_20250102_20260716_allocations.csv`
- `results/cvar_tail_risk_diagnostic_shadow_2018_correction.json`
- `results/cvar_tail_risk_diagnostic_shadow_2020_covid.json`
- `results/cvar_tail_risk_diagnostic_shadow_2022_rate_hike.json`
- `results/cvar_tail_risk_diagnostic_shadow_2026_recent.json`

## 驗證命令

```bash
.venv/bin/python -m py_compile scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py
```

```bash
.venv/bin/python scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py --start 2025-01-02 --end 2026-07-16 --output results/cvar_tail_risk_diagnostic_shadow_20250102_20260716.json
```

```bash
.venv/bin/python scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py --start 2018-01-02 --end 2018-12-31 --output results/cvar_tail_risk_diagnostic_shadow_2018_correction.json
.venv/bin/python scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py --start 2020-01-02 --end 2020-06-30 --output results/cvar_tail_risk_diagnostic_shadow_2020_covid.json
.venv/bin/python scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py --start 2022-01-03 --end 2022-10-31 --output results/cvar_tail_risk_diagnostic_shadow_2022_rate_hike.json
.venv/bin/python scripts/evaluate/evaluate_cvar_tail_risk_diagnostic_shadow.py --start 2026-01-02 --end 2026-07-16 --output results/cvar_tail_risk_diagnostic_shadow_2026_recent.json
```
