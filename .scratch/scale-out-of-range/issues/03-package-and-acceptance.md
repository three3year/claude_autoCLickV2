# 03 — 重打包與實機驗收

Spec：[../spec.md](../spec.md)。

**What to build:** 打包版帶上 01、02 的行為，並在真實遊戲視窗上確認：視窗縮到範圍外按執行，開頭就被擋，遊戲沒被點；調回原大小照常跑。

重打包：在 app 資料夾直接跑 PyInstaller（build.bat 程式化呼叫會壞編碼，見 memory `build-bat-encoding`）；先確認 dist 裡沒有使用者資料（memory `repackage-move-user-data-out`）。實機驗收要使用者在場：先查使用者是否閒置、前景是否在玩（memory `packaged-smoke-user-present`），不在場就停下等。

**Blocked by:** 01, 02

**Status:** ready-for-agent

- [ ] 全套測試：除了開工前就有的 3 個工具測試失敗（合成按鈕縮放餘裕）之外全過
- [ ] 已重打包，打包版開得起來
- [ ] 實機：繁中視窗縮到約 ×0.70 按執行 → 開頭就不執行，紀錄寫倍率、×0.85–1.15、「調大」，遊戲畫面沒被點
- [ ] 實機：調回原大小（最大化）按執行 → 照常開跑
- [ ] 實機：編輯器在 ×0.70 按「校準」→ 介面紀錄有範圍外警告
- [ ] memory `flow-folder-acceptance-pending` 註記這項已上線
