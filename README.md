# claude_autoClickV2

兩個部分、一個 repo:**AutoClick**(Windows 桌面按鍵精靈:找圖點擊、步驟序列自動執行,`app/`)
與它用來找圖的**主體偵測引擎**(遊戲無關,`src/subject_detection/`)。上半給要跑 AutoClick 的人,
下半給要改引擎的人。詞彙:引擎看 [CONTEXT.md](CONTEXT.md)、應用看 [app/CONTEXT.md](app/CONTEXT.md),
兩邊對照見 [CONTEXT-MAP.md](CONTEXT-MAP.md)。

## AutoClick

### 安裝(原始碼版)

Windows、Python 3.11 以上(pyproject 的 `requires-python`;3.12 驗過)。只想打包可以略過這段,直接看
「打包與部署」,build.bat 會自己建好同一套環境。

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[app,dev]"
.venv/Scripts/pip install torch --index-url https://download.pytorch.org/whl/cpu
```

torch 給引擎的驗證階段用(DINOv2-S,第一次啟動時從 torch.hub 下載權重並快取在本機
`%USERPROFILE%\.cache\torch\hub\`);沒裝 torch 引擎退化成「僅粗篩」,照常可用但精確率下降。
有 NVIDIA GPU 裝 CUDA 版即自動用 GPU。只要跑打包版就不必裝這些:見「打包與部署」。

### 啟動

```bash
.venv/Scripts/python app/app.py
```

視窗先開、引擎在背景載入(幾秒);就緒前執行與比對測試等辨識功能會提示並拒絕。開 app 自動開上次的流程,
第一次開或上次的流程不在了就是空白新流程。F12 急停。打包版的啟動方式見「打包與部署」。

### 流程

一份流程＝一個資料夾,佈局、欄位、執行語意的唯一正本是 [docs/flow-format.md](docs/flow-format.md);
開檔選資料夾裡的 `flow.yaml`。
引擎參數＝引擎內建預設,流程要改就在 `flow.yaml` 寫 `engine:` 段覆蓋(app 沒有編輯 UI,原樣保留)。

手改或自動產出的流程用檢查指令驗(不載引擎、不開視窗):

```bash
.venv/Scripts/python tools/flow_check <流程資料夾>
.venv/Scripts/python tools/video_to_flow --help      # 影片轉流程 (由 skill 驅動, 不進 app)
```

這兩個命令列工具只有原始碼版有;打包版只有 app 本體,沒有附帶任何命令列工具。

### 使用者資料在哪

| 什麼 | 打包版 | 原始碼執行 |
|------|--------|-----------|
| 流程存放區(開檔、新流程第一次存檔的預設位置) | exe 往上找得到本 repo 就是 repo 的 `flows\`,找不到 `%USERPROFILE%\AutoClick\` | repo 的 `flows\`(不進 git) |
| 本機狀態(`state.json` 只記上次開的流程)、日誌 `autoclick.log`、還沒存檔的新流程的截圖快取 `unsaved\` | `%LOCALAPPDATA%\AutoClick\` | repo 的 `.local\`(不進 git) |

打包版放在 repo 裡(app 的 dist 底下)時,打包版與原始碼執行看到同一組流程,但本機狀態各一份:
從原始碼開過的流程不會變成打包版下次自動開的那份。流程資料夾也可以放在別處,存放區只是預設。
點錯、找不到圖、輸入被吃掉先看 `autoclick.log`(`find.target`、`input`、`busy.check`、`calibrate`
幾種紀錄,超過 1MB 輪替一份);打包版開不起來或引擎沒就緒看同一份日誌的 engine.load.start /
engine.load.done(`coarse_only=True` 表示隨包的 DINOv2 沒載成功,退化成僅粗篩)。

### 打包與部署

**打包**:第一次 clone 直接雙擊 `app\build.bat`,缺的環境它自己補(約 3–5 分鐘 ＋ 第一次下載的時間)。
它只轉交給 `tools/build`:缺 `.venv` 就用機器上的 Python(3.11 以上,沒有或太舊會停下來告訴你)建一個並裝依賴
(含 PyInstaller);有 NVIDIA 顯卡裝 CUDA 版 torch、沒有裝 CPU 版;缺 DINOv2 權重就先下載(不開視窗、不動流程與
本機狀態);然後 PyInstaller onedir 打包。以後每次雙擊都順便補齊缺的東西,離線時只要都齊了照常打包。每一步開始都
印在視窗裡,結束視窗停住。重新打包會整個換掉 app 的 dist 底下的舊版,先關掉正在跑的 AutoClick。agent 跑同一支
工具 `python tools/build`,見 [app/CLAUDE.md](app/CLAUDE.md)「建置與部署」。

**交付物**:app 的 dist 底下整個 AutoClick 資料夾(從有 NVIDIA 的機器打約 3 GB,CUDA 的 DLL 隨 torch 進包;
沒有的約 700 MB),裡面只有三樣:

| 什麼 | 用途 |
|------|------|
| AutoClick.exe | 正式用。開啟時跳 UAC,管理員權限是對高權限視窗送滑鼠事件所必需(不提權點擊會被系統無聲丟棄) |
| AutoClick-noUAC.exe | 只給自動化冒煙用(UAC 會擋自動啟動);對高權限視窗的點擊會被丟棄,不作正式使用 |
| _internal 資料夾 | 兩個 exe 共用的程式、torch 與 DINOv2 權重;exe 離開它就開不起來 |

**使用**:目標機免 Python 免網路,整個資料夾放哪都行、要搬就整個搬,執行 AutoClick.exe 即可。
放在 repo 裡用的是 repo 的 `flows\`,拿到沒有 repo 的電腦用 `%USERPROFILE%\AutoClick\`(見上表);
本機狀態與日誌都在 `%LOCALAPPDATA%\AutoClick\`,資料夾裡沒有使用者資料,**部署＝關掉 AutoClick、
整個資料夾換掉**,流程與日誌不受影響。要驗一包好不好,開起來看日誌有 engine.load.done 且
`coarse_only=False`,開一份有範本的流程後紀錄區出現「範本就緒」。

## 主體偵測引擎

在螢幕截圖的指定範圍內,判斷某張預先登錄的模板主體是否存在並回報位置。遊戲無關:引擎只實作「怎麼找」,
模板圖、搜尋區域、預期尺度都由呼叫端交付(ADR 0006、0015);引擎參數只有內建預設加呼叫端的覆蓋。

### 使用

```python
from subject_detection import Engine

