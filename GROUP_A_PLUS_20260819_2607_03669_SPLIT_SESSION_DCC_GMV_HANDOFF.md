# Group A+ 2026-08-19: arXiv:2607.03669 Split-Session Cluster GARCH — 完整建模實測

**日期**：2026-08-19（同日稍晚的另一個session，延續同日稍早的`GROUP_A_PLUS_20260819_2607_03669_OVERNIGHT_INTRADAY_SESSION_SPLIT_HANDOFF.md`）
**論文**：arXiv:2607.03669 — Chen, Hansen & Tong, "Split-Session Cluster GARCH for Overnight and Intraday Returns: The Role of Tail Heterogeneity"
**狀態**：**closed，research_only，不promote**

## 0. 跟同日稍早那份handoff的關係（重要，避免下次搞混）

同日稍早的`GROUP_A_PLUS_20260819_2607_03669_OVERNIGHT_INTRADAY_SESSION_SPLIT_HANDOFF.md`測的是**使用者自己提的簡化版sanity check**（overnight×intraday方向組合4分類，ANOVA/t-test測能不能預測未來1/3/5天報酬），跟論文實際做的事情是**兩個不同問題**，那次null result不能代表論文本身被推翻。

這次（本文件）**直接讀了PDF全文**，確認論文真正的貢獻是：把每日報酬拆成overnight/intraday兩段，用session分離的動態相關性模型（+厚尾異質性）估計多資產共變異數矩陣，應用在GMV（全域最小變異數）投資組合上。本文件記錄對這個「真正的論文方法」在Group A+實際4檔交易資產（0050/00631L/00632R/00679B）上的完整實測。

## 1. 使用者需求脈絡

使用者先問「這份PDF分析過了嗎」→ 發現只是憑轉述測過，要求讀PDF全文核對。讀完後確認：論文核心是session分離+厚尾異質性的動態相關性建模，跟08-19稍早測的「事件表預測未來報酬」是不同問題。使用者選擇「小規模驗證可行性」（先測靜態尾部厚度差異值不值得投入），通過後選擇「做完整的」，於是做了完整的兩階段GARCH建模+DCC評估，之後使用者追問「還有實驗要做」，繼續做了第二層的真實報酬GMV測試。

## 2. Phase 0：小規模可行性驗證（靜態尾部厚度）

用`FinRL/data/stock_data.db`的`ohlcv`表算0050/00631L/00632R/00679B的overnight/intraday報酬，對每個session分別擬合Student-t自由度（數值越低=尾部越厚）。

**過程中意外抓到資料品質問題**：
1. `0050.TW`有2筆`open=0`的髒資料（2009-08-13、2010-01-25，此前未被記錄過）。
2. 命中3個已知但**未回溯調整**的公司行動價格斷點（08-16 session的`project_2608_00127_drawdown_bootstrap_calibration_20260816`已診斷過，但那次的修正**只套用在衍生分析曲線，沒有回寫`ohlcv`表本身**，所以這次重新從DB查詢又踩到）：
   - `0050.TW` 2014-01-02 真實1:4分割（比例0.25000）
   - `00631L.TW` 2015-01-05 真實~1:22反向合併（比例0.04569）
   - `00632R.TW` 2024-12-02 真實~1:7反向合併（比例6.93787）

用break當天`open/前一日close`的比例回溯調整斷點前所有價格後，最極端的overnight報酬全部對應到真實市場事件（2015-08-24中國黑色星期一、2025-04-07/04-10川普關稅崩盤、2020-03 COVID崩盤、2009 GFC），沒有其他隱藏資料錯誤。

**結果（清理後）**：

| 資產 | overnight 自由度 | intraday 自由度 |
|---|---|---|
| 0050.TW | 1.51 | 2.17 |
| 00631L.TW | 2.27 | 3.39 |
| 00632R.TW | 2.31 | 3.35 |
| 00679B.TWO | 2.88 | 3.27 |

