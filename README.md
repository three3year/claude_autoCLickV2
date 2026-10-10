# Subject Detection Engine(圖像主體偵測引擎)

在螢幕截圖的指定範圍內,判斷某張預先登錄的模板主體是否存在並回報位置。
遊戲無關:引擎只實作「怎麼找」,所有遊戲知識(模板庫、尺度、閾值)住在
遊戲設定檔資料夾。詞彙表見 [CONTEXT.md](CONTEXT.md)。

本 repo 另含自動化應用層 **AutoClick**(`app/`,Tkinter 桌面工具:流程編輯、
截圖建範本、找圖點擊、F12 急停),辨識全面走本引擎(ADR 0002)。
兩個 context 的對照見 [CONTEXT-MAP.md](CONTEXT-MAP.md)。

## AutoClick 應用

```bash
.venv/Scripts/pip install -e .[app]        # 另需 mss / pynput
.venv/Scripts/python app/app.py            # 從原始碼啟動
```

- 一份流程＝一個資料夾:`flow.yaml`(步驟與流程設定)+ `templates/`(範本圖)+ `.cache/`
  (可重建的快取)。預設放在 `%USERPROFILE%\AutoClick\`;開檔選資料夾裡的 `flow.yaml`。
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
profile = engine.load_profile("profiles/arknights")   # 自動補登錄
result = engine.query(profile, "cn/返回", search_region_bgr)  # np.ndarray (BGR)
result.found   # bool
result.box     # (x, y, w, h),search_region 座標系
result.score   # 驗證分數(嵌入餘弦相似度)
result.debug   # match_score / verify_score / candidates(除錯用,格式不承諾穩定)
```

每次查詢針對單一模板、單一搜尋區域。搜尋區域由呼叫端裁好傳入
(預期座標、語言選擇等遊戲邏輯留在呼叫端)。

## 新遊戲上手

1. 建資料夾 `profiles/<game>/templates/`,把裁好的模板圖丟進去。
   - 單張圖 = 一個模板(檔名即模板名,可用子資料夾當命名空間)。
   - 同一元素有多組拍攝(不同解析度/介面版本/遊戲狀態)時,建一個
     資料夾放多張圖:`templates/<名稱>/<拍攝1>.png, <拍攝2>.png ...`
     登錄會跨拍攝比對像素穩定度,自動剔除半透明透出背景與可變文字區。
2. 複製引擎預設設定 `src/subject_detection/default_config.yaml` 到
   `profiles/<game>/config.yaml`(保守值,先跑起來)。
3. 程式碼照上面「使用」呼叫即可。**沒有手動登錄步驟**:`load_profile`
   自動偵測新模板、內容變更(hash)、登錄相關參數變更,補跑受影響的登錄,
   產物寫在 `profiles/<game>/registered/`(可整個刪除,會自動重建)。

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
| 半透明/可變區污染 | 登錄 | `mask_strategy` | 用 `multi_capture` 並補第二張拍攝 |

**會觸發重新登錄的參數**:`scale_range`、`mask_strategy`(改完自動重跑,
不用手動)。`match_threshold`、`verify_threshold` 只在查詢時讀取,改動即生效。

## 調參紀律

1. 遇到失敗案例,**先**把它存進 `profiles/<game>/benchmark/`(見下),再調參。
2. 以 bench 整體數字為準,不對單一案例調參(避免過擬合)。
3. 調參只動 config;若必須改引擎程式碼才能達標,那是引擎通用能力的缺口,
   回頭修引擎(並補測試),不要塞遊戲特例。

## 基準測試(bench)

案例 = 一個資料夾丟進 `profiles/<game>/benchmark/`,不用改程式:

```
benchmark/<案例名>/
    screenshot.png    # 查詢用的搜尋區域影像
    expect.yaml       # template: cn/返回
                      # expected: present | absent
                      # center: [x, y]     (present 時必填,主體中心)
                      # tolerance: 15      (px,選填)
```

跑全部案例、輸出總正確率與漏抓/誤判分項:

```bash
python -m subject_detection.bench profiles/arknights      # -v 附除錯分數
```

`_` 開頭的資料夾是素材,不當案例。明日方舟基準集由
`tools/build_arknights_benchmark.py` 產生(確定性,可重生)。

## 驗收紀錄(明日方舟)

- 基準測試集 38 案例(跨模板集互測/合成尺度/色偏/半透明線索卡/可變計數/
  細粒度混淆/負樣本/全螢幕):**38/38 = 100%**(目標 ≥95%),漏抓 0、誤判 0。
- 近全螢幕(1063×789)單次查詢 **~385ms(純 CPU)**,已低於 500ms 目標;
  開發機無 NVIDIA GPU,GPU 數字待有 CUDA 環境補測(只會更快)。
  量測方式:`j0_fullscreen_返回` 案例重複 5 次取平均(暖機後)。
- cn 與翻新模板集已合併:同一元素的兩組拍攝放同一模板資料夾
  (`templates/cn/<名稱>/{cn,翻新}.png`),跨集案例(cn 參考圖 × 翻新尺度場景)
  全數命中——尺度處理做對後,不再需要按解析度維護平行模板集。
- 逐票數字見 `.scratch/subject-detection-engine/bench-log.md`。

## 架構(兩階段查詢)

1. **登錄**(離線、自動):跨拍攝穩定度 → 有效像素遮罩;參考圖 + 遮罩 +
   主體嵌入向量存於 `registered/`。
2. **粗篩**(保召回):梯度域(Scharr)多尺度模板匹配,粗掃降採樣影像後
   於原解析度帶遮罩精修,天然抗亮度/色偏。
3. **驗證**(保精確):DINOv2-S 嵌入相似度比對候選框與模板主體(雙方套遮罩),
   刷掉粗篩假陽性。

測試:`.venv/Scripts/python -m pytest tests/`(CPU 可跑,不依賴 GPU)。
