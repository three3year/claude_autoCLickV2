# 04 — 驗收：指令各跑一次、打包、地圖收尾

**What to build:** 文件裡每個指令手動各跑一次證明跑得通；打包一次把基準集階段之後的引擎帶進打包版；專案整理地圖註記文件階段完成、六階段全部結束。見 [spec](../spec.md)「Testing Decisions」的最後驗收與「Implementation Decisions」的建置、地圖兩段。

**Blocked by:** 02 — README 重排；03 — app/CLAUDE.md 分層

**Status:** resolved

- [x] 全套測試綠（app 全套在隱藏桌面跑）；對照測試整份綠
- [x] 原始碼啟動 app：隱藏桌面冒煙，啟動到引擎就緒沒有例外
- [x] 打包：照 `app/CLAUDE.md` 新寫的 agent 打包法做（打到新資料夾再換名；打包前從原始碼跑過一次讓 hub 快取存在；確認 dist 沒有使用者資料）；打包版帶 ADR 0016 之後的引擎
- [x] noUAC 版在隱藏桌面啟動、開一份在用流程：登錄快取重建一次、紀錄出現「範本就緒」
- [x] 基準測試集不帶參數跑：跟基線一致（80/80、已知失敗 17）
- [x] `tools/flow_check` 對一份在用流程跑過沒有錯誤；影片轉流程的 `--help` 跑得出來
- [x] 每個跑過的指令與結果一行記在本票 Comments
- [x] 地圖 Notes 註記文件階段完成、六階段全部結束
- [ ] 打包版實機驗收（開遊戲跑一輪）需要使用者在場：不在場就記下「待使用者」，不擋本票結案

## Comments

- 2026-10-21 指令各跑一次：
  - `.venv/Scripts/python -m pytest`（隱藏桌面）：1128 passed（7 分 13 秒），含文件對照測試 13 項。
  - `.venv/Scripts/python -m subject_detection.bench`：其他案例 80/80、已知失敗 0/17、結束碼 0——跟基線一致。
  - `.venv/Scripts/python tools/flow_check flows/晚_簡中`：沒有錯誤（61 步），結束碼 0。
  - `.venv/Scripts/python tools/video_to_flow --help`：印出四個子指令，結束碼 0。
  - `.venv/Scripts/python app/app.py`（隱藏桌面）：3 秒內 engine.load.done secs=2.02 coarse_only=False，stdout 沒有例外。
  - 安裝指令跳過（已裝）。
  - 打包：`cd app && ../.venv/Scripts/python -m PyInstaller --distpath dist-new AutoClick.spec` 成功（約 4 分鐘），
    舊版改名 dist/AutoClick-舊-1021-0219、新版搬進 dist/AutoClick（02:19 建置，帶 ADR 0016 之後的引擎與
    default_config.yaml）；dist 裡沒有使用者資料。
  - noUAC 冒煙（隱藏桌面）：engine.load.done secs=1.83，自動開上次流程 晚_簡中，範本預載把 `.cache/registered/`
    104 個檔全部重建（meta.json 換成新格式），state.json 的上次流程沒變。
  - 文件對照測試依 code review 補強：縮排的 bash 圍欄也抽指令（之前 app/CLAUDE.md 的打包指令沒被查到）、
    符號只收大寫常數、加 `-m 已刪模組` 反例；文件去重（使用者資料位置、打包交付物、引擎參數各留一個正本）。
  - 打包版實機驗收（開遊戲跑一輪）：使用者不在場（idle 14 分鐘，前景是 VS Code）——**待使用者**。
- 地圖 Notes 已註記文件階段完成、六階段全部結束。
