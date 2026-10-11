# 轉換計畫格式

`assemble`（新流程）與 `insert`（補充）讀的 JSON。**步驟的鍵、值、預設、區段寫法跟 flow.yaml 一模一樣**——
見 [docs/flow-format.md](../../../docs/flow-format.md)，這裡只寫不一樣的地方。工具用 app 的讀檔規則驗證步驟，
寫錯會指名報錯；相對路徑以計畫檔所在目錄為準。

## 跟 flow.yaml 不一樣的地方

1. **位置是影片像素的畫面位置**（影格左上角為 0,0），不是相對值：

   | 鍵 | 計畫裡寫 | 工具換成 |
   |---|---|---|
   | `click: [x, y]` | 點擊的畫面位置 | 相對原點的偏移 |
   | `drag: [x, y]`、`to: [x, y]` | 起點、終點的畫面位置 | 相對原點的偏移 |
   | 找圖的 `at: [x, y]`（計畫專用） | 點擊（或當原點）的畫面位置；沒寫＝挑中的框中心 | `offset` |
   | `pick: {near: [x, y]}` | 指定點的畫面位置 | 相對原點（確認圖用操作後的原點） |

2. **不寫** `within`、`offset`：固定矩形與偏移由工具算，寫了報錯。
3. **影片證據**（計畫專用，不進 flow.yaml）：

   | 鍵 | 寫在 | 意思 |
   |---|---|---|
   | `frame` | 任一步 | 這一步在影片裡看的那一幀。找圖：照它的設定在這一幀挑框（預設＝範本的取材幀；引用既有範本時必填）。座標點擊／拖曳：送出輸入的那一幀（有忙碌指示時必填，工具看它之後有沒有忙碌） |
   | `scroll` | 找圖 | `vertical`／`horizontal`：捲動軸。內容每次會變的清單（好友列表、每輪換一列）用；固定矩形該軸拉到影片兩端 |
   | `confirm: {appear: 名, frame: N}` | 確認圖 | 確認圖出現的那一幀（預設＝確認圖範本的取材幀；用既有範本時必填） |

4. 預設照 app（`on_fail` 停止、`timeout` 10、`interval` 0.3…）；`confirm` 沒寫＝不確認，**工具不替你推**：
   找圖點擊的下一步是找圖就寫 `confirm: next`，否則 `confirm: gone`；拖曳的原點來自找圖寫 `confirm: gone`。
   `busy_check` 也一樣，計畫明寫才勾（標準見 flow-format.md「忙碌檢查該勾哪些步驟」）。

已退場、寫了報錯（訊息會指出新鍵）：`type`、`action`、`template`、`colorCheck`、`onNotFound`、`updateOrigin`、
`busyCheck`、`onBreak`、`confirmTemplate`、`confirmTarget`、`ms`、`holdMs`、`count`、`loop_start`、毫秒的
`timeout`／`wait`、`key` 步驟、`limit`、`appearLimitMs`、`button`、`clicks`、`busyTarget`、`report.keys`。

## 最外層

| 欄位 | assemble | insert | 說明 |
|---|---|---|---|
| `video` | 必填 | 必填 | 示範影片路徑 |
| `templates` | 必填 | 可空 | `{範本名: 範本}`（見下）；補充時只寫新裁的，既有範本直接在步驟裡引用 |
| `steps` | 必填 | 必填 | 步驟清單（flow.yaml 的寫法，巢狀區段） |
| `report` | 選填 | 選填 | `{branches, unexplained, notes}`，各為字串清單，寫進交付報告；`unexplained`＝無法用點擊解釋的畫面變化（報告會註明流程不支援按鍵） |
| `name` | 必填 | — | 流程名＝資料夾名（撞名加 `_2`…） |
| `out` | 選填 | — | 輸出位置（預設 `%USERPROFILE%\AutoClick\`；命令列 `--out` 優先） |
| `calibration` | 必填 | — | `{"pair": [名, 名], "frame": N, "fallback": {"pair": [名, 名]}}`：校準對兩張都要在 `templates`；`frame` 預設＝第一張的取材幀；主對在那一幀量不到＝報錯 |
| `busy` | 選填 | — | 忙碌指示 `{"template": 名, "color": true, "pick": {...}, "frame": N}`；`frame`＝忙碌字樣清楚可見的那一幀（預設＝取材幀）。有步驟勾 `busy_check` 就必須有 |
| `after` ／ `into` | — | 擇一必填 | `after: N`＝插在第 N 步之後同一層（N 是區段開頭＝插在整個區段之後）；`into: N`＝插在重複區段 N 裡最前面。N 是 flow.yaml 行尾的 `# N` |
| `expect` | — | 必填 | 第 N 步的開頭鍵＋值，工具核對：`{"find": "标题_办公室"}`、`{"repeat": 2}`、`{"click": [801, 76]}`；分岔寫第一個分支條件的範本 `{"branch": "标题_办公室"}` |
| `scale_image` | — | 選填 | 影片裡量不到既有流程的校準對時，使用者給的同取景、同視窗大小的圖片 |
| `align` | — | 見說明 | `對齊圖` `{"find": 既有範本名, "frame": N, "at": [x, y], "step": N}`：`step`＝插入點前定位這張圖、有固定矩形的那一步（行尾 `# N`），`frame`＝第一次捲動前清單停住的那一幀，`at`＝它在那一幀的大約位置（影片像素）。插入段（含巢狀區段）有拖曳、或有找圖宣告了 `scroll` 時**必填**；`align: null`＝刻意不對齊（影片就是從插入點的畫面開始錄）。其他情況不寫＝不對齊。對齊時第一次拖曳要寫 `frame` |

