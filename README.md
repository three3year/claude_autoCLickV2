# Subject Detection Engine(圖像主體偵測引擎)

在螢幕截圖的指定範圍內,判斷某張預先登錄的模板主體是否存在並回報位置。
遊戲無關:引擎只實作「怎麼找」,模板圖、搜尋範圍、預期尺度都由呼叫端交付
(ADR 0006、0015);引擎參數只有內建預設加呼叫端的覆蓋。詞彙表見 [CONTEXT.md](CONTEXT.md)。

本 repo 另含自動化應用層 **AutoClick**(`app/`,Tkinter 桌面工具:流程編輯、
截圖建範本、找圖點擊、F12 急停),辨識全面走本引擎(ADR 0002)。
兩個 context 的對照見 [CONTEXT-MAP.md](CONTEXT-MAP.md)。

## AutoClick 應用

```bash
.venv/Scripts/pip install -e .[app]        # 另需 mss / pynput
.venv/Scripts/python app/app.py            # 從原始碼啟動
```

- 一份流程＝一個資料夾:`flow.yaml`(步驟與流程設定)+ `templates/`(範本圖)+ `.cache/`
  (可重建的快取)。預設放在流程存放區:repo 的 `flows\`(不進 git;
  打包版找不到 repo 時改用 `%USERPROFILE%\AutoClick\`);開檔選資料夾裡的 `flow.yaml`。
- 引擎參數＝引擎內建預設 + 流程 `flow.yaml` 的 `engine:` 段覆蓋。
- 開 app 自動開上次的流程;本機狀態與日誌在 `%LOCALAPPDATA%\AutoClick\`
  (從原始碼執行時在 repo 的 `.local\`)。
- 打包可攜版:`app\build.bat`(PyInstaller onedir,torch CPU 與 DINOv2 權重
  隨包,目標機免 Python 免網路;交付物 = `app\dist\AutoClick\` 整個資料夾,
  以系統管理員權限執行;部署＝整個資料夾換掉,裡面沒有使用者資料)。細節見
  `app/CLAUDE.md`「建置與部署」。

## 安裝

```bash
python -m venv .venv
.venv/Scripts/pip install -e .          # numpy / opencv / pyyaml
.venv/Scripts/pip install torch --index-url https://download.pytorch.org/whl/cpu
```

torch 供驗證階段(DINOv2-S,第一次使用時自 torch.hub 下載並常駐記憶體)。
沒裝 torch 時引擎自動退化為「僅粗篩」模式(精確率下降,照常可用)。
有 NVIDIA GPU 時裝 CUDA 版 torch 即自動使用 GPU。

## 使用

```python
from subject_detection import Engine

engine = Engine()                              # 模型載入一次,常駐
library = engine.load_templates({"返回": "templates/返回.png"},   # 範本清單: 名 → 一張圖
                                artifacts_dir=".cache/registered")  # 登錄產物放哪 (自動補登錄)
result = engine.query(library, "返回", search_region_bgr,  # np.ndarray (BGR)
                      expected_scale=1.0)                   # 選填: 預期尺度 (ADR 0009)
