# 06 — 一張預設表

**What to build:** app 一個模組放「沒寫＝」表（＝flow.yaml 欄位表的預設：`on_fail` stop、`timeout` 10、`interval` 0.3、`confirm` none、拖曳 `duration`／`hold` 0.5、`on_break` continue、`run` 1、`busy_check` false、`update_origin` true）。讀檔與新增步驟時補齊成完整步驟，執行器、編輯器、影片轉流程工具不再自帶預設（工具自己的預設模組收掉）。這是行為變更：找圖缺 `on_fail` 從跳過改成停止、拖曳缺值統一 0.5 秒。`timeout`／`interval`／`on_fail` 只補在有等待的步驟上。見 spec「預設表」。

**Blocked by:** 05

**Status:** resolved

- [x] 預設只存在一張表；執行器、編輯器、工具的讀取點不再有 `.get(鍵, 預設)` 式的各自預設
- [x] 舊存檔讀進來與新增步驟都補齊成完整步驟
- [x] 新增行為測試：找圖缺 `on_fail` 找不到時停止；拖曳缺 `duration`／`hold` 用 0.5 秒；沒設 `confirm` 的點擊不補 `timeout`
- [x] 四份流程缺值為零，讀進來的行為不變（開檔→存檔 `flow.json` 不變）
- [x] 測試全綠

## Comments

- 2026-10-11（agent）：表在 `app/automation/flowdefaults.py`（`complete`／`strip`／`new_step`，另有各步驟可帶欄位 `KEYS` 給讀檔驗證與編輯器換三態用）。找圖三態以外的 find／wait_gone 不帶 `confirm`、`busy_check`。執行器只剩忙碌檢查在「沒有等待欄位的步驟」用表裡的輪詢間隔。行為變更：找圖缺 `on_fail`＝停止、拖曳缺值 0.5／0.5 秒、輪詢預設 0.3 秒；影片轉流程的預設模組刪掉，生效確認的推定規則（next／gone）搬進 `assemble._complete`。
