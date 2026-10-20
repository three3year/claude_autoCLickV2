# 08 — 刪整個 profiles/、舊建構工具，文件同步

**What to build:** 整個 `profiles/` 從 repo 消失（舊基準集、來源素材、設定檔），舊的明日方舟基準集建構工具一起刪；`.gitignore` 的 `profiles/` 規則拿掉。`profiles/` 底下沒進版控的本機舊資料（舊 profile 的 flows、workspace 等），刪之前先問使用者。刪完再跑一次新集確認。文件寫明「改引擎前後必跑基準集」。見 [spec](../spec.md)「Implementation Decisions」的一次刪除、刪完重跑、文件三段。

**Blocked by:** 07 — 引擎刪多張圖登錄路徑

**Status:** resolved

- [x] 刪之前列出 `profiles/` 底下沒進版控的東西給使用者，得到同意才刪
- [x] `profiles/`、舊建構工具刪掉；全 repo 搜不到指向它們的引用（打包設定、測試、腳本）
- [x] `.gitignore` 的 `profiles/` 規則拿掉
- [x] 重跑新集：跟 06 基線一致
- [x] 全套測試綠
- [x] 引擎說明與 agent 文件寫明基準集指令與「改引擎（門檻、模型、刪路徑）前後必跑」；README、`app/CLAUDE.md` 的基準集描述改成 `benchmark/`（README 其他過期內容留給文件階段）
- [x] 專案整理地圖 Notes 註記基準集階段完成

## Comments

- 2026-10-21 agent：刪之前列給使用者的沒進版控資料：`profiles/arknights/flows/`（8/18 的 4 份舊格式 .autoclickpack＋_autosave.json）、`workspace/`（舊 profile 工作區 217 檔）、`benchmark/_registered/`＋`_assets/_registered/`（舊集登錄快取）。使用者選「全部刪掉」。
- 2026-10-21 agent：
  - `git rm -r profiles tools/build_arknights_benchmark.py`（進版控 285 檔）＋ `rm -rf profiles`；`.gitignore` 的 8 條 `profiles/*` 規則拿掉。
  - 全 repo 搜 `profiles/`、`build_arknights_benchmark`、`load_profile`：原始碼、測試、打包設定（`app/*.spec`、`build.bat`、`pyproject.toml`）都沒有；剩 `docs/adr/`（歷史）、`flows/*/交付報告/`（使用者流程資料夾內的舊紀錄，gitignore）、`app/dist/`（打包產物與備份，gitignore）、`app/CLAUDE.md` 一句「`profiles/` 已整個退場」。
  - 文件：README 開頭、「使用」範例（`load_profile` → `load_templates`）、「新遊戲上手」→「接上一個呼叫端」、調參紀律、整段「基準測試集」（格式、指令、改引擎前後必跑、目前基線）、架構的登錄一句；舊的「驗收紀錄（明日方舟）」刪掉。`CONTEXT.md` 基準測試集詞條加「改引擎前後都要跑」；根目錄 `CLAUDE.md` 新增「引擎基準測試集」段（指令、基線比對規則、怎麼加案例）；`app/CLAUDE.md` 的 `profiles/arknights/` 句改掉。
  - 重跑新集：`其他案例 80/80  misses: 0  false_alarms: 0  |  已知失敗 0/17  misses: 9  false_alarms: 8  |  OK`，逐案例判定跟 06 基線一致。
  - 全套：引擎＋tools 362 passed、app 751 passed（隱藏桌面）。
  - 專案整理地圖 Notes 已註記基準集階段完成。
- 2026-10-21 agent：`/code-review`（since 0dbf6ed，兩軸並行）後修正：
  - 修：`library.py::load_config` 已無生產呼叫端，搬進 `tests/synth.py`、`__init__.__all__` 拿掉；`engine.py`／`matching.py`／測試 docstring 與測試名的 profile 字眼改掉；`make_library` 錯誤訊息統一英文（測試改 `match="one image"`）；`bench.py` 的 `color_check`／`known_failure` 收成 `Case` property，docstring 與 README 的 `source:` 鍵補齊；**沒有案例（路徑打錯、空資料夾）結束碼 1 並印「沒有案例」**（原本印 `0/0 … OK`，先寫紅燈測試再改）；`CONTEXT.md` 只留一句指向根目錄 `CLAUDE.md`，不重複指令；README 去掉寫死的「97 個案例」；`cluebg08_tw`／`multi06_tw` 的原因文字改繁中「來自」；`cross04` 的 `source.kind` 註明是跨影片的比色負樣本。
  - 不修（有理由）：bench 輸出 UTF-8（票 06 已申報）、README 超出基準集描述的改動（都指向已刪的東西）、空 `known_failure` 算已知失敗（票 01 review 決定）、兩個貼內部格式的測試（種舊快取必須）、app 側沒有 US 43 的新測試（spec 測試決定放接縫二，引擎側已測）。
  - 修完：引擎 80、tools 284、app 751（隱藏桌面）全綠；新集跟基線一致。
