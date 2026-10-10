# 08 — App 開檔、存檔改用流程資料夾；刪舊存檔、工作區、步驟草稿

**What to build:** 使用者在 app 用一般開檔視窗選 `flow.yaml`，開它所在的流程資料夾；按存檔把流程寫回同一個資料夾：`flow.yaml` 整份重寫、`.cache/` 裡的未存檔截圖搬進 `templates/`、`templates/` 只留被引用的範本（步驟的找圖目標與確認圖＋校準對＋備用校準對＋忙碌指示）、`template_pos` 只留被引用的。截圖新增與重截先放 `.cache/`，重開 app 或讀取流程時清掉；登錄產物放 `.cache/`。範本改名連動步驟、確認圖、校準對、忙碌指示、拍攝位置。引擎收的範本清單由 app 組（`templates/`＋未存檔截圖，扣掉已刪的）。缺圖照樣開，彈窗加執行紀錄列出缺哪幾張。舊 zip 讀寫、format 檢查、03–05 的過渡翻譯層、工作區、步驟草稿全部刪掉（寬幅重構的收尾）。見 spec「存檔語意」「範本與快取」。

**Blocked by:** 07

**Status:** resolved

- [x] 開檔篩選 `flow.yaml`；讀檔報錯時不開啟，目前的流程不動
- [x] 存檔只寫引用集合；刪掉引用它的步驟再存檔，那張圖離開 `templates/`；校準對與忙碌指示的圖保留
- [x] 未存檔截圖存檔前不在 `templates/`；重開 app 或讀取流程時被清掉
- [x] 範本改名連動所有引用，存檔後檔名跟著改
- [x] 被引用卻缺圖：照樣開，彈窗與執行紀錄列出缺圖
- [x] 舊存檔模組的 zip 讀寫、工作區、步驟草稿與它們的測試刪掉；全 repo 沒有程式碼讀寫舊鍵
- [x] App 存讀檔測試（子類跳過重量級建構＋對話框樁＋假引擎）改寫成流程資料夾版本；全部測試綠
- [x] 這張還不處理未存檔提示與新流程第一次存檔（09）、profile（10）；過渡期新流程存檔可以先用簡單的選資料夾

## Comments

- 2026-10-11（agent）：與 10 一起做（App 的流程/範本/引擎參數三者拆不開）。`flowfile.FlowTemplates`＝本流程的範本：`templates/` 的圖＋`.cache/shots/` 的未存檔截圖＋`.cache/registered/` 登錄產物；新流程用本機狀態資料夾的「未存檔」快取。存檔 `FlowTemplates.save()`：被引用的截圖搬進 `templates/`、沒被引用的搬回 `shots/`（這次編輯期間還能用，重開或讀別的流程時清掉）。開檔篩選 `flow.yaml`、從 `%USERPROFILE%\AutoClick` 開。舊 zip/工作區/步驟草稿/`coordSpace` 標記全刪；`flowfmt.remap_flow` 改讀 `busy`。範本改名改成擋下不能當檔名的名字（不再靜靜清成底線）。新流程第一次存檔已照 09 的規則做（選位置＋名字、同名資料夾拒絕、未存檔快取搬進 `.cache/`）；未存檔提示留給 09。測試：`test_flowfile.py`（FlowTemplates）、`test_flow_open_save.py`（App 開存檔）。
