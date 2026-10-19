# 05 — 使用者審卡片、修正、案例進 benchmark/

**What to build:** 使用者用瀏覽器打開卡片頁看全部約 100 張，把錯的編號回報；agent 修正或刪除，最後把案例 commit 進 repo 根目錄 `benchmark/`。見 [spec](../spec.md)「Implementation Decisions」的審核流程。

**Blocked by:** 03 — 其餘類型；04 — 縮放兩端與跨影片

**Status:** ready-for-human

- [ ] 給使用者卡片頁的完整路徑；總數與各類數量列在本票 Comments
- [ ] 使用者回報錯的編號
- [ ] 錯的逐一修正答案或刪掉；修正過的再給使用者看一小頁確認
- [ ] 各類數量仍符合配額（刪掉造成不足的就補，補的也要給使用者看）
- [ ] 案例 commit 進 `benchmark/`；登錄快取沒進版控

## Comments

- 2026-10-20 agent：卡片頁 `C:\Users\three\我的電腦\AiProject\claude_autoClickV2\.scratch\benchmark-rebuild\tmp\cards.html`（本機檔，圖在旁邊的 `cards/`，不上傳）。共 97 張：一般正例 12、易誤判負樣本 12、同款多個 8、比色 12、忙碌指示 12、線索背景 10、混淆 11、縮放 12、跨影片 8（簡中 50、繁中 47）。agent 有疑問的 12 張排最前面（橘框）。等使用者回報錯的編號。
