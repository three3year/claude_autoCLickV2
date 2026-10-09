# 05 — 範本拍攝位置相對基準點,影片轉流程產出新格式

**What to build:** 範本的拍攝位置(截圖當下的中心)改存相對`座標基準點`的偏移(流程尺度)。截範本時用當下基準點記錄;比對測試找到圖時補記也用當下基準點;`預設原點` ◎ 退用拍攝位置時,用當下基準點換回螢幕。視窗挪過之後 ◎ 仍標在圖實際的位置。`影片轉流程`工具寫出的存檔直接是新版本:拍攝位置相對影片裡量到的基準點(影片尺度＝流程尺度)。

規格:`.scratch/coord-anchor/spec.md`(座標換算、影片轉流程工具、使用者故事 16、21、22、42)。

**Blocked by:** 03 — 絕對座標以座標基準點為準

**Status:** done

- [x] 截範本後記下的拍攝位置＝(截圖中心 − 當下基準點) ÷ 當下倍率。
- [x] 基準點換了位置的假截圖上,◎ 退用拍攝位置時標在換算後的正確螢幕位置。
- [x] 比對測試補記的拍攝位置是相對基準點。
- [x] 影片轉流程工具產出的存檔是新版本與新座標空間標記,app 開得起來;工具既有測試綠。
- [x] 接縫二綠。

## Comments

**2026-10-09(實作)**

- 拍攝位置:`ui_dialogs.template_pos_from_shot(r, anchor, k)`(沒有基準點＝不記);`save_captured(r, anchor, k)`、選範本對話框 `shoot`、比對測試補記(`from_screen`)都走它;`Workspace.pos` 語意改為相對基準點、流程尺度。
- ◎ 退用:`_template_screen_pos(app, name, anchor, k)` → `to_screen`;`test_editor_scale::test_預設原點退用拍攝位置_依當下基準點換到螢幕`。
- 影片轉流程:`assemble._measure_pair` 多回基準點(影片像素);pos＝取材框中心 − 基準點(沒有校準對就不寫 pos);`coordSpace: anchor`。`plan.py` 的 `near` 只剩 `at`、`limit` 只剩 `origin`、`busyTarget` 不寫 limit;`origin._target` 只換算以原點為基準的。`vtf_synth.make_profile` 草稿改經 `flowfile.write_draft`。SKILL.md 三處字句更新。
- 測試:tools/tests 140 passed(含新增「九宮格與以搜尋範圍為基準的指定點已退場」)。
