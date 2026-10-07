# 05 — 四份流程勾忙碌檢查與交付報告

**What to build:** `早_簡中`、`早_繁中`、`晚_簡中`、`晚_繁中` 在會讓遊戲忙的步驟勾上忙碌檢查,使用者打開就能跑。交付報告寫清楚勾了哪些、實跑要看什麼。

規格:`.scratch/busy-check/spec.md`(流程改動);ADR 0011。

**Blocked by:** 04 — 文件與打包;以及 evening-notice-close 收尾(外部:它的流程改動與票 03 驗收做完)

**Status:** ready-for-agent

- [ ] 前置:evening-notice-close 已收尾;使用者已關掉 AutoClick;備份 profiles 到 `app/dist/profiles-backup-<日期>-busy-check/`。
- [ ] 建構腳本放在本功能 `.scratch` 資料夾,可重跑;只透過 app 的流程存檔模組讀寫;以步驟內容定位,不靠編號。
- [ ] 四份都勾(該流程沒有的就略過):
  - ADR 0010 拿掉等待步驟的位置(busy-pause-fixed-rect `results/remove_busy_waits.json` 記的「緊接在前」那一步)。
  - 換班段的每一個拖曳。
  - 開頭清彈窗的關閉點擊(簽到、活動、公告、獲得物資;晚班開頭新加的公告關閉)。
  - 傳遞線索的點擊。
  - 可收獲、幹員信賴、確定。
- [ ] 忙碌出現等候不寫鍵(預設 1000ms)。
- [ ] `_autosave.json` 草稿同步成跟改動的流程一致。
- [ ] 讀回驗證:每份流程勾選的步驟清單與預期一致,其他步驟內容不變;流程有忙碌指示、執行前檢查不擋。
- [ ] 四份交付報告 `.md`:步驟表標出〔忙碌檢查〕,加一節寫這次改動與實跑要看的 `busy.check`。
