# flow.yaml 具體 schema（原型）

Type: prototype
Status: resolved

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

## Answer

2026-10-10 使用者對著樣本定案（「就這樣」）。

- **定案樣本**：[A_巢狀_一步一行.yaml](../prototypes/flow-yaml/out/A_巢狀_一步一行.yaml)（晚_簡中）。
  比較過、沒選的寫法：[B 平面標記](../prototypes/flow-yaml/out/B_平面標記_一步一行.yaml)（標記要自己配對，agent 改錯易交錯）、
  [C 巢狀展開](../prototypes/flow-yaml/out/C_巢狀_展開.yaml)（61 步 209 行，一屏看不到幾步）。
- **原型腳本**：[convert_proto.py](../prototypes/flow-yaml/convert_proto.py)——含 yaml → 舊步驟語意的往返驗證；
  四份在用流程（617 步）全部逐步一致，輸出在 [out_all/](../prototypes/flow-yaml/out_all/)。轉換工具（11）可直接拿它當起點。
  18.5KB 的 flow.json → 約 4.8KB。

### 排版

區段**巢狀**（不是平面標記），步驟**一步一行**（flow-style mapping）。行尾 `# N` 是存檔程式產生的步驟編號
（＝app 清單與執行紀錄的編號，區段標記也算一號）；app 存檔會重寫檔案，手寫註解不保留。
app 內部讀寫時轉成平面清單（記憶體模型照舊是平面標記，見下方「留給後續」）。

### 頂層

| 鍵 | 內容 | 沒寫＝ |
|---|---|---|
| `format` | `1` | 必填（日後改格式時讀檔能明確拒絕／轉換） |
| `run` | 輪數 N，或 `forever` | 1 |
| `scan_region` | `[x, y, w, h]` 螢幕座標 | 全螢幕 |
| `calibration` | `pair: [名, 名]`、`baseline`（四捨五入到小數 1 位）、`fallback: {pair, baseline, offset}` | 沒有校準 |
| `busy` | `{template: 名, within: [x, y, w, h]}` | 沒有忙碌指示 |
| `template_pos` | `名: [x, y]`（只列有拍攝位置的範本；範本清單本身＝`templates/`） | — |
| `engine` | 鍵名同引擎 `default_config.yaml` | 內建預設 |
| `steps` | 步驟清單 | — |

退場的頂層欄位：`flowFormat`（→ `format`）、`coordSpace`（座標恆相對座標基準點）、`avoidHover`（一律開）、`runMode`／`runCount`（→ `run`）。

### 步驟（開頭的鍵＝這步做什麼）

| 步驟 | 可帶欄位 |
|---|---|
| `find_click: 名`（找到就點）、`find: 名`（只找不點）、`wait_gone: 名`（等它消失） | `within: [x, y, w, h]`（固定矩形，相對座標基準點）、`pick: {top: N}｜{left: N}｜{near: [x, y]}`（沒寫＝分數最高）、`color: true`、`offset: [x, y]` |
| `click: [x, y]`（相對原點；唯一的座標模式） | — |
| `drag: [x, y]` ＋ `to: [x, y]`（相對原點） | `duration`、`hold`（秒，預設皆 0.5） |
| `wait: 秒` | — |
| 共通（找圖三態、點擊、拖曳） | `confirm: gone｜next｜{appear: 名, within…, pick…, color…}`（沒寫＝none）、`timeout`（10）、`interval`（0.3）、`on_fail: skip｜break`（沒寫＝stop；找不到與生效確認逾時共用）、`busy_check: true`、`update_origin: false` |
| `repeat: N` ＋ `steps: [...]` | `on_break: break`（沒寫＝continue） |
| `branch: [- if: {找圖步驟}, then: [...]]` | `on_break: break`；`if` 必須是找圖三態之一 |

- 時間一律**秒**（`wait: 0.5`）；輪詢間隔預設由 0.5 改 **0.3**（四份流程 337 個找圖全是 0.3）。
- `timeout`／`interval`／`on_fail` 只在有等待的步驟上有意義（找圖三態；點擊／拖曳要設了 `confirm` 才有）。
- 中文範本名直接當值（`allow_unicode`）。

### 範本名與檔名

- `templates/<名>.png`，檔名即範本名。存檔（含重新命名）擋下含 `\ / : * ? " < > |`、開頭或結尾空白、結尾句點的名字。
  四份流程 220 張範本無一違規。
- **`待重拍_` 前綴退場**：影片轉流程的待重拍清單只寫在交付報告，flow.yaml 與檔名都不帶標記；使用者在 app 重截同名圖即可。
  四份在用流程目前沒有帶前綴的檔。

### 與既有決策的差異

- ADR 0014 決策 2 的例子原寫 `find_click` → `find`；改為「開頭的鍵即動作」三個鍵名，已更新 ADR 0014。

### 留給後續

- app 記憶體裡的步驟模型要不要跟著改用 yaml 鍵名（或只在讀寫層轉換）——開票「記憶體步驟模型與 yaml 鍵名」。
