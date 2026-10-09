# 06 — 九宮格退場,最接近指定點只以原點

**What to build:** `限定範圍`剩三選一(不限定/以原點為基準的矩形/固定矩形),九宮格從執行、UI、寫入全部拿掉。`挑選規則`「最接近指定點」只剩相對`原點`的偏移(偏移 (0,0)＝最接近原點),拿掉「以搜尋範圍左上角」的基準;拾取指定點時點的位置減原點、除以當下倍率再存;沒有原點＝該步驟無法執行並提示,同`相對座標`。舊檔已由 01 拒絕開啟,不需要讀檔遷移。

規格:`.scratch/coord-anchor/spec.md`(九宮格與指定點的決定、使用者故事 12、13、26、27)。

**Blocked by:** 01 — 存檔新格式、舊格式拒絕開啟

**Status:** done

- [x] 限定範圍下拉沒有九宮格;執行器與存檔不再認得九宮格。
- [x] 最接近指定點只有 X/Y 偏移,沒有基準下拉;執行時以原點+偏移×倍率挑最近的匹配。
- [x] 沒有原點時用到最接近指定點的步驟無法執行、有提示。
- [x] 相關 runner 與對話框測試改寫;接縫一、二綠。

## Comments

**2026-10-09(實作)**

- `findtarget`:`limit_rect` 不認 grid、`make_target` 不寫 grid、`_pick` near 只用原點(`flowfmt.to_screen(偏移, origin, scale)`)、`needs_origin` 含所有 near、`pick_text` → `near(+x,+y)`、`summary` → 「最接近原點 (+x,+y)」。
- UI:`LIMIT_ZH` 三選一、九宮格勾選列移除;指定點只剩「相對原點 X/Y」與點選,`BASE_ZH` 移除;`edit_busy_indicator` 不再預設九宮格 8,提示改「請改用固定矩形或不限定」。
- 執行器:沒有原點時 near 步驟跳過並提示(既有的 `needs_origin` 路徑,`test_runner_findtarget::test_以原點為基準卻沒有原點_步驟無法執行而跳過`)。
- 測試:`test_findtarget`(指定點與搜尋範圍框法無關、偏移 0＝最接近原點)、`test_editor_scale::test_指定點沒有基準下拉_限定範圍沒有九宮格`、`test_runner_busy_*` 的忙碌指示改固定矩形、`test_retry_settings`。
