# 06 — 打包版冒煙

**What to build:** 重新打包後，用打包版 AutoClick 執行一份只含外部步驟（指向假工具）的臨時流程，確認四種情況在打包版裡跟測試一致：成功、失敗、逾時、F12。啟動工具時不跳主控台視窗，結束後沒有殘留的工具程序。這份臨時流程放在 scratchpad，不放進 `flows/`。

**Blocked by:** 02, 03, 04, 05

**Status:** ready-for-agent

- [ ] 照 `app/CLAUDE.md` 的 agent 打包法重新打包（打到 dist-new 再換上）
- [ ] 開打包版前先確認使用者在不在、是不是在玩遊戲（見記憶「打包版冒煙前先確認使用者在不在」）
- [ ] 成功：執行紀錄 done，含假工具的最後幾行
- [ ] 失敗：failed，含結束碼
- [ ] 逾時：failed，假工具和它的孫程序都已結束
- [ ] F12：stopped
- [ ] 全程沒有出現主控台視窗
- [ ] 記錄是用 `AutoClick.exe` 還是 `AutoClick-noUAC.exe` 跑的，以及子程序的權限
