# 01 — 移除忙碌暫停

**What to build:** 找圖等待(分岔條件、一般找圖、生效確認、等待消失、出現等候上限)不再因畫面上有忙碌指示而延後逾時,逾時照常計時。補做前查忙碌指示的那道門不變。這是後面忙碌檢查的前置整理,先把 ADR 0010 的機制拿乾淨。

規格:`.scratch/busy-check/spec.md`(執行器:移除忙碌暫停、接縫一);ADR 0011;詞彙見 `app/CONTEXT.md`。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 分岔、一般找圖(三態)、生效確認(找圖點擊、座標點擊、拖曳)、等待消失、出現等候上限:忙碌期間照原本時間逾時。
- [x] 生效確認裡補做的門照舊:這一輪沒生效時用同一張截圖查一次忙碌指示,看到就不補做;`busy_delay` 欄位保留。
- [x] 找圖等待不再為了暫停而查忙碌指示(查詢紀錄裡只剩補做門那一次)。
- [x] 共用的等待時鐘保留,只拿掉暫停;只為暫停存在的參數、欄位一併清掉。
- [x] `find.target`、`input.confirm` 不再有 `busy_pause` 欄位。
- [x] 忙碌暫停的既有測試改寫成反向(忙碌時照原本時間逾時);補做門、出現等候上限的其他測試照舊通過。
- [x] 全部 pytest 通過。

## Comments

**2026-10-08(實作)**

- `WaitClock` 只剩截止時間/出現等候上限,`pause`/`busy`/`BUSY_PAUSE_CAP` 全拿掉;`_note_busy` 改成 `_busy_seen`,只在 `_await_effect` 沒生效的那一輪呼叫(補做的門)。分岔、一般找圖、等待消失不再查忙碌指示。
- `find.target`、`input.confirm` 不再有 `busy_pause`;`busy_delay` 保留。
- 舊 `test_runner_busy_pause.py` 改寫成反向的 `test_runner_busy_no_pause.py`;`test_runner_retry` 的逾時案例改成照常 2 秒逾時(busy_delay 約 1.0)。
