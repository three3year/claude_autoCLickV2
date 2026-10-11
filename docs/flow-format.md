# flow.yaml 格式規範

寫流程（手改 `flow.yaml`、寫影片轉流程的計畫）時讀這一份就夠，不必讀 app 的開發文件。
這是 flow.yaml 唯一的正本：欄位、執行語意、常見寫法。詞彙的定義在 [`app/CONTEXT.md`](../app/CONTEXT.md)，
這裡用到的`找圖目標`、`原點`、`座標基準點`等詞照它的意思，不另外定義。

一份流程＝一個資料夾：

```
<流程名>/flow.yaml          步驟與流程層級設定
<流程名>/templates/<名>.png  被引用的範本圖（檔名即範本名）
<流程名>/.cache/            可重建的快取（不用管）
<流程名>/交付報告/          影片轉流程的說明（app 不讀不寫）
```

改完跑檢查指令（不載引擎、不開視窗）：

```
python tools/flow_check <流程資料夾>              # 只讀；有錯誤以 1 結束
python tools/flow_check <流程資料夾> --normalize  # 沒錯誤時重寫成標準排版（更新行尾步驟編號）
```

## 排版

區段巢狀、一步一行（flow-style mapping）。行尾 `# N` 是 app 存檔時產生的步驟編號（＝ app 清單與
執行紀錄的編號，區段標記也算一號）；手改後編號會過期，用 `--normalize` 重排。app 存檔會整份重寫，
手寫註解不保留。等於預設的值不寫。

```yaml
format: 1
calibration:
  pair: [主画面设置钮, 主画面仓库]
  baseline: 1719.2
busy: {template: 忙碌指示, within: [847, 719, 333, 101]}
steps:
  - {find_click: 基建图标, within: [1217, 611, 152, 158], confirm: gone, timeout: 30}    # 1
  - repeat: 3    # 2
    steps:
      - branch:    # 3
          - if: {find_click: 可收获, within: [85, 732, 220, 108], confirm: gone, timeout: 3, on_fail: skip, busy_check: true}    # 4
          - if: {find_click: 订单交付, within: [88, 732, 225, 108], confirm: gone, timeout: 3, on_fail: skip}    # 6
        on_break: break
  - {find: 返回, within: [-61, -70, 117, 132], timeout: 5}    # 9
  - {click: [419, 142]}    # 10
```

## 欄位表

「適用」是鍵出現的位置：`頂層`、步驟的開頭鍵（`find_click` 等）、或子結構（`calibration`、
`calibration.fallback`、`busy`、`confirm.appear`、`branch.分支`）。「沒寫＝」欄有反引號的是 app 補上的預設值；
沒有反引號的表示沒有預設（必填、或不寫就是沒有這個設定）。
`tests` 會拿這張表跟 app 讀檔認得的鍵與預設表對照，改 app 忘了改這裡（或反過來）會紅。

