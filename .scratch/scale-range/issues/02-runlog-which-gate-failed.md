# 02 — 執行紀錄說清楚哪一關沒過

**What to build:** 使用者看執行紀錄就知道找不到圖是粗篩、驗證還是比色沒過、分數多少;生效確認逾時與手動停止也留下可診斷的檔案紀錄,不必為了看紀錄故意等逾時。

規格:`.scratch/scale-range/spec.md`「執行紀錄」一節、user stories 32–35。接縫:執行器 harness(前例 `test_runner_runlog.py`、`test_runner_pointer_confirm.py`)。找圖結果物件已有「沒過的那一關」(match / verify / color / count)可直接用。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 找圖逾時的執行紀錄訊息改成寫沒過的那一關與該關分數:粗篩沒過「粗篩最高 0.59」、驗證沒過「驗證最高 0.72」、比色沒過「比色最高 0.942(圖形 0.974)」;挑選規則挑不到照現狀印數量。不再只印「最高相似度」。
- [x] 生效確認(等出現、等消失、找圖相連)逾時的 `input.confirm` 檔案紀錄多最高分與沒過的那一關,欄位名與 `find.target` 紀錄一致。
- [x] 手動停止落在找圖或生效確認的輪詢裡時,先寫一筆結果為 stopped、帶目前最高分與沒過的那一關的檔案紀錄,再停止;停止前已找到的照常不多寫。
- [x] harness 測試覆蓋三種關卡的訊息字樣、生效確認逾時紀錄欄位、手動停止紀錄;既有測試全綠。

## Comments

**2026-10-09（實作）**

- `runner.GateBest` 記輪詢期間各關最高分；逾時訊息改成「粗篩最高 0.590」「驗證最高 0.720」「比色最高 0.942（圖形 0.974）」，挑選規則挑不到照舊印數量；等待消失「從未出現」與生效確認（座標點擊／拖曳、找圖點擊的確認圖／下一步）逾時訊息也帶同一句。
- 檔案紀錄：`input.confirm` 逾時多 `best`／`failed`（與 `find.target` 同名；`原點的圖離開`沒離開時 failed=still_there、best 是仍在原位那個匹配的分數）。
- 手動停止落在找圖、等待消失、分岔、生效確認（找圖點擊與座標點擊／拖曳）的輪詢裡：先寫一筆 result=stopped（帶 best/failed、polls；等待消失帶看到的位置）再停止；還沒輪詢過一次就停不寫；停止前已找到的照常只有 found 那筆。
- 假偵測器 `harness.miss(關卡, 分數)` 可安排「卡在哪一關」；比色全沒過時分數改回圖形分數（同引擎）。
- 測試 `test_runner_gate_log.py` 16 個；runner 全部 334 passed。
