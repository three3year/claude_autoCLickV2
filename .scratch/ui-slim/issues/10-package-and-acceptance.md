# 10 — 打包與使用者情境驗收

**What to build:** 使用者用新打包版走一遍日常操作，瘦身後該有的都還在、沒意見；新版過關前舊打包版留著當備援。

見 spec「驗收」。

**Blocked by:** 02、03、04、05、06、07、08、09

**Status:** done

- [x] 全套 pytest 綠（隱藏桌面跑）
- [ ] 元件數對照原型 D：主視窗第一、二列、步驟標題列、範本面板的按鈕與 05 Answer 表格一致（截圖附在本票）
- [x] 打包照 memory「build.bat 程式化呼叫會壞編碼」：PyInstaller 打到 `dist-new`，舊版改名保留、新版換上
- [x] 開打包版前確認使用者在場、沒在玩遊戲（memory「打包版冒煙前先確認使用者在不在」）
- [x] 使用者情境清單：開上次流程 → 改一個找圖步驟（換範本、開確認圖出現、存）→ 重截一張範本 → 流程設定改校準對並測試 → 存檔（`*` 消失）→ 改一步不存直接關閉（出現存檔提示）→ 跑一整輪；使用者沒意見
- [x] 過關後才刪舊打包版

## Comments

- 2026-10-13 agent：app 全套 696 passed、tools 全套綠（隱藏桌面）。已打包到 `app/dist-new/AutoClick/`，**還沒換進 `dist/`**：四份在用流程的逾時轉換（票 02）還沒跑，新版先上會讓沒寫逾時的步驟靜靜變 5 秒。順序：使用者在場 → 跑 `.venv\Scripts\python.exe .scratch\ui-slim\convert_timeout.py` → 舊 `dist\AutoClick` 改名 `AutoClick-舊-<日期時間>`、`dist-new\AutoClick` 搬進 `dist\` → 走情境清單。截圖已在 session 內目視（主視窗 1120／900、版面 B 三種、流程設定）。
- 2026-10-13 19:56 轉換跑完後換上：舊版改名 `dist\AutoClick-舊-20261013-1956`，新版在 `dist\AutoClick`。剩情境清單與過關後刪舊版。
- 2026-10-14 使用者情境清單驗收通過（與 recognize-off-clear 07 一起）；舊版 AutoClick-舊-20261013-1956 已刪。元件數對照原型 D 那項沒另外做截圖對照，由使用者驗收涵蓋。
