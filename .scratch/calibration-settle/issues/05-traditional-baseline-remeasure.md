# 05: 繁中基準距離重量

**What to build:** 晚_繁中的`校準對`和早_繁中的`備用校準對`（都是主畫面設定鈕×倉庫，現為 1942.4），改用停穩後量到的基準距離，讓繁中客戶端也不再有視差造成的固定偏差。2026-11-09 晚_繁中量到 ×0.994，就是這個偏差。

做法：
1. 寫一支量測腳本，要求如下：
   - 用票 01 的停穩量測，停點和執行器相同，照流程檔的搜尋範圍。
   - 一次量出主畫面那一對和標題列對。
   - 流程名稱當參數。
2. 請使用者開繁中客戶端停在主畫面，跑一次腳本。
3. 新基準距離 ＝ 主畫面那一對的停穩距離 ÷ 標題列對量到的倍率。只改基準距離，偏移不動。

這張需要使用者在場。開始前先確認使用者是否在玩遊戲；腳本會移動滑鼠，跑之前要先問。

規格：`.scratch/calibration-settle/spec.md`（Implementation Decisions「基準距離」）

**Blocked by:** 01（共用的停穩量測入口）

**Status:** ready-for-human

- [x] 量測腳本放在 `.scratch/calibration-settle/`，畫面上沒有遊戲時，會在移動游標之前就中止。
- [ ] 使用者實跑一次，量到的停穩距離、標題列倍率、算出的新基準距離寫在這張票的 Comments。
- [ ] 兩份 flow.yaml 只有那兩個基準距離改變。

## Comments

- 2026-11-10 量測腳本：`.scratch/calibration-settle/measure_baseline.py`。離線自測是 `selftest_measure_baseline.py`，用假引擎、假截圖、假游標，7 項全過；還沒實跑。
  - 用法（在 repo 根目錄）：`.venv/Scripts/python .scratch/calibration-settle/measure_baseline.py 晚_繁中`，早班換成 `早_繁中`。兩份流程是同一個客戶端、同一個搜尋範圍 `[-8, 0, 1928, 1034]`，跑一份就夠；兩份都跑可以互相對照。
  - 選項：`--delay 秒`（引擎載入後倒數，讓你切到遊戲，預設 5）、`--out 路徑`。
  - 流程：載入引擎 → 倒數 → 不動游標先截一次，主畫面那一對和標題列對四張都要找到，否則中止，游標沒動過 → 停點直接用執行器的 `Runner._avoid_cursor`（搜尋範圍左下角外），用 `calibration.settle` 每 1 秒量兩對，四張圖中心連續兩次各差 ≤1px 定案，最多量 11 次 → 游標移回原位。
  - 輸出：停穩距離、標題列倍率、新基準距離＝停穩距離 ÷ 標題列倍率，以及要改的 flow.yaml 欄位（晚_繁中是 `calibration.baseline`，早_繁中是 `calibration.fallback.baseline`）。結果寫到 `.scratch/calibration-settle/baseline_<流程>.json`；停穩那張截圖存在 `.scratch/calibration-settle/tmp/baseline_<流程>.png`（不進版控）。
  - 哪一對是標題列對：兩張範本名都以「標題列」或「标题栏」開頭的那一對；另一對就是主畫面那一對。
