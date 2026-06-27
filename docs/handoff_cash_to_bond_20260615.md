# 交接記錄：Group A+ Cash→Bond 實驗（2026-06-15）

## 背景問題

使用者觀察到 `latest` (predict_20260615) 輸出：
- 0050.TW: 59.7%
- 00631L.TW: 10.3%
- **cash: 30%**
- 00679B: 0%

提出疑問：FinRL 留 30% cash，是否應該把這 30% 轉成 00679B？

---

## 實驗紀錄

### 實驗目的
比較兩種情境：
- **情境 A（production）**：risk_on regime 保留 cash（~30%）
- **情境 B（cash_to_bond）**：risk_on regime 把 cash 轉成 00679B

### 實驗方式
新建 `backtest_cash_to_bond.py`，使用合成信號（2020-04-09 ~ 2026-06-12，共 1503 交易日）。

信號 regime 邏輯：
- MA20-MA60 gap > +5% → risk_on，cash=30%
- MA20-MA60 gap > 0% → risk_on，cash=20%
- MA20-MA60 gap > -7% → caution，cash=5%
- MA20-MA60 gap ≤ -7% → risk_off，cash=2%

Overlay：risk_on=0% 00679B，caution=2%，risk_off=5%，severe=8%

### 實驗結果

| 指標 | Production (A) | Cash→Bond (B) | 差異 |
|------|---------------|---------------|------|
| Final | 992,329 | 991,481 | **-848** |
| Sharpe | -2.649 | -2.589 | **+0.060** |
| MDD | -0.77% | -0.85% | -0.08% |

### 結論
- 差異極小（不到 0.1%），方向不明確
- Sharpe 以 Cash→Bond 略好，但 Final 以 Production 略高
- 合成信號邏輯與真實 FinRL 決策不同，結果僅供方向參考

---

## 核心發現

### 為何 FinRL 留 30% cash？
這是 FinRL meta-ensemble 在 computing regime 的風險控制邏輯。當 regime 判斷市場偏高，自動提高 cash 權重來保護資本。**不是 overlay 加的，是 FinRL base 輸出的。**

### 為何 Cash→Bond 效果不明顯？
00679B 在 2020~2026 期間的價格成長有限（約 42→58，約 +38%）。相對於股票部位（0050 約 +70%）， bond 長期報酬率較低。在 risk_on 時期持有 bond 而非 cash，機會成本高，彌補不了 cash 的「無風險」特性。

### Cash 的角色
Cash 在 FinRL 框架中是「暫時立場，等待進場時機」的緩衝，不是閒置資產。在高檔持有 cash，等 market regime 反轉時可以直接進場、風險較低。轉成 00679B 反而鎖住在 bond 裡。

---

## 建議方向（需回測確認）

### 方向 1：不做 cash→bond 轉換（當前結論）
從這個實驗看，差異太小，不值得動到 production 邏輯。建議維持現狀。

### 方向 2：如果要進一步實驗
在 `_normalize_group_weights` 之後加一個參數化開關 `--cash-to-bond-threshold`，設定當 cash > X% 且 regime == risk_on 時才轉換，而非always 轉。搭配真實 FinRL 信號（2025~2026 期間）做對比回測。

### 方向 3：FinGenius 整合（最高優先）
優先整合**主力成本乖離率**到 Group A+ switch 判斷。這是 FinGenius 的核心優點，能更即時抓到主力成本偏離，當偏離擴大時提前進 bond defense。

---

## 檔案狀態

- `backtest_cash_to_bond.py` — 新建，實驗用，未進入 production
- `group_a_00679b_continuous_shadow.py` — **未修改**，維持原樣
- `group_a_plus_config.json` — **未修改**，維持原樣

---

## 最後確立的原則

**不做修改原則**：所有新變更都必須先回測驗證有改善，才能保留进 production。

---

## 尚未解決的問題

1. **FinRL PVA overlay cash 注入點**：Cash 在 FinRL 內部哪層注入，需往上追源頭才能正確實現 cash→00679B 轉換
2. **真實信號覆蓋範圍**：現有 `signal_group_a_*.json` 只覆蓋 2025~2026，2020~2024 需靠合成信號
3. **年輪記憶算法**：尚未評估是否值得整合
