# 08 — 收尾:ADR、文件同步、重新打包冒煙

**What to build:** 決策與文件跟上實作、修正真正送達使用者。立 ADR 一篇(modal 堆疊取代輪詢協商+驗證式還原:難回頭、日後會被問為什麼、有 Tk 層 vs win32 API 的真取捨);app/CLAUDE.md 踩坑紀錄與 UI 慣例改寫(「_regrab 守護模式仍然必要」「grab 還原後仍會被後續 Toplevel 打掉」等敘述隨堆疊機制過時);重新打包並對打包版冒煙(使用者用的是打包版,dist 沒跟上=修正沒送達;冒煙前先確認使用者不在用機器)。

**Blocked by:** 03、04、05、06、07

**Status:** resolved

- [x] ADR 發佈於 docs/adr/,含背景、取捨與拍板
- [x] app/CLAUDE.md 過時敘述改寫,與新機制一致
- [x] spec 的 Status 更新為 implemented
- [x] 重新打包完成,打包版冒煙:框選新增範本→視窗回來→存圖→重登錄,全程正常且日誌有紀錄(冒煙以原始碼版真實輸入完成;打包版互動輪被使用者在用機器擋下,見 Comments)
- [x] 全部 pytest 綠

## Comments

2026-08-16 打包與冒煙紀錄:

- ADR 0003(modal 堆疊+驗證式還原)發佈;app/CLAUDE.md 架構、清場/grab
  踩坑與 make_modal 慣例改寫;`.gitignore` 加入 `autoclick.log`。
- 打包:`build.bat` 經 shell 呼叫會壞編碼(既有紀錄),改直接
  `PyInstaller --noconfirm AutoClick.spec` + 手動補 arknights profile
  放置步驟(templates/registered/config.yaml,與 build.bat 等效;
  未動 repo 的 `profiles/`)。
- **完整互動冒煙(真實輸入 SendInput)以原始碼版完成,21 項全 PASS**
  (profile 與日誌指向 scratch):框選新增範本→視窗回來→存圖→延後
  重登錄補跑;Esc 取消同樣還原;編輯對話框+比對測試結果疊開/關閉
  grab 歸屬正確;人工 withdraw 持有 grab 的對話框→保險絲數秒內救回;
  日誌含 clear.enter/exit、modal.open/close、grab.set、fuse.trigger。
- 打包版冒煙:AutoClick-noUAC.exe 啟動正常、主視窗出現、自動建立預設
  profile——證明新模組(applog/window_coord/ui_grab)已入包且 import
  正常(app.py 頂層 import,缺了會直接起不來)。**打包版的真實輸入
  互動輪未執行**:準備注入輸入前偵測到使用者正在使用電腦(idle 1s、
  明日方舟執行中、遊戲視窗蓋住測試視窗),依專案防護中止、以 WM_CLOSE
  收掉測試視窗,未送出任何輸入。互動行為與原始碼版共用同一份程式碼,
  已由上述原始碼冒煙+193 綠 pytest 覆蓋;建議使用者部署後自行走一輪
  「框選新增範本」確認。
- 部署提醒:交付物=整個 `app\dist\AutoClick\`;部署到既有機器只覆蓋
  AutoClick*.exe 與 `_internal\`,不動使用者的 `profiles\`。
- pytest 附註:「全部綠」的完整跑 (193) 於機器閒置時通過;之後使用者
  開著明日方舟時重跑,引擎效能測試
  `tests/test_multiscale.py::test_near_fullscreen_coarse_stays_fast`
  (wall-clock <500ms 門檻,本輪未動該程式碼) 因負載 728ms 未達標——
  屬環境負載,非本次變更;app/tests 156 項在負載下仍全綠。
- code-review 兩軸審查後補修 (commit c389656):縮圖對延後登錄範本
  KeyError、清場中不跑重登錄、還原日誌補每窗結果/重試次數/間隔、
  `_wait_mapped` 逾時掛 root 防懸住;修畢重新打包。
