# 04 — profile 結構與切換/建立

**What to build:** 遊戲設定檔自帶流程存檔:`profiles/<game>/` 含模板庫、`flows/`、config、登錄產物。UI 提供 profile 下拉切換與「建立新 profile」(自動建目錄結構並帶入預設 config);切換 profile 同時切換流程清單與範本瀏覽器內容,流程自動存檔(autosave)隨 profile 走。部署後(frozen)使用者資料放 exe 旁,原始碼執行用 repo 內目錄——沿用既有 frozen 切換慣例。改名/刪除 profile 不進 UI(交檔案總管)。

**Blocked by:** 03 — 應用層引擎生命週期與比對測試

**Status:** done (2026-08-15)

- [x] profile 列舉/建立/切換以暫存目錄真測(不 mock;`test_profile_store.py`)
- [x] 切換 profile 後流程清單、範本瀏覽器、引擎查詢對象一致跟隨
      (`switch_profile`:autosave 舊 profile → 換目錄 → `reload_profile` →
      載入新 profile 的 autosave;`EngineDetector.profile` 同步換)
- [x] 建立新 profile 後立即可截圖建範本並在流程中引用(自動建 templates/flows/
      並複製引擎預設 config 整份含註解)
- [x] autosave 與流程存檔落在所屬 profile 的 flows 之下
      (`profiles/<game>/flows/_autosave.json`;存檔/讀檔預設目錄同此)
- [x] frozen 與原始碼兩種執行模式的資料根目錄正確(frozen=exe 旁、
      原始碼=repo 根目錄;`profile_store.data_root()` 有測試)

實作備註:
- 上次選用的 profile 記在 `profiles/app_state.json`(gitignore)。
- 執行中不允許切換 profile(messagebox 擋下、combobox 還原)。
- 改名/刪除 profile 不進 UI(交檔案總管),照票面。
