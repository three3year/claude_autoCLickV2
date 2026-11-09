# 04: 拾取和按確定後的拾取檢查等停穩，完成後游標移回原位

**What to build:** 所有`拾取`都在凍結畫面之前先等主畫面停穩，凍結給使用者框選的就是停穩的那張。這包括截圖框選、固定矩形、指定點、拾取座標、比對測試。步驟對話框按「確定」後自動做的`拾取檢查`也一樣要等停穩。

流程如下：先記下游標位置，把游標移到停點，等停穩，凍結畫面或量完，再把游標移回原本的位置。停點與不卡介面的等待，沿用票 03 的做法。

規格：`.scratch/calibration-settle/spec.md`（Implementation Decisions「編輯器 5 處」；決策「按確定後的拾取檢查也要等停穩嗎」「拾取後游標要不要移回原位」）

**Blocked by:** 03（編輯器的停點與不卡介面的等待）

**Status:** resolved

- [x] 拾取凍結的那張就是停穩那張（編輯器拾取測試）。
- [x] 拾取後游標回到原位。現有編輯器測試沒有假游標，要補一個。
- [x] 按確定後的拾取檢查用的是停穩後的倍率，檢查完游標回到原位（拾取檢查 UI 測試）。
- [x] app 全套測試通過（在隱藏桌面跑）。

## Comments

- 2026-11-10（agent）：完成。`ui_dialogs.measured_pick` 有校準對時分兩段，同一件辨識：清場中先記下游標位置，背景
  `_settled_measure` 跑 `calibration.settle`（每次 `avoid_cursor` 後截整個桌面再 `App.scan_frame`；拾取檢查只截
  搜尋範圍），介面執行緒 `Recognition.wait`；停穩那張就是凍結給覆蓋層的畫面，量完（finally）`win.park` 把游標移回原位。
  接著 `Job.follow`（新增，`chain` 改用它）在背景推算 ◎／拾取檢查，同時叫覆蓋層，照舊 pending／辨識中。停穩那段
  出錯或等待中主視窗被關：不叫覆蓋層，`cleared`（步驟對話框關閉）照做，收尾寫失敗。`Recognition.wait` 斷開 poll
  自我參照，Tk 變數不會在別的執行緒被 GC（全套曾出現 PytestUnraisableExceptionWarning）。
  測試：新增 `test_pick_settle.py`（截圖新增凍結停穩那張、倍率照停穩那次、凍結後與收尾時游標在原位；按確定的拾取檢查
  用停穩倍率、游標回原位；停穩時出錯對話框照關）。假游標沿用票 03 的 conftest autouse `fake_cursor`。
  `test_recognize_pick.py`：Held 改用 `held_after_settle`（停穩那段當場做完、後面扣住），「清場中查詢 0 次」改成
  「清場中只量校準」，「覆蓋層顯示中校準失敗」改成「停穩後校準失敗不叫覆蓋層」；`test_editor_scale`、
  `test_fixed_rect_ui` 校準查詢次數 ×2；`test_calibration_ui` 安靜量測的假 app 補 `scan_region` 與假截圖。
  文件：app/CLAUDE.md 拾取流程、GLOSSARY「避開游標」、app-pitfalls、app-testing。
- 偏離：沒有校準對時拾取不等停穩、也不移游標（沒有東西可比對停穩，照舊直接截）。停穩後校準失敗時不再先叫出
  覆蓋層（以前覆蓋層出現後才知道失敗並中止），直接還原後警告。
