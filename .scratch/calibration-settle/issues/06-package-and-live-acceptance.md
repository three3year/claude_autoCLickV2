# 06: 打包與晚_簡中實機驗收

**What to build:** 把票 01、03、04 的程式改動打包成新的打包版，然後請使用者在簡中客戶端的視窗模式和放大模式各實跑一次晚_簡中，確認原本找不到圖的問題修好了。放大時，使用者會自己重選搜尋範圍。

規格：`.scratch/calibration-settle/spec.md`（Testing Decisions「實機驗收」）

**Blocked by:** 01、02、03、04

**Status:** ready-for-agent

- [x] 照 agent 打包法重新打包，舊版改名保留後再換上新版。
- [ ] 使用者實跑視窗模式：紀錄的 `calibrate` 是 ×1.000，並寫著 `settle=stable`。沒達到的話，用票 05 的量測腳本，在執行器的停點重量簡中基準距離。
- [ ] 使用者實跑放大模式：`calibrate` 約 ×1.13，並寫著 `settle=stable`，第 3 步「待辦事項」通過。
- [ ] 第 18 步按「制造中」後「无人机加速」有沒有出現，只觀察，把結果記在 Comments。沒出現就另外開單，不擋這張票。
- [ ] 兩次實跑的 calibrate 行與結果記在這張票的 Comments。

## Comments

- 2026-11-10 01:25 打包完成，用的是整合分支 0c22967，含票 01–05 與 code review 修正。舊版改名為 `app/dist/AutoClick-舊-20261110-0126` 保留。沒做冒煙，直接交給使用者實跑驗收。
