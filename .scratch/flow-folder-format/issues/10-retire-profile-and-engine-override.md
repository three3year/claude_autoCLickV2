# 10 — profile 退場與引擎參數覆蓋

**What to build:** profile 整個退場（ADR 0015）：主視窗沒有 profile 下拉、建立 profile、開啟資料夾鈕；profile_store 模組與 `profiles/` 的用法刪掉。引擎參數＝引擎內建預設＋流程 `engine:` 段覆蓋，由 app 合併後交給引擎（引擎公開 API 形狀不變）；換流程就換參數。本機狀態 `state.json` 只記上次開的流程；打包版的狀態與 `autoclick.log` 放 `%LOCALAPPDATA%\AutoClick\`，從原始碼執行放 repo `.local\`（`.gitignore` 加 `.local/`）。開 app 自動開上次流程；它不在了就開空白新流程，執行紀錄一行說明。見 spec「profile 退場、本機狀態與日誌」「引擎參數」。

**Blocked by:** 08

**Status:** resolved

- [x] 主視窗沒有 profile 相關控制項與開啟資料夾鈕；全 repo 沒有程式碼讀 profile 目錄或 profile 的 `config.yaml`
- [x] 流程帶 `engine: {scale_range: [0.6, 1.5]}` 時引擎用這個範圍；沒寫用內建預設；未知鍵在讀檔時已被擋
- [x] 打包版（frozen）與原始碼執行的狀態、日誌位置各自正確
- [x] 開 app 自動開上次流程；上次流程不在時開空白並記一行
- [x] 基準測試集照舊能跑（依賴 profile 路徑的部分只做到不壞）
- [x] profile_store 的測試刪掉；新增本機狀態與引擎參數合併的測試；全部測試綠

## Comments

- 2026-10-11（agent）：與 08 一起做。`app/apppaths.py`：流程預設位置、本機狀態資料夾（frozen→`%LOCALAPPDATA%\AutoClick`、原始碼→repo `.local`）、`state.json`（只記 `last_flow`）、日誌、未存檔快取；測試 `test_apppaths.py`，conftest 把狀態資料夾與流程預設位置換到暫存目錄。引擎參數＝`load_default_config()`＋流程 `engine:`（`App.engine_config`），`EngineHub.bind(templates, config, registered_dir, changed)` 由 app 組範本清單；`EngineHub.load()` 只建引擎。hub 的 `profile` 欄位改名 `library`。引擎的 `load_config(profile_dir)` 與基準測試集沒動（只做到不壞）。`build.bat` 的 profile 放置步驟留給 13。
