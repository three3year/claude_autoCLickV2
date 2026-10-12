# 03 — 視窗標題顯示流程名與未存檔 `*`

**What to build:** 視窗標題看得出現在開的是哪份流程、有沒有沒存的改動：`早_簡中 — AutoClick`；改了任何東西變成 `*早_簡中 — AutoClick`；存檔後 `*` 消失。新流程沒存過時是 `未命名 — AutoClick`。

見 spec「主視窗」的視窗標題。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 標題格式 `[*]<流程名> — AutoClick`；流程名＝流程資料夾名，新流程沒存過＝`未命名`
- [x] 所有標成未存檔的地方經同一個入口，那個入口同時更新標題；存檔、開檔、新流程（含回答「不存」）後標題回到沒有 `*`
- [x] 第一次存檔選了資料夾後，標題換成新流程名
- [x] 測試（App 接縫）：沿用 test_flow_open_save 的「每種改動都標成未存檔」案例，再加斷言標題有 `*`；存檔／開檔／新流程後沒有；新流程是 `未命名`

## Comments

- 2026-10-13 agent：_set_dirty 是唯一入口，_update_title 寫標題；測試在 test_flow_open_save。commit 4f45f3d。
