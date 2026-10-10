# 專案整理（agent 友善格式、精簡、UI 瘦身）— wayfinder 地圖

Label: wayfinder:map
建立：2026-10-10

## Destination

整理專案的路線清楚到可以逐階段執行：每個階段的範圍、順序、相依、驗收方式都定了，
flow.yaml 的具體長相、UI 版面、影片轉流程的新規則、基準集重製方法、打包版佈局都有決定。
到了這裡，剩下的只是逐階段跑使用者自己的 `/to-spec` → `/to-tickets` → `/implement`；實作不在地圖上。
不必整張地圖解完才動手：一個階段的前置票解完，該階段就可以開工（階段與前置票見「階段切法與順序」）。

## Notes

- 決策與理由的正本：ADR 0014（流程＝資料夾、步驟選項裁減）、0015（profile 退場、引擎參數內建預設＋流程覆蓋）、
  0016（基準集從在用流程與影片影格重製、引擎刪多張圖路徑）。grilling 的完整紀錄與調查事實在同目錄 `grilling.md`。
- 詞彙：`app/CONTEXT.md`、`CONTEXT.md`、`CONTEXT-MAP.md` 已更新到目標狀態（退場詞條有標記）。寫票與解票時以它為準，
  用 `/domain-modeling` 維護。
- 解票預設用 `/grilling`＋`/domain-modeling`；原型票用 `/prototype`。
- 使用者偏好：回覆繁體中文。任何要使用者核可的 md（spec.md 等審核關卡）寫之前先用 `review-mirror` skill。
  GUI 冒煙或會開視窗的測試前先確認使用者不在玩遊戲（見 memory）。
- 四份在用流程的最新實體在打包版 `app/dist/AutoClick/profiles/arknights/flows/`（2026-10-10 14:58），不在 git。
- torch／DINOv2 不動；引擎只刪 multi_capture 路徑。
- 解票時機：格式階段之前解 02、04、09、11、12（04 可能回頭要 schema 欄位，所以提前）；
  10、05、06、07、08 等到各自階段開工前才解——它們建立在格式階段之後的現況上，早解會過期。

## Decisions so far

<!-- 一張已關閉的票一行：票名（連結）— 一句話答案 -->

- [階段切法與順序](issues/01-phases-and-order.md) — 六階段依序：~~暖機~~（已取消，見下一行）→ 格式（含 profile 退場）→ 影片轉流程規則＋agent 文件 → UI 瘦身 → 基準集（可插隊）→ 文件；每階段結束可跑可打包、一階段一份 spec、死碼誰的地盤誰清；各階段驗收在票內
- [診斷「預載完還再等 3 秒」](issues/03-diagnose-post-preload-wait.md) — 不是模型暖機：那 3 秒就是開始延遲本身（同 session 再跑時預載 0 秒，延遲全排在「範本就緒」後）；首次推論成本 <0.2 秒，暖機不做；真正的等待是讀取流程會清掉登錄產物、第一次執行要現場登錄（82 張 7.5 秒），**階段 0 取消，改為讀取流程即在背景預載、併進格式階段**（規則在票內）
- [flow.yaml 具體 schema（原型）](issues/02-flow-yaml-schema.md) — 區段巢狀、一步一行（行尾自動步驟編號）；開頭的鍵即動作（`find_click`／`find`／`wait_gone`／`click`／`drag`／`wait`）、`on_fail` 沒寫＝停止、時間一律秒、間隔預設 0.3、`format: 1`、`待重拍_` 前綴退場；定案樣本、欄位表與往返驗證腳本（四份 617 步一致）在票內
- [影片轉流程產固定矩形與忙碌檢查的規則](issues/04-v2f-fixed-rect-and-busy-check-rules.md) — 各步自己影格的框每邊外推 50%（內容會變的清單由計畫宣告捲動軸、拉到影片邊）、裁到影片邊；忙碌檢查只照計畫明寫（影片看到忙碌或送伺服器即勾，驗證兩向只報告）；唯一不過標待重拍；計畫鍵跟 flow.yaml 一致；全新流程沒校準對就報錯；規則 13 條在票內
- [打包版佈局與流程存放位置](issues/09-packaged-layout-and-flow-location.md) — 打包版只剩 exe 兩個＋`_internal\`（部署＝整個換掉）；流程預設 `%USERPROFILE%\AutoClick\<名>\`（避開 OneDrive 的「文件」），`交付報告.md` 住流程資料夾裡；開檔選 `flow.yaml`、不做關聯；本機狀態只記上次流程，與日誌放 `%LOCALAPPDATA%\AutoClick\`（原始碼執行放 repo `.local\`）；引擎參數不另放全域檔；佈局樹與給格式階段的連帶事項在票內
- [記憶體步驟模型與 yaml 鍵名](issues/12-in-memory-step-model-keys.md) — 鍵名改、形狀留：記憶體欄位跟 flow.yaml 同名同單位，`type`＝開頭鍵（`loop_*`→`repeat_*`、`action` 併入），區段仍平面標記、找圖目標仍子 dict；一張預設表讀檔補齊；tools 經 app 解析與寫檔；格式階段內「刪路徑 → 機械改名 → 預設統一 → 換 yaml」，回歸網在票內（ADR 0014 決策 7）

## Not yet specified

- 引擎 API 調整細節：`load_templates` 的 config 由 app 合併內建預設與流程覆蓋後交付；刪 multi_capture 後登錄介面怎麼收斂；
  bench loader 改讀新基準集格式。02（schema）已定，等 08（基準集方法）定了再切票。
- 補充流程（影片只錄一段、插進既有流程，如 add5）：先確認影片與既有流程同倍率，再沿用既有流程的校準對、決定插入點；工具要不要支援、怎麼支援，影片轉流程階段開工前再看。

## Out of scope

- torch 去留：使用者決定不動（打包體積不是痛點）。
- 並行執行／舞台接縫重做：接縫本次刪除，日後要做是新題目。
- 引擎粗篩方法與 OpenCV 依賴：不重評估。
- 8 月的 format 2 舊存檔（`profiles/arknights/flows/`）：不轉換，隨 profiles/ 一起消失。
- 多 profile／多遊戲的 UI：profile 整個退場，換遊戲靠流程裡的引擎參數覆蓋。
