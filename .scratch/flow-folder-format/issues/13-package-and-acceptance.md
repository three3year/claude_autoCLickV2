# 13 — 打包與驗收

**What to build:** 改 `build.bat`：刪掉建立 `profiles\arknights` 與複製 `config.yaml` 的步驟，結尾說明改成「部署＝整個資料夾換掉」（`AutoClick.spec` 不變）。重打包後 `dist\AutoClick\` 只剩兩個 exe 與 `_internal\`。新打包版開得起四份轉好的流程，讀取後等「範本就緒」再按執行約 3.5 秒開始第一步，使用者早晚班四份各實跑一次全過。這張需要使用者在場（HITL）。見 spec「打包與部署」「驗收」。

**Blocked by:** 09, 10, 11, 12

**Status:** ready-for-human

- [x] 確認舊打包版已在 `dist` 外（12 已搬），重打包前 `dist` 裡沒有使用者資料
- [ ] 打包產物只有兩個 exe 與 `_internal\`；狀態與日誌出現在 `%LOCALAPPDATA%\AutoClick\`
- [ ] 新打包版開得起四份流程
- [ ] 讀取流程→「範本就緒」→按執行，約 3.5 秒開始第一步
- [ ] 使用者早晚班四份各實跑一次全過（冒煙或實跑前先確認使用者不在玩遊戲）
- [ ] 過關後：刪 memory「重新打包前把使用者資料移出 dist」，提到 profile 路徑的 memory 改成新位置；舊打包版備援由使用者決定何時刪

## Comments

- 2026-10-11（agent）：`build.bat` 已改（刪建立 `profiles\arknights` 與複製 `config.yaml`，結尾改成「部署＝整個 AutoClick\ 資料夾換掉」）；`AutoClick.spec` 只改了說明註解。舊打包版是**複製**到 `AiProject\AutoClick-舊打包版-2026-10-10\`（見 12），`app/dist/AutoClick` 還在原處、裡面的 `profiles\` 是舊格式資料，重打包（`--noconfirm`）會連它一起清掉——備援就是那份複本。四份流程已在 `%USERPROFILE%\AutoClick\`。離線量測（11）讀取後等「範本就緒」再按執行 3.7 秒開始第一步。**還沒做**：重打包、打包版開四份流程、早晚班四份實跑、過關後的 memory 整理——等使用者在場。
