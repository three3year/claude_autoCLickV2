# 07 — 打包驗收收尾

**What to build:** 引擎背景載入的起訖與耗時寫入既有檔案日誌(供驗收與
日後回歸對照,不做常駐遙測);重新打包並部署,對打包版實測驗收:熱啟動
點擊 exe 到主視窗出現且按鈕可按 < 3 秒;冷啟動與改動前對照記錄。同步
改寫 app/CLAUDE.md 的啟動契約(「app 啟動建立一次 Engine、load_profile
自動登錄」已被 ADR 0004 推翻)與 ensure_registered 相關踩坑條目。

**Blocked by:** 02、03、04、05、06

**Status:** ready-for-agent

- [ ] 引擎載入 開始/完成(或失敗) 與耗時落地檔案日誌
- [ ] 重新打包成功並部署(只覆蓋 exe 與 _internal/,不動 profiles/)
- [ ] 打包版實測:熱啟動開窗 < 3 秒(至少兩次取值),數據記錄在 Comments
- [ ] 打包版冒煙:就緒前拒絕提示、範本預載、執行流程、比對測試各走一遍
- [ ] app/CLAUDE.md 啟動契約與踩坑條目改寫完成;spec Status 更新
