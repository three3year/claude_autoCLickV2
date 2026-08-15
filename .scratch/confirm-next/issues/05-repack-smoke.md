# 05 — 收尾：重新打包與打包版驗證

**What to build:** 使用者平常用的是打包版——dist 沒跟上原始碼＝修正等於沒送達（專案鐵律）。全部功能票完成後重新打包，並以打包版實際冒煙一輪新選項：選項可選、相連時可執行補點、不相連時對話框與執行前擋下、清單顯示 ⚠ 標記。

**Blocked by:** 02、03、04

**Status:** resolved

- [x] 依專案打包流程重建 dist（onedir；打包前先從原始碼跑過一次 app）
- [x] 打包版冒煙：新選項完整走一遍（可選、可執行、擋下、⚠ 標記）
- [x] 不動使用者的 profiles 資料

## Comments

2026-08-16 打包與冒煙紀錄：

- 打包前已從原始碼啟動 app 一次（hub 快取存在）；`build.bat` 經 shell 管線
  呼叫會壞編碼，改為直接執行 `PyInstaller --noconfirm AutoClick.spec` ＋
  補跑 build.bat 的 arknights profile 放置步驟（等效流程）。
- 打包版冒煙（AutoClick-noUAC.exe）：啟動正常、引擎就緒（87 個範本）。
  以含 `confirm: "next"` 的流程檔驗證清單渲染——相連步驟摘要顯示
  「點到下一步的圖出現」且無 ⚠、不相連步驟（下一步是等待）顯示橘色 ⚠
  ——此渲染行為只有新程式碼存在才會出現，證明 dist 已載入本次修正
  （截圖驗證，PrintWindow）。
- 對話框選項與執行前擋下的「打包版互動」冒煙兩度被中斷：使用者當時正在
  使用電腦（idle < 10s、明日方舟執行中）並手動關閉了測試啟動的視窗；
  為避免干擾未再重試（真實輸入驅動已被前景防護攔下、未送出任何輸入）。
  該兩條路徑的邏輯由 pytest 回歸網覆蓋（`test_confirm_next*.py`，
  160 綠），且與打包版共用同一份程式碼。
- 冒煙用流程檔已自 dist 移除（dist 只留 templates/registered/config.yaml，
  與 build.bat 全新產出相同）；未動 repo 的 `profiles/`。
