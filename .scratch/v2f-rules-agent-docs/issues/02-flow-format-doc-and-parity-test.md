# 02 — 格式規範＋對照測試

**What to build:** 寫流程的 agent 只讀 `docs/flow-format.md` 一份，就知道 flow.yaml 每個鍵的意思、沒寫時是什麼、執行起來怎麼走、常見寫法怎麼寫。

- 對照測試：pytest 讀它的欄位表，跟 app 的預設表、記憶體模型各步驟可帶的鍵、讀檔認得的頂層鍵對照，不一致就紅。
- `app/CLAUDE.md`：「UI 慣例」裡的執行語意搬過來，原處只留實作指標與坑。

見 spec「格式規範」、子步驟順序第 2 步；內容清單照 [agent 文件結構](../../project-cleanup/issues/10-agent-docs-structure.md) 第 1、5 點。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 欄位表：頂層與各步驟的鍵、值、沒寫＝、單位，加上範本命名規則；格式讓 pytest 機械讀得出來（一張 md 表，至少有「適用步驟」「鍵」「沒寫＝」）
- [x] 執行語意：區段巢狀、分岔怎麼選分支、`on_fail` 三種與 break 跳到哪、`on_break` 往外傳、找圖三態（`wait_gone` 要先看到）、`confirm` 三種與補做、`busy_check` 的等待規則、原點與 `update_origin`、座標相對誰
- [x] 常見寫法：定位找圖接相對座標、可選彈窗分岔、巢狀重複跳出後的動作、`busy_check` 該勾的標準＋四份在用流程勾的 21 步（哪一步、為什麼）、固定矩形餘裕、備用校準對
- [x] 詞彙引用 `app/CONTEXT.md`，不重定義
- [x] 對照測試：多一個鍵、少一個鍵、預設值不同，各會失敗，訊息指出哪一格（用暫時改壞的副本驗證過一次）
- [x] `app/CLAUDE.md`：執行語意刪掉，換成指向格式規範；加一行「改讀檔或預設表要同步格式規範（測試會擋）」；根 `CLAUDE.md` 不動

## Comments

- 2026-10-11（agent）：`docs/flow-format.md` 寫好（欄位表 48 列、座標相對誰、執行語意、常見寫法）。`flowfile` 讀檔認得的鍵改成公開常數＋`step_keys(head)`（`_parse_step` 也用它），對照測試 `app/tests/test_flow_format_doc.py` 比鍵集合與「沒寫＝」；改壞的副本（多一鍵、少一鍵、預設值不同、漏寫預設）各留一個常駐測試，訊息指出列號、適用與鍵。`app/CLAUDE.md`「UI 慣例」的執行語意換成「執行語意（正本在 docs/flow-format.md）」一節，只留函式指標與日誌欄位，加了同步規範的那行；根 `CLAUDE.md` 沒動。
- 「四份勾的 21 步」：實際數下來四份共 65 步勾了 `busy_check`（早_簡中 18、早_繁中 15、晚兩份各 16），所以規範裡按用途分 7 類列表（範本／動作、出現在哪幾份、為什麼勾），沒有逐步列。