補充一律沿用既有流程的校準對、忙碌指示、名稱與位置：計畫寫 `calibration`／`busy`／`name`／`out` 報錯；
也不收手打的倍率（`scale` 之類報錯）。

## 範本

| 欄位 | 必填 | 說明 |
|---|---|---|
| `frame` | ✓ | 取材幀（乾淨影格） |
| `box` | ✓ | `[x, y, w, h]` 裁切框（影片像素）；新流程原尺寸存，補充時除以影片倍率 |
| `absent` |  | 該**找不到**的幀（整張影格沒有任何匹配） |
| `present` |  | 該**找得到**的其他幀：幀號，或 `{"frame": N, "at": [x, y]}`（位置變了） |
| `clean` |  | `false`＝找不到乾淨影格 → 一律標待重拍（預設 `true`） |

範本名照 flow-format.md「範本命名」。補充時新範本跟既有範本撞名＝報錯（改名，或改成引用既有的）。

## 小範例（新流程）

```json
{
  "video": "C:/Users/me/Videos/daily.mp4",
  "name": "日常_影片",
  "templates": {
    "主画面设置钮": {"frame": 240, "box": [20, 40, 60, 60]},
    "主画面仓库": {"frame": 240, "box": [1560, 780, 90, 80]},
    "開始行動": {"frame": 240, "box": [1500, 880, 220, 90], "absent": [100]},
    "領取": {"frame": 900, "box": [820, 600, 160, 60], "absent": [780], "present": [990]},
    "忙碌指示": {"frame": 905, "box": [900, 900, 240, 24]}
  },
  "calibration": {"pair": ["主画面设置钮", "主画面仓库"], "frame": 240},
  "busy": {"template": "忙碌指示"},
  "steps": [
    {"find_click": "開始行動", "frame": 240, "at": [1610, 925], "confirm": "gone", "timeout": 30},
    {"repeat": 3, "steps": [
      {"find_click": "領取", "frame": 900, "at": [900, 630], "busy_check": true},
      {"click": [900, 900], "frame": 920}
    ]}
  ],
  "report": {"branches": ["開始行動前可能跳出「理智不足」彈窗，影片裡沒有出現"]}
}
```

## 小範例（補充）

插在第 120 步（找 `标题_办公室` 的分岔）之後，`标题_办公室` 是既有範本、`标题_回收站` 新裁；影片開錄時清單
停在別處，用第 121 步（分岔條件，定位辦公室標題）當對齊圖的參考步驟：

```json
{
  "video": "C:/Users/me/oCam Video/add5.mp4",
  "after": 120, "expect": {"branch": "标题_办公室"},
  "align": {"find": "标题_办公室", "frame": 180, "at": [1440, 742], "step": 121},
  "templates": {"标题_回收站": {"frame": 230, "box": [770, 690, 120, 40]}},
  "steps": [
    {"branch": [{"if": {"find": "标题_办公室", "frame": 180, "pick": {"top": 1}, "timeout": 3,
                         "on_fail": "skip", "scroll": "vertical"},
                 "then": [
                   {"drag": [1400, 760], "to": [1400, 430], "frame": 200, "confirm": "gone",
                    "on_fail": "break", "busy_check": true},
                   {"find": "标题_回收站", "frame": 230, "pick": {"top": 1}, "on_fail": "break"},
                   {"click": [1620, 790], "frame": 240, "busy_check": true}]}]}
  ]
}
```
