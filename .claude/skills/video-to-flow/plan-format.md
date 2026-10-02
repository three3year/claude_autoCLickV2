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
| `find_click` | `template`（必填）、`frame`（引擎在這一幀找範本；預設＝範本取材幀）、`at`（點擊位置；預設＝找到的中心） | `action` click/none/wait_gone、`confirm` none/gone/appear/next、`confirmTemplate`（appear 才寫）、`onNotFound` skip/break/stop、`timeout`、`interval`、`button`、`clicks`、`updateOrigin` |
| `click` | `at`（必填） | `button`、`clicks`、`updateOrigin` |
| `drag` | `from`、`to`（必填） | `button`、`ms`、`holdMs` |
| `key` | — | `keys`（必填，例如 `"esc"`、`"ctrl+a"`） |
| `wait` | — | `ms` |
| `loop_start` | — | `count`（必填） |
| `loop_end` / `branch_end` | — | `onBreak` continue/break |
| `branch_start` / `branch_or` | — | — |

組裝補的預設：找圖 `action` click、`timeout` 10、`onNotFound` stop；點擊的找圖下一步是
找圖 → `confirm: next`，否則 → `gone`；不點擊的找圖 → `none`。
明寫 `confirm: next` 但下一步不是找圖（`找圖相連`不成立）會報錯。

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
                 "present": [990, 1080]}
  },
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
