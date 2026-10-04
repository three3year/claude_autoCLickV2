# 07 — 遷移四份在用流程、重新打包、實跑驗收

**What to build:** 使用者升級後,四份在用流程(基建換班_簡中/繁中、日常_簡中/繁中)直接能跑,換客戶端不必再校準。Claude 先備份正式 profile(比照 `.scratch/find-target/issues/09-repackage-and-migrate.md`),把各流程座標換到自己的流程尺度(簡中 ×0.8057;繁中 × 繁中倍率,以 demo3 標題列距離 ÷ 舊基準距離 2049.8 求得),各自放入該客戶端的校準對範本(簡中沿用現有標題列圖示/關閉鈕;繁中從 demo3 截)與基準距離,移除正式 profile 的校準資料;四份廢棄流程不動。重新打包後請使用者兩個客戶端各實跑一次基建換班。

規格:`.scratch/flow-scale/spec.md`;ADR 0009。

**Blocked by:** 06 — 舊校準模型退場

**Status:** ready-for-agent

- [ ] 正式 profile 已備份,備份位置記在本檔 Comments
- [ ] 四份流程帶校準對與基準距離,座標為流程尺度
- [ ] 用示範影片影格自我驗證:找圖照常找到、相對座標換算後落點與影片一致
- [ ] 正式 profile 不再有校準資料檔與校準圖
- [ ] 全部 pytest、基準測試集通過,重新打包(注意 memory:build-bat-encoding、repackage-move-user-data-out、packaged-smoke-user-present)
- [ ] 使用者以簡中、繁中各實跑一次基建換班,執行紀錄的開頭校準倍率約為 1、全程無點偏
