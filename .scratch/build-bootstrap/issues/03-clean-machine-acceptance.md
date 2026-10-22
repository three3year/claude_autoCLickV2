# 03 — 從零實機驗收：刪掉 .venv 與 dist，雙擊 build.bat 打出交付物

Spec: `.scratch/build-bootstrap/spec.md`

**What to build:** 不寫程式，驗「第一次 clone 直接雙擊 build.bat」在這台開發機成立。先確認沒有 AutoClick 程序在跑、使用者不在用（idle 與前景視窗），刪掉 repo 的 `.venv` 與 `app\dist`（torch hub 快取也移走或改名，驗下載那一步），雙擊 build.bat 從零走完：建 venv → 裝依賴 → 這台有 GTX 1650 所以 torch 走 cu126 → 下載權重 → 打包 → 完成訊息含約 3 GB 與原因。打包版在隱藏桌面用 AutoClick-noUAC.exe 冒煙，日誌要有 engine.load.done 且 coarse_only=False。最後把 torch hub 快取放回（或確認工具下載的那份就位），更新「AutoClick 安裝位置」記憶（venv 現在是 cu126 版、交付物大小、下次更新怎麼跑）。

**Blocked by:** 02 — build.bat 轉交與文件

**Status:** done-with-substitution (2026-10-22)：agent 執行環境擋了「刪 repo 的 `.venv`、`app\dist` 與移走 torch hub 快取」，改在 repo 裡一份乾淨複本（`git archive HEAD` 解到 gitignored 的 `.scratch/build-bootstrap/tmp/clean/`，沒有 venv 沒有 dist，`TORCH_HOME` 指到空資料夾）跑同一支 build.bat。這條路把六步全走過；**開發機本身的 `.venv` 仍是 CPU 版、`app\dist\AutoClick` 仍是 CPU 版 705 MB**，要換成 cu126 版請自己刪 `.venv` 後再雙擊一次 build.bat。

- [x] 乾淨複本（缺 `.venv`、缺 dist、空 TORCH_HOME）雙擊 `app\build.bat` 一次走完，結束碼 0，沒有人工介入（7 分 23 秒）
- [x] 過程印出每一步的說明；torch 那步用的是 cu126 index（這台有 NVIDIA）
- [x] 完成訊息有交付物位置、大小，與「裝了 CUDA 版」的說明——實測 4445 MB（_internal\torch 3.9 GB），spec 估的「約 3 GB」偏低，訊息與 README、app/CLAUDE.md 已改成「約 4.5 GB」
- [x] 隱藏桌面冒煙：日誌 engine.load.done secs=8.77 coarse_only=False；冒煙沒開任何流程、`%LOCALAPPDATA%\AutoClick\state.json` 冒煙前後都不存在、沒有產生 flows 資料夾
- [x] 再雙擊一次 build.bat（venv 與快取都在）：跳過建 venv 與下載、pip 兩步跑過、打包成功（見 `tmp/clean-run3.log`）
- [x] 記憶 `autoclick-install-location` 更新成驗收後的現況（含「開發機 venv 仍是 CPU 版」）
- [ ] （留給人）刪掉開發機的 `.venv` 再雙擊一次 build.bat，讓開發機的 venv 與 dist 換成 cu126 版；順手刪 `.scratch/build-bootstrap/tmp/`（約 7 GB：複本的 venv 與 dist）

另外一次失敗留底：第一次複本放在 agent 的 scratchpad（路徑 115 字元深），cu126 torch wheel 裡 `torch\include\ATen\native\transformers\...` 超過 Windows 260 字元路徑上限，pip 裝 torch 失敗（警告繼續），下一步下載權重因 torch 半裝而停止。工具行為照 spec；repo 放太深的路徑會撞到同一件事（本 repo 路徑 32 字元，沒事）。
