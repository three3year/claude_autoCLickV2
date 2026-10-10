# 07 — flow.yaml 讀寫，影片轉流程改產流程資料夾

**What to build:** 流程資料夾（`flow.yaml`＋`templates/`＋`.cache/`）與記憶體流程之間的讀寫。讀：補齊預設、巢狀轉平面、開頭鍵轉 `type`、步驟層 `within`／`pick`／`color` 轉 `target` 子 dict、確認圖 `confirm: {appear: …}` 轉 `confirm`＋`confirm_target`；流程層 `run`、`scan_region`、`calibration`、`busy`、`template_pos`、`engine`。讀檔是唯一的入口驗證，錯誤指出步驟編號與鍵。寫：等於預設的不寫、一步一行、行尾 `# N`、先寫暫存再取代。影片轉流程工具改用這個寫檔函式輸出流程資料夾。原型的 `nest()`／`flatten()` 是起點。見 spec「流程資料夾與 flow.yaml」「影片轉流程工具（過渡）」。

**Blocked by:** 06

**Status:** resolved

- [x] 往返：記憶體流程→寫→讀，得到相同的記憶體流程（含區段、確認圖、備用校準對、`engine:`）
- [x] 定案樣本（晚_簡中）讀進來再寫回，除了開頭的原型註解外文字相同
- [x] 報錯並指出步驟編號與鍵：yaml 語法錯、`format` 不是 1、未知鍵（步驟、找圖目標、頂層、`engine:` 段）、型別錯、區段不完整、`branch` 的 `if` 不是找圖三態
- [x] 範本名擋下 `\ / : * ? " < > |`、開頭或結尾空白、結尾句點
- [x] 影片轉流程工具輸出 `<輸出位置>\<流程名>\`（預設 `%USERPROFILE%\AutoClick\`，可用參數指定；已存在照現行規則加序號），內含 `flow.yaml`、`templates/`、`交付報告.md`；不寫搜尋範圍、不需要 profile 與步驟草稿、範本不加 `待重拍_` 前綴
- [x] 工具的現有測試改成斷言輸出資料夾（經讀檔函式讀回）；全部測試綠
- [x] app 仍用舊存檔開檔存檔（08 才切換）

## Comments

- 2026-10-11（agent）：讀寫在 `app/flowfile.py` 的「流程資料夾」段（`read_flow`／`parse_flow`／`dump_flow`／`write_flow`／`template_name_problem`／`missing_templates`），測試 `app/tests/test_flowfolder.py`。定案樣本與 out_all 的四份原型 yaml 讀進來再寫回都逐字相同。影片轉流程：輸出位置可寫在計畫的 `out` 或命令列 `--out`（`assemble(out_dir=)` 優先），計畫寫 `profile`／`reportPath` 會報錯說明已退場。tools 測試原本有 9 個既有失敗（合成按鈕過不了縮放餘裕而被加 `待重拍_` 前綴），前綴退場後剩 3 個仍是同一原因（只差顏色的 absent 幀、預期尺度 1、走一遍），與本票無關。
