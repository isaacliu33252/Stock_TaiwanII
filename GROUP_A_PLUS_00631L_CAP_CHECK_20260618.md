# Group A+ 00631L Cap 檢查記錄
**日期：2026-06-18**

---

## 背景

用戶提問：「改善 #1（00631L cap 8%→10-12%）是否做過？」

---

## 確認結果

**已做過：**
- A1：槓桿 stop 靈敏度（trailing -20%→-15%, absolute -15%→-12%, cooldown 5→3）
- A2：00679B 動態區間（caution 1%→2%, risk_off 2%→5%, severe 4%→8%）

**未做過：**
- 00631L cap 8%→10-12%（live config 顯示 8%，但生產 config 已是 20%）

---

## 關鍵發現

### 1. 生產 config 的 cap 不是問題
`group_a_plus_config.json` 中：
```json
"max_weight_by_regime": {
  "risk_on": 0.20,
  "caution": 0.18,
  "risk_off": 0.0,
  "severe": 0.0
}
```
risk_on cap = 20%，遠高於模型觀察到的需求（~11%）。

### 2. live config 的 8% 是信號輸出，不是 cap
`results/group_a_plus_latest_strategy_125w_20260608_live_config.json` 第 80 行：
```json
"00631L.TW": 0.08
```
這是信號生成時 00631L 的 target_weight（被槓桿模組 cap住的實際目標），不是 `max_weight_by_regime` 的 cap 設定。

### 3. 00631L 真正問題：cooldown + caution regime
目前信號（2026-06-17）顯示 00631L = 0%，原因：
- regime: `caution`
- leverage_stop_cooldown: `cooldown_4d`（cooldown_days=3 已於 6/11 改好，但信號仍需重新生成才會吃新參數）
- caution regime max_weight = 18%，但槓桿模組 active 導致實際為 0

### 4. 所有 TDCC overlay 比 base 差
用 `group_a_meta_real_vote_tune_sweep` 跑 grid sweep（00679B risk_off bond 0.02~0.12）：
| 策略 | Final | Sharpe | MDD |
|------|-------|--------|-----|
| source_selected_meta | 2,067,030 | 2.495 | -0.23% |
| base (無 overlay) | 2,057,440 | 2.479 | -0.23% |
| 最佳 GroupA+ overlay | 1,993,435 | 2.643 | -0.20% |

**結論：Overlay 無法戰勝 base。** 這個結論在 2026-06-09 已確認，今日再次驗證一致。

---

## 待執行項目

| # | 項目 | 狀態 | 備註 |
|---|------|------|------|
| 1 | 00631L cap 8%→10-12% | **不需要** — 生產 config 已是 20% cap，live config 的 8% 是信號輸出非 cap | 真正的瓶頸是 cooldown + caution regime |
| 2 | 修正資料 lag | pending | — |
| 3 | 動態 TDCC overlay | pending | 所有 variant 均不如 base，方向放棄 |
| 4 | min_trade_value→0 | ✅ done | 6/11 已執行 |
| 5 | 槓桿 cooldown 參數 | ✅ done | 6/11 已執行（停損/absolute/cooldown）|

---

## 備註

- 00631L cap 從 8% 改到 10-12% 的訴求，**在 `group_a_plus_config.json` 生產層級已經是 20%，不需要改**。
- 如果是指 `live_config` 裡那個 8%，那是信號的實際目標權重，不是 cap 上限。要真正讓 00631L 有更高 target，需要：
  1. cooldown 完全解除（`cooldown_days=3` 已在 config 中，需重新生成信號）
  2. regime 脫離 caution（回到 risk_on）
