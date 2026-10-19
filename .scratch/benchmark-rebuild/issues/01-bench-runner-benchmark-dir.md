# 01 — 基準集執行器改讀 benchmark/、給預期尺度、已知失敗分開報

**What to build:** 基準集指令不帶參數就跑 repo 根目錄的 `benchmark/`（也可以給別的資料夾），引擎參數只用內建預設、不讀任何設定檔。每個案例查詢時照 app 的查法給`預期尺度`（`expect.yaml` 的 `expected_scale`，沒寫＝1.0）。有 `known_failure` 的案例是`已知失敗`：報表分開一區列出、這次通過的標「可拿掉標記」，總結行分開算；除已知失敗外全部命中才算成功（結束碼）。見 [spec](../spec.md)「Implementation Decisions」的案例格式與基準集執行器兩段。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 對外介面改成「給基準集資料夾」；不帶參數時用 repo 根目錄 `benchmark/`
- [ ] 不讀設定檔：資料夾裡就算有設定檔，結果也跟只用內建預設一樣
- [ ] `expected_scale` 傳給引擎當預期尺度；沒寫傳 1.0
- [ ] `known_failure` 沒過不算失敗、列在已知失敗區；通過時標「可拿掉標記」
- [ ] 除已知失敗外有沒過的 → 結束碼失敗；全過 → 成功
- [ ] 來源欄位（流程、範本名、影片、幀號、案例類型）讀得進來、不影響判定
- [ ] 登錄產物快取在 `benchmark/` 底下 `_` 開頭的子資料夾，`.gitignore` 排除
- [ ] 基準集程式測試照現有寫法（暫存資料夾合成小案例）補上面每一項；舊集暫時還在 `profiles/`，用到它的測試先不動
- [ ] 全套引擎測試綠
