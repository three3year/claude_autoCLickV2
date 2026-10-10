# 盤點示範影片與驗證產物能給基準集什麼

Type: task
Status: open

## Question

AFK 盤點，為 08（基準集重製方法）備料：
- 示範影片都在 oCam Video 資料夾（見 memory；路徑含中文，cv2 要用 imdecode 讀）。列出四份流程各對應哪些影片檔、
  長度、解析度、幀率是否可變（demo4 是；逐幀順序讀才準）。
- 四份流程的 `templates/_meta.json`（拍攝位置）與影片轉流程留下的驗證產物（`.scratch/video-to-flow/`、
  `.scratch/scale-range/results/` 等）裡，有沒有「範本 ↔ 影格編號 ↔ 框」的對應可以直接當基準集答案。
- 現有基準集 52 案例的類型分布（同款多個、跨集、縮放、比色、線索背景、計數、混淆、負樣本、繁中、全螢幕）與
  `tools/build_arknights_benchmark.py` 的案例格式；哪些類型能從影格重現、哪些不能（例：縮放 70%/140% 的畫面影片裡沒有）。
- 影格乾淨度：游標、點擊特效、半透明彈窗的比例。

Answer：一張表（流程 → 影片 → 可用對應）＋現有案例類型清單＋做不出來的類型。不做決定。
