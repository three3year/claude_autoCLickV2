# flow.yaml 具體 schema（原型）

Type: prototype
Status: open

## Question

flow.yaml 長什麼樣？用 `/prototype`：把打包版裡的 `晚_簡中.autoclickpack` 用一支拋棄式腳本轉成樣本
`flow.yaml`（放在本票旁的 `prototypes/`，不進 app），讓使用者對著真實內容反應。要定的：
- 頂層結構：`steps`、`calibration`（pair、baseline、fallback）、`busy`（找圖目標）、`templates`（拍攝位置）、
  `run`（輪數）、`scan_region`、`engine`（可選覆蓋）的名稱與巢狀。
- 步驟型別名與欄位名：`find`／`click`／`drag`／`wait`、區段標記（`loop`／`end`／`branch`／`or`／`end`？）；
  找圖目標（template、limit rect、pick、color）；生效確認（confirm、confirm_target、timeout、interval、on_not_found）；
  更新原點、忙碌檢查、偏移。
- 預設值哪些省略不寫；數值單位（秒或毫秒）統一。
- 可讀性：一步一行還是展開；中文範本名直接當值（PyYAML `allow_unicode`）；註解要不要。
- 範本名與檔名的對應規則（非法檔名字元、`待重拍_` 前綴）。

產出：一份使用者看過說「就這樣」的樣本 yaml（連結進本票），以及欄位表。10（agent 文件）與 11（轉換工具）等它。
