# 09 — 三個 skill：video-measure、video-to-flow 瘦身、edit-flow

**What to build:** agent 有三個分工清楚的 skill：

- **分流**：
  - 使用者交影片要新流程 → video-to-flow。
  - 要改既有流程（不論有沒有影片）→ edit-flow。
  - 兩者要量影片時都呼叫 video-measure；video-measure 不自己觸發。
- **知識只放一處**：影片特有的知識只在 video-measure；格式與執行語意一律指向 `docs/flow-format.md`。
- **edit-flow 的做法**：
  - 先問 app 是否開著這份且有未存改動，再直接改 `flow.yaml`。
  - 要像素值時，依序：改成找圖 → 錄影交給 video-measure＋`insert` → 都不行就列進待辦；永不寫猜的座標。
  - 檢查指令無錯後，用 `--normalize` 收尾。
  - 交付：改了什麼、要截哪些範本、要在 app 做什麼，並提醒在 app 重新讀取。
- **`plan-format.md`**：改成新鍵，只寫跟格式規範的差異（含 `insert` 的欄位），搬到 video-measure 底下。

見 spec「三個 skill 與計畫格式文件」、10 第 2–4 點與其 Comments。

**Blocked by:** 01 — 結構檢查抽出＋檢查指令；02 — 格式規範＋對照測試；08 — 補充的影片倍率

**Status:** done

- [x] 寫 skill 前先用 `writing-for-agents` skill
- [x] video-measure：錄影要求、掃描、特效／游標樣本（附件跟著搬）、覆核候選、挑幀取材（含捲動軸怎麼宣告）、驗證幀、拾取檢查、待重拍；description 寫明只由兩個入口呼叫
- [x] video-to-flow：只剩新流程入口（前置檢查 → video-measure → 寫計畫含校準對 → `assemble` → 讀驗證結果能修就修 → 交付），不帶補充
- [x] edit-flow：description 照 10 第 2 點；五步流程照 spec；明寫「不寫佔位座標」「`within` 不寫，列為建議」
- [x] 與格式規範重複的判斷規則（分岔寫法、定位找圖、忙碌檢查標準、比色、挑選語意）都改成指向規範；三個 skill 裡沒有第二份
- [x] `plan-format.md` 跟程式一致：照文件寫一份最小計畫，`assemble` 與 `insert` 都跑得過

## Comments

- 2026-10-11（agent）：先載了 `writing-for-agents`。`video-measure`（新，model-invoked——兩個入口要能呼叫它；description 寫明只在 video-to-flow 或 edit-flow 指示時用）：錄影要求（含補充的影片倍率與 `scale_image`）、掃描、覆核候選、把點擊寫成步驟（判斷規則指向 flow-format.md）、挑幀取材（含捲動軸）、寫計畫，另有「讀驗證結果」一節給兩個入口共用。特效樣本、游標圖、`learn-effect-sample.md`、`plan-format.md` 都搬到 `video-measure/`。`video-to-flow` 瘦身成新流程入口六步（前置 → video-measure → 校準對與流程設定 → assemble → 讀驗證結果 → 交付）。`edit-flow` 照 spec 五步，明寫不寫猜的座標、`within` 不寫列為建議、`--normalize` 收尾。`plan-format.md` 改寫成只寫差異（含 `insert` 欄位），`tools/tests/test_plan_format_doc.py` 把文件裡的兩個範例計畫丟給 `plan.load` 讀，文件寫錯會紅；`assemble` 與 `insert` 的實際行為由合成影片測試跑。