engine = Engine()                                   # 驗證模型載入一次, 常駐
library = engine.load_templates(
    {"返回": "flows/某流程/templates/返回.png"},      # 範本清單: 範本名 → 一張圖
    config=None,                                    # None＝內建預設; 或合併好覆蓋的 dict
    artifacts_dir="flows/某流程/.cache/registered")  # 登錄產物放哪 (過期自動重算)
result = engine.query(library, "返回", search_region_bgr,   # np.ndarray (BGR)
                      color_check=False,            # 選填: 比色 (ADR 0007)
                      expected_scale=1.0)           # 選填: 預期尺度 (ADR 0009)
result.found     # bool
result.box       # (x, y, w, h), 搜尋區域座標系; 最佳匹配
result.score     # 驗證分數 (嵌入餘弦相似度; 僅粗篩模式是粗篩分數)
result.matches   # 所有匹配 (Match: box, score, color), 最佳在前
result.failed    # 沒找到時擋在哪一關: "match" / "verify" / "color"
result.debug     # match_score / verify_score / candidates (除錯用, 格式不承諾穩定)
```

每次查詢針對單一模板、單一搜尋區域;搜尋區域由呼叫端裁好傳入,匹配有多個時取哪個是呼叫端的事。
給了預期尺度就只掃以它為中心的 5 個尺度(每格 ×1.09),沒給就照 `scale_range` 全掃。

### 接上一個呼叫端

1. 呼叫端自己管模板圖,交給引擎的是**範本清單**(範本名 → 一張圖的路徑);引擎不掃目錄。
   **一個模板只有一張圖**(ADR 0016;給清單會報錯),登錄用單張梯度啟發式產生遮罩。
2. 引擎參數＝`default_config.yaml` 的內建預設;要改就把合併後的 dict 交給 `Engine.load_templates`
   的 `config`(AutoClick 用流程的 `engine:` 段覆蓋,`App.engine_config` 合併)。
   交付已退場的鍵(例:mask_strategy)會報錯。
3. 沒有手動登錄步驟:`Engine.load_templates` 依圖的內容 hash 與登錄相關參數判斷產物過不過期,只重算受影響
   的那張;產物寫在呼叫端指定的 `artifacts_dir`,整個刪掉會自動重建。單張隨用走 `Engine.register`。

### 引擎參數與調參

改預設就改 `src/subject_detection/default_config.yaml`,改完重跑即生效,不碰引擎程式碼。

| 症狀 | 看哪個分數 | 調哪個參數(預設) | 方向 |
|------|-----------|-----------------|------|
| 漏抓,`match_score` 低 | 粗篩 | `match_threshold`(0.6) | 調低 |
| 漏抓,match 高但 `verify_score` 低 | 驗證 | `verify_threshold`(0.8) | 調低 |
| 漏抓,候選尺度貼在範圍邊界、且查詢沒給預期尺度 | 粗篩 | `scale_range`([0.5, 2.0]) | 放寬 |
| 漏抓,畫面有長寬比失真 | 粗篩 | `aspect_jitter`(0.1) | 調大 |
| 誤判(不存在卻回報存在) | 驗證 | `verify_threshold` | 調高 |
| 誤判(位置錯) | 粗篩 | `match_threshold` | 調高 |
| 開比色仍分不開顏色 | 比色 | `color_threshold`(0.95) | 調高 |
| 太慢且查詢沒給預期尺度 | — | `scale_range` | 縮窄 |

會觸發重新登錄的參數只有 `scale_range`(產物自動過期重算);三個門檻只在查詢時讀。

調參紀律:(1) 遇到失敗案例先存進基準測試集,再調參;(2) 以整體數字為準,不對單一案例調;
(3) 只動參數——必須改引擎程式碼才達標就是引擎通用能力的缺口,回頭修引擎並補測試,不塞遊戲特例。

### 基準測試集

引擎品質唯一的客觀驗收。住在 repo 根目錄 `benchmark/`:範本取自在用流程、畫面取自示範影片的真實影格
(ADR 0016),照類型配額(一般正例、同款多個、比色、忙碌指示、線索背景、混淆、縮放 ×0.85／×1.15、
易誤判負樣本、跨影片),簡中、繁中各半。案例 = 一個資料夾,加案例不改程式:

```
benchmark/<案例名>/
    template.png      # 這個案例的範本圖 (每個案例自帶, 不依賴任何模板庫)
    screenshot.png    # 查詢用的搜尋區域影像
    expect.yaml       # expected: present | absent
                      # center: [x, y]        (present 時必填, 主體中心)
                      # centers: [[x, y], …]  (同款多個: 全中且不能多)
                      # tolerance: 15         (px, 選填)
                      # color_check: true     (選填: 開比色)
                      # expected_scale: 1.15  (選填: 預期尺度, 沒寫＝1)
                      # known_failure: 原因   (選填: 已知的引擎弱點, 分開報)
                      # source: {...}         (給人看, 執行器不讀)
