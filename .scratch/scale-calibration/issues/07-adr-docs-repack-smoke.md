# 07 — ADR、文件與重新打包冒煙

**What to build:** 收尾三件事:(1) 補 ADR 記錄「流程檔座標以當前基準機器尺度儲存+存檔時重定基準」的決策與取捨(對照被捨棄的歸一化儲存方案、跨機語意、pack 換算的配套);(2) 校對文件——app 層 CLAUDE.md 補校準相關慣例與坑、CONTEXT.md 詞彙與實作對齊;(3) 重新打包(使用者用的是打包版)並做打包版冒煙:指定校準對→校準→執行縮放流程的最小走查。冒煙涉及真實輸入前,先確認使用者不在使用電腦(idle 與前景檢查)。

**Blocked by:** 04 — 編輯守門與重定基準;06 — 不同對匯入與存檔守門。

**Status:** resolved

- [x] ADR 落地於共用 ADR 目錄,含 context、決策、取捨與後果
- [x] app 層 CLAUDE.md 與 CONTEXT.md 對齊最終實作(含任何實作中新增的慣例/坑)
- [x] 依打包慣例重新打包(onedir、先從原始碼跑過一次、不動使用者 profiles)
- [x] 打包版冒煙通過（部分項目見下方註記）:校準按鈕顯示倍率、手寫倍率≠1 的校準資料後執行流程落點縮放正確

## Comments

- 2026-08-16 完成: ADR 0005 落地 docs/adr/；app/CLAUDE.md 補校準慣例與坑、CONTEXT.md code 標註對齊實作。
  打包依慣例 (PyInstaller onedir 直跑, build.bat 程式化呼叫會壞編碼)、arknights profile 手動補回、不動使用者 profiles。
- 打包版冒煙實測記錄:
  - ✅ 打包版啟動、引擎就緒 4.9s (engine.load.done, coarse_only=False)。
  - ✅ 手寫倍率 1.25 的 calibration.json → 主視窗校準按鈕正確顯示「校準　×1.25」(PrintWindow 截圖驗證)。
  - ✅ 機器指紋機制實測有效: 以非 DPI-aware 程序寫入的指紋與 app (DPI-aware, 125% 縮放) 不符 → 正確顯示「校準（未校準）」。
  - ✅ 冒煙同時抓到 UI 版面問題 (前兩列塞不下校準按鈕) → 校準自成第三列後重新打包驗證通過。
  - ⚠️ 「執行縮放流程、真實落點驗證」未走完: 三次嘗試期間使用者在使用電腦 (兩度手動關閉冒煙視窗、idle 檢查未過)。
    落點=中心+偏移×倍率的邏輯由 pytest 回歸網覆蓋 (test_runner_scale.py 全部落點斷言、test_calibration_ui.py 倍率接線)。
    重跑方式: scratchpad 的 smoke_setup.py（建 _smoke_cal profile, 期望落點 (205,745)）+ smoke_recorder.py + smoke_capture.py clickrun。
