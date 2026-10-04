# 09 — 收尾:重新打包與正式資料遷移

**What to build:** 讓使用者的打包版用上新功能。照專案記憶:先把打包版的 profiles 移出(重打包會整個刪掉 dist),
不程式化呼叫 build.bat、直接跑 PyInstaller,再放回 profiles 並補 arknights profile 的放置步驟。
改正式資料前備份;確認打包版開啟既有流程(`日常_繁中`、`日常_簡中`、`基建換班_*`)會遷移成 v3、
步驟與範本不變。不送真實輸入;實跑由使用者做。最後更新專案記憶「引擎分不出列名」那條。

**Blocked by:** 06、07、08

**Status:** ready-for-human

- [x] 正式資料已備份,備份位置告知使用者
- [ ] 打包版可啟動、開啟既有流程後轉成 v3、步驟與範本數不變
- [x] profile config 有 `color_threshold`
- [x] 引擎基準測試集與全部自動測試全綠
- [ ] 專案記憶已更新;請使用者實跑並回報

## Comments

- 正式資料備份: `app/dist/profiles-backup-2026-10-04-find-target/` (整個 profiles, 在 dist/AutoClick 外面)。
- 重新打包: profiles 與 autoclick.log 先移出 dist/AutoClick, 直接跑 PyInstaller (exit 0), 再移回;
  移回後與備份逐檔相同。打包產物的 PYZ 內含 automation.findtarget、subject_detection.color 與
  code-review 修正後的版本 (靜態檢查)。
- 打包版 arknights profile 的 config.yaml 加了 `color_threshold: 0.95`; arknight_cn、test 兩個 profile
  沿用引擎預設 0.95。
- 既有流程遷移以原始碼對備份副本試跑: 8 份流程＋步驟草稿全部轉成 v3, 步驟數、引用的範本、
  存檔內的圖數與遷移前相同, 寫回 v3 再讀回一致。(原本就缺圖: arknightMorning_cn 引用 43 張只帶 17 張、
  arknightNight_cn 引用 15 張帶 0 張——遷移前就如此, 未變。) 磁碟上的存檔要等使用者存檔才蓋章 3。
- **未做**: 打包版啟動冒煙 (使用者當時在看影片, 不在畫面上開 GUI)。基準集 50/50、自動測試 581 全綠。
- 專案記憶「引擎分不出列名」已更新。待使用者: 開打包版 (確認可啟動、開日常_繁中/基建換班_* 正常)、
  驗收編輯器 (票 07)、實跑。
