# Spec：打包自備環境——第一次 clone 直接雙擊 build.bat

Status: ready-for-agent

讓打包不再有前置條件：缺 venv 就建並裝依賴、缺 DINOv2 權重快取就先下載，然後才打包。邏輯住在一支新的 Python 工具 `tools/build`，人雙擊 `app\build.bat` 與 agent 由程式呼叫走同一份；打包版本身的佈局與行為（ADR 0004、0015、0017，README「使用者資料在哪」）完全不變。詞彙以 `app/CONTEXT.md` 為準（打包版、流程存放區、本機狀態資料夾）。

## 需要你決定的

全部在 2026-10-22 的 grilling 中裁定，列在這裡留底。

### 「缺就補」的邏輯住在哪？

決定(2026-10-22)：(a) bat 只轉交，其餘交 Python 腳本。

- (a) 新增 Python 工具 `tools/build`（建議）：build.bat 找到 Python 就交給它；建 venv、裝依賴、下載權重、PyInstaller 全在 Python 裡。人與 agent 共用同一份邏輯，bat 內容極少、不再有 cmd codepage 把 UTF-8 批次檔解析壞的風險。
- (b) 全部寫在 build.bat：集中一檔，但 agent 仍不能呼叫它，`app/CLAUDE.md` 的手動步驟要再寫一份。
- (c) 另拆 setup.bat：第一次 clone 要跑兩個檔。

### 沒有 .venv 時用哪個 Python 建？

決定(2026-10-22)：先 `py -3`（Windows 標準安裝都有），找不到才退 PATH 上的 `python`；建好後檢查版本 ≥3.11（pyproject 的 `requires-python`），不夠就印訊息停止。

### torch 裝哪一版？

決定(2026-10-22)：偵測到 NVIDIA 就裝 CUDA 版，否則 CPU 版。偵測方式是 `nvidia-smi` 找得到且跑得動（代表驅動正常）。CUDA index 用 cu126（驅動需 ≥560、支援的顯卡世代最廣；查證 cu126 與 cu130 都有 torch 2.14.1 Windows 版，cu128 停在 2.11）。引擎程式碼不必改：驗證階段本來就是有 CUDA 用 GPU、沒有用 CPU。

- 代價：有 GPU 的機器 venv 裝 CUDA 版（下載 2–3 GB），從它打出的交付物約 3 GB（CUDA DLL 隨 torch 進 _internal，無法只剔掉 CUDA 部分）。使用者接受：交付物不進 git；在有 NVIDIA 的目標機自動用 GPU，沒有的照常跑 CPU。這台開發機（GTX 1650、driver 591）就是這種情形。

### .venv 已存在時要不要再確認依賴齊全？

決定(2026-10-22)：每次都跑 pip install，靠 pip 自動略過已裝的（多花 10–20 秒）。涵蓋「上次裝 torch 中斷」與「pyproject 日後新增依賴」兩種情形；離線時 pip 失敗只印警告繼續打包。

### 缺 torch hub 快取怎麼補？

決定(2026-10-22)：無頭下載——用 venv 的 Python 建一次引擎的驗證器（Verifier），走的就是 app 載引擎的同一段 torch.hub.load；不開視窗、不碰使用者資料。下載失敗就停止（spec 的 assert 本來就會擋）。

### PyInstaller 怎麼裝？

決定(2026-10-22)：pyproject 新增 `build` extra（含 pyinstaller），工具裝 `.[app,dev,build]`；依賴清單只在 pyproject 一份。

### 舊 dist 怎麼處理？

決定(2026-10-22)：統一成直接覆蓋（PyInstaller `--noconfirm`）。`app/CLAUDE.md` 要 agent 打到 dist-new 再把舊版改名保留的流程廢止。

### 打完做到哪一步算成功？

決定(2026-10-22)：只確認 exe 存在，印出資料夾大小與（有 GPU 時）變大的原因；不自動冒煙。好不好用靠人開起來看日誌（README 已寫）。

