# 08 — 刪整個 profiles/、舊建構工具，文件同步

**What to build:** 整個 `profiles/` 從 repo 消失（舊基準集、來源素材、設定檔），舊的明日方舟基準集建構工具一起刪；`.gitignore` 的 `profiles/` 規則拿掉。`profiles/` 底下沒進版控的本機舊資料（舊 profile 的 flows、workspace 等），刪之前先問使用者。刪完再跑一次新集確認。文件寫明「改引擎前後必跑基準集」。見 [spec](../spec.md)「Implementation Decisions」的一次刪除、刪完重跑、文件三段。

**Blocked by:** 07 — 引擎刪多張圖登錄路徑

**Status:** ready-for-agent

- [ ] 刪之前列出 `profiles/` 底下沒進版控的東西給使用者，得到同意才刪
- [ ] `profiles/`、舊建構工具刪掉；全 repo 搜不到指向它們的引用（打包設定、測試、腳本）
- [ ] `.gitignore` 的 `profiles/` 規則拿掉
- [ ] 重跑新集：跟 06 基線一致
- [ ] 全套測試綠
- [ ] 引擎說明與 agent 文件寫明基準集指令與「改引擎（門檻、模型、刪路徑）前後必跑」；README、`app/CLAUDE.md` 的基準集描述改成 `benchmark/`（README 其他過期內容留給文件階段）
- [ ] 專案整理地圖 Notes 註記基準集階段完成
