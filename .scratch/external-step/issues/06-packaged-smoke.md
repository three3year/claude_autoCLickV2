# 06 — 打包版冒煙

**What to build:** 重新打包後，用打包版 AutoClick 執行一份只含外部步驟（指向假工具）的臨時流程，確認四種情況在打包版裡跟測試一致：成功、失敗、逾時、F12。啟動工具時不跳主控台視窗，結束後沒有殘留的工具程序。這份臨時流程放在 scratchpad，不放進 `flows/`。

**Blocked by:** 02, 03, 04, 05

**Status:** ready-for-agent

- [x] 照 `app/CLAUDE.md` 的 agent 打包法重新打包（打到 dist-new 再換上）
- [x] 開打包版前先確認使用者在不在、是不是在玩遊戲（見記憶「打包版冒煙前先確認使用者在不在」）
- [ ] 成功：執行紀錄 done，含假工具的最後幾行
- [ ] 失敗：failed，含結束碼
- [ ] 逾時：failed，假工具和它的孫程序都已結束
- [ ] F12：stopped
- [ ] 全程沒有出現主控台視窗
- [ ] 記錄是用 `AutoClick.exe` 還是 `AutoClick-noUAC.exe` 跑的，以及子程序的權限

## Comments

2026-11-03 驗收子代理（打包版 `app/dist/AutoClick/`，來源 786178e，由主代理打包）：**四種情況沒驗到，卡在隱藏桌面截不到畫面。**

- 使用者在用電腦（前景 VS Code，idle 約 56 秒；主代理說在看 YouTube），所以靶視窗和打包版都開在隱藏桌面（CreateDesktopW＋lpDesktop），沒送任何全域輸入。
- 隱藏桌面上截螢幕一定失敗：同一個 venv 的 mss `grab` 在 BitBlt 丟 `ScreenShotError: BitBlt: 存取被拒`；
  直接 BitBlt 螢幕 DC 也一樣，`SRCCOPY` 錯誤 6，`SRCCOPY|CAPTUREBLT` 錯誤 5。runner 開頭一定要校準（`_calibrate` → `capture.grab`），
  所以打包版在隱藏桌面走不到外部步驟。另外 `_grab` 截圖前會先 `_avoid_cursor` → `win.park`（SetCursorPos＋SendInput），
  為了不碰全域輸入，沒有按「開始執行」。
- 做到的部分：`AutoClick-noUAC.exe` 在隱藏桌面開得起來，state.json 暫時指向臨時流程（scratchpad `t06/flows/外部冒煙`：
  校準對＋一個外部步驟，登錄 `dir` 是 `.venv\Scripts`、`exe` 是 `python.exe`，跑 fake_tool），日誌記
  `engine.load.start` → `engine.load.done secs=1.91 coarse_only=False`。主視窗 PrintWindow 截圖看得到
  「[外部步驟] 假工具 …」、範本校準甲／校準乙，紀錄區顯示「已開啟流程「外部冒煙」」。啟動期間每 0.5 秒列隱藏桌面和 Default 桌面，
  沒有新的 ConsoleWindowClass／CASCADIA_HOSTING_WINDOW_CLASS。AutoClick 程序本身不是 elevated（TokenElevation=0）。
  送 WM_CLOSE 後正常結束（結束碼 0），沒有子程序，也沒有殘留的 AutoClick／python 程序。state.json 已還原，跟備份逐位元組相同。
- 還沒驗：成功、失敗、逾時、停止這四種情況，執行期間沒有主控台視窗，以及工具子程序的權限。要嘛等使用者不在時在一般桌面跑，
  要嘛由使用者自己跑。臨時流程和腳本留在 scratchpad `t06/`：`launch.py` 建隱藏桌面，`hd.py` 有 PrintWindow、行程樹、權限、點擊等工具。
