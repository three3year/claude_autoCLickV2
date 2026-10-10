# 12 — 轉換四份在用流程

**What to build:** 一次性轉換腳本放本 spec 同目錄（`convert.py`），把打包版 2026-10-10 的四份 `.autoclickpack`（早_簡中、早_繁中、晚_簡中、晚_繁中）轉成 `%USERPROFILE%\AutoClick\<流程名>\`。自己開 zip 讀舊檔，組成新記憶體模型交 app 的寫檔函式；只處理四份實有的欄位；四份各寫 `engine: {scale_range: [0.6, 1.5]}`；舊 `.md` 逐位元複製成 `交付報告.md`；`_autosave.json` 不轉；輸出資料夾已存在就報錯停下。跑完自我核對。不進 `tools/`、不寫正式測試、跟著提交當紀錄。規則全文見 [轉換工具規則與驗收](../../project-cleanup/issues/11-converter-rules-and-acceptance.md)；起點是 02 的原型轉換腳本。

**Blocked by:** 07

**Status:** resolved

- [x] 開工前，舊打包版整份搬到 `dist` 外（轉換的輸入、也是過關前的備援）；腳本從搬出後的位置讀
- [x] 四份輸出到 `%USERPROFILE%\AutoClick\`，各含 `flow.yaml`、`templates/`、`交付報告.md`
- [x] 自我核對每份全過：app 讀檔讀回→獨立的反向對映轉回舊鍵→與原檔逐步比（步數、每步欄位，去掉 `mode`／`button`／`clicks`）；範本圖逐位元相同、集合相同；`template_pos`、校準主對與備用對（`baseline` 允許 0.05 內的差）、忙碌指示、`run`、`scan_region`、`engine` 逐項相同
- [x] 印出每份步數與範本數；結果記在本票 Comments

## Comments

- 2026-10-11（agent）：舊打包版整份**複製**（不是搬）到 repo 外的 `C:\Users\three\我的電腦\AiProject\AutoClick-舊打包版-2026-10-10\`（698 MB），轉換從這份讀；`app/dist/AutoClick` 原地留著，使用者在重打包前照常能用，13 重打包時才換掉。`convert.py` 跑完四份自我核對全過，輸出在 `%USERPROFILE%\AutoClick\`：
  - 早_簡中 268 步、86 張範本
  - 早_繁中 227 步、82 張範本
  - 晚_簡中 61 步、26 張範本
  - 晚_繁中 61 步、26 張範本

  各含 `flow.yaml`、`templates/`、`交付報告.md`（舊 `.md` 逐位元複製）。新格式該類型沒有的欄位（只找圖／等消失的 `confirm`、`busyCheck`，拖曳的 `updateOrigin`）只在舊值沒有作用時才丟，否則報錯。核對確實會抓錯：故意改一個 `timeout`、刪一張圖，兩項都報出來。轉出的 `flow.yaml` 和 02 原型的 out_all 樣本相比，只多 `engine: {scale_range: [0.6, 1.5]}` 一行。
