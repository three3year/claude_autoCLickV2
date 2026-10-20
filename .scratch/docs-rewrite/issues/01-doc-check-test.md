# 01 — 文件對照測試

**What to build:** 一支隨根目錄 `pytest` 一起跑、不載引擎不開視窗的「文件對照」測試：讀 README、`app/CLAUDE.md`、它分出去的 `docs/agents/` 檔與三份 CONTEXT，把每個反引號路徑、指令、`模組.符號`、md 連結解析到 repo；解析不到就紅，訊息是「文件:行號 片語 — 規則名」、一次列全部。解析規則、對應表（`App`／`Runner`／`hub`／`store`／`win` 指到哪）、三條跳過規則（`<…>` 佔位、`%…%` 環境變數、`*`／`NNN` 樣式）與「流程資料夾內的名字對 app 佈局常數解析」都照 [spec](../spec.md)「Implementation Decisions」的文件對照測試一段。先例：格式規範對照測試。

**Blocked by:** None — can start immediately

**Status:** resolved

- [x] 四類片語各一個反例（不存在的路徑、符號、指向已刪模組的指令、斷掉的連結）用暫存 md 餵進同一個解析函式，紅且訊息含行號與規則名
- [x] 三條跳過規則各一個例子不紅
- [x] 流程資料夾內的名字對佈局常數解析：monkeypatch 常數後文件就紅
- [x] 對現在的文件跑一次，紅清單（預期至少有 `CONTEXT-MAP.md` 的 `load_config`）記在本票 Comments——這就是 02、03 要消掉的清單
- [x] 主測試（現有文件全部解析得過）這張票允許是紅的；02、03 各自把自己負責的文件修綠
- [x] 誤報要靠放寬解析規則處理（例：`capture.py` 對 `app/automation/` 解析），不是在測試裡加例外清單

## Comments

- 2026-10-21 測試寫好：`app/tests/test_doc_refs.py`（ast 讀原始檔、不 import app 模組、不載引擎）。
  反例、跳過規則、佈局常數 monkeypatch 三組案例綠；主測試對現在的文件跑出的紅清單（02、03 要消掉的）：
  - README.md:74 `config.yaml` — 路徑（設定檔早就沒了；02）
  - CONTEXT-MAP.md:35 `library.load_config` — 符號（02）
  - app/CLAUDE.md:77 `runner.start(calibration=…)` — 符號（是 `Runner.start`；03）
  - app/CLAUDE.md:82 `calibration.SCALE_LOW/HIGH` — 路徑（寫法：拆成兩個片語；03）
  - app/CLAUDE.md:88 `App.editor_scale` — 符號（已移除的東西不用反引號；03）
  - app/CLAUDE.md:146 `_internal\torch_home\hub` — 路徑（打包產物不在 repo；03）
  - app/CLAUDE.md:156 `profiles/` — 路徑（已退場；03）
  - app/CLAUDE.md:176 `cv2.imread/imwrite` — 路徑（寫法；03）
  - app/CLAUDE.md:207–208 `recognition.register`、`recognition.want` — 符號（是 `Recognition.register`／`want`；03）
  - app/CONTEXT.md:330 `calibration.fallback` — 符號（那是 yaml 鍵，不是 Python 符號；02）
- 放寬過的規則（誤報不進例外清單）：`app/` 開頭、沒帶參數的片語算路徑不算指令；docs/agents 既有三份
  skill 協定檔（issue-tracker、triage-labels、domain）不對照（內容不在本階段範圍，裡面的 `/wayfinder`
  是 skill 名、`map.md` 是範本名）。
