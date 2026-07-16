# results/ 清理候選清單（2026-07-08）

判定方式：檔名字串在整個 repo（排除 `.git` 和 `results/` 自身）的 `.md`/`.json`/`.py` 檔案中皆搜尋不到 —— 沒有任何 strategy.json、交接文件或程式碼引用這些檔案。皆為已否決實驗（BayesOpt/特徵掃描等）的舊 sweep 結果，日期落在 2026-06-03～06-18。

僅涵蓋 `results/` 前 20 大檔案的檢查結果，尚有 3-18MB 區間的候選未逐一檢查完。

## 2026-07-08 執行結果

已改採「壓縮封存後刪除原始檔」。

- Archive: `results/archive/results_retention_candidates_20260708.tar.gz`
- Archive size: `35M`
- Archive entries: `27`
- Archive contents:
  - 本檔 `RESULTS_RETENTION_CANDIDATES_20260708.md`
  - 下列 11 個候選 JSON
  - 與 11 個 JSON 同 stem 的 `.csv`
  - 與 GroupA+ overlay 類同 stem 的 `_curve.csv`
- 原始 JSON 大小合計：`507M`
- 原始 JSON/CSV/curve 已自 `results/` 刪除
- 本 md 保留在 repo root 作索引

驗證：

```bash
tar -tzf results/archive/results_retention_candidates_20260708.tar.gz | wc -l
# 27

ls -lh results/archive/results_retention_candidates_20260708.tar.gz
# 35M
```

判斷：

- 這批檔案仍有研究/審計價值：可追溯舊 sweep 為何被否決，或完整復查 variant metrics。
- 這批檔案沒有現役運行價值：未被程式、config、latest pointer、handoff 正式引用。
- 因此保留壓縮檔即可，原始大檔不需留在 `results/`。

注意：

- 同系列但仍被使用的 newer/current 檔案未刪，例如：
  - `results/group_a_meta_real_vote_tune_sweep_20250101_20260606_llmfilled.json`
  - `results/group_a_meta_real_vote_tune_sweep_20250101_20260611.json`
  - `results/group_a_plus_grid_sweep_20250102_20260605.json`
- `results/group_a_plus_grid_sweep_20250102_20260605.json` 雖與 `_dca` 同系列，但 2026-06-06 handoff 明確列為當天輸出，未納入本次刪除。

## 用途回查摘要

| 檔案 stem | 原用途 | 判斷 |
|---|---|---|
| `group_a_meta_real_balanced_controls_sweep_20200101_20260603` | Group A meta ensemble risk-off control / TDCC cap / balanced score 掃描 | 舊版掃描，現役設定已轉到後續 vote_tune 檔 |
| `group_a_meta_real_balanced_controls_sweep_20200101_20260603_v2` | 上述 balanced_controls 的 v2 重跑 | 舊版重跑，無引用 |
| `group_a_meta_real_riskoff_micro_sweep_20200101_20260603` | risk-off defensive intensity 微調 | 舊版掃描，無引用 |
| `group_a_meta_real_voting_bear_sweep_20250101_20260603_llmfilled` | regime vote / bear filter / recovery 組合掃描 | 後續由 vote_tune 系列取代 |
| `group_a_meta_real_recovery_sweep_20250101_20260603_llmfilled` | recovery step / cash 參數掃描 | 舊版掃描，無引用 |
| `group_a_meta_real_recovery_riskon_sweep_20250101_20260603_llmfilled` | recovery + risk-on 版本掃描 | 舊版掃描，無引用 |
| `group_a_meta_real_vote_tune_sweep_20250101_20260608` | vote tune / bear defense / recovery defense22 掃描 | 同系列有 20260606/20260611 仍作為現役/近現役紀錄；此 20260608 檔無引用 |
| `group_a_plus_grid_sweep_20250102_20260605_dca` | GroupA+ overlay grid，含 DCA 設定 | 旁支重跑，無引用 |
| `group_a_plus_grid_sweep_20250102_20260608` | 2026-06-08 GroupA+ overlay grid 重跑 | overlay 未優於 base，無引用 |
| `group_a_plus_00631l_cap_sweep` | 00631L cap / TDCC overlay 驗證 | 2026-06-18 結論已寫入 handoff：cap 不是瓶頸，overlay 不如 base |
| `recheck_group_a_plus_00631l_cap_sweep_20260618` | 2026-06-18 重新驗證 | 與原 cap sweep 同結論，無引用 |

