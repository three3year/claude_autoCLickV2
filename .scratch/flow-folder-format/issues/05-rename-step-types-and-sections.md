# 05 — 步驟種類與區段改名

**What to build:** 機械改名第三批：`type` 等於 yaml 開頭的鍵——找圖三態直接是 `find_click`／`find`／`wait_gone`（`action` 併進 `type`）；重複區段改 `repeat_start`（`repeat: N`）／`repeat_end`；區段結尾的跳出後動作改 `on_break`。區段仍是平面標記。範圍同 04。舊存檔翻譯層補這一組。不改行為：清單一列一項、執行紀錄的步驟編號、收合、測試選取照舊。見 spec「記憶體模型」。

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] 記憶體步驟沒有 `action`、`loop_*`、`count`、`onBreak`；全 repo 程式碼只讀新名（除了舊存檔翻譯層）
- [ ] 舊存檔開檔→存檔後 `flow.json` 內容不變（四份流程）
- [ ] 不改行為：現有測試全綠
