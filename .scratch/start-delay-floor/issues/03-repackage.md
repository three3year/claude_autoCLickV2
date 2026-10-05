# 03 — 重新打包

**What to build:** 打包版帶上新的開始延遲行為,使用者實跑時按下執行後等待的時間符合設定的下限。照 memory 的做法重打包:先把 `dist/AutoClick/` 裡的 profiles 與 autoclick.log 移到 dist 底下但 AutoClick 外面,直接跑 PyInstaller(不經 build.bat),再移回。打包版啟動冒煙前先確認使用者不在操作。

規格:`.scratch/start-delay-floor/spec.md`;memory:build-bat-encoding、repackage-move-user-data-out、packaged-smoke-user-present。

**Blocked by:** 02 — 狀態字跟著開跑前階段

**Status:** ready-for-human

- [x] 全部 pytest 通過後重新打包,profiles 與日誌原樣移回
- [ ] 打包版啟動冒煙:視窗正常、引擎就緒、流程讀得到
- [ ] 使用者實跑:紀錄順序與狀態字符合規格,設 3 秒時第 1 步在按下執行約 3 秒後開始(日誌 calibrate 時間對照)

## Comments

**2026-10-06 打包(agent)**
- 全套 pytest 通過(677 passed;另 1 個引擎計時測試 `test_near_fullscreen_coarse_stays_fast` 在機器忙時超過 500ms,單獨重跑通過,與本改動無關)。
- 打包前備份 `app/dist/profiles-backup-2026-10-05-start-delay/`;profiles 與 autoclick.log 移出、PyInstaller 重打、原樣移回,與備份逐檔一致。
- 打包版內容檢查(讀 PYZ/exe 的 bytecode,不開視窗):runner 與 app 帶 `pressed_at`、引擎預載帶 `on_loaded`、狀態字為「等待準備範本完成…」、舊「準備範本中…」狀態字已移除。
- 打包內容同時含工作區尚未提交的 not_appeared 紀錄 best/failed 改動(只多記欄位)。
- **啟動冒煙未做**:兩次檢查使用者都在操作(idle 0 秒,前景是遊戲),依規則不開 GUI。留給使用者:開打包版確認視窗、引擎就緒、流程讀得到,再實跑對照紀錄順序與 calibrate 時間。
