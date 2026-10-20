# 07 — 引擎刪多張圖登錄路徑

**What to build:** 引擎只剩單張範本：刪多張圖對齊與穩定度遮罩，遮罩只剩單張梯度啟發式（粗篩、DINOv2 驗證、比色不動）。載入範本清單只接受「範本名 → 一個圖檔路徑」，給清單就報錯；引擎參數的遮罩策略鍵退場，交付了就報錯。綁舊集真實影格的引擎測試改用新集對應案例。刪完重跑新集，結果跟基線一致。見 [spec](../spec.md)「Implementation Decisions」的引擎刪多張圖登錄路徑與測試改指兩段（ADR 0016 決策 1）。

**Blocked by:** 06 — 建立基線

**Status:** resolved

- [x] 一個範本給多張圖路徑 → 報錯；引擎參數帶遮罩策略鍵 → 報錯（引擎公開介面測試）
- [x] 單張圖範本照常登錄、查詢；現有遮罩與步行骨架測試只刪多張圖部分
- [x] 舊快取比對資訊少了遮罩策略後失效、重建一次；app 讀取流程的背景預載照常完成（app 測試綠）
- [x] 「同款多個／小圖示不被雜訊峰擠出」「比色只剩真正目標」兩組改用新集對應類型的案例、仍綠
- [x] 只測舊多張圖素材的 profile 測試在本票刪掉（它測的就是被刪的路徑）；舊集與 `profiles/` 本身留到 08
- [x] 重跑新集：跟 06 基線一致（已知失敗可以變少，不能變多）
- [x] 全套測試綠（app 全套照 memory 在隱藏桌面跑，或先確認使用者不在玩遊戲）

## Comments

- 2026-10-21 agent：
  - 引擎：`registration.py` 刪掉跨拍攝對齊與穩定度遮罩，只剩單張梯度啟發式；`load_or_register` 收一個圖檔路徑；比對資訊版本 3、登錄相關鍵只剩 `scale_range`。`library.py` 的 `Template.capture_paths` 改成 `image_path`，`make_library` 給清單就 `ValueError`（「一張圖」）；引擎參數帶 `mask_strategy` 也 `ValueError`。`default_config.yaml` 拿掉 `mask_strategy`（flowfile 以內建預設鍵當白名單，流程寫了這鍵也會被擋）。
  - 舊快取：`flows/*/.cache/registered/*/meta.json` 比對資訊帶 `mask_strategy`，跟新格式不同 → 失效重建一次（`test_auto_registration` 新測試；app 讀取流程的背景預載照常）。
  - 測試：遮罩與步行骨架只刪多張圖部分；新增「給清單報錯」「帶遮罩策略鍵報錯」「內建預設沒有遮罩策略鍵」「舊快取失效重建一次」。「小圖示不被雜訊峰擠出」改用 pos02／pos08／conf08，「同款多個」改用 multi01／multi03／multi07，「預期尺度 1 開比色」改用 color04／color10／color01，「開比色後只剩真正的目標」改用新集 10 個比色案例（已知失敗除外）；`test_arknights_profile.py`（只測舊多張圖素材）與「明日方舟 profile 設定檔有比色門檻」刪掉。`tests/synth.py` 的 `template_list`／`write_profile` 改一範本一張圖。
  - 文件：README 的「資料夾放多張圖」「`mask_strategy`」兩處、`app/CLAUDE.md` 的「引擎 `multi_capture` 能力保留」改掉（README 其他過期內容留給文件階段）。
  - 重跑新集：`其他案例 80/80  misses: 0  false_alarms: 0  |  已知失敗 0/17  misses: 9  false_alarms: 8  |  OK`，逐案例判定跟 06 基線**完全一致**。
  - 全套：引擎 78 passed、tools 284 passed、app 751 passed（隱藏桌面）。
