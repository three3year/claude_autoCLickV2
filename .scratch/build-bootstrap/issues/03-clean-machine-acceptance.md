# 03 — 從零實機驗收：刪掉 .venv 與 dist，雙擊 build.bat 打出交付物

Spec: `.scratch/build-bootstrap/spec.md`

**What to build:** 不寫程式，驗「第一次 clone 直接雙擊 build.bat」在這台開發機成立。先確認沒有 AutoClick 程序在跑、使用者不在用（idle 與前景視窗），刪掉 repo 的 `.venv` 與 `app\dist`（torch hub 快取也移走或改名，驗下載那一步），雙擊 build.bat 從零走完：建 venv → 裝依賴 → 這台有 GTX 1650 所以 torch 走 cu126 → 下載權重 → 打包 → 完成訊息含約 3 GB 與原因。打包版在隱藏桌面用 AutoClick-noUAC.exe 冒煙，日誌要有 engine.load.done 且 coarse_only=False。最後把 torch hub 快取放回（或確認工具下載的那份就位），更新「AutoClick 安裝位置」記憶（venv 現在是 cu126 版、交付物大小、下次更新怎麼跑）。

**Blocked by:** 02 — build.bat 轉交與文件

**Status:** ready-for-agent

- [ ] 刪掉 `.venv`、`app\dist`、移走 torch hub 快取後，雙擊 `app\build.bat` 一次走完，結束碼 0，沒有人工介入
- [ ] 過程印出每一步的說明；torch 那步用的是 cu126 index（這台有 NVIDIA）
- [ ] 完成訊息有交付物位置、大小，與「裝了 CUDA 版所以約 3 GB」的說明
- [ ] 隱藏桌面冒煙：日誌 engine.load.done 且 coarse_only=False；冒煙沒開任何流程、沒動 `%LOCALAPPDATA%\AutoClick\state.json`
- [ ] 再雙擊一次 build.bat（venv 與快取都在）：跳過建 venv 與下載、pip 兩步跑過、打包成功，確認「每次雙擊都順便補齊」
- [ ] 記憶 `autoclick-install-location` 更新成驗收後的現況
