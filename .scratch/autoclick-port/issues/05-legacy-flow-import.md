# 05 — 舊 flow 匯入

**What to build:** 單向匯入 autoClick 舊資產到當前 profile:舊 flow JSON 檔與 `.autoclickpack`(zip 內含 flow 與範本圖)。匯入規則:範本引用去 `.png` 副檔名對應到本 repo 範本名;pack 內 profile 缺少的範本圖補進 templates/(已存在的不覆蓋);legacy 螢幕空間座標沿用既有座標空間遷移邏輯轉為區域空間;每步 threshold 欄位安靜丟棄;匯入後以新格式存入當前 profile 的 flows。匯入為資料進資料出的純邏輯,用暫存目錄真測。

**Blocked by:** 04 — profile 結構與切換/建立

**Status:** ready-for-agent

- [ ] 舊 flow JSON 與 .autoclickpack 都能匯入,存檔落在當前 profile
- [ ] 範本名對應(去副檔名)與缺圖補檔行為有測試覆蓋
- [ ] legacy 座標空間與 threshold 丟棄行為有測試覆蓋
- [ ] 4 個實戰 pack(arknightMorning/Night × cn/zh)匯入成功,步驟數與範本引用完整
