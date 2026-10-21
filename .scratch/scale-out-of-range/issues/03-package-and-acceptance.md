# 03 — 重打包與實機驗收

Spec：[../spec.md](../spec.md)。

**What to build:** 打包版帶上 01、02 的行為，並在真實遊戲視窗上確認：視窗縮到範圍外按執行，開頭就被擋，遊戲沒被點；調回原大小照常跑。

重打包：在 app 資料夾直接跑 PyInstaller（build.bat 程式化呼叫會壞編碼，見 memory `build-bat-encoding`）；先確認 dist 裡沒有使用者資料（memory `repackage-move-user-data-out`）。實機驗收要使用者在場：先查使用者是否閒置、前景是否在玩（memory `packaged-smoke-user-present`），不在場就停下等。

**Blocked by:** 01, 02

**Status:** done

- [x] 全套測試：除了開工前就有的 3 個工具測試失敗（合成按鈕縮放餘裕）之外全過
- [x] 已重打包，打包版開得起來
- [x] 實機：視窗縮到範圍外按執行 → 開頭就不執行，紀錄寫倍率、×0.85–1.15、「調大」，遊戲畫面沒被點
- [x] 實機：調回原大小按執行 → 照常開跑
- [x] 實機：編輯器在範圍外按「校準」→ 介面紀錄有範圍外警告
- [x] memory `flow-folder-acceptance-pending` 註記這項已上線

## Comments

- 2026-10-11 13:57（agent；使用者閒置 39 分鐘、遊戲與打包版都沒開）：全套 app 636／引擎 66／工具 139 passed（工具 3 failed 為開工前就有）。直接跑 PyInstaller 重打包（dist/AutoClick 只有兩個 exe 與 `_internal`，沒有使用者資料）。noUAC 版在隱藏桌面啟動 40 秒、不送輸入：`engine.load.done` 4.94 秒。**還沒做**：三項實機驗收，要使用者在場。
- 2026-10-21 08:21（使用者實機）：使用者回報三項都完成。`autoclick.log` 對得上第一項：早_簡中視窗縮小後按執行，
  `calibrate result=out_of_range pair=標題列圖示,標題列關閉鈕 scale=0.358`，之後沒有任何 find.target／click，遊戲沒被點。
  第二、三項（調回原大小照常跑、編輯器校準警告）以使用者回報為準；同天 08:07–08:16 早_繁中／早_簡中 ×1.000 整趟跑完可佐證第二項。
  票收掉，scale-out-of-range 三張票全部完成。