4檔資產全部方向一致（overnight比intraday厚尾），跟論文US股票應用（overnight ν≈3.3、intraday ν≈11.0；100資產Hetero-t應用overnight均值2.62、intraday均值6.20）定性相符，但分離度較小（我們約1.1~1.5倍 vs 論文2.4~3.3倍）——合理解釋是Taiwan這4檔是指數/槓桿/反向ETF，沒有個股盤後財報消息驅動的overnight跳空，異質性天然較小。**Gate通過**，決定投入完整建模。

## 3. Phase 1：完整Split-Session DCC-t建模

### 3.1 方法論範圍決策（重要，之後若有人想擴充要先知道這個）

論文完整方法包含：(a) Coupled EGARCH（含跨session均值/波動率spillover耦合項）、(b) score-driven動態相關性（Archakov-Hansen矩陣對數參數化 + Fisher information scaling的VAR(1)遞迴）、(c) convolution-t分布的cluster尾部異質性、(d) canonical block representation（給大資產數用的降維技巧）。

**這次的實作範圍**：
- 環境沒有`arch`/`statsmodels`套件（`pip install`因`externally-managed-environment`被擋，且不想動系統共用Python環境去裝），全部用純numpy/scipy手刻。
- 拿掉論文的跨session mean/volatility spillover耦合項（Section 2的δ參數）——8個序列當獨立EGARCH(1,1)-t處理，是刻意的範圍簡化。
- **用論文自己的DCC-t benchmark引擎（Section 6），不是論文主打的score-driven矩陣對數GAS估計器（Section 3-5）**——後者的數值穩定性風險更高，在還不知道「session分離這個核心機制對Group A+這4檔資產有沒有用」之前，不值得投入更複雜的基礎設施。DCC-t本身就是論文自己拿來對照的benchmark，足以回答核心問題。
- 4資產不需要論文Section 5.4的block/canonical representation（那是給大資產數降維用的，d=n(n-1)/2=6維對4資產是trivial）。

### 3.2 Pipeline

**Stage 1**：每資產每session獨立擬合EGARCH(1,1)-t（8個模型），得到標準化殘差Z^N_t, Z^D_t：
```
log h_t = ω + β log h_{t-1} + τ1 z_{t-1} + τ2(|z_{t-1}| - sqrt(2/π))
```
MLE用`scipy.optimize.minimize`（Nelder-Mead）。全部8個fit收斂，nu範圍2.79~5.85，beta持續性0.92~1.0（部分逼近1.0上界，高波動叢聚很常見）。

**Stage 2**：在共同重疊窗口（2017-01-12~2026-08-18，n=2330天，00679B最晚上市決定起點）用corrected-DCC(cDCC, Aielli 2013)遞迴：
```
Q_{t+1} = (1-α-β)Q̄ + β Q_t + α (z_t z_t')
C_t = diag(Q_t)^{-1/2} Q_t diag(Q_t)^{-1/2}
```
三種變體（train ≤2024-12-31, n=1936天）：
- **Gaussian**（pooled，兩session各自α,β，無尾部參數）
- **Multivariate-t (G=1)**：兩session各自α,β，但共享一個ν（用block-diagonal 8維t分布聯合似然，`C_t^ND=0`）
- **Cluster-t (G=2)**：night跟day完全獨立擬合各自的(α,β,ν)——對應論文的session-level tail heterogeneity

**訓練結果（in-sample log-lik）**：
| 模型 | ν (night) | ν (day) | log-lik |
|---|---|---|---|
| Gaussian | - | - | -14695.2 |
| Multivariate-t (G=1) | 5.34（共享） | 5.34（共享） | -12719.8 |
| Cluster-t (G=2) | 4.02 | 5.76 | -12694.0 (=-6199.1-6495.0) |

Cluster-t贏MVt約26分，跟論文定性一致（night比day厚尾，且session分離改善fit）。

