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
- **基準集階段完成（2026-10-21）**：`benchmark/` 97 案例、基線 80/80＋已知失敗 17；引擎多張圖路徑、`mask_strategy`、整個 `profiles/`、舊建構工具都刪了；刪前後新集結果一致。spec 與票在 `.scratch/benchmark-rebuild/`。
- 解票時機：格式階段之前解 02、04、09、11、12（04 可能回頭要 schema 欄位，所以提前）；
  05、06、07、08、13 等到各自階段開工前才解（影片轉流程＋agent 文件階段等 04、10、13）——它們建立在格式階段之後的現況上，早解會過期。

## Decisions so far

<!-- 一張已關閉的票一行：票名（連結）— 一句話答案 -->

- [階段切法與順序](issues/01-phases-and-order.md) — 六階段依序：~~暖機~~（已取消，見下一行）→ 格式（含 profile 退場）→ 影片轉流程規則＋agent 文件 → UI 瘦身 → 基準集（可插隊）→ 文件；每階段結束可跑可打包、一階段一份 spec、死碼誰的地盤誰清；各階段驗收在票內
- [診斷「預載完還再等 3 秒」](issues/03-diagnose-post-preload-wait.md) — 不是模型暖機：那 3 秒就是開始延遲本身（同 session 再跑時預載 0 秒，延遲全排在「範本就緒」後）；首次推論成本 <0.2 秒，暖機不做；真正的等待是讀取流程會清掉登錄產物、第一次執行要現場登錄（82 張 7.5 秒），**階段 0 取消，改為讀取流程即在背景預載、併進格式階段**（規則在票內）
- [flow.yaml 具體 schema（原型）](issues/02-flow-yaml-schema.md) — 區段巢狀、一步一行（行尾自動步驟編號）；開頭的鍵即動作（`find_click`／`find`／`wait_gone`／`click`／`drag`／`wait`）、`on_fail` 沒寫＝停止、時間一律秒、間隔預設 0.3、`format: 1`、`待重拍_` 前綴退場；定案樣本、欄位表與往返驗證腳本（四份 617 步一致）在票內
- [影片轉流程產固定矩形與忙碌檢查的規則](issues/04-v2f-fixed-rect-and-busy-check-rules.md) — 各步自己影格的框每邊外推 50%（內容會變的清單由計畫宣告捲動軸、拉到影片邊）、裁到影片邊；忙碌檢查只照計畫明寫（影片看到忙碌或送伺服器即勾，驗證兩向只報告）；唯一不過標待重拍；計畫鍵跟 flow.yaml 一致；全新流程沒校準對就報錯；規則 13 條在票內
- [打包版佈局與流程存放位置](issues/09-packaged-layout-and-flow-location.md) — 打包版只剩 exe 兩個＋`_internal\`（部署＝整個換掉）；流程預設 `%USERPROFILE%\AutoClick\<名>\`（避開 OneDrive 的「文件」），`交付報告.md` 住流程資料夾裡；開檔選 `flow.yaml`、不做關聯；本機狀態只記上次流程，與日誌放 `%LOCALAPPDATA%\AutoClick\`（原始碼執行放 repo `.local\`）；引擎參數不另放全域檔；佈局樹與給格式階段的連帶事項在票內
- [記憶體步驟模型與 yaml 鍵名](issues/12-in-memory-step-model-keys.md) — 鍵名改、形狀留：記憶體欄位跟 flow.yaml 同名同單位，`type`＝開頭鍵（`loop_*`→`repeat_*`、`action` 併入），區段仍平面標記、找圖目標仍子 dict；一張預設表讀檔補齊；tools 經 app 解析與寫檔；格式階段內「刪路徑 → 機械改名 → 預設統一 → 換 yaml」，回歸網在票內（ADR 0014 決策 7）
- [轉換工具規則與驗收](issues/11-converter-rules-and-acceptance.md) — 一次性腳本放格式階段的 `.scratch`、不進 tools/；自己讀舊 zip、經 app 寫檔與讀回自對；只顧四份實有的欄位（缺值為零，套新預設不改行為）；四份各帶 `engine: {scale_range: [0.6, 1.5]}`（ADR 0015 已修訂）；`.md` 原樣成 `交付報告.md`；輸出已存在就拒絕；舊格式讀寫在格式階段內刪
- [agent 文件結構：格式規範、寫流程 skill、影片 skill 分工](issues/10-agent-docs-structure.md) — 格式規範唯一一份 `docs/flow-format.md`（欄位、執行語意、常見寫法，pytest 對照防過期）；新 skill `edit-flow` 只改既有流程、不寫猜的座標（找圖 → 錄影補充 → 交給 app；分工後由票 13 修訂）；新增不載引擎的檢查指令；影片 skill 只留影片特有；`app/CLAUDE.md` 的執行語意本階段就搬走；補充流程畢業成新票
- [補充流程規則](issues/13-supplement-flow-rules.md) — 兩個入口＋共用核心：video-to-flow（新流程）、edit-flow（既有流程，直接改不備份）都呼叫新 skill `video-measure`；在影格量既有校準對得影片倍率、任何支援範圍內的倍率都換算（量不到請使用者給同取景圖片）；插入段自己先定位、`after`/`into: N`＋內容核對、插入後舊步驟原點來源不得改變、範本可引用撞名報錯；交付報告拆成 `交付報告/`（總覽＋每頂層區段一份）；階段 2 驗收改成 add5 補充回早_簡中對照手動版＋另一支獨立重轉
- [盤點示範影片與驗證產物能給基準集什麼](issues/07-inventory-videos-and-verify-outputs.md) — 四份流程對六支 demo＋add1–5（demo4 變動幀率、demo1 0.5 Mbps 糊）；人工判定的對應只有 quick-place 標註、商店標註、舊計畫（在系統暫存目錄、會被清）、標題取材幀，其餘是自動量的、部分用跳轉讀幀；舊集 52 案例 38 個合成，縮放兩端、色偏、跨集影格裡做不出來，比色／負樣本／忙碌／同款多個做得出來；游標幾乎每格都在，轉場約 2–4/12
- [主視窗與流程設定對話框版面（原型）](issues/05-main-window-and-flow-settings-layout.md) — 兩列工具列＋兩欄（步驟｜範本上、紀錄下）；新增步驟＝步驟標題列靠右一排鈕＋「區段 ▾」，窄時收成「＋ 新增 ▾」；未存檔只標題 `*`；迷你視窗不動；流程設定對話框三列各有設定／清除／測試；**說明文字一律簡化進 ⓘ 懸停顯示、⚠ 警告縮一行常駐**（全部對話框適用）
- [步驟編輯器依動作顯示欄位（原型）](issues/06-step-editor-fields-by-action.md) — 版面 B 兩欄（找什麼｜找到之後；座標點擊、拖曳是位置｜送出之後），全攤開不折疊、寬度固定；找圖設定併進主對話框（確認圖仍是子對話框）；挑選規則四種都留、間隔與逾時同行；**逾時預設改 5 秒**（改前要把現有流程沒寫的 10 秒寫明，見票內連帶事項）
- [基準集重製方法](issues/08-benchmark-rebuild-method.md) — 約 100 個照類型配額（含忙碌指示、合成 ×0.85／1.15、易誤判負樣本、跨影片 6–8），現在的範本＋順序讀影格由工具配對、agent 先審、使用者看本機 HTML 卡片頁全審；格式沿用＋來源／`expected_scale`／`known_failure` 欄位，引擎只用內建預設；基線＝除已知失敗外 100%＋零誤判；一次性腳本在 `.scratch`；新集到基線後同階段一次刪 multi_capture、`profiles/`、舊建構工具與測試；手動跑

## Not yet specified

- 引擎 API 調整細節：`load_templates` 的 config 由 app 合併內建預設與流程覆蓋後交付；刪 multi_capture 後登錄介面怎麼收斂；
  bench loader 改讀新基準集格式。02、08 都已定，基準集階段 `/to-spec` 時一起切票。

## Out of scope

- torch 去留：使用者決定不動（打包體積不是痛點）。
- 並行執行／舞台接縫重做：接縫本次刪除，日後要做是新題目。
- 引擎粗篩方法與 OpenCV 依賴：不重評估。
- 8 月的 format 2 舊存檔（`profiles/arknights/flows/`）：不轉換，隨 profiles/ 一起消失。
- 多 profile／多遊戲的 UI：profile 整個退場，換遊戲靠流程裡的引擎參數覆蓋。
