# 10 — 文件收尾與打包冒煙

**What to build:** 把詞彙與決策落地成文件,重新打包,並在打包版上實際跑一次確認交付物真的送到了使用者手上。

詞彙:`流程`與 flow pack 合一了——存檔就是流程的唯一實體,flow pack 這個詞退場。範本庫從詞彙表消失,工作區進來。

ADR 一篇,涵蓋兩件事:流程存檔自包自足、引擎改收`範本清單`。要記下取捨——放棄多截圖登錄品質與跨流程共用同一份圖,換得「一個檔案就能搬」。

**Blocked by:** 06, 07, 09

**Status:** ready-for-human

- [x] `app/CONTEXT.md`:刪除 flow pack 詞條,改寫`流程`與`範本`詞條,新增「工作區」等新詞
- [x] `CONTEXT-MAP.md`:詞彙界線段落同步更新(app 的範本不再是 profile 範本庫裡的檔案;引擎不再掃目錄)
- [x] `app/CLAUDE.md` 的架構、踩坑與慣例段落更新(範本庫、登錄產物目錄、匯出動作等已不存在的東西要清掉)
- [x] 新增一篇 ADR,涵蓋兩件事並記下取捨與已知代價(40 個範本降級、跨流程共用變複製、切流程重登錄、孤兒範本消失)
- [x] 重新打包(交付物＝整個打包資料夾),打包前先從原始碼跑過一次
- [ ] 打包版冒煙:實際開啟一份轉換後的流程、跑一小段,確認`範本預載`與點擊落點正常
- [ ] 真實輸入的冒煙前先確認使用者不在使用電腦
- [x] 全套測試(引擎與 app)綠燈

## Comments

- 文件：`app/CONTEXT.md`（flow pack 詞條退場，改寫`流程`／`範本`／`profile`，新增`工作區`與`步驟草稿`）、`CONTEXT-MAP.md`（詞彙界線與引擎公開 API 段落）、根目錄 `CONTEXT.md`（模板庫改為「呼叫端交付的模板清單」、基準測試集自帶模板圖）、`app/CLAUDE.md`（架構／坑／慣例／建置部署／測試手法全段更新）。
- ADR：`docs/adr/0006-self-contained-flow-file-and-engine-template-list.md`，涵蓋兩件事並記下四項已知代價與四個被拒的替代方案。
- 打包：`app/build.bat` 的 seeding 步驟改成只建 `flows/` + 複製 `config.yaml`（沒有範本庫與登錄產物要複製了）。已重新打包（PyInstaller 直接跑，見 memory `build-bat-encoding`）；**打包前把使用者資料移出 `dist/AutoClick/`**（`--noconfirm` 會整個重建它），打包後放回。
- 打包版冒煙（**不注入任何輸入**）：`AutoClick-noUAC.exe` 開起來、引擎 5.71s 就緒（非 coarse-only）、草稿 44 步與工作區 17 個範本都在、面板列的是本流程的平面範本清單、工具列沒有「匯出」也沒有「＋資料夾」、關閉 exit 0。畫面存證：`.scratch/self-contained-flow-file/packaged-smoke.png`。
- 全套測試（引擎 + app）352 個綠燈。

## 未完成（等使用者）

- [ ] **真實輸入的冒煙**（實際跑一小段、確認點擊落點）：量到 idle 只有 160 秒、前景是 VS Code ⇒ 使用者正在用電腦，依既有紀律（memory `packaged-smoke-user-present`）沒有注入滑鼠事件。等使用者離開電腦時補跑。