### 3.3 Out-of-sample評估（2025-01-01~2026-08-18, n=394天）

**Log-likelihood（越高越好）**：
| Gaussian | Multivariate-t (G=1) | Cluster-t (G=2) |
|---|---|---|
| -2892.3 | -2320.6 | **-2302.7**（最佳） |

**GMV realized variance（標準化殘差Z空間，論文原始評估方式，越低越好）**：
| Gaussian | Multivariate-t (G=1) | Cluster-t (G=2) |
|---|---|---|
| 0.005583 | **0.005465**（最佳） | 0.005471 |

**顯著性檢定（本repo一貫的把關標準，不能只看聚合數字）**：
- Cluster-t vs MVt逐日log-lik差異：配對t檢定 **t=1.026, p=0.305**；394天裡只有**166天（42%）**站在Cluster-t這邊——聚合優勢由少數幾天貢獻，不是系統性edge。
- GMV squared-return差異：mean=5.07e-6，bootstrap 90% CI = **[-0.00039, +0.00042]**，完全跨過0。

**結論**：厚尾分布本身（Gaussian→t）價值巨大且穩固；但**session分離（Cluster-t vs pooled MVt）這一步在4資產規模下統計上站不住腳**——跟論文自己的6資產應用中Hetero-t（更細的asset-level切分）輸給Cluster-t的模式一致：切得太細、每個cluster的資料量撐不住額外參數。這次連Cluster-t vs pooled-t這一步的證據都不夠。

## 4. Phase 2：真實報酬GMV測試（使用者追問「還有實驗要做」後新增）

Phase 1的GMV評估用的是**標準化殘差Z空間**（論文原始做法，是診斷相關性預測品質的合成組合，不是真實可交易組合）。使用者想知道這個發現能不能接到「打贏production」這個真正有意義的比較，於是做了第二層：把session-split相關性模型接上**真實報酬**，跟一個「完全不分session、直接對日報酬建模」的naive baseline比較。

### 4.1 方法

把每日收盤對收盤報酬拆解為 `daily_ret = overnight_ret + intraday_ret`，共變異數用block-diagonal假設合成：
```
Σ_t^split = D^N_t C^N_t D^N_t + D^D_t C^D_t D^D_t   （用Phase 1已擬合的Cluster-t模型）
Σ_t^naive = D_t C_t D_t                              （直接對日報酬重新擬合4個EGARCH-t + 1個DCC-t，完全不分session）
```
GMV權重 `w_t = Σ_t^{-1} 1 / (1'Σ_t^{-1} 1)`，OOS(2025-01~2026-08, n=394天)每天用t-1可得資訊算權重，用t當天真實日報酬實現。

naive daily fit的nu：0050=4.40, 00631L=4.16, 00632R=4.38, 00679B=5.85；DCC(α=0.043, β=0.912, ν=4.90)。

### 4.2 結果——GMV本身在這個資產池上是災難性錯誤

| | 年化報酬 | 年化波動 | Sharpe | MDD | 日變異數 |
|---|---|---|---|---|---|
| session-split GMV | -6.46% | 3.19% | -2.024 | -9.60% | 0.000004 |
| naive daily-pooled GMV | -8.58% | 3.02% | -2.839 | -12.53% | 0.000004 |
| 等權重基準（對照組） | +16.00% | 14.73% | 1.086 | -17.04% | 0.000086 |

**根因**：GMV只優化變異數最小化，完全不管預期報酬。Group A+選單裡00631L（2倍槓桿）、00632R（反向）的報酬特性由結構性drift主導（槓桿長期波動耗損、反向ETF長期趨勢向下），GMV會判定這兩檔是「壓低整體變異數的好工具」而重壓/當避險用，完全無視其長期期望報酬為負。結果變異數壓得極低（年化波動僅3%）但報酬也跟著死掉——**不是相關性估計精準度的問題，是「風險最小化」這個目標函數本身跟含槓桿/反向商品的資產池結構性衝突**。

