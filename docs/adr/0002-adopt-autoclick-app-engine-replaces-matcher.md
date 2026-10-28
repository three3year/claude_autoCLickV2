# ADR 0002:autoClick 應用整包移植入本 repo,辨識全面改用引擎

Status: accepted(2026-08-15)

## 決策

1. **應用與引擎同 repo**。autoClick(外部專案,7,500 行 Tkinter 應用)整包
   搬入頂層 `app/`,其內部 `engine/` 子套件改名 `automation/`(點擊、截圖、
   流程執行)——「引擎」一詞在本 repo 專指 `subject_detection`。移植採
   「整包搬移再改造」:原始碼與測試照搬,只改辨識接縫,行為保真優先。
2. **舊 matcher 完全移除,辨識單一路徑走引擎**。所有找圖步驟
   (find_click / wait_gone / confirm / branch)經 `Engine.query` 兩階段管線;
   不保留舊模板比對作為選項或備援(舊比對的誤判正是要換掉的理由;
   並行保留的舊 app 本身就是後援)。
3. **門檻語意上移至 profile**。步驟層級的 `threshold` 欄位廢除,匹配門檻
   一律用 profile config(`match_threshold` / `verify_threshold`),遵循
   「先存失敗案例進基準集、以總體成績調參」的紀律。匯入舊 flow 時
   threshold 欄位直接丟棄,不做分數換算(CCOEFF 與驗證餘弦無可靠對應)。
4. **明確不做**:旋轉比對(rotate=True)與旋轉範本工具、flood-fill 去背工具
   (登錄遮罩已涵蓋其目的)、翻新解析度工具(引擎多尺度已涵蓋範本端;
   固定座標步驟的換算需求出現時再議)、**並行執行**(原實作有 bug 且測試
   不完整,本輪不移植;runner 的 stage 接縫與其測試保留,`ParallelRun`
   與並行 UI 不搬,留待日後重做)。
5. **profile 自帶 flows**。`profiles/<game>/` 除模板庫與 config 外,新增
   `flows/`;flow 內的範本引用只在所屬 profile 有意義。UI 支援 profile
   切換與建立(改名/刪除交給檔案總管)。
6. **舊資料單向匯入**。新 app 能讀舊 flow JSON 與 `.autoclickpack`
   (範本名去 `.png` 副檔名對應;pack 內缺少的範本圖補進 profile),
   讀入後以新格式儲存;不維持雙向相容。`profiles/arknights/templates`
   已是 autoClick 範本庫的多截圖重組版,直接沿用。
7. **發佈照舊 PyInstaller onedir(含 `--uac-admin`),接受體積與延遲**:
   torch CPU 版與 DINOv2 權重隨包(目標機免網路、免裝 Python),安裝包
   GB 級;單次查詢 ~385ms(近全螢幕、純 CPU)。準確與穩定優先於速度,
   速度優化留待實測證明太慢再開票。

## 理由

- 引擎規格原本就把「autoClick 呼叫端改寫與整合」列為引擎完成後的下一步;
  移植動機是舊模板比對在畫面變化下不夠準/穩,且要用上登錄遮罩與深度驗證。
- 接縫天然乾淨:舊 `matcher.py` 是純函式模組,執行期呼叫全集中在
  runner,測試 harness 也在同一接縫造假件——整包搬移的風險小。
- 挖機流程本有 0.5s 輪詢與大量等待,單次數百 ms 對總時長影響有限;
  誤判造成的錯點成本遠高於慢幾百 ms。

## 後續影響

- repo 從單一 context 變成兩個(引擎 / 自動化應用):app 落地時把
  autoClick 的 GLOSSARY.md 一併搬入 `app/`,根目錄建 `GLOSSARY-MAP.md`;
  兩邊字彙需對齊(engine「模板」vs app「範本」、engine「搜尋區域」
  (查詢輸入的裁切影像)vs app「搜尋範圍」(使用者設定的螢幕矩形))。
- 驗收:非並行舊測試全數移植且綠、引擎 bench 38/38 維持不增、
  PyInstaller 包在無 Python 無網路的乾淨機器可啟動。實機 flow 驗證
  由使用者手動進行,不列入自動驗收。
- 舊專案 claude_autoClick 並行保留一段時間作為後援,不再更新。
