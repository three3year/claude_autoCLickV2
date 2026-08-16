# 06 — 開窗關鍵路徑瘦身

**What to build:** 重量級套件(torch、cv2、mss、numpy 等)不得在開窗前
同步 import——隨背景載入或首次使用載入;範本瀏覽器維持啟動時的輕量清單
掃描,但縮圖影像改為視窗顯示後補建,不擋開窗。熱鍵註冊、profile 列舉、
自動存檔載入等輕量啟動工作維持現狀。目標:開窗時間再壓一段,逼近
tkinter 起動的下限。

**Blocked by:** 03 — 視窗先開+引擎背景載入+就緒 gating

**Status:** done

- [x] 主視窗首次映射前,重量級套件未被 import(測試以模組載入狀態斷言)
- [x] 範本瀏覽器清單開窗即見,縮圖在視窗顯示後補上且不閃爍錯位
- [x] 從原始碼量測開窗時間,相對 03 完成時有可感知下降,數據記錄在 Comments
- [x] 所有既有功能(拾取、清場、對話框、執行)不因延遲 import 出現首次使用卡頓以外的行為變化

## Comments

2026-08-16 完成。改動:
- `subject_detection/__init__.py` 改 PEP 562 惰性再匯出——flowpack 經
  `subject_detection.profile` 連帶載入 cv2/numpy 的鏈就是它(最大元兇)
- `automation/capture.py`、`automation/imgio.py`:cv2/mss/numpy 延後到
  首次擷取/讀寫;`ui_dialogs`、`ui_overlay` 頂層 cv2 移入使用的函式
- 縮圖佔位圖改純 Python PPM(不動用 numpy);實際縮圖本就只在
  「選取範本」時載入,開窗路徑不經過
- 熱鍵註冊維持現狀(pynput 實測僅 44ms,不值得動)
- 新增 `_slim_probe.py` 子程序探針測試:App 首次映射後斷言
  cv2/mss/torch/numpy 皆不在 sys.modules(cv2 假引擎工廠隔離背景載入)

量測(原始碼、熱):模組 import 0.19s→0.09s,開窗 1.28s→**1.18s**;
打包版收益更大(frozen cv2 DLL 載入成本較高),見票 07 實測。
