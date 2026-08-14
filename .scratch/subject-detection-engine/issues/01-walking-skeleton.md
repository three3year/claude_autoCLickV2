# 01 — 行走骨架:引擎 API + 遊戲設定檔結構

**What to build:** 腳本開發者可以建立一個明日方舟遊戲設定檔(模板庫 + config),用引擎公開 API 完成一次最簡單的查詢:載入設定檔、指定模板名稱與搜尋區域影像,拿回存在與否、邊界框座標與分數。比對演算法用最樸素的固定尺度模板匹配即可——這張票的價值是把唯一接縫(load_profile + query)、設定檔資料夾契約(templates / config.yaml / registered)、與 pytest 測試慣例一次打通,後續每張票都在這條通路上加強。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 引擎為可 import 的 Python 套件,Engine 建構一次後可重複查詢(常駐)
- [x] 建立明日方舟遊戲設定檔,模板自 autoClick 專案複製進設定檔的模板庫(至少含「返回」等數個同尺度可命中的模板)
- [x] query 對「主體存在」的截圖回報 found=true 且座標在容差內;對「主體不存在」的截圖回報 found=false
- [x] config.yaml 被讀取並生效(至少 match_threshold),引擎附一份保守預設 config
- [x] pytest 測試只經公開 API 進出,CPU 可跑
