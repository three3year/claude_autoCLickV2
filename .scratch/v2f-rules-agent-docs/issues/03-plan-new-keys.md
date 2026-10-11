# 03 — 轉換計畫改新鍵

**What to build:** agent 用跟 flow.yaml 一樣的鍵寫轉換計畫（開頭鍵即動作、秒、`on_fail`、`busy_check`、`repeat`／`branch` 巢狀），`assemble` 就組裝出一樣的流程資料夾。

- 計畫跟 flow.yaml 的差別只剩兩樣：影片像素位置（`at`／`from`／`to`），和影片證據欄位。
- 舊鍵、按鍵步驟、原點矩形、出現等候上限，以及寫了 `within` 或 `offset`，一律報錯，並指出新鍵或「已退場」。
- 工具不帶自己的預設，照 app 預設表。
- 寫完資料夾後用檢查指令驗一次。

見 spec「轉換計畫（新鍵）」、04 規則 10–13。

**Blocked by:** 01 — 結構檢查抽出＋檢查指令

**Status:** done

- [x] 計畫的步驟鍵與區段寫法跟 flow.yaml 相同；頂層是 `video`、`name`、`out`、`templates`、`steps`、`calibration`、`busy`、`report`
- [x] 舊鍵（`type`、`colorCheck`、`onNotFound`、毫秒、`loop_start`、`busyTarget`…）、按鍵、`within`、`offset`，各有報錯測試，輸出位置不多任何檔
- [x] 等於預設的值（`on_fail` 停止、`timeout` 10、`interval` 0.3）不寫出；工具裡沒有另一份預設
- [x] 寫完後跑檢查指令；檢查有錯就當工具錯誤報出
- [x] 現有的組裝測試、照 skill 程序走一遍的測試改成新鍵後全綠
- [x] `plan-format.md` 先改成新鍵（只改鍵名、刪三處牴觸；完整改寫在 09）

## Comments

- 2026-10-11（agent）：`plan.py` 重寫：步驟去掉影片證據（`frame`、`at`、`scroll`、`confirm.frame`）後交給 app 的 `flowfile.parse_steps` 驗證與補齊（新增的公開函式），工具裡沒有第二份鍵表或預設；舊鍵、按鍵、`within`、`offset`、毫秒（`timeout`／`wait` ≥ 100）各有指出新鍵的報錯。位置寫法：`click` 的值、`drag` 的值與 `to`、找圖的 `at`、`pick: {near}` 都是影片像素的畫面位置（spec 寫「at、from、to」，實作讓 click/drag 沿用 flow.yaml 的鍵、只差數字的意義，計畫跟 flow.yaml 少一個鍵名差異）。**工具不再自己推 `confirm`**（舊版找圖點擊自動 next/gone、拖曳自動 gone）：計畫明寫才有，跟 flow.yaml 一樣；skill 教 agent 怎麼寫。組裝與補充寫完都跑檢查指令，有錯當工具錯誤（`assemble` 在暫存資料夾裡檢查，不留半成品）。照 skill 走一遍的測試在 HEAD 就是紅的（合成「確定」在種子 100 的底圖上縮放餘裕 0.68），改用同一張底圖修好。`plan-format.md` 的完整改寫併在 09。
