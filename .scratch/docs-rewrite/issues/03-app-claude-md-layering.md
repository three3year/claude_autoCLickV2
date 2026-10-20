# 03 — app/CLAUDE.md 分層

**What to build:** `app/CLAUDE.md` 重寫成約 150 行的正文：一句定位 → 架構地圖（模組一行一個，只寫職責）→ 契約（每條一段、定義與坑放一起：辨識單一路徑、啟動契約與 gate、流程資料夾與唯一入口、範本與引用、一份流程一個尺度、存檔座標一律偏移量、清場中不辨識／背景辨識、拾取檢查；執行語意維持「正本在格式規範，這裡只留哪個函式負責」併進契約）→ 建置與部署（補 agent 打包法：`build.bat` 由程式呼叫會壞編碼、直接跑 PyInstaller 到新資料夾再換名；冒煙用 noUAC 版在隱藏桌面）→ 已移除清單（不用反引號）→ 三行指標。「踩過的坑」（依主題分組）、「測試手法」、「UI 慣例」（兩節合一）各成一份 `docs/agents/` 檔，開頭一句什麼情況讀；每條檢查相關性，過期的刪、重複的併、模型本來就會做的句子刪。見 [spec](../spec.md)「需要你決定的」第一題與「Implementation Decisions」的 `app/CLAUDE.md` 一段；寫法依 `writing-for-agents`。

**Blocked by:** 01 — 文件對照測試（可與 02 並行）

**Status:** resolved

- [x] 對照測試在 `app/CLAUDE.md` 與三份 `docs/agents/` 新檔全綠
- [x] 正文約 150 行；每個意思只在一處（正文或某一份分出去的檔）
- [x] 三個指標各寫明觸發條件（改 Tk／覆蓋層／grab 的程式碼、寫或改 app 測試、改版面或樣式）
- [x] 已移除清單只有一份、不用反引號
- [x] 建置與部署含 agent 打包法與冒煙法（來源：memory 的 build-bat-encoding、packaged-smoke）
- [x] 文件用 `app/CONTEXT.md` 的詞；「profile」「workspace」等退場詞只出現在已移除清單
- [x] 根目錄 `CLAUDE.md` 不加指標（地圖票 10 的決定）
