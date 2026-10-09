# 04 — 固定矩形以座標基準點為準

**What to build:** `固定矩形`改存相對`座標基準點`的偏移與寬高(流程尺度、整數像素),不再是搜尋範圍的比例。執行時換到螢幕再裁到搜尋範圍內(裁的行為不變);編輯器框選時用當下截圖的基準點與倍率換算再存;比對測試與固定矩形的預覽也用當下基準點。找圖步驟、`確認圖`、`忙碌指示`都是`找圖目標`,走同一條路。

規格:`.scratch/coord-anchor/spec.md`(座標換算、使用者故事 1–4、9、11、14、23、25)。

**Blocked by:** 03 — 絕對座標以座標基準點為準

**Status:** done

- [x] harness:同一份步驟,校準對擺在不同位置/倍率、搜尋範圍框得鬆緊不同,固定矩形查詢的裁切矩形跟著基準點走。
- [x] 固定矩形一部分落在搜尋範圍外時照裁、照找。
- [x] 編輯器框固定矩形存下相對基準點的偏移;倍率 ≠1 時已換回流程尺度。
- [x] 比對測試套用固定矩形的結果與執行一致;預覽畫在基準點換算後的位置。
- [x] 確認圖、忙碌指示的固定矩形同樣生效。
- [x] test_fixed_rect_ui 與相關 runner 測試改寫成新語意;接縫一、二綠。

## Comments

**2026-10-09(實作)**

- `findtarget.limit_rect(..., anchor)`:`rect` 改 `flowfmt.rect_to_screen(lim, anchor, scale)` 再裁到搜尋範圍;欄位要整數、寬高 >0;`needs_anchor`、`Found.reason == "anchor"`(沒有基準點時不查)。`fixed_rect_from_screen(box, anchor, k)` 取代 `ratio_rect_from_screen`(不裁,執行時才裁)。`limit_text` 顯示「固定矩形 (+x,+y) w×h」。
- 執行器與編輯器都傳 anchor;確認圖、忙碌指示同一條路(`test_coord_space::test_確認圖與忙碌指示的固定矩形同樣以基準點為準`)。比對測試把限定矩形(藍框)與 ⊕ 基準點畫在預覽上。
- 編輯器「在畫面上框選」沒有校準對時停用並說明;量不到不存。
- 測試:`test_findtarget` 固定矩形段重寫、`test_runner_findtarget`/`test_runner_runlog` 的九宮格與比例案例改成相對基準點、`test_fixed_rect_ui` 重寫。