| 適用 | 鍵 | 值 | 沒寫＝ | 單位 |
|---|---|---|---|---|
| 頂層 | `format` | `1` | 必填 | — |
| 頂層 | `run` | 輪數（1 以上整數）或 `forever` | `1` | 輪 |
| 頂層 | `scan_region` | `[x, y, w, h]`：`搜尋範圍` | 全螢幕 | 螢幕像素（存檔裡唯一的螢幕座標） |
| 頂層 | `calibration` | `校準對`，見 `calibration` 列 | 沒有（app 不執行） | — |
| 頂層 | `busy` | `忙碌指示`的找圖目標，見 `busy` 列 | 沒有 | — |
| 頂層 | `template_pos` | `{範本名: [x, y]}`：範本拍攝當下的中心 | 沒有 | 流程尺度，相對座標基準點 |
| 頂層 | `engine` | 引擎參數覆蓋（鍵名同引擎 `default_config.yaml`） | 引擎內建預設 | — |
| 頂層 | `steps` | 步驟清單 | 沒有步驟 | — |
| `calibration` | `pair` | `[範本名, 範本名]`：兩張不同的範本 | 必填 | — |
| `calibration` | `baseline` | `基準距離`（兩張中心的距離，存到小數 1 位） | 必填 | 流程尺度像素 |
| `calibration` | `fallback` | `備用校準對`：`{pair, baseline, offset}` | 沒有 | — |
| `calibration.fallback` | `pair` | `[範本名, 範本名]` | 必填 | — |
| `calibration.fallback` | `baseline` | 備用對自己的基準距離 | 必填 | 流程尺度像素 |
| `calibration.fallback` | `offset` | `[x, y]`：備用第一張中心 → 座標基準點 | 必填 | 流程尺度像素 |
| `busy` | `template` | 範本名 | 必填 | — |
| `busy` | `within` | `[x, y, w, h]`：`固定矩形` | 整個搜尋範圍 | 流程尺度，相對座標基準點 |
| `busy` | `pick` | 同步驟的 `pick` | 分數最高 | — |
| `busy` | `color` | `true` | 不比色 | — |
| `find_click` | `find_click` | 範本名：找到就點 | 開頭鍵（必填） | — |
| `find` | `find` | 範本名：只找不點 | 開頭鍵（必填） | — |
| `wait_gone` | `wait_gone` | 範本名：等它消失 | 開頭鍵（必填） | — |
| `find_click`、`find`、`wait_gone` | `within` | `[x, y, w, h]`：`固定矩形` | 整個搜尋範圍 | 流程尺度，相對座標基準點 |
| `find_click`、`find`、`wait_gone` | `pick` | `{top: N}`（由上到下第 N 個）、`{left: N}`（由左到右第 N 個）、`{near: [x, y]}`（最接近原點＋偏移） | 分數最高 | N 從 1 起；near 是流程尺度，相對原點 |
| `find_click`、`find`、`wait_gone` | `color` | `true`：`比色` | 不比色 | — |
| `find_click`、`find`、`wait_gone` | `offset` | `[x, y]`：點擊／原點相對找到的框中心 | `[0, 0]` | 流程尺度像素 |
| `click` | `click` | `[x, y]`：相對原點的點擊位置 | 開頭鍵（必填） | 流程尺度像素 |
| `drag` | `drag` | `[x, y]`：起點，相對原點 | 開頭鍵（必填） | 流程尺度像素 |
| `drag` | `to` | `[x, y]`：終點，相對原點（不是相對起點） | 必填 | 流程尺度像素 |
| `drag` | `duration` | 移動耗時 | `0.5` | 秒 |
| `drag` | `hold` | 按下後、移動前停留 | `0.5` | 秒 |
| `wait` | `wait` | 停留秒數 | 開頭鍵（必填） | 秒 |
| `find_click`、`click`、`drag` | `confirm` | `gone`、`next`、`{appear: 範本名, within, pick, color}`（見「生效確認」） | `none`（不確認；不能寫出來） | — |
| `find_click`、`find`、`wait_gone`、`click`、`drag` | `timeout` | 逾時（找圖等待；生效確認的等待另算一次） | `10` | 秒 |
| `find_click`、`find`、`wait_gone`、`click`、`drag` | `interval` | 輪詢間隔（大於 0） | `0.3` | 秒 |
| `find_click`、`find`、`wait_gone`、`click`、`drag` | `on_fail` | `skip`（跳過）、`break`（跳出區段）、`stop`（停止） | `stop` | — |
| `find_click`、`click`、`drag` | `busy_check` | `true`：`忙碌檢查` | `false` | — |
| `find_click`、`find`、`wait_gone`、`click` | `update_origin` | `false`：這步不更新原點 | `true` | — |
| `confirm.appear` | `appear` | 確認圖的範本名 | 必填 | — |
| `confirm.appear` | `within` | `[x, y, w, h]`：`固定矩形` | 整個搜尋範圍 | 流程尺度，相對座標基準點 |
| `confirm.appear` | `pick` | 同步驟的 `pick`（near 相對操作後的原點） | 分數最高 | — |
| `confirm.appear` | `color` | `true` | 不比色 | — |
| `repeat` | `repeat` | 次數（1 以上整數） | 開頭鍵（必填） | 次 |
| `repeat` | `steps` | 區段裡的步驟清單（不能是空的） | 必填 | — |
| `repeat` | `on_break` | `break`：因找不到跳出到這裡時連外層一起跳出 | `continue` | — |
| `branch` | `branch` | 分支清單 `- if: …` | 開頭鍵（必填） | — |
| `branch` | `on_break` | `break`（同 `repeat`） | `continue` | — |
| `branch.分支` | `if` | 一個找圖步驟（`find_click`／`find`／`wait_gone`）＝分支條件 | 必填 | — |
| `branch.分支` | `then` | 條件成立後接著做的步驟清單 | 沒有 | — |

