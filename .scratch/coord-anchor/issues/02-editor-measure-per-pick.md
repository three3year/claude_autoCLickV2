# 02 — 編輯器每次拾取當下量校準

**What to build:** 編輯器每次`拾取`時,用拾取的那張截圖在`搜尋範圍`內找`校準對`,當下得出`座標基準點`與`畫面倍率`;不再有跨操作保存的編輯器倍率。這張先讓既有用到倍率的拾取(截範本縮放、相對座標、以原點為基準的限定範圍、預設原點推算、比對測試)改用當下量到的倍率。量不到(找不到、兩張重疊)＝該次操作不存並提示重框;流程沒有校準對時,需要座標基準點的拾取擋下並提示先設校準對(只依原點的拾取照常)。「校準」鈕改成只量測並顯示目前倍率,不影響存下的值。

規格:`.scratch/coord-anchor/spec.md`(編輯器、使用者故事 14–20、24、接縫二)。ADR 0012 第 4 點、修正 ADR 0009 第 5 點。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 在倍率 ≠1 的假截圖上截範本、拾取相對座標,存下的值已除以當下量到的倍率,不必先按校準。
- [x] 拾取那張截圖裡找不到校準對時不存、提示重框搜尋範圍。
- [x] 沒有校準對的流程:需要座標基準點的拾取擋下並提示;相對座標、以原點為基準的限定範圍可照常拾取。
- [x] 「校準」鈕按了只顯示倍率,步驟資料不變。
- [x] 量測與執行開頭校準共用同一個量測函式,且只在搜尋範圍內查。
- [x] 編輯器對話框測試(接縫二)涵蓋以上,在隱藏桌面跑綠。

## Comments

**2026-10-09(實作)**

- `ui_dialogs.measured_pick(app, parent, body, need_anchor, hide, title)`:清場前 `App.calibration_ready`(引擎 gate、校準對範本在不在)→ 清場中 `App.calibrate_frame()`(依搜尋範圍截一張、`calibration.calibrate`)→ `body(anchor, k, frame)` 做拾取 → 清場後提示。量測與執行開頭共用 `calibration.calibrate`(`measure` 多了 `origin`,中心回螢幕座標;`Measurement.anchor`＝第一張中心)。
- 走它的入口:座標點擊/拖曳拾取、限定範圍框選、指定點、固定矩形、`App.pick_region_measured`(主視窗截圖框選與選範本對話框「截圖新增」共用)、`show_match_test`(直接用校準那張截圖)。`App.editor_scale`、`flow_scale_image`、`_region_origin`、`_region_base` 移除。
- 沒有校準對:need_anchor 的拾取彈 `NO_PAIR_MSG`;其餘 anchor＝None、k＝1。量不到:不存,提示「拾取當下…找不到校準圖…請重新框選搜尋範圍」。
- 「校準」鈕(`calibrate_now`)只量、顯示 `校準 ×k` 與基準點、不動任何值;切流程回到「校準」。
- 測試:`test_editor_scale`(重寫)、`test_calibration_ui`(重寫)。
