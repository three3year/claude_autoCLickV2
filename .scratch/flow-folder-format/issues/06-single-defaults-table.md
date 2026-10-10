# 06 — 一張預設表

**What to build:** app 一個模組放「沒寫＝」表（＝flow.yaml 欄位表的預設：`on_fail` stop、`timeout` 10、`interval` 0.3、`confirm` none、拖曳 `duration`／`hold` 0.5、`on_break` continue、`run` 1、`busy_check` false、`update_origin` true）。讀檔與新增步驟時補齊成完整步驟，執行器、編輯器、影片轉流程工具不再自帶預設（工具自己的預設模組收掉）。這是行為變更：找圖缺 `on_fail` 從跳過改成停止、拖曳缺值統一 0.5 秒。`timeout`／`interval`／`on_fail` 只補在有等待的步驟上。見 spec「預設表」。

**Blocked by:** 05

**Status:** ready-for-agent

- [ ] 預設只存在一張表；執行器、編輯器、工具的讀取點不再有 `.get(鍵, 預設)` 式的各自預設
- [ ] 舊存檔讀進來與新增步驟都補齊成完整步驟
- [ ] 新增行為測試：找圖缺 `on_fail` 找不到時停止；拖曳缺 `duration`／`hold` 用 0.5 秒；沒設 `confirm` 的點擊不補 `timeout`
- [ ] 四份流程缺值為零，讀進來的行為不變（開檔→存檔 `flow.json` 不變）
- [ ] 測試全綠
