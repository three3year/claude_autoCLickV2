# Context Map

本 repo 有兩個 bounded context（ADR 0002 起）。跨 context 討論時先確認詞彙屬於哪一邊。

| Context | 範圍 | 詞彙表 | 程式碼 |
|---|---|---|---|
| 主體偵測引擎（Subject Detection） | 遊戲無關的偵測核心：登錄模板庫、兩階段查詢（粗篩＋深度驗證） | 根目錄 `CONTEXT.md` | `src/subject_detection/` |
| 自動化應用（AutoClick） | Tkinter 桌面應用：流程編輯、截圖建範本、找圖點擊、F12 急停 | `app/CONTEXT.md` | `app/`（其自動化子套件為 `app/automation/`） |

## 詞彙界線（同名或近名、意義不同）

- **「引擎」**：在本 repo 專指主體偵測引擎（`src/subject_detection`）。
  app 的自動化子套件舊名 engine，已改名 `automation`，不要再叫它引擎。
- **引擎「模板（Template）」 vs app「範本（template）」**：
  引擎的模板是登錄進模板庫、經預處理的比對單位；app 的範本是使用者截圖存進
  profile `templates/` 的圖檔或多截圖目錄（正式名稱＝相對路徑不含副檔名，
  與引擎範本名一致）。app 的範本由引擎登錄成模板（load_profile 自動進行），
  但兩詞分屬兩個 context，文件與 UI 不混用。
- **引擎「搜尋區域（Search Region）」 vs app「搜尋範圍（scan_region）」**：
  搜尋區域＝單次查詢輸入的裁切影像；搜尋範圍＝使用者設定的螢幕矩形
  （同時是 app 絕對座標的基準）。執行期關係：app 依搜尋範圍截圖，
  截下來的影像才是引擎的搜尋區域。

## 依賴方向

自動化應用 → 主體偵測引擎（單向）。引擎不知道 app 存在。
**辨識**只有一條路：runner 建構時注入的偵測器
（`query(範本名, 搜尋區域) → QueryResult`，app 端實作為 `app.py` 的
`EngineDetector`；見 ADR 0002），不允許第二條比對路徑。
此外 app 也使用引擎的公開 API 做範本管理與顯示：`load_profile`（登錄）、
`Profile.templates`／`Artifacts.ref_bgr`（瀏覽器清單與預覽）、
`discover_templates`（匯入/匯出時列舉）、`QueryResult.debug`（比對測試的
除錯分數，格式不承諾穩定）。