**Session分離確實還是有一致方向的邊際改善**（Sharpe -2.02 vs -2.84、MDD -9.6% vs -12.5%，兩個指標都對）——但只是「兩種爛方法裡比較不爛的一種」，改善不了GMV本身跟production（golden1_0531/a2118歷史年化報酬通常兩位數，見本session之外的多份production驗證記錄）之間的巨大落差。

## 5. 跟既有負面結論的疊加

這次結論跟`project_baws_adaptive_window_pilot_20260818`（08-18, BAWS動態相關性pilot，3個threshold測試都沒打贏現行靜態bond0_cash60防禦籃子）方向一致，但**這次給出更根本的機制解釋**：不只是「動態相關性切換沒有幫助」，而是「用相關性/共變異數最佳化（不論靜態或動態、不論估計精準度多高）去配置一個含2倍槓桿+反向ETF的資產池，目標函數本身就選錯方向」。這是本repo目前為止在「動態相關性/GMV式配置」這條研究線上**最清楚的一次「為什麼不行」的解釋**，值得記住以免之後有人又提類似角度時重新踩坑。

## 6. 最終結論

**三層結論全部記錄，closed，research_only，不promote任何production程式碼：**
1. 厚尾分布建模本身（t vs Gaussian）在Group A+這4檔資產上價值巨大且穩固（OOS log-lik差570+分，GMV variance也顯著改善）——但這只回答「該不該用厚尾分布」，不是這篇論文的新意。
2. Session分離（論文真正主張）：方向一致（Cluster-t贏pooled-t）但**統計上不顯著**（p=0.305，逐日勝率僅42%，GMV variance差異bootstrap CI跨0）——4資產規模撐不住這個額外的自由度切分。
3. 把這個相關性模型接上**真實報酬**做GMV配置：**結構性不適用**——GMV目標函數本身跟含槓桿/反向ETF的資產池衝突，兩個變體(session-split/naive)都遠遠打不贏簡單等權重，更不用說跟production比。

## 7. 檔案位置與可重現性

**已進repo（uncommitted）**：
- `scripts/evaluate/evaluate_2607_03669_split_session_dcc_shadow.py`——完整可重跑腳本，涵蓋Phase 1全部（data prep+corp action修正、Stage 1 EGARCH-t、Stage 2 DCC-t三變體、Stage 3 OOS log-lik+GMV(Z空間)+顯著性檢定），跑一次約6分鐘（8個EGARCH MLE + 3個DCC MLE，全部Nelder-Mead）。
- `results/2607_03669_split_session_dcc_shadow.json`——Phase 1完整數值結果（含每個fit的參數、OOS log-lik、GMV variance、顯著性檢定）。

**使用者選擇先留在scratchpad、不進repo**（Phase 2真實報酬GMV測試的腳本）：`session_gmv_vs_daily_pooled.py` + 其依賴的`split_session_dcc.py`模組 + 中間快取檔（`stage1_results.pkl`/`stage2_fits.pkl`/`Zn_all.npy`等）。**這些是session-scoped temp，不會保留到下次session**。為了可重現性，Phase 2完整原始碼備份在本文件末尾附錄。若要重跑：Phase 1直接跑repo裡的腳本即可；Phase 2需要先跑Phase 1（或直接讀`results/2607_03669_split_session_dcc_shadow.json`裡已存的`stage1_egarch`/`stage2_dcc_fits`參數，不必重新優化），再執行附錄腳本邏輯（需要先把`from split_session_dcc import ...`那幾行改成直接從`evaluate_2607_03669_split_session_dcc_shadow.py`匯入對應函式，兩邊函式簽名一致）。

## 8. 待辦 / 下次注意事項

