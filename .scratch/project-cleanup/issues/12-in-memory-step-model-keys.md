# 記憶體步驟模型與 yaml 鍵名

Type: grilling
Status: resolved

## Question

flow.yaml 定了新鍵名與巢狀區段（[flow.yaml 具體 schema](02-flow-yaml-schema.md)），但 app 記憶體裡的步驟仍是舊模型：
平面標記（`loop_start`／`branch_or`…）、`type: find_click`＋`action`、`onNotFound`、`limit: {kind: rect…}`、毫秒。
執行器、編輯器、找圖目標（`findtarget`）、影片轉流程工具、拾取檢查都讀這套鍵。要定的：

- 記憶體模型**跟著改用 yaml 鍵名**（一套名字，改動面大：執行器、編輯器、findtarget、tools、約 600 個測試的資料），
  還是**只在讀寫層轉換**（改動面小，但兩套名字並存，agent 讀程式碼與讀 yaml 對不上）？或折衷（鍵名改、平面標記留）？
- 區段在記憶體裡維持平面標記（app 清單一列一項、執行紀錄編號）是否不動。
- 影片轉流程工具（tools/）的中間產物與輸出直接寫 yaml 結構，還是經 app 的寫檔函式。
- `app/CONTEXT.md` 的「code:」標注跟哪一套名字。

Answer：選定的模型與轉換邊界；進格式階段 spec。

## Answer

2026-10-11 使用者逐題選定後確認（「對，寫入」）。取捨與拒絕的替代方案已補進 ADR 0014 決策 7。

### 現況事實（盤點）

- 步驟全是純 dict，沒有 schema、沒有統一的正規化；預設值散在各讀取點的 `.get(鍵, 預設)` 且不一致：
  找圖缺 `onNotFound`＝skip（runner.py:1087）、點擊／拖曳缺＝stop（runner.py:782）；拖曳 `ms` runner 預設 300、
  `add_step` 預設 500；tools 另有 `video_to_flow/defaults.py`。
- 讀舊鍵的地方：runner 約 90 處、app.py（清單、摘要、結構檢查）約 93 處、ui_dialogs（編輯器，tk 變數也用同名）約 200 處、
  findtarget 約 55、flowfmt 約 11、pickcheck 約 10（只讀找圖目標）、tools/video_to_flow/plan.py 約 143（白名單）。
- 測試 743 個（app 626、tools 117）；41 檔建步驟 dict。共用 builder `app/tests/harness.py:44-95` 用 `**kw` 透傳，
  舊鍵名大量以 kwarg 出現在呼叫端（`onNotFound=` 62 次、`confirmTarget` 60 次…）。
- tools 已經經 `flowfile.write` 存檔（assemble.py:229），但 data dict 自己組、用舊鍵。

### 決定

1. **鍵名改、形狀留。** 記憶體步驟仍是 dict＋平面標記；欄位名、值、單位一律跟 flow.yaml 同（snake_case、秒）。
   另加 `type`＝yaml 開頭的鍵，開頭鍵的值就放在同名欄位：

   | type | 記憶體例子 |
   |---|---|
   | `find_click`／`find`／`wait_gone` | `{type: find_click, target: {...}, confirm: appear, confirm_target: {...}, on_fail: skip, timeout, interval, offset: [x, y], busy_check, update_origin}` |
   | `click` | `{type: click, click: [x, y], confirm, ...}` |
   | `drag` | `{type: drag, drag: [x, y], to: [x, y], duration, hold, ...}` |
   | `wait` | `{type: wait, wait: 0.5}` |
   | `repeat_start`／`repeat_end` | `{type: repeat_start, repeat: 3}`、`{type: repeat_end, on_break: break}` |
   | `branch_start`／`branch_or`／`branch_end` | `branch_end` 帶 `on_break` |

   退場：`action`（併進 type）、`key` 步驟、`loop_*` 名稱（→ `repeat_*`）、`mode`、`button`、`clicks`、`appearLimitMs`、
   `limit.kind`、所有毫秒欄位。
2. **找圖目標留子 dict、內容跟 yaml 同值**：`target`／`confirm_target` ＝ `{template, within: [x, y, w, h], pick: {top: N}｜{left: N}｜{near: [x, y]}, color: true}`。
   `confirm` 仍是 `none`／`gone`／`next`／`appear` 字串。findtarget、拾取檢查仍吃這一個型別。
3. **區段維持平面標記**；`on_break` 掛在結尾標記。讀寫層只做三種形狀轉換：巢狀↔平面、開頭鍵↔`type`、
   yaml 步驟層的 `within`／`pick`／`color`↔`target` 子 dict（確認圖：`confirm: {appear: 名, …}`↔`confirm: appear`＋`confirm_target`）。
   原型 `nest()`／`flatten()` 是起點。
4. **流程層同一規則**：記憶體流程 dict＝yaml 頭部（`run`、`scan_region`、`calibration`、`busy`、`template_pos`、`engine`）；
   `avoidHover`、`coordSpace`、`flowFormat`、`retryIntervalMs`、`busyAppearMs` 刪；拍攝位置不再另外傳（`_meta.json` 退場）。
5. **一張預設表**：app 一個模組放「沒寫＝」表（＝02 欄位表），讀檔與新增步驟時補齊成完整步驟、存檔時等於預設的不寫；
   執行器、編輯器、tools 不自帶預設，`tools/video_to_flow/defaults.py` 收掉。舊的不一致預設隨之消失。
6. **tools 經 app 產出**：轉換計畫的鍵＝yaml 鍵（04），所以計畫的步驟直接用 app 的 yaml→記憶體解析，組好的流程交 app 的寫檔函式
   存成 flow.yaml；格式只由 app 一處決定。
7. **格式階段內順序與回歸網**：刪執行器路徑（連同那些路徑的測試）→ 機械改名（含 harness builder 與編輯器 tk 變數名，
   不改行為；剩下的測試全綠就是網）→ 預設表統一（行為變更，單獨一步、補測試）→ 讀寫換 flow.yaml（02 的 617 步往返驗證當網）。
8. **文件**：`app/CONTEXT.md` 的 code: 標注已改新名（2026-10-11）。

### 給後續票

- [轉換工具規則與驗收](11-converter-rules-and-acceptance.md)：舊 `.autoclickpack` 的舊鍵 → 新記憶體模型／flow.yaml 的對映
  由轉換工具獨自承擔（app 不再認得舊鍵）；可以「舊 → yaml → 用 app 讀回驗證」。