result.found   # bool
result.box     # (x, y, w, h),search_region 座標系
result.score   # 驗證分數(嵌入餘弦相似度)
result.debug   # match_score / verify_score / candidates(除錯用,格式不承諾穩定)
```

每次查詢針對單一模板、單一搜尋區域。搜尋區域由呼叫端裁好傳入
(預期座標、語言選擇等遊戲邏輯留在呼叫端)。

## 接上一個呼叫端

1. 呼叫端自己管模板圖,交給引擎的是**範本清單**(範本名 → 一張圖的路徑);
   引擎不掃目錄。**一個模板只有一張圖**(ADR 0016;多張圖登錄已退場,給清單會報錯)。
   登錄用單張梯度啟發式產生遮罩:有結構的地方留下,平坦區剔除。
2. 引擎參數＝`src/subject_detection/default_config.yaml` 的內建預設;呼叫端要改就
   把覆蓋後的 dict 交給 `load_templates(config=...)`(AutoClick 用流程的 `engine:` 段)。
   沒有的鍵(例:已退場的 `mask_strategy`)交付了就報錯。
3. **沒有手動登錄步驟**:`load_templates` 依圖的內容 hash 與登錄相關參數判斷
   產物過不過期,只重算受影響的那張;產物寫在呼叫端指定的 `artifacts_dir`
   (可整個刪除,會自動重建)。

## 調參:症狀 → 參數

只改 `config.yaml`,不碰引擎程式碼。改完重跑即生效。

| 症狀 | 看哪個分數 | 調哪個參數 | 方向 |
|------|-----------|-----------|------|
| 漏抓,`debug["match_score"]` 低 | 粗篩 | `match_threshold` | 調低(預設 0.6) |
| 漏抓,match 高但 `verify_score` 低 | 驗證 | `verify_threshold` | 調低(預設 0.8) |
| 漏抓,候選尺度貼在範圍邊界 | 粗篩 | `scale_range` | 放寬 |
| 漏抓,畫面有長寬比失真 | 粗篩 | `aspect_jitter` | 調大 |
| 誤判(不存在卻回報存在) | 驗證 | `verify_threshold` | 調高 |
| 誤判(位置錯) | 粗篩 | `match_threshold` | 調高 |
| 太慢 | — | `scale_range` | 縮窄(掃描尺度數下降) |

**會觸發重新登錄的參數**:`scale_range`(改完自動重跑,不用手動)。
`match_threshold`、`verify_threshold` 只在查詢時讀取,改動即生效。

## 調參紀律

1. 遇到失敗案例,**先**把它存進 `benchmark/`(見下),再調參。
2. 以 bench 整體數字為準,不對單一案例調參(避免過擬合)。
3. 調參只動 config;若必須改引擎程式碼才能達標,那是引擎通用能力的缺口,
   回頭修引擎(並補測試),不要塞遊戲特例。

## 基準測試集(bench)

引擎品質唯一的客觀驗收。住在 repo 根目錄 `benchmark/`:97 個案例,範本取自四份在用流程、
畫面取自示範影片的真實影格(ADR 0016),照類型配額:一般正例、同款多個、比色、忙碌指示、
線索背景、混淆、縮放 ×0.85/×1.15、易誤判負樣本、跨影片;簡中、繁中各半。
案例 = 一個資料夾,不用改程式:

```
benchmark/<案例名>/
    template.png      # 這個案例的範本圖 (每個案例自帶, 不依賴任何模板庫)
    screenshot.png    # 查詢用的搜尋區域影像
    expect.yaml       # expected: present | absent
                      # center: [x, y]        (present 時必填,主體中心)
                      # centers: [[x, y], …]  (同款多個: 全中且不能多)
                      # tolerance: 15         (px,選填)
                      # color_check: true     (選填: 開比色)
                      # expected_scale: 1.15  (選填: 預期尺度, 沒寫＝1)
                      # known_failure: 原因   (選填: 已知的引擎弱點, 分開報)
                      # source: {...}         (給人看: 流程、範本、影片、幀、類型)
```

**改引擎(門檻、模型、刪路徑)前後都要跑**,結果要一致(已知失敗可以變少,不能變多):

```bash
.venv/Scripts/python -m subject_detection.bench      # 不帶參數＝repo 的 benchmark/; -v 附除錯分數
```

引擎參數只用內建預設、不讀任何設定檔;`_` 開頭的資料夾是登錄快取,不進版控。
結束碼 0 ＝除已知失敗外全部命中且零誤判;報表把已知失敗分開列,已知失敗這次通過的
標「可拿掉標記」。基準集不接進 pytest,手動跑。

目前基線(2026-10-21,ADR 0016 刪多張圖路徑前後一致):其他案例 80/80,已知失敗 17
(淡入淡出最淡的忙碌字樣、整張畫面找小範本、整顆變暗的按鈕比色擋不住、列名互相像、
範本連暗底一起截);每個已知失敗的原因寫在案例自己的 `expect.yaml`。

## 架構(兩階段查詢)

1. **登錄**(離線、自動):單張梯度啟發式 → 有效像素遮罩;參考圖 + 遮罩 +
   主體嵌入向量存於呼叫端指定的 `artifacts_dir`。
2. **粗篩**(保召回):梯度域(Scharr)多尺度模板匹配,粗掃降採樣影像後
   於原解析度帶遮罩精修,天然抗亮度/色偏。
3. **驗證**(保精確):DINOv2-S 嵌入相似度比對候選框與模板主體(雙方套遮罩),
   刷掉粗篩假陽性。

測試:`.venv/Scripts/python -m pytest tests/`(CPU 可跑,不依賴 GPU)。