## 已封存並刪除的原始檔

Archive 內含以下 27 個項目：

```text
RESULTS_RETENTION_CANDIDATES_20260708.md
results/group_a_meta_real_balanced_controls_sweep_20200101_20260603_v2.json
results/group_a_meta_real_balanced_controls_sweep_20200101_20260603_v2.csv
results/group_a_meta_real_balanced_controls_sweep_20200101_20260603.json
results/group_a_meta_real_balanced_controls_sweep_20200101_20260603.csv
results/group_a_meta_real_riskoff_micro_sweep_20200101_20260603.json
results/group_a_meta_real_riskoff_micro_sweep_20200101_20260603.csv
results/recheck_group_a_plus_00631l_cap_sweep_20260618.json
results/recheck_group_a_plus_00631l_cap_sweep_20260618.csv
results/recheck_group_a_plus_00631l_cap_sweep_20260618_curve.csv
results/group_a_plus_00631l_cap_sweep.json
results/group_a_plus_00631l_cap_sweep.csv
results/group_a_plus_00631l_cap_sweep_curve.csv
results/group_a_plus_grid_sweep_20250102_20260605_dca.json
results/group_a_plus_grid_sweep_20250102_20260605_dca.csv
results/group_a_plus_grid_sweep_20250102_20260605_dca_curve.csv
results/group_a_meta_real_voting_bear_sweep_20250101_20260603_llmfilled.json
results/group_a_meta_real_voting_bear_sweep_20250101_20260603_llmfilled.csv
results/group_a_meta_real_vote_tune_sweep_20250101_20260608.json
results/group_a_meta_real_vote_tune_sweep_20250101_20260608.csv
results/group_a_meta_real_recovery_sweep_20250101_20260603_llmfilled.json
results/group_a_meta_real_recovery_sweep_20250101_20260603_llmfilled.csv
results/group_a_meta_real_recovery_riskon_sweep_20250101_20260603_llmfilled.json
results/group_a_meta_real_recovery_riskon_sweep_20250101_20260603_llmfilled.csv
results/group_a_plus_grid_sweep_20250102_20260608.json
results/group_a_plus_grid_sweep_20250102_20260608.csv
results/group_a_plus_grid_sweep_20250102_20260608_curve.csv
```

## 檔案清單（共約 512MB）

```
results/group_a_meta_real_balanced_controls_sweep_20200101_20260603_v2.json
results/group_a_meta_real_balanced_controls_sweep_20200101_20260603.json
results/group_a_meta_real_riskoff_micro_sweep_20200101_20260603.json
results/recheck_group_a_plus_00631l_cap_sweep_20260618.json
results/group_a_plus_00631l_cap_sweep.json
results/group_a_plus_grid_sweep_20250102_20260605_dca.json
results/group_a_meta_real_voting_bear_sweep_20250101_20260603_llmfilled.json
results/group_a_meta_real_vote_tune_sweep_20250101_20260608.json
results/group_a_meta_real_recovery_sweep_20250101_20260603_llmfilled.json
results/group_a_meta_real_recovery_riskon_sweep_20250101_20260603_llmfilled.json
results/group_a_plus_grid_sweep_20250102_20260608.json
```