1. 不要重新測「動態相關性/GMV配置這4檔資產」這個大方向——已經有兩次獨立負面結論（BAWS pilot + 這次），且這次有清楚的機制解釋（GMV跟槓桿/反向ETF結構性衝突），除非有人想到完全不同的目標函數（例如risk parity而非純GMV，或明確排除00631L/00632R只對0050/00679B兩檔非槓桿資產做GMV），否則不建議重跑。
2. 若之後有人想真正實作論文的score-driven矩陣對數GAS估計器（比這次用的DCC-t benchmark更複雜），現在已知的前提是：DCC-t engine下session分離連統計顯著性都拿不到，更複雜的估計器要能扭轉這個結論的機率不高，投入前應該先想清楚。
3. `ohlcv`表的3個已知未回溯調整斷點（0050/00631L/00632R）**仍然只存在於衍生分析裡的修正，資料庫本身沒有回寫**——這是第三次在不同session獨立踩到同一個坑（08-16、08-19兩次），如果之後還有人要做全歷史範圍的量化分析，遇到異常尾部/kurtosis第一步應該先查這3個日期，不用重新診斷。也考慮是否值得直接回寫`ohlcv`表本身一次性修正，一勞永逸（本session未做，因為只影響研究分析不影響production的backtest起點）。
4. `0050.TW`有2筆`open=0`的髒資料（2009-08-13、2010-01-25）此前未被任何session記錄過，之後若有人重新做0050早期歷史分析要留意。

---

## 附錄：Phase 2完整原始碼備份（scratchpad，未進repo）

### `split_session_dcc.py`（Phase 2依賴的共用模組，內容跟`evaluate_2607_03669_split_session_dcc_shadow.py`的函式邏輯等價，只是拆成獨立module方便import）