補充規則：

- 一步只能有一個開頭鍵。`timeout`／`interval`／`on_fail` 只屬於有等待的步驟：找圖三態，以及寫了 `confirm` 的
  `click`／`drag`；沒寫 `confirm` 的點擊、拖曳寫了這三個會讀不進來。
- `pick` 的 `top`／`left`／`near` 三選一；`color` 只能寫 `true`（不比色就不寫）。
- `drag` 沒有 `update_origin`：拖曳的終點一律成為新原點。
- 已退場、讀不進來（也不要寫）：按鍵步驟、絕對座標、以原點為基準的矩形、九宮格、出現等候上限、
  `threshold`、滑鼠鍵與連點、補做間隔／忙碌出現等候／開始延遲／避開游標（四者是固定行為）、`待重拍_` 前綴。

### 範本命名

- 範本名＝`templates/` 裡的檔名（不含 `.png`），平面名稱、沒有資料夾層級，一份流程內唯一
  （Windows 檔名不分大小寫，`Btn` 與 `btn` 算撞名）。
- 不能有 `\ / : * ? " < > |`，開頭結尾不能是空白，結尾不能是 `.`。
- 被引用的範本＝步驟的找圖目標＋`confirm: {appear}` 的確認圖＋`calibration`（含 fallback）＋`busy`。
  app 存檔時 `templates/` 只留被引用的圖；引用了卻沒有圖的，檢查指令列成「要在 app 截的範本」，
  app 照樣開得起來、執行時擋下。

## 座標相對誰

存在 flow.yaml 裡的座標沒有一個是螢幕座標（`scan_region` 除外）：

| 欄位 | 相對誰 | 尺度 |
|---|---|---|
| `within`（步驟、確認圖、`busy`）、`template_pos` | `座標基準點`（`校準對`第一張的中心） | 流程尺度 |
| `click`、`drag`、`to`、`pick: {near}` | `原點`（執行到這一步時的） | 流程尺度 |
| `offset` | 這一步找到的框的中心 | 流程尺度 |
| `scan_region` | 螢幕 | 螢幕像素 |

執行時先`校準`：在搜尋範圍裡找校準對兩張圖，中心距離 ÷ `baseline`＝`畫面倍率`，第一張的中心＝座標基準點。
落點＝基準（基準點、原點或框中心）＋偏移×畫面倍率。找不到校準對就改量 `fallback`（印警告照跑），
都找不到、或倍率在`支援倍率範圍`（×0.85～×1.15）外，一個輸入都不送。所以流程裡的數字不必隨視窗位置或
大小改；但也因此**不能猜**——沒量過的座標寫進去就是點錯。

## 執行語意

### 步驟依序執行，區段巢狀

步驟從上到下執行一遍＝一`輪`，`run` 決定跑幾輪。區段（`repeat`、`branch`）必須完整巢狀，yaml 的縮排就是巢狀。

### 找圖三態

找圖步驟每 `interval` 秒截一次搜尋範圍、執行一次它的`找圖目標`（限定範圍 → 匹配 → 比色 → 挑選規則），
直到挑到或 `timeout` 秒到：

- `find_click`：挑到就點（框中心＋`offset`）。
- `find`：挑到就往下，不點。
- `wait_gone`：**必須先看到**挑中的那個，之後**那個位置**不再有匹配才通過（畫面別處的同款不算）；
  從頭到尾沒看到＝逾時（不是成功）。

逾時走 `on_fail`。`pick: {top: N}` 匹配不足 N 個＝這次沒挑到，繼續輪詢——不會退而點別個。

### 找不到時：`on_fail` 與跳出

- `stop`（沒寫）：停止整個流程。
- `skip`：這一步當作沒事，往下一步。
- `break`：跳到**最內層**所屬區段結尾之後；跳出 `repeat`＝放棄剩餘次數（不是 continue）。
  不在任何區段內時等同 `stop`。
- 區段的 `on_break: break`：因 `break` 抵達這個區段結尾時，連外層區段一起跳出（可一路往外傳；
  傳出最外層＝停止流程）。正常走到區段結尾不受影響。

`on_fail` 也是`生效確認`逾時的處置。

### 分岔怎麼選分支

