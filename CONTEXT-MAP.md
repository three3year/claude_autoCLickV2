# Context Map

本 repo 有兩個 bounded context（ADR 0002 起）。跨 context 討論時先確認詞彙屬於哪一邊。

| Context | 範圍 | 詞彙表 | 程式碼 |
|---|---|---|---|
| 主體偵測引擎（Subject Detection） | 遊戲無關的偵測核心：登錄呼叫端交來的模板清單、兩階段查詢（粗篩＋深度驗證） | 根目錄 `CONTEXT.md` | `src/subject_detection/` |
| 自動化應用（AutoClick） | Tkinter 桌面應用：流程編輯、截圖建範本、找圖點擊、F12 急停 | `app/CONTEXT.md` | `app/`（其自動化子套件為 `app/automation/`） |

## 詞彙界線（同名或近名、意義不同）

- **「引擎」**：在本 repo 專指主體偵測引擎（`src/subject_detection`）。
  app 的自動化子套件舊名 engine，已改名 `automation`，不要再叫它引擎。
- **引擎「模板（Template）」 vs app「範本（template）」**：
  引擎的模板是登錄進模板庫、經預處理的比對單位；app 的範本是使用者截圖、
  **住在某一份流程存檔裡**的一張圖（正式名稱＝平面名稱，在一份流程內唯一；
  ADR 0006）。app 的範本就是流程資料夾裡 `templates/` 的一張 PNG（ADR 0014）
  ——範本庫、profile 都已退場。執行與編輯時 app 把 `templates/` 掃成
  `範本清單`交給引擎登錄成模板；引擎自己不掃目錄、不知道存檔格式。
  兩詞分屬兩個 context，文件與 UI 不混用。
- **引擎「搜尋區域（Search Region）」 vs app「搜尋範圍（scan_region）」**：
  搜尋區域＝單次查詢輸入的裁切影像；搜尋範圍＝使用者設定的螢幕矩形
  （只決定在哪裡截圖找圖；app 的座標基準是`座標基準點`，不是它）。執行期關係：app 依搜尋範圍截圖，
  截下來的影像才是引擎的搜尋區域。

## 依賴方向

自動化應用 → 主體偵測引擎（單向）。引擎不知道 app 存在。
**辨識**只有一條路：runner 建構時注入的偵測器
（`query(範本名, 搜尋區域, color_check) → QueryResult`，回報所有匹配，app 端實作為 `enginehub.EngineHub`；
見 ADR 0002），不允許第二條比對路徑。
此外 app 也使用引擎的公開 API 做範本登錄與顯示：`Engine.load_templates`
（收`範本清單`＋引擎參數＋登錄產物位置）、`Engine.register`（單張登錄）、
`Library.templates`／`Artifacts.ref_bgr`（面板清單與預覽）、
`library.load_config`（引擎內建預設＋流程的`引擎參數覆蓋`合併，ADR 0015）、`QueryResult.debug`
（比對測試的除錯分數，格式不承諾穩定）。**掃目錄是呼叫端的事**：引擎沒有
「給我一個 profile 目錄我自己找圖」這條入口（ADR 0006）。
`tools/video_to_flow`（`影片轉流程`工具，不進 app、不進打包版）也直接用同一組
公開 API（`make_library`＋`Engine.register`／`query`）在影片影格上自我驗證範本：
它不執行流程、沒有 runner，不是 app 的第二條辨識路徑。
