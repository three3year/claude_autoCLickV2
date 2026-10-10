# 轉換工具規則與驗收

Type: grilling
Status: resolved
Blocked by: 02

## Question

舊 `.autoclickpack`（format 5）→ 新流程資料夾的一次性轉換：
- 輸入：打包版 `app/dist/AutoClick/profiles/arknights/flows/` 的四份（10/10）。輸出放 `%USERPROFILE%\AutoClick\<流程名>\`（09 已定）。
- 欄位對映：`find_click`→新名；`mode: prev` 丟掉（四份全 prev，遇到 abs 要報錯還是換算成相對？）；`button`／`clicks`
  非預設報錯；`appearLimitMs`、`retryIntervalMs`、`busyAppearMs`、原點 limit 遇到就報錯（統計是 0，但要防）；
  `onNotFound` 缺值時舊預設 skip → 新格式沒寫＝停止，所以舊檔缺值要明寫 `skip`；`confirm` 缺值同理。
- `templates/_meta.json` 的拍攝位置搬進 yaml（`template_pos`）；範本名→檔名的非法字元處理；~~`待重拍_` 前綴照搬~~（02 已定：前綴退場，四份流程無帶前綴的檔、無非法字元）。
- 輸出的鍵：app 記憶體改用 yaml 同名鍵、不再認得舊鍵（[12](12-in-memory-step-model-keys.md) 已定），舊鍵對映全由轉換工具承擔。
- 起點：02 的原型 `../prototypes/flow-yaml/convert_proto.py` 已含欄位對映與往返驗證，四份 617 步逐步一致。
- 旁邊的 `.md`（早_簡中.md 等）：搬進新資料夾成為 `交付報告.md`（09 已定）。
- 驗收：轉完四份在新版 app 開得起來、範本數與步驟數相同、至少一份（晚_簡中）實跑通過；轉換工具跑完刪除
  還是留在 tools/（ADR 0014 說功成身退）。
- 舊格式讀取碼（flowfile 的 zip 讀寫、format 檢查）在哪個階段刪。

Answer：對映表＋驗收清單；進 A 階段 spec。

## Answer

（2026-10-11 grilling，使用者逐題選定後確認「對，寫入」）

### 現況事實（盤點四份 10/10 `.autoclickpack`）

- 四份 617 步：`mode` 全 `prev`、`button` 全 `left`、`clicks` 全 `1`；沒有 `appearLimitMs`、原點 limit、`key` 步驟。
- **缺值為零**：每個會等待的步驟（找圖三態、設了生效確認的點擊／拖曳）都明寫 `onNotFound`／`interval`／`timeout`；
  `interval` 全 0.3、拖曳全 500/500 ms；沒寫 `confirm`／`onBreak` 的地方新舊預設相同（none／continue）。
- 每份有 4 張圖沒被步驟引用，是校準對（主＋備用）的圖，不是孤兒。
- 打包版 profile `config.yaml` 與引擎內建預設只差 `scale_range`（0.6–1.5 對 0.5–2.0）。每輪開頭的校準量測
  查詢不帶預期尺度（`enginehub.query(expected_scale=None)` 整段掃），登錄也用它——不是「幾乎用不到」。
- 流程資料夾另有四份 `.md`（交付報告）與 `_autosave.json`（步驟草稿）。

### 決定

1. **位置與去留**：轉換工具放格式階段 spec 的 `.scratch/<feature>/convert.py`，跟著提交當紀錄；不進 `tools/`、
   不寫正式測試、之後不維護（同 coord-anchor、scale-range 兩次一次性轉換的前例）。起點是原型
   [convert_proto.py](../prototypes/flow-yaml/convert_proto.py)。
2. **讀寫邊界**：自己開 zip 讀 `flow.json` 與 `templates/_meta.json`（不借 app 舊碼）；輸出組成新記憶體模型交 app 的新寫檔函式
   （格式只由 app 一處決定，見[記憶體步驟模型與 yaml 鍵名](12-in-memory-step-model-keys.md)）。所以在格式階段「讀寫換 flow.yaml」
   完成後才跑。**app 的舊格式讀寫（flowfile zip、format 檢查）在格式階段內刪**，不等驗收；備援是搬到 `dist` 外的舊打包版。
3. **範圍只到四份**：只處理四份實際出現的欄位與值；不為 abs 座標、右鍵、連點、`appearLimitMs`、`key` 步驟寫換算或防線。
   `mode`、`button`、`clicks` 直接丟。
4. **預設**：舊檔缺值套新預設（不補舊執行器的預設）。四份缺值為零，所以轉完行為不變；明寫值照搬，等於新預設的由寫檔省略。
5. **引擎參數**：四份各寫 `engine: {scale_range: [0.6, 1.5]}`，校準量測與登錄行為與現在相同。ADR 0015 已修訂。
6. **附帶檔**：舊 `.md` 逐位元複製成 `<流程>\交付報告.md`，內文不改（舊鍵名、`待重拍_` 是當時紀錄）；`_autosave.json` 不轉。
7. **輸出**：`%USERPROFILE%\AutoClick\<流程名>\`（[打包版佈局](09-packaged-layout-and-flow-location.md)）；
   資料夾已存在就報錯停下、不寫任何東西（要重轉先手動刪）。四份範本名無非法檔名字元、無 `待重拍_` 前綴（02 已查）。
8. **自我核對**（每份）：
   - 用 app 的新讀檔函式讀回 `flow.yaml` → 記憶體模型 → 轉換工具裡**獨立寫的反向對映**轉回舊鍵 → 與原檔逐步比
     （去掉 `mode`／`button`／`clicks`；步數相同、每步欄位相同）。
   - `templates/*.png` 與原 zip 逐位元相同、集合相同（含校準對與忙碌指示的圖）。
   - `template_pos`、校準（主對＋備用對；`baseline` 允許 0.05 內的四捨五入差）、忙碌指示、`run`、`scan_region`、`engine` 逐項比。
   - 任一項不過就報錯；全過印每份步數與範本數。
9. **驗收**以[階段切法與順序](01-phases-and-order.md)的格式階段驗收為準：自對全過、新打包版開得起四份、
   使用者早晚班四份各實跑一次全過。取代本票原寫的「至少一份實跑」。
10. **連帶影響**：`.scratch/` 裡約 70 支舊調查腳本 import 舊 flowfile，格式階段後會壞；視為歷史紀錄，不修、不刪。