### 測試接縫落在哪？

決定(2026-10-22)：一個純函式——環境事實 → 有序步驟清單；執行器只照清單跑 subprocess。測試餵事實、斷言清單，不真的建 venv、下載或打包。

## Problem Statement

第一次 clone 這個 repo 的人照 README 雙擊 `app\build.bat` 一定失敗：它寫死用 `..\.venv\Scripts\python`，但乾淨的機器沒有 `.venv`；就算有，`AutoClick.spec` 開頭還會 assert 本機 torch hub 快取存在，而快取只有「先從原始碼開過一次 app 等引擎載完」才會有。這兩個前置條件散在 README 兩段，沒有一處寫「第一次 clone 照這個順序」。2026-10-22 這台開發機重 clone 後就撞上這件事（沒有 `.venv`，記憶裡的舊安裝位置也不在了），花了一輪才釐清是環境不是產品。另一邊，agent 不能由程式呼叫 build.bat（cmd 用錯 codepage 解析 UTF-8 批次檔），所以 `app/CLAUDE.md` 另寫一套手動步驟（打到 dist-new 再改名），跟 build.bat 的覆蓋行為不一致，兩份邏輯各自演進。

## Solution

一支新的 Python 工具 `tools/build` 把「準備環境 → 打包」做成一條路：探測環境事實（有沒有 `.venv`、找得到哪個 Python 與版本、`nvidia-smi` 跑不跑得動、torch hub 快取在不在、舊 dist 在不在），由一個純函式排出要做的步驟（建 venv、pip install extras、pip install torch 到對的 index、無頭下載 DINOv2、PyInstaller 覆蓋 dist、確認 exe），再逐步執行並即時印出進度。`app\build.bat` 瘦成找到 Python 就轉交；agent 直接跑同一支工具。第一次 clone 雙擊 build.bat 就能從零打出交付物；以後每次雙擊都順便補齊缺的東西。README 的打包段改成一句「第一次 clone 直接雙擊 build.bat」，`app/CLAUDE.md` 的 agent 打包法改成跑這支工具。

## User Stories

1. 身為第一次 clone 這個 repo 的使用者，我要雙擊 `app\build.bat` 就從零打出交付物，這樣不必先讀 README 安裝段、建 venv、開一次 app。
2. 身為使用者，我要 build.bat 在缺 `.venv` 時自己用機器上的 Python 建一個，這樣不必知道 venv 是什麼。
3. 身為使用者，我要機器上的 Python 版本不夠（低於 3.11）或根本沒裝時，得到一句清楚的訊息說要裝哪個版本，這樣不會在後面某個 pip 錯誤裡迷路。
4. 身為使用者，我要工具每次都把依賴補齊（含上次中斷的、pyproject 新增的），這樣不會在 PyInstaller 階段看到難懂的 import 錯誤。
5. 身為有 NVIDIA 顯卡的使用者，我要工具自動裝 CUDA 版 torch，這樣從原始碼跑 app 時引擎用 GPU。
6. 身為有 NVIDIA 顯卡的使用者，我要打完時被告知交付物約 3 GB 與原因，這樣不會以為打壞了。
7. 身為沒有 NVIDIA 顯卡的使用者，我要工具裝 CPU 版 torch，這樣不會白下載 2–3 GB 又用不到。
8. 身為使用者，我要缺 DINOv2 權重時工具自己下載，這樣不必先開一次 app 再關掉。
9. 身為使用者，我要下載權重時不開任何視窗、不動我的流程與本機狀態，這樣打包不會干擾正在用的 AutoClick。
10. 身為使用者，我要離線時只要 venv 裡依賴與快取都齊了就照常打包，這樣沒網路也能重新打包。
11. 身為使用者，我要離線且缺東西時得到一句「缺什麼、需要網路」的訊息，這樣知道該做什麼。
12. 身為使用者，我要工具每一步開始時印出它在做什麼（建 venv、裝依賴、下載權重、打包），這樣等幾分鐘時知道卡在哪。
13. 身為使用者，我要打包完印出交付物的位置與資料夾大小，這樣知道去哪拿、要搬多大。
14. 身為使用者，我要重新打包直接換掉舊的 dist，這樣不會累積好幾個 700 MB 到 3 GB 的舊版。
15. 身為使用者，我要打包時 AutoClick 還開著的話得到提示（檔案被鎖、請先關掉），這樣不會以為是別的錯。
16. 身為使用者，我要 build.bat 失敗時視窗停住讓我看到訊息，這樣雙擊後不會一閃就關。
17. 身為 agent，我要由程式呼叫同一支工具打包，這樣不必再手動拼 PyInstaller 指令與改名流程。
18. 身為 agent，我要工具以結束碼回報成敗（0 成功、非 0 失敗），這樣能在腳本裡判斷。
19. 身為 agent，我要 `app/CLAUDE.md`「建置與部署」只寫一條打包法（跑這支工具），這樣不會跟 build.bat 行為不一致。
20. 身為維護者，我要 PyInstaller 列在 pyproject 的 extra 裡，這樣依賴清單只有一份。
21. 身為維護者，我要「環境事實 → 步驟清單」是純函式並有測試，這樣改偵測或步驟順序時測試會擋。
22. 身為維護者，我要 build.bat 只含 ASCII，這樣 cmd codepage 問題不會再回來、agent 必要時也能呼叫它。
23. 身為讀 README 的人，我要「打包與部署」開頭就是「第一次 clone 直接雙擊 build.bat」，這樣不必在安裝段與打包段之間來回對。
24. 身為讀 README 的人，我要安裝（原始碼版）段仍保留手動步驟，這樣只想從原始碼跑、不打包的人也知道怎麼裝。

