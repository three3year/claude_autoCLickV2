# 01 — 應用整包落地與瘦身

**What to build:** autoClick 應用原封搬入本 repo 頂層 `app/`,從原始碼即可啟動、既有操作(流程編輯、截圖建模板、執行、F12 急停)照舊可用。自動化子套件由 engine 改名 automation(「引擎」自此專指主體偵測引擎)。同時剝除本輪決定不帶的功能:並行執行 UI 與 ParallelRun、旋轉比對與旋轉模板工具、去背工具、翻新解析度工具、`_orig` 模板鏡像機制。舊 matcher 與每步 threshold **本票暫時保留**(接縫替換在 02 票),確保搬入的測試持續綠。非並行測試與 harness 一併搬入。

**Blocked by:** None — can start immediately

**Status:** done (2026-08-15)

- [x] 從原始碼可啟動 app,主要操作流程可用(手動 smoke:PrintWindow 截圖確認主視窗完整渲染、被剝除功能的 UI 入口不在)
- [x] 自動化子套件命名為 automation,repo 內不再有兩個「engine」
- [x] 並行執行、旋轉、去背、翻新解析度的程式碼與 UI 入口已移除;runner 的 stage 接縫與其測試保留
- [x] 搬入的非並行測試(runner 步驟/座標空間/區段/origin/stage、UI 純邏輯)全數綠(77 passed)
- [x] 舊專案 CLAUDE.md 的踩坑紀錄(UIPI、DWM 殘影、headless GUI 測試、中文路徑讀圖)整併進 `app/CLAUDE.md`
- [x] 引擎既有測試與 bench 38/38 不受影響(全套 114 passed;bench 38/38 100%)

實作備註:
- 兩套測試同時收集時 `tests/conftest.py` 與 `app/tests/conftest.py` 模組名衝突,
  引擎測試的共用假件搬到 `tests/synth.py`(純機械搬移,行為不變)。
- `_meta.json` 只留 `pos` 鍵;舊檔的 `rot` 鍵讀入即丟。
- app 原始碼執行的沙盒資料 `app/templates`、`app/flows` 已 gitignore。
