# 02 — runner 偵測接縫換引擎

**What to build:** 找圖相關步驟(find_click、wait_gone、confirm=gone/appear、branch 輪詢)的辨識全部改走引擎查詢:截取掃描範圍 → `query(profile, 模板名, 搜尋區域)` → 以 QueryResult 的 found/box 判定,座標換算照舊(區域內座標 + 截圖原點 = 螢幕座標)。舊 matcher 模組刪除,不留備援路徑。步驟資料與步驟編輯器移除每步 threshold 欄位(門檻自此一律來自 profile config)。測試 harness 的假件形狀從 find_template 換成 query(回 QueryResult),`vision.plan` 排程機制與虛擬時鐘原樣保留——這是全 repo 唯一假件點。

**Blocked by:** 01 — 應用整包落地與瘦身

**Status:** done (2026-08-15)

- [x] runner 全部行為測試(步驟語意、座標空間、區段/迴圈/分支、stage 接縫)經新假件形狀全綠(69 passed)
- [x] 舊 matcher 已刪除,repo 內無殘留呼叫
- [x] 步驟資料與編輯 UI 無 threshold 欄位(新增步驟預設值、step_desc、對話框滑桿全移除)
- [x] wait_gone 與 confirm 語意以 found 判定,行為測試覆蓋(既有測試經新接縫全綠)
- [x] 引擎既有測試與 bench 38/38 不受影響(全套 141 passed;bench 38/38 100%)

實作備註:
- 接縫形狀:`Runner(detector)` 建構時注入偵測器,`detector.query(範本名, 搜尋區域影像)
  → QueryResult`;範本不存在丟 KeyError,runner 轉成「找不到範本圖片」執行錯誤。
- harness 的 Vision 直接實作 query(回真的 `subject_detection.engine.QueryResult`),
  `vision.plan` 排程與虛擬時鐘原樣保留;matcher/imgio 的 monkeypatch 移除。
- 座標換算:QueryResult.box 中心 + 截圖原點 = 螢幕座標(含 offset)。
