# 03 — 找圖目標改名

**What to build:** 機械改名第一批（寬幅重構，照鍵的群組分批）：`找圖目標`（步驟的 `target` 與確認圖）的內容改成跟 flow.yaml 同名同值——`within: [x, y, w, h]`（取代 `limit: {kind: rect, rect}`）、`pick: {top: N}｜{left: N}｜{near: [x, y]}`（取代 `{kind, n}`／`{kind: near, at}`）、`color: true`（取代 `colorCheck`）。範圍是全部讀它的地方：執行器、找圖目標模組、拾取檢查、編輯器、清單摘要、影片轉流程工具、測試資料。舊存檔讀寫那一層加這組的舊鍵↔新鍵翻譯（過渡碼，08 刪）。不改行為。見 spec「記憶體模型」。

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] 記憶體裡的找圖目標只用 `template`、`within`、`pick`、`color`；全 repo 程式碼不再讀寫舊鍵（除了舊存檔翻譯層）
- [ ] 舊存檔讀進來翻成新鍵、寫出去翻回舊鍵；四份流程開檔→存檔後 `flow.json` 內容不變
- [ ] 影片轉流程工具組出的步驟用新鍵
- [ ] 不改行為：現有測試（只改資料的鍵名）全綠