```python
"""
Split-session dynamic correlation test for Group A+ (arXiv:2607.03669).
See scripts/evaluate/evaluate_2607_03669_split_session_dcc_shadow.py in the
repo for the canonical, saved version of stage 1+2+3 (this module's
load_session_returns/fit_egarch_t/dcc_Q_path/Q_to_C/fit_dcc_single_t/
fit_dcc_pooled_t/fit_dcc_pooled_gaussian/mvt_loglik_*/gauss_loglik_single
functions are logically identical to that script's, just organized as an
importable module during interactive development).
"""
from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

DB_PATH = "FinRL/data/stock_data.db"  # relative to repo root
TICKERS = ["0050.TW", "00631L.TW", "00632R.TW", "00679B.TWO"]
KNOWN_BREAKS = {
    "0050.TW": pd.Timestamp("2014-01-02"),
    "00631L.TW": pd.Timestamp("2015-01-05"),
    "00632R.TW": pd.Timestamp("2024-12-02"),
}
TRAIN_END = pd.Timestamp("2024-12-31")


def load_session_returns(ticker: str) -> pd.DataFrame:
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(
        f"select dt, open, close from ohlcv where ticker='{ticker}' order by dt"
    ).fetchdf()
    df["dt"] = pd.to_datetime(df["dt"])
    df = df.sort_values("dt").reset_index(drop=True)
    df = df[(df["open"] > 0) & (df["close"] > 0)].reset_index(drop=True)
    if ticker in KNOWN_BREAKS:
        brk = KNOWN_BREAKS[ticker]
        idx = df.index[df["dt"] == brk]
        if len(idx):
            i = idx[0]
            ratio = df.loc[i, "open"] / df.loc[i - 1, "close"]
            for col in ["open", "close"]:
                df.loc[: i - 1, col] = df.loc[: i - 1, col] * ratio
    df["prev_close"] = df["close"].shift(1)
    df["overnight_ret"] = np.log(df["open"] / df["prev_close"])
    df["intraday_ret"] = np.log(df["close"] / df["open"])
    df = df.dropna(subset=["overnight_ret", "intraday_ret"]).reset_index(drop=True)
    return df[["dt", "overnight_ret", "intraday_ret"]]


def dcc_Q_path(Z: np.ndarray, alpha: float, beta: float) -> np.ndarray:
    T, n = Z.shape
    Qbar = np.corrcoef(Z, rowvar=False)
    Q = np.empty((T, n, n))
    Q[0] = Qbar
    for t in range(1, T):
        zz = np.outer(Z[t - 1], Z[t - 1])
        Q[t] = (1 - alpha - beta) * Qbar + beta * Q[t - 1] + alpha * zz
    return Q


def Q_to_C(Q: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.diagonal(Q, axis1=-2, axis2=-1))
    dinv = 1.0 / d
    return Q * dinv[..., :, None] * dinv[..., None, :]


def mvt_loglik_single(Z, C, nu):
    T, n = Z.shape
    ll = np.empty(T)
    c = gammaln((nu + n) / 2) - gammaln(nu / 2) - (n / 2) * np.log((nu - 2) * np.pi)
    for t in range(T):
        try:
            sign, logdet = np.linalg.slogdet(C[t])
            if sign <= 0:
                ll[t] = -1e6
                continue
            q = Z[t] @ np.linalg.inv(C[t]) @ Z[t]
            ll[t] = c - 0.5 * logdet - (nu + n) / 2 * np.log(1 + q / (nu - 2))
        except np.linalg.LinAlgError:
            ll[t] = -1e6
    return ll


def gauss_loglik_single(Z, C):
    T, n = Z.shape
    ll = np.empty(T)
    c = -(n / 2) * np.log(2 * np.pi)
    for t in range(T):
        try:
            sign, logdet = np.linalg.slogdet(C[t])
            if sign <= 0:
                ll[t] = -1e6
                continue
            q = Z[t] @ np.linalg.inv(C[t]) @ Z[t]
            ll[t] = c - 0.5 * logdet - 0.5 * q
        except np.linalg.LinAlgError:
            ll[t] = -1e6
    return ll


def _sigmoid_ab(a_raw, b_raw, alpha_max=0.25):
    alpha = alpha_max / (1 + np.exp(-a_raw))
    beta = (0.999 - alpha) / (1 + np.exp(-b_raw))
    return alpha, beta


def fit_dcc_single_t(Z: np.ndarray, dist: str) -> dict:
    def negloglik(theta):
        alpha, beta = _sigmoid_ab(theta[0], theta[1])
        C = Q_to_C(dcc_Q_path(Z, alpha, beta))
        if dist == "gaussian":
            ll = gauss_loglik_single(Z, C)
        else:
            nu = 2.0 + np.exp(theta[2])
            ll = mvt_loglik_single(Z, C, nu)
        return -np.sum(ll)

    x0 = [0.0, 0.0] if dist == "gaussian" else [0.0, 0.0, np.log(8.0)]
    res = minimize(negloglik, x0, method="Nelder-Mead",
                    options={"maxiter": 3000, "xatol": 1e-6, "fatol": 1e-6})
    alpha, beta = _sigmoid_ab(res.x[0], res.x[1])
    nu = float(2.0 + np.exp(res.x[2])) if dist == "t" else None
    return {"alpha": float(alpha), "beta": float(beta), "nu": nu, "loglik": float(-res.fun)}
```

### `session_gmv_vs_daily_pooled.py`（Phase 2主腳本）