## Implementation Decisions

- **新工具 `tools/build`**：與 `tools/flow_check` 同一種套件佈局（可用 `python tools/build` 執行），可在任何 ≥3.11 的系統 Python 下啟動（只用標準庫；venv 裡的套件一律經 subprocess 用 venv 的 Python 跑）。
- **環境事實**（探測結果，一個小資料結構）：venv 的 Python 路徑（沒有則空）、找到的系統 Python（`py -3` 優先，再 `python`）與其版本、`nvidia-smi` 是否跑得動、torch hub 快取（`TORCH_HOME` 或使用者資料夾 `.cache\torch\hub\checkpoints`）是否存在、舊 dist 是否存在。探測是唯一碰環境的讀取；每項事實都是純值。
- **步驟清單**（純函式，唯一接縫）：事實 → 有序步驟，每步是「說明一句 ＋ 要跑的指令（argv 與工作目錄）＋ 失敗時的處置（停止／警告繼續）」；或是一個「拒絕」（找不到 Python、版本不夠），附給人看的訊息。順序固定：
  1. 缺 venv → 用系統 Python 建 `.venv`（`python -m venv`）。
  2. 一律 → venv 的 pip 升級、pip install `.[app,dev,build]`（失敗＝警告繼續）。
  3. 一律 → pip install torch，`nvidia-smi` 跑得動用 cu126 index、否則 cpu index（失敗＝警告繼續）。index 網址是工具裡的常數。
  4. 缺快取 → venv 的 Python 執行一行：匯入引擎的驗證器並建構一次（走 app 同一段 torch.hub.load；失敗＝停止）。
  5. 一律 → 在 app 目錄以 venv 的 Python 跑 PyInstaller `--noconfirm` 打 `AutoClick.spec`（失敗＝停止）。
  6. 一律 → 確認交付物 exe 存在、量資料夾大小（失敗＝停止）。
