# 01 — 結構檢查抽出＋檢查指令

**What to build:** agent 對任何一個流程資料夾跑檢查指令（不載引擎、不開視窗），就知道這份流程 app 讀不讀得進來、執行時會不會一開始就出錯。

- 錯誤：列出步驟與原因，以非零結束。
- 缺圖：引用了但缺圖的範本列成「要在 app 截的範本」，不算錯。
- `--normalize`：沒有錯誤時，經 app 的讀寫把 `flow.yaml` 重寫一次，讓手改後過期的行尾步驟編號與排版回到標準。

做法：先把 App 執行前的區段結構檢查抽成不依賴視窗的模組函式，App 與檢查指令共用。見 spec「結構檢查與檢查指令」、子步驟順序第 1 步。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 區段結構檢查（成對、不交錯、分岔每個分支開頭是找圖點擊、「或」直接在分岔內）是一個模組函式；App 執行前改呼叫它，訊息與行為不變，現有測試全綠
- [x] 檢查指令依序跑：讀檔（鍵、型別、`format`）、結構檢查、每個相對座標點擊／拖曳前有原點來源、勾 `busy_check` 但沒設 `busy`、缺圖
- [x] 每類錯誤各有一個測試（tmp_path 裡手寫的流程資料夾）：結束碼非零，訊息含步驟與原因
- [x] 缺圖：列出清單，結束碼為零
- [x] `--normalize`：手改過、編號過期的檔被寫回標準排版；有錯誤時不寫；不加旗標時一個檔都不寫
- [x] 四份在用流程（`%USERPROFILE%\AutoClick\`）跑檢查指令都沒有錯誤（只讀，不加 `--normalize`）

## Comments

- 2026-10-11（agent）：結構檢查抽到 `app/automation/flowcheck.py`（`section_error`、`no_origin`、`origin_leaves_bad`、`confirm_next_bad`、`busy_check_bad`，`flow_errors` 一次跑完整份）；App 的 `_flow_error`、`_fragment_origin_error`、`_origin_leaves_bad`、`_confirm_next_bad` 改成薄包裝，訊息不變，app 全套 643 passed（隱藏桌面）。檢查指令 `python tools/flow_check <流程資料夾> [--normalize]`（`tools/flow_check/`）。除了 spec 列的五類，也把 app 執行前另外會擋的「沒有校準對」「原點的圖離開的原點不是找圖」「點到下一步的圖出現不相連」列成錯誤——app 一樣會擋，檢查指令不放行。另列「templates/ 裡沒被引用的圖」當資訊（app 下次存檔會移走）。`--normalize` 只重寫 `flow.yaml`（經 `flowfile.dump_flow`），不動 `templates/`。四份在用流程唯讀跑過：早_簡中 268 步、早_繁中 227 步、晚_簡中 61 步、晚_繁中 61 步，都沒有錯誤。
