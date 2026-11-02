# 06 — 打包版冒煙

**What to build:** 重新打包後，用打包版 AutoClick 執行一份只含外部步驟（指向假工具）的臨時流程，確認四種情況在打包版裡跟測試一致：成功、失敗、逾時、F12。啟動工具時不跳主控台視窗，結束後沒有殘留的工具程序。這份臨時流程放在 scratchpad，不放進 `flows/`。

**Blocked by:** 02, 03, 04, 05

**Status:** ready-for-agent

- [x] 照 `app/CLAUDE.md` 的 agent 打包法重新打包（打到 dist-new 再換上）
- [x] 開打包版前先確認使用者在不在、是不是在玩遊戲（見記憶「打包版冒煙前先確認使用者在不在」）
- [x] 成功：執行紀錄 done，含假工具的最後幾行
- [x] 失敗：failed，含結束碼
- [x] 逾時：failed，假工具和它的孫程序都已結束
- [x] F12：stopped
- [x] 全程沒有出現主控台視窗
- [x] 記錄是用 `AutoClick.exe` 還是 `AutoClick-noUAC.exe` 跑的，以及子程序的權限

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

2026-11-03 補跑（使用者同意在一般桌面跑、不動滑鼠）：**四種情況都通過，跟測試一致。**

- 用 `AutoClick-noUAC.exe` 跑，每種情況各開一次打包版。靶視窗置頂，放在 (1000, 250, 900, 600) 顯示校準對，四次都是
  `calibrate result=ok … distance=568.2 baseline=568.2 scale=1.000`。「開始執行」用真實點擊，點之前確認前景是 AutoClick 主視窗。
  停止那項**按迷你窗的「■ 停止」鈕**（跟 F12 一樣呼叫 `App.stop_all`），沒有送 F12，也沒有送任何鍵盤輸入。
- 成功（`print-pid print-console print-cwd say=hwnd={hwnd} say=成功最後一行`）：
  `external step=1 tool=假工具 expected=5 result=done exit=0 tail=pid=18668 | C:\Users\three\我的電腦\AiProject\claude_autoClickV2\.venv\Scripts | console=0 | hwnd=67373716 | 成功最後一行`。
  紀錄區印出這 5 行，接著是「外部工具「假工具」完成（結束碼 0）」「執行完成」。工作目錄是登錄的資料夾，`{hwnd}` 代入的是靶視窗。
- 失敗（`exit=3`）：`result=failed exit=3 tail=pid=16876 | 失敗前一行`。
- 逾時（`expect=2 grandchild`，上限 12 秒）：`result=timeout exit=killed tail=pid=23000 | grandchild=13276`。
  按下開始後約 16.6 秒出現 taskkill（3 秒開始延遲＋校準＋詢問＋12 秒）。結束後 venv 的 python 啟動器、真正的 python（23000）、
  孫程序啟動器（13276）和它底下的真正 python（32320）都已經不在，查 pid 確認。
- 停止（`expect=20 listen`）：`result=stopped exit=2 tail=pid=27372 | console=0 | 等待中 | 收到停止`。
  紀錄區先是「已通知工具停止，等它收尾（最多到啟動後 30 秒）」，接著是「已收尾結束（結束碼 2） → 已停止」。
- 主控台視窗：執行期間每 0.2 秒列一般桌面的 ConsoleWindowClass、CASCADIA_HOSTING_WINDOW_CLASS 和 PseudoConsoleWindow，
  跟基線比，四次都沒有新增；假工具自己印的是 `console=0`。工具底下有 conhost.exe 程序，但沒有視窗（CREATE_NO_WINDOW 的正常現象）。
- 權限：AutoClick-noUAC 和它開的所有子程序（python 啟動器、真正的 python、孫程序、conhost、taskkill）的 TokenElevation 都是 0，都不是 elevated。
- 殘留程序：每種情況結束後，記下的子孫程序 pid 全部不在。最後沒有 AutoClick，也沒有本次開的 python（只剩另一個專案的 pytest，不是本次開的）。
  每次都用 WM_CLOSE 正常關掉 AutoClick（結束碼 0）。state.json 已還原，跟備份逐位元組相同。
- 第一次跑停止那項時沒點到：主視窗收起後，前景落到置頂的靶視窗，SetForegroundWindow 切不到迷你窗，所以沒點。
  工具因此跑到 30 秒上限，記 `result=timeout`，這是驅動腳本的問題，不是產品的問題。讓靶視窗程序 AllowSetForegroundWindow 後重跑，就通過了（上面那筆）。
