# 打包版佈局與流程存放位置

Type: grilling
Status: open

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
