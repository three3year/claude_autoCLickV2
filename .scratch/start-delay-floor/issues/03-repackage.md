# 03 — 重新打包

**What to build:** 打包版帶上新的開始延遲行為,使用者實跑時按下執行後等待的時間符合設定的下限。照 memory 的做法重打包:先把 `dist/AutoClick/` 裡的 profiles 與 autoclick.log 移到 dist 底下但 AutoClick 外面,直接跑 PyInstaller(不經 build.bat),再移回。打包版啟動冒煙前先確認使用者不在操作。

規格:`.scratch/start-delay-floor/spec.md`;memory:build-bat-encoding、repackage-move-user-data-out、packaged-smoke-user-present。

**Blocked by:** 02 — 狀態字跟著開跑前階段

**Status:** ready-for-human

- [ ] 全部 pytest 通過後重新打包,profiles 與日誌原樣移回
- [ ] 打包版啟動冒煙:視窗正常、引擎就緒、流程讀得到
- [ ] 使用者實跑:紀錄順序與狀態字符合規格,設 3 秒時第 1 步在按下執行約 3 秒後開始(日誌 calibrate 時間對照)
