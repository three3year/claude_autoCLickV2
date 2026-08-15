# 06 — flow pack 匯出(新格式)

**What to build:** 從當前 profile 匯出自包自足的 flow pack:flow 存檔 + 其引用的全部範本(含多截圖範本目錄整包)。匯出的 pack 可在另一個 profile(或另一台機器的同版 app)匯入還原,round-trip 後流程與範本完整一致。

**Blocked by:** 04 — profile 結構與切換/建立

**Status:** done (2026-08-15)

- [x] 匯出 pack 內含 flow 與所有被引用範本(單檔與多截圖目錄皆支援;
      磁碟相對路徑即 pack 內佈局;引用缺範本時擋下並逐一列出)
- [x] 匯出→匯入 round-trip 測試綠(暫存目錄真測):步驟一字不差、
      範本引用與範本圖一致、_meta pos 隨行(`test_flowpack.py`)
- [x] 未被引用的範本不進 pack(meta pos 也只帶被引用者)