`branch` 一次輪詢所有分支的 `if`（同一張截圖），先挑到的那個分支走；同一張截圖裡有好幾個成立時，
**排在前面的優先**。選中後執行那個 `if` 步驟本身（`find_click` 就會點），再執行它的 `then`。

- 等待時間＝各 `if` 的 `timeout` 取最大，輪詢間隔取最小。
- 全部逾時：任一個 `if` 是 `on_fail: stop`（沒寫）＝停止流程；否則跳過整個分岔
  （分岔設了 `on_break: break` 時改成往外跳出）。
- 分支裡後續步驟 `on_fail: break`＝跳到這個分岔結尾之後。

### `原點`與 `update_origin`

原點＝最近一個會更新原點的步驟產生的位置：

| 步驟 | 產生的原點 |
|---|---|
| `find_click` | 點擊位置（框中心＋`offset`） |
| `find` | 框中心＋`offset` |
| `wait_gone` | 最後一次看到的位置＋`offset` |
| `click` | 點擊位置 |
| `drag` | 終點（一律更新） |

`update_origin: false` 的步驟不更新原點（拖曳不能關）。`wait`、區段標記不影響原點。
原點不跟著區段重置：`repeat` 第二輪起的原點是上一輪結尾的那個。

以原點為基準的步驟（`click`、`drag`、`pick: {near}` 的找圖）執行時還沒有任何原點＝無法執行（跳過並寫紀錄）；
檢查指令把它列成錯誤。

### 生效確認 `confirm` 與補做

送出輸入（`find_click`、`click`、`drag`）之後判定遊戲有沒有接受，在 `timeout` 秒內：

| 值 | `find_click` | `click`／`drag` |
|---|---|---|
| `gone` | 被點的那個位置不再有匹配 | `原點的圖離開`：產生目前原點的那個找圖目標離開它挑中的位置（原點必須來自找圖） |
| `next` | 下一步的找圖目標找得到（下一步必須緊接著是找圖步驟） | 同左 |
| `{appear: …}` | `確認圖`找得到（near 相對操作後的原點） | 同左 |

還沒生效時`補做`：重送同一個輸入（找圖點擊的目標已離開原位就不補）。補做要過兩道門：
距上次輸入已過 1 秒，且畫面上沒有 `busy`（忙碌指示）。逾時仍沒生效＝走 `on_fail`。
座標點擊／拖曳的補做落點以第一次輸入前的原點計算。

### 忙碌檢查 `busy_check`

勾了的步驟：輸入 → 等忙碌指示 → 生效確認。等法：送出後 1 秒內輪詢 `busy`，一次都沒看到＝放行；
看到就等它消失（挑中的位置不再有匹配），從送出起 60 秒等不到＝停止流程。補做重送後不再另等。
有步驟勾了、流程卻沒有 `busy`＝執行前擋下。找圖的等待（含分岔、生效確認、`wait_gone`）**不看**忙碌指示，
逾時照常計時。

## 常見寫法

### 定位找圖接相對座標

點不到圖的地方（空白處、只差數字的列）先找一張畫面上唯一、位置固定相對的圖當`參考點`，
用 `find`（不點、更新原點），再用相對座標點：

```yaml
  - {find: 进驻总览, within: [70, 79, 202, 140]}
  - {click: [265, 472], confirm: next}
```

插進流程中段時，插入段自己先定位，不要沿用前面某個不相干步驟留下的原點。

### 可選彈窗：一個分支的分岔

可能出現、也可能不出現的彈窗寫成只有一個分支的分岔：`if` 找不到就跳過（`on_fail: skip`），
分支裡後續失敗就跳出（`on_fail: break`）：

```yaml
  - branch:
      - if: {find: 线索交流结果, within: [210, 91, 840, 150], timeout: 1.5, on_fail: skip}
        then:
          - {find_click: 返回, within: [-28, -9, 117, 132], timeout: 5, on_fail: break}
          - {wait: 0.8}
```

一串可能依序出現的彈窗（登入的簽到、活動、公告）：`repeat` 包一個多分支的分岔，分岔
`on_break: break`——全部都沒出現（逾時跳過）時連 `repeat` 一起跳出：

```yaml
  - repeat: 6
    steps:
      - branch:
          - if: {find_click: 签到关闭, within: [1101, 49, 453, 221], confirm: gone, timeout: 5, on_fail: skip, busy_check: true}
          - if: {find_click: 公告关闭, within: [1449, 36, 136, 136], confirm: gone, timeout: 5, on_fail: skip, busy_check: true}
        on_break: break
```

