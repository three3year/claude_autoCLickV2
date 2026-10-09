# 03 — 絕對座標以座標基準點為準

**What to build:** 執行開頭`校準`除了倍率,也得出這次的`座標基準點`(校準對第一張圖中心),執行紀錄多寫一行它的螢幕位置。`座標點擊`與`拖曳`的`絕對座標`從「搜尋範圍左上角」改成「座標基準點 + 偏移×倍率」,執行、編輯器拾取、預設原點推算(前一步是絕對座標時)一致。建立存檔座標⇄螢幕座標的共用換算純函式,之後 04–08 都用它。打通「量基準點 → 換算 → 執行與拾取」整條路。

規格:`.scratch/coord-anchor/spec.md`(座標基準點與校準、座標換算、接縫一、接縫二)。

**Blocked by:** 01 — 存檔新格式、舊格式拒絕開啟;02 — 編輯器每次拾取當下量校準

**Status:** done

- [x] harness 把校準對擺在不同位置/倍率、搜尋範圍框法不同時,絕對座標落點＝基準點+偏移×倍率,與搜尋範圍無關。
- [x] 校準對不在搜尋範圍內＝一個輸入都不送,報明原因(既有行為不退化)。
- [x] 執行紀錄寫出座標基準點位置。
- [x] 編輯器拾取絕對座標、拖曳端點時存成相對當下基準點的偏移(流程尺度)。
- [x] test_coord_space、test_runner_scale 的絕對座標案例改寫成新語意;接縫一、二綠。

## Comments

**2026-10-09(實作)**

- 共用換算只有 `flowfmt.to_screen/from_screen/rect_to_screen/rect_from_screen`(右下角各自換算再相減,寬高不差 1px)。
- 執行器:`_calibrate` 用 `calibration.calibrate` 得 `scale` 與 `anchor`;`_abs_origin` 回 anchor(不再要求搜尋範圍);`_find` 帶 anchor;執行紀錄多一行「座標基準點 (x, y)(校準對第一張「…」的中心…)」,落點紀錄改寫「基準點 +x,+y」;檔案日誌 `calibrate` 不變。範圍內找不到校準對的訊息改成提醒重框搜尋範圍。
- 編輯器:拾取絕對座標/拖曳端點走 `measured_pick(need_anchor=True)` → `flowfmt.from_screen`;`_resolve_prev_origin(app, step, dlg, k, anchor)` 絕對座標改 `to_screen`。對話框座標基準的字樣改「絕對座標(相對座標基準點)」。`start_run` 拿掉「絕對座標要先框搜尋範圍」的檢查。
- harness:`place_calibration(scale, anchor)`,預設把第一張擺在搜尋範圍左上角(預設基準點 (0,0),既有測試的數字不變),`run(anchor=…)` 指定基準點;新增 `query_regions()`。
- 測試:`test_coord_space` 重寫(基準點挪動/重框/縮放/紀錄/範圍內找不到就不送),`test_runner_scale` 絕對座標案例改寫。
