# 07 — 備用校準對核心:存檔、量測、執行器

**What to build:** 流程可以帶一組備用校準對;執行開頭主對找不到時自動改量備用對、座標基準點換算回同一個點,執行紀錄印一行警告後照跑;主備都找不到才不執行並列出兩組各缺哪張。沒設備用對的流程行為與現在完全相同。

規格:`.scratch/scale-range/spec.md`「校準對與備用校準對」存檔、量測、執行器三段;user stories 21–23、26–27。接縫:存檔格式純函式(前例 `test_flowfile.py`、`test_coord_space.py`)、calibration 純函式(前例 `test_calibration.py`)、執行器 harness(前例 `test_runner_calibrate.py`)。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 存檔:流程層級校準資料多一個可選的備用組——兩個範本名、它自己的基準距離、「備用第一張中心 → 座標基準點」的偏移(流程尺度整數)。沒有備用組的存檔一字不差;格式版本不升;備用組不成形(範本名缺、基準距離非正、偏移缺)讀檔時當沒有並警告。「只寫被引用的範本」把備用對兩張算進引用;重新命名範本時備用對的引用跟著改。
- [x] calibration 純函式多一個入口:先量主對,主對任一張找不到就量備用對;結果帶「用的是哪一組」;用備用對時基準點＝備用第一張中心 − 偏移×(備用距離 ÷ 備用基準距離),倍率是備用對量出來的(同樣有貼齊 1 的容差);主備都缺時結果列出兩組各缺哪張。
- [x] 執行器開頭校準走這個入口:用了備用對時 calibrate 檔案紀錄多一個欄位標明備用,執行紀錄區印「主校準對找不到(缺哪一張),改用備用校準對,座標誤差略大」,照跑;主備皆無時不送任何輸入,訊息列出兩組各缺哪張。
- [x] 測試:存檔讀寫與缺欄位;純函式的主對優先、備用換算、偏移為零時與主對同點;harness 的切換警告與紀錄、備用基準點下固定矩形的落點、主備皆無不送輸入。既有測試全綠。

## Comments

**2026-10-09（實作）**

- 存檔：校準資料多可選的 `fallback` 鍵 `{pair, baseline, offset}`（`calibration.make_fallback`／`fallback_pair`／`fallback_problem`）；格式版本不升；沒有備用組的存檔一字不差。`flow_refs` 與 `rename_flow_refs` 把備用對兩張算進引用。讀檔不成形的警告由編輯器 `_apply_flow` 印（票 08 一起接）。
- 量測：`calibration.calibrate` 先量主對，主對任一張找不到且有備用組才量備用對；`Calibrated.used`（main／fallback）、`main`／`fallback` 兩組量測、`pair`／`baseline` 是用的那一組；用備用對時基準點＝`fallback_anchor(備用第一張中心, 偏移, 倍率)`＝中心＋偏移×倍率（`flowfmt.to_screen`），設定時偏移＝`fallback_offset(基準點, 備用第一張中心, 倍率)`（`from_screen`），兩者互逆。主備都缺時 `describe()` 兩組各列缺哪張。
- 執行器：`calibrate` 紀錄用備用對時多 `used=fallback`、`main_missing`；主備皆缺時多 `fallback_pair`／`fallback_missing`；執行紀錄印「主校準對找不到（缺「x」），改用備用校準對「a」×「b」，座標誤差略大」後照跑；備用對列入範本預載；之後找圖的預期尺度是備用對量到的倍率。
- 測試 `test_fallback_calibration.py` 18 個（存檔往返、改名、純函式主對優先／備用換算／偏移為零同點／主備皆缺、harness 切換警告與紀錄、固定矩形落點、主備皆無不送輸入、預載、預期尺度）；runner 等 335 passed。
