# agent 文件結構：格式規範、寫流程 skill、影片 skill 分工

Type: grilling
Status: resolved
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

## Answer

2026-10-11 grilling 定案。原則：flow.yaml 的知識只有一個正本，寫流程的 agent 不必讀開發文件；yaml 裡永遠沒有猜的數字。

**檔案清單與職責**

1. **`docs/flow-format.md`（新，唯一正本）**——寫流程的人（agent）視角：
   - 欄位表：頂層與各步驟的鍵、值、沒寫＝、單位（照 [flow.yaml 具體 schema](02-flow-yaml-schema.md)）；範本命名（平面名稱＝檔名、禁用字元）。
   - **執行語意**（從 `app/CLAUDE.md`「UI 慣例」搬來）：區段巢狀、分岔怎麼選分支、`on_fail` 三種與 break 跳到哪、`on_break` 往外傳、
     找圖三態（`wait_gone` 要先看到）、`confirm` 三種與補做、`busy_check` 的等待規則、原點與 `update_origin`、座標相對誰（原點／座標基準點）。
   - **常見寫法**：定位找圖→相對座標；可選彈窗分岔（1 分支、`if` 找圖 `on_fail: skip`、分支內 `break`）；巢狀重複的跳出後動作；
     `busy_check` 該勾的標準＋四份在用流程勾的 21 步當例子（票 04 規則 6 原說放影片 skill，改放這裡，兩個 skill 共用）；
     固定矩形餘裕；備用校準對。
   - 詞彙引用 `app/CONTEXT.md`，不重定義。
   - **防過期**：一個 pytest 讀這份的欄位表，跟 `flowdefaults` 的預設表、`flowfile` 認得的鍵對照，多、少、預設值不同就紅。
2. **`.claude/skills/edit-flow/`（新，「改流程」）**——描述：「改流程——修改一份既有的 AutoClick 流程資料夾（flow.yaml）。
   使用者要加、刪、搬步驟，包分岔或重複，或改步驟選項時使用。」與 video-to-flow 靠「有沒有影片」分流。**只改既有流程**（新流程走影片轉流程或使用者在 app 建）。步驟：
   1. 先問使用者：app 是否開著這份且有未存改動（有就先存）——app 不偵測外部修改，舊視窗存檔會整份蓋掉。
   2. 讀 `flow.yaml`＋格式規範，改結構與選項（增刪搬步驟、包區段、`on_fail`／`busy_check`／`timeout`／`confirm`、改範本引用）。
   3. **要像素值時**（新的 click 偏移、drag 起訖、`within`），依序：能改成找圖就寫 `find_click`＋新範本名（缺圖＝重截前跑不了，安全）→
      非座標不可、使用者願意錄影 → 轉給 video-to-flow 的補充模式量、插入 → 不錄影 → 不寫那一步，交付清單請使用者在 app 新增。
      `within` 不寫（＝整個搜尋範圍），列為建議。**不寫佔位座標**。
   4. 跑檢查指令，沒有錯誤＝完成。
   5. 交付：改了哪幾步、要在 app 截哪些範本（缺圖清單）、要在 app 新增或框什麼、請在 app **重新讀取**這份流程（別用舊視窗存檔）。
3. **檢查指令（新，例 `tools/flow_check <流程資料夾>`）**：只呼叫 app 既有的檢查——`read_flow`（鍵、型別）、區段交錯（`_flow_error`）、
   相對座標前的原點來源、勾了 `busy_check` 卻沒設忙碌指示、引用但缺圖的範本；不載引擎、不開視窗。edit-flow 的完成條件；video-to-flow 組裝後也跑。
4. **video-to-flow 瘦身**：`SKILL.md` 只留影片特有的（錄影要求、掃描、特效／游標樣本、覆核候選、挑幀取材、驗證幀、組裝、待重拍、交付報告），
   與格式重複的判斷規則（分岔寫法、定位找圖、忙碌檢查標準、比色／挑選語意）改指向格式規範。`plan-format.md`：步驟鍵＝flow.yaml，
   指向規範，只寫差異（位置是影片像素 `at`／`from`／`to`、不寫 `within`／`offset`、證據欄位 `frame`／`box`／`present`／`absent`、捲動軸）。
   加**補充模式**（插進既有流程；規則見新票 [補充流程規則](13-supplement-flow-rules.md)）。
5. **`app/CLAUDE.md`**：執行語意搬走，只留實作指標（哪個函式負責）與坑，加一行指向格式規範與「改 flowfile／flowdefaults 要同步規範（測試會擋）」。
   **在影片轉流程＋agent 文件階段做**（不等最後的文件階段，避免中間幾個階段兩份並存）。根 `CLAUDE.md` 不加指標：寫流程靠 skill 觸發、開發靠 `app/CLAUDE.md`。

**連帶**：「補充流程」從地圖的霧畢業成票 13，併進影片轉流程階段、擋在該階段開工前。

這些進影片轉流程＋agent 文件階段的 spec。

## Comments

- 2026-10-11（[補充流程規則](13-supplement-flow-rules.md) 解票後）：分工修訂——影片特有的知識（第 4 點「只留影片特有」那些）搬進新 skill `video-measure`（不自己觸發，只由入口呼叫）；video-to-flow 只當新流程入口、不帶補充模式；edit-flow 第 3 步「轉給 video-to-flow 的補充模式」改成 edit-flow 自己呼叫 video-measure 量、自己寫回（不備份）。交付報告改成 `交付報告/` 資料夾。
