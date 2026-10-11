# 15 — 補充的錄影要求與計畫格式文件

**What to build:** agent 照 edit-flow／video-measure 做補充時，不再一律要求使用者「從插入點的畫面開始錄」：先問「插入段從影片量的每個位置，流程跑到那裡時會不會在同一個地方」，固定介面不限開錄位置、只差在清單捲到哪就寫 `align`、其他落差依序退路（讓位置不寫死 → 請使用者從插入點畫面重錄），不自己推算位移、新落差回報使用者。見 spec「三個 skill 與計畫格式文件」裡的「補充的錄影要求」。

**Blocked by:** 14 — 補充對齊：第一次捲動拖曳吸收位移

**Status:** done

- [x] video-measure 第 1 節的補充錄影要求改成判斷問題＋三種情況＋退路（照 spec），刪掉「從插入點畫面開始錄、不要自己推算位移」那段；校準對與影片倍率的要求不變
- [x] video-measure 寫明 `align` 怎麼挑：插入點前用固定矩形定位過、影片第一次捲動前停住時看得到的圖；`at` 寫影片裡的大約位置；`step` 照 flow.yaml 行尾編號
- [x] edit-flow 第 3 步「使用者願意錄一段影片」改指向新的錄影要求，不再一律請使用者先跑到插入點、F12 停下
- [x] edit-flow 交付清單包含「遇到工具沒涵蓋的落差」的回報
- [x] `plan-format.md` 補上 `align` 一列（鍵、何時必填、`null` 的意思），範例改成帶 `align`
- [x] 照 `writing-for-agents` 寫；計畫格式文件對照測試（若有）照過

## Comments

- 2026-10-11（agent）：video-measure 第 1 節改成判斷問題＋三種情況＋退路、完成條件加「已判斷屬哪一種」；第 6 節寫 `align` 的挑法；edit-flow 第 3 步指回第 1 節、錯誤清單加 align、交付清單加對齊位移與「工具沒涵蓋的落差」；plan-format.md 加 `align` 一列、補充範例帶 `align`（step 121），`test_plan_format_doc.py` 斷言它讀得進來。
