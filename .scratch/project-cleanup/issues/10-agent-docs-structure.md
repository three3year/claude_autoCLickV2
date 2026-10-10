# agent 文件結構：格式規範、寫流程 skill、影片 skill 分工

Type: grilling
Status: open
Blocked by: 02

## Question

flow.yaml schema 定了之後，給 agent 的文件怎麼擺（用 `/writing-for-agents`）：
- 格式規範一份：放哪（`docs/flow-format.md`？`.claude/skills/<新 skill>/format.md`？）；內容：欄位表、預設、單位、
  範本命名、常見模式（定位找圖→相對座標、可選彈窗分岔＋skip＋break、巢狀重複的跳出後動作、忙碌檢查該勾哪裡、
  固定矩形餘裕、備用校準對）。
- 新 skill「手寫／修改流程」：觸發描述（使用者說「幫我加一步」「改這份流程」時）、步驟（讀 yaml、改、用引擎自我驗證？
  用拾取檢查？）、交付（改了哪些步驟、哪些範本要重截）。
- 影片轉流程 skill：刪掉與格式重複的部分，只留影片特有的（點擊特效、游標樣本、影格挑選、交付報告）；引用格式規範。
- app/CLAUDE.md 要留什麼給開發 agent（執行語意、區段規則）與格式規範怎麼分工，避免兩處重複。
- 範本圖怎麼交給 agent：使用者截圖放進 templates/ 再在 yaml 引用；agent 不能自己截。

Answer：檔案清單＋各自職責＋交叉引用；進 D 階段 spec。
