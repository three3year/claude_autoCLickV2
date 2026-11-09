# 03: 編輯器 4 個校準按鈕等停穩

**What to build:** 編輯器的「設定校準對」「設定備用校準對」「測試校準對」「測試備用校準對」4 個按鈕，量測方式改成跟執行時相同：
- 先把游標移到`避開游標`的停點，跟執行器同一點：`搜尋範圍`左下角外側；沒設搜尋範圍時，照執行器的作法停在虛擬桌面角落。
- 接著用票 01 的共用入口等停穩，再量。

判斷停穩要看這次量到的每一張圖。例如設定校準對時，新對和用來換算的舊對都要停穩；只看其中一對，另一對可能還在動。「測試備用校準對」只看備用對那兩張。

等待期間 AutoClick 視窗要維持清場（隱藏），但介面不能「沒有回應」。編輯器現在截圖前完全不移游標，這張票要把它補上。

規格：`.scratch/calibration-settle/spec.md`（Implementation Decisions「編輯器 5 處」「測試備用校準對」「設定校準對、設定備用校準對」）

**Blocked by:** 01（共用的停穩量測入口）

**Status:** resolved

- [x] 用編輯器校準 UI 測試確認 4 個按鈕量的都是停穩後的畫面。
- [x] 設定校準對時，舊對已停穩、新對還在動，要等新對也停穩才定案；測試要涵蓋這個情況。
- [x] 等待期間介面事件照常處理；測試要能看出等待不是單純阻塞主執行緒。
- [x] app 全套測試通過（在隱藏桌面跑）。

## Comments

- 2026-11-10（agent）：完成。4 個鈕改走 `App.recognize_settled(title, names, read, done)`：清場中背景跑 `calibration.settle`，每次截圖前 `automation.runner.avoid_cursor(region, sleep)`（停點 `runner.park_point`，從 `Runner._avoid_cursor` 抽出，執行器與編輯器共用），介面執行緒用新的 `Recognition.wait(job)`（巢狀事件迴圈）等、不卡介面；還原後才 `then(done)`，彈窗與寫紀錄都在清場外。停穩比對：設定校準對／設定備用校準對用 `calibration.joint_reading` 把舊對（主對）與新對（備用對）合成一次，每張圖都要停穩；測試備用校準對只看備用對（`calibration.measurement_reading`）。測試：新增 `test_editor_calibration_settle.py`（停穩後的倍率、游標在停點、新對還在動要等、只看備用對、真執行緒下每秒等待期間介面事件照常處理）；conftest 加 autouse `fake_cursor`（測試不動真游標）；`test_recognition.py` 原本「清場中查詢 0 次／扣住時辨識中」改成「等停穩在清場中量、還原後才收尾」並用 `while_settling` 在等待中看一眼再放行；`test_calibration_ui.py` 兩個預期次數 ×2。契約文件（app/CLAUDE.md、GLOSSARY「清場」、app-pitfalls、app-testing）補上「等停穩是清場中唯一做辨識的例外」。
- 偏離：等待期間辨識在清場中做，所以這 4 個鈕還原後不再有`辨識中`階段（背景做完才還原）；編輯器逾時沒有額外提示（執行器才有警告），規格沒要求。
