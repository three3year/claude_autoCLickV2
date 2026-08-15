# 06 — flow pack 匯出(新格式)

**What to build:** 從當前 profile 匯出自包自足的 flow pack:flow 存檔 + 其引用的全部範本(含多截圖範本目錄整包)。匯出的 pack 可在另一個 profile(或另一台機器的同版 app)匯入還原,round-trip 後流程與範本完整一致。

**Blocked by:** 04 — profile 結構與切換/建立

**Status:** ready-for-agent

- [ ] 匯出 pack 內含 flow 與所有被引用範本(單檔與多截圖目錄皆支援)
- [ ] 匯出→匯入 round-trip 測試綠(暫存目錄真測):步驟、範本引用、範本圖一致
- [ ] 未被引用的範本不進 pack
