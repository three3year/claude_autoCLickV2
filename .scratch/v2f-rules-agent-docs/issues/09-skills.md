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

**Status:** ready-for-agent

- [ ] 寫 skill 前先用 `writing-for-agents` skill
- [ ] video-measure：錄影要求、掃描、特效／游標樣本（附件跟著搬）、覆核候選、挑幀取材（含捲動軸怎麼宣告）、驗證幀、拾取檢查、待重拍；description 寫明只由兩個入口呼叫
- [ ] video-to-flow：只剩新流程入口（前置檢查 → video-measure → 寫計畫含校準對 → `assemble` → 讀驗證結果能修就修 → 交付），不帶補充
- [ ] edit-flow：description 照 10 第 2 點；五步流程照 spec；明寫「不寫佔位座標」「`within` 不寫，列為建議」
- [ ] 與格式規範重複的判斷規則（分岔寫法、定位找圖、忙碌檢查標準、比色、挑選語意）都改成指向規範；三個 skill 裡沒有第二份
- [ ] `plan-format.md` 跟程式一致：照文件寫一份最小計畫，`assemble` 與 `insert` 都跑得過
