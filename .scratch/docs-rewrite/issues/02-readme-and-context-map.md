# 02 — README 重排與事實修正

**What to build:** README 改成一份兩大段：上半「AutoClick」給使用者（安裝、啟動、流程資料夾與流程存放區只指向 `docs/flow-format.md`、使用者資料位置、打包與部署、哪裡看日誌），下半「主體偵測引擎」給開發者（公開 API 範例、接呼叫端、引擎參數與調參表改成「內建預設＋流程 `engine:` 段覆蓋」且逐列核對、基準測試集格式與指令當正本、兩階段架構、涵蓋三個 testpaths 的測試指令一行）。根目錄 `CLAUDE.md` 的「引擎基準測試集」段只留規則、案例格式指向 README。`CONTEXT-MAP.md` 的引擎 API 清單拿掉 `load_config`。見 [spec](../spec.md)「Implementation Decisions」的 README、`CONTEXT-MAP.md`、根目錄 `CLAUDE.md` 三段。

**Blocked by:** 01 — 文件對照測試

**Status:** resolved

- [x] 對照測試在 README、根目錄 `CLAUDE.md`、三份 CONTEXT 全綠
- [x] 調參表每一列的參數名、預設值、方向對過引擎內建預設與程式碼
- [x] 基準測試集的格式與指令只在 README 一處；根目錄 `CLAUDE.md` 指過去、不重複格式
- [x] 舊集數字與「驗收紀錄」不出現
- [x] 文件用 CONTEXT 的詞（範本清單、預期尺度、已知失敗…），不用標為「避免」的詞
- [x] 每個指令的參數照現在的工具（bench 不帶參數、pytest 不給路徑即三個 testpaths）
