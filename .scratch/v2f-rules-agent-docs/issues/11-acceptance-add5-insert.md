# 11 — 驗收①：用 edit-flow 把 add5 插回早_簡中

**What to build:** 證明補充這條路真的能用。

1. 早_簡中複製一份。
2. 刪掉手動段：現在的第 124–129 步（找标题_办公室的分岔、拖曳、找标题_回收站、點擊）。
3. 照 edit-flow skill，用 add5.mp4 插回去。
4. 跟手動版比對。
5. 使用者在遊戲實跑。

手動版的做法與紀錄在 `.scratch/scale-range/add_recycle.py` 與 `scale-range/issues/11`。見 spec「驗收」①。

**Blocked by:** 09 — 三個 skill：video-measure、video-to-flow 瘦身、edit-flow

**Status:** ready-for-agent

- [ ] 在複本上做，在用的早_簡中不動
- [ ] 結構相同：步驟種類、區段、範本引用（含 `pick`）跟手動版一致
- [ ] 座標（點擊、拖曳起訖）跟手動版差幾像素內
- [ ] 固定矩形照新規則，只要求包含挑中的框（不跟手框的窄帶比）
- [ ] 拾取檢查全過、檢查指令無錯誤
- [ ] 實跑前照 memory 先確認使用者不在玩遊戲；使用者用複本在遊戲實跑，換班段通過
- [ ] 過程中發現 skill 或工具的問題，回頭修並記在本票
