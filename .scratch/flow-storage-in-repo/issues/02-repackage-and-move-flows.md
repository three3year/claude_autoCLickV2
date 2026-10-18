# 02 — 重新打包並搬家

**What to build:** 使用者的打包版改用新的`流程存放區`，現有流程也搬過去。重新打包後，6 份流程（早_簡中、早_繁中、晚_簡中、晚_繁中、早_簡中_驗收add5、新流程）從 `C:\Users\three\AutoClick\` 整份搬進 `<repo>\flows\`，打包版下次開啟時自動開新位置的上次流程。舊位置不留副本。這是一次性操作，不寫通用遷移，見 [spec](../spec.md)「Implementation Decisions」的搬家段。

**Blocked by:** 01 — 流程存放區改成專案內 flows/

**Status:** ready-for-agent

- [ ] 動手前確認使用者不在玩遊戲、打包版沒開著（照 memory「打包版冒煙前先確認使用者在不在」）
- [ ] 先重新打包再搬家：照 memory 的打包方式打到 dist-new，舊版改名後再換上；換上後新打包版在 `app\dist\AutoClick\`
- [ ] 6 份流程資料夾原封不動搬進 `<repo>\flows\`（含 templates、.cache、交付報告、flow.yaml 備份檔）；搬前後各列一次檔案數與大小，確認一致
- [ ] 舊的 `C:\Users\three\AutoClick\` 搬空後刪掉
- [ ] `%LOCALAPPDATA%\AutoClick\state.json` 的上次流程改成 `<repo>\flows\晚_簡中`
- [ ] `git status` 看不到 `flows/` 底下任何檔案
- [ ] 更新寫到舊位置的 memory（例：流程資料夾格式待驗收、共用矩形那幾則）
