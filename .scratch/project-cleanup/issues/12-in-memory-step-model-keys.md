# 記憶體步驟模型與 yaml 鍵名

Type: grilling
Status: open

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