```python
"""
Follow-up test: does the session-split (overnight+intraday) covariance
forecast produce a better REAL daily GMV portfolio than a naive covariance
model fit directly on close-to-close daily returns (no session split at
all)?

Sigma_t^split = D^N_t C^N_t D^N_t + D^D_t C^D_t D^D_t
Sigma_t^naive = D_t C_t D_t   (single EGARCH-t per asset on close-to-close
    daily returns, single DCC-t correlation, no session split)

OOS test 2025-01-01 onward, GMV weights w_t = Sigma^-1 1 / (1'Sigma^-1 1),
realized with actual next-day close-to-close return.
"""
import json
import time
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

from split_session_dcc import (
    TICKERS, TRAIN_END, load_session_returns,
    dcc_Q_path, Q_to_C, fit_dcc_single_t,
)

with open("results/2607_03669_split_session_dcc_shadow.json") as f:
    prior = json.load(f)


def _egarch_h_path(r, mu, omega, beta, tau1, tau2):
    T = len(r)
    e = r - mu
    log_h = np.empty(T)
    log_h[0] = omega / max(1e-6, (1 - beta))
    z = np.empty(T)
    z[0] = e[0] / np.exp(0.5 * log_h[0])
    for t in range(1, T):
        log_h[t] = omega + beta * log_h[t - 1] + tau1 * z[t - 1] + tau2 * (
            np.abs(z[t - 1]) - np.sqrt(2 / np.pi)
        )
        z[t] = e[t] / np.exp(0.5 * log_h[t])
    return np.exp(log_h), z


def _egarch_t_negloglik(params, r):
    mu, omega, beta_raw, tau1, tau2, log_nu_m2 = params
    nu = 2.0 + np.exp(log_nu_m2)
    beta = np.tanh(beta_raw)
    h, z = _egarch_h_path(r, mu, omega, beta, tau1, tau2)
    c = gammaln((nu + 1) / 2) - gammaln(nu / 2) - 0.5 * np.log((nu - 2) * np.pi)
    ll = c - 0.5 * np.log(h) - (nu + 1) / 2 * np.log(1 + z ** 2 / (nu - 2))
    if not np.all(np.isfinite(ll)):
        return 1e10
    return -np.sum(ll)


def fit_egarch_t(r):
    x0 = np.array([r.mean(), 0.0, np.arctanh(0.9), -0.05, 0.1, np.log(8.0)])
    res = minimize(_egarch_t_negloglik, x0, args=(r,), method="Nelder-Mead",
                    options={"maxiter": 4000, "xatol": 1e-6, "fatol": 1e-6})
    mu, omega, beta_raw, tau1, tau2, log_nu_m2 = res.x
    beta = np.tanh(beta_raw)
    nu = 2.0 + np.exp(log_nu_m2)
    h, z = _egarch_h_path(r, mu, omega, beta, tau1, tau2)
    return {"mu": mu, "omega": omega, "beta": beta, "tau1": tau1, "tau2": tau2,
            "nu": nu, "h": h, "z": z}


data = {tk: load_session_returns(tk) for tk in TICKERS}
for tk in TICKERS:
    data[tk]["daily_ret"] = data[tk]["overnight_ret"] + data[tk]["intraday_ret"]

date_sets = [set(data[tk]["dt"]) for tk in TICKERS]
common_dates = pd.DatetimeIndex(sorted(set.intersection(*date_sets)))

daily_fits = {}
Zdaily = np.zeros((len(common_dates), 4))
Hdaily = np.zeros((len(common_dates), 4))
for j, tk in enumerate(TICKERS):
    r_full = data[tk]["daily_ret"].values
    fit = fit_egarch_t(r_full)
    daily_fits[tk] = {k: v for k, v in fit.items() if k not in ("h", "z")}
    idx = data[tk].set_index("dt")
    Zdaily[:, j] = pd.Series(fit["z"], index=idx.index).reindex(common_dates).values
    Hdaily[:, j] = pd.Series(fit["h"], index=idx.index).reindex(common_dates).values

train_mask = np.asarray(common_dates <= TRAIN_END)
test_mask = ~train_mask

fit_daily_dcc = fit_dcc_single_t(Zdaily[train_mask], dist="t")
Cn_naive_full = Q_to_C(dcc_Q_path(Zdaily, fit_daily_dcc["alpha"], fit_daily_dcc["beta"]))

Hn = np.zeros((len(common_dates), 4))
Hd = np.zeros((len(common_dates), 4))
Zn = np.zeros((len(common_dates), 4))
Zd = np.zeros((len(common_dates), 4))
for j, tk in enumerate(TICKERS):
    pn = prior["stage1_egarch"][f"{tk}|overnight_ret"]
    pdd = prior["stage1_egarch"][f"{tk}|intraday_ret"]
    idx = data[tk].set_index("dt")
    h_n, z_n = _egarch_h_path(data[tk]["overnight_ret"].values, pn["mu"], pn["omega"], pn["beta"], pn["tau1"], pn["tau2"])
    h_d, z_d = _egarch_h_path(data[tk]["intraday_ret"].values, pdd["mu"], pdd["omega"], pdd["beta"], pdd["tau1"], pdd["tau2"])
    Hn[:, j] = pd.Series(h_n, index=idx.index).reindex(common_dates).values
    Hd[:, j] = pd.Series(h_d, index=idx.index).reindex(common_dates).values
    Zn[:, j] = pd.Series(z_n, index=idx.index).reindex(common_dates).values
    Zd[:, j] = pd.Series(z_d, index=idx.index).reindex(common_dates).values

cn_fit = prior["stage2_dcc_fits"]["cluster_t_g2_night"]
cd_fit = prior["stage2_dcc_fits"]["cluster_t_g2_day"]
Cn_split = Q_to_C(dcc_Q_path(Zn, cn_fit["alpha"], cn_fit["beta"]))
Cd_split = Q_to_C(dcc_Q_path(Zd, cd_fit["alpha"], cd_fit["beta"]))


def gmv_weights(Sigma):
    try:
        Sinv = np.linalg.inv(Sigma)
    except np.linalg.LinAlgError:
        return None
    ones = np.ones(Sigma.shape[0])
    return Sinv @ ones / (ones @ Sinv @ ones)


Rdaily = np.zeros((len(common_dates), 4))
for j, tk in enumerate(TICKERS):
    idx = data[tk].set_index("dt")
    Rdaily[:, j] = idx["daily_ret"].reindex(common_dates).values

test_idx = np.where(test_mask)[0]
port_split, port_naive, port_ew = [], [], []
for t in test_idx:
    Dn = np.diag(np.sqrt(Hn[t]))
    Dd = np.diag(np.sqrt(Hd[t]))
    Sigma_split = Dn @ Cn_split[t] @ Dn + Dd @ Cd_split[t] @ Dd

    Dnaive = np.diag(np.sqrt(Hdaily[t]))
    Sigma_naive = Dnaive @ Cn_naive_full[t] @ Dnaive

    w_split = gmv_weights(Sigma_split)
    w_naive = gmv_weights(Sigma_naive)
    r_t = Rdaily[t]
    if w_split is not None:
        port_split.append(w_split @ r_t)
    if w_naive is not None:
        port_naive.append(w_naive @ r_t)
    port_ew.append(np.mean(r_t))

port_split = np.array(port_split)
port_naive = np.array(port_naive)
port_ew = np.array(port_ew)


def perf(r):
    ann_ret = r.mean() * 252
    ann_vol = r.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else np.nan
    cum = np.exp(np.cumsum(r))
    mdd = (cum / np.maximum.accumulate(cum) - 1).min()
    return {"ann_ret": float(ann_ret), "ann_vol": float(ann_vol), "sharpe": float(sharpe),
            "mdd": float(mdd), "var": float(r.var())}


res_split = perf(port_split)
res_naive = perf(port_naive)
res_ew = perf(port_ew)
# res_split  = {ann_ret: -0.0646, ann_vol: 0.0319, sharpe: -2.024, mdd: -0.0960, var: 0.000004}
# res_naive  = {ann_ret: -0.0858, ann_vol: 0.0302, sharpe: -2.839, mdd: -0.1253, var: 0.000004}
# res_ew     = {ann_ret:  0.1600, ann_vol: 0.1473, sharpe:  1.086, mdd: -0.1704, var: 0.000086}
```
