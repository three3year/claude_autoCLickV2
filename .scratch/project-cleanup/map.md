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
- 解票時機：格式階段之前解 02、04、09、11（04 可能回頭要 schema 欄位，所以提前）；
  10、05、06、07、08 等到各自階段開工前才解——它們建立在格式階段之後的現況上，早解會過期。

## Decisions so far

<!-- 一張已關閉的票一行：票名（連結）— 一句話答案 -->

- [階段切法與順序](issues/01-phases-and-order.md) — 六階段依序：~~暖機~~（已取消，見下一行）→ 格式（含 profile 退場）→ 影片轉流程規則＋agent 文件 → UI 瘦身 → 基準集（可插隊）→ 文件；每階段結束可跑可打包、一階段一份 spec、死碼誰的地盤誰清；各階段驗收在票內
- [診斷「預載完還再等 3 秒」](issues/03-diagnose-post-preload-wait.md) — 不是模型暖機：那 3 秒就是開始延遲本身（同 session 再跑時預載 0 秒，延遲全排在「範本就緒」後）；首次推論成本 <0.2 秒，暖機不做；真正的等待是讀取流程會清掉登錄產物、第一次執行要現場登錄（82 張 7.5 秒），**階段 0 取消，改為讀取流程即在背景預載、併進格式階段**（規則在票內）

## Not yet specified

- 引擎 API 調整細節：`load_templates` 的 config 由 app 合併內建預設與流程覆蓋後交付；刪 multi_capture 後登錄介面怎麼收斂；
  bench loader 改讀新基準集格式。等 02（schema）與 08（基準集方法）定了再切票。
- 執行器刪路徑（按鍵、絕對座標、滑鼠鍵、連點、原點矩形、出現等候上限、兩個毫秒設定）後的回歸網：等 02；屬格式階段。

## Out of scope

- torch 去留：使用者決定不動（打包體積不是痛點）。
- 並行執行／舞台接縫重做：接縫本次刪除，日後要做是新題目。
- 引擎粗篩方法與 OpenCV 依賴：不重評估。
- 8 月的 format 2 舊存檔（`profiles/arknights/flows/`）：不轉換，隨 profiles/ 一起消失。
- 多 profile／多遊戲的 UI：profile 整個退場，換遊戲靠流程裡的引擎參數覆蓋。
