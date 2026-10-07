# 05 — 打包,並移除四份流程的忙碌等待步驟

**What to build:** 把 02–04 的程式改動打包進打包版,讓使用者平常用的 exe 有忙碌暫停和固定矩形。接著把早_簡中、早_繁中、晚_簡中、晚_繁中裡「忙碌指示 → 等待消失」的步驟全部拿掉,換班後等網路改由下一步的忙碌暫停接手。

規格:`.scratch/busy-pause-fixed-rect/spec.md`(流程改動、打包兩節)。

**Blocked by:** 02 — 忙碌暫停;03 — 固定矩形:找圖時會用;04 — 固定矩形:編輯器拖框

**Status:** ready-for-agent

- [ ] 動手前確認使用者已關掉 AutoClick。
- [ ] 打包:
  - 先把 `app/dist/AutoClick/profiles/` 移出 dist,打包後放回(記憶:重新打包前把使用者資料移出 dist)。
  - 直接跑 PyInstaller,不經 build.bat(記憶:程式呼叫 build.bat 會壞編碼),再補 arknights profile 的放置步驟。
- [ ] 改流程前備份 profiles 到 `app/dist/profiles-backup-2026-10-0X-busy-pause-fixed-rect/`。
- [ ] 移除的步驟(以內容為準,不靠編號;改動前的編號是):
  - 早_簡中:82、90、98、107。
  - 早_繁中:68、70、80、91。
  - 晚_簡中、晚_繁中:各 31、40、42、52、54、56、64。
- [ ] 移除後區段、分岔保持完整,執行前的區段檢查不報錯。
- [ ] 透過 app 的流程存檔模組讀寫;`_autosave.json` 同步成跟改後的流程一致。
- [ ] 用無頭 harness 跑各流程換班那一段:有忙碌時下一步會等,沒忙碌時直接走,事件序列正確。
- [ ] 四份 `.md` 交付報告的步驟表更新,並加一節寫這次的改動。
- [ ] 建構與驗證腳本放在 `.scratch/busy-pause-fixed-rect/`,可以重跑。