| 大小 | 檔名 |
|---|---|
| 93M | group_a_meta_real_balanced_controls_sweep_20200101_20260603_v2.json |
| 90M | group_a_meta_real_balanced_controls_sweep_20200101_20260603.json |
| 77M | group_a_meta_real_riskoff_micro_sweep_20200101_20260603.json |
| 66M | recheck_group_a_plus_00631l_cap_sweep_20260618.json |
| 66M | group_a_plus_00631l_cap_sweep.json |
| 21M | group_a_plus_grid_sweep_20250102_20260605_dca.json |
| 21M | group_a_meta_real_voting_bear_sweep_20250101_20260603_llmfilled.json |
| 20M | group_a_meta_real_vote_tune_sweep_20250101_20260608.json |
| 20M | group_a_meta_real_recovery_sweep_20250101_20260603_llmfilled.json |
| 20M | group_a_meta_real_recovery_riskon_sweep_20250101_20260603_llmfilled.json |
| 18M | group_a_plus_grid_sweep_20250102_20260608.json |

## 2026-07-09 後續盤點（未刪檔）

背景：`GROUP_A_PLUS_VOLATILITY_GATE_SHADOW_HANDOFF_20260709.md` 記錄 daily pipeline
當天成功，但 ops health 有 disk free below 2% 類警告。2026-07-09 晚間再次確認
workspace 所在 C 槽狀態：

```text
C:\ 238G total / 234G used / 4.0G available / 99% used
results/ 1.1G
report/ 4.2M
logs/ 716K
.pytest_cache/ 84K
FinRL/catboost_info/ 60K
catboost_info/ 60K
```

同時補跑較寬 GroupA+ 回歸測試：

```bash
.venv/bin/python -m pytest \
  tests/test_group_a_plus_daily_signal_v2.py \
  tests/test_group_a_plus_alert_state.py \
  tests/test_group_a_plus_signal_alignment.py \
  tests/test_group_a_plus_market_state.py \
  tests/test_group_a_plus_ops_health.py \
  tests/test_run_ncf_daily_pipeline.py \
  tests/test_group_a_plus_garch_regime_shadow.py \
  tests/test_evaluate_group_a_plus_volatility_gate_shadow.py \
  tests/test_group_a_plus_push_notifications.py
```

結果：

```text
142 passed, 3 warnings
```

warnings 仍是 `backtest_group_a_plus_switch_policy.py:530` 的 pandas
`FutureWarning`，與 volatility gate / alert metadata / push notification 邏輯無關。

### 後續可封存候選

以下 20260618 switch/risk sweep 大檔只在 handoff/review markdown 中被引用為歷史輸出，
未看到程式、config、latest pointer 或測試直接依賴。它們仍有審計價值，但看起來
不需要以原始 JSON 形式常駐 `results/` 根目錄；可比照 2026-07-08 做
「tar.gz 封存後刪原始 JSON/CSV」。

本段僅列候選，2026-07-09 未執行刪檔。

| 大小 | 檔案 |
|---:|---|
| 82M | `results/group_a_plus_switch_micro_sweep_2020_2024_20260618.json` |
| 64M | `results/group_a_plus_switch_chip_deriv_total_sweep_20260618.json` |
| 56M | `results/group_a_plus_switch_sweep_smart_money_cost_20260618.json` |
| 40M | `results/group_a_plus_latest_risk6_fine_sweep_20260618.json` |
| 2.7M | `results/group_a_plus_latest_risk6_fine_sweep_20260618.csv` |
| 2.0M | `results/group_a_plus_switch_chip_deriv_total_sweep_20260618.csv` |
| 999K | `results/group_a_plus_switch_sweep_smart_money_cost_20260618.csv` |
| 492K | `results/group_a_plus_switch_micro_sweep_2020_2024_20260618.csv` |

引用檢查摘要：

```text
group_a_plus_switch_sweep_smart_money_cost_20260618
  - GROUP_A_PLUS_SMART_MONEY_COST_PROXY_20260618.md

group_a_plus_switch_chip_deriv_total_sweep_20260618
group_a_plus_switch_micro_sweep_2020_2024_20260618
group_a_plus_latest_risk6_fine_sweep_20260618
  - GROUP_A_PLUS_RISK6_CONFIRM_HANDOFF_20260618.md
  - report/group_a_plus/review/md/risk6_confirm_handoff_20260618.md
```
