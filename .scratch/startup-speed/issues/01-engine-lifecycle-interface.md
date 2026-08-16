# 01 — 引擎生命週期介面(前置重構)

**What to build:** 把既有的引擎邊界(runner 注入的偵測器,`query`)擴充為
生命週期介面:就緒狀態查詢(載入中/就緒/失敗降級)、範本預載、單範本載入、
`query`。App 與 runner 改為只透過這個介面使用引擎,**外部行為完全不變**
(仍是啟動同步載入、整庫登錄)。harness 的引擎假件(全 repo 唯一假件點)
同步擴充,測試可直接把狀態撥成任意值,不碰 torch、不開執行緒。
這是「先讓改動變容易」的前置——後續各票都建立在這個介面上。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 介面涵蓋:就緒狀態查詢、範本預載(名單→載入)、單範本載入、query
- [x] App 與 runner 不再直接觸碰引擎具體型別,只透過介面
- [x] harness 假件擴充後,既有全部測試綠、無行為改變
- [x] 新增介面層的純測試:狀態撥切、預載/單張載入呼叫可被記錄斷言

## Comments

2026-08-16 完成:`app/enginehub.py` 的 EngineHub 取代 EngineDetector;
Engine 增 `register`(單張)與 `load_profile(register=False)`;harness Vision
擴充 state/preload/ensure_template。164→174 測試全綠。
