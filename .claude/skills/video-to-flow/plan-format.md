# 轉換計畫格式

組裝工具讀的 JSON（`tools/video_to_flow/plan.py` 是唯一權威；欄位寫錯工具會指名報錯）。
相對路徑以計畫檔所在目錄為準。**所有位置都是影片像素**（影格左上角為 0,0）。

## 最外層

| 欄位 | 必填 | 說明 |
|---|---|---|
| `video` | ✓ | 示範影片路徑 |
| `name` | ✓ | 流程名稱＝流程資料夾名（檔名不允許的字元換成 `_`；輸出位置裡已有同名資料夾時自動加 `_2`、`_3`…，不覆蓋） |
| `out` |  | 輸出位置：流程資料夾建在它底下（預設 `%USERPROFILE%\AutoClick\`；命令列 `--out` 優先於它） |
| `templates` | ✓ | `{範本名: 範本}` |
| `steps` | ✓ | 步驟清單 |
| `calibration` |  | `{"pair": [範本名, 範本名], "frame": N, "fallback": {"pair": [範本名, 範本名]}}`：`校準對`（兩張都要在 `templates` 裡；挑遊戲畫面內相距夠遠的兩張固定圖）與量`基準距離`的幀（預設＝第一張的取材幀）。`fallback`＝`備用校準對`（可不寫；例：標題列圖示＋關閉鈕），在同一幀上量它的基準距離與對座標基準點的偏移，兩組不能相同。沒寫 `calibration`＝流程不能執行 |
| `busyTarget` |  | `忙碌指示`：`{"template": 範本名, "colorCheck": bool}`（`colorCheck` 可不寫；不收挑選規則與限定範圍，要框`固定矩形`請使用者在 app 裡設）。補做前畫面上有它就先不送 |
| `report` |  | `{branches, unexplained, keys, notes}`，各為字串清單，原樣寫進交付報告（`keys` 列在「口頭補充的按鍵（流程不支援，請改用點擊）」一節） |

已退場、寫了會報錯：`profile`（改寫 `out`）、`reportPath`（報告一律是流程資料夾裡的
`交付報告.md`）、`retryIntervalMs`（`補做間隔`固定 1 秒）。

輸出：`<輸出位置>/<流程名>/`，內含 `flow.yaml`、`templates/`、`交付報告.md`。不寫搜尋範圍
（＝全螢幕）。

## 範本

| 欄位 | 必填 | 說明 |
|---|---|---|
| `frame` | ✓ | 取材幀（乾淨影格） |
| `box` | ✓ | `[x, y, w, h]` 裁切框，原尺寸寫成 PNG |
| `absent` |  | 該**找不到**的幀（按鈕還沒出現） |
| `present` |  | 該**找得到**的其他幀：幀號，或 `{"frame": N, "at": [x, y]}`（位置變了） |
| `clean` |  | `false`＝找不到乾淨影格 → 一律標待重拍（預設 `true`） |

範本名：平面名稱（範本名＝檔名，不能有 `/ \ : * ? " < > |`、前後空白或結尾的 `.`）。

## 步驟

步驟種類與欄位就是流程既有詞彙；位置寫影片像素，**不寫** `x`/`y`/`offsetX`/`mode` 等
偏移欄位（由組裝推算）。

| `type` | 位置欄位 | 其他可寫欄位（未寫＝預設） |
|---|---|---|
| `find_click` | `template`（必填）、`frame`（照找圖目標在這一幀挑範本；預設＝範本取材幀）、`at`（點擊位置；預設＝挑中的中心） | `colorCheck`、`pick`（見下節）、`action` click/none/wait_gone、`confirm` none/gone/appear/next、`confirmTemplate` 或 `confirmTarget`（appear 才寫；`confirm` 系列只有 `action` click 才能寫）、`onNotFound` skip/break/stop、`timeout`、`interval`、`updateOrigin` |
| `click` | `at`（必填） | `updateOrigin`、`生效確認`（見下） |
| `drag` | `from`、`to`（必填） | `ms`、`holdMs`、`生效確認`（見下） |
| `wait` | — | `ms` |
| `loop_start` | — | `count`（必填） |
| `loop_end` / `branch_end` | — | `onBreak` continue/break |
| `branch_start` / `branch_or` | — | — |

組裝補的預設：找圖 `action` click、`timeout` 10（秒）、`interval` 0.3（秒）、`onNotFound` stop；
點擊的找圖下一步是找圖 → `confirm: next`，否則 → `gone`；不點擊的找圖 → `none`。
拖曳 `ms`／`holdMs` 預設各 500。明寫 `confirm: next` 但下一步不是找圖（`找圖相連`不成立）會報錯。

