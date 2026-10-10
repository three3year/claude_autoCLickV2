# 04 — 步驟欄位改名、毫秒改秒

**What to build:** 機械改名第二批：步驟層欄位改成跟 flow.yaml 同名同單位——`on_fail`（`onNotFound`）、`confirm_target`（`confirmTarget`／`confirmTemplate`）、`update_origin`、`busy_check`、`offset: [x, y]`（`offsetX`／`offsetY`）、座標點擊 `click: [x, y]`、拖曳 `drag: [x, y]`＋`to: [x, y]`、等待 `wait: 秒`；所有時間欄位改秒（`timeout`、`interval`、拖曳 `duration`／`hold`、`wait`）。範圍含執行器、app 清單與結構檢查、編輯器（tk 變數同名）、影片轉流程工具、測試 builder 與測試資料。舊存檔翻譯層補這一組。不改行為（缺值預設照舊，統一留給 06）。見 spec「記憶體模型」。

**Blocked by:** 03（同一批檔案，排成串避免互撞）

**Status:** ready-for-agent

- [ ] 記憶體步驟只用新鍵與秒；全 repo 程式碼不再讀寫舊鍵與毫秒欄位（除了舊存檔翻譯層）
- [ ] 測試 builder 的參數改成新鍵名（呼叫端一併改）
- [ ] 舊存檔開檔→存檔後 `flow.json` 內容不變（四份流程）
- [ ] 不改行為：現有測試全綠
