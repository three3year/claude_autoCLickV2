# 01 — 文件對照測試

**What to build:** 一支隨根目錄 `pytest` 一起跑、不載引擎不開視窗的「文件對照」測試：讀 README、`app/CLAUDE.md`、它分出去的 `docs/agents/` 檔與三份 CONTEXT，把每個反引號路徑、指令、`模組.符號`、md 連結解析到 repo；解析不到就紅，訊息是「文件:行號 片語 — 規則名」、一次列全部。解析規則、對應表（`App`／`Runner`／`hub`／`store`／`win` 指到哪）、三條跳過規則（`<…>` 佔位、`%…%` 環境變數、`*`／`NNN` 樣式）與「流程資料夾內的名字對 app 佈局常數解析」都照 [spec](../spec.md)「Implementation Decisions」的文件對照測試一段。先例：格式規範對照測試。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 四類片語各一個反例（不存在的路徑、符號、指向已刪模組的指令、斷掉的連結）用暫存 md 餵進同一個解析函式，紅且訊息含行號與規則名
- [ ] 三條跳過規則各一個例子不紅
- [ ] 流程資料夾內的名字對佈局常數解析：monkeypatch 常數後文件就紅
- [ ] 對現在的文件跑一次，紅清單（預期至少有 `CONTEXT-MAP.md` 的 `load_config`）記在本票 Comments——這就是 02、03 要消掉的清單
- [ ] 主測試（現有文件全部解析得過）這張票允許是紅的；02、03 各自把自己負責的文件修綠
- [ ] 誤報要靠放寬解析規則處理（例：`capture.py` 對 `app/automation/` 解析），不是在測試裡加例外清單
