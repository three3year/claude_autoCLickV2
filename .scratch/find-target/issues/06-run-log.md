# 06 — 執行紀錄寫入 autoclick.log

**What to build:** 每個找圖目標的判定結束(找到、逾時、無法執行)時,在 `autoclick.log` 寫一筆:步驟位置、範本、
限定矩形、每個匹配的位置與分數(含比色分數)、挑選規則與挑中哪個、點擊落點;逾時另記最後一次查詢的
最高分與未過原因(匹配門檻/驗證門檻/比色門檻、數不到 N、沒有原點)。不逐次輪詢地寫。
UI 執行紀錄維持現有訊息,可附匹配數。

目的:使用者實跑回報點錯後,Claude 能從紀錄分辨「點錯哪個」與「沒找到」。

**Blocked by:** 04、05

**Status:** resolved

- [x] 執行器測試:找到、逾時、無法執行各寫一筆,內容含上列欄位
- [x] 一個輪詢多次的找圖步驟只寫一筆
- [x] 確認類(點擊後確認、確認圖、下一步的圖)的判定也有紀錄

## Comments

紀錄格式 (`autoclick.log` 一行一筆, 事件 `find.target`):

```
2026-10-04 18:00:00 find.target step=22 role=find template=製造站卡 result=found limit=all pick=top:3 color=off matches=[(212,668,103,40) 0.992; (439,668,103,40) 0.987; ...] picked=(666,668,103,40) polls=2 click=(717,688)
2026-10-04 18:00:05 find.target step=45 role=find template=快速置入 result=timeout limit=all pick=score color=on matches=[] rejected=[(1711,924,38,38) 0.886 c0.883] best=0.886 failed=color polls=7
```

- role: find / wait_gone / confirm_gone / confirm_appear / confirm_next / branch
- result: found / timeout / cannot_run / gone / not_gone (等待消失、目標圖消失)
- failed (沒挑到時): match / verify / color (引擎門檻)、count (數不到 N)、origin (沒有原點)、limit (限定範圍在搜尋範圍外)
- confirm_* 另記 clicks (含補點的總點擊數); step 是點擊的那一步。
