# 轉換計畫格式

組裝工具讀的 JSON（`tools/video_to_flow/plan.py` 是唯一權威；欄位寫錯工具會指名報錯）。
相對路徑以計畫檔所在目錄為準。**所有位置都是影片像素**（影格左上角為 0,0）。

## 最外層

| 欄位 | 必填 | 說明 |
|---|---|---|
| `video` | ✓ | 示範影片路徑 |
| `profile` | ✓ | 目標 profile 目錄（有 `config.yaml` 的那層） |
| `name` | ✓ | 流程名稱＝存檔檔名（撞名自動加 `_2`…） |
| `templates` | ✓ | `{範本名: 範本}` |
| `steps` | ✓ | 步驟清單 |
| `calibration` |  | `{"pair": [範本名, 範本名], "frame": N, "fallback": {"pair": [範本名, 範本名]}}`：`校準對`（兩張都要在 `templates` 裡；挑遊戲畫面內相距夠遠的兩張固定圖）與量`基準距離`的幀（預設＝第一張的取材幀）。`fallback`＝`備用校準對`（可不寫；例：標題列圖示＋關閉鈕），在同一幀上量它的基準距離與對座標基準點的偏移，兩組不能相同。沒寫 `calibration`＝流程不能執行 |
| `retryIntervalMs` |  | `補做間隔`（毫秒，預設 1000）：生效確認沒過時，距上次輸入至少隔這麼久才重送 |
| `busyTarget` |  | `忙碌指示`：`{"template": 範本名, "colorCheck": bool, "limit": {"kind": "grid", "cells": [...]}}`（只能九宮格）。補做前畫面上有它就先不送 |
| `report` |  | `{branches, unexplained, keys, notes}`，各為字串清單，原樣寫進交付報告 |
| `reportPath` |  | 報告位置（預設與存檔同名並排在 `flows/`） |

## 範本

| 欄位 | 必填 | 說明 |
|---|---|---|
| `frame` | ✓ | 取材幀（乾淨影格） |
| `box` | ✓ | `[x, y, w, h]` 裁切框，原尺寸寫成 PNG |
| `absent` |  | 該**找不到**的幀（按鈕還沒出現） |
| `present` |  | 該**找得到**的其他幀：幀號，或 `{"frame": N, "at": [x, y]}`（位置變了） |
| `clean` |  | `false`＝找不到乾淨影格 → 一律標待重拍（預設 `true`） |

範本名：平面名稱，不能以 `待重拍_` 開頭（那是工具標記用的前綴）。

## 步驟

步驟種類與欄位就是流程既有詞彙；位置寫影片像素，**不寫** `x`/`y`/`offsetX`/`mode` 等
偏移欄位（由組裝推算）。

| `type` | 位置欄位 | 其他可寫欄位（未寫＝預設） |
|---|---|---|
| `find_click` | `template`（必填）、`frame`（照找圖目標在這一幀挑範本；預設＝範本取材幀）、`at`（點擊位置；預設＝挑中的中心） | `colorCheck`、`pick`、`limit`（見下節）、`action` click/none/wait_gone、`confirm` none/gone/appear/next、`confirmTemplate` 或 `confirmTarget`（appear 才寫）、`onNotFound` skip/break/stop、`timeout`、`interval`、`button`、`clicks`、`updateOrigin`、`appearLimitMs`（wait_gone 才寫：`出現等候上限`毫秒，上限內沒看到＝通過） |
| `click` | `at`（必填） | `button`、`clicks`、`updateOrigin`、`生效確認`（見下） |
| `drag` | `from`、`to`（必填） | `button`、`ms`、`holdMs`、`生效確認`（見下） |
| `key` | — | `keys`（必填，例如 `"esc"`、`"ctrl+a"`） |
| `wait` | — | `ms` |
| `loop_start` | — | `count`（必填） |
| `loop_end` / `branch_end` | — | `onBreak` continue/break |
| `branch_start` / `branch_or` | — | — |

組裝補的預設：找圖 `action` click、`timeout` 10、`onNotFound` stop；點擊的找圖下一步是
找圖 → `confirm: next`，否則 → `gone`；不點擊的找圖 → `none`。
明寫 `confirm: next` 但下一步不是找圖（`找圖相連`不成立）會報錯。

## 找圖目標屬性

找圖步驟與確認圖都是一個`找圖目標`：範本＋下面三個屬性（都不寫＝整個搜尋範圍、分數最高、
不比色）。何時用哪個見 SKILL.md 第 5 節。

| 欄位 | 寫法 | 組裝存成 |
|---|---|---|
| `colorCheck` | `true` | 比色：顏色不符的不算匹配 |
| `pick` | `{"kind": "top", "n": 3}`／`{"kind": "left", "n": 2}`（由上到下／由左到右第 N 個，N 從 1 起） | 原樣 |
| `pick` | `{"kind": "near", "base": "origin", "at": [x, y]}`（最接近指定點；`base: "region"`＝以搜尋範圍為基準） | `at` 換成相對原點（region：相對影片左上） |
| `limit` | `{"kind": "origin", "rect": [x, y, w, h]}`（只在這個矩形裡找） | 矩形換成相對原點 |
| `limit` | `{"kind": "grid", "cells": [6, 9]}`（搜尋範圍 3×3 九宮格，格號由左上起逐列 1–9；多格＝包住它們的最小矩形） | 原樣 |

- `rect`／`at` 一律寫**影片像素的畫面位置**，跟 `at` 一樣；相對值由組裝依原點規則推算。
  找圖步驟用**這一步之前**的原點，確認圖用**點擊後**的原點。以原點為基準、這一步之前卻
  沒有原點 → 組裝報錯（同相對座標點擊）。
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
  "profile": "C:/.../app/dist/AutoClick/profiles/arknights",
  "name": "日常_影片",
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