```

```bash
.venv/Scripts/python -m subject_detection.bench      # 不帶參數＝repo 的 benchmark/; -v 附除錯分數
```

引擎參數只用內建預設、不讀任何設定檔;`_` 開頭的資料夾是登錄快取,不進版控。結束碼 0 ＝除已知失敗外
全部命中且零誤判;報表把已知失敗分開列,已知失敗這次通過的標「可拿掉標記」。不接進 pytest,手動跑。
改引擎前後必跑與基線比對的規則在根目錄 [CLAUDE.md](CLAUDE.md)。影格髒的(游標壓到主體、轉場)不收案例。

### 架構(兩階段查詢)

1. **登錄**(離線、自動):單張梯度啟發式 → 有效像素遮罩;參考圖＋遮罩＋主體嵌入向量存於呼叫端指定的
   `artifacts_dir`,以圖的 hash 與 `scale_range` 判斷過期。
2. **粗篩**(保召回):梯度域(Scharr)多尺度模板匹配,粗掃降採樣影像後於原解析度帶遮罩精修,
   天然抗亮度／色偏;給了預期尺度只掃它附近。
3. **驗證**(保精確):DINOv2-S 嵌入相似度比對候選框與模板主體(雙方套遮罩),刷掉粗篩假陽性;
   要求比色時再以彩色整張模板比一次。

### 測試

```bash
.venv/Scripts/python -m pytest        # 引擎 tests/、app/tests/、tools/tests/ 一起 (pyproject 的 testpaths)
```

CPU 可跑、不依賴 GPU。app 的測試會開真的 Tk 視窗,在隱藏桌面跑的做法見
[docs/agents/app-testing.md](docs/agents/app-testing.md)。
