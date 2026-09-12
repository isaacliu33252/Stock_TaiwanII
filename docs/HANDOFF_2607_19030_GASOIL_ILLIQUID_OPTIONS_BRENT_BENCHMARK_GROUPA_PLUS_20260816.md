# 2607.19030《Pricing options on illiquid assets using liquid market benchmarks: an application to energy markets》審查 — 交接記錄

**日期**：2026-08-16
**論文**：Aluigi, Caramellino, Pigato, Scrima (Enel Global Energy and Commodity Management / Università di Roma Tor Vergata)，*"Pricing options on illiquid assets using liquid market benchmarks: an application to energy markets"*
**結論**：**不適用，跟同日已審查的2608.12493、2607.29220同一類選擇權定價問題，Group A+無選擇權部位，快速排除。**

## 1. 論文核心

柴油(Gasoil)選擇權市場流動性差、報價稀疏不可靠，但柴油期貨跟高流動性的布蘭特原油(Brent)期貨高度相關。論文提出：

1. **雙變量correlated Bachelier local volatility模型**聯合建模布蘭特跟柴油期貨。布蘭特那端用Brigo-Mercurio normal mixture diffusion框架(藉由Fokker-Planck方程推導local volatility函數，讓futures價格的邊際分布是Gaussian mixture)去複製市場報價的隱含波動率微笑。
2. **柴油波動率 = 布蘭特波動率 + Gasoil-specific修正項h**，h只依賴時間跟crack spread(柴油-布蘭特價差)，用k-medians分群歷史「crack spread水準×波動率價差」的配置，把當下crack spread內插到分群中心點得出修正量——這是資料驅動、非參數的「液態市場資訊轉移到非流動市場」機制。
3. 整套模型用Monte Carlo模擬聯合布蘭特-柴油系統，反推柴油選擇權隱含波動率，最後用「柴油最終曲面=布蘭特市場報價曲面+模型算出的柴油-布蘭特波動率價差」錨定在真實流動的布蘭特報價上。

**實證結果**：用真實ICE市場資料(3個日期：2026-02-02平靜期、2026-04-21美伊衝突危機高峰、2026-05-26部分回穩)驗證，完整模型相對誤差3.28%~10.97%，遠優於「直接套用布蘭特波動率(h=0)」基準(23.76%~33.67%)跟「固定crack spread修正」基準(7.91%~8.98%)。論文誠實聲明柴油選擇權市場報價從未被用作模型輸入，只在事後拿來當驗證基準。

## 2. 為何不適用

核心產出是「柴油選擇權隱含波動率曲面」——整套機制(Bachelier定價公式、Fokker-Planck推導的mixture volatility、moneyness座標的smile比對、隱含波動率反推)全部是選擇權定價/避險專用的機器。**沒有選擇權部位就沒有東西可以套用**，跟今天稍早排除的兩篇同類：

- `2608.12493`(選擇權曲面transport幾何)
- `2607.29220`(選擇權IVS diffusion預測+SAAM修正)

三篇的排除邏輯完全相同：Group A+可交易資產(0050.TW/00631L.TW/00632R.TW/00679B.TWO)無選擇權部位，這個事實已在`2608.12493`審查時用WebSearch確認(00631L/00632R是台指期貨為主的槓桿/反向ETF，來源pocket.tw/元大投信官網/gugu.fund)，不需要重新查證。

## 3. 次要考量：「用流動資產當基準修正非流動資產」這個meta想法能否脫離選擇權套用？

評估後不成立。這個技巧的應用對象具體是「幫illiquid資產構建隱含波動率曲面」，Group A+沒有在對00631L/00632R「定價選擇權」——是直接持有/交易這些ETF現貨本身，沒有「用0050當流動性基準去修正00631L選擇權報價」這種問題存在。00631L/00632R本身的市場流動性(成交量)雖然可能不如0050，但這是「交易執行流動性」問題，不是「選擇權報價流動性」問題，論文的crack-spread clustering修正機制不是為前者設計的。

## Do Not Do
- 不要因為論文標題有"illiquid assets"、"liquid market benchmarks"這類聽起來通用的詞彙就假設可以套用——核心機制(隱含波動率曲面重建)綁死在選擇權定價上。
- 後續若再遇到選擇權曲面/定價類論文，直接引用「Group A+無選擇權部位」（來源見`docs/HANDOFF_2608_12493_VARIANCE_SURFACE_TRANSPORT_GROUPA_PLUS_20260816.md`）快速判定不適用，不需要重新深入分析論文內容——這是今天第三次套用同一個排除理由。

## Next Step
無——架構層級的問題不匹配，跟前兩篇選擇權論文同一個乾淨結論，沒有留下待辦事項。

詳細記錄完。
