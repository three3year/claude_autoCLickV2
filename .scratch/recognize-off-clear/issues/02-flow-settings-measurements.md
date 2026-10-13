# 02 — 流程設定其他三個量測入口

**What to build:** 在流程設定按「測試備用校準對」「設定校準對」「設定備用校準對」時，視窗只閃一下就回來，不再全白。量測在背景進行，流程設定對話框以辨識中顯示。量完後：

- 設定校準對照現在一樣：平移所有存下的座標、重算備用對偏移、寫紀錄。
- 量不到時照現在一樣提示，原本的校準資料與座標不動。

這三個入口現在已經是「清場只截圖」，但量測仍在介面執行緒上做。本票把量測交給 01 的背景辨識入口。改流程資料的部分（設定校準對、平移座標、`_mark_dirty`、提示 modal）留在介面執行緒的收尾裡做。

見 spec「實作決策」的「介面執行緒與背景的分工」。

**Blocked by:** 01

**Status:** done

- [x] 三個入口的量測（`calibration.calibrate`／`measure`／`measure_fallback`）都在背景做；量完的套用與提示都在介面執行緒做。
- [x] 辨識中，流程設定對話框顯示「辨識中…」、圖片類反灰、關閉無效。
- [x] 結果與現在完全相同：
  - 換對時平移座標，落點不變。
  - 有備用對時偏移跟著重算。
  - 舊對或新對量不到就拒絕，資料不動。
  - 兩張太近就拒絕。
- [x] 測試：
  - 三個入口各一條「清場中查詢 0 次」。
  - 扣住時，校準資料還沒變；放行後才變。
- [x] 既有的 `test_calibration_ui` 全綠。

## Comments

- 2026-10-13 agent：完成。背景辨識入口 `app/recognition.py`（`App.recognition`／`App.recognize`），拾取骨架 `ui_dialogs.measured_pick`（清場只截圖＋派背景＋覆蓋層 `shot=`/`pending=`/`late=`）。測試 `test_recognition.py`、`test_recognize_pick.py`、`test_overlay_pending_gui.py`；app 全套 748 passed、引擎＋tools 349 passed（隱藏桌面）。
