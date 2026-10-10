# 轉換工具規則與驗收

Type: grilling
Status: open
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
