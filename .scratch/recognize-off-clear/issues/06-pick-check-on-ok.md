# 06 — 按確定觸發的拾取檢查

**What to build:** 在步驟編輯器或找圖設定按「確定」時，視窗只閃一下（截圖），對話框就關、步驟照存。拾取檢查（唯一＋縮放餘裕）在背景進行，主視窗狀態列顯示「辨識中…」、圖片類反灰。做完照現在一樣寫紀錄、在範本面板標 ⚠。

這是「發起的對話框做完前不能關」的例外：檢查只警告、不改你剛按確定的內容，所以對話框照關，發起視窗記為主視窗。

技術上，拾取檢查的安靜模式（`measured_pick(quiet=True)`）清場中只截圖。校準、原點推算（用 04 的「在給定截圖上找上一步的圖」）、`pickcheck.check` 都在背景做。

**Blocked by:** 04

**Status:** done

- [x] 兩個確定入口：清場中查詢 0 次。
- [x] 按確定後對話框已關、步驟已存進清單；主視窗在辨識中（狀態列「辨識中…」、圖片類反灰）。
- [x] 放行後，⚠ 與紀錄跟現在的判斷相同（兩個匹配有唯一警告、改選第 2 個沒有、找不到沉默）；量不到時寫一行略過。
- [x] 引擎沒就緒或範本不在清單：照現在一樣安靜略過，不進辨識中。
- [x] 既有的 `test_pickcheck_ui` 確定相關測試全綠。

## Comments

- 2026-10-13 agent：完成。背景辨識入口 `app/recognition.py`（`App.recognition`／`App.recognize`），拾取骨架 `ui_dialogs.measured_pick`（清場只截圖＋派背景＋覆蓋層 `shot=`/`pending=`/`late=`）。測試 `test_recognition.py`、`test_recognize_pick.py`、`test_overlay_pending_gui.py`；app 全套 748 passed、引擎＋tools 349 passed（隱藏桌面）。
