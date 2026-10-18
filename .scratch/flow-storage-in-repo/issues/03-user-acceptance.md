# 03 — 使用者實機驗收

**What to build:** 使用者用新打包版確認搬家後日常使用沒受影響。見 [spec](../spec.md)「Testing Decisions」最後一條。

**Blocked by:** 02 — 重新打包並搬家

**Status:** ready-for-human

- [ ] 開新打包版，自動開到 `<repo>\flows\晚_簡中`
- [ ] 按「開檔」，對話框開在 `<repo>\flows\`，看得到 6 份流程
- [ ] 跑一輪平常的流程，行為跟搬家前一樣
- [ ] 改一個流程後存檔，`git status` 仍然乾淨