### 巢狀重複跳出後的動作

`repeat` 裡的步驟 `on_fail: break` 只跳出最內層。要「裡面找不到就整個結束外層」時，在內層區段設
`on_break: break`；不設（`continue`）則停在內層結尾之後、外層照常下一輪。

### 忙碌檢查該勾哪些步驟

工具與 app 都不自動勾，由寫流程的人判斷。任一成立就勾：

1. 這一步之後，影片（或實際畫面）看得到忙碌指示（明日方舟底部「正在提交反饋至神經……」）。
2. 這一步是送伺服器的操作：領取、收穫、確認購買／加速、關簽到或公告（會領獎）、換班的 ⇄、
   會載入資料的翻頁或捲動。

只是切畫面、開選單、找圖不點的步驟不勾。勾錯的代價不對稱：多勾只多等最多 1 秒，漏勾會在遊戲忙時
送出輸入被吃掉（例：換班的列名在忙碌時仍看得到，找圖第一輪就找到、馬上點，點擊被吃掉）。

四份在用流程（`%USERPROFILE%\AutoClick\` 的早／晚 × 簡中／繁中）勾的步驟，按用途：

| 步驟（範本或動作） | 出現在 | 為什麼勾 |
|---|---|---|
| 關掉登入彈窗：签到关闭、活动关闭、公告关闭（繁中：圓形叉叉、獲得物資） | 早兩份的開頭彈窗分岔；晚兩份第一步 | 關簽到會領獎、送伺服器，下一個彈窗要等它回應才出現 |
| 获得物资之後點空白處關結算 | 早_簡中開頭彈窗分岔 | 領取物資的結算，關掉時遊戲還在提交 |
| 基建待辦的收穫：可收获、干员信赖（繁中：可收穫、幹員信賴） | 四份的「repeat 3 ＋ 分岔」 | 收取＝送伺服器，連續收時下一個要等上一個完成 |
| 無人機加速的「确定／確定」 | 四份 | 加速＝送伺服器，之後才能點「收取」 |
| 传递线索（繁中：傳遞線索） | 早兩份 | 前面剛收完、置入完線索，遊戲常還在提交；點下去要等它忙完才會開傳遞頁 |
| 進駐總覽換班：各設施列的 ⇄ 點擊（相對列名或「非工作区」的 `click`） | 四份 | 換班＝送伺服器；忙碌時列名還看得到，不等就會點掉下一個 ⇄ |
| 進駐總覽的捲動拖曳（`drag … confirm: gone`） | 四份 | 換班後清單重載，忙碌中拖曳會被吃掉、後面的相對點擊點錯列 |

（「訂單交付」在四份裡都沒勾，實跑沒出過問題；不代表它不送伺服器，新流程照上面的標準判斷。）

### 固定矩形的餘裕

`within` 不要貼著範本框：每邊至少多出範本寬高的 20%（`拾取檢查`的矩形餘裕；倍率在 ×0.85～×1.15
之間變動時圖還在框裡）。影片轉流程產的框是每邊外推 50%（範本的 2 倍寬高、中心不變）。

會捲動、內容每次會變的清單（好友列表、每輪換一列）把框沿捲動方向拉長到涵蓋整段：

```yaml
  - {find_click: 访问基建, within: [1084, -19, 126, 920], pick: {top: 1}, timeout: 15}
```

手改時不知道該框多大就**不寫 `within`**（＝整個搜尋範圍），請使用者在 app 裡框；不要猜一個矩形。

### 備用校準對

主校準對選遊戲畫面內兩張相距夠遠的固定圖（主畫面的設定鈕＋倉庫）；標題列的圖示＋關閉鈕任何畫面都在，
但量到的倍率偏小約 0.4%，放在 `fallback`。開頭被彈窗蓋住主對時改用備用對、印警告照跑：

```yaml
calibration:
  pair: [主画面设置钮, 主画面仓库]
  baseline: 1719.2
  fallback: {pair: [標題列圖示, 標題列關閉鈕], baseline: 1650.0, offset: [33, 61]}
```

`offset` 與 `baseline` 由 app 的「設定校準對」或影片轉流程量出來，不要手寫。