已退場、寫了會報錯（ADR 0014）：`key` 步驟（影片裡看不到的按鍵寫進 `report.keys`）、
`limit`（限定範圍，含確認圖與 `busyTarget` 上的）、`appearLimitMs`、非左鍵的 `button`、
`clicks` 不是 1；寫預設值（`"button": "left"`、`"clicks": 1`）的照收、直接拿掉。
`忙碌檢查`（`busyCheck`）計畫還不能寫——要勾的步驟請使用者在 app 裡勾（見 SKILL.md 第 4 節）。

## 找圖目標屬性

找圖步驟與確認圖都是一個`找圖目標`：範本＋下面兩個屬性（`busyTarget` 只收 `colorCheck`）（都不寫＝整個畫面、
分數最高、不比色）。工具不產限定範圍；要縮小範圍請使用者事後在 app 的找圖設定裡框`固定矩形`。
何時用哪個見 SKILL.md 第 5 節。

| 欄位 | 寫法 | 組裝存成 |
|---|---|---|
| `colorCheck` | `true` | 比色：顏色不符的不算匹配 |
| `pick` | `{"kind": "top", "n": 3}`／`{"kind": "left", "n": 2}`（由上到下／由左到右第 N 個，N 從 1 起；不能有其他欄位） | 原樣 |
| `pick` | `{"kind": "near", "at": [x, y]}`（最接近指定點；只寫 `at`，沒有 `base`） | `at` 換成相對原點 |

- `pick.at` 一律寫**影片像素的畫面位置**，跟 `at` 一樣；相對值由組裝依原點規則推算。
  找圖步驟用**這一步之前**的原點，確認圖用**點擊後**的原點。這一步之前卻沒有原點 →
  組裝報錯（同相對座標點擊）。
- 座標點擊／拖曳的`生效確認`：`confirm` gone（`原點的圖離開`：產生原點的那個找圖目標離開
  原位＝生效，原點要來自找圖）／appear（`confirmTemplate`/`confirmTarget`）／next（下一步要是
  找圖），另可寫 `timeout`、`interval`、`onNotFound`（預設停止）；沒寫 `confirm` 就不要寫這三個。
  拖曳的原點來自找圖、又沒寫 `confirm` 時，組裝補 `gone`。
- 確認圖要設屬性時寫 `"confirmTarget": {"template": "確定", "colorCheck": true, ...}`；
  只有範本時 `confirmTemplate` 是它的簡寫，兩者擇一。
- 驗證照同一套找圖目標邏輯：步驟的 `frame` 上**挑中**的那個要在 `at` 附近（沒寫 `at` 而
  `frame` 是取材幀時，挑中的要是取材的那一個），不是就標待重拍。範本的取材幀／`present`
  只要求預期位置有匹配（同款別處也有匹配不算錯）；`absent` 幀要求**整張畫面沒有任何匹配**
  （照引用它的找圖目標用到的比色設定查），所以同款在別處仍看得到的幀不要列進 `absent`。

## 小範例

點「開始行動」→ 載入約 15 秒 → 點空白處關掉結算 → 連領 3 次獎勵（每次點「領取」再點空白處）。

```json
{
  "video": "C:/Users/me/Videos/daily.mp4",
  "name": "日常_影片",
  "out": "C:/Users/me/AutoClick",
  "templates": {
    "開始行動": {"frame": 240, "box": [1500, 880, 220, 90], "absent": [100]},
    "行動結束": {"frame": 760, "box": [80, 120, 300, 70], "absent": [500]},
    "領取":     {"frame": 900, "box": [820, 600, 160, 60], "absent": [780],
                 "present": [990, 1080]},
    "標題列圖示": {"frame": 240, "box": [6, 4, 28, 24]},
    "關閉鈕":     {"frame": 240, "box": [1886, 4, 28, 24]}
  },
  "calibration": {"pair": ["開始行動", "行動結束"], "frame": 760,
                  "fallback": {"pair": ["標題列圖示", "關閉鈕"]}},
  "steps": [
    {"type": "find_click", "template": "開始行動", "frame": 240, "at": [1610, 925]},
    {"type": "find_click", "template": "行動結束", "frame": 760, "action": "none",
     "timeout": 30},
    {"type": "click", "at": [960, 1000]},
    {"type": "loop_start", "count": 3},
    {"type": "find_click", "template": "領取", "frame": 900, "at": [900, 630]},
    {"type": "click", "at": [900, 900]},
    {"type": "loop_end"}
  ],
  "report": {
    "branches": ["步驟 1 前可能跳出「理智不足」彈窗，影片裡沒有出現"],
    "unexplained": [],
    "keys": []
  }
}
```

`行動結束` 是定位找圖（只等待出現、更新原點），讓後面的座標點擊有原點；
重複區段內先找「領取」再點空白處，區段內就有自己的原點。
`calibration` 指名遊戲畫面內的兩張圖當校準對（第 760 幀兩張都在），標題列的圖示與關閉鈕當
備用對：組裝在同一幀量兩組的中心距離當各自的基準距離、備用第一張中心到座標基準點的偏移；
執行時每次開頭先用校準對量畫面倍率，找不到才用備用對。
