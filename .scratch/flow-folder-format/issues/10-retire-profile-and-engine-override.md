# 10 — profile 退場與引擎參數覆蓋

**What to build:** profile 整個退場（ADR 0015）：主視窗沒有 profile 下拉、建立 profile、開啟資料夾鈕；profile_store 模組與 `profiles/` 的用法刪掉。引擎參數＝引擎內建預設＋流程 `engine:` 段覆蓋，由 app 合併後交給引擎（引擎公開 API 形狀不變）；換流程就換參數。本機狀態 `state.json` 只記上次開的流程；打包版的狀態與 `autoclick.log` 放 `%LOCALAPPDATA%\AutoClick\`，從原始碼執行放 repo `.local\`（`.gitignore` 加 `.local/`）。開 app 自動開上次流程；它不在了就開空白新流程，執行紀錄一行說明。見 spec「profile 退場、本機狀態與日誌」「引擎參數」。

**Blocked by:** 08

**Status:** ready-for-agent

- [ ] 主視窗沒有 profile 相關控制項與開啟資料夾鈕；全 repo 沒有程式碼讀 profile 目錄或 profile 的 `config.yaml`
- [ ] 流程帶 `engine: {scale_range: [0.6, 1.5]}` 時引擎用這個範圍；沒寫用內建預設；未知鍵在讀檔時已被擋
- [ ] 打包版（frozen）與原始碼執行的狀態、日誌位置各自正確
- [ ] 開 app 自動開上次流程；上次流程不在時開空白並記一行
- [ ] 基準測試集照舊能跑（依賴 profile 路徑的部分只做到不壞）
- [ ] profile_store 的測試刪掉；新增本機狀態與引擎參數合併的測試；全部測試綠
