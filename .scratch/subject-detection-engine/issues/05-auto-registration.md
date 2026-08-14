# 05 — 自動登錄與失效判斷

**What to build:** 腳本開發者的日常工作流變成「裁模板 → 丟進 templates 資料夾 → 重跑腳本 → 直接可用」,沒有任何手動登錄指令。load_profile 自動偵測:新模板(補登錄)、模板內容變更(以內容 hash 判斷,重登錄該模板)、影響登錄產物的 config 參數變更(scale_range、mask_strategy,自動重跑受影響部分);門檻類參數(match_threshold、verify_threshold)只在查詢時讀取,改動下次執行即時生效、不觸發重登錄。

**Blocked by:** 04 — 登錄遮罩

**Status:** ready-for-agent

- [ ] 丟一張新模板進 templates 資料夾,重新 load_profile 後即可查詢,無手動步驟
- [ ] 換掉一張既有模板的圖片內容,該模板自動重登錄,其他模板不受影響
- [ ] 改 scale_range 或 mask_strategy 後自動重跑受影響的登錄;改門檻參數不觸發重登錄
- [ ] 登錄產物損毀或缺漏時自動重建,不會讓查詢崩潰
- [ ] 上述行為全部以公開 API 的外部行為測試(操作資料夾與 config,斷言查詢結果與登錄有無發生)
