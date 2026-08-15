# 04 — profile 結構與切換/建立

**What to build:** 遊戲設定檔自帶流程存檔:`profiles/<game>/` 含模板庫、`flows/`、config、登錄產物。UI 提供 profile 下拉切換與「建立新 profile」(自動建目錄結構並帶入預設 config);切換 profile 同時切換流程清單與模板瀏覽器內容,流程自動存檔(autosave)隨 profile 走。部署後(frozen)使用者資料放 exe 旁,原始碼執行用 repo 內目錄——沿用既有 frozen 切換慣例。改名/刪除 profile 不進 UI(交檔案總管)。

**Blocked by:** 03 — 應用層引擎生命週期與比對測試

**Status:** ready-for-agent

- [ ] profile 列舉/建立/切換以暫存目錄真測(不 mock)
- [ ] 切換 profile 後流程清單、模板瀏覽器、引擎查詢對象一致跟隨
- [ ] 建立新 profile 後立即可截圖建模板並在流程中引用
- [ ] autosave 與流程存檔落在所屬 profile 的 flows 之下
- [ ] frozen 與原始碼兩種執行模式的資料根目錄正確
