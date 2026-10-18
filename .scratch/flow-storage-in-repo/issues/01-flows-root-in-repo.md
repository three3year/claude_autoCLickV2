# 01 — 流程存放區改成專案內 flows/

**What to build:** `流程存放區`從使用者資料夾底下的 `AutoClick` 改成 repo 根目錄的 `flows/`，整個資料夾不進版控。從原始碼執行 app 時，開檔對話框和新流程第一次存檔的對話框都開在 `<repo>/flows/`（不存在就建）。打包版從 exe 往上找 repo：找到就用同一個 `flows/`，找不到就退回 `%USERPROFILE%\AutoClick\`。影片轉流程工具沒指定輸出位置時，也把流程建在存放區。文件、agent 文件和決策紀錄同步改成這個位置。見 [spec](../spec.md)「Solution」「Implementation Decisions」。

**Blocked by:** None — can start immediately

**Status:** done

- [x] 存放區只由路徑模組的 `flows_root()` 決定：原始碼執行回 `<repo 根>/flows`；打包版從 exe 所在資料夾逐層往上，找到底下有本專案 `app` 路徑模組原始檔的那層，回該層的 `flows`；找到磁碟根都沒有就回 `%USERPROFILE%\AutoClick`
- [x] 影片轉流程工具寫死的預設輸出拿掉，改呼叫 `flows_root()`；`--out` 與計畫的 `out` 照舊優先
- [x] `.gitignore` 加根目錄 `flows/`
- [x] 路徑模組測試：原始碼執行、打包版 exe 在假專案樹底下、打包版往上找不到專案（取代原本「流程預設位置在使用者資料夾」那支），三種情況各一支
- [x] 影片轉流程工具測試：沒給 `--out`、計畫也沒寫 `out` 時，輸出位置＝`flows_root()`
- [x] 全套測試綠燈（app 全套會開 Tk 視窗：照 memory 在隱藏桌面跑，或先確認使用者不在）
- [x] 同步文件：README、打包腳本與打包設定檔的註解、路徑模組的說明、`video-to-flow` skill 與轉換計畫格式裡的預設輸出位置
- [x] 新寫 ADR 0017：存放區在 repo 內但不進版控、打包版往上找 repo 的方式與退回位置；說明它取代 project-cleanup 票 09 的位置決定（ADR 0015 不必改）
- [x] 從原始碼開 app，開檔對話框開在 `<repo>/flows/`（用驗證腳本或冒煙確認，不動使用者真的流程）

## Comments

- 2026-10-18 完成。`apppaths.flows_root()` 以 `app/apppaths.py` 當 repo 記號往上找；影片轉流程拿掉
  `DEFAULT_OUT`。另加 `tools/tests/conftest.py` 的 autouse 夾具：spec 說 conftest 已換掉 `flows_root`，
  但那只對 `app/tests` 成立，tools 的測試沒換（紅燈那輪真的寫進了 `%USERPROFILE%\AutoClick\日常`，
  已移到 scratchpad）。審查後把舊說法「流程預設位置」全改成「流程存放區」（含選範本對話框的提示文字）。
  全套 1101 passed（隱藏桌面）。對話框起點：原始碼執行 `flows_root()`＝`<repo>\flows`，
  模擬打包版 exe 在 `app\dist\AutoClick\`、`app\dist-new\AutoClick\` 都回同一個。
