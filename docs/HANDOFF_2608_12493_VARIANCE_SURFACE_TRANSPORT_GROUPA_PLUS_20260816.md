# 2608.12493 Beyond the Skew-Stickiness Ratio (Variance Surface Transport Geometry) — Group A+ 適用性審查

**日期**：2026-08-16
**論文**：Che & Das (2026), *"Beyond the Skew-Stickiness Ratio: Transport Geometry of Spot-Driven Variance Surface Dynamics"*, JPMorganChase Quantitative Trading & Research / Equity Derivatives Group
**結論**：**不導入 Group A+ / a2118（最新策略）**，判定 research_only，不需回測驗證即可關閉。

## 論文方法論摘要

- 研究選擇權隱含波動率曲面（implied variance surface, w(k,T)=σ²(k,T)T）如何隨標的價格變動而動態變形，把skew-stickiness ratio（SSR，經典經驗法則：ATM skew隨標的移動的黏滯係數）統一進一套「transport geometry」理論。
- 核心貢獻：把SSR推廣成一個transport velocity field v(k)，其Taylor jet β=v(0)（SSR本身）、η=∂ₖv(0)（skew-transport係數）、ψ=∂ₖₖv(0)（curvature-transport係數）構成完整hierarchy；證明在特定Lipschitz/positivity條件下，這個transport flow能保持曲面無蝶式(butterfly)/日曆(calendar)價差套利機會。
- 實證用SPX選擇權曲面資料(2021-2026, 7個到期日)驗證：SSR的β隨到期日單調遞減(1M時1.4375降到24M時1.0114)，self-similar transport(η=ψ=0)在所有到期日都被拒絕，skew-transport velocity的strike剖面在中期到期日呈U型、長期到期日呈單調遞減。Out-of-sample驗證顯示完整(β,η,ψ)模型比純SSR在curvature動態上改善17-21%。

## 為何不適用

**論文整套機制是選擇權造市/曲面風控的數學**（隱含變異數曲面、蝶式/日曆arbitrage-free條件、transport velocity field、vanna/volga曝險管理），存在意義是給有選擇權部位的交易台用來動態對沖smile risk。Group A+的標的（0050/00631L/00632R/00679B）是現貨/期貨型ETF regime timing系統，沒有選擇權部位需要管理曲面風險，論文的核心機制沒有轉譯空間。

### 使用者質疑並查證：00631L/00632R是否為選擇權產品？

使用者提出「00631L, 00632R都是選擇權」的質疑，這點如果成立會直接推翻上述結論。**用WebSearch查證後確認：這個說法不準確**。

- **00631L（元大台灣50正2）**：官方說明「以做多期貨為主要交易」，主力是台指期貨(TX)多單，搭配約40%台積電等權值股現貨部位。選擇權只是法規允許運用的衍生性商品之一，非主要複製工具。（來源：[口袋學堂](https://www.pocket.tw/school/report/ETF/3177/)、[元大投信官網](https://www.yuantaetfs.com/product/detail/00631L/Basic_information)）
- **00632R（元大台灣50反1）**：主要是「放空台指期貨」搭配RP債券附買回（約7成部位），一樣以期貨為主，不是選擇權。（來源：[元大投信官網](https://www.yuantaetfs.com/product/detail/00632R/Basic_information)、[gugu.fund](https://school.gugu.fund/blog/ETF/4082777470)）

兩者都屬於**期貨型槓桿/反向ETF**（台灣槓桿/反向ETF業界慣例與法規框架都是以台指期貨為核心複製工具，法規上雖允許選擇權等衍生品但非主力），不是選擇權型產品。**原本的「不適用」結論維持不變**。

### 唯一沾邊的既有機制：`trough_nowcast.py`的SOXX IV skew特徵

`group_a_plus/integrations/trough_nowcast.py`裡有`soxx_put_call_iv_skew_z252`——SOXX選擇權put/call IV skew的z-score，當作cross-market shock的門檻條件（shadow機制）。但這只是**單一時間點的skew水準快照**，不是論文要解決的「skew如何隨標的動態變動」問題；既有做法（z-score門檻）已經是這個單一特徵綽綽有餘的處理方式，沒有必要引入整套曲面transport幾何。

## Do Not Do
- 不要因為00631L/00632R「法規上允許用選擇權」就假設論文機制可以套用——複製策略主力仍是期貨，選擇權曲面動態不是這些ETF淨值變動的驅動因子。
- 不要嘗試把`soxx_put_call_iv_skew_z252`升級成完整的transport velocity field——既有z-score門檻用途單純（cross-market shock gating），殺雞用牛刀。

## Next Step
無。此論文已收手，不需要後續行動。若未來Group A+真的擴大到交易選擇權（目前無此規劃），可重新評估這篇論文的transport geometry框架。