- **執行器**：照清單跑，每步前印說明、後印結果；輸出用 UTF-8。結束碼 0／1。打包階段失敗且舊 dist 的 exe 被鎖住（PermissionError／存取被拒）時，訊息提示先關掉 AutoClick。有 GPU（裝了 CUDA 版）時完成訊息附一句交付物變大的原因。
- **`app\build.bat`**：只含 ASCII；`cd` 到 repo 根，依序試 `py -3` 與 `python` 執行 `tools\build`，結束後 `pause` 讓視窗停住。不再自己裝 PyInstaller、不再寫死 venv 路徑。
- **pyproject**：optional-dependencies 新增 `build = ["pyinstaller"]`。
- **AutoClick.spec**：不改（assert 快取存在仍在；工具保證它成立）。
- **`app/CLAUDE.md`「建置與部署」**：使用者與 agent 的打包法合併成一條「跑 `tools/build`」；刪 dist-new 改名流程與「build.bat 由程式呼叫會壞編碼」的坑（bat 已 ASCII 化，仍建議 agent 直接跑工具）；冒煙法、UAC 原因、必須 onedir、`upx=False` 等保留。
- **README**：「打包與部署」開頭改成「第一次 clone 直接雙擊 `app\build.bat`，缺的環境它自己補（約 3–5 分鐘 ＋ 第一次下載時間）」，刪「打包前先從原始碼啟動過一次 app」與「PyInstaller 不在 extras 裡」兩句；交付物表加一句「從有 NVIDIA 的機器打約 3 GB、沒有的約 700 MB」。「安裝（原始碼版）」保留手動步驟，補一句「只想打包可以略過這段，直接看打包與部署」。
- **記憶**：不在 spec 範圍；實作完成後 agent 自行更新打包現況的記憶。

## Testing Decisions

- 好的測試只看外部行為：餵一組事實、斷言步驟清單（哪幾步、順序、每步的 argv 關鍵片段、失敗處置），不看工具內部怎麼探測。
- `tools/tests` 新增一支測試，覆蓋：乾淨機器（缺 venv、缺快取、無 GPU）→ 六步全有、torch 走 cpu index；有 GPU → cu126 index；venv 與快取都在 → 跳過建 venv 與下載、pip 仍每次跑；找不到 Python → 拒絕並有訊息；版本 3.10 → 拒絕；pip 步驧標成「警告繼續」、下載與打包標成「停止」。
- 一支靜態防線：`app\build.bat` 全為 ASCII。
- 文件對照測試（既有）會自動擋 README 與 `app/CLAUDE.md` 裡 `tools/build` 路徑與指令寫錯。
- 先例：`tools/tests/test_flow_check.py`（工具層測試、用暫存目錄不 mock）、影片轉流程的「計畫」測試（餵資料斷言計畫，不執行）。
- 不寫會真的建 venv、下載或打包的測試；實機驗收一次：刪掉 `.venv` 與 dist 後雙擊 build.bat 從零打出交付物，開起來看日誌 engine.load.done 且 coarse_only=False。

## Out of Scope

- 打包後自動冒煙（隱藏桌面啟動 noUAC exe）。
- 保留舊版 dist 或只留最近一版。
- 打包專用的第二個 venv（永遠 CPU 版以縮小交付物）。
- 交付物瘦身（剔除 CUDA DLL、onefile、upx）。
- exe 簽章、防毒誤擋的處理。
- 目標機 GPU 相容性保證（哪些顯卡世代、驅動版本能真的用到 CUDA）。
- 把工具接進 CI 或排程。
- 第一次 clone 之外的「安裝」情境（例如把打包版部署到別台機器的流程，README 已寫、不變）。

## Further Notes

- 2026-10-22 這台開發機已照 README 手動重建 `.venv`（CPU 版 torch 2.14.1）並打包成功（705 MB、冒煙通過）。實作完成後實機驗收會刪掉這份 venv 重來；因為這台有 GTX 1650，驗收後 venv 會變成 cu126 版、交付物約 3 GB。
- torch hub 快取在使用者資料夾 `.cache\torch\hub\`，與 `TORCH_HOME` 環境變數的關係沿用 `AutoClick.spec` 現有的判斷。
- 權重下載那一步走引擎的驗證器而不是另寫下載程式：引擎改模型時這裡自動跟著，不會下載到過期的權重。
