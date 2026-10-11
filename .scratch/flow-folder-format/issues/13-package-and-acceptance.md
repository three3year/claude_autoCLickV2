# 13 — 打包與驗收

**What to build:** 改 `build.bat`：刪掉建立 `profiles\arknights` 與複製 `config.yaml` 的步驟，結尾說明改成「部署＝整個資料夾換掉」（`AutoClick.spec` 不變）。重打包後 `dist\AutoClick\` 只剩兩個 exe 與 `_internal\`。新打包版開得起四份轉好的流程，讀取後等「範本就緒」再按執行約 3.5 秒開始第一步，使用者早晚班四份各實跑一次全過。這張需要使用者在場（HITL）。見 spec「打包與部署」「驗收」。

**Blocked by:** 09, 10, 11, 12

**Status:** ready-for-human

- [x] 確認舊打包版已在 `dist` 外（12 已搬），重打包前 `dist` 裡沒有使用者資料
- [x] 打包產物只有兩個 exe 與 `_internal\`；狀態與日誌出現在 `%LOCALAPPDATA%\AutoClick\`
- [x] 新打包版開得起四份流程
- [ ] 讀取流程→「範本就緒」→按執行，約 3.5 秒開始第一步
- [ ] 使用者早晚班四份各實跑一次全過（冒煙或實跑前先確認使用者不在玩遊戲）
- [ ] 過關後：刪 memory「重新打包前把使用者資料移出 dist」，提到 profile 路徑的 memory 改成新位置；舊打包版備援由使用者決定何時刪

## Comments

- 2026-10-11（agent）：`build.bat` 已改（刪建立 `profiles\arknights` 與複製 `config.yaml`，結尾改成「部署＝整個 AutoClick\ 資料夾換掉」）；`AutoClick.spec` 只改了說明註解。舊打包版是**複製**到 `AiProject\AutoClick-舊打包版-2026-10-10\`（見 12），`app/dist/AutoClick` 還在原處、裡面的 `profiles\` 是舊格式資料，重打包（`--noconfirm`）會連它一起清掉——備援就是那份複本。四份流程已在 `%USERPROFILE%\AutoClick\`。離線量測（11）讀取後等「範本就緒」再按執行 3.7 秒開始第一步。**還沒做**：重打包、打包版開四份流程、早晚班四份實跑、過關後的 memory 整理——等使用者在場。
- 2026-10-11 08:25（agent，使用者同意重打包；閒置 8 分鐘、遊戲沒開）：直接跑 PyInstaller 重打包，`dist/AutoClick/` 只剩 `AutoClick.exe`、`AutoClick-noUAC.exe`、`_internal/`。冒煙用 noUAC 版、不送任何輸入：四份各把 state.json 的上次流程設成它再啟動，PrintWindow 截主視窗——四份都自動開成（晚_簡中 61 步／26 張、晚_繁中 61／26、早_簡中 268／86、早_繁中 227／82），引擎就緒後印「開始準備範本」，2–8 秒後「範本就緒」；`state.json`、`autoclick.log` 出現在 `%LOCALAPPDATA%/AutoClick/`。最後一次啟動的是早_繁中，所以下次開打包版會自動開它。剩下：讀取後按執行約 3.5 秒開始第一步（實機）、早晚班四份實跑、過關後整理 memory。
- 2026-10-11 12:45（agent，使用者實跑）：早_簡中最大化（×1.132）換班段點錯修好。原因：類別標題窄帶的左緣＝清單欄左緣（`.scratch/scale-range/shift_build.py` `band_rect` 用 `self.col`），左餘裕約 0，不合 ADR 0013 的矩形餘裕 20%；最大化時畫面左偏 2–4px 切到標題左側黃條 → 標題不是候選，「由上到下第 1 個」挑到第 1 列列名（低 61px），拖曳 `confirm: gone` 又被捲上來的 2 列後同款列名判成「仍在原位」而補拖，捲過頭。修正（流程資料，程式沒改）：四份流程所有 `标题_`/`標題_` 窄帶 x −24、w +24（早_簡中 10 處、其他各 8 處；備份 `flow.yaml.bak-2026-10-11-band`）。被動截圖＋真引擎重放重現原狀況、加寬後標題 0.986；使用者重跑 #97–130 通過（12:43 日誌：五個類別標題都挑到標題、五次拖曳都只送 1 次）。日後重建換班段要讓 `band_rect` 左右各留 20% 範本寬。早_繁中 ×0.70 範本認不出屬超出支援倍率範圍的新需求，另議。
