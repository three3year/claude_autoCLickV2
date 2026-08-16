# 05 — flow pack 攜帶校準對與匯入換算(無/同對)

**What to build:** 匯出 flow pack 時附帶校準對兩個範本(依既有範本打包規則)與基準距離。匯入時:目標 profile 沒有校準資料 → 採用 pack 的(補進缺的範本、寫入基準距離,倍率留空=未校準,校準按鈕立即可用);目標已有且為同一對校準圖(以範本名判定,撞名沿用「已存在不覆蓋」)→ 匯入流程的座標 ×(目標基準距離 ÷ pack 基準距離)換算後落地。既有 pack(無校準資料)照舊匯入。

**Blocked by:** 02 — 指定校準對與首次校準。

**Status:** resolved

- [x] 匯出:pack 內含校準對範本與基準距離;沒有校準對的 profile 匯出的 pack 與現狀相同
- [x] 匯入(目標無校準資料):採用 pack 校準對與基準,倍率留空=未校準;流程座標原樣落地
- [x] 匯入(同一對):流程座標依基準比值換算落地,換算為校準模組純函式、以檔案測試驗各類步驟欄位
- [x] 匯入無校準資料的舊 pack:行為與現狀相同(回歸)
- [x] 測試照 flow pack 既有手法:暫存目錄真檔案、匯出→匯入 roundtrip

## Comments

- 2026-08-16 已實作完成: export_pack 附 calibration.json 與校準對範本; import_pack 三分支 (adopted/converted/foreign), 校準對範本列入 refs 正確落地。tests: test_flowpack.py。
