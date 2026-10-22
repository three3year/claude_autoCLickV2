# 02 — build.bat 瘦成 ASCII 轉交；README 與 app/CLAUDE.md 改成一條打包法

Spec: `.scratch/build-bootstrap/spec.md`

**What to build:** 人雙擊 `app\build.bat` 走的就是票 01 的工具。build.bat 只含 ASCII：切到 repo 根，依序試 `py -3` 與 `python` 執行 `tools\build`，結束後 `pause` 讓視窗停住；不再寫死 venv 路徑、不再自己裝 PyInstaller。文件跟著改：README「打包與部署」開頭改成「第一次 clone 直接雙擊 build.bat，缺的環境它自己補」，刪「打包前先從原始碼啟動過一次 app」與「PyInstaller 不在 extras 裡」，交付物表加「從有 NVIDIA 的機器打約 3 GB、沒有的約 700 MB」；「安裝（原始碼版）」保留手動步驟並補一句「只想打包可略過這段」。`app/CLAUDE.md`「建置與部署」合併成一條「跑 `tools/build`」，刪 dist-new 改名流程與「build.bat 由程式呼叫會壞編碼」的坑，冒煙法、UAC 原因、必須 onedir、`upx=False` 保留。加一支靜態測試擋 build.bat 出現非 ASCII。

**Blocked by:** 01 — tools/build 工具

**Status:** done (2026-10-22)

- [x] 在現有 `.venv` 下雙擊 `app\build.bat`：打包成功、視窗停在完成訊息；失敗時視窗停在錯誤訊息
- [x] build.bat 全為 ASCII，有測試擋非 ASCII 字元
- [x] README「打包與部署」與「安裝（原始碼版）」照 spec 改寫；兩段互相指向、沒有重複的前置條件
- [x] `app/CLAUDE.md`「建置與部署」只剩一條打包法，沒有 dist-new 與改名流程
- [x] 文件對照測試（`app/tests/test_doc_refs.py`）綠：文件裡的 `tools/build` 路徑與指令都解析得過
- [x] 全套 pytest 綠
