# 打包版佈局與流程存放位置

Type: grilling
Status: resolved

## Question

profile 退場後打包版長什麼樣、流程放哪？
- `dist/AutoClick/` 底下還有什麼：exe（UAC／noUAC 兩個）、`_internal/`、`default_config.yaml`。四份流程資料夾放
  `dist/AutoClick/flows/<名稱>/` 還是使用者自己選的位置（例如 Documents）？重打包時 `--noconfirm` 會刪整個 dist，
  使用者資料放在裡面每次都要先搬（見 memory）；放外面就沒這問題。
- app 本機狀態（上次開的流程路徑、視窗位置）存哪：exe 旁、`%APPDATA%\AutoClick\`、還是不存。
- 檔案日誌 `autoclick.log` 位置。
- 「開檔」對話框：選資料夾（`flow.yaml` 所在）還是選 `flow.yaml` 檔；雙擊關聯？
- `build.bat` 與 `AutoClick.spec` 的改法：不再建立 profiles/、不再複製 config.yaml；torch_home 照舊。
- 引擎參數要不要在打包版旁留一份可改的預設（使用者前面選「內建預設＋流程覆蓋」，沒有全域檔；確認）。

Answer：佈局樹＋位置決定；進 B 階段 spec。

## Answer

（2026-10-11 grilling）

**佈局**

```
dist\AutoClick\                     打包產物，沒有任何使用者資料
  AutoClick.exe / AutoClick-noUAC.exe
  _internal\                        引擎內建預設參數（subject_detection\default_config.yaml）、torch_home\
%USERPROFILE%\AutoClick\            流程的預設位置（本機：C:\Users\three\AutoClick\，不在 OneDrive）
  <流程名>\
    flow.yaml
    templates\*.png
    .cache\
    交付報告.md                     影片轉流程產的；app 不讀不寫，存檔不動它
%LOCALAPPDATA%\AutoClick\           本機狀態 state.json（只記上次開的流程）＋ autoclick.log
<repo>\.local\                      從原始碼執行時的本機狀態與日誌（不進 git）
```

**決定**

- 打包版只有 exe 兩個與 `_internal\`：重新打包／部署＝整個資料夾換掉，不必再搬使用者資料。
- 流程預設位置 `%USERPROFILE%\AutoClick\`：四份在用流程轉換後放這裡；開檔與新流程第一次存檔的對話框從這裡開
  （資料夾不存在就建）。不放「文件」：本機的文件是 OneDrive 同步資料夾，存檔時可能遇到上傳鎖檔、
  範本圖被「隨選即用」變成雲端佔位檔。中文路徑不是問題（引擎與 app 讀寫圖都走 Unicode 安全的 imdecode／imencode）。
- `交付報告.md` 住在流程資料夾裡：流程不在 git，修改流程的 agent 要靠它知道某個框、某個分岔為什麼長那樣
  （例：晚_簡中 的待办铃铛框是早晚兩次位置的聯集）。四份舊 `.md` 由轉換工具搬進去。
- 開檔：一般開檔視窗、篩選 `flow.yaml`，開它所在的資料夾（Tk 在 Windows 的選資料夾視窗是舊式樹狀、不好用）。
  不做檔案關聯，也不做命令列參數。
- 本機狀態只記上次開的流程；主視窗維持現在的固定開啟大小，不記位置與大小（ADR 0015 原寫「與視窗位置」，已改）。
- 狀態與日誌放 `%LOCALAPPDATA%\AutoClick\`，重新打包不會刪掉日誌；從原始碼執行改放 repo `.local\`，
  agent 冒煙開過的測試流程不會變成打包版下次自動開的那份。
- 引擎參數不在 exe 旁放可改檔，維持「內建預設＋流程 `engine:` 段」兩層（確認 ADR 0015）。

**給格式階段 spec 的連帶事項**

- `build.bat`：刪掉建立 `profiles\arknights` 與複製 `config.yaml` 的步驟，結尾說明改成「部署＝整個資料夾換掉」。
  `AutoClick.spec` 不變（`default_config.yaml` 與 torch_home 照舊進 `_internal`）。
- `applog` 與執行器的預設日誌路徑、`profile_store.data_root()` 的兩種模式（frozen／原始碼）改成上面兩個位置；
  `.gitignore` 加 `.local/`。
- 格式階段第一次重新打包前，舊打包版（含 `profiles\arknights\flows\` 四份舊流程）先整份搬到 `dist` 外：
  它同時是轉換工具的輸入與過關前的備援（[階段切法與順序](01-phases-and-order.md)）。過關後 memory
  「重新打包前把使用者資料移出 dist」就作廢。
- 轉換工具的輸出位置與舊 `.md` 的去向由本票定，見[轉換工具規則與驗收](11-converter-rules-and-acceptance.md)。
